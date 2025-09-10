# Pydantic AI — практическое руководство для термодинамических расчётов

Pydantic AI — это Python-фреймворк для создания агентных систем на базе LLM с упором на типобезопасность, структурированный вывод и наблюдаемость. Создан командой Pydantic, наследует принципы FastAPI: типизация, валидация данных и понятные контракты.

## Ключевые преимущества для научных расчётов

- **Типобезопасность**: все входы/выходы строго типизированы через Pydantic-модели
- **Структурированный вывод**: гарантированно валидные результаты с возможностью ретраев
- **Модульность**: разделение логики через агентов, инструменты и зависимости
- **Наблюдаемость**: встроенная интеграция с Logfire для отладки и мониторинга
- **Универсальность**: работает с OpenAI, Anthropic, Gemini, Groq, Cohere и другими провайдерами


## Установка и настройка

```powershell
# Установка через uv (рекомендуется)
uv add pydantic-ai

# Альтернативно через pip
pip install pydantic-ai
```

Для работы с конкретными провайдерами:
```powershell
# OpenAI
uv add pydantic-ai[openai]
$env:OPENAI_API_KEY = "your-key"

# Anthropic  
uv add pydantic-ai[anthropic]
$env:ANTHROPIC_API_KEY = "your-key"

# Google Gemini
uv add pydantic-ai[google]
$env:GOOGLE_API_KEY = "your-key"
```


## Основные концепции

### Agent — центральный объект системы
Инкапсулирует модель, инструкции, инструменты и схему вывода. Типизируется как `Agent[DepsType, OutputType]`.

### Инструкции (instructions) vs Системные промпты
- **instructions**: динамически применяются для текущего агента (рекомендуется)
- **system_prompt**: сохраняются в истории сообщений между вызовами

### Инструменты (tools) — функции для доступа к данным
Два типа регистрации:
- `@agent.tool`: для функций, требующих `RunContext[Deps]`
- `@agent.tool_plain`: для простых функций без контекста

### Зависимости (deps) — типобезопасная инъекция данных
Передаются через `RunContext[DepsType]` в инструменты и инструкции.

### Структурированный вывод (output_type)
Гарантирует возврат данных, соответствующих Pydantic-модели. При ошибках валидации — автоматический ретрай.


## Пример агента для термодинамических расчётов

```python
from dataclasses import dataclass
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
import sqlite3

# Зависимости агента
@dataclass
class ThermoDbDeps:
    db_path: str
    T_ref: float = 298.15

# Структура результата
class ThermoResult(BaseModel):
    formula: str = Field(description="Химическая формула")
    T: float = Field(description="Температура, K") 
    Cp: float = Field(description="Теплоёмкость, Дж/(моль·К)")
    delta_H: float = Field(description="Изменение энтальпии, Дж/моль")
    delta_S: float = Field(description="Изменение энтропии, Дж/(моль·К)")
    delta_G: float = Field(description="Энергия Гиббса, Дж/моль")
    in_range: bool = Field(description="T в рабочем диапазоне")

# Создание агента
thermo_agent = Agent(
    'openai:gpt-4o',
    deps_type=ThermoDbDeps,
    output_type=ThermoResult,
    instructions="""
    Ты специалист по термодинамическим расчётам.
    Используй инструменты для поиска веществ в БД и расчёта свойств.
    Всегда проверяй температурные диапазоны.
    """
)

@thermo_agent.tool
async def find_species(ctx: RunContext[ThermoDbDeps], formula: str) -> dict:
    """Найти вещество в термодинамической БД по формуле"""
    # Подключение к БД и поиск
    with sqlite3.connect(ctx.deps.db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM compounds WHERE Formula = ?", (formula,)
        )
        row = cursor.fetchone()
        if row:
            return dict(zip([col[0] for col in cursor.description], row))
    raise ValueError(f"Вещество {formula} не найдено")

@thermo_agent.tool
def calc_thermo_props(
    ctx: RunContext[ThermoDbDeps], 
    T: float, 
    H298: float, S298: float,
    f1: float, f2: float, f3: float, f4: float, f5: float, f6: float,
    Tmin: float, Tmax: float
) -> dict:
    """Вычислить термодинамические свойства при температуре T"""
    
    # Проверка диапазона
    in_range = Tmin <= T <= Tmax
    
    # Расчёт Cp по коэффициентам (упрощённо)
    T_scaled = T / 1000.0
    Cp = f1 + f2*T_scaled + f3*T_scaled**2 + f4*T_scaled**3 + f5/T_scaled**2
    
    # Интегрирование для ΔH и ΔS (упрощённо)
    delta_T = T - ctx.deps.T_ref
    delta_H = H298 * 1000 + Cp * delta_T  # kJ/mol -> J/mol
    delta_S = S298 + Cp * (T / ctx.deps.T_ref - 1)
    
    # Энергия Гиббса
    delta_G = delta_H - T * delta_S
    
    return {
        'Cp': Cp, 'delta_H': delta_H, 'delta_S': delta_S, 
        'delta_G': delta_G, 'in_range': in_range
    }

# Использование
deps = ThermoDbDeps("data/thermo_data.db")
result = thermo_agent.run_sync(
    "Рассчитай термосвойства ZrO2(s) при 1000K", 
    deps=deps
)
print(result.output)
```


## Режимы структурированного вывода

Pydantic AI поддерживает три режима получения структурированных данных:

### 1. Tool Output (по умолчанию, рекомендуется)
Использует инструменты модели для генерации структурированного вывода. Поддерживается всеми моделями.

```python
from pydantic import BaseModel
from pydantic_ai import Agent, ToolOutput

class ReactionResult(BaseModel):
    equation: str
    delta_G: float  # кДж/моль
    feasible: bool

agent = Agent(
    'openai:gpt-4o',
    output_type=ToolOutput(ReactionResult, name='reaction_analysis')
)
```

### 2. Native Output
Использует встроенные возможности модели для структурированного вывода (не все модели поддерживают).

```python
from pydantic_ai import Agent, NativeOutput

agent = Agent(
    'openai:gpt-4o',
    output_type=NativeOutput(ReactionResult)
)
```

### 3. Prompted Output  
Модель получает инструкции в тексте промпта. Менее надёжно, но работает со всеми моделями.

```python
from pydantic_ai import Agent, PromptedOutput

agent = Agent(
    'openai:gpt-4o',
    output_type=PromptedOutput(ReactionResult)
)
```


## Валидация и обработка ошибок

### Автоматические ретраи
Pydantic AI автоматически повторяет запросы при ошибках валидации:

```python
from pydantic_ai import Agent, ModelRetry

@agent.tool
def calculate_with_validation(temperature: float) -> float:
    if temperature < 0:
        raise ModelRetry("Температура не может быть отрицательной")
    return temperature + 273.15

# При retries=3 будет до 3 попыток исправить ошибку
agent = Agent('openai:gpt-4o', retries=3)
```

### Output Validators
Дополнительная валидация результатов:

```python
@agent.output_validator
async def validate_thermo_result(
    ctx: RunContext[ThermoDbDeps], output: ThermoResult
) -> ThermoResult:
    # Проверка физической корректности
    if output.delta_G > 1000000:  # > 1 МДж/моль
        raise ModelRetry("Энергия Гиббса физически некорректна")
    return output
```


## Управление сообщениями и диалоги

### Доступ к истории сообщений
```python
result = agent.run_sync('Первый вопрос')
print(result.output)

# Продолжение диалога с контекстом
result2 = agent.run_sync(
    'Дополнительный вопрос', 
    message_history=result.new_messages()
)

# Все сообщения
all_msgs = result2.all_messages()
# Только новые сообщения из последнего запуска  
new_msgs = result2.new_messages()
```

### Обработка истории сообщений
Ограничение количества сообщений для экономии токенов:

```python
from pydantic_ai.messages import ModelMessage

async def keep_recent_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Оставить только последние 5 сообщений"""
    return messages[-5:] if len(messages) > 5 else messages

agent = Agent('openai:gpt-4o', history_processors=[keep_recent_messages])
```

### Сохранение и загрузка истории
```python
from pydantic_ai.messages import ModelMessagesTypeAdapter
import json

# Сохранение
history = result.all_messages()
with open('history.json', 'w') as f:
    json.dump(ModelMessagesTypeAdapter.dump_python(history), f)

# Загрузка
with open('history.json') as f:
    loaded_history = ModelMessagesTypeAdapter.validate_python(json.load(f))
```


## Потоковый вывод

### Потоковый текст
```python
async def stream_example():
    async with agent.run_stream('Объясни процесс хлорирования') as result:
        async for text in result.stream_text():
            print(text)  # Выводит накопленный текст
            
        # Для дельт (только изменения)
        async for delta in result.stream_text(delta=True):
            print(delta, end='')
```

### Потоковый структурированный вывод
```python
from typing_extensions import NotRequired, TypedDict

class ReactionAnalysis(TypedDict):
    reactants: list[str]
    products: NotRequired[list[str]]
    delta_G: NotRequired[float]
    
agent = Agent('openai:gpt-4o', output_type=ReactionAnalysis)

async def stream_structured():
    query = 'Проанализируй реакцию: ZrO2 + 4HCl -> ZrCl4 + 2H2O'
    async with agent.run_stream(query) as result:
        async for partial in result.stream_output():
            print(partial)  # Частично заполненный результат
```


## Настройки модели и ограничения

### Настройки модели (ModelSettings)
```python
from pydantic_ai import Agent, ModelSettings

agent = Agent(
    'openai:gpt-4o',
    model_settings=ModelSettings(
        temperature=0.1,  # Низкая температура для научных расчётов
        max_tokens=2000,
        timeout=30.0
    )
)

# Переопределение на уровне запуска
result = agent.run_sync(
    'Рассчитай энтальпию',
    model_settings=ModelSettings(temperature=0.0)  # Детерминированный вывод
)
```

### Ограничения использования (UsageLimits)
```python
from pydantic_ai import Agent, UsageLimits

agent = Agent('openai:gpt-4o')

try:
    result = agent.run_sync(
        'Сложная задача',
        usage_limits=UsageLimits(
            request_limit=5,        # Максимум 5 запросов к модели
            tool_calls_limit=10,    # Максимум 10 вызовов инструментов
            response_tokens_limit=1000  # Максимум токенов в ответе
        )
    )
except UsageLimitExceeded as e:
    print(f"Превышен лимит: {e}")
```


## Наблюдаемость с Logfire

Встроенная интеграция с Pydantic Logfire для отладки и мониторинга:

```python
import logfire
from pydantic_ai import Agent

# Глобальная настройка
logfire.configure()
logfire.instrument_pydantic_ai()

# Дополнительные инструменты
logfire.instrument_sqlite3()  # Для SQLite запросов

agent = Agent('openai:gpt-4o')
result = agent.run_sync('Анализ')  # Автоматически логируется

# Или выборочно для конкретного вызова
from pydantic_ai.direct import model_request_sync

response = model_request_sync(
    'openai:gpt-4o',
    [{'role': 'user', 'content': 'Привет'}],
    instrument=True  # Включить только для этого запроса
)
```

Преимущества:
- Трассировка всех шагов агента и вызовов инструментов
- Мониторинг производительности и стоимости
- Отладка ошибок валидации и ретраев
- Метрики использования токенов по провайдерам


## Тестирование агентов

### Переопределение зависимостей
```python
from dataclasses import dataclass

@dataclass 
class MockThermoDb:
    def get_compound(self, formula: str):
        # Тестовые данные вместо реальной БД
        return {"Formula": formula, "H298": -1000, "S298": 50}

# В тестах
def test_thermo_calculation():
    test_deps = MockThermoDb()
    
    with thermo_agent.override(deps=test_deps):
        result = thermo_agent.run_sync("Рассчитай для H2O")
        assert result.output.formula == "H2O"
```

### Тестирование с FunctionModel
```python
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, TextPart

def test_function(messages, info):
    # Детерминированные ответы для тестов
    return ModelResponse(parts=[TextPart(content="Test response")])

test_model = FunctionModel(test_function)
result = agent.run_sync("Test", model=test_model)
```

### Ограничения в тестах
```python
# Быстрые тесты с ограничениями
result = agent.run_sync(
    "Simple test",
    usage_limits=UsageLimits(request_limit=1, tool_calls_limit=3)
)
```


## Многоагентные паттерны

### Оркестратор + специализированные агенты
```python
# Агент для поиска в БД
db_agent = Agent[ThermoDbDeps, dict](
    'openai:gpt-4o-mini',  # Дешёвая модель для простых задач
    deps_type=ThermoDbDeps,
    output_type=dict,
    instructions="Найди вещество в БД по формуле"
)

# Агент для расчётов 
calc_agent = Agent[None, ThermoResult](
    'openai:gpt-4o',  # Мощная модель для сложных расчётов
    output_type=ThermoResult,
    instructions="Вычисли термодинамические свойства"
)

# Оркестратор
orchestrator = Agent(
    'openai:gpt-4o',
    instructions="Координируй работу других агентов"
)

@orchestrator.tool
async def delegate_to_db_agent(formula: str) -> dict:
    """Найти вещество через агента БД"""
    result = await db_agent.run(f"Найди {formula}", deps=db_deps)
    return result.output

@orchestrator.tool  
async def delegate_to_calc_agent(compound_data: dict, temperature: float) -> ThermoResult:
    """Рассчитать свойства через агента расчётов"""
    result = await calc_agent.run(
        f"Рассчитай свойства при {temperature}K для: {compound_data}"
    )
    return result.output
```

### Передача контекста между агентами
```python
# Первый агент
result1 = agent1.run_sync("Анализ реакции")

# Второй агент с контекстом от первого
result2 = agent2.run_sync(
    "Продолжи анализ", 
    message_history=result1.new_messages()
)
```


## Лучшие практики для научных расчётов

### 1. Типобезопасность
```python
# Всегда указывайте типы зависимостей и выходов
agent: Agent[ThermoDbDeps, ThermoResult] = Agent(
    'openai:gpt-4o',
    deps_type=ThermoDbDeps,
    output_type=ThermoResult
)
```

### 2. Валидация научных данных
```python
class ThermoResult(BaseModel):
    temperature: float = Field(gt=0, description="Температура > 0K")
    delta_G: float = Field(description="Энергия Гиббса, Дж/моль")
    
    @field_validator('temperature')
    @classmethod
    def validate_temperature(cls, v):
        if v > 6000:  # Выше температуры плазмы
            raise ValueError("Нереалистично высокая температура")
        return v
```

### 3. Детерминированность для расчётов
```python
# Низкая температура для точных вычислений
model_settings = ModelSettings(temperature=0.1, max_tokens=2000)
agent = Agent('openai:gpt-4o', model_settings=model_settings)
```

### 4. Обработка ошибок диапазонов
```python
@agent.tool
def check_temperature_range(T: float, Tmin: float, Tmax: float) -> bool:
    """Проверить, что температура в допустимом диапазоне"""
    if not (Tmin <= T <= Tmax):
        raise ModelRetry(
            f"Температура {T}K вне диапазона [{Tmin}, {Tmax}]K. "
            f"Используй ближайшие допустимые значения."
        )
    return True
```

### 5. Кэширование для производительности
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_compound_data(formula: str) -> dict:
    """Кэшированный поиск соединений"""
    # Дорогой запрос к БД
    pass

@agent.tool
def cached_compound_lookup(formula: str) -> dict:
    return get_compound_data(formula)
```


## Решение распространённых проблем

### Превышение лимитов токенов
```python
# Ограничьте историю сообщений
def truncate_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    return messages[-10:]  # Последние 10 сообщений

agent = Agent('openai:gpt-4o', history_processors=[truncate_history])
```

### Ошибки валидации
```python
# Детальная диагностика через output validator
@agent.output_validator
async def detailed_validation(ctx, output: ThermoResult) -> ThermoResult:
    issues = []
    if output.delta_G > 1e6:
        issues.append("Энергия Гиббса слишком высокая")
    if output.temperature < 0:
        issues.append("Отрицательная температура")
    
    if issues:
        raise ModelRetry(f"Проблемы с результатом: {'; '.join(issues)}")
    return output
```

### Отладка инструментов
```python
import logging

# Включить логирование для отладки
logging.basicConfig(level=logging.DEBUG)

@agent.tool
def debug_tool(param: str) -> str:
    print(f"Вызов инструмента с параметром: {param}")
    # Ваша логика
    return "result"
```

### Работа с отсутствующими данными
```python
@agent.tool
def robust_compound_search(formula: str) -> dict:
    """Поиск с обработкой отсутствующих данных"""
    try:
        return find_compound(formula)
    except CompoundNotFound:
        # Предложить альтернативы
        alternatives = find_similar_compounds(formula)
        raise ModelRetry(
            f"Соединение {formula} не найдено. "
            f"Доступные альтернативы: {alternatives}"
        )
```


## Интеграция с научным стеком Python

### Работа с NumPy/SciPy
```python
import numpy as np
from scipy.integrate import quad

@agent.tool
def numerical_integration(
    coefficients: list[float], 
    T_start: float, 
    T_end: float
) -> float:
    """Численное интегрирование теплоёмкости"""
    def cp_func(T):
        T_scaled = T / 1000.0
        return sum(c * T_scaled**i for i, c in enumerate(coefficients))
    
    result, _ = quad(cp_func, T_start, T_end)
    return float(result)
```

### Работа с Pandas DataFrame
```python
import pandas as pd

@agent.tool
def analyze_data_table(csv_path: str) -> dict:
    """Анализ табличных данных"""
    df = pd.read_csv(csv_path)
    return {
        'mean_temperature': float(df['Temperature'].mean()),
        'max_pressure': float(df['Pressure'].max()),
        'compound_count': len(df['Formula'].unique())
    }
```

### Matplotlib для графиков
```python
import matplotlib.pyplot as plt
import io
import base64

@agent.tool
def plot_phase_diagram(temperatures: list[float], pressures: list[float]) -> str:
    """Создать фазовую диаграмму и вернуть как base64"""
    fig, ax = plt.subplots()
    ax.plot(temperatures, pressures)
    ax.set_xlabel('Температура, K')
    ax.set_ylabel('Давление, атм')
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png')
    buffer.seek(0)
    
    image_base64 = base64.b64encode(buffer.getvalue()).decode()
    plt.close()
    return image_base64
```


## Полезные ссылки

### Основная документация
- [Официальный сайт](https://ai.pydantic.dev/)
- [Установка](https://ai.pydantic.dev/install/)
- [Руководство по агентам](https://ai.pydantic.dev/agents/)
- [Инструменты](https://ai.pydantic.dev/tools/)
- [Зависимости](https://ai.pydantic.dev/dependencies/)
- [Структурированный вывод](https://ai.pydantic.dev/output/)
- [История сообщений](https://ai.pydantic.dev/message-history/)

### API Reference  
- [pydantic_ai.agent](https://ai.pydantic.dev/api/agent/)
- [pydantic_ai.tools](https://ai.pydantic.dev/api/tools/)
- [pydantic_ai.output](https://ai.pydantic.dev/api/output/)
- [pydantic_ai.messages](https://ai.pydantic.dev/api/messages/)
- [pydantic_ai.settings](https://ai.pydantic.dev/api/settings/)

### Модели и провайдеры
- [OpenAI](https://ai.pydantic.dev/models/openai/)
- [Anthropic](https://ai.pydantic.dev/models/anthropic/)
- [Google Gemini](https://ai.pydantic.dev/models/google/)
- [Groq](https://ai.pydantic.dev/models/groq/)

### Примеры проектов
- [Пример с SQL](https://ai.pydantic.dev/examples/sql-gen/)
- [Чат-приложение](https://ai.pydantic.dev/examples/chat-app/)
- [Анализ данных](https://ai.pydantic.dev/examples/data-analyst/)

---

Эта документация охватывает основные возможности Pydantic AI применительно к задачам термодинамических расчётов. Для актуальной информации обращайтесь к официальной документации.
