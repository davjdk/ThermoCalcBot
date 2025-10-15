"""
Unit-тесты для ReactionAggregator.
"""

import pytest
from src.thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from src.thermo_agents.models.search import CompoundSearchResult, DatabaseRecord
from src.thermo_agents.models.aggregation import FilterStatistics


@pytest.fixture
def mock_database_record():
    """Mock запись базы данных."""
    return DatabaseRecord(
        id=1,
        formula="H2O(l)",
        phase="l",
        tmin=273.15,
        tmax=373.15,
        h298=-285.83,
        s298=69.95,
        f1=30.09,
        f2=6.83,
        f3=6.28,
        f4=-2.78,
        f5=0.0,
        f6=0.0,
        tmelt=273.15,
        tboil=373.15,
        reliability_class=1
    )


@pytest.fixture
def mock_filter_statistics_success():
    """Mock успешной статистики фильтрации."""
    return FilterStatistics(
        stage_1_initial_matches=5,
        stage_2_temperature_filtered=3,
        stage_2_description="Температурная фильтрация (298K)",
        stage_3_phase_selected=1,
        stage_3_description="Выбор жидкой фазы",
        stage_4_final_selected=1,
        is_found=True
    )


@pytest.fixture
def mock_filter_statistics_failure():
    """Mock провальной статистики фильтрации."""
    return FilterStatistics(
        stage_1_initial_matches=0,
        stage_2_temperature_filtered=0,
        stage_2_description="Температурная фильтрация (298K)",
        stage_3_phase_selected=0,
        stage_3_description="Выбор фазы",
        stage_4_final_selected=0,
        is_found=False,
        failure_stage=1,
        failure_reason="Вещество не найдено в базе данных"
    )


@pytest.fixture
def mock_compound_search_result(mock_database_record):
    """Mock результат поиска по веществу."""
    # Создать SearchStatistics вместо FilterStatistics
    from src.thermo_agents.models.search import SearchStatistics

    search_stats = SearchStatistics(
        total_records=5,
        unique_phases=1,
        temperature_coverage=1.0,
        avg_reliability=1.0,
        min_temperature=273.15,
        max_temperature=373.15,
        avg_temperature_range=100.0
    )

    return CompoundSearchResult(
        compound_formula="H2O",
        records_found=[mock_database_record],
        coverage_status="complete",
        filter_statistics=search_stats
    )


@pytest.fixture
def reaction_aggregator():
    """Экземпляр ReactionAggregator для тестов."""
    return ReactionAggregator(max_compounds=10)


class TestReactionAggregator:
    """Тесты для ReactionAggregator."""

    def test_successful_aggregation_complete(
        self,
        reaction_aggregator,
        mock_compound_search_result
    ):
        """Тест успешной агрегации для полного набора данных."""
        reaction_equation = "H2 + O2 → H2O"
        compounds_results = [mock_compound_search_result]

        result = reaction_aggregator.aggregate_reaction_data(
            reaction_equation, compounds_results
        )

        assert result.reaction_equation == reaction_equation
        assert len(result.compounds_data) == 1
        assert result.completeness_status == "complete"
        assert len(result.found_compounds) == 1
        assert len(result.missing_compounds) == 0
        assert result.get_completeness_percentage() == 100.0

    def test_partial_aggregation(
        self,
        reaction_aggregator,
        mock_compound_search_result
    ):
        """Тест частичной агрегации (некоторые вещества не найдены)."""
        # Создать результат для ненайденного вещества
        missing_result = CompoundSearchResult(
            compound_formula="UnknownCompound",
            records_found=[],
            coverage_status="none",
            warnings=["Вещество не найдено"],
            filter_statistics=None
        )

        reaction_equation = "H2 + O2 → H2O + UnknownCompound"
        compounds_results = [mock_compound_search_result, missing_result]

        result = reaction_aggregator.aggregate_reaction_data(
            reaction_equation, compounds_results
        )

        assert result.completeness_status == "partial"
        assert len(result.found_compounds) == 1
        assert len(result.missing_compounds) == 1
        assert result.get_completeness_percentage() == 50.0
        assert "UnknownCompound" in result.missing_compounds

    def test_incomplete_aggregation(
        self,
        reaction_aggregator
    ):
        """Тест полной агрегации (все вещества не найдены)."""
        missing_result = CompoundSearchResult(
            compound_formula="UnknownCompound",
            records_found=[],
            coverage_status="none",
            warnings=["Вещество не найдено"],
            filter_statistics=None
        )

        reaction_equation = "A + B → C"
        compounds_results = [missing_result]

        result = reaction_aggregator.aggregate_reaction_data(
            reaction_equation, compounds_results
        )

        assert result.completeness_status == "incomplete"
        assert len(result.found_compounds) == 0
        assert len(result.missing_compounds) == 1
        assert result.get_completeness_percentage() == 0.0

    def test_max_compounds_validation(self, reaction_aggregator):
        """Тест валидации максимального количества веществ."""
        # Создать 11 результатов (превышение лимита в 10)
        compounds_results = []
        for i in range(11):
            result = CompoundSearchResult(
                compound_formula=f"Compound{i}",
                records_found=[],
                coverage_status="none",
                filter_statistics=None
            )
            compounds_results.append(result)

        with pytest.raises(ValueError, match="Превышено максимальное количество веществ"):
            reaction_aggregator.aggregate_reaction_data(
                "A + B → C", compounds_results
            )

    def test_warnings_generation(
        self,
        reaction_aggregator,
        mock_database_record,
        mock_filter_statistics_success
    ):
        """Тест генерации предупреждений."""
        # Создать запись с низким классом надёжности
        low_reliability_record = DatabaseRecord(
            id=2,
            formula="CO2(g)",
            phase="g",
            tmin=200.0,
            tmax=500.0,
            h298=-393.51,
            s298=213.74,
            f1=44.22,
            f2=8.79,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=194.65,
            tboil=194.65,
            reliability_class=4  # Низкий класс
        )

        # Создать результат с частичным покрытием
        from src.thermo_agents.models.search import SearchStatistics

        search_stats = SearchStatistics(
            total_records=3,
            unique_phases=1,
            temperature_coverage=0.5,
            avg_reliability=4.0,
            min_temperature=200.0,
            max_temperature=500.0,
            avg_temperature_range=300.0
        )

        partial_result = CompoundSearchResult(
            compound_formula="CO2",
            records_found=[low_reliability_record],
            coverage_status="partial",
            warnings=["Существуют данные только для ограниченного температурного диапазона"],
            filter_statistics=search_stats
        )

        result = reaction_aggregator.aggregate_reaction_data(
            "CO2 + H2O → H2CO3", [partial_result]
        )

        assert len(result.warnings) >= 2  # Предупреждение о покрытии и надёжности
        assert "частичное покрытие" in result.warnings[0]
        assert "низкий класс надёжности" in " ".join(result.warnings)

    def test_recommendations_generation(
        self,
        reaction_aggregator,
        mock_compound_search_result,
        mock_filter_statistics_failure
    ):
        """Тест генерации рекомендаций."""
        missing_result = CompoundSearchResult(
            compound_formula="UnknownCompound",
            records_found=[],
            coverage_status="none",
            warnings=[],
            filter_statistics=mock_filter_statistics_failure
        )

        result = reaction_aggregator.aggregate_reaction_data(
            "H2O + UnknownCompound → Product",
            [mock_compound_search_result, missing_result]
        )

        assert len(result.recommendations) >= 1
        assert "UnknownCompound" in result.recommendations[0]

    def test_validate_compound_results_success(
        self,
        reaction_aggregator,
        mock_compound_search_result
    ):
        """Тест валидации успешных результатов."""
        errors = reaction_aggregator.validate_compound_results([mock_compound_search_result])
        assert len(errors) == 0

    def test_validate_compound_results_errors(self, reaction_aggregator):
        """Тест валидации результатов с ошибками."""
        # Создать некорректный результат
        invalid_result = CompoundSearchResult(
            compound_formula="",  # Пустая формула
            records_found=[],
            coverage_status="none",
            filter_statistics=None  # Отсутствует статистика
        )

        errors = reaction_aggregator.validate_compound_results([invalid_result])
        assert len(errors) >= 1
        assert any("отсутствует формула" in error for error in errors)