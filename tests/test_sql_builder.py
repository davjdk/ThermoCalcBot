"""
Tests for SQL Builder module.

Tests cover deterministic SQL generation based on Stage 0 database analysis.
"""

import pytest
from src.thermo_agents.search.sql_builder import SQLBuilder, FilterPriorities


class TestSQLBuilder:
    """Test cases for SQLBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sql_builder = SQLBuilder()

    def test_basic_compound_search_query(self):
        """Test basic compound search query generation."""
        query, params = self.sql_builder.build_compound_search_query("H2O")

        assert "SELECT * FROM compounds" in query
        assert "TRIM(Formula) = 'H2O'" in query
        assert "Formula LIKE 'H2O(%'" in query
        assert "Formula LIKE 'H2O%'" in query
        assert "ORDER BY" in query
        assert "LIMIT ?" in query
        assert params == [100]  # Default limit

    def test_complex_compound_search_query(self):
        """Test complex compound search query generation."""
        query, params = self.sql_builder.build_compound_search_query("HCl")

        assert "TRIM(Formula) = 'HCl'" in query
        assert "Formula LIKE 'HCl(%'" in query
        assert "Formula LIKE 'HCl%'" in query
        # HCl is a simple formula, so no containment search
        assert "Formula LIKE '%HCl%'" not in query
        assert params == [100]

    def test_very_complex_compound_search_query(self):
        """Test very complex compound search query generation."""
        query, params = self.sql_builder.build_compound_search_query("Fe2(SO4)3")

        assert "TRIM(Formula) = 'Fe2(SO4)3'" in query
        assert "Formula LIKE 'Fe2(SO4)3(%'" in query
        assert "Formula LIKE 'Fe2(SO4)3%'" in query
        # Complex formula should include containment search
        assert "Formula LIKE '%Fe2(SO4)3%'" in query
        assert params == [100]

    def test_temperature_filtering(self):
        """Test temperature filtering in query generation."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(298, 673)
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert 298 in params
        assert 673 in params
        assert 100 in params  # Limit

    def test_phase_filtering(self):
        """Test phase filtering in query generation."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            phase="g"
        )

        assert "Phase = ?" in query
        assert "g" in params
        assert 100 in params  # Limit

    def test_combined_filters(self):
        """Test combined temperature and phase filtering."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(298, 673),
            phase="l"
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert "Phase = ?" in query
        assert 298 in params
        assert 673 in params
        assert "l" in params
        assert 100 in params  # Limit

    def test_custom_limit(self):
        """Test custom result limit."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            limit=50
        )

        assert params[-1] == 50  # Last parameter is the limit

    def test_order_clause_priorities(self):
        """Test ORDER BY clause includes proper prioritization."""
        query, params = self.sql_builder.build_compound_search_query("H2O")

        assert "ORDER BY" in query
        assert "ReliabilityClass" in query
        assert "Tmax - Tmin" in query
        assert "LENGTH(TRIM(Formula))" in query
        assert "ID ASC" in query

    def test_sql_escaping(self):
        """Test SQL value escaping."""
        escaped = self.sql_builder._escape_sql("H2O' AND 1=1")
        assert escaped == "H2O'' AND 1=1"

    def test_count_query(self):
        """Test COUNT query generation."""
        query, params = self.sql_builder.build_compound_count_query("H2O")

        assert "SELECT COUNT(*) as total_count" in query
        assert "AVG(ReliabilityClass) as avg_reliability" in query
        assert "MIN(Tmin) as min_temp" in query
        assert "MAX(Tmax) as max_temp" in query
        assert "TRIM(Formula) = 'H2O'" in query

    def test_count_query_with_filters(self):
        """Test COUNT query with temperature and phase filters."""
        query, params = self.sql_builder.build_compound_count_query(
            "H2O",
            temperature_range=(298, 673),
            phase="g"
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert "Phase = ?" in query
        assert 298 in params
        assert 673 in params
        assert "g" in params

    def test_temperature_stats_query(self):
        """Test temperature statistics query generation."""
        query, params = self.sql_builder.build_temperature_range_stats_query("H2O")

        assert "COUNT(*) as total_records" in query
        assert "COUNT(DISTINCT Phase) as unique_phases" in query
        assert "MIN(Tmin) as overall_min_temp" in query
        assert "MAX(Tmax) as overall_max_temp" in query
        assert "AVG(Tmax - Tmin) as avg_temp_range" in query
        assert "MIN(MeltingPoint) as min_melting_point" in query
        assert "MAX(BoilingPoint) as max_boiling_point" in query
        assert params == []

    def test_custom_priorities(self):
        """Test SQL builder with custom filtering priorities."""
        custom_priorities = FilterPriorities(
            reliability_classes=[1, 2],  # Only top 2 classes
            prefer_wider_range=False,
            require_thermo_data=True
        )
        custom_builder = SQLBuilder(priorities=custom_priorities)

        query, params = custom_builder.build_compound_search_query("H2O")

        assert "ORDER BY" in query
        assert "ReliabilityClass" in query
        # Should not include temperature range in ordering
        assert "(Tmax - Tmin) DESC" not in query


class TestSearchStrategySuggestions:
    """Test search strategy suggestion functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sql_builder = SQLBuilder()

    def test_simple_formula_strategy(self):
        """Test strategy suggestion for simple formulas."""
        strategy = self.sql_builder.suggest_search_strategy("H2O")

        assert strategy["formula"] == "H2O"
        assert strategy["estimated_difficulty"] == "easy"
        assert "exact_match" in strategy["search_strategies"]
        assert "phase_in_parentheses" in strategy["search_strategies"]
        assert "prefix_search" in strategy["search_strategies"]

    def test_complex_formula_strategy(self):
        """Test strategy suggestion for complex formulas."""
        strategy = self.sql_builder.suggest_search_strategy("HCl")

        assert strategy["formula"] == "HCl"
        assert strategy["estimated_difficulty"] == "medium"
        assert "exact_match" in strategy["search_strategies"]
        assert "prefix_search" in strategy["search_strategies"]
        assert "containment_search" in strategy["search_strategies"]
        assert any("prefix search" in rec for rec in strategy["recommendations"])

    def test_very_complex_formula_strategy(self):
        """Test strategy suggestion for very complex formulas."""
        strategy = self.sql_builder.suggest_search_strategy("Fe2(SO4)3")

        assert strategy["formula"] == "Fe2(SO4)3"
        assert strategy["estimated_difficulty"] == "hard"
        assert "exact_match" in strategy["search_strategies"]
        assert "prefix_search" in strategy["search_strategies"]
        assert "containment_search" in strategy["search_strategies"]
        assert any("alternative formula" in rec for rec in strategy["recommendations"])

    def test_strategy_recommendations_content(self):
        """Test that strategy recommendations include key insights."""
        strategy = self.sql_builder.suggest_search_strategy("H2O")

        recommendations = strategy["recommendations"]

        # Should include general recommendations based on database analysis
        assert any("temperature filtering" in rec for rec in recommendations)
        assert any("ReliabilityClass = 1" in rec for rec in recommendations)
        assert any("phase transitions" in rec for rec in recommendations)


class TestDatabaseAnalysisIntegration:
    """Test integration of database analysis findings."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sql_builder = SQLBuilder()

    def test_hcl_prefix_search_support(self):
        """Test that HCl prefix search is properly supported."""
        # From database analysis: HCl needs prefix search
        query, params = self.sql_builder.build_compound_search_query("HCl")

        assert "Formula LIKE 'HCl%'" in query
        # HCl is treated as a simple compound, but also gets containment search
        assert "Formula LIKE '%HCl%'" in query

    def test_co2_prefix_search_support(self):
        """Test that CO2 prefix search is properly supported."""
        # From database analysis: CO2 needs prefix search
        query, params = self.sql_builder.build_compound_search_query("CO2")

        assert "Formula LIKE 'CO2%'" in query

    def test_nh3_prefix_search_support(self):
        """Test that NH3 prefix search is properly supported."""
        # From database analysis: NH3 needs prefix search
        query, params = self.sql_builder.build_compound_search_query("NH3")

        assert "Formula LIKE 'NH3%'" in query

    def test_ch4_prefix_search_support(self):
        """Test that CH4 prefix search is properly supported."""
        # From database analysis: CH4 needs prefix search
        query, params = self.sql_builder.build_compound_search_query("CH4")

        assert "Formula LIKE 'CH4%'" in query

    def test_phase_in_parentheses_support(self):
        """Test support for formulas with phases in parentheses."""
        query, params = self.sql_builder.build_compound_search_query("H2O")

        assert "Formula LIKE 'H2O(%'" in query

    def test_reliability_class_prioritization(self):
        """Test that ReliabilityClass prioritization is implemented."""
        query, params = self.sql_builder.build_compound_search_query("H2O")

        assert "ReliabilityClass" in query
        assert "CASE ReliabilityClass" in query

    def test_temperature_range_filtering(self):
        """Test temperature range filtering based on 100% coverage finding."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O", temperature_range=(298, 673)
        )

        # Database analysis showed 100% temperature coverage
        assert "? >= Tmin AND ? <= Tmax" in query
        # No NULL handling needed as all records have temperature ranges
        assert "Tmin IS NOT NULL" not in query
        assert "Tmax IS NOT NULL" not in query

    def test_thermodynamic_data_completeness_assumption(self):
        """Test that queries assume complete thermodynamic data."""
        # Database analysis showed 100% thermodynamic data coverage
        query, params = self.sql_builder.build_compound_search_query("H2O")

        # No need to check for NULL thermodynamic data in WHERE clause
        assert "H298 IS NOT NULL" not in query
        assert "S298 IS NOT NULL" not in query
        # But data completeness can be used in ordering
        assert "Tmax - Tmin" in query  # Temperature range width


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.sql_builder = SQLBuilder()

    def test_empty_formula(self):
        """Test handling of empty formula."""
        query, params = self.sql_builder.build_compound_search_query("")

        assert "TRIM(Formula) = ''" in query
        assert "Formula LIKE '%'" in query
        assert "Formula LIKE '%('" in query

    def test_whitespace_only_formula(self):
        """Test handling of whitespace-only formula."""
        query, params = self.sql_builder.build_compound_search_query("  ")

        assert "TRIM(Formula) = ''" in query

    def test_sql_injection_attempt(self):
        """Test SQL injection prevention."""
        malicious_formula = "H2O'; DROP TABLE compounds; --"
        query, params = self.sql_builder.build_compound_search_query(malicious_formula)

        # Single quotes should be escaped
        assert "H2O''; DROP TABLE compounds; --" in query
        assert not "'; DROP TABLE" in query

    def test_very_long_formula(self):
        """Test handling of very long formulas."""
        long_formula = "C" * 1000
        query, params = self.sql_builder.build_compound_search_query(long_formula)

        assert "TRIM(Formula)" in query
        assert long_formula in query

    def test_special_characters_in_formula(self):
        """Test handling of special characters in formulas."""
        special_formula = "Fe[SO4]2"
        query, params = self.sql_builder.build_compound_search_query(special_formula)

        assert "Fe[SO4]2" in query
        assert "Formula LIKE '%Fe[SO4]2%'" in query

    def test_zero_temperature_range(self):
        """Test zero temperature range filtering."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(298.15, 298.15)
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert params.count(298.15) == 2

    def test_negative_temperature(self):
        """Test negative temperature filtering."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(-100, 100)
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert -100 in params
        assert 100 in params

    def test_extreme_temperatures(self):
        """Test extreme temperature ranges from database analysis."""
        # Database analysis showed range: 0.00015K to 100,000K
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            temperature_range=(0.0001, 100000)
        )

        assert "? >= Tmin AND ? <= Tmax" in query
        assert 0.0001 in params
        assert 100000 in params

    def test_zero_limit(self):
        """Test zero result limit."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            limit=0
        )

        assert params[-1] == 0

    def test_very_large_limit(self):
        """Test very large result limit."""
        query, params = self.sql_builder.build_compound_search_query(
            "H2O",
            limit=1000000
        )

        assert params[-1] == 1000000