#!/usr/bin/env python3
"""
Comprehensive test for Fe2O3 coefficient validation fix.

This test verifies that the coefficient validation fixes work correctly
for multi-record compounds with mixed data quality.
"""

import pytest
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from thermo_agents.core_logic.thermodynamic_engine import ThermodynamicEngine
from thermo_agents.core_logic.compound_data_loader import CompoundDataLoader
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder
from thermo_agents.selection.optimal_record_selector import OptimalRecordSelector
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.storage.static_data_manager import StaticDataManager
from thermo_agents.selection.selection_config import OptimizationConfig
import logging


class TestFe2O3CoefficientValidation:
    """Test suite for Fe2O3 coefficient validation."""

    @pytest.fixture
    def setup_components(self):
        """Set up test components."""
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        # Create components
        db_connector = DatabaseConnector("data/thermo_data.db")
        static_manager = StaticDataManager("data/static_compounds")
        data_loader = CompoundDataLoader(db_connector, static_manager, logger)
        thermo_engine = ThermodynamicEngine(logger)
        optimizer = OptimalRecordSelector(OptimizationConfig())
        record_builder = RecordRangeBuilder(logger, optimizer)

        return {
            'data_loader': data_loader,
            'thermo_engine': thermo_engine,
            'record_builder': record_builder,
            'optimizer': optimizer,
            'logger': logger
        }

    def test_fe2o3_data_loading_and_validation(self, setup_components):
        """Test that Fe2O3 data is loaded and zero coefficient records are identified."""
        components = setup_components
        data_loader = components['data_loader']

        # Load Fe2O3 data
        fe2o3_data = data_loader.get_raw_compound_data("Fe2O3")

        # Should find records
        assert len(fe2o3_data) > 0, "Fe2O3 data should be found"
        print(f"Found {len(fe2o3_data)} records for Fe2O3")

        # Count valid and invalid records
        valid_records = []
        invalid_records = []

        for idx, row in fe2o3_data.iterrows():
            if data_loader._has_valid_shomate_coefficients(row):
                valid_records.append(row)
            else:
                invalid_records.append(row)

        # Should have both valid and invalid records
        assert len(valid_records) > 0, "Should have valid coefficient records"
        assert len(invalid_records) > 0, "Should have zero coefficient records to filter"

        print(f"Valid records: {len(valid_records)}")
        print(f"Invalid records: {len(invalid_records)}")

        # Verify that invalid records indeed have all zero coefficients
        for row in invalid_records:
            coeffs = [row.get(f"f{i}", 0) for i in range(1, 7)]
            assert all(abs(c) < 1e-10 for c in coeffs), f"Invalid record should have all zero coefficients: {coeffs}"

    def test_thermodynamic_engine_coefficient_validation(self, setup_components):
        """Test ThermodynamicEngine coefficient validation."""
        components = setup_components
        thermo_engine = components['thermo_engine']

        # Test with valid coefficients
        valid_record = pd.Series({
            'Formula': 'Fe2O3',
            'Phase': 's',
            'Tmin': 298.15,
            'Tmax': 700.0,
            'H298': -825.0,
            'S298': 87.4,
            'f1': 143.566,
            'f2': -36.3229,
            'f3': -31.4331,
            'f4': 71.7917,
            'f5': 0.0,
            'f6': 0.0
        })

        properties = thermo_engine.calculate_properties(valid_record, 500.0)

        # Should return non-zero values
        assert properties['cp'] != 0, "Cp should be non-zero for valid coefficients"
        assert properties['enthalpy'] != 0, "Enthalpy should be non-zero for valid coefficients"
        assert properties['entropy'] != 0, "Entropy should be non-zero for valid coefficients"
        assert properties['gibbs_energy'] != 0, "Gibbs energy should be non-zero for valid coefficients"

        # Test with zero coefficients
        zero_record = pd.Series({
            'Formula': 'Fe2O3',
            'Phase': 's',
            'Tmin': 298.15,
            'Tmax': 300.0,
            'H298': -798.0,
            'S298': 93.0,
            'f1': 0.0,
            'f2': 0.0,
            'f3': 0.0,
            'f4': 0.0,
            'f5': 0.0,
            'f6': 0.0
        })

        properties = thermo_engine.calculate_properties(zero_record, 299.0)

        # Should return zero values and not crash
        assert properties['cp'] == 0, "Cp should be zero for zero coefficients"
        assert properties['enthalpy'] == 0, "Enthalpy should be zero for zero coefficients"
        assert properties['entropy'] == 0, "Entropy should be zero for zero coefficients"
        assert properties['gibbs_energy'] == 0, "Gibbs energy should be zero for zero coefficients"

    def test_record_range_builder_filters_zero_coefficients(self, setup_components):
        """Test that RecordRangeBuilder filters zero coefficient records."""
        components = setup_components
        data_loader = components['data_loader']
        record_builder = components['record_builder']

        # Load Fe2O3 data
        fe2o3_data = data_loader.get_raw_compound_data("Fe2O3")

        # Create test temperature range
        t_range = [300.0, 800.0]

        # Get records using RecordRangeBuilder
        selected_records = record_builder.get_compound_records_for_range(
            fe2o3_data, t_range, melting=None, boiling=None
        )

        # Should have selected records
        assert len(selected_records) > 0, "Should select records for the range"

        # All selected records should have valid coefficients
        for record in selected_records:
            assert record_builder._has_valid_shomate_coefficients(record), \
                f"Selected record should have valid coefficients: {record.get('f1', 0)}-{record.get('f6', 0)}"

    def test_optimal_record_selector_filters_zero_coefficients(self, setup_components):
        """Test that OptimalRecordSelector filters zero coefficient records."""
        components = setup_components
        data_loader = components['data_loader']
        optimizer = components['optimizer']

        # Load Fe2O3 data
        fe2o3_data = data_loader.get_raw_compound_data("Fe2O3")

        # Create a list with mixed valid/invalid records for testing
        test_records = []
        for idx, row in fe2o3_data.head(10).iterrows():
            test_records.append(row)

        # Filter using OptimalRecordSelector
        filtered_records = optimizer._filter_by_constraints(
            test_records, is_elemental=False, is_first_in_phase=True
        )

        # All filtered records should have valid coefficients
        for record in filtered_records:
            assert optimizer._has_valid_shomate_coefficients(record), \
                f"Filtered record should have valid coefficients: {record.get('f1', 0)}-{record.get('f6', 0)}"

    def test_end_to_end_fe2o3_calculation(self, setup_components):
        """Test end-to-end Fe2O3 calculation with coefficient validation."""
        components = setup_components
        data_loader = components['data_loader']
        record_builder = components['record_builder']
        thermo_engine = components['thermo_engine']

        # Load Fe2O3 data
        fe2o3_data = data_loader.get_raw_compound_data("Fe2O3")

        # Create test temperature range
        t_range = [300.0, 800.0]

        # Get records using RecordRangeBuilder
        selected_records = record_builder.get_compound_records_for_range(
            fe2o3_data, t_range, melting=None, boiling=None
        )

        # Should have selected valid records
        assert len(selected_records) > 0, "Should select valid records for calculation"

        # Test calculation at multiple temperatures
        test_temperatures = [350.0, 450.0, 550.0, 650.0, 750.0]

        for temp in test_temperatures:
            # Find record covering this temperature
            covering_record = None
            for record in selected_records:
                if record['Tmin'] <= temp <= record['Tmax']:
                    covering_record = record
                    break

            if covering_record is not None:
                # Calculate properties
                properties = thermo_engine.calculate_properties(covering_record, temp)

                # Should get meaningful (non-zero) results
                assert properties['cp'] > 0, f"Cp should be positive at {temp}K"

                # Allow zero for enthalpy/entropy only if reference values are zero
                if covering_record.get('H298', 0) != 0 or covering_record.get('S298', 0) != 0:
                    assert abs(properties['enthalpy']) > 1e-6 or abs(properties['entropy']) > 1e-6, \
                        f"Should have non-zero enthalpy or entropy at {temp}K for valid reference data"

        print(f"Successfully tested calculations at {len(test_temperatures)} temperatures")


if __name__ == "__main__":
    # Run tests directly if script is executed
    pytest.main([__file__, "-v"])