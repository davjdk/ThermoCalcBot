"""
Phase Segment Filter Stage

This module implements the PhaseSegmentStage which integrates
phase segment building into the FilterPipeline for multi-phase
thermodynamic calculations.

Key features:
- Integrates PhaseSegmentBuilder into FilterPipeline
- Builds phase segments from filtered records
- Handles multi-phase scenarios with transitions
- Preserves backward compatibility with existing pipeline
- Provides detailed statistics and logging

Technical description:
PhaseSegmentStage реализует интеграцию PhaseSegmentBuilder в конвейер
фильтрации для многофазных термодинамических расчётов.

Стадия выполняет следующие функции:
1. Получает отфильтрованные записи от предыдущих стадий
2. Использует PhaseSegmentBuilder для построения фазовых сегментов
3. Создаёт MultiPhaseProperties с сегментами и переходами
4. Сохраняет результаты в контексте для последующих стадий
5. Предоставляет детальную статистику и логирование

Интеграция в FilterPipeline:
- Добавляется после температурной фильтрации
- Работает с расширенным температурным диапазоном
- Сохраняет MultiPhaseProperties в context.additional_params
- Обеспечивает совместимость с существующими стадиями

Пример использования:
    # Создание конвейера с новой стадией
    pipeline = (FilterPipelineBuilder()
                .with_deduplication()
                .with_temperature_filter()
                .with_phase_segment_building()  # Новая стадия
                .with_phase_selection()
                .with_reliability_priority()
                .build())

    # Выполнение с контекстом
    context = FilterContext(
        compound_formula="FeO",
        temperature_range=(773, 973),
        full_calculation_range=(298, 5000)  # Расширенный диапазон
    )

    result = pipeline.execute(records, context)

    # Получение многофазных свойств
    multi_phase_props = context.additional_params.get("multi_phase_properties")
"""

import time
from typing import Any, Dict, List, Optional

from ..models.search import DatabaseRecord, MultiPhaseProperties
from .filter_pipeline import FilterContext, FilterStage
from .phase_segment_builder import PhaseSegmentBuilder
from .record_selector import RecordSelector
from .constants import (
    MIN_TEMPERATURE_COVERAGE_RATIO,
)


class PhaseSegmentStage(FilterStage):
    """
    Filter stage for building phase segments from database records.

    This stage integrates PhaseSegmentBuilder into the FilterPipeline and creates
    MultiPhaseProperties for subsequent thermodynamic calculations.
    """

    def __init__(
        self,
        phase_segment_builder: Optional[PhaseSegmentBuilder] = None,
        record_selector: Optional[RecordSelector] = None,
        enable_optimization: bool = True
    ):
        """
        Initialize the phase segment building stage.

        Args:
            phase_segment_builder: Optional custom PhaseSegmentBuilder
            record_selector: Optional custom RecordSelector
            enable_optimization: Whether to enable segment optimization
        """
        super().__init__()
        self.phase_segment_builder = phase_segment_builder or PhaseSegmentBuilder()
        self.record_selector = record_selector or RecordSelector()
        self.enable_optimization = enable_optimization

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Build phase segments from filtered records.

        This method performs the core logic:
        1. Extract temperature range from context
        2. Build phase segments using PhaseSegmentBuilder
        3. Optimize record selection if enabled
        4. Store MultiPhaseProperties in context
        5. Return original records for compatibility

        Args:
            records: Filtered database records from previous stages
            context: Filter context with temperature range and parameters

        Returns:
            Original records (unchanged for compatibility)
        """
        start_time = time.time()

        if not records:
            self._update_stats([], context, 0.0)
            return records

        # Extract temperature range
        temperature_range = context.effective_temperature_range
        compound_formula = context.compound_formula

        self.logger.info(f"🔄 Построение фазовых сегментов для {compound_formula}")
        self.logger.info(f"   Температурный диапазон: {temperature_range[0]:.0f}-{temperature_range[1]:.0f}K")
        self.logger.info(f"   Входные записи: {len(records)}")

        # Step 1: Build phase segments
        try:
            multi_phase_properties = self.phase_segment_builder.build_phase_segments(
                records=records,
                temperature_range=temperature_range,
                compound_formula=compound_formula
            )

            self.logger.info(f"   Создано сегментов: {len(multi_phase_properties.segments)}")
            self.logger.info(f"   Найдено переходов: {len(multi_phase_properties.phase_transitions)}")

        except Exception as e:
            self.logger.error(f"Ошибка построения фазовых сегментов: {e}")
            # Create minimal properties for fallback
            multi_phase_properties = self._create_fallback_properties(
                records, temperature_range, compound_formula
            )

        # Step 2: Optimize record selection if enabled
        if self.enable_optimization:
            self._optimize_record_selection(multi_phase_properties, records, temperature_range)

        # Step 3: Store results in context for subsequent stages
        context.additional_params = context.additional_params or {}
        context.additional_params["multi_phase_properties"] = multi_phase_properties
        context.additional_params["phase_segments_processed"] = True
        context.additional_params["segment_analysis"] = {
            "total_segments": len(multi_phase_properties.segments),
            "phase_transitions": len(multi_phase_properties.phase_transitions),
            "warnings": multi_phase_properties.warnings,
            "phase_sequence": multi_phase_properties.phase_sequence
        }

        # Step 4: Update statistics
        execution_time = (time.time() - start_time) * 1000
        self._update_stats(records, context, execution_time)

        # Step 5: Log completion
        self._log_completion(multi_phase_properties, execution_time)

        # Return original records for compatibility with existing pipeline
        return records

    def _create_fallback_properties(
        self,
        records: List[DatabaseRecord],
        temperature_range: tuple,
        compound_formula: str
    ) -> MultiPhaseProperties:
        """
        Create fallback MultiPhaseProperties when segment building fails.

        Args:
            records: Available records
            temperature_range: Temperature range
            compound_formula: Compound formula

        Returns:
            Minimal MultiPhaseProperties for fallback
        """
        self.logger.warning("Создание fallback свойств из-за ошибки построения сегментов")

        T_target = (temperature_range[0] + temperature_range[1]) / 2

        # Find best record for target temperature
        selection = self.record_selector.select_record_for_temperature(records, T_target)

        return MultiPhaseProperties(
            T_target=T_target,
            H_final=selection.selected_record.h298,
            S_final=selection.selected_record.s298,
            G_final=0.0,  # Will be calculated
            Cp_final=0.0,  # Will be calculated
            segments=[],  # No segments available
            phase_transitions=[],
            temperature_path=[T_target],
            H_path=[selection.selected_record.h298],
            S_path=[selection.selected_record.s298],
            warnings=["Fallback mode: segment building failed"] + selection.warnings
        )

    def _optimize_record_selection(
        self,
        multi_phase_properties: MultiPhaseProperties,
        original_records: List[DatabaseRecord],
        temperature_range: tuple
    ) -> None:
        """
        Optimize record selection for each segment.

        Args:
            multi_phase_properties: Multi-phase properties to optimize
            original_records: Original available records
            temperature_range: Temperature range
        """
        if not multi_phase_properties.segments:
            return

        optimized_segments = []

        for segment in multi_phase_properties.segments:
            # Find optimal record for segment temperature range
            segment_mid = (segment.T_start + segment.T_end) / 2

            try:
                selection = self.record_selector.select_record_for_temperature(
                    original_records, segment_mid
                )

                # Update segment with optimal record
                segment.record = selection.selected_record
                segment.H_start = selection.selected_record.h298
                segment.S_start = selection.selected_record.s298

                optimized_segments.append(segment)

                self.logger.debug(f"Оптимизирован сегмент {segment.T_start:.0f}-{segment.T_end:.0f}K: "
                                f"запись {selection.selected_record.id}, причина: {selection.selection_reason}")

            except Exception as e:
                self.logger.warning(f"Не удалось оптимизировать сегмент {segment.T_start:.0f}-{segment.T_end:.0f}K: {e}")
                optimized_segments.append(segment)  # Keep original

        # Update properties with optimized segments
        multi_phase_properties.segments = optimized_segments

    def _update_stats(
        self,
        records: List[DatabaseRecord],
        context: FilterContext,
        execution_time: float
    ) -> None:
        """
        Update stage statistics.

        Args:
            records: Processed records
            context: Filter context
            execution_time: Execution time in milliseconds
        """
        segment_analysis = context.additional_params.get("segment_analysis", {})

        self.last_stats = {
            "stage_name": self.get_stage_name(),
            "records_input": len(records),
            "records_output": len(records),  # Unchanged for compatibility
            "segments_created": segment_analysis.get("total_segments", 0),
            "transitions_found": segment_analysis.get("phase_transitions", 0),
            "warnings_count": len(segment_analysis.get("warnings", [])),
            "phase_sequence": segment_analysis.get("phase_sequence", "unknown"),
            "execution_time_ms": execution_time,
            "temperature_range": context.effective_temperature_range,
            "compound_formula": context.compound_formula,
            "phase_segments_enabled": context.additional_params.get("phase_segments_processed", False)
        }

    def _log_completion(
        self,
        multi_phase_properties: MultiPhaseProperties,
        execution_time: float
    ) -> None:
        """
        Log stage completion with detailed information.

        Args:
            multi_phase_properties: Resulting multi-phase properties
            execution_time: Execution time in milliseconds
        """
        self.logger.info(f"✅ Построение фазовых сегментов завершено за {execution_time:.1f}мс")

        # Log segment information
        if multi_phase_properties.segments:
            segments_info = []
            for segment in multi_phase_properties.segments:
                phase = segment.record.phase if segment.record else "unknown"
                segments_info.append(f"{phase}({segment.T_start:.0f}-{segment.T_end:.0f}K)")

            self.logger.info(f"   Фазовые сегменты: {' → '.join(segments_info)}")

        # Log transition information
        if multi_phase_properties.phase_transitions:
            transitions_info = []
            for transition in multi_phase_properties.phase_transitions:
                transitions_info.append(
                    f"{transition.from_phase}→{transition.to_phase} при {transition.temperature:.0f}K"
                )

            self.logger.info(f"   Фазовые переходы: {', '.join(transitions_info)}")

        # Log warnings
        if multi_phase_properties.warnings:
            self.logger.warning(f"   Предупреждения: {len(multi_phase_properties.warnings)}")
            for warning in multi_phase_properties.warnings[:3]:  # Log first 3 warnings
                self.logger.warning(f"     - {warning}")

    def get_stage_name(self) -> str:
        """Get the stage name for logging and statistics."""
        return "Построение фазовых сегментов"

    def get_multi_phase_properties(
        self,
        context: FilterContext
    ) -> Optional[MultiPhaseProperties]:
        """
        Extract MultiPhaseProperties from filter context.

        Args:
            context: Filter context with processing results

        Returns:
            MultiPhaseProperties if available, None otherwise
        """
        return context.additional_params.get("multi_phase_properties") if context.additional_params else None

    def is_phase_segments_processed(self, context: FilterContext) -> bool:
        """
        Check if phase segments processing was completed.

        Args:
            context: Filter context

        Returns:
            True if processing was completed, False otherwise
        """
        return bool(
            context.additional_params and
            context.additional_params.get("phase_segments_processed", False)
        )

    def get_segment_analysis(
        self,
        context: FilterContext
    ) -> Dict[str, Any]:
        """
        Get segment analysis from filter context.

        Args:
            context: Filter context

        Returns:
            Segment analysis dictionary
        """
        return (
            context.additional_params.get("segment_analysis", {})
            if context.additional_params
            else {}
        )


# Backward compatibility alias
PhaseSegmentBuildingStage = PhaseSegmentStage