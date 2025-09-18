---
applyTo: '**'
---
# Архитектура проекта Thermo Agents v2.0

## Обзор системы

Проект представляет собой многоагентную систему для анализа термодинамических данных, построенную на базе PydanticAI с использованием архитектуры Agent-to-Agent (A2A) коммуникации через централизованное хранилище.

## Ключевые принципы архитектуры

### 1. Полная инкапсуляция агентов
- **Никаких прямых вызовов**: Агенты не вызывают друг друга напрямую
- **Message-passing**: Вся коммуникация через структурированные сообщения
- **Storage-based communication**: Централизованное хранилище для обмена данными
- **Автономность**: Каждый агент работает независимо в своем цикле

### 2. Storage Architecture (из PydanticAI)
Основан на официальной документации PydanticAI:
- **Centralized Storage**: Единое хранилище для всех агентов
- **Message Queue**: Очередь сообщений между агентами
- **Session Management**: Управление сессиями агентов
- **TTL Support**: Автоматическое удаление устаревших данных

### 3. Асинхронная обработка
- **Event Loop**: Каждый агент работает в своем event loop
- **Non-blocking**: Все операции неблокирующие
- **Concurrent Processing**: Параллельная обработка сообщений

## Компонентная архитектура v2.0

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                 AGENT STORAGE                                         │
│                              (Централизованное хранилище)                            │
│ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────────┐            │
│ │   Storage   │ │ Message Queue│ │   Sessions   │ │   Message History │            │
│ │ Key-Value   │ │   Messages   │ │ Agent States │ │    Audit Trail    │            │
│ └─────────────┘ └──────────────┘ └──────────────┘ └───────────────────┘            │
└──────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────────┘
       │              │              │              │              │
       │   Messages   │   Messages   │   Messages   │   Messages   │   Messages
       │              │              │              │              │
┌──────▼─────┐ ┌─────▼──────┐ ┌─────▼────┐ ┌───────▼────┐ ┌────────▼────────┐
│            │ │            │ │          │ │            │ │                 │
│ORCHESTRATOR│ │   THERMO   │ │   SQL    │ │ DATABASE   │ │    RESULTS      │
│   AGENT    │ │   AGENT    │ │  AGENT   │ │   AGENT    │ │   FILTERING     │
│            │ │            │ │          │ │            │ │     AGENT       │
│┌──────────┐│ │┌──────────┐│ │┌────────┐│ │┌──────────┐│ │┌───────────────┐│
││  Route   ││ ││ Extract  ││ ││Generate││ ││ Execute  ││ ││    Filter     ││
││ Messages ││ ││Parameters││ ││   SQL  ││ ││   SQL    ││ ││   Results     ││
│├──────────┤│ │├──────────┤│ │├────────┤│ │├──────────┤│ │├───────────────┤│
││Coordinate││ ││ Convert  ││ ││ Clean  ││ ││Filter by ││ ││ LLM Analysis  ││
││  Flow    ││ ││  Units   ││ ││ Query  ││ ││   Temp   ││ ││   Selection   ││
│├──────────┤│ │├──────────┤│ │├────────┤│ │├──────────┤│ │├───────────────┤│
││  Error   ││ ││ Validate ││ ││Explain ││ ││ Return   ││ ││  Temperature  ││
││Handling  ││ ││  Input   ││ ││ Query  ││ ││ Results  ││ ││   Coverage    ││
│└──────────┘│ │└──────────┘│ │└────────┘│ │└──────────┘│ │└───────────────┘│
└────────────┘ └────────────┘ └──────────┘ └────────────┘ └─────────────────┘
      ▲                                                            │
      │                                                            │
┌─────┴────────┐                                          ┌───────▼──────┐
│  CLI/API     │                                          │   SQLite DB  │
│  Interface   │                                          │(316,434 recs)│
│ ThermoSystem │                                          │ 32,790 comp. │
└──────────────┘                                          └──────────────┘
```

## Поток коммуникации между агентами

### Message Flow через Storage
```
User Request (CLI/ThermoSystem)
    │
    ▼
Orchestrator (ThermoOrchestrator)
    │
    ├─► Storage.send_message(
    │     source: "orchestrator",
    │     target: "thermo_agent",
    │     type: "extract_parameters",
    │     payload: {"user_query": "..."}
    │   )
    │
    ▼
Thermo Agent (ThermodynamicAgent)
    │
    ├─► Storage.receive_messages("thermo_agent", "extract_parameters")
    ├─► Process using PydanticAI Agent with EXTRACT_INPUTS_PROMPT
    ├─► Extract parameters (compounds, temperature, phases, properties)
    │
    ├─► Storage.set("thermo_result_{msg_id}", extracted_params)
    ├─► Send response to orchestrator
    │
    ├─► Storage.send_message(
    │     source: "thermo_agent",
    │     target: "sql_agent",
    │     type: "generate_query",
    │     payload: {sql_hint, extracted_params}
    │   )
    │
    ▼
SQL Agent (SQLGenerationAgent)
    │
    ├─► Storage.receive_messages("sql_agent", "generate_query")
    ├─► Process using PydanticAI Agent with SQL_GENERATION_PROMPT
    ├─► Generate SQL query from hint and parameters
    ├─► Clean query (remove HTML entities, take first statement)
    │
    ├─► Storage.send_message(
    │     source: "sql_agent",
    │     target: "database_agent",
    │     type: "execute_sql",
    │     payload: {sql_query, extracted_params}
    │   )
    │
    ▼
Database Agent (DatabaseAgent)
    │
    ├─► Storage.receive_messages("database_agent", "execute_sql")
    ├─► Execute SQL query on SQLite database
    ├─► Apply temperature range filtering if needed
    ├─► Return execution results
    │
    ├─► Storage.send_message(
    │     source: "database_agent",
    │     target: "results_filtering_agent",
    │     type: "filter_results",
    │     payload: {execution_result, extracted_params}
    │   )
    │
    ▼
Results Filtering Agent (ResultsFilteringAgent)
    │
    ├─► Storage.receive_messages("results_filtering_agent", "filter_results")
    ├─► Apply temperature range pre-filtering
    ├─► Use LLM with RESULT_FILTER_ENGLISH_PROMPT for intelligent selection
    ├─► Select most relevant records per compound/phase
    ├─► Generate reasoning and statistics
    │
    ├─► Storage.send_message(
    │     source: "results_filtering_agent",
    │     target: "sql_agent",
    │     type: "results_filtered",
    │     payload: {filtered_result, selected_records}
    │   )
    │
    ▼
SQL Agent (consolidates all results)
    │
    ├─► Receive filtering results
    ├─► Combine SQL query + execution result + filtered result
    ├─► Storage.set("sql_result_{msg_id}", complete_result)
    │
    ├─► Storage.send_message(
    │     source: "sql_agent",
    │     target: "orchestrator",
    │     type: "sql_ready",
    │     payload: {result_key, sql_query}
    │   )
    │
    ▼
Orchestrator (receives final result)
    │
    ├─► Get complete result from storage
    ├─► Format response with all components:
    │   • Extracted parameters
    │   • Generated SQL query with explanation
    │   • Raw execution results
    │   • Filtered/selected records with reasoning
    │
    └─► Return to user via ThermoSystem
```

## Детальная архитектура компонентов

### Agent Storage (agent_storage.py)
```python
@dataclass
class AgentStorage:
    """Централизованное хранилище для A2A коммуникации"""

    # Хранилище данных
    _storage: Dict[str, StorageEntry] = field(default_factory=dict)
    _message_queue: List[AgentMessage] = field(default_factory=list)
    _message_history: List[AgentMessage] = field(default_factory=list)
    _agent_sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Core Storage Functions
    set(key: str, value: Any, ttl_seconds: Optional[int], metadata: Optional[Dict])
    get(key: str, default: Any) -> Any
    delete(key: str) -> bool
    exists(key: str) -> bool
    clear() -> None

    # Message Passing
    send_message(source_agent: str, target_agent: str, message_type: str,
                 payload: Dict, correlation_id: Optional[str]) -> str
    receive_messages(agent_id: str, message_type: Optional[str]) -> List[AgentMessage]
    get_message_history(agent_id: Optional[str], limit: int) -> List[AgentMessage]

    # Session Management
    start_session(agent_id: str, session_data: Optional[Dict])
    get_session(agent_id: str) -> Optional[Dict[str, Any]]
    update_session(agent_id: str, updates: Dict[str, Any])
    end_session(agent_id: str)

    # Maintenance & Diagnostics
    cleanup_expired() -> int
    get_stats() -> Dict[str, Any]
    to_dict() -> Dict[str, Any]
    from_dict(data: Dict[str, Any])
```

### Thermodynamic Agent (thermodynamic_agent.py)
```python
class ThermodynamicAgent:
    """Инкапсулированный термо-агент для извлечения параметров"""

    def __init__(self, config: ThermoAgentConfig):
        self.agent = Agent(model, deps_type=ThermoAgentConfig,
                          output_type=ExtractedParameters,
                          system_prompt=EXTRACT_INPUTS_PROMPT)
        self.storage.start_session(self.agent_id, {...})

    async def start(self):
        """Запуск в режиме прослушивания"""
        while self.running:
            messages = self.storage.receive_messages(
                self.agent_id, message_type="extract_parameters"
            )
            for message in messages:
                await self._process_message(message)
            await asyncio.sleep(self.config.poll_interval)

    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        user_query = message.payload.get("user_query")

        # Извлечение параметров через PydanticAI
        result = await self.agent.run(user_query, deps=self.config)
        extracted_params = result.output

        # Сохранение результата
        result_key = f"thermo_result_{message.id}"
        self.storage.set(result_key, extracted_params.model_dump(), ttl_seconds=600)

        # Ответ оркестратору
        self.storage.send_message(...)

        # Пересылка SQL агенту если нужен SQL
        if extracted_params.sql_query_hint:
            self.storage.send_message(target_agent="sql_agent", ...)
```

### SQL Generation Agent (sql_generation_agent.py)
```python
class SQLGenerationAgent:
    """Инкапсулированный SQL агент для генерации запросов"""

    def __init__(self, config: SQLAgentConfig):
        self.agent = Agent(model, deps_type=SQLAgentConfig,
                          output_type=SQLQueryResult,
                          system_prompt=SQL_GENERATION_PROMPT)
        self.storage.start_session(self.agent_id, {...})

    async def start(self):
        """Запуск в режиме прослушивания"""
        while self.running:
            messages = self.storage.receive_messages(
                self.agent_id, message_type="generate_query"
            )
            for message in messages:
                await self._process_message(message)
            await asyncio.sleep(self.config.poll_interval)

    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        sql_hint = message.payload.get("sql_hint")
        extracted_params = message.payload.get("extracted_params", {})

        # Генерация SQL через PydanticAI
        result = await self.agent.run(sql_hint, deps=self.config)
        sql_result = result.output

        # Очистка SQL запроса
        sql_result.sql_query = self._clean_sql_query(sql_result.sql_query)

        # Отправка в Database Agent для выполнения
        self.storage.send_message(target_agent="database_agent",
                                 message_type="execute_sql", ...)

        # Ожидание результатов от Database и Filtering агентов
        # Консолидация всех результатов
        # Отправка итогового ответа
```

### Database Agent (database_agent.py)
```python
class DatabaseAgent:
    """Агент для выполнения SQL запросов к термодинамической БД"""

    def __init__(self, config: DatabaseAgentConfig):
        self.storage.start_session(self.agent_id, {
            "capabilities": ["execute_sql", "filter_results", "query_database"],
            "database": config.db_path
        })

    async def _process_message(self, message):
        """Обработка запроса на выполнение SQL"""
        sql_query = message.payload.get("sql_query")
        extracted_params = message.payload.get("extracted_params", {})

        # Выполнение SQL запроса
        execution_result = await self._execute_query(sql_query, extracted_params)

        # Отправка результатов агенту фильтрации
        if execution_result.get("success") and execution_result.get("row_count", 0) > 0:
            self.storage.send_message(target_agent="results_filtering_agent",
                                     message_type="filter_results", ...)

        # Ответ SQL агенту
        self.storage.send_message(target_agent=message.source_agent,
                                 message_type="sql_executed", ...)

    async def _execute_query(self, sql_query: str, extracted_params: Dict) -> Dict:
        """Выполнение SQL с температурной фильтрацией"""
        conn = sqlite3.connect(self.config.db_path)
        cursor = conn.cursor()
        cursor.execute(self._clean_sql_query(sql_query))
        rows = cursor.fetchall()
        conn.close()

        # Применение температурной фильтрации
        if extracted_params.get("temperature_range_k"):
            rows = self._filter_by_temperature_range(rows, columns, temp_range)

        return {"success": True, "columns": columns, "rows": rows, ...}
```

### Results Filtering Agent (results_filtering_agent.py)
```python
class ResultsFilteringAgent:
    """Агент для интеллектуальной фильтрации результатов"""

    def __init__(self, config: ResultsFilteringAgentConfig):
        self.agent = Agent(model, deps_type=ResultsFilteringAgentConfig,
                          output_type=FilteredResult,
                          system_prompt=RESULT_FILTER_ENGLISH_PROMPT)
        self.storage.start_session(self.agent_id, {
            "capabilities": ["filter_results", "temperature_analysis", "compound_selection"]
        })

    async def _process_message(self, message):
        """Обработка запроса на фильтрацию результатов"""
        execution_result = message.payload.get("execution_result", {})
        extracted_params = message.payload.get("extracted_params", {})

        # Предварительная температурная фильтрация
        temp_filtered_records = self._filter_by_temperature_range(
            rows, columns, temperature_range
        )

        # LLM-анализ для выбора наиболее релевантных записей
        if temp_filtered_records:
            filtered_result = await self._llm_filter_records(
                temp_filtered_records, columns, compounds, phases, temperature_range
            )

            # Конвертация ID в полные записи
            selected_records = self._convert_ids_to_records(
                filtered_result.selected_entries, temp_filtered_records
            )

            # Отправка результатов SQL агенту
            self.storage.send_message(target_agent="sql_agent",
                                     message_type="results_filtered", ...)
```

### Orchestrator (orchestrator.py)
```python
class ThermoOrchestrator:
    """Координатор агентов"""

    def __init__(self, config: OrchestratorConfig):
        self.agent = Agent(model, deps_type=OrchestratorConfig,
                          output_type=OrchestratorResponse)
        # Инструменты для управления агентами через хранилище

    async def process_request(self, request: OrchestratorRequest) -> OrchestratorResponse:
        """Координация обработки запроса через A2A"""
        # Отправка сообщения thermo_agent
        thermo_message_id = self.storage.send_message(
            source_agent=self.agent_id, target_agent="thermo_agent",
            message_type="extract_parameters", payload={"user_query": request.user_query}
        )

        # Ожидание ответа от thermo_agent
        while not timeout:
            messages = self.storage.receive_messages(
                self.agent_id, message_type="response"
            )
            for msg in messages:
                if msg.correlation_id == thermo_message_id:
                    extracted_params = msg.payload.get("extracted_params")
                    break

        # Ожидание результата SQL цепочки (sql_agent -> database_agent -> filtering_agent)
        while not timeout:
            messages = self.storage.receive_messages(
                self.agent_id, message_type="sql_ready"
            )
            for msg in messages:
                if msg.correlation_id == thermo_message_id:
                    result_key = msg.payload.get("result_key")
                    sql_result = self.storage.get(result_key)
                    break

        # Сбор и возврат полного результата
        return OrchestratorResponse(
            success=True,
            result={
                "extracted_parameters": extracted_params,
                "sql_query": sql_result.get("sql_query"),
                "execution_result": sql_result.get("execution_result"),
                "filtered_result": sql_result.get("filtered_result")
            }
        )
```

### ThermoSystem (main.py)
```python
class ThermoSystem:
    """Главная система управления агентами"""

    def __init__(self):
        self.storage = get_storage()
        self.session_logger = create_session_logger()
        self.config = self.load_config()

    def initialize_agents(self):
        """Инициализация всех агентов системы"""
        self.thermo_agent = ThermodynamicAgent(thermo_config)
        self.sql_agent = SQLGenerationAgent(sql_config)
        self.database_agent = DatabaseAgent(database_config)
        self.results_filtering_agent = ResultsFilteringAgent(filtering_config)
        self.orchestrator = ThermoOrchestrator(orchestrator_config)

    async def start_agents(self):
        """Запуск всех агентов в отдельных задачах"""
        self.agent_tasks = [
            asyncio.create_task(self.thermo_agent.start()),
            asyncio.create_task(self.sql_agent.start()),
            asyncio.create_task(self.database_agent.start()),
            asyncio.create_task(self.results_filtering_agent.start()),
        ]

    async def process_user_query(self, query: str):
        """Обработка запроса пользователя через оркестратор"""
        request = OrchestratorRequest(user_query=query, request_type="thermodynamic")
        response = await self.orchestrator.process_request(request)
        # Форматирование и вывод результатов
```

## Модели данных

### AgentMessage
```python
class AgentMessage(BaseModel):
    """Сообщение между агентами"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source_agent: str  # Идентификатор агента-отправителя
    target_agent: str  # Идентификатор агента-получателя
    message_type: str  # Тип сообщения (extract_parameters, generate_query, execute_sql, etc.)
    payload: Dict[str, Any]  # Данные сообщения
    correlation_id: Optional[str] = None  # ID связанного сообщения
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### StorageEntry
```python
class StorageEntry(BaseModel):
    """Запись в хранилище"""
    key: str  # Ключ для доступа к данным
    value: Any  # Сохраненные данные
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    ttl_seconds: Optional[int] = None  # Time to live в секундах
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### ExtractedParameters
```python
class ExtractedParameters(BaseModel):
    """Извлеченные параметры из запроса пользователя"""
    intent: str  # "lookup", "calculation", "reaction", "comparison"
    compounds: List[str]  # Химические формулы (включая все реагенты и продукты)
    temperature_k: float  # Температура в Кельвинах
    temperature_range_k: List[float]  # Диапазон температур [min, max]
    phases: List[str]  # Фазовые состояния ["s", "l", "g", "aq"]
    properties: List[str]  # Требуемые свойства ["basic", "all", "thermal"]
    sql_query_hint: str  # Подсказка для генерации SQL
    reaction_equation: Optional[str] = None  # Уравнение реакции (для intent="reaction")
```

### SQLQueryResult
```python
class SQLQueryResult(BaseModel):
    """Результат генерации SQL запроса"""
    sql_query: str  # Сгенерированный SQL запрос
    explanation: str  # Краткое объяснение запроса
    expected_columns: list[str]  # Ожидаемые колонки в результате
```

### FilteredResult
```python
class FilteredResult(BaseModel):
    """Результат фильтрации записей"""
    selected_entries: List[SelectedEntry]  # Выбранные записи с ID
    phase_determinations: Dict[str, Dict[str, Any]]  # Анализ фаз
    missing_compounds: List[str]  # Отсутствующие соединения
    excluded_entries_count: int  # Количество исключенных записей
    overall_confidence: float  # Общая уверенность
    warnings: List[str]  # Предупреждения
    filter_summary: str  # Резюме фильтрации

class SelectedEntry(BaseModel):
    """Выбранная запись с обоснованием"""
    compound: str
    selected_id: int
    reasoning: str
```

### OrchestratorRequest/Response
```python
class OrchestratorRequest(BaseModel):
    """Запрос к оркестратору"""
    user_query: str  # Исходный запрос пользователя
    request_type: str = "thermodynamic"  # Тип запроса
    options: Dict[str, Any] = Field(default_factory=dict)  # Дополнительные опции

class OrchestratorResponse(BaseModel):
    """Ответ от оркестратора"""
    success: bool  # Успешность обработки
    result: Dict[str, Any]  # Результаты обработки
    errors: list[str] = Field(default_factory=list)  # Список ошибок
    trace: list[str] = Field(default_factory=list)  # Трассировка выполнения
```

## Паттерны взаимодействия

### 1. Request-Response Pattern
```python
# Agent A отправляет запрос
message_id = storage.send_message(
    source="agent_a",
    target="agent_b",
    type="request",
    payload=data
)

# Agent B получает и обрабатывает
messages = storage.receive_messages("agent_b", type="request")
# ... processing ...

# Agent B отправляет ответ
storage.send_message(
    source="agent_b",
    target="agent_a",
    type="response",
    correlation_id=message_id,
    payload=result
)
```

### 2. Pipeline Pattern
```python
# Последовательная обработка через цепочку агентов
User → Orchestrator → Thermo Agent → SQL Agent → Orchestrator → User
```

### 3. Publish-Subscribe Pattern
```python
# Агент публикует результат для всех заинтересованных
storage.set("global_result_key", result, ttl_seconds=300)
# Любой агент может подписаться на изменения
```

## Конфигурация и развертывание

### Структура проекта v2.0 (Актуальная)
```
├── src/thermo_agents/
│   ├── __init__.py
│   ├── agent_storage.py           # Централизованное хранилище A2A коммуникации
│   ├── thermodynamic_agent.py     # Агент извлечения параметров (PydanticAI)
│   ├── sql_generation_agent.py    # Агент генерации SQL запросов (PydanticAI)
│   ├── database_agent.py          # Агент выполнения SQL и температурной фильтрации
│   ├── results_filtering_agent.py # Агент интеллектуальной фильтрации (LLM)
│   ├── orchestrator.py            # Координатор агентов
│   ├── prompts.py                 # Системные промпты для всех агентов
│   └── thermo_agents_logger.py    # Система сессионного логирования
├── data/
│   └── thermo_data.db             # SQLite база: 316,434 записей, 32,790 соединений
├── logs/sessions/                 # Логи сессий с детальной трассировкой
├── main.py                        # Точка входа с ThermoSystem
├── pyproject.toml                 # Конфигурация uv с PydanticAI 1.0.8
├── .env                           # Переменные окружения (OPENROUTER_API_KEY, etc.)
└── CLAUDE.md                      # Инструкции для Claude Code
```

### База данных (data/thermo_data.db)
```sql
-- Схема таблицы compounds
CREATE TABLE "compounds" (
  "Formula" TEXT,           -- Химическая формула
  "Structure" TEXT,         -- Структурная формула
  "FirstName" TEXT,         -- Основное название
  "SecondName" TEXT,        -- Альтернативное название
  "Phase" TEXT,             -- Фаза: s/l/g/aq
  "CAS" TEXT,               -- CAS номер
  "MeltingPoint" REAL,      -- Температура плавления
  "BoilingPoint" REAL,      -- Температура кипения
  "Density" REAL,           -- Плотность
  "Solubility" REAL,        -- Растворимость
  "Color" INTEGER,          -- Цвет
  "H298" REAL,              -- Энтальпия образования при 298K (кДж/моль)
  "S298" REAL,              -- Энтропия при 298K (Дж/(моль*К))
  "Tmin" REAL,              -- Минимальная температура действия данных
  "Tmax" REAL,              -- Максимальная температура действия данных
  "f1" REAL,                -- Коэффициент теплоемкости f1
  "f2" REAL,                -- Коэффициент теплоемкости f2
  "f3" REAL,                -- Коэффициент теплоемкости f3
  "f4" REAL,                -- Коэффициент теплоемкости f4
  "f5" REAL,                -- Коэффициент теплоемкости f5
  "f6" REAL,                -- Коэффициент теплоемкости f6
  "ReliabilityClass" INTEGER, -- Класс надежности данных
  "Reference" TEXT          -- Источник данных
);

-- Статистика: 316,434 записей, 32,790 уникальных соединений
```

### Запуск системы (main.py)
```python
class ThermoSystem:
    """Главная система управления агентами"""

    def __init__(self):
        self.storage = get_storage()  # Singleton хранилище
        self.session_logger = create_session_logger()
        self.config = self.load_config()  # Из .env файла

    def initialize_agents(self):
        """Инициализация всех 5 агентов системы"""
        self.thermo_agent = ThermodynamicAgent(thermo_config)
        self.sql_agent = SQLGenerationAgent(sql_config)
        self.database_agent = DatabaseAgent(database_config)
        self.results_filtering_agent = ResultsFilteringAgent(filtering_config)
        self.orchestrator = ThermoOrchestrator(orchestrator_config)

    async def start_agents(self):
        """Запуск агентов в отдельных асинхронных задачах"""
        self.agent_tasks = [
            asyncio.create_task(self.thermo_agent.start(), name="thermo_agent_task"),
            asyncio.create_task(self.sql_agent.start(), name="sql_agent_task"),
            asyncio.create_task(self.database_agent.start(), name="database_agent_task"),
            asyncio.create_task(self.results_filtering_agent.start(), name="filtering_agent_task"),
        ]
        await asyncio.sleep(1)  # Время на инициализацию

    async def process_user_query(self, query: str):
        """Обработка запроса пользователя через оркестратор"""
        request = OrchestratorRequest(user_query=query, request_type="thermodynamic")
        response = await self.orchestrator.process_request(request)

        # Форматированный вывод результатов
        if response.success:
            result = response.result
            print_extracted_parameters(result.get("extracted_parameters"))
            print_sql_query(result.get("sql_query"), result.get("explanation"))
            print_execution_results(result.get("execution_result"))
            print_filtered_results(result.get("filtered_result"))

    async def interactive_mode(self):
        """CLI интерфейс для взаимодействия с системой"""
        while True:
            user_input = input("Query> ").strip()
            if user_input.lower() in ["exit", "quit"]:
                break
            elif user_input.lower() == "status":
                self.print_system_status()
            elif user_input.lower() == "clear":
                self.storage.clear()
            else:
                await self.process_user_query(user_input)

async def main():
    """Точка входа в приложение"""
    system = ThermoSystem()
    await system.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### Переменные окружения (.env)
```bash
# LLM Configuration
OPENROUTER_API_KEY=your_api_key_here
LLM_BASE_URL=https://openrouter.ai/api/v1/chat/completions
LLM_DEFAULT_MODEL=openai:gpt-4o

# Database Configuration
DB_PATH=data/thermo_data.db

# Logging Configuration
LOG_LEVEL=INFO
DEBUG=false
```

### Команды для запуска
```bash
# Установка зависимостей
uv sync

# Активация виртуального окружения
uv shell

# Запуск главного приложения (полная система агентов)
uv run python main.py

# Запуск отдельных агентов для тестирования
uv run python src/thermo_agents/thermodynamic_agent.py
uv run python src/thermo_agents/sql_generation_agent.py

# Работа с Jupyter notebook
uv run python -m ipykernel
# Затем выбрать ядро .venv (Python 3.12) в VS Code
```

## Преимущества реализованной архитектуры

### 1. Полная инкапсуляция агентов
- **5 независимых агентов**: ThermodynamicAgent, SQLGenerationAgent, DatabaseAgent, ResultsFilteringAgent, ThermoOrchestrator
- **Никаких прямых вызовов**: Только communication через AgentStorage
- **Message-driven architecture**: 8 типов сообщений (extract_parameters, generate_query, execute_sql, filter_results, etc.)
- **Correlation IDs**: Полная трассировка сообщений через всю цепочку

### 2. Интеллектуальная обработка данных
- **PydanticAI агенты**: Структурированные выходы для Thermo, SQL и Filtering агентов
- **Двухуровневая фильтрация**: Температурная предфильтрация + LLM-анализ для выбора релевантных записей
- **Объяснения и рассуждения**: Каждый этап предоставляет обоснование своих решений
- **Fallback механизмы**: Graceful degradation при сбоях LLM

### 3. Масштабируемость и производительность
- **Асинхронная архитектура**: Все агенты работают параллельно в собственных event loops
- **Configurable timeouts**: 60s для SQL генерации, 30s для DB запросов, 90s для фильтрации
- **Memory-efficient storage**: TTL для автоматической очистки, batch обработка сообщений
- **SQL оптимизация**: Cleaning HTML entities, single statement execution, temperature range filtering

### 4. Comprehensive Logging & Observability
- **Session-based logging**: Каждая сессия получает уникальный файл с полной трассировкой
- **Multi-level tracing**: Agent events, SQL queries, message passing, filtering decisions
- **Structured data tables**: Formatted logging для SQL results и filtered data
- **Error tracking**: Детальная информация об ошибках с context

### 5. Robust Error Handling
- **Agent isolation**: Сбой одного агента не влияет на других
- **Timeout management**: Automatic timeout handling для долгих операций
- **Graceful degradation**: Fallback filtering когда LLM недоступен
- **Message persistence**: Сообщения не теряются при перезапуске

### 6. Rich Data Processing Pipeline
```
User Query → Parameter Extraction → SQL Generation → Database Execution → Results Filtering → User Response
     ↓              ↓                    ↓                ↓                    ↓              ↓
 Intent, Temp    Compounds,          Clean SQL        316K records       LLM Selection   Formatted
 Compounds,      Temperature,        Query with      → Temp Filter    → Most Relevant   Output with
 Phases         Range, Phases       Explanation     → 100-1000 recs   → 5-20 records   Reasoning
```

## Production Features

### 1. Database Integration
- **Large-scale database**: 316,434 records, 32,790 unique compounds
- **Optimized queries**: Temperature range overlap detection, phase-specific filtering
- **Connection management**: Proper SQLite connection handling with cleanup
- **Schema awareness**: Full understanding of 23 columns including thermodynamic properties

### 2. Configuration Management
- **Environment-based config**: .env file support for all API keys and settings
- **Agent-specific configs**: Individual configuration classes for each agent
- **Dependency injection**: Clean separation of configuration from implementation
- **Runtime reconfiguration**: Ability to update settings without restart

### 3. CLI and User Experience
- **Interactive mode**: Full CLI interface with commands (status, clear, exit)
- **Formatted output**: Structured presentation of results with tables and reasoning
- **Progress tracking**: Real-time updates on query processing steps
- **Error messaging**: Clear user-friendly error messages

### 4. Development and Testing
- **Standalone agent execution**: Each agent can run independently for testing
- **Factory functions**: Clean agent creation patterns
- **Process single query**: Legacy compatibility methods for testing
- **Mock-friendly storage**: Easy to mock AgentStorage for unit tests

## Технические особенности

### Message Types и Flow
```python
# 8 основных типов сообщений:
"extract_parameters"  # Orchestrator → Thermo Agent
"response"           # Thermo Agent → Orchestrator
"generate_query"     # Thermo Agent → SQL Agent
"execute_sql"        # SQL Agent → Database Agent
"sql_executed"       # Database Agent → SQL Agent
"filter_results"     # Database Agent → Filtering Agent
"results_filtered"   # Filtering Agent → SQL Agent
"sql_ready"          # SQL Agent → Orchestrator
```

### Storage Architecture
- **4 основных компонента**: _storage (key-value), _message_queue, _message_history, _agent_sessions
- **TTL support**: Automatic cleanup of expired data
- **Correlation tracking**: Full message genealogy through correlation_id
- **Session management**: Agent state persistence across restarts

### Data Models
- **7 основных моделей**: AgentMessage, StorageEntry, ExtractedParameters, SQLQueryResult, FilteredResult, OrchestratorRequest/Response
- **Type safety**: Полная типизация через Pydantic models
- **Validation**: Automatic validation всех входящих и исходящих данных

## Future Extensions

### Planned Enhancements
1. **Web API**: REST endpoints for remote access
2. **Real-time WebSocket**: Live query progress updates
3. **Caching layer**: Redis integration for frequently accessed data
4. **Metrics collection**: Prometheus/Grafana monitoring
5. **Distributed deployment**: Multi-node agent distribution

### Architecture Flexibility
- **Storage backends**: Easy migration to Redis, PostgreSQL, or cloud storage
- **Agent scaling**: Horizontal scaling of individual agent types
- **Protocol extension**: Support for additional message types and workflows
- **Integration points**: Clean APIs for external system integration

## Заключение

Реализованная архитектура представляет собой production-ready систему с:

✅ **Полной инкапсуляцией агентов** через message passing
✅ **Интеллектуальной обработкой данных** с LLM filtering
✅ **Comprehensive logging и observability**
✅ **Robust error handling и recovery**
✅ **Высокой производительностью** через async architecture
✅ **Flexibility для будущих расширений**

Система успешно обрабатывает сложные термодинамические запросы, предоставляя пользователям точные, релевантные данные с полным обоснованием выбора и детальной трассировкой процесса принятия решений.