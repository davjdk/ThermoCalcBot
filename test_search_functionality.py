"""
Simple functionality test for the search module.

This test verifies that the main components work together correctly.
"""

import tempfile
from pathlib import Path

from src.thermo_agents.search.sql_builder import SQLBuilder
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.search.compound_searcher import CompoundSearcher


def test_search_functionality():
    """Test basic search functionality with a temporary database."""
    # Create a temporary database file
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
        db_path = Path(temp_file.name)

    try:
        # Create a test database
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()

            # Create test table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS compounds (
                    ID INTEGER PRIMARY KEY,
                    Formula TEXT,
                    Phase TEXT,
                    Tmin REAL,
                    Tmax REAL,
                    H298 REAL,
                    S298 REAL,
                    ReliabilityClass INTEGER
                )
            """)

            # Insert test data
            test_data = [
                (1, 'H2O', 'l', 273.15, 373.15, -285.83, 69.91, 1),
                (2, 'H2O', 'g', 373.15, 673.15, -241.82, 188.72, 1),
                (3, 'HCl', 'g', 100.0, 1000.0, -92.30, 186.69, 1),
            ]

            cursor.executemany("""
                INSERT INTO compounds (ID, Formula, Phase, Tmin, Tmax, H298, S298, ReliabilityClass)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, test_data)

            conn.commit()

        # Test the search functionality
        db_connector = DatabaseConnector(db_path)
        sql_builder = SQLBuilder()
        searcher = CompoundSearcher(sql_builder, db_connector)

        # Test basic search
        result = searcher.search_compound('H2O')
        assert result.compound_formula == 'H2O'
        assert len(result.records_found) == 2
        assert result.filter_statistics is not None
        assert result.execution_time_ms is not None

        # Test search with temperature filtering
        result_temp = searcher.search_compound('H2O', temperature_range=(300.0, 350.0))
        assert len(result_temp.records_found) >= 1

        # Test search with phase filtering
        result_phase = searcher.search_compound('H2O', phase='g')
        assert all(r.phase == 'g' for r in result_phase.records_found)

        # Test search for non-existent compound
        result_none = searcher.search_compound('Nonexistent')
        assert len(result_none.records_found) == 0

        print("OK All basic functionality tests passed!")
        return True

    except Exception as e:
        print(f"ERROR Test failed: {e}")
        return False

    finally:
        # Clean up temporary database file
        try:
            if db_path.exists():
                db_path.unlink()
        except PermissionError:
            # Ignore permission errors on Windows
            pass


if __name__ == "__main__":
    success = test_search_functionality()
    if success:
        print("\nSUCCESS Search module functionality test completed successfully!")
    else:
        print("\nFAILED Search module functionality test failed!")
        exit(1)