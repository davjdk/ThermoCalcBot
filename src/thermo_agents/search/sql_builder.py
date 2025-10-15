"""
Deterministic SQL Builder for thermodynamic compound search.

This module replaces the LLM-based SQL Generation Agent with deterministic
logic based on the comprehensive database analysis from Stage 0.

Key findings from database analysis implemented:
- 316,434 total records with 32,790 unique formulas
- 74.66% of records have ReliabilityClass = 1 (highest quality)
- 100% temperature range coverage (Tmin/Tmax always filled)
- Complex formula variability requiring multi-level search approach
- Many compounds need prefix/suffix search (e.g., HCl, CO2, NH3, CH4)
"""

from typing import Optional, Tuple, List, Dict, Any
import re
from dataclasses import dataclass


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
            self.reliability_classes = [1, 2, 3, 0, 4, 5]


class SQLBuilder:
    """
    Deterministic SQL generator for searching thermodynamic compounds.

    This class implements deterministic SQL generation logic based on the
    comprehensive database analysis from Stage 0. It replaces the LLM-based
    SQL Generation Agent with predictable, rule-based query construction.
    """

    def __init__(self, priorities: Optional[FilterPriorities] = None):
        """
        Initialize SQL builder with filtering priorities.

        Args:
            priorities: Custom filtering priorities, defaults to standard config
        """
        self.priorities = priorities or FilterPriorities()

    def build_compound_search_query(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = 100
    ) -> str:
        """
        Generate SQL query for compound search with multi-level formula matching.

        Based on database analysis findings:
        - Many compounds require prefix search (e.g., HCl, CO2, NH3, CH4)
        - Complex formulas may have phase suffixes in parentheses
        - Need to handle formula variability comprehensively

        Args:
            formula: Chemical formula (e.g., 'H2O', 'HCl', 'TiO2')
            temperature_range: Optional (tmin, tmax) in Kelvin
            phase: Optional phase filter ('s', 'l', 'g', 'aq', etc.)
            limit: Maximum number of results to return

        Returns:
            SQL query string for compound search
        """
        # Build WHERE conditions
        where_conditions = []
        params = []

        # Multi-level formula search based on database analysis
        formula_condition = self._build_formula_condition(formula)
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

    def _build_formula_condition(self, formula: str) -> str:
        """
        Build comprehensive formula search condition.

        Based on database analysis showing that many compounds require
        prefix/suffix search rather than exact matching.

        Examples from analysis:
        - HCl: exact match → 0 records, prefix search → 153 records
        - CO2: exact match → 0 records, prefix search → 1428 records
        - NH3: exact match → 1 record, prefix search → 1710 records
        - CH4: exact match → 0 records, prefix search → 1352 records
        """
        # Clean and escape formula
        clean_formula = formula.strip()

        # Build comprehensive search condition
        conditions = [
            f"TRIM(Formula) = '{self._escape_sql(clean_formula)}'",
            f"Formula LIKE '{self._escape_sql(clean_formula)}(%'",  # Formula with phase in parentheses
            f"Formula LIKE '{self._escape_sql(clean_formula)}%'",   # Prefix search for compounds like HCl
        ]

        # For complex formulas, also include containment search
        if not re.match(r'^[A-Z][a-z]?[0-9]*$', clean_formula):
            # Non-simple formula, add containment search
            conditions.append(f"Formula LIKE '%{self._escape_sql(clean_formula)}%'")

        return "(" + " OR ".join(conditions) + ")"

    def _build_temperature_condition(
        self,
        tmin_user: float,
        tmax_user: float
    ) -> Tuple[str, List[float]]:
        """
        Build temperature filtering condition.

        Database analysis shows:
        - 100% temperature range coverage (Tmin/Tmax always filled)
        - Temperature ranges: 0.00015K to 100,000K
        - No NULL values to handle
        """
        return "(? >= Tmin AND ? <= Tmax)", [tmin_user, tmax_user]

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

        # Quaternary: Phase priority (gas > liquid > solid > aqueous)
        phase_priority = "CASE Phase "
        for phase, priority in [('g', 0), ('l', 1), ('s', 2), ('aq', 3)]:
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
        phase: Optional[str] = None
    ) -> str:
        """
        Generate COUNT query for compound search.

        Useful for getting total number of matches without retrieving all data.

        Args:
            formula: Chemical formula
            temperature_range: Optional (tmin, tmax) in Kelvin
            phase: Optional phase filter

        Returns:
            SQL COUNT query and parameters
        """
        # Build WHERE conditions (same logic as search query)
        where_conditions = []
        params = []

        formula_condition = self._build_formula_condition(formula)
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
            "recommendations": []
        }

        # Analyze formula complexity
        clean_formula = formula.strip()

        # Simple formula (e.g., H2O, Fe, NaCl)
        if re.match(r'^[A-Z][a-z]?[0-9]*$', clean_formula):
            suggestions["search_strategies"].extend([
                "exact_match",
                "phase_in_parentheses",
                "prefix_search"
            ])
            suggestions["estimated_difficulty"] = "easy"

        # Compound with complex pattern (e.g., HCl, CO2, NH3, CH4)
        elif re.match(r'^[A-Z][a-z]?[0-9]*[A-Z].*$', clean_formula):
            suggestions["search_strategies"].extend([
                "exact_match",
                "prefix_search",
                "containment_search"
            ])
            suggestions["estimated_difficulty"] = "medium"
            suggestions["recommendations"].append(
                "Many compounds with this pattern require prefix search"
            )

        # Very complex formula
        else:
            suggestions["search_strategies"].extend([
                "exact_match",
                "prefix_search",
                "containment_search"
            ])
            suggestions["estimated_difficulty"] = "hard"
            suggestions["recommendations"].extend([
                "Consider alternative formula notations",
                "Check for ionized forms (+, - charges)",
                "Verify compound exists in database"
            ])

        # Add general recommendations based on database analysis
        suggestions["recommendations"].extend([
            "Use temperature filtering to reduce duplicates",
            "Check ReliabilityClass = 1 for highest quality data",
            "Consider phase transitions around MeltingPoint/BoilingPoint"
        ])

        return suggestions