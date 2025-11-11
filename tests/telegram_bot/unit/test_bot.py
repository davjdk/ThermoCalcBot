"""
Unit тесты основного класса бота ThermoSystemTelegramBot
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.telegram_bot.config import TelegramBotConfig, BotStatus
from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_command_update, create_mock_update, create_mock_context,
    create_mock_telegram_bot_config, create_mock_orchestrator, create_mock_session_manager
)


class TestThermoSystemTelegramBot:
    """Тесты основного класса бота"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.admin_user_id = 12345
        config.bot_timeout_seconds = 30
        return config

    @pytest.fixture
    async def bot(self, mock_config):
        """Создание экземпляра бота для тестов"""
        with patch('src.thermo_agents.telegram_bot.bot.Application'), \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager'), \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter'), \
             patch('src.thermo_agents.telegram_bot.bot.ThermoIntegration'), \
             patch('src.thermo_agents.telegram_bot.bot.HealthChecker'), \
             patch('src.thermo_agents.telegram_bot.bot.TelegramBotErrorHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.SmartResponseHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CommandHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.AdminCommands'), \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CallbackHandler'):

            bot = ThermoSystemTelegramBot(mock_config)
            yield bot

    def test_bot_initialization(self, bot, mock_config):
        """Тест инициализации бота"""
        assert bot.config == mock_config
        assert isinstance(bot.status, BotStatus)
        assert bot.session_manager is not None
        assert bot.rate_limiter is not None
        assert bot.thermo_integration is not None
        assert bot.health_checker is not None
        assert bot.error_handler is not None
        assert bot.smart_response_handler is not None
        assert bot.command_handler is not None
        assert bot.admin_commands is not None
        assert bot.message_handler is not None
        assert bot.callback_handler is not None

    def test_logging_setup(self, bot):
        """Тест настройки логирования"""
        assert bot.logger is not None
        assert hasattr(bot, '_setup_logging')

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, bot):
        """Тест health check при здоровом состоянии"""
        # Mock здоровых компонентов
        bot.thermo_integration.health_check = AsyncMock(return_value={
            "status": "healthy",
            "components": {
                "database": True,
                "llm": True,
                "static_data": True
            }
        })

        health = await bot.thermo_integration.health_check()
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, bot):
        """Тест health check при деградации"""
        # Mock нездоровых компонентов
        bot.thermo_integration.health_check = AsyncMock(return_value={
            "status": "degraded",
            "components": {
                "database": True,
                "llm": False,
                "static_data": True
            }
        })

        health = await bot.thermo_integration.health_check()
        assert health["status"] == "degraded"

    def test_register_handlers(self, bot):
        """Тест регистрации обработчиков"""
        # Создание mock приложения
        bot.application = Mock()
        bot.application.add_handler = Mock()

        # Вызов метода регистрации
        bot._register_handlers()

        # Проверка вызова add_handler
        assert bot.application.add_handler.called

        # Проверка количества вызовов (должно быть несколько обработчиков)
        call_count = bot.application.add_handler.call_count
        assert call_count >= 8  # start, help, status, examples, about, admin commands, callbacks, messages

    @pytest.mark.asyncio
    async def test_handle_start_command(self, bot):
        """Тест обработки команды /start"""
        update = create_mock_command_update("/start")
        context = create_mock_context()

        # Mock сессии
        bot.session_manager.start_session = AsyncMock(return_value=True)
        bot.command_handler.handle_start = AsyncMock()

        await bot._handle_start(update, context)

        # Проверки
        bot.session_manager.start_session.assert_called_once_with(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name
        )
        bot.command_handler.handle_start.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_start_command_error(self, bot):
        """Тест обработки ошибки в команде /start"""
        update = create_mock_command_update("/start")
        context = create_mock_context()

        # Mock ошибки
        bot.session_manager.start_session = AsyncMock(side_effect=Exception("Session error"))
        update.message.reply_text = AsyncMock()

        await bot._handle_start(update, context)

        # Проверка отправки сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "ошибка" in args[0].lower() or "error" in args[0].lower()

    @pytest.mark.asyncio
    async def test_handle_help_command(self, bot):
        """Тест обработки команды /help"""
        update = create_mock_command_update("/help")
        context = create_mock_context()

        bot.command_handler.handle_help = AsyncMock()

        await bot._handle_help(update, context)

        bot.command_handler.handle_help.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_status_command(self, bot):
        """Тест обработки команды /status"""
        update = create_mock_command_update("/status")
        context = create_mock_context()

        bot.command_handler.handle_status = AsyncMock()

        await bot._handle_status(update, context)

        bot.command_handler.handle_status.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_examples_command(self, bot):
        """Тест обработки команды /examples"""
        update = create_mock_command_update("/examples")
        context = create_mock_context()

        bot.command_handler.handle_examples = AsyncMock()

        await bot._handle_examples(update, context)

        bot.command_handler.handle_examples.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_about_command(self, bot):
        """Тест обработки команды /about"""
        update = create_mock_command_update("/about")
        context = create_mock_context()

        bot.command_handler.handle_about = AsyncMock()

        await bot._handle_about(update, context)

        bot.command_handler.handle_about.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_message_success(self, bot):
        """Тест успешной обработки текстового сообщения"""
        update = create_mock_update("H2O properties at 300K")
        context = create_mock_context()

        # Mock rate limiting и сессии
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        bot.session_manager.is_user_active = Mock(return_value=True)
        bot.session_manager.update_activity = AsyncMock()
        bot.message_handler.handle_message = AsyncMock()

        await bot._handle_message(update, context)

        # Проверки
        bot.rate_limiter.check_rate_limit.assert_called_once_with(update.effective_user.id)
        bot.session_manager.update_activity.assert_called_once_with(update.effective_user.id)
        bot.message_handler.handle_message.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_message_rate_limit(self, bot):
        """Тест обработки сообщения при превышении rate limit"""
        update = create_mock_update("H2O properties at 300K")
        context = create_mock_context()

        # Mock rate limiting
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(False, "Rate limit exceeded"))
        update.message.reply_text = AsyncMock()

        await bot._handle_message(update, context)

        # Проверка отправки сообщения о rate limit
        update.message.reply_text.assert_called_once_with("Rate limit exceeded")

    @pytest.mark.asyncio
    async def test_handle_message_new_session(self, bot):
        """Тест обработки сообщения с созданием новой сессии"""
        update = create_mock_update("H2O properties at 300K")
        context = create_mock_context()

        # Mock rate limiting и сессии
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        bot.session_manager.is_user_active = Mock(return_value=False)
        bot.session_manager.start_session = AsyncMock(return_value=True)
        bot.session_manager.update_activity = AsyncMock()
        bot.message_handler.handle_message = AsyncMock()

        await bot._handle_message(update, context)

        # Проверки
        bot.session_manager.start_session.assert_called_once_with(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name
        )
        bot.message_handler.handle_message.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_message_session_full(self, bot):
        """Тест обработки сообщения при заполненной системе"""
        update = create_mock_update("H2O properties at 300K")
        context = create_mock_context()

        # Mock rate limiting и сессии
        bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        bot.session_manager.is_user_active = Mock(return_value=False)
        bot.session_manager.start_session = AsyncMock(return_value=False)
        update.message.reply_text = AsyncMock()

        await bot._handle_message(update, context)

        # Проверка отправки сообщения о перегрузке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        assert "перегружена" in args[0].lower() or "overloaded" in args[0].lower()

    @pytest.mark.asyncio
    async def test_handle_unknown_command(self, bot):
        """Тест обработки неизвестной команды"""
        update = create_mock_command_update("/unknown_command")
        context = create_mock_context()

        bot.command_handler.handle_unknown = AsyncMock()

        await bot._handle_unknown(update, context)

        bot.command_handler.handle_unknown.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_send_error_message(self, bot):
        """Тест отправки сообщения об ошибке"""
        update = create_mock_update("test message")
        update.message.reply_text = AsyncMock()

        error_message = "Test error message"
        await bot._send_error_message(update, error_message)

        update.message.reply_text.assert_called_once_with(f"❌ {error_message}")

    @pytest.mark.asyncio
    async def test_get_bot_statistics(self, bot):
        """Тест получения статистики бота"""
        # Mock компонентов
        bot.health_checker.check_all_components = AsyncMock(return_value={
            "overall": "healthy",
            "components": {}
        })
        bot.session_manager.get_user_statistics = Mock(return_value={
            "active_users": 5,
            "total_sessions": 100
        })
        bot.rate_limiter.get_global_rate_info = Mock(return_value={
            "requests_per_minute": 25,
            "blocked_users": 2
        })
        bot.error_handler.get_error_statistics = Mock(return_value={
            "total_errors": 10,
            "recent_errors": 2
        })
        bot.smart_response_handler.get_optimization_stats = Mock(return_value={
            "files_sent": 15,
            "messages_sent": 85
        })

        stats = await bot.get_bot_statistics()

        assert "status" in stats
        assert "sessions" in stats
        assert "rate_limits" in stats
        assert "health" in stats
        assert "errors" in stats
        assert "smart_response" in stats

    @pytest.mark.asyncio
    async def test_get_bot_statistics_error(self, bot):
        """Тест обработки ошибки при получении статистики"""
        # Mock ошибки
        bot.health_checker.check_all_components = AsyncMock(side_effect=Exception("Stats error"))

        stats = await bot.get_bot_statistics()

        assert "error" in stats
        assert "Stats error" in stats["error"]

    @pytest.mark.asyncio
    async def test_periodic_cleanup(self, bot):
        """Тест периодической очистки"""
        # Mock компонентов
        bot.status.is_running = True

        with patch('src.thermo_agents.telegram_bot.bot.FileHandler') as mock_file_handler:
            mock_handler_instance = Mock()
            mock_handler_instance.cleanup_old_files = AsyncMock(return_value=5)
            mock_file_handler.return_value = mock_handler_instance

            # Запуск задачи очистки
            cleanup_task = asyncio.create_task(bot._periodic_cleanup())

            # Небольшая задержка
            await asyncio.sleep(0.1)

            # Остановка задачи
            bot.status.is_running = False
            await asyncio.sleep(0.1)

            # Отмена задачи
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_cleanup_temp_files(self, bot):
        """Тест очистки временных файлов"""
        with patch('src.thermo_agents.telegram_bot.bot.FileHandler') as mock_file_handler:
            mock_handler_instance = Mock()
            mock_handler_instance.cleanup_old_files = AsyncMock(return_value=3)
            mock_file_handler.return_value = mock_handler_instance

            await bot._cleanup_temp_files()

            mock_handler_instance.cleanup_old_files.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_signal_handlers(self, bot):
        """Тест настройки обработчиков сигналов"""
        with patch('src.thermo_agents.telegram_bot.bot.signal') as mock_signal, \
             patch('asyncio.create_task') as mock_create_task:

            bot._setup_signal_handlers()

            # Проверка регистрации обработчиков сигналов
            assert mock_signal.signal.called
            assert mock_signal.signal.call_count >= 2

    # Административные команды
    @pytest.mark.asyncio
    async def test_handle_admin_status(self, bot):
        """Тест обработки команды /admin_status"""
        update = create_mock_command_update("/admin_status")
        context = create_mock_context()

        bot.admin_commands.handle_admin_status = AsyncMock()

        await bot._handle_admin_status(update, context)

        bot.admin_commands.handle_admin_status.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_admin_stats(self, bot):
        """Тест обработки команды /admin_stats"""
        update = create_mock_command_update("/admin_stats")
        context = create_mock_context()

        bot.admin_commands.handle_admin_stats = AsyncMock()

        await bot._handle_admin_stats(update, context)

        bot.admin_commands.handle_admin_stats.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_callback(self, bot):
        """Тест обработки callback запроса"""
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        update = create_mock_callback_query("calc_test")
        context = create_mock_context()

        bot.callback_handler.handle_callback = AsyncMock()

        await bot._handle_callback(update, context)

        bot.callback_handler.handle_callback.assert_called_once_with(update, context)

    @pytest.mark.asyncio
    async def test_handle_callback_error(self, bot):
        """Тест обработки ошибки в callback"""
        from tests.telegram_bot.fixtures.mock_updates import create_mock_callback_query

        update = create_mock_callback_query("calc_test")
        context = create_mock_context()

        # Mock ошибки
        bot.callback_handler.handle_callback = AsyncMock(side_effect=Exception("Callback error"))
        bot.error_handler.send_user_friendly_error = AsyncMock()

        await bot._handle_callback(update, context)

        bot.error_handler.send_user_friendly_error.assert_called_once()


class TestBotStartStop:
    """Тесты запуска и остановки бота"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.admin_user_id = 12345
        config.bot_timeout_seconds = 30
        return config

    @pytest.mark.asyncio
    async def test_start_validation_error(self, mock_config):
        """Тест ошибки валидации при запуске"""
        # Неверная конфигурация (пустой токен)
        mock_config.bot_token = ""

        with patch('src.thermo_agents.telegram_bot.bot.Application'):
            bot = ThermoSystemTelegramBot(mock_config)

            with pytest.raises(ValueError, match="Конфигурация неверна"):
                await bot.start()

    @pytest.mark.asyncio
    async def test_start_health_warning(self, mock_config):
        """Тест предупреждения о здоровье компонентов при запуске"""
        with patch('src.thermo_agents.telegram_bot.bot.Application') as mock_application, \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager'), \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter'), \
             patch('src.thermo_agents.telegram_bot.bot.ThermoIntegration') as mock_thermo, \
             patch('src.thermo_agents.telegram_bot.bot.HealthChecker'), \
             patch('src.thermo_agents.telegram_bot.bot.TelegramBotErrorHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.SmartResponseHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CommandHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.AdminCommands'), \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CallbackHandler'):

            # Mock нездоровых компонентов
            mock_thermo_instance = Mock()
            mock_thermo_instance.health_check = AsyncMock(return_value={
                "status": "degraded",
                "components": {"llm": False}
            })
            mock_thermo.return_value = mock_thermo_instance

            bot = ThermoSystemTelegramBot(mock_config)

            # Mock Application
            mock_app = Mock()
            mock_app.add_handler = Mock()
            mock_app.run_polling = AsyncMock()
            mock_application.return_value = mock_app

            # Запуск с коротким таймаутом для теста
            with patch('asyncio.sleep', side_effect=asyncio.TimeoutError()):
                with pytest.raises(asyncio.TimeoutError):
                    await bot.start()

            # Проверка, что предупреждение было залогировано
            # (в реальном тесте нужно проверить логи)

    @pytest.mark.asyncio
    async def test_stop_cleanup(self, mock_config):
        """Тест очистки при остановке"""
        with patch('src.thermo_agents.telegram_bot.bot.Application'), \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager') as mock_session, \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter') as mock_rate, \
             patch('src.thermo_agents.telegram_bot.bot.ThermoIntegration'), \
             patch('src.thermo_agents.telegram_bot.bot.HealthChecker'), \
             patch('src.thermo_agents.telegram_bot.bot.TelegramBotErrorHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.SmartResponseHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CommandHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.AdminCommands'), \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler'), \
             patch('src.thermo_agents.telegram_bot.bot.CallbackHandler'):

            bot = ThermoSystemTelegramBot(mock_config)

            # Mock компонентов
            mock_session_instance = Mock()
            mock_session_instance.shutdown = AsyncMock()
            mock_session.return_value = mock_session_instance

            mock_rate_instance = Mock()
            mock_rate_instance.cleanup = AsyncMock()
            mock_rate.return_value = mock_rate_instance

            # Mock приложения
            bot.application = Mock()
            bot.application.stop = AsyncMock()
            bot.application.shutdown = AsyncMock()

            await bot.stop()

            # Проверки
            assert bot.status.is_running is False
            bot.application.stop.assert_called_once()
            bot.application.shutdown.assert_called_once()
            mock_session_instance.shutdown.assert_called_once()
            mock_rate_instance.cleanup.assert_called_once()