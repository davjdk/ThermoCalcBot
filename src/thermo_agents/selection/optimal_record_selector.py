"""
Optimal record selector for thermodynamic data.

This module implements algorithms for optimizing the selection of database records
to cover temperature ranges with minimal record count while maintaining accuracy.
Supports virtual record merging for contiguous records with identical Shomate coefficients.
"""

import logging
import time
from dataclasses import field
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ..models.search import DatabaseRecord
from .selection_config import OptimizationConfig, OptimizationScore, RecordGroup

logger = logging.getLogger(__name__)


class VirtualRecord(DatabaseRecord):
    """A virtual record created by merging multiple physical records."""

    def __init__(self, source_records: List[DatabaseRecord], **data):
        """Initialize virtual record from source records."""
        if not source_records:
            raise ValueError("Source records list cannot be empty")

        # Use data from the first source record for base properties
        source = source_records[0]

        # Initialize with source record data
        init_data = {
            "id": source.id,
            "formula": source.formula,
            "name": source.name,
            "first_name": source.first_name,
            "second_name": source.second_name,
            "phase": source.phase,
            "tmin": min(r.tmin for r in source_records),
            "tmax": max(r.tmax for r in source_records),
            "h298": source.h298,
            "s298": source.s298,
            "f1": source.f1,
            "f2": source.f2,
            "f3": source.f3,
            "f4": source.f4,
            "f5": source.f5,
            "f6": source.f6,
            "tmelt": source.tmelt,
            "tboil": source.tboil,
            # Use best (minimum) reliability class from all source records
            "reliability_class": min(r.reliability_class for r in source_records),
            **data,
        }

        super().__init__(**init_data)

        # Set virtual record specific attributes
        self.is_virtual = True
        self.source_records = source_records
        self.merged_tmin = init_data["tmin"]
        self.merged_tmax = init_data["tmax"]

    def explain_merge(self) -> str:
        """Get explanation of how this virtual record was created."""
        if not self.source_records:
            return "No source records"

        # Format temperatures as integers if they are whole numbers
        def format_temp(temp: float) -> str:
            return f"{int(temp)}" if temp == int(temp) else f"{temp}"

        source_ranges = [
            f"{format_temp(r.Tmin)}-{format_temp(r.Tmax)}K" for r in self.source_records
        ]
        return (
            f"Virtual record merged from {len(self.source_records)} records: "
            f"{', '.join(source_ranges)} → {format_temp(self.merged_tmin)}-{format_temp(self.merged_tmax)}K"
        )


class OptimalRecordSelector:
    """
    Optimizes the selection of database records for temperature ranges.

    This class implements a post-processing step after the three-level selection
    strategy to minimize the number of records while maintaining accuracy.
    """

    def __init__(self, config: Optional[OptimizationConfig] = None):
        """Initialize the selector with configuration."""
        self.config = config or OptimizationConfig()
        self._virtual_record_cache: Dict[str, VirtualRecord] = {}
        logger.debug(f"OptimalRecordSelector initialized with config: {self.config}")

    def optimize_selected_records(
        self,
        selected_records: List[Union[pd.Series, DatabaseRecord]],
        target_range: Tuple[float, float],
        all_available_records: pd.DataFrame,
        melting: Optional[float] = None,
        boiling: Optional[float] = None,
        is_elemental: Optional[bool] = None,
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Optimize a set of selected records for minimal count while maintaining coverage.

        This is the main entry point that implements the 4-step optimization process:
        1. Analyze current selection
        2. Search for alternatives
        3. Validate phase transitions
        4. Final validation

        Args:
            selected_records: Records from three-level selection strategy
            target_range: Target temperature range (tmin, tmax)
            all_available_records: All available records in database
            melting: Melting point temperature (K)
            boiling: Boiling point temperature (K)
            is_elemental: Whether the compound is elemental

        Returns:
            Optimized list of records (may contain VirtualRecord instances)
        """
        start_time = time.perf_counter()
        target_min, target_max = target_range

        logger.debug(
            f"[OptimalRecordSelector] Optimizing {len(selected_records)} records for range {target_range}K"
        )

        # Step 0: Handle edge cases
        if not selected_records:
            logger.debug(
                "[OptimalRecordSelector] Empty input records - returning empty list"
            )
            return []

        if len(selected_records) == 1:
            logger.debug(
                "[OptimalRecordSelector] Single record - no optimization possible"
            )
            return selected_records

        # Step 1: Analyze current selection
        current_score = self._calculate_selection_score(
            selected_records, target_range, melting, boiling
        )
        logger.debug(
            f"[OptimalRecordSelector] Current selection score: {current_score.total_score:.4f}"
        )

        # Step 2: Group records by phase and temperature continuity
        phase_groups = self._group_records_by_phase(
            selected_records, target_min, target_max
        )
        logger.debug(
            f"[OptimalRecordSelector] Grouped into {len(phase_groups)} phase groups"
        )

        # Step 3: Optimize each phase group
        optimized_groups = []
        for group in phase_groups:
            optimized_group = self._optimize_phase_group(
                group, all_available_records, is_elemental or False
            )
            optimized_groups.extend(optimized_group)

        # Step 4: Validate phase transition coverage
        final_records = self._ensure_phase_transition_coverage(
            optimized_groups, target_range, melting, boiling, all_available_records
        )

        # Step 5: Final validation
        validated_records = self._validate_final_selection(
            final_records,
            selected_records,  # Pass original for fallback
            target_range,
            melting,
            boiling,
            is_elemental or False,
        )

        # Step 6: Calculate improvement
        if validated_records != selected_records:
            new_score = self._calculate_selection_score(
                validated_records, target_range, melting, boiling
            )
            improvement = (
                new_score.total_score - current_score.total_score
            ) / current_score.total_score

            if improvement > self.config.min_score_improvement:
                reduction = len(selected_records) - len(validated_records)
                logger.info(
                    f"[OptimalRecordSelector] ✓ Optimization improved score by {improvement:.1%} "
                    f"({reduction} fewer records: {len(selected_records)} → {len(validated_records)})"
                )
            else:
                logger.debug(
                    f"[OptimalRecordSelector] Optimization insufficient improvement ({improvement:.1%} "
                    f"< {self.config.min_score_improvement:.1%}) - keeping original"
                )
                validated_records = selected_records
        else:
            logger.debug("[OptimalRecordSelector] No optimization improvements found")

        # Performance logging
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"[OptimalRecordSelector] Optimization completed in {elapsed_ms:.2f}ms"
        )

        if elapsed_ms > self.config.max_optimization_time_ms:
            logger.warning(
                f"[OptimalRecordSelector] Optimization exceeded time limit: "
                f"{elapsed_ms:.2f}ms > {self.config.max_optimization_time_ms}ms"
            )

        return validated_records

    def _group_records_by_phase(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        target_min: float,
        target_max: float,
    ) -> List[RecordGroup]:
        """
        Group records by phase and temperature continuity.

        Creates groups of contiguous records of the same phase that can be
        considered for virtual merging.
        """
        if not records:
            return []

        # Sort records by temperature
        sorted_records = sorted(records, key=lambda r: self._get_temp_min(r))

        groups = []
        current_group = None

        for record in sorted_records:
            phase = self._get_phase(record)
            tmin = self._get_temp_min(record)
            tmax = self._get_temp_max(record)

            # Check if we can continue the current group
            if (
                current_group
                and current_group.phase == phase
                and tmin <= current_group.tmax + self.config.gap_tolerance_k
            ):
                # Add to current group
                current_group.records.append(record)
                current_group.tmax = max(current_group.tmax, tmax)
            else:
                # Start new group
                if current_group:
                    groups.append(current_group)

                current_group = RecordGroup(
                    phase=phase,
                    tmin=max(tmin, target_min),
                    tmax=min(tmax, target_max),
                    records=[record],
                    is_first_in_phase=len([g for g in groups if g.phase == phase]) == 0,
                )

        # Add the last group
        if current_group:
            groups.append(current_group)

        return groups

    def _optimize_phase_group(
        self, group: RecordGroup, all_records: pd.DataFrame, is_elemental: bool
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Optimize a single phase group for minimal record count.

        Attempts to replace multiple records with fewer records or virtual records.
        """
        if len(group.records) <= 1:
            return group.records

        logger.debug(
            f"[OptimalRecordSelector] Optimizing phase '{group}' group: "
            f"{len(group.records)} records covering {group.tmin}-{group.tmax}K"
        )

        # Strategy 1: Look for single record covering the entire range
        covering_records = self._find_covering_records(
            all_records, group.phase, group.tmin, group.tmax
        )

        valid_covering = self._filter_by_constraints(
            covering_records, is_elemental, group.is_first_in_phase
        )

        if valid_covering:
            # Select the best covering record (highest reliability, widest range)
            best_record = min(
                valid_covering, key=lambda r: self._get_reliability_class(r)
            )
            logger.debug(
                f"[OptimalRecordSelector] Found single covering record for phase '{group.phase}'"
            )
            return [best_record]

        # Strategy 2: Try virtual merging of contiguous records
        if self._can_merge_virtually(group.records):
            virtual_record = self._create_virtual_record(group.records)
            logger.debug(
                f"[OptimalRecordSelector] Created virtual record for phase '{group.phase}': "
                f"{virtual_record.merged_tmin}-{virtual_record.merged_tmax}K"
            )
            return [virtual_record]

        # Strategy 3: Try to reduce record count by replacing with better alternatives
        optimized_records = self._reduce_record_count(group, all_records, is_elemental)

        if len(optimized_records) < len(group.records):
            reduction = len(group.records) - len(optimized_records)
            logger.debug(
                f"[OptimalRecordSelector] Reduced phase '{group.phase}' records by {reduction}: "
                f"{len(group.records)} → {len(optimized_records)}"
            )
            return optimized_records

        # No optimization possible
        logger.debug(
            f"[OptimalRecordSelector] Phase '{group.phase}' group already optimal"
        )
        return group.records

    def _find_covering_records(
        self, all_records: pd.DataFrame, phase: str, tmin: float, tmax: float
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """Find records that completely cover the given temperature range."""
        covering = []

        for _, record in all_records.iterrows():
            if self._get_phase(record) == phase:
                record_tmin = self._get_temp_min(record)
                record_tmax = self._get_temp_max(record)

                if record_tmin <= tmin and record_tmax >= tmax:
                    covering.append(record)

        return covering

    def _filter_by_constraints(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        is_elemental: bool,
        is_first_in_phase: bool,
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Filter records by thermodynamic constraints.

        For complex compounds (is_elemental=False), the first record of each phase
        must have non-zero H298 and S298 values.
        """
        filtered = []

        for record in records:
            # Check base data requirements for complex compounds
            if not is_elemental and is_first_in_phase:
                h298 = self._get_h298(record)
                s298 = self._get_s298(record)

                # Allow zero values with warning, but prefer non-zero
                if h298 == 0 or s298 == 0:
                    logger.debug(
                        f"[OptimalRecordSelector] Skipping record with zero base data: "
                        f"H298={h298}, S298={s298}"
                    )
                    continue

            filtered.append(record)

        return filtered

    def _can_merge_virtually(
        self, records: List[Union[pd.Series, DatabaseRecord]]
    ) -> bool:
        """
        Check if records can be virtually merged.

        Conditions for virtual merging:
        1. Same phase
        2. Contiguous or overlapping temperature ranges (gap ≤ tolerance)
        3. Identical Shomate coefficients (within tolerance)
        4. Same base data (H298, S298) for all records
        """
        if len(records) < 2:
            return False

        # Check same phase
        phases = {self._get_phase(r) for r in records}
        if len(phases) != 1:
            return False

        # Check temperature continuity
        sorted_records = sorted(records, key=lambda r: self._get_temp_min(r))
        for i in range(1, len(sorted_records)):
            prev_tmax = self._get_temp_max(sorted_records[i - 1])
            curr_tmin = self._get_temp_min(sorted_records[i])

            if curr_tmin > prev_tmax + self.config.gap_tolerance_k:
                return False

        # Check identical Shomate coefficients
        base_coeffs = self._get_shomate_coeffs(records[0])
        for record in records[1:]:
            coeffs = self._get_shomate_coeffs(record)
            if not self._coeffs_equal(base_coeffs, coeffs):
                return False

        # Check same base data
        base_h298 = self._get_h298(records[0])
        base_s298 = self._get_s298(records[0])
        for record in records[1:]:
            if (
                self._get_h298(record) != base_h298
                or self._get_s298(record) != base_s298
            ):
                return False

        return True

    def _create_virtual_record(
        self, records: List[Union[pd.Series, DatabaseRecord]]
    ) -> VirtualRecord:
        """Create a virtual record by merging multiple physical records."""
        # Convert to DatabaseRecord objects if they are pandas Series
        db_records = []
        for record in records:
            if isinstance(record, pd.Series):
                db_record = self._series_to_database_record(record)
            else:
                db_record = record
            db_records.append(db_record)

        # Create cache key
        record_ids = [id(r) for r in db_records]
        cache_key = f"virtual_{'_'.join(map(str, sorted(record_ids)))}"

        # Check cache
        if cache_key in self._virtual_record_cache:
            return self._virtual_record_cache[cache_key]

        # Create new virtual record
        virtual_record = VirtualRecord(source_records=db_records)

        # Cache the result
        if len(self._virtual_record_cache) < self.config.max_virtual_records:
            self._virtual_record_cache[cache_key] = virtual_record

        return virtual_record

    def _reduce_record_count(
        self, group: RecordGroup, all_records: pd.DataFrame, is_elemental: bool
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Reduce record count by finding better alternative combinations.

        This method tries to replace multiple short records with fewer
        longer records while maintaining coverage.
        New strategy: prefer records with gaps < 100K to find better combinations.
        """
        if len(group.records) <= 2:
            return group.records

        # Strategy 1: Try to find alternative records from database with smaller gaps
        optimized_from_db = self._find_optimal_combination_from_db(
            group, all_records, is_elemental
        )
        if optimized_from_db and len(optimized_from_db) < len(group.records):
            logger.debug(
                f"[OptimalRecordSelector] Found better combination from DB: "
                f"{len(group.records)} → {len(optimized_from_db)} records"
            )
            return optimized_from_db

        # Strategy 2: Original greedy approach with current records
        sorted_records = sorted(
            group.records, key=lambda r: self._get_reliability_class(r)
        )

        # Try to build coverage with minimal records
        optimized = []
        current_coverage = group.tmin

        while current_coverage < group.tmax and sorted_records:
            # Find the best record that extends coverage
            best_record = None
            best_extension = 0

            for record in sorted_records:
                record_tmin = self._get_temp_min(record)
                record_tmax = self._get_temp_max(record)

                if record_tmin <= current_coverage + self.config.gap_tolerance_k:
                    extension = min(record_tmax, group.tmax) - current_coverage
                    if extension > best_extension:
                        best_extension = extension
                        best_record = record

            if best_record is not None:
                optimized.append(best_record)
                current_coverage = min(self._get_temp_max(best_record), group.tmax)
                sorted_records.remove(best_record)
            else:
                # Can't extend coverage - add remaining record with smallest gap
                if sorted_records:
                    next_record = min(
                        sorted_records, key=lambda r: self._get_temp_min(r)
                    )
                    optimized.append(next_record)
                    current_coverage = self._get_temp_max(next_record)
                    sorted_records.remove(next_record)
                else:
                    break

        return optimized if len(optimized) < len(group.records) else group.records

    def _find_optimal_combination_from_db(
        self, group: RecordGroup, all_records: pd.DataFrame, is_elemental: bool
    ) -> Optional[List[Union[pd.Series, DatabaseRecord]]]:
        """
        Find optimal combination of records from database with minimal gaps.

        Searches for records that:
        1. Cover the target range
        2. Have gaps < 100K between consecutive records
        3. Minimize total number of records
        """
        MAX_GAP = 100.0  # Maximum acceptable gap between records

        # Get all relevant records for this phase
        phase_records = []
        for _, record in all_records.iterrows():
            if self._get_phase(record) != group.phase:
                continue

            record_tmin = self._get_temp_min(record)
            record_tmax = self._get_temp_max(record)

            # Only consider records that overlap with our target range
            if record_tmax >= group.tmin and record_tmin <= group.tmax:
                phase_records.append(record)

        if not phase_records:
            return None

        # Sort by temperature
        phase_records.sort(key=lambda r: self._get_temp_min(r))

        # Try to build optimal coverage using dynamic programming approach
        best_combination = None
        min_count = float("inf")

        # Simple greedy approach: start from records that cover tmin
        for start_record in phase_records:
            start_tmin = self._get_temp_min(start_record)
            start_tmax = self._get_temp_max(start_record)

            # Must cover the start of range
            if start_tmin > group.tmin + self.config.gap_tolerance_k:
                continue

            # Try building combination starting from this record
            combination = [start_record]
            current_coverage = start_tmax

            # Build coverage by selecting records with minimal gaps
            while current_coverage < group.tmax - self.config.gap_tolerance_k:
                # Find next best record with gap < MAX_GAP
                next_record = None
                min_gap = float("inf")
                max_extension = 0

                for record in phase_records:
                    record_tmin = self._get_temp_min(record)
                    record_tmax = self._get_temp_max(record)

                    # Skip if already used
                    if any(self._records_equal(record, r) for r in combination):
                        continue

                    # Calculate gap
                    gap = record_tmin - current_coverage

                    # Skip if gap is too large or record doesn't extend coverage
                    if gap > MAX_GAP or record_tmax <= current_coverage:
                        continue

                    # Prefer records with smaller gaps and larger extensions
                    extension = record_tmax - current_coverage
                    if gap <= min_gap:
                        if gap < min_gap or extension > max_extension:
                            min_gap = gap
                            max_extension = extension
                            next_record = record

                if next_record is not None:
                    combination.append(next_record)
                    current_coverage = self._get_temp_max(next_record)
                else:
                    # Can't continue this path
                    break

            # Check if this combination covers the full range
            if current_coverage >= group.tmax - self.config.gap_tolerance_k:
                # Validate constraints
                valid_combination = self._filter_by_constraints(
                    combination, is_elemental, group.is_first_in_phase
                )

                if valid_combination and len(valid_combination) < min_count:
                    min_count = len(valid_combination)
                    best_combination = valid_combination

        return best_combination

    def _records_equal(
        self, r1: Union[pd.Series, DatabaseRecord], r2: Union[pd.Series, DatabaseRecord]
    ) -> bool:
        """Check if two records are the same."""
        try:
            rowid1 = r1.rowid if hasattr(r1, "rowid") else r1.get("rowid")
            rowid2 = r2.rowid if hasattr(r2, "rowid") else r2.get("rowid")
            return rowid1 == rowid2
        except:
            # Fallback: compare by temperature and phase
            return (
                self._get_temp_min(r1) == self._get_temp_min(r2)
                and self._get_temp_max(r1) == self._get_temp_max(r2)
                and self._get_phase(r1) == self._get_phase(r2)
            )

    def _ensure_phase_transition_coverage(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        target_range: Tuple[float, float],
        melting: Optional[float],
        boiling: Optional[float],
        all_available_records: pd.DataFrame,
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Ensure that phase transition temperatures are properly covered.

        Adds records if necessary to cover melting and boiling points
        within the specified tolerance.
        """
        if not melting and not boiling:
            return records

        target_min, target_max = target_range
        result = list(records)

        # Check melting point coverage
        if melting and target_min <= melting <= target_max:
            covering_record = self._find_record_covering_temperature(result, melting)
            if covering_record is None:
                # Need to add a record for melting point
                transition_record = self._find_best_record_for_transition(
                    all_available_records, melting, self.config.transition_tolerance_k
                )
                if transition_record is not None:
                    result = self._insert_record_in_order(result, transition_record)
                    logger.debug(
                        f"[OptimalRecordSelector] Added record for melting point {melting}K"
                    )

        # Check boiling point coverage
        if boiling and target_min <= boiling <= target_max:
            covering_record = self._find_record_covering_temperature(result, boiling)
            if covering_record is None:
                # Need to add a record for boiling point
                transition_record = self._find_best_record_for_transition(
                    all_available_records, boiling, self.config.transition_tolerance_k
                )
                if transition_record is not None:
                    result = self._insert_record_in_order(result, transition_record)
                    logger.debug(
                        f"[OptimalRecordSelector] Added record for boiling point {boiling}K"
                    )

        return result

    def _validate_final_selection(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        original_records: List[Union[pd.Series, DatabaseRecord]],
        target_range: Tuple[float, float],
        melting: Optional[float],
        boiling: Optional[float],
        is_elemental: bool,
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """
        Perform final validation of the selected records.

        Checks that all constraints are satisfied:
        1. Complete temperature coverage
        2. Valid phase sequence
        3. Base data requirements
        """
        if not records:
            return records

        target_min, target_max = target_range

        # Validate temperature coverage
        if not self._validate_temperature_coverage(records, target_min, target_max):
            logger.warning(
                "[OptimalRecordSelector] Temperature coverage validation failed"
            )
            # Return original records if validation fails
            return original_records

        # Validate phase sequence
        if not self._validate_phase_sequence(records):
            logger.warning("[OptimalRecordSelector] Phase sequence validation failed")
            return original_records

        # Validate base data for complex compounds
        if not is_elemental and not self._validate_base_data(records):
            logger.warning("[OptimalRecordSelector] Base data validation failed")
            return original_records

        return records

    def _calculate_selection_score(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        target_range: Tuple[float, float],
        melting: Optional[float],
        boiling: Optional[float],
    ) -> OptimizationScore:
        """Calculate optimization score for a selection of records."""
        if not records:
            return OptimizationScore(0.0, 0.0, 0.0, 0.0)

        n_records = len(records)
        avg_reliability = np.mean([self._get_reliability_class(r) for r in records])
        transition_coverage = self._calculate_transition_coverage(
            records, melting, boiling
        )

        return OptimizationScore.calculate(
            n_records, avg_reliability, transition_coverage, self.config
        )

    # Helper methods for extracting data from different record types
    def _get_phase(self, record: Union[pd.Series, DatabaseRecord]) -> str:
        """Get phase from record."""
        if hasattr(record, "Phase"):
            return record.Phase
        elif hasattr(record, "phase"):
            return record.phase
        elif "Phase" in record:
            return record["Phase"]
        elif "phase" in record:
            return record["phase"]
        return "unknown"

    def _get_temp_min(self, record: Union[pd.Series, DatabaseRecord]) -> float:
        """Get minimum temperature from record."""
        if hasattr(record, "Tmin"):
            return record.Tmin
        elif hasattr(record, "tmin"):
            return record.tmin
        elif "Tmin" in record:
            return record["Tmin"]
        elif "tmin" in record:
            return record["tmin"]
        return 0.0

    def _get_temp_max(self, record: Union[pd.Series, DatabaseRecord]) -> float:
        """Get maximum temperature from record."""
        if hasattr(record, "Tmax"):
            return record.Tmax
        elif hasattr(record, "tmax"):
            return record.tmax
        elif "Tmax" in record:
            return record["Tmax"]
        elif "tmax" in record:
            return record["tmax"]
        return 0.0

    def _get_reliability_class(self, record: Union[pd.Series, DatabaseRecord]) -> float:
        """Get reliability class from record."""
        if hasattr(record, "ReliabilityClass"):
            return record.ReliabilityClass
        elif hasattr(record, "reliability_class"):
            return record.reliability_class
        elif "ReliabilityClass" in record:
            return record["ReliabilityClass"]
        elif "reliability_class" in record:
            return record["reliability_class"]
        return 3.0  # Worst class as default

    def _get_h298(self, record: Union[pd.Series, DatabaseRecord]) -> float:
        """Get H298 value from record."""
        if hasattr(record, "H298"):
            return record.H298
        elif hasattr(record, "h298"):
            return record.h298
        elif "H298" in record:
            return record["H298"]
        elif "h298" in record:
            return record["h298"]
        return 0.0

    def _get_s298(self, record: Union[pd.Series, DatabaseRecord]) -> float:
        """Get S298 value from record."""
        if hasattr(record, "S298"):
            return record.S298
        elif hasattr(record, "s298"):
            return record.s298
        elif "S298" in record:
            return record["S298"]
        elif "s298" in record:
            return record["s298"]
        return 0.0

    def _get_shomate_coeffs(
        self, record: Union[pd.Series, DatabaseRecord]
    ) -> List[float]:
        """Get Shomate coefficients from record."""
        coeffs = []
        for coeff_name in ["f1", "f2", "f3", "f4", "f5", "f6"]:
            if hasattr(record, coeff_name):
                coeffs.append(getattr(record, coeff_name))
            elif coeff_name in record:
                coeffs.append(record[coeff_name])
            else:
                coeffs.append(0.0)
        return coeffs

    def _coeffs_equal(self, coeffs1: List[float], coeffs2: List[float]) -> bool:
        """Check if two sets of coefficients are equal within tolerance."""
        if len(coeffs1) != len(coeffs2):
            return False
        return all(
            abs(c1 - c2) <= self.config.coeffs_comparison_tolerance
            for c1, c2 in zip(coeffs1, coeffs2)
        )

    def _series_to_database_record(self, series: pd.Series) -> DatabaseRecord:
        """Convert pandas Series to DatabaseRecord."""
        # This is a simplified conversion - in practice, you might need
        # to handle the conversion more carefully based on your exact data structure
        return DatabaseRecord(**series.to_dict())

    def _find_record_covering_temperature(
        self, records: List[Union[pd.Series, DatabaseRecord]], temperature: float
    ) -> Optional[Union[pd.Series, DatabaseRecord]]:
        """Find a record that covers the given temperature."""
        for record in records:
            if self._get_temp_min(record) <= temperature <= self._get_temp_max(record):
                return record
        return None

    def _find_best_record_for_transition(
        self, all_records: pd.DataFrame, transition_temp: float, tolerance: float
    ) -> Optional[Union[pd.Series, DatabaseRecord]]:
        """Find the best record for covering a phase transition."""
        candidates = []

        for _, record in all_records.iterrows():
            tmin = self._get_temp_min(record)
            tmax = self._get_temp_max(record)

            if (
                tmin <= transition_temp + tolerance
                and tmax >= transition_temp - tolerance
            ):
                candidates.append(record)

        if not candidates:
            return None

        # Select the best candidate (highest reliability, widest range)
        return min(candidates, key=lambda r: self._get_reliability_class(r))

    def _insert_record_in_order(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        new_record: Union[pd.Series, DatabaseRecord],
    ) -> List[Union[pd.Series, DatabaseRecord]]:
        """Insert a record into the list maintaining temperature order."""
        result = list(records)
        new_tmin = self._get_temp_min(new_record)

        # Find insertion point
        insert_pos = 0
        for i, record in enumerate(result):
            if self._get_temp_min(record) > new_tmin:
                insert_pos = i
                break
            insert_pos = i + 1

        result.insert(insert_pos, new_record)
        return result

    def _validate_temperature_coverage(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        target_min: float,
        target_max: float,
    ) -> bool:
        """Validate that records completely cover the target temperature range."""
        if not records:
            return False

        # Sort by temperature
        sorted_records = sorted(records, key=lambda r: self._get_temp_min(r))

        # Check first record covers start
        if (
            self._get_temp_min(sorted_records[0])
            > target_min + self.config.gap_tolerance_k
        ):
            return False

        # Check coverage continuity only for records within or overlapping target range
        current_max = self._get_temp_max(sorted_records[0])
        for record in sorted_records[1:]:
            record_tmin = self._get_temp_min(record)
            record_tmax = self._get_temp_max(record)

            # Stop checking if we've covered the target range
            if current_max >= target_max - self.config.gap_tolerance_k:
                break

            # Only check gap if this record is needed for coverage
            if record_tmin <= target_max:
                if record_tmin > current_max + self.config.gap_tolerance_k:
                    return False
                current_max = max(current_max, record_tmax)

        # Check final coverage
        return current_max >= target_max - self.config.gap_tolerance_k

    def _validate_phase_sequence(
        self, records: List[Union[pd.Series, DatabaseRecord]]
    ) -> bool:
        """Validate that phase sequence is physically correct."""
        if not records:
            return True

        # Expected phase sequence: s -> l -> g
        phase_order = {"s": 0, "l": 1, "g": 2}
        previous_order = -1

        for record in records:
            phase = self._get_phase(record)
            if phase in phase_order:
                current_order = phase_order[phase]
                if current_order < previous_order:
                    return False
                previous_order = current_order

        return True

    def _validate_base_data(
        self, records: List[Union[pd.Series, DatabaseRecord]]
    ) -> bool:
        """Validate that complex compounds have proper base data."""
        phase_counts = {}
        for record in records:
            phase = self._get_phase(record)
            if phase not in phase_counts:
                phase_counts[phase] = 0
            phase_counts[phase] += 1

        # Check each phase's first record has non-zero base data
        for record in records:
            phase = self._get_phase(record)
            if phase_counts.get(phase, 0) > 0:
                phase_counts[phase] -= 1
                if phase_counts[phase] == 0:  # This is the last (first in order) record
                    if self._get_h298(record) == 0 or self._get_s298(record) == 0:
                        return False

        return True

    def _calculate_transition_coverage(
        self,
        records: List[Union[pd.Series, DatabaseRecord]],
        melting: Optional[float],
        boiling: Optional[float],
    ) -> float:
        """Calculate how well phase transitions are covered."""
        if not melting and not boiling:
            return 1.0

        covered_transitions = 0
        total_transitions = 0

        if melting:
            total_transitions += 1
            if self._find_record_covering_temperature(records, melting) is not None:
                covered_transitions += 1

        if boiling:
            total_transitions += 1
            if self._find_record_covering_temperature(records, boiling) is not None:
                covered_transitions += 1

        return covered_transitions / total_transitions if total_transitions > 0 else 1.0
