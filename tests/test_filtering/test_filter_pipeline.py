"""
Unit tests for FilterPipeline and related components.

Tests pipeline construction, stage execution, statistics collection,
and error handling functionality.
"""

import pytest
from typing import List, Optional

from thermo_agents.models.search import DatabaseRecord
from thermo_agents.filtering.filter_pipeline import (
    FilterPipeline, FilterContext, FilterResult, FilterStage, FilterPipelineBuilder
)
from thermo_agents.filtering.filter_stages import TemperatureFilterStage
from thermo_agents.filtering.temperature_resolver import TemperatureResolver


class MockFilterStage(FilterStage):
    """Mock filter stage for testing."""

    def __init__(self, name: str, should_fail: bool = False, return_count: Optional[int] = None):
        super().__init__()
        self.stage_name = name
        self.should_fail = should_fail
        self.return_count = return_count

    def filter(self, records: List[DatabaseRecord], context: FilterContext) -> List[DatabaseRecord]:
        """Mock filter implementation."""
        if self.should_fail:
            return []  # Simulate failure

        if self.return_count is not None:
            return records[:self.return_count]

        # Default: return all records
        return records.copy()

    def get_stage_name(self) -> str:
        return self.stage_name


class TestFilterContext:
    """Test cases for FilterContext class."""

    def test_valid_context_creation(self):
        """Test creating valid filter context."""
        context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="H2O",
            user_query="test query"
        )

        assert context.temperature_range == (300.0, 500.0)
        assert context.compound_formula == "H2O"
        assert context.user_query == "test query"
        assert context.additional_params == {}

    def test_context_validation_invalid_temperature_range(self):
        """Test context validation with invalid temperature range."""
        with pytest.raises(ValueError, match="Минимальная температура не может быть больше максимальной"):
            FilterContext(
                temperature_range=(500.0, 300.0),
                compound_formula="H2O"
            )

    def test_context_validation_empty_formula(self):
        """Test context validation with empty formula."""
        with pytest.raises(ValueError, match="Формула соединения не может быть пустой"):
            FilterContext(
                temperature_range=(300.0, 500.0),
                compound_formula=""
            )

        with pytest.raises(ValueError, match="Формула соединения не может быть пустой"):
            FilterContext(
                temperature_range=(300.0, 500.0),
                compound_formula=None
            )

    def test_additional_params_initialization(self):
        """Test additional params initialization."""
        context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="H2O",
            additional_params={"param1": "value1", "param2": 42}
        )

        assert context.additional_params == {"param1": "value1", "param2": 42}


class TestFilterResult:
    """Test cases for FilterResult class."""

    def test_successful_result(self):
        """Test successful filter result."""
        result = FilterResult(
            filtered_records=[1, 2, 3],
            stage_statistics=[{"stage": 1}, {"stage": 2}],
            is_found=True
        )

        assert result.total_filtered == 3
        assert result.successful_stages == 2
        assert result.failure_stage is None
        assert result.failure_reason is None

    def test_failed_result(self):
        """Test failed filter result."""
        result = FilterResult(
            filtered_records=[],
            stage_statistics=[{"stage": 1}],
            is_found=False,
            failure_stage=2,
            failure_reason="No records after filtering"
        )

        assert result.total_filtered == 0
        assert result.successful_stages == 1
        assert result.failure_stage == 2
        assert result.failure_reason == "No records after filtering"


class TestFilterPipeline:
    """Test cases for FilterPipeline class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.pipeline = FilterPipeline()
        self.context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="H2O"
        )
        self.test_records = [
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
            )
        ]

    def test_empty_pipeline_creation(self):
        """Test creating empty pipeline."""
        assert len(self.pipeline.stages) == 0
        assert len(self.pipeline.statistics) == 0
        assert self.pipeline.get_stage_names() == []

    def test_add_stage(self):
        """Test adding stages to pipeline."""
        stage1 = MockFilterStage("Stage1")
        stage2 = MockFilterStage("Stage2")

        # Test fluent API
        result = self.pipeline.add_stage(stage1).add_stage(stage2)

        assert result is self.pipeline  # Should return self for fluent API
        assert len(self.pipeline.stages) == 2
        assert self.pipeline.get_stage_names() == ["Stage1", "Stage2"]

    def test_add_invalid_stage(self):
        """Test adding invalid stage to pipeline."""
        with pytest.raises(TypeError, match="Стадия должна наследоваться от FilterStage"):
            self.pipeline.add_stage("not a stage")

    def test_clear_stages(self):
        """Test clearing all stages from pipeline."""
        stage = MockFilterStage("TestStage")
        self.pipeline.add_stage(stage)

        assert len(self.pipeline.stages) == 1

        # Test fluent API
        result = self.pipeline.clear_stages()

        assert result is self.pipeline
        assert len(self.pipeline.stages) == 0

    def test_execute_successful_pipeline(self):
        """Test successful pipeline execution."""
        stage1 = MockFilterStage("Stage1")
        stage2 = MockFilterStage("Stage2", return_count=1)

        self.pipeline.add_stage(stage1).add_stage(stage2)

        result = self.pipeline.execute(self.test_records, self.context)

        assert result.is_found == True
        assert len(result.filtered_records) == 1
        assert len(result.stage_statistics) == 3  # Initial + 2 stages
        assert result.failure_stage is None
        assert result.failure_reason is None

    def test_execute_pipeline_with_failure(self):
        """Test pipeline execution with stage failure."""
        stage1 = MockFilterStage("Stage1")
        stage2 = MockFilterStage("Stage2", should_fail=True)
        stage3 = MockFilterStage("Stage3")  # Should not be executed

        self.pipeline.add_stage(stage1).add_stage(stage2).add_stage(stage3)

        result = self.pipeline.execute(self.test_records, self.context)

        assert result.is_found == False
        assert len(result.filtered_records) == 0
        assert len(result.stage_statistics) == 2  # Initial + 1 stage (failure)
        assert result.failure_stage == 2
        assert "Stage2" in result.failure_reason

    def test_execute_pipeline_statistics(self):
        """Test statistics collection during pipeline execution."""
        stage = MockFilterStage("TestStage")
        self.pipeline.add_stage(stage)

        result = self.pipeline.execute(self.test_records, self.context)

        # Check initial statistics
        initial_stats = result.stage_statistics[0]
        assert initial_stats['stage_number'] == 0
        assert initial_stats['stage_name'] == 'Начальные данные'
        assert initial_stats['records_before'] == 2
        assert initial_stats['records_after'] == 2
        assert initial_stats['reduction_rate'] == 0.0

        # Check stage statistics
        stage_stats = result.stage_statistics[1]
        assert stage_stats['stage_number'] == 1
        assert stage_stats['stage_name'] == 'TestStage'
        assert stage_stats['records_before'] == 2
        assert stage_stats['records_after'] == 2

        # Check final statistics
        final_stats = result.stage_statistics[2]
        assert final_stats['stage_number'] == 2
        assert final_stats['stage_name'] == 'Завершение'
        assert final_stats['records_before'] == 2
        assert final_stats['records_after'] == 2

    def test_execute_pipeline_timing(self):
        """Test execution time measurement."""
        stage = MockFilterStage("TestStage")
        self.pipeline.add_stage(stage)

        result = self.pipeline.execute(self.test_records, self.context)

        assert self.pipeline.get_last_execution_time_ms() is not None
        assert self.pipeline.get_last_execution_time_ms() >= 0

        # Check that timing is recorded in statistics
        final_stats = result.stage_statistics[-1]
        assert 'total_execution_time_ms' in final_stats
        assert final_stats['total_execution_time_ms'] >= 0

    def test_get_pipeline_summary(self):
        """Test pipeline summary information."""
        stage1 = MockFilterStage("Stage1")
        stage2 = MockFilterStage("Stage2")

        self.pipeline.add_stage(stage1).add_stage(stage2)

        summary = self.pipeline.get_pipeline_summary()

        assert summary['total_stages'] == 2
        assert summary['stage_names'] == ["Stage1", "Stage2"]
        assert summary['statistics_count'] == 0  # Before execution
        assert summary['last_execution_time_ms'] is None

        # Execute pipeline and check summary update
        self.pipeline.execute(self.test_records, self.context)

        summary = self.pipeline.get_pipeline_summary()
        assert summary['statistics_count'] > 0

    def test_pipeline_with_real_temperature_filter(self):
        """Test pipeline with real TemperatureFilterStage."""
        temp_resolver = TemperatureResolver()
        temp_stage = TemperatureFilterStage(temp_resolver)

        self.pipeline.add_stage(temp_stage)

        result = self.pipeline.execute(self.test_records, self.context)

        assert result.is_found == True
        # Both records should pass temperature filter (300-500K range)
        assert len(result.filtered_records) == 2

        # Check temperature-specific statistics
        stage_stats = result.stage_statistics[1]
        assert 'temperature_range' in stage_stats
        assert 'records_in_range' in stage_stats
        assert 'records_out_of_range' in stage_stats


class TestFilterPipelineBuilder:
    """Test cases for FilterPipelineBuilder class."""

    def test_builder_empty_pipeline(self):
        """Test building empty pipeline."""
        builder = FilterPipelineBuilder()
        pipeline = builder.build()

        assert isinstance(pipeline, FilterPipeline)
        assert len(pipeline.stages) == 0

    def test_builder_with_temperature_filter(self):
        """Test building pipeline with temperature filter."""
        builder = FilterPipelineBuilder()
        pipeline = builder.with_temperature_filter().build()

        assert len(pipeline.stages) == 1
        assert isinstance(pipeline.stages[0], TemperatureFilterStage)

    def test_builder_with_multiple_stages(self):
        """Test building pipeline with multiple stages."""
        from thermo_agents.filtering.filter_stages import ReliabilityPriorityStage
        from thermo_agents.filtering.phase_resolver import PhaseResolver

        temp_resolver = TemperatureResolver()
        phase_resolver = PhaseResolver()

        builder = FilterPipelineBuilder()
        pipeline = (builder
                   .with_temperature_filter()
                   .with_phase_selection(phase_resolver)
                   .with_reliability_priority(max_records=1)
                   .build())

        assert len(pipeline.stages) == 3
        assert pipeline.stages[0].get_stage_name() == "Температурная фильтрация"
        assert pipeline.stages[1].get_stage_name() == "Фазовая фильтрация"
        assert pipeline.stages[2].get_stage_name() == "Приоритизация по надёжности"

    def test_builder_fluent_api(self):
        """Test builder fluent API chaining."""
        builder = FilterPipelineBuilder()

        # All methods should return the builder for chaining
        result1 = builder.with_temperature_filter()
        assert result1 is builder

        result2 = result1.with_temperature_filter()
        assert result2 is builder

        pipeline = result2.build()
        assert len(pipeline.stages) == 2

    def test_builder_execution(self):
        """Test executing pipeline built with builder."""
        test_records = [
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
            )
        ]

        context = FilterContext(temperature_range=(300.0, 500.0), compound_formula="H2O")

        builder = FilterPipelineBuilder()
        pipeline = (builder
                   .with_temperature_filter()
                   .with_reliability_priority(max_records=1)
                   .build())

        result = pipeline.execute(test_records, context)

        assert result.is_found == True
        assert len(result.filtered_records) == 1