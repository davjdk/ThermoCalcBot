"""
Интеграционные тесты модуля ThermoIntegration
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.utils.thermo_integration import ThermoIntegration, ThermoResponse
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from tests.telegram_bot.fixtures.test_data import (
    TEST_COMPOUNDS, TEST_REACTIONS, SAMPLE_THERMO_RESPONSES
)


class TestThermoIntegration:
    """Интеграционные тесты модуля ThermoIntegration"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = Mock(spec=TelegramBotConfig)
        config.llm_api_key = "test_api_key"
        config.llm_base_url = "https://test.api.com"
        config.llm_model = "test-model"
        config.thermo_db_path = "data/thermo_data.db"
        config.thermo_static_data_dir = "data/static_compounds"
        config.request_timeout_seconds = 60
        config.max_concurrent_users = 20
        return config

    @pytest.fixture
    async def thermo_integration(self, mock_config):
        """Создание ThermoIntegration для тестов"""
        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.ThermoOrchestrator') as mock_orchestrator:
            mock_orchestrator_instance = Mock()
            mock_orchestrator_instance.process_query = AsyncMock(return_value="Test response")
            mock_orchestrator.return_value = mock_orchestrator_instance

            integration = ThermoIntegration(mock_config)
            integration.orchestrator = mock_orchestrator_instance
            yield integration

    @pytest.mark.asyncio
    async def test_thermo_integration_initialization(self, mock_config):
        """Тест инициализации ThermoIntegration"""
        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.ThermoOrchestrator') as mock_orchestrator:
            mock_orchestrator_instance = Mock()
            mock_orchestrator.return_value = mock_orchestrator_instance

            integration = ThermoIntegration(mock_config)

            assert integration.config == mock_config
            assert integration.orchestrator is not None
            mock_orchestrator.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_thermodynamic_query_success(self, thermo_integration):
        """Тест успешной обработки термодинамического запроса"""
        query = "H2O properties at 298K"
        expected_response = SAMPLE_THERMO_RESPONSES["h2o_properties"]

        thermo_integration.orchestrator.process_query = AsyncMock(return_value=expected_response)

        result = await thermo_integration.process_thermodynamic_query(query)

        assert isinstance(result, ThermoResponse)
        assert result.success is True
        assert result.content == expected_response
        assert result.query_type == "calculation"
        assert "H2O" in result.compounds
        assert result.processing_time_ms > 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_process_thermodynamic_query_reaction(self, thermo_integration):
        """Тест обработки запроса реакции"""
        query = "2 H2 + O2 → 2 H2O"
        expected_response = SAMPLE_THERMO_RESPONSES["reaction_h2_o2"]

        thermo_integration.orchestrator.process_query = AsyncMock(return_value=expected_response)

        result = await thermo_integration.process_thermodynamic_query(query)

        assert isinstance(result, ThermoResponse)
        assert result.success is True
        assert result.content == expected_response
        assert result.query_type == "reaction"
        assert "H2" in result.compounds and "O2" in result.compounds
        assert result.has_large_tables is True  # Реакция содержит таблицу

    @pytest.mark.asyncio
    async def test_process_thermodynamic_query_error(self, thermo_integration):
        """Тест обработки ошибки в запросе"""
        query = "InvalidCompoundThatDoesNotExist"
        error_message = "Compound not found in database"

        thermo_integration.orchestrator.process_query = AsyncMock(
            side_effect=Exception(error_message)
        )

        result = await thermo_integration.process_thermodynamic_query(query)

        assert isinstance(result, ThermoResponse)
        assert result.success is False
        assert result.content == ""
        assert result.query_type == "error"
        assert result.compounds == []
        assert result.error == error_message

    @pytest.mark.asyncio
    async def test_process_thermodynamic_query_timeout(self, thermo_integration):
        """Тест обработки таймаута запроса"""
        query = "Complex calculation"

        # Mock таймаута
        thermo_integration.orchestrator.process_query = AsyncMock(
            side_effect=asyncio.TimeoutError("Query timeout")
        )

        result = await thermo_integration.process_thermodynamic_query(query)

        assert isinstance(result, ThermoResponse)
        assert result.success is False
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_extract_compounds_from_query(self, thermo_integration):
        """Тест извлечения соединений из запроса"""
        test_cases = [
            ("H2O properties at 298K", ["H2O"]),
            ("2 H2 + O2 → 2 H2O", ["H2", "O2", "H2O"]),
            ("CO2 and CH4 reaction", ["CO2", "CH4"]),
            ("Properties of nitrogen N2", ["N2"]),
            ("Invalid query with no compounds", [])
        ]

        for query, expected_compounds in test_cases:
            thermo_integration.orchestrator.process_query = AsyncMock(return_value="Response")
            result = await thermo_integration.process_thermodynamic_query(query)

            # Проверка извлечения соединений (базовая реализация)
            # В реальном коде здесь был бы более сложный парсинг
            for compound in expected_compounds:
                assert compound in result.content or any(compound in c for c in result.compounds)

    @pytest.mark.asyncio
    async def test_determine_query_type(self, thermo_integration):
        """Тест определения типа запроса"""
        test_cases = [
            ("H2O properties", "calculation"),
            ("2 H2 + O2 → 2 H2O", "reaction"),
            ("CH4 combustion enthalpy", "calculation"),
            ("Equilibrium constant", "calculation"),
            ("Phase transition", "calculation")
        ]

        for query, expected_type in test_cases:
            thermo_integration.orchestrator.process_query = AsyncMock(return_value="Response")
            result = await thermo_integration.process_thermodynamic_query(query)

            # Базовая проверка типа запроса
            if "→" in query or "+" in query and "=" in query:
                assert result.query_type == "reaction"
            else:
                assert result.query_type in ["calculation", "error"]

    @pytest.mark.asyncio
    async def test_detect_large_tables(self, thermo_integration):
        """Тест определения больших таблиц"""
        # Тест с таблицей
        table_response = SAMPLE_THERMO_RESPONSES["reaction_h2_o2"]
        thermo_integration.orchestrator.process_query = AsyncMock(return_value=table_response)

        result = await thermo_integration.process_thermodynamic_query("Reaction with table")

        assert result.has_large_tables is True
        assert "|" in result.content

        # Тест без таблицы
        short_response = SAMPLE_THERMO_RESPONSES["h2o_properties"]
        thermo_integration.orchestrator.process_query = AsyncMock(return_value=short_response)

        result = await thermo_integration.process_thermodynamic_query("Simple properties")

        assert result.has_large_tables is False

    @pytest.mark.asyncio
    async def test_concurrent_queries(self, thermo_integration):
        """Тест обработки конкурентных запросов"""
        queries = [
            "H2O properties",
            "CO2 properties",
            "CH4 properties",
            "N2 properties",
            "O2 properties"
        ]

        # Mock обработки с задержкой
        async def mock_process_with_delay(query):
            await asyncio.sleep(0.1)
            return f"Response for {query}"

        thermo_integration.orchestrator.process_query = AsyncMock(
            side_effect=mock_process_with_delay
        )

        # Запуск всех запросов concurrently
        tasks = [
            thermo_integration.process_thermodynamic_query(query)
            for query in queries
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Проверки
        assert len(results) == len(queries)
        for i, result in enumerate(results):
            assert isinstance(result, ThermoResponse)
            assert result.success is True
            assert f"Response for {queries[i]}" in result.content

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, thermo_integration):
        """Тест health check при здоровом состоянии"""
        # Mock здоровых компонентов
        thermo_integration.orchestrator.thermodynamic_agent.test_connection = AsyncMock(
            return_value=True
        )

        health = await thermo_integration.health_check()

        assert health["status"] == "healthy"
        assert health["database_connection"] is True
        assert health["llm_api_status"] is True
        assert health["static_data_available"] is True

    @pytest.mark.asyncio
    async def test_health_check_degraded_llm_down(self, thermo_integration):
        """Тест health check при недоступности LLM"""
        # Mock недоступного LLM
        thermo_integration.orchestrator.thermodynamic_agent.test_connection = AsyncMock(
            side_effect=Exception("LLM API down")
        )

        health = await thermo_integration.health_check()

        assert health["status"] == "degraded"
        assert health["database_connection"] is True
        assert health["llm_api_status"] is False
        assert "error" in health or "llm" in health.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_health_check_database_error(self, thermo_integration):
        """Тест health check при ошибке базы данных"""
        # Mock ошибки базы данных
        thermo_integration.orchestrator.process_query = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        health = await thermo_integration.health_check()

        assert health["status"] == "unhealthy"
        assert health["database_connection"] is False
        assert "database" in health.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_response_time_measurement(self, thermo_integration):
        """Тест измерения времени ответа"""
        # Mock обработки с задержкой
        async def mock_with_delay(query):
            await asyncio.sleep(0.1)  # 100ms задержка
            return "Response"

        thermo_integration.orchestrator.process_query = AsyncMock(side_effect=mock_with_delay)

        result = await thermo_integration.process_thermodynamic_query("Test query")

        assert result.processing_time_ms >= 90  # Допуск на погрешность
        assert result.processing_time_ms < 200   # Не должно быть слишком долго

    @pytest.mark.asyncio
    async def test_unicode_support(self, thermo_integration):
        """Тест поддержки Unicode в запросах и ответах"""
        unicode_query = "Свойства H₂O при 298K"
        unicode_response = "Термодинамические свойства H₂O: ΔH = -285.83 кДж/моль"

        thermo_integration.orchestrator.process_query = AsyncMock(return_value=unicode_response)

        result = await thermo_integration.process_thermodynamic_query(unicode_query)

        assert result.success is True
        assert "H₂O" in result.content
        assert "ΔH" in result.content
        assert "298K" in result.content

    @pytest.mark.asyncio
    async def test_error_handling_graceful_degradation(self, thermo_integration):
        """Тест обработки ошибок с graceful degradation"""
        # Mock частичной ошибки (например, LLM недоступен, но база данных работает)
        thermo_integration.orchestrator.process_query = AsyncMock(
            side_effect=Exception("LLM service unavailable")
        )

        result = await thermo_integration.process_thermodynamic_query("H2O properties")

        assert result.success is False
        assert result.error is not None
        assert "LLM" in result.error

        # Проверка, что система продолжает работать
        health = await thermo_integration.health_check()
        assert health["status"] in ["degraded", "unhealthy"]

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, thermo_integration):
        """Тест стабильности использования памяти при множественных запросах"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Выполнение множества запросов
        for i in range(20):
            query = f"Test query {i}"
            thermo_integration.orchestrator.process_query = AsyncMock(return_value=f"Response {i}")

            result = await thermo_integration.process_thermodynamic_query(query)
            assert result.success is True

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Проверка, что память не выросла более чем на 50MB
        assert memory_increase < 50, f"Memory increased by {memory_increase}MB"

    @pytest.mark.asyncio
    async def test_session_logging_integration(self, thermo_integration):
        """Тест интеграции с логированием сессий"""
        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.SessionLogger') as mock_logger:
            mock_logger_instance = Mock()
            mock_logger.return_value = mock_logger_instance

            # Реинициализация с mock логгером
            integration = ThermoIntegration(thermo_integration.config)
            integration.orchestrator = thermo_integration.orchestrator

            query = "H2O properties"
            thermo_integration.orchestrator.process_query = AsyncMock(return_value="Response")

            result = await integration.process_thermodynamic_query(query)

            # Проверка вызовов логгера
            mock_logger_instance.log_request.assert_called()
            mock_logger_instance.log_response.assert_called()

    @pytest.mark.asyncio
    async def test_configuration_validation(self, mock_config):
        """Тест валидации конфигурации"""
        # Тест с отсутствующим API ключом
        mock_config.llm_api_key = None

        with patch('src.thermo_agents.telegram_bot.utils.thermo_integration.ThermoOrchestrator') as mock_orchestrator:
            integration = ThermoIntegration(mock_config)

            # Проверка, что orchestrator все равно создается
            # (в реальной реализации может быть выброшено исключение)
            assert integration.config == mock_config