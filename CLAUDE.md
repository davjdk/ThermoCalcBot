# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Обзор проекта

Это проект термодинамических AI-агентов на Python для анализа термодинамических данных химических соединений. Система использует **гибридную архитектуру v2.0**, сочетающую LLM и детерминированную логику:

### LLM-компоненты
- **Thermodynamic Agent** - Извлекает параметры из запросов пользователей (соединения, температура, фазы и т.д.)

### Детерминированные компоненты
- **CompoundSearcher** - Поиск данных для вещества
- **FilterPipeline** - Конвейерная фильтрация (6 стадий)
- **ReactionAggregator** - Агрегация данных по реакции
- **TableFormatter** - Форматирование результатов через tabulate
- **StatisticsFormatter** - Форматирование детальной статистики

Система заменяет традиционных LLM-агентов на детерминированные модули для повышения производительности и предсказуемости результатов.

## Команды

### Настройка окружения
```bash
# Установка зависимостей
uv sync

# Активация виртуального окружения
uv shell

# Запуск главного приложения
uv run python main.py
```

### Разработка
```bash
# Добавление новых зависимостей
uv add package-name

# Добавление зависимостей для разработки
uv add --dev package-name

# Запуск компонентов для тестирования
uv run python src/thermo_agents/thermodynamic_agent.py  # Только LLM агент
uv run python main.py  # Полная система с гибридной архитектурой

# Запуск тестов
uv run pytest tests/ -v
uv run pytest tests/integration/ -v  # Интеграционные тесты
uv run pytest tests/integration/test_end_to_end.py -v  # Сквозные тесты
```

### Jupyter Notebooks
```bash
# Запуск Jupyter с виртуальным окружением
uv run python -m ipykernel

# Затем выбрать ядро .venv (Python 3.12) в VS Code
```

## Архитектура после рефакторинга (v2.0)

### LLM-компоненты
- **ThermodynamicAgent** — извлечение параметров из естественного языка

### Детерминированные компоненты
- **CompoundSearcher** — поиск данных для вещества
- **FilterPipeline** — конвейерная фильтрация (6 стадий)
- **ReactionAggregator** — агрегация данных по реакции
- **TableFormatter** — форматирование результатов

### Поток выполнения
1. User Query → ThermodynamicAgent → ExtractedReactionParameters
2. For each compound:
   - CompoundSearcher → SQL query → DatabaseRecord[]
   - FilterPipeline → Filtered records
3. ReactionAggregator → AggregatedReactionData
4. TableFormatter → Formatted response

### Основные компоненты v2.0

#### LLM-компонент
- **src/thermo_agents/thermodynamic_agent.py** - Агент извлечения параметров (PydanticAI)

#### Детерминированные модули
- **src/thermo_agents/search/** - Модули поиска
  - `sql_builder.py` - Генерация детерминированных SQL запросов
  - `database_connector.py` - Надежное соединение с SQLite
  - `compound_searcher.py` - Координация поиска соединений

- **src/thermo_agents/filtering/** - Конвейерная фильтрация
  - `filter_pipeline.py` - 6-стадийный конвейер фильтрации
  - `filter_stages.py` - Реализация стадий фильтрации
  - `temperature_resolver.py` - Разрешение температурных диапазонов
  - `phase_resolver.py` - Определение фазовых состояний
  - `complex_search_stage.py` - Комплексный поиск для сложных соединений

- **src/thermo_agents/aggregation/** - Агрегация и форматирование
  - `reaction_aggregator.py` - Агрегация данных по реакции (до 10 веществ)
  - `table_formatter.py` - Форматирование таблиц через tabulate
  - `statistics_formatter.py` - Форматирование статистики

#### Оркестрация
- **src/thermo_agents/orchestrator.py** - ThermoOrchestrator v2.0 с гибридной архитектурой

#### Модели данных
- **src/thermo_agents/models/** - Pydantic модели
  - `search.py` - Модели поиска (DatabaseRecord, CompoundSearchResult)
  - `aggregation.py` - Модели агрегации (AggregatedReactionData)
  - `extraction.py` - Модели извлечения (ExtractedReactionParameters)

#### Поддержка
- **src/thermo_agents/agent_storage.py** - Хранилище для LLM коммуникации
- **src/thermo_agents/prompts.py** - Системные промпты
- **src/thermo_agents/thermo_agents_logger.py** - Система логирования

### Модели данных v2.0

Ключевые Pydantic модели:
- `ExtractedReactionParameters` - Параметры из запроса (до 10 соединений, валидация диапазонов)
- `DatabaseRecord` - Запись из базы данных термодинамических свойств
- `CompoundSearchResult` - Результат поиска соединения со статистикой
- `FilterStatistics` - Статистика по стадиям фильтрации
- `AggregatedReactionData` - Агрегированные данные по реакции
- `ThermoAgentConfig` - Конфигурация LLM агента
- `OrchestratorConfig` - Конфигурация оркестратора v2.0

### Конфигурация

Переменные окружения в `.env`:
- `OPENROUTER_API_KEY` - API ключ для доступа к LLM
- `LLM_BASE_URL` - OpenRouter API endpoint
- `LLM_DEFAULT_MODEL` - Модель LLM по умолчанию (например, openai/gpt-4o)
- `DB_PATH` - Путь к термодинамической базе данных (data/thermo_data.db)
- `LOG_LEVEL` - Уровень логирования (INFO, DEBUG, и т.д.)

### Схема базы данных

Таблица `compounds` содержит:
- Химические формулы, названия, фазы (s/l/g/aq)
- Термодинамические свойства: H298, S298, коэффициенты теплоемкости f1-f6
- Температурные диапазоны (Tmin, Tmax), температуры плавления/кипения
- 316,434 записей с 32,790 уникальными химическими формулами

### Паттерны агентов

- Используют dependency injection через dataclass конфигурации
- Асинхронный паттерн async/await для всех операций агентов
- Структурированный вывод с Pydantic моделями
- Обработка ошибок с fallback-ответами
- Сессионное логирование для отладки и анализа
- **A2A коммуникация** через централизованное AgentStorage хранилище
- **Message-passing архитектура** с корреляционными ID для трассировки

## Структура проекта v2.0

```
src/thermo_agents/
├── __init__.py
├── agent_storage.py              # Хранилище для LLM коммуникации
├── thermodynamic_agent.py        # LLM агент извлечения параметров
├── orchestrator.py               # ThermoOrchestrator v2.0
├── prompts.py                    # Системные промпты для LLM
├── thermo_agents_logger.py       # Система сессионного логирования
├── search/                       # Детерминированный поиск
│   ├── sql_builder.py           # Генерация SQL запросов
│   ├── database_connector.py    # Соединение с БД
│   └── compound_searcher.py     # Поиск соединений
├── filtering/                    # Конвейерная фильтрация
│   ├── filter_pipeline.py       # Конвейер из 6 стадий
│   ├── filter_stages.py         # Реализация стадий
│   ├── temperature_resolver.py  # Разрешение температур
│   ├── phase_resolver.py        # Определение фаз
│   └── complex_search_stage.py  # Комплексный поиск
├── aggregation/                  # Агрегация данных
│   ├── reaction_aggregator.py   # Агрегатор реакций
│   ├── table_formatter.py       # Форматирование таблиц
│   └── statistics_formatter.py  # Форматирование статистики
└── models/                       # Pydantic модели
    ├── search.py                # Модели поиска
    ├── aggregation.py           # Модели агрегации
    └── extraction.py            # Модели извлечения

data/
└── thermo_data.db                # База термодинамических данных (316K записей)

tests/
├── integration/                  # Интеграционные тесты
│   ├── test_end_to_end.py      # Сквозные тесты
│   └── test_edge_cases.py      # Тесты граничных случаев
└── unit/                        # Unit тесты для модулей

examples/                         # Примеры использования
├── basic_usage.py               # Базовое использование
├── advanced_filtering.py        # Расширенная фильтрация
└── custom_formatters.py         # Кастомное форматирование

logs/sessions/                    # Логи сессий
docs/specs/stages/                # Спецификации этапов рефакторинга
main.py                           # CLI приложение с ThermoSystem v2.0
pyproject.toml                    # Конфигурация uv с tabulate
.env                              # Переменные окружения
```

## Особенности разработки v2.0

- **Гибридная архитектура**: LLM для извлечения параметров, детерминированная логика для обработки
- **Детерминированная фильтрация**: 6-стадийный конвейер без использования LLM
- **Tabulate форматирование**: Профессиональные таблицы и статистика
- **Многоуровневый поиск**: Префиксный поиск для сложных соединений (HCl, CO2, NH3)
- **Температурная валидация**: Проверка диапазонов и фазовых переходов
- **Агрегация данных**: Поддержка до 10 соединений в реакции
- **Прямые вызовы**: Упрощенная архитектура вместо message-passing
- **Comprehensive тестирование**: 35+ интеграционных тестов, включая граничные случаи
- **Русскоязычный интерфейс**: Для пользователей, английский для внутренней обработки
- **Надежное логирование**: Детальная трассировка всех этапов обработки
- **Оптимизированная производительность**: <5 секунд для 10 соединений