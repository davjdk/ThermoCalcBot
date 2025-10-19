"""
Integration tests for YAML cache functionality with CompoundSearcher.

Tests cover the complete flow from YAML cache to MultiPhaseSearchResult.
"""

import pytest
from pathlib import Path
import tempfile
import logging

from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.storage.static_data_manager import StaticDataManager
from thermo_agents.models.search import MultiPhaseSearchResult


class TestYAMLCacheIntegration:
    """Test integration between StaticDataManager and CompoundSearcher."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary directory for YAML files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir) / "static_compounds"

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for fallback testing."""
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

        # Insert some test data
        test_data = [
            {
                "Formula": "N2", "Phase": "g", "Tmin": 298.0, "Tmax": 1500.0,
                "H298": 0.0, "S298": 191.61,
                "f1": 28.883, "f2": 3.295, "f3": -0.853, "f4": 0.097,
                "f5": -0.226, "f6": -0.009,
                "MeltingPoint": 63.15, "BoilingPoint": 77.36,
                "ReliabilityClass": 1
            },
            {
                "Formula": "O2", "Phase": "g", "Tmin": 298.0, "Tmax": 1500.0,
                "H298": 0.0, "S298": 205.15,
                "f1": 29.659, "f2": 6.137, "f3": -1.186, "f4": 0.095,
                "f5": -0.219, "f6": -0.008,
                "MeltingPoint": 54.36, "BoilingPoint": 90.20,
                "ReliabilityClass": 1
            }
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
    def h2o_yaml(self, temp_data_dir):
        """Create H2O YAML file."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        yaml_content = """
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
        (temp_data_dir / "H2O.yaml").write_text(yaml_content)

    @pytest.fixture
    def searcher_with_yaml_cache(self, temp_data_dir, temp_db):
        """Create CompoundSearcher with StaticDataManager."""
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)
        static_manager = StaticDataManager(data_dir=temp_data_dir)

        return CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=static_manager
        )

    @pytest.fixture
    def searcher_without_yaml_cache(self, temp_db):
        """Create CompoundSearcher without StaticDataManager."""
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(temp_db)

        return CompoundSearcher(
            sql_builder=sql_builder,
            db_connector=db_connector,
            static_data_manager=None
        )

    def test_yaml_cache_priority(self, searcher_with_yaml_cache, h2o_yaml):
        """Test that YAML cache takes priority over database."""
        result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        # Verify result from YAML cache
        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "H2O"
        assert len(result.records) == 3  # s + l + g phases
        assert result.records[0].name == "Water from YAML cache"
        assert result.phase_count == 3
        assert result.has_gas_phase is True
        assert result.covers_298K is True

        # Verify phases are in correct order
        phases = [record.phase for record in result.records]
        assert phases == ["s", "l", "g"]

    def test_fallback_to_database(self, searcher_with_yaml_cache, temp_db):
        """Test fallback to database when compound not in YAML cache."""
        result = searcher_with_yaml_cache.search_all_phases("N2", max_temperature=1000.0)

        # Verify result from database
        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "N2"
        assert len(result.records) == 1
        assert result.records[0].phase == "g"
        assert result.records[0].h298 == 0.0
        assert result.records[0].s298 == 191.61

    def test_yaml_cache_not_used_when_unavailable(self, searcher_without_yaml_cache, temp_db):
        """Test that database is used when StaticDataManager is not available."""
        result = searcher_without_yaml_cache.search_all_phases("O2", max_temperature=1000.0)

        # Verify result from database
        assert isinstance(result, MultiPhaseSearchResult)
        assert result.compound_formula == "O2"
        assert len(result.records) == 1
        assert result.records[0].phase == "g"
        assert result.records[0].h298 == 0.0
        assert result.records[0].s298 == 205.15

    def test_yaml_cache_performance(self, searcher_with_yaml_cache, h2o_yaml):
        """Test performance of YAML cache loading."""
        import time

        # First load (from file)
        start = time.perf_counter()
        result1 = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)
        first_load_time = (time.perf_counter() - start) * 1000

        # Second load (from cache)
        start = time.perf_counter()
        result2 = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)
        second_load_time = (time.perf_counter() - start) * 1000

        # Both results should be identical
        assert result1.compound_formula == result2.compound_formula
        assert len(result1.records) == len(result2.records)

        # Second load should be faster (from cache)
        assert second_load_time < first_load_time

        # Performance requirements (specification: <10ms from cache)
        assert second_load_time < 10.0, f"Cache loading too slow: {second_load_time:.2f}ms"

    def test_yaml_cache_temperature_filtering(self, searcher_with_yaml_cache, h2o_yaml):
        """Test temperature filtering with YAML cache."""
        # Search with low max temperature (only solid phase)
        result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=250.0)

        assert result.compound_formula == "H2O"
        assert len(result.records) == 1  # Only solid phase
        assert result.records[0].phase == "s"
        assert result.coverage_end == 250.0

        # Search with higher max temperature (all phases)
        result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        assert len(result.records) == 3  # All phases
        assert result.coverage_end == 1500.0

    def test_yaml_cache_phase_transitions(self, searcher_with_yaml_cache, h2o_yaml):
        """Test phase transition extraction from YAML cache."""
        result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        # Verify phase transitions are extracted correctly
        assert result.tmelt == 273.15
        assert result.tboil == 373.15
        assert result.phase_count == 3

    def test_yaml_cache_with_session_logger(self, searcher_with_yaml_cache, h2o_yaml, caplog):
        """Test session logging with YAML cache."""
        # Add session logger
        import io
        from thermo_agents.thermo_agents_logger import SessionLogger

        log_stream = io.StringIO()
        session_logger = SessionLogger(log_stream)
        searcher_with_yaml_cache.session_logger = session_logger

        # Search with YAML cache
        result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        # Check that YAML cache usage was logged
        log_content = log_stream.getvalue()
        assert "YAML" in log_content
        assert result.compound_formula == "H2O"

    def test_yaml_cache_list_available_compounds(self, temp_data_dir, h2o_yaml):
        """Test listing available compounds in YAML cache."""
        # Add another YAML file
        yaml_content = """
compound:
  formula: "CO2"
  description: "Carbon dioxide"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1500.0
      h298: -393510.0
      s298: 213.79
      f1: 24.997
      f2: 55.186
      f3: -33.691
      f4: 7.948
      f5: -0.136
      f6: -0.403
      tmelt: 0.0
      tboil: 194.68
      reliability_class: 1
  metadata:
    source_database: "test"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        (temp_data_dir / "CO2.yaml").write_text(yaml_content)

        manager = StaticDataManager(data_dir=temp_data_dir)
        available = manager.list_available_compounds()

        assert len(available) == 2
        assert "H2O" in available
        assert "CO2" in available
        assert available == sorted(available)

    def test_yaml_cache_invalid_file_handling(self, searcher_with_yaml_cache, temp_data_dir, caplog):
        """Test handling of invalid YAML files."""
        # Create invalid YAML file
        (temp_data_dir / "Invalid.yaml").write_text("invalid: yaml: structure")

        # Should handle gracefully and fallback to database if available
        result = searcher_with_yaml_cache.search_all_phases("Invalid", max_temperature=1000.0)

        # Should return empty result since compound doesn't exist in DB either
        assert result.compound_formula == "Invalid"
        assert len(result.records) == 0
        assert "Вещество не найдено в БД" in result.warnings

    def test_yaml_cache_reload_functionality(self, searcher_with_yaml_cache, h2o_yaml):
        """Test cache reload functionality."""
        # Load compound
        result1 = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)
        assert len(result1.records) == 3

        # Check cache status
        cache_info = searcher_with_yaml_cache.static_data_manager.get_cache_info()
        assert cache_info["cache_size"] == 1
        assert "H2O" in cache_info["cached_compounds"]

        # Reload cache
        searcher_with_yaml_cache.static_data_manager.reload()

        # Cache should be empty
        cache_info = searcher_with_yaml_cache.static_data_manager.get_cache_info()
        assert cache_info["cache_size"] == 0

        # Load again - should work fine
        result2 = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)
        assert len(result2.records) == 3
        assert result1.compound_formula == result2.compound_formula

    def test_yaml_cache_compatibility_with_database_records(self, searcher_with_yaml_cache, h2o_yaml, temp_db):
        """Test that YAML cache records are compatible with database records."""
        # Load from YAML cache
        yaml_result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        # Load from database (add H2O to DB for comparison)
        connector = DatabaseConnector(temp_db)
        connector.execute_query("""
            INSERT INTO compounds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            "H2O", "g", 298.0, 1500.0, -241826.0, 188.83,
            33.066, 2.563, 0.0, 0.0, 0.0, 0.0,
            273.15, 373.15, 1
        ])

        db_result = searcher_with_yaml_cache.search_all_phases("H2O", max_temperature=1500.0)

        # Both should have same interface
        assert isinstance(yaml_result, MultiPhaseSearchResult)
        assert isinstance(db_result, MultiPhaseSearchResult)

        # YAML result should have more phases (from cache)
        assert len(yaml_result.records) >= len(db_result.records)

        # Records should have same structure
        for record in yaml_result.records:
            assert hasattr(record, 'formula')
            assert hasattr(record, 'phase')
            assert hasattr(record, 'tmin')
            assert hasattr(record, 'tmax')
            assert hasattr(record, 'h298')
            assert hasattr(record, 's298')