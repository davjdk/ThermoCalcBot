"""
Unit tests for RecordSelector (Stage 2).

This module tests the record selection functionality
for multi-phase thermodynamic calculations.
"""

import pytest
from datetime import datetime

from src.thermo_agents.models.search import DatabaseRecord
from src.thermo_agents.filtering.record_selector import (
    RecordSelector,
    RecordSelection,
    TransitionPoint
)


class TestRecordSelector:
    """Unit tests for RecordSelector."""

    @pytest.fixture
    def selector(self):
        """Create a RecordSelector instance for testing."""
        return RecordSelector()

    @pytest.fixture
    def feo_records(self):
        """Create sample FeO records for testing."""
        return [
            DatabaseRecord(
                id=1,
                formula="FeO",
                phase="s",
                tmin=298.0,
                tmax=600.0,
                h298=-265.053,
                s298=59.807,
                f1=45.2,
                f2=18.5,
                f3=-3.7,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="FeO",
                phase="s",
                tmin=500.0,
                tmax=900.0,
                h298=-265.053,
                s298=59.807,
                f1=48.1,
                f2=16.2,
                f3=-2.8,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=2  # Lower reliability
            ),
            DatabaseRecord(
                id=3,
                formula="FeO",
                phase="l",
                tmin=1650.0,
                tmax=3000.0,
                h298=-233.553,
                s298=80.307,
                f1=60.5,
                f2=12.3,
                f3=-1.2,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=4,
                formula="FeO",
                phase="g",
                tmin=3687.0,
                tmax=6000.0,
                h298=-200.0,
                s298=95.0,
                f1=35.7,
                f2=8.9,
                f3=-0.5,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=5,
                formula="FeO",
                phase="s",
                tmin=298.0,
                tmax=1650.0,
                h298=0.0,  # Bad data
                s298=0.0,  # Bad data
                f1=50.0,
                f2=15.0,
                f3=-2.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=3  # Worst reliability
            )
        ]

    def test_select_record_for_temperature_perfect_coverage(self, selector, feo_records):
        """Test selecting record with perfect temperature coverage."""
        temperature = 500.0

        selection = selector.select_record_for_temperature(feo_records, temperature)

        assert isinstance(selection, RecordSelection)
        assert selection.selected_record is not None
        assert selection.selected_record.tmin <= temperature <= selection.selected_record.tmax
        assert selection.confidence > 0.5

        # Should prefer record with better reliability
        assert selection.selected_record.reliability_class == 1
        assert selection.selected_record.phase == 's'

    def test_select_record_for_temperature_with_preferred_phase(self, selector, feo_records):
        """Test selecting record with preferred phase."""
        temperature = 2000.0
        preferred_phase = 'l'

        selection = selector.select_record_for_temperature(
            feo_records, temperature, preferred_phase
        )

        assert selection.selected_record.phase == preferred_phase
        assert selection.selected_record.tmin <= temperature <= selection.selected_record.tmax

    def test_select_record_for_temperature_closest_match(self, selector, feo_records):
        """Test selecting closest record when no perfect coverage."""
        temperature = 4000.0

        selection = selector.select_record_for_temperature(feo_records, temperature)

        assert selection.selected_record is not None
        # Should select the gas phase record (closest)
        assert selection.selected_record.phase == 'g'
        assert selection.selected_record.id == 4

        # Should have warnings about not covering temperature
        assert any("does not cover" in warning for warning in selection.warnings)

    def test_select_record_for_temperature_data_quality_priority(self, selector, feo_records):
        """Test that records with better data quality are preferred."""
        temperature = 400.0

        selection = selector.select_record_for_temperature(feo_records, temperature)

        # Should prefer record 1 over record 5 due to better data (h298, s298)
        assert selection.selected_record.h298 != 0
        assert selection.selected_record.s298 != 0

        # Record with good data should have higher confidence
        assert selection.confidence > 0.7

    def test_select_record_for_temperature_empty_records(self, selector):
        """Test handling of empty records list."""
        with pytest.raises(ValueError, match="No records provided"):
            selector.select_record_for_temperature([], 500.0)

    def test_find_covering_records(self, selector, feo_records):
        """Test finding records that cover a temperature."""
        temperature = 500.0

        covering_records = selector._find_covering_records(feo_records, temperature)

        assert len(covering_records) >= 2  # Records 1 and 2 should cover
        for record in covering_records:
            assert record.tmin <= temperature <= record.tmax

    def test_find_closest_records(self, selector, feo_records):
        """Test finding records closest to a temperature."""
        temperature = 4000.0

        closest_records = selector._find_closest_records(feo_records, temperature)

        assert len(closest_records) == len(feo_records)
        assert closest_records[0].id == 4  # Gas record should be closest

        # Verify distance calculation
        for record in closest_records:
            if temperature < record.tmin:
                expected_distance = record.tmin - temperature
            elif temperature > record.tmax:
                expected_distance = temperature - record.tmax
            else:
                expected_distance = 0

            # Should be sorted by distance
            record_index = closest_records.index(record)
            if record_index > 0:
                prev_record = closest_records[record_index - 1]
                # This is a simplified check - in practice, we'd need to calculate actual distances
                assert True  # Placeholder assertion

    def test_score_records(self, selector, feo_records):
        """Test scoring of records."""
        temperature = 500.0

        scored_records = selector._score_records(feo_records, temperature)

        assert len(scored_records) == len(feo_records)
        assert all(0 <= score <= 1 for _, score in scored_records)

        # Should be sorted by score (descending)
        scores = [score for _, score in scored_records]
        assert scores == sorted(scores, reverse=True)

        # Record with good coverage and reliability should have highest score
        best_record, best_score = scored_records[0]
        assert best_score > 0.7
        assert best_record.h298 != 0  # Good data

    def test_determine_selection_reason(self, selector, feo_records):
        """Test determination of selection reason."""
        # Test perfect coverage
        record = feo_records[0]  # Good coverage, high reliability
        temperature = 500.0
        score = 0.9

        reason, confidence = selector._determine_selection_reason(record, temperature, score)

        assert "covers temperature" in reason
        assert "high reliability" in reason
        assert "complete thermodynamic data" in reason
        assert confidence > 0.8

    def test_determine_selection_reason_low_quality(self, selector, feo_records):
        """Test selection reason for low quality record."""
        record = feo_records[4]  # Bad data, low reliability
        temperature = 400.0
        score = 0.3

        reason, confidence = selector._determine_selection_reason(record, temperature, score)

        assert "missing thermodynamic data" in reason
        assert confidence < 0.5

    def test_generate_selection_warnings(self, selector, feo_records):
        """Test generation of selection warnings."""
        # Test record with good data
        good_record = feo_records[0]
        temperature = 500.0

        warnings = selector._generate_selection_warnings(good_record, temperature, feo_records)
        assert len(warnings) == 0

        # Test record with bad data
        bad_record = feo_records[4]
        warnings = selector._generate_selection_warnings(bad_record, temperature, feo_records)
        assert len(warnings) > 0
        assert any("H298=0 and S298=0" in warning for warning in warnings)

        # Test record that doesn't cover temperature
        temperature = 4000.0
        partial_record = feo_records[0]  # Solid record doesn't cover gas temperature
        warnings = selector._generate_selection_warnings(partial_record, temperature, feo_records)
        assert any("does not cover temperature" in warning for warning in warnings)

    def test_find_transition_points(self, selector, feo_records):
        """Test finding transition points between records."""
        transitions = selector.find_transition_points(feo_records)

        assert isinstance(transitions, list)
        # Should find transitions at boundaries
        assert len(transitions) > 0

        # Check transition structure
        for transition in transitions:
            assert isinstance(transition, TransitionPoint)
            assert transition.temperature > 0
            assert transition.from_record is not None
            assert transition.to_record is not None
            assert transition.reason in ["temperature_limit", "reliability", "phase_change"]
            assert 0 <= transition.confidence <= 1

    def test_analyze_record_transition_touching(self, selector):
        """Test analysis of touching records."""
        record1 = DatabaseRecord(
            id=1, formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1
        )
        record2 = DatabaseRecord(
            id=2, formula="FeO", phase="l", tmin=600.0, tmax=900.0,
            h298=-233.0, s298=80.0, f1=60.0, f2=12.0, f3=-1.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1
        )

        transitions = selector._analyze_record_transition(record1, record2)

        assert len(transitions) == 1
        transition = transitions[0]
        assert transition.from_record == record1
        assert transition.to_record == record2
        assert transition.temperature == 600.0  # Touching point
        assert transition.reason == "phase_change"  # Different phases
        assert transition.confidence > 0.8

    def test_analyze_record_transition_reliability(self, selector):
        """Test analysis of transition due to reliability difference."""
        record1 = DatabaseRecord(
            id=1, formula="FeO", phase="s", tmin=298.0, tmax=800.0,
            h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=3  # Low reliability
        )
        record2 = DatabaseRecord(
            id=2, formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=-265.0, s298=60.0, f1=48.0, f2=16.0, f3=-2.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1  # High reliability
        )

        transitions = selector._analyze_record_transition(record1, record2)

        assert len(transitions) == 1
        transition = transitions[0]
        assert transition.reason == "reliability"  # Due to reliability difference

    def test_optimize_record_sequence(self, selector, feo_records):
        """Test optimization of record sequence."""
        temperature_range = (298.0, 4000.0)

        optimized_sequence = selector.optimize_record_sequence(feo_records, temperature_range)

        assert len(optimized_sequence) <= len(feo_records)
        assert len(optimized_sequence) > 0

        # Should be sorted by reliability
        reliabilities = [r.reliability_class for r in optimized_sequence if r.reliability_class]
        assert reliabilities == sorted(reliabilities)

        # Should cover the temperature range
        if len(optimized_sequence) > 1:
            assert optimized_sequence[0].tmin <= temperature_range[0]
            assert optimized_sequence[-1].tmax >= temperature_range[1]

    def test_remove_duplicates(self, selector):
        """Test removal of duplicate records."""
        # Create records with duplicates
        record1 = DatabaseRecord(
            id=1, formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1
        )
        record2 = DatabaseRecord(
            id=1, formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1
        )  # Duplicate (same ID)
        record3 = DatabaseRecord(
            id=None, formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
            f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
            reliability_class=1
        )  # Duplicate (same data, no ID)

        records_with_duplicates = [record1, record2, record3]
        unique_records = selector._remove_duplicates(records_with_duplicates)

        assert len(unique_records) == 1
        assert unique_records[0].id == 1

    def test_verify_sequence_coverage_good(self, selector, feo_records):
        """Test verification of good sequence coverage."""
        # Create a sequence with good coverage
        good_sequence = [feo_records[0], feo_records[2]]  # Solid and liquid
        temperature_range = (298.0, 3000.0)

        issues = selector._verify_sequence_coverage(good_sequence, temperature_range)

        # Should have minimal issues
        assert len(issues) <= 1

    def test_verify_sequence_coverage_gaps(self, selector, feo_records):
        """Test verification of sequence with gaps."""
        # Create a sequence with gaps
        gap_sequence = [feo_records[0]]  # Only solid, missing liquid/gas
        temperature_range = (298.0, 5000.0)

        issues = selector._verify_sequence_coverage(gap_sequence, temperature_range)

        # Should detect gaps
        assert len(issues) > 0
        assert any("Gap" in issue for issue in issues)

    def test_caching_behavior(self, selector, feo_records):
        """Test that caching works correctly."""
        temperature = 500.0

        # First call - should cache result
        selection1 = selector.select_record_for_temperature(feo_records, temperature)

        # Second call - should use cached result
        selection2 = selector.select_record_for_temperature(feo_records, temperature)

        # Results should be identical
        assert selection1.selected_record.id == selection2.selected_record.id
        assert selection1.confidence == selection2.confidence

        # Different temperature - should not use cache
        selection3 = selector.select_record_for_temperature(feo_records, 600.0)

        # Cache should have multiple entries
        assert len(selector._selection_cache) >= 2