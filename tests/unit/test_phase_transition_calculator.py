"""
Unit tests for PhaseTransitionCalculator - Stage 4 Implementation.

Tests the phase transition calculation functionality including:
- Property calculation at transition points
- Thermodynamic validation
- Transition corrections
- Multiple transition handling
"""

import pytest
from unittest.mock import Mock, patch
import logging

from src.thermo_agents.models.search import (
    PhaseTransition,
    DatabaseRecord,
    TransitionType
)
from src.thermo_agents.calculations.thermodynamic_calculator import (
    ThermodynamicProperties
)
from src.thermo_agents.calculations.phase_transition_calculator import (
    PhaseTransitionCalculator,
    TransitionCalculationError
)


class TestPhaseTransitionCalculator:
    """Test cases for PhaseTransitionCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create a PhaseTransitionCalculator instance."""
        mock_thermo_calc = Mock()
        return PhaseTransitionCalculator(mock_thermo_calc)

    @pytest.fixture
    def sample_transition(self):
        """Create a sample phase transition for testing."""
        return PhaseTransition(
            temperature=1650.0,
            from_phase='s',
            to_phase='l',
            transition_type=TransitionType.MELTING,
            delta_H_transition=31.5,  # kJ/mol
            delta_S_transition=19.1,  # J/(mol·K)
            reliability=0.8,
            calculation_method='calculated'
        )

    @pytest.fixture
    def sample_properties(self):
        """Create sample thermodynamic properties."""
        return ThermodynamicProperties(
            T=1650.0,
            H=-240500.0,  # J/mol
            S=60.0,  # J/(mol·K)
            G=-340000.0,  # J/mol
            Cp=50.0  # J/(mol·K)
        )

    def test_calculate_properties_at_transition(self, calculator, sample_transition, sample_properties):
        """Test calculation of properties at transition point."""
        h_before = sample_properties.H
        s_before = sample_properties.S
        cp_before = sample_properties.Cp

        h_after, s_after, g_after, cp_after = calculator.calculate_properties_at_transition(
            sample_transition, h_before, s_before, cp_before
        )

        # Check enthalpy jump
        expected_h = h_before + (sample_transition.delta_H_transition * 1000)
        assert h_after == expected_h

        # Check entropy jump
        expected_s = s_before + sample_transition.delta_S_transition
        assert s_after == expected_s

        # Check Gibbs energy calculation
        expected_g = h_after - sample_transition.temperature * s_after
        assert g_after == expected_g

        # Heat capacity should be unchanged (placeholder)
        assert cp_after == cp_before

    def test_validate_transition_thermodynamics_valid(self, calculator, sample_transition):
        """Test validation of thermodynamically correct transition."""
        assert calculator.validate_transition_thermodynamics(sample_transition) is True

    def test_validate_transition_thermodynamics_negative_enthalpy(self, calculator):
        """Test validation fails for negative enthalpy."""
        with pytest.raises(ValueError) as excinfo:
            invalid_transition = PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=-5.0,  # Negative!
                delta_S_transition=19.1,
                reliability=0.8,
                calculation_method='calculated'
            )

        # Check that the error message is appropriate
        assert "Энтальпия перехода" in str(excinfo.value)
        assert "отрицательна" in str(excinfo.value)

    def test_validate_transition_thermodynamics_negative_entropy(self, calculator):
        """Test validation fails for negative entropy."""
        with pytest.raises(ValueError) as excinfo:
            invalid_transition = PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=31.5,
                delta_S_transition=-5.0,  # Negative!
                reliability=0.8,
                calculation_method='calculated'
            )

        # Check that the error message is appropriate
        assert "Энтропия перехода" in str(excinfo.value)
        assert "отрицательна" in str(excinfo.value)

    def test_validate_transition_thermodynamics_boiling_outside_trouton(
        self, calculator, caplog
    ):
        """Test validation warning for boiling entropy outside Trouton's rule."""
        # Create transition with entropy outside Trouton's range (75-95 J/mol·K)
        unusual_boiling = PhaseTransition(
            temperature=373.0,
            from_phase='l',
            to_phase='g',
            transition_type=TransitionType.BOILING,
            delta_H_transition=40.0,
            delta_S_transition=107.2,  # Above Trouton's range
            reliability=0.6,
            calculation_method='calculated'
        )

        # Should still return True but log warning
        assert calculator.validate_transition_thermodynamics(unusual_boiling) is True

        # Check that warning was logged
        assert "Энтропия кипения выходит за пределы правила Трутона" in caplog.text

    def test_validate_transition_thermodynamics_melting_unusual_entropy(
        self, calculator, caplog
    ):
        """Test validation warning for unusual melting entropy."""
        unusual_melting = PhaseTransition(
            temperature=1000.0,
            from_phase='s',
            to_phase='l',
            transition_type=TransitionType.MELTING,
            delta_H_transition=60.0,
            delta_S_transition=60.0,  # Above typical range (8-35)
            reliability=0.3,
            calculation_method='heuristic'
        )

        # Should still return True but log warning
        assert calculator.validate_transition_thermodynamics(unusual_melting) is True

        # Check that warning was logged
        assert "Энтропия плавления выходит за типичные пределы" in caplog.text

    def test_calculate_transition_corrections(self, calculator, sample_transition):
        """Test calculation of transition corrections."""
        # Create mock database records
        from_record = Mock(spec=DatabaseRecord)
        to_record = Mock(spec=DatabaseRecord)

        # Mock thermodynamic calculator responses
        from_props = ThermodynamicProperties(
            T=1650.0,
            H=-240500.0,
            S=59.0,
            G=-340000.0,
            Cp=45.0
        )
        to_props = ThermodynamicProperties(
            T=1650.0,
            H=-209000.0,
            S=78.0,
            G=-340000.0,
            Cp=55.0
        )

        calculator.thermodynamic_calculator.calculate_properties.side_effect = [from_props, to_props]

        corrections = calculator.calculate_transition_corrections(
            from_record, to_record, sample_transition, 1650.0
        )

        # Check that corrections are calculated
        assert "actual_h_jump" in corrections
        assert "actual_s_jump" in corrections
        assert "transition_h_jump" in corrections
        assert "corrected_h" in corrections
        assert "corrected_s" in corrections
        assert "h_correction" in corrections
        assert "s_correction" in corrections

        # Check actual jumps
        assert corrections["actual_h_jump"] == 31500.0  # -209000 - (-240500)
        assert corrections["actual_s_jump"] == 19.0    # 78.0 - 59.0

    def test_detect_transition_at_temperature_exact_match(self, calculator, sample_transition):
        """Test detection of transition at exact temperature."""
        transitions = [sample_transition]

        found = calculator.detect_transition_at_temperature(transitions, 1650.0)

        assert found is not None
        assert found.temperature == 1650.0
        assert found.from_phase == 's'
        assert found.to_phase == 'l'

    def test_detect_transition_at_temperature_with_tolerance(self, calculator, sample_transition):
        """Test detection of transition within tolerance."""
        transitions = [sample_transition]

        # Test with small temperature difference
        found = calculator.detect_transition_at_temperature(transitions, 1650.0005)

        assert found is not None
        assert found.temperature == 1650.0

    def test_detect_transition_at_temperature_no_match(self, calculator, sample_transition):
        """Test no transition detected when temperature doesn't match."""
        transitions = [sample_transition]

        found = calculator.detect_transition_at_temperature(transitions, 1600.0)

        assert found is None

    def test_detect_transition_at_temperature_empty_list(self, calculator):
        """Test no transition detected with empty transition list."""
        found = calculator.detect_transition_at_temperature([], 1650.0)

        assert found is None

    def test_apply_transition_to_properties(self, calculator, sample_transition, sample_properties):
        """Test applying transition to thermodynamic properties."""
        updated_props = calculator.apply_transition_to_properties(sample_properties, sample_transition)

        # Check temperature is unchanged
        assert updated_props.temperature == sample_properties.temperature

        # Check enthalpy jump
        expected_h = sample_properties.enthalpy + (sample_transition.delta_H_transition * 1000)
        assert updated_props.enthalpy == expected_h

        # Check entropy jump
        expected_s = sample_properties.entropy + sample_transition.delta_S_transition
        assert updated_props.entropy == expected_s

        # Check Gibbs energy is recalculated
        expected_g = updated_props.enthalpy - updated_props.temperature * updated_props.entropy
        assert updated_props.gibbs_energy == expected_g

        # Check phase is updated
        assert updated_props.phase == sample_transition.to_phase

    def test_apply_transition_to_properties_temperature_mismatch(
        self, calculator, sample_transition, sample_properties, caplog
    ):
        """Test warning when property temperature doesn't match transition temperature."""
        # Create properties with different temperature
        mismatched_props = ThermodynamicProperties(
            T=1600.0,  # Different from transition
            H=-240500.0,
            S=60.0,
            G=-340000.0,
            Cp=50.0
        )

        updated_props = calculator.apply_transition_to_properties(mismatched_props, sample_transition)

        # Should still apply transition but log warning
        assert updated_props.phase == sample_transition.to_phase
        assert "не совпадает с температурой перехода" in caplog.text

    def test_calculate_multiple_transitions(self, calculator):
        """Test calculation with multiple transitions."""
        # Create multiple transitions
        transitions = [
            PhaseTransition(
                temperature=1000.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=20.0,
                delta_S_transition=20.0
            ),
            PhaseTransition(
                temperature=2000.0,
                from_phase='l',
                to_phase='g',
                transition_type=TransitionType.BOILING,
                delta_H_transition=40.0,
                delta_S_transition=20.0
            )
        ]

        # Initial properties
        initial_props = ThermodynamicProperties(
            T=500.0,
            H=-300000.0,
            S=50.0,
            G=-325000.0,
            Cp=30.0
        )
        # Add phase attribute manually since it's not in the dataclass
        initial_props.phase = 's'

        # Target temperatures including transitions
        target_temps = [500.0, 1000.0, 1500.0, 2000.0, 2500.0]

        results = calculator.calculate_multiple_transitions(
            initial_props, transitions, target_temps
        )

        # Should get results for all target temperatures
        assert len(results) == len(target_temps)

        # Check phase progression
        assert results[0].phase == 's'   # Before first transition
        assert results[1].phase == 'l'   # After melting
        assert results[2].phase == 'l'   # Between transitions
        assert results[3].phase == 'g'   # After boiling
        assert results[4].phase == 'g'   # After last transition

    def test_get_transition_summary(self, calculator):
        """Test generation of transition summary."""
        transitions = [
            PhaseTransition(
                temperature=1000.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=20.0,
                delta_S_transition=20.0,
                reliability=0.8,
                calculation_method='calculated'
            ),
            PhaseTransition(
                temperature=2000.0,
                from_phase='l',
                to_phase='g',
                transition_type=TransitionType.BOILING,
                delta_H_transition=40.0,
                delta_S_transition=20.0,
                reliability=0.6,
                calculation_method='heuristic',
                warning="Эвристическая оценка"
            )
        ]

        summary = calculator.get_transition_summary(transitions)

        # Check summary statistics
        assert summary["transitions_count"] == 2
        assert summary["melting_transitions"] == 1
        assert summary["boiling_transitions"] == 1
        assert summary["sublimation_transitions"] == 0
        assert summary["min_transition_temp"] == 1000.0
        assert summary["max_transition_temp"] == 2000.0
        assert summary["temperature_range"] == 1000.0
        assert summary["average_reliability"] == 0.7  # (0.8 + 0.6) / 2
        assert "calculated" in summary["calculation_methods"]
        assert "heuristic" in summary["calculation_methods"]
        assert summary["has_warnings"] is True
        assert "Эвристическая оценка" in summary["warnings"]

    def test_get_transition_summary_empty(self, calculator):
        """Test summary generation with empty transition list."""
        summary = calculator.get_transition_summary([])

        assert summary["transitions_count"] == 0
        assert len(summary) == 1  # Only the count field

    def test_error_handling_in_calculate_properties_at_transition(
        self, calculator, sample_transition
    ):
        """Test error handling in transition property calculation."""
        # This test ensures the method handles edge cases gracefully
        # No specific error conditions in current implementation
        h_before = -240500.0
        s_before = 60.0
        cp_before = 50.0

        # Should not raise any exceptions
        h_after, s_after, g_after, cp_after = calculator.calculate_properties_at_transition(
            sample_transition, h_before, s_before, cp_before
        )

        # Should return valid results
        assert isinstance(h_after, float)
        assert isinstance(s_after, float)
        assert isinstance(g_after, float)
        assert isinstance(cp_after, float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])