# Техническое задание: Система логирования сессий

## 1. Общее описание

Система логирования предназначена для записи и хранения детальной информации о каждом пользовательском запросе (сессии) в термодинамической системе. Каждая сессия представляет собой отдельный запрос пользователя, обрабатываемый системой от начала до конца.

**Ключевые аспекты:**
- Одна сессия = один пользовательский запрос
- Логи сохраняются в `logs/sessions`
- Формат: `.log` файлы
- Фокус на трёх ключевых этапах: LLM-ответы, поиск в БД, фильтрация

## 2. Цели и задачи

**Цели:**
- Обеспечить прозрачность работы системы на всех этапах обработки запроса
- Упростить диагностику проблем и локализацию ошибок
- Сохранить историю взаимодействия пользователя с системой

**Задачи:**
- Логировать результаты классификации запроса через LLM
- Записывать SQL-запросы и результаты поиска в БД (первые 30 записей)
- Фиксировать процесс фильтрации записей
- Обеспечить читаемость логов через tabulate
- Автоматически создавать уникальные файлы для каждой сессии

## 3. Требования к системе

### 3.1 Функциональные требования

- **FR-1**: Создание нового лог-файла для каждой пользовательской сессии
- **FR-2**: Логирование полного ответа от LLM (классификация запроса)
- **FR-3**: Запись SQL-запросов с параметрами
- **FR-4**: Вывод результатов SQL-запросов в формате таблицы (первые 30 записей)
- **FR-5**: Логирование этапов фильтрации с промежуточными результатами
- **FR-6**: Автоматическая ротация логов (опционально)

### 3.2 Нефункциональные требования

- **NFR-1**: Минимальное влияние на производительность системы
- **NFR-2**: Читаемость логов без дополнительных инструментов
- **NFR-3**: Кроссплатформенность (Windows/Linux)
- **NFR-4**: Потокобезопасность записи логов
- **NFR-5**: Ограничение размера одного лог-файла (рекомендуется 10 МБ)

## 4. Архитектура системы

### 4.1 Структура файлов логов

```
logs/
└── sessions/
    ├── session_20251028_143052_a1b2c3.log
    ├── session_20251028_143145_d4e5f6.log
    └── session_20251028_144312_g7h8i9.log
```

**Формат имени файла:** `session_YYYYMMDD_HHMMSS_<unique_id>.log`
- `YYYYMMDD` — дата
- `HHMMSS` — время начала сессии
- `<unique_id>` — уникальный идентификатор (6 символов hex)

### 4.2 Компоненты системы

- **SessionLogger** — основной класс для логирования сессий
- **LogFormatter** — форматирование данных для записи в лог
- **TableFormatter** — обёртка над tabulate для вывода таблиц
- **Integration Points** — точки интеграции в существующий код

## 5. Логируемые события

### 5.1 Ответы от LLM

**Что логировать:**
- Исходный запрос пользователя (полный текст)
- Полный ответ от LLM в формате JSON с классификацией
- Извлечённые параметры (формула реакции, температуры, шаг и т.д.)
- Время обработки запроса (timestamp начала и конца)
- Модель LLM и параметры вызова (температура модели, max_tokens и т.д.)
- Статус обработки (SUCCESS/ERROR)

**Детали реализации:**
- Логировать ДО парсинга ответа (сырой JSON)
- Логировать ПОСЛЕ парсинга (извлечённые параметры)
- При ошибке парсинга — логировать полный traceback
- Форматировать JSON с отступами для читаемости

**Пример структуры:**
```
================================================================================
[LLM REQUEST] 2025-10-28 14:30:52.123
================================================================================
User query:
расчет реакции 3H2S + Fe2O3 -> 3H2O + 2FeS при 773-973K с шагом 100K

Query length: 65 characters
Query type: text

================================================================================
[LLM RESPONSE] 2025-10-28 14:30:54.456 (duration: 2.333s)
================================================================================
Model: gpt-4-turbo
Temperature: 0.0
Max tokens: 1000

Raw response (JSON):
{
  "query_type": "REACTION_CALCULATION",
  "reaction_equation": "3H2S + Fe2O3 -> 3H2O + 2FeS",
  "temperature_start": 773,
  "temperature_end": 973,
  "temperature_step": 100,
  "pressure": null,
  "phases": null
}

Extracted parameters:
  ✓ query_type: REACTION_CALCULATION
  ✓ reaction: 3H2S + Fe2O3 -> 3H2O + 2FeS
  ✓ temp_start: 773 K
  ✓ temp_end: 973 K
  ✓ temp_step: 100 K
  ○ pressure: not specified (using default)
  ○ phases: not specified (auto-detect)

Status: SUCCESS
```

**Обработка ошибок:**
```
[LLM ERROR] 2025-10-28 14:31:05.789
Error type: JSONDecodeError
Error message: Expecting value: line 1 column 1 (char 0)

Raw response:
I cannot parse this request...

Traceback:
  File "orchestrator.py", line 123, in parse_llm_response
    data = json.loads(response)
  ...
```

### 5.2 Поиск в базе данных

**Что логировать:**
- SQL-запрос с параметрами (полный текст)
- Количество найденных записей (total count)
- Первые 30 записей в табличном формате (через tabulate)
- Время выполнения запроса (в миллисекундах)
- Используемые фильтры и JOIN-ы
- Название таблиц и индексов

**Детали реализации:**
- Логировать запрос с подставленными параметрами для отладки
- Использовать `tabulate` с форматом `grid` для максимальной читаемости
- Сокращать длинные значения (> 50 символов) с добавлением "..."
- Выводить метаданные: имена колонок, типы данных
- Группировать результаты по compound_id или formula

**Структура логирования:**
```
================================================================================
[DATABASE SEARCH] 2025-10-28 14:30:55.123
================================================================================
Search context: Looking for compounds in reaction equation
Compounds to search: ['H2S', 'Fe2O3', 'H2O', 'FeS']

SQL Query:
  SELECT 
    c.compound_id,
    c.formula,
    c.name,
    c.phase,
    c.t_min,
    c.t_max,
    c.h298,
    c.s298
  FROM compounds c
  WHERE c.formula IN (?, ?, ?, ?)
    AND c.t_min <= ?
    AND c.t_max >= ?
  ORDER BY c.formula, c.phase

Parameters: 
  formulas: ['H2S', 'Fe2O3', 'H2O', 'FeS']
  temp_min: 773
  temp_max: 973

Execution time: 152.3 ms
Total records found: 47
Records to display: 30 (first batch)

================================================================================
[SEARCH RESULTS] First 30 records
================================================================================
+-------+----------+-------------------------+-------+--------+--------+----------+--------+
| ID    | Formula  | Name                    | Phase | T_min  | T_max  | H298     | S298   |
+=======+==========+=========================+=======+========+========+==========+========+
| 12345 | H2S      | Hydrogen sulfide        | g     | 298    | 2000   | -20.630  | 205.81 |
| 12346 | H2S      | Hydrogen sulfide        | l     | 187    | 373    | -20.630  | 205.81 |
| 12347 | Fe2O3    | Iron(III) oxide         | s     | 298    | 950    | -824.200 | 87.400 |
| 12348 | Fe2O3(G) | gamma-Iron(III) oxide   | s     | 273    | 760    | 0.000    | 0.000  |
| 12349 | H2O      | Hydrogen oxide          | g     | 298    | 6000   | -241.826 | 188.84 |
| 12350 | H2O      | Hydrogen oxide          | l     | 273    | 647    | -285.830 | 69.950 |
| 12351 | H2O      | Hydrogen oxide          | s     | 3      | 273    | -285.830 | 69.950 |
| ...   | ...      | ...                     | ...   | ...    | ...    | ...      | ...    |
+-------+----------+-------------------------+-------+--------+--------+----------+--------+

Grouped by formula:
  H2S: 3 records (g, l, s)
  Fe2O3: 2 records (s, s)
  H2O: 5 records (g, l, s, ...)
  FeS: 4 records (l, s, ...)

================================================================================
[SEARCH STATISTICS]
================================================================================
Database: thermochemistry.db
Tables queried: compounds
Indexes used: idx_formula, idx_temperature_range
Cache hit: NO
Query complexity: MODERATE (1 table, 3 conditions)
```

**Обработка больших результатов:**
- Если записей > 30, добавить сообщение: "... and X more records (not shown)"
- Опционально: сохранить полный результат в отдельный файл
- Показать статистику распределения по формулам/фазам

### 5.3 Фильтрация записей

**Что логировать:**
- Критерии фильтрации на каждом этапе
- Количество записей до фильтрации
- Количество записей после каждого этапа фильтрации
- Финальный набор записей (первые 30 через tabulate)
- Причины отсева записей (детальная статистика)
- Примененные стратегии приоритизации

**Этапы фильтрации:**
1. **Фильтрация по диапазону температур** — проверка t_min/t_max
2. **Фильтрация по фазовому состоянию** — отбор релевантных фаз
3. **Приоритизация по качеству данных** — полнота Cp-коэффициентов
4. **Выбор best-match** — один лучший вариант для каждого соединения
5. **Валидация финального набора** — проверка на корректность

**Детали реализации:**
```
================================================================================
[FILTERING PIPELINE] 2025-10-28 14:30:56.234
================================================================================
Input: 47 records from database search
Target temperature range: 773-973 K
Required compounds: ['H2S', 'Fe2O3', 'H2O', 'FeS']

--------------------------------------------------------------------------------
STAGE 1: Temperature Range Filter
--------------------------------------------------------------------------------
Criteria:
  - Record t_min <= 773 K
  - Record t_max >= 973 K
  - Or: partial overlap with [773, 973] range

Input records: 47
Output records: 28
Removed: 19 records

Removal reasons:
  • t_max < 773 K: 7 records
    - H2O (s, 3-273K)
    - Fe2O3 (s, 298-600K)
    - ...
  • t_min > 973 K: 12 records
    - H2S (g, 1500-3000K)
    - ...

Records after stage 1 (first 30):
+-------+----------+-------------------------+-------+--------+--------+
| ID    | Formula  | Name                    | Phase | T_min  | T_max  |
+=======+==========+=========================+=======+========+========+
| 12345 | H2S      | Hydrogen sulfide        | g     | 298    | 2000   |
| 12348 | Fe2O3(G) | gamma-Iron(III) oxide   | s     | 273    | 760    |
| 12349 | H2O      | Hydrogen oxide          | g     | 298    | 6000   |
| ...   | ...      | ...                     | ...   | ...    | ...    |
+-------+----------+-------------------------+-------+--------+--------+

--------------------------------------------------------------------------------
STAGE 2: Phase State Filter
--------------------------------------------------------------------------------
Criteria:
  - Prefer phases stable at avg temperature (873 K)
  - For reaction: detect expected phases from stoichiometry
  - Priority: s > l > g (for reactants), l > g > s (for products)

Input records: 28
Output records: 18
Removed: 10 records

Phase distribution before:
  H2S: g(1), l(1) 
  Fe2O3: s(2)
  H2O: g(1), l(1), s(1)
  FeS: l(1), s(1)

Phase distribution after:
  H2S: g(1) — gas preferred at 773-973K
  Fe2O3: s(1) — solid Fe2O3(G) selected
  H2O: l(1) — liquid preferred (product)
  FeS: l(1) — liquid preferred at high T

Removed records:
  • H2S (l): out of temperature range
  • Fe2O3 (s, alpha): gamma modification preferred
  • H2O (g, s): liquid more suitable
  • FeS (s): liquid phase more stable at 773-973K

--------------------------------------------------------------------------------
STAGE 3: Data Quality Prioritization
--------------------------------------------------------------------------------
Criteria:
  - Complete Cp coefficients (6 values)
  - Non-zero H298 and S298
  - Reference data available
  - Peer-reviewed source

Input records: 18
Output records: 12
Removed: 6 records

Quality scores:
  ✓ H2SO4*6.5H2O (score: 95/100) — all data complete
  ✓ Fe2O3(G) (score: 60/100) — missing H298/S298 (WARNING)
  ✓ H2O (score: 100/100) — perfect data
  ✓ FeS(l) (score: 70/100) — Cp has only 1 coefficient

Removed records:
  • Incomplete Cp data: 3 records
  • Missing H298/S298: 2 records
  • Unreliable source: 1 record

--------------------------------------------------------------------------------
STAGE 4: Best Match Selection
--------------------------------------------------------------------------------
Strategy: One record per compound (formula + phase)

Input records: 12
Output records: 4
Grouped by: formula

Selection logic per compound:
  H2S:
    Candidates: 3 records
    Selected: ID 12345 (g, 298-2000K) — widest T range
    Reason: Best coverage of target range [773-973]
  
  Fe2O3:
    Candidates: 2 records
    Selected: ID 12348 (gamma, 273-760K) — only option after quality filter
    WARNING: t_max (760K) < temp_start (773K) — partial coverage
  
  H2O:
    Candidates: 4 records
    Selected: ID 12350 (l, 273-647K)
    WARNING: t_max (647K) < temp_start (773K) — extrapolation needed
  
  FeS:
    Candidates: 3 records
    Selected: ID 12351 (l, 298-3000K) — complete coverage

--------------------------------------------------------------------------------
STAGE 5: Final Validation
--------------------------------------------------------------------------------
Validation checks:
  ✓ All required compounds present: 4/4
  ⚠ Temperature coverage issues: 2 compounds
  ✓ Phase consistency: OK
  ⚠ Data quality warnings: 1 compound (Fe2O3(G) missing H298/S298)

Issues detected:
  1. Fe2O3(G): t_max=760K < required 773K (diff: 13K)
     Impact: Extrapolation required for 13K
     Risk: LOW (small extrapolation)
  
  2. H2O: t_max=647K < required 773K (diff: 126K)
     Impact: Extrapolation required for 126K
     Risk: MEDIUM (significant extrapolation)
  
  3. Fe2O3(G): H298=0, S298=0
     Impact: May affect reaction enthalpy/entropy
     Risk: HIGH (critical data missing)

Recommendations:
  • Consider manual review for Fe2O3(G)
  • Search for alternative H2O records with higher t_max
  • Validate extrapolation results

================================================================================
[FILTERING COMPLETE] 2025-10-28 14:30:56.892 (duration: 658ms)
================================================================================
Final records: 4
Records removed: 43 (91.5%)
Warnings: 3
Errors: 0

Final dataset (first 30):
+-------+------------------+-----------------------------+-------+------+-------+-----------+----------+
| ID    | Formula          | Name                        | Phase | T_mn | T_max | H298      | S298     |
+=======+==================+=============================+=======+======+=======+===========+==========+
| 12xxx | H2SO4*6.5H2O     | Sulfuric acid; Hemi...      | l     | 220  | 1000  | 34.116    | 154.862  |
| 12348 | Fe2O3(G)         | gamma-Iron(III) oxide       | s     | 273  | 760   | 0.000 ⚠   | 0.000 ⚠  |
| 12350 | H2O              | Hydrogen oxide              | s     | 3    | 273   | -285.830  | 69.950   |
| 12351 | FeS(l)           | Iron(II) sulfide            | l     | 298  | 3000  | -64.630   | 91.206   |
+-------+------------------+-----------------------------+-------+------+-------+-----------+----------+
```

**Статистика по причинам отсева:**
- Приводить агрегированную статистику
- Показывать топ-3 причины удаления
- Подсвечивать критичные проблемы (⚠ WARNING, ❌ ERROR)


## 6. Формат данных

### 6.1 Структура лог-файла

```
================================================================================
SESSION START: 2025-10-28 14:30:52
SESSION ID: a1b2c3
EXECUTION MODE: production
================================================================================

[SECTION: LLM PROCESSING]
...

[SECTION: DATABASE SEARCH]
...

[SECTION: FILTERING]
...

[SECTION: CALCULATION]
...

================================================================================
SESSION END: 2025-10-28 14:31:15
TOTAL DURATION: 23.4s
STATUS: SUCCESS
================================================================================
```

### 6.2 Формат записей

**Общий формат записи:**
```
[EVENT_TYPE] Timestamp (duration)
Key: Value
...
<optional table or structured data>

```

**Использование tabulate:**
- Библиотека: `tabulate`
- Формат таблицы: `grid` (для лучшей читаемости)
- Максимум записей: 30
- Сокращение длинных значений: > 50 символов

## 7. Интеграция с существующей системой

### 7.1 Точки интеграции

**Модули для модификации:**
1. `src/thermo_agents/orchestrator.py` — инициализация логгера, логирование LLM
2. `src/thermo_agents/search/*.py` — логирование SQL-запросов
3. `src/thermo_agents/filtering/*.py` — логирование фильтрации
4. `main.py` — создание сессии при запуске

**Минимальные изменения:**
- Добавить параметр `session_logger` в конструкторы классов
- Вызывать методы логирования в ключевых точках
- Не изменять существующую бизнес-логику

### 7.2 Изменения в существующем коде

**Принципы интеграции:**
- Dependency Injection для передачи логгера
- Опциональное логирование (если логгер None, то не логировать)
- Минимальная связанность (loosely coupled)
- Не использовать глобальное состояние

**Пример интеграции:**
```python
class Orchestrator:
    def __init__(self, ..., session_logger: Optional[SessionLogger] = None):
        self.session_logger = session_logger
    
    def process_query(self, query: str):
        if self.session_logger:
            self.session_logger.log_llm_request(query)
        # ... existing code
```


## 8. Примеры использования

### 8.1 Инициализация логгера

```python
"""
Модуль для логирования сессий пользователя.
Каждая сессия = один пользовательский запрос.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Dict, List
import uuid
import json
from tabulate import tabulate


class SessionLogger:
    """
    Логгер для записи детальной информации о пользовательской сессии.
    
    Attributes:
        session_id: Уникальный идентификатор сессии
        log_file: Путь к файлу лога
        start_time: Время начала сессии
    """
    
    def __init__(self, logs_dir: Path = Path("logs/sessions")):
        """
        Инициализация логгера сессии.
        
        Args:
            logs_dir: Директория для сохранения логов
        """
        self.session_id = self._generate_session_id()
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Генерация имени файла: session_YYYYMMDD_HHMMSS_<id>.log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}_{self.session_id}.log"
        self.log_file = self.logs_dir / filename
        
        self.start_time = datetime.now()
        self._file_handle = open(self.log_file, "w", encoding="utf-8")
        
        # Запись заголовка сессии
        self._write_header()
    
    def _generate_session_id(self) -> str:
        """Генерация уникального ID сессии (6 символов hex)."""
        return uuid.uuid4().hex[:6]
    
    def _write_header(self) -> None:
        """Запись заголовка лог-файла."""
        separator = "=" * 80
        self._write(separator)
        self._write(f"SESSION START: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"SESSION ID: {self.session_id}")
        self._write(f"LOG FILE: {self.log_file}")
        self._write(separator)
        self._write("")
    
    def _write(self, text: str = "") -> None:
        """Запись строки в файл."""
        self._file_handle.write(text + "\n")
        self._file_handle.flush()  # Немедленная запись на диск
    
    def close(self, status: str = "SUCCESS") -> None:
        """
        Закрытие сессии и файла лога.
        
        Args:
            status: Статус завершения сессии (SUCCESS/ERROR)
        """
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        separator = "=" * 80
        self._write("")
        self._write(separator)
        self._write(f"SESSION END: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"TOTAL DURATION: {duration:.1f}s")
        self._write(f"STATUS: {status}")
        self._write(separator)
        
        self._file_handle.close()
    
    def __enter__(self):
        """Context manager support."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        status = "ERROR" if exc_type else "SUCCESS"
        self.close(status)


# Использование в main.py
def main():
    with SessionLogger() as logger:
        # Вся обработка запроса
        logger.log_llm_request("расчет реакции...")
        # ...
        
# Альтернативное использование
def main_alternative():
    logger = SessionLogger()
    try:
        # Обработка запроса
        pass
    finally:
        logger.close(status="SUCCESS")
```

### 8.2 Логирование LLM-ответов

```python
def log_llm_request(self, query: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """
    Логирование пользовательского запроса к LLM.
    
    Args:
        query: Текст запроса пользователя
        metadata: Дополнительные метаданные (опционально)
    """
    separator = "=" * 80
    self._write(separator)
    self._write(f"[LLM REQUEST] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    self._write(separator)
    self._write(f"User query:")
    self._write(query)
    self._write("")
    self._write(f"Query length: {len(query)} characters")
    self._write(f"Query type: text")
    
    if metadata:
        self._write("\nMetadata:")
        for key, value in metadata.items():
            self._write(f"  {key}: {value}")
    
    self._write("")


def log_llm_response(
    self,
    response: Dict[str, Any],
    duration: float,
    model: str = "gpt-4-turbo",
    temperature: float = 0.0,
    max_tokens: int = 1000
) -> None:
    """
    Логирование ответа от LLM.
    
    Args:
        response: Parsed JSON-ответ от LLM
        duration: Время обработки в секундах
        model: Название модели LLM
        temperature: Температура модели
        max_tokens: Максимальное количество токенов
    """
    separator = "=" * 80
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    self._write(separator)
    self._write(f"[LLM RESPONSE] {timestamp} (duration: {duration:.3f}s)")
    self._write(separator)
    self._write(f"Model: {model}")
    self._write(f"Temperature: {temperature}")
    self._write(f"Max tokens: {max_tokens}")
    self._write("")
    
    # Сырой JSON
    self._write("Raw response (JSON):")
    formatted_json = json.dumps(response, indent=2, ensure_ascii=False)
    self._write(formatted_json)
    self._write("")
    
    # Извлечённые параметры
    self._write("Extracted parameters:")
    for key, value in response.items():
        status = "✓" if value else "○"
        display_value = value if value else "not specified"
        self._write(f"  {status} {key}: {display_value}")
    
    self._write("")
    self._write("Status: SUCCESS")
    self._write("")


def log_llm_error(self, error: Exception, raw_response: str = "") -> None:
    """
    Логирование ошибки при обработке LLM-ответа.
    
    Args:
        error: Объект исключения
        raw_response: Сырой ответ от LLM (если есть)
    """
    import traceback
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    self._write(f"[LLM ERROR] {timestamp}")
    self._write(f"Error type: {type(error).__name__}")
    self._write(f"Error message: {str(error)}")
    self._write("")
    
    if raw_response:
        self._write("Raw response:")
        self._write(raw_response)
        self._write("")
    
    self._write("Traceback:")
    self._write(traceback.format_exc())
    self._write("")


# Пример использования в Orchestrator
class Orchestrator:
    def __init__(self, session_logger: Optional[SessionLogger] = None):
        self.session_logger = session_logger
    
    def process_query(self, query: str):
        # Логирование запроса
        if self.session_logger:
            self.session_logger.log_llm_request(query)
        
        # Вызов LLM
        start = datetime.now()
        try:
            response = self.llm_client.classify(query)
            duration = (datetime.now() - start).total_seconds()
            
            # Логирование ответа
            if self.session_logger:
                self.session_logger.log_llm_response(
                    response=response,
                    duration=duration,
                    model="gpt-4-turbo"
                )
        except Exception as e:
            # Логирование ошибки
            if self.session_logger:
                self.session_logger.log_llm_error(e, raw_response="...")
            raise
```

### 8.3 Логирование SQL-запросов

```python
def log_database_search(
    self,
    sql_query: str,
    parameters: Dict[str, Any],
    results: List[Dict[str, Any]],
    execution_time: float,
    context: str = ""
) -> None:
    """
    Логирование поиска в базе данных.
    
    Args:
        sql_query: SQL-запрос
        parameters: Параметры запроса
        results: Результаты запроса (список словарей)
        execution_time: Время выполнения в секундах
        context: Контекст поиска (описание)
    """
    separator = "=" * 80
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    self._write(separator)
    self._write(f"[DATABASE SEARCH] {timestamp}")
    self._write(separator)
    
    if context:
        self._write(f"Search context: {context}")
    
    # Параметры поиска
    if "formulas" in parameters:
        formulas_str = ", ".join(f"'{f}'" for f in parameters["formulas"])
        self._write(f"Compounds to search: [{formulas_str}]")
    self._write("")
    
    # SQL запрос
    self._write("SQL Query:")
    # Форматирование SQL для читаемости
    for line in sql_query.strip().split("\n"):
        self._write(f"  {line}")
    self._write("")
    
    # Параметры
    self._write("Parameters:")
    for key, value in parameters.items():
        self._write(f"  {key}: {value}")
    self._write("")
    
    # Статистика
    self._write(f"Execution time: {execution_time*1000:.1f} ms")
    self._write(f"Total records found: {len(results)}")
    display_count = min(30, len(results))
    self._write(f"Records to display: {display_count} (first batch)")
    self._write("")
    
    # Результаты в виде таблицы
    if results:
        self._write(separator)
        self._write(f"[SEARCH RESULTS] First {display_count} records")
        self._write(separator)
        
        # Берём первые 30 записей
        display_results = results[:30]
        
        # Форматирование через tabulate
        table_data = []
        headers = list(display_results[0].keys())
        
        for row in display_results:
            formatted_row = []
            for key in headers:
                value = row[key]
                # Сокращение длинных значений
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                formatted_row.append(value)
            table_data.append(formatted_row)
        
        # Создание таблицы
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            numalign="right",
            stralign="left"
        )
        self._write(table)
        
        if len(results) > 30:
            remaining = len(results) - 30
            self._write(f"\n... and {remaining} more records (not shown)")
    
    self._write("")
    
    # Группировка по формулам (опционально)
    self._log_formula_distribution(results)


def _log_formula_distribution(self, results: List[Dict[str, Any]]) -> None:
    """Логирование распределения результатов по формулам."""
    from collections import defaultdict
    
    formula_groups = defaultdict(list)
    for record in results:
        formula = record.get("formula", "UNKNOWN")
        phase = record.get("phase", "?")
        formula_groups[formula].append(phase)
    
    self._write("Grouped by formula:")
    for formula, phases in sorted(formula_groups.items()):
        phase_str = ", ".join(phases)
        self._write(f"  {formula}: {len(phases)} records ({phase_str})")
    
    self._write("")


# Пример использования в SearchService
class CompoundSearchService:
    def __init__(self, db_path: str, session_logger: Optional[SessionLogger] = None):
        self.db = Database(db_path)
        self.session_logger = session_logger
    
    def search_compounds(self, formulas: List[str], temp_range: tuple) -> List[Dict]:
        sql = """
            SELECT 
                c.compound_id,
                c.formula,
                c.name,
                c.phase,
                c.t_min,
                c.t_max,
                c.h298,
                c.s298
            FROM compounds c
            WHERE c.formula IN ({})
              AND c.t_min <= ?
              AND c.t_max >= ?
            ORDER BY c.formula, c.phase
        """.format(",".join("?" * len(formulas)))
        
        params = {
            "formulas": formulas,
            "temp_min": temp_range[0],
            "temp_max": temp_range[1]
        }
        
        # Выполнение запроса
        start = datetime.now()
        results = self.db.execute(sql, formulas + list(temp_range))
        execution_time = (datetime.now() - start).total_seconds()
        
        # Логирование
        if self.session_logger:
            self.session_logger.log_database_search(
                sql_query=sql,
                parameters=params,
                results=results,
                execution_time=execution_time,
                context="Looking for compounds in reaction equation"
            )
        
        return results
```

### 8.4 Логирование фильтрации

```python
def log_filtering_stage(
    self,
    stage_name: str,
    stage_number: int,
    criteria: Dict[str, Any],
    input_count: int,
    output_count: int,
    removed_records: List[Dict[str, Any]],
    removal_reasons: Dict[str, List[str]]
) -> None:
    """
    Логирование одного этапа фильтрации.
    
    Args:
        stage_name: Название этапа
        stage_number: Номер этапа
        criteria: Критерии фильтрации
        input_count: Количество записей на входе
        output_count: Количество записей на выходе
        removed_records: Удалённые записи
        removal_reasons: Причины удаления (группированные)
    """
    separator = "-" * 80
    
    self._write(separator)
    self._write(f"STAGE {stage_number}: {stage_name}")
    self._write(separator)
    
    # Критерии
    self._write("Criteria:")
    for key, value in criteria.items():
        self._write(f"  - {key}: {value}")
    self._write("")
    
    # Статистика
    removed = input_count - output_count
    self._write(f"Input records: {input_count}")
    self._write(f"Output records: {output_count}")
    self._write(f"Removed: {removed} records")
    self._write("")
    
    # Причины удаления
    if removal_reasons:
        self._write("Removal reasons:")
        for reason, examples in removal_reasons.items():
            self._write(f"  • {reason}: {len(examples)} records")
            for example in examples[:3]:  # Первые 3 примера
                self._write(f"    - {example}")
            if len(examples) > 3:
                self._write(f"    - ... and {len(examples) - 3} more")
    self._write("")


def log_filtering_pipeline_start(
    self,
    input_count: int,
    target_temp_range: tuple,
    required_compounds: List[str]
) -> None:
    """Начало pipeline фильтрации."""
    separator = "=" * 80
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    self._write(separator)
    self._write(f"[FILTERING PIPELINE] {timestamp}")
    self._write(separator)
    self._write(f"Input: {input_count} records from database search")
    self._write(f"Target temperature range: {target_temp_range[0]}-{target_temp_range[1]} K")
    compounds_str = ", ".join(f"'{c}'" for c in required_compounds)
    self._write(f"Required compounds: [{compounds_str}]")
    self._write("")


def log_filtering_complete(
    self,
    final_count: int,
    initial_count: int,
    duration: float,
    warnings: List[str],
    final_records: List[Dict[str, Any]]
) -> None:
    """Завершение pipeline фильтрации."""
    separator = "=" * 80
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    
    removed = initial_count - final_count
    removal_pct = (removed / initial_count * 100) if initial_count > 0 else 0
    
    self._write(separator)
    self._write(f"[FILTERING COMPLETE] {timestamp} (duration: {duration*1000:.0f}ms)")
    self._write(separator)
    self._write(f"Final records: {final_count}")
    self._write(f"Records removed: {removed} ({removal_pct:.1f}%)")
    self._write(f"Warnings: {len(warnings)}")
    self._write(f"Errors: 0")
    self._write("")
    
    # Финальный датасет
    if final_records:
        display_count = min(30, len(final_records))
        self._write(f"Final dataset (first {display_count}):")
        
        # Форматирование через tabulate
        headers = list(final_records[0].keys())
        table_data = []
        
        for record in final_records[:30]:
            row = []
            for key in headers:
                value = record[key]
                # Добавление warnings к значениям
                if key in ["h298", "s298"] and value == 0:
                    value = f"{value} ⚠"
                elif isinstance(value, str) and len(value) > 30:
                    value = value[:27] + "..."
                row.append(value)
            table_data.append(row)
        
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            numalign="right"
        )
        self._write(table)
    
    self._write("")


# Пример использования в FilteringService
class FilteringService:
    def __init__(self, session_logger: Optional[SessionLogger] = None):
        self.session_logger = session_logger
    
    def filter_records(
        self,
        records: List[Dict],
        temp_range: tuple,
        required_compounds: List[str]
    ) -> List[Dict]:
        start_time = datetime.now()
        initial_count = len(records)
        
        # Начало pipeline
        if self.session_logger:
            self.session_logger.log_filtering_pipeline_start(
                input_count=initial_count,
                target_temp_range=temp_range,
                required_compounds=required_compounds
            )
        
        # Stage 1: Temperature filter
        filtered, removed, reasons = self._filter_by_temperature(records, temp_range)
        if self.session_logger:
            self.session_logger.log_filtering_stage(
                stage_name="Temperature Range Filter",
                stage_number=1,
                criteria={
                    "t_min": f"<= {temp_range[0]} K",
                    "t_max": f">= {temp_range[1]} K"
                },
                input_count=len(records),
                output_count=len(filtered),
                removed_records=removed,
                removal_reasons=reasons
            )
        records = filtered
        
        # ... остальные stages ...
        
        # Завершение
        duration = (datetime.now() - start_time).total_seconds()
        if self.session_logger:
            self.session_logger.log_filtering_complete(
                final_count=len(records),
                initial_count=initial_count,
                duration=duration,
                warnings=["Fe2O3(G): H298=0, S298=0"],
                final_records=records
            )
        
        return records
```

**Добавление методов в класс SessionLogger:**
```python
# Все методы выше должны быть добавлены в класс SessionLogger
class SessionLogger:
    # ... __init__, _write, close и т.д. ...
    
    # Методы из 8.2
    def log_llm_request(self, query: str, metadata: Optional[Dict] = None): ...
    def log_llm_response(self, response: Dict, duration: float, ...): ...
    def log_llm_error(self, error: Exception, raw_response: str = ""): ...
    
    # Методы из 8.3
    def log_database_search(self, sql_query: str, parameters: Dict, ...): ...
    def _log_formula_distribution(self, results: List[Dict]): ...
    
    # Методы из 8.4
    def log_filtering_stage(self, stage_name: str, stage_number: int, ...): ...
    def log_filtering_pipeline_start(self, input_count: int, ...): ...
    def log_filtering_complete(self, final_count: int, ...): ...
```


## 9. План реализации

**Этап 1: Создание базового функционала (2-3 часа)**
- Создать класс `SessionLogger`
- Реализовать генерацию имён файлов и создание директорий
- Базовое форматирование записей

**Этап 2: Интеграция с LLM (1-2 часа)**
- Добавить методы логирования LLM-запросов и ответов
- Интегрировать в `Orchestrator`

**Этап 3: Логирование БД (2-3 часа)**
- Реализовать логирование SQL-запросов
- Добавить форматирование через tabulate
- Интегрировать в модули поиска

**Этап 4: Логирование фильтрации (2-3 часа)**
- Добавить логирование этапов фильтрации
- Интегрировать в filtering модули

**Этап 5: Тестирование и доработка (1-2 часа)**
- Протестировать на реальных запросах
- Убедиться в читаемости логов
- Оптимизация производительности

**Общее время: 8-13 часов**

## 10. Критерии приёмки

✅ **Обязательные критерии:**
1. Для каждого запроса создаётся отдельный лог-файл в `logs/sessions`
2. Логируется полный ответ от LLM с извлечёнными параметрами
3. SQL-запросы записываются с параметрами и результатами (первые 30 записей через tabulate)
4. Фиксируются все этапы фильтрации с количеством записей
5. Логи читаемы без дополнительных инструментов
6. Система работает кроссплатформенно (Windows/Linux)
7. Нет заметного снижения производительности

✅ **Желательные критерии:**
1. Автоматическая ротация старых логов (опционально)
2. Конфигурируемый уровень детализации логирования
3. Возможность отключения логирования без изменения кода

✅ **Критерии качества кода:**
1. Следование принципам из `.github/copilot-instructions.md`
2. Типизация (type hints)
3. Документация к публичным методам
4. Минимальная связанность с существующим кодом

