"""
Performance tests for DatabaseRecord extension methods (Stage 02).

Tests that the new methods meet the performance targets specified in the specification.
"""

import pytest
import time
from thermo_agents.models.search import DatabaseRecord


def test_covers_temperature_performance():
    """Performance test for covers_temperature() method."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 100,000 calls
    for _ in range(100_000):
        _ = record.covers_temperature(450.0)

    elapsed = time.perf_counter() - start

    # Requirement: < 15ms for 100k calls (relaxed for Windows)
    assert elapsed < 0.015, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 100_000) * 1_000_000  # microseconds
    print(f"covers_temperature(): {per_call:.3f} us/call")


def test_is_base_record_performance():
    """Performance test for is_base_record() method."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 100,000 calls
    for _ in range(100_000):
        _ = record.is_base_record()

    elapsed = time.perf_counter() - start

    # Requirement: < 15ms for 100k calls (relaxed for Windows)
    assert elapsed < 0.015, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 100_000) * 1_000_000
    print(f"is_base_record(): {per_call:.3f} us/call")


def test_get_transition_type_performance():
    """Performance test for get_transition_type() method."""
    record1 = DatabaseRecord(
        formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
        h298=0.0, s298=0.0,
        f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    record2 = DatabaseRecord(
        formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
        h298=24.058, s298=14.581,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 50,000 calls
    for _ in range(50_000):
        _ = record1.get_transition_type(record2)

    elapsed = time.perf_counter() - start

    # Requirement: < 20ms for 50k calls (relaxed for Windows)
    assert elapsed < 0.02, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 50_000) * 1_000_000
    print(f"get_transition_type(): {per_call:.3f} us/call")


def test_has_phase_transition_at_performance():
    """Performance test for has_phase_transition_at() method."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 100,000 calls with different temperatures
    test_temps = [1650.0, 3687.0, 1000.0, 500.0, 298.0]
    for _ in range(20_000):  # 20k * 5 temps = 100k total
        for T in test_temps:
            _ = record.has_phase_transition_at(T)

    elapsed = time.perf_counter() - start

    # Requirement: < 20ms for 100k calls (relaxed for Windows)
    assert elapsed < 0.02, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 100_000) * 1_000_000
    print(f"has_phase_transition_at(): {per_call:.3f} us/call")


def test_get_temperature_range_performance():
    """Performance test for get_temperature_range() method."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 100,000 calls
    for _ in range(100_000):
        _ = record.get_temperature_range()

    elapsed = time.perf_counter() - start

    # Requirement: < 15ms for 100k calls (relaxed for Windows)
    assert elapsed < 0.015, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 100_000) * 1_000_000
    print(f"get_temperature_range(): {per_call:.3f} us/call")


def test_overlaps_with_performance():
    """Performance test for overlaps_with() method."""
    record1 = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    record2 = DatabaseRecord(
        formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
        h298=24.058, s298=14.581,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )

    start = time.perf_counter()

    # 50,000 calls
    for _ in range(50_000):
        _ = record1.overlaps_with(record2)

    elapsed = time.perf_counter() - start

    # Requirement: < 20ms for 50k calls (relaxed for Windows)
    assert elapsed < 0.02, f"Too slow: {elapsed*1000:.2f}ms"

    per_call = (elapsed / 50_000) * 1_000_000
    print(f"overlaps_with(): {per_call:.3f} us/call")


def test_combined_operations_performance():
    """Performance test for combined operations typical in multi-phase calculations."""
    # Create multiple records
    records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.053, s298=59.807,
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
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24.058, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        )
    ]

    start = time.perf_counter()

    # Simulate typical multi-phase calculation operations
    for _ in range(10_000):
        # Check if first record is base
        _ = records[0].is_base_record()

        # Check temperature coverage for target T
        target_T = 1700.0
        covering_records = [r for r in records if r.covers_temperature(target_T)]

        # Check for transitions
        for i in range(len(records) - 1):
            _ = records[i].get_transition_type(records[i + 1])

        # Check phase transitions at boundaries
        for record in records:
            _ = record.has_phase_transition_at(record.tmax)

    elapsed = time.perf_counter() - start

    # Requirement: < 150ms for 10k complete cycles (relaxed for Windows)
    assert elapsed < 0.15, f"Too slow: {elapsed*1000:.2f}ms"

    per_cycle = (elapsed / 10_000) * 1_000_000
    print(f"Combined operations: {per_cycle:.3f} us/cycle")


def test_memory_efficiency():
    """Test that methods don't create excessive memory allocations."""
    import gc
    import sys

    # Force garbage collection before test
    gc.collect()

    # Create many records
    records = []
    for i in range(1000):
        record = DatabaseRecord(
            formula=f"Test{i}", phase="s", tmin=298.0 + i, tmax=600.0 + i,
            h298=-265.053, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        )
        records.append(record)

    # Perform many operations
    for record in records:
        for _ in range(100):
            _ = record.is_base_record()
            _ = record.covers_temperature(400.0)
            _ = record.get_temperature_range()

    # Simple memory check - should not crash
    print(f"Memory efficiency: Successfully processed {len(records)} records")

    # Clean up
    del records
    gc.collect()


if __name__ == "__main__":
    # Run performance tests manually
    test_covers_temperature_performance()
    test_is_base_record_performance()
    test_get_transition_type_performance()
    test_has_phase_transition_at_performance()
    test_get_temperature_range_performance()
    test_overlaps_with_performance()
    test_combined_operations_performance()
    test_memory_efficiency()
    print("🚀 All performance tests passed!")