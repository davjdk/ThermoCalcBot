"""
Integration tests for the search module.

This module tests the integration between SQLBuilder, DatabaseConnector,
and CompoundSearcher using the actual thermodynamic database.
"""

import pytest
import os
from pathlib import Path

from src.thermo_agents.search.sql_builder import SQLBuilder, FilterPriorities
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.models.search import CoverageStatus


@pytest.mark.integration
class TestSearchModuleIntegration:
    """Integration tests for the complete search module."""

    @classmethod
    def setup_class(cls):
        """Set up class-level test fixtures."""
        # Find the database file
        db_paths = [
            Path("data/thermo_data.db"),
            Path("../data/thermo_data.db"),
            Path("../../data/thermo_data.db"),
        ]

        cls.db_path = None
        for path in db_paths:
            if path.exists():
                cls.db_path = path.resolve()
                break

        if cls.db_path is None:
            pytest.skip("Thermodynamic database not found")

        # Initialize components
        cls.db_connector = DatabaseConnector(cls.db_path)
        cls.sql_builder = SQLBuilder()
        cls.searcher = CompoundSearcher(cls.sql_builder, cls.db_connector)

    def test_database_connection(self):
        """Test that we can connect to the real database."""
        with self.db_connector:
            assert self.db_connector.check_connection()

            # Get basic table info
            table_count = self.db_connector.get_table_count('compounds')
            assert table_count > 0

            # Get table structure
            table_info = self.db_connector.get_table_info('compounds')
            assert len(table_info) > 0

    def test_sql_builder_integration(self):
        """Test SQL builder with realistic queries."""
        # Test basic compound search query
        query, params = self.sql_builder.build_compound_search_query(
            formula='H2O',
            temperature_range=(298.0, 673.0),
            phase='l',
            limit=10
        )

        assert query is not None
        assert isinstance(params, list)
        assert 'SELECT * FROM compounds' in query
        assert 'H2O' in query

        # Test count query
        count_query, count_params = self.sql_builder.build_compound_count_query(
            formula='H2O',
            temperature_range=(298.0, 673.0)
        )

        assert count_query is not None
        assert 'COUNT(*)' in count_query

        # Test temperature stats query
        temp_query, temp_params = self.sql_builder.build_temperature_range_stats_query(
            formula='H2O'
        )

        assert temp_query is not None
        assert 'MIN(Tmin)' in temp_query
        assert 'MAX(Tmax)' in temp_query

    def test_compound_searcher_real_data_h2o(self):
        """Test compound searcher with real H2O data."""
        result = self.searcher.search_compound('H2O')

        # Basic result validation
        assert result.compound_formula == 'H2O'
        assert len(result.records_found) > 0
        assert result.filter_statistics is not None
        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0

        # Check that we found multiple phases of H2O
        phases = result.get_unique_phases()
        assert len(phases) >= 1

        # Check that records have expected data structure
        for record in result.records_found[:3]:  # Check first 3 records
            assert record.formula is not None
            assert record.id is not None

            # Temperature data should be present for most records
            if record.tmin is not None and record.tmax is not None:
                assert record.tmin > 0
                assert record.tmax > record.tmin

    def test_compound_searcher_real_data_hcl(self):
        """Test compound searcher with real HCl data."""
        result = self.searcher.search_compound('HCl')

        assert result.compound_formula == 'HCl'
        assert len(result.records_found) > 0

        # HCl should primarily be found in gas phase
        gas_records = [r for r in result.records_found if r.phase == 'g']
        assert len(gas_records) > 0

    def test_compound_searcher_real_data_co2(self):
        """Test compound searcher with real CO2 data."""
        result = self.searcher.search_compound('CO2')

        assert result.compound_formula == 'CO2'
        assert len(result.records_found) > 0

        # CO2 should primarily be found in gas phase
        gas_records = [r for r in result.records_found if r.phase == 'g']
        assert len(gas_records) > 0

    def test_compound_searcher_with_temperature_filtering(self):
        """Test temperature filtering with real data."""
        # Search H2O with specific temperature range
        result = self.searcher.search_compound(
            'H2O',
            temperature_range=(298.0, 373.0)  # Room temperature to boiling point
        )

        assert len(result.records_found) > 0

        # Check that returned records overlap with temperature range
        overlapping_records = 0
        for record in result.records_found:
            if record.tmin is not None and record.tmax is not None:
                if record.tmax >= 298.0 and record.tmin <= 373.0:
                    overlapping_records += 1

        assert overlapping_records > 0

    def test_compound_searcher_with_phase_filtering(self):
        """Test phase filtering with real data."""
        # Search for liquid water only
        result = self.searcher.search_compound('H2O', phase='l')

        assert len(result.records_found) > 0

        # All returned records should be liquid phase
        liquid_records = [r for r in result.records_found if r.phase == 'l']
        assert len(liquid_records) == len(result.records_found)

        # Search for gaseous water only
        result_gas = self.searcher.search_compound('H2O', phase='g')

        if len(result_gas.records_found) > 0:
            # All returned records should be gas phase
            gas_records = [r for r in result_gas.records_found if r.phase == 'g']
            assert len(gas_records) == len(result_gas.records_found)

    def test_compound_searcher_complex_formulas(self):
        """Test search with complex chemical formulas."""
        complex_formulas = ['CH4', 'NH3', 'TiO2', 'Fe2O3', 'CaCO3']

        for formula in complex_formulas:
            result = self.searcher.search_compound(formula)

            # Should find some records for most common compounds
            if len(result.records_found) > 0:
                assert result.compound_formula == formula

                # Check that found records contain the formula
                matching_records = [
                    r for r in result.records_found
                    if formula in r.formula or r.formula in formula
                ]
                assert len(matching_records) > 0

    def test_compound_searcher_nonexistent_compounds(self):
        """Test search for compounds that likely don't exist."""
        nonexistent_formulas = ['XyZ123', 'Unobtanium', 'Element119']

        for formula in nonexistent_formulas:
            result = self.searcher.search_compound(formula)

            assert result.compound_formula == formula
            assert len(result.records_found) == 0
            assert result.coverage_status == CoverageStatus.NONE
            assert len(result.warnings) > 0

    def test_search_strategy_recommendations(self):
        """Test search strategy recommendations with real formulas."""
        test_formulas = ['H2O', 'HCl', 'TiO2', 'ComplexFormula123']

        for formula in test_formulas:
            strategy = self.searcher.get_search_strategy(formula)

            assert strategy.formula == formula
            assert len(strategy.search_strategies) > 0
            assert strategy.estimated_difficulty in ['easy', 'medium', 'hard']
            assert isinstance(strategy.recommendations, list)

    def test_count_queries(self):
        """Test count queries with real data."""
        # Count H2O records
        count_data = self.searcher.count_compound_records('H2O')
        assert isinstance(count_data, dict)

        # Count with temperature filtering
        count_data_temp = self.searcher.count_compound_records(
            'H2O',
            temperature_range=(298.0, 373.0)
        )
        assert isinstance(count_data_temp, dict)

        # Count with phase filtering
        count_data_phase = self.searcher.count_compound_records('H2O', phase='l')
        assert isinstance(count_data_phase, dict)

    def test_temperature_statistics(self):
        """Test temperature statistics queries."""
        # Get temperature statistics for H2O
        temp_stats = self.searcher.get_temperature_statistics('H2O')
        assert isinstance(temp_stats, dict)

        if temp_stats:
            # Should contain temperature-related fields
            temp_fields = ['min_temp', 'max_temp', 'avg_temp_range']
            found_fields = [field for field in temp_fields if field in temp_stats]
            assert len(found_fields) > 0

    def test_search_pipeline_tracking(self):
        """Test detailed pipeline tracking with real data."""
        result, pipeline = self.searcher.search_compound_with_pipeline('H2O')

        assert isinstance(result, object)  # CompoundSearchResult
        assert isinstance(pipeline, object)  # SearchPipeline

        # Should have executed some operations
        assert hasattr(pipeline, 'initial_results')
        assert hasattr(pipeline, 'final_results')
        assert hasattr(pipeline, 'operations')

    def test_database_record_parsing_real_data(self):
        """Test parsing of real database records."""
        # Get a raw database row
        with self.db_connector:
            raw_rows = self.db_connector.execute_query(
                "SELECT * FROM compounds WHERE Formula LIKE 'H2O%' LIMIT 3"
            )

        if raw_rows:
            # Parse each row
            for row in raw_rows:
                record = self.searcher._parse_record(row)

                # Validate parsed record
                assert record is not None
                assert hasattr(record, 'id')
                assert hasattr(record, 'formula')

                # Check that common fields are properly parsed
                if record.tmin is not None:
                    assert isinstance(record.tmin, (int, float))
                if record.reliability_class is not None:
                    assert isinstance(record.reliability_class, int)

    def test_statistics_calculation_real_data(self):
        """Test statistics calculation with real data."""
        # Get some H2O records
        result = self.searcher.search_compound('H2O', limit=50)

        if result.records_found:
            stats = self.searcher._calculate_statistics(result.records_found)

            assert stats.total_records == len(result.records_found)
            assert stats.unique_phases >= 1
            assert stats.phase_distribution is not None

            # Check phase distribution
            total_in_distribution = sum(stats.phase_distribution.values())
            assert total_in_distribution == len(result.records_found)

            # Check reliability distribution if present
            if stats.reliability_distribution:
                total_reliability = sum(stats.reliability_distribution.values())
                assert total_reliability <= len(result.records_found)

    def test_coverage_analysis_real_data(self):
        """Test coverage status analysis with real data."""
        # Test full coverage scenario
        result_full = self.searcher.search_compound(
            'H2O',
            temperature_range=(298.0, 350.0)  # Common laboratory range
        )

        if result_full.records_found:
            coverage = self.searcher._determine_coverage_status(
                result_full.records_found,
                (298.0, 350.0)
            )
            assert coverage in [CoverageStatus.FULL, CoverageStatus.PARTIAL]

        # Test no coverage scenario
        result_none = self.searcher.search_compound('NonexistentCompound')
        coverage_none = self.searcher._determine_coverage_status(
            result_none.records_found,
            (298.0, 350.0)
        )
        assert coverage_none == CoverageStatus.NONE

    def test_performance_large_search(self):
        """Test performance with larger search operations."""
        import time

        # Time a search operation
        start_time = time.time()
        result = self.searcher.search_compound('H2O', limit=100)
        end_time = time.time()

        execution_time = (end_time - start_time) * 1000  # Convert to ms

        # Should complete reasonably quickly (adjust threshold as needed)
        assert execution_time < 5000  # 5 seconds max

        # Result should also have reasonable execution time recorded
        assert result.execution_time_ms is not None
        assert result.execution_time_ms > 0

    def test_edge_cases_real_data(self):
        """Test edge cases with real database data."""
        # Search with very large limit
        result_large = self.searcher.search_compound('H2O', limit=1000)
        assert len(result_large.records_found) <= 1000

        # Search with very specific temperature range
        result_specific = self.searcher.search_compound(
            'H2O',
            temperature_range=(298.15, 298.15)  # Exactly standard conditions
        )
        # Should handle gracefully

        # Search for formulas with special characters
        result_special = self.searcher.search_compound('Fe2O3')
        # Should handle metal oxides correctly

    def test_database_schema_validation(self):
        """Test validation of database schema compatibility."""
        with self.db_connector:
            # Check that required columns exist
            table_info = self.db_connector.get_table_info('compounds')
            column_names = [col['name'].lower() for col in table_info]

            required_columns = [
                'id', 'formula', 'phase', 'tmin', 'tmax',
                'h298', 's298', 'reliabilityclass'
            ]

            missing_columns = [
                col for col in required_columns
                if col not in column_names
            ]

            # Allow for some column name variations
            assert len(missing_columns) <= 2  # Allow for minor schema differences

    def test_search_with_priorities(self):
        """Test search with custom priority settings."""
        # Create custom priorities
        custom_priorities = FilterPriorities(
            reliability_classes=[1, 2, 0, 3, 4, 5],  # Prioritize class 1, then 2
            prefer_wider_range=True,
            require_thermo_data=True
        )

        custom_sql_builder = SQLBuilder(custom_priorities)
        custom_searcher = CompoundSearcher(custom_sql_builder, self.db_connector)

        result = custom_searcher.search_compound('H2O', limit=5)

        assert len(result.records_found) <= 5
        if result.records_found:
            # Check that high reliability records are preferred
            high_reliability = [
                r for r in result.records_found
                if r.reliability_class in [1, 2]
            ]
            # Should prioritize high reliability records
            assert len(high_reliability) > 0

    def test_data_quality_assessment(self):
        """Test assessment of data quality in search results."""
        # Get a diverse set of results
        result = self.searcher.search_compound('H2O', limit=20)

        if result.records_found:
            # Check data completeness
            complete_records = 0
            records_with_thermo_data = 0
            high_reliability_records = 0

            for record in result.records_found:
                # Check for basic data completeness
                if record.formula and record.phase:
                    complete_records += 1

                # Check for thermodynamic data
                if record.h298 is not None and record.s298 is not None:
                    records_with_thermo_data += 1

                # Check reliability
                if record.reliability_class == 1:
                    high_reliability_records += 1

            # Most records should be complete
            assert complete_records >= len(result.records_found) * 0.8

            # Many records should have thermodynamic data
            assert records_with_thermo_data >= len(result.records_found) * 0.5

            # Should have some high reliability data
            assert high_reliability_records > 0

    @pytest.mark.slow
    def test_comprehensive_formula_search(self):
        """Test comprehensive search across many formula types."""
        # Test a variety of formula types
        test_formulas = [
            # Simple compounds
            'H2', 'O2', 'N2', 'Cl2',
            # Common compounds
            'H2O', 'CO2', 'NH3', 'CH4', 'HCl', 'SO2',
            # Metal oxides
            'Fe2O3', 'CaO', 'MgO', 'Al2O3',
            # Acids and bases
            'H2SO4', 'HNO3', 'NaOH', 'KOH',
            # Simple organic compounds
            'CH3OH', 'C2H5OH', 'C6H6',
        ]

        results_summary = {}

        for formula in test_formulas:
            result = self.searcher.search_compound(formula)
            results_summary[formula] = {
                'records_found': len(result.records_found),
                'phases': result.get_unique_phases(),
                'coverage': result.coverage_status,
                'warnings': len(result.warnings)
            }

        # Should find data for most common compounds
        successful_searches = sum(
            1 for summary in results_summary.values()
            if summary['records_found'] > 0
        )

        # At least 50% of common compounds should be found
        assert successful_searches >= len(test_formulas) * 0.5

        # Print summary for manual inspection
        print(f"\nSearch summary for {len(test_formulas)} formulas:")
        print(f"Successful searches: {successful_searches}/{len(test_formulas)}")
        for formula, summary in results_summary.items():
            if summary['records_found'] > 0:
                print(f"  {formula}: {summary['records_found']} records, "
                      f"phases: {summary['phases']}")