# Telegram Bot Tests

Комплексная стратегия тестирования для Telegram бота ThermoSystem.

## 📋 Обзор

Этот пакет содержит полный набор тестов для обеспечения надёжности и производительности Telegram бота:

- **Unit тесты** - Тестирование отдельных компонентов в изоляции
- **Интеграционные тесты** - Проверка взаимодействия между модулями
- **Performance тесты** - Нагрузочное тестирование и проверка производительности
- **E2E тесты** - Тестирование с реальным Telegram API

## 🗂️ Структура

```
tests/telegram_bot/
├── __init__.py
├── README.md
├── unit/                        # Unit тесты
│   ├── __init__.py
│   ├── test_bot.py             # Основной класс бота
│   ├── test_handlers.py        # Обработчики команд и сообщений
│   └── test_formatters.py      # Форматирование и файлы
├── integration/                 # Интеграционные тесты
│   ├── __init__.py
│   ├── test_bot_integration.py # Интеграция бота с ThermoOrchestrator
│   └── test_thermo_integration.py # Модуль ThermoIntegration
├── performance/                 # Performance тесты
│   ├── __init__.py
│   ├── test_concurrent_users.py # Конкурентные пользователи
│   └── test_file_operations.py # Файловые операции
├── e2e/                         # End-to-end тесты
│   ├── __init__.py
│   ├── test_real_telegram_bot.py # Тесты с реальным ботом
│   └── test_user_scenarios.py   # Пользовательские сценарии
├── fixtures/                    # Тестовые данные
│   ├── __init__.py
│   ├── mock_updates.py         # Моки Telegram обновлений
│   └── test_data.py            # Тестовые термодинамические данные
└── utils/                       # Утилиты для тестирования
    ├── __init__.py
    ├── test_helpers.py         # Вспомогательные функции
    └── bot_test_client.py      # Test клиент для бота
```

## 🚀 Запуск тестов

### Все тесты
```bash
uv run pytest tests/telegram_bot/ -v
```

### Только unit тесты
```bash
uv run pytest tests/telegram_bot/unit/ -v -m unit
```

### Интеграционные тесты
```bash
uv run pytest tests/telegram_bot/integration/ -v -m integration
```

### Performance тесты
```bash
uv run pytest tests/telegram_bot/performance/ -v -m performance
```

### E2E тесты (требуют настройки)
```bash
# Установить переменные окружения
export TELEGRAM_BOT_TOKEN_TEST="your_test_bot_token"
export TELEGRAM_TEST_CHAT_ID="your_test_chat_id"

# Запустить E2E тесты
uv run pytest tests/telegram_bot/e2e/ -v -m e2e -s
```

### С покрытием кода
```bash
uv run pytest tests/telegram_bot/ --cov=src/thermo_agents/telegram_bot --cov-report=html
```

## 🏷️ Маркеры тестов

- `@pytest.mark.unit` - Unit тесты
- `@pytest.mark.integration` - Интеграционные тесты
- `@pytest.mark.performance` - Performance тесты
- `@pytest.mark.e2e` - End-to-end тесты
- `@pytest.mark.slow` - Медленные тесты
- `@pytest.mark.external` - Тесты требующие внешних сервисов

## 📊 Метрики

### Цели покрытия кода
- **Minimum**: 80%
- **Target**: 90%
- **Excellent**: 95%+

### Цели производительности
- **Время ответа**: < 10 секунд (среднее)
- **Максимальное время**: < 30 секунд
- **Конкурентные пользователи**: 20+ одновременно
- **Использование памяти**: < 100MB рост

## 🛠️ Настройка окружения

### Разработка
```bash
# Установка зависимостей
uv sync

# Активация окружения
uv shell
```

### E2E тесты
```bash
# Создать тестового бота в @BotFather
# Получить токен и ID тестового чата

# Установить переменные окружения
export TELEGRAM_BOT_TOKEN_TEST="your_bot_token"
export TELEGRAM_TEST_CHAT_ID="your_chat_id"

# Запустить тесты
uv run pytest tests/telegram_bot/e2e/ -v -m e2e
```

## 📝 Написание тестов

### Unit тесты
```python
import pytest
from unittest.mock import Mock, AsyncMock

class TestComponent:
    @pytest.fixture
    def component(self):
        return Component()

    @pytest.mark.asyncio
    async def test_functionality(self, component):
        result = await component.method()
        assert result is not None
```

### Интеграционные тесты
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration(self):
    # Тест взаимодействия компонентов
    result = await component_a.process(data)
    processed = await component_b.handle(result)
    assert processed.success
```

### Performance тесты
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_performance(self):
    start_time = time.time()
    result = await component.method()
    execution_time = time.time() - start_time

    assert execution_time < 1.0
    assert result is not None
```

### E2E тесты
```python
@pytest.mark.e2e
@pytest.mark.external
@pytest.mark.asyncio
async def test_real_bot(self):
    bot = Bot(token=REAL_TOKEN)
    message = await bot.send_message(chat_id=CHAT_ID, text="test")
    assert message is not None
```

## 🔍 Отладка тестов

### Подробный вывод
```bash
uv run pytest tests/telegram_bot/ -v -s --tb=long
```

### Остановка на первом падении
```bash
uv run pytest tests/telegram_bot/ -x
```

### Запуск конкретного теста
```bash
uv run pytest tests/telegram_bot/unit/test_bot.py::TestThermoSystemTelegramBot::test_bot_initialization -v
```

### Запуск с отладчиком
```bash
uv run pytest tests/telegram_bot/ --pdb
```

## 📈 Отчёты

### HTML отчёт о покрытии
```bash
uv run pytest tests/telegram_bot/ --cov=src/thermo_agents/telegram_bot --cov-report=html
# Открыть htmlcov/index.html
```

### XML отчёт для CI
```bash
uv run pytest tests/telegram_bot/ --junitxml=test-results.xml
```

### Performance отчёт
```bash
uv run pytest tests/telegram_bot/performance/ -v --benchmark-only
```

## 🚨 Проблемы и решения

### Частые проблемы

1. **Токен бота истёк**
   - Обновить `TELEGRAM_BOT_TOKEN_TEST`
   - Проверить права бота

2. **Тесты зависают**
   - Увеличить таймауты
   - Проверить состояние сети

3. **Memory leaks в тестах**
   - Использовать фикстуры для очистки
   - Проверять корректность cleanup

4. **Flaky тесты**
   - Увеличить время ожидания
   - Добавить retry механизмы
   - Изолировать тесты друг от друга

### Решение проблем

```bash
# Проверка конфигурации pytest
uv run pytest --version

# Проверка зависимостей
uv pip list

# Очистка кэша
uv run pytest --cache-clear
```

## 📚 Ресурсы

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [python-telegram-bot documentation](https://python-telegram-bot.org/)
- [Telegram Bot API](https://core.telegram.org/bots/api)

---

**Последнее обновление**: 9 ноября 2025
**Версия**: 1.0