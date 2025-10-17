"""Unit tests for chemical utilities."""

import pytest
from src.thermo_agents.utils.chem_utils import (
    parse_formula,
    sum_formulas,
    is_ionic_formula,
    is_ionic_name,
    query_contains_charge,
    normalize_composite_formula,
    expand_composite_candidates,
)

# Mock record class for testing
class MockRecord:
    def __init__(self, formula, name=None, rowid=1):
        self.Formula = formula
        self.FirstName = name
        self.rowid = rowid


class TestParseFormula:
    """Test parse_formula function."""

    def test_simple_formula(self):
        """Test parsing simple chemical formulas."""
        result = parse_formula("CO2")
        expected = {"C": 1, "O": 2}
        assert result == expected

    def test_complex_formula(self):
        """Test parsing more complex formulas."""
        result = parse_formula("Li2TiO3")
        expected = {"Li": 2, "Ti": 1, "O": 3}
        assert result == expected

    def test_single_element(self):
        """Test parsing single element formulas."""
        result = parse_formula("Na")
        expected = {"Na": 1}
        assert result == expected

    def test_with_spaces(self):
        """Test parsing formulas with spaces."""
        result = parse_formula(" H2O ")
        expected = {"H": 2, "O": 1}
        assert result == expected

    def test_composite_formula(self):
        """Test parsing composite formulas."""
        result = parse_formula("Li2O*TiO2")
        expected = {"Li": 2, "O": 3, "Ti": 1}
        assert result == expected


class TestSumFormulas:
    """Test sum_formulas function."""

    def test_sum_two_formulas(self):
        """Test summing two formulas."""
        parts = ["Li2O", "TiO2"]
        result = sum_formulas(parts)
        expected = {"Li": 2, "O": 3, "Ti": 1}
        assert result == expected

    def test_sum_three_formulas(self):
        """Test summing three formulas."""
        parts = ["NaCl", "KBr", "LiF"]
        result = sum_formulas(parts)
        expected = {"Na": 1, "Cl": 1, "K": 1, "Br": 1, "Li": 1, "F": 1}
        assert result == expected

    def test_empty_parts(self):
        """Test summing empty parts list."""
        result = sum_formulas([])
        assert result == {}

    def test_parts_with_spaces(self):
        """Test summing parts with empty strings."""
        parts = ["Li2O", "", "TiO2", "  "]
        result = sum_formulas(parts)
        expected = {"Li": 2, "O": 3, "Ti": 1}
        assert result == expected


class TestIsIonicFormula:
    """Test is_ionic_formula function."""

    def test_ionic_with_plus(self):
        """Test detecting ionic formulas with +."""
        assert is_ionic_formula("CO2(+g)")
        assert is_ionic_formula("Na+")
        assert is_ionic_formula("Fe2+")

    def test_ionic_with_minus(self):
        """Test detecting ionic formulas with -."""
        assert is_ionic_formula("Cl-")
        assert is_ionic_formula("SO42-")
        assert is_ionic_formula("CO3(-2g)")

    def test_neutral_formula(self):
        """Test that neutral formulas are not detected as ionic."""
        assert not is_ionic_formula("CO2(g)")
        assert not is_ionic_formula("Li2TiO3")
        assert not is_ionic_formula("NaCl")

    def test_complex_ionic_patterns(self):
        """Test complex ionic patterns."""
        assert is_ionic_formula("Fe(+3g)")
        assert is_ionic_formula("Al(-2g)")
        assert is_ionic_formula("NH4+")
        assert is_ionic_formula("PO43-")


class TestIsIonicName:
    """Test is_ionic_name function."""

    def test_ionic_keywords(self):
        """Test detecting ionic keywords in names."""
        assert is_ionic_name("Carbon dioxide ion")
        assert is_ionic_name("Sodium cation")
        assert is_ionic_name("Chloride anion")
        assert is_ionic_name("Ionic compound")

    def test_neutral_names(self):
        """Test that neutral names are not detected as ionic."""
        assert not is_ionic_name("Carbon dioxide")
        assert not is_ionic_name("Lithium titanate")
        assert not is_ionic_name("Water")

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert is_ionic_name("ION")
        assert is_ionic_name("Cation")
        assert is_ionic_name("ANION")
        assert is_ionic_name("Ionic")

    def test_empty_name(self):
        """Test empty name handling."""
        assert not is_ionic_name("")
        assert not is_ionic_name(None)


class TestQueryContainsCharge:
    """Test query_contains_charge function."""

    def test_explicit_charge_symbols(self):
        """Test detection of explicit charge symbols."""
        assert query_contains_charge("CO2+")
        assert query_contains_charge("Na-")
        assert query_contains_charge("Fe2+")

    def test_ionic_keywords(self):
        """Test detection of ionic keywords."""
        assert query_contains_charge("carbon dioxide ion")
        assert query_contains_charge("sodium cation")
        assert query_contains_charge("chloride anion")

    def test_neutral_queries(self):
        """Test that neutral queries are not detected as ionic."""
        assert not query_contains_charge("CO2")
        assert not query_contains_charge("Li2TiO3")
        assert not query_contains_charge("water")

    def test_mixed_queries(self):
        """Test mixed queries."""
        assert query_contains_charge("CO2(g) ion")
        assert not query_contains_charge("CO2(g) gas")


class TestNormalizeCompositeFormula:
    """Test normalize_composite_formula function."""

    def test_standard_delimiter(self):
        """Test standard * delimiter."""
        result = normalize_composite_formula("Li2O*TiO2")
        assert result == "Li2O*TiO2"

    def test_bullet_delimiter(self):
        """Test bullet · delimiter."""
        result = normalize_composite_formula("Li2O·TiO2")
        assert result == "Li2O*TiO2"

    def test_dot_delimiter(self):
        """Test dot . delimiter."""
        result = normalize_composite_formula("Li2O.TiO2")
        assert result == "Li2O*TiO2"

    def test_spaces_and_delimiters(self):
        """Test spaces mixed with delimiters."""
        result = normalize_composite_formula(" Li2O · TiO2 ")
        assert result == "Li2O*TiO2"

    def test_simple_formula(self):
        """Test normalization of simple formulas."""
        result = normalize_composite_formula("CO2")
        assert result == "CO2"


class TestExpandCompositeCandidates:
    """Test expand_composite_candidates function."""

    def test_exact_composite_match(self):
        """Test finding exact composite matches."""
        query = "Li2TiO3"
        records = [
            MockRecord("Li2O*TiO2", "Lithium titanate", 1),
            MockRecord("CO2(g)", "Carbon dioxide", 2),
            MockRecord("FeO*Cr2O3", "Iron(III) chromate", 3),
        ]

        result = expand_composite_candidates(query, records)
        assert len(result) == 1
        assert result[0].Formula == "Li2O*TiO2"
        assert result[0].rowid == 1

    def test_no_composite_match(self):
        """Test when no composite matches exist."""
        query = "CO2"
        records = [
            MockRecord("Li2O*TiO2", "Lithium titanate", 1),
            MockRecord("FeO*Cr2O3", "Iron(III) chromate", 2),
        ]

        result = expand_composite_candidates(query, records)
        assert len(result) == 0

    def test_multiple_composite_matches(self):
        """Test finding multiple composite matches."""
        query = "Li2TiO3"
        records = [
            MockRecord("Li2O*TiO2", "Lithium titanate", 1),
            MockRecord("Li2O·TiO2", "Lithium titanate alternative", 2),
            MockRecord("Li2O.TiO2", "Lithium titanate another", 3),
        ]

        result = expand_composite_candidates(query, records)
        assert len(result) == 3

    def test_different_composite_patterns(self):
        """Test different composite formula patterns."""
        query = "LiCrO3"
        records = [
            MockRecord("Li2O*Cr2O3", "Lithium chromate", 1),  # Li2CrO4 - not match
            MockRecord("FeO*Cr2O3", "Iron(III) chromate", 2),  # FeCr2O4 - not match
        ]

        result = expand_composite_candidates(query, records)
        assert len(result) == 0

    def test_empty_records(self):
        """Test with empty records list."""
        result = expand_composite_candidates("Li2TiO3", [])
        assert len(result) == 0

    def test_records_without_formula(self):
        """Test handling records without Formula attribute."""
        class BadRecord:
            def __init__(self):
                self.FirstName = "Test"

        records = [BadRecord()]
        result = expand_composite_candidates("Li2TiO3", records)
        assert len(result) == 0

    def test_non_composite_formulas(self):
        """Test that non-composite formulas are ignored."""
        query = "Li2TiO3"
        records = [
            MockRecord("Li2O", "Lithium oxide", 1),
            MockRecord("TiO2", "Titanium dioxide", 2),
            MockRecord("CO2", "Carbon dioxide", 3),
        ]

        result = expand_composite_candidates(query, records)
        assert len(result) == 0