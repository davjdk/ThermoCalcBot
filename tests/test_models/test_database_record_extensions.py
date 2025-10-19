"""
Unit tests for DatabaseRecord extension methods (Stage 02).

Tests the new multi-phase calculation support methods added to DatabaseRecord.
"""

import pytest
from thermo_agents.models.search import DatabaseRecord


@pytest.fixture
def base_record():
    """Base record with H298≠0."""
    return DatabaseRecord(
        formula="FeO",
        phase="s",
        tmin=298.0,
        tmax=600.0,
        h298=-265.053,  # кДж/моль → Дж/моль
        s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )


@pytest.fixture
def continuation_record():
    """Continuation record with H298=0."""
    return DatabaseRecord(
        formula="FeO",
        phase="s",
        tmin=600.0,
        tmax=900.0,
        h298=0.0,  # Requires accumulation
        s298=0.0,
        f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )


@pytest.fixture
def liquid_record():
    """Record for liquid phase."""
    return DatabaseRecord(
        formula="FeO",
        phase="l",
        tmin=1650.0,
        tmax=5000.0,
        h298=24.058,
        s298=14.581,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )


class TestIsBaseRecord:
    """Test the is_base_record method."""

    def test_base_record_is_detected(self, base_record):
        """Test that records with H298≠0 are identified as base records."""
        assert base_record.is_base_record() is True

    def test_continuation_record_is_not_base(self, continuation_record):
        """Test that records with H298=0 are not base records."""
        assert continuation_record.is_base_record() is False

    def test_s298_nonzero_makes_record_base(self):
        """Test that records with S298≠0 are also base records."""
        record = DatabaseRecord(
            formula="Test", phase="s", tmin=298.0, tmax=500.0,
            h298=0.0, s298=50.0,  # S298≠0 makes it base
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        )
        assert record.is_base_record() is True

    def test_small_values_below_threshold(self):
        """Test that very small values are treated as zero."""
        record = DatabaseRecord(
            formula="Test", phase="s", tmin=298.0, tmax=500.0,
            h298=1e-8, s298=0.0,  # Below threshold
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        )
        assert record.is_base_record() is False


class TestCoversTemperature:
    """Test the covers_temperature method."""

    def test_covers_temperature_inside_range(self, base_record):
        """Test temperature inside the range."""
        assert base_record.covers_temperature(298.0) is True
        assert base_record.covers_temperature(450.0) is True
        assert base_record.covers_temperature(600.0) is True

    def test_covers_temperature_outside_range(self, base_record):
        """Test temperature outside the range."""
        assert base_record.covers_temperature(200.0) is False
        assert base_record.covers_temperature(700.0) is False

    def test_covers_temperature_exact_boundaries(self, base_record):
        """Test exact boundary temperatures."""
        assert base_record.covers_temperature(298.0) is True  # Tmin
        assert base_record.covers_temperature(600.0) is True  # Tmax


class TestHasPhaseTransitionAt:
    """Test the has_phase_transition_at method."""

    def test_detects_melting_transition(self, base_record):
        """Test detection of melting transition."""
        assert base_record.has_phase_transition_at(1650.0) == "melting"
        assert base_record.has_phase_transition_at(1650.001) == "melting"
        assert base_record.has_phase_transition_at(1649.999) == "melting"

    def test_detects_boiling_transition(self, base_record):
        """Test detection of boiling transition."""
        assert base_record.has_phase_transition_at(3687.0) == "boiling"
        assert base_record.has_phase_transition_at(3687.0005) == "boiling"

    def test_no_transition_at_regular_temperature(self, base_record):
        """Test no transition at regular temperature."""
        assert base_record.has_phase_transition_at(1000.0) is None

    def test_custom_tolerance(self):
        """Test custom tolerance parameter."""
        record = DatabaseRecord(
            formula="Test", phase="s", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=400.0, tboil=600.0, reliability_class=1
        )

        # With default tolerance
        assert record.has_phase_transition_at(400.05) is None

        # With larger tolerance
        assert record.has_phase_transition_at(400.05, tolerance=0.1) == "melting"

    def test_zero_melting_boiling_points(self):
        """Test handling of zero melting/boiling points."""
        record = DatabaseRecord(
            formula="Test", phase="s", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=0.0, tboil=0.0, reliability_class=1
        )

        assert record.has_phase_transition_at(0.0) is None
        assert record.has_phase_transition_at(273.15) is None


class TestGetTransitionType:
    """Test the get_transition_type method."""

    def test_same_phase_no_transition(self, base_record, continuation_record):
        """Test that same phase records have no transition."""
        transition = base_record.get_transition_type(continuation_record)
        assert transition is None

    def test_solid_to_liquid_transition(self, base_record, liquid_record):
        """Test solid to liquid transition detection."""
        solid_to_liquid = DatabaseRecord(
            formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
            h298=0.0, s298=0.0,
            f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        )
        transition = solid_to_liquid.get_transition_type(liquid_record)
        assert transition == "s→l"

    def test_gap_between_records_no_transition(self):
        """Test that records with gaps have no transition."""
        record1 = DatabaseRecord(
            formula="X", phase="s", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="X", phase="s", tmin=600.0, tmax=1000.0,  # Gap 500-600K
            h298=0.0, s298=0.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        )

        transition = record1.get_transition_type(record2)
        assert transition is None

    def test_none_phases_handling(self):
        """Test handling of None phases."""
        record1 = DatabaseRecord(
            formula="X", phase=None, tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=0.0, tboil=0.0, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="X", phase="s", tmin=500.0, tmax=1000.0,
            h298=0.0, s298=0.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=0.0, tboil=0.0, reliability_class=1
        )

        transition = record1.get_transition_type(record2)
        assert transition == "→s"  # Empty string for None phase

    def test_case_insensitive_phases(self):
        """Test that phase comparison is case insensitive."""
        record1 = DatabaseRecord(
            formula="X", phase="S", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=500.0, tboil=1000.0, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="X", phase="L", tmin=500.0, tmax=1000.0,
            h298=0.0, s298=0.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=500.0, tboil=1000.0, reliability_class=1
        )

        transition = record1.get_transition_type(record2)
        assert transition == "s→l"


class TestGetTemperatureRange:
    """Test the get_temperature_range method."""

    def test_returns_correct_range(self, base_record):
        """Test that correct temperature range is returned."""
        tmin, tmax = base_record.get_temperature_range()
        assert tmin == 298.0
        assert tmax == 600.0

    def test_works_for_all_records(self, liquid_record):
        """Test that method works for all record types."""
        tmin, tmax = liquid_record.get_temperature_range()
        assert tmin == 1650.0
        assert tmax == 5000.0


class TestOverlapsWith:
    """Test the overlaps_with method."""

    def test_overlapping_records(self):
        """Test overlapping temperature ranges."""
        record1 = DatabaseRecord(
            formula="H2O", phase="s", tmin=200.0, tmax=273.15,
            h298=-285.83, s298=69.95,
            f1=30.0, f2=6.0, f3=6.0, f4=-2.0, f5=0.0, f6=0.0,
            tmelt=273.15, tboil=373.15, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="H2O", phase="l", tmin=273.15, tmax=373.15,
            h298=-285.83, s298=69.95,
            f1=75.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=273.15, tboil=373.15, reliability_class=1
        )

        assert record1.overlaps_with(record2) is True

    def test_non_overlapping_records(self):
        """Test non-overlapping temperature ranges."""
        record1 = DatabaseRecord(
            formula="H2O", phase="l", tmin=273.15, tmax=373.15,
            h298=-285.83, s298=69.95,
            f1=75.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=273.15, tboil=373.15, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="H2O", phase="g", tmin=500.0, tmax=1000.0,
            h298=-241.83, s298=188.83,
            f1=33.0, f2=2.5, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=273.15, tboil=373.15, reliability_class=1
        )

        assert record1.overlaps_with(record2) is False

    def test_edge_touching_overlaps(self):
        """Test that records touching at edges overlap."""
        record1 = DatabaseRecord(
            formula="X", phase="s", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=500.0, tboil=1000.0, reliability_class=1
        )

        record2 = DatabaseRecord(
            formula="X", phase="l", tmin=500.0, tmax=800.0,
            h298=0.0, s298=0.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=500.0, tboil=1000.0, reliability_class=1
        )

        assert record1.overlaps_with(record2) is True