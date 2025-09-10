# Этап 2: Конфигурация и инфраструктура

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
