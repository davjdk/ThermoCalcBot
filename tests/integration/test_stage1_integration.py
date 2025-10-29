"""
Integration tests for Stage 1 enhanced search functionality.

This module tests the complete Stage 1 implementation including:
- TemperatureRangeResolver integration
- CompoundSearcher Stage 1 methods
- FilterPipeline Stage 1 context handling
- Data model enhancements
- End-to-end Stage 1 workflow

These tests validate that the Stage 1 requirements from the specification
are met comprehensively.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from thermo_agents.filtering.temperature_range_resolver import TemperatureRangeResolver
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.models.search import DatabaseRecord, CompoundSearchResult
from thermo_agents.models.extraction import ExtractedReactionParameters


class TestStage1Integration:
    """Integration tests for Stage 1 enhanced search functionality."""

    @pytest.fixture
    def test_db_path(self):
        """Create a temporary test database with comprehensive test data."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        temp_db.close()
        db_path = Path(temp_db.name)

        # Create test database with FeO example from specification
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create table matching actual database schema
        cursor.execute("""
            CREATE TABLE compounds (
                Formula TEXT,
                Structure TEXT,
                FirstName TEXT,
                SecondName TEXT,
                Phase TEXT,
                CAS TEXT,
                MeltingPoint REAL,
                BoilingPoint REAL,
                Density REAL,
                Solubility REAL,
                Color INTEGER,
                H298 REAL,
                S298 REAL,
                Tmin REAL,
                Tmax REAL,
                f1 REAL,
                f2 REAL,
                f3 REAL,
                f4 REAL,
                f5 REAL,
                f6 REAL,
                ReliabilityClass INTEGER,
                Reference TEXT
            )
        """)

        # Insert FeO test data (from specification example)
        feo_data = [
            # Record that would be found by old logic (limited range)
            ("FeO", None, "Iron(II) oxide limited", None, "s", None, 1650.0, 3687.0, None, None, None, 0.0, 0.0, 600.0, 900.0, 25.0, 8.0, 0.0, 0.0, 0.0, 0.0, 2, None),
            # Additional records that should be found by Stage 1
            ("FeO", None, "Iron(II) oxide wide range", None, "s", None, 1650.0, 3687.0, None, None, None, -265.053, 59.807, 298.0, 1650.0, 30.0, 10.0, 0.0, 0.0, 0.0, 0.0, 1, None),
            ("FeO", None, "Iron(II) oxide high temp", None, "s", None, 1650.0, 3687.0, None, None, None, -240.0, 58.0, 900.0, 1650.0, 32.0, 12.0, 0.0, 0.0, 0.0, 0.0, 1, None),
            ("FeO", None, "Iron(II) oxide liquid", None, "l", None, 1650.0, 3687.0, None, None, None, -200.0, 62.0, 1650.0, 3687.0, 35.0, 15.0, 0.0, 0.0, 0.0, 0.0, 1, None),
            ("FeO", None, "Iron(II) oxide gas", None, "g", None, 1650.0, 3687.0, None, None, None, -150.0, 68.0, 3687.0, 5000.0, 40.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1, None),
        ]

        # Insert O2 data for multi-compound tests
        o2_data = [
            ("O2", None, "Oxygen wide range", None, "g", None, 54.36, 90.20, None, None, None, 0.0, 205.0, 298.0, 2000.0, 31.0, 20.0, 0.0, 0.0, 0.0, 0.0, 1, None),
            ("O2", None, "Oxygen high temp", None, "g", None, 54.36, 90.20, None, None, None, 10.0, 210.0, 2000.0, 6000.0, 35.0, 25.0, 0.0, 0.0, 0.0, 0.0, 1, None),
        ]

        # Insert all data
        insert_sql = """
            INSERT INTO compounds VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for record in feo_data + o2_data:
            cursor.execute(insert_sql, record)

        conn.commit()
        conn.close()

        yield db_path

        # Cleanup
        db_path.unlink()

    @pytest.fixture
    def components(self, test_db_path):
        """Initialize test components with test database."""
        db_connector = DatabaseConnector(test_db_path)
        sql_builder = SQLBuilder()
        compound_searcher = CompoundSearcher(sql_builder, db_connector)
        temperature_resolver = TemperatureRangeResolver()
        filter_pipeline = FilterPipeline()

        return {
            "db_connector": db_connector,
            "sql_builder": sql_builder,
            "compound_searcher": compound_searcher,
            "temperature_resolver": temperature_resolver,
            "filter_pipeline": filter_pipeline
        }

    def test_feo_stage1_enhanced_search(self, components):
        """Test the FeO example from the Stage 1 specification."""
        searcher = components["compound_searcher"]
        resolver = components["temperature_resolver"]

        # User requests FeO in range 773-973K
        user_range = (773.0, 973.0)

        # Stage 1: Enhanced search that ignores temperature limitations
        result = searcher.search_compound_stage1(
            formula="FeO",
            user_temperature_range=user_range
        )

        # Verify Stage 1 requirements are met
        assert result.compound_formula == "FeO"
        assert len(result.records_found) == 5, f"Expected 5 records, got {len(result.records_found)}"
        assert result.stage1_mode is True
        assert result.original_user_range == user_range

        # Test TemperatureRangeResolver integration (sets full_calculation_range)
        compounds_data = {"FeO": result.records_found}
        range_analysis = resolver.determine_calculation_range(compounds_data, user_range)

        # Update result with TemperatureRangeResolver analysis
        result.set_stage1_ranges(
            full_calculation_range=range_analysis.calculation_range,
            original_user_range=user_range
        )

        assert result.full_calculation_range is not None

        # Verify H298 correctness (Stage 1 core requirement)
        records_with_h298 = [r for r in result.records_found if abs(r.h298 + 265.053) < 1e-6]
        assert len(records_with_h298) >= 1, "Should find record with correct H298 = -265.053"

        # Verify temperature range expansion
        assert result.has_range_expansion(), "Should have range expansion"
        expansion_info = result.get_range_expansion_info()
        assert expansion_info["expanded"] is True
        assert expansion_info["expansion_factor"] > 1.0

        # Test TemperatureRangeResolver integration
        compounds_data = {"FeO": result.records_found}
        range_analysis = resolver.determine_calculation_range(compounds_data, user_range)

        assert range_analysis.calculation_range[0] <= 298.15, "Should include 298K"
        assert range_analysis.calculation_range[1] >= 3687.0, "Should include high temperature data"
        assert range_analysis.includes_298K is True

        print("FeO Stage 1 test passed:")
        print(f"   Records found: {len(result.records_found)} (expected 5)")
        print(f"   Range expansion: {expansion_info['expansion_factor']:.1f}x")
        print(f"   Calculation range: {range_analysis.calculation_range[0]:.0f}-{range_analysis.calculation_range[1]:.0f}K")
        print(f"   Correct H298 found: {len(records_with_h298) >= 1}")

    def test_stage1_filter_pipeline_integration(self, components):
        """Test FilterPipeline integration with Stage 1 context."""
        searcher = components["compound_searcher"]
        pipeline = components["filter_pipeline"]

        # Get Stage 1 search results
        search_result = searcher.search_compound_stage1(
            formula="FeO",
            user_temperature_range=(773.0, 973.0)
        )

        # Create Stage 1 context
        stage1_context = pipeline.create_stage1_context(
            compound_formula="FeO",
            user_temperature_range=(773.0, 973.0),
            full_calculation_range=(298.0, 5000.0)
        )

        # Verify Stage 1 context properties
        assert stage1_context.stage1_mode is True
        assert stage1_context.original_user_range == (773.0, 973.0)
        assert stage1_context.full_calculation_range == (298.0, 5000.0)
        assert stage1_context.effective_temperature_range == (298.0, 5000.0)

        # Execute Stage 1 pipeline
        filter_result = pipeline.execute_stage1(
            records=search_result.records_found,
            compound_formula="FeO",
            user_temperature_range=(773.0, 973.0),
            full_calculation_range=(298.0, 5000.0)
        )

        # Verify filtering worked
        assert len(filter_result.filtered_records) > 0
        assert filter_result.is_found is True

        print(f"✅ Stage 1 FilterPipeline integration test passed:")
        print(f"   Input records: {len(search_result.records_found)}")
        print(f"   Filtered records: {len(filter_result.filtered_records)}")
        print(f"   Context effective range: {stage1_context.effective_temperature_range}")

    def test_multi_compound_stage1_analysis(self, components):
        """Test TemperatureRangeResolver with multiple compounds."""
        resolver = components["temperature_resolver"]
        searcher = components["compound_searcher"]

        # Get data for multiple compounds
        feo_result = searcher.search_compound_stage1("FeO")
        o2_result = searcher.search_compound_stage1("O2")

        compounds_data = {
            "FeO": feo_result.records_found,
            "O2": o2_result.records_found
        }

        user_range = (773.0, 973.0)

        # Test range analysis for multiple compounds
        range_analysis = resolver.determine_calculation_range(compounds_data, user_range)

        # Should find intersection that covers both compounds
        assert range_analysis.calculation_range[0] <= 298.0
        assert range_analysis.calculation_range[1] >= 1650.0  # FeO melting point
        assert range_analysis.includes_298K is True

        # Test coverage validation
        coverage = resolver.validate_range_coverage(compounds_data, range_analysis.calculation_range)
        assert coverage["FeO"] is True
        assert coverage["O2"] is True

        # Get statistics
        stats = resolver.get_range_statistics(compounds_data)
        assert stats["total_records"] > 0
        assert stats["compounds_count"] == 2
        assert stats["compounds_with_data"] == 2

        print(f"✅ Multi-compound Stage 1 analysis test passed:")
        print(f"   Calculation range: {range_analysis.calculation_range[0]:.0f}-{range_analysis.calculation_range[1]:.0f}K")
        print(f"   Total records: {stats['total_records']}")
        print(f"   Coverage validation: {coverage}")

    def test_stage1_data_model_enhancements(self, components):
        """Test Stage 1 enhancements to data models."""
        searcher = components["compound_searcher"]

        # Get Stage 1 search result
        result = searcher.search_compound_stage1(
            formula="FeO",
            user_temperature_range=(500.0, 800.0)
        )

        # Test Stage 1 model methods
        assert result.get_effective_temperature_range() is not None

        # Set full calculation range using TemperatureRangeResolver (simulating full workflow)
        resolver = components["temperature_resolver"]
        compounds_data = {"FeO": result.records_found}
        range_analysis = resolver.determine_calculation_range(compounds_data, (500.0, 800.0))
        result.set_stage1_ranges(range_analysis.calculation_range, (500.0, 800.0))

        assert result.has_range_expansion() is True

        expansion_info = result.get_range_expansion_info()
        assert "expanded" in expansion_info
        assert "expansion_factor" in expansion_info
        assert "records_in_original_range" in expansion_info
        assert "records_in_full_range" in expansion_info

        summary = result.get_stage1_summary()
        assert summary["stage1_enabled"] is True
        assert "range_expansion" in summary
        assert "original_user_range" in summary
        assert "full_calculation_range" in summary

        print(f"✅ Stage 1 data model enhancements test passed:")
        print(f"   Stage 1 mode: {summary['stage1_enabled']}")
        print(f"   Expansion factor: {expansion_info['expansion_factor']:.1f}x")
        print(f"   Records in original range: {expansion_info['records_in_original_range']}")
        print(f"   Records in full range: {expansion_info['records_in_full_range']}")

    def test_stage1_backward_compatibility(self, components):
        """Test that Stage 1 changes don't break existing functionality."""
        searcher = components["compound_searcher"]

        # Test regular search still works
        regular_result = searcher.search_compound(
            formula="FeO",
            temperature_range=(600.0, 900.0),
            ignore_temperature_range=False
        )

        assert regular_result.compound_formula == "FeO"
        assert regular_result.stage1_mode is False
        assert regular_result.full_calculation_range is None
        assert regular_result.original_user_range is None

        # Test that Stage 1 search is different
        stage1_result = searcher.search_compound_stage1(
            formula="FeO",
            user_temperature_range=(600.0, 900.0)
        )

        assert stage1_result.stage1_mode is True
        assert len(stage1_result.records_found) > len(regular_result.records_found)

        print(f"✅ Backward compatibility test passed:")
        print(f"   Regular search records: {len(regular_result.records_found)}")
        print(f"   Stage 1 search records: {len(stage1_result.records_found)}")
        print(f"   Regular search Stage 1 mode: {regular_result.stage1_mode}")
        print(f"   Stage 1 search Stage 1 mode: {stage1_result.stage1_mode}")

    def test_stage1_recommendations_system(self, components):
        """Test Stage 1 recommendations and warnings system."""
        resolver = components["temperature_resolver"]
        searcher = components["compound_searcher"]

        # Get search result
        result = searcher.search_compound_stage1(
            formula="FeO",
            user_temperature_range=(400.0, 600.0)
        )

        # Get range analysis with recommendations
        compounds_data = {"FeO": result.records_found}
        range_analysis = resolver.determine_calculation_range(compounds_data, (400.0, 600.0))

        # Verify recommendations are generated
        assert len(range_analysis.recommendations) > 0
        assert isinstance(range_analysis.recommendations, list)

        # Verify search result warnings include Stage 1 information
        stage1_warnings = [w for w in result.warnings if "Stage 1" in w]
        assert len(stage1_warnings) > 0

        print(f"✅ Stage 1 recommendations system test passed:")
        print(f"   Recommendations generated: {len(range_analysis.recommendations)}")
        print(f"   Stage 1 warnings: {len(stage1_warnings)}")
        print(f"   Sample recommendation: {range_analysis.recommendations[0] if range_analysis.recommendations else 'None'}")

    def test_stage1_performance_characteristics(self, components):
        """Test that Stage 1 performance is acceptable."""
        import time

        searcher = components["compound_searcher"]
        resolver = components["temperature_resolver"]

        # Measure Stage 1 search performance
        start_time = time.time()
        result = searcher.search_compound_stage1("FeO")
        search_time = time.time() - start_time

        # Measure range resolver performance
        start_time = time.time()
        compounds_data = {"FeO": result.records_found}
        range_analysis = resolver.determine_calculation_range(compounds_data, (500.0, 1000.0))
        resolver_time = time.time() - start_time

        # Performance assertions (should be fast for small datasets)
        assert search_time < 2.0, f"Stage 1 search too slow: {search_time:.2f}s"
        assert resolver_time < 0.5, f"Range resolver too slow: {resolver_time:.3f}s"

        print(f"✅ Stage 1 performance test passed:")
        print(f"   Search time: {search_time:.3f}s")
        print(f"   Resolver time: {resolver_time:.3f}s")
        print(f"   Records processed: {len(result.records_found)}")


if __name__ == "__main__":
    # Run specific test for manual verification
    print("Running Stage 1 integration tests...")

    # This allows running individual tests for debugging
    test_instance = TestStage1Integration()

    # Create test database
    temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db.close()
    db_path = Path(temp_db.name)

    try:
        # Initialize database (simplified version)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE compounds (
                ID INTEGER PRIMARY KEY,
                Formula TEXT,
                Name TEXT,
                Phase TEXT,
                Tmin REAL,
                Tmax REAL,
                H298 REAL,
                S298 REAL,
                F1 REAL,
                F2 REAL,
                F3 REAL,
                F4 REAL,
                F5 REAL,
                F6 REAL,
                MeltingPoint REAL,
                BoilingPoint REAL,
                ReliabilityClass INTEGER
            )
        """)

        # Insert minimal test data
        cursor.execute("""
            INSERT INTO compounds VALUES
            (1, 'FeO', 'Iron(II) oxide', 's', 298.0, 1650.0, -265.053, 59.807, 30.0, 10.0, 0.0, 0.0, 0.0, 0.0, 1650.0, 3687.0, 1)
        """)
        conn.commit()
        conn.close()

        # Initialize components
        db_connector = DatabaseConnector(db_path)
        sql_builder = SQLBuilder()
        searcher = CompoundSearcher(sql_builder, db_connector)
        resolver = TemperatureRangeResolver()

        # Run basic test
        print("Testing basic Stage 1 functionality...")
        result = searcher.search_compound_stage1("FeO", (500.0, 800.0))
        print(f"Found {len(result.records_found)} records")
        print(f"Stage 1 mode: {result.stage1_mode}")
        print(f"Range expansion: {result.has_range_expansion()}")

    finally:
        # Cleanup
        db_path.unlink()

    print("Manual test completed.")