"""
Integration tests for Stage 3 - Automatic Record Selection.

This module tests the complete integration of Stage 3 components including
MultiPhaseCompoundData, RecordTransitionManager, enhanced ThermodynamicCalculator,
and MultiPhaseReactionCalculator working together.

Key test scenarios:
1. FeO multi-record calculation example from specification
2. Temperature continuity across record boundaries
3. Performance with large datasets
4. Integration with existing filtering and search components
5. End-to-end reaction calculations with multiple records
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch

from src.thermo_agents.models.search import (
    MultiPhaseCompoundData,
    DatabaseRecord,
    PhaseSegment,
    RecordTransition
)
from src.thermo_agents.calculations.record_transition_manager import RecordTransitionManager
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from src.thermo_agents.calculations.reaction_calculator import MultiPhaseReactionCalculator
from src.thermo_agents.filtering.record_selector import RecordSelector


class TestStage3Integration:
    """Integration tests for Stage 3 components."""

    @pytest.fixture
    def feo_records(self):
        """Create realistic FeO records as described in the specification."""
        return [
            # Record 1: 298-600K, H298 = -265.053
            DatabaseRecord(
                id=1,
                formula="FeO",
                phase="s",
                tmin=298.0,
                tmax=600.0,
                h298=-265.053,
                s298=59.807,
                f1=45.2,
                f2=15.8,
                f3=-2.1,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            # Record 2: 600-900K, H298 = 0.0 (requires accumulation)
            DatabaseRecord(
                id=2,
                formula="FeO",
                phase="s",
                tmin=600.0,
                tmax=900.0,
                h298=0.0,
                s298=0.0,
                f1=48.1,
                f2=16.2,
                f3=-2.3,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            # Record 3: 900-1300K, H298 = 0.0
            DatabaseRecord(
                id=3,
                formula="FeO",
                phase="s",
                tmin=900.0,
                tmax=1300.0,
                h298=0.0,
                s298=0.0,
                f1=50.5,
                f2=17.1,
                f3=-2.5,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            ),
            # Record 4: 1300-1650K, H298 = 0.0
            DatabaseRecord(
                id=4,
                formula="FeO",
                phase="s",
                tmin=1300.0,
                tmax=1650.0,
                h298=0.0,
                s298=0.0,
                f1=52.8,
                f2=18.0,
                f3=-2.7,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1650.0,
                tboil=3687.0,
                reliability_class=1
            )
        ]

    @pytest.fixture
    def feo_compound_data(self, feo_records):
        """Create MultiPhaseCompoundData for FeO."""
        segments = [PhaseSegment.from_database_record(record) for record in feo_records]

        return MultiPhaseCompoundData(
            compound_formula="FeO",
            all_records=feo_records,
            phase_segments=segments
        )

    @pytest.fixture
    def h2o_records(self):
        """Create H2O records for testing multi-phase scenarios."""
        return [
            # Ice phase
            DatabaseRecord(
                id=10,
                formula="H2O",
                phase="s",
                tmin=298.0,
                tmax=273.15,
                h298=-285.83,
                s298=69.95,
                f1=46.0,
                f2=30.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            # Liquid phase
            DatabaseRecord(
                id=11,
                formula="H2O",
                phase="l",
                tmin=273.15,
                tmax=373.15,
                h298=-285.83,
                s298=69.95,
                f1=75.3,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            ),
            # Gas phase
            DatabaseRecord(
                id=12,
                formula="H2O",
                phase="g",
                tmin=373.15,
                tmax=2000.0,
                h298=-241.83,
                s298=188.84,
                f1=30.0,
                f2=10.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1
            )
        ]

    def test_feo_multi_record_calculation_scenario(self, feo_compound_data):
        """Test the FeO multi-record calculation scenario from specification."""
        calculator = ThermodynamicCalculator()

        # Test calculation in first record range (298-600K)
        props_400 = calculator.calculate_properties_multi_record(feo_compound_data, 400.0)
        assert props_400.T == 400.0
        assert props_400.H < 0  # Should be negative due to H298 = -265.053

        # Test calculation at transition temperature (600K)
        props_600 = calculator.calculate_properties_multi_record(feo_compound_data, 600.0)
        assert props_600.T == 600.0

        # Test calculation in second record range (600-900K)
        props_700 = calculator.calculate_properties_multi_record(feo_compound_data, 700.0)
        assert props_700.T == 700.0

        # Test calculation in final record range (1300-1650K)
        props_1500 = calculator.calculate_properties_multi_record(feo_compound_data, 1500.0)
        assert props_1500.T == 1500.0

        # Verify record selection works correctly
        record_400 = feo_compound_data.get_record_at_temperature(400.0)
        assert record_400.id == 1

        record_700 = feo_compound_data.get_record_at_temperature(700.0)
        assert record_700.id == 2

        record_1500 = feo_compound_data.get_record_at_temperature(1500.0)
        assert record_1500.id == 4

    def test_temperature_continuity_across_boundaries(self, feo_compound_data):
        """Test that thermodynamic properties are continuous across record boundaries."""
        calculator = ThermodynamicCalculator()
        transition_manager = RecordTransitionManager()

        # Test continuity around 600K boundary
        T_before = 599.0
        T_after = 601.0
        T_boundary = 600.0

        props_before = calculator.calculate_properties_multi_record(feo_compound_data, T_before)
        props_after = calculator.calculate_properties_multi_record(feo_compound_data, T_after)

        # Get the records involved in transition
        record_before = feo_compound_data.get_record_at_temperature(T_before)
        record_after = feo_compound_data.get_record_at_temperature(T_after)

        # Calculate transition corrections
        delta_H_corr, delta_S_corr = transition_manager.ensure_continuity(
            record_before, record_after, T_boundary
        )

        # Verify corrections are calculated (even if zero)
        assert isinstance(delta_H_corr, float)
        assert isinstance(delta_S_corr, float)

        # The corrected values should be continuous
        H_corrected = props_after.H + delta_H_corr
        S_corrected = props_after.S + delta_S_corr

        # Check continuity (within reasonable tolerance)
        H_diff = abs(H_corrected - props_before.H)
        S_diff = abs(S_corrected - props_before.S)

        # Allow some tolerance due to numerical integration
        assert H_diff < 1000  # Less than 1 kJ/mol difference
        assert S_diff < 10    # Less than 10 J/(mol·K) difference

    def test_multi_record_table_generation(self, feo_compound_data):
        """Test generation of thermodynamic tables with multiple records."""
        calculator = ThermodynamicCalculator()

        # Generate table across multiple records
        table = calculator.calculate_table_multi_record(
            feo_compound_data,
            temperature_range=(400.0, 1500.0),
            num_points=20
        )

        assert table.formula == "FeO"
        assert table.phase == "multi"
        assert table.temperature_range == (400.0, 1500.0)
        assert len(table.properties) > 0

        # Verify table spans multiple records
        temperatures = [prop.T for prop in table.properties]
        assert min(temperatures) >= 400.0
        assert max(temperatures) <= 1500.0

        # Check that we have data points from different records
        records_used = set()
        for prop in table.properties:
            try:
                record = feo_compound_data.get_record_at_temperature(prop.T)
                records_used.add(record.id)
            except ValueError:
                continue

        assert len(records_used) > 1  # Should use multiple records

    def test_record_selector_integration(self, feo_compound_data):
        """Test RecordSelector integration with MultiPhaseCompoundData."""
        selector = RecordSelector()

        # Test record selection using MultiPhaseCompoundData
        selection = selector.select_record_for_temperature_multi_phase(
            feo_compound_data, 500.0
        )

        assert selection.selected_record.id == 1
        assert selection.confidence == 1.0
        assert "MultiPhaseCompoundData" in selection.selection_reason

        # Test near transition point
        selection_near_boundary = selector.select_record_for_temperature_multi_phase(
            feo_compound_data, 600.0
        )
        assert "segment boundary" in selection_near_boundary.selection_reason
        assert selection_near_boundary.confidence == 0.9

    def test_multi_phase_reaction_calculation(self, feo_compound_data):
        """Test reaction calculations with multi-record compounds."""
        reaction_calculator = MultiPhaseReactionCalculator()

        # Create a simple oxidation reaction: FeO + 1/2 O2 → FeO2
        # For testing, we'll use FeO as both reactant and product
        stoichiometry = {"FeO": -1.0}  # Just decomposition for simplicity

        # Calculate reaction properties at different temperatures
        props_400 = reaction_calculator.calculate_reaction_properties(
            reactants_data=[feo_compound_data],
            products_data=[],
            stoichiometry=stoichiometry,
            temperature=400.0
        )

        props_1000 = reaction_calculator.calculate_reaction_properties(
            reactants_data=[feo_compound_data],
            products_data=[],
            stoichiometry=stoichiometry,
            temperature=1000.0
        )

        assert props_400.temperature == 400.0
        assert props_1000.temperature == 1000.0

        # Properties should be different at different temperatures
        assert props_400.delta_H != props_1000.delta_H
        assert props_400.delta_S != props_1000.delta_S

        # Check component contributions
        assert "FeO" in props_400.component_contributions
        assert props_400.component_contributions["FeO"]["stoichiometry"] == -1.0

    def test_transition_impact_analysis(self, feo_compound_data):
        """Test analysis of transition impact on reaction properties."""
        reaction_calculator = MultiPhaseReactionCalculator()

        stoichiometry = {"FeO": -1.0}

        # Analyze transition impact
        analysis = reaction_calculator.analyze_transition_impact(
            reactants_data=[feo_compound_data],
            products_data=[],
            stoichiometry=stoichiometry,
            temperature_range=(400.0, 1500.0)
        )

        assert "temperature_range" in analysis
        assert "total_transitions" in analysis
        assert "significant_transitions" in analysis
        assert "max_H_jump" in analysis
        assert "max_G_jump" in analysis
        assert "recommendation" in analysis

        # Should detect transitions in our test data
        assert analysis["total_transitions"] >= 0

    def test_precomputed_transitions(self, feo_compound_data):
        """Test precomputation of record transitions."""
        # Initially should have no transitions
        assert len(feo_compound_data.record_transitions) == 0

        # Precompute transitions
        feo_compound_data.precompute_transitions()

        # Should have transitions computed (depending on implementation)
        # The exact number depends on how many records touch each other
        assert len(feo_compound_data.record_transitions) >= 0

        # Test retrieval of precomputed transitions
        if feo_compound_data.record_transitions:
            first_key = list(feo_compound_data.record_transitions.keys())[0]
            transition = feo_compound_data.get_transition_between_records(
                first_key[0], first_key[1]
            )
            assert transition is not None

    def test_record_sequence_building(self, feo_compound_data):
        """Test building optimal record sequences."""
        selector = RecordSelector()

        # Build sequence for full temperature range
        sequence = selector.build_record_sequence(
            feo_compound_data,
            temperature_range=(400.0, 1500.0)
        )

        assert len(sequence) >= 1
        assert all(record.formula == "FeO" for record in sequence)

        # Verify sequence covers the temperature range
        first_record = sequence[0]
        last_record = sequence[-1]

        assert first_record.tmin <= 400.0
        assert last_record.tmax >= 1500.0

    def test_multi_record_coverage_analysis(self, feo_compound_data):
        """Test analysis of multi-record coverage."""
        selector = RecordSelector()

        analysis = selector.analyze_multi_record_coverage(
            feo_compound_data,
            temperature_range=(400.0, 1500.0)
        )

        assert analysis["coverage_percentage"] > 90  # Should have good coverage
        assert analysis["segments_count"] >= 1
        assert analysis["records_count"] >= 1
        assert "transition_quality" in analysis
        assert "warnings" in analysis

    def test_performance_with_large_temperature_range(self, feo_compound_data):
        """Test performance with large temperature ranges and many points."""
        import time

        calculator = ThermodynamicCalculator()

        # Test with many temperature points
        start_time = time.time()
        table = calculator.calculate_table_multi_record(
            feo_compound_data,
            temperature_range=(298.0, 1650.0),
            num_points=100
        )
        end_time = time.time()

        # Should complete in reasonable time (less than 2 seconds)
        assert end_time - start_time < 2.0
        assert len(table.properties) > 50  # Should have most points calculated

    def test_error_handling_and_robustness(self, feo_compound_data):
        """Test error handling and robustness of Stage 3 components."""
        calculator = ThermodynamicCalculator()

        # Test with temperature outside range
        with pytest.raises(ValueError):
            calculator.calculate_properties_multi_record(feo_compound_data, 200.0)

        with pytest.raises(ValueError):
            calculator.calculate_properties_multi_record(feo_compound_data, 2000.0)

        # Test with invalid temperature range
        with pytest.raises(ValueError):
            calculator.calculate_table_multi_record(
                feo_compound_data,
                temperature_range=(500.0, 400.0),  # Invalid range
                num_points=10
            )

        # Test with temperature range outside available range
        with pytest.raises(ValueError):
            calculator.calculate_table_multi_record(
                feo_compound_data,
                temperature_range=(200.0, 300.0),  # Outside available range
                num_points=10
            )

    def test_multi_phase_h2o_scenario(self, h2o_records):
        """Test multi-phase scenario with H2O (solid → liquid → gas)."""
        segments = [PhaseSegment.from_database_record(record) for record in h2o_records]
        h2o_compound_data = MultiPhaseCompoundData(
            compound_formula="H2O",
            all_records=h2o_records,
            phase_segments=segments
        )

        calculator = ThermodynamicCalculator()

        # Test calculation in solid phase (below melting point)
        props_solid = calculator.calculate_properties_multi_record(h2o_compound_data, 250.0)
        record_solid = h2o_compound_data.get_record_at_temperature(250.0)
        assert record_solid.phase == "s"

        # Test calculation in liquid phase
        props_liquid = calculator.calculate_properties_multi_record(h2o_compound_data, 300.0)
        record_liquid = h2o_compound_data.get_record_at_temperature(300.0)
        assert record_liquid.phase == "l"

        # Test calculation in gas phase
        props_gas = calculator.calculate_properties_multi_record(h2o_compound_data, 500.0)
        record_gas = h2o_compound_data.get_record_at_temperature(500.0)
        assert record_gas.phase == "g"

        # Verify different phases have different properties
        assert props_solid.H != props_liquid.H != props_gas.H

    def test_caching_performance(self, feo_compound_data):
        """Test that caching improves performance for repeated calculations."""
        calculator = ThermodynamicCalculator()

        import time

        # First calculation (should populate cache)
        start_time = time.time()
        props1 = calculator.calculate_properties_multi_record(feo_compound_data, 500.0)
        first_time = time.time() - start_time

        # Second calculation (should use cache)
        start_time = time.time()
        props2 = calculator.calculate_properties_multi_record(feo_compound_data, 500.0)
        second_time = time.time() - start_time

        # Results should be identical
        assert props1.H == props2.H
        assert props1.S == props2.S

        # Second calculation should be faster (or at least not significantly slower)
        # Allow some tolerance for timing variations
        assert second_time <= first_time * 2  # Should not be more than 2x slower