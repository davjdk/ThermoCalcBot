# Этап 6: Оптимизация производительности и типизации

**Длительность**: 2-3 дня
**Приоритет**: Средний
**Риски**: Низкие
**Зависимости**: Этапы 1-5 завершены

## Обзор

На этом этапе мы оптимизируем производительность системы через кэширование, ленивую инициализацию и улучшение типизации. Это позволит повысить скорость выполнения и обеспечить лучшую типобезопасность кода.

---

## Задача 6.1: Кэширование в CommonCompoundResolver

### Проблема
Каждый запрос создаёт словари и проверяет паттерны заново, что приводит к избыточным вычислениям для повторяющихся запросов.

### Решение
🔧 **ДОБАВИТЬ @lru_cache для методов проверки**

### Текущая реализация

```python
# src/thermo_agents/search/common_compounds.py
class CommonCompoundResolver:
    def __init__(self):
        self._exact_matches = {
            "H2O": "Water",
            "CO2": "Carbon Dioxide",
            "O2": "Oxygen",
            # ... больше записей
        }
        self._pattern_cache = {}  # Не используется эффективно
```

### Оптимизированная реализация

```python
# src/thermo_agents/search/common_compounds.py
from functools import lru_cache
from typing import Dict, Set, Optional

class CommonCompoundResolver:
    """Оптимизированный резолвер для распространённых соединений."""

    def __init__(self):
        # Предвычисленные множества для быстрой проверки
        self._exact_matches: Dict[str, str] = {
            "H2O": "Water",
            "H2O": "Вода",
            "CO2": "Carbon Dioxide",
            "CO2": "Углекислый газ",
            "O2": "Oxygen",
            "O2": "Кислород",
            "N2": "Nitrogen",
            "N2": "Азот",
            "H2": "Hydrogen",
            "H2": "Водород",
            "CH4": "Methane",
            "CH4": "Метан",
            "NH3": "Ammonia",
            "NH3": "Аммиак",
            "HCl": "Hydrogen Chloride",
            "HCl": "Хлороводород",
            "H2SO4": "Sulfuric Acid",
            "H2SO4": "Серная кислота",
            "NaCl": "Sodium Chloride",
            "NaCl": "Поваренная соль",
        }

        # Множества для быстрой проверки membership
        self._common_formulas: Set[str] = set(self._exact_matches.keys())
        self._common_names: Set[str] = set(self._exact_matches.values())

        # Компилированные паттерны для regex
        self._compiled_patterns = self._compile_patterns()

    @lru_cache(maxsize=512)
    def is_common_compound(self, formula: str) -> bool:
        """Кэшированная проверка распространённого соединения.

        Args:
            formula: Химическая формула для проверки

        Returns:
            True если это распространённое соединение
        """
        # Нормализация и проверка
        normalized = formula.upper().strip()
        return normalized in self._common_formulas

    @lru_cache(maxsize=256)
    def get_common_compound_name(self, formula: str) -> Optional[str]:
        """Кэшированное получение названия распространённого соединения.

        Args:
            formula: Химическая формула

        Returns:
            Название соединения или None если не найдено
        """
        normalized = formula.upper().strip()
        return self._exact_matches.get(normalized)

    @lru_cache(maxsize=128)
    def find_ambiguous_patterns(self, formula: str) -> list[str]:
        """Кэшированный поиск неоднозначных паттернов.

        Args:
            formula: Химическая формула

        Returns:
            Список потенциально неоднозначных совпадений
        """
        # Использование предкомпилированных паттернов
        matches = []
        for pattern, description in self._compiled_patterns.items():
            if pattern.search(formula):
                matches.append(description)
        return matches

    def _compile_patterns(self) -> Dict[re.Pattern, str]:
        """Предкомпилировать regex паттерны."""
        import re

        patterns = {
            re.compile(r'^H2O$'): 'Water exact match',
            re.compile(r'H2O[0-9]'): 'Water with number',
            re.compile(r'Fe[0-9]+O[0-9]+'): 'Iron oxide pattern',
            re.compile(r'TiO[0-9]'): 'Titanium oxide pattern',
            # ... больше паттернов
        }
        return patterns

    def clear_cache(self):
        """Очистить все кэши."""
        self.is_common_compound.cache_clear()
        self.get_common_compound_name.cache_clear()
        self.find_ambiguous_patterns.cache_clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Получить статистику использования кэша."""
        return {
            "is_common_compound": self.is_common_compound.cache_info().hits,
            "get_common_compound_name": self.get_common_compound_name.cache_info().hits,
            "find_ambiguous_patterns": self.find_ambiguous_patterns.cache_info().hits,
        }
```

---

## Задача 6.2: Ленивая инициализация в DatabaseConnector

### Проблема
Соединение с БД открывается при создании объекта, даже если не используется, что приводит к избыточным ресурсам.

### Решение
🔧 **РЕАЛИЗОВАТЬ lazy connection через property**

### Текущая реализация

```python
# src/thermo_agents/search/database_connector.py
class DatabaseConnector:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)  # Сразу открывает соединение
        self._setup_connection()
```

### Оптимизированная реализация

```python
# src/thermo_agents/search/database_connector.py
import sqlite3
import threading
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import time

class DatabaseConnector:
    """Коннектор с ленивой инициализацией и пулом соединений."""

    def __init__(self, db_path: str, pool_size: int = 1):
        self.db_path = db_path
        self.pool_size = pool_size
        self._connections: List[sqlite3.Connection] = []
        self._available_connections: List[sqlite3.Connection] = []
        self._lock = threading.RLock()
        self._initialized = False

    @property
    def connection(self) -> sqlite3.Connection:
        """Ленивое получение соединения из пула."""
        if not self._initialized:
            self._initialize_pool()

        with self._lock:
            if self._available_connections:
                conn = self._available_connections.pop()
            else:
                conn = self._create_connection()
                self._connections.append(conn)

            return conn

    def _initialize_pool(self):
        """Инициализировать пул соединений."""
        with self._lock:
            if self._initialized:
                return

            for _ in range(self.pool_size):
                conn = self._create_connection()
                self._connections.append(conn)
                self._available_connections.append(conn)

            self._initialized = True

    def _create_connection(self) -> sqlite3.Connection:
        """Создать новое соединение с БД."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row  # Удобный доступ к колонкам
        self._setup_connection(conn)
        return conn

    def _setup_connection(self, conn: sqlite3.Connection):
        """Настроить соединение."""
        # Оптимизации для SQLite
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=10000")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB

    @contextmanager
    def get_connection(self):
        """Context manager для работы с соединением."""
        conn = self.connection
        try:
            yield conn
        finally:
            self._return_connection(conn)

    def _return_connection(self, conn: sqlite3.Connection):
        """Вернуть соединение в пул."""
        with self._lock:
            if conn in self._connections and conn not in self._available_connections:
                self._available_connections.append(conn)

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Выполнить запрос с измерением производительности."""
        start_time = time.time()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            results = [dict(row) for row in cursor.fetchall()]

        execution_time = time.time() - start_time

        # Логирование медленных запросов
        if execution_time > 1.0:  # Больше 1 секунды
            print(f"Slow query ({execution_time:.2f}s): {query[:100]}...")

        return results

    def close_all(self):
        """Закрыть все соединения."""
        with self._lock:
            for conn in self._connections:
                conn.close()
            self._connections.clear()
            self._available_connections.clear()
            self._initialized = False

    def get_connection_stats(self) -> Dict[str, int]:
        """Получить статистику пула соединений."""
        with self._lock:
            return {
                "total_connections": len(self._connections),
                "available_connections": len(self._available_connections),
                "active_connections": len(self._connections) - len(self._available_connections),
                "pool_size": self.pool_size
            }
```

---

## Задача 6.3: Улучшение типизации AgentStorage

### Проблема
`AgentStorage` использует `Any` для значений, что снижает типобезопасность и затрудняет анализ кода.

### Решение
🔧 **ДОБАВИТЬ generics для типизированного хранилища**

### Оптимизированная реализация

```python
# src/thermo_agents/storage/typed_storage.py
from typing import TypeVar, Generic, Optional, Dict, Any, Type, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
import json

T = TypeVar('T')

@dataclass
class TypedStorageEntry(Generic[T]):
    """Типизированная запись в хранилище."""
    value: T
    created_at: datetime
    expires_at: Optional[datetime] = None
    value_type: Type = Any

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        return {
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "value_type": f"{self.value_type.__module__}.{self.value_type.__name__}"
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TypedStorageEntry[T]':
        """Десериализовать из словаря."""
        created_at = datetime.fromisoformat(data["created_at"])
        expires_at = datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None
        return cls(
            value=data["value"],
            created_at=created_at,
            expires_at=expires_at,
            value_type=Any  # В реальной реализации можно восстановить тип
        )

class TypedStorage(Generic[T]):
    """Типизированное хранилище с поддержкой TTL."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self._storage: Dict[str, TypedStorageEntry[T]] = {}
        self._lock = threading.RLock()
        self.default_ttl = timedelta(seconds=default_ttl_seconds)

    def set(self, key: str, value: T, ttl_seconds: Optional[int] = None) -> None:
        """Сохранить типизированное значение с опциональным TTL."""
        expires_at = None
        if ttl_seconds is not None:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
        elif self.default_ttl:
            expires_at = datetime.now() + self.default_ttl

        entry = TypedStorageEntry(
            value=value,
            created_at=datetime.now(),
            expires_at=expires_at,
            value_type=type(value)
        )

        with self._lock:
            self._storage[key] = entry

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Получить типизированное значение."""
        with self._lock:
            entry = self._storage.get(key)
            if entry is None:
                return default

            if entry.is_expired:
                del self._storage[key]
                return default

            return entry.value

    def get_typed(self, key: str, expected_type: Type[T], default: Optional[T] = None) -> Optional[T]:
        """Получить значение с проверкой типа."""
        value = self.get(key, default)
        if value is not None and not isinstance(value, expected_type):
            raise TypeError(f"Expected {expected_type}, got {type(value)} for key '{key}'")
        return value

    def delete(self, key: str) -> bool:
        """Удалить ключ. Возвращает True если ключ существовал."""
        with self._lock:
            if key in self._storage:
                del self._storage[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """Проверить существование не просроченного ключа."""
        with self._lock:
            entry = self._storage.get(key)
            return entry is not None and not entry.is_expired

    def clear(self) -> None:
        """Очистить всё хранилище."""
        with self._lock:
            self._storage.clear()

    def cleanup_expired(self) -> int:
        """Удалить просроченные записи. Возвращает количество удалённых."""
        with self._lock:
            expired_keys = [
                key for key, entry in self._storage.items()
                if entry.is_expired
            ]

            for key in expired_keys:
                del self._storage[key]

            return len(expired_keys)

    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """Получить список активных ключей."""
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
        """Количество активных записей."""
        with self._lock:
            return sum(1 for entry in self._storage.values() if not entry.is_expired)

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику хранилища."""
        with self._lock:
            total_entries = len(self._storage)
            active_entries = sum(1 for entry in self._storage.values() if not entry.is_expired)
            expired_entries = total_entries - active_entries

            type_stats = {}
            for entry in self._storage.values():
                type_name = entry.value_type.__name__
                type_stats[type_name] = type_stats.get(type_name, 0) + 1

            return {
                "total_entries": total_entries,
                "active_entries": active_entries,
                "expired_entries": expired_entries,
                "type_distribution": type_stats
            }

# Специализированные типизированные хранилища
class StringStorage(TypedStorage[str]):
    """Хранилище для строк."""
    pass

class DictStorage(TypedStorage[Dict[str, Any]]):
    """Хранилище для словарей."""
    pass

class ListStorage(TypedStorage[List[Any]]):
    """Хранилище для списков."""
    pass
```

---

## Задача 6.4: Оптимизация фильтрации через предвычисления

### Проблема
Повторяющиеся вычисления в фильтрации для одних и тех же формул и диапазонов температур.

### Решение
🔧 **ДОБАВИТЬ кэширование результатов фильтрации**

```python
# src/thermo_agents/filtering/cached_filter.py
from functools import lru_cache
from typing import List, Tuple, Optional
import hashlib

class CachedFilterMixin:
    """Mixin для кэширования результатов фильтрации."""

    @lru_cache(maxsize=1024)
    def _cached_temperature_filter(
        self,
        formula_hash: str,
        temp_min: float,
        temp_max: float,
        phase: str
    ) -> List[int]:
        """Кэшированная температурная фильтрация.

        Returns:
            Список ID записей, прошедших фильтр
        """
        # Реализация фильтрации
        pass

    def _get_formula_hash(self, formula: str) -> str:
        """Получить хеш формулы для кэширования."""
        return hashlib.md5(formula.encode()).hexdigest()

    def _get_cache_key(self, *args) -> str:
        """Сгенерировать ключ для кэша."""
        return "|".join(str(arg) for arg in args)
```

---

## Порядок выполнения

### Шаг 1: Подготовка (0.5 дня)
```bash
# Создать ветку
git checkout -b refactor/stage-6-optimization

# Создать структуру
mkdir -p src/thermo_agents/storage
mkdir -p tests/unit/optimization
```

### Шаг 2: Оптимизация CommonCompoundResolver (0.5 дня)
1. Добавить @lru_cache для методов
2. Предвычислить множества и паттерны
3. Добавить статистику кэша
4. Написать тесты производительности

### Шаг 3: Ленивая инициализация DatabaseConnector (1 день)
1. Реализовать пул соединений
2. Добавить context manager
3. Оптимизировать настройки SQLite
4. Добавить метрики производительности

### Шаг 4: Улучшение типизации (0.5 день)
1. Создать TypedStorage с generics
2. Обновить AgentStorage
3. Добавить специализированные хранилища
4. Обновить тесты

### Шаг 5: Кэширование фильтрации (0.5 день)
1. Добавить кэширование в стадии фильтрации
2. Реализовать CachedFilterMixin
3. Оптимизировать горячие пути
4. Измерить производительность

### Шаг 6: Валидация (0.5 день)
```bash
# Запустить все тесты
uv run pytest tests/ -v

# Бенчмарки производительности
uv run pytest tests/unit/test_optimization.py::test_performance -v

# Проверить типизацию
uv run mypy src/thermo_agents/
```

---

## Ожидаемые результаты

### Производительность
- ✅ **Ускорение на 10-20%** для повторяющихся запросов (кэширование)
- ✅ **Снижение использования памяти** (ленивая инициализация)
- ✅ **Улучшение并发ности** (пул соединений)
- ✅ **Быстрая фильтрация** (предвычисления)

### Типобезопасность
- ✅ **Строгая типизация** хранилища данных
- ✅ **Проверка типов** при извлечении данных
- ✅ **Улучшенная поддержка IDE** (автодополнение)
- ✅ **Снижение runtime ошибок**

### Мониторинг и отладка
- ✅ **Метрики производительности** для всех компонентов
- ✅ **Статистика кэшей** и соединений
- ✅ **Профилирование запросов** к БД
- ✅ **Диагностика узких мест**

---

## Критерии завершения

- [ ] CommonCompoundResolver использует кэширование
- [ ] DatabaseConnector имеет ленивую инициализацию
- [ ] TypedStorage реализован с generics
- [ ] Кэширование фильтрации работает
- [ ] Все тесты проходят
- [ ] Бенчмарки показывают улучшение производительности
- [ ] Mypy не показывает ошибок типизации
- [ ] Code review завершён

---

## Метрики производительности

### Бенчмарки для реализации

```python
# tests/unit/test_optimization.py
import time
import pytest

def test_common_compound_cache_performance():
    """Тест производительности кэша распространённых соединений."""
    resolver = CommonCompoundResolver()

    # Холодный запуск
    start = time.time()
    for _ in range(1000):
        resolver.is_common_compound("H2O")
    cold_time = time.time() - start

    # Тёплый запуск (с кэшем)
    start = time.time()
    for _ in range(1000):
        resolver.is_common_compound("H2O")
    warm_time = time.time() - start

    # Ожидаем ускорение минимум в 10 раз
    assert warm_time < cold_time / 10

def test_database_connector_pool_performance():
    """Тест производительности пула соединений."""
    # Тест concurrent доступа
    pass

def test_typed_storage_performance():
    """Тест производительности типизированного хранилища."""
    # Сравнение с обычным хранилищем
    pass
```

---

## Следующий этап

После завершения Этапа 6 можно переходить к **Этапу 7: Структурные изменения**, который включает реорганизацию промптов, создание config модуля и финальное тестирование.