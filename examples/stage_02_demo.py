#!/usr/bin/env python3
"""
Stage 02 Demo: DatabaseRecord Extension Methods

This script demonstrates the new multi-phase calculation support methods
added to DatabaseRecord in Stage 02 of the multi-phase thermodynamic calculations implementation.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from thermo_agents.models.search import DatabaseRecord


def demo_feo_multimethods():
    """Demonstrate all new methods using FeO example from specifications."""

    print("Stage 02 Demo: DatabaseRecord Extension Methods")
    print("=" * 60)
    print()

    # Create FeO records (5 segments: 4 solid + 1 liquid)
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

    print("FeO Records (5 segments):")
    for i, record in enumerate(records, 1):
        base_mark = "[BASE]" if record.is_base_record() else "[CONT]"
        print(f"  {i}. {base_mark} {record.phase}: {record.tmin}-{record.tmax}K, H298={record.h298:.3f}")
    print()

    # Demo is_base_record()
    print("is_base_record() - Identification of base records:")
    for i, record in enumerate(records, 1):
        is_base = record.is_base_record()
        print(f"  Record {i}: {'BASE' if is_base else 'CONTINUATION'} (H298={record.h298:.3f})")
    print()

    # Demo covers_temperature()
    test_temps = [400.0, 1000.0, 1700.0, 3000.0]
    print("covers_temperature() - Temperature coverage analysis:")
    for T in test_temps:
        covering = [i for i, r in enumerate(records, 1) if r.covers_temperature(T)]
        print(f"  T={T:.0f}K: Covered by records {covering}")
    print()

    # Demo has_phase_transition_at()
    transition_temps = [1650.0, 3687.0, 1000.0]
    print("has_phase_transition_at() - Phase transition detection:")
    for T in transition_temps:
        transitions = set()
        for i, record in enumerate(records, 1):
            transition = record.has_phase_transition_at(T)
            if transition:
                transitions.add(transition)
        print(f"  T={T:.0f}K: {' → '.join(transitions) if transitions else 'No transition'}")
    print()

    # Demo get_transition_type()
    print("get_transition_type() - Transition type between consecutive records:")
    for i in range(len(records) - 1):
        transition = records[i].get_transition_type(records[i + 1])
        if transition:
            # Replace arrow with text for compatibility
            transition_text = transition.replace("→", " to ")
            print(f"  Record {i+1} to Record {i+2}: {transition_text} at {records[i].tmax}K")
        else:
            print(f"  Record {i+1} to Record {i+2}: No transition (same phase or gap)")
    print()

    # Demo get_temperature_range()
    print("get_temperature_range() - Temperature ranges:")
    for i, record in enumerate(records, 1):
        tmin, tmax = record.get_temperature_range()
        print(f"  Record {i}: {tmin:.0f}-{tmax:.0f}K (range: {tmax-tmin:.0f}K)")
    print()

    # Demo overlaps_with()
    print("overlaps_with() - Overlap analysis:")
    for i in range(len(records)):
        for j in range(i+1, len(records)):
            overlaps = records[i].overlaps_with(records[j])
            status = "OK" if overlaps else "NO"
            print(f"  Records {i+1} & {j+1}: {status} {'Overlap' if overlaps else 'No overlap'}")
    print()

    # Multi-phase calculation scenario
    print("Multi-phase calculation scenario:")
    target_T = 1700.0  # Target temperature

    # Find covering record
    covering_records = [r for r in records if r.covers_temperature(target_T)]

    if covering_records:
        record = covering_records[0]
        print(f"  Target T={target_T:.0f}K:")
        print(f"    Covered by {record.phase} phase ({record.tmin}-{record.tmax}K)")
        print(f"    Record type: {'BASE' if record.is_base_record() else 'CONTINUATION'}")

        # Check for transitions
        transition = record.has_phase_transition_at(record.tmax)
        if transition:
            print(f"    Phase transition at boundary: {transition}")
    else:
        print(f"  Target T={target_T:.0f}K: Not covered by any record")

    print()
    print("Stage 02 implementation complete!")
    print("Ready for Stage 03: CompoundSearcher.search_all_phases()")


if __name__ == "__main__":
    demo_feo_multimethods()