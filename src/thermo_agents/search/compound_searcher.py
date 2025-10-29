"""
Compound searcher for thermodynamic database.

This module provides the main search functionality for individual chemical compounds,
coordinating SQL generation and database execution to find thermodynamic data.

Техническое описание:
Основной поисковый движок для химических соединений в термодинамической базе данных.
Координирует генерацию SQL через SQLBuilder и выполнение через DatabaseConnector,
предоставляя комплексную функциональность поиска в гибридной архитектуре v2.0.

Ключевые компоненты:
- CompoundSearcher: Основной класс поиска соединений
- Интеграция с SQLBuilder для генерации запросов
- Интеграция с DatabaseConnector для выполнения запросов
- Поддержка SessionLogger для детального логирования

Основные методы CompoundSearcher:
- search_compound(): Основной метод поиска с координацией SQL и БД
- search_compound_with_pipeline(): Поиск с детальным трейсингом конвейера
- search_compound_stage1(): Stage 1 - поиск без температурных ограничений (все записи)
- search_all_phases(): Поиск всех фаз соединения с температурным покрытием
- count_compound_records(): Подсчет записей без извлечения полных данных
- get_temperature_statistics(): Статистика температурных диапазонов
- get_search_strategy(): Рекомендации по стратегии поиска

Вспомогательные методы:
- _parse_record(): Парсинг строки БД в DatabaseRecord объект
- _calculate_statistics(): Расчет статистики поиска
- _determine_coverage_status(): Определение статуса покрытия
- _add_warnings(): Добавление предупреждений в результаты
- _record_in_temperature_range(): Проверка температурного диапазона
- _apply_priority_sorting(): Применение сортировки по приоритетам
- _build_result(): Построение MultiPhaseSearchResult
- _extract_phase_transitions(): Извлечение температур фазовых переходов
- _generate_warnings(): Генерация предупреждений о покрытии

MultiPhaseSearchResult:
- Специализированный результат для поиска всех фаз
- Определение температурного покрытия
- Выявление фазовых переходов
- Анализ пробелов и перекрытий в данных
- Проверка покрытия стандартной температуры 298K

Особенности реализации:
- Координация между SQL генерацией и выполнением
- Детальное логирование операций поиска
- Поддержка распространенных веществ через CommonCompoundResolver
- Интеграция с YAML кэшем для статических данных
- Метрики производительности и статистика

Обработка результатов:
- Парсинг разнообразных форматов колонок БД
- Валидация и очистка термодинамических данных
- Расчет статистики по фазам и надежности
- Определение полного/частичного покрытия диапазона

Интеграция с логированием:
- SQL запросы и параметры
- Время выполнения операций
- Результаты поиска в структурированном виде
- Предупреждения о проблемах с данными

Стратегии поиска:
- Multi-level формула matching
- Температурная фильтрация
- Фильтрация по фазовым состояниям
- Приоритизация по надежности данных
- Управление лимитами результатов

Используется в:
- ThermoOrchestrator для поиска соединений
- FilterPipeline для получения исходных данных
- ThermodynamicCalculator для термодинамических расчетов
- Тестировании и отладке системы поиска
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..filtering.constants import (
    DEFAULT_CACHE_SIZE,
    DEFAULT_QUERY_LIMIT,
    MAX_QUERY_LIMIT,
    MAX_RELIABILITY_CLASS,
    SLOW_OPERATION_THRESHOLD_MS,
)
from ..models.search import (
    CompoundSearchResult,
    CoverageStatus,
    DatabaseRecord,
    FilterOperation,
    MultiPhaseSearchResult,
    SearchPipeline,
    SearchStatistics,
    SearchStrategy,
)
from .database_connector import DatabaseConnector
from .sql_builder import FilterPriorities, SQLBuilder

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
        session_logger: Optional[Any] = None,
        static_data_manager: Optional[Any] = None,  # Будет в Stage 04
    ):
        """
        Initialize compound searcher.

        Args:
            sql_builder: SQL builder instance for query generation
            db_connector: Database connector for query execution
            session_logger: Optional session logger for detailed logging
            static_data_manager: Optional static data manager for YAML cache
        """
        self.sql_builder = sql_builder
        self.db_connector = db_connector
        self.session_logger = session_logger  # НОВОЕ
        self.static_data_manager = static_data_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def search_compound(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        compound_names: Optional[List[str]] = None,
        ignore_temperature_range: bool = False,  # Stage 1 parameter
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
            compound_names: Optional list of compound names for additional search
            ignore_temperature_range: If True, ignores temperature limits for maximum data retrieval (Stage 1)

        Returns:
            CompoundSearchResult with found records and metadata
        """
        start_time = time.time()
        self.logger.info(f"Searching for compound: {formula}")

        # НОВОЕ: Логирование начала поиска + проверка на распространенное вещество
        if self.session_logger:
            self.session_logger.log_info(f"Начало поиска для {formula}")
            # Проверка через резолвер распространенных веществ
            if self.sql_builder.common_resolver.is_common_compound(formula):
                description = self.sql_builder.common_resolver.get_description(formula)
                self.session_logger.log_info(
                    f"⚡ Обнаружено распространенное вещество: {description}"
                )
                self.session_logger.log_info(
                    "   Используется точная логика поиска (без широких паттернов)"
                )

            # Stage 1: Log if temperature range is being ignored
            if ignore_temperature_range:
                self.session_logger.log_info(
                    "🔄 Stage 1: Игнорирование температурного диапазона для поиска всех записей"
                )
                if temperature_range:
                    self.session_logger.log_info(
                        f"   Пользовательский диапазон {temperature_range[0]:.0f}-{temperature_range[1]:.0f}K сохранен для вывода"
                    )

        # Stage 1: Determine actual temperature range for SQL query
        sql_temperature_range = None if ignore_temperature_range else temperature_range

        # Initialize result
        result = CompoundSearchResult(
            compound_formula=formula,
            search_parameters={
                "temperature_range": temperature_range,
                "phase": phase,
                "limit": limit,
                "compound_names": compound_names,
                "ignore_temperature_range": ignore_temperature_range,  # Stage 1
            },
        )

        try:
            # Generate SQL query
            query, params = self.sql_builder.build_compound_search_query(
                formula=formula,
                temperature_range=sql_temperature_range,  # Use modified range
                phase=phase,
                limit=limit,
                compound_names=compound_names,
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
                formatted_query = (
                    query.replace("SELECT", "  SELECT")
                    .replace("FROM", "\n  FROM")
                    .replace("WHERE", "\n  WHERE")
                    .replace("ORDER BY", "\n  ORDER BY")
                    .replace("LIMIT", "\n  LIMIT")
                )
                self.session_logger.log_info(formatted_query)
                if params:
                    self.session_logger.log_info(f"Параметры: {params}")

            # Execute query
            start_db_time = time.time()
            raw_results = self.db_connector.execute_query(query, params)
            db_execution_time = time.time() - start_db_time

            # Parse results into DatabaseRecord objects
            records = [self._parse_record(row) for row in raw_results]

            # НОВОЕ: Детальное логирование поиска в БД
            if self.session_logger:
                # Преобразуем записи в словари для логирования
                records_dict = [record.model_dump() for record in records]
                parameters = {
                    "formula": formula,
                    "temperature_range": temperature_range,
                    "phase": phase,
                    "limit": limit,
                }
                if compound_names:
                    parameters["compound_names"] = compound_names

                self.session_logger.log_database_search(
                    sql_query=query,
                    parameters=parameters,
                    results=records_dict,
                    execution_time=db_execution_time,
                    context=f"Searching for compound {formula}",
                )

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
                self.session_logger.log_info(
                    f"Время выполнения: {result.execution_time_ms:.1f} мс"
                )
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
        limit: int = DEFAULT_QUERY_LIMIT,
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
            formula_query, formula_params = (
                self.sql_builder.build_compound_search_query(
                    formula=formula,
                    temperature_range=None,
                    phase=None,
                    limit=limit * 5,  # Get more for filtering
                )
            )

            raw_results = self.db_connector.execute_query(formula_query, formula_params)
            pipeline.initial_results = len(raw_results)

            pipeline.add_operation(
                FilterOperation(
                    operation_type="formula_search",
                    input_count=0,  # No input for initial search
                    output_count=len(raw_results),
                    filter_criteria={"formula": formula},
                )
            )

        except Exception as e:
            self.logger.error(f"Initial formula search failed: {e}")
            pipeline.initial_results = 0
            raw_results = []

        # Step 2: Temperature filtering (if specified)
        if temperature_range and raw_results:
            filtered_by_temp = [
                record
                for record in raw_results
                if self._record_in_temperature_range(record, temperature_range)
            ]

            pipeline.add_operation(
                FilterOperation(
                    operation_type="temperature_filter",
                    input_count=len(raw_results),
                    output_count=len(filtered_by_temp),
                    filter_criteria={"temperature_range": temperature_range},
                )
            )

            raw_results = filtered_by_temp

        # Step 3: Phase filtering (if specified)
        if phase and raw_results:
            filtered_by_phase = [
                record
                for record in raw_results
                if str(record.get("Phase", "")).lower() == phase.lower()
            ]

            pipeline.add_operation(
                FilterOperation(
                    operation_type="phase_filter",
                    input_count=len(raw_results),
                    output_count=len(filtered_by_phase),
                    filter_criteria={"phase": phase},
                )
            )

            raw_results = filtered_by_phase

        # Step 4: Priority sorting and limit
        if raw_results:
            # Apply SQL builder's sorting logic
            sorted_results = self._apply_priority_sorting(raw_results)
            limited_results = sorted_results[:limit]

            pipeline.add_operation(
                FilterOperation(
                    operation_type="priority_sorting_and_limit",
                    input_count=len(sorted_results),
                    output_count=len(limited_results),
                    filter_criteria={"limit": limit},
                )
            )

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
                "limit": limit,
            },
            filter_statistics=self._calculate_statistics(records),
            coverage_status=self._determine_coverage_status(records, temperature_range),
            execution_time_ms=pipeline.total_time_ms,
        )

        self._add_warnings(result, records, temperature_range)

        return result, pipeline

    def search_compound_stage1(
        self,
        formula: str,
        user_temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        compound_names: Optional[List[str]] = None,
    ) -> CompoundSearchResult:
        """
        Stage 1: Search compound with full temperature range data retrieval.

        This method implements the core Stage 1 requirement: ignore user temperature
        limitations during database search to ensure all relevant records are found.
        The user's temperature range is preserved for result reporting.

        Args:
            formula: Chemical formula (e.g., "FeO", "H2O", "O2")
            user_temperature_range: User's original temperature range (for reporting only)
            phase: Optional phase filter
            limit: Maximum number of results to return (default increased for Stage 1)
            compound_names: Optional list of compound names for additional search

        Returns:
            CompoundSearchResult with all available records and Stage 1 metadata
        """
        self.logger.info(f"Stage 1 search for compound: {formula}")

        # Stage 1: Always use higher limit for comprehensive data retrieval
        stage1_limit = max(limit, 100)

        # Stage 1: Call main search with ignore_temperature_range=True
        result = self.search_compound(
            formula=formula,
            temperature_range=user_temperature_range,
            phase=phase,
            limit=stage1_limit,
            compound_names=compound_names,
            ignore_temperature_range=True  # Core Stage 1 logic
        )

        # Stage 1: Add specific metadata and recommendations
        if user_temperature_range:
            range_diff_note = (
                f"Запрошенный диапазон {user_temperature_range[0]:.0f}-{user_temperature_range[1]:.0f}K, "
                f"найдены записи в полном диапазоне данных"
            )
            result.add_warning(f"Stage 1: {range_diff_note}")

        # Stage 1: Add record count improvement notification
        if len(result.records_found) > 1:
            result.add_warning(f"Stage 1: Найдено {len(result.records_found)} записей (многофазный поиск)")

        # Stage 1: Log comprehensive search results
        if self.session_logger:
            self.session_logger.log_info("")
            separator = "═" * 63
            self.session_logger.log_info(separator)
            self.session_logger.log_info(f"Stage 1 ЗАВЕРШЕН: {formula}")
            self.session_logger.log_info("─" * 63)
            self.session_logger.log_info(f"📊 Найдено записей: {len(result.records_found)}")

            if result.records_found:
                min_temp = min(r.tmin for r in result.records_found)
                max_temp = max(r.tmax for r in result.records_found)
                self.session_logger.log_info(f"🌡️  Полный диапазон: {min_temp:.0f}-{max_temp:.0f}K")

                if user_temperature_range:
                    self.session_logger.log_info(
                        f"🎯 Запрошенный диапазон: {user_temperature_range[0]:.0f}-{user_temperature_range[1]:.0f}K"
                    )

                # Check if 298K data is available
                has_298K = any(r.covers_temperature(298.15) for r in result.records_found)
                if has_298K:
                    self.session_logger.log_info("✅ Данные для 298K доступны")
                else:
                    self.session_logger.log_info("⚠️  Данные для 298K отсутствуют")

            self.session_logger.log_info(separator)

        # Set Stage 1 mode and ranges on the result
        result.stage1_mode = True
        result.original_user_range = user_temperature_range

        return result

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
        phase: Optional[str] = None,
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
                formula=formula, temperature_range=temperature_range, phase=phase
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
            query, params = self.sql_builder.build_temperature_range_stats_query(
                formula
            )
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
            if clean_key == "id" or clean_key == "rowid":
                processed_row["id"] = value
            elif clean_key in ["formula", "compound"]:
                processed_row["formula"] = str(value).strip() if value else None
            elif clean_key == "phase":
                processed_row["phase"] = str(value).strip() if value else None
            elif clean_key in ["tmin", "temp_min"]:
                processed_row["tmin"] = float(value) if value is not None else None
            elif clean_key in ["tmax", "temp_max"]:
                processed_row["tmax"] = float(value) if value is not None else None
            elif clean_key in ["h298", "h_298", "enthalpy"]:
                processed_row["h298"] = float(value) if value is not None else None
            elif clean_key in ["s298", "s_298", "entropy"]:
                processed_row["s298"] = float(value) if value is not None else None
            elif clean_key in ["tmelt", "melting_point", "t_melt"]:
                processed_row["tmelt"] = float(value) if value is not None else None
            elif clean_key in ["tboil", "boiling_point", "t_boil"]:
                processed_row["tboil"] = float(value) if value is not None else None
            elif clean_key in ["reliability_class", "reliability", "class"]:
                processed_row["reliability_class"] = (
                    int(value) if value is not None else None
                )
            elif clean_key.startswith("f") and clean_key[1:].isdigit():
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
        avg_range = (
            sum(t[1] - t[0] for t in temperatures) / len(temperatures)
            if temperatures
            else None
        )

        return SearchStatistics(
            total_records=len(records),
            unique_phases=len(phases),
            min_temperature=min_temp,
            max_temperature=max_temp,
            avg_temperature_range=avg_range,
            avg_reliability=sum(reliability_classes) / len(reliability_classes)
            if reliability_classes
            else None,
            phase_distribution=phase_dist,
            reliability_distribution=reliability_dist,
        )

    def _determine_coverage_status(
        self,
        records: List[DatabaseRecord],
        temperature_range: Optional[Tuple[float, float]],
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
        temperature_range: Optional[Tuple[float, float]],
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
        low_reliability = [
            r
            for r in records
            if r.reliability_class and r.reliability_class > MAX_RELIABILITY_CLASS
        ]
        if low_reliability:
            result.add_warning(
                f"Found {len(low_reliability)} records with low reliability (>3)"
            )

        # Check temperature coverage
        if temperature_range:
            coverage_status = self._determine_coverage_status(
                records, temperature_range
            )
            if coverage_status == CoverageStatus.PARTIAL:
                result.add_warning(
                    "Only partial temperature coverage available for requested range"
                )

        # Check for missing thermodynamic data
        missing_thermo = [r for r in records if not (r.h298 and r.s298)]
        if missing_thermo:
            result.add_warning(
                f"Found {len(missing_thermo)} records missing standard thermodynamic data"
            )

    def _record_in_temperature_range(
        self, record: Dict[str, Any], temperature_range: Tuple[float, float]
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
        tmin_rec = record.get("Tmin")
        tmax_rec = record.get("Tmax")

        if tmin_rec is None or tmax_rec is None:
            return False

        return tmin_req <= tmax_rec and tmax_req >= tmin_rec

    def _apply_priority_sorting(
        self, records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
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
            reliability = record.get("ReliabilityClass", 999)

            # Secondary: Temperature range width
            tmin = record.get("Tmin", 0) or 0
            tmax = record.get("Tmax", 0) or 0
            temp_width = tmax - tmin

            # Tertiary: Formula simplicity
            formula = str(record.get("Formula", "")).strip()
            formula_length = len(formula)

            # Quaternary: Phase priority
            phase = str(record.get("Phase", "")).lower()
            phase_priority = {"g": 0, "l": 1, "s": 2, "aq": 3}.get(phase, 4)

            # Quinary: Row ID for consistency
            record_id = record.get("rowid", 0)

            return (reliability, -temp_width, formula_length, phase_priority, record_id)

        return sorted(records, key=sort_key)

    def search_all_phases(
        self,
        formula: str,
        max_temperature: float,
        compound_names: Optional[List[str]] = None,
    ) -> MultiPhaseSearchResult:
        """
        Search all phases of a compound with coverage up to max_temperature.

        Args:
            formula: Chemical formula (e.g., "H2O", "FeO")
            max_temperature: Maximum calculation temperature, K
            compound_names: Additional names for search

        Returns:
            MultiPhaseSearchResult with found records and metadata
        """
        self.logger.info(f"Поиск всех фаз для {formula}, T_max={max_temperature}K")

        # ШАГ 1: Проверка YAML кэша (приоритет)
        if self.static_data_manager and self.static_data_manager.is_available(formula):
            self.logger.info(f"⚡ Найдено в статическом кэше: {formula}")
            if self.session_logger:
                self.session_logger.log_info(f"⚡ Использован YAML кэш для {formula}")

            records = self.static_data_manager.get_compound_phases(formula)
            return self._build_result(formula, records, max_temperature)

        # ШАГ 2: Поиск в БД
        self.logger.info(f"Поиск в БД для {formula}")

        # Генерация SQL запроса для поиска всех записей вещества
        sql_query = self.sql_builder.build_compound_search_query(
            formula=formula,
            temperature_range=None,  # Ищем все записи
            phase=None,  # Все фазы
            limit=100,  # Увеличиваем лимит
            compound_names=compound_names,
        )

        # Выполнение запроса
        query, params = sql_query
        start_db_time = time.time()
        all_records_raw = self.db_connector.execute_query(query, params)
        db_execution_time = time.time() - start_db_time

        all_records = [self._parse_record(row) for row in all_records_raw]

        # НОВОЕ: Логирование поиска в БД
        if self.session_logger:
            records_dict = [record.model_dump() for record in all_records]
            parameters = {
                "formula": formula,
                "temperature_range": None,
                "phase": None,
                "limit": 100,
                "max_temperature": max_temperature,
            }
            if compound_names:
                parameters["compound_names"] = compound_names

            self.session_logger.log_database_search(
                sql_query=query,
                parameters=parameters,
                results=records_dict,
                execution_time=db_execution_time,
                context=f"Searching all phases for compound {formula}",
            )

        if not all_records:
            self.logger.warning(f"Не найдено записей для {formula}")
            return MultiPhaseSearchResult(
                compound_formula=formula,
                records=[],
                coverage_start=0.0,
                coverage_end=0.0,
                covers_298K=False,
                phase_count=0,
                warnings=["Вещество не найдено в БД"],
            )

        return self._build_result(formula, all_records, max_temperature)

    def _build_result(
        self, formula: str, all_records: List[DatabaseRecord], max_temperature: float
    ) -> MultiPhaseSearchResult:
        """
        Build MultiPhaseSearchResult from found records.

        Args:
            formula: Compound formula
            all_records: All found records
            max_temperature: Maximum temperature

        Returns:
            MultiPhaseSearchResult
        """
        # ШАГ 1: Фильтрация по температуре
        relevant_records = [rec for rec in all_records if rec.tmin <= max_temperature]

        # Сортировка по Tmin
        relevant_records.sort(key=lambda r: r.tmin)

        if not relevant_records:
            return MultiPhaseSearchResult(
                compound_formula=formula,
                records=[],
                coverage_start=0.0,
                coverage_end=0.0,
                covers_298K=False,
                phase_count=0,
                warnings=["Нет записей, покрывающих требуемый температурный диапазон"],
            )

        # ШАГ 2: Определение покрытия
        coverage_start = relevant_records[0].tmin
        coverage_end = min(relevant_records[-1].tmax, max_temperature)
        covers_298K = any(rec.covers_temperature(298.15) for rec in relevant_records)

        # ШАГ 3: Определение фазовых переходов
        tmelt, tboil = self._extract_phase_transitions(relevant_records)

        # ШАГ 4: Подсчёт фаз
        phases = set(rec.phase for rec in relevant_records if rec.phase)
        phase_count = len(phases)
        has_gas_phase = "g" in phases

        # ШАГ 5: Генерация предупреждений
        warnings = self._generate_warnings(relevant_records, covers_298K)

        return MultiPhaseSearchResult(
            compound_formula=formula,
            records=relevant_records,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            covers_298K=covers_298K,
            tmelt=tmelt,
            tboil=tboil,
            phase_count=phase_count,
            has_gas_phase=has_gas_phase,
            warnings=warnings,
        )

    def _extract_phase_transitions(
        self, records: List[DatabaseRecord]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract phase transition temperatures from records.

        Args:
            records: List of records

        Returns:
            Tuple of (Tmelt, Tboil)
        """
        tmelt_candidates = [rec.tmelt for rec in records if rec.tmelt > 0]
        tboil_candidates = [rec.tboil for rec in records if rec.tboil > 0]

        # Берём наиболее частое значение (mode)
        from collections import Counter

        tmelt = None
        if tmelt_candidates:
            tmelt = Counter(tmelt_candidates).most_common(1)[0][0]

        tboil = None
        if tboil_candidates:
            tboil = Counter(tboil_candidates).most_common(1)[0][0]

        return tmelt, tboil

    def _generate_warnings(
        self, records: List[DatabaseRecord], covers_298K: bool
    ) -> List[str]:
        """
        Generate warnings about coverage problems.

        Args:
            records: List of records
            covers_298K: Whether range covers 298K

        Returns:
            List of warning strings
        """
        warnings = []

        # Предупреждение 1: Нет покрытия 298K
        if not covers_298K:
            warnings.append("⚠️ Отсутствует покрытие 298K (стандартная температура)")

        # Предупреждение 2: Пробелы между записями
        for i in range(len(records) - 1):
            gap = records[i + 1].tmin - records[i].tmax
            if gap > 1.0:  # Пробел больше 1K
                warnings.append(
                    f"⚠️ Пробел в покрытии: {records[i].tmax}K - {records[i + 1].tmin}K"
                )

        # Предупреждение 3: Перекрытия
        for i in range(len(records) - 1):
            if records[i].overlaps_with(records[i + 1]):
                overlap_start = max(records[i].tmin, records[i + 1].tmin)
                overlap_end = min(records[i].tmax, records[i + 1].tmax)
                if overlap_end - overlap_start > 1.0:
                    warnings.append(
                        f"⚠️ Перекрытие записей: {overlap_start}K - {overlap_end}K"
                    )

        # Предупреждение 4: Нет базовой записи
        if records and not records[0].is_base_record():
            warnings.append("⚠️ Первая запись не является базовой (H298=0, S298=0)")

        return warnings
