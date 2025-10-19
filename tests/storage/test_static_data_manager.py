"""
Unit tests for StaticDataManager functionality.

Tests cover YAML loading, validation, caching, and conversion to DatabaseRecord.
"""

import pytest
import logging
from pathlib import Path
from datetime import datetime, timedelta

from thermo_agents.storage.static_data_manager import StaticDataManager
from thermo_agents.models.static_data import YAMLCompoundData, YAMLPhaseRecord


class TestStaticDataManager:
    """Test StaticDataManager functionality."""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create temporary directory for tests."""
        return tmp_path / "static_compounds"

    @pytest.fixture
    def sample_yaml_h2o(self, temp_data_dir):
        """Create sample H2O YAML file."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  description: "Water"
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
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        yaml_path = temp_data_dir / "H2O.yaml"
        yaml_path.write_text(yaml_content, encoding="utf-8")
        return yaml_path

    @pytest.fixture
    def sample_yaml_multi_phase(self, temp_data_dir):
        """Create multi-phase YAML file."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        yaml_content = """
compound:
  formula: "CO2"
  common_names: ["Carbon dioxide"]
  description: "Carbon dioxide"
  phases:
    - phase: "s"
      tmin: 150.0
      tmax: 194.68
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
    - phase: "g"
      tmin: 194.68
      tmax: 3000.0
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
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        yaml_path = temp_data_dir / "CO2.yaml"
        yaml_path.write_text(yaml_content)
        return yaml_path

    @pytest.fixture
    def outdated_yaml(self, temp_data_dir):
        """Create outdated YAML file."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d")
        yaml_content = f"""
compound:
  formula: "O2"
  common_names: ["Oxygen"]
  description: "Oxygen"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1500.0
      h298: 0.0
      s298: 205.15
      f1: 29.659
      f2: 6.137
      f3: -1.186
      f4: 0.095
      f5: -0.219
      f6: -0.008
      tmelt: 54.36
      tboil: 90.20
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "{old_date}"
    version: "1.0"
"""
        yaml_path = temp_data_dir / "O2.yaml"
        yaml_path.write_text(yaml_content)
        return yaml_path

    def test_static_data_manager_initialization(self, temp_data_dir):
        """Test StaticDataManager initialization."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        assert manager.data_dir == temp_data_dir
        assert manager.cache == {}
        assert temp_data_dir.exists()

    def test_static_data_manager_is_available(self, temp_data_dir, sample_yaml_h2o):
        """Test checking YAML file availability."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        assert manager.is_available("H2O") is True
        assert manager.is_available("CO2") is False

    def test_static_data_manager_load_compound(self, temp_data_dir, sample_yaml_h2o):
        """Test loading YAML file."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        compound_data = manager.load_compound("H2O")

        assert compound_data is not None
        assert compound_data.formula == "H2O"
        assert compound_data.description == "Water"
        assert len(compound_data.phases) == 1
        assert compound_data.phases[0].phase == "s"
        assert compound_data.phases[0].tmin == 200.0
        assert compound_data.metadata.version == "1.0"

    def test_static_data_manager_load_compound_not_found(self, temp_data_dir):
        """Test loading non-existent compound."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        compound_data = manager.load_compound("NonExistent")

        assert compound_data is None

    def test_static_data_manager_cache_functionality(self, temp_data_dir, sample_yaml_h2o):
        """Test caching functionality."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        # First load
        data1 = manager.load_compound("H2O")
        assert data1 is not None

        # Second load should use cache
        data2 = manager.load_compound("H2O")
        assert data1 is data2  # Same object from cache

        # Cache should contain one item
        assert len(manager.cache) == 1
        assert "H2O" in manager.cache

    def test_static_data_manager_get_compound_phases(self, temp_data_dir, sample_yaml_h2o):
        """Test converting to DatabaseRecord objects."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        records = manager.get_compound_phases("H2O")

        assert len(records) == 1
        record = records[0]
        assert record.formula == "H2O"
        assert record.name == "Water"
        assert record.phase == "s"
        assert record.h298 == -285830.0
        assert record.s298 == 69.95
        assert record.tmelt == 273.15
        assert record.tboil == 373.15

    def test_static_data_manager_get_compound_phases_multi(self, temp_data_dir, sample_yaml_multi_phase):
        """Test converting multi-phase compound."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        records = manager.get_compound_phases("CO2")

        assert len(records) == 2
        assert records[0].phase == "s"
        assert records[0].tmin == 150.0
        assert records[1].phase == "g"
        assert records[1].tmin == 194.68

    def test_static_data_manager_list_available_compounds(self, temp_data_dir, sample_yaml_h2o, sample_yaml_multi_phase):
        """Test listing available compounds."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        compounds = manager.list_available_compounds()

        assert len(compounds) == 2
        assert "H2O" in compounds
        assert "CO2" in compounds
        assert compounds == sorted(compounds)  # Should be sorted

    def test_static_data_manager_outdated_warning(self, temp_data_dir, outdated_yaml, caplog):
        """Test warning for outdated YAML data."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        # Should generate warning for outdated data
        with caplog.at_level(logging.WARNING):
            data = manager.load_compound("O2")

        assert data is not None
        assert any("outdated" in record.message for record in caplog.records if record.levelname == "WARNING")

    def test_static_data_manager_reload(self, temp_data_dir, sample_yaml_h2o):
        """Test cache reload functionality."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        # Load compound
        data1 = manager.load_compound("H2O")
        assert data1 is not None
        assert len(manager.cache) == 1

        # Reload cache
        manager.reload()
        assert len(manager.cache) == 0

        # Load again
        data2 = manager.load_compound("H2O")
        assert data2 is not None
        assert data1 is not data2  # Different objects after reload

    def test_static_data_manager_get_cache_info(self, temp_data_dir, sample_yaml_h2o, sample_yaml_multi_phase):
        """Test getting cache information."""
        manager = StaticDataManager(data_dir=temp_data_dir)

        # Load one compound
        manager.load_compound("H2O")

        cache_info = manager.get_cache_info()

        assert cache_info["cache_size"] == 1
        assert cache_info["data_dir"] == str(temp_data_dir)
        assert cache_info["available_files"] == 2
        assert cache_info["cached_compounds"] == ["H2O"]

    def test_invalid_yaml_structure(self, temp_data_dir, caplog):
        """Test handling of invalid YAML structure."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)

        # Create invalid YAML
        invalid_yaml = """
invalid: "structure"
missing: "compound key"
"""
        (temp_data_dir / "Invalid.yaml").write_text(invalid_yaml)

        manager = StaticDataManager(data_dir=temp_data_dir)

        with caplog.at_level(logging.ERROR):
            data = manager.load_compound("Invalid")

        assert data is None
        assert any("Error loading YAML" in record.message for record in caplog.records if record.levelname == "ERROR")

    def test_yaml_validation_error(self, temp_data_dir, caplog):
        """Test handling of YAML validation errors."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML with invalid phase data
        invalid_yaml = """
compound:
  formula: "X"
  description: "Invalid compound"
  phases:
    - phase: "s"
      tmin: 300.0
      tmax: 200.0  # Invalid: tmax < tmin
      h298: -100.0
      s298: 50.0
      f1: 30.0
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 1000.0
      tboil: 2000.0
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        (temp_data_dir / "X.yaml").write_text(invalid_yaml)

        manager = StaticDataManager(data_dir=temp_data_dir)

        with caplog.at_level(logging.ERROR):
            data = manager.load_compound("X")

        assert data is None
        assert any("Error loading YAML" in record.message for record in caplog.records if record.levelname == "ERROR")

    def test_phase_sorting_validation(self, temp_data_dir, caplog):
        """Test validation of phase sorting."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)

        # Create YAML with unsorted phases
        unsorted_yaml = """
compound:
  formula: "Y"
  description: "Unsorted phases"
  phases:
    - phase: "s"
      tmin: 500.0
      tmax: 700.0
      h298: -100.0
      s298: 50.0
      f1: 30.0
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 1000.0
      tboil: 2000.0
      reliability_class: 1
    - phase: "s"
      tmin: 200.0  # This should come first
      tmax: 400.0
      h298: -100.0
      s298: 50.0
      f1: 30.0
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 1000.0
      tboil: 2000.0
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        (temp_data_dir / "Y.yaml").write_text(unsorted_yaml)

        manager = StaticDataManager(data_dir=temp_data_dir)

        with caplog.at_level(logging.ERROR):
            data = manager.load_compound("Y")

        assert data is None
        assert any("Error loading YAML" in record.message for record in caplog.records if record.levelname == "ERROR")

    def test_default_initialization(self):
        """Test initialization with default directory."""
        import tempfile

        # Test with None (should use default)
        manager = StaticDataManager(data_dir=None)

        # Should create default directory structure
        # The path depends on where the test is run from
        expected_dir = manager.data_dir  # Use actual path from manager
        assert expected_dir.exists()  # Should be created