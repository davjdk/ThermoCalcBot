"""
Unit-тесты для TableFormatter.
"""

import pytest
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.models.search import CompoundSearchResult, DatabaseRecord
from thermo_agents.models.aggregation import FilterStatistics


@pytest.fixture
def mock_database_record_h2o():
    """Mock запись базы данных для H2O."""
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
def mock_database_record_co2():
    """Mock запись базы данных для CO2."""
    return DatabaseRecord(
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
        reliability_class=2
    )


@pytest.fixture
def mock_database_record_incomplete():
    """Mock неполной записи базы данных."""
    return DatabaseRecord(
        id=3,
        formula="NH3(aq)",
        phase="aq",
        tmin=273.15,
        tmax=373.15,
        h298=-80.29,
        s298=111.30,
        f1=25.87,
        f2=33.00,
        f3=-3.05,
        f4=0.0,
        f5=0.0,
        f6=0.0,
        tmelt=195.40,
        tboil=239.82,
        reliability_class=3
    )


@pytest.fixture
def mock_compound_search_results(
    mock_database_record_h2o,
    mock_database_record_co2,
    mock_database_record_incomplete
):
    """Mock результаты поиска по веществам."""
    from thermo_agents.models.search import SearchStatistics

    mock_stats = SearchStatistics(
        total_records=5,
        unique_phases=1,
        temperature_coverage=1.0,
        avg_reliability=1.0,
        min_temperature=273.15,
        max_temperature=373.15,
        avg_temperature_range=100.0
    )

    return [
        CompoundSearchResult(
            compound_formula="H2O",
            records_found=[mock_database_record_h2o],
            coverage_status="complete",
            filter_statistics=mock_stats
        ),
        CompoundSearchResult(
            compound_formula="CO2",
            records_found=[mock_database_record_co2],
            coverage_status="complete",
            filter_statistics=mock_stats
        ),
        CompoundSearchResult(
            compound_formula="NH3",
            records_found=[mock_database_record_incomplete],
            coverage_status="partial",
            warnings=["Неполные данные"],
            filter_statistics=mock_stats
        )
    ]


@pytest.fixture
def table_formatter():
    """Экземпляр TableFormatter для тестов."""
    return TableFormatter()


class TestTableFormatter:
    """Тесты для TableFormatter."""

    def test_format_summary_table_success(
        self,
        table_formatter,
        mock_compound_search_results
    ):
        """Тест успешного форматирования сводной таблицы."""
        result = table_formatter.format_summary_table(mock_compound_search_results)

        assert "Формула" in result
        assert "Фаза" in result
        assert "T_диапазон (K)" in result
        assert "H298 (кДж/моль)" in result
        assert "H2O" in result
        assert "CO2" in result
        assert "NH3" in result
        assert "l" in result  # Фаза воды
        assert "g" in result  # Фаза CO2
        assert "-285.8" in result  # H298 воды
        assert "-393.5" in result  # H298 CO2

    def test_format_summary_table_empty(self, table_formatter):
        """Тест форматирования пустой таблицы."""
        result = table_formatter.format_summary_table([])
        assert result == "Нет данных для отображения"

    def test_format_summary_table_no_records(self, table_formatter):
        """Тест форматирования с результатами без записей."""
        empty_result = CompoundSearchResult(
            compound_formula="Empty",
            records_found=[],
            coverage_status="none",
            filter_statistics=None
        )

        result = table_formatter.format_summary_table([empty_result])
        assert result == "Нет данных для отображения"

    def test_format_detailed_table(
        self,
        table_formatter,
        mock_compound_search_results
    ):
        """Тест форматирования детальной таблицы."""
        result = table_formatter.format_detailed_table(mock_compound_search_results)

        assert "** H2O **" in result
        assert "** CO2 **" in result
        assert "** NH3 **" in result
        assert "Формула" in result
        assert "Фаза" in result

    def test_format_compact_table(
        self,
        table_formatter,
        mock_compound_search_results
    ):
        """Тест форматирования компактной таблицы."""
        result = table_formatter.format_compact_table(mock_compound_search_results)

        assert "Формула" in result
        assert "Фаза" in result
        assert "T_диапазон (K)" in result
        assert "H298 (кДж/моль)" in result
        assert "Надёжность" in result
        assert "H2O" in result
        assert "-285.8" in result
        # Не должно быть колонок с Cp коэффициентами
        assert "Cp_коэффициенты" not in result

    def test_format_formula(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования формулы."""
        result = table_formatter._format_formula(mock_database_record_h2o)
        assert result == "H2O"

    def test_format_formula_without_phase(self, table_formatter):
        """Тест форматирования формулы без фазы."""
        record = DatabaseRecord(
            id=1,
            formula="Fe",
            phase=None,
            tmin=298.0,
            tmax=1800.0,
            h298=0.0,
            s298=27.28,
            f1=23.99,
            f2=8.36,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1811.0,
            tboil=3134.0,
            reliability_class=1
        )

        result = table_formatter._format_formula(record)
        assert result == "Fe"

    def test_format_phase_from_record(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования фазы из записи."""
        result = table_formatter._format_phase(mock_database_record_h2o)
        assert result == "l"

    def test_format_phase_from_formula(self, table_formatter):
        """Тест форматирования фазы из формулы."""
        record = DatabaseRecord(
            id=1,
            formula="Fe(s)",
            phase=None,
            tmin=298.0,
            tmax=1800.0,
            h298=0.0,
            s298=27.28,
            f1=23.99,
            f2=8.36,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1811.0,
            tboil=3134.0,
            reliability_class=1
        )

        result = table_formatter._format_phase(record)
        assert result == "s"

    def test_format_temperature_range_finite(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования конечного температурного диапазона."""
        result = table_formatter._format_temperature_range(mock_database_record_h2o)
        assert result == "273-373"

    def test_format_temperature_range_infinite(self, table_formatter):
        """Тест форматирования бесконечного температурного диапазона."""
        record = DatabaseRecord(
            id=1,
            formula="Ar(g)",
            phase="g",
            tmin=50.0,
            tmax=9999.0,  # Условная бесконечность
            h298=0.0,
            s298=154.84,
            f1=20.79,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=83.81,
            tboil=87.30,
            reliability_class=1
        )

        result = table_formatter._format_temperature_range(record)
        assert result == "50-9999"

    def test_format_h298_value(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования значения H298."""
        result = table_formatter._format_h298(mock_database_record_h2o)
        assert result == "-285.8"

    def test_format_h298_null(self, table_formatter, mock_database_record_incomplete):
        """Тест форматирования пустого значения H298."""
        result = table_formatter._format_h298(mock_database_record_incomplete)
        assert result == "—"

    def test_format_s298_value(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования значения S298."""
        result = table_formatter._format_s298(mock_database_record_h2o)
        assert result == "70.0"

    def test_format_cp_coefficients_full(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования полных коэффициентов теплоёмкости."""
        result = table_formatter._format_cp_coefficients(mock_database_record_h2o)
        assert "30.090" in result  # f1
        assert "6.830" in result   # f2
        assert "6.280" in result   # f3
        assert ", ..." in result

    def test_format_cp_coefficients_simple(self, table_formatter, mock_database_record_co2):
        """Тест форматирования простых коэффициентов теплоёмкости."""
        result = table_formatter._format_cp_coefficients(mock_database_record_co2)
        assert "44.220" in result  # f1
        assert "8.790" in result   # f2
        assert "—" in result        # f3
        assert ", ..." in result

    def test_format_reliability_value(self, table_formatter, mock_database_record_h2o):
        """Тест форматирования класса надёжности."""
        result = table_formatter._format_reliability(mock_database_record_h2o)
        assert result == "1"

    def test_format_reliability_medium(self, table_formatter, mock_database_record_co2):
        """Тест форматирования среднего класса надёжности."""
        result = table_formatter._format_reliability(mock_database_record_co2)
        assert result == "2"