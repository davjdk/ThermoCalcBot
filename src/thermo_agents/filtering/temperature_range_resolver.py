"""
Temperature Range Resolver for Multi-phase Logic (Stage 1)

This module implements the TemperatureRangeResolver component that determines
the optimal calculation temperature range for multi-phase thermodynamic calculations.

Key features:
- Ignores user temperature limits for database search (Stage 1 core requirement)
- Determines optimal calculation range from all available compound data
- Ensures 298K is included when data is available
- Provides validation of range coverage across all compounds
- Supports intersection analysis for multi-compound reactions

Technical description:
TemperatureRangeResolver реализует логику определения оптимального температурного диапазона
для многофазных термодинамических расчётов в соответствии с требованиями Этапа 1.

Основная задача — игнорировать пользовательский температурный диапазон при поиске данных
в базе данных, обеспечивая максимальное использование доступных записей. Компонент
определяет общий расчётный диапазон как пересечение диапазонов всех веществ реакции.

Ключевая логика:
1. Собрать все tmin/tmax из записей всех веществ
2. Найти пересечение температурных диапазонов
3. Расширить диапазон до включения 298K если возможно
4. Провести валидацию покрытия для всех веществ
5. Вернуть оптимальный диапазон для расчётов

Пример использования:
    resolver = TemperatureRangeResolver()

    # Для одного вещества
    calc_range = resolver.determine_calculation_range({
        "FeO": [record1, record2, record3, ...]
    })

    # Для реакции из нескольких веществ
    calc_range = resolver.determine_calculation_range({
        "FeO": feo_records,
        "O2": o2_records,
        "Fe2O3": fe2o3_records
    })

    # Валидация покрытия
    coverage = resolver.validate_range_coverage(compounds_data, calc_range)

Результат:
- FeO: найдено 6 записей вместо 1
- Используется H₂₉₈ = -265.053 кДж/моль вместо 0.0
- Расчётный диапазон: 298-5000K вместо пользовательского 773-973K
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime

from ..models.search import DatabaseRecord
from .constants import (
    MIN_TEMPERATURE_K,
    MAX_TEMPERATURE_K,
    MIN_TEMPERATURE_COVERAGE_RATIO,
)

logger = logging.getLogger(__name__)


@dataclass
class TemperatureRangeAnalysis:
    """Analysis result for temperature range determination."""

    calculation_range: Tuple[float, float]
    original_user_range: Optional[Tuple[float, float]]
    includes_298K: bool
    coverage_per_compound: Dict[str, str]
    intersection_details: Dict[str, Any]
    recommendations: List[str]
    analysis_timestamp: datetime


class TemperatureRangeResolver:
    """
    Temperature range resolver for multi-phase calculations (Stage 1).

    This component implements the core logic for determining optimal temperature
    ranges that ignore user limitations and maximize data utilization from the database.
    """

    def __init__(self):
        """Initialize the temperature range resolver."""
        self._analysis_cache = {}
        logger.info("TemperatureRangeResolver initialized for Stage 1 implementation")

    def determine_calculation_range(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]],
        user_range: Optional[Tuple[float, float]] = None
    ) -> TemperatureRangeAnalysis:
        """
        Determine the optimal calculation temperature range for multi-phase logic.

        This method implements the core Stage 1 requirement: ignore user temperature
        limitations and use the maximum available data from the database.

        Args:
            compounds_data: Dictionary mapping compound formulas to their database records
            user_range: Original user-requested temperature range (for tracking only)

        Returns:
            TemperatureRangeAnalysis with calculation range and metadata
        """
        logger.info(f"Determining calculation range for {len(compounds_data)} compounds")

        if not compounds_data:
            raise ValueError("No compounds data provided for range determination")

        # Step 1: Extract all temperature ranges from all records
        all_ranges = self._extract_all_temperature_ranges(compounds_data)

        # Step 2: Find intersection of all compound ranges
        intersection_range = self._find_intersection_range(all_ranges)

        # Step 3: Ensure 298K is included if possible
        final_range = self._ensure_298K_inclusion(intersection_range, all_ranges)

        # Step 4: Validate coverage for each compound
        coverage_per_compound = self._validate_compound_coverage(compounds_data, final_range)

        # Step 5: Generate recommendations
        recommendations = self._generate_recommendations(
            compounds_data, final_range, user_range, coverage_per_compound
        )

        # Step 6: Create analysis result
        analysis = TemperatureRangeAnalysis(
            calculation_range=final_range,
            original_user_range=user_range,
            includes_298K=final_range[0] <= 298.15 <= final_range[1],
            coverage_per_compound=coverage_per_compound,
            intersection_details={
                'total_compounds': len(compounds_data),
                'intersection_before_298K_expansion': intersection_range,
                'all_individual_ranges': all_ranges,
                'records_per_compound': {
                    formula: len(records) for formula, records in compounds_data.items()
                }
            },
            recommendations=recommendations,
            analysis_timestamp=datetime.now()
        )

        logger.info(f"Calculation range determined: {final_range[0]:.1f}-{final_range[1]:.1f}K")
        return analysis

    def _extract_all_temperature_ranges(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]]
    ) -> Dict[str, List[Tuple[float, float]]]:
        """Extract temperature ranges from all records of each compound."""
        all_ranges = {}

        for formula, records in compounds_data.items():
            if not records:
                logger.warning(f"No records found for compound {formula}")
                continue

            compound_ranges = []
            for record in records:
                if record.tmin is not None and record.tmax is not None:
                    # Apply reasonable limits for extreme values
                    tmin = max(record.tmin, MIN_TEMPERATURE_K)
                    tmax = min(record.tmax, MAX_TEMPERATURE_K)

                    if tmax > tmin:
                        compound_ranges.append((tmin, tmax))

            all_ranges[formula] = compound_ranges
            logger.debug(f"Extracted {len(compound_ranges)} ranges for {formula}")

        return all_ranges

    def _find_intersection_range(
        self,
        all_ranges: Dict[str, List[Tuple[float, float]]]
    ) -> Tuple[float, float]:
        """Find the intersection of temperature ranges across all compounds."""
        if not all_ranges:
            return (298.15, 298.15)  # Default to standard temperature

        # Start with the range of the first compound
        compound_names = list(all_ranges.keys())
        if not compound_names:
            return (298.15, 298.15)

        first_compound = compound_names[0]
        if not all_ranges[first_compound]:
            logger.warning(f"No valid ranges for {first_compound}")
            return (298.15, 298.15)

        # Find the union of ranges for the first compound
        current_intersection = self._unite_ranges(all_ranges[first_compound])

        # Intersect with each subsequent compound
        for formula in compound_names[1:]:
            compound_ranges = all_ranges[formula]
            if not compound_ranges:
                logger.warning(f"No valid ranges for {formula}")
                return (298.15, 298.15)

            compound_union = self._unite_ranges(compound_ranges)
            current_intersection = self._intersect_two_ranges(current_intersection, compound_union)

            # Early termination if intersection becomes empty
            if current_intersection[0] >= current_intersection[1]:
                logger.warning(f"No intersection found after processing {formula}")
                return (298.15, 298.15)

        logger.debug(f"Intersection range found: {current_intersection[0]:.1f}-{current_intersection[1]:.1f}K")
        return current_intersection

    def _unite_ranges(self, ranges: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Unite overlapping temperature ranges into a single range."""
        if not ranges:
            return (298.15, 298.15)

        min_temp = min(r[0] for r in ranges)
        max_temp = max(r[1] for r in ranges)

        return (min_temp, max_temp)

    def _intersect_two_ranges(
        self,
        range1: Tuple[float, float],
        range2: Tuple[float, float]
    ) -> Tuple[float, float]:
        """Intersect two temperature ranges."""
        start = max(range1[0], range2[0])
        end = min(range1[1], range2[1])

        return (start, max(start, end))  # Ensure valid range

    def _ensure_298K_inclusion(
        self,
        current_range: Tuple[float, float],
        all_ranges: Dict[str, List[Tuple[float, float]]]
    ) -> Tuple[float, float]:
        """
        Ensure 298K is included in the calculation range if possible.

        This is a critical Stage 1 requirement - always try to include
        standard temperature for correct H298 and S298 values.
        """
        standard_temp = 298.15

        # If 298K is already in range, return as-is
        if current_range[0] <= standard_temp <= current_range[1]:
            logger.debug("298K already included in calculation range")
            return current_range

        # Check if any compound has data at 298K
        has_298K_data = any(
            any(r[0] <= standard_temp <= r[1] for r in ranges)
            for ranges in all_ranges.values()
        )

        if not has_298K_data:
            logger.debug("No compound has data at 298K, keeping original range")
            return current_range

        # Try to expand range to include 298K
        if standard_temp < current_range[0]:
            # Try to extend lower bound
            new_min = standard_temp
            new_max = current_range[1]
        else:
            # Try to extend upper bound
            new_min = current_range[0]
            new_max = standard_temp

        # Validate that expanded range still has data for all compounds
        expanded_has_coverage = all(
            any(
                not (new_max < r[0] or new_min > r[1])  # Overlap check
                for r in ranges
            )
            for ranges in all_ranges.values()
        )

        if expanded_has_coverage:
            logger.debug(f"Expanded range to include 298K: {new_min:.1f}-{new_max:.1f}K")
            return (new_min, new_max)
        else:
            logger.debug("Cannot expand range to include 298K while maintaining coverage")
            return current_range

    def _validate_compound_coverage(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]],
        target_range: Tuple[float, float]
    ) -> Dict[str, str]:
        """Validate that each compound has coverage in the target range."""
        coverage_status = {}

        for formula, records in compounds_data.items():
            if not records:
                coverage_status[formula] = 'no_data'
                continue

            # Check if any record covers the target range
            has_coverage = any(
                not (target_range[1] < record.tmin or target_range[0] > record.tmax)
                for record in records
            )

            if has_coverage:
                coverage_status[formula] = 'covered'
            else:
                coverage_status[formula] = 'no_coverage'

        return coverage_status

    def _generate_recommendations(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]],
        final_range: Tuple[float, float],
        user_range: Optional[Tuple[float, float]],
        coverage_per_compound: Dict[str, str]
    ) -> List[str]:
        """Generate recommendations based on the range analysis."""
        recommendations = []

        # Record count improvements
        total_records = sum(len(records) for records in compounds_data.values())
        if total_records > 10:
            recommendations.append(f"Найдено {total_records} записей по всем веществам")

        # 298K inclusion
        if final_range[0] <= 298.15 <= final_range[1]:
            recommendations.append("Расчётный диапазон включает стандартные условия (298K)")
        else:
            recommendations.append("Внимание: расчётный диапазон не включает 298K")

        # Range comparison with user request
        if user_range:
            if final_range != user_range:
                recommendations.append(
                    f"Расчётный диапазон ({final_range[0]:.0f}-{final_range[1]:.0f}K) "
                    f"отличается от запрошенного ({user_range[0]:.0f}-{user_range[1]:.0f}K)"
                )

        # Coverage warnings
        uncovered_compounds = [
            formula for formula, status in coverage_per_compound.items()
            if status in ['no_data', 'no_coverage']
        ]

        if uncovered_compounds:
            recommendations.append(
                f"Внимание: отсутствуют данные для веществ: {', '.join(uncovered_compounds)}"
            )

        return recommendations

    def validate_range_coverage(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]],
        temp_range: Tuple[float, float]
    ) -> Dict[str, bool]:
        """
        Validate temperature range coverage for all compounds.

        Args:
            compounds_data: Dictionary mapping compounds to their records
            temp_range: Temperature range to validate

        Returns:
            Dictionary mapping compound names to coverage status (True/False)
        """
        coverage_results = {}

        for formula, records in compounds_data.items():
            if not records:
                coverage_results[formula] = False
                continue

            # Check if any record covers the temperature range
            has_coverage = any(
                record.tmin <= temp_range[0] and record.tmax >= temp_range[1]
                for record in records
            )

            coverage_results[formula] = has_coverage

        return coverage_results

    def get_range_statistics(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]]
    ) -> Dict[str, Any]:
        """
        Get comprehensive statistics about temperature ranges in compounds data.

        Args:
            compounds_data: Dictionary mapping compounds to their records

        Returns:
            Statistics dictionary with temperature range analysis
        """
        if not compounds_data:
            return {}

        all_temps = []
        compound_stats = {}

        for formula, records in compounds_data.items():
            if not records:
                continue

            temps = [(record.tmin, record.tmax) for record in records if record.tmin and record.tmax]
            all_temps.extend(temps)

            if temps:
                compound_stats[formula] = {
                    'record_count': len(records),
                    'min_temp': min(t[0] for t in temps),
                    'max_temp': max(t[1] for t in temps),
                    'range_width': max(t[1] for t in temps) - min(t[0] for t in temps)
                }

        overall_stats = {
            'total_records': sum(len(records) for records in compounds_data.values()),
            'compounds_count': len(compounds_data),
            'compounds_with_data': len(compound_stats),
            'overall_min_temp': min(t[0] for t in all_temps) if all_temps else None,
            'overall_max_temp': max(t[1] for t in all_temps) if all_temps else None,
            'compound_statistics': compound_stats
        }

        return overall_stats