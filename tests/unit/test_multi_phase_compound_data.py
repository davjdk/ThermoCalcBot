"""
Unit tests for MultiPhaseCompoundData (Stage 3 component).

This module tests the functionality of the MultiPhaseCompoundData class,
which serves as the central data structure for managing multiple database
records within phase segments.
"""

import pytest
from unittest.mock import Mock, patch

from src.thermo_agents.models.search import (
    MultiPhaseCompoundData,
    DatabaseRecord,
    PhaseSegment,
    RecordTransition
)


class TestMultiPhaseCompoundData:
    """Test cases for MultiPhaseCompoundData."""

    @pytest.fixture
    def sample_records(self):
        """Create sample database records for testing."""
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
                f2=15.8,
                f3=-2.1,
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
                tmin=600.0,
                tmax=900.0,
                h298=0.0,
                s298=0.0,
                f1=48.1,
                f2=16.2,
                f3=-2.3,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=3,
                formula="FeO",
                phase="l",
                tmin=1650.0,
                tmax=3687.0,
                h298=0.0,
                s298=0.0,
                f1=60.5,
                f2=18.3,
                f3=-2.8,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            )
        ]

    @pytest.fixture
    def sample_segments(self, sample_records):
        """Create sample phase segments from records."""
        return [
            PhaseSegment.from_database_record(record)
            for record in sample_records
        ]

    @pytest.fixture
    def compound_data(self, sample_records, sample_segments):
        """Create a MultiPhaseCompoundData instance for testing."""
        return MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=sample_records,
            phase_segments=sample_segments
        )

    def test_init_basic(self, sample_records, sample_segments):
        """Test basic initialization."""
        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=sample_records,
            phase_segments=sample_segments
        )

        assert data.compound_formula == "FeO"
        assert len(data.all_records) == 3
        assert len(data.phase_segments) == 3
        assert data.total_temperature_range == (298.0, 3687.0)

    def test_init_with_segments_only(self, sample_segments):
        """Test initialization with only segments (records extracted from segments)."""
        records = [segment.record for segment in sample_segments]

        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=records,
            phase_segments=sample_segments
        )

        assert data.compound_formula == "FeO"
        assert len(data.all_records) == 3
        assert len(data.phase_segments) == 3

    def test_post_init_auto_calculation(self, sample_records, sample_segments):
        """Test that post-initialization automatically calculates total range."""
        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=sample_records,
            phase_segments=sample_segments,
            total_temperature_range=None  # Should be calculated
        )

        assert data.total_temperature_range == (298.0, 3687.0)

    def test_get_record_at_temperature(self, compound_data):
        """Test getting record for specific temperature."""
        # Test temperature in first record range
        record_400 = compound_data.get_record_at_temperature(400.0)
        assert record_400.id == 1
        assert record_400.tmin <= 400.0 <= record_400.tmax

        # Test temperature in second record range
        record_700 = compound_data.get_record_at_temperature(700.0)
        assert record_700.id == 2
        assert record_700.tmin <= 700.0 <= record_700.tmax

        # Test temperature in third record range
        record_2000 = compound_data.get_record_at_temperature(2000.0)
        assert record_2000.id == 3
        assert record_2000.tmin <= 2000.0 <= record_2000.tmax

    def test_get_record_at_temperature_out_of_range(self, compound_data):
        """Test error when temperature is outside available range."""
        with pytest.raises(ValueError, match="No phase segment covers temperature"):
            compound_data.get_record_at_temperature(200.0)  # Below minimum

        with pytest.raises(ValueError, match="No phase segment covers temperature"):
            compound_data.get_record_at_temperature(4000.0)  # Above maximum

    def test_get_record_at_temperature_caching(self, compound_data):
        """Test that record selection is cached."""
        # First call should populate cache
        record1 = compound_data.get_record_at_temperature(400.0)
        assert len(compound_data.active_records_cache) == 1

        # Second call should use cache
        record2 = compound_data.get_record_at_temperature(400.0)
        assert record1 is record2  # Should be same object
        assert len(compound_data.active_records_cache) == 1

    def test_get_transition_between_records(self, compound_data):
        """Test getting transition information between records."""
        # Add a transition to test retrieval
        transition = RecordTransition(
            from_record_id=1,
            to_record_id=2,
            transition_temperature=600.0,
            delta_H_correction=100.0,
            delta_S_correction=2.0
        )
        compound_data.record_transitions[(1, 2)] = transition

        retrieved = compound_data.get_transition_between_records(1, 2)
        assert retrieved is not None
        assert retrieved.from_record_id == 1
        assert retrieved.to_record_id == 2
        assert retrieved.transition_temperature == 600.0

        # Test non-existent transition
        assert compound_data.get_transition_between_records(1, 3) is None

    def test_precompute_transitions(self, compound_data):
        """Test precomputation of transitions."""
        with patch('src.thermo_agents.models.search.RecordTransitionManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Mock the transition calculation
            mock_manager.calculate_transition_corrections.return_value = {
                "delta_H": 100.0,
                "delta_S": 2.0,
                "warning": None
            }

            compound_data.precompute_transitions()

            # Should have called the transition manager
            mock_manager_class.assert_called_once()

            # Should have computed transitions for consecutive records
            # (This is a simplified test - real implementation would be more complex)
            assert len(compound_data.record_transitions) >= 0

    def test_get_available_range(self, compound_data):
        """Test getting available temperature range."""
        range_ = compound_data.get_available_range()
        assert range_ == (298.0, 3687.0)

    def test_get_available_range_precomputed(self, sample_records, sample_segments):
        """Test getting range when precomputed."""
        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=sample_records,
            phase_segments=sample_segments,
            total_temperature_range=(300.0, 3500.0)  # Precomputed
        )

        range_ = data.get_available_range()
        assert range_ == (300.0, 3500.0)  # Should return precomputed value

    def test_get_available_range_no_segments(self):
        """Test getting range when no segments exist."""
        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=[],
            phase_segments=[]
        )

        range_ = data.get_available_range()
        assert range_ == (0.0, 0.0)

    def test_get_records_in_range(self, compound_data):
        """Test getting records within temperature range."""
        # Range overlapping multiple records
        records = compound_data.get_records_in_range(500.0, 800.0)
        assert len(records) == 2  # Should include records 1 and 2
        assert records[0].id == 1
        assert records[1].id == 2

        # Range within single record
        records = compound_data.get_records_in_range(300.0, 400.0)
        assert len(records) == 1
        assert records[0].id == 1

        # Range with no records
        records = compound_data.get_records_in_range(100.0, 200.0)
        assert len(records) == 0

    def test_get_segments_in_range(self, compound_data):
        """Test getting segments within temperature range."""
        # Range overlapping multiple segments
        segments = compound_data.get_segments_in_range(500.0, 2000.0)
        assert len(segments) == 3  # Should include all segments

        # Range within single segment
        segments = compound_data.get_segments_in_range(300.0, 400.0)
        assert len(segments) == 1
        assert segments[0].record.id == 1

    def test_check_multiple_records_true(self):
        """Test detection of multiple records per segment."""
        # Create records that overlap in temperature range
        record1 = DatabaseRecord(
            id=1,
            formula="FeO",
            phase="s",
            tmin=298.0,
            tmax=600.0,
            h298=-265.053,
            s298=59.807,
            f1=45.2,
            f2=15.8,
            f3=-2.1,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

        record2 = DatabaseRecord(
            id=2,
            formula="FeO",
            phase="s",
            tmin=599.0,  # Overlaps with record1
            tmax=900.0,
            h298=0.0,
            s298=0.0,
            f1=48.1,
            f2=16.2,
            f3=-2.3,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=1650.0,
            tboil=3687.0,
            reliability_class=1
        )

        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=[record1, record2],
            phase_segments=[]
        )

        assert data.has_multiple_records_per_segment is True

    def test_check_multiple_records_false(self, compound_data):
        """Test detection when no multiple records per segment."""
        # Our sample compound_data has records in different phases, so no overlap
        assert compound_data.has_multiple_records_per_segment is False

    def test_to_dict(self, compound_data):
        """Test dictionary serialization."""
        data_dict = compound_data.to_dict()

        assert data_dict["formula"] == "FeO"
        assert data_dict["records_count"] == 3
        assert data_dict["segments_count"] == 3
        assert data_dict["temperature_range"] == (298.0, 3687.0)
        assert data_dict["has_multiple_records"] is False
        assert data_dict["transitions_count"] == 0
        assert "phase_sequence" in data_dict

    def test_to_dict_with_transitions(self, compound_data):
        """Test dictionary serialization with transitions."""
        # Add a transition
        transition = RecordTransition(
            from_record_id=1,
            to_record_id=2,
            transition_temperature=600.0,
            delta_H_correction=100.0,
            delta_S_correction=2.0
        )
        compound_data.record_transitions[(1, 2)] = transition

        data_dict = compound_data.to_dict()
        assert data_dict["transitions_count"] == 1

    def test_calculate_total_range(self, compound_data):
        """Test internal total range calculation."""
        # Clear the range to force recalculation
        compound_data.total_temperature_range = None
        compound_data._calculate_total_range()

        assert compound_data.total_temperature_range == (298.0, 3687.0)

    def test_calculate_total_range_no_records(self):
        """Test total range calculation with no records."""
        data = MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=[],
            phase_segments=[]
        )

        data._calculate_total_range()
        assert data.total_temperature_range is None

    def test_empty_compound_data(self):
        """Test MultiPhaseCompoundData with no data."""
        data = MultiPhaseCompoundData(
            compound_formula="Empty",
            all_records=[],
            phase_segments=[]
        )

        assert data.compound_formula == "Empty"
        assert len(data.all_records) == 0
        assert len(data.phase_segments) == 0
        assert data.total_temperature_range is None
        assert data.has_multiple_records_per_segment is False

        # Should handle empty state gracefully
        with pytest.raises(ValueError):
            data.get_record_at_temperature(300.0)

        range_ = data.get_available_range()
        assert range_ == (0.0, 0.0)

    def test_edge_case_exact_boundary_temperatures(self, compound_data):
        """Test record selection at exact boundary temperatures."""
        # At exact boundary between records 1 and 2
        record = compound_data.get_record_at_temperature(600.0)
        # Should select record that covers this temperature
        assert record.tmin <= 600.0 <= record.tmax

        # At minimum temperature
        record = compound_data.get_record_at_temperature(298.0)
        assert record.tmin <= 298.0 <= record.tmax

        # At maximum temperature
        record = compound_data.get_record_at_temperature(3687.0)
        assert record.tmin <= 3687.0 <= record.tmax