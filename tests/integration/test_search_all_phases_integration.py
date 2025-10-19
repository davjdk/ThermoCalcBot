"""
Integration tests for multi-phase search functionality.

Tests cover real database interactions and integration with other components
including the prioritized YAML cache → Database fallback pattern.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.models.search import DatabaseRecord, MultiPhaseSearchResult


class TestSearchAllPhasesIntegration:
    """Integration tests for search_all_phases functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with test data."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name

        # Create test database
        connector = DatabaseConnector(db_path)
        connector.execute_query("""
            CREATE TABLE compounds (
                Formula TEXT,
                Phase TEXT,
                Tmin REAL,
                Tmax REAL,
                H298 REAL,
                S298 REAL,
                f1 REAL, f2 REAL, f3 REAL, f4 REAL, f5 REAL, f6 REAL,
                MeltingPoint REAL,
                BoilingPoint REAL,
                ReliabilityClass INTEGER
            )
        """)

        # Insert test data
        test_data = [
            # FeO data (similar to specification)
            {
                "Formula": "FeO", "Phase": "s", "Tmin": 298.0, "Tmax": 600.0,
                "H298": -265.053, "S298": 59.807,
                "f1": 50.278, "f2": 3.651, "f3": -1.941, "f4": 8.234,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 1650.0, "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO", "Phase": "s", "Tmin": 600.0, "Tmax": 900.0,
                "H298": 0.0, "S298": 0.0,
                "f1": 30.849, "f2": 46.228, "f3": 11.694, "f4": -19.278,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 1650.0, "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO", "Phase": "s", "Tmin": 900.0, "Tmax": 1300.0,
                "H298": 0.0, "S298": 0.0,
                "f1": 90.408, "f2": -38.021, "f3": -83.811, "f4": 15.358,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 1650.0, "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO", "Phase": "s", "Tmin": 1300.0, "Tmax": 1650.0,
                "H298": 0.0, "S298": 0.0,
                "f1": 153.698, "f2": -82.062, "f3": -374.815, "f4": 21.975,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 1650.0, "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            {
                "Formula": "FeO", "Phase": "l", "Tmin": 1650.0, "Tmax": 5000.0,
                "H298": 24.058, "S298": 14.581,
                "f1": 68.199, "f2": 0.0, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 1650.0, "BoilingPoint": 3687.0,
                "ReliabilityClass": 1
            },
            # H2O data (3 phases)
            {
                "Formula": "H2O", "Phase": "s", "Tmin": 200.0, "Tmax": 273.15,
                "H298": -285830.0, "S298": 69.95,
                "f1": 30.092, "f2": 6.832, "f3": 6.793, "f4": -2.534,
                "f5": 0.082, "f6": -0.007, "MeltingPoint": 273.15, "BoilingPoint": 373.15,
                "ReliabilityClass": 1
            },
            {
                "Formula": "H2O", "Phase": "l", "Tmin": 273.15, "Tmax": 373.15,
                "H298": -285830.0, "S298": 69.95,
                "f1": 75.327, "f2": 0.0, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 273.15, "BoilingPoint": 373.15,
                "ReliabilityClass": 1
            },
            {
                "Formula": "H2O", "Phase": "g", "Tmin": 373.15, "Tmax": 2000.0,
                "H298": -241826.0, "S298": 188.83,
                "f1": 33.066, "f2": 2.563, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0, "MeltingPoint": 273.15, "BoilingPoint": 373.15,
                "ReliabilityClass": 1
            },
        ]

        for data in test_data:
            connector.execute_query(
                "INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    data["Formula"], data["Phase"], data["Tmin"], data["Tmax"],
                    data["H298"], data["S298"], data["f1"], data["f2"], data["f3"],
                    data["f4"], data["f5"], data["f6"], data["MeltingPoint"],
                    data["BoilingPoint"], data["ReliabilityClass"]
                ]
            )

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def searcher(self, temp_db):
        """Create a CompoundSearcher with test database."""
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        return CompoundSearcher(sql_builder, db_connector)

    def test_search_feo_all_phases_integration(self, searcher):
        """Test integrated search of FeO phases using real database."""
        result = searcher.search_all_phases("FeO", max_temperature=1700.0)

        # Verify result structure
        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "FeO"
        assert len(result.records) == 5
        assert result.covers_298K is True
        assert result.coverage_start == 298.0
        assert result.coverage_end == 1700.0  # Limited by max_temperature
        assert result.tmelt == 1650.0
        assert result.tboil == 3687.0
        assert result.phase_count == 2  # s and l
        assert result.has_gas_phase is False
        assert len(result.warnings) == 0

        # Verify phase sequence
        phases = [rec.phase for rec in result.records]
        assert phases == ["s", "s", "s", "s", "l"]  # 4 solid + 1 liquid

        # Verify records are sorted by Tmin
        for i in range(len(result.records) - 1):
            assert result.records[i].tmin <= result.records[i + 1].tmin

    def test_search_h2o_three_phases_integration(self, searcher):
        """Test search of H2O with all three phases."""
        result = searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Verify result
        assert result.compound_formula == "H2O"
        assert len(result.records) == 3
        assert result.covers_298K is True
        assert result.phase_count == 3  # s, l, g
        assert result.has_gas_phase is True
        assert result.tmelt == 273.15
        assert result.tboil == 373.15

        # Verify phase sequence
        phases = [rec.phase for rec in result.records]
        assert phases == ["s", "l", "g"]

    def test_search_nonexistent_compound_integration(self, searcher):
        """Test search for compound that doesn't exist."""
        result = searcher.search_all_phases("NonExistent", max_temperature=1000.0)

        # Verify empty result
        assert result.compound_formula == "NonExistent"
        assert len(result.records) == 0
        assert result.coverage_start == 0.0
        assert result.coverage_end == 0.0
        assert result.covers_298K is False
        assert result.phase_count == 0
        assert "Вещество не найдено в БД" in result.warnings

    def test_temperature_filtering_integration(self, searcher):
        """Test temperature filtering in real database."""
        # Search with low max temperature
        result = searcher.search_all_phases("FeO", max_temperature=800.0)

        # Should only include first two records (298-600K and 600-900K)
        assert len(result.records) == 2
        assert result.coverage_start == 298.0
        assert result.coverage_end == 800.0  # Limited by max_temperature
        assert result.records[-1].tmax >= 800.0

    def test_yaml_cache_priority_integration(self, temp_db):
        """Test that YAML cache takes priority over database."""
        # Create mock static data manager
        static_manager = Mock()
        static_manager.is_available.return_value = True
        static_manager.get_compound_phases.return_value = [
            DatabaseRecord(
                formula="H2O", phase="g", tmin=298.0, tmax=1700.0,
                h298=-241826.0, s298=188.83,
                f1=33.066, f2=2.563, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=273.15, tboil=373.15, reliability_class=1,
                name="From YAML Cache"
            )
        ]

        # Create searcher with static manager
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        searcher = CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=static_manager
        )

        # Search H2O
        result = searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Verify cache was used
        static_manager.is_available.assert_called_once_with("H2O")
        static_manager.get_compound_phases.assert_called_once_with("H2O")

        # Verify result from cache
        assert result.compound_formula == "H2O"
        assert len(result.records) == 1
        assert result.records[0].phase == "g"
        assert result.records[0].name == "From YAML Cache"

    def test_fallback_to_database_when_cache_unavailable(self, searcher):
        """Test fallback to database when compound not in cache."""
        # Create mock static manager that doesn't have the compound
        static_manager = Mock()
        static_manager.is_available.return_value = False

        # Update searcher to use static manager
        searcher.static_data_manager = static_manager

        # Search H2O
        result = searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Verify cache was checked but not used
        static_manager.is_available.assert_called_once_with("H2O")
        static_manager.get_compound_phases.assert_not_called()

        # Verify database was used
        assert len(result.records) == 3  # H2O has 3 phases in DB
        assert result.covers_298K is True

    def test_phase_transition_consensus_integration(self, searcher):
        """Test phase transition extraction with consensus across records."""
        result = searcher.search_all_phases("FeO", max_temperature=2000.0)

        # All FeO records have the same Tmelt and Tboil values
        assert result.tmelt == 1650.0
        assert result.tboil == 3687.0

    def test_warning_generation_integration(self, temp_db):
        """Test warning generation with problematic data."""
        # Add problematic data to database
        connector = DatabaseConnector(temp_db)
        connector.execute_query(
            "INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["Problem", "s", 400.0, 600.0, 0.0, 0.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1000.0, 2000.0, 1]
        )
        connector.execute_query(
            "INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["Problem", "s", 800.0, 1000.0, 0.0, 0.0, 35.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1000.0, 2000.0, 1]
        )

        # Create searcher
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        searcher = CompoundSearcher(sql_builder, db_connector)

        # Search problem compound
        result = searcher.search_all_phases("Problem", max_temperature=1200.0)

        # Verify warnings
        assert len(result.warnings) >= 2  # No 298K coverage + gap + no base record
        assert any("298K" in w for w in result.warnings)
        assert any("Пробел в покрытии" in w for w in result.warnings)
        assert any("базовой записи" in w for w in result.warnings)

    def test_performance_with_database_search(self, searcher):
        """Test performance of database search."""
        import time

        start_time = time.perf_counter()
        result = searcher.search_all_phases("FeO", max_temperature=1700.0)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Should be fast (<100ms as per specification)
        assert elapsed_ms < 100.0, f"Database search too slow: {elapsed_ms:.2f}ms"
        assert len(result.records) == 5

    def test_comprehensive_result_serialization(self, searcher):
        """Test MultiPhaseSearchResult.to_dict() method."""
        result = searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Test serialization
        result_dict = result.to_dict()

        # Verify structure
        assert "formula" in result_dict
        assert "coverage" in result_dict
        assert "covers_298K" in result_dict
        assert "transitions" in result_dict
        assert "phases" in result_dict
        assert "records_count" in result_dict
        assert "warnings" in result_dict

        # Verify values
        assert result_dict["formula"] == "H2O"
        assert result_dict["coverage"] == [200.0, 1500.0]
        assert result_dict["covers_298K"] is True
        assert result_dict["transitions"]["melting"] == 273.15
        assert result_dict["transitions"]["boiling"] == 373.15
        assert result_dict["phases"] == "s → l → g"
        assert result_dict["records_count"] == 3

    def test_edge_case_single_phase_only(self, searcher):
        """Test search that returns only a single phase."""
        # Add single-phase compound to database
        connector = DatabaseConnector(searcher.db_connector.db_path)
        connector.execute_query(
            "INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["SinglePhase", "s", 298.0, 1000.0, -100.0, 50.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1500.0, 2500.0, 1]
        )

        # Search
        result = searcher.search_all_phases("SinglePhase", max_temperature=800.0)

        # Verify single phase result
        assert len(result.records) == 1
        assert result.phase_count == 1
        assert result.has_gas_phase is False
        assert result.phase_sequence == "s"