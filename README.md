# ThermoCalcBot v2.2 - Термодинамический Telegram Бот

Интеллектуальная система термодинамического анализа химических реакций с Telegram интерфейсом. Использует гибридную архитектуру (LLM + детерминированные вычисления) для точных расчётов термодинамических свойств веществ и реакций.

## 🎯 Основные возможности

- **Telegram Bot** — Удобный интерфейс для работы с системой через мессенджер
- **Термодинамические расчёты** — ΔH, ΔS, ΔG, константы равновесия (K) для химических реакций
- **Табличные данные** — Cp, H, S, G для отдельных веществ в заданном температурном диапазоне
- **База данных** — 316,434 записей, 32,790 уникальных химических формул (25-6000K)
- **Многофазные расчёты** — Автоматическое определение фазовых переходов (плавление, кипение)
- **Интеллектуальная обработка** — LLM для понимания запросов на естественном языке
- **Высокая точность** — 74.66% данных высшего качества (ReliabilityClass = 1)

## 🚀 Быстрый старт на VPS

**Минимальные требования:** Ubuntu 22.04+, 512MB RAM, 20GB диск

```bash
# 1. Установка зависимостей
sudo apt update && sudo apt install -y python3.12 git curl
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Клонирование и установка
git clone https://github.com/davjdk/ThermoCalcBot.git
cd ThermoCalcBot
uv sync

# 3. Настройка
cp .env.example .env
nano .env  # Заполните TELEGRAM_BOT_TOKEN и OPENROUTER_API_KEY

# 4. Запуск
uv run python telegram_bot.py
```

📖 **Подробные инструкции:**
- [Полное руководство по развертыванию на VPS](docs/VPS_DEPLOYMENT.md)
- [Архитектура Telegram бота](docs/TELEGRAM_BOT_ARCHITECTURE.md)
- [Руководство пользователя](docs/user_guide.md)

## 🆕 Примеры использования Telegram бота

После запуска бота найдите его в Telegram и попробуйте:

```
/start — Приветствие и краткая справка
/help — Подробная справка по командам

📊 Табличные данные веществ:
"H2O при 300-600K с шагом 50"
"Термодинамические данные для Fe при 400-800K"

⚗️ Расчёты реакций:
"2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
"Zn + S → ZnS при 298-1000K шаг 100"
"Fe + O2 → FeO при стандартных условиях"

📈 Статистика и помощь:
/stats — Статистика использования
/example — Примеры запросов
```

## 🏗️ Архитектура системы

### Гибридная архитектура v2.2

**LLM-компонент:**
- `ThermodynamicAgent` — Извлечение параметров из естественного языка с помощью PydanticAI
- Структурированный вывод через модель `ExtractedReactionParameters`

**Детерминированные компоненты:**
- `CompoundDataLoader` — Двухстадийная загрузка (YAML кэш → база данных)
- `ThermodynamicEngine` — Расчёты по формулам Шомейта с численным интегрированием
- `ReactionEngine` — Расчёт ΔH, ΔS, ΔG, константы равновесия (K)
- `UnifiedReactionFormatter` — Профессиональное форматирование через tabulate

### Telegram Bot интеграция

**Основные компоненты:**
- `ThermoSystemTelegramBot` — Основной класс бота с интегрированной логикой
- `TelegramBotConfig` — Централизованная конфигурация
- `SessionManager` — Управление пользовательскими сессиями
- `RateLimiter` — Ограничение частоты запросов
- `HealthChecker` — Мониторинг здоровья системы

**Поток обработки запроса:**
```
User (Telegram) → Bot → SessionManager → ThermoIntegration → ThermoOrchestrator
                                                                      ↓
                                                            ThermodynamicEngine
                                                                      ↓
                                                            UnifiedFormatter
                                                                      ↓
User ← Bot ← SmartResponseHandler ← FormattedResponse
```

Подробнее: [Архитектура Telegram бота](docs/TELEGRAM_BOT_ARCHITECTURE.md)

## 📦 Локальная установка для разработки

### Требования

- Python 3.12+
- uv для управления зависимостями
- OpenRouter API ключ (для LLM)
- Telegram Bot Token (получите через @BotFather)

### Установка

1. **Клонируйте репозиторий:**
```bash
git clone https://github.com/davjdk/ThermoCalcBot.git
cd ThermoCalcBot
```

2. **Установите зависимости с помощью uv:**
```bash
# Установка UV (если не установлен)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Синхронизация зависимостей
uv sync

# Для разработки с тестами
uv sync --group dev

# Для работы с Jupyter ноутбуками
uv sync --group notebook
```

3. **Настройте переменные окружения в `.env`:**
```bash
cp .env.example .env
# Отредактируйте .env и заполните обязательные параметры
```

**Обязательные переменные в `.env`:**
```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_BOT_USERNAME=YourBotUsername
TELEGRAM_MODE=polling

# LLM API
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o

# База данных
DB_PATH=data/thermo_data.db

# Логирование
LOG_LEVEL=INFO
```

### Запуск

**Запуск Telegram бота:**
```bash
uv run python telegram_bot.py
```

**Запуск в интерактивном режиме (без Telegram):**
```bash
uv run python main.py
```

## 📊 База данных

Система использует SQLite базу с **316,434 записями** и **32,790 уникальных химических формул**:

- 100% покрытие температурных диапазонов (Tmin/Tmax)
- 74.66% данных высшего качества (ReliabilityClass = 1)
- Поддержка фазовых переходов (Tmelt/Tboil)
- Температурный диапазон: 25-6000K (зависит от вещества)
- Многоуровневый поиск для сложных соединений
- YAML кэш для распространённых веществ (H₂O, CO₂, O₂, и др.)

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
uv run pytest

# Только модульные тесты
uv run pytest -m unit

# Интеграционные тесты
uv run pytest -m integration

# Тесты Telegram бота
uv run pytest tests/telegram_bot/

# Тесты с покрытием кода
uv run pytest --cov=src --cov-report=html

# Быстрые тесты (исключая медленные)
uv run pytest -m "not slow"
```

### Категории тестов

- **unit** — Модульные тесты отдельных компонентов
- **integration** — Интеграционные тесты взаимодействия модулей
- **e2e** — End-to-end тесты полных сценариев
- **performance** — Тесты производительности и нагрузки
- **slow** — Медленные тесты (>1 секунды)
- **external** — Тесты, требующие внешних сервисов (API, сеть)

## 📚 Примеры использования

### Python API (программное использование)

```python
import asyncio
from pathlib import Path
from thermo_agents.orchestrator import ThermoOrchestrator, ThermoOrchestratorConfig
from thermo_agents.session_logger import SessionLogger

async def main():
    # Конфигурация
    config = ThermoOrchestratorConfig(
        llm_api_key="your_openrouter_key",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="openai/gpt-4o",
        db_path=Path("data/thermo_data.db")
    )
    
    # Создание оркестратора с логированием
    with SessionLogger() as logger:
        orchestrator = ThermoOrchestrator(config, session_logger=logger)
        
        # Расчёт реакции
        response = await orchestrator.process_query(
            "Zn + S → ZnS при 298-1000K шаг 100"
        )
        
        print(response)

asyncio.run(main())
```

### Примеры из репозитория

```bash
# Базовое использование системы
uv run python examples/basic_usage.py

# Расширенные стратегии фильтрации
uv run python examples/advanced_filtering.py

# Кастомные форматтеры (CSV, JSON, HTML)
uv run python examples/custom_formatters.py

# Демонстрация работы с реакциями
uv run python examples/reaction_calculation_example.py
```

### Jupyter ноутбуки

```bash
# Установка зависимостей для ноутбуков
uv sync --group notebook

# Запуск Jupyter
uv run jupyter notebook

# Примеры ноутбуков:
# - docs/calc_example.ipynb — Примеры расчётов
# - docs/db_work.ipynb — Работа с базой данных
# - docs/сhlorination_of_tungsten.ipynb — Хлорирование вольфрама
```

## 📁 Структура проекта

```
ThermoCalcBot/
├── telegram_bot.py                 # Основной скрипт запуска Telegram бота
├── main.py                         # Интерактивный режим (без Telegram)
├── pyproject.toml                  # Конфигурация проекта и зависимости
├── .env.example                    # Шаблон переменных окружения
│
├── src/thermo_agents/              # Основной код системы
│   ├── orchestrator.py             # Главный оркестратор v2.2
│   ├── thermodynamic_agent.py      # LLM агент извлечения параметров
│   ├── session_logger.py           # Логирование сессий
│   │
│   ├── core_logic/                 # Детерминированная логика
│   │   ├── compound_data_loader.py # Двухстадийная загрузка данных
│   │   ├── thermodynamic_engine.py # Расчёты по формулам Шомейта
│   │   ├── reaction_engine.py      # Расчёт ΔH, ΔS, ΔG, K
│   │   ├── phase_transition_detector.py # Определение фазовых переходов
│   │   └── record_range_builder.py # Трехуровневая стратегия отбора
│   │
│   ├── search/                     # Система поиска
│   │   ├── sql_builder.py          # Генератор SQL запросов
│   │   ├── database_connector.py   # Подключение к SQLite
│   │   └── compound_searcher.py    # Координатор поиска
│   │
│   ├── formatting/                 # Форматирование вывода
│   │   ├── unified_reaction_formatter.py # Унифицированный форматтер
│   │   ├── table_formatter.py      # Табличное представление
│   │   └── compound_info_formatter.py # Информация о веществах
│   │
│   ├── telegram_bot/               # Telegram Bot компоненты
│   │   ├── bot.py                  # Основной класс бота
│   │   ├── config.py               # Конфигурация бота
│   │   ├── handlers/               # Обработчики сообщений
│   │   ├── commands/               # Команды бота
│   │   ├── utils/                  # Утилиты (session, rate limiter)
│   │   ├── formatters/             # Форматирование для Telegram
│   │   └── managers/               # Менеджеры (smart response)
│   │
│   ├── storage/                    # Управление данными
│   │   └── static_data_manager.py  # YAML кэш для веществ
│   │
│   └── models/                     # Pydantic модели
│       ├── extraction.py           # Модели извлечения параметров
│       ├── search.py               # Модели поиска
│       └── static_data.py          # Модели YAML данных
│
├── data/                           # Данные
│   ├── thermo_data.db              # База термодинамических данных (316K записей)
│   └── static_compounds/           # YAML кэш для распространённых веществ
│       ├── H2O.yaml
│       ├── CO2.yaml
│       └── ...
│
├── tests/                          # Тесты
│   ├── unit/                       # Модульные тесты
│   ├── integration/                # Интеграционные тесты
│   ├── telegram_bot/               # Тесты Telegram бота
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── e2e/
│   │   └── performance/
│   └── conftest.py                 # Fixtures для pytest
│
├── examples/                       # Примеры использования
│   ├── basic_usage.py
│   ├── reaction_calculation_example.py
│   └── custom_formatters.py
│
├── docs/                           # Документация
│   ├── ARCHITECTURE.md             # Архитектура ThermoSystem
│   ├── TELEGRAM_BOT_ARCHITECTURE.md # Архитектура Telegram бота
│   ├── VPS_DEPLOYMENT.md           # Развертывание на VPS
│   ├── user_guide.md               # Руководство пользователя
│   └── calc_example.ipynb          # Примеры расчётов (Jupyter)
│
├── logs/                           # Логи системы
│   └── sessions/                   # Логи сессий
│
└── scripts/                        # Служебные скрипты
    ├── database_analysis.py
    └── run_dev.py
```

## � Конфигурация

### Переменные окружения (.env)

**Telegram Bot (обязательные):**
```env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_BOT_USERNAME=YourBotUsername
TELEGRAM_MODE=polling  # или webhook для production
```

**LLM API (обязательные):**
```env
OPENROUTER_API_KEY=your_openrouter_api_key
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o
```

**База данных:**
```env
DB_PATH=data/thermo_data.db
STATIC_DATA_DIR=data/static_compounds
```

**Ограничения и производительность:**
```env
MAX_CONCURRENT_USERS=50
MAX_REQUESTS_PER_MINUTE=10
REQUEST_TIMEOUT_SECONDS=60
```

**Логирование:**
```env
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
LOG_DIR=logs
```

**Временные файлы:**
```env
TEMP_FILE_DIR=temp/telegram_files
FILE_CLEANUP_HOURS=24
MAX_FILE_SIZE_MB=10
```

### Режимы работы

**Polling (рекомендуется для VPS):**
- Бот сам опрашивает Telegram API
- Не требует SSL сертификата
- Проще в настройке

**Webhook (для production с доменом):**
- Telegram отправляет обновления на ваш сервер
- Требует SSL сертификат и домен
- Более эффективен для высоких нагрузок

Подробнее: [VPS Deployment Guide](docs/VPS_DEPLOYMENT.md)

##
## 🔒 Безопасность

### Рекомендации по безопасности

1. **Защита API ключей:**
   - Никогда не коммитьте `.env` файл в Git
   - Используйте `.env.example` как шаблон
   - Храните ключи в безопасном месте

2. **Rate Limiting:**
   - Настройте `MAX_REQUESTS_PER_MINUTE` для предотвращения злоупотреблений
   - Система автоматически ограничивает количество запросов

3. **Валидация входных данных:**
   - Все входные данные проверяются через Pydantic модели
   - Защита от SQL инъекций через параметризованные запросы

4. **Мониторинг:**
   - Регулярно проверяйте логи на подозрительную активность
   - Используйте `/stats` для мониторинга использования

Подробнее: [Telegram Bot Security Guide](docs/telegram_bot_security_guide.md)

## 📈 Производительность

### Метрики системы

**Время ответа (полный цикл):**
- LLM извлечение параметров: 500-1000ms
- Поиск в базе данных: 50-200ms
- Термодинамические расчёты: 100-300ms
- Форматирование: <100ms
- **Общее среднее время: 1-2 секунды**

**Эффективность кэширования:**
- SQL запросы: >90% hit rate
- YAML кэш: мгновенный доступ для 10+ веществ
- Статические данные: ~5MB в памяти

**Использование ресурсов:**
- Базовое использование: ~50MB RAM
- С активным кэшем: ~150MB RAM
- Рекомендуемый VPS: 512MB RAM минимум

### Оптимизации v2.2

- ✅ Двухстадийная загрузка данных (YAML → DB)
- ✅ Трехуровневая стратегия отбора записей
- ✅ Виртуальное объединение идентичных записей
- ✅ LRU кэширование SQL запросов
- ✅ Асинхронная обработка запросов
- ✅ Прямые вызовы без message passing overhead

## 🛠️ Разработка и вклад

### Добавление зависимостей

```bash
# Основная зависимость
uv add package-name

# Зависимость для разработки
uv add --group dev package-name

# Зависимость для ноутбуков
uv add --group notebook package-name
```

### Структура тестов

```bash
# Написание тестов
tests/
├── unit/           # Модульные тесты (быстрые, изолированные)
├── integration/    # Интеграционные тесты (взаимодействие модулей)
├── telegram_bot/   # Тесты Telegram бота
└── e2e/            # End-to-end тесты (полные сценарии)

# Запуск специфических тестов
uv run pytest tests/unit/test_thermodynamic_engine.py -v
```

### Code Style

Проект следует стандартам:
- PEP 8 для Python кода
- Type hints для всех функций
- Docstrings для публичных API
- Pydantic модели для валидации данных

## 📊 Статус проекта

| Компонент         | Версия | Статус             | Покрытие тестами |
| ----------------- | ------ | ------------------ | ---------------- |
| ThermoSystem Core | 2.2    | ✅ Production Ready | >85%             |
| Telegram Bot      | 1.0    | ✅ Production Ready | >80%             |
| База данных       | 1.0    | ✅ Stable           | 100%             |
| YAML Cache        | 1.0    | ✅ Stable           | >90%             |
| Документация      | 2.2    | ✅ Complete         | -                |

## 📚 Документация

- **[Архитектура системы](docs/ARCHITECTURE.md)** — Детальное описание ThermoSystem v2.2
- **[Архитектура Telegram бота](docs/TELEGRAM_BOT_ARCHITECTURE.md)** — Компоненты и потоки бота
- **[Развертывание на VPS](docs/VPS_DEPLOYMENT.md)** — Полное руководство по развертыванию
- **[Руководство пользователя](docs/user_guide.md)** — Инструкции для пользователей
- **[Анализ базы данных](docs/database_analysis_report.md)** — Детальный анализ 316K записей

## 🐛 Решение проблем

### Частые проблемы

**Бот не запускается:**
```powershell
# Проверьте конфигурацию (Windows PowerShell)
uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('Token:', bool(os.getenv('TELEGRAM_BOT_TOKEN')))"

# Проверьте логи
Get-Content logs/sessions/session_*.log -Tail 50
```

**Ошибки LLM API:**
```powershell
# Проверьте OpenRouter API ключ (Windows PowerShell)
$env:OPENROUTER_API_KEY = (Get-Content .env | Select-String "OPENROUTER_API_KEY").ToString().Split("=")[1]
Invoke-RestMethod -Uri "https://openrouter.ai/api/v1/models" -Headers @{Authorization="Bearer $env:OPENROUTER_API_KEY"}
```

**База данных заблокирована:**
```powershell
# Перезапустите бота (Windows PowerShell)
Stop-Process -Name python -Force
uv run python telegram_bot.py
```

Подробнее: [VPS Deployment - Troubleshooting](docs/VPS_DEPLOYMENT.md#решение-проблем)

## 📞 Контакты и поддержка

- **GitHub Repository:** https://github.com/davjdk/ThermoCalcBot
- **GitHub Issues:** https://github.com/davjdk/ThermoCalcBot/issues
- **Документация:** [docs/](docs/)
- **Примеры:** [examples/](examples/)

## 📄 Лицензия

Проект для научных и образовательных целей.

---

**Версия:** 2.2  
**Обновлено:** 11 ноября 2025  
**Статус:** Production Ready with Telegram Bot Integration
