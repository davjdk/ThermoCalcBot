# ТЗ v1.1: Команда агентов термодинамических расчётов на базе Pydantic AI

Версия: 1.1 (детализированная). Основано на черновике `tech_spec.md`, возможностях Pydantic AI и конкретных требованиях пользователя.

См. справочные материалы: `docs/pydantic-ai-ru.md`, https://ai.pydantic.dev/agents/

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


## 5. Конфигурация и зависимости

### 5.1 OpenRouter AI Configuration
```python
from dataclasses import dataclass
from typing import Callable
import sqlite3

@dataclass
class ModelConfig:
    """Конфигурация для OpenRouter AI"""
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str  # Из переменной окружения OPENROUTER_API_KEY
    default_model: str = "anthropic/claude-3.5-sonnet"  # Высокое качество для научных расчётов
    backup_models: list[str] = None  # Фоллбэк модели
    
    def __post_init__(self):
        if self.backup_models is None:
            self.backup_models = [
                "openai/gpt-4o",
                "google/gemini-pro-1.5",
                "meta-llama/llama-3.1-70b-instruct"
            ]

@dataclass 
class DBDeps:
    """Зависимости для работы с БД"""
    db_path: str
    connection_factory: Callable[[], sqlite3.Connection]
    synonyms_map: dict[str, str]  # Карта синонимов формул
    cache_size: int = 1000  # LRU кэш для запросов
    retry_attempts: int = 3
    retry_delay: float = 0.1  # Экспоненциальная задержка

@dataclass
class ThermoDeps:
    """Зависимости для термодинамических расчётов"""
    T_ref: float = 298.15  # Референсная температура, K
    integration_points: int = 400  # Точность численного интегрирования
    zero_gibbs_tolerance: float = 1000.0  # Допуск для ΔG≈0, Дж/моль
    temperature_extrapolation_warning: float = 50.0  # Предупреждение при экстраполяции >50K

@dataclass
class ReactionDeps:
    """Зависимости для анализа реакций"""
    max_balancing_attempts: int = 5
    equilibrium_search_tolerance: float = 100.0  # Дж/моль
    default_T_bounds: tuple[float, float] = (298.15, 2273.15)  # 25°C - 2000°C
    common_byproducts: list[str] = None  # Частые побочные продукты
    
    def __post_init__(self):
        if self.common_byproducts is None:
            self.common_byproducts = [
                "CO(g)", "CO2(g)", "H2O(g)", "H2O(l)", 
                "HCl(g)", "Cl2(g)", "O2(g)", "N2(g)"
            ]

@dataclass
class AppDeps:
    """Общие зависимости приложения"""
    db: DBDeps
    thermo: ThermoDeps
    reactions: ReactionDeps
    model_config: ModelConfig
```

### 5.2 Переменные окружения (.env)
```bash
# OpenRouter AI
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEFAULT_MODEL=anthropic/claude-3.5-sonnet

# Database
DB_PATH=c:\IDE\repository\agents_for_david\data\thermo_data.db

# Logging & Monitoring  
LOGFIRE_TOKEN=your_logfire_token_here
LOG_LEVEL=INFO

# Development
ENVIRONMENT=development
DEBUG=false
```

### 5.3 Инъекция зависимостей в Pydantic AI
```python
from pydantic_ai import Agent, RunContext

# Создание агентов с типизированными зависимостями
orchestrator = Agent[AppDeps, UserResponse](
    model=f"openrouter:{model_config.default_model}",
    deps_type=AppDeps,
    output_type=UserResponse
)

db_resolver = Agent[DBDeps, SpeciesRecord](
    model=f"openrouter:{model_config.default_model}",
    deps_type=DBDeps, 
    output_type=SpeciesRecord
)

# Использование зависимостей в инструментах
@db_resolver.tool
async def search_compound(ctx: RunContext[DBDeps], formula: str) -> dict:
    """Поиск соединения с использованием инжектированных зависимостей"""
    conn = ctx.deps.connection_factory()
    # Нормализация формулы через synonyms_map
    normalized_formula = ctx.deps.synonyms_map.get(formula.upper(), formula)
    # ... логика поиска
```


## 6. Инфраструктура и провайдеры данных

### 6.1 SQLite провайдер (без MCP)
```python
class ThermoDBProvider:
    """Провайдер термодинамических данных на SQLite"""
    
    def __init__(self, db_path: str, cache_size: int = 1000):
        self.db_path = db_path
        self.cache = {}  # LRU кэш для часто запрашиваемых веществ
        self.synonyms = self._load_synonyms_map()
    
    async def get_compounds_by_formula(
        self, 
        formula: str, 
        phase: Optional[str] = None
    ) -> list[dict]:
        """Поиск соединений по формуле с кэшированием"""
        
    async def search_compounds_fuzzy(
        self, 
        query: str, 
        limit: int = 10
    ) -> list[dict]:
        """Нечёткий поиск по названию/формуле"""
        
    async def get_temperature_coverage(
        self, 
        formula: str, 
        target_T: float
    ) -> dict:
        """Анализ покрытия температурного диапазона"""

    def _normalize_formula(self, formula: str) -> str:
        """Нормализация формулы через карту синонимов"""
        return self.synonyms.get(formula.upper(), formula)
```

### 6.2 Кэширование и производительность  
- **LRU кэш**: 1000 записей для часто запрашиваемых веществ
- **Ретраи**: до 3 попыток с экспоненциальной задержкой при блокировках БД
- **Connection pooling**: переиспользование подключений SQLite
- **Индексы**: `(Formula, Phase)`, `(Formula, Tmin, Tmax)` для быстрого поиска

### 6.3 Карта синонимов и нормализация
```python
FORMULA_SYNONYMS = {
    # Регистр
    "ZRO2": "ZrO2", "TIO2": "TiO2", "AL2O3": "Al2O3",
    # Альтернативные записи
    "CARBON TETRACHLORIDE": "CCl4",
    "TITANIUM DIOXIDE": "TiO2", 
    "ZIRCONIUM DIOXIDE": "ZrO2",
    # Фазовые уточнения
    "ZrO2(SOLID)": "ZrO2(s)",
    "CCL4(LIQUID)": "CCl4(l)"
}
```

### 6.4 Диагностика и логирование
- **SQL Query logging**: через Pydantic Logfire
- **Cache hit/miss metrics**: мониторинг эффективности кэша
- **Temperature range warnings**: предупреждения при экстраполяции
- **Data quality indicators**: флаги качества данных в ответах


## 7. Алгоритмы и бизнес-логика

### 7.1 Выбор фазы и температурного диапазона

**Приоритеты выбора записи:**
1. Точное совпадение фазы + температура в диапазоне [Tmin, Tmax]
2. Любая фаза + температура в диапазоне  
3. Указанная фаза + ближайший диапазон
4. Стабильная фаза при заданной температуре (по термодинамическим данным)
5. Запись с наиболее широким температурным покрытием

**Алгоритм разрешения неоднозначности:**
```python
def select_best_record(records: list[SpeciesRecord], target_T: float, phase_hint: str) -> SpeciesRecord:
    # 1. Фильтр по фазе (если указана)
    if phase_hint:
        phase_filtered = [r for r in records if r.phase == phase_hint]
        if phase_filtered:
            records = phase_filtered
    
    # 2. Фильтр по температурному диапазону
    in_range = [r for r in records if r.tmin <= target_T <= r.tmax]
    if in_range:
        # Выбрать наиболее узкий диапазон
        return min(in_range, key=lambda r: r.tmax - r.tmin)
    
    # 3. Ближайший диапазон 
    return min(records, key=lambda r: min(abs(target_T - r.tmin), abs(target_T - r.tmax)))
```

### 7.2 Термодинамические расчёты

**Формула теплоёмкости** (из пользовательской БД):
```python
def calculate_cp(T: float, f1: float, f2: float, f3: float, f4: float, f5: float, f6: float) -> float:
    """Cp в Дж/(моль·К)"""
    return (f1 + f2*T/1000 + f3*T**(-2) * 100_000 + 
            f4*T**2 / 1_000_000 + f5*T**(-3) * 1_000 + 
            f6*T**3 * 10**(-9))
```

**Численное интегрирование:**
```python
from scipy.integrate import quad

def calculate_enthalpy_change(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """ΔH(T) = H298 + ∫[T_ref→T] Cp dT"""
    def cp_func(temp):
        return calculate_cp(temp, species.f1, species.f2, species.f3, 
                          species.f4, species.f5, species.f6)
    
    integral, _ = quad(cp_func, T_ref, T)
    return species.H298_kJ_per_mol * 1000 + integral  # кДж→Дж

def calculate_entropy_change(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """ΔS(T) = S298 + ∫[T_ref→T] (Cp/T) dT"""
    def cp_over_t_func(temp):
        return calculate_cp(temp, species.f1, species.f2, species.f3,
                          species.f4, species.f5, species.f6) / temp
    
    integral, _ = quad(cp_over_t_func, T_ref, T)
    return species.S298_J_per_molK + integral
```

### 7.3 Балансировка химических реакций

**Линейная система для элементов:**
```python
import numpy as np
from typing import Dict, List

def balance_reaction(reactants: List[str], products: List[str]) -> Dict[str, float]:
    """Балансировка по элементному составу"""
    # 1. Парсинг формул → элементный состав
    elements = get_all_elements(reactants + products)
    
    # 2. Составление матрицы A·x = 0
    # где x = [коэф_реагентов, коэф_продуктов]
    matrix = build_element_matrix(reactants, products, elements)
    
    # 3. Решение системы (метод наименьших квадратов)
    coefficients = solve_linear_system(matrix)
    
    # 4. Нормализация к целым числам
    return normalize_coefficients(coefficients, reactants, products)

def generate_byproduct_hypotheses(main_products: List[str], available_elements: set) -> List[List[str]]:
    """Генерация гипотез с учётом частых побочных продуктов"""
    common_byproducts = ["CO(g)", "CO2(g)", "H2O(g)", "HCl(g)", "Cl2(g)"]
    
    # Фильтр по доступным элементам
    valid_byproducts = [bp for bp in common_byproducts 
                       if get_elements(bp).issubset(available_elements)]
    
    # Генерация комбинаций
    return generate_combinations(main_products, valid_byproducts)
```

### 7.4 Поиск температуры равновесия  

**Метод бисекции для T_eq:**
```python
def find_equilibrium_temperature(
    participants: List[ReactionParticipant], 
    T_bounds: Tuple[float, float] = (298, 2273),
    tolerance: float = 100.0  # Дж/моль
) -> Optional[float]:
    """Поиск T где ΔG_reaction ≈ 0"""
    
    def delta_g_reaction(T: float) -> float:
        total_dg = 0.0
        for participant in participants:
            species_data = resolve_species(participant.formula, participant.phase, T)
            thermo_point = calculate_properties(species_data, T)
            
            if participant.role == 'product':
                total_dg += participant.coefficient * thermo_point.G
            else:  # reactant
                total_dg -= participant.coefficient * thermo_point.G
        return total_dg
    
    # Проверка смены знака в границах
    dg_low = delta_g_reaction(T_bounds[0])
    dg_high = delta_g_reaction(T_bounds[1])
    
    if dg_low * dg_high > 0:
        return None  # Нет пересечения с осью T
    
    # Бисекция
    T_low, T_high = T_bounds
    while T_high - T_low > 1.0:  # точность 1K
        T_mid = (T_low + T_high) / 2
        dg_mid = delta_g_reaction(T_mid)
        
        if abs(dg_mid) < tolerance:
            return T_mid
            
        if dg_mid * dg_low < 0:
            T_high = T_mid
        else:
            T_low = T_mid
            dg_low = dg_mid
    
    return (T_low + T_high) / 2
```


## 8. Структурированный вывод и валидация

### 8.1 Pydantic AI Output Configuration

**Режим Tool Output** (рекомендуется):
```python
from pydantic_ai import Agent, ToolOutput, ModelSettings

# Агент с типизированным выводом
orchestrator = Agent(
    model="openrouter:anthropic/claude-3.5-sonnet",
    output_type=ToolOutput(UserResponse, name="thermodynamic_analysis"),
    model_settings=ModelSettings(
        temperature=0.1,  # Низкая температура для научных расчётов
        max_tokens=4000,
        timeout=60.0
    )
)

# Output validator для дополнительной проверки
@orchestrator.output_validator
async def validate_thermo_response(ctx: RunContext[AppDeps], output: UserResponse) -> UserResponse:
    """Валидация физической корректности результатов"""
    
    if output.reaction_result:
        # Проверка энергии Гиббса
        if abs(output.reaction_result.delta_G_kJ_per_mol) > 1000:  # >1000 кДж/моль
            raise ModelRetry("Энергия Гиббса физически некорректна")
        
        # Проверка температуры равновесия
        if output.reaction_result.T_equilibrium:
            if not (200 <= output.reaction_result.T_equilibrium <= 3000):
                raise ModelRetry("Температура равновесия вне физически разумных пределов")
    
    return output
```

### 8.2 Форматирование ответа пользователю

**Структура финального ответа:**
```json
{
  "query_type": "reaction_analysis",
  "reaction_result": {
    "balanced_equation": "ZrO2(s) + CCl4(g) → ZrCl4(g) + CO2(g)",
    "delta_H_kJ_per_mol": 125.3,
    "delta_S_J_per_molK": 89.7,
    "delta_G_kJ_per_mol": -18.2,
    "feasible_at_T": true,
    "T_equilibrium": 1156.8,
    "confidence": 0.85,
    "diagnostics": {
      "species_found": ["ZrO2(s)", "CCl4(g)", "ZrCl4(g)", "CO2(g)"],
      "temperature_ranges": {
        "ZrO2(s)": "298-2000K",
        "CCl4(g)": "298-1500K"
      },
      "extrapolation_warnings": []
    }
  },
  "summary_ru": "Хлорирование диоксида циркония четырёххлористым углеродом термодинамически возможно при температурах выше 1157K (884°C). Реакция эндотермическая с ΔH = 125.3 кДж/моль.",
  "recommendations": [
    "Проводить реакцию при температуре не ниже 900°C",
    "Учесть образование токсичного угарного газа", 
    "Рекомендуется избыток CCl4 для смещения равновесия"
  ],
  "data_quality": {
    "all_species_found": true,
    "temperature_coverage": "good",
    "confidence_level": "high"
  }
}
```

### 8.3 Обработка ошибок и ретраи

**Автоматические ретраи при:**
- Ошибках валидации Pydantic моделей
- Физически некорректных значениях
- Отсутствии ключевых данных

**Usage Limits для контроля затрат:**
```python
from pydantic_ai import UsageLimits

usage_limits = UsageLimits(
    tool_calls_limit=15,  # Максимум 15 вызовов инструментов
    request_token_limit=8000,  # Лимит токенов на запрос
    response_token_limit=2000   # Лимит токенов в ответе
)

result = orchestrator.run_sync(
    user_query,
    deps=app_deps,
    usage_limits=usage_limits
)
```

### 8.4 Стриминг (опционально)

```python
async def stream_analysis(query: str) -> None:
    """Потоковый анализ с промежуточными результатами"""
    async with orchestrator.run_stream(query, deps=app_deps) as result:
        print("🔍 Анализирую запрос...")
        
        async for text in result.stream_text():
            # Промежуточные результаты для UX
            print(f"📊 {text}")
        
        # Финальный структурированный результат
        final_output = await result.output()
        return final_output
```


## 9. Наблюдаемость и мониторинг

### 9.1 Pydantic Logfire интеграция

```python
import logfire
from pydantic_ai import Agent

# Глобальная конфигурация
logfire.configure(
    service_name="thermodynamic-agents",
    environment="development"
)

# Инструментация Pydantic AI
logfire.instrument_pydantic_ai()
logfire.instrument_sqlite3()  # Для логирования SQL запросов

# Создание агентов с автоматическим логированием
orchestrator = Agent(
    "openrouter:anthropic/claude-3.5-sonnet",
    deps_type=AppDeps,
    output_type=UserResponse
)
# Все вызовы автоматически трассируются в Logfire
```

### 9.2 Метрики производительности

**Отслеживаемые метрики:**
- **Usage по моделям**: токены, запросы, стоимость на провайдера
- **Время выполнения**: общее время + breakdown по агентам
- **Cache hit ratio**: эффективность кэширования БД
- **Errors & retries**: частота ошибок валидации, ретраев
- **Data quality**: процент успешного разрешения веществ

```python
@logfire.instrument("thermodynamic_analysis")
async def analyze_reaction(query: str, deps: AppDeps) -> UserResponse:
    """Анализ реакции с метриками"""
    
    start_time = time.time()
    
    try:
        result = await orchestrator.run(query, deps=deps)
        
        # Логирование успешного результата
        logfire.info("Analysis completed", 
                    duration=time.time() - start_time,
                    tokens_used=result.usage.total_tokens,
                    confidence=result.output.reaction_result.confidence if result.output.reaction_result else None)
        
        return result.output
        
    except Exception as e:
        logfire.error("Analysis failed", error=str(e), duration=time.time() - start_time)
        raise
```

### 9.3 Message History Management

**Стратегии управления историей:**
```python
from pydantic_ai.messages import ModelMessage

async def smart_history_processor(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Умная обрезка истории с сохранением контекста"""
    
    # Сохранить последние N сообщений
    recent_limit = 10
    
    # Обязательно сохранить пары tool call/return
    essential_pairs = []
    for i, msg in enumerate(messages):
        if msg.role == "assistant" and hasattr(msg, 'tool_calls'):
            # Найти соответствующий tool return
            for j in range(i+1, min(i+3, len(messages))):
                if messages[j].role == "tool":
                    essential_pairs.extend([msg, messages[j]])
                    break
    
    # Объединить recent + essential
    recent_messages = messages[-recent_limit:]
    return list(dict.fromkeys(essential_pairs + recent_messages))  # Дедупликация

# Применение к агенту
orchestrator = Agent(
    "openrouter:anthropic/claude-3.5-sonnet",
    history_processors=[smart_history_processor]
)
```

### 9.4 Сохранение и воспроизводимость

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter
import json
from datetime import datetime

async def save_analysis_session(result: RunResult[UserResponse], query: str) -> str:
    """Сохранение сессии для воспроизводимости"""
    
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "output": result.output.model_dump(),
        "usage": result.usage.model_dump(),
        "messages": ModelMessagesTypeAdapter.dump_python(result.all_messages())
    }
    
    session_id = f"session_{int(time.time())}"
    with open(f"logs/{session_id}.json", "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    
    return session_id

async def replay_analysis_session(session_id: str) -> UserResponse:
    """Воспроизведение анализа из сохранённой сессии"""
    
    with open(f"logs/{session_id}.json", "r", encoding="utf-8") as f:
        session_data = json.load(f)
    
    # Восстановление истории сообщений
    messages = ModelMessagesTypeAdapter.validate_python(session_data["messages"])
    
    # Повторный запуск с той же историей
    result = await orchestrator.run(
        session_data["query"],
        message_history=messages[:-1],  # Исключить последний ответ
        deps=app_deps
    )
    
    return result.output
```


## 10. Тестовые сценарии (E2E)

### 10.1 Сценарий 1: Хлорирование оксида циркония

**Запрос пользователя:**
> "Возможно ли хлорирование оксида циркония четыреххлористым углеродом? При какой температуре начнется реакция?"

**Ожидаемый процесс:**
1. **Парсинг запроса**: Orchestrator определяет тип задачи - анализ реакции
2. **Резолвинг веществ**: DB Resolver находит ZrO2(s), CCl4(g/l)
3. **Генерация гипотез**: Reactions Analyzer предлагает варианты:
   - `ZrO2(s) + CCl4(g) → ZrCl4(g) + CO2(g)`
   - `ZrO2(s) + 2CCl4(g) → ZrCl4(g) + 2COCl2(g)`
   - `ZrO2(s) + CCl4(g) → ZrCl4(g) + CO(g) + 1/2O2(g)`
4. **Термодинамический анализ**: Расчёт ΔG для каждой гипотезы
5. **Поиск T_eq**: Бисекция для лучшей реакции в диапазоне 400-1500K

**Ожидаемый результат:**
```json
{
  "query_type": "reaction_analysis",
  "reaction_result": {
    "balanced_equation": "ZrO2(s) + CCl4(g) → ZrCl4(g) + CO2(g)",
    "delta_H_kJ_per_mol": 125.3,
    "delta_S_J_per_molK": 89.7, 
    "delta_G_kJ_per_mol": -18.2,
    "feasible_at_T": true,
    "T_equilibrium": 1156.8,
    "confidence": 0.85,
    "diagnostics": {
      "alternative_reactions_considered": 3,
      "best_reaction_reason": "Минимальная энергия Гиббса",
      "species_data_quality": "good"
    }
  },
  "summary_ru": "Хлорирование диоксида циркония четырёххлористым углеродом термодинамически возможно при температурах выше 1157K (884°C). Реакция эндотермическая.",
  "recommendations": [
    "Проводить реакцию при температуре не ниже 900°C",
    "Обеспечить хорошую вентиляцию из-за токсичных продуктов"
  ]
}
```

### 10.2 Сценарий 2: Хлорирование оксида титана

**Запрос пользователя:**
> "Возможна ли реакция оксида титана с хлором при 700 градусах в присутствии метана?"

**Ожидаемый процесс:**
1. **Конвертация температуры**: 700°C = 973.15K
2. **Резолвинг веществ**: TiO2(s), Cl2(g), CH4(g) 
3. **Генерация гипотез**:
   - `TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO2(g) + 2H2(g)`
   - `TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO(g) + 2HCl(g)`
   - `TiO2(s) + 4HCl(g) → TiCl4(g) + 2H2O(g)` (если CH4 дает HCl)
4. **Анализ при T=973.15K**: Расчёт ΔG для каждой реакции
5. **Оценка осуществимости**: Проверка ΔG < 0

**Ожидаемый результат:**
```json
{
  "query_type": "reaction_analysis", 
  "reaction_result": {
    "balanced_equation": "TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO2(g) + 2H2(g)",
    "delta_H_kJ_per_mol": -89.4,
    "delta_S_J_per_molK": 145.2,
    "delta_G_kJ_per_mol": -230.8,
    "feasible_at_T": true,
    "T_equilibrium": null,
    "confidence": 0.78,
    "diagnostics": {
      "evaluation_temperature": 973.15,
      "methane_role": "reducing_agent",
      "byproduct_uncertainty": "moderate"
    }
  },
  "summary_ru": "Реакция оксида титана с хлором в присутствии метана при 700°C термодинамически возможна (ΔG = -230.8 кДж/моль). Метан выступает как восстановитель.",
  "recommendations": [
    "Реакция сильно экзотермическая - контролировать температуру",
    "Возможно образование различных побочных продуктов (CO/CO2, H2/HCl)"
  ]
}
```

### 10.3 Критерии успешности тестов

**Обязательные требования:**
- [x] Корректное распознавание типа запроса
- [x] Успешное разрешение всех веществ из БД  
- [x] Физически разумные значения ΔH, ΔS, ΔG
- [x] Температура равновесия в диапазоне 200-3000K (если найдена)
- [x] Краткое резюме на русском языке
- [x] Структурированный JSON в соответствии с UserResponse схемой

**Дополнительные проверки:**
- Время выполнения < 30 секунд  
- Использование токенов < 10,000
- Количество вызовов инструментов < 15
- Confidence score > 0.7 для найденных реакций
- Диагностическая информация о качестве данных


## 11. Архитектура проекта и структура файлов

### 11.1 Рекомендуемая структура

```
agents_for_david/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # Главный агент-координатор
│   │   ├── db_resolver.py        # Резолвинг веществ из БД  
│   │   ├── thermo_calculator.py  # Термодинамические расчёты
│   │   ├── reactions_analyzer.py # Анализ реакций и балансировка
│   │   └── base.py               # Базовые классы агентов
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py             # Pydantic модели данных
│   │   ├── thermo.py             # Термодинамические функции
│   │   ├── reactions.py          # Логика реакций и балансировки
│   │   └── chemistry.py          # Химические утилиты (парсинг формул)
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── provider.py       # SQLite провайдер
│   │   │   ├── cache.py          # LRU кэширование
│   │   │   └── synonyms.py       # Карта синонимов
│   │   ├── config.py             # Конфигурация из .env
│   │   ├── logging.py            # Настройка логирования
│   │   └── openrouter.py         # OpenRouter AI клиент
│   └── shared/
│       ├── __init__.py
│       ├── exceptions.py         # Кастомные исключения
│       └── utils.py              # Общие утилиты
├── app/
│   ├── __init__.py
│   ├── main.py                   # Точка входа приложения
│   ├── dependencies.py           # DI контейнер
│   └── cli.py                    # CLI интерфейс (опционально)
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── test_db_resolver.py   # Тесты резолвинга
│   │   ├── test_thermo.py        # Тесты расчётов
│   │   ├── test_reactions.py     # Тесты реакций
│   │   └── test_chemistry.py     # Тесты химических утилит
│   ├── integration/
│   │   ├── test_agents.py        # Интеграционные тесты агентов
│   │   └── test_database.py      # Тесты работы с БД
│   ├── e2e/
│   │   └── test_scenarios.py     # End-to-end тестовые сценарии
│   └── fixtures/
│       ├── test_data.db          # Тестовая БД
│       └── mock_responses.json   # Моки ответов LLM
├── data/
│   └── thermo_data.db            # Основная термодинамическая БД
├── docs/
│   ├── tech_spec_v1.md           # Данное ТЗ
│   ├── pydantic-ai-ru.md         # Документация по Pydantic AI
│   ├── db_work.ipynb             # Анализ структуры БД
│   └── сhlorination_of_tungsten.ipynb
├── logs/                         # Логи выполнения (создается автоматически)
├── .env.example                  # Пример конфигурации
├── .env                          # Локальная конфигурация (не в git)
├── pyproject.toml                # Зависимости и настройки проекта
├── uv.lock                       # Зафиксированные версии
└── README.md                     # Документация проекта
```

### 11.2 Интеграция существующих файлов

**Миграция текущих файлов:**
```bash
# Текущий main.py -> app/main.py (с рефакторингом)
# Текущий check_db.py -> src/infrastructure/database/ (как утилита)
# Добавить зависимости в pyproject.toml
```

### 11.3 Ключевые компоненты

**app/main.py** - точка входа:
```python
from src.agents.orchestrator import create_orchestrator
from src.infrastructure.config import load_config
from app.dependencies import setup_dependencies

async def main():
    """Главная функция приложения"""
    config = load_config()
    deps = setup_dependencies(config)
    orchestrator = create_orchestrator(config.model_config)
    
    # CLI или API интерфейс
    while True:
        query = input("Введите запрос: ")
        if query.lower() in ['exit', 'quit']:
            break
            
        result = await orchestrator.run(query, deps=deps)
        print(f"Ответ: {result.output.summary_ru}")
        print(f"Детали: {result.output.model_dump_json(indent=2)}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

**app/dependencies.py** - DI контейнер:
```python
from dataclasses import dataclass
from src.infrastructure.database.provider import ThermoDBProvider
from src.infrastructure.config import Config

@dataclass
class Dependencies:
    """Контейнер зависимостей приложения"""
    db_provider: ThermoDBProvider
    config: Config

def setup_dependencies(config: Config) -> Dependencies:
    """Настройка всех зависимостей"""
    db_provider = ThermoDBProvider(
        db_path=config.db_path,
        cache_size=config.cache_size
    )
    
    return Dependencies(
        db_provider=db_provider,
        config=config
    )
```


## 12. Настройка окружения и запуск

### 12.1 Требования к системе

**Python**: >=3.12  
**Управление зависимостями**: uv  
**ОС**: Windows (основная), Linux/macOS (поддерживается)  
**Внешние сервисы**: OpenRouter AI, Pydantic Logfire (опционально)

### 12.2 Зависимости проекта (pyproject.toml)

```toml
[project]
name = "agents-for-david"
version = "0.1.0"
description = "Thermodynamic analysis agents powered by Pydantic AI"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    # Основной фреймворк
    "pydantic-ai>=0.0.14",
    "pydantic>=2.9.0",
    
    # Научные расчёты
    "numpy>=1.24.0",
    "scipy>=1.10.0",
    "pandas>=2.2.0",
    
    # База данных
    "sqlite3",  # Встроенный в Python
    
    # Конфигурация и логирование
    "pydantic-settings>=2.0.0",
    "logfire>=0.50.0",
    
    # CLI и утилиты
    "click>=8.0.0",
    "rich>=13.0.0",  # Красивый вывод в консоли
    
    # Разработка и тестирование
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-mock>=3.10.0",
]

[project.optional-dependencies]
dev = [
    "jupyter>=1.0.0",
    "matplotlib>=3.7.0",
    "ipykernel>=6.29.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
strict = true
```

### 12.3 Конфигурация (.env.example)

```bash
# OpenRouter AI Configuration
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DEFAULT_MODEL=anthropic/claude-3.5-sonnet
BACKUP_MODELS=openai/gpt-4o,google/gemini-pro-1.5

# Database Configuration  
DB_PATH=c:\IDE\repository\agents_for_david\data\thermo_data.db
CACHE_SIZE=1000
DB_RETRY_ATTEMPTS=3

# Thermodynamic Calculation Settings
T_REF=298.15
INTEGRATION_POINTS=400
ZERO_GIBBS_TOLERANCE=1000.0

# Logging and Monitoring
LOGFIRE_TOKEN=your_logfire_token_here
LOG_LEVEL=INFO
ENVIRONMENT=development

# Performance Limits
MAX_TOOL_CALLS=15
MAX_REQUEST_TOKENS=8000
MAX_RESPONSE_TOKENS=2000

# Development
DEBUG=false
SAVE_SESSIONS=true
```

### 12.4 Установка и запуск (Windows PowerShell)

**Первоначальная настройка:**
```powershell
# Клонирование и переход в директорию
cd c:\IDE\repository\agents_for_david

# Создание виртуального окружения через uv
uv venv
.\.venv\Scripts\Activate.ps1

# Установка зависимостей
uv sync

# Копирование конфигурации
cp .env.example .env
# Отредактировать .env файл с вашими API ключами
```

**Настройка переменных окружения:**
```powershell
# Установка основных переменных
$env:OPENROUTER_API_KEY = "your_actual_api_key"
$env:DB_PATH = "c:\IDE\repository\agents_for_david\data\thermo_data.db"

# Проверка доступности БД
python -c "import sqlite3; print('DB OK' if sqlite3.connect('$env:DB_PATH') else 'DB Error')"
```

**Запуск приложения:**
```powershell
# Активация окружения
.\.venv\Scripts\Activate.ps1

# Запуск основного приложения
python app/main.py

# Альтернативно - через модуль
python -m app.main

# Запуск тестов
pytest tests/ -v

# Запуск конкретного тестового сценария
pytest tests/e2e/test_scenarios.py::test_zirconia_chlorination -v
```

### 12.5 Проверка настройки

**Скрипт валидации установки:**
```python
# scripts/validate_setup.py
import os
import sqlite3
import sys
from pathlib import Path

def validate_setup():
    """Проверка корректности настройки проекта"""
    
    checks = []
    
    # Проверка переменных окружения
    required_vars = ["OPENROUTER_API_KEY", "DB_PATH"]
    for var in required_vars:
        if os.getenv(var):
            checks.append(f"✅ {var} установлена")
        else:
            checks.append(f"❌ {var} не найдена")
    
    # Проверка доступности БД
    db_path = os.getenv("DB_PATH", "data/thermo_data.db")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM compounds")
        count = cursor.fetchone()[0]
        checks.append(f"✅ БД доступна, найдено {count} соединений")
        conn.close()
    except Exception as e:
        checks.append(f"❌ Ошибка БД: {e}")
    
    # Проверка импортов
    try:
        import pydantic_ai
        checks.append(f"✅ Pydantic AI {pydantic_ai.__version__}")
    except ImportError:
        checks.append("❌ Pydantic AI не установлен")
    
    # Результат
    print("\n".join(checks))
    
    success = all("✅" in check for check in checks)
    if success:
        print("\n🎉 Настройка завершена успешно!")
    else:
        print("\n⚠️ Есть проблемы с настройкой")
        sys.exit(1)

if __name__ == "__main__":
    validate_setup()
```

```powershell
# Запуск проверки
python scripts/validate_setup.py
```


## 13. Тестирование и качество кода

### 13.1 Стратегия тестирования

**Unit тесты** - изолированное тестирование компонентов:
```python
# tests/unit/test_thermo.py
import pytest
from src.domain.thermo import calculate_cp, calculate_enthalpy_change
from src.domain.models import SpeciesRecord

class TestThermodynamicCalculations:
    """Тесты термодинамических расчётов"""
    
    def test_cp_calculation(self):
        """Тест расчёта теплоёмкости по коэффициентам"""
        # Тестовые коэффициенты
        result = calculate_cp(T=1000, f1=50, f2=10, f3=0, f4=0, f5=0, f6=0)
        expected = 50 + 10*1000/1000  # 60 Дж/(моль·К)
        assert abs(result - expected) < 0.01
    
    def test_enthalpy_integration(self):
        """Тест численного интегрирования энтальпии"""
        species = SpeciesRecord(
            formula="H2O", phase="g", tmin=298, tmax=2000,
            H298_kJ_per_mol=-241.8, S298_J_per_molK=188.8,
            f1=33.6, f2=0.0073, f3=0, f4=0, f5=0, f6=0,
            source="test"
        )
        
        result = calculate_enthalpy_change(species, T=1000)
        # Ожидаемое значение из справочных данных
        assert abs(result - (-241800 + 24000)) < 1000  # ±1 кДж/моль
```

**Integration тесты** - взаимодействие компонентов:
```python
# tests/integration/test_agents.py
import pytest
from src.agents.db_resolver import DBResolverAgent
from src.infrastructure.database.provider import ThermoDBProvider

@pytest.mark.asyncio
class TestAgentIntegration:
    """Интеграционные тесты агентов"""
    
    async def test_db_resolver_integration(self, test_db_provider):
        """Тест интеграции агента с БД провайдером"""
        agent = DBResolverAgent()
        deps = create_test_deps(db_provider=test_db_provider)
        
        result = await agent.run(
            "Найди данные для ZrO2",
            deps=deps
        )
        
        assert result.output.formula == "ZrO2"
        assert result.output.phase in ["s", "l", "g"]
        assert result.output.tmin > 0
```

**E2E тесты** - полные сценарии:
```python
# tests/e2e/test_scenarios.py
import pytest
from app.main import create_app

@pytest.mark.asyncio
class TestEndToEndScenarios:
    """End-to-end тестовые сценарии"""
    
    async def test_zirconia_chlorination_scenario(self, app_with_test_deps):
        """Сценарий 1: Хлорирование оксида циркония"""
        
        query = "Возможно ли хлорирование оксида циркония четыреххлористым углеродом? При какой температуре начнется реакция?"
        
        result = await app_with_test_deps.analyze(query)
        
        # Проверки результата
        assert result.query_type == "reaction_analysis"
        assert result.reaction_result is not None
        assert "ZrO2" in result.reaction_result.balanced_equation
        assert "CCl4" in result.reaction_result.balanced_equation
        assert result.reaction_result.T_equilibrium > 0
        assert result.reaction_result.confidence > 0.7
        assert "циркония" in result.summary_ru.lower()
    
    async def test_titania_chlorination_scenario(self, app_with_test_deps):
        """Сценарий 2: Хлорирование оксида титана"""
        
        query = "Возможна ли реакция оксида титана с хлором при 700 градусах в присутствии метана?"
        
        result = await app_with_test_deps.analyze(query)
        
        assert result.query_type == "reaction_analysis"
        assert result.reaction_result.feasible_at_T is not None
        assert "TiO2" in result.reaction_result.balanced_equation
        assert "700" in result.summary_ru or "973" in result.summary_ru
```

### 13.2 Фикстуры и моки

```python
# tests/fixtures/test_data.py
import pytest
from src.infrastructure.database.provider import ThermoDBProvider
from src.domain.models import SpeciesRecord

@pytest.fixture
def test_species_data():
    """Тестовые данные веществ"""
    return [
        SpeciesRecord(
            formula="ZrO2", phase="s", tmin=298, tmax=2000,
            H298_kJ_per_mol=-1097.5, S298_J_per_molK=50.4,
            f1=69.6, f2=7.1, f3=-8.3, f4=0, f5=0, f6=0,
            source="test_data"
        ),
        SpeciesRecord(
            formula="CCl4", phase="g", tmin=298, tmax=1500,
            H298_kJ_per_mol=-95.7, S298_J_per_molK=309.9,
            f1=83.0, f2=0.3, f3=0, f4=0, f5=0, f6=0,
            source="test_data"
        )
    ]

@pytest.fixture
def mock_openrouter_client():
    """Мок клиента OpenRouter для тестирования без реальных API вызовов"""
    from unittest.mock import AsyncMock
    
    mock = AsyncMock()
    mock.run.return_value = create_mock_response()
    return mock
```

### 13.3 Конфигурация тестов

```python
# tests/conftest.py
import pytest
import tempfile
import sqlite3
from pathlib import Path

@pytest.fixture(scope="session")
def test_database():
    """Создание временной тестовой БД"""
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Создание схемы и заполнение тестовыми данными
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE compounds (
            Formula TEXT, Phase TEXT, Tmin REAL, Tmax REAL,
            H298 REAL, S298 REAL,
            f1 REAL, f2 REAL, f3 REAL, f4 REAL, f5 REAL, f6 REAL,
            source TEXT
        )
    """)
    
    # Вставка тестовых данных
    test_compounds = [
        ("ZrO2", "s", 298, 2000, -1097.5, 50.4, 69.6, 7.1, -8.3, 0, 0, 0, "test"),
        ("CCl4", "g", 298, 1500, -95.7, 309.9, 83.0, 0.3, 0, 0, 0, 0, "test"),
        # ... другие тестовые соединения
    ]
    
    conn.executemany(
        "INSERT INTO compounds VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
        test_compounds
    )
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    Path(db_path).unlink()

@pytest.fixture
def app_with_test_deps(test_database):
    """Приложение с тестовыми зависимостями"""
    from app.dependencies import setup_test_dependencies
    return setup_test_dependencies(db_path=test_database)
```

### 13.4 Автоматизация качества кода

```bash
# .github/workflows/test.yml (для CI/CD)
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: windows-latest
    steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v1
    - run: uv sync
    - run: uv run pytest tests/ --cov=src/ --cov-report=xml
    - run: uv run mypy src/
    - run: uv run ruff check src/
```

**Локальные скрипты проверки:**
```powershell
# scripts/quality_check.ps1
Write-Host "Запуск проверок качества кода..."

# Тесты
Write-Host "🧪 Запуск тестов..."
uv run pytest tests/ -v --cov=src/ --cov-report=term-missing

# Типизация  
Write-Host "🔍 Проверка типов..."
uv run mypy src/

# Линтер
Write-Host "✨ Проверка стиля кода..."
uv run ruff check src/

# Форматирование
Write-Host "🎨 Проверка форматирования..."
uv run black --check src/

Write-Host "✅ Все проверки завершены"
```


## 14. Управление рисками и план миграции

### 14.1 Технические риски

**Риск: Неполные данные в БД**
- **Проявление**: Отсутствие веществ или неточные коэффициенты Cp
- **Митигация**: 
  - Валидация качества данных при загрузке
  - Предложение альтернативных веществ при поиске
  - Явные предупреждения о качестве данных в ответах
- **Индикаторы**: Процент успешного разрешения < 80%

**Риск: Высокие затраты на токены OpenRouter**
- **Проявление**: Превышение бюджета LLM API
- **Митигация**:
  - Usage limits на агентах (tool_calls_limit=15)
  - История сообщений с умной обрезкой  
  - Кэширование часто запрашиваемых расчётов
  - Fallback модели (дешёвые варианты для простых задач)
- **Мониторинг**: Трекинг затрат через Logfire

**Риск: Ошибки численного интегрирования**
- **Проявление**: Неточные результаты ΔH, ΔS при экстраполяции
- **Митигация**:
  - Флаги `in_range` для температурных диапазонов
  - Предупреждения при экстраполяции >50K
  - Валидация физической разумности результатов
- **Контроль**: Сравнение с эталонными данными в тестах

### 14.2 Эксплуатационные риски

**Риск: Некорректная интерпретация запросов**
- **Проявление**: Неправильное распознавание типа задачи
- **Митигация**:
  - Детальные инструкции агентам на русском языке
  - Confirmation loops для неоднозначных запросов
  - Валидация выходных схем Pydantic
- **Метрики**: Confidence score < 0.7 в результатах

**Риск: Блокировки SQLite при concurrent доступе**
- **Проявление**: SQLite locked errors при параллельных запросах  
- **Митигация**:
  - Connection pooling с retry логикой
  - WAL mode для SQLite
  - Асинхронные операции с тайм-аутами
- **Мониторинг**: Логирование ошибок БД

### 14.3 План миграции

**Этап 1: Базовая реализация (4-6 недель)**
```
Неделя 1-2: Инфраструктура
├── Настройка проекта (uv, структура)
├── SQLite провайдер с базовым кэшированием
├── Конфигурация OpenRouter + Logfire
└── Pydantic модели данных

Неделя 3-4: Агенты
├── DB Resolver Agent (поиск веществ)
├── Thermo Calculator Agent (Cp, H, S, G)
├── Reactions Analyzer Agent (балансировка)
└── Orchestrator Agent (координация)

Неделя 5-6: Интеграция и тестирование
├── E2E тесты для основных сценариев
├── CLI интерфейс для тестирования
├── Базовое логирование и мониторинг
└── Документация и примеры
```

**Этап 2: Улучшения (2-3 недели)**
```
├── Расширенная балансировка с гипотезами побочных продуктов
├── Поиск температуры равновесия (бисекция)
├── Интеллектуальный кэш с LRU eviction
├── Обработка фазовых переходов
└── Улучшенная диагностика и предупреждения
```

**Этап 3: Производственная готовность (1-2 недели)**
```
├── Comprehensive тестирование и нагрузочные тесты
├── Профилирование производительности
├── API интерфейс (FastAPI) для интеграций
├── Docker контейнеризация
└── CI/CD пайплайны
```

### 14.4 План отката

**Сценарий: Критические проблемы с Pydantic AI**
- **Fallback**: Прямое использование OpenRouter HTTP API
- **Время**: 2-3 дня на переписывание агентов
- **Сохранение**: Pydantic модели остаются, логика - переносится

**Сценарий: Проблемы с OpenRouter**
- **Fallback**: Переключение на прямые API OpenAI/Anthropic
- **Время**: 1 день на изменение конфигурации
- **Изменения**: Только провайдер модели, архитектура остается

**Сценарий: Производительность SQLite**
- **Fallback**: Миграция на PostgreSQL с сохранением схемы
- **Время**: 3-5 дней на адаптацию провайдера
- **Преимущества**: Лучшая concurrent поддержка

### 14.5 Метрики успеха

**Функциональные метрики:**
- Успешность разрешения веществ: >85%
- Точность термодинамических расчётов: <5% отклонение от эталонов
- Время ответа на запрос: <30 секунд
- Confidence score финальных ответов: >0.7

**Технические метрики:**
- Покрытие тестами: >80%
- Средняя стоимость запроса: <$0.10
- Доступность системы: >99%
- Время до первого байта: <5 секунд

**Пользовательские метрики:**
- Релевантность ответов экспертной оценкой: >4/5
- Полнота диагностической информации: >4/5  
- Понятность резюме на русском языке: >4/5


## 15. Roadmap и будущие расширения

### 15.1 Краткосрочные цели (следующие 2-3 месяца)

**Версия 1.0 - Базовая функциональность**
- ✅ Архитектура на Pydantic AI
- ✅ OpenRouter интеграция
- ✅ SQLite термодинамическая БД
- ✅ Основные агенты (DB, Thermo, Reactions, Orchestrator)
- ✅ E2E тесты для тестовых сценариев
- ✅ CLI интерфейс

**Версия 1.1 - Улучшения качества**
- 🔄 Расширенная балансировка с побочными продуктами
- 🔄 Поиск температуры равновесия
- 🔄 Интеллектуальное кэширование
- 🔄 Улучшенная диагностика ошибок
- 🔄 Обработка фазовых переходов

### 15.2 Среднесрочные цели (6-12 месяцев)

**Версия 2.0 - Расширенная химия**
- 🔮 Поддержка многокомпонентных систем
- 🔮 Расчёт активностей и коэффициентов активности
- 🔮 Анализ кинетики реакций (базовый)
- 🔮 Диаграммы состояния и фазовые равновесия
- 🔮 Интеграция с внешними химическими БД (PubChem, NIST)

**API и интеграции**
- 🔮 REST API на FastAPI для внешних приложений
- 🔮 Веб-интерфейс для интерактивного анализа
- 🔮 Интеграция с Jupyter Notebook (магические команды)
- 🔮 Экспорт результатов в форматы (Excel, PDF, LaTeX)

### 15.3 Долгосрочные цели (1-2 года)

**Версия 3.0 - Интеллектуальная платформа**
- 🌟 Мультимодальные агенты (текст + диаграммы + графики)
- 🌟 Планирование экспериментов на основе термодинамики
- 🌟 Обучение на пользовательских данных (fine-tuning)
- 🌟 Интеграция с системами управления лабораториями (LIMS)
- 🌟 Предиктивная аналитика процессов

**Масштабирование**
- 🌟 Миграция на PostgreSQL/ClickHouse для больших БД
- 🌟 Микросервисная архитектура
- 🌟 Kubernetes deployment
- 🌟 Распределённые вычисления для комплексных расчётов

### 15.4 Исследовательские направления

**Улучшение качества моделей**
- Сравнительный анализ различных LLM для научных задач
- Специализированное промпт-инжиниринг для химии
- RAG (Retrieval Augmented Generation) с научной литературой
- Валидация против экспериментальных данных

**Новые возможности**
- Анализ неопределённости в термодинамических данных
- Оптимизация химических процессов через RL-агентов
- Автоматическое составление технологических карт
- Интеграция с quantum chemistry расчётами (DFT)

### 15.5 Технологический стек будущего

**Рассматриваемые технологии:**
```
Machine Learning:
├── LangChain/LlamaIndex для RAG
├── Weights & Biases для ML ops
├── Hugging Face для специализированных моделей
└── MLflow для управления моделями

Data & Computing:
├── Apache Arrow для больших dataset
├── Dask для параллельных вычислений  
├── Redis для высокопроизводительного кэширования
└── TimescaleDB для временных рядов экспериментов

Visualization:
├── Plotly Dash для интерактивных дашбордов
├── Streamlit для быстрого прототипирования
├── D3.js для кастомных визуализаций
└── Matplotlib/Seaborn для статических графиков
```

**Интеграции:**
- **LabView/MATLAB**: Экспорт расчётов в инженерные среды
- **ChemCAD/Aspen**: Интеграция с процессными симуляторами  
- **Materials Project**: Доступ к вычислительным материаловедческим данным
- **NIST WebBook**: Автоматическая синхронизация справочных данных

### 15.6 Критерии принятия решений

**Добавление новых функций:**
1. **Научная ценность**: Улучшает ли качество термодинамического анализа?
2. **Пользовательский запрос**: Есть ли реальная потребность?
3. **Техническая сложность**: Соотношение усилий и пользы
4. **Совместимость**: Вписывается ли в текущую архитектуру?

**Технологические решения:**
1. **Зрелость**: Стабильные, проверенные решения
2. **Сообщество**: Активная поддержка и развитие
3. **Производительность**: Соответствие требованиям масштабирования
4. **Лицензирование**: Совместимость с open-source подходом

---

**Заключение**: Проект нацелен на создание интеллектуальной платформы для термодинамического анализа химических процессов, с фокусом на качество результатов, пользовательский опыт и научную достоверность. Поэтапная реализация позволит валидировать подходы и адаптироваться к пользовательским потребностям.


## 16. Примеры кода и реализации

### 16.1 Пример агента DB Resolver

```python
# src/agents/db_resolver.py
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from dataclasses import dataclass

@dataclass
class DBDeps:
    db_path: str
    synonyms_map: dict[str, str]
    cache: dict[str, any]

class SpeciesSearchResult(BaseModel):
    """Результат поиска вещества"""
    formula: str
    phase: str
    tmin: float
    tmax: float
    confidence: float
    alternatives: List[str] = []

# Создание агента
db_resolver = Agent[DBDeps, SpeciesSearchResult](
    model="openrouter:anthropic/claude-3.5-sonnet",
    deps_type=DBDeps,
    output_type=SpeciesSearchResult,
    instructions="""
    Ты специалист по поиску химических веществ в термодинамической базе данных.
    
    Твоя задача:
    1. Найти точное соответствие формулы в БД
    2. Учесть синонимы и альтернативные записи
    3. Выбрать оптимальную запись по температурному диапазону
    4. Предложить альтернативы при неточном совпадении
    
    При поиске:
    - Нормализуй регистр формул (ZrO2, TiO2)
    - Учитывай фазовые состояния (s, l, g, aq)
    - Приоритизируй записи с подходящим температурным диапазоном
    """,
    model_settings={"temperature": 0.1}  # Низкая температура для точности
)

@db_resolver.tool
async def search_compound_exact(
    ctx: RunContext[DBDeps], 
    formula: str, 
    phase_hint: Optional[str] = None
) -> dict:
    """Точный поиск соединения по формуле"""
    
    # Нормализация формулы
    normalized_formula = ctx.deps.synonyms_map.get(formula.upper(), formula)
    
    # Проверка кэша
    cache_key = f"{normalized_formula}_{phase_hint}"
    if cache_key in ctx.deps.cache:
        return ctx.deps.cache[cache_key]
    
    # Поиск в БД
    conn = sqlite3.connect(ctx.deps.db_path)
    
    if phase_hint:
        query = "SELECT * FROM compounds WHERE Formula = ? AND Phase = ?"
        params = (normalized_formula, phase_hint)
    else:
        query = "SELECT * FROM compounds WHERE Formula = ?"
        params = (normalized_formula,)
    
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    
    conn.close()
    
    if not rows:
        return {"found": False, "formula": formula}
    
    # Конвертация в словари
    results = [dict(zip(columns, row)) for row in rows]
    
    # Кэширование
    ctx.deps.cache[cache_key] = {"found": True, "records": results}
    
    return {"found": True, "records": results}

@db_resolver.tool 
async def search_compound_fuzzy(
    ctx: RunContext[DBDeps],
    query: str,
    limit: int = 5
) -> dict:
    """Нечёткий поиск соединений"""
    
    conn = sqlite3.connect(ctx.deps.db_path)
    
    # LIKE поиск по формуле
    sql = """
    SELECT Formula, Phase, Tmin, Tmax, 
           CASE 
               WHEN Formula = ? THEN 1.0
               WHEN Formula LIKE ? THEN 0.8
               WHEN UPPER(Formula) LIKE UPPER(?) THEN 0.6
               ELSE 0.4
           END as similarity
    FROM compounds 
    WHERE Formula LIKE ? OR UPPER(Formula) LIKE UPPER(?)
    ORDER BY similarity DESC, Formula
    LIMIT ?
    """
    
    like_pattern = f"%{query}%"
    cursor = conn.execute(sql, (query, like_pattern, like_pattern, 
                              like_pattern, like_pattern, limit))
    
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    results = [dict(zip(columns, row)) for row in rows]
    
    conn.close()
    
    return {"results": results}
```

### 16.2 Пример термодинамических расчётов

```python
# src/domain/thermo.py
import numpy as np
from scipy.integrate import quad
from typing import Tuple
from .models import SpeciesRecord, ThermoPoint

def calculate_cp(T: float, f1: float, f2: float, f3: float, 
                f4: float, f5: float, f6: float) -> float:
    """
    Расчёт теплоёмкости по пользовательской формуле
    Cp = f1 + f2*T/1000 + f3*T^(-2)*100000 + f4*T^2/1000000 + f5*T^(-3)*1000 + f6*T^3*10^(-9)
    """
    return (f1 + f2*T/1000 + f3*T**(-2) * 100_000 + 
            f4*T**2 / 1_000_000 + f5*T**(-3) * 1_000 + 
            f6*T**3 * 10**(-9))

def integrate_enthalpy(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """Интегрирование энтальпии: H(T) = H298 + ∫[T_ref→T] Cp dT"""
    
    def cp_func(temp):
        return calculate_cp(temp, species.f1, species.f2, species.f3,
                          species.f4, species.f5, species.f6)
    
    if abs(T - T_ref) < 0.1:
        return species.H298_kJ_per_mol * 1000  # кДж → Дж
    
    integral, error = quad(cp_func, T_ref, T)
    
    # Проверка точности интегрирования
    if error > abs(integral) * 0.01:  # 1% относительная ошибка
        raise ValueError(f"Интегрирование неточное: ошибка {error:.2f}")
    
    return species.H298_kJ_per_mol * 1000 + integral

def integrate_entropy(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """Интегрирование энтропии: S(T) = S298 + ∫[T_ref→T] Cp/T dT"""
    
    def cp_over_t_func(temp):
        cp = calculate_cp(temp, species.f1, species.f2, species.f3,
                         species.f4, species.f5, species.f6)
        return cp / temp
    
    if abs(T - T_ref) < 0.1:
        return species.S298_J_per_molK
    
    integral, error = quad(cp_over_t_func, T_ref, T)
    
    return species.S298_J_per_molK + integral

def calculate_thermodynamic_properties(
    species: SpeciesRecord, 
    T: float
) -> ThermoPoint:
    """Полный расчёт термодинамических свойств при температуре T"""
    
    # Проверка диапазона
    in_range = species.tmin <= T <= species.tmax
    
    # Расчёт Cp
    Cp = calculate_cp(T, species.f1, species.f2, species.f3,
                     species.f4, species.f5, species.f6)
    
    # Интегрирование H и S
    H = integrate_enthalpy(species, T)
    S = integrate_entropy(species, T)
    
    # Энергия Гиббса
    G = H - T * S
    
    return ThermoPoint(
        T=T, Cp=Cp, H=H, S=S, G=G, in_range=in_range
    )

def validate_thermodynamic_result(result: ThermoPoint) -> bool:
    """Валидация физической корректности результата"""
    
    # Проверки физических ограничений
    if result.Cp < 0:
        return False, "Отрицательная теплоёмкость"
    
    if result.Cp > 1000:  # Дж/(моль·К)
        return False, "Слишком высокая теплоёмкость"
    
    if abs(result.G) > 2e6:  # >2 МДж/моль
        return False, "Энергия Гиббса вне разумных пределов"
    
    return True, "OK"
```

### 16.3 Пример Orchestrator Agent

```python
# src/agents/orchestrator.py
from pydantic_ai import Agent, RunContext, ModelRetry
from pydantic import BaseModel
from typing import Literal, Optional
from dataclasses import dataclass
import re

@dataclass
class AppDeps:
    db_resolver: Agent
    thermo_calculator: Agent  
    reactions_analyzer: Agent
    config: dict

class QueryAnalysis(BaseModel):
    """Анализ пользовательского запроса"""
    query_type: Literal['reaction_analysis', 'substance_properties', 'unknown']
    substances_mentioned: list[str]
    temperature_mentioned: Optional[float] = None
    key_phrases: list[str]
    confidence: float

class UserResponse(BaseModel):
    """Финальный ответ пользователю"""
    query_type: Literal['reaction_analysis', 'substance_properties']
    reaction_result: Optional[dict] = None
    substance_properties: Optional[list[dict]] = None
    summary_ru: str
    recommendations: list[str]
    data_quality: dict

# Главный агент-оркестратор
orchestrator = Agent[AppDeps, UserResponse](
    model="openrouter:anthropic/claude-3.5-sonnet",
    deps_type=AppDeps,
    output_type=UserResponse,
    instructions="""
    Ты главный координатор системы термодинамического анализа.
    
    Твоя задача:
    1. Проанализировать запрос пользователя на русском языке
    2. Определить тип задачи (анализ реакции vs свойства вещества)
    3. Координировать работу специализированных агентов
    4. Составить итоговый ответ с кратким резюме на русском
    
    Типы запросов:
    - "Возможна ли реакция..." → reaction_analysis
    - "При какой температуре..." → reaction_analysis  
    - "Рассчитай свойства..." → substance_properties
    
    Всегда предоставляй:
    - Структурированные данные
    - Краткое резюме на русском языке
    - Практические рекомендации
    - Информацию о качестве данных
    """,
    model_settings={"temperature": 0.2}
)

@orchestrator.tool
async def analyze_user_query(
    ctx: RunContext[AppDeps],
    query: str
) -> QueryAnalysis:
    """Анализ запроса пользователя"""
    
    query_lower = query.lower()
    
    # Определение типа запроса
    reaction_indicators = [
        "возможна ли реакция", "возможно ли", "может ли", 
        "реагировать", "взаимодействие", "при какой температуре",
        "хлорирование", "окисление", "восстановление"
    ]
    
    property_indicators = [
        "рассчитай", "свойства", "теплоёмкость", "энтальпия",
        "энтропия", "энергия гиббса", "температурная зависимость"
    ]
    
    query_type = "unknown"
    if any(indicator in query_lower for indicator in reaction_indicators):
        query_type = "reaction_analysis"
    elif any(indicator in query_lower for indicator in property_indicators):
        query_type = "substance_properties"
    
    # Извлечение веществ
    chemical_patterns = [
        r'\b[A-Z][a-z]?[0-9]*[A-Z]*[a-z]*[0-9]*\b',  # Химические формулы
        r'оксид\s+\w+', r'хлорид\s+\w+', r'диоксид\s+\w+'  # Названия
    ]
    
    substances = []
    for pattern in chemical_patterns:
        substances.extend(re.findall(pattern, query))
    
    # Извлечение температуры
    temp_match = re.search(r'(\d+)\s*(?:градус|°|k|кельвин)', query_lower)
    temperature = None
    if temp_match:
        temp_value = float(temp_match.group(1))
        # Конвертация Цельсия в Кельвины если нужно
        if temp_value < 500:  # Вероятно Цельсии
            temperature = temp_value + 273.15
        else:
            temperature = temp_value
    
    return QueryAnalysis(
        query_type=query_type,
        substances_mentioned=substances,
        temperature_mentioned=temperature,
        key_phrases=[phrase for phrase in reaction_indicators + property_indicators 
                    if phrase in query_lower],
        confidence=0.8 if query_type != "unknown" else 0.3
    )

@orchestrator.tool
async def delegate_to_reaction_analysis(
    ctx: RunContext[AppDeps],
    substances: list[str],
    temperature: Optional[float] = None
) -> dict:
    """Делегирование анализа реакции специализированным агентам"""
    
    # 1. Резолвинг веществ через DB агента
    resolved_species = []
    for substance in substances:
        result = await ctx.deps.db_resolver.run(
            f"Найди данные для {substance}",
            deps={"db_path": ctx.deps.config["db_path"]}
        )
        if result.output:
            resolved_species.append(result.output)
    
    if len(resolved_species) < 2:
        raise ModelRetry(f"Недостаточно данных о веществах: найдено {len(resolved_species)} из {len(substances)}")
    
    # 2. Анализ реакции через Reactions агента
    reaction_result = await ctx.deps.reactions_analyzer.run(
        f"Проанализируй возможность реакции между {', '.join(substances)} при температуре {temperature}K",
        deps={"species": resolved_species, "target_temperature": temperature}
    )
    
    return {
        "resolved_species": resolved_species,
        "reaction_analysis": reaction_result.output,
        "data_quality": {"species_found": len(resolved_species), "total_requested": len(substances)}
    }

@orchestrator.output_validator
async def validate_final_response(
    ctx: RunContext[AppDeps], 
    output: UserResponse
) -> UserResponse:
    """Валидация финального ответа"""
    
    # Проверка полноты ответа
    if not output.summary_ru:
        raise ModelRetry("Отсутствует резюме на русском языке")
    
    if len(output.summary_ru) < 50:
        raise ModelRetry("Резюме слишком короткое")
    
    # Проверка результатов реакции
    if output.query_type == "reaction_analysis" and not output.reaction_result:
        raise ModelRetry("Отсутствуют результаты анализа реакции")
    
    # Проверка физической разумности
    if output.reaction_result and output.reaction_result.get("delta_G_kJ_per_mol"):
        dG = abs(output.reaction_result["delta_G_kJ_per_mol"])
        if dG > 1000:  # >1000 кДж/моль
            raise ModelRetry(f"Энергия Гиббса {dG} кДж/моль физически некорректна")
    
    return output
```

---

Эти примеры демонстрируют:
- **Типобезопасность** через Pydantic модели и `Agent[Deps, Output]`
- **Инструменты** с доступом к зависимостям через `RunContext`
- **Валидацию** на разных уровнях (входные данные, физическая корректность)
- **Интеграцию** между агентами через делегирование задач
- **Обработку ошибок** через `ModelRetry` для автоматических ретраев

---

## Заключение

Данное техническое задание определяет архитектуру системы термодинамического анализа на базе Pydantic AI с использованием OpenRouter в качестве провайдера LLM моделей. 

**Ключевые особенности проекта:**

✅ **Типобезопасность** — полная типизация через Pydantic модели и `Agent[Deps, Output]`  
✅ **Гибкость моделей** — OpenRouter обеспечивает доступ к multiple LLM провайдерам  
✅ **Научная точность** — специализированные формулы расчёта Cp и валидация результатов  
✅ **Русскоязычный интерфейс** — запросы и ответы на русском языке  
✅ **Локальная БД** — никаких внешних зависимостей для термодинамических данных  
✅ **Наблюдаемость** — интеграция с Pydantic Logfire для трассировки и мониторинга  

**Готовность к реализации:** Техническое задание детализирует все аспекты от архитектуры до конкретных формул, тестовых сценариев и примеров кода. Определены чёткие критерии успеха и план поэтапной разработки.

**Следующие шаги:**
1. Настройка проектной структуры и зависимостей (uv, pyproject.toml)
2. Реализация базовой инфраструктуры (SQLite провайдер, конфигурация)  
3. Разработка агентов в порядке: DB Resolver → Thermo Calculator → Reactions Analyzer → Orchestrator
4. E2E тестирование на целевых сценариях хлорирования оксидов

Проект готов к началу разработки. 🚀
