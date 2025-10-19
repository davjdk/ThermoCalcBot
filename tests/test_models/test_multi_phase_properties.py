"""
Unit tests for MultiPhaseProperties model.
"""

import pytest
from thermo_agents.models.search import (
    DatabaseRecord,
    PhaseSegment,
    PhaseTransition,
    MultiPhaseProperties,
    TransitionType
)


def test_multi_phase_properties_creation():
    """Test basic MultiPhaseProperties creation."""
    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-235633.0,
        S_final=155.44,
        G_final=-499582.0,
        Cp_final=68.199
    )

    assert result.T_target == 1700.0
    assert result.H_final == -235633.0
    assert result.S_final == 155.44
    assert result.G_final == -499582.0
    assert result.Cp_final == 68.199

    # Test default values
    assert len(result.segments) == 0
    assert len(result.phase_transitions) == 0
    assert len(result.warnings) == 0


def test_multi_phase_properties_with_segments_and_transitions():
    """Test MultiPhaseProperties with segments and transitions."""
    # Create a dummy record
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    # Create a segment
    segment = PhaseSegment(
        record=record,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85
    )

    # Create a transition
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-235633.0,
        S_final=155.44,
        G_final=-499582.0,
        Cp_final=68.199,
        segments=[segment],
        phase_transitions=[transition],
        warnings=["Test warning"]
    )

    assert len(result.segments) == 1
    assert len(result.phase_transitions) == 1
    assert len(result.warnings) == 1
    assert result.warnings[0] == "Test warning"


def test_multi_phase_properties_segments_validation():
    """Test segment sorting validation."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment1 = PhaseSegment(
        record=record,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85
    )

    # Create a different record for the second segment
    record2 = DatabaseRecord(
        formula="FeO", phase="s", tmin=650.0, tmax=900.0,
        h298=-265053.0, s298=59.807,
        f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment2 = PhaseSegment(
        record=record2,
        T_start=650.0,  # After segment1 ends
        T_end=800.0,   # Within record2 range
        H_start=-249633.0,
        S_start=96.657,
        delta_H=10000.0,
        delta_S=20.0
    )

    # Valid: segments in order
    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-235633.0,
        S_final=155.44,
        G_final=-499582.0,
        Cp_final=68.199,
        segments=[segment1, segment2]
    )
    assert len(result.segments) == 2

    # Invalid: segments out of order
    with pytest.raises(ValueError, match="Segments must be sorted by temperature"):
        MultiPhaseProperties(
            T_target=1700.0,
            H_final=-235633.0,
            S_final=155.44,
            G_final=-499582.0,
            Cp_final=68.199,
            segments=[segment2, segment1]  # segment2 starts before segment1 ends
        )


def test_multi_phase_properties_to_dict():
    """Test result serialization."""
    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-235633.0,
        S_final=155.44,
        G_final=-499582.0,
        Cp_final=68.199,
        warnings=["Test warning"]
    )

    serialized = result.to_dict()

    assert serialized["T_target"] == 1700.0
    assert "thermodynamic_properties" in serialized

    props = serialized["thermodynamic_properties"]
    assert props["H"] == -235.633  # Converted to kJ/mol
    assert props["S"] == 155.44
    assert props["G"] == -499.582  # Converted to kJ/mol
    assert props["Cp"] == 68.199

    assert serialized["segments_count"] == 0
    assert serialized["transitions_count"] == 0
    assert serialized["warnings"] == ["Test warning"]


def test_multi_phase_properties_has_phase_transitions():
    """Test has_phase_transitions property."""
    # No transitions
    result1 = MultiPhaseProperties(
        T_target=1000.0,
        H_final=0.0,
        S_final=0.0,
        G_final=0.0,
        Cp_final=0.0
    )
    assert result1.has_phase_transitions is False

    # With transitions
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l"
    )
    result2 = MultiPhaseProperties(
        T_target=1000.0,
        H_final=0.0,
        S_final=0.0,
        G_final=0.0,
        Cp_final=0.0,
        phase_transitions=[transition]
    )
    assert result2.has_phase_transitions is True


def test_multi_phase_properties_segment_count():
    """Test segment_count property."""
    record1 = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    record2 = DatabaseRecord(
        formula="FeO", phase="s", tmin=650.0, tmax=900.0,
        h298=-265053.0, s298=59.807,
        f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment1 = PhaseSegment(
        record=record1,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85
    )

    segment2 = PhaseSegment(
        record=record2,
        T_start=650.0,
        T_end=900.0,
        H_start=-249633.0,
        S_start=96.657,
        delta_H=10000.0,
        delta_S=20.0
    )

    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-235633.0,
        S_final=155.44,
        G_final=-499582.0,
        Cp_final=68.199,
        segments=[segment1, segment2]  # Two different segments for test
    )

    assert result.segment_count == 2


def test_multi_phase_properties_phase_sequence():
    """Test phase_sequence property."""
    record1 = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    record2 = DatabaseRecord(
        formula="FeO", phase="s", tmin=600.0, tmax=900.0,
        h298=-265053.0, s298=59.807,
        f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    record3 = DatabaseRecord(
        formula="FeO", phase="l", tmin=1650.0, tmax=3000.0,
        h298=-265053.0, s298=59.807,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment1 = PhaseSegment(
        record=record1,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85
    )

    segment2 = PhaseSegment(
        record=record2,
        T_start=600.0,
        T_end=900.0,
        H_start=-249633.0,
        S_start=96.657,
        delta_H=10000.0,
        delta_S=20.0
    )

    segment3 = PhaseSegment(
        record=record3,
        T_start=1650.0,
        T_end=2000.0,
        H_start=-167238.0,
        S_start=170.27,
        delta_H=5000.0,
        delta_S=10.0
    )

    # Test with segments
    result = MultiPhaseProperties(
        T_target=2000.0,
        H_final=-162238.0,
        S_final=180.27,
        G_final=-522778.0,
        Cp_final=68.199,
        segments=[segment1, segment2, segment3]
    )

    # Should deduplicate consecutive phases: s → s → l becomes s → l
    assert result.phase_sequence == "s → l"

    # Test with no segments
    empty_result = MultiPhaseProperties(
        T_target=1000.0,
        H_final=0.0,
        S_final=0.0,
        G_final=0.0,
        Cp_final=0.0
    )
    assert empty_result.phase_sequence == "unknown"

    # Test with segments with None phase
    record_none_phase = DatabaseRecord(
        formula="FeO", phase=None, tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    segment_none = PhaseSegment(
        record=record_none_phase,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85
    )

    result_none = MultiPhaseProperties(
        T_target=600.0,
        H_final=-249633.0,
        S_final=96.657,
        G_final=-307636.0,
        Cp_final=50.0,
        segments=[segment_none]
    )
    assert result_none.phase_sequence == "unknown"