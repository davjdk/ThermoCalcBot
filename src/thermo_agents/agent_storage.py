"""
Хранилище для обмена данными между агентами (A2A Storage).

Реализует паттерн Storage из PydanticAI для обеспечения слабой связанности
между агентами и обмена состоянием через структурированные сообщения.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


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
    """Запись в хранилище."""

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
    
    Основано на принципах Storage Architecture из PydanticAI:
    - Агенты не вызывают друг друга напрямую
    - Обмен происходит через структурированные сообщения
    - Состояние сохраняется между вызовами
    """

    # Хранилище данных
    _storage: Dict[str, StorageEntry] = field(default_factory=dict)
    
    # Очередь сообщений между агентами
    _message_queue: List[AgentMessage] = field(default_factory=list)
    
    # История обработанных сообщений
    _message_history: List[AgentMessage] = field(default_factory=list)
    
    # Активные сессии агентов
    _agent_sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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
        entry = StorageEntry(
            key=key,
            value=value,
            ttl_seconds=ttl_seconds,
            metadata=metadata or {}
        )
        self._storage[key] = entry

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получить данные из хранилища.
        
        Args:
            key: Ключ для доступа к данным
            default: Значение по умолчанию если ключ не найден
            
        Returns:
            Сохраненные данные или значение по умолчанию
        """
        entry = self._storage.get(key)
        if entry is None:
            return default
            
        # Проверка TTL
        if entry.ttl_seconds is not None:
            elapsed = (datetime.now() - entry.created_at).total_seconds()
            if elapsed > entry.ttl_seconds:
                del self._storage[key]
                return default
                
        return entry.value

    def delete(self, key: str) -> bool:
        """
        Удалить данные из хранилища.
        
        Args:
            key: Ключ для удаления
            
        Returns:
            True если ключ был удален, False если не найден
        """
        if key in self._storage:
            del self._storage[key]
            return True
        return False

    def exists(self, key: str) -> bool:
        """Проверить существование ключа в хранилище."""
        return key in self._storage

    def clear(self) -> None:
        """Очистить все хранилище."""
        self._storage.clear()

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
        message = AgentMessage(
            source_agent=source_agent,
            target_agent=target_agent,
            message_type=message_type,
            payload=payload,
            correlation_id=correlation_id,
            metadata=metadata or {}
        )
        self._message_queue.append(message)
        return message.id

    def receive_messages(self, agent_id: str, message_type: Optional[str] = None) -> List[AgentMessage]:
        """
        Получить все сообщения для агента.
        
        Args:
            agent_id: ID агента-получателя
            message_type: Фильтр по типу сообщения (опционально)
            
        Returns:
            Список сообщений для агента
        """
        messages = []
        remaining_queue = []
        
        for msg in self._message_queue:
            if msg.target_agent == agent_id:
                if message_type is None or msg.message_type == message_type:
                    messages.append(msg)
                    self._message_history.append(msg)
                else:
                    remaining_queue.append(msg)
            else:
                remaining_queue.append(msg)
                
        self._message_queue = remaining_queue
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
        self._agent_sessions[agent_id] = session_data or {}

    def get_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить данные сессии агента.
        
        Args:
            agent_id: ID агента
            
        Returns:
            Данные сессии или None если сессия не найдена
        """
        return self._agent_sessions.get(agent_id)

    def update_session(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """
        Обновить данные сессии агента.
        
        Args:
            agent_id: ID агента
            updates: Обновления для сессии
        """
        if agent_id in self._agent_sessions:
            self._agent_sessions[agent_id].update(updates)

    def end_session(self, agent_id: str) -> None:
        """
        Завершить сессию агента.
        
        Args:
            agent_id: ID агента
        """
        if agent_id in self._agent_sessions:
            del self._agent_sessions[agent_id]

    # =============================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # =============================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику использования хранилища."""
        return {
            "storage_entries": len(self._storage),
            "message_queue_size": len(self._message_queue),
            "message_history_size": len(self._message_history),
            "active_sessions": len(self._agent_sessions),
            "agents": list(self._agent_sessions.keys())
        }

    def cleanup_expired(self) -> int:
        """
        Очистить просроченные записи с TTL.
        
        Returns:
            Количество удаленных записей
        """
        expired_keys = []
        now = datetime.now()
        
        for key, entry in self._storage.items():
            if entry.ttl_seconds is not None:
                elapsed = (now - entry.created_at).total_seconds()
                if elapsed > entry.ttl_seconds:
                    expired_keys.append(key)
                    
        for key in expired_keys:
            del self._storage[key]
            
        return len(expired_keys)

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