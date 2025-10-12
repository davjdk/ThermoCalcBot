# Техническое задание на рефакторинг проекта Thermo Agents

**Версия:** 1.0  
**Дата:** 12 октября 2025  
**Ветка:** `refactoring/code-optimization`  
**Цель:** Сокращение кода при сохранении функциональности и улучшение поддерживаемости

---

## 1. Общие положения

### 1.1 Контекст проекта
- Система термодинамических AI-агентов на базе PydanticAI v1.0.8
- Архитектура: Agent-to-Agent (A2A) с обменом через централизованное хранилище
- Текущий объем: ~87MB кода, 15 модулей Python
- Основные агенты: Orchestrator, Thermodynamic, SQL Generation, Database, Individual Search

### 1.2 Принципы рефакторинга
- **Сохранение функциональности**: Все агенты остаются функциональными
- **Предсказуемость**: Код должен быть понятным и предсказуемым
- **Поддерживаемость**: Упрощение без потери гибкости
- **Документация PydanticAI**: Опора на официальные best practices
- **Обратная совместимость**: НЕ требуется

---

## 2. Основные направления рефакторинга

### 2.1 ⚠️ ОТКАЗ от базового класса агента
**Проблема:** Дублирование кода инициализации, обработки сообщений и управления жизненным циклом в каждом агенте.

**Анализ документации PydanticAI:**
- **PydanticAI НЕ использует наследование для агентов**
- Агенты — это stateless контейнеры, создаваемые через `Agent()` конструктор
- Философия: **композиция вместо наследования**
- Агенты предназначены для переиспользования как module globals (как FastAPI apps)

**ИСПРАВЛЕННОЕ РЕШЕНИЕ:**
- **НЕ создавать BaseAgent класс** — это противоречит философии PydanticAI
- Использовать стандартный `Agent` класс из PydanticAI для LLM-агентов
- Вынести общую логику координации в **helper-функции** и **утилиты**:
  - `start_agent_listener()` — общая функция запуска цикла прослушивания
  - `register_agent_in_storage()` — регистрация агента
  - `create_agent_config()` — фабрика конфигураций
- Использовать **dependency injection** через `deps_type` для передачи зависимостей

**Ожидаемый эффект:** Сокращение ~100-150 строк через утилиты, сохранение философии PydanticAI

---

### 2.2 Унификация конфигурации
**Проблема:** Множественные dataclass-конфигурации с повторяющимися полями.

**Решение:**
- Создать базовую `BaseAgentConfig` с общими полями:
  - `agent_id`, `storage`, `logger`, `session_logger`
  - `poll_interval`, `max_retries`, `timeout_seconds`
- Специфичные конфигурации наследуются и добавляют свои поля
- Централизовать настройки системы в `SystemConfig`

**Ожидаемый эффект:** Сокращение ~50-80 строк повторяющихся определений

---

### 2.3 Использование встроенной валидации Pydantic
**Проблема:** Модуль `message_validator.py` (~441 строка) дублирует функциональность Pydantic.

**Решение:**
- Определить строгие Pydantic-модели для всех типов сообщений
- Использовать встроенную валидацию через `Field()`, validators
- Удалить `MessageValidator` класс
- Обработка ошибок валидации через `ValidationError`

**Ожидаемый эффект:** Удаление ~400 строк избыточного кода, упрощение pipeline

---

### 2.4 ✅ Замена TimeoutManager на встроенный механизм PydanticAI
**Проблема:** Избыточная сложность (~600 строк) с adaptive timeouts, circuit breaker.

**Анализ документации PydanticAI:**
- **PydanticAI имеет встроенный retry механизм!**
- Поддержка `retries` параметра на уровне агента, инструментов и outputs
- Встроенная интеграция с библиотекой **tenacity** через `pydantic-ai[retries]`
- HTTP retry transports: `AsyncTenacityTransport` и `TenacityTransport`
- Поддержка `ModelRetry` exception для ручного управления повторами
- `UsageLimits` для контроля лимитов (токены, запросы, вызовы инструментов)

**ИСПРАВЛЕННОЕ РЕШЕНИЕ:**
- **УДАЛИТЬ** custom `TimeoutManager` (~600 строк)
- Использовать встроенный `retries` параметр PydanticAI:
  ```python
  agent = Agent('model', retries=2)  # На уровне агента
  @agent.tool(retries=3)  # На уровне инструмента
  ```
- Использовать `asyncio.wait_for()` для простых таймаутов
- Использовать `UsageLimits` для контроля:
  ```python
  agent.run(prompt, usage_limits=UsageLimits(
      request_limit=5,
      total_tokens_limit=500
  ))
  ```
- Для HTTP retry использовать `pydantic_ai.retries.AsyncTenacityTransport`

**Ожидаемый эффект:** Удаление ~600 строк custom кода, использование проверенного решения

---

### 2.5 Оптимизация GracefulDegradation
**Проблема:** Сложная система отслеживания состояния компонентов (~492 строки).

**Решение:**
- Оценить реальное использование механизма degradation
- Упростить или удалить неиспользуемый функционал
- Интегрировать с базовой обработкой ошибок агентов

**Ожидаемый эффект:** Потенциальное сокращение ~200-300 строк

---

### 2.6 Рефакторинг AgentStorage
**Проблема:** Избыточная функциональность в хранилище (~648 строк).

**Решение:**
- Выделить core функциональность (сообщения, данные, сессии)
- Удалить неиспользуемые методы
- Упростить API для частых операций
- Документировать публичный интерфейс

**Ожидаемый эффект:** Сокращение ~100-150 строк, улучшение читаемости

---

### 2.7 Оптимизация операций логирования
**Проблема:** Модуль `operations.py` (~452 строки) с избыточным структурированием.

**Решение:**
- Сохранить текущий уровень логирования (требование заказчика)
- Упростить структуры данных операций
- Убрать избыточные метаданные
- Оптимизировать создание контекста операций

**Ожидаемый эффект:** Сокращение ~50-100 строк при сохранении функциональности

---

### 2.8 Консолидация промптов
**Проблема:** Файл `prompts.py` содержит ~891 строку промптов и вспомогательного кода.

**Решение:**
- **НЕ ИЗМЕНЯТЬ** содержание промптов (требование заказчика)
- Возможная оптимизация вспомогательных функций
- Улучшение структуры и документации

**Ожидаемый эффект:** Минимальное сокращение, фокус на организацию

---

### 2.9 ✅ НОВОЕ: Использование встроенных возможностей PydanticAI

#### 2.9.1 Agent Delegation Pattern
**Преимущество:** Встроенная поддержка делегирования между агентами.

**Применение в проекте:**
- Orchestrator → Thermodynamic Agent
- Orchestrator → SQL Agent → Database Agent
- Individual Search Agent как delegate

**Реализация:**
```python
@orchestrator.tool
async def delegate_to_thermo(ctx: RunContext, query: str):
    result = await thermo_agent.run(
        query,
        deps=ctx.deps,  # Передача зависимостей
        usage=ctx.usage  # Передача usage для подсчета
    )
    return result.output
```

**Эффект:** Упрощение координации агентов, автоматический подсчет usage

---

#### 2.9.2 Dependency Injection
**Преимущество:** Встроенная система DI через `deps_type` и `RunContext`.

**Применение в проекте:**
```python
from dataclasses import dataclass

@dataclass
class SystemDeps:
    storage: AgentStorage
    db_path: str
    logger: logging.Logger

agent = Agent('model', deps_type=SystemDeps)

@agent.tool
async def my_tool(ctx: RunContext[SystemDeps]) -> str:
    # Полный type-safe доступ к зависимостям
    ctx.deps.storage.set("key", "value")
    return "done"
```

**Эффект:** Удаление custom DI логики, type-safe код

---

#### 2.9.3 ModelSettings для конфигурации
**Преимущество:** Встроенная централизованная конфигурация моделей.

**Применение в проекте:**
```python
from pydantic_ai import Agent, ModelSettings

# Общие настройки для всех агентов
default_settings = ModelSettings(
    temperature=0.0,
    max_tokens=2000,
    timeout=60.0
)

agent = Agent(
    'openai:gpt-4o',
    model_settings=default_settings
)

# Runtime override при необходимости
result = await agent.run(
    prompt,
    model_settings=ModelSettings(temperature=0.5)
)
```

**Эффект:** Централизация настроек, удаление ~50-100 строк custom конфигурации

---

#### 2.9.4 UsageLimits для контроля ресурсов
**Преимущество:** Встроенный контроль токенов, запросов и вызовов.

**Применение в проекте:**
```python
from pydantic_ai import UsageLimits

# Предотвращение runaway loops
result = await agent.run(
    prompt,
    usage_limits=UsageLimits(
        request_limit=5,      # Макс. 5 запросов к LLM
        total_tokens_limit=500,  # Макс. 500 токенов
        tool_calls_limit=10   # Макс. 10 вызовов инструментов
    )
)
```

**Эффект:** Замена custom лимитов, защита от зацикливания

---

#### 2.9.5 Testing Support
**Преимущество:** Встроенные `TestModel` и `override()` для тестирования.

**Применение в проекте:**
```python
from pydantic_ai.models.test import TestModel

# Тестирование без реальных LLM вызовов
test_model = TestModel()
agent.run_sync('test', model=test_model)

# Override зависимостей в тестах
class TestDeps:
    storage = MockStorage()

with agent.override(deps=TestDeps()):
    result = agent.run_sync('test')
```

**Эффект:** Упрощение тестирования (если будут добавлены тесты в будущем)

---

## 3. Детальный план изменений

### 3.1 Фаза 1: Базовая инфраструктура (Приоритет: Высокий)
1. ~~Создать `base_agent.py`~~ **ОТМЕНЕНО** — противоречит PydanticAI философии
2. Создать `agent_utils.py` с helper-функциями для общей логики
3. Создать `config.py` с централизованными конфигурациями (включая `BaseAgentConfig`)
4. Определить Pydantic-модели для всех типов сообщений в `message_models.py`
5. Обновить `agent_storage.py` для работы с новыми моделями
6. Добавить `pydantic-ai[retries]` в зависимости для замены TimeoutManager

**Файлы:**
- `src/thermo_agents/agent_utils.py` (новый) — helper функции
- `src/thermo_agents/config.py` (новый) — централизованные конфигурации
- `src/thermo_agents/message_models.py` (новый) — Pydantic модели сообщений
- `src/thermo_agents/agent_storage.py` (модификация)
- `pyproject.toml` (добавить `pydantic-ai[retries]`)

---

### 3.2 Фаза 2: Миграция агентов (Приоритет: Высокий)
1. Рефакторинг `thermodynamic_agent.py`:
   - Использовать встроенный `Agent` класс PydanticAI
   - Заменить custom retry на `retries` параметр
   - Использовать helper-функции из `agent_utils.py`
2. Рефакторинг `sql_generation_agent.py`:
   - Аналогично п.1
   - Упростить через dependency injection
3. Рефакторинг `database_agent.py`:
   - Убрать custom wrapper, использовать стандартный подход
4. Рефакторинг `individual_search_agent.py`:
   - Использовать `UsageLimits` для контроля
5. Обновить `orchestrator.py`:
   - Использовать паттерн **Agent Delegation** из документации
   - Передавать `ctx.usage` между агентами

**Файлы:**
- `src/thermo_agents/thermodynamic_agent.py` (рефакторинг)
- `src/thermo_agents/sql_generation_agent.py` (рефакторинг)
- `src/thermo_agents/database_agent.py` (рефакторинг)
- `src/thermo_agents/individual_search_agent.py` (рефакторинг)
- `src/thermo_agents/orchestrator.py` (рефакторинг)

---

### 3.3 Фаза 3: Очистка и оптимизация (Приоритет: Средний)
1. **УДАЛИТЬ** `message_validator.py` (~441 строка) после миграции на Pydantic-модели
2. **УДАЛИТЬ** `timeout_manager.py` (~600 строк) — заменить на встроенный retry PydanticAI
3. Проанализировать и упростить `graceful_degradation.py`
4. Оптимизировать `operations.py`
5. Рефакторинг `agent_storage.py` (удаление неиспользуемого)

**Файлы:**
- `src/thermo_agents/message_validator.py` (**УДАЛИТЬ** ~441 строка)
- `src/thermo_agents/timeout_manager.py` (**УДАЛИТЬ** ~600 строк)
- `src/thermo_agents/graceful_degradation.py` (упрощение)
- `src/thermo_agents/operations.py` (оптимизация)

---

### 3.4 Фаза 4: Главный модуль и утилиты (Приоритет: Низкий)
1. Упростить `main.py` с использованием новых базовых классов
2. Централизовать конфигурацию системы
3. Обновить импорты и зависимости

**Файлы:**
- `main.py` (упрощение)
- `src/thermo_agents/__init__.py` (обновление экспортов)

---

## 4. Технические детали реализации

### 4.1 ✅ Helper-функции вместо BaseAgent (соответствие PydanticAI)

**ОТКАЗ от наследования в пользу композиции и helper-функций:**

```python
# agent_utils.py - Helper функции для общей логики

async def start_agent_listener(
    agent_id: str,
    storage: AgentStorage,
    message_type: str,
    process_callback: Callable,
    poll_interval: float = 1.0,
    logger: Optional[logging.Logger] = None
) -> None:
    """Общая функция для цикла прослушивания сообщений."""
    running = True
    while running:
        messages = storage.receive_messages(agent_id, message_type)
        for message in messages:
            await process_callback(message)
        await asyncio.sleep(poll_interval)

def register_agent_in_storage(
    agent_id: str,
    storage: AgentStorage,
    capabilities: List[str],
    **metadata
) -> None:
    """Регистрация агента в хранилище."""
    storage.start_session(agent_id, {
        "status": "initialized",
        "capabilities": capabilities,
        **metadata
    })
```

**Преимущества:**
- Соответствие философии PydanticAI (композиция вместо наследования)
- Агенты остаются простыми и переиспользуемыми
- DRY через helper-функции
- Легче тестировать отдельные функции

---

### 4.2 Pydantic-модели сообщений

**Примеры моделей:**
```python
class ExtractParametersMessage(BaseMessage):
    message_type: Literal["extract_parameters"]
    user_query: str
    options: Dict[str, Any] = Field(default_factory=dict)

class GenerateQueryMessage(BaseMessage):
    message_type: Literal["generate_query"]
    sql_hint: str
    extracted_params: ExtractedParameters
    
class ExecuteSQLMessage(BaseMessage):
    message_type: Literal["execute_sql"]
    sql_query: str
    extracted_params: ExtractedParameters
```

**Преимущества:**
- Автоматическая валидация через Pydantic
- Type hints для IDE
- Самодокументирующийся код
- Удаление 400+ строк ручной валидации

---

### 4.3 ✅ Замена TimeoutManager на встроенный retry PydanticAI

**Использование встроенных возможностей PydanticAI:**

```python
# Вместо custom TimeoutManager используем встроенные механизмы

# 1. Retry на уровне агента
from pydantic_ai import Agent

agent = Agent(
    'openai:gpt-4o',
    retries=2,  # Встроенный retry механизм
)

# 2. Retry на уровне инструмента
@agent.tool(retries=3)
async def my_tool(ctx: RunContext, param: str) -> str:
    # Инструмент автоматически повторится до 3 раз
    ...

# 3. Ручное управление через ModelRetry
from pydantic_ai import ModelRetry

@agent.tool
async def smart_tool(ctx: RunContext, data: str) -> str:
    if not is_valid(data):
        raise ModelRetry("Please provide valid data")
    return process(data)

# 4. Использование UsageLimits для контроля
from pydantic_ai import UsageLimits

result = await agent.run(
    prompt,
    usage_limits=UsageLimits(
        request_limit=5,
        total_tokens_limit=500,
        tool_calls_limit=10
    )
)

# 5. HTTP retry для провайдеров
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig
from tenacity import stop_after_attempt, wait_exponential

transport = AsyncTenacityTransport(
    config=RetryConfig(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=60),
        reraise=True
    )
)
client = AsyncClient(transport=transport)
```

**Преимущества:**
- Удаление ~600 строк custom кода
- Использование проверенного решения от PydanticAI
- Интеграция с tenacity для продвинутых сценариев
- Автоматическая обработка Retry-After headers

---

### 4.4 Централизованная конфигурация

**Структура:**
```python
@dataclass
class SystemConfig:
    # LLM настройки
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    
    # Database
    db_path: str
    
    # Система
    log_level: str
    debug: bool
    
    # Агенты
    agent_poll_interval: float = 1.0
    agent_max_retries: int = 2
    agent_timeout: int = 60
```

---

## 5. Риски и митигация

### 5.1 Риск: Нарушение функциональности
**Вероятность:** Средняя  
**Влияние:** Высокое  
**Митигация:**
- Пошаговая миграция по одному агенту
- Ручное тестирование после каждого изменения
- Сохранение оригинальных файлов в git истории
- Использование отдельной ветки `refactoring/code-optimization`

### 5.2 Риск: Избыточное упрощение
**Вероятность:** Средняя  
**Влияние:** Среднее  
**Митигация:**
- Анализ реального использования перед удалением функционала
- Консультация с заказчиком при сомнениях
- Документирование удаленной функциональности

### 5.3 Риск: Рост сложности базового класса
**Вероятность:** Низкая  
**Влияние:** Среднее  
**Митигация:**
- Минималистичный BaseAgent (только общая логика)
- Композиция вместо наследования где возможно
- Code review структуры

---

## 6. Критерии успеха

### 6.1 Количественные метрики
- [ ] Сокращение кодовой базы на 25-35% (цель: ~56-65MB из 87MB)
  - MessageValidator: -441 строка
  - TimeoutManager: -600 строк
  - Общее дублирование: -500-800 строк
  - Упрощения: -200-400 строк
- [ ] Уменьшение дублирования кода на 70%+
- [ ] Сокращение среднего размера модуля на 30%

### 6.2 Качественные метрики
- [ ] Все агенты работают без ошибок
- [ ] Код проходит type checking (mypy)
- [ ] Улучшение читаемости (субъективная оценка)
- [ ] Упрощение добавления новых агентов

### 6.3 Функциональные требования
- [ ] Сохранение всех агентов: Orchestrator, Thermodynamic, SQL, Database, Individual Search
- [ ] Сохранение A2A архитектуры
- [ ] Сохранение текущего уровня логирования
- [ ] Сохранение промптов без изменений
- [ ] Работа индивидуального поиска соединений
- [ ] Работа параллельной обработки

---

## 7. План выполнения

### Этап 1: Подготовка (1-2 часа)
- [x] Создание ветки `refactoring/code-optimization`
- [x] Изучение документации PydanticAI
- [x] Создание технического задания
- [ ] Анализ использования GracefulDegradation
- [ ] Подготовка списка удаляемой функциональности

### Этап 2: Фаза 1 - Базовая инфраструктура (2-3 часа)
- [ ] Создание `agent_utils.py` с helper-функциями
- [ ] Создание `config.py` с централизованными конфигурациями
- [ ] Создание `message_models.py` с Pydantic моделями
- [ ] Обновление `agent_storage.py`
- [ ] Добавление `pydantic-ai[retries]` в зависимости

### Этап 3: Фаза 2 - Миграция агентов (3-4 часа)
- [ ] Рефакторинг Thermodynamic Agent (использование Agent, retries)
- [ ] Рефакторинг SQL Generation Agent (DI, helper-функции)
- [ ] Рефакторинг Database Agent (упрощение)
- [ ] Рефакторинг Individual Search Agent (UsageLimits)
- [ ] Обновление Orchestrator (Agent Delegation pattern)

### Этап 4: Фаза 3 - Очистка (2-3 часа)
- [ ] **УДАЛЕНИЕ** MessageValidator (~441 строка)
- [ ] **УДАЛЕНИЕ** TimeoutManager (~600 строк)
- [ ] Упрощение GracefulDegradation
- [ ] Оптимизация Operations

### Этап 5: Фаза 4 - Финализация (1-2 часа)
- [ ] Упрощение main.py (ModelSettings, dependencies)
- [ ] Обновление импортов
- [ ] Финальная проверка

### Этап 6: Тестирование (2-3 часа)
- [ ] Тестирование каждого агента отдельно
- [ ] Интеграционное тестирование
- [ ] Проверка логирования
- [ ] Проверка обработки ошибок
- [ ] Проверка retry механизма

**Общее время:** 11-17 часов

---

## 8. Документация изменений

### 8.1 Файлы для обновления
- [ ] README.md - обновление структуры проекта
- [ ] CHANGELOG.md - описание изменений рефакторинга
- [ ] Inline комментарии в коде

### 8.2 Миграционное руководство
- Не требуется (обратная совместимость не нужна)

---

## 9. Дополнительные возможности (опционально)

### 9.1 Потенциальные улучшения после основного рефакторинга
- Добавление type hints там, где их нет
- Создание utility функций для частых операций
- Оптимизация импортов
- Документация API в формате docstrings

### 9.2 Долгосрочная оптимизация
- Профилирование производительности
- Оптимизация запросов к БД
- Кэширование часто используемых данных

---

## 10. Контрольные точки согласования

### Точка 1: После Фазы 1
**Проверка:**
- Базовые классы созданы и протестированы
- Pydantic-модели определены
- Согласование архитектуры с заказчиком

### Точка 2: После миграции первого агента
**Проверка:**
- Один агент полностью мигрирован
- Функциональность сохранена
- Оценка объема сокращения кода

### Точка 3: После Фазы 3
**Проверка:**
- Все агенты мигрированы
- Старый код удален
- Система работает стабильно

---

## 11. Заключение

Данное техническое задание описывает комплексный рефакторинг системы термодинамических агентов с целью сокращения кода на 25-35% при полном сохранении функциональности.

**Ключевые изменения на основе документации PydanticAI:**

1. **⚠️ КРИТИЧНО:** Отказ от BaseAgent класса в пользу композиции (философия PydanticAI)
2. **✅ УДАЛЕНИЕ:** TimeoutManager (~600 строк) → встроенный retry механизм PydanticAI
3. **✅ УДАЛЕНИЕ:** MessageValidator (~441 строка) → Pydantic модели с автовалидацией
4. **✅ НОВОЕ:** Использование Agent Delegation pattern для координации
5. **✅ НОВОЕ:** Dependency Injection через `deps_type` и `RunContext`
6. **✅ НОВОЕ:** ModelSettings для централизованной конфигурации
7. **✅ НОВОЕ:** UsageLimits для контроля ресурсов

**Основные принципы:**
- **Композиция вместо наследования** (PydanticAI philosophy)
- **Использование встроенного функционала** фреймворка вместо custom кода
- **DRY** через helper-функции, а не через базовые классы
- **Type-safe** код с полной поддержкой IDE
- **Поддерживаемость** через предсказуемую структуру

**Ожидаемый результат:**
- Удаление ~1600-1800 строк кода (MessageValidator + TimeoutManager + дублирование)
- Сокращение на 25-35% от 87MB
- Все агенты сохранены и работают
- Полное соответствие best practices PydanticAI

Рефакторинг выполняется в отдельной ветке `refactoring/code-optimization` с возможностью отката и не требует обратной совместимости.
