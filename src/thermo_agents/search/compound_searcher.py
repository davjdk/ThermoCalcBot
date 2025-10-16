"""
Compound searcher for thermodynamic database.

This module provides the main search functionality for individual chemical compounds,
coordinating SQL generation and database execution to find thermodynamic data.
"""

from typing import List, Tuple, Optional, Dict, Any
import logging
import time
from datetime import datetime

from .sql_builder import SQLBuilder, FilterPriorities
from .database_connector import DatabaseConnector
from ..models.search import (
    DatabaseRecord,
    CompoundSearchResult,
    SearchStatistics,
    CoverageStatus,
    SearchStrategy,
    SearchPipeline,
    FilterOperation
)

logger = logging.getLogger(__name__)


class CompoundSearcher:
    """
    Search engine for individual chemical compounds in thermodynamic database.

    Coordinates SQL generation through SQLBuilder and database execution through
    DatabaseConnector to provide comprehensive compound search functionality.
    """

    def __init__(
        self,
        sql_builder: SQLBuilder,
        db_connector: DatabaseConnector,
        session_logger: Optional[Any] = None
    ):
        """
        Initialize compound searcher.

        Args:
            sql_builder: SQL builder instance for query generation
            db_connector: Database connector for query execution
            session_logger: Optional session logger for detailed logging
        """
        self.sql_builder = sql_builder
        self.db_connector = db_connector
        self.session_logger = session_logger  # НОВОЕ
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def search_compound(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = 100
    ) -> CompoundSearchResult:
        """
        Search for a chemical compound in the thermodynamic database.

        This is the main search method that coordinates SQL generation and
        database execution to find matching records.

        Args:
            formula: Chemical formula (e.g., "H2O", "HCl", "TiO2")
            temperature_range: Optional temperature range (tmin, tmax) in Kelvin
            phase: Optional phase filter ('s', 'l', 'g', 'aq', etc.)
            limit: Maximum number of results to return

        Returns:
            CompoundSearchResult with found records and metadata
        """
        start_time = time.time()
        self.logger.info(f"Searching for compound: {formula}")

        # НОВОЕ: Логирование начала поиска
        if self.session_logger:
            self.session_logger.log_info(f"Начало поиска для {formula}")

        # Initialize result
        result = CompoundSearchResult(
            compound_formula=formula,
            search_parameters={
                "temperature_range": temperature_range,
                "phase": phase,
                "limit": limit
            }
        )

        try:
            # Generate SQL query
            query, params = self.sql_builder.build_compound_search_query(
                formula=formula,
                temperature_range=temperature_range,
                phase=phase,
                limit=limit
            )

            self.logger.debug(f"Generated SQL query: {query[:100]}...")

            # НОВОЕ: Логирование SQL запроса
            if self.session_logger:
                self.session_logger.log_info("")
                separator = "═" * 63
                self.session_logger.log_info(separator)
                self.session_logger.log_info(f"ПОИСК: {formula}")
                self.session_logger.log_info("─" * 63)
                self.session_logger.log_info("SQL запрос:")
                # Форматируем SQL для красивого вывода
                formatted_query = query.replace("SELECT", "  SELECT").replace("FROM", "\n  FROM").replace("WHERE", "\n  WHERE").replace("ORDER BY", "\n  ORDER BY").replace("LIMIT", "\n  LIMIT")
                self.session_logger.log_info(formatted_query)
                if params:
                    self.session_logger.log_info(f"Параметры: {params}")

            # Execute query
            raw_results = self.db_connector.execute_query(query, params)

            # Parse results into DatabaseRecord objects
            records = [self._parse_record(row) for row in raw_results]

            # Update result with found records
            result.records_found = records

            # Calculate statistics
            result.filter_statistics = self._calculate_statistics(records)

            # Determine coverage status
            result.coverage_status = self._determine_coverage_status(
                records, temperature_range
            )

            # Add warnings if needed
            self._add_warnings(result, records, temperature_range)

            # Calculate execution time
            result.execution_time_ms = (time.time() - start_time) * 1000

            # НОВОЕ: Логирование результатов поиска
            if self.session_logger:
                self.session_logger.log_info(f"Найдено записей: {len(records)}")
                self.session_logger.log_info(f"Время выполнения: {result.execution_time_ms:.1f} мс")
                separator = "═" * 63
                self.session_logger.log_info(separator)

            self.logger.info(
                f"Search completed: {len(records)} records found in "
                f"{result.execution_time_ms:.2f}ms"
            )

            return result

        except Exception as e:
            self.logger.error(f"Search failed for {formula}: {e}")
            result.add_warning(f"Search failed: {str(e)}")
            result.execution_time_ms = (time.time() - start_time) * 1000
            return result

    def search_compound_with_pipeline(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = 100
    ) -> Tuple[CompoundSearchResult, SearchPipeline]:
        """
        Search compound with detailed pipeline tracking.

        This method provides detailed information about each filtering step
        for debugging and optimization purposes.

        Args:
            formula: Chemical formula
            temperature_range: Optional temperature range in Kelvin
            phase: Optional phase filter
            limit: Maximum results

        Returns:
            Tuple of (CompoundSearchResult, SearchPipeline)
        """
        start_time = time.time()
        pipeline = SearchPipeline(
            initial_query=f"formula={formula}, temp_range={temperature_range}, phase={phase}"
        )

        # Step 1: Initial formula search (no temperature/phase filtering)
        try:
            formula_query, formula_params = self.sql_builder.build_compound_search_query(
                formula=formula,
                temperature_range=None,
                phase=None,
                limit=limit * 5  # Get more for filtering
            )

            raw_results = self.db_connector.execute_query(formula_query, formula_params)
            pipeline.initial_results = len(raw_results)

            pipeline.add_operation(FilterOperation(
                operation_type="formula_search",
                input_count=0,  # No input for initial search
                output_count=len(raw_results),
                filter_criteria={"formula": formula}
            ))

        except Exception as e:
            self.logger.error(f"Initial formula search failed: {e}")
            pipeline.initial_results = 0
            raw_results = []

        # Step 2: Temperature filtering (if specified)
        if temperature_range and raw_results:
            filtered_by_temp = [
                record for record in raw_results
                if self._record_in_temperature_range(record, temperature_range)
            ]

            pipeline.add_operation(FilterOperation(
                operation_type="temperature_filter",
                input_count=len(raw_results),
                output_count=len(filtered_by_temp),
                filter_criteria={"temperature_range": temperature_range}
            ))

            raw_results = filtered_by_temp

        # Step 3: Phase filtering (if specified)
        if phase and raw_results:
            filtered_by_phase = [
                record for record in raw_results
                if str(record.get('Phase', '')).lower() == phase.lower()
            ]

            pipeline.add_operation(FilterOperation(
                operation_type="phase_filter",
                input_count=len(raw_results),
                output_count=len(filtered_by_phase),
                filter_criteria={"phase": phase}
            ))

            raw_results = filtered_by_phase

        # Step 4: Priority sorting and limit
        if raw_results:
            # Apply SQL builder's sorting logic
            sorted_results = self._apply_priority_sorting(raw_results)
            limited_results = sorted_results[:limit]

            pipeline.add_operation(FilterOperation(
                operation_type="priority_sorting_and_limit",
                input_count=len(sorted_results),
                output_count=len(limited_results),
                filter_criteria={"limit": limit}
            ))

            raw_results = limited_results

        # Parse final results
        records = [self._parse_record(row) for row in raw_results]
        pipeline.final_results = len(records)
        pipeline.total_time_ms = (time.time() - start_time) * 1000

        # Create search result
        result = CompoundSearchResult(
            compound_formula=formula,
            records_found=records,
            search_parameters={
                "temperature_range": temperature_range,
                "phase": phase,
                "limit": limit
            },
            filter_statistics=self._calculate_statistics(records),
            coverage_status=self._determine_coverage_status(records, temperature_range),
            execution_time_ms=pipeline.total_time_ms
        )

        self._add_warnings(result, records, temperature_range)

        return result, pipeline

    def get_search_strategy(self, formula: str) -> SearchStrategy:
        """
        Get search strategy recommendations for a formula.

        Args:
            formula: Chemical formula to analyze

        Returns:
            SearchStrategy with recommendations
        """
        strategy_dict = self.sql_builder.suggest_search_strategy(formula)
        return SearchStrategy(**strategy_dict)

    def count_compound_records(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Count records matching criteria without retrieving full data.

        Args:
            formula: Chemical formula
            temperature_range: Optional temperature range
            phase: Optional phase filter

        Returns:
            Dictionary with count statistics
        """
        try:
            query, params = self.sql_builder.build_compound_count_query(
                formula=formula,
                temperature_range=temperature_range,
                phase=phase
            )

            result = self.db_connector.execute_single_row(query, params)
            return result if result else {}

        except Exception as e:
            self.logger.error(f"Count query failed for {formula}: {e}")
            return {}

    def get_temperature_statistics(self, formula: str) -> Dict[str, Any]:
        """
        Get temperature range statistics for a compound.

        Args:
            formula: Chemical formula

        Returns:
            Dictionary with temperature statistics
        """
        try:
            query, params = self.sql_builder.build_temperature_range_stats_query(formula)
            result = self.db_connector.execute_single_row(query, params)
            return result if result else {}

        except Exception as e:
            self.logger.error(f"Temperature stats query failed for {formula}: {e}")
            return {}

    def _parse_record(self, row: Dict[str, Any]) -> DatabaseRecord:
        """
        Parse database row into DatabaseRecord object.

        Args:
            row: Database row as dictionary

        Returns:
            DatabaseRecord object
        """
        # Handle column name variations and data cleaning
        processed_row = {}

        for key, value in row.items():
            # Handle common column name variations
            clean_key = key.strip().lower()

            # Map to expected field names
            if clean_key == 'id' or clean_key == 'rowid':
                processed_row['id'] = value
            elif clean_key in ['formula', 'compound']:
                processed_row['formula'] = str(value).strip() if value else None
            elif clean_key == 'phase':
                processed_row['phase'] = str(value).strip() if value else None
            elif clean_key in ['tmin', 'temp_min']:
                processed_row['tmin'] = float(value) if value is not None else None
            elif clean_key in ['tmax', 'temp_max']:
                processed_row['tmax'] = float(value) if value is not None else None
            elif clean_key in ['h298', 'h_298', 'enthalpy']:
                processed_row['h298'] = float(value) if value is not None else None
            elif clean_key in ['s298', 's_298', 'entropy']:
                processed_row['s298'] = float(value) if value is not None else None
            elif clean_key in ['tmelt', 'melting_point', 't_melt']:
                processed_row['tmelt'] = float(value) if value is not None else None
            elif clean_key in ['tboil', 'boiling_point', 't_boil']:
                processed_row['tboil'] = float(value) if value is not None else None
            elif clean_key in ['reliability_class', 'reliability', 'class']:
                processed_row['reliability_class'] = int(value) if value is not None else None
            elif clean_key.startswith('f') and clean_key[1:].isdigit():
                # Heat capacity coefficients f1-f6
                processed_row[clean_key] = float(value) if value is not None else None
            else:
                # Keep other fields as-is (for extra="allow" in Pydantic model)
                processed_row[key] = value

        return DatabaseRecord(**processed_row)

    def _calculate_statistics(self, records: List[DatabaseRecord]) -> SearchStatistics:
        """
        Calculate search statistics from found records.

        Args:
            records: List of database records

        Returns:
            SearchStatistics object
        """
        if not records:
            return SearchStatistics()

        # Basic counts
        phases = set()
        reliability_classes = []
        temperatures = []

        # Phase distribution
        phase_dist = {}
        reliability_dist = {}

        for record in records:
            # Phases
            if record.phase:
                phases.add(record.phase)
                phase_dist[record.phase] = phase_dist.get(record.phase, 0) + 1

            # Reliability classes
            if record.reliability_class is not None:
                reliability_classes.append(record.reliability_class)
                reliability_dist[record.reliability_class] = (
                    reliability_dist.get(record.reliability_class, 0) + 1
                )

            # Temperature ranges
            if record.tmin is not None and record.tmax is not None:
                temperatures.append((record.tmin, record.tmax))

        # Temperature statistics
        min_temp = min(t[0] for t in temperatures) if temperatures else None
        max_temp = max(t[1] for t in temperatures) if temperatures else None
        avg_range = sum(t[1] - t[0] for t in temperatures) / len(temperatures) if temperatures else None

        return SearchStatistics(
            total_records=len(records),
            unique_phases=len(phases),
            min_temperature=min_temp,
            max_temperature=max_temp,
            avg_temperature_range=avg_range,
            avg_reliability=sum(reliability_classes) / len(reliability_classes) if reliability_classes else None,
            phase_distribution=phase_dist,
            reliability_distribution=reliability_dist
        )

    def _determine_coverage_status(
        self,
        records: List[DatabaseRecord],
        temperature_range: Optional[Tuple[float, float]]
    ) -> CoverageStatus:
        """
        Determine coverage status based on found records.

        Args:
            records: List of found records
            temperature_range: Requested temperature range

        Returns:
            CoverageStatus enum value
        """
        if not records:
            return CoverageStatus.NONE

        if not temperature_range:
            # No temperature constraint, any records mean full coverage
            return CoverageStatus.FULL if records else CoverageStatus.NONE

        # Check if requested temperature range is covered
        requested_min, requested_max = temperature_range

        # Find combined temperature coverage
        covered_temps = []
        for record in records:
            if record.tmin is not None and record.tmax is not None:
                covered_temps.append((record.tmin, record.tmax))

        if not covered_temps:
            return CoverageStatus.PARTIAL

        # Check if full range is covered
        min_covered = min(t[0] for t in covered_temps)
        max_covered = max(t[1] for t in covered_temps)

        if min_covered <= requested_min and max_covered >= requested_max:
            return CoverageStatus.FULL
        elif covered_temps:
            return CoverageStatus.PARTIAL
        else:
            return CoverageStatus.NONE

    def _add_warnings(
        self,
        result: CompoundSearchResult,
        records: List[DatabaseRecord],
        temperature_range: Optional[Tuple[float, float]]
    ) -> None:
        """
        Add warnings to search result based on analysis.

        Args:
            result: Search result to modify
            records: Found records
            temperature_range: Requested temperature range
        """
        if not records:
            result.add_warning("No records found for the specified criteria")
            return

        # Check for low reliability data
        low_reliability = [r for r in records if r.reliability_class and r.reliability_class > 3]
        if low_reliability:
            result.add_warning(f"Found {len(low_reliability)} records with low reliability (>3)")

        # Check temperature coverage
        if temperature_range:
            coverage_status = self._determine_coverage_status(records, temperature_range)
            if coverage_status == CoverageStatus.PARTIAL:
                result.add_warning("Only partial temperature coverage available for requested range")

        # Check for missing thermodynamic data
        missing_thermo = [r for r in records if not (r.h298 and r.s298)]
        if missing_thermo:
            result.add_warning(f"Found {len(missing_thermo)} records missing standard thermodynamic data")

    def _record_in_temperature_range(
        self,
        record: Dict[str, Any],
        temperature_range: Tuple[float, float]
    ) -> bool:
        """
        Check if a database record falls within temperature range.

        Args:
            record: Database record
            temperature_range: (tmin, tmax) tuple

        Returns:
            True if record is within temperature range
        """
        tmin_req, tmax_req = temperature_range
        tmin_rec = record.get('Tmin')
        tmax_rec = record.get('Tmax')

        if tmin_rec is None or tmax_rec is None:
            return False

        return tmin_req <= tmax_rec and tmax_req >= tmin_rec

    def _apply_priority_sorting(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply priority sorting to records based on SQL builder logic.

        Args:
            records: List of database records

        Returns:
            Sorted list of records
        """
        # This is a simplified version of the SQL ORDER BY logic
        # In practice, we rely on the SQL query to do proper sorting

        def sort_key(record):
            # Primary: ReliabilityClass
            reliability = record.get('ReliabilityClass', 999)

            # Secondary: Temperature range width
            tmin = record.get('Tmin', 0) or 0
            tmax = record.get('Tmax', 0) or 0
            temp_width = tmax - tmin

            # Tertiary: Formula simplicity
            formula = str(record.get('Formula', '')).strip()
            formula_length = len(formula)

            # Quaternary: Phase priority
            phase = str(record.get('Phase', '')).lower()
            phase_priority = {'g': 0, 'l': 1, 's': 2, 'aq': 3}.get(phase, 4)

            # Quinary: Row ID for consistency
            record_id = record.get('rowid', 0)

            return (reliability, -temp_width, formula_length, phase_priority, record_id)

        return sorted(records, key=sort_key)