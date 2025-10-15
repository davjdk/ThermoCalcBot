"""
Unit tests for PhaseResolver.

Tests phase determination at given temperatures, phase normalization,
and phase transition analysis functionality.
"""

import pytest
from typing import List

from src.thermo_agents.models.search import DatabaseRecord
from src.thermo_agents.filtering.phase_resolver import PhaseResolver, PhaseTransition


class TestPhaseResolver:
    """Test cases for PhaseResolver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = PhaseResolver()

    def create_test_records(self) -> List[DatabaseRecord]:
        """Create test database records with various phase properties."""
        return [
            DatabaseRecord(
                id=1,
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
                id=2,
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
                id=3,
                formula="Fe(s)",
                phase="s",
                tmin=298.0,
                tmax=1800.0,
                h298=0.0,
                s298=27.3,
                f1=20.0,
                f2=5.0,
                f3=0.3,
                f4=-0.02,
                f5=0.002,
                f6=-0.0002,
                tmelt=1811.0,
                tboil=3134.0,
                reliability_class=2
            ),
            DatabaseRecord(
                id=4,
                formula="NH3(ao)",
                phase="ao",
                tmin=200.0,
                tmax=400.0,
                h298=-45.9,
                s298=192.8,
                f1=28.0,
                f2=9.0,
                f3=0.8,
                f4=-0.08,
                f5=0.008,
                f6=-0.0008,
                tmelt=195.0,
                tboil=240.0,
                reliability_class=1
            ),
            DatabaseRecord(
                id=5,
                formula="CO2",
                phase=None,  # No phase specified
                tmin=100.0,
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

    def test_get_phase_at_temperature_solid(self):
        """Test phase determination for solid state."""
        record = self.create_test_records()[2]  # Fe(s)

        # Below melting point - should be solid
        phase = self.resolver.get_phase_at_temperature(record, 300.0)
        assert phase == 's'

        # Well below melting point - still solid
        phase = self.resolver.get_phase_at_temperature(record, 100.0)
        assert phase == 's'

    def test_get_phase_at_temperature_liquid(self):
        """Test phase determination for liquid state."""
        record = self.create_test_records()[1]  # H2O(l)

        # Between melting and boiling points - should be liquid
        phase = self.resolver.get_phase_at_temperature(record, 300.0)
        assert phase == 'l'

    def test_get_phase_at_temperature_gas(self):
        """Test phase determination for gas state."""
        record = self.create_test_records()[0]  # H2O(g)

        # Above boiling point - should be gas
        phase = self.resolver.get_phase_at_temperature(record, 400.0)
        assert phase == 'g'

        # Well above boiling point - still gas
        phase = self.resolver.get_phase_at_temperature(record, 1000.0)
        assert phase == 'g'

    def test_get_phase_at_temperature_transition_points(self):
        """Test phase determination at transition points."""
        record = self.create_test_records()[1]  # H2O(l) with tmelt=273, tboil=373

        # At melting point - should be liquid (>= tmelt)
        phase = self.resolver.get_phase_at_temperature(record, 273.0)
        assert phase == 'l'

        # Just below melting point - should be solid
        phase = self.resolver.get_phase_at_temperature(record, 272.9)
        assert phase == 's'

        # At boiling point - should be gas (>= tboil)
        phase = self.resolver.get_phase_at_temperature(record, 373.0)
        assert phase == 'g'

        # Just below boiling point - should be liquid
        phase = self.resolver.get_phase_at_temperature(record, 372.9)
        assert phase == 'l'

    def test_extract_phase_from_formula(self):
        """Test phase extraction from formula strings."""
        # Standard phases
        assert self.resolver._extract_phase_from_formula("H2O(g)") == "g"
        assert self.resolver._extract_phase_from_formula("H2O(l)") == "l"
        assert self.resolver._extract_phase_from_formula("H2O(s)") == "s"
        assert self.resolver._extract_phase_from_formula("NaCl(aq)") == "aq"

        # Database-specific phases
        assert self.resolver._extract_phase_from_formula("NH3(ao)") == "ao"
        assert self.resolver._extract_phase_from_formula("Fe(ai)") == "ai"

        # No phase in formula
        assert self.resolver._extract_phase_from_formula("CO2") is None
        assert self.resolver._extract_phase_from_formula("H2O") is None

        # Empty formula
        assert self.resolver._extract_phase_from_formula("") is None
        assert self.resolver._extract_phase_from_formula(None) is None

    def test_normalize_phase(self):
        """Test phase normalization."""
        # Direct matches
        assert self.resolver.normalize_phase("s") == "s"
        assert self.resolver.normalize_phase("l") == "l"
        assert self.resolver.normalize_phase("g") == "g"
        assert self.resolver.normalize_phase("aq") == "aq"

        # Database-specific phases
        assert self.resolver.normalize_phase("a") == "a"
        assert self.resolver.normalize_phase("ao") == "ao"
        assert self.resolver.normalize_phase("ai") == "ai"

        # Case insensitive
        assert self.resolver.normalize_phase("S") == "s"
        assert self.resolver.normalize_phase("G") == "g"
        assert self.resolver.normalize_phase("L") == "l"

        # Synonyms
        assert self.resolver.normalize_phase("solid") == "s"
        assert self.resolver.normalize_phase("liquid") == "l"
        assert self.resolver.normalize_phase("gas") == "g"
        assert self.resolver.normalize_phase("aqueous") == "aq"
        assert self.resolver.normalize_phase("vapor") == "g"

        # Whitespace handling
        assert self.resolver.normalize_phase("  s  ") == "s"

        # Invalid phases
        assert self.resolver.normalize_phase("xyz") is None
        assert self.resolver.normalize_phase("") is None
        assert self.resolver.normalize_phase(None) is None

    def test_get_phase_transitions(self):
        """Test extraction of phase transition temperatures."""
        record = self.create_test_records()[0]  # H2O(g)

        transitions = self.resolver.get_phase_transitions(record)

        assert 'melting' in transitions
        assert 'boiling' in transitions
        assert transitions['melting'] == 273.0
        assert transitions['boiling'] == 373.0

    def test_is_phase_transition_temperature(self):
        """Test detection of phase transition temperatures."""
        record = self.create_test_records()[0]  # H2O(g) with tmelt=273, tboil=373

        # Exactly at transition points
        assert self.resolver.is_phase_transition_temperature(record, 273.0) == True
        assert self.resolver.is_phase_transition_temperature(record, 373.0) == True

        # Within tolerance
        assert self.resolver.is_phase_transition_temperature(record, 275.0, tolerance=5.0) == True
        assert self.resolver.is_phase_transition_temperature(record, 370.0, tolerance=5.0) == True

        # Outside tolerance
        assert self.resolver.is_phase_transition_temperature(record, 275.0, tolerance=1.0) == False
        assert self.resolver.is_phase_transition_temperature(record, 370.0, tolerance=1.0) == False

        # Far from transitions
        assert self.resolver.is_phase_transition_temperature(record, 300.0) == False
        assert self.resolver.is_phase_transition_temperature(record, 500.0) == False

    def test_get_stable_phases(self):
        """Test determination of stable phases in temperature range."""
        record = self.create_test_records()[1]  # H2O(l) with tmelt=273, tboil=373

        # Range spanning all three phases
        phases = self.resolver.get_stable_phases(record, (200.0, 500.0))

        assert 's' in phases
        assert 'l' in phases
        assert 'g' in phases

        # Check temperature ranges
        assert phases['s'][0] == 200.0
        assert phases['s'][1] == 273.0

        assert phases['l'][0] == 273.0
        assert phases['l'][1] == 373.0

        assert phases['g'][0] == 373.0
        assert phases['g'][1] == 500.0

    def test_get_stable_phases_single_phase(self):
        """Test stable phases when range covers only one phase."""
        record = self.create_test_records()[1]  # H2O(l) with tmelt=273, tboil=373

        # Only liquid range
        phases = self.resolver.get_stable_phases(record, (300.0, 350.0))

        assert 'l' in phases
        assert len(phases) == 1
        assert phases['l'] == (300.0, 350.0)

    def test_validate_phase_consistency(self):
        """Test phase consistency validation."""
        # Consistent record
        record1 = DatabaseRecord(
            id=1,
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
        )

        validation = self.resolver.validate_phase_consistency(record1)
        assert validation['is_consistent'] == True
        assert len(validation['issues']) == 0
        assert validation['formula_phase'] == 'g'
        assert validation['record_phase'] == 'g'

        # Inconsistent record
        record2 = DatabaseRecord(
            id=2,
            formula="H2O(g)",
            phase="l",  # Inconsistent with formula
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
        )

        validation = self.resolver.validate_phase_consistency(record2)
        assert validation['is_consistent'] == False
        assert len(validation['issues']) > 0
        assert validation['formula_phase'] == 'g'
        assert validation['record_phase'] == 'l'

        # Unphysical transition temperatures
        record3 = DatabaseRecord(
            id=3,
            formula="H2O(l)",
            phase="l",
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
            tmelt=500.0,  # Higher than boiling point
            tboil=400.0,
            reliability_class=1
        )

        validation = self.resolver.validate_phase_consistency(record3)
        assert validation['is_consistent'] == False
        assert any("плавления" in issue for issue in validation['issues'])

    def test_cache_functionality(self):
        """Test caching of phase determination results."""
        record = self.create_test_records()[0]
        temperature = 300.0

        # First call should compute and cache
        phase1 = self.resolver.get_phase_at_temperature(record, temperature)

        # Second call should use cache
        phase2 = self.resolver.get_phase_at_temperature(record, temperature)

        assert phase1 == phase2

        # Clear cache and verify recomputation
        self.resolver.clear_cache()
        phase3 = self.resolver.get_phase_at_temperature(record, temperature)
        assert phase3 == phase1

    def test_determine_phase_completeness(self):
        """Test that phase determination works with complete database data."""
        """
        Note: According to database analysis, MeltingPoint and BoilingPoint
        are 100% populated, so we always have complete phase transition data.
        """
        record = self.create_test_records()[0]  # Has complete phase transition data

        # Should be able to determine phase for any temperature
        phase_low = self.resolver.get_phase_at_temperature(record, 100.0)
        phase_mid = self.resolver.get_phase_at_temperature(record, 300.0)
        phase_high = self.resolver.get_phase_at_temperature(record, 500.0)

        assert phase_low == 's'  # Below melting
        assert phase_mid == 'l'  # Between melting and boiling
        assert phase_high == 'g'  # Above boiling

    def test_database_specific_phases(self):
        """Test handling of database-specific phase designations."""
        # Test amorphous phases found in database analysis
        assert self.resolver.normalize_phase("a") == "a"
        assert self.resolver.normalize_phase("ao") == "ao"
        assert self.resolver.normalize_phase("ai") == "ai"

        # Test extraction from formula
        assert self.resolver._extract_phase_from_formula("NH3(ao)") == "ao"
        assert self.resolver._extract_phase_from_formula("Fe(ai)") == "ai"

    def test_phase_distribution_from_database(self):
        """Test phases according to database analysis distribution."""
        """
        From database analysis:
        - g (54.9%), l (16.67%), s (16.02%)
        - a, ao, ai (amorphous phases - ~12% total)
        - aq (aqueous - rare)
        """

        # Test that we can handle all phases found in database
        common_phases = ['s', 'l', 'g', 'a', 'ao', 'ai', 'aq']

        for phase in common_phases:
            normalized = self.resolver.normalize_phase(phase)
            assert normalized is not None
            assert normalized in self.resolver.valid_phases or normalized in ['a', 'ao', 'ai']