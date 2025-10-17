"""
Высокопроизводительный Deterministic SQL Builder для поиска термодинамических соединений.

Оптимизированная версия с индексацией, кэшированием и быстрыми алгоритмами.
Заменяет LLM-based SQL Generation Agent на детерминированную логику.

Key findings from database analysis implemented:
- 316,434 total records with 32,790 unique formulas
- 74.66% of records have ReliabilityClass = 1 (highest quality)
- 100% temperature range coverage (Tmin/Tmax always filled)
- Complex formula variability requiring multi-level search approach
- Many compounds need prefix/suffix search (e.g., HCl, CO2, NH3, CH4)
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import time
from functools import lru_cache

from ..filtering.constants import (
    DEFAULT_QUERY_LIMIT,
    MAX_QUERY_LIMIT,
    DEFAULT_CACHE_SIZE,
    MAX_RELIABILITY_CLASS,
    RELIABILITY_CLASS_EXCELLENT,
    VALID_PHASES,
    FAST_QUERY_THRESHOLD,
    SLOW_QUERY_THRESHOLD,
)
from .common_compounds import CommonCompoundResolver


@dataclass
class FilterPriorities:
    """Configuration for filtering and sorting priorities."""

    # ReliabilityClass priority (1 = highest)
    reliability_classes: List[int] = None

    # Temperature range priority
    prefer_wider_range: bool = True

    # Data completeness priority
    require_thermo_data: bool = True

    def __post_init__(self):
        if self.reliability_classes is None:
            self.reliability_classes = [
                RELIABILITY_CLASS_EXCELLENT,  # 1 - excellent
                2,  # good
                MAX_RELIABILITY_CLASS,  # 3 - fair
                0,  # unknown/unspecified
                4,  # poor
                5,  # very poor
            ]


class SQLBuilder:
    """
    Высокопроизводительный SQL генератор с кэшированием и оптимизациями.

    Особенности производительности:
    - Кэширование сгенерированных запросов
    - Оптимизированные алгоритмы построения условий
    - Предвычисленные паттерны для распространенных запросов
    - Метрики производительности
    """

    def __init__(self, priorities: Optional[FilterPriorities] = None):
        """
        Initialize SQL builder with filtering priorities and performance optimizations.

        Args:
            priorities: Custom filtering priorities, defaults to standard config
        """
        self.priorities = priorities or FilterPriorities()
        self.common_resolver = CommonCompoundResolver()

        # Кэширование запросов
        self._query_cache: Dict[str, Tuple[str, List[Any]]] = {}
        self._cache_size = DEFAULT_CACHE_SIZE
        self._cache_hits = 0
        self._cache_misses = 0

        # Метрики производительности
        self._query_count = 0
        self._total_build_time = 0.0

    def build_compound_search_query(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = DEFAULT_QUERY_LIMIT,
        compound_names: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Generate optimized SQL query for compound search with caching.

        Based on database analysis findings:
        - Many compounds require prefix search (e.g., HCl, CO2, NH3, CH4)
        - Complex formulas may have phase suffixes in parentheses
        - Need to handle formula variability comprehensively
        - Can search by compound names to improve accuracy

        Args:
            formula: Chemical formula (e.g., 'H2O', 'HCl', 'TiO2')
            temperature_range: Optional (tmin, tmax) in Kelvin
            phase: Optional phase filter ('s', 'l', 'g', 'aq', etc.)
            limit: Maximum number of results to return
            compound_names: Optional list of compound names

        Returns:
            Tuple of (SQL query string, parameters) for compound search
        """
        start_time = time.time()
        self._query_count += 1

        # Генерируем ключ кэша
        cache_key = self._generate_query_cache_key(
            formula, temperature_range, phase, limit, compound_names
        )

        # Проверяем кэш
        if cache_key in self._query_cache:
            self._cache_hits += 1
            cached_query, cached_params = self._query_cache[cache_key]
            self._total_build_time += time.time() - start_time
            return cached_query, cached_params.copy()

        self._cache_misses += 1

        # Строим запрос
        query, params = self._build_query_optimized(
            formula, temperature_range, phase, limit, compound_names
        )

        # Кэшируем результат
        self._cache_query(cache_key, query, params)

        self._total_build_time += time.time() - start_time
        return query, params

    def _generate_query_cache_key(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]],
        phase: Optional[str],
        limit: int,
        compound_names: Optional[List[str]]
    ) -> str:
        """Генерировать ключ кэша для запроса."""
        key_parts = [
            formula.upper(),
            str(temperature_range) if temperature_range else "None",
            phase.upper() if phase else "None",
            str(limit),
            str(compound_names) if compound_names else "None"
        ]
        return "_".join(key_parts)

    def _cache_query(
        self,
        cache_key: str,
        query: str,
        params: List[Any]
    ) -> None:
        """Сохранить запрос в кэш."""
        # Очищаем кэш при необходимости
        if len(self._query_cache) >= self._cache_size:
            # Удаляем 25% самых старых записей
            items_to_remove = len(self._query_cache) // 4
            for _ in range(items_to_remove):
                if self._query_cache:
                    self._query_cache.pop(next(iter(self._query_cache)))

        self._query_cache[cache_key] = (query, params.copy())

    def _build_query_optimized(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]],
        phase: Optional[str],
        limit: int,
        compound_names: Optional[List[str]]
    ) -> Tuple[str, List[Any]]:
        """Оптимизированное построение запроса."""
        # Build WHERE conditions
        where_conditions = []
        params = []

        # Multi-level formula search based on database analysis
        formula_condition = self._build_formula_condition(formula, compound_names)
        where_conditions.append(formula_condition)

        # Temperature filtering (100% coverage in database)
        if temperature_range:
            temp_condition, temp_params = self._build_temperature_condition(
                temperature_range[0], temperature_range[1]
            )
            where_conditions.append(temp_condition)
            params.extend(temp_params)

        # Phase filtering
        if phase:
            where_conditions.append("Phase = ?")
            params.append(phase)

        # Combine WHERE conditions
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        # Build ORDER BY clause for prioritization
        order_clause = self._build_order_clause()

        # Complete query
        query = f"""
        SELECT * FROM compounds
        WHERE {where_clause}
        {order_clause}
        LIMIT ?
        """

        # Add limit parameter
        params.append(limit)

        return query, params

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Получить метрики производительности SQL Builder."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (
            self._cache_hits / total_requests * 100
            if total_requests > 0 else 0
        )

        avg_build_time = (
            self._total_build_time / self._query_count * 1000
            if self._query_count > 0 else 0
        )

        return {
            "cache_hit_rate": hit_rate,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "query_cache_size": len(self._query_cache),
            "total_queries": self._query_count,
            "avg_build_time_ms": avg_build_time,
            "total_build_time_ms": self._total_build_time * 1000,
        }

    def _build_formula_condition(
        self, formula: str, compound_names: Optional[List[str]] = None
    ) -> str:
        """
        Build comprehensive formula search condition.

        Based on database analysis showing that many compounds require
        prefix/suffix search rather than exact matching.

        Examples from analysis:
        - HCl: exact match → 0 records, prefix search → 153 records
        - CO2: exact match → 0 records, prefix search → 1428 records
        - NH3: exact match → 1 record, prefix search → 1710 records
        - CH4: exact match → 0 records, prefix search → 1352 records

        Also searches by compound names (FirstName field) if provided.

        ПРИОРИТЕТ: Для распространенных веществ (H2O, CO2, O2 и т.д.) используется
        специальная точная логика через CommonCompoundResolver, чтобы избежать
        ложных совпадений (например, H2O2 вместо H2O).
        """
        # Clean and escape formula
        clean_formula = formula.strip()

        # ПРИОРИТЕТ 1: Проверка на распространенное вещество
        if self.common_resolver.is_common_compound(clean_formula):
            common_condition = self.common_resolver.build_sql_condition(
                clean_formula, compound_names
            )
            if common_condition:
                # Используем точную логику для распространенных веществ
                return common_condition

        # ПРИОРИТЕТ 2: Обычная логика для остальных веществ
        # Build comprehensive search condition
        conditions = [
            f"TRIM(Formula) = '{self._escape_sql(clean_formula)}'",
            f"Formula LIKE '{self._escape_sql(clean_formula)}(%'",  # Formula with phase in parentheses
            f"Formula LIKE '{self._escape_sql(clean_formula)}%'",  # Prefix search for compounds like HCl
        ]

        # For complex formulas, also include containment search
        if not re.match(r"^[A-Z][a-z]?[0-9]*$", clean_formula):
            # Non-simple formula, add containment search
            conditions.append(f"Formula LIKE '%{self._escape_sql(clean_formula)}%'")

        # Add name-based search if compound names are provided
        if compound_names:
            name_conditions = []
            for name in compound_names:
                if name and name.strip():
                    escaped_name = self._escape_sql(name.strip())
                    # Case-insensitive exact match on FirstName
                    name_conditions.append(
                        f"LOWER(TRIM(FirstName)) = LOWER('{escaped_name}')"
                    )

            if name_conditions:
                # Add name search as additional OR conditions
                conditions.extend(name_conditions)

        return "(" + " OR ".join(conditions) + ")"

    def _build_temperature_condition(
        self, tmin_user: float, tmax_user: float
    ) -> Tuple[str, List[float]]:
        """
        Build temperature filtering condition.

        Database analysis shows:
        - 100% temperature range coverage (Tmin/Tmax always filled)
        - Temperature ranges: 0.00015K to 100,000K
        - No NULL values to handle

        Использует логику пересечения диапазонов:
        - Диапазон БД [Tmin, Tmax] пересекается с пользовательским [tmin_user, tmax_user]
        - Условие: NOT (Tmax < tmin_user OR Tmin > tmax_user)
        - Что эквивалентно: (Tmax >= tmin_user AND Tmin <= tmax_user)
        """
        return "(Tmax >= ? AND Tmin <= ?)", [tmin_user, tmax_user]

    def _build_order_clause(self) -> str:
        """
        Build ORDER BY clause for result prioritization.

        Based on database analysis:
        - 74.66% of records have ReliabilityClass = 1 (highest quality)
        - All records have complete thermodynamic data (H298, S298, f1-f6)
        - 100% have phase transition data (MeltingPoint, BoilingPoint)
        """
        conditions = []

        # Primary: ReliabilityClass (1 = highest priority)
        reliability_case = "CASE ReliabilityClass "
        for i, rel_class in enumerate(self.priorities.reliability_classes):
            reliability_case += f"WHEN {rel_class} THEN {i} "
        reliability_case += f"ELSE {len(self.priorities.reliability_classes)} END"
        conditions.append(reliability_case)

        # Secondary: Temperature range width (if prefer_wider_range)
        if self.priorities.prefer_wider_range:
            conditions.append("(Tmax - Tmin) DESC")

        # Tertiary: Formula simplicity (prefer base formulas over modified ones)
        conditions.append("LENGTH(TRIM(Formula)) ASC")

        # Quaternary: Phase priority using constants for valid phases
        phase_priority = "CASE Phase "
        # Define phase priority based on typical thermodynamic analysis needs
        phase_priorities = [("g", 0), ("l", 1), ("s", 2), ("aq", 3)]
        for phase, priority in phase_priorities:
            if phase in VALID_PHASES:
                phase_priority += f"WHEN '{phase}' THEN {priority} "
        phase_priority += "ELSE 4 END"
        conditions.append(phase_priority)

        # Final: Row ID for consistency
        conditions.append("rowid ASC")

        return "ORDER BY " + ", ".join(conditions)

    def _escape_sql(self, value: str) -> str:
        """
        Escape SQL values to prevent injection.

        Args:
            value: String value to escape

        Returns:
            Escaped string safe for SQL queries
        """
        # Basic SQL escaping - replace single quotes
        return value.replace("'", "''")

    def build_compound_count_query(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        compound_names: Optional[List[str]] = None,
    ) -> str:
        """
        Generate COUNT query for compound search.

        Useful for getting total number of matches without retrieving all data.

        Args:
            formula: Chemical formula
            temperature_range: Optional (tmin, tmax) in Kelvin
            phase: Optional phase filter
            compound_names: Optional list of compound names

        Returns:
            SQL COUNT query and parameters
        """
        # Build WHERE conditions (same logic as search query)
        where_conditions = []
        params = []

        formula_condition = self._build_formula_condition(formula, compound_names)
        where_conditions.append(formula_condition)

        if temperature_range:
            temp_condition, temp_params = self._build_temperature_condition(
                temperature_range[0], temperature_range[1]
            )
            where_conditions.append(temp_condition)
            params.extend(temp_params)

        if phase:
            where_conditions.append("Phase = ?")
            params.append(phase)

        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

        query = f"""
        SELECT COUNT(*) as total_count,
               AVG(ReliabilityClass) as avg_reliability,
               MIN(Tmin) as min_temp,
               MAX(Tmax) as max_temp
        FROM compounds
        WHERE {where_clause}
        """

        return query, params

    def build_temperature_range_stats_query(self, formula: str) -> str:
        """
        Generate query to get temperature range statistics for a compound.

        Based on database analysis showing complete temperature coverage.

        Args:
            formula: Chemical formula

        Returns:
            SQL query for temperature statistics and parameters
        """
        formula_condition = self._build_formula_condition(formula)

        query = f"""
        SELECT
            COUNT(*) as total_records,
            COUNT(DISTINCT Phase) as unique_phases,
            MIN(Tmin) as overall_min_temp,
            MAX(Tmax) as overall_max_temp,
            AVG(Tmax - Tmin) as avg_temp_range,
            MIN(MeltingPoint) as min_melting_point,
            MAX(MeltingPoint) as max_melting_point,
            MIN(BoilingPoint) as min_boiling_point,
            MAX(BoilingPoint) as max_boiling_point,
            AVG(ReliabilityClass) as avg_reliability
        FROM compounds
        WHERE {formula_condition}
        """

        return query, []

    def suggest_search_strategy(self, formula: str) -> Dict[str, Any]:
        """
        Suggest optimal search strategy based on formula analysis.

        Based on database analysis patterns to provide guidance for
        difficult-to-find compounds.

        Args:
            formula: Chemical formula to analyze

        Returns:
            Dictionary with search strategy recommendations
        """
        suggestions = {
            "formula": formula,
            "search_strategies": [],
            "estimated_difficulty": "easy",
            "recommendations": [],
        }

        # Analyze formula complexity
        clean_formula = formula.strip()

        # Simple formula (e.g., H2O, Fe, NaCl)
        if re.match(r"^[A-Z][a-z]?[0-9]*$", clean_formula):
            suggestions["search_strategies"].extend(
                ["exact_match", "phase_in_parentheses", "prefix_search"]
            )
            suggestions["estimated_difficulty"] = "easy"

        # Compound with complex pattern (e.g., HCl, CO2, NH3, CH4)
        elif re.match(r"^[A-Z][a-z]?[0-9]*[A-Z].*$", clean_formula):
            suggestions["search_strategies"].extend(
                ["exact_match", "prefix_search", "containment_search"]
            )
            suggestions["estimated_difficulty"] = "medium"
            suggestions["recommendations"].append(
                "Many compounds with this pattern require prefix search"
            )

        # Very complex formula
        else:
            suggestions["search_strategies"].extend(
                ["exact_match", "prefix_search", "containment_search"]
            )
            suggestions["estimated_difficulty"] = "hard"
            suggestions["recommendations"].extend(
                [
                    "Consider alternative formula notations",
                    "Check for ionized forms (+, - charges)",
                    "Verify compound exists in database",
                ]
            )

        # Add general recommendations based on database analysis
        suggestions["recommendations"].extend(
            [
                "Use temperature filtering to reduce duplicates",
                "Check ReliabilityClass = 1 for highest quality data",
                "Consider phase transitions around MeltingPoint/BoilingPoint",
            ]
        )

        return suggestions
