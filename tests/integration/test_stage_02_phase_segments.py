"""
Integration tests for Stage 2: Phase Segment Building.

This module tests the integration of phase segment building
with the FilterPipeline and other components.
"""

import pytest
from unittest.mock import Mock, patch

from src.thermo_agents.models.search import (
    DatabaseRecord,
    FilterContext,
    MultiPhaseProperties
)
from src.thermo_agents.filtering import (
    FilterPipelineBuilder,
    PhaseSegmentBuildingStage,
    PhaseSegmentBuilder,
    RecordSelector,
    PhaseResolver
)


class TestStage2PhaseSegments:
    """Integration tests for Stage 2 phase segment functionality."""

    @pytest.fixture
    def feo_records(self):
        """Create realistic FeO records for testing."""
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
                phase="s",
                tmin=900.0,
                tmax=1300.0,
                h298=-265.053,
                s298=59.807,
                f1=50.5,
                f2=14.8,
                f3=-2.2,
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
                id=5,
                formula="FeO",
                phase="g",
                tmin=400.0,
                tmax=2100.0,
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
        """Create realistic H2O records for testing."""
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

    def test_filter_pipeline_with_stage_2_feo(self, feo_records):
        """Test complete FilterPipeline with Stage 2 for FeO."""
        # Create pipeline with Stage 2
        pipeline = (FilterPipelineBuilder()
                    .with_deduplication()
                    .with_temperature_filter()
                    .with_phase_segment_building()  # Stage 2
                    .build())

        # Create Stage 1 context (enhanced temperature range)
        context = pipeline.create_stage1_context(
            compound_formula="FeO",
            user_temperature_range=(773.0, 973.0),  # Original user request
            full_calculation_range=(298.0, 5000.0)  # Stage 1 enhanced range
        )

        # Execute pipeline
        result = pipeline.execute(feo_records, context)

        # Verify pipeline execution
        assert result.is_found
        assert result.total_filtered > 0

        # Verify Stage 2 processing
        assert context.additional_params is not None
        assert context.additional_params.get("stage2_processed", False)

        # Get multi-phase properties
        multi_phase_props = context.additional_params.get("multi_phase_properties")
        assert multi_phase_props is not None
        assert isinstance(multi_phase_props, MultiPhaseProperties)

        # Verify FeO specific behavior
        assert len(multi_phase_props.segments) >= 2  # Should have solid and at least one other phase
        assert len(multi_phase_props.phase_transitions) >= 1  # Should have transitions

        # Check phase sequence
        phase_sequence = multi_phase_props.phase_sequence
        assert 's' in phase_sequence  # Solid phase should be present
        assert 'l' in phase_sequence or 'g' in phase_sequence  # At least one other phase

    def test_filter_pipeline_stage_2_water(self, water_records):
        """Test FilterPipeline with Stage 2 for H2O."""
        pipeline = (FilterPipelineBuilder()
                    .with_deduplication()
                    .with_temperature_filter()
                    .with_phase_segment_building()
                    .build())

        context = pipeline.create_stage1_context(
            compound_formula="H2O",
            user_temperature_range=(298.0, 350.0),
            full_calculation_range=(250.0, 500.0)
        )

        result = pipeline.execute(water_records, context)

        assert result.is_found
        assert context.additional_params.get("stage2_processed", False)

        multi_phase_props = context.additional_params.get("multi_phase_properties")
        assert multi_phase_props is not None

        # Water should have all three phases in the range
        phases = multi_phase_props.phase_sequence
        assert 's' in phases
        assert 'l' in phases
        assert 'g' in phases

        # Should have melting and boiling transitions
        transitions = multi_phase_props.phase_transitions
        assert len(transitions) >= 2

    def test_stage_2_with_phase_resolver_integration(self, feo_records):
        """Test integration between Stage 2 and PhaseResolver."""
        # Create components
        segment_builder = PhaseSegmentBuilder()
        phase_resolver = PhaseResolver()

        # Build segments
        multi_phase_props = segment_builder.build_phase_segments(
            records=feo_records,
            temperature_range=(298.0, 5000.0),
            compound_formula="FeO"
        )

        # Test PhaseResolver enhanced methods
        test_temperatures = [500.0, 1500.0, 2000.0, 4000.0]

        for temp in test_temperatures:
            try:
                phase, segment = phase_resolver.resolve_phase_at_temperature(
                    multi_phase_props, temp
                )
                assert phase in ['s', 'l', 'g']
                assert segment is not None
                assert segment.T_start <= temp <= segment.T_end

                # Test getting active record
                active_record = phase_resolver.get_active_record(segment, temp)
                assert active_record is not None
                assert active_record.covers_temperature(temp)

            except ValueError:
                # Temperature might not be covered - this is expected for some temps
                pass

        # Test phase sequence
        phase_sequence = phase_resolver.get_phase_sequence(multi_phase_props)
        assert len(phase_sequence) >= 2
        assert all(phase in ['s', 'l', 'g'] for phase, _ in phase_sequence)

        # Test segment continuity validation
        validation = phase_resolver.validate_segment_continuity(multi_phase_props)
        assert isinstance(validation, dict)
        assert "is_continuous" in validation
        assert "issues" in validation
        assert "recommendations" in validation

    def test_stage_2_statistics_and_logging(self, feo_records):
        """Test Stage 2 statistics and logging functionality."""
        stage = PhaseSegmentBuildingStage()

        # Create context
        context = FilterContext(
            temperature_range=(298.0, 5000.0),
            compound_formula="FeO",
            stage1_mode=True,
            original_user_range=(773.0, 973.0),
            full_calculation_range=(298.0, 5000.0)
        )

        # Execute stage
        result_records = stage.filter(feo_records, context)

        # Verify statistics
        stats = stage.get_statistics()
        assert stats["records_input"] == len(feo_records)
        assert stats["records_output"] == len(feo_records)  # Unchanged for compatibility
        assert stats["segments_created"] > 0
        assert stats["stage_name"] == "Построение фазовых сегментов (Stage 2)"
        assert stats["stage2_enabled"] == True

        # Verify multi-phase properties extraction
        multi_phase_props = stage.get_multi_phase_properties(context)
        assert multi_phase_props is not None
        assert isinstance(multi_phase_props, MultiPhaseProperties)

        # Verify segment analysis
        analysis = stage.get_segment_analysis(context)
        assert analysis["total_segments"] > 0
        assert "phase_transitions" in analysis
        assert "warnings" in analysis
        assert "phase_sequence" in analysis

        # Verify Stage 2 processing flag
        assert stage.is_stage2_processed(context)

    def test_stage_2_backward_compatibility(self, feo_records):
        """Test that Stage 2 maintains backward compatibility."""
        # Create pipeline without Stage 2
        old_pipeline = (FilterPipelineBuilder()
                       .with_deduplication()
                       .with_temperature_filter()
                       .build())

        # Create pipeline with Stage 2
        new_pipeline = (FilterPipelineBuilder()
                       .with_deduplication()
                       .with_temperature_filter()
                       .with_phase_segment_building()
                       .build())

        # Same context for both
        context = FilterContext(
            temperature_range=(500.0, 800.0),
            compound_formula="FeO"
        )

        # Execute both pipelines
        old_result = old_pipeline.execute(feo_records, context)
        new_result = new_pipeline.execute(feo_records, context)

        # Both should succeed
        assert old_result.is_found
        assert new_result.is_found

        # New pipeline should return same records for compatibility
        assert len(new_result.filtered_records) == len(old_result.filtered_records)

        # But new pipeline should have additional Stage 2 data
        assert new_pipeline.context.additional_params is not None
        assert new_pipeline.context.additional_params.get("stage2_processed", False)

    def test_stage_2_error_handling(self, feo_records):
        """Test Stage 2 error handling and fallback."""
        stage = PhaseSegmentBuildingStage()

        # Create context that will cause issues
        context = FilterContext(
            temperature_range=(5000.0, 10000.0),  # Very high temperature
            compound_formula="FeO"
        )

        # Should still succeed with fallback
        result_records = stage.filter(feo_records, context)

        assert len(result_records) == len(feo_records)  # Records unchanged

        # Should have fallback properties
        multi_phase_props = stage.get_multi_phase_properties(context)
        assert multi_phase_props is not None
        assert len(multi_phase_props.warnings) > 0
        assert any("fallback" in warning.lower() for warning in multi_phase_props.warnings)

    def test_stage_2_with_empty_records(self):
        """Test Stage 2 behavior with empty records."""
        stage = PhaseSegmentBuildingStage()

        context = FilterContext(
            temperature_range=(298.0, 1000.0),
            compound_formula="FeO"
        )

        # Should handle empty records gracefully
        result_records = stage.filter([], context)

        assert len(result_records) == 0

        # Should not create multi-phase properties
        multi_phase_props = stage.get_multi_phase_properties(context)
        assert multi_phase_props is None

    def test_stage_2_optimization_feature(self, feo_records):
        """Test Stage 2 optimization feature."""
        # Create stage with optimization enabled
        stage_with_optimization = PhaseSegmentBuildingStage(enable_optimization=True)

        # Create stage with optimization disabled
        stage_without_optimization = PhaseSegmentBuildingStage(enable_optimization=False)

        context = FilterContext(
            temperature_range=(298.0, 5000.0),
            compound_formula="FeO"
        )

        # Execute both stages
        result_with_opt = stage_with_optimization.filter(feo_records, context)
        result_without_opt = stage_without_optimization.filter(feo_records, context)

        # Both should succeed
        assert len(result_with_opt) == len(feo_records)
        assert len(result_without_opt) == len(feo_records)

        # Optimization should improve record selection
        props_with_opt = stage_with_optimization.get_multi_phase_properties(context)
        props_without_opt = stage_without_optimization.get_multi_phase_properties(context)

        # Optimized version should have better record assignments
        assert props_with_opt is not None
        assert props_without_opt is not None

        # Count segments with records
        opt_segments_with_records = sum(1 for s in props_with_opt.segments if s.record)
        no_opt_segments_with_records = sum(1 for s in props_without_opt.segments if s.record)

        # Optimization should result in equal or better record assignment
        assert opt_segments_with_records >= no_opt_segments_with_records

    def test_stage_2_integration_with_real_data_flow(self, feo_records):
        """Test Stage 2 in realistic data flow scenario."""
        # Simulate realistic scenario: user wants calculations in 773-973K range
        user_request_range = (773.0, 973.0)
        full_calculation_range = (298.0, 5000.0)  # Stage 1 expanded range

        # Create complete pipeline
        pipeline = (FilterPipelineBuilder()
                    .with_deduplication()
                    .with_temperature_filter()
                    .with_phase_segment_building()
                    .with_phase_selection(PhaseResolver())
                    .with_reliability_priority()
                    .build())

        # Create Stage 1 context
        context = pipeline.create_stage1_context(
            compound_formula="FeO",
            user_temperature_range=user_request_range,
            full_calculation_range=full_calculation_range
        )

        # Execute pipeline
        result = pipeline.execute(feo_records, context)

        # Verify execution
        assert result.is_found
        assert len(result.filtered_records) > 0

        # Verify Stage 1 range expansion worked
        assert context.stage1_mode
        assert context.full_calculation_range == full_calculation_range
        assert context.original_user_range == user_request_range

        # Verify Stage 2 processing
        assert context.additional_params.get("stage2_processed", False)

        # Get final multi-phase properties
        multi_phase_props = context.additional_params.get("multi_phase_properties")
        assert multi_phase_props is not None

        # Verify that original user range is covered
        user_start, user_end = user_request_range
        assert any(
            seg.T_start <= user_start and seg.T_end >= user_end
            or (seg.T_start <= user_start <= seg.T_end)
            or (seg.T_start <= user_end <= seg.T_end)
            for seg in multi_phase_props.segments
        )

        # Verify enhanced temperature range benefits
        segment_analysis = context.additional_params.get("segment_analysis", {})
        assert segment_analysis["total_segments"] > 1  # Should have multiple segments
        assert segment_analysis["phase_transitions"] > 0  # Should have transitions

        # Should provide better data than original range
        original_range_records = [r for r in feo_records
                                 if r.tmin <= user_end and r.tmax >= user_start]
        assert len(result.filtered_records) >= len(original_range_records)

        print(f"Stage 2 Integration Test Results:")
        print(f"  User range: {user_request_range[0]:.0f}-{user_request_range[1]:.0f}K")
        print(f"  Full range: {full_calculation_range[0]:.0f}-{full_calculation_range[1]:.0f}K")
        print(f"  Segments created: {segment_analysis['total_segments']}")
        print(f"  Phase transitions: {segment_analysis['phase_transitions']}")
        print(f"  Phase sequence: {segment_analysis['phase_sequence']}")
        print(f"  Records processed: {len(result.filtered_records)}")