"""
Модуль фильтрации термодинамических данных.

Реализует конвейерную систему фильтрации с детерминированной логикой:
- FilterPipeline: конвейер с возможностью добавления новых стадий
- TemperatureFilterStage: фильтрация по температурному диапазону
- PhaseSelectionStage: выбор правильной фазы с учётом переходов
- ReliabilityPriorityStage: приоритизация по надёжности данных
- ComplexFormulaSearchStage: комплексный поиск химических формул
- FormulaConsistencyStage: удаление дубликатов и проверка согласованности
"""

from .filter_pipeline import FilterPipeline, FilterContext, FilterResult, FilterStage, FilterPipelineBuilder
from .filter_stages import (
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage
)
from .temperature_resolver import TemperatureResolver
from .phase_resolver import PhaseResolver
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
    'ComplexFormulaSearchStage',
    'FormulaConsistencyStage'
]