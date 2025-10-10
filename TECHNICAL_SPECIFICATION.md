# Техническое задание: Индивидуальный поиск соединений в термодинамической базе данных

## Обзор проекта

Необходимо изменить пайплайн обработки пользовательских запросов в системе термодинамических AI-агентов так, чтобы каждое вещество из уравнения реакции искалось в базе данных по отдельности. Для каждого вещества должны выбираться наиболее релевантные записи из базы данных с последующей сборкой сводной таблицы.

## Текущая архитектура v2.0

Система использует многоагентную архитектуру с **Agent-to-Agent (A2A) коммуникацией через централизованное хранилище**:

### Компоненты архитектуры

1. **AgentStorage** - Централизованное хранилище для обмена сообщениями
   - Асинхронная обработка сообщений
   - `AgentMessage` с `correlation_id` для трассировки
   - TTL и метаданные для сообщений
   - Очередь сообщений и история

2. **Thermodynamic Agent** - Извлечение параметров из запросов
   - Работает автономно через систему хранилища
   - Использует PydanticAI для структурированного извлечения
   - Отправляет результаты через `AgentMessage`

3. **SQL Generation Agent** - Генерация SQL запросов
   - Принимает извлеченные параметры через хранилище
   - Генерирует оптимизированные SQL запросы
   - Передает запросы Database Agent

4. **Database Agent** - Выполнение SQL и температурная фильтрация
   - Выполняет запросы к SQLite базе данных
   - Применяет температурные фильтры
   - Отправляет результаты на фильтрацию

5. **Results Filtering Agent** - Интеллектуальная фильтрация
   - Выбирает наиболее релевантные записи
   - Ранжирует результаты по релевантности
   - Использует LLM для принятия решений

6. **Thermo Orchestrator** - Координатор системы
   - Управляет потоком выполнения
   - Координирует взаимодействие между агентами
   - Обрабатывает ошибки и таймауты

### Текущий flow обработки

1. **User Input** → Thermo Orchestrator
2. **Parameter Extraction** → Thermodynamic Agent (через AgentStorage)
3. **SQL Generation** → SQL Generation Agent (через AgentStorage)
4. **Database Execution** → Database Agent (через AgentStorage)
5. **Results Filtering** → Results Filtering Agent (через AgentStorage)
6. **Response Formation** → Thermo Orchestrator

## Техническая реализация A2A коммуникации

### AgentStorage архитектура

```python
class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_agent: str  # ID агента-отправителя
    target_agent: str  # ID агента-получателя
    message_type: str  # extract_parameters, generate_query, execute_sql, etc.
    payload: Dict[str, Any]  # Данные сообщения
    correlation_id: Optional[str] = None  # ID связанного сообщения
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AgentStorage:
    # Централизованное хранилище для A2A коммуникации
    def send_message(self, source_agent, target_agent, message_type, payload, correlation_id=None)
    def receive_messages(self, agent_id, message_type=None)
    def set(self, key, value, ttl_seconds=None)
    def get(self, key, default=None)
```

### Паттерны взаимодействия

**Асинхронная обработка сообщений:**
- Агенты работают в цикле `while running` с `poll_interval`
- Каждый агент слушает свои типы сообщений
- Используются `correlation_id` для связи запросов и ответов

**Пример коммуникации:**
```python
# Thermo Agent отправляет запрос SQL Agent
message_id = storage.send_message(
    source_agent="thermo_agent",
    target_agent="sql_agent",
    message_type="generate_query",
    payload={"sql_hint": "...", "extracted_params": {...}},
    correlation_id=original_message_id
)

# SQL Agent обрабатывает и отвечает
storage.send_message(
    source_agent="sql_agent",
    target_agent="thermo_agent",
    message_type="response",
    correlation_id=message_id,
    payload={"status": "success", "result_key": "..."}
)
```

### Проблемы текущего подхода

1. **Неточность поиска**: Общие запросы могут находить нерелевантные записи для отдельных веществ
2. **Сложность SQL**: Один запрос для многих веществ становится громоздким
3. **Низкое качество фильтрации**: Фильтрация всех веществ вместе менее эффективна
4. **Потеря релевантных данных**: Уникальные записи для отдельных веществ могут быть упущены

## Структура базы данных compounds

**Основные характеристики:**
- **316,434 записей**, **32,790 уникальных химических формул**
- **23 колонки** включая термодинамические свойства
- **Фазы**: s (solid), l (liquid), g (gas), aq (aqueous), ионные формы (+, -)
- **Температурные диапазоны**: Tmin, Tmax для каждой записи
- **Надежность данных**: ReliabilityClass (1-3, где 1 - наиболее надежные)

**Ключевые поля для поиска:**
- `Formula` (TEXT): Химическая формула - основной ключ поиска
- `Phase` (TEXT): Фаза вещества (s/l/g/aq)
- `Tmin`/`Tmax` (REAL): Температурный диапазон применимости
- `ReliabilityClass` (INTEGER): Класс надежности данных
- `FirstName`/`SecondName` (TEXT): Систематические названия
- `CAS` (TEXT): CAS номер для уникальной идентификации

## Оптимальные SQL паттерны для индивидуального поиска

### Базовый паттерн для одного вещества
```sql
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%')
ORDER BY
  CASE
    WHEN Phase = 'g' AND 673 >= Tmin AND 673 <= Tmax THEN 1
    WHEN Phase = 'l' AND 673 >= Tmin AND 673 <= Tmax THEN 2
    WHEN ReliabilityClass = 1 THEN 3
    ELSE 4
  END
LIMIT 100
```

### Продвинутый паттерн с фазовыми приоритетами
```sql
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'TiO2' OR Formula LIKE 'TiO2(%' OR
 TRIM(Formula) = 'TiO' OR Formula LIKE 'TiO(%')
AND (
  (Tmin IS NOT NULL AND Tmax IS NOT NULL AND 673 >= Tmin AND 673 <= Tmax) OR
  (Tmin IS NULL) OR (Tmax IS NULL)
))
ORDER BY
CASE
    WHEN TRIM(Formula) = 'TiO2' AND Phase IN ('s', 'l') THEN 1
    WHEN TRIM(Formula) = 'TiO2' AND ReliabilityClass = 1 THEN 2
    WHEN Formula LIKE 'TiO2(%' AND Phase = 's' THEN 3
    WHEN ReliabilityClass = 1 THEN 4
    ELSE 5
  END,
  (Tmin IS NOT NULL AND Tmax IS NOT NULL AND 673 >= Tmin AND 673 <= Tmax) DESC,
  ReliabilityClass ASC
LIMIT 100
```

### Паттерн для поиска с ионными формами
```sql
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'NO3' OR Formula LIKE 'NO3(%' OR
 TRIM(Formula) = 'NO3-' OR Formula LIKE 'NO3-(%' OR
 TRIM(Formula) = 'HNO3' OR Formula LIKE 'HNO3(%')
ORDER BY
  CASE
    WHEN Formula LIKE '%NO3%-%' AND Phase = 'aq' THEN 1
    WHEN TRIM(Formula) = 'HNO3' AND Phase = 'l' THEN 2
    WHEN ReliabilityClass = 1 THEN 3
    ELSE 4
  END
LIMIT 100
```

### Температурная фильтрация на SQL уровне
```sql
-- Фильтрация по пересечению температурных интервалов
WHERE (Tmin IS NULL OR Tmax IS NULL OR 673 >= Tmin) AND
      (Tmin IS NULL OR Tmax IS NULL OR 673 <= Tmax)
```

### Оптимизация по ReliabilityClass
```sql
ORDER BY ReliabilityClass ASC,  -- 1 = наиболее надежные
         ABS(COALESCE(Tmin, 673) - 673) ASC  -- ближайшие температурные диапазоны
```

## Стратегии поиска для разных типов соединений

### 1. Простые бинарные соединения (H2O, CO2, NH3)
```sql
-- Приоритет: фазовые варианты, затем ReliabilityClass
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%')
AND температура в диапазоне [Tmin, Tmax])
ORDER BY
  CASE WHEN Phase = 'g' AND temp >= Tmin AND temp <= Tmax THEN 1 END,
  CASE WHEN Phase = 'l' AND temp >= Tmin AND temp <= Tmax THEN 2 END,
  ReliabilityClass ASC
LIMIT 100
```

### 2. Оксиды и соли (TiO2, Fe2O3, CaCO3)
```sql
-- Приоритет: твердые фазы, высокая надежность
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'TiO2' OR Formula LIKE 'TiO2(%')
AND температура в диапазоне)
ORDER BY
  CASE WHEN Phase IN ('s', 'l') THEN 1 ELSE 2 END,
  ReliabilityClass ASC,
  ABS(COALESCE(Tmin, temp) - temp) ASC
LIMIT 100
```

### 3. Ионные соединения и кислоты (HNO3, H2SO4)
```sql
-- Приоритет: водные растворы, затем чистые вещества
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'HNO3' OR Formula LIKE 'HNO3(%' OR
 TRIM(Formula) = 'NO3-' OR Formula LIKE 'NO3-(%')
AND температура в диапазоне)
ORDER BY
  CASE WHEN Phase = 'aq' AND Formula LIKE '%-%' THEN 1 END,
  CASE WHEN Phase = 'l' AND TRIM(Formula) = 'HNO3' THEN 2 END,
  ReliabilityClass ASC
LIMIT 100
```

### 4. Металлы и сплавы (Fe, Cu, Al)
```sql
-- Приоритет: твердые фазы, металлические состояния
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'Fe' OR Formula LIKE 'Fe(%')
AND температура в диапазоне)
ORDER BY
  CASE WHEN Phase = 's' THEN 1 END,
  CASE WHEN Phase = 'l' THEN 2 END,
  ReliabilityClass ASC
LIMIT 100
```

### 5. Газы (O2, N2, H2, CO)
```sql
-- Приоритет: газообразные фазы при нужной температуре
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'O2' OR Formula LIKE 'O2(%')
AND температура в диапазоне)
ORDER BY
  CASE WHEN Phase = 'g' AND temp >= Tmin AND temp <= Tmax THEN 1 END,
  ReliabilityClass ASC,
  ABS(COALESCE(Tmin, temp) - temp) ASC
LIMIT 100
```

## Оптимизация производительности

### Индексация для быстрых запросов
- `Formula` с COLLATE NOCASE для регистронезависимого поиска
- `Tmin`, `Tmax` для температурной фильтрации
- `ReliabilityClass` для сортировки по надежности
- Составной индекс `(Formula, Phase, ReliabilityClass)`

### Кэширование результатов
```sql
-- Кэшировать запросы для повторного использования
CREATE TABLE query_cache AS
SELECT query_hash, results, timestamp
FROM recent_individual_queries
WHERE timestamp > datetime('now', '-1 hour')
```

## Текущие модели данных v2.0

### Основные Pydantic модели в системе

#### ExtractedParameters (термодинамический агент)
```python
class ExtractedParameters(BaseModel):
    intent: str                              # "lookup", "calculation", "reaction", "comparison"
    compounds: List[str]                     # Химические формулы (все реагенты и продукты)
    temperature_k: float                     # Температура в Кельвинах
    temperature_range_k: List[float]         # Диапазон температур [min, max]
    phases: List[str]                        # Фазовые состояния ["s", "l", "g", "aq"]
    properties: List[str]                    # Требуемые свойства ["basic", "all", "thermal"]
    sql_query_hint: str                      # Подсказка для генерации SQL
    reaction_equation: Optional[str] = None  # Уравнение реакции (для intent="reaction")
```

#### SQLQueryResult (SQL генерация агент)
```python
class SQLQueryResult(BaseModel):
    sql_query: str              # Сгенерированный SQL запрос
    explanation: str            # Краткое объяснение запроса
    expected_columns: list[str] # Ожидаемые колонки в результате
```

#### OrchestratorRequest/Response (оркестратор)
```python
class OrchestratorRequest(BaseModel):
    user_query: str                    # Исходный запрос пользователя
    request_type: str = "thermodynamic"  # Тип запроса
    options: Dict[str, Any] = Field(default_factory=dict)

class OrchestratorResponse(BaseModel):
    success: bool                      # Успешность обработки
    result: Dict[str, Any]             # Результаты обработки
    errors: list[str] = Field(default_factory=list)  # Список ошибок
    trace: list[str] = Field(default_factory=list)    # Трассировка выполнения
```

#### AgentMessage (коммуникация между агентами)
```python
class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_agent: str               # ID агента-отправителя
    target_agent: str               # ID агента-получателя
    message_type: str               # Тип сообщения (request, response, error)
    payload: Dict[str, Any]         # Данные сообщения
    correlation_id: Optional[str] = None  # ID связанного сообщения
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### Конфигурация агентов (Dependency Injection)

#### ThermoAgentConfig
```python
@dataclass
class ThermoAgentConfig:
    agent_id: str = "thermo_agent"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 1.0
    max_retries: int = 2
```

#### SQLAgentConfig
```python
@dataclass
class SQLAgentConfig:
    agent_id: str = "sql_agent"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"
    db_path: str = "data/thermo_data.db"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 1.0
    max_retries: int = 2
```

#### OrchestratorConfig
```python
@dataclass
class OrchestratorConfig:
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    max_retries: int = 2
    timeout_seconds: int = 60
```

### PydanticAI фреймворк v1.0.8

Система использует PydanticAI с паттернами:
- `Agent` класс для создания агентов
- `RunContext[ConfigType]` для dependency injection
- `@agent.tool` для добавления инструментов
- `output_type` для структурированного вывода
- Асинхронная обработка через `async/await`

### Логирование и сессии

#### SessionLogger
```python
class SessionLogger:
    # Сессионное логирование для отладки и анализа
    def log_extracted_parameters(self, params: ExtractedParameters)
    def log_sql_generation(self, sql_query: str, columns: List[str], explanation: str)
    def log_info(self, message: str)
    def log_error(self, error: str)
```

**Особенности логирования:**
- Все сессии логируются в `logs/sessions/`
- Детальная трассировка всех этапов обработки
- Корреляция запросов через `correlation_id`
- Структурированные логи для анализа производительности

## Новая архитектура

### Основная концепция
Параллельный индивидуальный поиск каждого вещества с последующей агрегацией результатов.

### Изменения в агентах

#### 1. Thermodynamic Agent (изменения)
- **Задача**: Извлекать параметры и разделять соединения для индивидуальной обработки
- **Изменения**:
  - Добавить логику разделения соединений при извлечении параметров
  - Сохранять общую информацию (температура, фазы) для всех веществ
  - Формировать список индивидуальных запросов для каждого вещества
  - Создавать новую модель данных: `IndividualSearchRequest`

#### 2. Individual Search Agent (НОВЫЙ агент)
- **Задача**: Координировать параллельный поиск веществ
- **Функционал**:
  - Получать список веществ от Thermo Agent
  - Для каждого вещества создавать отдельный запрос к SQL Agent
  - Координировать параллельную обработку запросов
  - Собирать индивидуальные результаты в общую структуру
  - Управлять таймаутами и ошибками для каждого запроса

#### 3. SQL Generation Agent (изменения)
- **Задача**: Оптимизированная генерация SQL для одного вещества
- **Изменения**:
  - Генерация индивидуальных SQL запросов для одного соединения
  - Использование `TRIM(Formula)` для точных совпадений
  - Паттерны `LIKE 'Formula(%'` для фазовых/ионных форм
  - Температурная фильтрация на SQL уровне через Tmin/Tmax
  - Сортировка по ReliabilityClass + фазовые приоритеты
  - LIMIT 100 для контроля количества результатов
  - Умное создание синонимов и вариантов формул

#### 4. Database Agent (изменения)
- **Задача**: Эффективное выполнение индивидуальных запросов
- **Изменения**:
  - Оптимизированное выполнение запросов для одного вещества
  - Улучшенная температурная фильтрация для индивидуальных соединений
  - Кэширование результатов для повторных запросов

#### 5. Results Filtering Agent (изменения)
- **Задача**: Интеллектуальная фильтрация для каждого вещества
- **Изменения**:
  - Индивидуальная фильтрация для каждого вещества
  - Улучшенный алгоритм выбора наиболее релевантных записей
  - Создание сводной таблицы из отобранных записей
  - Ранжирование результатов по релевантности

#### 6. Orchestrator (изменения)
- **Задача**: Координация нового пайплайна обработки
- **Изменения**:
  - Управление Individual Search Agent
  - Агрегация результатов в финальную сводную таблицу
  - Обработка ошибок для отдельных веществ
  - Формирование финального ответа пользователю

### Модели данных

#### IndividualSearchRequest
```python
class IndividualSearchRequest(BaseModel):
    compounds: List[str]           # Список соединений
    common_params: Dict            # Общие параметры (температура, фазы)
    search_strategy: str           # Стратегия поиска
    correlation_id: str            # ID для корреляции
```

#### IndividualCompoundResult
```python
class IndividualCompoundResult(BaseModel):
    compound: str                  # Химическая формула
    search_results: List[Dict]     # Результаты поиска
    selected_records: List[Dict]   # Отобранные записи
    confidence: float              # Уверенность в результате
    errors: List[str]              # Ошибки поиска
```

#### AggregatedResults
```python
class AggregatedResults(BaseModel):
    individual_results: List[IndividualCompoundResult]  # Результаты по веществам
    summary_table: List[Dict]                          # Сводная таблица
    overall_confidence: float                           # Общая уверенность
    missing_compounds: List[str]                        # Отсутствующие вещества
    warnings: List[str]                                 # Предупреждения
```

### Пример пайплайна обработки с SQL паттернами

**Запрос пользователя:** "Найди данные для реакции TiO2 + 2HCl → TiCl4 + H2O при 400°C"

#### Шаг 1: Parameter Extraction (Thermodynamic Agent)
```
Извлеченные параметры:
- compounds: ["TiO2", "HCl", "TiCl4", "H2O"]
- temperature: 673K (400°C + 273)
- phases: ["s", "aq", "l", "g"] (предполагаемые)
- reaction_type: "acid_dissolution"
```

#### Шаг 2: Individual Search Coordination
```
IndividualSearchRequest:
- compounds: ["TiO2", "HCl", "TiCl4", "H2O"]
- common_params: {temperature: 673, phases: ["s","aq","l","g"]}
- correlation_id: "req_12345"
```

#### Шаг 3: Parallel SQL Generation (для каждого вещества)

**Для TiO2:**
```sql
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'TiO2' OR Formula LIKE 'TiO2(%')
AND (Tmin IS NULL OR Tmax IS NULL OR (673 >= Tmin AND 673 <= Tmax)))
ORDER BY
  CASE WHEN Phase IN ('s', 'l') THEN 1 ELSE 2 END,
  ReliabilityClass ASC,
  ABS(COALESCE(Tmin, 673) - 673) ASC
LIMIT 100
```

**Для HCl:**
```sql
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'HCl' OR Formula LIKE 'HCl(%' OR
 TRIM(Formula) = 'Cl-' OR Formula LIKE 'Cl-(%')
AND (Tmin IS NULL OR Tmax IS NULL OR (673 >= Tmin AND 673 <= Tmax)))
ORDER BY
  CASE WHEN Phase = 'aq' AND Formula LIKE '%-%' THEN 1 END,
  CASE WHEN Phase = 'g' AND TRIM(Formula) = 'HCl' THEN 2 END,
  ReliabilityClass ASC
LIMIT 100
```

#### Шаг 4: Parallel Database Execution
- TiO2: 45 записей найдено
- HCl: 82 записей найдено
- TiCl4: 23 записей найдено
- H2O: 156 записей найдено

#### Шаг 5: Individual Filtering
- TiO2: выбраны 3 наиболее релевантные записи (твердая фаза, ReliabilityClass=1)
- HCl: выбраны 2 записи (водный раствор + газ)
- TiCl4: выбраны 1 запись (жидкая фаза)
- H2O: выбраны 3 записи (пар + жидкость)

#### Шаг 6: Results Aggregation
```python
AggregatedResults:
{
  "individual_results": [
    {"compound": "TiO2", "selected_records": 3, "confidence": 0.95},
    {"compound": "HCl", "selected_records": 2, "confidence": 0.88},
    {"compound": "TiCl4", "selected_records": 1, "confidence": 0.92},
    {"compound": "H2O", "selected_records": 3, "confidence": 0.90}
  ],
  "summary_table": 9 записей,
  "overall_confidence": 0.91,
  "missing_compounds": [],
  "warnings": ["Для HCl рассматривать как в растворе, так и в газовой фазе"]
}
```

### Актуальный flow обработки (текущая реализация)

#### Реальный поток в системе v2.0:
1. **User Input** → Thermo Orchestrator получает запрос
2. **Thermo Orchestrator** отправляет сообщение `extract_parameters` в AgentStorage
3. **Thermodynamic Agent** принимает сообщение, извлекает параметры, отправляет ответ
4. **Thermodynamic Agent** автоматически отправляет сообщение `generate_query` SQL Agent
5. **SQL Generation Agent** генерирует запрос, отправляет `execute_sql` Database Agent
6. **Database Agent** выполняет запрос, отправляет `results_filtered` Filtering Agent
7. **Results Filtering Agent** фильтрует результаты, возвращает ответ SQL Agent
8. **SQL Agent** отправляет уведомление `sql_ready` Orchestrator
9. **Thermo Orchestrator** собирает все результаты и формирует ответ пользователю

### Новый flow с Individual Search Agent

#### Интегрированный flow:
1. **User Input** → Thermo Orchestrator
2. **Parameter Extraction** → Thermodynamic Agent (через AgentStorage, с разделением веществ)
3. **Individual Search Coordination** → Individual Search Agent (NEW)
4. **Parallel SQL Generation** → SQL Agent (для каждого вещества, через AgentStorage)
5. **Parallel Database Execution** → Database Agent (индивидуальные запросы, через AgentStorage)
6. **Individual Filtering** → Results Filtering Agent (для каждого вещества, через AgentStorage)
7. **Results Aggregation** → Individual Search Agent (собирает через AgentStorage)
8. **Response Formation** → Thermo Orchestrator (через AgentStorage)

### Ключевые изменения в коммуникации

**Новые типы сообщений:**
- `individual_search_request` - запрос на индивидуальный поиск
- `compound_search_result` - результат поиска для одного вещества
- `parallel_coordination` - координация параллельных запросов
- `aggregation_complete` - завершение агрегации результатов

**Обновленная маршрутизация:**
- Individual Search Agent координирует множественные запросы к SQL Agent
- Используются уникальные `correlation_id` для каждого вещества
- Агрегация результатов происходит через хранилище

### Структура проекта v2.0

```
src/thermo_agents/
├── __init__.py
├── agent_storage.py              # Централизованное хранилище A2A коммуникации
├── thermodynamic_agent.py        # Агент извлечения параметров (PydanticAI)
├── sql_generation_agent.py       # Агент генерации SQL запросов (PydanticAI)
├── database_agent.py             # Агент выполнения SQL и температурной фильтрации
├── results_filtering_agent.py    # Агент интеллектуальной фильтрации (LLM)
├── orchestrator.py               # Координатор агентов
├── prompts.py                    # Системные промпты для всех агентов
└── thermo_agents_logger.py       # Система сессионного логирования

data/
└── thermo_data.db                # SQLite база: 316,434 записей, 32,790 соединений

logs/sessions/                    # Логи сессий с детальной трассировкой
docs/                             # Jupyter notebooks и документация
main.py                           # CLI приложение с ThermoSystem
pyproject.toml                    # Конфигурация uv с PydanticAI 1.0.8
.env                              # Переменные окружения (OPENROUTER_API_KEY и т.д.)
```

### Технический стек и зависимости

**Core фреймворки:**
- **PydanticAI 1.0.8** - основной фреймворк для AI агентов
- **Pydantic** - валидация и модели данных
- **SQLite** - база данных термодинамических соединений
- **asyncio** - асинхронная обработка

**Управление зависимостями:**
- **uv** - современный менеджер пакетов (замена pip/conda)
- **python-dotenv** - управление переменными окружения
- **ipykernel** - поддержка Jupyter notebooks

### Конфигурация окружения

**Переменные окружения (.env):**
```bash
OPENROUTER_API_KEY=your_api_key_here
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o
DB_PATH=data/thermo_data.db
LOG_LEVEL=INFO
```

### Особенности реализации

**Асинхронная архитектура:**
- Все агенты работают в цикле `while running`
- Используют `poll_interval` для проверки сообщений
- Поддерживают `start()`/`stop()` методы для управления жизненным циклом

**Обработка ошибок:**
- Graceful degradation при ошибках отдельных агентов
- Таймауты для всех операций
- Fallback ответы при недоступности LLM
- Комплексное логирование всех ошибок

**Инкапсуляция агентов:**
- Полная независимость агентов друг от друга
- Коммуникация только через AgentStorage
- Инъекция зависимостей через dataclass конфигурации
- Возможность standalone запуска каждого агента

### Промпты

#### Обновление EXTRACT_INPUTS_PROMPT
- Добавить логику разделения соединений
- Указывать необходимость индивидуального поиска
- Сохранять контекст реакции

#### Новый INDIVIDUAL_SEARCH_COORDINATION_PROMPT
- Координация параллельных запросов
- Управление таймаутами и ошибками
- Агрегация результатов

#### Обновление SQL_GENERATION_PROMPT
- Оптимизация для одного вещества
- Улучшенные паттерны поиска
- Индивидуальная фильтрация
- Температурные диапазоны на SQL уровне
- Приоритезация по ReliabilityClass

**Пример промпта для SQL Generation Agent:**
```
Генерируй SQL запрос для поиска одного химического соединения в таблице compounds.

Правила:
1. Используй TRIM(Formula) = '{compound}' для точного совпадения
2. Добавь Formula LIKE '{compound}(%' для фазовых/ионных вариантов
3. Включи температурную фильтрацию: (Tmin <= {temp} <= Tmax) OR Tmin IS NULL
4. Сортируй по ReliabilityClass ASC (1 = лучшие данные)
5. Используй LIMIT 100 для контроля результатов
6. Учитывай фазовые приоритеты в ORDER BY

Пример для TiO2 при T=673K:
SELECT * FROM compounds WHERE
(TRIM(Formula) = 'TiO2' OR Formula LIKE 'TiO2(%')
AND (Tmin IS NULL OR Tmax IS NULL OR (673 >= Tmin AND 673 <= Tmax)))
ORDER BY ReliabilityClass ASC,
         CASE WHEN Phase IN ('s','l') THEN 1 ELSE 2 END
LIMIT 100
```

## Преимущества нового подхода

1. **Точность поиска**: Индивидуальный поиск для каждого вещества улучшает релевантность
2. **Оптимизация**: SQL запросы становятся проще и быстрее
3. **Параллельность**: Возможность одновременной обработки нескольких веществ
4. **Масштабируемость**: Легко добавлять новые вещества в реакцию
5. **Качество результатов**: Лучшее покрытие для каждого вещества
6. **Отказоустойчивость**: Ошибка с одним веществе не останавливает весь процесс
7. **Гибкость**: Возможность применения разных стратегий поиска для разных веществ

## План реализации v2.0

### Этап 1: Фундаментальные изменения (3-4 дня)

**1.1 Создание Individual Search Agent**
- Создать `src/thermo_agents/individual_search_agent.py`
- Реализовать `IndividualSearchAgentConfig` (dataclass)
- Внедрить `IndividualSearchRequest` и `IndividualCompoundResult` модели
- Настроить A2A коммуникацию через AgentStorage
- Реализовать асинхронную обработку с `poll_interval`

**1.2 Модификация Thermodynamic Agent**
- Обновить `EXTRACT_INPUTS_PROMPT` для разделения соединений
- Добавить логику создания `IndividualSearchRequest`
- Реализовать новую коммуникацию с Individual Search Agent
- Сохранить обратную совместимость с текущим flow

**1.3 Обновление моделей данных**
- Добавить `IndividualSearchRequest`, `IndividualCompoundResult`, `AggregatedResults`
- Обновить `AgentMessage` для новых типов сообщений
- Расширить `ExtractedParameters` при необходимости

### Этап 2: Оптимизация поиска (2-3 дня)

**2.1 Модификация SQL Generation Agent**
- Обновить `SQL_GENERATION_PROMPT` для одного вещества
- Реализовать умные паттерны поиска (`TRIM(Formula)`, `LIKE 'Formula(%'`)
- Добавить температурную фильтрацию на SQL уровне
- Внедрить сортировку по ReliabilityClass + фазовые приоритеты
- Настроить LIMIT 100 для контроля результатов

**2.2 Оптимизация Database Agent**
- Реализовать кэширование результатов для повторных запросов
- Улучшить температурную фильтрацию для индивидуальных соединений
- Оптимизировать выполнение запросов для одного вещества

**2.3 Улучшение Results Filtering Agent**
- Реализовать индивидуальную фильтрацию для каждого вещества
- Обновить `RESULT_FILTER_PROMPT` для работы с отдельными соединениями
- Улучшить алгоритм выбора наиболее релевантных записей
- Добавить ранжирование результатов по релевантности

### Этап 3: Интеграция (2 дня)

**3.1 Обновление Orchestrator**
- Интегрировать Individual Search Agent в flow обработки
- Обновить логику маршрутизации сообщений
- Реализовать обработку ошибок для отдельных веществ
- Добавить агрегацию результатов в финальную сводную таблицу

**3.2 Обновление системы промптов**
- Создать `INDIVIDUAL_SEARCH_COORDINATION_PROMPT`
- Обновить все существующие промпты для новой архитектуры
- Добавить промпты для обработки ошибок и таймаутов

**3.3 Тестирование и отладка**
- Базовое тестирование нового flow
- Отладка A2A коммуникации
- Проверка корреляции запросов через `correlation_id`

### Этап 4: Комплексное тестирование (2-3 дня)

**4.1 Unit тесты**
- `tests/test_individual_search_agent.py`
- Тесты для обновленных агентов
- Тесты моделей данных

**4.2 Интеграционные тесты**
- `tests/test_individual_search_integration.py`
- Тестирование полного пайплайна
- Тестирование параллельной обработки

**4.3 Тестирование производительности**
- Сравнение с текущим подходом
- Тестирование таймаутов и обработки ошибок
- Анализ потребления ресурсов

**4.4 Валидация**
- Тестирование на реальных химических реакциях
- Проверка качества результатов
- Валидация SQL паттернов

## Файлы для изменения/создания

### Изменения:
- `src/thermo_agents/thermodynamic_agent.py`
- `src/thermo_agents/sql_generation_agent.py`
- `src/thermo_agents/database_agent.py`
- `src/thermo_agents/results_filtering_agent.py`
- `src/thermo_agents/orchestrator.py`
- `src/thermo_agents/prompts.py`

### Новые файлы:
- `src/thermo_agents/individual_search_agent.py`
- `tests/test_individual_search_agent.py`
- `tests/test_individual_search_integration.py`

## Критерии успеха

1. **Функциональность**: Каждое вещество ищется индивидуально
2. **Точность**: Улучшение релевантности результатов на 30%+
3. **Производительность**: Время обработки не увеличивается более чем на 20%
4. **Надежность**: Система работает при ошибке поиска отдельных веществ
5. **Качество**: Сводная таблица содержит наиболее релевантные данные
6. **SQL оптимизация**: Каждый запрос возвращает не более 100 записей
7. **Температурная точность**: Улучшенное попадание в температурные диапазоны на 50%+
8. **Фазовая релевантность**: Правильное определение фаз для 90%+ соединений
9. **Reliability приоритезация**: ReliabilityClass=1 записи выбираются в первую очередь
10. **Полнота покрытия**: Находятся все варианты формул (основные, ионные, фазовые)

## Риски и митигация

1. **Сложность координации** → Тщательное проектирование Individual Search Agent
2. **Производительность** → Асинхронная обработка и кэширование
3. **Совместимость** → Плавный переход с обратной совместимостью
4. **Отладка** → Улучшенное логирование и трассировка

## Дедлайны

- **Этап 1**: 3-4 дня
- **Этап 2**: 2-3 дня
- **Этап 3**: 2 дня
- **Этап 4**: 2-3 дня

**Общий срок**: 9-12 дней