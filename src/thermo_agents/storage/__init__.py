"""Модуль хранилища данных для термодинамических агентов.

Предоставляет простое Key-Value хранилище с поддержкой TTL и типизации.
Объединяет функциональность сложной Message Queue системы в простой
и эффективный интерфейс.
"""

from .simple_storage import SimpleAgentStorage, TypedStorage
from .typed_storage import StringStorage, DictStorage, ListStorage

__all__ = [
    "SimpleAgentStorage",
    "TypedStorage",
    "StringStorage",
    "DictStorage",
    "ListStorage"
]