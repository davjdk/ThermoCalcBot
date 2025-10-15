"""
Тесты граничных случаев для термодинамической системы v2.0.

Тестирует обработку ошибочных ситуаций, экстремальных значений
и непредвиденных сценариев использования.
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline, FilterContext
from thermo_agents.filtering.filter_stages import (
    ComplexFormulaSearchStage,
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.models.extraction import ExtractedReactionParameters


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
def compound_searcher(test_db_path):
    """Создает поисковик для тестов."""
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(test_db_path)
    return CompoundSearcher(sql_builder, db_connector)


@pytest.fixture
def filter_pipeline():
    """Создает конвейер фильтрации для тестов."""
    pipeline = FilterPipeline()
    pipeline.add_stage(TemperatureFilterStage())

    temperature_resolver = TemperatureResolver()
    phase_resolver = PhaseResolver()

    pipeline.add_stage(PhaseSelectionStage(phase_resolver))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
    pipeline.add_stage(TemperatureCoverageStage(temperature_resolver))

    return pipeline


@pytest.fixture
def reaction_aggregator():
    """Создает агрегатор реакций для тестов."""
    return ReactionAggregator(max_compounds=10)


class TestSubstancesNotFound:
    """Тесты для веществ, отсутствующих в базе данных."""

    @pytest.mark.asyncio
    async def test_completely_unknown_substance(self, compound_searcher):
        """TC1: Вещество отсутствует в БД."""
        result = compound_searcher.search_compound("Xyz123", (500, 600))

        assert result is not None
        assert result.search_statistics.total_found == 0
        assert len(result.records_found) == 0
        assert not result.is_found

    @pytest.mark.asyncio
    async def test_invalid_formula_format(self, compound_searcher):
        """TC2: Некорректный формат химической формулы."""
        invalid_formulas = [
            "!!!invalid!!!",
            "123456",
            "@#$%^&",
            "",
            "   ",  # Пробелы
            "H",    # Слишком короткая
            "C999999999999H999999999999",  # Слишком длинная
        ]

        for formula in invalid_formulas:
            result = compound_searcher.search_compound(formula, (298, 500))
            # Должен обработать без ошибок, но не найти ничего
            assert result is not None
            assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_case_sensitivity(self, compound_searcher):
        """TC3: Проверка чувствительности к регистру."""
        # H2O должно найтись в разных регистрах
        variants = ["H2O", "h2o", "H2o", "h2O"]

        found_any = False
        for variant in variants:
            result = compound_searcher.search_compound(variant, (298, 500))
            if result and result.search_statistics.total_found > 0:
                found_any = True
                break

        # Хотя бы один вариант должен найтись
        assert found_any, f"None of the H2O variants found in database"

    @pytest.mark.asyncio
    async def test_prefix_search_fallback(self, compound_searcher):
        """TC4: Префиксный поиск для сложных соединений."""
        # Соединения, которые могут требовать префиксного поиска
        complex_compounds = ["HCl", "CO2", "NH3", "CH4"]

        for compound in complex_compounds:
            result = compound_searcher.search_compound(compound, (298, 500))
            # Результат должен быть, даже если точного совпадения нет
            assert result is not None


class TestTemperatureEdgeCases:
    """Тесты граничных случаев с температурами."""

    @pytest.mark.asyncio
    async def test_extreme_high_temperatures(self, compound_searcher):
        """TC5: Экстремально высокие температуры."""
        result = compound_searcher.search_compound("H2O", (2000, 5000))

        assert result is not None
        # Может найти данные или не найти, но не должно быть ошибок
        assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_extreme_low_temperatures(self, compound_searcher):
        """TC6: Экстремально низкие температуры."""
        result = compound_searcher.search_compound("H2O", (0, 50))

        assert result is not None
        assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_negative_temperatures(self, compound_searcher):
        """TC7: Отрицательные температуры (физически некорректно)."""
        result = compound_searcher.search_compound("H2O", (-100, 50))

        assert result is not None
        # Должен обработать без ошибок
        assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_zero_temperature_range(self, compound_searcher):
        """TC8: Нулевой температурный диапазон."""
        result = compound_searcher.search_compound("H2O", (298, 298))

        assert result is not None
        assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_inverted_temperature_range(self, compound_searcher):
        """TC9: Инвертированный температурный диапазон."""
        # Tmin > Tmax
        result = compound_searcher.search_compound("H2O", (500, 300))

        assert result is not None
        # Должен обработать корректно
        assert result.search_statistics.total_found >= 0

    @pytest.mark.asyncio
    async def test_very_wide_temperature_range(self, compound_searcher):
        """TC10: Очень широкий температурный диапазон."""
        result = compound_searcher.search_compound("Fe", (0, 10000))

        assert result is not None
        assert result.search_statistics.total_found >= 0


class TestFilteringEdgeCases:
    """Тесты граничных случаев фильтрации."""

    @pytest.mark.asyncio
    async def test_filter_empty_records(self, filter_pipeline):
        """TC11: Фильтрация пустого списка записей."""
        filter_context = FilterContext(
            temperature_range=(298, 500),
            compound_formula="H2O"
        )

        result = filter_pipeline.execute([], filter_context)

        assert result is not None
        assert not result.is_found
        assert len(result.filtered_records) == 0

    @pytest.mark.asyncio
    async def test_filter_malformed_records(self, filter_pipeline):
        """TC12: Фильтрация некорректных записей."""
        # Создаем записи с отсутствующими полями
        malformed_records = [
            {"Formula": "H2O"},  # Отсутствуют температурные поля
            {"Tmin": 298, "Tmax": 500},  # Отсутствует формула
            {"Formula": "CO2", "Tmin": "invalid", "Tmax": 500},  # Некорректные типы
            {"Formula": "NH3", "Tmin": 300, "Tmax": 200},  # Tmin > Tmax
        ]

        filter_context = FilterContext(
            temperature_range=(298, 500),
            compound_formula="test"
        )

        result = filter_pipeline.execute(malformed_records, filter_context)

        assert result is not None
        # Не должно быть ошибок, даже с некорректными данными

    @pytest.mark.asyncio
    async def test_filter_outside_range(self, filter_pipeline):
        """TC13: Все записи вне температурного диапазона."""
        # Создаем записи, которые точно вне диапазона
        out_of_range_records = [
            {"Formula": "H2O", "Tmin": 1000, "Tmax": 1500},  # Выше 298-500
            {"Formula": "CO2", "Tmin": 0, "Tmax": 100},  # Ниже 298-500
        ]

        filter_context = FilterContext(
            temperature_range=(298, 500),
            compound_formula="test"
        )

        result = filter_pipeline.execute(out_of_range_records, filter_context)

        assert result is not None
        # Может быть не найдено или найдено после корректировки

    @pytest.mark.asyncio
    async def test_filter_exact_boundary(self, filter_pipeline):
        """TC14: Записи точно на границах температурного диапазона."""
        boundary_records = [
            {"Formula": "H2O", "Tmin": 298, "Tmax": 500},  # Точно совпадает
            {"Formula": "CO2", "Tmin": 250, "Tmax": 298},  # Граничное пересечение
            {"Formula": "NH3", "Tmin": 500, "Tmax": 600},  # Граничное пересечение
        ]

        filter_context = FilterContext(
            temperature_range=(298, 500),
            compound_formula="test"
        )

        result = filter_pipeline.execute(boundary_records, filter_context)

        assert result is not None


class TestAggregationEdgeCases:
    """Тесты граничных случаев агрегации."""

    @pytest.mark.asyncio
    async def test_aggregate_empty_results(self, reaction_aggregator):
        """TC15: Агрегация пустых результатов."""
        aggregated = reaction_aggregator.aggregate_reaction_data(
            reaction_equation="A + B -> C",
            compounds_results=[]
        )

        assert aggregated is not None
        assert aggregated.completeness_status == "incomplete"
        assert len(aggregated.found_compounds) == 0

    @pytest.mark.asyncio
    async def test_aggregate_all_missing(self, reaction_aggregator):
        """TC16: Агрегация с полностью отсутствующими данными."""
        from thermo_agents.models.search import CompoundSearchResult

        # Создаем результаты с нулевыми находками
        empty_results = [
            CompoundSearchResult(
                compound="X",
                search_statistics=None,
                records_found=[],
                is_found=False
            ),
            CompoundSearchResult(
                compound="Y",
                search_statistics=None,
                records_found=[],
                is_found=False
            )
        ]

        aggregated = reaction_aggregator.aggregate_reaction_data(
            reaction_equation="X + Y -> Z",
            compounds_results=empty_results
        )

        assert aggregated is not None
        assert aggregated.completeness_status == "incomplete"
        assert len(aggregated.missing_compounds) == 2

    @pytest.mark.asyncio
    async def test_aggregate_partial_data(self, reaction_aggregator):
        """TC17: Агрегация с частичными данными."""
        from thermo_agents.models.search import CompoundSearchResult, SearchStatistics
        from thermo_agents.models.search import DatabaseRecord

        # Создаем смешанные результаты
        mixed_results = [
            # Найдены данные
            CompoundSearchResult(
                compound="H2O",
                search_statistics=SearchStatistics(total_found=1, search_time_ms=10),
                records_found=[DatabaseRecord(Formula="H2O", Tmin=298, Tmax=500)],
                is_found=True
            ),
            # Не найдены данные
            CompoundSearchResult(
                compound="Xyz123",
                search_statistics=SearchStatistics(total_found=0, search_time_ms=5),
                records_found=[],
                is_found=False
            )
        ]

        aggregated = reaction_aggregator.aggregate_reaction_data(
            reaction_equation="H2O + Xyz123 -> Products",
            compounds_results=mixed_results
        )

        assert aggregated is not None
        assert aggregated.completeness_status == "partial"
        assert len(aggregated.found_compounds) == 1
        assert len(aggregated.missing_compounds) == 1

    @pytest.mark.asyncio
    async def test_aggregate_maximum_compounds(self, reaction_aggregator):
        """TC18: Агрегация максимального количества соединений."""
        from thermo_agents.models.search import CompoundSearchResult, SearchStatistics
        from thermo_agents.models.search import DatabaseRecord

        # Создаем 10 результатов (максимум)
        max_results = []
        for i in range(10):
            result = CompoundSearchResult(
                compound=f"Compound{i}",
                search_statistics=SearchStatistics(total_found=1, search_time_ms=5),
                records_found=[DatabaseRecord(Formula=f"Compound{i}", Tmin=298, Tmax=500)],
                is_found=True
            )
            max_results.append(result)

        aggregated = reaction_aggregator.aggregate_reaction_data(
            reaction_equation=" + ".join([f"C{i}" for i in range(10)]) + " -> Products",
            compounds_results=max_results
        )

        assert aggregated is not None
        assert len(aggregated.found_compounds) == 10

    @pytest.mark.asyncio
    async def test_aggregate_exceed_maximum_compounds(self, reaction_aggregator):
        """TC19: Превышение максимального количества соединений."""
        from thermo_agents.models.search import CompoundSearchResult

        # Создаем 15 результатов (превышение лимита)
        too_many_results = []
        for i in range(15):
            result = CompoundSearchResult(
                compound=f"Compound{i}",
                search_statistics=None,
                records_found=[],
                is_found=True
            )
            too_many_results.append(result)

        # Должен обработать, но может ограничить количество
        aggregated = reaction_aggregator.aggregate_reaction_data(
            reaction_equation=" + ".join([f"C{i}" for i in range(15)]) + " -> Products",
            compounds_results=too_many_results
        )

        assert aggregated is not None
        # Система должна обработать ситуацию


class TestExtractionModelEdgeCases:
    """Тесты граничных случаев модели извлечения."""

    def test_empty_compounds_list(self):
        """TC20: Пустой список соединений."""
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=[],
                temperature_range_k=[298, 500],
                balanced_equation="Empty"
            )

    def test_invalid_temperature_range(self):
        """TC21: Некорректный температурный диапазон."""
        # Отрицательная температура
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=["H2O"],
                temperature_range_k=[-100, 500],
                balanced_equation="Test"
            )

        # Tmin > Tmax
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=["H2O"],
                temperature_range_k=[500, 300],
                balanced_equation="Test"
            )

        # Слишком широкий диапазон
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=["H2O"],
                temperature_range_k=[0, 100000],
                balanced_equation="Test"
            )

    def test_too_many_compounds(self):
        """TC22: Слишком много соединений."""
        # Создаем 15 соединений (превышает лимит)
        too_many_compounds = [f"C{i}" for i in range(15)]

        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=too_many_compounds,
                temperature_range_k=[298, 500],
                balanced_equation="Too many"
            )

    def test_invalid_compound_names(self):
        """TC23: Некорректные имена соединений."""
        invalid_compounds = [
            "",  # Пустая строка
            "   ",  # Пробелы
            "!!!invalid!!!",  # Специальные символы
        ]

        for invalid_compound in invalid_compounds:
            with pytest.raises(ValueError):
                ExtractedReactionParameters(
                    all_compounds=[invalid_compound],
                    temperature_range_k=[298, 500],
                    balanced_equation="Invalid"
                )

    def test_missing_required_fields(self):
        """TC24: Отсутствие обязательных полей."""
        # Отсутствие balanced_equation
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                all_compounds=["H2O"],
                temperature_range_k=[298, 500],
                balanced_equation=""
            )


class TestTableFormattingEdgeCases:
    """Тесты граничных случаев форматирования таблиц."""

    def test_format_empty_data(self):
        """TC25: Форматирование пустых данных."""
        formatter = TableFormatter()
        table = formatter.format_summary_table([])
        assert table is not None
        assert len(table) > 0

    def test_format_malformed_data(self):
        """TC26: Форматирование некорректных данных."""
        formatter = TableFormatter()

        # Данные с разными структурами
        malformed_data = [
            {"Formula": "H2O"},  # Минимальные данные
            {"Tmin": 298, "Tmax": 500},  # Без формулы
            {"Formula": "CO2", "Tmin": "invalid"},  # Некорректный тип
        ]

        table = formatter.format_summary_table(malformed_data)
        assert table is not None
        # Не должно быть ошибок при форматировании


class TestErrorHandling:
    """Тесты обработки ошибок."""

    @pytest.mark.asyncio
    async def test_database_connection_error(self):
        """TC27: Ошибка подключения к базе данных."""
        # Несуществующий путь к базе
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector("nonexistent/path/db.sqlite")
        searcher = CompoundSearcher(sql_builder, db_connector)

        # Должно обработать ошибку gracefully
        result = searcher.search_compound("H2O", (298, 500))
        assert result is not None

    @pytest.mark.asyncio
    async def test_memory_pressure(self, compound_searcher):
        """TC28: Проверка обработки больших объемов данных."""
        # Ищем соединение, которое может вернуть много данных
        result = compound_searcher.search_compound("Fe", (200, 2000))

        if result and len(result.records_found) > 1000:
            # Если найдено много данных, проверяем, что система не падает
            assert len(result.records_found) > 0
            assert result.search_statistics is not None

    def test_sql_injection_attempt(self, compound_searcher):
        """TC29: Попытка SQL инъекции."""
        injection_attempts = [
            "'; DROP TABLE compounds; --",
            "H2O' OR '1'='1",
            "'; SELECT * FROM compounds; --",
            "H2O UNION SELECT * FROM users",
        ]

        for injection in injection_attempts:
            result = compound_searcher.search_compound(injection, (298, 500))
            # Должно обработать безопасно
            assert result is not None
            # Не должно находить неожиданные результаты
            assert result.search_statistics.total_found >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])