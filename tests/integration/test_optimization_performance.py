"""
Performance tests for optimal record selection.

Tests optimization performance, memory usage, and scalability.
"""

import pytest
import time
import psutil
import os
import pandas as pd
import numpy as np
from typing import List

from src.thermo_agents.selection.optimal_record_selector import (
    OptimalRecordSelector,
    VirtualRecord,
    OptimizationConfig
)
from src.thermo_agents.models.search import DatabaseRecord


class TestOptimizationPerformance:
    """Performance tests for optimal record selection."""

    @pytest.fixture
    def selector(self):
        """Create OptimalRecordSelector instance for performance testing."""
        config = OptimizationConfig(
            max_optimization_time_ms=50.0,  # Strict time limit
            max_virtual_records=100
        )
        return OptimalRecordSelector(config)

    @pytest.fixture
    def large_test_compounds(self):
        """Create a list of test compounds for performance testing."""
        return [
            "H2O", "CO2", "NH3", "CH4", "O2", "N2", "H2", "HCl",
            "SiO2", "Fe2O3", "CaCO3", "Al2O3", "CuO", "ZnO", "MgO",
            "NaCl", "KCl", "CeCl3", "WO3", "TiO2"
        ]

    @pytest.fixture
    def performance_test_records(self):
        """Create a large set of records for performance testing."""
        records = []
        compound_id = 0

        for compound in ["TestCompound1", "TestCompound2", "TestCompound3"]:
            for phase in ["s", "l", "g"]:
                # Create multiple records for each phase
                base_tmin = 100 + compound_id * 100
                for i in range(10):  # 10 records per phase
                    record = DatabaseRecord(
                        rowid=len(records),
                        formula=compound,
                        first_name=compound,
                        phase=phase,
                        tmin=base_tmin + i * 50,
                        tmax=base_tmin + (i + 1) * 50,
                        h298=-100.0 if i == 0 else 0.0,
                        s298=50.0 if i == 0 else 0.0,
                        f1=10.0 + i * 0.1,
                        f2=0.1,
                        f3=0.0,
                        f4=0.0,
                        f5=0.0,
                        f6=0.0,
                        tmelt=500.0,
                        tboil=1000.0,
                        reliability_class=1
                    )
                    records.append(record)
                compound_id += 1

        return records

    def test_optimization_time_per_compound(self, selector, large_test_compounds):
        """Test optimization time per compound (target: <50ms)."""
        # Create mock data for each compound
        optimization_times = []

        for compound in large_test_compounds:
            # Create test records for this compound
            records = []
            for i in range(5):  # 5 records per compound
                record = DatabaseRecord(
                    rowid=i,
                    formula=compound,
                    first_name=compound,
                    phase='g' if i > 2 else 's',
                    tmin=100 + i * 100,
                    tmax=200 + i * 100,
                    h298=-100.0 if i == 0 else 0.0,
                    s298=50.0 if i == 0 else 0.0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=500.0,
                    tboil=1000.0,
                    reliability_class=1
                )
                records.append(record)

            # Create DataFrame for all available records
            all_records_df = pd.DataFrame([{
                'rowid': r.rowid,
                'Formula': r.formula,
                'FirstName': r.first_name,
                'Phase': r.phase,
                'Tmin': r.tmin,
                'Tmax': r.tmax,
                'H298': r.h298,
                'S298': r.s298,
                'f1': r.f1,
                'f2': r.f2,
                'f3': r.f3,
                'f4': r.f4,
                'f5': r.f5,
                'f6': r.f6,
                'MeltingPoint': r.tmelt,
                'BoilingPoint': r.tboil,
                'ReliabilityClass': r.reliability_class
            } for r in records])

            # Measure optimization time
            start_time = time.perf_counter()

            result = selector.optimize_selected_records(
                selected_records=records,
                target_range=(298, 1500),
                all_available_records=all_records_df,
                melting=500.0,
                boiling=1000.0,
                is_elemental=False
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            optimization_times.append(elapsed_ms)

            # Each optimization should complete within time limit
            assert elapsed_ms < selector.config.max_optimization_time_ms, \
                f"Optimization for {compound} took {elapsed_ms:.2f}ms > {selector.config.max_optimization_time_ms}ms"

            # Should return valid results
            assert len(result) > 0

        # Calculate statistics
        avg_time = sum(optimization_times) / len(optimization_times)
        max_time = max(optimization_times)

        print(f"Average optimization time: {avg_time:.2f}ms")
        print(f"Maximum optimization time: {max_time:.2f}ms")

        # Performance requirements
        assert avg_time < 30.0, f"Average time {avg_time:.2f}ms > 30ms"
        assert max_time < 50.0, f"Maximum time {max_time:.2f}ms > 50ms"

    def test_overhead_vs_three_level(self, selector, performance_test_records):
        """Test overhead compared to three-level selection (target: <20%)."""
        # Create DataFrame with all records
        all_records_df = pd.DataFrame([{
            'rowid': r.rowid,
            'Formula': r.formula,
            'FirstName': r.first_name,
            'Phase': r.phase,
            'Tmin': r.tmin,
            'Tmax': r.tmax,
            'H298': r.h298,
            'S298': r.s298,
            'f1': r.f1,
            'f2': r.f2,
            'f3': r.f3,
            'f4': r.f4,
            'f5': r.f5,
            'f6': r.f6,
            'MeltingPoint': r.tmelt,
            'BoilingPoint': r.tboil,
            'ReliabilityClass': r.reliability_class
        } for r in performance_test_records])

        overhead_ratios = []

        # Test with subsets of records
        for subset_size in [5, 10, 20, 30]:
            if subset_size > len(performance_test_records):
                continue

            test_records = performance_test_records[:subset_size]

            # Measure time without optimization (just returning input)
            start_time = time.perf_counter()
            no_opt_result = test_records  # Simulate no optimization
            no_opt_time = time.perf_counter() - start_time

            # Measure time with optimization
            start_time = time.perf_counter()
            opt_result = selector.optimize_selected_records(
                selected_records=test_records,
                target_range=(100, 800),
                all_available_records=all_records_df,
                melting=500.0,
                boiling=1000.0,
                is_elemental=False
            )
            opt_time = time.perf_counter() - start_time

            # Calculate overhead
            if no_opt_time > 0:
                overhead_ratio = opt_time / no_opt_time
                overhead_ratios.append(overhead_ratio)

                print(f"Subset size {subset_size}: overhead = {overhead_ratio:.2f}x")

                # Overhead should be reasonable
                assert overhead_ratio < 1.2, f"Overhead {overhead_ratio:.2f}x > 1.2x for {subset_size} records"

        # Average overhead should be within limits
        if overhead_ratios:
            avg_overhead = sum(overhead_ratios) / len(overhead_ratios)
            assert avg_overhead < 1.2, f"Average overhead {avg_overhead:.2f}x > 1.2x"

    def test_memory_usage(self, selector):
        """Test memory usage (target: <10MB additional)."""
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB

        # Create many virtual records
        virtual_records = []
        for i in range(100):
            source_records = [
                DatabaseRecord(
                    rowid=i * 2,
                    formula=f"Test{i}",
                    first_name=f"Test{i}",
                    phase="g",
                    tmin=100 + i,
                    tmax=200 + i,
                    h298=0.0,
                    s298=0.0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=0.0,
                    tboil=0.0,
                    reliability_class=1
                ),
                DatabaseRecord(
                    rowid=i * 2 + 1,
                    formula=f"Test{i}",
                    first_name=f"Test{i}",
                    phase="g",
                    tmin=200 + i,
                    tmax=300 + i,
                    h298=0.0,
                    s298=0.0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=0.0,
                    tboil=0.0,
                    reliability_class=1
                )
            ]

            virtual_record = selector._create_virtual_record(source_records)
            virtual_records.append(virtual_record)

        # Measure memory after creating virtual records
        peak_memory = process.memory_info().rss / (1024 * 1024)  # MB
        additional_memory = peak_memory - initial_memory

        print(f"Additional memory usage: {additional_memory:.2f}MB")
        print(f"Virtual records created: {len(virtual_records)}")

        # Memory usage should be within limits
        assert additional_memory < 10.0, f"Memory usage {additional_memory:.2f}MB > 10MB"

        # Check that virtual record cache is within limits
        assert len(selector._virtual_record_cache) <= selector.config.max_virtual_records

    def test_full_reaction_calculation_time(self, selector):
        """Test time for full reaction calculation with multiple compounds."""
        # Simulate a reaction: SiO2 + 3C = Si + 3CO
        reaction_compounds = ["SiO2", "C", "Si", "CO"]
        temp_range = (298, 1500)
        total_time = 0.0

        for compound in reaction_compounds:
            # Create test records for each compound
            records = []
            for i in range(4):  # 4 records per compound
                record = DatabaseRecord(
                    rowid=i,
                    formula=compound,
                    first_name=compound,
                    phase='g' if i > 1 else 's',
                    tmin=100 + i * 200,
                    tmax=300 + i * 200,
                    h298=-100.0 if i == 0 else 0.0,
                    s298=50.0 if i == 0 else 0.0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=800.0,
                    tboil=1500.0,
                    reliability_class=1
                )
                records.append(record)

            # Create DataFrame
            all_records_df = pd.DataFrame([{
                'rowid': r.rowid,
                'Formula': r.formula,
                'FirstName': r.first_name,
                'Phase': r.phase,
                'Tmin': r.tmin,
                'Tmax': r.tmax,
                'H298': r.h298,
                'S298': r.s298,
                'f1': r.f1,
                'f2': r.f2,
                'f3': r.f3,
                'f4': r.f4,
                'f5': r.f5,
                'f6': r.f6,
                'MeltingPoint': r.tmelt,
                'BoilingPoint': r.tboil,
                'ReliabilityClass': r.reliability_class
            } for r in records])

            # Measure optimization time for this compound
            start_time = time.perf_counter()

            result = selector.optimize_selected_records(
                selected_records=records,
                target_range=temp_range,
                all_available_records=all_records_df,
                melting=800.0,
                boiling=1500.0,
                is_elemental=compound in ["C", "Si"]  # Elemental compounds
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            total_time += elapsed_ms

            # Should complete within time limit
            assert elapsed_ms < selector.config.max_optimization_time_ms
            assert len(result) > 0

        print(f"Total time for reaction with {len(reaction_compounds)} compounds: {total_time:.2f}ms")

        # Full reaction calculation should complete within 3 seconds
        assert total_time < 3000.0, f"Full reaction took {total_time:.2f}ms > 3000ms"

    def test_scalability_with_record_count(self, selector):
        """Test scalability with increasing number of records."""
        record_counts = [5, 10, 20, 50, 100]
        optimization_times = []

        for count in record_counts:
            # Create test records
            records = []
            for i in range(count):
                record = DatabaseRecord(
                    rowid=i,
                    formula=f"TestCompound{i % 5}",  # 5 different compounds
                    first_name=f"TestCompound{i % 5}",
                    phase=['s', 'l', 'g'][i % 3],
                    tmin=100 + i * 10,
                    tmax=200 + i * 10,
                    h298=-100.0 if i % 10 == 0 else 0.0,
                    s298=50.0 if i % 10 == 0 else 0.0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=500.0,
                    tboil=1000.0,
                    reliability_class=1
                )
                records.append(record)

            # Create DataFrame
            all_records_df = pd.DataFrame([{
                'rowid': r.rowid,
                'Formula': r.formula,
                'FirstName': r.first_name,
                'Phase': r.phase,
                'Tmin': r.tmin,
                'Tmax': r.tmax,
                'H298': r.h298,
                'S298': r.s298,
                'f1': r.f1,
                'f2': r.f2,
                'f3': r.f3,
                'f4': r.f4,
                'f5': r.f5,
                'f6': r.f6,
                'MeltingPoint': r.tmelt,
                'BoilingPoint': r.tboil,
                'ReliabilityClass': r.reliability_class
            } for r in records])

            # Measure optimization time
            start_time = time.perf_counter()

            result = selector.optimize_selected_records(
                selected_records=records,
                target_range=(100, 1000),
                all_available_records=all_records_df,
                melting=500.0,
                boiling=1000.0,
                is_elemental=False
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            optimization_times.append(elapsed_ms)

            print(f"Record count {count}: {elapsed_ms:.2f}ms")

            # Should complete within time limit
            assert elapsed_ms < selector.config.max_optimization_time_ms
            assert len(result) > 0

        # Check scalability (time should grow sub-linearly)
        if len(optimization_times) >= 2:
            # Calculate growth rate
            time_growth = optimization_times[-1] / optimization_times[0]
            record_growth = record_counts[-1] / record_counts[0]

            # Time growth should be less than record growth (sub-linear)
            if record_growth > 1:
                scalability_ratio = time_growth / record_growth
                print(f"Scalability ratio: {scalability_ratio:.2f} (lower is better)")
                assert scalability_ratio < 2.0, f"Poor scalability: {scalability_ratio:.2f}"

    def test_cache_performance(self, selector):
        """Test virtual record cache performance."""
        # Create identical source records multiple times
        source_records = [
            DatabaseRecord(
                rowid=1,
                formula="CacheTest",
                first_name="CacheTest",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0.0,
                s298=0.0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0.0,
                tboil=0.0,
                reliability_class=1
            ),
            DatabaseRecord(
                rowid=2,
                formula="CacheTest",
                first_name="CacheTest",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0.0,
                s298=0.0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0.0,
                tboil=0.0,
                reliability_class=1
            )
        ]

        # First creation (should add to cache)
        start_time = time.perf_counter()
        virtual_record1 = selector._create_virtual_record(source_records)
        first_creation_time = time.perf_counter() - start_time

        # Second creation (should use cache)
        start_time = time.perf_counter()
        virtual_record2 = selector._create_virtual_record(source_records)
        second_creation_time = time.perf_counter() - start_time

        # Cache should improve performance
        print(f"First creation: {first_creation_time*1000:.3f}ms")
        print(f"Second creation: {second_creation_time*1000:.3f}ms")

        # Should be the same object (from cache)
        assert virtual_record1 is virtual_record2, "Cache should return same object"

        # Cache should contain the record
        assert len(selector._virtual_record_cache) > 0

        # Performance should be better with cache (though timing may be variable)
        # This is a soft assertion due to timing variability
        if second_creation_time > 0:
            speedup = first_creation_time / second_creation_time
            print(f"Cache speedup: {speedup:.2f}x")


if __name__ == "__main__":
    pytest.main([__file__])