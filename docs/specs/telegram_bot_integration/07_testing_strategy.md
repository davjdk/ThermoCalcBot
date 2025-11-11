# Стадия 7: Стратегия тестирования

**Статус:** Ready for implementation
**Версия:** 1.0
**Дата:** 9 ноября 2025

---

## 📋 Обзор

Этот документ определяет комплексную стратегию тестирования для Telegram бота ThermoSystem, включая unit, integration, performance и end-to-end тесты. Тестирование критически важно для обеспечения надёжности и производительности системы.

## 🧪 1. Структура тестов

### 1.1. Иерархия тестов

```
tests/telegram_bot/
├── unit/                        # Unit тесты (быстрые, изолированные)
│   ├── test_bot.py             # Основной класс бота
│   ├── test_handlers.py        # Обработчики сообщений и команд
│   ├── test_formatters.py      # Форматирование ответов
│   ├── test_file_handler.py    # Управление файлами
│   ├── test_managers.py        # Менеджеры сессий, rate limiting
│   ├── test_config.py          # Конфигурация
│   └── test_validators.py      # Валидация и безопасность
├── integration/                 # Интеграционные тесты (взаимодействие модулей)
│   ├── test_bot_integration.py # Интеграция бота с ThermoOrchestrator
│   ├── test_orchestrator_integration.py # Интеграция с основной системой
│   ├── test_database_integration.py # Работа с базой данных
│   ├── test_file_integration.py # Файловая система
│   └── test_telegram_api_integration.py # Интеграция с Telegram API
├── performance/                 # Performance тесты (нагрузка, стресс)
│   ├── test_concurrent_users.py # Конкурентные пользователи
│   ├── test_rate_limiting.py   # Rate limiting
│   ├── test_memory_usage.py    # Использование памяти
│   ├── test_response_times.py  # Время ответа
│   └── test_file_operations.py # Производительность файловых операций
├── e2e/                         # End-to-end тесты (полный цикл)
│   ├── test_real_telegram_bot.py # Тесты с реальным ботом
│   ├── test_user_scenarios.py  # Реальные сценарии использования
│   └── test_error_scenarios.py # Сценарии ошибок
├── fixtures/                    # Тестовые данные и моки
│   ├── mock_updates.py         # Моки Telegram обновлений
│   ├── test_data.py            # Тестовые термодинамические данные
│   └── sample_responses.py     # Примеры ответов
└── utils/                       # Утилиты для тестирования
    ├── test_helpers.py         # Вспомогательные функции
    ├── bot_test_client.py      # Test клиент для бота
    └── database_setup.py       # Настройка тестовой БД
```

### 1.2. Тестовая конфигурация

**Pytest configuration:**
```python
# pytest.ini (или pyproject.toml)
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
    "-v",
    "--strict-markers",
    "--disable-warnings",
    "--tb=short",
    "--cov=src/thermo_agents/telegram_bot",
    "--cov-report=term-missing",
    "--cov-report=html:htmlcov",
    "--cov-fail-under=80"
]
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "performance: Performance tests",
    "e2e: End-to-end tests",
    "slow: Slow tests",
    "external: Tests requiring external services"
]
```

## 🔧 2. Unit тесты

### 2.1. Тесты основного класса бота

**Тесты инициализации и конфигурации:**
```python
# tests/telegram_bot/unit/test_bot.py
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.telegram_bot.config import TelegramBotConfig

class TestThermoSystemTelegramBot:
    """Тесты основного класса бота"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = Mock(spec=TelegramBotConfig)
        config.bot_token = "test_token_12345"
        config.bot_username = "TestBot"
        config.mode = "polling"
        config.max_concurrent_users = 10
        config.request_timeout_seconds = 60
        return config

    @pytest.fixture
    def bot(self, mock_config):
        """Создание экземпляра бота для тестов"""
        with patch('src.thermo_agents.telegram_bot.bot.create_orchestrator'):
            with patch('src.thermo_agents.telegram_bot.bot.Application'):
                return ThermoSystemTelegramBot(mock_config)

    def test_bot_initialization(self, bot, mock_config):
        """Тест инициализации бота"""
        assert bot.config == mock_config
        assert bot.orchestrator is not None
        assert bot.session_manager is not None
        assert bot.application is not None

    def test_bot_setup_handlers(self, bot):
        """Тест настройки обработчиков"""
        # Проверка регистрации обработчиков
        application = bot.application
        application.add_handler.assert_called()

        # Проверка количества обработчиков
        call_count = application.add_handler.call_count
        assert call_count >= 4  # start, help, calculate, text messages

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, bot):
        """Тест health check при здоровом состоянии"""
        # Mock healthy components
        bot.orchestrator.thermodynamic_agent.test_connection = AsyncMock(return_value=True)

        with patch('src.thermo_agents.telegram_bot.bot.DatabaseConnector') as mock_db:
            mock_db.return_value.connect.return_value = None

            health_status = await bot.health_check()

            assert health_status["status"] == "healthy"
            assert health_status["database_connection"] is True
            assert health_status["llm_api_status"] is True

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, bot):
        """Тест health check при деградации"""
        # Mock unhealthy LLM
        bot.orchestrator.thermodynamic_agent.test_connection = AsyncMock(side_effect=Exception("LLM down"))

        with patch('src.thermo_agents.telegram_bot.bot.DatabaseConnector') as mock_db:
            mock_db.return_value.connect.return_value = None

            health_status = await bot.health_check()

            assert health_status["status"] == "degraded"
            assert health_status["database_connection"] is True
            assert health_status["llm_api_status"] is False

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, bot):
        """Тест корректного завершения работы"""
        bot.session_manager.close_all_sessions = AsyncMock()
        bot.application.stop = AsyncMock()
        bot.application.shutdown = AsyncMock()

        await bot.shutdown()

        bot.session_manager.close_all_sessions.assert_called_once()
        bot.application.stop.assert_called_once()
        bot.application.shutdown.assert_called_once()
```

### 2.2. Тесты обработчиков сообщений

**Тесты обработки команд:**
```python
# tests/telegram_bot/unit/test_handlers.py
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.handlers.bot_command_handlers import BotCommandHandlers
from src.thermo_agents.telegram_bot.handlers.message_handler import TelegramMessageHandler
from tests.telegram_bot.fixtures.mock_updates import create_mock_update, create_mock_context

class TestBotCommandHandlers:
    """Тесты обработчиков команд"""

    @pytest.fixture
    def mock_orchestrator(self):
        """Mock оркестратора"""
        orchestrator = Mock()
        orchestrator.process_query = AsyncMock(return_value="Test response")
        return orchestrator

    @pytest.fixture
    def mock_session_manager(self):
        """Mock менеджера сессий"""
        session_manager = Mock()
        session_manager.get_or_create_session = Mock(return_value=Mock())
        return session_manager

    @pytest.fixture
    def handlers(self, mock_orchestrator, mock_session_manager):
        """Создание обработчиков для тестов"""
        return BotCommandHandlers(mock_orchestrator, mock_session_manager)

    @pytest.mark.asyncio
    async def test_start_command(self, handlers):
        """Тест команды /start"""
        update = create_mock_update(message="/start")
        context = create_mock_context()

        await handlers.start(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ThermoCalcBot" in args[0]
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_help_command(self, handlers):
        """Тест команды /help"""
        update = create_mock_update(message="/help")
        context = create_mock_context()

        await handlers.help(update, context)

        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "Справка" in args[0] or "Help" in args[0]
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_calculate_command_success(self, handlers):
        """Тест команды /calculate при успешном выполнении"""
        update = create_mock_update(message="/calculate H2O properties 300K")
        context = create_mock_context()

        await handlers.calculate(update, context)

        # Проверка вызова оркестратора
        handlers.orchestrator.process_query.assert_called_once_with("H2O properties 300K")
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_calculate_command_error(self, handlers):
        """Тест команды /calculate при ошибке"""
        # Mock ошибки в оркестраторе
        handlers.orchestrator.process_query = AsyncMock(side_effect=Exception("Test error"))

        update = create_mock_update(message="/calculate invalid query")
        context = create_mock_context()

        await handlers.calculate(update, context)

        # Проверка сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ошибка" in args[0].lower() or "error" in args[0].lower()

    @pytest.mark.asyncio
    async def test_status_command(self, handlers):
        """Тест команды /status"""
        update = create_mock_update(message="/status")
        context = create_mock_context()

        # Mock сессий
        handlers.session_manager.get_active_session_count.return_value = 5
        handlers.session_manager.get_session_stats.return_value = {
            "total_requests": 100,
            "avg_session_duration": 45.2
        }

        await handlers.status(update, context)

        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "статус" in args[0].lower() or "status" in args[0].lower()

class TestTelegramMessageHandler:
    """Тесты обработчика текстовых сообщений"""

    @pytest.fixture
    def message_handler(self, mock_orchestrator, mock_session_manager):
        """Создание обработчика сообщений для тестов"""
        return TelegramMessageHandler(mock_orchestrator, mock_session_manager)

    @pytest.mark.asyncio
    async def test_handle_text_success(self, message_handler):
        """Тест обработки текстового сообщения"""
        update = create_mock_update(message="H2O properties at 300K")
        context = create_mock_context()

        # Mock ответа оркестратора
        message_handler.orchestrator.process_query = AsyncMock(
            return_value="Thermodynamic properties of H2O..."
        )

        await message_handler.handle_text(update, context)

        # Проверки
        message_handler.orchestrator.process_query.assert_called_once_with("H2O properties at 300K")
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_text_with_chat_action(self, message_handler):
        """Тест отправки индикатора набора текста"""
        update = create_mock_update(message="Complex calculation")
        context = create_mock_context()

        message_handler.orchestrator.process_query = AsyncMock(return_value="Response")

        await message_handler.handle_text(update, context)

        # Проверка отправки chat action
        context.bot.send_chat_action.assert_called_once_with(
            chat_id=update.effective_chat.id,
            action="typing"
        )

    @pytest.mark.asyncio
    async def test_handle_text_error_handling(self, message_handler):
        """Тест обработки ошибок в текстовых сообщениях"""
        update = create_mock_update(message="Invalid query")
        context = create_mock_context()

        # Mock ошибки
        message_handler.orchestrator.process_query = AsyncMock(side_effect=Exception("Processing error"))

        await message_handler.handle_text(update, context)

        # Проверка отправки сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ошибка" in args[0].lower() or "error" in args[0].lower()
```

### 2.3. Тесты форматирования

**Тесты адаптации для Telegram:**
```python
# tests/telegram_bot/unit/test_formatters.py
import pytest

from src.thermo_agents.telegram_bot.formatters.telegram_formatter import TelegramResponseFormatter

class TestTelegramResponseFormatter:
    """Тесты форматирования ответов для Telegram"""

    @pytest.fixture
    def formatter(self):
        """Создание форматера для тестов"""
        return TelegramResponseFormatter()

    @pytest.mark.asyncio
    async def test_format_short_response(self, formatter):
        """Тест форматирования короткого ответа"""
        response = "Short thermodynamic response"
        result = await formatter.format_response(response)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == response

    @pytest.mark.asyncio
    async def test_format_long_response_splitting(self, formatter):
        """Тест разделения длинного ответа"""
        # Создание длинного ответа (>4000 символов)
        long_response = "A" * 5000
        result = await formatter.format_response(long_response)

        assert isinstance(result, list)
        assert len(result) >= 2
        # Проверка, что каждая часть не превышает лимит
        for part in result:
            assert len(part) <= formatter.MAX_MESSAGE_LENGTH

    @pytest.mark.asyncio
    async def test_unicode_chemical_formulas(self, formatter):
        """Тест сохранения Unicode химических формул"""
        response = "H₂O + O₂ → H₂O₂"
        result = await formatter.format_response(response)

        assert isinstance(result, list)
        assert "H₂O" in result[0]
        assert "O₂" in result[0]
        assert "→" in result[0]

    def test_markdown_formatting(self, formatter):
        """Тест Markdown форматирования"""
        text = "ΔH = -571.66 kJ/mol\nT = 298.15 K\nK = 2.1e+83"
        formatted = formatter._apply_markdown_formatting(text)

        assert "**ΔH = -571.66**" in formatted
        assert "**T = 298.15 K**" in formatted
        assert "**K = 2.1e+83**" in formatted

    def test_emoji_structure_addition(self, formatter):
        """Тест добавления эмодзи структуры"""
        text = "ΔH = -571.66 kJ/mol\nThis is a table:\nT (K) | Cp (J/mol·K)"
        formatted = formatter._add_emoji_structure(text)

        assert "🔥" in formatted or "📊" in formatted
        lines = formatted.split('\n')
        assert any(line.startswith('🔥') for line in lines if 'ΔH' in line)

    def test_smart_message_splitting(self, formatter):
        """Тест умного разделения сообщений"""
        # Тест с таблицей
        table_text = "Header\n" + "Row with table data | More data\n" * 50
        parts = formatter._split_long_message(table_text)

        assert len(parts) > 1
        # Проверка, что таблицы не разрываются посередине строк
        for part in parts:
            lines = part.split('\n')
            for line in lines:
                if '|' in line and len(line) > 0:
                    # Строка таблицы должна быть полной
                    assert line.count('|') >= 2  # Минимум 2 столбца

    def test_filename_sanitization(self, formatter):
        """Тест очистки имён файлов"""
        # Эта функция может быть в другом классе, но для примера
        from src.thermo_agents.telegram_bot.managers.file_handler import TelegramFileHandler

        file_handler = TelegramFileHandler()

        # Тест с Unicode и специальными символами
        filename = "2H₂ + O₂ → 2H₂O @ 298K"
        sanitized = file_handler._sanitize_filename(filename)

        assert sanitized == "2H2_O2_to_2H2O_298K"
        assert all(c.isalnum() or c in '_' for c in sanitized)
```

### 2.4. Тесты управления файлами

**Тесты файлового хендлера:**
```python
# tests/telegram_bot/unit/test_file_handler.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile

from src.thermo_agents.telegram_bot.managers.file_handler import TelegramFileHandler

class TestTelegramFileHandler:
    """Тесты файлового хендлера"""

    @pytest.fixture
    def temp_dir(self):
        """Временная директория для тестов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def file_handler(self, temp_dir):
        """Создание файлового хендлера для тестов"""
        return TelegramFileHandler(
            temp_dir=temp_dir,
            cleanup_hours=1  # Быстрая очистка для тестов
        )

    def test_file_handler_initialization(self, file_handler, temp_dir):
        """Тест инициализации файлового хендлера"""
        assert file_handler.temp_dir == Path(temp_dir)
        assert file_handler.cleanup_hours == 1
        assert Path(temp_dir).exists()

    @pytest.mark.asyncio
    async def test_create_temp_file(self, file_handler):
        """Тест создания временного файла"""
        content = "Test thermodynamic report content"
        user_id = 12345
        reaction_info = "H2 + O2 -> H2O"

        file_path = await file_handler.create_temp_file(content, user_id, reaction_info)

        # Проверки
        assert Path(file_path).exists()
        assert file_path.startswith(file_handler.temp_dir)
        assert user_id in file_handler.active_files

        # Проверка содержимого файла
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_send_file_success(self, file_handler):
        """Тест успешной отправки файла"""
        update = Mock()
        context = Mock()
        content = "Test report content"
        reaction_info = "Test reaction"

        # Mock успешной отправки
        context.bot.send_document = AsyncMock()

        result = await file_handler.send_file(update, context, content, reaction_info)

        assert result is True
        context.bot.send_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_file_size_limit(self, file_handler):
        """Тест ограничения размера файла"""
        update = Mock()
        context = Mock()
        update.message = Mock()
        update.message.reply_text = AsyncMock()

        # Создание контента >20MB
        large_content = "A" * (21 * 1024 * 1024)  # 21MB

        result = await file_handler.send_file(update, context, large_content)

        assert result is False
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "слишком большой" in args[0].lower() or "too large" in args[0].lower()

    def test_sanitize_filename_unicode(self, file_handler):
        """Тест очистки имён файлов с Unicode"""
        # Тест с подстрочными индексами и стрелками
        filename = "2H₂ + O₂ → 2H₂O"
        sanitized = file_handler._sanitize_filename(filename)

        expected = "2H2_O2_to_2H2O"
        assert sanitized == expected

    def test_sanitize_filename_special_chars(self, file_handler):
        """Тест очистки имён файлов со специальными символами"""
        filename = "Reaction@#$%^&*()with special chars"
        sanitized = file_handler._sanitize_filename(filename)

        # Проверка отсутствия специальных символов
        assert all(c.isalnum() or c in '_' for c in sanitized)
        assert len(sanitized) <= 50  # Проверка ограничения длины

    @pytest.mark.asyncio
    async def test_periodic_cleanup(self, file_handler):
        """Тест периодической очистки файлов"""
        # Создание тестового файла
        content = "Test content"
        user_id = 12345
        file_path = await file_handler.create_temp_file(content, user_id)

        assert Path(file_path).exists()

        # Имитация времени очистки
        import time
        time.sleep(0.1)  # Небольшая задержка

        # Ручной вызов очистки
        await file_handler._cleanup_old_files()

        # Проверка, что файл удалён (если достаточно старый)
        # В реальном тесте нужно имитировать старые файлы
```

## 🔗 3. Интеграционные тесты

### 3.1. Интеграция с ThermoOrchestrator

**Тесты взаимодействия с основной системой:**
```python
# tests/telegram_bot/integration/test_bot_integration.py
import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.orchestrator import ThermoOrchestrator
from src.thermo_agents.telegram_bot.config import TelegramBotConfig

class TestBotIntegration:
    """Интеграционные тесты бота с ThermoSystem"""

    @pytest.fixture
    def real_config(self):
        """Реальная конфигурация для интеграционных тестов"""
        return TelegramBotConfig(
            bot_token="test_token",
            bot_username="TestBot",
            mode="polling",
            max_concurrent_users=5,
            request_timeout_seconds=30
        )

    @pytest.fixture
    async def integrated_bot(self, real_config):
        """Создание бота с реальными зависимостями"""
        # Использование реального оркестратора (с тестовой базой данных)
        with patch('src.thermo_agents.telegram_bot.bot.Application'):
            bot = ThermoSystemTelegramBot(real_config)
            yield bot

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_calculation_flow(self, integrated_bot):
        """Тест полного потока расчёта"""
        # Создание mock обновления
        update = Mock()
        update.message = Mock()
        update.message.text = "H2O properties at 300-400K"
        update.effective_user = Mock()
        update.effective_user.id = 12345
        update.effective_chat = Mock()
        update.effective_chat.id = 12345

        context = Mock()
        context.bot = Mock()
        context.bot.send_chat_action = AsyncMock()
        update.message.reply_text = AsyncMock()

        # Выполнение полного потока
        message_handler = integrated_bot._message_handler
        await message_handler.handle_text(update, context)

        # Проверки
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка наличия термодинамических данных в ответе
        response_text = args[0]
        assert "H2O" in response_text or "вода" in response_text.lower()
        assert "300" in response_text or "400" in response_text

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_error_handling_integration(self, integrated_bot):
        """Тест обработки ошибок в интеграции"""
        # Запрос с некорректными данными
        update = Mock()
        update.message = Mock()
        update.message.text = "InvalidCompoundThatDoesNotExist properties"
        update.effective_user = Mock()
        update.effective_user.id = 12345
        update.effective_chat = Mock()
        update.effective_chat.id = 12345

        context = Mock()
        context.bot = Mock()
        update.message.reply_text = AsyncMock()

        message_handler = integrated_bot._message_handler
        await message_handler.handle_text(update, context)

        # Проверка обработки ошибки
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        response_text = args[0].lower()

        # Должно содержать сообщение об ошибке
        assert "ошибка" in response_text or "не найдено" in response_text or "error" in response_text

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_integration(self, integrated_bot):
        """Тест интеграции с базой данных"""
        # Тест с реальной базой данных
        update = Mock()
        update.message = Mock()
        update.message.text = "CO2 properties at 298K"
        update.effective_user = Mock()
        update.effective_user.id = 12345
        update.effective_chat = Mock()
        update.effective_chat.id = 12345

        context = Mock()
        context.bot = Mock()
        update.message.reply_text = AsyncMock()

        message_handler = integrated_bot._message_handler
        await message_handler.handle_text(update, context)

        # Проверки
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        response_text = args[0]

        # Должна содержать данные о CO2
        assert "CO2" in response_text or "CO₂" in response_text
```

## ⚡ 4. Performance тесты

### 4.1. Тесты производительности

**Тесты времени ответа и нагрузки:**
```python
# tests/telegram_bot/performance/test_concurrent_users.py
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.telegram_bot.config import TelegramBotConfig

class TestPerformance:
    """Performance тесты"""

    @pytest.fixture
    def performance_config(self):
        """Конфигурация для performance тестов"""
        return TelegramBotConfig(
            bot_token="test_token",
            bot_username="TestBot",
            mode="polling",
            max_concurrent_users=20,
            request_timeout_seconds=30
        )

    @pytest.fixture
    async def performance_bot(self, performance_config):
        """Бот для performance тестов"""
        with patch('src.thermo_agents.telegram_bot.bot.Application'):
            bot = ThermoSystemTelegramBot(performance_config)
            yield bot

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_concurrent_users_performance(self, performance_bot):
        """Тест производительности при конкурентных пользователях"""
        # Создание нескольких одновременных запросов
        user_count = 10
        requests_per_user = 3

        async def simulate_user_request(user_id: int, request_id: int):
            """Симуляция запроса пользователя"""
            start_time = time.time()

            update = Mock()
            update.message = Mock()
            update.message.text = f"H2O properties request {request_id}"
            update.effective_user = Mock()
            update.effective_user.id = user_id
            update.effective_chat = Mock()
            update.effective_chat.id = user_id

            context = Mock()
            context.bot = Mock()
            update.message.reply_text = AsyncMock()

            try:
                message_handler = performance_bot._message_handler
                await message_handler.handle_text(update, context)

                processing_time = time.time() - start_time
                return {
                    "user_id": user_id,
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "success": True
                }
            except Exception as e:
                processing_time = time.time() - start_time
                return {
                    "user_id": user_id,
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "success": False,
                    "error": str(e)
                }

        # Запуск всех запросов concurrently
        tasks = []
        for user_id in range(user_count):
            for request_id in range(requests_per_user):
                task = simulate_user_request(user_id, request_id)
                tasks.append(task)

        # Ожидание завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализ результатов
        successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
        processing_times = [r["processing_time"] for r in successful_results]

        # Проверки производительности
        assert len(successful_results) >= user_count * requests_per_user * 0.9  # 90% успеха
        assert max(processing_times) < 30  # Максимум 30 секунд на запрос
        assert sum(processing_times) / len(processing_times) < 10  # Среднее <10 секунд

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, performance_bot):
        """Тест стабильности использования памяти"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Выполнение множества запросов
        for i in range(100):
            update = Mock()
            update.message = Mock()
            update.message.text = f"Test query {i}"
            update.effective_user = Mock()
            update.effective_user.id = i
            update.effective_chat = Mock()
            update.effective_chat.id = i

            context = Mock()
            context.bot = Mock()
            update.message.reply_text = AsyncMock()

            message_handler = performance_bot._message_handler
            await message_handler.handle_text(update, context)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Проверка, что память не выросла более чем на 100MB
        assert memory_increase < 100, f"Memory increased by {memory_increase} MB"

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_response_time_regression(self, performance_bot):
        """Тест регрессии времени ответа"""
        response_times = []

        for i in range(20):
            start_time = time.time()

            update = Mock()
            update.message = Mock()
            update.message.text = "H2O properties at 298K"
            update.effective_user = Mock()
            update.effective_user.id = 12345
            update.effective_chat = Mock()
            update.effective_chat.id = 12345

            context = Mock()
            context.bot = Mock()
            update.message.reply_text = AsyncMock()

            message_handler = performance_bot._message_handler
            await message_handler.handle_text(update, context)

            response_time = time.time() - start_time
            response_times.append(response_time)

        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)

        # Проверки
        assert avg_response_time < 5.0, f"Average response time: {avg_response_time}s"
        assert max_response_time < 10.0, f"Max response time: {max_response_time}s"

    @pytest.mark.performance
    def test_file_operations_performance(self):
        """Тест производительности файловых операций"""
        from src.thermo_agents.telegram_bot.managers.file_handler import TelegramFileHandler
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            file_handler = TelegramFileHandler(temp_dir=temp_dir)

            # Тест скорости создания файлов
            large_content = "A" * 10000  # 10KB content
            file_count = 50

            start_time = time.time()
            file_paths = []

            for i in range(file_count):
                file_path = asyncio.run(
                    file_handler.create_temp_file(large_content, i, f"Test reaction {i}")
                )
                file_paths.append(file_path)

            creation_time = time.time() - start_time

            # Проверки
            assert len(file_paths) == file_count
            assert creation_time < 5.0, f"File creation took {creation_time}s"
            assert all(Path(path).exists() for path in file_paths)
```

## 🌐 5. End-to-End тесты

### 5.1. Тесты с реальным Telegram API

**Полноцикловые тесты:**
```python
# tests/telegram_bot/e2e/test_real_telegram_bot.py
import pytest
import asyncio
from typing import Optional

# Эти тесты требуют реального токена и должны запускаться отдельно
@pytest.mark.e2e
@pytest.mark.external
class TestRealTelegramBot:
    """E2E тесты с реальным Telegram API"""

    @pytest.fixture(scope="class")
    def real_bot_token(self):
        """Реальный токен бота (из переменных окружения)"""
        import os
        token = os.getenv("TELEGRAM_BOT_TOKEN_TEST")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")
        return token

    @pytest.fixture(scope="class")
    def test_chat_id(self):
        """ID тестового чата (из переменных окружения)"""
        import os
        chat_id = os.getenv("TELEGRAM_TEST_CHAT_ID")
        if not chat_id:
            pytest.skip("TELEGRAM_TEST_CHAT_ID not set")
        return int(chat_id)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_start_command(self, real_bot_token, test_chat_id):
        """Тест команды /start с реальным ботом"""
        from telegram import Bot
        from telegram.ext import Application

        # Создание приложения
        application = Application.builder().token(real_bot_token).build()
        bot = application.bot

        try:
            # Отправка /start команды
            message = await bot.send_message(
                chat_id=test_chat_id,
                text="/start"
            )

            # Проверка ответа
            assert message is not None
            assert message.text is not None

            # Ожидание ответа от бота (polling)
            await asyncio.sleep(5)

        finally:
            await application.stop()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_calculation(self, real_bot_token, test_chat_id):
        """Тест реального расчёта через бота"""
        from telegram import Bot
        from telegram.ext import Application

        application = Application.builder().token(real_bot_token).build()
        bot = application.bot

        try:
            # Отправка запроса на расчёт
            message = await bot.send_message(
                chat_id=test_chat_id,
                text="H2O properties at 298K"
            )

            # Ожидание ответа
            await asyncio.sleep(10)

        finally:
            await application.stop()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_file_download(self, real_bot_token, test_chat_id):
        """Тест скачивания файла от реального бота"""
        from telegram import Bot
        from telegram.ext import Application

        application = Application.builder().token(real_bot_token).build()
        bot = application.bot

        try:
            # Отправка запроса, который должен вернуть файл
            message = await bot.send_message(
                chat_id=test_chat_id,
                text="2 H2 + O2 → 2 H2O при 298-1000K с шагом 50K"
            )

            # Ожидание файла
            await asyncio.sleep(15)

        finally:
            await application.stop()
```

---

## 📝 Резюме

**Ключевые элементы стратегии тестирования:**

1. **Unit тесты (80% покрытие):**
   - Быстрые изолированные тесты всех компонентов
   - Mock внешних зависимостей
   - Тестирование граничных случаев

2. **Интеграционные тесты:**
   - Проверка взаимодействия между модулями
   - Тестирование с реальной базой данных
   - End-to-end потоки обработки запросов

3. **Performance тесты:**
   - Нагрузочное тестирование concurrent пользователей
   - Тестирование времени ответа
   - Мониторинг использования памяти

4. **E2E тесты:**
   - Тесты с реальным Telegram API
   - Проверка полного пользовательского опыта
   - Тестирование в production-like окружении

5. **Автоматизация:**
   - CI/CD integration
   - Автоматический запуск тестов
   - Performance регрессия тесты

**Следующий этап:** [08_implementation_phases.md](08_implementation_phases.md) - План реализации.