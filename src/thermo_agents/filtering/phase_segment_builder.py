"""
Phase Segment Builder for Multi-phase Logic (Stage 2)

This module implements the PhaseSegmentBuilder component that creates
phase segments from database records for multi-phase thermodynamic calculations.

Key features:
- Builds phase segments based on temperature ranges and phase transitions
- Handles solid→liquid→gas phase transitions
- Optimizes record assignment within segments
- Validates segment continuity and coverage
- Supports complex multi-compound scenarios

Technical description:
PhaseSegmentBuilder реализует логику построения фазовых сегментов для многофазных
термодинамических расчётов в соответствии с требованиями Этапа 2.

Основная задача — разбить все найденные записи вещества на фазовые сегменты
на основе температур плавления и кипения, обеспечив бесшовные переходы между
фазами и оптимальное использование доступных данных.

Ключевая логика:
1. Извлечь температуры переходов (tmelt, tboil) из записей
2. Создать фазовые сегменты: [start, tmelt)s, [tmelt, tboil)l, [tboil, end]g
3. Распределить записи по соответствующим сегментам
4. Оптимизировать выбор записей в каждом сегменте
5. Провести валидацию непрерывности и покрытия

Пример использования:
    builder = PhaseSegmentBuilder()

    # Для FeO с 6 записями
    segments_data = builder.build_phase_segments(
        records=feo_records,           # 6 записей: 3(s), 1(l), 2(g)
        temperature_range=(298, 5000)  # Полный диапазон расчёта
    )

    # Результат:
    # - Сегмент 1: [298-1650)K, фаза s, 3 записи
    # - Переход: плавление при 1650K, ΔH = 31.5 кДж/моль
    # - Сегмент 2: [1650-3687)K, фаза l, 1 запись
    # - Переход: кипение при 3687K, ΔH = 340.0 кДж/моль
    # - Сегмент 3: [3687-5000]K, фаза g, 2 записи

Валидация:
- Проверка непрерывности температурного покрытия
- Валидация фазовых переходов
- Анализ пробелов и перекрытий в данных
- Генерация предупреждений о проблемных участках
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime

from ..models.search import (
    DatabaseRecord,
    PhaseSegment,
    PhaseTransition,
    MultiPhaseProperties,
    TransitionType
)
from .constants import (
    MIN_TEMPERATURE_K,
    MAX_TEMPERATURE_K,
    TEMPERATURE_EXTENSION_MARGIN,
)

logger = logging.getLogger(__name__)


@dataclass
class SegmentAnalysis:
    """Analysis result for phase segment building."""

    total_segments: int
    phase_transitions: List[PhaseTransition]
    coverage_gaps: List[Tuple[float, float]]
    coverage_overlaps: List[Tuple[float, float]]
    optimized_segments: List[PhaseSegment]
    warnings: List[str]
    analysis_timestamp: datetime


class PhaseSegmentBuilder:
    """
    Phase segment builder for multi-phase calculations (Stage 2).

    This component implements the core logic for creating phase segments
    from database records, handling phase transitions, and optimizing
    record assignment within segments.
    """

    def __init__(self):
        """Initialize the phase segment builder."""
        self._analysis_cache = {}
        logger.info("PhaseSegmentBuilder initialized for Stage 2 implementation")

    def build_phase_segments(
        self,
        records: List[DatabaseRecord],
        temperature_range: Tuple[float, float],
        compound_formula: Optional[str] = None
    ) -> MultiPhaseProperties:
        """
        Build phase segments from database records.

        Args:
            records: List of database records for the compound
            temperature_range: Temperature range for calculations (Tmin, Tmax)
            compound_formula: Optional compound formula for logging

        Returns:
            MultiPhaseProperties with segments and transitions

        Raises:
            ValueError: If records are empty or invalid
        """
        if not records:
            raise ValueError("No records provided for segment building")

        if len(temperature_range) != 2 or temperature_range[0] >= temperature_range[1]:
            raise ValueError(f"Invalid temperature range: {temperature_range}")

        compound_name = compound_formula or records[0].formula
        logger.info(f"Building phase segments for {compound_name} from {len(records)} records")
        logger.info(f"Temperature range: {temperature_range[0]:.1f}-{temperature_range[1]:.1f}K")

        # Шаг 1: Извлечь температуры переходов
        tmelt, tboil = self._extract_transition_temperatures(records)
        logger.info(f"Transition temperatures: Tmelt={tmelt}K, Tboil={tboil}K")

        # Шаг 2: Создать фазовые сегменты
        segments = self._create_phase_segments(records, temperature_range, tmelt, tboil)
        logger.info(f"Created {len(segments)} phase segments")

        # Шаг 3: Распределить записи по сегментам
        self._assign_records_to_segments(records, segments)

        # Шаг 4: Оптимизировать сегменты
        self._optimize_segments_coverage(segments)

        # Шаг 5: Определить фазовые переходы
        transitions = self._identify_phase_transitions(segments, tmelt, tboil)
        logger.info(f"Identified {len(transitions)} phase transitions")

        # Шаг 6: Валидация и анализ
        analysis = self._analyze_segments(segments, temperature_range)
        if analysis.warnings:
            logger.warning(f"Segment analysis warnings: {analysis.warnings}")

        # Шаг 7: Создать результат
        return self._create_multi_phase_properties(
            segments=segments,
            transitions=transitions,
            temperature_range=temperature_range,
            compound_formula=compound_name,
            analysis=analysis
        )

    def _extract_transition_temperatures(
        self,
        records: List[DatabaseRecord]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract phase transition temperatures from records.

        Args:
            records: Database records

        Returns:
            Tuple of (tmelt, tboil) temperatures
        """
        if not records:
            return None, None

        # According to database analysis, MeltingPoint and BoilingPoint
        # are 100% populated, so we can use them directly
        tmelt_values = [r.tmelt for r in records if r.tmelt and r.tmelt > 0]
        tboil_values = [r.tboil for r in records if r.tboil and r.tboil > 0]

        # Use most common values (should be consistent)
        tmelt = max(set(tmelt_values), key=tmelt_values.count) if tmelt_values else None
        tboil = max(set(tboil_values), key=tboil_values.count) if tboil_values else None

        # Validate transition temperatures
        if tmelt and tboil and tmelt >= tboil:
            logger.warning(f"Invalid transition temperatures: Tmelt ({tmelt}K) >= Tboil ({tboil}K)")
            # Use defaults based on typical values
            tmelt = min(tmelt, tboil - 100) if tmelt else None
            tboil = max(tboil, tmelt + 100) if tboil else None

        return tmelt, tboil

    def _create_phase_segments(
        self,
        records: List[DatabaseRecord],
        temperature_range: Tuple[float, float],
        tmelt: Optional[float],
        tboil: Optional[float]
    ) -> List[PhaseSegment]:
        """
        Create phase segments based on temperature range and transition temperatures.

        Args:
            records: Database records
            temperature_range: Overall temperature range (Tmin, Tmax)
            tmelt: Melting temperature
            tboil: Boiling temperature

        Returns:
            List of phase segments
        """
        segments = []
        t_start, t_end = temperature_range

        # Determine phase segments based on transition temperatures
        if tmelt and tboil and tmelt < tboil:
            # Complete transition information available
            # Create segments from appropriate records for each phase

            # Solid segment - find solid records
            solid_records = [r for r in records if r.phase == 's']
            if solid_records and t_start < tmelt:
                solid_end = min(tmelt, t_end)
                # Use the solid record with best coverage
                best_solid = max(solid_records, key=lambda r: max(0, min(r.tmax, solid_end) - max(r.tmin, t_start)))
                segments.append(PhaseSegment.from_database_record(best_solid))
                # Adjust segment temperature range
                segments[-1].T_start = t_start
                segments[-1].T_end = solid_end
                segments[-1].is_transition_boundary = (solid_end >= tmelt)

            # Liquid segment - find liquid records
            liquid_records = [r for r in records if r.phase == 'l']
            if liquid_records and t_end > tmelt and t_start < tboil:
                # Check for H298/S298 reference liquid record
                reference_liquid = next((r for r in liquid_records if r.is_h298_s298_reference), None)

                if reference_liquid:
                    # Use H298/S298 reference record with its full temperature range
                    liquid_start = max(reference_liquid.tmin, t_start)
                    liquid_end = min(reference_liquid.tmax, t_end)
                    if liquid_start < liquid_end:
                        liquid_segment = PhaseSegment.from_database_record(reference_liquid)
                        liquid_segment.T_start = liquid_start
                        liquid_segment.T_end = liquid_end
                        liquid_segment.is_transition_boundary = (liquid_end >= tboil)
                        segments.append(liquid_segment)
                else:
                    # Normal liquid segment creation
                    liquid_start = max(tmelt, t_start)
                    liquid_end = min(tboil, t_end)
                    if liquid_start < liquid_end:
                        best_liquid = liquid_records[0]  # Usually only one liquid record
                        liquid_segment = PhaseSegment.from_database_record(best_liquid)
                        liquid_segment.T_start = liquid_start
                        liquid_segment.T_end = liquid_end
                        liquid_segment.is_transition_boundary = (liquid_end >= tboil)
                        segments.append(liquid_segment)

            # Gas segment - find gas records
            gas_records = [r for r in records if r.phase == 'g']
            if gas_records and t_end > tboil:
                gas_start = max(tboil, t_start)
                if gas_start < t_end:
                    # Use the gas record with best coverage
                    best_gas = max(gas_records, key=lambda r: max(0, min(r.tmax, t_end) - max(r.tmin, gas_start)))
                    gas_segment = PhaseSegment.from_database_record(best_gas)
                    gas_segment.T_start = gas_start
                    gas_segment.T_end = t_end
                    gas_segment.is_transition_boundary = False
                    segments.append(gas_segment)

        else:
            # Partial or no transition information
            # Create segment from the best available record
            if records:
                best_record = max(records, key=lambda r: r.tmax - r.tmin)
                segment = PhaseSegment.from_database_record(best_record)
                segment.T_start = t_start
                segment.T_end = t_end
                segment.is_transition_boundary = False
                segments.append(segment)

        logger.info(f"Created {len(segments)} phase segments")
        return segments

    def _assign_records_to_segments(
        self,
        records: List[DatabaseRecord],
        segments: List[PhaseSegment]
    ) -> None:
        """
        Assign database records to appropriate phase segments.

        Args:
            records: Database records to assign
            segments: Phase segments to assign records to
        """
        # Group records by phase
        records_by_phase = self._group_records_by_phase(records)

        # Assign records to segments based on phase compatibility
        for segment in segments:
            # Determine expected phase for segment
            expected_phase = self._determine_segment_phase(segment, records)

            # Find compatible records
            compatible_records = []

            # First, check for H298/S298 reference records for segments near 298K
            if abs(segment.T_start - 298.15) < 1.0:  # Segment starts near 298K
                reference_records = [r for r in records if r.is_h298_s298_reference]
                if reference_records:
                    compatible_records.extend(reference_records)

            # Then add phase-specific records
            if expected_phase in records_by_phase:
                compatible_records.extend(records_by_phase[expected_phase])
            else:
                # Fallback: find records that cover the segment temperature range
                coverage_records = [
                    r for r in records
                    if r.tmin <= segment.T_end and r.tmax >= segment.T_start
                ]
                compatible_records.extend(coverage_records)

            # Remove duplicates
            compatible_records = list({r.id: r for r in compatible_records if hasattr(r, 'id')}.values())

            # Sort by H298/S298 reference priority, then temperature coverage and reliability
            compatible_records.sort(key=lambda r: (
                -1000 if r.is_h298_s298_reference else 0,  # H298/S298 reference gets highest priority
                -(min(r.tmax, segment.T_end) - max(r.tmin, segment.T_start)),  # Coverage
                r.reliability_class if r.reliability_class else 999  # Reliability
            ))

            # Assign best record (if available)
            if compatible_records:
                segment.record = compatible_records[0]
                segment.H_start = compatible_records[0].h298
                segment.S_start = compatible_records[0].s298
                logger.debug(f"Assigned record {compatible_records[0].id} to segment {segment.T_start}-{segment.T_end}K")
            else:
                logger.warning(f"No compatible records found for segment {segment.T_start}-{segment.T_end}K")

    def _group_records_by_phase(self, records: List[DatabaseRecord]) -> Dict[str, List[DatabaseRecord]]:
        """
        Group records by their phase.

        Args:
            records: Database records

        Returns:
            Dictionary mapping phase to list of records
        """
        phase_groups = {}

        for record in records:
            phase = record.phase or 'unknown'
            if phase not in phase_groups:
                phase_groups[phase] = []
            phase_groups[phase].append(record)

        return phase_groups

    def _determine_segment_phase(
        self,
        segment: PhaseSegment,
        records: List[DatabaseRecord]
    ) -> str:
        """
        Determine the expected phase for a segment based on temperature.

        Args:
            segment: Phase segment
            records: Available records (for transition temperature info)

        Returns:
            Expected phase ('s', 'l', 'g', or 'unknown')
        """
        # Get transition temperatures from records
        tmelt, tboil = self._extract_transition_temperatures(records)

        if tmelt and tboil:
            # Use transition temperatures
            if segment.T_end <= tmelt:
                return 's'  # Solid
            elif segment.T_start >= tboil:
                return 'g'  # Gas
            elif segment.T_start < tboil and segment.T_end > tmelt:
                return 'l'  # Liquid

        # Use temperature-based heuristics
        T_mid = (segment.T_start + segment.T_end) / 2

        if T_mid < 500:
            return 's'  # Likely solid
        elif T_mid > 2000:
            return 'g'  # Likely gas
        else:
            return 'l'  # Likely liquid

    def _optimize_segments_coverage(self, segments: List[PhaseSegment]) -> None:
        """
        Optimize segment coverage and ensure continuity.

        Args:
            segments: Phase segments to optimize
        """
        # Sort segments by temperature
        segments.sort(key=lambda s: s.T_start)

        # Check for gaps and overlaps
        for i in range(len(segments) - 1):
            current = segments[i]
            next_segment = segments[i + 1]

            # Check for gaps
            if current.T_end < next_segment.T_start:
                gap_size = next_segment.T_start - current.T_end
                if gap_size > TEMPERATURE_EXTENSION_MARGIN:
                    logger.warning(f"Gap between segments: {gap_size:.1f}K from {current.T_end}K to {next_segment.T_start}K")

            # Check for overlaps
            elif current.T_end > next_segment.T_start:
                overlap_size = current.T_end - next_segment.T_start
                if overlap_size > TEMPERATURE_EXTENSION_MARGIN:
                    logger.warning(f"Overlap between segments: {overlap_size:.1f}K from {next_segment.T_start}K to {current.T_end}K")
                    # Adjust boundaries to remove overlap
                    mid_point = (current.T_end + next_segment.T_start) / 2
                    current.T_end = mid_point
                    next_segment.T_start = mid_point

    def _identify_phase_transitions(
        self,
        segments: List[PhaseSegment],
        tmelt: Optional[float],
        tboil: Optional[float]
    ) -> List[PhaseTransition]:
        """
        Identify phase transitions between segments.

        Args:
            segments: Phase segments
            tmelt: Melting temperature
            tboil: Boiling temperature

        Returns:
            List of phase transitions
        """
        transitions = []

        if not tmelt or not tboil:
            return transitions

        # Sort segments by temperature
        segments.sort(key=lambda s: s.T_start)

        for i in range(len(segments) - 1):
            current = segments[i]
            next_segment = segments[i + 1]

            # Check if there's a phase transition at the boundary
            if abs(current.T_end - next_segment.T_start) < TEMPERATURE_EXTENSION_MARGIN:
                # Determine phases
                current_phase = current.record.phase if current.record else 'unknown'
                next_phase = next_segment.record.phase if next_segment.record else 'unknown'

                if current_phase != next_phase:
                    # Determine transition type
                    transition_temp = (current.T_end + next_segment.T_start) / 2

                    if abs(transition_temp - tmelt) < TEMPERATURE_EXTENSION_MARGIN:
                        transition_type = TransitionType.MELTING
                        from_phase = 's'
                        to_phase = 'l'
                    elif abs(transition_temp - tboil) < TEMPERATURE_EXTENSION_MARGIN:
                        transition_type = TransitionType.BOILING
                        from_phase = 'l'
                        to_phase = 'g'
                    else:
                        # Determine from phases
                        transition_type = TransitionType.UNKNOWN
                        from_phase = current_phase
                        to_phase = next_phase

                    # Estimate enthalpy change (rough approximation)
                    delta_H = self._estimate_transition_enthalpy(from_phase, to_phase, transition_temp)
                    delta_S = delta_H * 1000 / transition_temp if transition_temp > 0 else 0  # J/(mol·K)

                    transition = PhaseTransition(
                        temperature=transition_temp,
                        from_phase=from_phase,
                        to_phase=to_phase,
                        transition_type=transition_type,
                        delta_H_transition=delta_H,  # kJ/mol
                        delta_S_transition=delta_S   # J/(mol·K)
                    )

                    transitions.append(transition)
                    logger.info(f"Identified transition: {from_phase}→{to_phase} at {transition_temp:.1f}K")

        return transitions

    def _estimate_transition_enthalpy(
        self,
        from_phase: str,
        to_phase: str,
        temperature: float
    ) -> float:
        """
        Estimate enthalpy change for phase transition.

        Args:
            from_phase: Source phase
            to_phase: Target phase
            temperature: Transition temperature

        Returns:
            Estimated enthalpy change in kJ/mol
        """
        # Rough approximations for common transitions
        if from_phase == 's' and to_phase == 'l':
            # Melting: typical range 5-50 kJ/mol
            return 25.0  # Average value
        elif from_phase == 'l' and to_phase == 'g':
            # Boiling: typical range 20-200 kJ/mol
            return 80.0  # Average value
        else:
            # Unknown transition: use small value
            return 10.0

    def _analyze_segments(
        self,
        segments: List[PhaseSegment],
        temperature_range: Tuple[float, float]
    ) -> SegmentAnalysis:
        """
        Analyze segments for coverage, gaps, and overlaps.

        Args:
            segments: Phase segments to analyze
            temperature_range: Expected temperature range

        Returns:
            Segment analysis result
        """
        warnings = []
        coverage_gaps = []
        coverage_overlaps = []

        if not segments:
            warnings.append("No segments created")
            return SegmentAnalysis(
                total_segments=0,
                phase_transitions=[],
                coverage_gaps=coverage_gaps,
                coverage_overlaps=coverage_overlaps,
                optimized_segments=[],
                warnings=warnings,
                analysis_timestamp=datetime.now()
            )

        # Sort segments by temperature
        sorted_segments = sorted(segments, key=lambda s: s.T_start)

        # Check coverage
        expected_start, expected_end = temperature_range
        actual_start = sorted_segments[0].T_start
        actual_end = sorted_segments[-1].T_end

        if actual_start > expected_start:
            coverage_gaps.append((expected_start, actual_start))
            warnings.append(f"Gap at start: {expected_start:.1f}-{actual_start:.1f}K")

        if actual_end < expected_end:
            coverage_gaps.append((actual_end, expected_end))
            warnings.append(f"Gap at end: {actual_end:.1f}-{expected_end:.1f}K")

        # Check gaps and overlaps between segments
        for i in range(len(sorted_segments) - 1):
            current = sorted_segments[i]
            next_segment = sorted_segments[i + 1]

            if current.T_end < next_segment.T_start:
                coverage_gaps.append((current.T_end, next_segment.T_start))
                warnings.append(f"Gap between segments: {current.T_end:.1f}-{next_segment.T_start:.1f}K")

            elif current.T_end > next_segment.T_start:
                overlap_size = current.T_end - next_segment.T_start
                coverage_overlaps.append((next_segment.T_start, current.T_end))
                warnings.append(f"Overlap between segments: {next_segment.T_start:.1f}-{current.T_end:.1f}K ({overlap_size:.1f}K)")

        # Check for segments without records
        segments_without_records = [s for s in sorted_segments if s.record is None]
        if segments_without_records:
            warnings.append(f"{len(segments_without_records)} segments without assigned records")

        return SegmentAnalysis(
            total_segments=len(sorted_segments),
            phase_transitions=[],  # Will be filled by caller
            coverage_gaps=coverage_gaps,
            coverage_overlaps=coverage_overlaps,
            optimized_segments=sorted_segments,
            warnings=warnings,
            analysis_timestamp=datetime.now()
        )

    def _create_multi_phase_properties(
        self,
        segments: List[PhaseSegment],
        transitions: List[PhaseTransition],
        temperature_range: Tuple[float, float],
        compound_formula: str,
        analysis: SegmentAnalysis
    ) -> MultiPhaseProperties:
        """
        Create MultiPhaseProperties from segments and transitions.

        Args:
            segments: Phase segments
            transitions: Phase transitions
            temperature_range: Temperature range
            compound_formula: Compound formula
            analysis: Segment analysis

        Returns:
            MultiPhaseProperties result
        """
        # For now, set target to middle of range
        T_target = (temperature_range[0] + temperature_range[1]) / 2

        return MultiPhaseProperties(
            T_target=T_target,
            H_final=0.0,  # Will be calculated by ThermodynamicCalculator
            S_final=0.0,  # Will be calculated by ThermodynamicCalculator
            G_final=0.0,  # Will be calculated by ThermodynamicCalculator
            Cp_final=0.0,  # Will be calculated by ThermodynamicCalculator
            segments=analysis.optimized_segments,
            phase_transitions=transitions,
            temperature_path=[],  # Will be filled by calculator
            H_path=[],  # Will be filled by calculator
            S_path=[],  # Will be filled by calculator
            warnings=analysis.warnings
        )