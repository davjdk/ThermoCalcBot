# CLAUDE.md

Этот файл содержит инструкции для Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Обзор проекта

Это проект термодинамических AI-агентов на Python для анализа термодинамических данных химических соединений. Система использует многоагентную архитектуру v2.0:

1. **Thermodynamic Agent** - Извлекает параметры из запросов пользователей (соединения, температура, фазы и т.д.)
2. **SQL Generation Agent** - Генерирует SQL-запросы для получения термодинамических данных из базы
3. **Database Agent** - Выполняет SQL-запросы и применяет температурную фильтрацию
4. **Results Filtering Agent** - Интеллектуальная фильтрация результатов с использованием LLM
5. **Thermo Orchestrator** - Координатор взаимодействия между агентами

Агенты используют Agent-to-Agent (A2A) коммуникацию через централизованное хранилище AgentStorage и фреймворк PydanticAI. Взаимодействуют с SQLite базой данных, содержащей термодинамические данные соединений.

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

# Запуск отдельных агентов для тестирования
uv run python src/thermo_agents/thermodynamic_agent.py
uv run python src/thermo_agents/sql_generation_agent.py
uv run python src/thermo_agents/database_agent.py
uv run python src/thermo_agents/results_filtering_agent.py
uv run python src/thermo_agents/orchestrator.py
```

### Jupyter Notebooks
```bash
# Запуск Jupyter с виртуальным окружением
uv run python -m ipykernel

# Затем выбрать ядро .venv (Python 3.12) в VS Code
```

## Архитектура

### Основные компоненты

- **main.py** - Интерактивное CLI приложение, точка входа в систему
- **src/thermo_agents/agent_storage.py** - Централизованное хранилище для A2A коммуникации
- **src/thermo_agents/thermodynamic_agent.py** - Агент извлечения параметров из запросов
- **src/thermo_agents/sql_generation_agent.py** - Агент генерации SQL-запросов
- **src/thermo_agents/database_agent.py** - Агент выполнения SQL и температурной фильтрации
- **src/thermo_agents/results_filtering_agent.py** - Агент интеллектуальной фильтрации результатов
- **src/thermo_agents/orchestrator.py** - Координатор взаимодействия между агентами
- **src/thermo_agents/prompts.py** - Системные промпты для всех агентов
- **src/thermo_agents/thermo_agents_logger.py** - Система сессионного логирования

### Поток выполнения агентов

1. **User input** → Thermo Orchestrator получает запрос пользователя
2. **Parameter Extraction** → Thermodynamic Agent извлекает параметры через `EXTRACT_INPUTS_PROMPT`
3. **SQL Generation** → SQL Generation Agent генерирует запрос с использованием извлеченных параметров
4. **Database Execution** → Database Agent выполняет SQL и применяет температурную фильтрацию
5. **Results Filtering** → Results Filtering Agent интеллектуально отбирает релевантные записи
6. **Response Consolidation** → SQL Agent консолидирует все результаты и возвращает их оркестратору
7. **User Response** → Thermo Orchestrator формирует и возвращает ответ пользователю

Все агенты используют OpenRouter/OpenAI API через PydanticAI и взаимодействуют через AgentStorage. Сессионное логирование отслеживает все взаимодействия в `logs/sessions/`.

### Модели данных

Ключевые Pydantic модели:
- `ExtractedParameters` - Выход термо-агента с соединениями, температурой, фазами и т.д.
- `SQLQueryResult` - Выход SQL-агента с запросом, объяснением, ожидаемыми колонками
- `FilteredResult` - Результат интеллектуальной фильтрации записей
- `AgentMessage` - Сообщение между агентами в A2A архитектуре
- `OrchestratorRequest/Response` - Запросы и ответы оркестратора
- `ThermoAgentConfig`, `SQLAgentConfig` и др. - Конфигурации агентов через dependency injection

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
├── agent_storage.py              # Централизованное хранилище A2A коммуникации
├── thermodynamic_agent.py        # Агент извлечения параметров (PydanticAI)
├── sql_generation_agent.py       # Агент генерации SQL запросов (PydanticAI)
├── database_agent.py             # Агент выполнения SQL и температурной фильтрации
├── results_filtering_agent.py    # Агент интеллектуальной фильтрации (LLM)
├── orchestrator.py               # Координатор агентов
├── prompts.py                    # Системные промпты для всех агентов
└── thermo_agents_logger.py       # Система сессионного логирования

data/
└── thermo_data.db                # SQLite база: 316,434 записей, 32,790 соединений

logs/sessions/                    # Логи сессий с детальной трассировкой
docs/                             # Jupyter notebooks и документация
main.py                           # CLI приложение с ThermoSystem
pyproject.toml                    # Конфигурация uv с PydanticAI 1.0.8
.env                              # Переменные окружения (OPENROUTER_API_KEY и т.д.)
```

## Особенности разработки

- Проект использует `uv` для управления зависимостями (не pip/conda)
- Все агенты асинхронны и используют фреймворк PydanticAI
- Русскоязычный интерфейс для пользователей, английский для внутренней обработки
- Обработка температуры: ввод в Цельсиях, конвертация в Кельвины внутри
- Оптимизация запросов к базе для химических формул и фазово-специфичного поиска
- **Полная инкапсуляция агентов** через message-passing архитектуру
- **Централизованное хранилище** для A2A коммуникации с TTL и корреляционными ID
- **Интеллектуальная фильтрация** результатов с использованием LLM для выбора релевантных записей
- **Comprehensive логирование** сессий с детальной трассировкой всех этапов обработки