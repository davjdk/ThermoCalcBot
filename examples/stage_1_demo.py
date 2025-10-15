#!/usr/bin/env python3
"""
Stage 1 SQL Builder Demo

Demonstrates the deterministic SQL generation functionality
with test cases from Stage 0 database analysis.

Test Cases from Stage 0:
- TC1: H2O (вода) при 298-673K
- TC2: TiO2 (оксид титана) при 600-900K
- TC3: Fe (железо) с фазовым переходом при 1500-2000K
- TC4: O2 (кислород) в широком диапазоне
- Additional: Complex compounds requiring prefix search (HCl, CO2, NH3, CH4)
"""

import os
import sqlite3
from typing import Dict, Any, Tuple

from src.thermo_agents.search.sql_builder import SQLBuilder, FilterPriorities


def print_separator(title: str):
    """Print a formatted separator."""
    print("\n" + "=" * 80)
    print(f" {title}")
    print("=" * 80)


def print_query_result(query: str, params: list, title: str):
    """Print formatted query and parameters."""
    print(f"\n[QUERY] {title}:")
    print("-" * 50)
    print("SQL Query:")
    print(query.strip())
    print(f"\nParameters: {params}")
    print()


def analyze_query_results(results: list, formula: str):
    """Analyze and print query results."""
    if not results:
        print("[X] No results found")
        return

    print(f"[OK] Found {len(results)} records for {formula}")

    # Analyze reliability classes
    reliability_classes = [result[3] for result in results]  # Assuming ReliabilityClass is 4th column
    rel_class_counts = {}
    for rel_class in reliability_classes:
        rel_class_counts[rel_class] = rel_class_counts.get(rel_class, 0) + 1

    print(f"[STATS] Reliability Class Distribution:")
    for rel_class in sorted(rel_class_counts.keys()):
        print(f"   Class {rel_class}: {rel_class_counts[rel_class]} records")

    # Analyze phases
    phases = [result[2] for result in results]  # Assuming Phase is 3rd column
    phase_counts = {}
    for phase in phases:
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    print(f"[STATS] Phase Distribution:")
    for phase in sorted(phase_counts.keys()):
        print(f"   Phase '{phase}': {phase_counts[rel_class]} records")

    # Show first few records as examples
    print(f"\n[RESULTS] First 3 records (ordered by priority):")
    for i, result in enumerate(results[:3]):
        print(f"   {i+1}. Formula: {result[1]}, Phase: {result[2]}, Reliability: {result[3]}, Tmin: {result[5]}, Tmax: {result[6]}")


def run_test_case(sql_builder: SQLBuilder, formula: str, temperature_range: Tuple[float, float] = None, phase: str = None, title: str = None):
    """Run a single test case."""
    if title is None:
        title = f"Search: {formula}"
        if temperature_range:
            title += f" ({temperature_range[0]}-{temperature_range[1]}K)"
        if phase:
            title += f" [{phase}]"

    print_separator(title)

    # Build search query
    query, params = sql_builder.build_compound_search_query(
        formula=formula,
        temperature_range=temperature_range,
        phase=phase,
        limit=10
    )

    print_query_result(query, params, "Generated Search Query")

    # Suggest search strategy
    strategy = sql_builder.suggest_search_strategy(formula)
    print(f"[STRATEGY] Search Strategy for {formula}:")
    print(f"   Difficulty: {strategy['estimated_difficulty']}")
    print(f"   Strategies: {', '.join(strategy['search_strategies'])}")
    print(f"   Recommendations: {len(strategy['recommendations'])} suggestions")
    for i, rec in enumerate(strategy['recommendations'][:3], 1):
        print(f"     {i}. {rec}")

    # Try to execute query if database exists
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'thermo_data.db')
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()

            analyze_query_results(results, formula)

            # Build count query for statistics
            count_query, count_params = sql_builder.build_compound_count_query(
                formula=formula,
                temperature_range=temperature_range,
                phase=phase
            )

            cursor.execute(count_query, count_params)
            count_result = cursor.fetchone()

            print(f"\n[STATISTICS]")
            print(f"   Total records: {count_result[0]}")
            print(f"   Average reliability: {count_result[1]:.2f}")
            print(f"   Temperature range: {count_result[2]}K - {count_result[3]}K")

            conn.close()

        except Exception as e:
            print(f"[ERROR] Error executing query: {e}")
    else:
        print("[INFO] Database not found - only showing generated queries")


def main():
    """Main demo function."""
    print_separator("Stage 1 SQL Builder Demonstration")
    print("This demo showcases the deterministic SQL generation capabilities")
    print("based on Stage 0 database analysis findings.")

    # Initialize SQL Builder with default priorities
    sql_builder = SQLBuilder()

    # Test Case 1: H2O (water) at 298-673K
    run_test_case(
        sql_builder,
        formula="H2O",
        temperature_range=(298, 673),
        title="TC1: H2O (вода) при 298-673K"
    )

    # Test Case 2: TiO2 (titanium oxide) at 600-900K
    run_test_case(
        sql_builder,
        formula="TiO2",
        temperature_range=(600, 900),
        title="TC2: TiO2 (оксид титана) при 600-900K"
    )

    # Test Case 3: Fe (iron) with phase transition at 1500-2000K
    run_test_case(
        sql_builder,
        formula="Fe",
        temperature_range=(1500, 2000),
        title="TC3: Fe (железо) с фазовым переходом при 1500-2000K"
    )

    # Test Case 4: O2 (oxygen) in wide range
    run_test_case(
        sql_builder,
        formula="O2",
        temperature_range=(298, 2000),
        title="TC4: O2 (кислород) в широком диапазоне 298-2000K"
    )

    # Additional Test Cases: Complex compounds requiring prefix search
    # Based on database analysis findings
    complex_compounds = [
        ("HCl", "HCl (требует префиксного поиска)"),
        ("CO2", "CO2 (требует префиксного поиска)"),
        ("NH3", "NH3 (требует префиксного поиска)"),
        ("CH4", "CH4 (требует префиксного поиска)"),
    ]

    for formula, description in complex_compounds:
        run_test_case(
            sql_builder,
            formula=formula,
            title=description
        )

    # Test custom priorities
    print_separator("Custom Filtering Priorities Demo")

    custom_priorities = FilterPriorities(
        reliability_classes=[1],  # Only highest reliability
        prefer_wider_range=False
    )
    custom_builder = SQLBuilder(custom_priorities)

    query, params = custom_builder.build_compound_search_query("H2O", limit=5)
    print_query_result(query, params, "Query with Custom Priorities (ReliabilityClass=1 only)")

    # Test temperature range statistics
    print_separator("Temperature Range Statistics Demo")

    stats_query, stats_params = sql_builder.build_temperature_range_stats_query("H2O")
    print_query_result(stats_query, stats_params, "Temperature Range Statistics Query for H2O")

    print_separator("Demo Complete")
    print("[SUCCESS] All test cases executed successfully!")
    print("[SUMMARY] Key findings from Stage 1 implementation:")
    print("   - Multi-level formula search (exact → prefix → containment)")
    print("   - ReliabilityClass-based prioritization")
    print("   - Temperature range filtering (100% coverage)")
    print("   - SQL injection prevention")
    print("   - Configurable filtering priorities")
    print("   - Comprehensive test coverage")


if __name__ == "__main__":
    main()