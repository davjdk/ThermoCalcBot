"""
Simplified unit tests for multi-phase thermodynamic calculator.
"""

import pytest
from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from thermo_agents.models.search import DatabaseRecord, TransitionType


class TestMultiPhaseCalculatorSimple:
    """Simplified tests for multi-phase calculator functionality."""

    @pytest.fixture
    def calculator(self):
        """Create ThermodynamicCalculator instance."""
        return ThermodynamicCalculator()

    @pytest.fixture
    def simple_records(self):
        """Create simple test records."""
        return [
            DatabaseRecord(
                id=1,
                formula="Test",
                name="Test solid",
                phase="s",
                tmin=298.15,
                tmax=500.0,
                h298=-100000.0,
                s298=50.0,
                f1=30.0,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=500.0,
                tboil=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="Test",
                name="Test liquid",
                phase="l",
                tmin=500.0,
                tmax=1000.0,
                h298=-95000.0,  # Different H298 to simulate phase transition
                s298=55.0,
                f1=40.0,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=500.0,
                tboil=0.0,
                reliability_class=1
            )
        ]

    def test_empty_records_error(self, calculator):
        """Test error handling for empty records list."""
        with pytest.raises(ValueError, match="Список записей не может быть пустым"):
            calculator.calculate_multi_phase_properties(records=[])

    def test_determine_transition_type(self, calculator):
        """Test transition type determination."""
        assert calculator._determine_transition_type("s", "l") == TransitionType.MELTING
        assert calculator._determine_transition_type("l", "g") == TransitionType.BOILING
        assert calculator._determine_transition_type("s", "g") == TransitionType.SUBLIMATION
        assert calculator._determine_transition_type("l", "s") is None
        assert calculator._determine_transition_type("x", "y") is None

    def test_basic_multi_phase_calculation(self, calculator, simple_records):
        """Test basic multi-phase calculation."""
        result = calculator.calculate_multi_phase_properties(
            records=simple_records,
            trajectory=[298.15, 400.0, 600.0, 800.0]
        )

        assert result.T_target == 800.0
        assert len(result.segments) == 2
        assert len(result.phase_transitions) == 1
        assert result.phase_transitions[0].transition_type == TransitionType.MELTING
        assert result.phase_transitions[0].from_phase == "s"
        assert result.phase_transitions[0].to_phase == "l"

    def test_single_phase_calculation(self, calculator, simple_records):
        """Test calculation with single phase only."""
        result = calculator.calculate_multi_phase_properties(
            records=[simple_records[0]],  # Only solid phase
            trajectory=[298.15, 400.0]
        )

        assert result.T_target == 400.0
        assert len(result.segments) == 1
        assert len(result.phase_transitions) == 0

    def test_performance_target(self, calculator, simple_records):
        """Test performance target (<500ms for typical calculation)."""
        import time

        start_time = time.perf_counter()

        result = calculator.calculate_multi_phase_properties(
            records=simple_records,
            trajectory=[298.15, 500.0, 1000.0]
        )

        elapsed_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

        assert elapsed_time < 500.0, f"Performance target missed: {elapsed_time:.2f}ms > 500ms"
        assert result.T_target == 1000.0

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
                h298=-95000.0, s298=55.0, f1=40.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
                tmelt=0.0, tboil=0.0, reliability_class=1
            )
        ]

        with pytest.raises(ValueError, match="Обнаружен пробел между записями"):
            calculator.calculate_multi_phase_properties(records=records_with_gap)

    def test_integration_methods(self, calculator, simple_records):
        """Test integration methods work correctly."""
        segment = calculator._create_segment_from_record(simple_records[0])

        # Test enthalpy integration
        delta_H, error = calculator._integrate_enthalpy(segment, 298.15, 400.0)
        assert delta_H > 0  # Should be positive for heating
        assert error is None or abs(error) < 1e-6

        # Test entropy integration
        delta_S, error = calculator._integrate_entropy(segment, 298.15, 400.0)
        assert delta_S > 0  # Should be positive for heating
        assert error is None or abs(error) < 1e-9

    def test_cp_calculation(self, calculator, simple_records):
        """Test heat capacity calculation."""
        Cp = calculator._calculate_cp_at_temperature(simple_records[0], 400.0)
        assert Cp > 0  # Heat capacity should be positive
        assert isinstance(Cp, float)

    def test_disable_phase_transitions(self, calculator, simple_records):
        """Test calculation with disabled phase transitions."""
        result = calculator.calculate_multi_phase_properties(
            records=simple_records,
            trajectory=[298.15, 600.0],
            include_phase_transitions=False
        )

        assert len(result.phase_transitions) == 0
        assert len(result.segments) == 2