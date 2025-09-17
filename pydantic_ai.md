# PydanticAI: Руководство по созданию абстрактных инструментов и агентов

## Философия архитектуры PydanticAI

PydanticAI следует функциональному подходу с композицией вместо наследования. Фреймворк спроектирован вокруг концепций:
- **Tools как функции**, а не классы
- **Agents как stateless контейнеры** для оркестрации
- **Dependency Injection** для управления зависимостями
- **Pydantic модели** для валидации данных
- **Type-first разработка** с полной типизацией

## 1. Создание абстрактных паттернов для Tools

### 1.1 Базовый паттерн Tool Factory

Вместо наследования от базового класса, используйте фабричные функции для создания семейств инструментов:

```python
from typing import TypeVar, Generic, Protocol, Callable, Any
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext, Tool
from dataclasses import dataclass
import functools

# Протокол для абстрактного процессора
class ProcessorProtocol(Protocol):
    """Протокол определяющий интерфейс процессора"""
    async def validate_input(self, data: Any) -> Any: ...
    async def process(self, data: Any) -> Any: ...
    async def validate_output(self, result: Any) -> Any: ...

# Generic типы для input/output
InputT = TypeVar('InputT', bound=BaseModel)
OutputT = TypeVar('OutputT', bound=BaseModel)

def create_processing_tool(
    name: str,
    input_model: type[InputT],
    output_model: type[OutputT],
    processor: ProcessorProtocol,
    description: str = None
) -> Callable:
    """
    Фабрика для создания инструментов с валидацией.
    Реализует паттерн Template Method через композицию.
    """
    async def tool_function(
        ctx: RunContext[Any],
        data: input_model
    ) -> output_model:
        # Template Method реализованный через композицию:
        # 1. Валидация входных данных (автоматически через Pydantic)
        validated_input = await processor.validate_input(data)
        
        # 2. Обработка
        raw_result = await processor.process(validated_input)
        
        # 3. Валидация выходных данных
        validated_output = await processor.validate_output(raw_result)
        
        # 4. Возврат типизированного результата
        return output_model(**validated_output)
    
    # Устанавливаем метаданные для инструмента
    tool_function.__name__ = name
    tool_function.__doc__ = description or f"Process {name}"
    
    return tool_function
```

### 1.2 Композиция инструментов через Toolsets

```python
from pydantic_ai.tools import ToolDefinition
from typing import Protocol

class ToolsetProtocol(Protocol):
    """Протокол для набора связанных инструментов"""
    def get_tools(self) -> list[Tool]: ...
    def get_definitions(self) -> list[ToolDefinition]: ...

@dataclass
class ThermodynamicsToolset:
    """Набор инструментов для термодинамических расчетов"""
    calculator: Any
    validator: Any
    database: Any
    
    def create_calculation_tool(self) -> Tool:
        """Создает инструмент расчета с замыканием на зависимости"""
        calculator = self.calculator
        
        async def calculate_properties(
            ctx: RunContext[Any],
            substance: str,
            temperature: float = Field(gt=0, le=1000, description="Temperature in K"),
            pressure: float = Field(gt=0, description="Pressure in Pa")
        ) -> dict:
            """Calculate thermodynamic properties"""
            return await calculator.calculate(substance, temperature, pressure)
        
        return Tool(calculate_properties)
    
    def create_validation_tool(self) -> Tool:
        """Создает инструмент валидации"""
        validator = self.validator
        
        async def validate_conditions(
            ctx: RunContext[Any],
            conditions: dict
        ) -> bool:
            """Validate thermodynamic conditions"""
            return await validator.validate(conditions)
        
        return Tool(validate_conditions)
    
    def get_all_tools(self) -> list[Tool]:
        """Возвращает все инструменты набора"""
        return [
            self.create_calculation_tool(),
            self.create_validation_tool()
        ]
```

### 1.3 Паттерн Tool Wrapper для миграции

```python
def wrap_existing_tool(
    legacy_tool: Any,
    method_name: str,
    input_transformer: Callable = None,
    output_transformer: Callable = None
) -> Tool:
    """
    Оборачивает существующий инструмент в PydanticAI Tool.
    Позволяет постепенную миграцию legacy кода.
    """
    async def wrapped_tool(ctx: RunContext[Any], **kwargs):
        # Преобразование входных данных если необходимо
        if input_transformer:
            kwargs = input_transformer(kwargs)
        
        # Вызов legacy метода
        method = getattr(legacy_tool, method_name)
        result = await method(**kwargs) if asyncio.iscoroutinefunction(method) else method(**kwargs)
        
        # Преобразование выходных данных
        if output_transformer:
            result = output_transformer(result)
        
        return result
    
    # Копируем метаданные
    wrapped_tool.__name__ = method_name
    wrapped_tool.__doc__ = getattr(legacy_tool, method_name).__doc__
    
    return Tool(wrapped_tool)
```

## 2. Создание абстрактных Agent паттернов

### 2.1 Базовый Agent Builder

```python
from typing import Type, Optional, List
from pydantic import BaseModel

class AgentBuilder:
    """Builder паттерн для создания агентов с общей конфигурацией"""
    
    def __init__(self, model: str = 'openai:gpt-4o'):
        self.model = model
        self.deps_type: Optional[Type] = None
        self.output_type: Optional[Type[BaseModel]] = None
        self.tools: List[Tool] = []
        self.system_prompt: str = ""
        self.instructions: List[str] = []
        self.retries: int = 2
        
    def with_dependencies(self, deps_type: Type) -> 'AgentBuilder':
        """Устанавливает тип зависимостей"""
        self.deps_type = deps_type
        return self
    
    def with_output(self, output_type: Type[BaseModel]) -> 'AgentBuilder':
        """Устанавливает тип выходных данных"""
        self.output_type = output_type
        return self
    
    def with_tools(self, *tools: Tool) -> 'AgentBuilder':
        """Добавляет инструменты"""
        self.tools.extend(tools)
        return self
    
    def with_toolset(self, toolset: Any) -> 'AgentBuilder':
        """Добавляет набор инструментов"""
        if hasattr(toolset, 'get_all_tools'):
            self.tools.extend(toolset.get_all_tools())
        return self
    
    def with_system_prompt(self, prompt: str) -> 'AgentBuilder':
        """Устанавливает системный промпт"""
        self.system_prompt = prompt
        return self
    
    def build(self) -> Agent:
        """Создает агента с заданной конфигурацией"""
        return Agent(
            model=self.model,
            deps_type=self.deps_type,
            output_type=self.output_type,
            tools=self.tools,
            system_prompt=self.system_prompt,
            retries=self.retries
        )
```

### 2.2 Композиция агентов через делегирование

```python
@dataclass
class AgentOrchestrator:
    """Оркестратор для управления множеством специализированных агентов"""
    
    analysis_agent: Agent
    calculation_agent: Agent
    validation_agent: Agent
    synthesis_agent: Agent
    
    async def process_complex_request(
        self, 
        request: str,
        deps: Any
    ) -> Any:
        """
        Обрабатывает сложный запрос через цепочку агентов.
        Реализует паттерн Chain of Responsibility.
        """
        # Этап 1: Анализ запроса
        analysis_result = await self.analysis_agent.run(
            f"Analyze this request: {request}",
            deps=deps
        )
        
        # Этап 2: Расчеты на основе анализа
        calc_result = await self.calculation_agent.run(
            f"Calculate based on: {analysis_result.output}",
            deps=deps,
            message_history=analysis_result.new_messages()
        )
        
        # Этап 3: Валидация результатов
        validation_result = await self.validation_agent.run(
            f"Validate: {calc_result.output}",
            deps=deps
        )
        
        # Этап 4: Синтез финального ответа
        final_result = await self.synthesis_agent.run(
            f"Synthesize final answer from: {validation_result.output}",
            deps=deps
        )
        
        return final_result.output
```

### 2.3 Динамическая регистрация инструментов

```python
class DynamicToolRegistry:
    """Реестр для динамической регистрации инструментов"""
    
    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self._conditions: dict[str, Callable] = {}
    
    def register(
        self, 
        name: str, 
        tool: Tool,
        condition: Optional[Callable[[RunContext], bool]] = None
    ):
        """Регистрирует инструмент с опциональным условием активации"""
        self._tools[name] = tool
        if condition:
            self._conditions[name] = condition
    
    async def prepare_tools(
        self, 
        ctx: RunContext[Any],
        tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        """Подготавливает инструменты на основе контекста"""
        active_tools = []
        
        for tool_def in tool_defs:
            name = tool_def.name
            
            # Проверяем условие активации
            if name in self._conditions:
                condition = self._conditions[name]
                if await condition(ctx):
                    active_tools.append(tool_def)
            else:
                active_tools.append(tool_def)
        
        return active_tools

# Использование динамического реестра
registry = DynamicToolRegistry()

# Регистрируем инструмент с условием
async def advanced_tool(ctx: RunContext[Any], data: str) -> str:
    return f"Advanced processing: {data}"

registry.register(
    "advanced_tool",
    Tool(advanced_tool),
    condition=lambda ctx: ctx.deps.user_level == "advanced"
)

# Создаем агента с динамическими инструментами
agent = Agent(
    'openai:gpt-4o',
    tools=[registry._tools[name] for name in registry._tools],
    tools_prepare=registry.prepare_tools
)
```

## 3. Паттерны валидации и типизации

### 3.1 Создание переиспользуемых валидаторов

```python
from pydantic import Field, validator, AfterValidator
from typing import Annotated
import re

# Создаем переиспользуемые валидаторы
def validate_chemical_formula(v: str) -> str:
    """Валидирует химическую формулу"""
    if not re.match(r'^[A-Z][a-z]?\d*(\([A-Z][a-z]?\d*\)\d*)*$', v):
        raise ValueError('Invalid chemical formula')
    return v

def validate_temperature_kelvin(v: float) -> float:
    """Валидирует температуру в Кельвинах"""
    if v < 0:
        raise ValueError('Temperature cannot be negative in Kelvin')
    if v > 6000:
        raise ValueError('Temperature exceeds reasonable limits')
    return v

# Создаем типизированные алиасы
ChemicalFormula = Annotated[str, AfterValidator(validate_chemical_formula)]
TemperatureKelvin = Annotated[float, AfterValidator(validate_temperature_kelvin)]

# Использование в моделях
class ThermodynamicRequest(BaseModel):
    """Модель запроса с валидацией"""
    substance: ChemicalFormula
    temperature: TemperatureKelvin
    pressure: float = Field(gt=0, le=1e9, description="Pressure in Pa")
    
    @validator('pressure')
    def validate_pressure_range(cls, v, values):
        """Дополнительная валидация на основе других полей"""
        if 'temperature' in values and values['temperature'] > 1000:
            if v < 1e5:  # Минимальное давление для высоких температур
                raise ValueError('Pressure too low for high temperature')
        return v
```

### 3.2 Generic модели для переиспользования

```python
from typing import Generic, TypeVar

T = TypeVar('T')
S = TypeVar('S')

class ProcessingRequest(BaseModel, Generic[T]):
    """Обобщенная модель запроса обработки"""
    data: T
    options: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)

class ProcessingResponse(BaseModel, Generic[T, S]):
    """Обобщенная модель ответа обработки"""
    input_data: T
    result: S
    success: bool
    errors: list[str] = Field(default_factory=list)
    processing_time_ms: float

# Специализация для конкретного домена
class ChemicalData(BaseModel):
    formula: ChemicalFormula
    properties: dict

class CalculationResult(BaseModel):
    enthalpy: float
    entropy: float
    gibbs_energy: float

# Использование generic моделей
ChemicalRequest = ProcessingRequest[ChemicalData]
ChemicalResponse = ProcessingResponse[ChemicalData, CalculationResult]
```

## 4. Лучшие практики организации кода

### 4.1 Структура проекта

```
project/
├── agents/
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── builders.py          # Agent builders
│   │   ├── protocols.py         # Протоколы и интерфейсы
│   │   └── types.py             # Типы и generic модели
│   ├── toolsets/
│   │   ├── __init__.py
│   │   ├── calculation.py       # Набор инструментов расчета
│   │   ├── validation.py        # Набор инструментов валидации
│   │   └── database.py          # Набор инструментов БД
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py          # Модели запросов
│   │   ├── responses.py         # Модели ответов
│   │   └── validators.py        # Переиспользуемые валидаторы
│   └── specialized/
│       ├── __init__.py
│       ├── thermodynamics.py    # Специализированный агент
│       └── chemistry.py         # Другой специализированный агент
```

### 4.2 Dependency Injection паттерны

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class DatabaseProtocol(Protocol):
    """Протокол для абстракции базы данных"""
    async def execute(self, query: str) -> list[dict]: ...
    async def validate(self, query: str) -> bool: ...

@runtime_checkable
class CalculatorProtocol(Protocol):
    """Протокол для абстракции калькулятора"""
    async def calculate(self, expression: str) -> float: ...

@dataclass
class Dependencies:
    """Контейнер зависимостей с валидацией протоколов"""
    database: DatabaseProtocol
    calculator: CalculatorProtocol
    config: dict
    
    def __post_init__(self):
        """Валидация соответствия протоколам"""
        if not isinstance(self.database, DatabaseProtocol):
            raise TypeError("database must implement DatabaseProtocol")
        if not isinstance(self.calculator, CalculatorProtocol):
            raise TypeError("calculator must implement CalculatorProtocol")

# Фабрика для создания зависимостей
class DependencyFactory:
    """Фабрика для создания и управления зависимостями"""
    
    @staticmethod
    def create_production() -> Dependencies:
        """Создает production зависимости"""
        return Dependencies(
            database=PostgreSQLDatabase(),
            calculator=ScientificCalculator(),
            config=load_production_config()
        )
    
    @staticmethod
    def create_testing() -> Dependencies:
        """Создает test зависимости"""
        return Dependencies(
            database=MockDatabase(),
            calculator=MockCalculator(),
            config={'test': True}
        )
```

### 4.3 Композиция vs Наследование

```python
# ❌ Антипаттерн: попытка наследования для tools
# PydanticAI не поддерживает это!
class BaseTool:  # Это НЕ работает в PydanticAI
    async def process(self, data):
        pass

# ✅ Правильный подход: композиция через функции и протоколы
class ToolComposer:
    """Компонует инструменты через композицию"""
    
    @staticmethod
    def compose(*processors: Callable) -> Callable:
        """Создает композицию процессоров"""
        async def composed_tool(ctx: RunContext[Any], data: Any) -> Any:
            result = data
            for processor in processors:
                result = await processor(ctx, result)
            return result
        return composed_tool
    
    @staticmethod
    def with_retry(tool: Callable, max_retries: int = 3) -> Callable:
        """Добавляет retry логику к инструменту"""
        @functools.wraps(tool)
        async def wrapped(ctx: RunContext[Any], *args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return await tool(ctx, *args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(2 ** attempt)
            
        return wrapped
    
    @staticmethod
    def with_cache(tool: Callable, ttl: int = 300) -> Callable:
        """Добавляет кеширование к инструменту"""
        cache = {}
        
        @functools.wraps(tool)
        async def wrapped(ctx: RunContext[Any], *args, **kwargs):
            cache_key = str((args, kwargs))
            
            if cache_key in cache:
                cached_value, cached_time = cache[cache_key]
                if time.time() - cached_time < ttl:
                    return cached_value
            
            result = await tool(ctx, *args, **kwargs)
            cache[cache_key] = (result, time.time())
            return result
        
        return wrapped
```

## 5. Тестирование абстракций

### 5.1 Тестирование инструментов

```python
import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai import models

# Отключаем реальные вызовы LLM
models.ALLOW_MODEL_REQUESTS = False

@pytest.fixture
def test_agent():
    """Создает агента для тестирования"""
    return AgentBuilder() \
        .with_dependencies(TestDependencies) \
        .with_output(TestOutput) \
        .build()

@pytest.fixture
def mock_deps():
    """Создает mock зависимости"""
    return TestDependencies(
        database=MockDatabase(),
        calculator=MockCalculator()
    )

async def test_tool_composition():
    """Тестирует композицию инструментов"""
    # Создаем композицию
    validator = lambda ctx, x: x if x > 0 else 0
    multiplier = lambda ctx, x: x * 2
    
    composed = ToolComposer.compose(validator, multiplier)
    
    # Тестируем
    result = await composed(None, 5)
    assert result == 10
    
    result = await composed(None, -5)
    assert result == 0

async def test_agent_with_mocked_model(test_agent, mock_deps):
    """Тестирует агента с мocked моделью"""
    with test_agent.override(model=TestModel()):
        result = await test_agent.run(
            "Test query",
            deps=mock_deps
        )
        assert result.output is not None
```

### 5.2 Property-based тестирование

```python
from hypothesis import given, strategies as st
from hypothesis.strategies import builds

# Стратегии для генерации тестовых данных
chemical_formula = st.text(
    alphabet=st.characters(whitelist_categories=('Lu',)),
    min_size=1,
    max_size=10
).filter(lambda x: re.match(r'^[A-Z]', x))

temperature = st.floats(min_value=0, max_value=6000)
pressure = st.floats(min_value=1, max_value=1e9)

# Property-based тест
@given(
    formula=chemical_formula,
    temp=temperature,
    press=pressure
)
async def test_calculation_properties(formula, temp, press):
    """Тестирует свойства расчетов"""
    request = ThermodynamicRequest(
        substance=formula,
        temperature=temp,
        pressure=press
    )
    
    # Проверяем инварианты
    assert request.temperature >= 0
    assert request.pressure > 0
    
    # Тестируем обработку
    result = await process_request(request)
    assert result.gibbs_energy <= result.enthalpy
```

## 6. Продвинутые паттерны

### 6.1 Middleware для агентов

```python
from typing import Any, Callable
import time

class AgentMiddleware:
    """Middleware паттерн для агентов"""
    
    @staticmethod
    def timing_middleware(func: Callable) -> Callable:
        """Добавляет замер времени выполнения"""
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                print(f"Execution time: {duration:.2f}s")
        return wrapped
    
    @staticmethod
    def logging_middleware(func: Callable) -> Callable:
        """Добавляет логирование"""
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            print(f"Calling {func.__name__} with {len(args)} args")
            result = await func(*args, **kwargs)
            print(f"Result type: {type(result)}")
            return result
        return wrapped

# Применение middleware
@AgentMiddleware.timing_middleware
@AgentMiddleware.logging_middleware
async def complex_calculation(ctx: RunContext[Any], data: dict) -> dict:
    """Сложный расчет с middleware"""
    await asyncio.sleep(1)  # Симуляция работы
    return {"result": "calculated"}
```

### 6.2 Event-driven архитектура

```python
from typing import List, Dict
from dataclasses import field

@dataclass
class EventDrivenAgent:
    """Агент с event-driven архитектурой"""
    
    agent: Agent
    event_handlers: Dict[str, List[Callable]] = field(default_factory=dict)
    
    def on(self, event: str, handler: Callable):
        """Регистрирует обработчик события"""
        if event not in self.event_handlers:
            self.event_handlers[event] = []
        self.event_handlers[event].append(handler)
    
    async def emit(self, event: str, data: Any = None):
        """Генерирует событие"""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                await handler(data)
    
    async def run_with_events(self, prompt: str, deps: Any) -> Any:
        """Запускает агента с обработкой событий"""
        await self.emit("before_run", {"prompt": prompt})
        
        try:
            result = await self.agent.run(prompt, deps=deps)
            await self.emit("after_run", {"result": result})
            return result
        except Exception as e:
            await self.emit("error", {"error": e})
            raise

# Использование
event_agent = EventDrivenAgent(agent=my_agent)

# Регистрируем обработчики
event_agent.on("before_run", lambda data: print(f"Starting: {data['prompt']}"))
event_agent.on("after_run", lambda data: print(f"Completed successfully"))
event_agent.on("error", lambda data: print(f"Error occurred: {data['error']}"))

# Запускаем с событиями
result = await event_agent.run_with_events("Calculate something", deps)
```

## Заключение

PydanticAI предоставляет мощные абстракции через:
- **Функциональную композицию** вместо классического ООП
- **Dependency Injection** для управления зависимостями
- **Type-safe валидацию** через Pydantic
- **Протоколы** для определения интерфейсов
- **Builder паттерны** для создания сложных агентов

Ключевые принципы:
1. Используйте композицию, а не наследование
2. Tools - это функции, а не классы
3. Agents - stateless и переиспользуемые
4. Валидация через Pydantic модели
5. Абстракции через протоколы и DI