"""
Хранилище для обмена данными между агентами (A2A Storage).

РЕФАКТОРИНГ v2.0: Теперь использует SimpleAgentStorage как backend.
Сохраняет backward compatibility с существующим API.

Объединяет сложную Message Queue систему в простое Key-Value хранилище
с поддержкой TTL для архитектуры v2.0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .storage.simple_storage import SimpleAgentStorage


class AgentMessage(BaseModel):
    """Сообщение между агентами."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_agent: str  # Идентификатор агента-отправителя
    target_agent: str  # Идентификатор агента-получателя
    message_type: str  # Тип сообщения (request, response, error)
    payload: Dict[str, Any]  # Данные сообщения
    correlation_id: Optional[str] = None  # ID связанного сообщения
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StorageEntry(BaseModel):
    """Запись в хранилище (legacy compatibility)."""

    key: str  # Ключ для доступа к данным
    value: Any  # Сохраненные данные
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    ttl_seconds: Optional[int] = None  # Time to live в секундах
    metadata: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class AgentStorage:
    """
    Централизованное хранилище для обмена данными между агентами.

    РЕФАКТОРИНГ v2.0: Использует SimpleAgentStorage как backend.
    Сохраняет backward compatibility с существующим API.

    В архитектуре v2.0:
    - SimpleAgentStorage обеспечивает быстрое Key-Value хранение
    - Message passing эмулируется через SimpleAgentStorage
    - Сохраняется совместимость с существующим кодом
    """

    # Backend хранилище
    _backend: SimpleAgentStorage = field(default_factory=SimpleAgentStorage)

    # =============================================================================
    # УПРАВЛЕНИЕ ДАННЫМИ
    # =============================================================================

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None, metadata: Optional[Dict] = None) -> None:
        """
        Сохранить данные в хранилище.

        Args:
            key: Ключ для доступа к данным
            value: Данные для сохранения
            ttl_seconds: Время жизни в секундах (опционально)
            metadata: Дополнительные метаданные
        """
        # Делегируем в SimpleAgentStorage backend
        self._backend.set(key, value, ttl_seconds)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получить данные из хранилища.

        Args:
            key: Ключ для доступа к данным
            default: Значение по умолчанию если ключ не найден

        Returns:
            Сохраненные данные или значение по умолчанию
        """
        # Делегируем в SimpleAgentStorage backend
        return self._backend.get(key, default)

    def delete(self, key: str) -> bool:
        """
        Удалить данные из хранилище.

        Args:
            key: Ключ для удаления

        Returns:
            True если ключ был удален, False если не найден
        """
        # Делегируем в SimpleAgentStorage backend
        return self._backend.delete(key)

    def exists(self, key: str) -> bool:
        """Проверить существование ключа в хранилище."""
        # Делегируем в SimpleAgentStorage backend
        return self._backend.exists(key)

    def clear(self) -> None:
        """Очистить все хранилище."""
        # Делегируем в SimpleAgentStorage backend
        self._backend.clear()

    # =============================================================================
    # ОБМЕН СООБЩЕНИЯМИ
    # =============================================================================

    def send_message(
        self,
        source_agent: str,
        target_agent: str,
        message_type: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """
        Отправить сообщение от одного агента другому.

        Args:
            source_agent: ID агента-отправителя
            target_agent: ID агента-получателя
            message_type: Тип сообщения
            payload: Данные сообщения
            correlation_id: ID связанного сообщения
            metadata: Дополнительные метаданные

        Returns:
            ID отправленного сообщения
        """
        # Делегируем в SimpleAgentStorage backend
        message_id = self._backend.send_message(
            source_agent=source_agent,
            target_agent=target_agent,
            message_type=message_type,
            correlation_id=correlation_id,
            payload=payload
        )

        # Улучшенное логирование для диагностики коммуникации
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"MESSAGE SENT: {source_agent} -> {target_agent} | Type: {message_type} | ID: {message_id} | Correlation: {correlation_id}")

        return message_id

    def send_message_with_ack(
        self,
        source_agent: str,
        target_agent: str,
        message_type: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        ack_timeout: float = 5.0
    ) -> Dict[str, Any]:
        """
        Отправить сообщение с подтверждением получения.

        Args:
            source_agent: ID агента-отправителя
            target_agent: ID агента-получателя
            message_type: Тип сообщения
            payload: Данные сообщения
            correlation_id: ID связанного сообщения
            metadata: Дополнительные метаданные
            ack_timeout: Таймаут ожидания подтверждения

        Returns:
            Результат отправки с информацией о подтверждении
        """
        import asyncio
        import logging
        logger = logging.getLogger(__name__)

        # Добавляем флаг ожидания подтверждения
        if metadata is None:
            metadata = {}
        metadata["requires_ack"] = True
        metadata["ack_sent_at"] = None

        # Отправляем основное сообщение
        message_id = self.send_message(
            source_agent=source_agent,
            target_agent=target_agent,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
            metadata=metadata
        )

        # Проверяем, готов ли целевой агент принять сообщения
        target_session = self.get_session(target_agent)
        if not target_session:
            logger.warning(f"Target agent {target_agent} not active for message {message_id}")
            return {
                "message_id": message_id,
                "status": "sent_but_target_inactive",
                "ack_received": False,
                "warning": f"Target agent {target_agent} not found in active sessions"
            }

        # Логируем отправку с ожиданием подтверждения
        logger.info(f"MESSAGE SENT WITH ACK: {source_agent} -> {target_agent} | Type: {message_type} | ID: {message_id}")

        return {
            "message_id": message_id,
            "status": "sent",
            "ack_received": False,
            "target_active": True
        }

    def acknowledge_message(
        self,
        original_message_id: str,
        ack_source_agent: str,
        ack_status: str = "received"
    ) -> bool:
        """
        Подтвердить получение сообщения.

        Args:
            original_message_id: ID исходного сообщения
            ack_source_agent: Агент, подтверждающий получение
            ack_status: Статус подтверждения

        Returns:
            True если подтверждение успешно отправлено
        """
        import logging
        logger = logging.getLogger(__name__)

        # Ищем исходное сообщение в истории
        original_message = None
        for msg in self._message_history:
            if msg.id == original_message_id:
                original_message = msg
                break

        if not original_message:
            logger.warning(f"Cannot acknowledge unknown message: {original_message_id}")
            return False

        # Отправляем подтверждение
        ack_message = AgentMessage(
            source_agent=ack_source_agent,
            target_agent=original_message.source_agent,
            message_type="acknowledgment",
            payload={
                "original_message_id": original_message_id,
                "original_message_type": original_message.message_type,
                "status": ack_status,
                "ack_timestamp": datetime.now().isoformat()
            },
            correlation_id=original_message.correlation_id,
            metadata={"ack_type": "message_received"}
        )

        self._message_queue.append(ack_message)

        logger.info(f"ACK SENT: {ack_source_agent} -> {original_message.source_agent} | "
                   f"Original: {original_message_id} | Status: {ack_status}")

        return True

    def receive_messages(
        self,
        agent_id: str,
        message_type: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> List[AgentMessage]:
        """
        Получить все сообщения для агента.

        Args:
            agent_id: ID агента-получателя
            message_type: Фильтр по типу сообщения (опционально)
            correlation_id: Фильтр по ID корреляции (опционально)

        Returns:
            Список сообщений для агента
        """
        # Делегируем в SimpleAgentStorage backend
        raw_messages = self._backend.receive_messages(agent_id, message_type)

        # Конвертируем в AgentMessage объекты для совместимости
        messages = []
        for raw_msg in raw_messages:
            message = AgentMessage(
                id=raw_msg.get("message_id"),
                timestamp=datetime.fromisoformat(raw_msg.get("created_at")),
                source_agent=raw_msg.get("source_agent"),
                target_agent=raw_msg.get("target_agent"),
                message_type=raw_msg.get("message_type"),
                payload=raw_msg.get("payload", {}),
                correlation_id=raw_msg.get("correlation_id"),
                metadata={}
            )
            messages.append(message)

        # Улучшенное логирование для диагностики коммуникации
        import logging
        logger = logging.getLogger(__name__)

        if messages:
            for msg in messages:
                logger.debug(f"MESSAGE RECEIVED: {msg.source_agent} -> {agent_id} | Type: {msg.message_type} | ID: {msg.id} | Correlation: {msg.correlation_id}")

                # Дополнительное логирование для критических сообщений
                if msg.message_type in ["individual_search_complete", "sql_ready", "response"]:
                    logger.info(f"IMPORTANT MESSAGE: {msg.source_agent} -> {agent_id} | Type: {msg.message_type} | ID: {msg.id} | Correlation: {msg.correlation_id}")
        else:
            # Логируем отсутствие сообщений для диагностики
            if message_type or correlation_id:
                logger.debug(f"NO MESSAGES FOUND for {agent_id} | Type: {message_type} | Correlation: {correlation_id}")

        return messages

    def get_message_history(self, agent_id: Optional[str] = None, limit: int = 100) -> List[AgentMessage]:
        """
        Получить историю обработанных сообщений.
        
        Args:
            agent_id: Фильтр по ID агента (опционально)
            limit: Максимальное количество сообщений
            
        Returns:
            Список исторических сообщений
        """
        history = self._message_history
        if agent_id:
            history = [
                msg for msg in history 
                if msg.source_agent == agent_id or msg.target_agent == agent_id
            ]
        return history[-limit:]

    def diagnose_message_flow(self, source_agent: str, target_agent: str, message_type: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Диагностировать поток сообщений между агентами.

        Args:
            source_agent: ID агента-отправителя
            target_agent: ID агента-получателя
            message_type: Тип сообщения для поиска
            correlation_id: ID корреляции (опционально)

        Returns:
            Диагностическая информация о потоке сообщений
        """
        import logging
        logger = logging.getLogger(__name__)

        # Ищем сообщения в очереди
        queued_messages = [
            msg for msg in self._message_queue
            if (msg.source_agent == source_agent and
                msg.target_agent == target_agent and
                msg.message_type == message_type and
                (correlation_id is None or msg.correlation_id == correlation_id))
        ]

        # Ищем сообщения в истории
        historical_messages = [
            msg for msg in self._message_history
            if (msg.source_agent == source_agent and
                msg.target_agent == target_agent and
                msg.message_type == message_type and
                (correlation_id is None or msg.correlation_id == correlation_id))
        ]

        # Проверяем активность агентов
        source_session = self.get_session(source_agent)
        target_session = self.get_session(target_agent)

        diagnosis = {
            "source_agent": {
                "id": source_agent,
                "active": source_session is not None,
                "status": source_session.get("status") if source_session else "not_found",
                "last_message": None
            },
            "target_agent": {
                "id": target_agent,
                "active": target_session is not None,
                "status": target_session.get("status") if target_session else "not_found",
                "last_message": None
            },
            "message_flow": {
                "queued_count": len(queued_messages),
                "historical_count": len(historical_messages),
                "total_messages": len(queued_messages) + len(historical_messages)
            },
            "correlation_id": correlation_id,
            "message_type": message_type
        }

        # Добавляем информацию о последних сообщениях
        if queued_messages:
            latest_queued = max(queued_messages, key=lambda m: m.timestamp)
            diagnosis["source_agent"]["last_message"] = {
                "id": latest_queued.id,
                "timestamp": latest_queued.timestamp.isoformat(),
                "status": "queued"
            }

        if historical_messages:
            latest_historical = max(historical_messages, key=lambda m: m.timestamp)
            diagnosis["target_agent"]["last_message"] = {
                "id": latest_historical.id,
                "timestamp": latest_historical.timestamp.isoformat(),
                "status": "delivered"
            }

        # Логируем диагноз
        logger.info(f"MESSAGE FLOW DIAGNOSIS: {source_agent} -> {target_agent} | Type: {message_type} | "
                   f"Queued: {len(queued_messages)} | Historical: {len(historical_messages)} | "
                   f"Source Active: {diagnosis['source_agent']['active']} | Target Active: {diagnosis['target_agent']['active']}")

        return diagnosis

    # =============================================================================
    # УПРАВЛЕНИЕ СЕССИЯМИ
    # =============================================================================

    def start_session(self, agent_id: str, session_data: Optional[Dict] = None) -> None:
        """
        Начать сессию для агента.

        Args:
            agent_id: ID агента
            session_data: Начальные данные сессии
        """
        # Делегируем в SimpleAgentStorage backend
        self._backend.start_session(agent_id, session_data)

    def get_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить данные сессии агента.

        Args:
            agent_id: ID агента

        Returns:
            Данные сессии или None если сессия не найдена
        """
        # Делегируем в SimpleAgentStorage backend
        return self._backend.get_session(agent_id)

    def update_session(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """
        Обновить данные сессии агента.

        Args:
            agent_id: ID агента
            updates: Обновления для сессии
        """
        # Делегируем в SimpleAgentStorage backend
        self._backend.update_session(agent_id, updates)

    def end_session(self, agent_id: str) -> None:
        """
        Завершить сессию агента.

        Args:
            agent_id: ID агента
        """
        # Удаляем сессию из backend
        self._backend.delete(f"session:{agent_id}")

    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =============================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику использования хранилища."""
        # Делегируем в SimpleAgentStorage backend и добавляем legacy поля
        backend_stats = self._backend.get_stats()

        # Эмулируем статистику для совместимости
        session_count = len([key for key in self._backend.keys() if key.startswith("session:")])
        message_count = len([key for key in self._backend.keys() if key.startswith("message:")])

        return {
            "storage_entries": backend_stats["total_entries"],
            "message_queue_size": message_count,
            "message_history_size": 0,  # В v2.0 истории нет
            "active_sessions": session_count,
            "agents": [],  # В v2.0 агенты не отслеживаются отдельно
            **backend_stats
        }

    def cleanup_expired(self) -> int:
        """
        Очистить просроченные записи с TTL.

        Returns:
            Количество удаленных записей
        """
        # Делегируем в SimpleAgentStorage backend
        return self._backend.cleanup_expired()

    def get_storage_snapshot(self, include_content: bool = False) -> Dict[str, Any]:
        """
        Получить снимок состояния хранилища для логирования.

        Args:
            include_content: Включать ли полный контент сообщений и данных

        Returns:
            Словарь с состоянием хранилища
        """
        # Делегируем в SimpleAgentStorage backend
        return self._backend.get_storage_snapshot(include_content)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать хранилище в словарь."""
        return {
            "storage": {k: v.model_dump() for k, v in self._storage.items()},
            "message_queue": [msg.model_dump() for msg in self._message_queue],
            "message_history": [msg.model_dump() for msg in self._message_history],
            "agent_sessions": self._agent_sessions,
            "stats": self.get_stats()
        }

    def from_dict(self, data: Dict[str, Any]) -> None:
        """Восстановить хранилище из словаря."""
        self._storage = {
            k: StorageEntry(**v) for k, v in data.get("storage", {}).items()
        }
        self._message_queue = [
            AgentMessage(**msg) for msg in data.get("message_queue", [])
        ]
        self._message_history = [
            AgentMessage(**msg) for msg in data.get("message_history", [])
        ]
        self._agent_sessions = data.get("agent_sessions", {})


# =============================================================================
# ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ (SINGLETON)
# =============================================================================

_global_storage: Optional[AgentStorage] = None


def get_storage() -> AgentStorage:
    """Получить глобальное хранилище (singleton pattern)."""
    global _global_storage
    if _global_storage is None:
        _global_storage = AgentStorage()
    return _global_storage


def reset_storage() -> None:
    """Сбросить глобальное хранилище."""
    global _global_storage
    _global_storage = AgentStorage()