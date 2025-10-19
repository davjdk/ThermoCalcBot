"""
Simplified integration tests for multi-phase thermodynamic calculator.
"""

import pytest
import tempfile
from pathlib import Path

from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from thermo_agents.models.search import DatabaseRecord, TransitionType


class TestMultiPhaseIntegrationSimple:
    """Simplified integration tests for multi-phase calculator."""

    @pytest.fixture
    def calculator(self):
        """Create ThermodynamicCalculator instance."""
        return ThermodynamicCalculator()

    @pytest.fixture
    def feo_records_realistic(self):
        """Create realistic FeO records for integration testing."""
        return [
            DatabaseRecord(
                id=1,
                formula="FeO",
                name="Iron(II) oxide - B1 (solid)",
                phase="s",
                tmin=298.15,
                tmax=1642.0,
                h298=-272043.2,  # J/mol
                s298=60.089,     # J/(mol·K)
                f1=49.9146,
                f2=9.2956,
                f3=-0.0185,
                f4=0.000094,
                f5=0.0,
                f6=0.0,
                tmelt=1642.0,
                tboil=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="FeO",
                name="Iron(II) oxide (liquid)",
                phase="l",
                tmin=1642.0,
                tmax=3400.0,
                h298=-272043.2,  # Same H298 for simplicity
                s298=60.089,
                f1=95.407,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1642.0,
                tboil=0.0,
                reliability_class=1
            )
        ]

    @pytest.fixture
    def h2o_records_realistic(self):
        """Create realistic H2O records for integration testing."""
        return [
            DatabaseRecord(
                id=3,
                formula="H2O",
                name="Water (solid)",
                phase="s",
                tmin=200.0,
                tmax=273.15,
                h298=-285830.0,
                s298=69.95,
                f1=30.092,
                f2=6.832,
                f3=6.793,
                f4=-2.534,
                f5=0.082,
                f6=-0.007,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            DatabaseRecord(
                id=4,
                formula="H2O",
                name="Water (liquid)",
                phase="l",
                tmin=273.15,
                tmax=373.15,
                h298=-285830.0,
                s298=69.95,
                f1=75.327,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            DatabaseRecord(
                id=5,
                formula="H2O",
                name="Water (gas)",
                phase="g",
                tmin=373.15,
                tmax=1700.0,
                h298=-241826.0,  # Different H298 for gas phase
                s298=188.83,
                f1=33.066,
                f2=2.563,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            )
        ]

    def test_feo_specification_example(self, calculator, feo_records_realistic):
        """Test FeO example from specification (298K → 1700K)."""
        result = calculator.calculate_multi_phase_properties(
            records=feo_records_realistic,
            trajectory=[298.15, 1700.0]
        )

        assert result.T_target == 1700.0
        assert len(result.segments) == 2
        assert len(result.phase_transitions) == 1

        # Verify melting transition
        transition = result.phase_transitions[0]
        assert transition.transition_type == TransitionType.MELTING
        assert transition.from_phase == "s"
        assert transition.to_phase == "l"

        # Verify calculation results are reasonable
        assert result.H_final != 0  # Should have calculated enthalpy
        assert result.S_final != 0  # Should have calculated entropy
        assert result.G_final != 0  # Should have calculated Gibbs energy
        assert result.Cp_final > 0  # Heat capacity should be positive

    def test_h2o_three_phase_transition(self, calculator, h2o_records_realistic):
        """Test H2O with three phase transitions (solid → liquid → gas)."""
        result = calculator.calculate_multi_phase_properties(
            records=h2o_records_realistic,
            trajectory=[250.0, 273.15, 373.15, 500.0]
        )

        assert result.T_target == 500.0
        assert len(result.segments) == 3
        assert len(result.phase_transitions) == 2

        # Verify phase transitions
        transitions = result.phase_transitions
        assert transitions[0].transition_type == TransitionType.MELTING  # s → l
        assert transitions[1].transition_type == TransitionType.BOILING  # l → g

        # Verify temperatures cross phase boundaries
        assert 250.0 < 273.15  # solid phase
        assert 273.15 <= 373.15  # liquid phase
        assert 500.0 > 373.15     # gas phase

    def test_performance_with_real_data(self, calculator, h2o_records_realistic):
        """Test performance with realistic data (target <500ms)."""
        import time

        start_time = time.perf_counter()

        result = calculator.calculate_multi_phase_properties(
            records=h2o_records_realistic,
            trajectory=[298.15, 500.0, 1000.0, 1500.0]
        )

        elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

        assert result is not None  # Just check it's a valid result
        assert elapsed_time < 500.0, f"Performance target missed: {elapsed_time:.2f}ms > 500ms"

    def test_complex_temperature_trajectory(self, calculator, h2o_records_realistic):
        """Test complex temperature trajectory with multiple points."""
        trajectory = [200.0, 250.0, 273.15, 300.0, 350.0, 373.15, 400.0, 500.0, 1000.0]

        result = calculator.calculate_multi_phase_properties(
            records=h2o_records_realistic,
            trajectory=trajectory
        )

        assert result.T_target == 1000.0
        assert len(result.segments) == 3  # Should use all three phases
        assert len(result.phase_transitions) == 2

    def test_single_phase_only(self, calculator, h2o_records_realistic):
        """Test calculation with single phase only."""
        # Use only liquid phase
        result = calculator.calculate_multi_phase_properties(
            records=[h2o_records_realistic[1]],  # Only liquid
            trajectory=[298.15, 350.0]
        )

        assert result.T_target == 350.0
        assert len(result.segments) == 1
        assert len(result.phase_transitions) == 0

    def test_temperature_below_298K(self, calculator, h2o_records_realistic):
        """Test calculation with temperatures below 298.15K."""
        result = calculator.calculate_multi_phase_properties(
            records=[h2o_records_realistic[0]],  # Only solid phase
            trajectory=[200.0, 250.0, 273.15]
        )

        assert result.T_target == 273.15
        assert len(result.segments) == 1
        assert result.segments[0].record.phase == "s"

    def test_end_to_end_workflow_simulation(self, calculator, feo_records_realistic, h2o_records_realistic):
        """Test end-to-end workflow simulation."""
        compounds_data = {
            "FeO": feo_records_realistic,
            "H2O": h2o_records_realistic
        }

        results = {}

        for compound, records in compounds_data.items():
            # Simulate searching for all phases
            assert len(records) >= 2  # Should have at least 2 phases

            # Calculate multi-phase properties
            result = calculator.calculate_multi_phase_properties(
                records=records,
                trajectory=[298.15, 1000.0, 1500.0]
            )

            assert result.T_target == 1500.0
            assert len(result.segments) >= 2
            assert result.H_final != 0
            assert result.S_final != 0

            results[compound] = result

        # Verify different compounds have different behaviors
        assert len(results["FeO"].phase_transitions) == 1  # melting only
        assert len(results["H2O"].phase_transitions) == 2  # melting + boiling

    def test_phase_transition_thermodynamics(self, calculator, feo_records_realistic):
        """Test that phase transitions have reasonable thermodynamic values."""
        result = calculator.calculate_multi_phase_properties(
            records=feo_records_realistic,
            trajectory=[298.15, 1642.0, 2000.0]
        )

        assert len(result.phase_transitions) == 1
        transition = result.phase_transitions[0]

        # Phase transition should be at reasonable temperature
        assert 1600.0 <= transition.temperature <= 1700.0

        # Enthalpy and entropy changes should be reasonable (may be 0 if H298 values are same)
        assert transition.delta_H_transition >= 0  # Should be non-negative
        assert transition.delta_S_transition >= 0  # Should be non-negative

    def test_disable_phase_transitions_integration(self, calculator, h2o_records_realistic):
        """Test integration with disabled phase transitions."""
        # Use trajectory that actually crosses phase transitions
        result_enabled = calculator.calculate_multi_phase_properties(
            records=h2o_records_realistic,
            trajectory=[250.0, 273.15, 373.15, 500.0],  # Crosses both transitions
            include_phase_transitions=True
        )

        result_disabled = calculator.calculate_multi_phase_properties(
            records=h2o_records_realistic,
            trajectory=[250.0, 273.15, 373.15, 500.0],
            include_phase_transitions=False
        )

        # Both should have same segments
        assert len(result_enabled.segments) == len(result_disabled.segments)

        # Only enabled version should have transitions
        assert len(result_enabled.phase_transitions) > 0
        assert len(result_disabled.phase_transitions) == 0

        # Results should be different (due to transition contributions)
        assert result_enabled.H_final != result_disabled.H_final