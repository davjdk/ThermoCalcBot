# Этап 2: Разработка модуля поиска

**Длительность:** 3-4 дня  
**Приоритет:** Высокий  
**Статус:** Не начат  
**Зависимости:** Этап 1

---

## Описание

Создание модуля поиска для работы с отдельными химическими веществами. Модуль координирует генерацию SQL (Этап 1) и выполнение запросов к БД.

---

## Основные задачи

### 1. Создать структуру модуля `search/`

**Структура каталога:**
```
src/thermo_agents/search/
├── __init__.py                 # Экспорты
├── sql_builder.py              # Из Этапа 1
├── database_connector.py       # Выполнение SQL
├── compound_searcher.py        # Логика поиска одного вещества
└── models.py                   # Pydantic модели для результатов
```

**Задачи:**
- [ ] Создать каталог `src/thermo_agents/search/`
- [ ] Создать файл `__init__.py` с экспортами
- [ ] Перенести `sql_builder.py` из Этапа 1 (если ещё не там)

---

### 2. Реализовать `CompoundSearcher`

**Файл:** `src/thermo_agents/search/compound_searcher.py`

**Класс:**
```python
from typing import List, Tuple, Optional
from src.thermo_agents.search.sql_builder import SQLBuilder
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.models.search import CompoundSearchResult, DatabaseRecord

class CompoundSearcher:
    """Поиск данных для одного химического вещества."""
    
    def __init__(
        self, 
        sql_builder: SQLBuilder,
        db_connector: DatabaseConnector
    ):
        self.sql_builder = sql_builder
        self.db_connector = db_connector
    
    def search_compound(
        self, 
        formula: str, 
        temperature_range: Tuple[float, float]
    ) -> CompoundSearchResult:
        """
        Поиск данных для вещества в заданном температурном диапазоне.
        
        Алгоритм:
        1. Генерация SQL через sql_builder
        2. Выполнение запроса через db_connector
        3. Получение списка DatabaseRecord
        4. Формирование CompoundSearchResult
        
        Args:
            formula: Химическая формула (например, "H2O")
            temperature_range: Диапазон температур (tmin, tmax) в K
            
        Returns:
            CompoundSearchResult с найденными записями
        """
        # Шаг 1: Генерация SQL
        query = self.sql_builder.build_compound_search_query(
            formula, temperature_range
        )
        
        # Шаг 2: Выполнение запроса
        raw_results = self.db_connector.execute_query(query)
        
        # Шаг 3: Преобразование в DatabaseRecord
        records = [self._parse_record(row) for row in raw_results]
        
        # Шаг 4: Формирование результата
        return CompoundSearchResult(
            compound_formula=formula,
            records_found=records,
            filter_statistics=None,  # Будет заполнено на Этапе 3
            coverage_status="unknown",
            warnings=[]
        )
    
    def _parse_record(self, row: dict) -> DatabaseRecord:
        """Преобразование строки БД в DatabaseRecord."""
        ...
```

**Задачи:**
- [ ] Реализовать класс `CompoundSearcher`
- [ ] Добавить метод `search_compound()`
- [ ] Добавить вспомогательный метод `_parse_record()`
- [ ] Написать docstrings для всех методов

---

### 3. Реализовать `DatabaseConnector`

**Файл:** `src/thermo_agents/search/database_connector.py`

**Класс:**
```python
import sqlite3
from typing import List, Dict, Any
from pathlib import Path

class DatabaseConnector:
    """Подключение к БД и выполнение SQL-запросов."""
    
    def __init__(self, db_path: str):
        """
        Инициализация коннектора.
        
        Args:
            db_path: Путь к файлу БД SQLite
        """
        self.db_path = Path(db_path)
        self._connection = None
    
    def connect(self):
        """Установка соединения с БД."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"БД не найдена: {self.db_path}")
        
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row  # Доступ по именам колонок
    
    def disconnect(self):
        """Закрытие соединения."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Выполнение SQL-запроса и получение результатов.
        
        Args:
            query: SQL-запрос
            
        Returns:
            Список словарей с результатами
        """
        if not self._connection:
            self.connect()
        
        cursor = self._connection.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Преобразование Row в dict
        return [dict(row) for row in rows]
    
    def __enter__(self):
        """Контекстный менеджер: вход."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер: выход."""
        self.disconnect()
```

**Задачи:**
- [ ] Реализовать класс `DatabaseConnector`
- [ ] Добавить поддержку контекстного менеджера (`with` statement)
- [ ] Добавить обработку ошибок подключения
- [ ] Добавить логирование выполняемых запросов
- [ ] Написать docstrings

---

### 4. Создать Pydantic модели

**Файл:** `src/thermo_agents/models/search.py`

**Модели:**
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class DatabaseRecord(BaseModel):
    """Одна запись из БД compounds."""
    formula: str
    phase: Optional[str] = None
    tmin: Optional[float] = None
    tmax: Optional[float] = None
    h298: Optional[float] = None
    s298: Optional[float] = None
    f1: Optional[float] = None
    f2: Optional[float] = None
    f3: Optional[float] = None
    f4: Optional[float] = None
    f5: Optional[float] = None
    f6: Optional[float] = None
    reliability_class: Optional[int] = None
    tmelt: Optional[float] = None
    tboil: Optional[float] = None
    # ... остальные поля из БД

class CompoundSearchResult(BaseModel):
    """Результат поиска для одного вещества."""
    compound_formula: str
    records_found: List[DatabaseRecord]
    filter_statistics: Optional[Any] = None  # Будет FilterStatistics на Этапе 3
    coverage_status: str = Field(
        ..., 
        description="Статус покрытия: 'full', 'partial', 'none'"
    )
    warnings: List[str] = Field(default_factory=list)
```

**Задачи:**
- [ ] Создать `src/thermo_agents/models/search.py`
- [ ] Реализовать `DatabaseRecord` с валидацией полей
- [ ] Реализовать `CompoundSearchResult`
- [ ] Добавить валидаторы для `coverage_status` (только 'full'/'partial'/'none')

---

### 5. Написать unit-тесты

**Файл:** `tests/test_compound_searcher.py`

**Тестовые случаи:**

**TC1: Поиск H2O**
```python
def test_search_h2o():
    searcher = CompoundSearcher(sql_builder, db_connector)
    result = searcher.search_compound('H2O', (298, 673))
    
    assert result.compound_formula == 'H2O'
    assert len(result.records_found) > 0
    assert all(r.formula.startswith('H2O') for r in result.records_found)
```

**TC2: Несуществующее вещество**
```python
def test_search_nonexistent():
    searcher = CompoundSearcher(sql_builder, db_connector)
    result = searcher.search_compound('Xyz123', (298, 673))
    
    assert result.compound_formula == 'Xyz123'
    assert len(result.records_found) == 0
    assert result.coverage_status == 'none'
```

**TC3: DatabaseConnector контекстный менеджер**
```python
def test_db_connector_context_manager():
    with DatabaseConnector(db_path) as connector:
        results = connector.execute_query("SELECT * FROM compounds LIMIT 1")
        assert len(results) == 1
```

**Задачи:**
- [ ] Создать `tests/test_compound_searcher.py`
- [ ] Создать `tests/test_database_connector.py`
- [ ] Реализовать минимум 10 тестов
- [ ] Покрытие тестами >80%
- [ ] Использовать моки для изоляции тестов

---

## Артефакты этапа

### Файлы для создания:
1. `src/thermo_agents/search/compound_searcher.py`
2. `src/thermo_agents/search/database_connector.py`
3. `src/thermo_agents/models/search.py`
4. `tests/test_compound_searcher.py`
5. `tests/test_database_connector.py`

### Обновления:
- `src/thermo_agents/search/__init__.py` — добавить экспорты

---

## Критерии завершения этапа

✅ **Обязательные:**
1. Модуль `search/` создан со всеми компонентами
2. `CompoundSearcher` корректно выполняет поиск вещества
3. `DatabaseConnector` поддерживает контекстный менеджер
4. Pydantic модели валидируют данные
5. Все unit-тесты проходят успешно
6. Покрытие тестами >80%
7. Интеграционный тест с реальной БД проходит

📋 **Дополнительные:**
- Логирование всех SQL-запросов
- Обработка сетевых ошибок (если БД удалённая)
- Кеширование результатов запросов

---

## Риски

| Риск                                     | Вероятность | Влияние | Митигация                                               |
| ---------------------------------------- | ----------- | ------- | ------------------------------------------------------- |
| Медленные запросы к БД                   | Средняя     | Среднее | Добавить индексы, ограничить LIMIT                      |
| Утечки памяти при множественных запросах | Низкая      | Среднее | Использовать контекстный менеджер, закрывать соединения |
| Несовместимость схемы БД                 | Низкая      | Высокое | Валидация через Pydantic, обработка исключений          |

---

## Следующий этап

➡️ **Этап 3:** Разработка модульной фильтрации
