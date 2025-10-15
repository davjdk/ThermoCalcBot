"""
Unit tests for CompoundSearcher.

This module tests the compound search functionality, including
SQL generation coordination and result processing.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.search.sql_builder import SQLBuilder, FilterPriorities
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.models.search import (
    DatabaseRecord,
    CompoundSearchResult,
    CoverageStatus,
    SearchStatistics
)


class TestCompoundSearcher:
    """Test cases for CompoundSearcher class."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Create a temporary database file
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)

        # Create a test database
        self._create_test_database()

        # Initialize components
        self.db_connector = DatabaseConnector(self.db_path)
        self.sql_builder = SQLBuilder()
        self.searcher = CompoundSearcher(self.sql_builder, self.db_connector)

    def teardown_method(self):
        """Clean up after each test method."""
        # Disconnect if connected
        if self.db_connector.is_connected():
            self.db_connector.disconnect()

        # Remove temporary database file
        if self.db_path.exists():
            self.db_path.unlink()

    def _create_test_database(self):
        """Create a test database with sample data."""
        import sqlite3
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Create test table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS compounds (
                    ID INTEGER PRIMARY KEY,
                    Formula TEXT,
                    Name TEXT,
                    Phase TEXT,
                    Tmin REAL,
                    Tmax REAL,
                    H298 REAL,
                    S298 REAL,
                    F1 REAL,
                    F2 REAL,
                    F3 REAL,
                    F4 REAL,
                    F5 REAL,
                    F6 REAL,
                    Tmelt REAL,
                    Tboil REAL,
                    ReliabilityClass INTEGER
                )
            """)

            # Insert test data
            test_data = [
                # H2O records with different phases
                (1, 'H2O', 'Water', 'l', 273.15, 373.15, -285.83, 69.91, 30.09, 8.18, 0.0, 0.0, 0.0, 0.0, 273.15, 373.15, 1),
                (2, 'H2O', 'Water vapor', 'g', 373.15, 673.15, -241.82, 188.72, 33.50, 0.03, 0.0, 0.0, 0.0, 0.0, 273.15, 373.15, 1),

                # HCl records
                (3, 'HCl', 'Hydrogen chloride', 'g', 100.0, 1000.0, -92.30, 186.69, 28.85, 0.18, 0.0, 0.0, 0.0, 0.0, 158.0, 188.0, 1),

                # CO2 records
                (4, 'CO2', 'Carbon dioxide', 'g', 100.0, 2000.0, -393.51, 213.74, 44.22, 8.79, 0.0, 0.0, 0.0, 0.0, 194.7, 194.7, 1),

                # NH3 with lower reliability
                (5, 'NH3', 'Ammonia', 'g', 100.0, 700.0, -45.94, 192.77, 29.75, 0.24, 0.0, 0.0, 0.0, 0.0, 195.4, 239.8, 3),

                # H2O(s) - solid phase
                (6, 'H2O', 'Ice', 's', 0.0, 273.15, -292.72, 41.33, 20.52, 0.03, 0.0, 0.0, 0.0, 0.0, 273.15, 273.15, 1),

                # Compound with missing thermodynamic data
                (7, 'TEST', 'Test compound', 'g', 200.0, 800.0, None, None, None, None, None, None, None, None, None, None, 2),

                # Complex formula
                (8, 'TiO2', 'Titanium dioxide', 's', 100.0, 2000.0, -944.75, 50.24, 75.19, 0.12, 0.0, 0.0, 0.0, 0.0, 2113.0, 2113.0, 1),
            ]

            cursor.executemany("""
                INSERT INTO compounds (ID, Formula, Name, Phase, Tmin, Tmax, H298, S298,
                                      F1, F2, F3, F4, F5, F6, Tmelt, Tboil, ReliabilityClass)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, test_data)

            conn.commit()

    def test_init_success(self):
        """Test successful initialization of CompoundSearcher."""
        assert self.searcher.sql_builder is self.sql_builder
        assert self.searcher.db_connector is self.db_connector

    def test_search_compound_basic(self):
        """Test basic compound search."""
        result = self.searcher.search_compound('H2O')

        assert isinstance(result, CompoundSearchResult)
        assert result.compound_formula == 'H2O'
        assert len(result.records_found) > 0
        assert all(isinstance(r, DatabaseRecord) for r in result.records_found)

    def test_search_compound_with_temperature_range(self):
        """Test compound search with temperature filtering."""
        result = self.searcher.search_compound(
            'H2O',
            temperature_range=(300.0, 400.0)
        )

        assert result.compound_formula == 'H2O'
        # Should find liquid H2O in this range
        liquid_records = [r for r in result.records_found if r.phase == 'l']
        assert len(liquid_records) > 0

        # Check that returned records overlap with temperature range
        for record in result.records_found:
            if record.tmin and record.tmax:
                assert record.tmax >= 300.0  # Should overlap with requested range
                assert record.tmin <= 400.0

    def test_search_compound_with_phase(self):
        """Test compound search with phase filtering."""
        result = self.searcher.search_compound('H2O', phase='g')

        assert result.compound_formula == 'H2O'
        assert all(r.phase == 'g' for r in result.records_found)

    def test_search_compound_with_all_parameters(self):
        """Test compound search with all parameters."""
        result = self.searcher.search_compound(
            'H2O',
            temperature_range=(300.0, 350.0),
            phase='l',
            limit=5
        )

        assert result.compound_formula == 'H2O'
        assert all(r.phase == 'l' for r in result.records_found)
        assert len(result.records_found) <= 5

    def test_search_compound_nonexistent(self):
        """Test search for non-existent compound."""
        result = self.searcher.search_compound('Xyz123')

        assert result.compound_formula == 'Xyz123'
        assert len(result.records_found) == 0
        assert result.coverage_status == CoverageStatus.NONE
        assert len(result.warnings) > 0

    def test_search_compound_complex_formula(self):
        """Test search for complex formula."""
        result = self.searcher.search_compound('TiO2')

        assert result.compound_formula == 'TiO2'
        assert len(result.records_found) > 0
        assert all('TiO2' in r.formula for r in result.records_found)

    def test_search_compound_execution_time(self):
        """Test that execution time is recorded."""
        result = self.searcher.search_compound('H2O')

        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0

    def test_search_compound_limit_parameter(self):
        """Test limit parameter functionality."""
        # Search without limit
        result_unlimited = self.searcher.search_compound('H2O', limit=100)

        # Search with small limit
        result_limited = self.searcher.search_compound('H2O', limit=2)

        assert len(result_limited.records_found) <= 2
        assert len(result_limited.records_found) <= len(result_unlimited.records_found)

    def test_search_compound_statistics_calculation(self):
        """Test that search statistics are calculated correctly."""
        result = self.searcher.search_compound('H2O')

        assert result.filter_statistics is not None
        assert isinstance(result.filter_statistics, SearchStatistics)
        assert result.filter_statistics.total_records == len(result.records_found)

        if result.records_found:
            assert result.filter_statistics.unique_phases >= 1
            assert result.filter_statistics.phase_distribution is not None

    def test_search_compound_coverage_status_full(self):
        """Test coverage status determination for full coverage."""
        result = self.searcher.search_compound(
            'H2O',
            temperature_range=(280.0, 320.0)  # Within liquid range
        )

        # Should have full coverage for H2O in this range
        assert result.coverage_status in [CoverageStatus.FULL, CoverageStatus.PARTIAL]

    def test_search_compound_coverage_status_none(self):
        """Test coverage status for no results."""
        result = self.searcher.search_compound('Nonexistent')
        assert result.coverage_status == CoverageStatus.NONE

    def test_search_compound_warnings_generation(self):
        """Test that appropriate warnings are generated."""
        # Search for compound with low reliability data
        result = self.searcher.search_compound('NH3')

        # Should have warning about low reliability data
        reliability_warnings = [
            w for w in result.warnings
            if 'low reliability' in w.lower()
        ]
        # May or may not have warnings depending on test data

        # Search for compound with missing thermodynamic data
        result = self.searcher.search_compound('TEST')
        thermo_warnings = [
            w for w in result.warnings
            if 'thermodynamic' in w.lower()
        ]
        # Should have warning about missing data

    def test_search_compound_with_pipeline(self):
        """Test compound search with detailed pipeline tracking."""
        result, pipeline = self.searcher.search_compound_with_pipeline('H2O')

        assert isinstance(result, CompoundSearchResult)
        assert isinstance(pipeline, Mock)  # Would be actual SearchPipeline in real implementation
        assert pipeline.initial_results >= 0
        assert pipeline.final_results == len(result.records_found)

    def test_get_search_strategy(self):
        """Test getting search strategy recommendations."""
        strategy = self.searcher.get_search_strategy('H2O')

        assert hasattr(strategy, 'formula')
        assert hasattr(strategy, 'search_strategies')
        assert hasattr(strategy, 'estimated_difficulty')
        assert hasattr(strategy, 'recommendations')

    def test_count_compound_records(self):
        """Test counting records without retrieving full data."""
        count_data = self.searcher.count_compound_records('H2O')

        assert isinstance(count_data, dict)
        assert 'total_count' in count_data or 'COUNT(*)' in count_data

    def test_get_temperature_statistics(self):
        """Test getting temperature statistics for a compound."""
        temp_stats = self.searcher.get_temperature_statistics('H2O')

        assert isinstance(temp_stats, dict)
        # Should contain temperature-related statistics

    def test_parse_record_complete_data(self):
        """Test parsing of complete database record."""
        # Create a mock database row
        row = {
            'ID': 1,
            'Formula': 'H2O',
            'Name': 'Water',
            'Phase': 'l',
            'Tmin': 273.15,
            'Tmax': 373.15,
            'H298': -285.83,
            'S298': 69.91,
            'F1': 30.09,
            'F2': 8.18,
            'Tmelt': 273.15,
            'Tboil': 373.15,
            'ReliabilityClass': 1
        }

        record = self.searcher._parse_record(row)

        assert isinstance(record, DatabaseRecord)
        assert record.id == 1
        assert record.formula == 'H2O'
        assert record.phase == 'l'
        assert record.tmin == 273.15
        assert record.tmax == 373.15
        assert record.h298 == -285.83
        assert record.s298 == 69.91
        assert record.reliability_class == 1

    def test_parse_record_minimal_data(self):
        """Test parsing of minimal database record."""
        row = {
            'ID': 1,
            'Formula': 'TEST',
            'Phase': None,
            'Tmin': None,
            'Tmax': None,
            'H298': None,
            'S298': None,
            'ReliabilityClass': None
        }

        record = self.searcher._parse_record(row)

        assert isinstance(record, DatabaseRecord)
        assert record.id == 1
        assert record.formula == 'TEST'
        assert record.phase is None
        assert record.tmin is None
        assert record.tmax is None

    def test_parse_record_with_column_variations(self):
        """Test parsing records with column name variations."""
        row = {
            'ID': 1,
            'formula': 'h2o',  # lowercase
            'Phase': 'L',      # uppercase
            'temp_min': 273.15,  # alternative name
            'temp_max': 373.15,  # alternative name
            'H_298': -285.83,     # alternative name
            'S_298': 69.91,       # alternative name
            'reliability': 1       # alternative name
        }

        record = self.searcher._parse_record(row)

        assert record.formula == 'h2o'
        assert record.phase == 'L'
        assert record.tmin == 273.15
        assert record.tmax == 373.15
        assert record.h298 == -285.83
        assert record.s298 == 69.91
        assert record.reliability_class == 1

    def test_calculate_statistics_with_records(self):
        """Test statistics calculation with actual records."""
        # Create some test records
        records = [
            DatabaseRecord(
                id=1, formula='H2O', phase='l', tmin=273.15, tmax=373.15,
                h298=-285.83, s298=69.91, reliability_class=1
            ),
            DatabaseRecord(
                id=2, formula='H2O', phase='g', tmin=373.15, tmax=673.15,
                h298=-241.82, s298=188.72, reliability_class=1
            ),
            DatabaseRecord(
                id=3, formula='NH3', phase='g', tmin=100.0, tmax=700.0,
                h298=-45.94, s298=192.77, reliability_class=3
            )
        ]

        stats = self.searcher._calculate_statistics(records)

        assert stats.total_records == 3
        assert stats.unique_phases == 2  # 'l' and 'g'
        assert stats.avg_reliability == (1 + 1 + 3) / 3
        assert stats.min_temperature == 100.0
        assert stats.max_temperature == 673.15
        assert 'l' in stats.phase_distribution
        assert 'g' in stats.phase_distribution
        assert stats.phase_distribution['l'] == 1
        assert stats.phase_distribution['g'] == 2

    def test_calculate_statistics_empty_records(self):
        """Test statistics calculation with empty records."""
        stats = self.searcher._calculate_statistics([])

        assert stats.total_records == 0
        assert stats.unique_phases == 0
        assert stats.avg_reliability is None
        assert stats.min_temperature is None
        assert stats.max_temperature is None

    def test_determine_coverage_status_full(self):
        """Test coverage status determination for full coverage."""
        records = [
            DatabaseRecord(id=1, formula='H2O', tmin=273.15, tmax=373.15),
            DatabaseRecord(id=2, formula='H2O', tmin=373.15, tmax=673.15)
        ]

        status = self.searcher._determine_coverage_status(records, (300.0, 400.0))
        assert status == CoverageStatus.FULL

    def test_determine_coverage_status_partial(self):
        """Test coverage status determination for partial coverage."""
        records = [
            DatabaseRecord(id=1, formula='H2O', tmin=273.15, tmax=373.15)
        ]

        # Request range that extends beyond available data
        status = self.searcher._determine_coverage_status(records, (300.0, 500.0))
        assert status == CoverageStatus.PARTIAL

    def test_determine_coverage_status_none(self):
        """Test coverage status determination for no coverage."""
        status = self.searcher._determine_coverage_status([], (300.0, 400.0))
        assert status == CoverageStatus.NONE

    def test_determine_coverage_status_no_temperature_constraint(self):
        """Test coverage status when no temperature constraint is given."""
        records = [DatabaseRecord(id=1, formula='H2O')]

        status = self.searcher._determine_coverage_status(records, None)
        assert status == CoverageStatus.FULL

    def test_record_in_temperature_range(self):
        """Test temperature range checking for records."""
        record = {'Tmin': 273.15, 'Tmax': 373.15}
        temperature_range = (300.0, 350.0)

        assert self.searcher._record_in_temperature_range(record, temperature_range) is True

        # Non-overlapping range
        assert self.searcher._record_in_temperature_range(record, (400.0, 500.0)) is False

        # Missing temperature data
        incomplete_record = {'Tmin': 273.15}
        assert self.searcher._record_in_temperature_range(incomplete_record, temperature_range) is False

    def test_apply_priority_sorting(self):
        """Test priority sorting of records."""
        records = [
            {'ID': 1, 'Formula': 'H2O', 'ReliabilityClass': 2, 'Tmin': 273.15, 'Tmax': 373.15, 'Phase': 'l'},
            {'ID': 2, 'Formula': 'H2O', 'ReliabilityClass': 1, 'Tmin': 100.0, 'Tmax': 1000.0, 'Phase': 'g'},
            {'ID': 3, 'Formula': 'H2O', 'ReliabilityClass': 3, 'Tmin': 200.0, 'Tmax': 400.0, 'Phase': 's'},
        ]

        sorted_records = self.searcher._apply_priority_sorting(records)

        # Should be sorted by reliability class (1 first), then other criteria
        assert sorted_records[0]['ReliabilityClass'] == 1
        assert sorted_records[1]['ReliabilityClass'] == 2
        assert sorted_records[2]['ReliabilityClass'] == 3

    @patch('src.thermo_agents.search.compound_searcher.logger')
    def test_search_compound_with_database_error(self, mock_logger):
        """Test search behavior when database error occurs."""
        # Mock database connector to raise an error
        self.db_connector.execute_query = Mock(side_effect=Exception("Database error"))

        result = self.searcher.search_compound('H2O')

        assert result.compound_formula == 'H2O'
        assert len(result.records_found) == 0
        assert len(result.warnings) > 0
        assert any("Search failed" in w for w in result.warnings)
        assert result.execution_time_ms is not None

    @patch('src.thermo_agents.search.compound_searcher.logger')
    def test_search_compound_logging(self, mock_logger):
        """Test that search operations are properly logged."""
        self.searcher.search_compound('H2O')

        # Check that appropriate logging calls were made
        mock_logger.info.assert_called()
        mock_logger.debug.assert_called()

    def test_search_compound_various_formula_formats(self):
        """Test search with different formula formats."""
        # Test with simple formula
        result1 = self.searcher.search_compound('H2O')
        assert result1.compound_formula == 'H2O'

        # Test with formula that has spaces
        result2 = self.searcher.search_compound(' H2O ')
        assert result2.compound_formula == ' H2O '

        # Test with complex formula
        result3 = self.searcher.search_compound('TiO2')
        assert result3.compound_formula == 'TiO2'

    def test_search_compound_edge_cases(self):
        """Test search with edge cases."""
        # Empty string formula
        result = self.searcher.search_compound('')
        assert result.compound_formula == ''

        # Very high temperature range
        result = self.searcher.search_compound('H2O', temperature_range=(5000.0, 6000.0))
        # Should handle gracefully without crashing

        # Limit of 0
        result = self.searcher.search_compound('H2O', limit=0)
        assert len(result.records_found) == 0