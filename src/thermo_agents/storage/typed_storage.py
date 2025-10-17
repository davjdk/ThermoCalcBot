"""
Специализированные типизированные хранилища.

Предоставляют типобезопасные интерфейсы для работы с определенными типами данных.
"""

from typing import Any, Dict, List, Optional, TypeVar

from .simple_storage import SimpleAgentStorage

T = TypeVar('T')


class StringStorage:
    """
    Хранилище для строковых данных.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._storage = SimpleAgentStorage(default_ttl_seconds)

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        """Сохранить строку."""
        if not isinstance(value, str):
            raise TypeError(f"Expected str, got {type(value)}")
        self._storage.set(key, value, ttl_seconds)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получить строку."""
        value = self._storage.get(key, default)
        if value is not None and not isinstance(value, str):
            raise TypeError(f"Expected str, got {type(value)}")
        return value

    def delete(self, key: str) -> bool:
        """Удалить ключ."""
        return self._storage.delete(key)

    def exists(self, key: str) -> bool:
        """Проверить существование."""
        return self._storage.exists(key)

    def clear(self) -> None:
        """Очистить."""
        self._storage.clear()

    def size(self) -> int:
        """Размер."""
        return self._storage.size()

    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """Получить ключи."""
        return self._storage.keys(pattern)


class DictStorage:
    """
    Хранилище для словарей.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._storage = SimpleAgentStorage(default_ttl_seconds)

    def set(self, key: str, value: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
        """Сохранить словарь."""
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict, got {type(value)}")
        self._storage.set(key, value, ttl_seconds)

    def get(self, key: str, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Получить словарь."""
        value = self._storage.get(key, default)
        if value is not None and not isinstance(value, dict):
            raise TypeError(f"Expected dict, got {type(value)}")
        return value

    def delete(self, key: str) -> bool:
        """Удалить ключ."""
        return self._storage.delete(key)

    def exists(self, key: str) -> bool:
        """Проверить существование."""
        return self._storage.exists(key)

    def clear(self) -> None:
        """Очистить."""
        self._storage.clear()

    def size(self) -> int:
        """Размер."""
        return self._storage.size()

    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """Получить ключи."""
        return self._storage.keys(pattern)


class ListStorage:
    """
    Хранилище для списков.
    """

    def __init__(self, default_ttl_seconds: int = 3600):
        self._storage = SimpleAgentStorage(default_ttl_seconds)

    def set(self, key: str, value: List[Any], ttl_seconds: Optional[int] = None) -> None:
        """Сохранить список."""
        if not isinstance(value, list):
            raise TypeError(f"Expected list, got {type(value)}")
        self._storage.set(key, value, ttl_seconds)

    def get(self, key: str, default: Optional[List[Any]] = None) -> Optional[List[Any]]:
        """Получить список."""
        value = self._storage.get(key, default)
        if value is not None and not isinstance(value, list):
            raise TypeError(f"Expected list, got {type(value)}")
        return value

    def append(self, key: str, item: Any, ttl_seconds: Optional[int] = None) -> None:
        """Добавить элемент в список."""
        current_list = self.get(key, [])
        current_list.append(item)
        self.set(key, current_list, ttl_seconds)

    def extend(self, key: str, items: List[Any], ttl_seconds: Optional[int] = None) -> None:
        """Расширить список."""
        current_list = self.get(key, [])
        current_list.extend(items)
        self.set(key, current_list, ttl_seconds)

    def delete(self, key: str) -> bool:
        """Удалить ключ."""
        return self._storage.delete(key)

    def exists(self, key: str) -> bool:
        """Проверить существование."""
        return self._storage.exists(key)

    def clear(self) -> None:
        """Очистить."""
        self._storage.clear()

    def size(self) -> int:
        """Размер."""
        return self._storage.size()

    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """Получить ключи."""
        return self._storage.keys(pattern)