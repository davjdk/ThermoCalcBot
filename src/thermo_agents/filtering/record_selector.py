"""
Record Selector for Multi-phase Logic (Stage 2)

This module implements the RecordSelector component that selects optimal
database records for specific temperatures and identifies transition points.

Key features:
- Selects best records for specific temperatures based on coverage and reliability
- Identifies transition points where record switches occur
- Optimizes record sequences for continuous coverage
- Handles overlapping records and priority selection
- Supports multi-record scenarios with intelligent fallback

Technical description:
RecordSelector реализует логику выбора оптимальных записей базы данных
для конкретных температур в многофазных термодинамических расчётах.

Основная задача — выбирать наиболее подходящие записи для заданной температуры
на основе температурного покрытия, класса надёжности и других параметров.
Компонент также определяет точки переключения между записями и оптимизирует
последовательности записей для бесшовных расчётов.

Ключевая логика:
1. Для заданной температуры найти все покрывающие записи
2. Отсортировать по надёжности и покрытию
3. Выбрать лучшую запись или предоставить fallback
4. Определить точки переключения между записями
5. Оптимизировать последовательность для непрерывности

Пример использования:
    selector = RecordSelector()

    # Выбрать запись для температуры 1000K
    best_record = selector.select_record_for_temperature(
        records=feo_records,
        temperature=1000.0
    )

    # Найти точки переключения
    transitions = selector.find_transition_points(feo_records)

    # Оптимизировать последовательность
    optimized = selector.optimize_record_sequence(feo_records)

Валидация:
- Проверка температурного покрытия
- Валидация классов надёжности
- Анализ перекрытий и пробелов
- Генерация предупреждений о неоднозначностях
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime

from ..models.search import DatabaseRecord
from .constants import (
    MAX_RELIABILITY_CLASS,
    TEMPERATURE_EXTENSION_MARGIN,
)

logger = logging.getLogger(__name__)


@dataclass
class TransitionPoint:
    """Represents a temperature point where record switching occurs."""

    temperature: float
    from_record: DatabaseRecord
    to_record: DatabaseRecord
    reason: str  # "temperature_limit", "reliability", "phase_change"
    confidence: float  # 0.0 to 1.0


@dataclass
class RecordSelection:
    """Result of record selection for a temperature."""

    selected_record: DatabaseRecord
    alternative_records: List[DatabaseRecord]
    selection_reason: str
    confidence: float
    warnings: List[str]


class RecordSelector:
    """
    Record selector for multi-phase calculations (Stage 2).

    This component implements intelligent selection of database records
    for specific temperatures, handling overlaps, transitions, and
    optimization of record sequences.
    """

    def __init__(self):
        """Initialize the record selector."""
        self._selection_cache = {}
        logger.info("RecordSelector initialized for Stage 2 implementation")

    def select_record_for_temperature(
        self,
        records: List[DatabaseRecord],
        temperature: float,
        preferred_phase: Optional[str] = None
    ) -> RecordSelection:
        """
        Select the best record for a specific temperature.

        Args:
            records: Available database records
            temperature: Target temperature in Kelvin
            preferred_phase: Optional preferred phase

        Returns:
            RecordSelection with best record and alternatives

        Raises:
            ValueError: If no records are provided
        """
        if not records:
            raise ValueError("No records provided for selection")

        cache_key = f"select_{len(records)}_{temperature}_{preferred_phase}"
        if cache_key in self._selection_cache:
            return self._selection_cache[cache_key]

        logger.debug(f"Selecting record for T={temperature:.1f}K from {len(records)} records")

        # Step 1: Find records that cover the temperature
        covering_records = self._find_covering_records(records, temperature)

        if not covering_records:
            # Fallback: find closest records
            covering_records = self._find_closest_records(records, temperature)
            logger.warning(f"No records cover T={temperature:.1f}K, using closest matches")

        # Step 2: Filter by preferred phase if specified
        if preferred_phase:
            phase_records = [r for r in covering_records if r.phase == preferred_phase]
            if phase_records:
                covering_records = phase_records
                logger.debug(f"Filtered by preferred phase '{preferred_phase}': {len(phase_records)} records")

        # Step 3: Score and rank records
        scored_records = self._score_records(covering_records, temperature)

        # Step 4: Select best record
        best_record, best_score = scored_records[0]
        alternatives = [r for r, score in scored_records[1:] if score > 0.5]

        # Step 5: Determine selection reason and confidence
        reason, confidence = self._determine_selection_reason(best_record, temperature, best_score)
        warnings = self._generate_selection_warnings(best_record, temperature, covering_records)

        selection = RecordSelection(
            selected_record=best_record,
            alternative_records=alternatives,
            selection_reason=reason,
            confidence=confidence,
            warnings=warnings
        )

        self._selection_cache[cache_key] = selection
        return selection

    def find_transition_points(
        self,
        records: List[DatabaseRecord]
    ) -> List[TransitionPoint]:
        """
        Find temperature points where record switching should occur.

        Args:
            records: Database records to analyze

        Returns:
            List of transition points sorted by temperature
        """
        if not records:
            return []

        logger.debug(f"Finding transition points in {len(records)} records")

        # Sort records by temperature range
        sorted_records = sorted(records, key=lambda r: (r.tmin, r.tmax))

        transition_points = []

        for i in range(len(sorted_records) - 1):
            current = sorted_records[i]
            next_record = sorted_records[i + 1]

            # Check for potential transition points
            transitions = self._analyze_record_transition(current, next_record)
            transition_points.extend(transitions)

        # Sort by temperature
        transition_points.sort(key=lambda t: t.temperature)

        logger.debug(f"Found {len(transition_points)} transition points")
        return transition_points

    def optimize_record_sequence(
        self,
        records: List[DatabaseRecord],
        temperature_range: Optional[Tuple[float, float]] = None
    ) -> List[DatabaseRecord]:
        """
        Optimize the sequence of records for continuous coverage.

        Args:
            records: Database records to optimize
            temperature_range: Optional temperature range to consider

        Returns:
            Optimized sequence of records
        """
        if not records:
            return []

        logger.debug(f"Optimizing sequence of {len(records)} records")

        # Remove exact duplicates
        unique_records = self._remove_duplicates(records)

        # Sort by reliability and temperature coverage
        sorted_records = sorted(
            unique_records,
            key=lambda r: (
                r.reliability_class if r.reliability_class else 999,
                r.tmin,
                -(r.tmax - r.tmin)  # Prefer wider coverage
            )
        )

        # Build optimal sequence using greedy algorithm
        optimal_sequence = []
        used_temperatures = set()

        if temperature_range:
            t_start, t_end = temperature_range
            current_temp = t_start
        else:
            t_start = min(r.tmin for r in sorted_records)
            t_end = max(r.tmax for r in sorted_records)
            current_temp = t_start

        while current_temp <= t_end and optimal_sequence:
            # Find best record for current temperature
            selection = self.select_record_for_temperature(sorted_records, current_temp)

            if selection.selected_record not in optimal_sequence:
                optimal_sequence.append(selection.selected_record)
                logger.debug(f"Added record {selection.selected_record.id} at T={current_temp:.1f}K")

            # Move to next uncovered temperature
            record = selection.selected_record
            current_temp = max(record.tmax, current_temp) + TEMPERATURE_EXTENSION_MARGIN

        # Verify coverage
        if temperature_range:
            coverage_issues = self._verify_sequence_coverage(optimal_sequence, temperature_range)
            if coverage_issues:
                logger.warning(f"Coverage issues in optimized sequence: {coverage_issues}")

        logger.debug(f"Optimized sequence: {len(optimal_sequence)} records")
        return optimal_sequence

    def _find_covering_records(
        self,
        records: List[DatabaseRecord],
        temperature: float
    ) -> List[DatabaseRecord]:
        """
        Find records that cover the specified temperature.

        Args:
            records: Database records
            temperature: Target temperature

        Returns:
            List of records that cover the temperature
        """
        covering_records = []

        for record in records:
            if record.tmin <= temperature <= record.tmax:
                covering_records.append(record)

        return covering_records

    def _find_closest_records(
        self,
        records: List[DatabaseRecord],
        temperature: float
    ) -> List[DatabaseRecord]:
        """
        Find records closest to the specified temperature.

        Args:
            records: Database records
            temperature: Target temperature

        Returns:
            List of records sorted by distance to temperature
        """
        records_with_distance = []

        for record in records:
            if temperature < record.tmin:
                distance = record.tmin - temperature
            elif temperature > record.tmax:
                distance = temperature - record.tmax
            else:
                distance = 0  # Shouldn't happen if called from select_record_for_temperature

            records_with_distance.append((record, distance))

        # Sort by distance
        records_with_distance.sort(key=lambda x: x[1])

        return [r for r, d in records_with_distance]

    def _score_records(
        self,
        records: List[DatabaseRecord],
        temperature: float
    ) -> List[Tuple[DatabaseRecord, float]]:
        """
        Score records based on various criteria.

        Args:
            records: Records to score
            temperature: Target temperature

        Returns:
            List of (record, score) tuples sorted by score (descending)
        """
        scored_records = []

        for record in records:
            score = 0.0

            # Temperature coverage score (0-40 points)
            if record.tmin <= temperature <= record.tmax:
                # Perfect coverage
                t_range = record.tmax - record.tmin
                if t_range > 0:
                    # Higher score for records that aren't stretched too thin
                    coverage_score = min(40, 40 * (temperature - record.tmin) / t_range,
                                       40 * (record.tmax - temperature) / t_range)
                    score += coverage_score
                else:
                    score += 20  # Minimal score for single-point coverage
            else:
                # Penalty for not covering temperature
                if temperature < record.tmin:
                    distance = record.tmin - temperature
                else:
                    distance = temperature - record.tmax
                score += max(0, 40 - distance / 100)  # Penalty based on distance

            # Reliability score (0-30 points)
            reliability = record.reliability_class if record.reliability_class else 3
            if reliability <= MAX_RELIABILITY_CLASS:
                reliability_score = 30 * (MAX_RELIABILITY_CLASS + 1 - reliability) / (MAX_RELIABILITY_CLASS + 1)
                score += reliability_score

            # Data completeness score (0-20 points)
            completeness_score = 0
            if record.h298 != 0:
                completeness_score += 10
            if record.s298 != 0:
                completeness_score += 10
            score += completeness_score

            # Temperature range score (0-10 points)
            t_range = record.tmax - record.tmin
            range_score = min(10, t_range / 1000)  # Prefer wider ranges
            score += range_score

            # Normalize score to 0-1 range
            normalized_score = min(1.0, score / 100.0)
            scored_records.append((record, normalized_score))

        # Sort by score (descending)
        scored_records.sort(key=lambda x: x[1], reverse=True)

        return scored_records

    def _determine_selection_reason(
        self,
        record: DatabaseRecord,
        temperature: float,
        score: float
    ) -> Tuple[str, float]:
        """
        Determine the reason for record selection and confidence.

        Args:
            record: Selected record
            temperature: Target temperature
            score: Selection score

        Returns:
            Tuple of (reason, confidence)
        """
        reasons = []
        confidence = score

        # Check temperature coverage
        if record.tmin <= temperature <= record.tmax:
            reasons.append("covers temperature")
            confidence += 0.2
        else:
            if temperature < record.tmin:
                reasons.append(f"closest below (tmin={record.tmin:.0f}K)")
            else:
                reasons.append(f"closest above (tmax={record.tmax:.0f}K)")
            confidence -= 0.1

        # Check reliability
        if record.reliability_class and record.reliability_class == 1:
            reasons.append("high reliability")
            confidence += 0.1
        elif record.reliability_class and record.reliability_class > 2:
            reasons.append("low reliability")
            confidence -= 0.1

        # Check data completeness
        if record.h298 != 0 and record.s298 != 0:
            reasons.append("complete thermodynamic data")
        elif record.h298 == 0 and record.s298 == 0:
            reasons.append("missing thermodynamic data")
            confidence -= 0.2

        # Combine reasons
        reason = ", ".join(reasons) if reasons else "default selection"
        confidence = max(0.0, min(1.0, confidence))

        return reason, confidence

    def _generate_selection_warnings(
        self,
        record: DatabaseRecord,
        temperature: float,
        all_records: List[DatabaseRecord]
    ) -> List[str]:
        """
        Generate warnings about the record selection.

        Args:
            record: Selected record
            temperature: Target temperature
            all_records: All available records

        Returns:
            List of warnings
        """
        warnings = []

        # Check temperature coverage
        if not (record.tmin <= temperature <= record.tmax):
            warnings.append(f"Selected record does not cover temperature {temperature:.1f}K "
                          f"(range: {record.tmin:.1f}-{record.tmax:.1f}K)")

        # Check data quality
        if record.h298 == 0 and record.s298 == 0:
            warnings.append("Selected record has H298=0 and S298=0")
        elif record.h298 == 0:
            warnings.append("Selected record has H298=0")
        elif record.s298 == 0:
            warnings.append("Selected record has S298=0")

        # Check reliability
        if record.reliability_class and record.reliability_class > 2:
            warnings.append(f"Selected record has low reliability class ({record.reliability_class})")

        # Check for better alternatives
        better_alternatives = [
            r for r in all_records
            if (r.tmin <= temperature <= r.tmax and
                r.reliability_class and
                record.reliability_class and
                r.reliability_class < record.reliability_class)
        ]
        if better_alternatives:
            warnings.append(f"Better reliability alternatives exist: {len(better_alternatives)} records")

        return warnings

    def _analyze_record_transition(
        self,
        record1: DatabaseRecord,
        record2: DatabaseRecord
    ) -> List[TransitionPoint]:
        """
        Analyze transition points between two records.

        Args:
            record1: First record
            record2: Second record

        Returns:
            List of transition points
        """
        transitions = []

        # Check for temperature boundary transition
        if abs(record1.tmax - record2.tmin) < TEMPERATURE_EXTENSION_MARGIN:
            # Records touch at boundary
            transition_temp = (record1.tmax + record2.tmin) / 2

            # Determine reason for transition
            reason = "temperature_limit"
            confidence = 0.8

            # Check for phase change
            if record1.phase != record2.phase:
                reason = "phase_change"
                confidence = 0.9

            # Check reliability difference
            if (record1.reliability_class and record2.reliability_class and
                abs(record1.reliability_class - record2.reliability_class) > 1):
                reason = "reliability"
                confidence = 0.7

            transition = TransitionPoint(
                temperature=transition_temp,
                from_record=record1,
                to_record=record2,
                reason=reason,
                confidence=confidence
            )
            transitions.append(transition)

        # Check for overlap (should choose one over the other)
        elif record1.tmax > record2.tmin and record2.tmax > record1.tmin:
            # Records overlap - might need to switch based on reliability
            if (record1.reliability_class and record2.reliability_class and
                record1.reliability_class > record2.reliability_class):
                # record2 is more reliable, might switch to it
                switch_temp = record2.tmin + (record1.tmax - record2.tmin) / 2

                transition = TransitionPoint(
                    temperature=switch_temp,
                    from_record=record1,
                    to_record=record2,
                    reason="reliability",
                    confidence=0.6
                )
                transitions.append(transition)

        return transitions

    def _remove_duplicates(self, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """
        Remove exact duplicate records.

        Args:
            records: Records to deduplicate

        Returns:
            List of unique records
        """
        unique_records = []
        seen_ids = set()

        for record in records:
            if record.id and record.id not in seen_ids:
                unique_records.append(record)
                seen_ids.add(record.id)
            elif not record.id:
                # For records without ID, check all fields
                is_duplicate = False
                for existing in unique_records:
                    if (existing.formula == record.formula and
                        existing.phase == record.phase and
                        existing.tmin == record.tmin and
                        existing.tmax == record.tmax and
                        existing.h298 == record.h298 and
                        existing.s298 == record.s298):
                        is_duplicate = True
                        break

                if not is_duplicate:
                    unique_records.append(record)

        logger.debug(f"Removed {len(records) - len(unique_records)} duplicate records")
        return unique_records

    def _verify_sequence_coverage(
        self,
        sequence: List[DatabaseRecord],
        temperature_range: Tuple[float, float]
    ) -> List[str]:
        """
        Verify that the record sequence provides complete coverage.

        Args:
            sequence: Record sequence to verify
            temperature_range: Expected temperature range

        Returns:
            List of coverage issues
        """
        issues = []
        t_start, t_end = temperature_range

        if not sequence:
            return ["No records in sequence"]

        # Sort by tmin
        sorted_sequence = sorted(sequence, key=lambda r: r.tmin)

        # Check start coverage
        if sorted_sequence[0].tmin > t_start:
            issues.append(f"Gap at start: {t_start:.1f}-{sorted_sequence[0].tmin:.1f}K")

        # Check coverage between records
        for i in range(len(sorted_sequence) - 1):
            current = sorted_sequence[i]
            next_record = sorted_sequence[i + 1]

            if current.tmax < next_record.tmin:
                gap = next_record.tmin - current.tmax
                if gap > TEMPERATURE_EXTENSION_MARGIN:
                    issues.append(f"Gap between records {current.id} and {next_record.id}: {gap:.1f}K")

        # Check end coverage
        if sorted_sequence[-1].tmax < t_end:
            issues.append(f"Gap at end: {sorted_sequence[-1].tmax:.1f}-{t_end:.1f}K")

        return issues