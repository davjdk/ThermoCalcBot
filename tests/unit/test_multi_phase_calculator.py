"""
Unit tests for multi-phase thermodynamic calculator.

Tests cover calculate_multi_phase_properties() method and supporting functionality.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from typing import List

from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from thermo_agents.models.search import DatabaseRecord, PhaseSegment, PhaseTransition, MultiPhaseProperties, TransitionType


class TestMultiPhaseCalculator:
    """Test multi-phase thermodynamic calculator functionality."""

    @pytest.fixture
    def calculator(self):
        """Create ThermodynamicCalculator instance."""
        return ThermodynamicCalculator()

    @pytest.fixture
    def feo_records(self):
        """Create FeO records for testing (from specification)."""
        return [
            DatabaseRecord(
                id=1,
                formula="FeO",
                name="Iron(II) oxide - FeO, B1",
                phase="s",
                tmin=298.15,
                tmax=1642.0,
                h298=-272043.2,
                s298=60.089,
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
                name="Iron(II) oxide - FeO, liquid",
                phase="l",
                tmin=1642.0,
                tmax=3400.0,
                h298=-272043.2,
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
    def h2o_records(self):
        """Create H2O records for testing."""
        return [
            DatabaseRecord(
                id=3,
                formula="H2O",
                name="Water - solid",
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
                name="Water - liquid",
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
                name="Water - gas",
                phase="g",
                tmin=373.15,
                tmax=1700.0,
                h298=-241826.0,
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

    def test_single_phase_calculation(self, calculator, feo_records):
        """Test calculation with single phase record."""
        single_record = [feo_records[0]]  # Only solid phase

        result = calculator.calculate_multi_phase_properties(
            records=single_record,
            trajectory=[298.15, 500.0, 1000.0]
        )

        assert isinstance(result, MultiPhaseProperties)
        assert result.formula == "FeO"
        assert len(result.segments) == 1
        assert result.segments[0].record.phase == "s"
        assert result.T_target == 1000.0
        # Check that the segments contain the original H298 and S298 values
        assert len(result.segments) == 1
        assert result.segments[0].H_start == -272043.2
        assert result.segments[0].S_start == 60.089

    def test_multi_phase_calculation_feo(self, calculator, feo_records):
        """Test multi-phase calculation with FeO (solid → liquid)."""
        result = calculator.calculate_multi_phase_properties(
            records=feo_records,
            trajectory=[298.15, 1000.0, 1642.0, 2000.0]
        )

        assert isinstance(result, MultiPhaseProperties)
        assert result.formula == "FeO"
        assert len(result.segments) == 2
        assert result.segments[0].record.phase == "s"
        assert result.segments[1].record.phase == "l"

        # Check phase transitions
        assert len(result.transitions) == 1
        transition = result.transitions[0]
        assert transition.from_phase == "s"
        assert transition.to_phase == "l"
        assert transition.transition_type == TransitionType.MELTING

        # Check final temperature
        assert result.T_target == 2000.0

    def test_multi_phase_calculation_h2o(self, calculator, h2o_records):
        """Test multi-phase calculation with H2O (solid → liquid → gas)."""
        result = calculator.calculate_multi_phase_properties(
            records=h2o_records,
            trajectory=[298.15, 273.15, 373.15, 500.0]
        )

        assert isinstance(result, MultiPhaseProperties)
        assert result.formula == "H2O"
        assert len(result.segments) == 3
        assert [seg.record.phase for seg in result.segments] == ["s", "l", "g"]

        # Check phase transitions
        assert len(result.transitions) == 2
        assert result.transitions[0].transition_type == TransitionType.MELTING  # s → l
        assert result.transitions[1].transition_type == TransitionType.BOILING  # l → g

    def test_default_trajectory(self, calculator, feo_records):
        """Test default trajectory [298.15, 1700.0]."""
        result = calculator.calculate_multi_phase_properties(records=feo_records)

        assert result.T_target == 1700.0
        assert result.formula == "FeO"

    def test_empty_records_error(self, calculator):
        """Test error handling for empty records list."""
        with pytest.raises(ValueError, match="Список записей не может быть пустым"):
            calculator.calculate_multi_phase_properties(records=[])

    def test_gap_between_records_error(self, calculator):
        """Test error handling for gaps between records."""
        records_with_gap = [
            DatabaseRecord(
                id=1, formula="Test", phase="s", tmin=298.15, tmax=500.0,
                h298=-100000.0, s298=50.0, f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=0.0, tboil=0.0, reliability_class=1
            ),
            DatabaseRecord(
                id=2, formula="Test", phase="l", tmin=600.0, tmax=1000.0,  # Gap: 500.0-600.0
                h298=-100000.0, s298=50.0, f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=0.0, tboil=0.0, reliability_class=1
            )
        ]

        with pytest.raises(ValueError, match="Обнаружен пробел между записями"):
            calculator.calculate_multi_phase_properties(records=records_with_gap)

    def test_disable_phase_transitions(self, calculator, feo_records):
        """Test calculation with disabled phase transitions."""
        result = calculator.calculate_multi_phase_properties(
            records=feo_records,
            trajectory=[298.15, 1642.0, 2000.0],
            include_phase_transitions=False
        )

        assert len(result.transitions) == 0
        assert len(result.segments) == 2

    def test_identify_phase_transitions(self, calculator):
        """Test phase transition identification."""
        segments = [
            PhaseSegment(
                phase="s", tmin=298.15, tmax=273.15, h298=-100.0, s298=50.0,
                f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0
            ),
            PhaseSegment(
                phase="l", tmin=273.15, tmax=373.15, h298=-90.0, s298=60.0,
                f1=75.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0
            ),
            PhaseSegment(
                phase="g", tmin=373.15, tmax=1000.0, h298=-80.0, s298=150.0,
                f1=33.0, f2=2.5, f3=0.0, f4=0.0, f5=0.0, f6=0.0
            )
        ]

        transitions = calculator._identify_phase_transitions(segments)

        assert len(transitions) == 2
        assert transitions[0].transition_type == "melting"
        assert transitions[0].from_phase == "s"
        assert transitions[0].to_phase == "l"

        assert transitions[1].transition_type == "boiling"
        assert transitions[1].from_phase == "l"
        assert transitions[1].to_phase == "g"

    def test_determine_transition_type(self, calculator):
        """Test transition type determination."""
        test_cases = [
            ("s", "l", TransitionType.MELTING),
            ("l", "g", TransitionType.BOILING),
            ("s", "g", TransitionType.SUBLIMATION),
            ("l", "s", None),  # Not supported (reverse melting)
            ("g", "l", None),  # Not supported (condensation)
            ("g", "s", None),  # Not supported (deposition)
            ("s", "s", None),  # Same phase
            ("x", "y", None),  # Unknown phases
        ]

        for from_phase, to_phase, expected in test_cases:
            result = calculator._determine_transition_type(from_phase, to_phase)
            assert result == expected

    def test_integrate_enthalpy(self, calculator):
        """Test enthalpy integration."""
        segment = PhaseSegment(
            phase="s", tmin=298.15, tmax=500.0, h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0
        )

        delta_H, error = calculator._integrate_enthalpy(segment, 298.15, 400.0)

        assert delta_H > 0  # Endothermic process
        assert error is None or abs(error) < 1e-6

    def test_integrate_entropy(self, calculator):
        """Test entropy integration."""
        segment = PhaseSegment(
            phase="s", tmin=298.15, tmax=500.0, h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0
        )

        delta_S, error = calculator._integrate_entropy(segment, 298.15, 400.0)

        assert delta_S > 0  # Entropy increases with temperature
        assert error is None or abs(error) < 1e-9

    def test_performance_target(self, calculator, h2o_records):
        """Test performance target (<500ms for typical calculation)."""
        import time

        start_time = time.perf_counter()

        result = calculator.calculate_multi_phase_properties(
            records=h2o_records,
            trajectory=[298.15, 500.0, 1000.0, 1500.0]
        )

        elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

        assert isinstance(result, MultiPhaseProperties)
        assert elapsed_time < 500.0, f"Performance target missed: {elapsed_time:.2f}ms > 500ms"

    def test_feo_specification_example(self, calculator):
        """Test FeO example from specification (298K → 1700K)."""
        # Create FeO records as in specification
        feo_records = [
            DatabaseRecord(
                id=1, formula="FeO", name="FeO, B1", phase="s",
                tmin=298.15, tmax=1642.0,
                h298=-272043.2, s298=60.089,
                f1=49.9146, f2=9.2956, f3=-0.0185, f4=0.000094, f5=0.0, f6=0.0,
                tmelt=1642.0, tboil=0.0, reliability_class=1
            ),
            DatabaseRecord(
                id=2, formula="FeO", name="FeO, liquid", phase="l",
                tmin=1642.0, tmax=3400.0,
                h298=-272043.2, s298=60.089,
                f1=95.407, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=1642.0, tboil=0.0, reliability_class=1
            )
        ]

        result = calculator.calculate_multi_phase_properties(
            records=feo_records,
            trajectory=[298.15, 1700.0]
        )

        assert result.formula == "FeO"
        assert result.T_target == 1700.0
        assert len(result.segments) == 2
        assert len(result.transitions) == 1
        assert result.transitions[0].transition_type == "melting"

        # Verify calculation results are reasonable
        assert result.H_final != 0  # Should have calculated enthalpy
        assert result.S_final != 0  # Should have calculated entropy
        assert result.G_final != 0  # Should have calculated Gibbs energy
        assert result.Cp_final > 0  # Heat capacity should be positive

    def test_temperature_below_298K(self, calculator, h2o_records):
        """Test calculation with temperatures below 298.15K."""
        result = calculator.calculate_multi_phase_properties(
            records=h2o_records[:1],  # Only solid phase
            trajectory=[250.0, 273.15]  # Below and at 298.15K
        )

        assert result.T_target == 273.15
        assert isinstance(result, MultiPhaseProperties)

    def test_custom_trajectory(self, calculator, feo_records):
        """Test custom temperature trajectory."""
        custom_trajectory = [298.15, 500.0, 1000.0, 1500.0, 1642.0, 1800.0]

        result = calculator.calculate_multi_phase_properties(
            records=feo_records,
            trajectory=custom_trajectory
        )

        assert result.T_target == 1800.0
        assert len(result.segments) == 2  # Should cross phase boundary

    def test_single_record_no_transitions(self, calculator, h2o_records):
        """Test single record produces no transitions."""
        result = calculator.calculate_multi_phase_properties(
            records=[h2o_records[1]],  # Only liquid phase
            trajectory=[298.15, 350.0]
        )

        assert len(result.segments) == 1
        assert len(result.transitions) == 0