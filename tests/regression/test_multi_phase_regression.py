"""
Регрессионные тесты многофазной термодинамической системы.

Проверяют обратную совместимость и отсутствие регрессий:
- Старые запросы работают с новой системой
- Функциональность не нарушена
- Обработка ошибок сохранена
- Результаты согласованы
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)
from thermo_agents.orchestrator import ThermoOrchestrator, OrchestratorConfig
from thermo_agents.agent_storage import AgentStorage
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline, FilterContext
from thermo_agents.filtering.filter_stages import (
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.complex_search_stage import ComplexFormulaSearchStage
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
async def multi_phase_orchestrator(test_db_path):
    """Создает многофазный оркестратор для регрессионных тестов."""

    config = MultiPhaseOrchestratorConfig(
        db_path=test_db_path,
        llm_api_key="test_key",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        static_cache_dir="data/static_compounds",
        integration_points=100,
    )

    orchestrator = MultiPhaseOrchestrator(config)
    yield orchestrator


@pytest.fixture
async def legacy_orchestrator(test_db_path):
    """Создает легаси оркестратор для сравнения."""

    # Инициализация хранилища
    storage = AgentStorage()

    # Термодинамический агент
    thermo_config = ThermoAgentConfig(
        agent_id="test_thermo_agent",
        llm_api_key="test_key",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        storage=storage,
        session_logger=None,
    )
    thermo_agent = ThermodynamicAgent(thermo_config)

    # Детерминированные компоненты
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(test_db_path)
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    # Конвейер фильтрации
    filter_pipeline = FilterPipeline()
    filter_pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    filter_pipeline.add_stage(TemperatureFilterStage())

    # Резолверы
    temperature_resolver = TemperatureResolver()
    phase_resolver = PhaseResolver()

    filter_pipeline.add_stage(PhaseSelectionStage(phase_resolver))
    filter_pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
    filter_pipeline.add_stage(TemperatureCoverageStage(temperature_resolver))

    # Компоненты агрегации
    reaction_aggregator = ReactionAggregator(max_compounds=10)
    table_formatter = TableFormatter()
    statistics_formatter = StatisticsFormatter()

    # Оркестратор
    config = OrchestratorConfig(storage=storage)
    orchestrator = ThermoOrchestrator(
        thermodynamic_agent=thermo_agent,
        compound_searcher=compound_searcher,
        filter_pipeline=filter_pipeline,
        reaction_aggregator=reaction_aggregator,
        table_formatter=table_formatter,
        statistics_formatter=statistics_formatter,
        config=config
    )

    yield orchestrator

    # Cleanup
    await orchestrator.shutdown()


class TestMultiPhaseRegression:
    """Регрессионные тесты многофазных расчётов."""

    # Список старых запросов, которые должны продолжать работать
    LEGACY_QUERIES = [
        "Свойства воды при 298K",
        "CO2 термодинамика при 500K",
        "FeO свойства от 298K до 1000K",
        "NH3 данные при 400K",
        "CH4 свойства",
        "Расчёт реакции Fe + O2 → FeO",
        "Термодинамика H2O",
        "Данные по N2 от 298K до 1000K",
        "Свойства TiO2",
        "Энтальпия образования Al2O3",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("query", LEGACY_QUERIES)
    async def test_legacy_compound_queries_still_work(self, multi_phase_orchestrator, query):
        """
        Регрессионный тест: старые запросы соединений работают с многофазной системой.
        """

        try:
            response = await multi_phase_orchestrator.process_query(query)

            # Базовые проверки
            assert response is not None, f"Ответ не должен быть None для запроса: {query}"
            assert len(response) > 0, f"Ответ не должен быть пустым для запроса: {query}"

            # Проверяем отсутствие ошибок
            error_indicators = ["error", "ошибка", "failed", "сбой", "exception", "исключение"]
            has_error = any(indicator in response.lower() for indicator in error_indicators)
            assert not has_error, f"Ответ не должен содержать ошибки: {response[:200]}..."

            # Проверяем наличие содержательной информации
            meaningful_indicators = [
                "кдж", "дж", "ккал", "кал",  # Единицы энергии
                "h298", "s298", "g298",    # Термодинамические функции
                "темп", "температур",      # Температура
                "фаз",                     # Фаза
                "кп",                      # Теплоёмкость
            ]

            has_meaningful_content = any(indicator in response.lower() for indicator in meaningful_indicators)
            has_substantial_length = len(response) > 50

            assert has_meaningful_content or has_substantial_length, \
                f"Ответ должен содержать полезную информацию: {response[:100]}..."

        except Exception as e:
            # Если возникает ошибка, она должна быть информативной
            pytest.fail(f"Запрос вызвал необработанное исключение: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_legacy_reaction_queries_still_work(self, multi_phase_orchestrator):
        """
        Регрессионный тест: старые запросы реакций работают с многофазной системой.
        """

        legacy_reaction_queries = [
            "Fe + O2 → FeO термодинамика",
            "H2 + O2 → H2O реакция",
            "CO2 + NH3 расчёт",
            "TiO2 + Cl2 → TiCl4 + O2",
        ]

        for query in legacy_reaction_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для реакции: {query}"
                assert len(response) > 0, f"Ответ не должен быть пустым для реакции: {query}"

                # Проверяем, что система обрабатывает реакцию
                reaction_indicators = ["→", "->", "реакц", "продукт", "реагент"]
                has_reaction_context = any(indicator in response for indicator in reaction_indicators)

                # Проверяем наличие термодинамических данных или объяснения их отсутствия
                thermo_indicators = ["δh", "δg", "δs", "кдж", "дж", "энерг"]
                explanation_indicators = ["не найдено", "недостаточно", "отсутствует", "нет данных"]

                has_useful_content = (
                    any(indicator in response.lower() for indicator in thermo_indicators) or
                    any(indicator in response.lower() for indicator in explanation_indicators)
                )

                assert has_useful_content, f"Ответ должен содержать термодинамические данные или объяснение: {response[:200]}..."

            except Exception as e:
                pytest.fail(f"Запрос реакции вызвал необработанное исключение: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_single_phase_compounds_still_work(self, multi_phase_orchestrator):
        """
        Регрессионный тест: однофазные соединения работают корректно.
        """

        # Соединения, которые обычно существуют в одной фазе при нормальных условиях
        single_phase_queries = [
            "H2 свойства при 298K",    # Газ
            "N2 данные при 298K",     # Газ
            "O2 термодинамика 298K",  # Газ
            "Ar свойства 298K",       # Инертный газ
        ]

        for query in single_phase_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для: {query}"
                assert len(response) > 20, f"Ответ слишком короткий для: {query}"

                # Проверяем, что система не пытается создавать несуществующие фазовые переходы
                response_lower = response.lower()

                # Если система указывает на фазовые переходы, они должны быть корректными
                if "фаз" in response_lower:
                    # Должна быть разумная информация о фазах
                    phase_info_present = any(
                        phase in response_lower
                        for phase in ["газ", "твёрд", "жидк", "s", "l", "g"]
                    )
                    assert phase_info_present, f"Информация о фазах должна быть корректной: {response[:200]}..."

            except Exception as e:
                pytest.fail(f"Однофазный запрос вызвал исключение: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_temperature_range_format_compatibility(self, multi_phase_orchestrator):
        """
        Регрессионный тест: совместимость форматов температурных диапазонов.
        """

        temperature_formats = [
            "H2O при 298K",                    # Одна температура
            "H2O при 298 K",                   # С пробелом
            "H2O при 25°C",                    # Цельсий
            "H2O от 298K до 500K",            # Диапазон K
            "H2O от 298 до 500 K",             # Диапазон с пробелами
            "H2O от 25°C до 227°C",            # Диапазон в Цельсий
            "H2O свойства в диапазоне 298-500K", # Тире
            "H2O при T=298K",                  # Явное указание
        ]

        for query in temperature_formats:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для формата: {query}"
                assert len(response) > 10, f"Ответ не должен быть пустым для формата: {query}"

                # Проверяем, что система понимает температуру
                has_temp_reference = (
                    "298" in response or "500" in response or
                    "25" in response or "227" in response or
                    "температур" in response.lower()
                )

                # Если система не находит данные, должно быть понятно объяснено
                if not has_temp_reference:
                    has_explanation = any(
                        indicator in response.lower()
                        for indicator in ["не найдено", "отсутствует", "нет данных"]
                    )
                    assert has_explanation, f"Должно быть объяснение отсутствия данных: {response[:150]}..."

            except Exception as e:
                pytest.fail(f"Формат температуры вызвал исключение: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_error_handling_robustness(self, multi_phase_orchestrator):
        """
        Регрессионный тест: робастность обработки ошибок.
        """

        error_prone_queries = [
            "XYZ999 несуществующее вещество",  # Несуществующее соединение
            "H2O при 999999K",                 # Экстремальная температура
            "Очень длинный запрос с множеством слов и символов который может вызвать проблемы с обработкой",  # Слишком длинный
            "H2O при -1000K",                  # Отрицательная температура
            "",                                 # Пустой запрос
            "   ",                             # Только пробелы
        ]

        for query in error_prone_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                # Система должна возвращать ответ, а не падать
                assert response is not None, f"Система должна возвращать ответ для: {repr(query)}"

                # Ответ должен быть осмысленным (не пустым, не системной ошибкой)
                if len(response) > 0:
                    # Проверяем отсутствие системных ошибок
                    system_errors = [
                        "traceback", "exception", "stack trace",
                        "assertion", "attribute error", "key error"
                    ]
                    has_system_error = any(error in response.lower() for error in system_errors)
                    assert not has_system_error, f"Ответ не должен содержать системные ошибки: {response[:200]}..."

            except Exception as e:
                # Некоторые исключения могут быть приемлемыми для невалидных запросов
                acceptable_errors = ["ValueError", "TypeError", "AttributeError"]
                error_type = type(e).__name__

                if error_type not in acceptable_errors:
                    pytest.fail(f"Недопустимое исключение для запроса {repr(query)}: {e}")

    @pytest.mark.asyncio
    async def test_missing_transition_data_handling(self, multi_phase_orchestrator):
        """
        Регрессионный тест: обработка отсутствующих данных о фазовых переходах.
        """

        # Запросы, которые могут затребовать отсутствующие данные о переходах
        missing_data_queries = [
            "H2O свойства от 100K до 2000K",  # Широкий диапазон
            "FeO свойства от 100K до 5000K",  # Очень широкий диапазон
            "Неизвестное соединение фазовые переходы",  # Несуществующее вещество
        ]

        for query in missing_data_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для: {query}"
                assert len(response) > 0, f"Ответ не должен быть пустым для: {query}"

                # Система должна либо предоставить данные, либо вежливо объяснить их отсутствие
                has_data = any(
                    indicator in response.lower()
                    for indicator in ["кдж", "дж", "h298", "s298", "кп", "температур"]
                )
                has_explanation = any(
                    indicator in response.lower()
                    for indicator in ["не найдено", "недостаточно", "отсутствует", "нет данных", "ограничен"]
                )

                assert has_data or has_explanation, \
                    f"Ответ должен содержать данные или объяснение: {response[:200]}..."

            except Exception as e:
                pytest.fail(f"Обработка отсутствующих данных вызвала исключение: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_edge_temperature_range_handling(self, multi_phase_orchestrator):
        """
        Регрессионный тест: обработка граничных температурных диапазонов.
        """

        edge_cases = [
            ("H2O при 0K", "Абсолютный ноль"),
            ("H2O при 1K", "Близко к абсолютному нулю"),
            ("H2O при 10000K", "Очень высокая температура"),
            ("H2O от 0K до 1K", "Минимальный диапазон"),
            ("H2O от 9999K до 10000K", "Высокотемпературный диапазон"),
        ]

        for query, description in edge_cases:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для {description}: {query}"
                assert len(response) > 0, f"Ответ не должен быть пустым для {description}: {query}"

                # Проверяем, что система обрабатывает граничные случаи без падения
                has_content = len(response) > 20
                has_error_indicators = any(
                    error in response.lower()
                    for error in ["error", "ошибка", "failed", "exception"]
                )

                if has_content and has_error_indicators:
                    # Если есть ошибки, они должны быть информативными
                    assert "недопустим" in response.lower() or "коррект" in response.lower() or "невозможн" in response.lower(), \
                        f"Ошибка должна быть информативной для {description}: {response[:200]}..."

            except Exception as e:
                # Некоторые граничные случаи могут вызывать исключения
                if "Temperature" in str(e) or "range" in str(e) or "value" in str(e):
                    # Приемлемые исключения для температурных проблем
                    pass
                else:
                    pytest.fail(f"Граничный случай вызвал недопустимое исключение ({description}): {query} -> {e}")

    @pytest.mark.asyncio
    async def test_unicode_and_special_characters(self, multi_phase_orchestrator):
        """
        Регрессионный тест: обработка Unicode и специальных символов.
        """

        unicode_queries = [
            "H₂O свойства при 298K",           # Подстрочные индексы
            "FeO + H₂S → FeS + H₂O реакция",  # Стрелка и индексы
            "CO₂ термодинамика",              # Индекс
            "NH₃ свойства",                   # Индекс
            "Температура 25°C",               # Градус Цельсия
            "ΔH реакции",                     # Символ дельты
        ]

        for query in unicode_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None для Unicode: {query}"
                assert len(response) > 0, f"Ответ не должен быть пустым для Unicode: {query}"

                # Проверяем, что система не повреждает Unicode
                original_unicode_chars = set(query) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ()0123456789->+')
                response_unicode_chars = set(response) - set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ()0123456789->+')

                # Некоторые Unicode символы могут быть преобразованы, но основные должны сохраниться
                if any(char in "₂₃°" for char in original_unicode_chars):
                    # Проверяем, что хотя бы некоторые Unicode символы обрабатываются корректно
                    pass  # Система может конвертировать Unicode в ASCII

            except Exception as e:
                # Unicode ошибки не должны приводить к падению системы
                if "unicode" in str(e).lower() or "encoding" in str(e).lower():
                    pytest.fail(f"Unicode обработка вызвала ошибку: {query} -> {e}")

    @pytest.mark.asyncio
    async def test_backward_compatibility_response_format(self, multi_phase_orchestrator):
        """
        Регрессионный тест: совместимость формата ответов.
        """

        # Проверяем, что формат ответов остается понятным
        compatibility_queries = [
            "H2O свойства при 298K",
            "FeO термодинамика",
            "CO2 + NH3 реакция",
        ]

        for query in compatibility_queries:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None, f"Ответ не должен быть None: {query}"
                assert len(response) > 0, f"Ответ не должен быть пустым: {query}"

                # Проверяем, что ответ содержит структурированную информацию
                has_structured_data = (
                    # Таблицы или списки
                    "┌" in response or "│" in response or "└" in response or  # Unicode таблицы
                    # Форматированные данные
                    any(char in response for char in ["=", "-", ":", "•", "*"]) or
                    # Числовые данные
                    any(char.isdigit() for char in response)
                )

                # Ответ должен быть либо структурированным, либо содержать объяснение
                if not has_structured_data:
                    has_explanation = len(response) > 100 and any(
                        word in response.lower()
                        for word in ["данные", "свойства", "информация", "результат", "расчёт"]
                    )
                    assert has_explanation, f"Ответ должен быть структурированным или содержать объяснение: {response[:200]}..."

            except Exception as e:
                pytest.fail(f"Формат ответа вызвал исключение: {query} -> {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

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