"""
Regression тесты многофазных термодинамических расчётов.

Проверяют, что старые запросы работают с новой многофазной системой.
"""

import pytest
import tempfile
from pathlib import Path

from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig


@pytest.fixture
def temp_cache_dir():
    """Временная директория для YAML кэша."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def regression_orchestrator(temp_cache_dir):
    """Оркестратор для regression тестов."""
    config = MultiPhaseOrchestratorConfig(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(temp_cache_dir / "static_compounds"),
        integration_points=200,
        llm_api_key=""
    )
    return MultiPhaseOrchestrator(config)


class TestMultiPhaseRegression:
    """Regression тесты многофазных расчётов."""

    # Список старых запросов, которые должны продолжать работать
    OLD_QUERIES = [
        "Рассчитай O2 при 500K",
        "Данные по N2 от 298K до 1000K",
        "Свойства CO2",
        "Термодинамика H2O",
        "Расчёт CH4 при 600K",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", OLD_QUERIES)
    async def test_old_queries_work_with_multi_phase(self, regression_orchestrator, query):
        """
        Regression-тест: старые запросы работают с новой многофазной системой.

        Args:
            regression_orchestrator: Оркестратор для тестов
            query: Старый запрос пользователя
        """
        try:
            response = await regression_orchestrator.process_query(query)

            # Базовые проверки
            assert len(response) > 50, f"Ответ слишком короткий для запроса: {query}"
            assert "❌" not in response or "LLM агент недоступен" in response, f"Ответ содержит ошибку: {response[:100]}"

            # Проверка, что система не упала
            assert response is not None
            assert isinstance(response, str)

        except Exception as e:
            pytest.fail(f"Запрос '{query}' вызвал ошибку: {e}")

    @pytest.mark.asyncio
    async def test_simple_query_format_change(self, regression_orchestrator):
        """
        Тест изменения формата вывода.

        Старые простые запросы теперь могут возвращать многофазный формат.
        Это ОЖИДАЕМОЕ ИЗМЕНЕНИЕ после Big Bang.
        """
        query = "Рассчитай H2O от 298K до 500K"
        response = await regression_orchestrator.process_query(query)

        # Формат может включать многофазные элементы (это нормально)
        assert "H2O" in response or "Water" in response or "LLM агент недоступен" in response

        # Проверяем, что нет явных ошибок
        if "LLM агент недоступен" not in response:
            assert "❌" not in response, f"Неожиданная ошибка в ответе: {response[:200]}"

    @pytest.mark.asyncio
    async def test_temperature_range_compatibility(self, regression_orchestrator):
        """Тест совместимости температурных диапазонов."""
        query = "Свойства O2 от 298K до 800K с шагом 100K"
        response = await regression_orchestrator.process_query(query)

        # Проверяем, что система обрабатывает температурные диапазоны
        if "LLM агент недоступен" not in response:
            assert len(response) > 0
            # Многофазный формат может включать температурные данные
            assert "298" in response or "800" in response or "T(" in response

    def test_config_backward_compatibility(self):
        """Тест обратной совместимости конфигурации."""
        from thermo_agents.config.multi_phase_config import MULTI_PHASE_CONFIG

        # Проверяем, что все ожидаемые ключи существуют
        expected_keys = [
            "use_static_cache",
            "static_cache_dir",
            "integration_points",
            "max_temperature",
            "min_segments_for_warning",
            "gap_threshold",
            "overlap_threshold",
            "show_phase_transitions",
            "show_segment_info",
            "show_metadata",
            "max_reliability_class",
            "require_298K_coverage",
        ]

        for key in expected_keys:
            assert key in MULTI_PHASE_CONFIG, f"Отсутствует ключ конфигурации: {key}"

        # Проверяем типы значений
        assert isinstance(MULTI_PHASE_CONFIG["use_static_cache"], bool)
        assert isinstance(MULTI_PHASE_CONFIG["static_cache_dir"], str)
        assert isinstance(MULTI_PHASE_CONFIG["integration_points"], int)
        assert isinstance(MULTI_PHASE_CONFIG["max_temperature"], (int, float))

    def test_orchestrator_api_compatibility(self, temp_cache_dir):
        """Тест совместимости API оркестратора."""
        config = MultiPhaseOrchestratorConfig(
            db_path="tests/fixtures/test_thermo.db",
            static_cache_dir=str(temp_cache_dir),
        )

        orchestrator = MultiPhaseOrchestrator(config)

        # Проверяем, что все ожидаемые методы существуют
        assert hasattr(orchestrator, "process_query")
        assert hasattr(orchestrator, "get_status")
        assert callable(orchestrator.process_query)
        assert callable(orchestrator.get_status)

        # Проверяем статус
        status = orchestrator.get_status()
        assert isinstance(status, dict)
        assert "orchestrator_type" in status
        assert "status" in status
        assert "components" in status

    @pytest.mark.asyncio
    async def test_component_integration_compatibility(self, regression_orchestrator):
        """Тест совместимости интеграции компонентов."""
        # Проверяем, что все компоненты инициализированы
        assert regression_orchestrator.compound_searcher is not None
        assert regression_orchestrator.calculator is not None
        assert regression_orchestrator.static_data_manager is not None
        assert regression_orchestrator.compound_formatter is not None
        assert regression_orchestrator.reaction_formatter is not None

        # Проверяем, что компоненты работают вместе
        try:
            # Поиск должен работать
            search_result = regression_orchestrator.compound_searcher.search_all_phases(
                formula="H2O",
                max_temperature=500.0
            )
            assert search_result is not None

            # Калькулятор должен работать с результатами поиска
            if search_result.records:
                mp_result = regression_orchestrator.calculator.calculate_multi_phase_properties(
                    records=search_result.records,
                    T_target=400.0
                )
                assert mp_result is not None

        except Exception as e:
            pytest.fail(f"Интеграция компонентов не работает: {e}")

    def test_static_data_manager_compatibility(self, temp_cache_dir):
        """Тест совместимости StaticDataManager."""
        from thermo_agents.storage.static_data_manager import StaticDataManager

        manager = StaticDataManager(temp_cache_dir)

        # Проверяем базовые методы
        assert hasattr(manager, "is_available")
        assert hasattr(manager, "load_compound")
        assert hasattr(manager, "get_compound_phases")

        # Проверяем работу с отсутствующими файлами
        assert manager.is_available("NonExistentCompound") is False
        assert manager.load_compound("NonExistentCompound") is None

    @pytest.mark.asyncio
    async def test_calculation_accuracy_regression(self, regression_orchestrator):
        """Тест точности расчётов (регрессия)."""
        # Ищем тестовые данные
        search_result = regression_orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        if not search_result.records:
            pytest.skip("Нет данных для H2O в тестовой БД")

        # Выполняем расчёт при стандартной температуре
        mp_result = regression_orchestrator.calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=298.15
        )

        # Проверяем физическую осмысленность результатов
        assert mp_result.Cp_final > 0, "Теплоёмкость должна быть положительной"
        assert mp_result.S_final > 0, "Энтропия должна быть положительной"

        # Для воды энтальпия должна быть отрицательной
        if search_result.records[0].formula == "H2O":
            assert mp_result.H_final < 0, "Энтальпия воды должна быть отрицательной"

        # Проверяем, что энергия Гиббса отрицательна при стандартных условиях
        assert mp_result.G_final < 0, "Энергия Гиббса должна быть отрицательной при 298K"

    @pytest.mark.asyncio
    async def test_multi_phase_vs_single_phase_consistency(self, regression_orchestrator):
        """Тест согласованности многофазных и однофазных расчётов."""
        # Ищем данные
        search_result = regression_orchestrator.compound_searcher.search_all_phases(
            formula="O2",
            max_temperature=500.0
        )

        if not search_result.records:
            pytest.skip("Нет данных для O2 в тестовой БД")

        # Многофазный расчёт
        mp_result = regression_orchestrator.calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=400.0
        )

        # Однофазный расчёт (если есть только одна фаза)
        if len(search_result.records) == 1:
            from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
            calculator = ThermodynamicCalculator()

            single_props = calculator.calculate_properties(
                record=search_result.records[0],
                T=400.0
            )

            # Сравниваем результаты (должны быть близкими)
            assert abs(mp_result.Cp_final - single_props.Cp) < 0.01, "Расхождение в теплоёмкости"
            assert abs(mp_result.H_final - single_props.H) < 100, "Расхождение в энтальпии"
            assert abs(mp_result.S_final - single_props.S) < 0.1, "Расхождение в энтропии"

    def test_error_handling_regression(self, regression_orchestrator):
        """Тест обработки ошибок (регрессия)."""
        import asyncio

        # Проверяем, что система обрабатывает некорректные запросы без падения
        async def test_bad_query(query):
            try:
                response = await regression_orchestrator.process_query(query)
                return response, None
            except Exception as e:
                return None, e

        bad_queries = [
            "",  # Пустой запрос
            "InvalidCompound123456789 свойства",  # Несуществующее вещество
            "Расчёт при температуре -100K",  # Некорректная температура
        ]

        for query in bad_queries:
            response, error = asyncio.run(test_bad_query(query))

            # Система не должна падать
            assert error is None, f"Система упала на запросе '{query}': {error}"

            # Должен быть какой-то ответ
            assert response is not None, f"Нет ответа на запрос '{query}'"
            assert len(response) > 0, f"Пустой ответ на запрос '{query}'"

    def test_logging_compatibility(self, regression_orchestrator):
        """Тест совместимости логирования."""
        # Проверяем, что у компонентов есть логгеры
        assert hasattr(regression_orchestrator, "logger")
        assert regression_orchestrator.logger is not None

        assert hasattr(regression_orchestrator.compound_searcher, "logger")
        assert regression_orchestrator.compound_searcher.logger is not None

        assert hasattr(regression_orchestrator.calculator, "logger")
        assert regression_orchestrator.calculator.logger is not None

        # Проверяем, что логгеры работают
        try:
            regression_orchestrator.logger.info("Test logging message")
            regression_orchestrator.compound_searcher.logger.info("Test component logging")
        except Exception as e:
            pytest.fail(f"Логирование не работает: {e}")

    @pytest.mark.asyncio
    async def test_memory_leak_regression(self, regression_orchestrator):
        """Тест утечек памяти (регрессия)."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Выполняем серию расчётов
        for i in range(20):
            query = f"Тестовый запрос номер {i}"
            await regression_orchestrator.process_query(query)

        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory

        # Утечка памяти должна быть минимальной
        memory_increase_mb = memory_increase / 1024 / 1024
        assert memory_increase_mb < 10, f"Слишком большая утечка памяти: {memory_increase_mb:.1f}MB"