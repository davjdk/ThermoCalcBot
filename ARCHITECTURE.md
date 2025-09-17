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
┌──────────────────────────────────────────────────────────────────────────┐
│                           AGENT STORAGE                                   │
│                        (Централизованное хранилище)                      │
│ ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌───────────────────┐ │
│ │   Storage   │ │ Message Queue│ │   Sessions   │ │   Message History │ │
│ │ Key-Value   │ │   Messages   │ │ Agent States │ │    Audit Trail    │ │
│ └─────────────┘ └──────────────┘ └──────────────┘ └───────────────────┘ │
└────────────┬─────────────────┬─────────────────┬────────────────────────┘
             │                 │                 │
             │    Messages     │    Messages     │    Messages
             │                 │                 │
    ┌────────▼────────┐ ┌─────▼──────┐ ┌───────▼────────┐
    │                 │ │            │ │                │
    │  ORCHESTRATOR   │ │  THERMO    │ │  SQL AGENT     │
    │     AGENT       │ │   AGENT    │ │                │
    │                 │ │            │ │                │
    │ ┌─────────────┐ │ │ ┌────────┐ │ │ ┌────────────┐ │
    │ │  Routing    │ │ │ │Extract │ │ │ │  Generate  │ │
    │ │  Logic      │ │ │ │ Params │ │ │ │    SQL     │ │
    │ ├─────────────┤ │ │ ├────────┤ │ │ ├────────────┤ │
    │ │ Coordination│ │ │ │Convert │ │ │ │  Execute   │ │
    │ │  Control    │ │ │ │ Units  │ │ │ │   Query    │ │
    │ ├─────────────┤ │ │ ├────────┤ │ │ ├────────────┤ │
    │ │   Error     │ │ │ │Validate│ │ │ │  Explain   │ │
    │ │  Handling   │ │ │ │ Input  │ │ │ │   Query    │ │
    │ └─────────────┘ │ │ └────────┘ │ │ └────────────┘ │
    └─────────────────┘ └────────────┘ └────────────────┘
             ▲                               │
             │                               │
    ┌────────┴────────┐                      ▼
    │   CLI/API       │              ┌──────────────┐
    │   Interface     │              │   SQLite DB  │
    └─────────────────┘              └──────────────┘
```

## Поток коммуникации между агентами

### Message Flow через Storage
```
User Request
    │
    ▼
Orchestrator
    │
    ├─► Storage.send_message(
    │     source: "orchestrator",
    │     target: "thermo_agent",
    │     type: "extract_parameters",
    │     payload: {...}
    │   )
    │
    ▼
Thermo Agent (listening)
    │
    ├─► Storage.receive_messages("thermo_agent")
    ├─► Process message
    ├─► Extract parameters
    │
    ├─► Storage.set("result_key", extracted_params)
    │
    ├─► Storage.send_message(
    │     source: "thermo_agent",
    │     target: "sql_agent",
    │     type: "generate_query",
    │     payload: {...}
    │   )
    │
    ▼
SQL Agent (listening)
    │
    ├─► Storage.receive_messages("sql_agent")
    ├─► Process message
    ├─► Generate SQL
    │
    ├─► Storage.set("sql_result_key", sql_query)
    │
    └─► Storage.send_message(
          source: "sql_agent",
          target: "orchestrator",
          type: "response",
          payload: {...}
        )
```

## Детальная архитектура компонентов

### Agent Storage (agent_storage.py)
```python
@dataclass
class AgentStorage:
    """Централизованное хранилище для A2A коммуникации"""
    
    # Core Storage Functions
    set(key: str, value: Any, ttl_seconds: Optional[int])
    get(key: str, default: Any) -> Any
    delete(key: str) -> bool
    exists(key: str) -> bool
    
    # Message Passing
    send_message(source: str, target: str, type: str, payload: Dict)
    receive_messages(agent_id: str, type: Optional[str]) -> List[Message]
    
    # Session Management
    start_session(agent_id: str, data: Dict)
    get_session(agent_id: str) -> Dict
    update_session(agent_id: str, updates: Dict)
    end_session(agent_id: str)
    
    # Maintenance
    cleanup_expired() -> int
    get_stats() -> Dict
```

### Thermodynamic Agent (thermodynamic_agent.py)
```python
class ThermodynamicAgent:
    """Полностью инкапсулированный термо-агент"""
    
    def __init__(self, config: ThermoAgentConfig):
        # Инициализация PydanticAI агента
        # Регистрация в хранилище
        # Запуск event loop
    
    async def start(self):
        """Запуск в режиме прослушивания"""
        while self.running:
            messages = storage.receive_messages(self.agent_id)
            for message in messages:
                await self._process_message(message)
            await asyncio.sleep(poll_interval)
    
    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        # Извлечение параметров
        # Сохранение в хранилище
        # Отправка ответа через хранилище
```

### SQL Generation Agent (sql_generation_agent.py)
```python
class SQLGenerationAgent:
    """Полностью инкапсулированный SQL агент"""
    
    def __init__(self, config: SQLAgentConfig):
        # Инициализация PydanticAI агента
        # Регистрация в хранилище
        # Подключение к БД
    
    async def start(self):
        """Запуск в режиме прослушивания"""
        while self.running:
            messages = storage.receive_messages(self.agent_id)
            for message in messages:
                await self._process_message(message)
            await asyncio.sleep(poll_interval)
    
    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        # Генерация SQL
        # Опциональное выполнение
        # Сохранение результата
        # Отправка ответа
```

### Orchestrator (orchestrator.py)
```python
class ThermoOrchestrator:
    """Координатор агентов"""
    
    async def process_request(self, request: OrchestratorRequest):
        """Координация обработки запроса"""
        # Отправка сообщения thermo_agent
        # Ожидание ответа через хранилище
        # Отправка сообщения sql_agent
        # Сбор результатов
        # Возврат полного ответа
```

## Модели данных

### AgentMessage
```python
class AgentMessage(BaseModel):
    id: str
    timestamp: datetime
    source_agent: str
    target_agent: str
    message_type: str
    payload: Dict[str, Any]
    correlation_id: Optional[str]
    metadata: Dict[str, Any]
```

### StorageEntry
```python
class StorageEntry(BaseModel):
    key: str
    value: Any
    created_at: datetime
    updated_at: datetime
    ttl_seconds: Optional[int]
    metadata: Dict[str, Any]
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

### Структура проекта v2.0
```
├── src/thermo_agents/
│   ├── __init__.py
│   ├── agent_storage.py        # Централизованное хранилище
│   ├── thermodynamic_agent.py  # Инкапсулированный термо-агент
│   ├── sql_generation_agent.py # Инкапсулированный SQL агент
│   ├── orchestrator.py         # Координатор агентов
│   ├── prompts.py              # Системные промпты
│   └── thermo_agents_logger.py # Система логирования
├── data/
│   └── thermo_data.db          # База термодинамических данных
├── logs/sessions/              # Логи сессий
├── main_v2.py                  # Точка входа с новой архитектурой
├── pyproject.toml              # Конфигурация uv
└── .env                        # Переменные окружения
```

### Запуск системы
```python
# main_v2.py
async def main():
    # Инициализация хранилища
    storage = AgentStorage()
    
    # Создание и запуск агентов
    thermo_agent = create_thermo_agent(config, storage)
    sql_agent = create_sql_agent(config, storage)
    orchestrator = ThermoOrchestrator(config, storage)
    
    # Запуск агентов в отдельных задачах
    tasks = [
        asyncio.create_task(thermo_agent.start()),
        asyncio.create_task(sql_agent.start()),
    ]
    
    # Обработка запросов через оркестратор
    while True:
        user_query = input("Query: ")
        response = await orchestrator.process_request(user_query)
        print(response)
```

## Преимущества новой архитектуры

### 1. Полная инкапсуляция
- Агенты не знают о существовании друг друга
- Нет прямых зависимостей между агентами
- Легко добавлять/удалять агентов

### 2. Масштабируемость
- Агенты могут работать на разных машинах
- Storage может быть заменен на Redis/RabbitMQ
- Горизонтальное масштабирование агентов

### 3. Отказоустойчивость
- Падение одного агента не влияет на других
- Сообщения сохраняются в хранилище
- Возможность replay сообщений

### 4. Наблюдаемость
- Все взаимодействия логируются
- Message history для отладки
- Метрики по каждому агенту

### 5. Тестируемость
- Агенты тестируются изолированно
- Mock хранилище для юнит-тестов
- Replay реальных сценариев

## Миграция с v1.0 на v2.0

### Изменения в коде
1. **Замена прямых вызовов**: 
   - Было: `result = await process_thermodynamic_query(query)`
   - Стало: Message passing через storage

2. **Новые агенты**:
   - `thermodynamic_agent.py` вместо `main_thermo_agent.py`
   - `sql_generation_agent.py` вместо `sql_agent.py`
   - Добавлен `orchestrator.py`

3. **Хранилище**:
   - Новый компонент `agent_storage.py`
   - Все состояние в централизованном хранилище

### Обратная совместимость
- Старые функции сохранены для legacy кода
- Можно использовать `process_single_query()` для тестов
- Постепенная миграция через адаптеры

## Безопасность

### Изоляция агентов
- Агенты не имеют прямого доступа друг к другу
- Валидация всех сообщений
- Ограничение прав доступа к хранилищу

### Аудит
- Все сообщения логируются
- История взаимодействий сохраняется
- Возможность анализа инцидентов

## Расширение системы

### Добавление нового агента
1. Создать класс агента с базовым интерфейсом
2. Реализовать `start()` и `_process_message()`
3. Зарегистрировать в оркестраторе
4. Обновить маршрутизацию сообщений

### Интеграция с внешними системами
- REST API endpoint для оркестратора
- WebSocket для real-time обновлений
- Интеграция с Kafka/RabbitMQ для масштабирования

## Метрики и мониторинг

### Ключевые метрики
- **Message throughput**: Сообщений/сек
- **Processing latency**: Время обработки сообщения
- **Queue size**: Размер очереди сообщений
- **Agent availability**: Доступность агентов
- **Error rate**: Процент ошибок

### Инструменты мониторинга
- Prometheus для сбора метрик
- Grafana для визуализации
- ELK stack для анализа логов

## Заключение

Новая архитектура v2.0 полностью реализует принципы A2A коммуникации из PydanticAI, обеспечивая:
- Полную инкапсуляцию агентов
- Storage-based communication
- Масштабируемость и отказоустойчивость
- Простоту расширения и тестирования

Система готова к production использованию и может быть легко масштабирована для обработки больших объемов запросов.