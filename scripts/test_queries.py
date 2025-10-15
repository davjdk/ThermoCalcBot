#!/usr/bin/env python3
"""
Stage 0: Test Queries for Real Scenarios
This script tests the database with the specific scenarios mentioned in the requirements.
"""

import sqlite3
import json
from typing import List, Dict, Any

def connect_to_db(db_path: str = "data/thermo_data.db") -> sqlite3.Connection:
    """Connect to the SQLite database."""
    return sqlite3.connect(db_path)

def test_h2o_scenarios(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test H2O scenarios in different phases and temperatures."""
    cursor = conn.cursor()

    # Test 1: Basic H2O formulas
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
    FROM compounds
    WHERE TRIM(Formula) = 'H2O'
    ORDER BY ReliabilityClass ASC, Phase
    """)
    h2o_basic = cursor.fetchall()

    # Test 2: H2O with phase specifications in formula
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
    FROM compounds
    WHERE Formula LIKE 'H2O(%'
    ORDER BY ReliabilityClass ASC, Formula
    """)
    h2o_with_phase = cursor.fetchall()

    # Test 3: Temperature-specific queries for H2O
    scenarios = [
        (298, "room temperature"),
        (273, "freezing point"),
        (673, "high temperature")
    ]

    temp_results = {}
    for temp, description in scenarios:
        cursor.execute("""
        SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
        FROM compounds
        WHERE (TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%')
          AND (? >= Tmin OR Tmin IS NULL)
          AND (? <= Tmax OR Tmax IS NULL)
        ORDER BY ReliabilityClass ASC
        """, (temp, temp))

        temp_results[f"{temp}K ({description})"] = cursor.fetchall()

    return {
        'basic_h2o': h2o_basic,
        'h2o_with_phase': h2o_with_phase,
        'temperature_scenarios': temp_results
    }

def test_tio2_reaction(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test TiO2 + 2HCl → TiCl4 + H2O reaction at 600-900K."""
    cursor = conn.cursor()

    compounds = ['TiO2', 'HCl', 'TiCl4', 'H2O']
    temp_ranges = [(600, 900), (700, 800)]

    results = {}

    for compound in compounds:
        results[compound] = {}

        # Basic search
        cursor.execute("""
        SELECT Formula, Phase, Tmin, Tmax, ReliabilityClass, FirstName
        FROM compounds
        WHERE TRIM(Formula) = ?
        ORDER BY ReliabilityClass ASC
        """, (compound,))
        results[compound]['basic'] = cursor.fetchall()

        # Temperature-specific searches
        for temp_min, temp_max in temp_ranges:
            cursor.execute("""
            SELECT Formula, Phase, Tmin, Tmax, ReliabilityClass, FirstName
            FROM compounds
            WHERE TRIM(Formula) = ?
              AND (? >= Tmin OR Tmin IS NULL)
              AND (? <= Tmax OR Tmax IS NULL)
            ORDER BY ReliabilityClass ASC
            """, (compound, temp_min, temp_max))

            results[compound][f'{temp_min}-{temp_max}K'] = cursor.fetchall()

    return results

def test_iron_phase_transitions(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test Fe with phase transitions around 1811K."""
    cursor = conn.cursor()

    # Search for Fe compounds
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
    FROM compounds
    WHERE Formula LIKE 'Fe%'
    ORDER BY ReliabilityClass ASC, Formula
    """)
    fe_compounds = cursor.fetchall()

    # Temperature-specific searches around melting point
    scenarios = [
        (1500, "below melting point"),
        (1811, "at melting point"),
        (2000, "above melting point")
    ]

    temp_results = {}
    for temp, description in scenarios:
        cursor.execute("""
        SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
        FROM compounds
        WHERE Formula LIKE 'Fe%'
          AND (? >= Tmin OR Tmin IS NULL)
          AND (? <= Tmax OR Tmax IS NULL)
        ORDER BY ReliabilityClass ASC
        """, (temp, temp))

        temp_results[f"{temp}K ({description})"] = cursor.fetchall()

    return {
        'all_fe_compounds': fe_compounds,
        'temperature_scenarios': temp_results
    }

def test_oxygen_gas(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test O2 gas stability across temperature ranges."""
    cursor = conn.cursor()

    # Search for O2 compounds
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, ReliabilityClass
    FROM compounds
    WHERE Formula LIKE 'O2%'
    ORDER BY ReliabilityClass ASC
    """)
    o2_compounds = cursor.fetchall()

    # Wide temperature range test
    temp_ranges = [
        (298, "room temp"),
        (1000, "high temp"),
        (5000, "very high temp")
    ]

    temp_results = {}
    for temp, description in temp_ranges:
        cursor.execute("""
        SELECT Formula, Phase, Tmin, Tmax, ReliabilityClass
        FROM compounds
        WHERE Formula LIKE 'O2%'
          AND (? >= Tmin OR Tmin IS NULL)
          AND (? <= Tmax OR Tmax IS NULL)
        ORDER BY ReliabilityClass ASC
        """, (temp, temp))

        temp_results[f"{temp}K ({description})"] = cursor.fetchall()

    return {
        'all_o2_compounds': o2_compounds,
        'temperature_scenarios': temp_results
    }

def test_nacl_phases(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Test NaCl with solid->liquid transition at 1074K and aqueous forms."""
    cursor = conn.cursor()

    # Search for NaCl compounds
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
    FROM compounds
    WHERE Formula LIKE 'NaCl%'
    ORDER BY ReliabilityClass ASC
    """)
    nacl_compounds = cursor.fetchall()

    # Search for aqueous forms
    cursor.execute("""
    SELECT Formula, Phase, Tmin, Tmax, ReliabilityClass
    FROM compounds
    WHERE Formula LIKE '%Na%' AND Formula LIKE '%Cl%' AND Phase LIKE '%a%'
    ORDER BY ReliabilityClass ASC
    """)
    aqueous_forms = cursor.fetchall()

    # Temperature-specific searches
    scenarios = [
        (298, "room temp"),
        (1074, "at melting point"),
        (1200, "above melting point")
    ]

    temp_results = {}
    for temp, description in scenarios:
        cursor.execute("""
        SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint, ReliabilityClass
        FROM compounds
        WHERE Formula LIKE 'NaCl%'
          AND (? >= Tmin OR Tmin IS NULL)
          AND (? <= Tmax OR Tmax IS NULL)
        ORDER BY ReliabilityClass ASC
        """, (temp, temp))

        temp_results[f"{temp}K ({description})"] = cursor.fetchall()

    return {
        'all_nacl_compounds': nacl_compounds,
        'aqueous_forms': aqueous_forms,
        'temperature_scenarios': temp_results
    }

def analyze_detailed_examples(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Analyze specific examples mentioned in requirements."""
    cursor = conn.cursor()

    # Analyze TiO2 polymorphs
    cursor.execute("""
    SELECT Formula, Phase, FirstName, SecondName, ReliabilityClass, Tmin, Tmax
    FROM compounds
    WHERE Formula LIKE 'TiO2%'
    ORDER BY ReliabilityClass ASC
    """)
    tio2_polymorphs = cursor.fetchall()

    # Analyze ionic forms of iron
    cursor.execute("""
    SELECT Formula, Phase, ReliabilityClass, Tmin, Tmax
    FROM compounds
    WHERE Formula LIKE 'Fe+%'
    ORDER BY ReliabilityClass ASC
    """)
    iron_ionic = cursor.fetchall()

    return {
        'tio2_polymorphs': tio2_polymorphs,
        'iron_ionic_forms': iron_ionic
    }

def main():
    """Main test function."""
    print("Starting test queries for real scenarios...")

    conn = connect_to_db()

    # Test 1: H2O scenarios
    print("\n1. Testing H2O scenarios...")
    h2o_results = test_h2o_scenarios(conn)

    # Test 2: TiO2 reaction
    print("2. Testing TiO2 + 2HCl -> TiCl4 + H2O...")
    tio2_results = test_tio2_reaction(conn)

    # Test 3: Iron phase transitions
    print("3. Testing Fe phase transitions...")
    fe_results = test_iron_phase_transitions(conn)

    # Test 4: Oxygen gas stability
    print("4. Testing O2 gas stability...")
    o2_results = test_oxygen_gas(conn)

    # Test 5: NaCl phases
    print("5. Testing NaCl phases...")
    nacl_results = test_nacl_phases(conn)

    # Test 6: Detailed examples
    print("6. Analyzing detailed examples...")
    detailed_results = analyze_detailed_examples(conn)

    # Compile all results
    test_results = {
        'h2o_scenarios': h2o_results,
        'tio2_reaction': tio2_results,
        'iron_phase_transitions': fe_results,
        'oxygen_gas': o2_results,
        'nacl_phases': nacl_results,
        'detailed_examples': detailed_results
    }

    # Save results
    with open('docs/test_queries_results.json', 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)

    print("\nTest queries complete! Results saved to docs/test_queries_results.json")

    # Print summary statistics
    print("\n=== SUMMARY STATISTICS ===")
    print(f"H2O basic entries: {len(h2o_results['basic_h2o'])}")
    print(f"H2O with phase in formula: {len(h2o_results['h2o_with_phase'])}")
    print(f"TiO2 entries: {len(tio2_results['TiO2']['basic'])}")
    print(f"HCl entries: {len(tio2_results['HCl']['basic'])}")
    print(f"TiCl4 entries: {len(tio2_results['TiCl4']['basic'])}")
    print(f"Fe compounds: {len(fe_results['all_fe_compounds'])}")
    print(f"O2 compounds: {len(o2_results['all_o2_compounds'])}")
    print(f"NaCl compounds: {len(nacl_results['all_nacl_compounds'])}")
    print(f"NaCl aqueous forms: {len(nacl_results['aqueous_forms'])}")
    print(f"TiO2 polymorphs: {len(detailed_results['tio2_polymorphs'])}")
    print(f"Fe ionic forms: {len(detailed_results['iron_ionic_forms'])}")

    conn.close()

if __name__ == "__main__":
    main()