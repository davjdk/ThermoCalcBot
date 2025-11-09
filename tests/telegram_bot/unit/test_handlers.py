"""
Unit тесты обработчиков команд и сообщений
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.commands.command_handler import CommandHandler
from src.thermo_agents.telegram_bot.handlers.message_handler import MessageHandler
from src.thermo_agents.telegram_bot.config import TelegramBotConfig, BotStatus
from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_command_update, create_mock_update, create_mock_context,
    create_mock_telegram_bot_config, create_mock_orchestrator, create_mock_session_manager
)


class TestCommandHandler:
    """Тесты обработчика команд"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.bot_username = "TestBot"
        return config

    @pytest.fixture
    def mock_status(self):
        """Mock статуса бота"""
        status = BotStatus()
        status.is_running = True
        status.start_time = 1234567890
        status.total_requests = 100
        status.failed_requests = 5
        return status

    @pytest.fixture
    def command_handler(self, mock_config, mock_status):
        """Создание обработчика команд для тестов"""
        with patch('src.thermo_agents.telegram_bot.commands.command_handler.ResponseFormatter'):
            return CommandHandler(mock_config, mock_status)

    @pytest.mark.asyncio
    async def test_handle_start_command(self, command_handler):
        """Тест обработки команды /start"""
        update = create_mock_command_update("/start")
        context = create_mock_context()

        await command_handler.handle_start(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка содержимого сообщения
        message_text = args[0]
        assert "Добро пожаловать" in message_text
        assert "ThermoSystem Bot" in message_text
        assert "термодинамических расчётов" in message_text
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_handle_help_command(self, command_handler):
        """Тест обработки команды /help"""
        update = create_mock_command_update("/help")
        context = create_mock_context()

        await command_handler.handle_help(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка содержимого сообщения
        message_text = args[0]
        assert "Справка" in message_text or "Помощь" in message_text
        assert "команды" in message_text.lower()
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_handle_status_command(self, command_handler):
        """Тест обработки команды /status"""
        update = create_mock_command_update("/status")
        context = create_mock_context()

        # Mock psutil для информации о системе
        with patch('psutil.cpu_percent', return_value=25.5), \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk:

            # Mock памяти и диска
            mock_memory.return_value.percent = 60.2
            mock_disk.return_value.percent = 45.8

            await command_handler.handle_status(update, context)

            # Проверка отправки сообщения
            update.message.reply_text.assert_called_once()
            args, kwargs = update.message.reply_text.call_args

            # Проверка содержимого сообщения
            message_text = args[0]
            assert "Статус" in message_text or "Status" in message_text
            assert "работает" in message_text.lower() or "running" in message_text.lower()
            assert "CPU" in message_text
            assert "память" in message_text.lower() or "memory" in message_text.lower()
            assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_handle_examples_command(self, command_handler):
        """Тест обработки команды /examples"""
        update = create_mock_command_update("/examples")
        context = create_mock_context()

        await command_handler.handle_examples(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка содержимого сообщения
        message_text = args[0]
        assert "Примеры" in message_text or "Examples" in message_text
        assert "H2O" in message_text
        assert "реакц" in message_text.lower() or "reaction" in message_text.lower()
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_handle_about_command(self, command_handler):
        """Тест обработки команды /about"""
        update = create_mock_command_update("/about")
        context = create_mock_context()

        await command_handler.handle_about(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка содержимого сообщения
        message_text = args[0]
        assert "О системе" in message_text or "About" in message_text
        assert "ThermoSystem" in message_text
        assert "версия" in message_text.lower() or "version" in message_text.lower()
        assert kwargs.get("parse_mode") == "Markdown"

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, command_handler):
        """Тест обработки неизвестной команды"""
        update = create_mock_command_update("/unknown")
        context = create_mock_context()

        await command_handler.handle_unknown(update, context)

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args

        # Проверка содержимого сообщения
        message_text = args[0]
        assert "неизвестная" in message_text.lower() or "unknown" in message_text.lower()
        assert "команда" in message_text.lower() or "command" in message_text.lower()
        assert "/help" in message_text


class TestMessageHandler:
    """Тесты обработчика сообщений"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.bot_username = "TestBot"
        config.enable_progress_indicators = True
        return config

    @pytest.fixture
    def mock_status(self):
        """Mock статуса бота"""
        status = BotStatus()
        status.is_running = True
        return status

    @pytest.fixture
    def mock_thermo_integration(self):
        """Mock интеграции с ThermoSystem"""
        integration = Mock()
        integration.process_thermodynamic_query = AsyncMock(return_value="Test thermodynamic response")
        return integration

    @pytest.fixture
    def mock_smart_response_handler(self):
        """Mock умного обработчика ответов"""
        handler = Mock()
        handler.send_response = AsyncMock()
        return handler

    @pytest.fixture
    def message_handler(self, mock_config, mock_status, mock_thermo_integration, mock_smart_response_handler):
        """Создание обработчика сообщений для тестов"""
        with patch('src.thermo_agents.telegram_bot.handlers.message_handler.ResponseFormatter'):
            return MessageHandler(mock_config, mock_status, mock_thermo_integration, mock_smart_response_handler)

    @pytest.mark.asyncio
    async def test_handle_message_success(self, message_handler):
        """Тест успешной обработки текстового сообщения"""
        update = create_mock_update("H2O properties at 300K")
        context = create_mock_context()

        await message_handler.handle_message(update, context)

        # Проверка вызова интеграции с ThermoSystem
        message_handler.thermo_integration.process_thermodynamic_query.assert_called_once_with("H2O properties at 300K")

        # Проверка вызова умного обработчика ответов
        message_handler.smart_response_handler.send_response.assert_called_once()

        # Обновление статистики
        assert message_handler.status.total_requests == 1

    @pytest.mark.asyncio
    async def test_handle_message_with_progress_indicator(self, message_handler):
        """Тест обработки сообщения с индикатором прогресса"""
        update = create_mock_update("Complex thermodynamic calculation")
        context = create_mock_context()

        await message_handler.handle_message(update, context)

        # Проверка отправки chat action
        context.bot.send_chat_action.assert_called_once_with(
            chat_id=update.effective_chat.id,
            action="typing"
        )

    @pytest.mark.asyncio
    async def test_handle_message_thermo_error(self, message_handler):
        """Тест обработки ошибки от ThermoSystem"""
        update = create_mock_update("Invalid query")
        context = create_mock_context()

        # Mock ошибки от ThermoSystem
        message_handler.thermo_integration.process_thermodynamic_query = AsyncMock(
            side_effect=Exception("ThermoSystem error")
        )
        update.message.reply_text = AsyncMock()

        await message_handler.handle_message(update, context)

        # Проверка отправки сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ошибка" in args[0].lower() or "error" in args[0].lower()

        # Обновление статистики ошибок
        assert message_handler.status.failed_requests == 1

    @pytest.mark.asyncio
    async def test_handle_message_smart_response_error(self, message_handler):
        """Тест обработки ошибки в умном обработчике ответов"""
        update = create_mock_update("H2O properties")
        context = create_mock_context()

        # Mock ошибки в smart response handler
        message_handler.smart_response_handler.send_response = AsyncMock(
            side_effect=Exception("Response error")
        )
        update.message.reply_text = AsyncMock()

        await message_handler.handle_message(update, context)

        # Проверка отправки сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ошибка" in args[0].lower() or "error" in args[0].lower()

    @pytest.mark.asyncio
    async def test_handle_message_empty_text(self, message_handler):
        """Тест обработки пустого сообщения"""
        update = create_mock_update("")
        context = create_mock_context()
        update.message.reply_text = AsyncMock()

        await message_handler.handle_message(update, context)

        # Проверка отправки сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "пустое" in args[0].lower() or "empty" in args[0].lower()

    @pytest.mark.asyncio
    async def test_handle_message_very_long_text(self, message_handler):
        """Тест обработки очень длинного сообщения"""
        long_text = "A" * 5000  # 5000 символов
        update = create_mock_update(long_text)
        context = create_mock_context()

        await message_handler.handle_message(update, context)

        # Проверка, что длинный текст был обработан
        message_handler.thermo_integration.process_thermodynamic_query.assert_called_once_with(long_text)

    @pytest.mark.asyncio
    async def test_handle_message_unicode_chemical_formulas(self, message_handler):
        """Тест обработки сообщений с Unicode химическими формулами"""
        unicode_text = "H₂O + O₂ → H₂O₂ при 298K"
        update = create_mock_update(unicode_text)
        context = create_mock_context()

        await message_handler.handle_message(update, context)

        # Проверка, что Unicode символы были сохранены
        message_handler.thermo_integration.process_thermodynamic_query.assert_called_once_with(unicode_text)

    @pytest.mark.asyncio
    async def test_handle_message_multiple_users(self, message_handler):
        """Тест обработки сообщений от разных пользователей"""
        users = [12345, 67890, 11111]

        for user_id in users:
            update = create_mock_update(f"Query from user {user_id}", user_id=user_id)
            context = create_mock_context()

            await message_handler.handle_message(update, context)

            # Проверка, что каждый запрос был обработан
            message_handler.thermo_integration.process_thermodynamic_query.assert_called_with(f"Query from user {user_id}")

        # Проверка общего количества запросов
        assert message_handler.status.total_requests == len(users)


class TestCallbackHandler:
    """Тесты обработчика callback запросов"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        return config

    @pytest.fixture
    def mock_status(self):
        """Mock статуса бота"""
        status = BotStatus()
        status.is_running = True
        return status

    @pytest.fixture
    def mock_thermo_integration(self):
        """Mock интеграции с ThermoSystem"""
        integration = Mock()
        integration.process_thermodynamic_query = AsyncMock(return_value="Callback response")
        return integration

    @pytest.mark.asyncio
    async def test_handle_calc_callback(self, mock_config, mock_status, mock_thermo_integration):
        """Тест обработки callback для расчёта"""
        from src.thermo_agents.telegram_bot.handlers.callback_handler import CallbackHandler
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        with patch('src.thermo_agents.telegram_bot.handlers.callback_handler.ResponseFormatter'):
            callback_handler = CallbackHandler(mock_config, mock_status, mock_thermo_integration)

            update = create_mock_callback_query("calc_H2O_300K")
            context = create_mock_context()

            await callback_handler.handle_callback(update, context)

            # Проверка ответа на callback
            update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_format_callback(self, mock_config, mock_status, mock_thermo_integration):
        """Тест обработки callback для форматирования"""
        from src.thermo_agents.telegram_bot.handlers.callback_handler import CallbackHandler
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        with patch('src.thermo_agents.telegram_bot.handlers.callback_handler.ResponseFormatter'):
            callback_handler = CallbackHandler(mock_config, mock_status, mock_thermo_integration)

            update = create_mock_callback_query("format_table")
            context = create_mock_context()

            await callback_handler.handle_callback(update, context)

            # Проверка ответа на callback
            update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_info_callback(self, mock_config, mock_status, mock_thermo_integration):
        """Тест обработки callback для информации"""
        from src.thermo_agents.telegram_bot.handlers.callback_handler import CallbackHandler
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        with patch('src.thermo_agents.telegram_bot.handlers.callback_handler.ResponseFormatter'):
            callback_handler = CallbackHandler(mock_config, mock_status, mock_thermo_integration)

            update = create_mock_callback_query("info_compound")
            context = create_mock_context()

            await callback_handler.handle_callback(update, context)

            # Проверка ответа на callback
            update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_error(self, mock_config, mock_status, mock_thermo_integration):
        """Тест обработки ошибки в callback"""
        from src.thermo_agents.telegram_bot.handlers.callback_handler import CallbackHandler
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        with patch('src.thermo_agents.telegram_bot.handlers.callback_handler.ResponseFormatter') as mock_formatter:
            # Mock ошибки
            mock_formatter_instance = Mock()
            mock_formatter_instance.format_response = AsyncMock(side_effect=Exception("Formatter error"))
            mock_formatter.return_value = mock_formatter_instance

            callback_handler = CallbackHandler(mock_config, mock_status, mock_thermo_integration)

            update = create_mock_callback_query("calc_error")
            context = create_mock_context()

            await callback_handler.handle_callback(update, context)

            # Проверка ответа на callback с ошибкой
            update.callback_query.answer.assert_called_once_with(
                text="❌ Произошла ошибка при обработке запроса",
                show_alert=True
            )


class TestAdminCommands:
    """Тесты административных команд"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.admin_user_id = 12345
        return config

    @pytest.mark.asyncio
    async def test_admin_commands_permission_check(self, mock_config):
        """Тест проверки прав администратора"""
        from src.thermo_agents.telegram_bot.commands.admin_commands import AdminCommands

        # Mock компонентов
        mock_health_checker = Mock()
        mock_error_handler = Mock()
        mock_session_manager = Mock()
        mock_rate_limiter = Mock()

        admin_commands = AdminCommands(
            mock_config,
            mock_health_checker,
            mock_error_handler,
            mock_session_manager,
            mock_rate_limiter
        )

        # Тест с неправильным user_id
        update = create_mock_command_update("/admin_status", user_id=99999)
        context = create_mock_context()
        update.message.reply_text = AsyncMock()

        await admin_commands.handle_admin_status(update, context)

        # Проверка сообщения об отсутствии прав
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "доступ" in args[0].lower() or "access" in args[0].lower()
        assert "администратор" in args[0].lower() or "admin" in args[0].lower()

    @pytest.mark.asyncio
    async def test_admin_status_command_success(self, mock_config):
        """Тест успешной обработки команды /admin_status"""
        from src.thermo_agents.telegram_bot.commands.admin_commands import AdminCommands

        # Mock компонентов
        mock_health_checker = Mock()
        mock_health_checker.get_system_status = Mock(return_value={"status": "healthy"})
        mock_error_handler = Mock()
        mock_session_manager = Mock()
        mock_session_manager.get_active_user_count = Mock(return_value=5)
        mock_rate_limiter = Mock()
        mock_rate_limiter.get_global_stats = Mock(return_value={"requests_per_minute": 25})

        admin_commands = AdminCommands(
            mock_config,
            mock_health_checker,
            mock_error_handler,
            mock_session_manager,
            mock_rate_limiter
        )

        # Тест с правильным user_id
        update = create_mock_command_update("/admin_status", user_id=12345)
        context = create_mock_context()

        await admin_commands.handle_admin_status(update, context)

        # Проверка вызовов компонентов
        mock_health_checker.get_system_status.assert_called_once()
        mock_session_manager.get_active_user_count.assert_called_once()
        mock_rate_limiter.get_global_stats.assert_called_once()

        # Проверка отправки сообщения
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "Admin" in args[0] or "Административный" in args[0]
        assert "статус" in args[0].lower() or "status" in args[0].lower()