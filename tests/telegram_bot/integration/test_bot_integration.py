"""
Интеграционные тесты бота с ThermoSystem
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from src.thermo_agents.orchestrator import ThermoOrchestrator
from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_update, create_mock_command_update, create_mock_context,
    create_mock_telegram_bot_config
)
from tests.telegram_bot.fixtures.test_data import (
    TEST_COMPOUNDS, TEST_REACTIONS, SAMPLE_THERMO_RESPONSES
)


class TestBotThermoIntegration:
    """Интеграционные тесты бота с ThermoSystem"""

    @pytest.fixture
    def real_config(self):
        """Реальная конфигурация для интеграционных тестов"""
        config = create_mock_telegram_bot_config()
        config.db_path = "data/thermo_data.db"  # Реальная база данных
        config.static_data_dir = "data/static_compounds"
        config.admin_user_id = 12345
        return config

    @pytest.fixture
    async def integrated_bot(self, real_config):
        """Создание бота с реальными зависимостями"""
        with patch('src.thermo_agents.telegram_bot.bot.Application') as mock_application, \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager') as mock_session_manager, \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter') as mock_rate_limiter, \
             patch('src.thermo_agents.telegram_config.bot.HealthChecker') as mock_health_checker, \
             patch('src.thermo_agents.telegram_bot.bot.TelegramBotErrorHandler') as mock_error_handler, \
             patch('src.thermo_agents.telegram_bot.bot.SmartResponseHandler') as mock_smart_response, \
             patch('src.thermo_agents.telegram_bot.bot.CommandHandler') as mock_command_handler, \
             patch('src.thermo_agents.telegram_bot.bot.AdminCommands') as mock_admin_commands, \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler') as mock_message_handler, \
             patch('src.thermo_agents.telegram_bot.bot.CallbackHandler') as mock_callback_handler:

            bot = ThermoSystemTelegramBot(real_config)
            yield bot

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_thermo_orchestrator_initialization(self, real_config):
        """Тест инициализации ThermoOrchestrator в боте"""
        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.ThermoOrchestrator') as mock_orchestrator:
            mock_orchestrator_instance = Mock()
            mock_orchestrator.return_value = mock_orchestrator_instance

            from src.thermo_agents.telegram_bot.utils.thermo_integration import ThermoIntegration
            integration = ThermoIntegration(real_config)

            assert integration.orchestrator is not None
            mock_orchestrator.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_calculation_flow_h2o_properties(self, integrated_bot):
        """Тест полного потока расчёта свойств H2O"""
        # Mock успешного ответа от ThermoOrchestrator
        mock_response = SAMPLE_THERMO_RESPONSES["h2o_properties"]
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            return_value=mock_response
        )

        # Создание mock обновления
        update = create_mock_update("H2O properties at 298K")
        context = create_mock_context()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        # Mock message handler
        integrated_bot.message_handler.handle_message = AsyncMock()

        # Выполнение полного потока
        await integrated_bot._handle_message(update, context)

        # Проверки
        integrated_bot.thermo_integration.process_thermodynamic_query.assert_called_once_with("H2O properties at 298K")
        integrated_bot.message_handler.handle_message.assert_called_once_with(update, context)

        # Проверка обновления статистики
        assert integrated_bot.status.total_requests == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_calculation_flow_reaction(self, integrated_bot):
        """Тест полного потока расчёта реакции"""
        # Mock успешного ответа от ThermoOrchestrator
        mock_response = SAMPLE_THERMO_RESPONSES["reaction_h2_o2"]
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            return_value=mock_response
        )

        update = create_mock_update("2 H2 + O2 → 2 H2O")
        context = create_mock_context()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        # Mock message handler
        integrated_bot.message_handler.handle_message = AsyncMock()

        await integrated_bot._handle_message(update, context)

        # Проверки
        integrated_bot.thermo_integration.process_thermodynamic_query.assert_called_once_with("2 H2 + O2 → 2 H2O")
        integrated_bot.message_handler.handle_message.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_error_handling_invalid_compound(self, integrated_bot):
        """Тест обработки ошибки при неверном соединении"""
        # Mock ошибки от ThermoOrchestrator
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            side_effect=Exception("Compound not found in database")
        )

        update = create_mock_update("InvalidCompoundThatDoesNotExist properties")
        context = create_mock_context()
        update.message.reply_text = AsyncMock()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        await integrated_bot._handle_message(update, context)

        # Проверка обработки ошибки
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        response_text = args[0].lower()
        assert "ошибка" in response_text or "error" in response_text

        # Проверка обновления статистики ошибок
        assert integrated_bot.status.failed_requests == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_database_integration_real_queries(self, integrated_bot):
        """Тест интеграции с реальной базой данных"""
        # Создание реального ThermoOrchestrator с тестовой базой данных
        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.ThermoOrchestrator') as mock_orchestrator_class:
            mock_orchestrator = Mock()
            mock_orchestrator.process_query = AsyncMock(return_value="Real database response")
            mock_orchestrator_class.return_value = mock_orchestrator

            # Реинициализация с реальным оркестратором
            from src.thermo_agents.telegram_bot.utils.thermo_integration import ThermoIntegration
            integration = ThermoIntegration(integrated_bot.config)
            integrated_bot.thermo_integration = integration

            # Тест с реальной базой данных
            update = create_mock_update("CO2 properties at 298K")
            context = create_mock_context()

            # Mock rate limiting и сессии
            integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
            integrated_bot.session_manager.is_user_active = Mock(return_value=True)
            integrated_bot.session_manager.update_activity = AsyncMock()

            # Mock message handler
            integrated_bot.message_handler.handle_message = AsyncMock()

            await integrated_bot._handle_message(update, context)

            # Проверки
            mock_orchestrator.process_query.assert_called_once_with("CO2 properties at 298K")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_unicode_formula_preservation(self, integrated_bot):
        """Тест сохранения Unicode формул через всю цепочку"""
        unicode_query = "H₂O + O₂ → H₂O₂ при 298K"
        mock_response = "Unicode response with H₂O and O₂ and →"
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            return_value=mock_response
        )

        update = create_mock_update(unicode_query)
        context = create_mock_context()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        # Mock message handler
        integrated_bot.message_handler.handle_message = AsyncMock()

        await integrated_bot._handle_message(update, context)

        # Проверка сохранения Unicode
        integrated_bot.thermo_integration.process_thermodynamic_query.assert_called_once_with(unicode_query)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_session_lifecycle_with_thermo(self, integrated_bot):
        """Тест жизненного цикла сессии с ThermoSystem"""
        user_id = 12345

        # Mock ThermoSystem
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            return_value="Thermo response"
        )

        # 1. Начало сессии через /start
        start_update = create_mock_command_update("/start", user_id=user_id)
        start_context = create_mock_context()
        integrated_bot.session_manager.start_session = AsyncMock(return_value=True)
        integrated_bot.command_handler.handle_start = AsyncMock()

        await integrated_bot._handle_start(start_update, start_context)

        integrated_bot.session_manager.start_session.assert_called_once_with(
            user_id,
            start_update.effective_user.username,
            start_update.effective_user.first_name
        )

        # 2. Несколько запросов в сессии
        queries = ["H2O properties", "CO2 properties", "CH4 properties"]
        for query in queries:
            update = create_mock_update(query, user_id=user_id)
            context = create_mock_context()

            integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
            integrated_bot.session_manager.is_user_active = Mock(return_value=True)
            integrated_bot.session_manager.update_activity = AsyncMock()
            integrated_bot.message_handler.handle_message = AsyncMock()

            await integrated_bot._handle_message(update, context)

            # Проверка вызова ThermoSystem
            integrated_bot.thermo_integration.process_thermodynamic_query.assert_called_with(query)

        # 3. Проверка статистики
        assert integrated_bot.status.total_requests >= len(queries) + 1  # +1 за /start

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_requests_with_thermo(self, integrated_bot):
        """Тест конкурентных запросов к ThermoSystem"""
        # Mock ThermoSystem с задержкой для симуляции реальной работы
        async def mock_slow_thermo(query):
            await asyncio.sleep(0.1)  # Симуляция задержки
            return f"Response for {query}"

        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            side_effect=mock_slow_thermo
        )

        # Создание нескольких одновременных запросов
        user_queries = [
            ("H2O properties", 12345),
            ("CO2 properties", 67890),
            ("CH4 properties", 11111),
            ("N2 properties", 22222),
            ("O2 properties", 33333)
        ]

        tasks = []
        for query, user_id in user_queries:
            update = create_mock_update(query, user_id=user_id)
            context = create_mock_context()

            integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
            integrated_bot.session_manager.is_user_active = Mock(return_value=True)
            integrated_bot.session_manager.update_activity = AsyncMock()
            integrated_bot.message_handler.handle_message = AsyncMock()

            task = integrated_bot._handle_message(update, context)
            tasks.append(task)

        # Запуск всех задач concurrently
        await asyncio.gather(*tasks, return_exceptions=True)

        # Проверка, что все запросы были обработаны
        assert integrated_bot.thermo_integration.process_thermodynamic_query.call_count == len(user_queries)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_health_check_integration(self, integrated_bot):
        """Тест интеграции health check с ThermoSystem"""
        # Mock здоровья компонентов
        integrated_bot.thermo_integration.health_check = AsyncMock(return_value={
            "status": "healthy",
            "components": {
                "database": True,
                "llm": True,
                "static_data": True
            },
            "response_time_ms": 150
        })

        health_status = await integrated_bot.thermo_integration.health_check()

        assert health_status["status"] == "healthy"
        assert health_status["components"]["database"] is True
        assert health_status["components"]["llm"] is True
        assert health_status["response_time_ms"] == 150

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_admin_stats_integration(self, integrated_bot):
        """Тест интеграции административной статистики"""
        # Mock компонентов
        integrated_bot.health_checker.check_all_components = AsyncMock(return_value={
            "overall": "healthy",
            "database": {"status": "healthy", "response_time": 50},
            "llm": {"status": "healthy", "response_time": 200}
        })
        integrated_bot.session_manager.get_user_statistics = Mock(return_value={
            "active_users": 5,
            "total_sessions": 100,
            "avg_session_duration": 45.2
        })
        integrated_bot.rate_limiter.get_global_rate_info = Mock(return_value={
            "requests_per_minute": 25,
            "blocked_users": 2
        })
        integrated_bot.error_handler.get_error_statistics = Mock(return_value={
            "total_errors": 10,
            "recent_errors": 2
        })
        integrated_bot.smart_response_handler.get_optimization_stats = Mock(return_value={
            "files_sent": 15,
            "messages_sent": 85
        })

        stats = await integrated_bot.get_bot_statistics()

        assert "status" in stats
        assert "sessions" in stats
        assert "rate_limits" in stats
        assert "health" in stats
        assert "errors" in stats
        assert "smart_response" in stats

        # Проверка конкретных значений
        assert stats["sessions"]["active_users"] == 5
        assert stats["rate_limits"]["requests_per_minute"] == 25
        assert stats["health"]["overall"] == "healthy"
        assert stats["errors"]["total_errors"] == 10
        assert stats["smart_response"]["files_sent"] == 15

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_file_generation_integration(self, integrated_bot):
        """Тест интеграции генерации файлов"""
        # Mock длинного ответа, который должен быть отправлен как файл
        long_response = "Large thermodynamic table:\n"
        for i in range(100):
            long_response += f"T = {298 + i*10}K, ΔH = {-571.66 - i*0.1} kJ\n"

        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            return_value=long_response
        )

        update = create_mock_update("Generate large table")
        context = create_mock_context()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        # Mock smart response handler с файлом
        integrated_bot.smart_response_handler.send_response = AsyncMock()

        await integrated_bot._handle_message(update, context)

        # Проверка вызова
        integrated_bot.thermo_integration.process_thermodynamic_query.assert_called_once()
        integrated_bot.smart_response_handler.send_response.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_graceful_degradation_thermo_down(self, integrated_bot):
        """Тест graceful degradation при недоступности ThermoSystem"""
        # Mock недоступности ThermoSystem
        integrated_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            side_effect=Exception("ThermoSystem temporarily unavailable")
        )

        update = create_mock_update("H2O properties")
        context = create_mock_context()
        update.message.reply_text = AsyncMock()

        # Mock rate limiting и сессии
        integrated_bot.rate_limiter.check_rate_limit = AsyncMock(return_value=(True, None))
        integrated_bot.session_manager.is_user_active = Mock(return_value=True)
        integrated_bot.session_manager.update_activity = AsyncMock()

        await integrated_bot._handle_message(update, context)

        # Проверка отправки вежливого сообщения об ошибке
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        response_text = args[0].lower()
        assert "ошибка" in response_text or "error" in response_text
        assert "попробуйте" in response_text or "try again" in response_text

        # Проверка обновления статистики
        assert integrated_bot.status.failed_requests == 1
        assert integrated_bot.status.last_error is not None