"""
Unit tests for ComplexFormulaSearchStage and FormulaConsistencyStage.

Tests complex formula search strategies, duplicate handling,
and formula consistency validation functionality.
"""

import pytest
import sys
from pathlib import Path
from typing import List

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.thermo_agents.models.search import DatabaseRecord
from src.thermo_agents.filtering.filter_pipeline import FilterContext
from src.thermo_agents.filtering.complex_search_stage import (
    ComplexFormulaSearchStage, FormulaConsistencyStage
)


class TestComplexFormulaSearchStage:
    """Test cases for ComplexFormulaSearchStage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.stage = ComplexFormulaSearchStage()
        self.context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="H2O"
        )

    def create_test_records(self) -> List[DatabaseRecord]:
        """Create test database records with various formula formats."""
        return [
            DatabaseRecord(
                id=1,
                formula="H2O",
                phase=None,
                tmin=298.0,
                tmax=2000.0,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="H2O(g)",
                phase="g",
                tmin=298.0,
                tmax=2000.0,
                h298=-241.8,
                s298=188.7,
                f1=30.0,
                f2=10.0,
                f3=1.0,
                f4=-0.1,
                f5=0.01,
                f6=-0.001,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=3,
                formula="H2O(l)",
                phase="l",
                tmin=273.0,
                tmax=373.0,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=4,
                formula="HCL",  # Different compound
                phase="g",
                tmin=200.0,
                tmax=1000.0,
                h298=-92.3,
                s298=186.7,
                f1=28.0,
                f2=9.0,
                f3=0.8,
                f4=-0.08,
                f5=0.008,
                f6=-0.0008,
                tmelt=159.0,
                tboil=188.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=5,
                formula="2H2O",  # Isotope/similar compound
                phase="l",
                tmin=273.0,
                tmax=373.0,
                h298=-571.6,
                s298=139.8,
                f1=50.0,
                f2=16.0,
                f3=1.0,
                f4=-0.1,
                f5=0.01,
                f6=-0.001,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            )
        ]

    def test_complex_search_exact_match(self):
        """Test complex search with exact formula match."""
        records = self.create_test_records()
        filtered = self.stage.filter(records, self.context)

        # Should include records 1, 2, 3 (all H2O variants)
        # Should exclude records 4, 5 (different compounds)
        assert len(filtered) == 3

        formula_ids = [r.id for r in filtered]
        assert 1 in formula_ids
        assert 2 in formula_ids
        assert 3 in formula_ids
        assert 4 not in formula_ids
        assert 5 not in formula_ids

    def test_complex_search_hcl_prefix(self):
        """Test complex search for HCL (requires prefix search)."""
        context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="HCL"
        )
        records = self.create_test_records()
        filtered = self.stage.filter(records, context)

        # Should include record 4 (HCL)
        # Should exclude all H2O records
        assert len(filtered) == 1
        assert filtered[0].id == 4

    def test_complex_search_statistics(self):
        """Test complex search statistics collection."""
        records = self.create_test_records()
        self.stage.filter(records, self.context)

        stats = self.stage.get_statistics()

        assert 'target_formula' in stats
        assert 'search_method' in stats
        assert 'total_records_before' in stats
        assert 'total_records_after' in stats
        assert 'search_statistics' in stats
        assert 'execution_time_ms' in stats
        assert 'reduction_rate' in stats

        search_stats = stats['search_statistics']
        assert 'exact_matches' in search_stats
        assert 'phase_matches' in search_stats
        assert 'prefix_matches' in search_stats
        assert 'contains_matches' in search_stats

        assert stats['total_records_before'] == 5
        assert stats['total_records_after'] == 3
        assert search_stats['exact_matches'] == 1  # Record 1
        assert search_stats['phase_matches'] == 2  # Records 2, 3

    def test_determine_search_method(self):
        """Test search method determination."""
        # Simple molecules requiring prefix search
        assert self.stage._determine_search_method("HCL") == "prefix_required"
        assert self.stage._determine_search_method("CO2") == "prefix_required"
        assert self.stage._determine_search_method("NH3") == "prefix_required"

        # Isotopic formulas
        assert self.stage._determine_search_method("2H2O") == "isotope_possible"

        # Phase-aware formulas
        assert self.stage._determine_search_method("H2O(g)") == "phase_aware"

        # Ionic compounds
        assert self.stage._determine_search_method("NA+") == "ionic"
        assert self.stage._determine_search_method("CL-") == "ionic"

        # Standard formulas
        assert self.stage._determine_search_method("H2O") == "standard"

    def test_check_formula_match(self):
        """Test formula matching logic."""
        # Exact match
        match_type = self.stage._check_formula_match("H2O", "H2O")
        assert match_type == 'exact'

        # Phase match
        match_type = self.stage._check_formula_match("H2O(g)", "H2O")
        assert match_type == 'phase'

        # Prefix match
        match_type = self.stage._check_formula_match("H2O2", "H2O")
        assert match_type == 'prefix'

        # Isotope match
        match_type = self.stage._check_formula_match("2H2O", "H2O")
        assert match_type == 'contains'

        # No match
        match_type = self.stage._check_formula_match("CO2", "H2O")
        assert match_type is None

    def test_isotope_or_isomer_match(self):
        """Test isotope and isomer matching."""
        # Isotope match (same chemical symbols)
        assert self.stage._is_isotope_or_isomer_match("2H2O", "H2O") == True
        assert self.stage._is_isotope_or_isomer_match("H2O18", "H2O") == True

        # Different compounds
        assert self.stage._is_isotope_or_isomer_match("CO2", "H2O") == False
        assert self.stage._is_isotope_or_isomer_match("NH3", "H2O") == False

        # Complex formulas
        assert self.stage._is_isotope_or_isomer_match("C6H12O6", "C6H12O6") == True
        assert self.stage._is_isotope_or_isomer_match("13C6H12O6", "C6H12O6") == True

    def test_get_search_recommendations(self):
        """Test search recommendations for different formulas."""
        # Simple molecule requiring prefix search
        recommendations = self.stage.get_search_recommendations("HCL")
        assert "Formula LIKE 'HCL%'" in recommendations
        assert "TRIM(Formula) = 'HCL'" in recommendations
        assert "Formula LIKE '%HCL%'" in recommendations

        # Standard molecule
        recommendations = self.stage.get_search_recommendations("H2O")
        assert "TRIM(Formula) = 'H2O'" in recommendations[0]  # First recommendation
        assert any("Formula LIKE 'H2O(%'" in rec for rec in recommendations)

    def test_get_stage_name(self):
        """Test stage name."""
        assert self.stage.get_stage_name() == "Комплексный поиск формул"


class TestFormulaConsistencyStage:
    """Test cases for FormulaConsistencyStage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.stage = FormulaConsistencyStage(max_records_per_formula=2)
        self.context = FilterContext(
            temperature_range=(300.0, 500.0),
            compound_formula="H2O"
        )

    def create_test_records_with_duplicates(self) -> List[DatabaseRecord]:
        """Create test records with duplicates (simulating database structure)."""
        return [
            # H2O variants - same base formula, different phases/reliability
            DatabaseRecord(
                id=1,
                formula="H2O",
                phase=None,
                tmin=298.0,
                tmax=2000.0,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="H2O(g)",
                phase="g",
                tmin=298.0,
                tmax=2000.0,
                h298=-241.8,
                s298=188.7,
                f1=30.0,
                f2=10.0,
                f3=1.0,
                f4=-0.1,
                f5=0.01,
                f6=-0.001,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=3,
                formula="H2O(l)",
                phase="l",
                tmin=273.0,
                tmax=373.0,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=2  # Lower reliability
            ),
            DatabaseRecord(
                id=4,
                formula="H2O(s)",
                phase="s",
                tmin=200.0,
                tmax=273.0,
                h298=-292.0,
                s298=41.0,
                f1=15.0,
                f2=5.0,
                f3=0.3,
                f4=-0.03,
                f5=0.003,
                f6=-0.0003,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=3  # Lowest reliability
            ),
            # Different compound
            DatabaseRecord(
                id=5,
                formula="CO2",
                phase="g",
                tmin=200.0,
                tmax=2500.0,
                h298=-393.5,
                s298=213.7,
                f1=35.0,
                f2=12.0,
                f3=1.2,
                f4=-0.12,
                f5=0.012,
                f6=-0.0012,
                tmelt=194.0,
                tboil=195.0,
                reliability_class=1
            )
        ]

    def test_formula_consistency_deduplication(self):
        """Test formula consistency and deduplication."""
        records = self.create_test_records_with_duplicates()
        filtered = self.stage.filter(records, self.context)

        # Should have 3 H2O records (limited to max_records_per_formula=2, but we have different phases)
        # Actually, with max_records_per_formula=2, should select top 2 H2O records
        # Plus 1 CO2 record
        assert len(filtered) == 3

        # Check that best H2O records are selected (reliability class 1)
        h2o_records = [r for r in filtered if r.formula.startswith("H2O")]
        assert len(h2o_records) == 2
        assert all(r.reliability_class == 1 for r in h2o_records)

        # CO2 record should be included
        co2_records = [r for r in filtered if r.formula.startswith("CO2")]
        assert len(co2_records) == 1

    def test_formula_consistency_statistics(self):
        """Test formula consistency statistics collection."""
        records = self.create_test_records_with_duplicates()
        self.stage.filter(records, self.context)

        stats = self.stage.get_statistics()

        assert 'duplication_statistics' in stats
        assert 'deduplication_rate' in stats
        assert 'execution_time_ms' in stats
        assert 'max_records_per_formula' in stats

        dup_stats = stats['duplication_statistics']
        assert 'total_formulas' in dup_stats
        assert 'total_records_before' in dup_stats
        assert 'total_records_after' in dup_stats
        assert 'max_group_size' in dup_stats
        assert 'avg_group_size' in dup_stats

        assert dup_stats['total_records_before'] == 5
        assert dup_stats['total_records_after'] == 3
        assert dup_stats['total_formulas'] == 2  # H2O and CO2
        assert dup_stats['max_group_size'] == 4  # H2O group
        assert dup_stats['avg_group_size'] == 2.5  # 5 records / 2 formulas

    def test_formula_consistency_grouping(self):
        """Test formula grouping logic."""
        records = self.create_test_records_with_duplicates()

        # Simulate internal grouping logic
        formula_groups = {}
        for record in records:
            base_formula = record.formula.split('(')[0].strip().upper()
            if base_formula not in formula_groups:
                formula_groups[base_formula] = []
            formula_groups[base_formula].append(record)

        assert len(formula_groups) == 2
        assert 'H2O' in formula_groups
        assert 'CO2' in formula_groups
        assert len(formula_groups['H2O']) == 4
        assert len(formula_groups['CO2']) == 1

    def test_formula_consistency_priority_sorting(self):
        """Test priority sorting within formula groups."""
        records = self.create_test_records_with_duplicates()

        # Group by base formula and sort
        formula_groups = {}
        for record in records:
            base_formula = record.formula.split('(')[0].strip().upper()
            if base_formula not in formula_groups:
                formula_groups[base_formula] = []
            formula_groups[base_formula].append(record)

        # Sort H2O group by reliability class
        h2o_group = formula_groups['H2O']
        h2o_group.sort(key=lambda r: (
            r.reliability_class,
            -(r.tmax - r.tmin) if r.tmax and r.tmin else 0
        ))

        # Check sorting (best reliability first)
        assert h2o_group[0].reliability_class == 1
        assert h2o_group[1].reliability_class == 1
        assert h2o_group[2].reliability_class == 2
        assert h2o_group[3].reliability_class == 3

    def test_formula_consistency_max_records_limit(self):
        """Test max_records_per_formula limiting."""
        stage = FormulaConsistencyStage(max_records_per_formula=1)
        records = self.create_test_records_with_duplicates()
        filtered = stage.filter(records, self.context)

        # Should have only 1 H2O record (best) + 1 CO2 record
        assert len(filtered) == 2

        h2o_records = [r for r in filtered if r.formula.startswith("H2O")]
        assert len(h2o_records) == 1
        assert h2o_records[0].reliability_class == 1

    def test_get_stage_name(self):
        """Test stage name."""
        assert self.stage.get_stage_name() == "Удаление дубликатов"

    def test_formula_consistency_edge_cases(self):
        """Test edge cases in formula consistency."""
        # Empty records list
        filtered = self.stage.filter([], self.context)
        assert len(filtered) == 0

        # Single record
        single_record = [self.create_test_records_with_duplicates()[0]]
        filtered = self.stage.filter(single_record, self.context)
        assert len(filtered) == 1

        # All same formula
        stage = FormulaConsistencyStage(max_records_per_formula=3)
        same_formula_records = [
            DatabaseRecord(
                id=i,
                formula="H2O",
                phase=None,
                tmin=298.0 + i * 10,
                tmax=2000.0 + i * 10,
                h298=-285.8,
                s298=69.9,
                f1=25.0,
                f2=8.0,
                f3=0.5,
                f4=-0.05,
                f5=0.005,
                f6=-0.0005,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1 + i
            )
            for i in range(5)
        ]

        filtered = stage.filter(same_formula_records, self.context)
        assert len(filtered) == 3  # Limited by max_records_per_formula
        assert all(r.reliability_class == 1 for r in filtered)  # Best reliability