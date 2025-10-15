"""
Example usage of the search module for thermodynamic compounds.

This example demonstrates how to use the new deterministic search functionality
to find thermodynamic data for chemical compounds.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.thermo_agents.search.sql_builder import SQLBuilder, FilterPriorities
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.search.compound_searcher import CompoundSearcher


def main():
    """Demonstrate search module functionality."""
    print("=== Thermodynamic Compounds Search Example ===\n")

    # Find the database file
    db_paths = [
        Path("data/thermo_data.db"),
        Path("../data/thermo_data.db"),
        Path("../../data/thermo_data.db"),
    ]

    db_path = None
    for path in db_paths:
        if path.exists():
            db_path = path.resolve()
            break

    if db_path is None:
        print("ERROR: Thermodynamic database not found")
        print("Please ensure 'data/thermo_data.db' exists")
        return

    print(f"Using database: {db_path}\n")

    # Initialize components
    try:
        db_connector = DatabaseConnector(db_path)
        sql_builder = SQLBuilder()
        searcher = CompoundSearcher(sql_builder, db_connector)
        print("OK Search components initialized successfully\n")
    except Exception as e:
        print(f"ERROR: Failed to initialize search components: {e}")
        return

    # Example 1: Basic compound search
    print("1. Basic search for H2O:")
    print("-" * 30)
    try:
        result = searcher.search_compound('H2O')
        print(f"   Formula: {result.compound_formula}")
        print(f"   Records found: {len(result.records_found)}")
        print(f"   Phases: {result.get_unique_phases()}")
        print(f"   Coverage status: {result.coverage_status}")
        print(f"   Execution time: {result.execution_time_ms:.2f} ms")

        if result.records_found:
            print("\n   First record:")
            record = result.records_found[0]
            print(f"     Phase: {record.phase}")
            print(f"     Temperature range: {record.tmin} - {record.tmax} K")
            print(f"     H298: {record.h298} kJ/mol")
            print(f"     S298: {record.s298} J/(mol·K)")
            print(f"     Reliability class: {record.reliability_class}")

        if result.warnings:
            print(f"   Warnings: {result.warnings}")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "="*50 + "\n")

    # Example 2: Search with temperature filtering
    print("2. Search for H2O with temperature filtering (298-373 K):")
    print("-" * 55)
    try:
        result = searcher.search_compound('H2O', temperature_range=(298.0, 373.0))
        print(f"   Records found: {len(result.records_found)}")
        print(f"   Coverage status: {result.coverage_status}")

        if result.records_found:
            print("\n   Records in temperature range:")
            for i, record in enumerate(result.records_found[:3]):  # Show first 3
                print(f"     {i+1}. {record.phase} phase: {record.tmin}-{record.tmax} K")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "="*50 + "\n")

    # Example 3: Search with phase filtering
    print("3. Search for H2O in gas phase only:")
    print("-" * 35)
    try:
        result = searcher.search_compound('H2O', phase='g')
        print(f"   Records found: {len(result.records_found)}")
        if result.records_found:
            for record in result.records_found:
                print(f"     {record.phase}: {record.tmin}-{record.tmax} K")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "="*50 + "\n")

    # Example 4: Search strategy recommendations
    print("4. Search strategy recommendations:")
    print("-" * 32)
    try:
        test_formulas = ['H2O', 'HCl', 'TiO2', 'ComplexFormula']
        for formula in test_formulas:
            strategy = searcher.get_search_strategy(formula)
            print(f"   {formula}:")
            print(f"     Difficulty: {strategy.estimated_difficulty}")
            print(f"     Strategies: {', '.join(strategy.search_strategies)}")
            if strategy.recommendations:
                print(f"     Recommendations: {strategy.recommendations[0]}")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "="*50 + "\n")

    # Example 5: Multiple compound comparison
    print("5. Multiple compound comparison:")
    print("-" * 30)
    try:
        compounds = ['H2O', 'CO2', 'NH3', 'CH4']
        for compound in compounds:
            result = searcher.search_compound(compound, limit=5)
            best_record = result.get_best_record() if result.records_found else None

            print(f"   {compound}:")
            print(f"     Total records: {len(result.records_found)}")
            if best_record:
                print(f"     Best record: {best_record.phase} phase, "
                      f"Reliability: {best_record.reliability_class}")
            else:
                print(f"     No data found")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "="*50 + "\n")

    # Example 6: Advanced search with custom priorities
    print("6. Advanced search with custom reliability priorities:")
    print("-" * 50)
    try:
        # Create custom priorities that prefer class 1 and 2 data
        custom_priorities = FilterPriorities(
            reliability_classes=[1, 2, 0, 3, 4, 5],
            prefer_wider_range=True,
            require_thermo_data=True
        )
        custom_sql_builder = SQLBuilder(custom_priorities)
        custom_searcher = CompoundSearcher(custom_sql_builder, db_connector)

        result = custom_searcher.search_compound('H2O', limit=3)
        print(f"   High-priority H2O records: {len(result.records_found)}")
        for i, record in enumerate(result.records_found):
            print(f"     {i+1}. Phase: {record.phase}, "
                  f"Reliability: {record.reliability_class}, "
                  f"Range: {record.tmin}-{record.tmax} K")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n=== Search Example Completed ===")


if __name__ == "__main__":
    main()