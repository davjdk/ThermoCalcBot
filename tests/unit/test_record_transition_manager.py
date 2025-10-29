"""
Unit tests for RecordTransitionManager (Stage 3 component).

This module tests the functionality of the RecordTransitionManager class,
which handles seamless transitions between database records in multi-phase
thermodynamic calculations.
"""

import pytest
import math
from unittest.mock import Mock, patch

from src.thermo_agents.calculations.record_transition_manager import (
    RecordTransitionManager,
    TransitionCorrection
)
from src.thermo_agents.models.search import DatabaseRecord


class TestRecordTransitionManager:
    """Test cases for RecordTransitionManager."""

    @pytest.fixture
    def transition_manager(self):
        """Create a RecordTransitionManager instance for testing."""
        return RecordTransitionManager(tolerance=1e-6)

    @pytest.fixture
    def sample_record_1(self):
        """Create a sample database record."""
        return DatabaseRecord(
            id=1,
            formula="FeO",
            phase="s",
            tmin=298.0,
            tmax=600.0,
            h298=-265.053,  # kJ/mol
            s298=59.807,     # J/(mol·K)
            f1=45.2,
            f2=15.8,
            f3=-2.1,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

    @pytest.fixture
    def sample_record_2(self):
        """Create a second sample database record."""
        return DatabaseRecord(
            id=2,
            formula="FeO",
            phase="s",
            tmin=600.0,
            tmax=900.0,
            h298=0.0,        # kJ/mol (requires accumulation)
            s298=0.0,        # J/(mol·K) (requires accumulation)
            f1=48.1,
            f2=16.2,
            f3=-2.3,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

    def test_init(self, transition_manager):
        """Test RecordTransitionManager initialization."""
        assert transition_manager.tolerance == 1e-6
        assert transition_manager.get_cache_size() == 0

    def test_calculate_properties_at_temperature(self, transition_manager, sample_record_1):
        """Test calculation of thermodynamic properties at a specific temperature."""
        H, S = transition_manager._calculate_properties_at_temperature(sample_record_1, 400.0)

        # Check that values are reasonable
        assert H > -300000  # Should be close to -265 kJ + integration
        assert S > 0        # Should be positive
        assert isinstance(H, float)
        assert isinstance(S, float)

    def test_calculate_properties_at_temperature_outside_range(self, transition_manager, sample_record_1):
        """Test error handling for temperature outside record range."""
        with pytest.raises(ValueError, match="outside record range"):
            transition_manager._calculate_properties_at_temperature(sample_record_1, 200.0)

    def test_calculate_heat_capacity(self, transition_manager, sample_record_1):
        """Test heat capacity calculation."""
        Cp = transition_manager._calculate_heat_capacity(sample_record_1, 400.0)

        # Should be positive and reasonable
        assert Cp > 0
        assert Cp < 200  # Reasonable upper bound for most compounds

    def test_calculate_transition_corrections_continuous(
        self, transition_manager, sample_record_1, sample_record_2
    ):
        """Test transition corrections for naturally continuous records."""
        # Mock the property calculations to return the same values
        with patch.object(
            transition_manager,
            '_calculate_properties_at_temperature',
            side_effect=[(1000.0, 50.0), (1000.0, 50.0)]  # H, S for record 1 and 2
        ):
            corrections = transition_manager.calculate_transition_corrections(
                sample_record_1, sample_record_2, 600.0
            )

            assert corrections["delta_H"] == 0.0
            assert corrections["delta_S"] == 0.0
            assert corrections["warning"] is None

    def test_calculate_transition_corrections_with_discontinuity(
        self, transition_manager, sample_record_1, sample_record_2
    ):
        """Test transition corrections when there's a discontinuity."""
        # Mock the property calculations to return different values
        with patch.object(
            transition_manager,
            '_calculate_properties_at_temperature',
            side_effect=[(1000.0, 50.0), (950.0, 48.0)]  # H, S for record 1 and 2
        ):
            corrections = transition_manager.calculate_transition_corrections(
                sample_record_1, sample_record_2, 600.0
            )

            assert corrections["delta_H"] == 50.0  # 1000 - 950
            assert corrections["delta_S"] == 2.0   # 50 - 48
            assert corrections["warning"] is not None

    def test_calculate_transition_corrections_large_discontinuity_warning(
        self, transition_manager, sample_record_1, sample_record_2
    ):
        """Test warning generation for large discontinuities."""
        # Mock a large enthalpy discontinuity (> 1 kJ/mol)
        with patch.object(
            transition_manager,
            '_calculate_properties_at_temperature',
            side_effect=[(100000.0, 50.0), (98000.0, 48.0)]  # Large H difference
        ):
            corrections = transition_manager.calculate_transition_corrections(
                sample_record_1, sample_record_2, 600.0
            )

            assert corrections["delta_H"] == 2000.0
            assert "Значительный разрыв энтальпии" in corrections["warning"]

    def test_ensure_continuity(self, transition_manager, sample_record_1, sample_record_2):
        """Test the ensure_continuity method."""
        # Mock the calculation to return specific corrections
        with patch.object(
            transition_manager,
            'calculate_transition_corrections',
            return_value={"delta_H": 100.0, "delta_S": 2.0, "warning": None}
        ):
            delta_H, delta_S = transition_manager.ensure_continuity(
                sample_record_1, sample_record_2, 600.0
            )

            assert delta_H == 100.0
            assert delta_S == 2.0

    def test_validate_record_compatibility(self, transition_manager, sample_record_1, sample_record_2):
        """Test record compatibility validation."""
        # Records should be compatible (touching by temperature)
        assert transition_manager.validate_record_compatibility(sample_record_1, sample_record_2)

    def test_validate_record_compatibility_no_touch(self, transition_manager, sample_record_1):
        """Test incompatibility when records don't touch."""
        unrelated_record = DatabaseRecord(
            id=3,
            formula="FeO",
            phase="s",
            tmin=650.0,  # Gap between records
            tmax=900.0,
            h298=0.0,
            s298=0.0,
            f1=48.1,
            f2=16.2,
            f3=-2.3,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

        assert not transition_manager.validate_record_compatibility(sample_record_1, unrelated_record)

    def test_validate_record_compatibility_different_phase(self, transition_manager, sample_record_1):
        """Test incompatibility when records have different phases."""
        liquid_record = DatabaseRecord(
            id=3,
            formula="FeO",
            phase="l",  # Different phase
            tmin=600.0,
            tmax=900.0,
            h298=0.0,
            s298=0.0,
            f1=48.1,
            f2=16.2,
            f3=-2.3,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

        assert not transition_manager.validate_record_compatibility(sample_record_1, liquid_record)

    def test_analyze_transition_quality_excellent(
        self, transition_manager, sample_record_1, sample_record_2
    ):
        """Test transition quality analysis for excellent quality."""
        # Mock continuous transition
        with patch.object(
            transition_manager,
            'calculate_transition_corrections',
            return_value={"delta_H": 0.0, "delta_S": 0.0, "warning": None}
        ):
            with patch.object(
                transition_manager,
                '_calculate_properties_at_temperature',
                side_effect=[(1000.0, 50.0), (1000.0, 50.0)]
            ):
                analysis = transition_manager.analyze_transition_quality(
                    sample_record_1, sample_record_2, 600.0
                )

                assert analysis["quality"] == "excellent"
                assert analysis["is_continuous"] is True
                assert analysis["warning"] is None

    def test_analyze_transition_quality_poor(
        self, transition_manager, sample_record_1, sample_record_2
    ):
        """Test transition quality analysis for poor quality."""
        # Mock large discontinuity
        with patch.object(
            transition_manager,
            'calculate_transition_corrections',
            return_value={"delta_H": 5000.0, "delta_S": 20.0, "warning": "Large discontinuity"}
        ):
            with patch.object(
                transition_manager,
                '_calculate_properties_at_temperature',
                side_effect=[(100000.0, 50.0), (95000.0, 30.0)]
            ):
                analysis = transition_manager.analyze_transition_quality(
                    sample_record_1, sample_record_2, 600.0
                )

                assert analysis["quality"] == "poor"
                assert analysis["is_continuous"] is False
                assert analysis["warning"] == "Large discontinuity"

    def test_caching_functionality(self, transition_manager, sample_record_1, sample_record_2):
        """Test that transition calculations are properly cached."""
        # First calculation should populate cache
        corrections1 = transition_manager.calculate_transition_corrections(
            sample_record_1, sample_record_2, 600.0
        )

        assert transition_manager.get_cache_size() == 1

        # Second calculation should use cache
        corrections2 = transition_manager.calculate_transition_corrections(
            sample_record_1, sample_record_2, 600.0
        )

        assert corrections1 == corrections2
        assert transition_manager.get_cache_size() == 1  # Still only one entry

    def test_clear_cache(self, transition_manager, sample_record_1, sample_record_2):
        """Test cache clearing functionality."""
        # Add something to cache
        transition_manager.calculate_transition_corrections(
            sample_record_1, sample_record_2, 600.0
        )

        assert transition_manager.get_cache_size() > 0

        # Clear cache
        transition_manager.clear_cache()
        assert transition_manager.get_cache_size() == 0

    def test_integrate_heat_capacity(self, transition_manager, sample_record_1):
        """Test heat capacity integration."""
        delta_H, _ = transition_manager._integrate_heat_capacity(sample_record_1, 298.15, 400.0)

        # Should be positive (temperature increasing)
        assert delta_H > 0
        assert isinstance(delta_H, float)

    def test_integrate_entropy(self, transition_manager, sample_record_1):
        """Test entropy integration."""
        _, delta_S = transition_manager._integrate_entropy(sample_record_1, 298.15, 400.0)

        # Should be positive (temperature increasing)
        assert delta_S > 0
        assert isinstance(delta_S, float)

    def test_integrate_reverse_direction(self, transition_manager, sample_record_1):
        """Test integration in reverse direction (higher to lower temperature)."""
        delta_H_reverse, _ = transition_manager._integrate_heat_capacity(sample_record_1, 400.0, 298.15)
        delta_H_forward, _ = transition_manager._integrate_heat_capacity(sample_record_1, 298.15, 400.0)

        # Should be opposite signs
        assert abs(delta_H_reverse + delta_H_forward) < 1e-6  # Should sum to zero

    def test_transition_correction_dataclass(self):
        """Test TransitionCorrection dataclass."""
        correction = TransitionCorrection(
            delta_H=100.0,
            delta_S=2.0,
            warning="Test warning",
            is_natural_continuity=False
        )

        assert correction.delta_H == 100.0
        assert correction.delta_S == 2.0
        assert correction.warning == "Test warning"
        assert correction.is_natural_continuity is False

        # Test to_dict method
        correction_dict = correction.to_dict()
        assert correction_dict["delta_H"] == 100.0
        assert correction_dict["delta_S"] == 2.0
        assert correction_dict["warning"] == "Test warning"
        assert correction_dict["natural_continuity"] is False

    def test_edge_case_zero_tolerance(self):
        """Test behavior with zero tolerance."""
        manager = RecordTransitionManager(tolerance=0.0)

        # Even tiny differences should be detected with zero tolerance
        with patch.object(
            manager,
            '_calculate_properties_at_temperature',
            side_effect=[(1000.0, 50.0), (1000.000001, 50.0)]
        ):
            corrections = manager.calculate_transition_corrections(
                Mock(id=1), Mock(id=2), 600.0
            )

            assert corrections["delta_H"] == -0.000001  # Should detect tiny difference