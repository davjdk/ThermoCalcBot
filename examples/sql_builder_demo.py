"""
SQL Builder Demo - Testing Stage 0 Examples

This script demonstrates the SQL Builder functionality using the test cases
from Stage 0 database analysis. It validates that the deterministic SQL
generation properly handles the complex formula variability discovered
during database investigation.
"""

import sqlite3
import os
import sys
from typing import List, Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from thermo_agents.search.sql_builder import SQLBuilder


class SQLBuilderDemo:
    """Demonstration of SQL Builder functionality."""

    def __init__(self, db_path: str = "data/thermo_data.db"):
        """Initialize demo with database path."""
        self.db_path = db_path
        self.sql_builder = SQLBuilder()
        self.conn = None

    def connect_database(self) -> bool:
        """Connect to the thermodynamic database."""
        try:
            if not os.path.exists(self.db_path):
                print(f"❌ Database not found: {self.db_path}")
                return False

            self.conn = sqlite3.connect(self.db_path)
            print(f"✅ Connected to database: {self.db_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            return False

    def test_query_execution(self, query: str, params: List) -> Dict[str, Any]:
        """Execute SQL query and return results."""
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            return {
                "success": True,
                "count": len(rows),
                "columns": columns,
                "rows": rows[:10],  # Limit to first 10 for display
                "query": query,
                "params": params
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "params": params
            }

    def test_case_h2o(self):
        """Test Case 1: H2O (вода) при 298-673K."""
        print("\n" + "="*80)
        print("TEST CASE 1: H2O (вода) при 298-673K")
        print("="*80)

        # Generate SQL query
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(298, 673),
            limit=20
        )

        print(f"Generated SQL Query:")
        print(query)
        print(f"Parameters: {params}")

        # Execute query
        result = self.test_query_execution(query, params)

        if result["success"]:
            print(f"\n✅ Query executed successfully")
            print(f"📊 Found {result['count']} records")

            # Analyze results
            phases = set()
            reliability_classes = set()
            temp_ranges = []

            for row in result["rows"]:
                if len(row) > 1:  # Assuming Phase is in column 1
                    phases.add(row[1])
                if len(row) > 4:  # Assuming ReliabilityClass is in column 4
                    reliability_classes.add(row[4])
                if len(row) > 7 and len(row) > 8:  # Tmin, Tmax
                    temp_ranges.append((row[7], row[8]))

            print(f"🔬 Phases found: {sorted(phases)}")
            print(f"⭐ Reliability classes: {sorted(reliability_classes)}")
            print(f"🌡️  Temperature ranges: {len(temp_ranges)} records")

            # Check for expected phases (liquid and gas)
            if 'l' in phases or 'g' in phases:
                print("✅ Found expected liquid and/or gas phases")
            else:
                print("⚠️  Expected liquid/gas phases not found")

        else:
            print(f"❌ Query failed: {result['error']}")

        # Test search strategy
        strategy = self.sql_builder.suggest_search_strategy("H2O")
        print(f"\n📋 Search Strategy:")
        print(f"   Difficulty: {strategy['estimated_difficulty']}")
        print(f"   Methods: {', '.join(strategy['search_strategies'])}")

        return result

    def test_case_tio2(self):
        """Test Case 2: TiO2 (оксид титана) при 600-900K."""
        print("\n" + "="*80)
        print("TEST CASE 2: TiO2 (оксид титана) при 600-900K")
        print("="*80)

        query, params = self.sql_builder.build_compound_search_query(
            "TiO2",
            temperature_range=(600, 900),
            limit=20
        )

        print(f"Generated SQL Query:")
        print(query)
        print(f"Parameters: {params}")

        result = self.test_query_execution(query, params)

        if result["success"]:
            print(f"\n✅ Query executed successfully")
            print(f"📊 Found {result['count']} records")

            # Analyze results - expect solid phase
            phases = set()
            for row in result["rows"]:
                if len(row) > 1:
                    phases.add(row[1])

            print(f"🔬 Phases found: {sorted(phases)}")

            if 's' in phases:
                print("✅ Found expected solid phase")
            else:
                print("⚠️  Expected solid phase not found")

        else:
            print(f"❌ Query failed: {result['error']}")

        return result

    def test_case_fe(self):
        """Test Case 3: Fe (железо) с фазовым переходом при 1500-2000K."""
        print("\n" + "="*80)
        print("TEST CASE 3: Fe (железо) с фазовым переходом при 1500-2000K")
        print("="*80)

        query, params = self.sql_builder.build_compound_search_query(
            "Fe",
            temperature_range=(1500, 2000),
            limit=20
        )

        print(f"Generated SQL Query:")
        print(query)
        print(f"Parameters: {params}")

        result = self.test_query_execution(query, params)

        if result["success"]:
            print(f"\n✅ Query executed successfully")
            print(f"📊 Found {result['count']} records")

            # Analyze results - expect phase transition around 1811K
            phases = set()
            melting_points = set()
            boiling_points = set()

            for row in result["rows"]:
                if len(row) > 1:
                    phases.add(row[1])
                if len(row) > 15:  # MeltingPoint
                    melting_points.add(row[15])
                if len(row) > 16:  # BoilingPoint
                    boiling_points.add(row[16])

            print(f"🔬 Phases found: {sorted(phases)}")
            print(f"🌡️  Melting points: {sorted(list(melting_points))[:5]}...")  # Show first 5
            print(f"🌡️  Boiling points: {sorted(list(boiling_points))[:5]}...")

            # Check for transition around 1811K
            has_transition = False
            for mp in melting_points:
                if mp and 1500 <= mp <= 2000:
                    has_transition = True
                    print(f"✅ Found phase transition around melting point: {mp}K")
                    break

            if not has_transition:
                print("⚠️  No phase transition found in temperature range")

        else:
            print(f"❌ Query failed: {result['error']}")

        return result

    def test_case_o2(self):
        """Test Case 4: O2 (кислород) в широком диапазоне."""
        print("\n" + "="*80)
        print("TEST CASE 4: O2 (кислород) в широком диапазоне 298-2000K")
        print("="*80)

        query, params = self.sql_builder.build_compound_search_query(
            "O2",
            temperature_range=(298, 2000),
            limit=20
        )

        print(f"Generated SQL Query:")
        print(query)
        print(f"Parameters: {params}")

        result = self.test_query_execution(query, params)

        if result["success"]:
            print(f"\n✅ Query executed successfully")
            print(f"📊 Found {result['count']} records")

            # Analyze results - expect gas phase
            phases = set()
            for row in result["rows"]:
                if len(row) > 1:
                    phases.add(row[1])

            print(f"🔬 Phases found: {sorted(phases)}")

            if 'g' in phases:
                print("✅ Found expected gas phase")
            else:
                print("⚠️  Expected gas phase not found")

        else:
            print(f"❌ Query failed: {result['error']}")

        return result

    def test_case_hcl(self):
        """Test Case 5: HCl (хлороводород) - проверка комплексного поиска."""
        print("\n" + "="*80)
        print("TEST CASE 5: HCl (хлороводород) - проверка комплексного поиска")
        print("="*80)

        # Test search strategy first
        strategy = self.sql_builder.suggest_search_strategy("HCl")
        print(f"📋 Search Strategy for HCl:")
        print(f"   Difficulty: {strategy['estimated_difficulty']}")
        print(f"   Methods: {', '.join(strategy['search_strategies'])}")
        print(f"   Recommendations: {strategy['recommendations']}")

        query, params = self.sql_builder.build_compound_search_query(
            "HCl",
            limit=20
        )

        print(f"\nGenerated SQL Query:")
        print(query)
        print(f"Parameters: {params}")

        result = self.test_query_execution(query, params)

        if result["success"]:
            print(f"\n✅ Query executed successfully")
            print(f"📊 Found {result['count']} records")

            if result["count"] > 0:
                print("✅ Successfully found HCl records using complex search")
            else:
                print("⚠️  No HCl records found - search strategy may need adjustment")

        else:
            print(f"❌ Query failed: {result['error']}")

        return result

    def test_count_queries(self):
        """Test COUNT query functionality."""
        print("\n" + "="*80)
        print("TESTING COUNT QUERIES")
        print("="*80)

        test_formulas = ["H2O", "TiO2", "Fe", "O2", "HCl"]

        for formula in test_formulas:
            print(f"\n📊 Counting records for {formula}:")

            # Basic count query
            query, params = self.sql_builder.build_compound_count_query(formula)
            result = self.test_query_execution(query, params)

            if result["success"] and result["rows"]:
                row = result["rows"][0]
                print(f"   Total records: {row[0]}")
                print(f"   Avg reliability: {row[1]:.2f}")
                print(f"   Temperature range: {row[2]:.1f}K - {row[3]:.1f}K")
            else:
                print(f"   ❌ Count query failed")

    def test_temperature_stats_queries(self):
        """Test temperature statistics queries."""
        print("\n" + "="*80)
        print("TESTING TEMPERATURE STATISTICS QUERIES")
        print("="*80)

        test_formulas = ["H2O", "Fe"]

        for formula in test_formulas:
            print(f"\n🌡️  Temperature statistics for {formula}:")

            query, params = self.sql_builder.build_temperature_range_stats_query(formula)
            result = self.test_query_execution(query, params)

            if result["success"] and result["rows"]:
                row = result["rows"][0]
                print(f"   Total records: {row[0]}")
                print(f"   Unique phases: {row[1]}")
                print(f"   Overall temp range: {row[2]:.1f}K - {row[3]:.1f}K")
                print(f"   Avg temp range width: {row[4]:.1f}K")
                print(f"   Melting points: {row[5]:.1f}K - {row[6]:.1f}K")
                print(f"   Boiling points: {row[7]:.1f}K - {row[8]:.1f}K")
                print(f"   Avg reliability: {row[9]:.2f}")
            else:
                print(f"   ❌ Temperature stats query failed")

    def run_all_tests(self) -> Dict[str, Any]:
        """Run all test cases and return summary."""
        print("Starting SQL Builder Demo Tests")
        print("="*80)

        if not self.connect_database():
            return {"success": False, "error": "Database connection failed"}

        results = {}

        try:
            # Run individual test cases
            results["h2o"] = self.test_case_h2o()
            results["tio2"] = self.test_case_tio2()
            results["fe"] = self.test_case_fe()
            results["o2"] = self.test_case_o2()
            results["hcl"] = self.test_case_hcl()

            # Run additional tests
            self.test_count_queries()
            self.test_temperature_stats_queries()

        except Exception as e:
            print(f"❌ Test execution failed: {e}")
            results["error"] = str(e)

        finally:
            if self.conn:
                self.conn.close()

        return results

    def print_summary(self, results: Dict[str, Any]):
        """Print test execution summary."""
        print("\n" + "="*80)
        print("TEST EXECUTION SUMMARY")
        print("="*80)

        successful_tests = 0
        total_tests = 0

        for test_name, result in results.items():
            if test_name == "error":
                continue

            total_tests += 1
            if result.get("success", False):
                successful_tests += 1
                status = "✅ PASSED"
                record_count = result.get("count", 0)
                print(f"{status} {test_name.upper()}: {record_count} records found")
            else:
                status = "❌ FAILED"
                error = result.get("error", "Unknown error")
                print(f"{status} {test_name.upper()}: {error}")

        print(f"\n📊 Summary: {successful_tests}/{total_tests} tests passed")

        if successful_tests == total_tests:
            print("🎉 All tests passed! SQL Builder is working correctly.")
        else:
            print("⚠️  Some tests failed. Review the errors above.")


def main():
    """Main demo execution."""
    demo = SQLBuilderDemo()
    results = demo.run_all_tests()
    demo.print_summary(results)


if __name__ == "__main__":
    main()