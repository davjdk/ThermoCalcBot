"""
Unit tests for PhaseSegment model.
"""

import pytest
from thermo_agents.models.search import PhaseSegment, DatabaseRecord


def test_phase_segment_creation():
    """Test PhaseSegment creation."""
    record = DatabaseRecord(
        formula="H2O",
        phase="s",
        tmin=200.0,
        tmax=273.15,
        h298=-285830.0,
        s298=69.95,
        f1=30.092, f2=6.832, f3=6.793, f4=-2.534, f5=0.082, f6=-0.007,
        tmelt=273.15,
        tboil=373.15,
        reliability_class=1
    )

    segment = PhaseSegment(
        record=record,
        T_start=200.0,
        T_end=273.15,
        H_start=-285830.0,
        S_start=69.95,
        delta_H=5000.0,
        delta_S=15.0,
        is_transition_boundary=True
    )

    assert segment.T_start == 200.0
    assert segment.T_end == 273.15
    assert segment.is_transition_boundary is True
    assert segment.record.formula == "H2O"


def test_phase_segment_validation_temperature():
    """Test temperature range validation."""
    record = DatabaseRecord(
        formula="H2O", phase="s", tmin=200.0, tmax=273.15,
        h298=-285830.0, s298=69.95,
        f1=30.0, f2=6.0, f3=6.0, f4=-2.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )

    # Test T_end < T_start (with valid temperature range for record)
    with pytest.raises(ValueError, match="T_end must be greater than T_start"):
        PhaseSegment(
            record=record,
            T_start=250.0,  # Within record range
            T_end=200.0,   # Invalid: T_end < T_start
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
        )

    # Test T_end == T_start
    with pytest.raises(ValueError, match="T_end must be greater than T_start"):
        PhaseSegment(
            record=record,
            T_start=250.0,  # Within record range
            T_end=250.0,   # Invalid: T_end == T_start
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
        )


def test_phase_segment_validation_record_range():
    """Test validation of temperatures within record range."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    # Test T_start < record.tmin
    with pytest.raises(ValueError, match="Temperature 250.0K is outside record range"):
        PhaseSegment(
            record=record,
            T_start=250.0,  # Below record range
            T_end=400.0,
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
        )

    # Test T_end > record.tmax
    with pytest.raises(ValueError, match="Temperature 700.0K is outside record range"):
        PhaseSegment(
            record=record,
            T_start=300.0,
            T_end=700.0,  # Above record range
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
        )


def test_phase_segment_to_dict():
    """Test segment serialization."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment = PhaseSegment(
        record=record,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85,
        is_transition_boundary=False
    )

    result = segment.to_dict()

    assert result["formula"] == "FeO"
    assert result["phase"] == "s"
    assert result["T_range"] == [298.0, 600.0]
    assert result["H_range"] == [-265053.0, -249633.0]  # H_start + delta_H
    assert result["S_range"][0] == 59.807
    assert abs(result["S_range"][1] - 96.657) < 0.001  # S_start + delta_S
    assert result["is_transition"] is False


def test_phase_segment_default_values():
    """Test PhaseSegment with default values."""
    record = DatabaseRecord(
        formula="CO2", phase="g", tmin=298.0, tmax=1000.0,
        h298=-393509.0, s298=213.74,
        f1=44.228, f2=8.987, f3=-8.742, f4=3.003, f5=0.0, f6=0.0,
        tmelt=194.7, tboil=194.7, reliability_class=1
    )

    segment = PhaseSegment(
        record=record,
        T_start=298.0,
        T_end=500.0,
        H_start=-393509.0,
        S_start=213.74,
        delta_H=8500.0,
        delta_S=25.3
    )

    # Test default value for is_transition_boundary
    assert segment.is_transition_boundary is False