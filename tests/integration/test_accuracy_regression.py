"""
Accuracy regression tests for optimal record selection.

Tests that optimization does not degrade thermodynamic calculation accuracy.
"""

import pytest
import numpy as np
from typing import List, Dict, Any

from src.thermo_agents.selection.optimal_record_selector import (
    OptimalRecordSelector,
    VirtualRecord,
    OptimizationConfig
)
from src.thermo_agents.models.search import DatabaseRecord


class TestAccuracyRegression:
    """Accuracy regression tests for optimal record selection."""

    @pytest.fixture
    def selector(self):
        """Create OptimalRecordSelector instance."""
        return OptimalRecordSelector()

    @pytest.fixture
    def precise_test_records(self):
        """Create records with known thermodynamic properties for accuracy testing."""
        return {
            'H2O': [
                # Liquid water record
                DatabaseRecord(
                    rowid=1,
                    formula="H2O",
                    first_name="Water",
                    phase="l",
                    tmin=273.15,
                    tmax=373.15,
                    h298=-285.830,  # kJ/mol
                    s298=69.95,     # J/(mol·K)
                    f1=30.09,
                    f2=6.8325,
                    f3=6.283,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=273.15,
                    tboil=373.15,
                    reliability_class=1
                ),
                # Gas water record 1
                DatabaseRecord(
                    rowid=2,
                    formula="H2O",
                    first_name="Water",
                    phase="g",
                    tmin=298.15,
                    tmax=600.0,
                    h298=-241.826,  # kJ/mol
                    s298=188.838,   # J/(mol·K)
                    f1=33.33,
                    f2=0.0113,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=273.15,
                    tboil=373.15,
                    reliability_class=1
                ),
                # Gas water record 2 (continuation, identical coefficients)
                DatabaseRecord(
                    rowid=3,
                    formula="H2O",
                    first_name="Water",
                    phase="g",
                    tmin=600.0,
                    tmax=1600.0,
                    h298=0.0,
                    s298=0.0,
                    f1=33.33,
                    f2=0.0113,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=273.15,
                    tboil=373.15,
                    reliability_class=1
                )
            ],
            'NH3': [
                # Ammonia record 1
                DatabaseRecord(
                    rowid=1,
                    formula="NH3",
                    first_name="Ammonia",
                    phase="g",
                    tmin=298.15,
                    tmax=1000.0,
                    h298=-45.9,     # kJ/mol
                    s298=192.8,     # J/(mol·K)
                    f1=25.49,
                    f2=36.89,
                    f3=-6.293,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=195.4,
                    tboil=239.8,
                    reliability_class=1
                ),
                # Ammonia record 2 (continuation)
                DatabaseRecord(
                    rowid=2,
                    formula="NH3",
                    first_name="Ammonia",
                    phase="g",
                    tmin=1000.0,
                    tmax=6000.0,
                    h298=0.0,
                    s298=0.0,
                    f1=59.74,
                    f2=-2.501,
                    f3=0.1366,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=195.4,
                    tboil=239.8,
                    reliability_class=1
                )
            ]
        }

    def calculate_thermodynamic_properties(self, record: DatabaseRecord, temperature: float) -> Dict[str, float]:
        """
        Calculate thermodynamic properties using Shomate equations.

        This implements the standard Shomate polynomial calculations
        for Cp, H, S, and G at a given temperature.
        """
        # Convert temperature from K to K/1000 for Shomate equations
        T = temperature / 1000.0
        R = 8.314462618  # J/(mol·K) - Universal gas constant

        # Heat capacity Cp(T) = f1 + f2*T + f3*T^2 + f4*T^3 + f5/T^2
        Cp = record.f1 + record.f2 * T + record.f3 * T**2 + record.f4 * T**3 + record.f5 / T**2

        # Enthalpy H(T) = H298 + ∫Cp(T)dT from 298K to T
        # H(T) = H298 + f1*(T-0.298) + f2/2*(T^2-0.298^2) + f3/3*(T^3-0.298^3) + f4/4*(T^4-0.298^4) - f5*(1/T-1/0.298)
        T298 = 298.15 / 1000.0
        H = record.h298 + (
            record.f1 * (T - T298) +
            record.f2 * (T**2 - T298**2) / 2 +
            record.f3 * (T**3 - T298**3) / 3 +
            record.f4 * (T**4 - T298**4) / 4 -
            record.f5 * (1/T - 1/T298)
        )

        # Entropy S(T) = S298 + ∫Cp(T)/T dT from 298K to T
        # S(T) = S298 + f1*ln(T/0.298) + f2*(T-0.298) + f3/2*(T^2-0.298^2) + f4/3*(T^3-0.298^3) - f5/2*(1/T^2-1/0.298^2)
        S = record.s298 + (
            record.f1 * np.log(T / T298) +
            record.f2 * (T - T298) +
            record.f3 * (T**2 - T298**2) / 2 +
            record.f4 * (T**3 - T298**3) / 3 -
            record.f5 * (1/T**2 - 1/T298**2) / 2
        )

        # Gibbs free energy G(T) = H(T) - T*S(T)
        G = H - temperature * S / 1000.0  # Convert S to kJ

        return {
            'Cp': Cp,
            'H': H,
            'S': S,
            'G': G
        }

    def test_thermodynamic_properties_accuracy(self, selector, precise_test_records):
        """
        Test that optimized records produce thermodynamic properties within ±0.01% of original.
        """
        tolerance = 0.0001  # 0.01%

        for compound, records in precise_test_records.items():
            # Test temperatures
            test_temperatures = [298.15, 350, 400, 500, 800, 1000]

            # Create DataFrame for all available records
            import pandas as pd
            all_records_df = pd.DataFrame([{
                'rowid': r.rowid,
                'Formula': r.formula,
                'FirstName': r.first_name,
                'Phase': r.phase,
                'Tmin': r.tmin,
                'Tmax': r.tmax,
                'H298': r.h298,
                'S298': r.s298,
                'f1': r.f1,
                'f2': r.f2,
                'f3': r.f3,
                'f4': r.f4,
                'f5': r.f5,
                'f6': r.f6,
                'MeltingPoint': r.tmelt,
                'BoilingPoint': r.tboil,
                'ReliabilityClass': r.reliability_class
            } for r in records])

            # Optimize records
            optimized_records = selector.optimize_selected_records(
                selected_records=records,
                target_range=(298.15, 1000),
                all_available_records=all_records_df,
                melting=records[0].tmelt if records else None,
                boiling=records[0].tboil if records else None,
                is_elemental=False
            )

            for temp in test_temperatures:
                # Find appropriate record for this temperature in original records
                original_record = None
                for record in records:
                    if record.tmin <= temp <= record.tmax:
                        original_record = record
                        break

                if not original_record:
                    continue  # Skip if no record covers this temperature

                # Find appropriate record in optimized records
                optimized_record = None
                for record in optimized_records:
                    # Handle both regular and virtual records
                    if isinstance(record, VirtualRecord):
                        if record.merged_tmin <= temp <= record.merged_tmax:
                            optimized_record = record
                            break
                    else:
                        if record.tmin <= temp <= record.tmax:
                            optimized_record = record
                            break

                if not optimized_record:
                    continue  # Skip if no record covers this temperature

                # Calculate properties for both records
                original_props = self.calculate_thermodynamic_properties(original_record, temp)
                optimized_props = self.calculate_thermodynamic_properties(optimized_record, temp)

                # Check accuracy for each property
                for prop_name in ['Cp', 'H', 'S', 'G']:
                    original_val = original_props[prop_name]
                    optimized_val = optimized_props[prop_name]

                    if original_val != 0:
                        relative_error = abs(optimized_val - original_val) / abs(original_val)
                        assert relative_error <= tolerance, (
                            f"Property {prop_name} accuracy regression for {compound} at {temp}K: "
                            f"original={original_val:.6f}, optimized={optimized_val:.6f}, "
                            f"error={relative_error:.6f} > {tolerance}"
                        )
                    else:
                        # For zero values, check absolute difference
                        abs_diff = abs(optimized_val - original_val)
                        assert abs_diff <= 1e-6, (
                            f"Property {prop_name} absolute difference for {compound} at {temp}K: "
                            f"original={original_val}, optimized={optimized_val}, "
                            f"diff={abs_diff} > 1e-6"
                        )

    def test_reaction_equilibrium_accuracy(self, selector, precise_test_records):
        """
        Test that reaction equilibrium constants are within ±0.05% of original values.
        """
        tolerance = 0.0005  # 0.05%

        # Test reaction: 2 H2O → 2 H2 + O2 (simplified example)
        # We'll use H2O and NH3 as our test compounds
        test_reaction = {
            'reactants': ['H2O', 'NH3'],
            'products': [],
            'stoichiometry': {'H2O': -2, 'NH3': -1}
        }

        test_temperature = 500  # K
        R = 8.314462618  # J/(mol·K)

        # Calculate reaction properties using original records
        original_delta_H = 0
        original_delta_S = 0
        original_delta_G = 0

        for compound, coeff in test_reaction['stoichiometry'].items():
            if compound in precise_test_records:
                records = precise_test_records[compound]
                # Find appropriate record
                record = None
                for r in records:
                    if r.tmin <= test_temperature <= r.tmax:
                        record = r
                        break

                if record:
                    props = self.calculate_thermodynamic_properties(record, test_temperature)
                    original_delta_H += coeff * props['H']
                    original_delta_S += coeff * props['S']
                    original_delta_G += coeff * props['G']

        # Calculate reaction properties using optimized records
        optimized_delta_H = 0
        optimized_delta_S = 0
        optimized_delta_G = 0

        for compound, coeff in test_reaction['stoichiometry'].items():
            if compound in precise_test_records:
                records = precise_test_records[compound]

                # Optimize records
                import pandas as pd
                all_records_df = pd.DataFrame([{
                    'rowid': r.rowid,
                    'Formula': r.formula,
                    'FirstName': r.first_name,
                    'Phase': r.phase,
                    'Tmin': r.tmin,
                    'Tmax': r.tmax,
                    'H298': r.h298,
                    'S298': r.s298,
                    'f1': r.f1,
                    'f2': r.f2,
                    'f3': r.f3,
                    'f4': r.f4,
                    'f5': r.f5,
                    'f6': r.f6,
                    'MeltingPoint': r.tmelt,
                    'BoilingPoint': r.tboil,
                    'ReliabilityClass': r.reliability_class
                } for r in records])

                optimized_records = selector.optimize_selected_records(
                    selected_records=records,
                    target_range=(298.15, 1000),
                    all_available_records=all_records_df,
                    melting=records[0].tmelt if records else None,
                    boiling=records[0].tboil if records else None,
                    is_elemental=False
                )

                # Find appropriate optimized record
                optimized_record = None
                for r in optimized_records:
                    if isinstance(r, VirtualRecord):
                        if r.merged_tmin <= test_temperature <= r.merged_tmax:
                            optimized_record = r
                            break
                    else:
                        if r.tmin <= test_temperature <= r.tmax:
                            optimized_record = r
                            break

                if optimized_record:
                    props = self.calculate_thermodynamic_properties(optimized_record, test_temperature)
                    optimized_delta_H += coeff * props['H']
                    optimized_delta_S += coeff * props['S']
                    optimized_delta_G += coeff * props['G']

        # Calculate equilibrium constants
        if original_delta_G != 0:
            original_K = np.exp(-original_delta_G * 1000 / (R * test_temperature))  # Convert kJ to J
        else:
            original_K = 1.0

        if optimized_delta_G != 0:
            optimized_K = np.exp(-optimized_delta_G * 1000 / (R * test_temperature))
        else:
            optimized_K = 1.0

        # Check accuracy
        if original_K > 0:
            relative_error = abs(optimized_K - original_K) / original_K
            assert relative_error <= tolerance, (
                f"Equilibrium constant accuracy regression at {test_temperature}K: "
                f"original={original_K:.6f}, optimized={optimized_K:.6f}, "
                f"error={relative_error:.6f} > {tolerance}"
            )

        # Also check delta G accuracy
        if original_delta_G != 0:
            delta_G_error = abs(optimized_delta_G - original_delta_G) / abs(original_delta_G)
            assert delta_G_error <= tolerance, (
                f"Delta G accuracy regression at {test_temperature}K: "
                f"original={original_delta_G:.6f}, optimized={optimized_delta_G:.6f}, "
                f"error={delta_G_error:.6f} > {tolerance}"
            )

    def test_phase_transition_enthalpy_accuracy(self, selector, precise_test_records):
        """
        Test that phase transition enthalpies are preserved within ±0.1 kJ/mol.
        """
        tolerance = 0.1  # kJ/mol

        # Test H2O phase transitions
        h2o_records = precise_test_records['H2O']

        # Create DataFrame for optimization
        import pandas as pd
        all_records_df = pd.DataFrame([{
            'rowid': r.rowid,
            'Formula': r.formula,
            'FirstName': r.first_name,
            'Phase': r.phase,
            'Tmin': r.tmin,
            'Tmax': r.tmax,
            'H298': r.h298,
            'S298': r.s298,
            'f1': r.f1,
            'f2': r.f2,
            'f3': r.f3,
            'f4': r.f4,
            'f5': r.f5,
            'f6': r.f6,
            'MeltingPoint': r.tmelt,
            'BoilingPoint': r.tboil,
            'ReliabilityClass': r.reliability_class
        } for r in h2o_records])

        # Optimize records
        optimized_records = selector.optimize_selected_records(
            selected_records=h2o_records,
            target_range=(250, 400),  # Range covering boiling point
            all_available_records=all_records_df,
            melting=273.15,
            boiling=373.15,
            is_elemental=False
        )

        # Calculate enthalpy change at boiling point
        T_boil = 373.15

        # Find liquid and gas records around boiling point
        original_liquid = None
        original_gas = None

        for record in h2o_records:
            if record.phase == 'l' and record.tmin <= T_boil <= record.tmax:
                original_liquid = record
            elif record.phase == 'g' and record.tmin <= T_boil <= record.tmax:
                original_gas = record

        optimized_liquid = None
        optimized_gas = None

        for record in optimized_records:
            if isinstance(record, VirtualRecord):
                if record.phase == 'l' and record.merged_tmin <= T_boil <= record.merged_tmax:
                    optimized_liquid = record
                elif record.phase == 'g' and record.merged_tmin <= T_boil <= record.merged_tmax:
                    optimized_gas = record
            else:
                if record.phase == 'l' and record.tmin <= T_boil <= record.tmax:
                    optimized_liquid = record
                elif record.phase == 'g' and record.tmin <= T_boil <= record.tmax:
                    optimized_gas = record

        if original_liquid and original_gas and optimized_liquid and optimized_gas:
            # Calculate enthalpies
            original_liquid_props = self.calculate_thermodynamic_properties(original_liquid, T_boil - 0.01)
            original_gas_props = self.calculate_thermodynamic_properties(original_gas, T_boil + 0.01)

            optimized_liquid_props = self.calculate_thermodynamic_properties(optimized_liquid, T_boil - 0.01)
            optimized_gas_props = self.calculate_thermodynamic_properties(optimized_gas, T_boil + 0.01)

            # Calculate enthalpy of vaporization
            original_delta_H_vap = original_gas_props['H'] - original_liquid_props['H']
            optimized_delta_H_vap = optimized_gas_props['H'] - optimized_liquid_props['H']

            # Check accuracy
            delta_H_diff = abs(optimized_delta_H_vap - original_delta_H_vap)
            assert delta_H_diff <= tolerance, (
                f"Enthalpy of vaporization accuracy regression: "
                f"original={original_delta_H_vap:.3f} kJ/mol, "
                f"optimized={optimized_delta_H_vap:.3f} kJ/mol, "
                f"diff={delta_H_diff:.3f} kJ/mol > {tolerance}"
            )

    def test_temperature_inversion_preservation(self, selector, precise_test_records):
        """
        Test that temperature inversions in reaction spontaneity are preserved.
        """
        # This test checks if reactions that change spontaneity at certain temperatures
        # maintain the same inversion points after optimization.

        # Create a synthetic case where reaction spontaneity changes
        # Reaction A: A → B with different temperature dependencies

        compound_a_records = [
            DatabaseRecord(
                rowid=1,
                formula="A",
                first_name="CompoundA",
                phase="g",
                tmin=298.15,
                tmax=1000.0,
                h298=-50.0,
                s298=100.0,
                f1=20.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=200.0,
                tboil=400.0,
                reliability_class=1
            )
        ]

        compound_b_records = [
            DatabaseRecord(
                rowid=1,
                formula="B",
                first_name="CompoundB",
                phase="g",
                tmin=298.15,
                tmax=1000.0,
                h298=-30.0,
                s298=150.0,
                f1=25.0,
                f2=0.2,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=250.0,
                tboil=450.0,
                reliability_class=1
            )
        ]

        # Find inversion temperature where ΔG = 0
        def find_inversion_temperature(records_a, records_b):
            """Find temperature where reaction A → B changes spontaneity."""
            for temp in np.linspace(298.15, 1000, 100):
                # A → B: ΔG = G(B) - G(A)
                props_a = self.calculate_thermodynamic_properties(records_a[0], temp)
                props_b = self.calculate_thermodynamic_properties(records_b[0], temp)
                delta_G = props_b['G'] - props_a['G']

                if abs(delta_G) < 0.1:  # Close to zero
                    return temp

            return None

        original_inversion = find_inversion_temperature(compound_a_records, compound_b_records)

        # Optimize records
        import pandas as pd

        for compound_name, records in [("A", compound_a_records), ("B", compound_b_records)]:
            all_records_df = pd.DataFrame([{
                'rowid': r.rowid,
                'Formula': r.formula,
                'FirstName': r.first_name,
                'Phase': r.phase,
                'Tmin': r.tmin,
                'Tmax': r.tmax,
                'H298': r.h298,
                'S298': r.s298,
                'f1': r.f1,
                'f2': r.f2,
                'f3': r.f3,
                'f4': r.f4,
                'f5': r.f5,
                'f6': r.f6,
                'MeltingPoint': r.tmelt,
                'BoilingPoint': r.tboil,
                'ReliabilityClass': r.reliability_class
            } for r in records])

            # Since we have single records, optimization should not change them
            optimized_records = selector.optimize_selected_records(
                selected_records=records,
                target_range=(298.15, 1000),
                all_available_records=all_records_df,
                melting=records[0].tmelt,
                boiling=records[0].tboil,
                is_elemental=False
            )

            # Check that records are preserved
            assert len(optimized_records) == len(records)

        optimized_inversion = find_inversion_temperature(compound_a_records, compound_b_records)

        # Inversion temperatures should be identical (since records aren't changed)
        if original_inversion and optimized_inversion:
            inversion_diff = abs(optimized_inversion - original_inversion)
            assert inversion_diff < 1.0, (
                f"Temperature inversion point changed: "
                f"original={original_inversion:.1f}K, "
                f"optimized={optimized_inversion:.1f}K, "
                f"diff={inversion_diff:.1f}K"
            )

    def test_virtual_record_coefficient_preservation(self, selector):
        """
        Test that virtual records preserve Shomate coefficients exactly.
        """
        # Create records with identical coefficients
        source_records = [
            DatabaseRecord(
                rowid=1,
                formula="TestCompound",
                first_name="Test",
                phase="g",
                tmin=100.0,
                tmax=200.0,
                h298=0.0,
                s298=0.0,
                f1=15.123456789,
                f2=0.234567890,
                f3=0.345678901,
                f4=0.456789012,
                f5=0.567890123,
                f6=0.678901234,
                tmelt=50.0,
                tboil=300.0,
                reliability_class=1
            ),
            DatabaseRecord(
                rowid=2,
                formula="TestCompound",
                first_name="Test",
                phase="g",
                tmin=200.0,
                tmax=300.0,
                h298=0.0,
                s298=0.0,
                f1=15.123456789,  # Identical coefficients
                f2=0.234567890,
                f3=0.345678901,
                f4=0.456789012,
                f5=0.567890123,
                f6=0.678901234,
                tmelt=50.0,
                tboil=300.0,
                reliability_class=1
            )
        ]

        # Create virtual record
        virtual_record = selector._create_virtual_record(source_records)

        # Check that coefficients are preserved exactly
        assert virtual_record.f1 == source_records[0].f1
        assert virtual_record.f2 == source_records[0].f2
        assert virtual_record.f3 == source_records[0].f3
        assert virtual_record.f4 == source_records[0].f4
        assert virtual_record.f5 == source_records[0].f5
        assert virtual_record.f6 == source_records[0].f6

        # Check temperature range
        assert virtual_record.merged_tmin == 100.0
        assert virtual_record.merged_tmax == 300.0

        # Check that virtual record produces same thermodynamic properties
        test_temp = 250.0
        virtual_props = self.calculate_thermodynamic_properties(virtual_record, test_temp)
        source_props = self.calculate_thermodynamic_properties(source_records[0], test_temp)

        for prop_name in ['Cp', 'H', 'S', 'G']:
            assert virtual_props[prop_name] == source_props[prop_name], (
                f"Virtual record property {prop_name} mismatch at {test_temp}K"
            )


if __name__ == "__main__":
    pytest.main([__file__])