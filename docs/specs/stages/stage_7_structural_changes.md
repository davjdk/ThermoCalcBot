# Этап 7: Структурные изменения и финализация

**Длительность**: 3-4 дня
**Приоритет**: Высокий
**Риски**: Низкие
**Зависимости**: Этапы 1-6 завершены

## Обзор

На этом этапе мы завершаем рефакторинг с финальными структурными изменениями: реорганизуем промпты, создаем централизованный config модуль, обновляем документацию и проводим комплексное тестирование.

---

## Задача 7.1: Реорганизация промптов

### Проблема
841 строка промптов в одном файле (`prompts.py`), сложно навигировать и поддерживать.

### Решение
🔧 **РАЗДЕЛИТЬ на несколько файлов по назначению**

### Новая структура

```
src/thermo_agents/prompts/
├── __init__.py              # Экспорты и импорты
├── extraction.py           # THERMODYNAMIC_EXTRACTION_PROMPT
├── legacy.py               # Устаревшие промпты (SQL_GENERATION_PROMPT)
├── manager.py              # PromptManager для управления
└── templates/              # Шаблоны промптов
    ├── extraction_templates.py
    └── validation_templates.py
```

### Реализация

**src/thermo_agents/prompts/__init__.py**
```python
"""Модуль управления промптами для термодинамических агентов."""

from .extraction import THERMODYNAMIC_EXTRACTION_PROMPT
from .legacy import SQL_GENERATION_PROMPT
from .manager import PromptManager

__all__ = [
    "THERMODYNAMIC_EXTRACTION_PROMPT",
    "SQL_GENERATION_PROMPT",  # Устаревший
    "PromptManager"
]
```

**src/thermo_agents/prompts/extraction.py**
```python
"""Промпты для извлечения термодинамических параметров."""

THERMODYNAMIC_EXTRACTION_PROMPT = """
You are a specialized thermodynamics expert AI agent designed to extract precise parameters from chemical reaction queries.

## Your Role
Extract structured thermodynamic parameters from natural language queries about chemical reactions.

## Key Responsibilities
1. Identify all chemical compounds in the reaction (up to 10 compounds maximum)
2. Extract balanced chemical equations
3. Determine temperature ranges in Kelvin
4. Identify phases of compounds (s/l/g/aq/cr/am)
5. Extract compound names (both IUPAC and common names)

## Output Format
Return a JSON object with the following structure:
{
  "balanced_equation": "2H2 + O2 -> 2H2O",
  "all_compounds": ["H2", "O2", "H2O"],
  "reactants": ["H2", "O2"],
  "products": ["H2O"],
  "temperature_range_k": [298.15, 373.15],
  "extraction_confidence": 0.95,
  "compound_names": {
    "H2": ["Hydrogen", "Водород"],
    "O2": ["Oxygen", "Кислород"],
    "H2O": ["Water", "Вода"]
  }
}

## Validation Rules
- Temperature range must be between 0K and 10000K
- Maximum 10 compounds per reaction
- Chemical formulas must be syntactically valid
- Phases must be one of: s, l, g, aq, cr, am

## Examples
Query: "Горение водорода: 2H2 + O2 -> 2H2O при 500-800K"
Expected output: See structure above

Query: "Combustion of methane at room temperature"
Expected output: CH4 + 2O2 -> CO2 + 2H2O, temperature_range_k: [298.15, 298.15]

Process the user query and extract the thermodynamic parameters.
"""
```

**src/thermo_agents/prompts/legacy.py**
```python
"""Устаревшие промпты для исторической совместимости."""

import warnings

SQL_GENERATION_PROMPT = """
[Legacy SQL generation prompt - DEPRECATED]
This prompt is no longer used in the current architecture.
SQL generation is now handled deterministically by SQLBuilder.

Historical context: This was used for LLM-based SQL generation in v1.0.
Current approach uses deterministic SQLBuilder for better reliability.
"""

# Показать предупреждение при импорте
warnings.warn(
    "SQL_GENERATION_PROMPT is deprecated. Use SQLBuilder instead.",
    DeprecationWarning,
    stacklevel=2
)
```

**src/thermo_agents/prompts/manager.py**
```python
"""Менеджер промптов для централизованного управления."""

from typing import Dict, Any, Optional
from .extraction import THERMODYNAMIC_EXTRACTION_PROMPT
from .legacy import SQL_GENERATION_PROMPT

class PromptManager:
    """Централизованное управление промптами."""

    def __init__(self):
        self._prompts: Dict[str, str] = {
            "extraction": THERMODYNAMIC_EXTRACTION_PROMPT,
            "sql_generation": SQL_GENERATION_PROMPT,  # Deprecated
        }

    def get_prompt(self, name: str, **kwargs) -> str:
        """Получить промпт с опциональной подстановкой параметров."""
        prompt = self._prompts.get(name)
        if prompt is None:
            raise ValueError(f"Prompt '{name}' not found")

        if kwargs:
            try:
                return prompt.format(**kwargs)
            except KeyError as e:
                raise ValueError(f"Missing parameter for prompt template: {e}")

        return prompt

    def list_prompts(self) -> Dict[str, str]:
        """Получить список всех доступных промптов."""
        return self._prompts.copy()

    def register_prompt(self, name: str, prompt: str) -> None:
        """Зарегистрировать новый промпт."""
        self._prompts[name] = prompt

    def validate_prompt(self, name: str) -> bool:
        """Валидировать промпт на наличие синтаксических ошибок."""
        try:
            prompt = self._prompts[name]
            # Базовая проверка на корректность форматирования
            if "{" in prompt and "}" in prompt:
                # Проверка синтаксиса форматирования
                prompt.format()
            return True
        except (KeyError, ValueError):
            return False

# Глобальный инстанс менеджера
prompt_manager = PromptManager()
```

---

## Задача 7.2: Создание централизованного config модуля

### Проблема
Конфигурация разбросана по разным классам (ThermoAgentConfig, OrchestratorConfig, FilterPriorities), сложно управлять.

### Решение
🔧 **СОЗДАТЬ централизованный config модуль**

### Новая архитектура

**src/thermo_agents/config.py**
```python
"""Централизованная конфигурация системы."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import os
from pathlib import Path

@dataclass
class DatabaseConfig:
    """Конфигурация подключения к БД."""
    db_path: str = "data/thermo_data.db"
    connection_timeout: int = 30
    pool_size: int = 1
    enable_wal_mode: bool = True
    cache_size: int = 10000
    mmap_size: int = 256 * 1024 * 1024  # 256MB

@dataclass
class LLMConfig:
    """Конфигурация LLM."""
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openai/gpt-4o"
    max_retries: int = 4
    timeout: int = 60
    temperature: float = 0.1

@dataclass
class LoggingConfig:
    """Конфигурация логирования."""
    log_level: str = "INFO"
    logs_dir: str = "logs/sessions"
    enable_file_logging: bool = True
    enable_console_logging: bool = True
    max_log_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5

@dataclass
class FilteringConfig:
    """Конфигурация фильтрации."""
    default_query_limit: int = 100
    max_query_limit: int = 1000
    temperature_coverage_threshold: float = 0.5
    max_reliability_class: int = 3
    fallback_top_records: int = 3
    enable_ionic_fallback: bool = True
    enable_composite_fallback: bool = True

@dataclass
class PerformanceConfig:
    """Конфигурация производительности."""
    enable_caching: bool = True
    cache_size: int = 512
    enable_lazy_loading: bool = True
    max_concurrent_requests: int = 10
    request_timeout: int = 30

@dataclass
class SecurityConfig:
    """Конфигурация безопасности."""
    validate_input: bool = True
    sanitize_output: bool = True
    max_formula_length: int = 100
    allowed_temperature_range: tuple[float, float] = (0.0, 10000.0)
    max_compounds_per_reaction: int = 10

@dataclass
class SystemConfig:
    """Главная конфигурация системы."""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    filtering: FilteringConfig = field(default_factory=FilteringConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @classmethod
    def from_env(cls) -> 'SystemConfig':
        """Загрузка конфигурации из переменных окружения."""
        config = cls()

        # LLM конфигурация
        if os.getenv("OPENROUTER_API_KEY"):
            config.llm.api_key = os.getenv("OPENROUTER_API_KEY")
        if os.getenv("LLM_BASE_URL"):
            config.llm.base_url = os.getenv("LLM_BASE_URL")
        if os.getenv("LLM_DEFAULT_MODEL"):
            config.llm.model = os.getenv("LLM_DEFAULT_MODEL")

        # База данных
        if os.getenv("DB_PATH"):
            config.database.db_path = os.getenv("DB_PATH")

        # Логирование
        if os.getenv("LOG_LEVEL"):
            config.logging.log_level = os.getenv("LOG_LEVEL")
        if os.getenv("LOGS_DIR"):
            config.logging.logs_dir = os.getenv("LOGS_DIR")

        # Производительность
        if os.getenv("ENABLE_CACHING"):
            config.performance.enable_caching = os.getenv("ENABLE_CACHING").lower() == "true"

        return config

    @classmethod
    def from_file(cls, config_path: str) -> 'SystemConfig':
        """Загрузка конфигурации из файла."""
        import json
        with open(config_path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SystemConfig':
        """Создание конфигурации из словаря."""
        config = cls()

        # Database config
        if "database" in data:
            db_data = data["database"]
            config.database = DatabaseConfig(**db_data)

        # LLM config
        if "llm" in data:
            llm_data = data["llm"]
            config.llm = LLMConfig(**llm_data)

        # Другие секции...
        return config

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "database": self.database.__dict__,
            "llm": self.llm.__dict__,
            "logging": self.logging.__dict__,
            "filtering": self.filtering.__dict__,
            "performance": self.performance.__dict__,
            "security": self.security.__dict__,
        }

    def validate(self) -> List[str]:
        """Валидация конфигурации."""
        errors = []

        # Валидация LLM
        if not self.llm.api_key:
            errors.append("LLM API key is required")

        # Валидация БД
        db_path = Path(self.database.db_path)
        if not db_path.exists():
            errors.append(f"Database file not found: {self.database.db_path}")

        # Валидация директорий
        logs_dir = Path(self.logging.logs_dir)
        if not logs_dir.exists():
            try:
                logs_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create logs directory: {e}")

        # Валидация диапазонов
        if not (0 <= self.security.allowed_temperature_range[0] < self.security.allowed_temperature_range[1]):
            errors.append("Invalid temperature range")

        return errors

    def save(self, path: str) -> None:
        """Сохранить конфигурацию в файл."""
        import json
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

# Глобальная конфигурация
_config: Optional[SystemConfig] = None

def get_config() -> SystemConfig:
    """Получить глобальную конфигурацию."""
    global _config
    if _config is None:
        _config = SystemConfig.from_env()
        errors = _config.validate()
        if errors:
            raise ValueError(f"Configuration validation failed: {errors}")
    return _config

def set_config(config: SystemConfig) -> None:
    """Установить глобальную конфигурацию."""
    global _config
    errors = config.validate()
    if errors:
        raise ValueError(f"Configuration validation failed: {errors}")
    _config = config
```

---

## Задача 7.3: Обновление компонентов для использования новой конфигурации

### Обновление оркестратора

```python
# src/thermo_agents/orchestrator.py
from src.thermo_agents.config import get_config, SystemConfig

class ThermoOrchestrator:
    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or get_config()
        self.logger = UnifiedLogger(
            session_id=self._generate_session_id(),
            log_level=LogLevel[self.config.logging.log_level]
        )

        # Инициализация компонентов с конфигурацией
        self.searcher = CompoundSearcher(
            db_path=self.config.database.db_path,
            timeout=self.config.performance.request_timeout
        )

        self.filter_pipeline = FilterPipeline(
            config=self.config.filtering
        )
```

### Обновление фильтрации

```python
# src/thermo_agents/filtering/filter_pipeline.py
from src.thermo_agents.config import FilteringConfig

class FilterPipeline:
    def __init__(self, config: FilteringConfig):
        self.config = config
        self.max_query_limit = config.max_query_limit
        self.fallback_top_records = config.fallback_top_records
        # ... инициализация с конфигурацией
```

---

## Задача 7.4: Обновление документации

### Обновление ARCHITECTURE.md

```markdown
## Конфигурация

### Централизованная конфигурация (новое в v2.0)

Система использует централизованную конфигурацию через `src/thermo_agents/config.py`:

```python
from src.thermo_agents.config import SystemConfig, get_config

# Автоматическая загрузка из .env
config = get_config()

# Явная конфигурация
config = SystemConfig.from_file("config.json")

# Валидация конфигурации
errors = config.validate()
```

### Структура конфигурации
- **DatabaseConfig**: Настройки подключения к БД
- **LLMConfig**: Параметры LLM модели
- **LoggingConfig**: Настройки логирования
- **FilteringConfig**: Параметры фильтрации
- **PerformanceConfig**: Оптимизации производительности
- **SecurityConfig**: Настройки безопасности
```

### Создание CHANGELOG.md

```markdown
# Changelog

## [2.1.0] - 2024-XX-XX (Post-refactor)

### Added
- Централизованная система конфигурации
- Структурированное управление промптами
- Улучшенная типизация хранилищ данных
- Кэширование результатов фильтрации
- Пул соединений с базой данных

### Changed
- Рефакторинг логирования в UnifiedLogger
- Упрощение AgentStorage до Key-Value хранилища
- Разделение сложных компонентов на модули
- Стандартизация именования и импортов

### Deprecated
- Message Queue функциональность в AgentStorage
- SQL_GENERATION_PROMPT (использовать SQLBuilder)

### Fixed
- Дублирование логики в операциях
- Сложные условия в фильтрации
- Несогласованность именования полей

### Performance
- Ускорение на 10-20% для повторяющихся запросов
- Оптимизированное использование памяти
- Улучшенная concurrent поддержка
```

---

## Задача 7.5: Комплексное тестирование

### Финальные тесты

**tests/integration/test_refactored_system.py**
```python
"""Комплексные тесты отрефакторенной системы."""

import pytest
from src.thermo_agents.orchestrator import ThermoOrchestrator
from src.thermo_agents.config import SystemConfig

class TestRefactoredSystem:
    """Тесты отрефакторенной системы."""

    def test_config_loading(self):
        """Тест загрузки конфигурации."""
        config = SystemConfig.from_env()
        assert config.database.db_path
        assert config.llm.api_key
        errors = config.validate()
        assert len(errors) == 0

    def test_orchestrator_with_new_config(self):
        """Тест оркестратора с новой конфигурацией."""
        config = SystemConfig.from_env()
        orchestrator = ThermoOrchestrator(config)
        assert orchestrator.config == config

    @pytest.mark.asyncio
    async def test_end_to_end_refactored(self):
        """Сквозной тест отрефакторенной системы."""
        config = SystemConfig.from_env()
        orchestrator = ThermoOrchestrator(config)

        query = "Горение водорода: 2H2 + O2 -> 2H2O при 298K"
        result = await orchestrator.process_request(query)

        assert result is not None
        assert "H2" in result
        assert "O2" in result
        assert "H2O" in result

    def test_performance_improvements(self):
        """Тест улучшений производительности."""
        # Сравнение производительности до и после рефакторинга
        pass

    def test_caching_functionality(self):
        """Тест работы кэширования."""
        # Проверка кэша в различных компонентах
        pass
```

### Метрики качества кода

```bash
# Запуск всех тестов
uv run pytest tests/ -v --cov=src/thermo_agents --cov-report=html

# Проверка сложности
uv run radon cc src/thermo_agents/ -a

# Проверка метрик
uv run radon mi src/thermo_agents/

# Линтинг
uv run ruff check src/thermo_agents/
uv run ruff format src/thermo_agents/

# Типизация
uv run mypy src/thermo_agents/
```

---

## Порядок выполнения

### Шаг 1: Реорганизация промптов (1 день)
1. Создать новую структуру директорий
2. Разделить промпты по файлам
3. Создать PromptManager
4. Обновить импорты в коде

### Шаг 2: Конфигурация (1 день)
1. Создать config.py со всеми классами
2. Обновить компоненты для использования конфигурации
3. Добавить валидацию конфигурации
4. Обновить .env пример

### Шаг 3: Документация (0.5 день)
1. Обновить ARCHITECTURE.md
2. Создать CHANGELOG.md
3. Обновить README.md
4. Добавить примеры конфигурации

### Шаг 4: Тестирование (1 день)
1. Написать финальные интеграционные тесты
2. Запустить все тесты
3. Проверить метрики качества
4. Провести нагрузочное тестирование

### Шаг 5: Финализация (0.5 день)
1. Создать финальный PR
2. Обновить версию проекта
3. Создать релизные заметки
4. Провести code review

---

## Ожидаемые результаты

### Структура проекта
- ✅ **Чёткая организация** промптов и конфигурации
- ✅ **Централизованное управление** настройками
- ✅ **Улучшенная документация** и примеры
- ✅ **Комплексное тестирование** всех компонентов

### Качество кода
- ✅ **Покрытие тестами** > 85%
- ✅ **Сложность** снижена на 20%
- ✅ **Типизация** без ошибок mypy
- ✅ **Стиль кода** соответствует стандартам

### Производительность
- ✅ **Ускорение** на 10-20% для типичных запросов
- ✅ **Оптимизированная память** и CPU использование
- ✅ **Параллельная обработка** данных
- ✅ **Эффективное кэширование**

---

## Критерии завершения

- [ ] Промпты реорганизованы по модулям
- [ ] Централизованная конфигурация работает
- [ ] Все компоненты используют новую конфигурацию
- [ ] Документация обновлена
- [ ] Все тесты проходят (покрытие > 85%)
- [ ] Метрики качества кода достигнуты
- [ ] Performance тесты показывают улучшения
- [ ] Финальный PR создан и одобрен
- [ ] Версия проекта обновлена

---

## Итоги рефакторинга

После завершения всех 7 этапов:

1. **Удаление технического долга**: Неиспользуемый код удалён
2. **Единообразие**: Консистентный стиль и именование
3. **Модульность**: Чёткое разделение ответственности
4. **Читаемость**: Понятная структура и документация
5. **Производительность**: Оптимизированные горячие пути
6. **Архитектура**: Гибкие и расширяемые компоненты
7. **Качество**: Высокое покрытие тестов и валидация

**Результат**: Чистая, поддерживаемая, элегантная кодовая база, готовая к дальнейшему развитию и масштабированию.