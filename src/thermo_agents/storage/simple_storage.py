"""
Простое Key-Value хранилище с поддержкой TTL.

Упрощенная замена сложной Message Queue системы для AgentStorage.
Предоставляет простой, быстрый и надежный интерфейс для хранения
и извлечения данных с опциональным временем жизни.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Type, Union, TypeVar
from dataclasses import dataclass

T = TypeVar('T')


@dataclass
class StorageEntry:
    """Запись в хранилище с TTL."""
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None

    @property
    def is_expired(self) -> bool:
        """Проверить, истекло ли время жизни записи."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at


class SimpleAgentStorage:
    """
    Простое Key-Value хранилище с поддержкой TTL.

    Упрощенная замена сложной Message Queue системы.
    Обеспечивает быстрый и надежный доступ к данным.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        """
        Инициализация хранилища.

        Args:
            default_ttl_seconds: Время жизни по умолчанию в секундах
        """
        self._storage: Dict[str, StorageEntry] = {}
        self._lock = threading.RLock()
        self.default_ttl = timedelta(seconds=default_ttl_seconds)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Сохранить значение с опциональным TTL.

        Args:
            key: Ключ
            value: Значение
            ttl_seconds: Время жизни в секундах
        """
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        elif self.default_ttl:
            expires_at = datetime.now() + self.default_ttl

        entry = StorageEntry(
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at
        )

        with self._lock:
            self._storage[key] = entry

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получить значение или default.

        Args:
            key: Ключ
            default: Значение по умолчанию

        Returns:
            Значение или default
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                return default

            if entry.is_expired:
                del self._storage[key]
                return default

            return entry.value

    def get_typed(self, key: str, expected_type: Type[T], default: Optional[T] = None) -> Optional[T]:
        """
        Получить значение с проверкой типа.

        Args:
            key: Ключ
            expected_type: Ожидаемый тип
            default: Значение по умолчанию

        Returns:
            Типизированное значение или default

        Raises:
            TypeError: Если тип не совпадает
        """
        value = self.get(key, default)
        if value is not None and not isinstance(value, expected_type):
            raise TypeError(f"Expected {expected_type}, got {type(value)} for key '{key}'")
        return value

    def delete(self, key: str) -> bool:
        """
        Удалить ключ. Возвращает True если ключ существовал.

        Args:
            key: Ключ для удаления

        Returns:
            True если ключ был удален
        """
        with self._lock:
            if key in self._storage:
                del self._storage[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """
        Проверить существование не просроченного ключа.

        Args:
            key: Ключ для проверки

        Returns:
            True если ключ существует и не просрочен
        """
        with self._lock:
            entry = self._storage.get(key)
            return entry is not None and not entry.is_expired

    def clear(self) -> None:
        """Очистить всё хранилище."""
        with self._lock:
            self._storage.clear()

    def cleanup_expired(self) -> int:
        """
        Удалить просроченные записи. Возвращает количество удалённых.

        Returns:
            Количество удалённых записей
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._storage.items()
                if entry.is_expired
            ]

            for key in expired_keys:
                del self._storage[key]

            return len(expired_keys)

    def keys(self, pattern: Optional[str] = None) -> list[str]:
        """
        Получить список активных ключей.

        Args:
            pattern: Опциональный фильтр (wildcard)

        Returns:
            Список активных ключей
        """
        with self._lock:
            active_keys = [
                key for key, entry in self._storage.items()
                if not entry.is_expired
            ]

            if pattern:
                import fnmatch
                return [key for key in active_keys if fnmatch.fnmatch(key, pattern)]

            return active_keys

    def size(self) -> int:
        """
        Количество активных записей.

        Returns:
            Количество активных записей
        """
        with self._lock:
            return sum(1 for entry in self._storage.values() if not entry.is_expired)

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику хранилища.

        Returns:
            Статистика использования
        """
        with self._lock:
            total_entries = len(self._storage)
            active_entries = sum(1 for entry in self._storage.values() if not entry.is_expired)
            expired_entries = total_entries - active_entries

            type_stats = {}
            for entry in self._storage.values():
                type_name = type(entry.value).__name__
                type_stats[type_name] = type_stats.get(type_name, 0) + 1

            return {
                "total_entries": total_entries,
                "active_entries": active_entries,
                "expired_entries": expired_entries,
                "type_distribution": type_stats
            }

    def get_entry_info(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о записи.

        Args:
            key: Ключ

        Returns:
            Информация о записи или None
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                return None

            return {
                "key": key,
                "value_type": type(entry.value).__name__,
                "created_at": entry.created_at.isoformat(),
                "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
                "is_expired": entry.is_expired
            }

    def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        """
        Обновить TTL для существующего ключа.

        Args:
            key: Ключ
            ttl_seconds: Новое время жизни в секундах

        Returns:
            True если TTL обновлен
        """
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                return False

            entry.expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            return True

    def get_all_expired(self) -> Dict[str, Any]:
        """
        Получить все просроченные записи.

        Returns:
            Словарь просроченных записей
        """
        with self._lock:
            expired_entries = {}
            for key, entry in self._storage.items():
                if entry.is_expired:
                    expired_entries[key] = entry.value
            return expired_entries

    def vacuum(self) -> int:
        """
        Принудительная очистка просроченных записей.

        Returns:
            Количество удаленных записей
        """
        return self.cleanup_expired()

    # Backward compatibility методы для Message Queue API

    def start_session(self, agent_id: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Начать сессию (backward compatibility).

        Args:
            agent_id: ID агента
            initial_data: Начальные данные
        """
        session_key = f"session:{agent_id}"
        session_data = {
            "agent_id": agent_id,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            **(initial_data or {})
        }
        self.set(session_key, session_data)

    def update_session(self, agent_id: str, updates: Dict[str, Any]) -> None:
        """
        Обновить сессию (backward compatibility).

        Args:
            agent_id: ID агента
            updates: Обновления
        """
        session_key = f"session:{agent_id}"
        current_session = self.get(session_key)
        if current_session:
            current_session.update(updates)
            self.set(session_key, current_session)

    def get_session(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Получить сессию (backward compatibility).

        Args:
            agent_id: ID агента

        Returns:
            Данные сессии или None
        """
        return self.get(f"session:{agent_id}")

    def send_message(
        self,
        source_agent: str,
        target_agent: str,
        message_type: str,
        correlation_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Отправить сообщение (backward compatibility).

        Args:
            source_agent: Агент-отправитель
            target_agent: Агент-получатель
            message_type: Тип сообщения
            correlation_id: ID корреляции
            payload: Полезная нагрузка

        Returns:
            ID сообщения
        """
        import uuid
        message_id = str(uuid.uuid4())
        message_key = f"message:{target_agent}:{message_id}"

        message_data = {
            "message_id": message_id,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "message_type": message_type,
            "correlation_id": correlation_id,
            "payload": payload or {},
            "created_at": datetime.now().isoformat()
        }

        self.set(message_key, message_data)
        return message_id

    def receive_messages(self, target_agent: str, message_type: Optional[str] = None) -> list:
        """
        Получить сообщения (backward compatibility).

        Args:
            target_agent: Агент-получатель
            message_type: Фильтр по типу сообщения

        Returns:
            Список сообщений
        """
        messages = []
        message_keys = self.keys(f"message:{target_agent}:*")

        for key in message_keys:
            message = self.get(key)
            if message and (message_type is None or message.get("message_type") == message_type):
                messages.append(message)
                # Удаляем сообщение после прочтения
                self.delete(key)

        return messages

    def get_storage_snapshot(self, include_content: bool = False) -> Dict[str, Any]:
        """
        Получить снимок хранилища (backward compatibility).

        Args:
            include_content: Включать содержимое

        Returns:
            Снимок хранилища
        """
        snapshot = {
            "stats": self.get_stats(),
            "keys": self.keys()
        }

        if include_content:
            snapshot["content"] = {}
            for key in self.keys():
                snapshot["content"][key] = self.get(key)

        return snapshot

    def __contains__(self, key: str) -> bool:
        """Проверить наличие ключа."""
        return self.exists(key)

    def __len__(self) -> int:
        """Количество активных записей."""
        return self.size()

    def __str__(self) -> str:
        """Строковое представление."""
        return f"SimpleAgentStorage(size={self.size()})"

    def __repr__(self) -> str:
        """Полное строковое представление."""
        return f"SimpleAgentStorage(active={self.size()}, total={len(self._storage)})"


# Создаем TypedStorage как alias для backward compatibility
class TypedStorage(SimpleAgentStorage):
    """
    Типизированное хранилище (legacy compatibility).

    Использует SimpleAgentStorage как базу.
    """
    pass