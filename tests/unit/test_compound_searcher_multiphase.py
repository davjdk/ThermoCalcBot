"""
Unit tests for multi-phase search functionality in CompoundSearcher.

Tests cover search_all_phases() method, result building, warning generation,
and phase transition extraction for multi-phase thermodynamic calculations.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import List, Optional

from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.models.search import DatabaseRecord, MultiPhaseSearchResult


class TestCompoundSearcherMultiPhase:
    """Test multi-phase search functionality."""

    @pytest.fixture
    def mock_searcher(self):
        """Create a mock CompoundSearcher for testing."""
        sql_builder = Mock()
        db_connector = Mock()
        session_logger = Mock()

        return CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            session_logger=session_logger,
            static_data_manager=None
        )

    @pytest.fixture
    def feo_records(self) -> List[DatabaseRecord]:
        """Create test FeO records similar to specification example."""
        return [
            DatabaseRecord(
                formula="FeO", phase="s", tmin=298.0, tmax=600.0,
                h298=-265.053, s298=59.807,
                f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
                tmelt=1650.0, tboil=3687.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="FeO", phase="s", tmin=600.0, tmax=900.0,
                h298=0.0, s298=0.0,
                f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
                tmelt=1650.0, tboil=3687.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="FeO", phase="s", tmin=900.0, tmax=1300.0,
                h298=0.0, s298=0.0,
                f1=90.408, f2=-38.021, f3=-83.811, f4=15.358, f5=0.0, f6=0.0,
                tmelt=1650.0, tboil=3687.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
                h298=0.0, s298=0.0,
                f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
                tmelt=1650.0, tboil=3687.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
                h298=24.058, s298=14.581,
                f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1650.0, tboil=3687.0, reliability_class=1
            ),
        ]

    @pytest.fixture
    def records_with_gap(self) -> List[DatabaseRecord]:
        """Create records with a temperature gap for warning testing."""
        return [
            DatabaseRecord(
                formula="X", phase="s", tmin=298.0, tmax=500.0,
                h298=-100.0, s298=50.0,
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1000.0, tboil=2000.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="X", phase="s", tmin=600.0, tmax=1000.0,  # Gap 500-600K
                h298=0.0, s298=0.0,
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1000.0, tboil=2000.0, reliability_class=1
            ),
        ]

    def test_search_all_phases_feo_success(self, mock_searcher, feo_records):
        """Test successful search of all FeO phases."""
        # Setup mocks
        mock_query = ("SELECT * FROM compounds WHERE formula = ?", ["FeO"])
        mock_searcher.sql_builder.build_compound_search_query.return_value = mock_query
        mock_searcher.db_connector.execute_query.return_value = [
            {
                "Formula": "FeO",
                "Phase": "s",
                "Tmin": 298.0,
                "Tmax": 600.0,
                "H298": -265.053,
                "S298": 59.807,
                "f1": 50.278,
                "f2": 3.651,
                "f3": -1.941,
                "f4": 8.234,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1650.0,
                "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO",
                "Phase": "s",
                "Tmin": 600.0,
                "Tmax": 900.0,
                "H298": 0.0,
                "S298": 0.0,
                "f1": 30.849,
                "f2": 46.228,
                "f3": 11.694,
                "f4": -19.278,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1650.0,
                "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO",
                "Phase": "s",
                "Tmin": 900.0,
                "Tmax": 1300.0,
                "H298": 0.0,
                "S298": 0.0,
                "f1": 90.408,
                "f2": -38.021,
                "f3": -83.811,
                "f4": 15.358,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1650.0,
                "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO",
                "Phase": "s",
                "Tmin": 1300.0,
                "Tmax": 1650.0,
                "H298": 0.0,
                "S298": 0.0,
                "f1": 153.698,
                "f2": -82.062,
                "f3": -374.815,
                "f4": 21.975,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1650.0,
                "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO",
                "Phase": "l",
                "Tmin": 1650.0,
                "Tmax": 5000.0,
                "H298": 24.058,
                "S298": 14.581,
                "f1": 68.199,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1650.0,
                "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
        ]

        # Execute search
        result = mock_searcher.search_all_phases("FeO", max_temperature=1700.0)

        # Verify result structure
        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "FeO"
        assert len(result.records) == 5
        assert result.covers_298K is True
        assert result.coverage_start == 298.0
        assert result.coverage_end == 1700.0
        assert result.tmelt == 1650.0
        assert result.tboil == 3687.0
        assert result.phase_count == 2  # s и l
        assert result.has_gas_phase is False
        assert len(result.warnings) == 0  # Нет предупреждений

        # Verify records are sorted by Tmin
        for i in range(len(result.records) - 1):
            assert result.records[i].tmin <= result.records[i + 1].tmin

    def test_search_all_phases_no_records(self, mock_searcher):
        """Test search when no records found."""
        # Setup mocks
        mock_query = ("SELECT * FROM compounds WHERE formula = ?", ["XYZ"])
        mock_searcher.sql_builder.build_compound_search_query.return_value = mock_query
        mock_searcher.db_connector.execute_query.return_value = []

        # Execute search
        result = mock_searcher.search_all_phases("XYZ", max_temperature=1000.0)

        # Verify result
        assert result.compound_formula == "XYZ"
        assert len(result.records) == 0
        assert result.coverage_start == 0.0
        assert result.coverage_end == 0.0
        assert result.covers_298K is False
        assert result.phase_count == 0
        assert "Вещество не найдено в БД" in result.warnings

    def test_search_all_phases_gap_warning(self, mock_searcher, records_with_gap):
        """Test gap warning generation."""
        # Setup mocks
        mock_query = ("SELECT * FROM compounds WHERE formula = ?", ["X"])
        mock_searcher.sql_builder.build_compound_search_query.return_value = mock_query
        mock_searcher.db_connector.execute_query.return_value = [
            {
                "Formula": "X",
                "Phase": "s",
                "Tmin": 298.0,
                "Tmax": 500.0,
                "H298": -100.0,
                "S298": 50.0,
                "f1": 30.0,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1000.0,
                "BoilingPoint": 2000.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "X",
                "Phase": "s",
                "Tmin": 600.0,
                "Tmax": 1000.0,
                "H298": 0.0,
                "S298": 0.0,
                "f1": 30.0,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1000.0,
                "BoilingPoint": 2000.0,
                "ReliabilityClass": 1
            },
        ]

        # Execute search
        result = mock_searcher.search_all_phases("X", max_temperature=1000.0)

        # Verify gap warning
        assert any("Пробел в покрытии" in warning for warning in result.warnings)
        assert "500.0K - 600.0K" in result.warnings[0]

    def test_search_all_phases_no_298K_coverage(self, mock_searcher):
        """Test warning when 298K is not covered."""
        # Setup mocks with records starting at 400K
        mock_query = ("SELECT * FROM compounds WHERE formula = ?", ["Y"])
        mock_searcher.sql_builder.build_compound_search_query.return_value = mock_query
        mock_searcher.db_connector.execute_query.return_value = [
            {
                "Formula": "Y",
                "Phase": "l",
                "Tmin": 400.0,
                "Tmax": 800.0,
                "H298": -50.0,
                "S298": 30.0,
                "f1": 40.0,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 350.0,
                "BoilingPoint": 1000.0,
                "ReliabilityClass": 1
            },
        ]

        # Execute search
        result = mock_searcher.search_all_phases("Y", max_temperature=600.0)

        # Verify 298K warning
        assert any("298K" in warning for warning in result.warnings)
        assert result.covers_298K is False

    def test_search_all_phases_with_static_cache_priority(self, mock_searcher, feo_records):
        """Test that static cache has priority over database."""
        # Setup static data manager mock
        static_manager = Mock()
        static_manager.is_available.return_value = True
        static_manager.get_compound_phases.return_value = feo_records

        mock_searcher.static_data_manager = static_manager

        # Execute search
        result = mock_searcher.search_all_phases("FeO", max_temperature=1700.0)

        # Verify static cache was used
        static_manager.is_available.assert_called_once_with("FeO")
        static_manager.get_compound_phases.assert_called_once_with("FeO")

        # Verify database was NOT called
        mock_searcher.sql_builder.build_compound_search_query.assert_not_called()
        mock_searcher.db_connector.execute_query.assert_not_called()

        # Verify result
        assert result.compound_formula == "FeO"
        assert len(result.records) == 5
        assert result.covers_298K is True

    def test_search_all_phases_temperature_filtering(self, mock_searcher):
        """Test that records are properly filtered by max_temperature."""
        # Setup mocks with records beyond max_temperature
        mock_query = ("SELECT * FROM compounds WHERE formula = ?", ["Z"])
        mock_searcher.sql_builder.build_compound_search_query.return_value = mock_query
        mock_searcher.db_connector.execute_query.return_value = [
            {
                "Formula": "Z",
                "Phase": "s",
                "Tmin": 298.0,
                "Tmax": 800.0,
                "H298": -100.0,
                "S298": 50.0,
                "f1": 30.0,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1000.0,
                "BoilingPoint": 2000.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "Z",
                "Phase": "l",
                "Tmin": 1200.0,  # Beyond max_temperature
                "Tmax": 2000.0,
                "H298": -50.0,
                "S298": 30.0,
                "f1": 40.0,
                "f2": 0.0,
                "f3": 0.0,
                "f4": 0.0,
                "f5": 0.0,
                "f6": 0.0,
                "MeltingPoint": 1000.0,
                "BoilingPoint": 2000.0,
                "ReliabilityClass": 1
            },
        ]

        # Execute search with max_temperature=1000K
        result = mock_searcher.search_all_phases("Z", max_temperature=1000.0)

        # Verify only first record is included
        assert len(result.records) == 1
        assert result.records[0].phase == "s"
        assert result.coverage_end == 800.0  # Limited by first record's Tmax

    def test_extract_phase_transitions_consensus(self, mock_searcher):
        """Test phase transition extraction with consensus method."""
        # Create records with different Tmelt values
        records = [
            DatabaseRecord(
                formula="Test", phase="s", tmin=298.0, tmax=500.0,
                h298=-100.0, s298=50.0, tmelt=1000.0, tboil=2000.0,
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Test", phase="s", tmin=500.0, tmax=800.0,
                h298=0.0, s298=0.0, tmelt=1000.0, tboil=2000.0,  # Same Tmelt
                f1=35.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Test", phase="s", tmin=800.0, tmax=1200.0,
                h298=0.0, s298=0.0, tmelt=1000.0, tboil=2000.0,  # Same Tmelt
                f1=40.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
        ]

        # Extract transitions
        tmelt, tboil = mock_searcher._extract_phase_transitions(records)

        # Verify consensus value is returned
        assert tmelt == 1000.0
        assert tboil == 2000.0

    def test_extract_phase_transitions_empty(self, mock_searcher):
        """Test phase transition extraction with empty records."""
        tmelt, tboil = mock_searcher._extract_phase_transitions([])

        assert tmelt is None
        assert tboil is None

    def test_generate_warnings_no_records(self, mock_searcher):
        """Test warning generation with no records."""
        warnings = mock_searcher._generate_warnings([], False)

        # Should generate 298K warning even with no records
        assert len(warnings) == 1
        assert "298K" in warnings[0]

    def test_generate_warnings_multiple_issues(self, mock_searcher):
        """Test warning generation with multiple issues."""
        # Create records with multiple problems
        records = [
            DatabaseRecord(
                formula="Problem", phase="s", tmin=400.0, tmax=500.0,  # No 298K
                h298=0.0, s298=0.0,  # Not base record
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1000.0, tboil=2000.0, reliability_class=1
            ),
            DatabaseRecord(
                formula="Problem", phase="s", tmin=600.0, tmax=800.0,  # Gap
                h298=0.0, s298=0.0,
                f1=35.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1000.0, tboil=2000.0, reliability_class=1
            ),
        ]

        warnings = mock_searcher._generate_warnings(records, False)  # No 298K coverage

        # Verify multiple warnings - we expect: 298K warning + gap warning + base record warning
        assert len(warnings) >= 3
        assert any("298K" in w for w in warnings)
        assert any("500.0K - 600.0K" in w for w in warnings)  # Specific gap
        assert any("H298=0" in w for w in warnings)  # Base record warning

    def test_multi_phase_result_properties(self, mock_searcher):
        """Test MultiPhaseSearchResult properties."""
        # Create real DatabaseRecord objects
        records = [
            DatabaseRecord(
                formula="Test", phase="s", tmin=298.0, tmax=500.0,
                h298=-100.0, s298=50.0, tmelt=1000.0, tboil=2000.0,
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Test", phase="s", tmin=500.0, tmax=800.0,
                h298=0.0, s298=0.0, tmelt=1000.0, tboil=2000.0,
                f1=35.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Test", phase="l", tmin=800.0, tmax=1200.0,
                h298=-50.0, s298=40.0, tmelt=1000.0, tboil=2000.0,
                f1=40.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Test", phase="g", tmin=1200.0, tmax=2000.0,
                h298=-20.0, s298=60.0, tmelt=1000.0, tboil=2000.0,
                f1=45.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                reliability_class=1
            ),
        ]

        # Create result
        result = MultiPhaseSearchResult(
            compound_formula="Test",
            records=records,
            coverage_start=298.0,
            coverage_end=2000.0,
            covers_298K=True,
            phase_count=3,
            has_gas_phase=True
        )

        # Test properties
        assert result.is_complete is True  # covers_298K and no warnings
        assert result.phase_sequence == "s → s → l → g"  # All phases shown