"""
Integration tests for multi-phase thermodynamic calculations.
"""

import pytest
from thermo_agents.models.search import (
    DatabaseRecord,
    PhaseSegment,
    PhaseTransition,
    MultiPhaseProperties,
    TransitionType
)


def test_full_multi_phase_calculation_feo():
    """
    Integration test: complete FeO calculation from 298K to 1700K.

    Tests interaction of all three models:
    - 5 segments (4 solid + 1 liquid)
    - 1 phase transition (melting at 1650K)
    - Temperature, enthalpy, and entropy trajectories
    """
    # STEP 1: Create database records
    records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265053.0, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=0.0, s298=0.0,
            f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=900.0, tmax=1300.0,
            h298=0.0, s298=0.0,
            f1=90.408, f2=-38.021, f3=-83.811, f4=15.358, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
            h298=0.0, s298=0.0,
            f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24058.0, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]

    # STEP 2: Create segments (emulating calculation)
    segments = [
        PhaseSegment(
            record=records[0],
            T_start=298.0,
            T_end=600.0,
            H_start=-265053.0,
            S_start=59.807,
            delta_H=15420.0,
            delta_S=36.85,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[1],
            T_start=600.0,
            T_end=900.0,
            H_start=-249633.0,
            S_start=96.657,
            delta_H=19418.0,
            delta_S=29.793,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[2],
            T_start=900.0,
            T_end=1300.0,
            H_start=-230215.0,
            S_start=126.45,
            delta_H=30977.0,
            delta_S=24.42,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[3],
            T_start=1300.0,
            T_end=1650.0,
            H_start=-199238.0,
            S_start=150.87,
            delta_H=32000.0,  # Includes melting enthalpy
            delta_S=19.4,
            is_transition_boundary=True
        ),
        PhaseSegment(
            record=records[4],
            T_start=1650.0,
            T_end=1700.0,
            H_start=-167238.0,
            S_start=170.27,
            delta_H=3605.0,
            delta_S=3.17,
            is_transition_boundary=False
        ),
    ]

    # STEP 3: Create phase transition
    melting = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=32.0,  # kJ/mol
        delta_S_transition=19.4
    )

    # STEP 4: Final result
    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-163633.0,  # J/mol
        S_final=173.44,     # J/(mol·K)
        G_final=-458481.0,  # G = H - T*S
        Cp_final=68.199,
        segments=segments,
        phase_transitions=[melting],
        temperature_path=[298.0, 600.0, 900.0, 1300.0, 1650.0, 1700.0],
        H_path=[-265053, -249633, -230215, -199238, -167238, -163633],
        S_path=[59.807, 96.657, 126.45, 150.87, 170.27, 173.44],
        warnings=[]
    )

    # Verifications
    assert result.T_target == 1700.0
    assert len(result.segments) == 5
    assert len(result.phase_transitions) == 1
    assert result.has_phase_transitions is True
    assert result.phase_sequence == "s → l"
    assert len(result.warnings) == 0

    # Verify trajectory data
    assert len(result.temperature_path) == 6
    assert len(result.H_path) == 6
    assert len(result.S_path) == 6

    # Verify start and end points
    assert result.temperature_path[0] == 298.0
    assert result.temperature_path[-1] == 1700.0
    assert result.H_path[0] == -265053
    assert result.H_path[-1] == -163633

    # Verify serialization
    data = result.to_dict()
    assert data["segments_count"] == 5
    assert data["transitions_count"] == 1
    assert "thermodynamic_properties" in data

    props = data["thermodynamic_properties"]
    assert abs(props["H"] - (-163.633)) < 0.001  # kJ/mol
    assert abs(props["G"] - (-458.481)) < 0.001  # kJ/mol

    print("✅ Integration test passed: FeO 298K→1700K")


def test_multi_phase_calculation_with_warnings():
    """Test multi-phase calculation with warnings."""
    record = DatabaseRecord(
        formula="H2O", phase="s", tmin=200.0, tmax=273.15,
        h298=-285830.0, s298=69.95,
        f1=30.092, f2=6.832, f3=6.793, f4=-2.534, f5=0.082, f6=-0.007,
        tmelt=273.15, tboil=373.15, reliability_class=1
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

    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=6.008,
        delta_S_transition=22.0
    )

    result = MultiPhaseProperties(
        T_target=300.0,
        H_final=-280822.0,
        S_final=106.95,
        G_final=-312907.0,
        Cp_final=75.0,
        segments=[segment],
        phase_transitions=[transition],
        warnings=[
            "Temperature gap detected between 273.15K and 280.0K",
            "Data reliability class 2 for liquid phase"
        ]
    )

    assert len(result.warnings) == 2
    assert "gap detected" in result.warnings[0]
    assert "reliability class" in result.warnings[1]


def test_multi_phase_calculation_no_transitions():
    """Test calculation without phase transitions."""
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

    result = MultiPhaseProperties(
        T_target=500.0,
        H_final=-385009.0,
        S_final=239.04,
        G_final=-504529.0,
        Cp_final=50.0,
        segments=[segment],
        temperature_path=[298.0, 500.0],
        H_path=[-393509, -385009],
        S_path=[213.74, 239.04]
    )

    # No phase transitions
    assert result.has_phase_transitions is False
    assert len(result.phase_transitions) == 0
    assert result.phase_sequence == "g"

    # Single segment
    assert result.segment_count == 1
    assert len(result.segments) == 1


def test_multi_phase_complex_trajectory():
    """Test multi-phase calculation with complex trajectory."""
    # Multiple segments with different phases
    records = [
        DatabaseRecord(
            formula="H2O", phase="s", tmin=200.0, tmax=273.15,
            h298=-285830.0, s298=69.95,
            f1=30.092, f2=6.832, f3=6.793, f4=-2.534, f5=0.082, f6=-0.007,
            tmelt=273.15, tboil=373.15, reliability_class=1
        ),
        DatabaseRecord(
            formula="H2O", phase="l", tmin=273.15, tmax=373.15,
            h298=-285830.0, s298=69.95,
            f1=75.291, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=273.15, tboil=373.15, reliability_class=1
        ),
        DatabaseRecord(
            formula="H2O", phase="g", tmin=373.15, tmax=1000.0,
            h298=0.0, s298=0.0,
            f1=30.009, f2=6.965, f3=6.447, f4=-2.714, f5=0.125, f6=-0.018,
            tmelt=273.15, tboil=373.15, reliability_class=1
        ),
    ]

    segments = [
        PhaseSegment(
            record=records[0],
            T_start=250.0,
            T_end=273.15,
            H_start=-285000.0,
            S_start=65.0,
            delta_H=1000.0,
            delta_S=5.0,
            is_transition_boundary=True
        ),
        PhaseSegment(
            record=records[1],
            T_start=273.15,
            T_end=373.15,
            H_start=-284000.0,
            S_start=70.0,
            delta_H=7500.0,
            delta_S=20.0,
            is_transition_boundary=True
        ),
        PhaseSegment(
            record=records[2],
            T_start=373.15,
            T_end=450.0,
            H_start=-276500.0,
            S_start=90.0,
            delta_H=2000.0,
            delta_S=8.0,
            is_transition_boundary=False
        ),
    ]

    transitions = [
        PhaseTransition(
            temperature=273.15,
            from_phase="s",
            to_phase="l",
            transition_type=TransitionType.MELTING,
            delta_H_transition=6.008,
            delta_S_transition=22.0
        ),
        PhaseTransition(
            temperature=373.15,
            from_phase="l",
            to_phase="g",
            transition_type=TransitionType.BOILING,
            delta_H_transition=40.66,
            delta_S_transition=109.0
        ),
    ]

    result = MultiPhaseProperties(
        T_target=450.0,
        H_final=-274500.0,
        S_final=98.0,
        G_final=-318600.0,
        Cp_final=35.0,
        segments=segments,
        phase_transitions=transitions,
        temperature_path=[250.0, 273.15, 373.15, 450.0],
        H_path=[-285000, -284000, -276500, -274500],
        S_path=[65.0, 70.0, 90.0, 98.0]
    )

    # Verify complex multi-phase scenario
    assert result.segment_count == 3
    assert result.has_phase_transitions is True
    assert len(result.phase_transitions) == 2
    assert result.phase_sequence == "s → l → g"

    # Verify transitions
    melting = result.phase_transitions[0]
    assert melting.transition_type == TransitionType.MELTING
    assert melting.temperature == 273.15

    boiling = result.phase_transitions[1]
    assert boiling.transition_type == TransitionType.BOILING
    assert boiling.temperature == 373.15