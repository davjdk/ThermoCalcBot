#!/usr/bin/env python3
"""
Stage 0: Database Structure Analysis
This script analyzes the compounds database structure and generates comprehensive statistics.
"""

import sqlite3
import pandas as pd
from typing import Dict, List, Tuple
import json

def connect_to_db(db_path: str = "data/thermo_data.db") -> sqlite3.Connection:
    """Connect to the SQLite database."""
    return sqlite3.connect(db_path)

def analyze_table_structure(conn: sqlite3.Connection) -> pd.DataFrame:
    """Analyze the structure of the compounds table."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    columns = cursor.fetchall()

    df = pd.DataFrame(columns, columns=['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk'])
    return df

def analyze_null_distribution(conn: sqlite3.Connection) -> Dict[str, Dict]:
    """Analyze NULL value distribution across all columns."""
    cursor = conn.cursor()

    # Get all column names
    cursor.execute("PRAGMA table_info(compounds)")
    columns = [row[1] for row in cursor.fetchall()]

    null_stats = {}
    total_records = 0

    for column in columns:
        cursor.execute(f"""
        SELECT
            COUNT(*) as total_count,
            COUNT({column}) as non_null_count,
            COUNT(*) - COUNT({column}) as null_count,
            ROUND(COUNT(*) - COUNT({column}) * 100.0 / COUNT(*), 2) as null_percentage
        FROM compounds
        """)

        total_count, non_null_count, null_count, null_percentage = cursor.fetchone()

        if total_records == 0:
            total_records = total_count

        null_stats[column] = {
            'total_count': total_count,
            'non_null_count': non_null_count,
            'null_count': null_count,
            'null_percentage': null_percentage
        }

    return null_stats, total_records

def analyze_reliability_class_distribution(conn: sqlite3.Connection) -> pd.DataFrame:
    """Analyze distribution by ReliabilityClass."""
    query = """
    SELECT
        ReliabilityClass,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM compounds), 2) as percentage
    FROM compounds
    GROUP BY ReliabilityClass
    ORDER BY ReliabilityClass
    """
    return pd.read_sql_query(query, conn)

def analyze_formula_patterns(conn: sqlite3.Connection) -> Dict:
    """Analyze chemical formula patterns."""
    cursor = conn.cursor()

    # Basic formula statistics
    cursor.execute("""
    SELECT
        COUNT(*) as total_records,
        COUNT(DISTINCT Formula) as unique_formulas,
        COUNT(DISTINCT TRIM(Formula)) as unique_trimmed_formulas
    FROM compounds
    """)

    total_records, unique_formulas, unique_trimmed_formulas = cursor.fetchone()

    # Analyze formulas with phases in parentheses
    cursor.execute("""
    SELECT COUNT(*)
    FROM compounds
    WHERE Formula LIKE '%(%)%'
    """)

    formulas_with_parentheses = cursor.fetchone()[0]

    # Analyze ionic forms (with + or -)
    cursor.execute("""
    SELECT COUNT(*)
    FROM compounds
    WHERE Formula LIKE '%+%' OR Formula LIKE '%-%'
    """)

    ionic_formulas = cursor.fetchone()[0]

    return {
        'total_records': total_records,
        'unique_formulas': unique_formulas,
        'unique_trimmed_formulas': unique_trimmed_formulas,
        'formulas_with_parentheses': formulas_with_parentheses,
        'ionic_formulas': ionic_formulas,
        'duplicate_ratio': round((total_records - unique_formulas) / total_records * 100, 2)
    }

def analyze_temperature_ranges(conn: sqlite3.Connection) -> Dict:
    """Analyze temperature range coverage."""
    cursor = conn.cursor()

    # Temperature range statistics
    cursor.execute("""
    SELECT
        COUNT(*) as total_records,
        COUNT(Tmin) as has_tmin,
        COUNT(Tmax) as has_tmax,
        COUNT(*) - COUNT(Tmin) as null_tmin,
        COUNT(*) - COUNT(Tmax) as null_tmax,
        COUNT(CASE WHEN Tmin IS NOT NULL AND Tmax IS NOT NULL THEN 1 END) as both_temp_defined,
        MIN(Tmin) as min_temp,
        MAX(Tmax) as max_temp
    FROM compounds
    """)

    result = cursor.fetchone()
    temp_stats = {
        'total_records': result[0],
        'has_tmin': result[1],
        'has_tmax': result[2],
        'null_tmin': result[3],
        'null_tmax': result[4],
        'both_temp_defined': result[5],
        'min_temp': result[6],
        'max_temp': result[7],
        'null_tmin_percentage': round(result[3] / result[0] * 100, 2),
        'null_tmax_percentage': round(result[4] / result[0] * 100, 2)
    }

    # Temperature range distribution
    cursor.execute("""
    SELECT
        CASE
            WHEN Tmin < 100 THEN '< 100K'
            WHEN Tmin < 298 THEN '100K - 298K'
            WHEN Tmin < 500 THEN '298K - 500K'
            WHEN Tmin < 1000 THEN '500K - 1000K'
            WHEN Tmin < 2000 THEN '1000K - 2000K'
            ELSE '> 2000K'
        END as temp_range,
        COUNT(*) as count
    FROM compounds
    WHERE Tmin IS NOT NULL
    GROUP BY temp_range
    ORDER BY MIN(Tmin)
    """)

    temp_distribution = dict(cursor.fetchall())

    return temp_stats, temp_distribution

def analyze_phase_states(conn: sqlite3.Connection) -> Dict:
    """Analyze phase states and transitions."""
    # Phase distribution
    phase_query = """
    SELECT
        Phase,
        COUNT(*) as count,
        ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM compounds), 2) as percentage
    FROM compounds
    GROUP BY Phase
    ORDER BY count DESC
    """

    phase_df = pd.read_sql_query(phase_query, conn)

    # Phase transition data availability
    cursor = conn.cursor()
    cursor.execute("""
    SELECT
        COUNT(*) as total_records,
        COUNT(MeltingPoint) as has_melting_point,
        COUNT(BoilingPoint) as has_boiling_point,
        COUNT(CASE WHEN MeltingPoint IS NOT NULL OR BoilingPoint IS NOT NULL THEN 1 END) as has_transition_data
    FROM compounds
    """)

    transition_stats = cursor.fetchone()

    return {
        'phase_distribution': phase_df.to_dict('records'),
        'transition_stats': {
            'total_records': transition_stats[0],
            'has_melting_point': transition_stats[1],
            'has_boiling_point': transition_stats[2],
            'has_transition_data': transition_stats[3],
            'melting_point_percentage': round(transition_stats[1] / transition_stats[0] * 100, 2),
            'boiling_point_percentage': round(transition_stats[2] / transition_stats[0] * 100, 2),
            'any_transition_percentage': round(transition_stats[3] / transition_stats[0] * 100, 2)
        }
    }

def analyze_thermodynamic_properties(conn: sqlite3.Connection) -> Dict:
    """Analyze thermodynamic properties completeness."""
    cursor = conn.cursor()

    properties = ['H298', 'S298', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6']

    prop_stats = {}
    for prop in properties:
        cursor.execute(f"""
        SELECT
            COUNT(*) as total_records,
            COUNT({prop}) as has_value,
            ROUND(COUNT({prop}) * 100.0 / (SELECT COUNT(*) FROM compounds), 2) as percentage
        FROM compounds
        """)

        total, has_value, percentage = cursor.fetchone()
        prop_stats[prop] = {
            'has_value': has_value,
            'percentage': percentage
        }

    # Check complete sets of f1-f6 coefficients
    cursor.execute("""
    SELECT COUNT(*) as complete_sets
    FROM compounds
    WHERE f1 IS NOT NULL
      AND f2 IS NOT NULL
      AND f3 IS NOT NULL
      AND f4 IS NOT NULL
      AND f5 IS NOT NULL
      AND f6 IS NOT NULL
    """)

    complete_f_sets = cursor.fetchone()[0]

    return {
        'individual_properties': prop_stats,
        'complete_f_sets': {
            'count': complete_f_sets,
            'percentage': round(complete_f_sets / cursor.execute("SELECT COUNT(*) FROM compounds").fetchone()[0] * 100, 2)
        }
    }

def main():
    """Main analysis function."""
    print("Starting comprehensive database analysis...")

    conn = connect_to_db()

    # 1. Table structure
    print("\nAnalyzing table structure...")
    table_structure = analyze_table_structure(conn)
    print(f"Found {len(table_structure)} columns in compounds table")

    # 2. NULL distribution
    print("\nAnalyzing NULL value distribution...")
    null_stats, total_records = analyze_null_distribution(conn)
    print(f"Total records: {total_records:,}")

    # 3. Reliability class distribution
    print("\nAnalyzing ReliabilityClass distribution...")
    reliability_dist = analyze_reliability_class_distribution(conn)

    # 4. Formula patterns
    print("\nAnalyzing chemical formula patterns...")
    formula_stats = analyze_formula_patterns(conn)

    # 5. Temperature ranges
    print("\nAnalyzing temperature ranges...")
    temp_stats, temp_distribution = analyze_temperature_ranges(conn)

    # 6. Phase states
    print("\nAnalyzing phase states...")
    phase_stats = analyze_phase_states(conn)

    # 7. Thermodynamic properties
    print("\nAnalyzing thermodynamic properties...")
    thermo_stats = analyze_thermodynamic_properties(conn)

    # Save results to JSON
    analysis_results = {
        'total_records': total_records,
        'table_structure': table_structure.to_dict('records'),
        'null_distribution': null_stats,
        'reliability_distribution': reliability_dist.to_dict('records'),
        'formula_statistics': formula_stats,
        'temperature_statistics': temp_stats,
        'temperature_distribution': temp_distribution,
        'phase_statistics': phase_stats,
        'thermodynamic_statistics': thermo_stats
    }

    with open('docs/database_analysis_results.json', 'w', encoding='utf-8') as f:
        json.dump(analysis_results, f, indent=2, ensure_ascii=False)

    print("\nAnalysis complete! Results saved to docs/database_analysis_results.json")

    conn.close()

if __name__ == "__main__":
    main()