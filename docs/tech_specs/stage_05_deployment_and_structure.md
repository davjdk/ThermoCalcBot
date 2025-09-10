# Этап 5: Развёртывание и структура

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
