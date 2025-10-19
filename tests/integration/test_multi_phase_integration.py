"""
Integration tests for multi-phase thermodynamic calculator with real data.

Tests cover integration with CompoundSearcher, StaticDataManager, and database records.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from typing import List

from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.storage.static_data_manager import StaticDataManager
from thermo_agents.models.search import MultiPhaseSearchResult, MultiPhaseProperties


class TestMultiPhaseIntegration:
    """Integration tests for multi-phase calculator."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database with test data."""
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
                tmelt REAL,
                tboil REAL,
                reliability_class INTEGER
            )
        """)

        # Insert FeO test data (from specification)
        feo_data = [
            {
                "Formula": "FeO", "Phase": "s", "Tmin": 298.15, "Tmax": 1642.0,
                "H298": -272043.2, "S298": 60.089,  # in J/mol and J/(mol·K)
                "f1": 49.9146, "f2": 9.2956, "f3": -0.0185, "f4": 0.000094,
                "f5": 0.0, "f6": 0.0,
                "tmelt": 1642.0, "tboil": 0.0, "reliability_class": 1
            },
            {
                "Formula": "FeO", "Phase": "l", "Tmin": 1642.0, "Tmax": 3400.0,
                "H298": -272043.2, "S298": 60.089,
                "f1": 95.407, "f2": 0.0, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0,
                "tmelt": 1642.0, "tboil": 0.0, "reliability_class": 1
            }
        ]

        # Insert H2O test data
        h2o_data = [
            {
                "Formula": "H2O", "Phase": "s", "Tmin": 200.0, "Tmax": 273.15,
                "H298": -285.830, "S298": 69.95,
                "f1": 30.092, "f2": 6.832, "f3": 6.793, "f4": -2.534,
                "f5": 0.082, "f6": -0.007,
                "MeltingPoint": 273.15, "BoilingPoint": 373.15, "ReliabilityClass": 1
            },
            {
                "Formula": "H2O", "Phase": "l", "Tmin": 273.15, "Tmax": 373.15,
                "H298": -285.830, "S298": 69.95,
                "f1": 75.327, "f2": 0.0, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0,
                "MeltingPoint": 273.15, "BoilingPoint": 373.15, "ReliabilityClass": 1
            },
            {
                "Formula": "H2O", "Phase": "g", "Tmin": 373.15, "Tmax": 1700.0,
                "H298": -241.826, "S298": 188.83,
                "f1": 33.066, "f2": 2.563, "f3": 0.0, "f4": 0.0,
                "f5": 0.0, "f6": 0.0,
                "MeltingPoint": 273.15, "BoilingPoint": 373.15, "ReliabilityClass": 1
            }
        ]

        # Insert CO2 test data (sublimation)
        co2_data = [
            {
                "Formula": "CO2", "Phase": "s", "Tmin": 150.0, "Tmax": 194.68,
                "H298": -393.510, "S298": 213.79,
                "f1": 24.997, "f2": 55.186, "f3": -33.691, "f4": 7.948,
                "f5": -0.136, "f6": -0.403,
                "MeltingPoint": 0.0, "BoilingPoint": 194.68, "ReliabilityClass": 1
            },
            {
                "Formula": "CO2", "Phase": "g", "Tmin": 194.68, "Tmax": 3000.0,
                "H298": -393.510, "S298": 213.79,
                "f1": 24.997, "f2": 55.186, "f3": -33.691, "f4": 7.948,
                "f5": -0.136, "f6": -0.403,
                "MeltingPoint": 0.0, "BoilingPoint": 194.68, "ReliabilityClass": 1
            }
        ]

        # Combine all data
        all_data = feo_data + h2o_data + co2_data

        for data in all_data:
            connector.execute_query(
                "INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    data["Formula"], data["Phase"], data["Tmin"], data["Tmax"],
                    data["H298"], data["S298"], data["f1"], data["f2"], data["f3"],
                    data["f4"], data["f5"], data["f6"], data["tmelt"],
                    data["tboil"], data["reliability_class"]
                ]
            )

        yield db_path

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    @pytest.fixture
    def temp_yaml_dir(self):
        """Create temporary directory with YAML cache."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yaml_dir = Path(tmp_dir) / "static_compounds"
            yaml_dir.mkdir(parents=True)

            # Create H2O YAML file
            h2o_yaml = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  description: "Water from YAML cache"
  phases:
    - phase: "s"
      tmin: 200.0
      tmax: 273.15
      h298: -285830.0
      s298: 69.95
      f1: 30.092
      f2: 6.832
      f3: 6.793
      f4: -2.534
      f5: 0.082
      f6: -0.007
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
    - phase: "l"
      tmin: 273.15
      tmax: 373.15
      h298: -285830.0
      s298: 69.95
      f1: 75.327
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
    - phase: "g"
      tmin: 373.15
      tmax: 1700.0
      h298: -241826.0
      s298: 188.83
      f1: 33.066
      f2: 2.563
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
  metadata:
    source_database: "yaml_cache"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
            (yaml_dir / "H2O.yaml").write_text(h2o_yaml, encoding="utf-8")

            yield yaml_dir

    @pytest.fixture
    def calculator(self):
        """Create ThermodynamicCalculator instance."""
        return ThermodynamicCalculator()

    @pytest.fixture
    def compound_searcher(self, temp_db, temp_yaml_dir):
        """Create CompoundSearcher with StaticDataManager."""
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        static_manager = StaticDataManager(data_dir=temp_yaml_dir)

        return CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=static_manager
        )

    def test_feo_database_integration(self, calculator, temp_db):
        """Test FeO calculation using database records."""
        # Create searcher without YAML cache
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        searcher = CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=None
        )

        # Search for FeO
        result = searcher.search_all_phases("FeO", max_temperature=2000.0)

        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "FeO"
        assert len(result.records) == 2  # solid + liquid

        # Calculate multi-phase properties
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=[298.15, 1000.0, 1642.0, 2000.0]
        )

        assert isinstance(multi_phase_result, MultiPhaseProperties)
        assert multi_phase_result.formula == "FeO"
        assert len(multi_phase_result.segments) == 2
        assert len(multi_phase_result.transitions) == 1

        # Verify melting transition
        transition = multi_phase_result.transitions[0]
        assert transition.from_phase == "s"
        assert transition.to_phase == "l"
        assert transition.transition_type == "melting"

    def test_h2o_yaml_cache_priority(self, calculator, compound_searcher):
        """Test H2O calculation using YAML cache priority."""
        # Search for H2O (should use YAML cache)
        result = compound_searcher.search_all_phases("H2O", max_temperature=1500.0)

        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "H2O"
        assert len(result.records) == 3  # solid + liquid + gas
        assert result.records[0].name == "Water from YAML cache"

        # Calculate multi-phase properties
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=[298.15, 273.15, 373.15, 1000.0]
        )

        assert isinstance(multi_phase_result, MultiPhaseProperties)
        assert multi_phase_result.formula == "H2O"
        assert len(multi_phase_result.segments) == 3
        assert len(multi_phase_result.transitions) == 2  # melting + boiling

    def test_co2_sublimation_integration(self, calculator, temp_db):
        """Test CO2 sublimation (solid → gas)."""
        # Create searcher for CO2
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        searcher = CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=None
        )

        result = searcher.search_all_phases("CO2", max_temperature=1000.0)

        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "CO2"
        assert len(result.records) == 2  # solid + gas

        # Calculate multi-phase properties
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=[298.15, 194.68, 500.0]
        )

        assert isinstance(multi_phase_result, MultiPhaseProperties)
        assert len(multi_phase_result.transitions) == 1

        # Verify sublimation transition
        transition = multi_phase_result.transitions[0]
        assert transition.from_phase == "s"
        assert transition.to_phase == "g"
        assert transition.transition_type == "sublimation"

    def test_performance_with_real_data(self, calculator, compound_searcher):
        """Test performance with real database and YAML cache data."""
        import time

        # Test H2O (YAML cache)
        start_time = time.perf_counter()
        h2o_result = compound_searcher.search_all_phases("H2O", max_temperature=1500.0)
        h2o_multi_phase = calculator.calculate_multi_phase_properties(
            records=h2o_result.records,
            trajectory=[298.15, 500.0, 1000.0, 1500.0]
        )
        yaml_time = (time.perf_counter() - start_time) * 1000

        # Test FeO (database)
        start_time = time.perf_counter()
        feo_result = compound_searcher.search_all_phases("FeO", max_temperature=2000.0)
        feo_multi_phase = calculator.calculate_multi_phase_properties(
            records=feo_result.records,
            trajectory=[298.15, 1000.0, 1642.0, 2000.0]
        )
        db_time = (time.perf_counter() - start_time) * 1000

        # Verify results
        assert isinstance(h2o_multi_phase, MultiPhaseProperties)
        assert isinstance(feo_multi_phase, MultiPhaseProperties)

        # Performance targets (from specification)
        assert yaml_time < 100.0, f"YAML cache too slow: {yaml_time:.2f}ms"
        assert db_time < 500.0, f"Database too slow: {db_time:.2f}ms"

    def test_end_to_end_workflow(self, calculator, compound_searcher):
        """Test complete end-to-end workflow."""
        compounds_to_test = ["H2O", "FeO", "CO2"]
        results = {}

        for compound in compounds_to_test:
            # Search for all phases
            search_result = compound_searcher.search_all_phases(
                compound, max_temperature=2000.0
            )

            assert search_result.compound_formula == compound
            assert len(search_result.records) > 0

            # Calculate multi-phase properties
            multi_phase_result = calculator.calculate_multi_phase_properties(
                records=search_result.records,
                trajectory=[298.15, 1000.0, 1500.0, 2000.0]
            )

            assert isinstance(multi_phase_result, MultiPhaseProperties)
            assert multi_phase_result.formula == compound

            results[compound] = multi_phase_result

        # Verify each compound has different behavior
        assert results["H2O"].T_final == 2000.0
        assert results["FeO"].T_final == 2000.0
        assert results["CO2"].T_final == 2000.0

        # H2O should have 2 transitions (melting + boiling)
        assert len(results["H2O"].transitions) == 2

        # FeO should have 1 transition (melting)
        assert len(results["FeO"].transitions) == 1

        # CO2 should have 1 transition (sublimation)
        assert len(results["CO2"].transitions) == 1

    def test_temperature_trajectory_validation(self, calculator, compound_searcher):
        """Test temperature trajectory handling with real data."""
        result = compound_searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Test trajectory that spans multiple phases
        trajectory = [250.0, 273.15, 300.0, 373.15, 500.0, 1000.0]
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=trajectory
        )

        assert multi_phase_result.T_final == 1000.0
        assert len(multi_phase_result.segments) == 3  # Should use all three phases

    def test_complex_trajectory_with_gaps(self, calculator, compound_searcher):
        """Test complex trajectory with temperature gaps."""
        result = compound_searcher.search_all_phases("H2O", max_temperature=1500.0)

        # Trajectory with gaps
        trajectory = [298.15, 400.0, 800.0, 1200.0]
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=trajectory
        )

        assert isinstance(multi_phase_result, MultiPhaseProperties)
        assert multi_phase_result.T_final == 1200.0

    def test_single_phase_calculation(self, calculator, compound_searcher):
        """Test calculation with single phase only."""
        # Search for H2O with low max temperature (only solid phase)
        result = compound_searcher.search_all_phases("H2O", max_temperature=250.0)

        assert len(result.records) == 1
        assert result.records[0].phase == "s"

        # Calculate single-phase properties
        multi_phase_result = calculator.calculate_multi_phase_properties(
            records=result.records,
            trajectory=[200.0, 250.0]
        )

        assert isinstance(multi_phase_result, MultiPhaseProperties)
        assert len(multi_phase_result.segments) == 1
        assert len(multi_phase_result.transitions) == 0

    def test_error_handling_integration(self, calculator, compound_searcher):
        """Test error handling in integration scenarios."""
        # Test with non-existent compound
        result = compound_searcher.search_all_phases("NonExistent", max_temperature=1000.0)

        assert len(result.records) == 0

        # Should handle empty records gracefully
        with pytest.raises(ValueError, match="Список записей не может быть пустым"):
            calculator.calculate_multi_phase_properties(records=result.records)