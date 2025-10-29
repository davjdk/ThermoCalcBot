"""
Unit tests for TransitionDataManager - Stage 4 Implementation.

Tests the transition data management functionality including:
- Extraction of transition data from database records
- Calculation of transition enthalpies from H298 differences
- Heuristic estimation for missing data
- Validation of transition consistency
- Caching functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging

from src.thermo_agents.models.search import (
    DatabaseRecord,
    PhaseTransition,
    TransitionType
)
from src.thermo_agents.calculations.transition_data_manager import (
    TransitionDataManager,
    TransitionDataError,
    CompoundType
)


class TestTransitionDataManager:
    """Test cases for TransitionDataManager."""

    @pytest.fixture
    def calculator(self):
        """Create a TransitionDataManager instance."""
        mock_thermo_calc = Mock()
        return TransitionDataManager(mock_thermo_calc)

    @pytest.fixture
    def feo_solid_record(self):
        """Create a sample FeO solid record."""
        record = Mock(spec=DatabaseRecord)
        record.formula = "FeO"
        record.phase = "s"
        record.Tmin = 298.15
        record.Tmax = 600.0
        record.H298 = -265.053  # kJ/mol
        record.S298 = 59.807    # J/(mol·K)
        record.MeltingPoint = 1650.0
        record.BoilingPoint = 3687.0
        record.id = 1
        return record

    @pytest.fixture
    def feo_liquid_record(self):
        """Create a sample FeO liquid record."""
        record = Mock(spec=DatabaseRecord)
        record.formula = "FeO"
        record.phase = "l"
        record.Tmin = 1650.0
        record.Tmax = 5000.0
        record.H298 = -254.106  # kJ/mol
        record.S298 = 54.365    # J/(mol·K)
        record.MeltingPoint = 1650.0
        record.BoilingPoint = 3687.0
        record.id = 2
        return record

    @pytest.fixture
    def feo_gas_record(self):
        """Create a sample FeO gas record."""
        record = Mock(spec=DatabaseRecord)
        record.formula = "FeO"
        record.phase = "g"
        record.Tmin = 3687.0
        record.Tmax = 6000.0
        record.H298 = -200.0    # kJ/mol (hypothetical)
        record.S298 = 80.0      # J/(mol·K) (hypothetical)
        record.MeltingPoint = 1650.0
        record.BoilingPoint = 3687.0
        record.id = 3
        return record

    def test_extract_transition_data_complete(self, calculator, feo_solid_record, feo_liquid_record, feo_gas_record):
        """Test extraction of complete transition data for FeO."""
        records = [feo_solid_record, feo_liquid_record, feo_gas_record]

        # Mock thermodynamic calculator responses
        def mock_calc_properties(record, temperature):
            if record.phase == 's':
                return Mock(enthalpy=-240500.0)  # J/mol at 1650K
            elif record.phase == 'l':
                return Mock(enthalpy=-209000.0)  # J/mol at 1650K
            elif record.phase == 'g':
                return Mock(enthalpy=-180000.0)  # J/mol at 3687K

        calculator.thermodynamic_calculator.calculate_properties.side_effect = mock_calc_properties

        transitions = calculator.extract_transition_data(records)

        # Should find both melting and boiling transitions
        assert len(transitions) == 2

        # Check melting transition
        melting = next((t for t in transitions if t.transition_type == TransitionType.MELTING), None)
        assert melting is not None
        assert melting.temperature == 1650.0
        assert melting.from_phase == 's'
        assert melting.to_phase == 'l'
        assert melting.delta_H_transition > 0  # Should be positive
        assert melting.delta_S_transition > 0  # Should be positive

        # Check boiling transition
        boiling = next((t for t in transitions if t.transition_type == TransitionType.BOILING), None)
        assert boiling is not None
        assert boiling.temperature == 3687.0
        assert boiling.from_phase == 'l'
        assert boiling.to_phase == 'g'
        assert boiling.delta_H_transition > 0  # Should be positive
        assert boiling.delta_S_transition > 0  # Should be positive

    def test_extract_transition_data_no_liquid_phase(self, calculator, feo_solid_record, feo_gas_record):
        """Test extraction when only solid and gas phases are available (sublimation)."""
        records = [feo_solid_record, feo_gas_record]

        # Mock thermodynamic calculator responses
        def mock_calc_properties(record, temperature):
            if record.phase == 's':
                return Mock(enthalpy=-220000.0)  # J/mol at 3687K
            elif record.phase == 'g':
                return Mock(enthalpy=-180000.0)  # J/mol at 3687K

        calculator.thermodynamic_calculator.calculate_properties.side_effect = mock_calc_properties

        transitions = calculator.extract_transition_data(records)

        # Should find sublimation transition
        assert len(transitions) == 1

        sublimation = transitions[0]
        assert sublimation.transition_type == TransitionType.SUBLIMATION
        assert sublimation.temperature == 3687.0
        assert sublimation.from_phase == 's'
        assert sublimation.to_phase == 'g'

    def test_extract_transition_data_no_transition_temps(self, calculator, feo_solid_record):
        """Test extraction when no transition temperatures are available."""
        # Record without transition temperatures
        feo_solid_record.MeltingPoint = None
        feo_solid_record.BoilingPoint = None

        transitions = calculator.extract_transition_data([feo_solid_record])

        # Should find no transitions
        assert len(transitions) == 0

    def test_group_records_by_phase(self, calculator, feo_solid_record, feo_liquid_record, feo_gas_record):
        """Test grouping of records by phase."""
        records = [feo_solid_record, feo_liquid_record, feo_gas_record]

        grouped = calculator._group_records_by_phase(records)

        assert 's' in grouped
        assert 'l' in grouped
        assert 'g' in grouped
        assert len(grouped['s']) == 1
        assert len(grouped['l']) == 1
        assert len(grouped['g']) == 1
        assert grouped['s'][0] == feo_solid_record
        assert grouped['l'][0] == feo_liquid_record
        assert grouped['g'][0] == feo_gas_record

    def test_calculate_transition_enthalpy_positive_result(self, calculator, feo_solid_record, feo_liquid_record):
        """Test calculation of transition enthalpy with positive result."""
        # Mock thermodynamic calculator to return positive enthalpy change
        def mock_calc_properties(record, temperature):
            if record.phase == 's':
                return Mock(enthalpy=-240500.0)  # J/mol
            elif record.phase == 'l':
                return Mock(enthalpy=-209000.0)  # J/mol (higher, so ΔH > 0)

        calculator.thermodynamic_calculator.calculate_properties.side_effect = mock_calc_properties

        delta_h, method = calculator.calculate_transition_enthalpy(
            feo_solid_record, feo_liquid_record, 1650.0
        )

        # Should return positive enthalpy change
        assert delta_h > 0
        assert method == 'calculated'

    def test_calculate_transition_enthalpy_negative_result_fallback_to_heuristic(
        self, calculator, feo_solid_record, feo_liquid_record
    ):
        """Test fallback to heuristic when calculated enthalpy is negative."""
        # Mock thermodynamic calculator to return negative enthalpy change (physically incorrect)
        def mock_calc_properties(record, temperature):
            if record.phase == 's':
                return Mock(enthalpy=-200000.0)  # J/mol (higher)
            elif record.phase == 'l':
                return Mock(enthalpy=-240500.0)  # J/mol (lower, so ΔH < 0)

        calculator.thermodynamic_calculator.calculate_properties.side_effect = mock_calc_properties

        delta_h, method = calculator.calculate_transition_enthalpy(
            feo_solid_record, feo_liquid_record, 1650.0
        )

        # Should fallback to heuristic estimation
        assert delta_h > 0  # Heuristic should be positive
        assert method == 'heuristic'

    def test_apply_heuristic_estimation_boiling(self, calculator):
        """Test heuristic estimation for boiling."""
        delta_h = calculator.apply_heuristic_estimation('boiling', 373.0)

        # Should use Trouton's rule: ΔS ≈ 87 J/(mol·K)
        expected_h = 373.0 * 87.0 / 1000  # kJ/mol
        assert abs(delta_h - expected_h) < 0.1

    def test_apply_heuristic_estimation_melting_metal(self, calculator):
        """Test heuristic estimation for metal melting."""
        delta_h = calculator.apply_heuristic_estimation('melting', 1000.0, 'metal')

        # Should use ΔS ≈ 10 J/(mol·K) for metals
        expected_h = 1000.0 * 10.0 / 1000  # kJ/mol
        assert abs(delta_h - expected_h) < 0.1

    def test_apply_heuristic_estimation_melting_salt(self, calculator):
        """Test heuristic estimation for salt melting."""
        delta_h = calculator.apply_heuristic_estimation('melting', 1000.0, 'salt')

        # Should use ΔS ≈ 25 J/(mol·K) for salts
        expected_h = 1000.0 * 25.0 / 1000  # kJ/mol
        assert abs(delta_h - expected_h) < 0.1

    def test_apply_heuristic_estimation_sublimation(self, calculator):
        """Test heuristic estimation for sublimation."""
        delta_h = calculator.apply_heuristic_estimation('sublimation', 1500.0, 'oxide')

        # Sublimation ≈ melting + boiling
        melting_h = calculator.apply_heuristic_estimation('melting', 1500.0, 'oxide')
        boiling_h = calculator.apply_heuristic_estimation('boiling', 1500.0, 'oxide')
        expected_h = melting_h + boiling_h

        assert abs(delta_h - expected_h) < 0.1

    def test_classify_compound_metal(self, calculator):
        """Test classification of metal compounds."""
        assert calculator._classify_compound('Fe') == 'metal'
        assert calculator._classify_compound('Cu') == 'metal'
        assert calculator._classify_compound('Al') == 'metal'

    def test_classify_compound_oxide(self, calculator):
        """Test classification of oxide compounds."""
        assert calculator._classify_compound('FeO') == 'oxide'
        assert calculator._classify_compound('Al2O3') == 'oxide'
        assert calculator._classify_compound('SiO2') == 'oxide'

    def test_classify_compound_salt(self, calculator):
        """Test classification of salt compounds."""
        assert calculator._classify_compound('NaCl') == 'salt'
        assert calculator._classify_compound('KBr') == 'salt'
        assert calculator._classify_compound('CaF2') == 'salt'

    def test_classify_compound_molecular(self, calculator):
        """Test classification of molecular compounds."""
        assert calculator._classify_compound('H2O') == 'molecular'
        assert calculator._classify_compound('CO2') == 'molecular'
        assert calculator._classify_compound('CH4') == 'molecular'

    def test_classify_compound_unknown(self, calculator):
        """Test classification of unknown compounds."""
        assert calculator._classify_compound('XYZ') == 'molecular'  # Default to molecular

    def test_validate_transition_consistency_valid(self, calculator):
        """Test validation of thermodynamically consistent transitions."""
        transitions = [
            PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=31.5,
                delta_S_transition=19.1,
                reliability=0.8,
                calculation_method='calculated'
            ),
            PhaseTransition(
                temperature=3687.0,
                from_phase='l',
                to_phase='g',
                transition_type=TransitionType.BOILING,
                delta_H_transition=85.0,
                delta_S_transition=87.0,  # Within Trouton's range
                reliability=0.7,
                calculation_method='calculated'
            )
        ]

        warnings = calculator.validate_transition_consistency(transitions)

        # Should have no warnings for valid transitions
        assert len(warnings) == 0

    def test_validate_transition_consistency_negative_enthalpy(self, calculator):
        """Test validation detects negative enthalpy."""
        transitions = [
            PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=-5.0,  # Negative!
                delta_S_transition=19.1,
                reliability=0.8,
                calculation_method='calculated'
            )
        ]

        warnings = calculator.validate_transition_consistency(transitions)

        # Should warn about negative enthalpy
        assert len(warnings) >= 1
        assert any("Отрицательная энтальпия" in warning for warning in warnings)

    def test_validate_transition_consistency_negative_entropy(self, calculator):
        """Test validation detects negative entropy."""
        transitions = [
            PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=31.5,
                delta_S_transition=-5.0,  # Negative!
                reliability=0.8,
                calculation_method='calculated'
            )
        ]

        warnings = calculator.validate_transition_consistency(transitions)

        # Should warn about negative entropy
        assert len(warnings) >= 1
        assert any("Отрицательная энтропия" in warning for warning in warnings)

    def test_validate_transition_consistency_trouton_violation(self, calculator):
        """Test validation detects Trouton's rule violations."""
        transitions = [
            PhaseTransition(
                temperature=373.0,
                from_phase='l',
                to_phase='g',
                transition_type=TransitionType.BOILING,
                delta_H_transition=40.0,
                delta_S_transition=107.2,  # Outside Trouton's range (75-95)
                reliability=0.6,
                calculation_method='calculated'
            )
        ]

        warnings = calculator.validate_transition_consistency(transitions)

        # Should warn about Trouton's rule violation
        assert len(warnings) >= 1
        assert any("правила Трутона" in warning for warning in warnings)

    def test_cache_transition_data(self, calculator):
        """Test caching of transition data."""
        transitions = [
            PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=31.5,
                delta_S_transition=19.1
            )
        ]

        calculator.cache_transition_data('FeO', transitions)

        cached = calculator.get_cached_transitions('FeO', 1)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].temperature == 1650.0

    def test_get_cached_transitions_miss(self, calculator):
        """Test cache miss for non-existent data."""
        cached = calculator.get_cached_transitions('UnknownCompound', 1)
        assert cached is None

    def test_clear_cache(self, calculator):
        """Test clearing of transition cache."""
        transitions = [
            PhaseTransition(
                temperature=1650.0,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=31.5,
                delta_S_transition=19.1
            )
        ]

        # Cache some data
        calculator.cache_transition_data('FeO', transitions)
        assert calculator.get_cached_transitions('FeO', 1) is not None

        # Clear cache
        calculator.clear_cache()
        assert calculator.get_cached_transitions('FeO', 1) is None

    def test_extract_melting_point(self, calculator, feo_solid_record):
        """Test extraction of melting point from records."""
        melting_point = calculator._extract_melting_point([feo_solid_record])
        assert melting_point == 1650.0

    def test_extract_boiling_point(self, calculator, feo_solid_record):
        """Test extraction of boiling point from records."""
        boiling_point = calculator._extract_boiling_point([feo_solid_record])
        assert boiling_point == 3687.0

    def test_select_record_for_temperature_exact_match(self, calculator, feo_solid_record):
        """Test selection of record for exact temperature match."""
        selected = calculator._select_record_for_temperature([feo_solid_record], 400.0)
        assert selected == feo_solid_record

    def test_select_record_for_temperature_closest_match(self, calculator, feo_solid_record):
        """Test selection of closest record when no exact match."""
        selected = calculator._select_record_for_temperature([feo_solid_record], 700.0)
        assert selected == feo_solid_record

    def test_extract_transition_data_empty_records(self, calculator):
        """Test extraction with empty record list."""
        transitions = calculator.extract_transition_data([])
        assert len(transitions) == 0

    def test_create_heuristic_melting_transition(self, calculator):
        """Test creation of heuristic melting transition."""
        transition = calculator._create_heuristic_melting_transition(1650.0, 'FeO')

        assert transition is not None
        assert transition.temperature == 1650.0
        assert transition.from_phase == 's'
        assert transition.to_phase == 'l'
        assert transition.transition_type == TransitionType.MELTING
        assert transition.calculation_method == 'heuristic'
        assert transition.reliability == 0.4
        assert transition.warning is not None

    def test_create_heuristic_boiling_transition(self, calculator):
        """Test creation of heuristic boiling transition."""
        transition = calculator._create_heuristic_boiling_transition(373.0, 'H2O')

        assert transition is not None
        assert transition.temperature == 373.0
        assert transition.from_phase == 'l'
        assert transition.to_phase == 'g'
        assert transition.transition_type == TransitionType.BOILING
        assert transition.calculation_method == 'heuristic'
        assert transition.reliability == 0.5
        assert transition.warning is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])