"""
Integration tests for DatabaseRecord extension methods (Stage 02).

Tests the new multi-phase calculation support methods with real-world examples.
"""

import pytest
from thermo_agents.models.search import DatabaseRecord


def test_feo_full_chain_with_new_methods():
    """
    Integration test: check all new methods on real FeO example.

    Scenario:
    - 5 FeO records (4 solid + 1 liquid)
    - Check base record
    - Check temperature coverage
    - Check phase transitions
    - Check transition types between records
    """
    # STEP 1: Create 5 FeO records
    records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.053, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=0.0, s298=0.0,  # Continuation record
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
            h298=24.058, s298=14.581,  # Base record for liquid phase
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]

    # STEP 2: Check is_base_record()
    assert records[0].is_base_record() is True, "First record should be base"
    assert records[1].is_base_record() is False, "Second record is continuation"
    assert records[2].is_base_record() is False
    assert records[3].is_base_record() is False
    assert records[4].is_base_record() is True, "Liquid phase has its own H298/S298"

    # STEP 3: Check covers_temperature()
    assert records[0].covers_temperature(298.0) is True
    assert records[0].covers_temperature(450.0) is True
    assert records[0].covers_temperature(600.0) is True
    assert records[0].covers_temperature(700.0) is False, "Outside range"

    assert records[4].covers_temperature(1700.0) is True
    assert records[4].covers_temperature(3000.0) is True
    assert records[4].covers_temperature(1500.0) is False, "Below liquid Tmin"

    # STEP 4: Check has_phase_transition_at()
    for rec in records:
        assert rec.has_phase_transition_at(1650.0) == "melting", "All records know Tmelt"
        assert rec.has_phase_transition_at(3687.0) == "boiling", "All records know Tboil"
        assert rec.has_phase_transition_at(1000.0) is None, "No transition at 1000K"

    # STEP 5: Check get_transition_type()
    # s → s (same phase, no transition)
    assert records[0].get_transition_type(records[1]) is None
    assert records[1].get_transition_type(records[2]) is None
    assert records[2].get_transition_type(records[3]) is None

    # s → l (melting)
    transition = records[3].get_transition_type(records[4])
    assert transition == "s→l", f"Expected s→l transition, got {transition}"

    # STEP 6: Check get_temperature_range()
    tmin, tmax = records[0].get_temperature_range()
    assert tmin == 298.0
    assert tmax == 600.0

    # STEP 7: Check overlaps_with()
    assert records[0].overlaps_with(records[1]) is True, "Records touch at 600K"
    assert records[3].overlaps_with(records[4]) is True, "Records touch at 1650K"
    assert records[0].overlaps_with(records[2]) is False, "Records don't overlap"

    print("✅ All new methods work correctly on FeO example")


def test_edge_case_gap_between_records():
    """Test edge case: gap between records."""
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

    # Should return None due to gap
    assert record1.get_transition_type(record2) is None

    # overlaps_with should return False
    assert record1.overlaps_with(record2) is False


def test_edge_case_none_phases():
    """Test edge case: records with None in phases."""
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

    # Should handle None phase gracefully
    transition = record1.get_transition_type(record2)
    assert transition == "→s"  # Empty string for None phase


def test_multi_compound_phase_analysis():
    """Test phase analysis across multiple compounds."""

    # H2O records
    h2o_solid = DatabaseRecord(
        formula="H2O", phase="s", tmin=200.0, tmax=273.15,
        h298=-285.83, s298=69.95,
        f1=30.0, f2=6.0, f3=6.0, f4=-2.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )

    h2o_liquid = DatabaseRecord(
        formula="H2O", phase="l", tmin=273.15, tmax=373.15,
        h298=-285.83, s298=69.95,
        f1=75.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )

    h2o_gas = DatabaseRecord(
        formula="H2O", phase="g", tmin=373.15, tmax=1000.0,
        h298=-241.83, s298=188.83,
        f1=33.0, f2=2.5, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )

    # Test solid-liquid transition
    assert h2o_solid.get_transition_type(h2o_liquid) == "s→l"

    # Test liquid-gas transition
    assert h2o_liquid.get_transition_type(h2o_gas) == "l→g"

    # Test melting detection
    assert h2o_solid.has_phase_transition_at(273.15) == "melting"
    assert h2o_liquid.has_phase_transition_at(273.15) == "melting"

    # Test boiling detection
    assert h2o_liquid.has_phase_transition_at(373.15) == "boiling"
    assert h2o_gas.has_phase_transition_at(373.15) == "boiling"

    # Test temperature coverage
    assert h2o_solid.covers_temperature(250.0) is True
    assert h2o_solid.covers_temperature(300.0) is False
    assert h2o_liquid.covers_temperature(300.0) is True
    assert h2o_gas.covers_temperature(500.0) is True

    # Test overlaps
    assert h2o_solid.overlaps_with(h2o_liquid) is True
    assert h2o_liquid.overlaps_with(h2o_gas) is True
    assert h2o_solid.overlaps_with(h2o_gas) is False


def test_complex_phase_sequence():
    """Test complex phase sequence with multiple transitions."""

    # Simulate CO2 sublimation
    co2_solid = DatabaseRecord(
        formula="CO2", phase="s", tmin=194.65, tmax=194.65,
        h298=-393.51, s298=213.7,
        f1=25.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=194.65, tboil=194.65, reliability_class=1
    )

    co2_gas = DatabaseRecord(
        formula="CO2", phase="g", tmin=194.65, tmax=2000.0,
        h298=-393.51, s298=213.7,
        f1=44.0, f2=9.0, f3=-8.5, f4=2.0, f5=0.0, f6=0.0,
        tmelt=194.65, tboil=194.65, reliability_class=1
    )

    # Test sublimation (s→g at same temperature)
    transition = co2_solid.get_transition_type(co2_gas)
    assert transition == "s→g"

    # Test that both records know about transitions
    assert co2_solid.has_phase_transition_at(194.65) in ["melting", "boiling"]
    assert co2_gas.has_phase_transition_at(194.65) in ["melting", "boiling"]


def test_temperature_range_analysis():
    """Test comprehensive temperature range analysis."""

    # Create records with various ranges
    low_temp = DatabaseRecord(
        formula="Test", phase="s", tmin=10.0, tmax=100.0,
        h298=-100.0, s298=50.0,
        f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=100.0, tboil=500.0, reliability_class=1
    )

    mid_temp = DatabaseRecord(
        formula="Test", phase="l", tmin=100.0, tmax=500.0,
        h298=0.0, s298=0.0,
        f1=40.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=100.0, tboil=500.0, reliability_class=1
    )

    high_temp = DatabaseRecord(
        formula="Test", phase="g", tmin=500.0, tmax=2000.0,
        h298=10.0, s298=100.0,
        f1=50.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=100.0, tboil=500.0, reliability_class=1
    )

    records = [low_temp, mid_temp, high_temp]

    # Test full coverage analysis
    test_temperatures = [50.0, 200.0, 1000.0]
    coverage = []

    for T in test_temperatures:
        covering_records = [r for r in records if r.covers_temperature(T)]
        coverage.append(len(covering_records))

    assert coverage == [1, 1, 1], "Each temperature should be covered by exactly one record"

    # Test base record identification
    base_records = [r for r in records if r.is_base_record()]
    assert len(base_records) == 2, "Should have 2 base records (low and high temp)"

    # Test transition detection
    transitions = []
    for i in range(len(records) - 1):
        transition = records[i].get_transition_type(records[i + 1])
        if transition:
            transitions.append(transition)

    assert transitions == ["s→l", "l→g"], "Should detect both transitions"