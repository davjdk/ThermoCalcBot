"""
Модуль фильтрации термодинамических данных.

Реализует конвейерную систему фильтрации с детерминированной логикой:
- FilterPipeline: конвейер с возможностью добавления новых стадий
- TemperatureFilterStage: фильтрация по температурному диапазону
- PhaseSelectionStage: выбор правильной фазы с учётом переходов
- ReliabilityPriorityStage: приоритизация по надёжности данных
- ComplexFormulaSearchStage: комплексный поиск химических формул
- FormulaConsistencyStage: удаление дубликатов и проверка согласованности
- PhaseSegmentBuildingStage: построение фазовых сегментов (Stage 2)
"""

from .filter_pipeline import FilterPipeline, FilterContext, FilterResult, FilterStage, FilterPipelineBuilder
from .filter_stages import (
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage
)
from .temperature_resolver import TemperatureResolver
from .phase_resolver import PhaseResolver
from .temperature_range_resolver import TemperatureRangeResolver  # Stage 1
from .phase_segment_builder import PhaseSegmentBuilder  # Stage 2
from .record_selector import RecordSelector  # Stage 2
from .stage_02_phase_segments import PhaseSegmentBuildingStage  # Stage 2
from .complex_search_stage import (
    ComplexFormulaSearchStage,
    FormulaConsistencyStage
)

__all__ = [
    'FilterPipeline',
    'FilterContext',
    'FilterResult',
    'FilterStage',
    'FilterPipelineBuilder',
    'TemperatureFilterStage',
    'PhaseSelectionStage',
    'ReliabilityPriorityStage',
    'TemperatureResolver',
    'PhaseResolver',
    'TemperatureRangeResolver',  # Stage 1
    'PhaseSegmentBuilder',      # Stage 2
    'RecordSelector',           # Stage 2
    'PhaseSegmentBuildingStage',# Stage 2
    'ComplexFormulaSearchStage',
    'FormulaConsistencyStage'
]