"""
Unit tests for PhaseSegmentBuilder (Stage 2).

This module tests the phase segment building functionality
for multi-phase thermodynamic calculations.
"""

import pytest
from datetime import datetime

from src.thermo_agents.models.search import (
    DatabaseRecord,
    PhaseSegment,
    PhaseTransition,
    TransitionType
)
from src.thermo_agents.filtering.phase_segment_builder import (
    PhaseSegmentBuilder,
    SegmentAnalysis
)


class TestPhaseSegmentBuilder:
    """Unit tests for PhaseSegmentBuilder."""

    @pytest.fixture
    def builder(self):
        """Create a PhaseSegmentBuilder instance for testing."""
        return PhaseSegmentBuilder()

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
                tmin=600.0,
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
                reliability_class=1
            ),
            DatabaseRecord(
                id=3,
                formula="FeO",
                phase="l",
                tmin=1650.0,
                tmax=5000.0,
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
                reliability_class=2
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
                reliability_class=2
            )
        ]

    @pytest.fixture
    def water_records(self):
        """Create sample H2O records for testing."""
        return [
            DatabaseRecord(
                id=10,
                formula="H2O",
                phase="s",
                tmin=273.15,
                tmax=273.15,
                h298=-285.83,
                s298=69.91,
                f1=46.7,
                f2=32.4,
                f3=-8.7,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            DatabaseRecord(
                id=11,
                formula="H2O",
                phase="l",
                tmin=273.15,
                tmax=373.15,
                h298=-285.83,
                s298=69.91,
                f1=75.3,
                f2=15.8,
                f3=-2.4,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            DatabaseRecord(
                id=12,
                formula="H2O",
                phase="g",
                tmin=373.15,
                tmax=2000.0,
                h298=-241.83,
                s298=188.72,
                f1=30.0,
                f2=7.3,
                f3=-1.2,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            )
        ]

    def test_build_phase_segments_feo(self, builder, feo_records):
        """Test building phase segments for FeO."""
        temperature_range = (298.0, 5000.0)

        result = builder.build_phase_segments(
            records=feo_records,
            temperature_range=temperature_range,
            compound_formula="FeO"
        )

        # Verify basic structure
        assert result is not None
        assert len(result.segments) > 0

        # Verify segments cover the temperature range
        assert result.segments[0].T_start <= temperature_range[0]
        assert result.segments[-1].T_end >= temperature_range[1]

        # Verify phase transitions are identified
        assert len(result.phase_transitions) >= 1

        # Check for specific FeO behavior
        phases = [seg.record.phase for seg in result.segments if seg.record]
        assert 's' in phases  # Solid phase should be present
        assert 'l' in phases  # Liquid phase should be present
        assert 'g' in phases  # Gas phase should be present

    def test_build_phase_segments_water(self, builder, water_records):
        """Test building phase segments for H2O."""
        temperature_range = (250.0, 1000.0)

        result = builder.build_phase_segments(
            records=water_records,
            temperature_range=temperature_range,
            compound_formula="H2O"
        )

        # Verify water has all three phases
        phases = [seg.record.phase for seg in result.segments if seg.record]
        assert 's' in phases
        assert 'l' in phases
        assert 'g' in phases

        # Verify transition temperatures for water
        transitions = result.phase_transitions
        melting_transition = next((t for t in transitions if t.transition_type == TransitionType.MELTING), None)
        boiling_transition = next((t for t in transitions if t.transition_type == TransitionType.BOILING), None)

        assert melting_transition is not None
        assert boiling_transition is not None
        assert abs(melting_transition.temperature - 273.15) < 10.0
        assert abs(boiling_transition.temperature - 373.15) < 10.0

    def test_extract_transition_temperatures(self, builder, feo_records):
        """Test extraction of transition temperatures."""
        tmelt, tboil = builder._extract_transition_temperatures(feo_records)

        assert tmelt is not None
        assert tboil is not None
        assert tmelt < tboil

        # Verify FeO specific values
        assert abs(tmelt - 1650.0) < 1.0
        assert abs(tboil - 3687.0) < 1.0

    def test_create_phase_segments_complete_transitions(self, builder):
        """Test creating segments with complete transition information."""
        records = []  # Not used in this test
        temperature_range = (298.0, 5000.0)
        tmelt = 1650.0
        tboil = 3687.0

        segments = builder._create_phase_segments(
            records=records,
            temperature_range=temperature_range,
            tmelt=tmelt,
            tboil=tboil
        )

        # Should create 3 segments: solid, liquid, gas
        assert len(segments) == 3

        # Verify segment boundaries
        assert segments[0].T_start == temperature_range[0]  # Solid starts at range start
        assert segments[0].T_end == tmelt  # Solid ends at melting
        assert segments[1].T_start == tmelt  # Liquid starts at melting
        assert segments[1].T_end == tboil  # Liquid ends at boiling
        assert segments[2].T_start == tboil  # Gas starts at boiling
        assert segments[2].T_end == temperature_range[1]  # Gas ends at range end

    def test_create_phase_segments_partial_transitions(self, builder):
        """Test creating segments with partial transition information."""
        records = []  # Not used in this test
        temperature_range = (298.0, 1000.0)
        tmelt = None
        tboil = None

        segments = builder._create_phase_segments(
            records=records,
            temperature_range=temperature_range,
            tmelt=tmelt,
            tboil=tboil
        )

        # Should create 1 segment when no transition info
        assert len(segments) == 1
        assert segments[0].T_start == temperature_range[0]
        assert segments[0].T_end == temperature_range[1]

    def test_assign_records_to_segments(self, builder, feo_records):
        """Test assignment of records to segments."""
        temperature_range = (298.0, 5000.0)
        tmelt, tboil = builder._extract_transition_temperatures(feo_records)

        # Create segments
        segments = builder._create_phase_segments(
            records=feo_records,
            temperature_range=temperature_range,
            tmelt=tmelt,
            tboil=tboil
        )

        # Assign records
        builder._assign_records_to_segments(feo_records, segments)

        # Verify records are assigned
        for segment in segments:
            assert segment.record is not None

        # Verify phase assignment
        solid_segment = next((s for s in segments if s.T_end <= tmelt), None)
        liquid_segment = next((s for s in segments if tmelt <= s.T_start < tboil), None)
        gas_segment = next((s for s in segments if s.T_start >= tboil), None)

        assert solid_segment is not None
        assert liquid_segment is not None
        assert gas_segment is not None

        assert solid_segment.record.phase == 's'
        assert liquid_segment.record.phase == 'l'
        assert gas_segment.record.phase == 'g'

    def test_group_records_by_phase(self, builder, feo_records):
        """Test grouping records by phase."""
        grouped = builder._group_records_by_phase(feo_records)

        assert 's' in grouped
        assert 'l' in grouped
        assert 'g' in grouped

        assert len(grouped['s']) == 2  # Two solid records
        assert len(grouped['l']) == 1  # One liquid record
        assert len(grouped['g']) == 1  # One gas record

    def test_determine_segment_phase(self, builder, feo_records):
        """Test determining expected phase for segments."""
        # Test solid segment
        solid_segment = PhaseSegment(
            record=None,
            T_start=298.0,
            T_end=1000.0,
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
            is_transition_boundary=False
        )
        phase = builder._determine_segment_phase(solid_segment, feo_records)
        assert phase == 's'

        # Test liquid segment
        liquid_segment = PhaseSegment(
            record=None,
            T_start=2000.0,
            T_end=3000.0,
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
            is_transition_boundary=False
        )
        phase = builder._determine_segment_phase(liquid_segment, feo_records)
        assert phase == 'l'

        # Test gas segment
        gas_segment = PhaseSegment(
            record=None,
            T_start=4000.0,
            T_end=5000.0,
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
            is_transition_boundary=False
        )
        phase = builder._determine_segment_phase(gas_segment, feo_records)
        assert phase == 'g'

    def test_identify_phase_transitions(self, builder):
        """Test identification of phase transitions."""
        # Create segments with known boundaries
        segments = [
            PhaseSegment(
                record=DatabaseRecord(
                    id=1, formula="FeO", phase="s", tmin=298.0, tmax=1650.0,
                    h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=1
                ),
                T_start=298.0,
                T_end=1650.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=True
            ),
            PhaseSegment(
                record=DatabaseRecord(
                    id=2, formula="FeO", phase="l", tmin=1650.0, tmax=3687.0,
                    h298=-233.0, s298=80.0, f1=60.0, f2=12.0, f3=-1.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=2
                ),
                T_start=1650.0,
                T_end=3687.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=True
            )
        ]

        transitions = builder._identify_phase_transitions(
            segments=segments,
            tmelt=1650.0,
            tboil=3687.0
        )

        assert len(transitions) >= 1

        melting_transition = next(
            (t for t in transitions if t.transition_type == TransitionType.MELTING),
            None
        )
        assert melting_transition is not None
        assert melting_transition.from_phase == 's'
        assert melting_transition.to_phase == 'l'
        assert abs(melting_transition.temperature - 1650.0) < 10.0

    def test_analyze_segments(self, builder):
        """Test segment analysis functionality."""
        # Create segments with complete coverage
        segments = [
            PhaseSegment(
                record=DatabaseRecord(
                    id=1, formula="FeO", phase="s", tmin=298.0, tmax=1650.0,
                    h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=1
                ),
                T_start=298.0,
                T_end=1650.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            ),
            PhaseSegment(
                record=DatabaseRecord(
                    id=2, formula="FeO", phase="l", tmin=1650.0, tmax=3687.0,
                    h298=-233.0, s298=80.0, f1=60.0, f2=12.0, f3=-1.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=2
                ),
                T_start=1650.0,
                T_end=3687.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            )
        ]

        temperature_range = (298.0, 3687.0)
        analysis = builder._analyze_segments(segments, temperature_range)

        assert isinstance(analysis, SegmentAnalysis)
        assert analysis.total_segments == 2
        assert len(analysis.optimized_segments) == 2
        assert len(analysis.coverage_gaps) == 0  # No gaps
        assert len(analysis.coverage_overlaps) == 0  # No overlaps
        assert isinstance(analysis.warnings, list)
        assert isinstance(analysis.analysis_timestamp, datetime)

    def test_analyze_segments_with_gaps(self, builder):
        """Test segment analysis with gaps in coverage."""
        # Create segments with a gap
        segments = [
            PhaseSegment(
                record=DatabaseRecord(
                    id=1, formula="FeO", phase="s", tmin=298.0, tmax=1000.0,
                    h298=-265.0, s298=60.0, f1=45.0, f2=18.0, f3=-3.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=1
                ),
                T_start=298.0,
                T_end=1000.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            ),
            PhaseSegment(
                record=DatabaseRecord(
                    id=2, formula="FeO", phase="l", tmin=2000.0, tmax=3000.0,
                    h298=-233.0, s298=80.0, f1=60.0, f2=12.0, f3=-1.0,
                    f4=0.0, f5=0.0, f6=0.0, tmelt=1650.0, tboil=3687.0,
                    reliability_class=2
                ),
                T_start=2000.0,
                T_end=3000.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            )
        ]

        temperature_range = (298.0, 3000.0)
        analysis = builder._analyze_segments(segments, temperature_range)

        # Should detect the gap between 1000K and 2000K
        assert len(analysis.coverage_gaps) == 1
        gap_start, gap_end = analysis.coverage_gaps[0]
        assert gap_start == 1000.0
        assert gap_end == 2000.0

        # Should have warnings about the gap
        assert any("gap" in warning.lower() for warning in analysis.warnings)

    def test_invalid_input_empty_records(self, builder):
        """Test handling of empty records list."""
        with pytest.raises(ValueError, match="No records provided"):
            builder.build_phase_segments(
                records=[],
                temperature_range=(298.0, 1000.0)
            )

    def test_invalid_input_temperature_range(self, builder, feo_records):
        """Test handling of invalid temperature range."""
        # Invalid range (start >= end)
        with pytest.raises(ValueError, match="Invalid temperature range"):
            builder.build_phase_segments(
                records=feo_records,
                temperature_range=(1000.0, 500.0)
            )

    def test_optimize_segments_coverage(self, builder):
        """Test optimization of segment coverage."""
        # Create segments with overlap
        segments = [
            PhaseSegment(
                record=None,
                T_start=298.0,
                T_end=1200.0,  # Overlaps with next
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            ),
            PhaseSegment(
                record=None,
                T_start=1000.0,  # Overlaps with previous
                T_end=2000.0,
                H_start=0.0,
                S_start=0.0,
                delta_H=0.0,
                delta_S=0.0,
                is_transition_boundary=False
            )
        ]

        builder._optimize_segments_coverage(segments)

        # Segments should be sorted
        assert segments[0].T_start <= segments[1].T_start

        # Overlap should be resolved (segments adjusted)
        assert segments[0].T_end <= segments[1].T_start

    def test_estimate_transition_enthalpy(self, builder):
        """Test estimation of transition enthalpy."""
        # Test melting transition
        delta_H = builder._estimate_transition_enthalpy('s', 'l', 1650.0)
        assert delta_H > 0
        assert isinstance(delta_H, float)

        # Test boiling transition
        delta_H = builder._estimate_transition_enthalpy('l', 'g', 3687.0)
        assert delta_H > 0
        assert isinstance(delta_H, float)

        # Test unknown transition
        delta_H = builder._estimate_transition_enthalpy('s', 'g', 2000.0)
        assert delta_H > 0
        assert isinstance(delta_H, float)