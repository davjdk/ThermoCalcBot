"""
Unit tests for TemperatureResolver.

Tests temperature range coverage calculation, interval merging,
and temperature statistics functionality.
"""

import pytest
from typing import List

from src.thermo_agents.models.search import DatabaseRecord
from src.thermo_agents.filtering.temperature_resolver import (
    TemperatureResolver, TemperatureInterval
)


class TestTemperatureInterval:
    """Test cases for TemperatureInterval class."""

    def test_valid_interval_creation(self):
        """Test creating valid temperature intervals."""
        interval = TemperatureInterval(tmin=100.0, tmax=500.0)
        assert interval.tmin == 100.0
        assert interval.tmax == 500.0
        assert interval.width == 400.0

    def test_invalid_interval_creation(self):
        """Test creating invalid temperature intervals."""
        with pytest.raises(ValueError, match="Минимальная температура не может быть больше максимальной"):
            TemperatureInterval(tmin=500.0, tmax=100.0)

        with pytest.raises(ValueError, match="Температуры должны быть положительными"):
            TemperatureInterval(tmin=-100.0, tmax=500.0)

    def test_contains_temperature(self):
        """Test temperature containment checking."""
        interval = TemperatureInterval(tmin=100.0, tmax=500.0)

        assert interval.contains(100.0) == True  # Boundary
        assert interval.contains(300.0) == True  # Middle
        assert interval.contains(500.0) == True  # Boundary
        assert interval.contains(99.9) == False   # Below
        assert interval.contains(500.1) == False  # Above

    def test_overlaps_with(self):
        """Test interval overlap checking."""
        interval1 = TemperatureInterval(tmin=100.0, tmax=300.0)
        interval2 = TemperatureInterval(tmin=200.0, tmax=400.0)
        interval3 = TemperatureInterval(tmin=400.0, tmax=600.0)

        assert interval1.overlaps_with(interval2) == True   # Overlapping
        assert interval2.overlaps_with(interval1) == True   # Symmetric
        assert interval1.overlaps_with(interval3) == False  # Non-overlapping
        assert interval2.overlaps_with(interval3) == True   # Touching boundary

    def test_intersection(self):
        """Test interval intersection."""
        interval1 = TemperatureInterval(tmin=100.0, tmax=300.0)
        interval2 = TemperatureInterval(tmin=200.0, tmax=400.0)
        interval3 = TemperatureInterval(tmin=400.0, tmax=600.0)

        intersection = interval1.intersection(interval2)
        assert intersection is not None
        assert intersection.tmin == 200.0
        assert intersection.tmax == 300.0

        no_intersection = interval1.intersection(interval3)
        assert no_intersection is None

    def test_union(self):
        """Test interval union."""
        interval1 = TemperatureInterval(tmin=100.0, tmax=300.0)
        interval2 = TemperatureInterval(tmin=200.0, tmax=400.0)

        union = interval1.union(interval2)
        assert union.tmin == 100.0
        assert union.tmax == 400.0

        # Non-overlapping intervals should raise error
        interval3 = TemperatureInterval(tmin=500.0, tmax=600.0)
        with pytest.raises(ValueError):
            interval1.union(interval3)


class TestTemperatureResolver:
    """Test cases for TemperatureResolver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = TemperatureResolver()

    def create_test_records(self) -> List[DatabaseRecord]:
        """Create test database records."""
        return [
            DatabaseRecord(
                id=1,
                formula="H2O(g)",
                tmin=298.0,
                tmax=2000.0,
                h298=-241.8,
                s298=188.7,
                f1=30.0,
                f2=10.0,
                f3=1.0,
                f4=-0.1,
                f5=0.01,
                f6=-0.001,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="H2O(l)",
                tmin=273.0,
                tmax=373.0,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=3,
                formula="Fe(s)",
                tmin=298.0,
                tmax=1800.0,
                h298=0.0,
                s298=27.3,
                f1=20.0,
                f2=5.0,
                f3=0.3,
                f4=-0.02,
                f5=0.002,
                f6=-0.0002,
                tmelt=1811.0,
                tboil=3134.0,
                reliability_class=2
            )
        ]

    def test_check_coverage_full(self):
        """Test full temperature coverage."""
        records = self.create_test_records()
        target_range = (300.0, 350.0)

        coverage = self.resolver.check_coverage(records, target_range)
        assert coverage == 'full'

    def test_check_coverage_partial(self):
        """Test partial temperature coverage."""
        records = self.create_test_records()
        target_range = (100.0, 400.0)

        coverage = self.resolver.check_coverage(records, target_range)
        assert coverage == 'partial'

    def test_check_coverage_none(self):
        """Test no temperature coverage."""
        records = self.create_test_records()
        target_range = (2500.0, 3000.0)

        coverage = self.resolver.check_coverage(records, target_range)
        assert coverage == 'none'

    def test_check_coverage_empty_records(self):
        """Test coverage with empty records list."""
        target_range = (300.0, 350.0)
        coverage = self.resolver.check_coverage([], target_range)
        assert coverage == 'none'

    def test_get_covered_ranges(self):
        """Test getting covered temperature ranges."""
        records = self.create_test_records()
        target_range = (250.0, 500.0)

        covered = self.resolver.get_covered_ranges(records, target_range)
        assert len(covered) > 0

        # Check that intervals are within target range
        for interval in covered:
            assert interval.tmin >= 250.0
            assert interval.tmax <= 500.0

    def test_get_covered_ranges_no_target(self):
        """Test getting covered ranges without target limitation."""
        records = self.create_test_records()
        covered = self.resolver.get_covered_ranges(records)

        assert len(covered) >= 1
        # Should merge overlapping intervals
        total_coverage = sum(interval.width for interval in covered)
        assert total_coverage > 0

    def test_get_gaps(self):
        """Test finding gaps in temperature coverage."""
        records = self.create_test_records()
        target_range = (100.0, 500.0)

        gaps = self.resolver.get_gaps(records, target_range)
        assert len(gaps) > 0

        # Check that gaps are within target range
        for gap in gaps:
            assert gap.tmin >= 100.0
            assert gap.tmax <= 500.0

        # Check that gaps don't overlap with covered ranges
        covered = self.resolver.get_covered_ranges(records, target_range)
        for gap in gaps:
            for interval in covered:
                assert not gap.overlaps_with(interval)

    def test_get_gaps_no_gaps(self):
        """Test gaps when there are none (full coverage)."""
        records = self.create_test_records()
        target_range = (300.0, 350.0)

        gaps = self.resolver.get_gaps(records, target_range)
        # Should have minimal or no gaps in fully covered range
        total_gap_width = sum(gap.width for gap in gaps)
        assert total_gap_width < 10.0  # Allow small gaps

    def test_calculate_coverage_percentage(self):
        """Test percentage coverage calculation."""
        records = self.create_test_records()

        # Full coverage
        percentage = self.resolver.calculate_coverage_percentage(records, (300.0, 350.0))
        assert percentage == pytest.approx(1.0)

        # Partial coverage
        percentage = self.resolver.calculate_coverage_percentage(records, (100.0, 500.0))
        assert 0.0 < percentage < 1.0

        # No coverage
        percentage = self.resolver.calculate_coverage_percentage(records, (2500.0, 3000.0))
        assert percentage == 0.0

    def test_get_temperature_statistics(self):
        """Test temperature statistics calculation."""
        records = self.create_test_records()
        stats = self.resolver.get_temperature_statistics(records)

        assert stats['total_records'] == 3
        assert stats['records_with_temperatures'] == 3
        assert stats['min_temperature'] > 0
        assert stats['max_temperature'] > stats['min_temperature']
        assert stats['avg_range_width'] > 0
        assert stats['total_coverage_width'] > 0

    def test_get_temperature_statistics_empty(self):
        """Test temperature statistics with empty records."""
        stats = self.resolver.get_temperature_statistics([])

        assert stats['total_records'] == 0
        assert stats['records_with_temperatures'] == 0
        assert stats['min_temperature'] is None
        assert stats['max_temperature'] is None
        assert stats['avg_range_width'] == 0.0
        assert stats['total_coverage_width'] == 0.0

    def test_cache_functionality(self):
        """Test caching of results."""
        records = self.create_test_records()
        target_range = (300.0, 350.0)

        # First call should compute and cache
        coverage1 = self.resolver.check_coverage(records, target_range)

        # Second call should use cache
        coverage2 = self.resolver.check_coverage(records, target_range)

        assert coverage1 == coverage2

        # Clear cache and verify recomputation
        self.resolver.clear_cache()
        coverage3 = self.resolver.check_coverage(records, target_range)
        assert coverage3 == coverage1

    def test_merge_intervals(self):
        """Test interval merging functionality."""
        intervals = [
            TemperatureInterval(100.0, 200.0, reliability_class=1),
            TemperatureInterval(150.0, 250.0, reliability_class=2),  # Overlaps with first
            TemperatureInterval(300.0, 400.0, reliability_class=1),  # Separate
            TemperatureInterval(350.0, 450.0, reliability_class=3),  # Overlaps with third
        ]

        merged = self.resolver._merge_intervals(intervals)

        # Should merge overlapping intervals
        assert len(merged) == 2

        # First merged interval
        assert merged[0].tmin == 100.0
        assert merged[0].tmax == 250.0
        assert merged[0].reliability_class == 1  # Best reliability

        # Second merged interval
        assert merged[1].tmin == 300.0
        assert merged[1].tmax == 450.0
        assert merged[1].reliability_class == 1  # Best reliability

    def test_extract_intervals(self):
        """Test interval extraction from records."""
        records = self.create_test_records()
        intervals = self.resolver._extract_intervals(records)

        assert len(intervals) == 3

        # Check that all intervals are valid
        for interval in intervals:
            assert interval.tmin > 0
            assert interval.tmax > interval.tmin
            assert interval.source_record_id is not None

        # Check that tmax values are reasonable (capped)
        for interval in intervals:
            assert interval.tmax <= 10000.0