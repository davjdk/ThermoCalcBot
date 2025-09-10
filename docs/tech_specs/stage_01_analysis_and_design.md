# Этап 1: Анализ и проектирование

## Краткое описание

Система агентов для анализа термодинамической возможности химических реакций с использованием:
- **Модель**: OpenRouter AI (гибкий выбор провайдера)
- **База данных**: SQLite с термодинамическими константами
- **Архитектура**: Pydantic AI с типобезопасными агентами
- **Основные сценарии**: хлорирование оксидов металлов, поиск температурных условий реакций


## 1. Цели и результаты

Функциональные цели:
- **Анализ осуществимости реакций**: определение термодинамической возможности процессов хлорирования оксидов
- **Расчёт термодинамических величин**: Cp(T), ΔH(T), ΔS(T), ΔG(T) для отдельных веществ и реакций
- **Поиск условий реакций**: определение температуры начала реакции (T_eq где ΔG≈0)
- **Разрешение веществ**: надёжное сопоставление формула → запись БД с учётом фазы и температурного диапазона
- **Балансировка реакций**: автоматическое составление уравнений с учётом побочных продуктов

Нефункциональные:
- **Типобезопасность**: `Agent[Deps, Output]` с валидируемыми Pydantic моделями
- **Провайдер модели**: OpenRouter AI (поддержка multiple LLM providers)
- **Локальная БД**: SQLite (путь из `OPENROUTER_BASE_URL`, `DB_PATH`)
- **Наблюдаемость**: Pydantic Logfire для трассировки, usage limits
- **Кроссплатформенность**: uv + .env для Windows/Linux

Критерии готовности (acceptance):
- Агенты (Orchestrator, DB Resolver, Thermo Calculator, Reactions Analyzer) проходят unit-тесты
- **Тестовые сценарии**:
  1. "Возможно ли хлорирование оксида циркония четыреххлористым углеродом? При какой температуре начнется реакция?"
  2. "Возможна ли реакция оксида титана с хлором при 700 градусах в присутствии метана?"
- Структурированный JSON-ответ + краткое резюме на русском языке
- При отсутствии данных — информативная диагностика с альтернативами


## 2. Данные и математические модели

### 2.1 Источник данных
SQLite `data/thermo_data.db` (конфигурируется через `DB_PATH`).

**Основная таблица**: `compounds`
- `Formula`, `Phase` (s|l|g|aq), `Tmin`, `Tmax` (K)
- `H298` (кДж/моль), `S298` (Дж/(моль·К))
- Коэффициенты теплоёмкости: `f1`, `f2`, `f3`, `f4`, `f5`, `f6`
- `source`, дополнительные идентификаторы/синонимы

**Индексы**: `(Formula, Phase, Tmin, Tmax)` для быстрого поиска

### 2.2 Формула расчёта теплоёмкости
```python
def cp_function(T):
    """Теплоёмкость в Дж/(моль·К) при температуре T (K)"""
    return (f1 + f2*T/1000 + f3*T**(-2) * 100_000 + 
            f4*T**2 / 1_000_000 + f5*T**(-3) * 1_000 + 
            f6*T**3 * 10**(-9))
```

### 2.3 Интегрирование термодинамических функций
- **ΔH(T)**: численное интегрирование Cp от T_ref=298.15 K до T
- **ΔS(T)**: интегрирование Cp/T от T_ref до T
- **ΔG(T)**: ΔH(T) - T·ΔS(T)
- **Единицы**: все расчёты в Дж/моль, H298 конвертируется из кДж/моль

### 2.4 Ограничения и валидация
- При T вне [Tmin, Tmax] — расчёт с флагом `in_range=False`
- При неоднозначностях фазы/диапазона — предупреждения в диагностике
- Точность интегрирования: 400 точек по умолчанию


## 3. Архитектура агентов на Pydantic AI

### 3.1 Общая схема
```
┌─────────────────┐    ┌──────────────────┐    ┌────────────────┐
│  User Query     │───▶│  Orchestrator    │───▶│  Final Result  │
│  (Natural Lang) │    │  Agent           │    │  (JSON + Text) │
└─────────────────┘    └──────────────────┘    └────────────────┘
                                │
                 ┌──────────────┼──────────────┐
                 ▼              ▼              ▼
        ┌─────────────┐ ┌──────────────┐ ┌────────────────┐
        │ DB Resolver │ │ Thermo Calc  │ │ Reactions      │
        │ Agent       │ │ Agent        │ │ Analyzer Agent │
        └─────────────┘ └──────────────┘ └────────────────┘
                 │              │              │
                 ▼              ▼              ▼
        ┌─────────────┐ ┌──────────────┐ ┌────────────────┐
        │ SQLite DB   │ │ Thermo Funcs │ │ Balancing      │
        │ Provider    │ │ (Cp, H, S, G)│ │ & T_eq Search  │
        └─────────────┘ └──────────────┘ └────────────────┘
```

### 3.2 Описание агентов

**Orchestrator Agent** `Agent[AppDeps, UserResponse]`
- Принимает пользовательский запрос на русском языке
- Парсит тип задачи (анализ реакции vs свойства вещества)
- Координирует работу специализированных агентов
- Агрегирует результаты в итоговый ответ
- Управляет message_history для многошаговых диалогов

**DB Resolver Agent** `Agent[DBDeps, SpeciesLookupResult]`
- Поиск веществ по формуле/названию с нормализацией регистра
- Разрешение синонимов и альтернативных записей
- Выбор оптимальной записи по температурному диапазону
- Фильтрация по фазовому состоянию

**Thermo Calculator Agent** `Agent[ThermoDeps, ThermoProperties]`
- Расчёт Cp(T), ΔH(T), ΔS(T), ΔG(T) по коэффициентам БД
- Валидация температурных диапазонов
- Генерация термодинамических таблиц
- Контроль точности численного интегрирования

**Reactions Analyzer Agent** `Agent[ReactionDeps, ReactionResult]`
- Балансировка химических уравнений по элементам
- Перебор гипотез для побочных продуктов
- Расчёт ΔG_реакции суммированием по стехиометрии
- Поиск T_eq методом бисекции/секущих

### 3.3 Pydantic AI особенности
- **Tool Output mode**: структурированный вывод через инструменты модели
- **Type safety**: `Agent[DepsType, OutputType]` с валидацией
- **Usage limits**: `tool_calls_limit=12`, токен-лимиты для экономии
- **Model settings**: низкая температура (0.1-0.2) для научных расчётов
- **Retries**: автоматические ретраи при ошибках валидации


## 4. Модели данных и контракты API

### 4.1 Основные Pydantic модели

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum

class Phase(str, Enum):
    SOLID = "s"
    LIQUID = "l" 
    GAS = "g"
    AQUEOUS = "aq"

class SpeciesRecord(BaseModel):
    """Запись вещества из БД"""
    formula: str = Field(description="Химическая формула")
    phase: Phase = Field(description="Фазовое состояние")
    tmin: float = Field(description="Минимальная температура, K", gt=0)
    tmax: float = Field(description="Максимальная температура, K", gt=0)
    H298_kJ_per_mol: float = Field(description="Энтальпия образования при 298K, кДж/моль")
    S298_J_per_molK: float = Field(description="Энтропия при 298K, Дж/(моль·К)")
    f1: float = Field(description="Коэффициент f1 для Cp")
    f2: float = Field(description="Коэффициент f2 для Cp") 
    f3: float = Field(description="Коэффициент f3 для Cp")
    f4: float = Field(description="Коэффициент f4 для Cp")
    f5: float = Field(description="Коэффициент f5 для Cp")
    f6: float = Field(description="Коэффициент f6 для Cp")
    source: str = Field(description="Источник данных")
    notes: Optional[str] = Field(default=None, description="Дополнительные заметки")

class ThermoPoint(BaseModel):
    """Термодинамические свойства при заданной температуре"""
    T: float = Field(description="Температура, K", gt=0)
    Cp: float = Field(description="Теплоёмкость, Дж/(моль·К)")
    H: float = Field(description="Энтальпия, Дж/моль")
    S: float = Field(description="Энтропия, Дж/(моль·К)")
    G: float = Field(description="Энергия Гиббса, Дж/моль")
    in_range: bool = Field(description="Температура в рабочем диапазоне")

class ReactionParticipant(BaseModel):
    """Участник химической реакции"""
    name: str = Field(description="Название вещества")
    formula: str = Field(description="Химическая формула")
    phase: Optional[Phase] = Field(default=None, description="Фазовое состояние")
    role: Literal['reactant', 'product'] = Field(description="Роль в реакции")
    coefficient: Optional[float] = Field(default=None, description="Стехиометрический коэффициент")

class ReactionResult(BaseModel):
    """Результат анализа реакции"""
    balanced_equation: str = Field(description="Сбалансированное уравнение реакции")
    delta_H_kJ_per_mol: float = Field(description="Изменение энтальпии, кДж/моль")
    delta_S_J_per_molK: float = Field(description="Изменение энтропии, Дж/(моль·К)")
    delta_G_kJ_per_mol: float = Field(description="Изменение энергии Гиббса, кДж/моль")
    feasible_at_T: Optional[bool] = Field(default=None, description="Возможна ли реакция при заданной T")
    T_equilibrium: Optional[float] = Field(default=None, description="Температура равновесия, K")
    confidence: float = Field(description="Уверенность в результате, 0-1", ge=0, le=1)
    diagnostics: dict = Field(description="Диагностическая информация")

class UserResponse(BaseModel):
    """Итоговый ответ пользователю"""
    query_type: Literal['reaction_analysis', 'substance_properties'] = Field(description="Тип запроса")
    reaction_result: Optional[ReactionResult] = Field(default=None, description="Результат анализа реакции")
    substance_properties: Optional[list[ThermoPoint]] = Field(default=None, description="Свойства веществ")
    summary_ru: str = Field(description="Краткий ответ на русском языке")
    recommendations: list[str] = Field(description="Рекомендации и предложения")
    data_quality: dict = Field(description="Информация о качестве данных")
```

### 4.2 Контракты инструментов

**DB Resolver Tools:**
```python
@agent.tool
async def resolve_species(
    ctx: RunContext[DBDeps], 
    formula: str, 
    phase_hint: Optional[str] = None,
    temperature: Optional[float] = None
) -> SpeciesRecord:
    """Найти вещество в БД с учётом фазы и температуры"""

@agent.tool 
async def search_species_alternatives(
    ctx: RunContext[DBDeps],
    query: str
) -> list[dict]:
    """Поиск альтернативных записей при неточном совпадении"""
```

**Thermo Calculator Tools:**
```python
@agent.tool
async def calculate_properties(
    ctx: RunContext[ThermoDeps],
    species: SpeciesRecord,
    temperature: float
) -> ThermoPoint:
    """Рассчитать термодинамические свойства при T"""

@agent.tool
async def generate_thermo_table(
    ctx: RunContext[ThermoDeps],
    species: SpeciesRecord,
    T_start: float,
    T_end: float,
    step: int = 100
) -> list[ThermoPoint]:
    """Генерация таблицы свойств в диапазоне температур"""
```

**Reactions Analyzer Tools:**
```python
@agent.tool
async def balance_reaction(
    ctx: RunContext[ReactionDeps],
    reactants: list[str],
    products: list[str]
) -> dict:
    """Балансировка химического уравнения"""

@agent.tool
async def find_equilibrium_temperature(
    ctx: RunContext[ReactionDeps],
    participants: list[ReactionParticipant],
    T_bounds: tuple[float, float] = (298, 2000)
) -> Optional[float]:
    """Найти температуру равновесия методом бисекции"""
```
