"""
Модуль фильтрации термодинамических данных.

Реализует конвейерную систему фильтрации с детерминированной логикой:
- FilterPipeline: конвейер с возможностью добавления новых стадий
- TemperatureFilterStage: фильтрация по температурному диапазону
- PhaseSelectionStage: выбор правильной фазы с учётом переходов
- ReliabilityPriorityStage: приоритизация по надёжности данных
- ComplexFormulaSearchStage: комплексный поиск химических формул
- FormulaConsistencyStage: удаление дубликатов и проверка согласованности
- PhaseSegmentStage: построение фазовых сегментов
"""

from .filter_pipeline import FilterPipeline, FilterContext, FilterResult, FilterStage, FilterPipelineBuilder
from .filter_stages import (
    PhaseSelectionStage,
    ReliabilityPriorityStage
)
from .phase_resolver import PhaseResolver
from .phase_segment_builder import PhaseSegmentBuilder
from .record_selector import RecordSelector
from .phase_segment_stage import PhaseSegmentStage, PhaseSegmentBuildingStage  # Backward compatibility
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
    'PhaseSelectionStage',
    'ReliabilityPriorityStage',
    'PhaseResolver',
    'PhaseSegmentBuilder',
    'RecordSelector',
    'PhaseSegmentStage',
    'PhaseSegmentBuildingStage',  # Backward compatibility
    'ComplexFormulaSearchStage',
    'FormulaConsistencyStage'
]