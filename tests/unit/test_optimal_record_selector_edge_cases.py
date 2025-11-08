"""
Edge case tests for OptimalRecordSelector.

Tests boundary conditions, error handling, and unusual scenarios.
"""

import numpy as np
import pandas as pd
import pytest

from thermo_agents.models.search import DatabaseRecord
from thermo_agents.selection.optimal_record_selector import (
    OptimalRecordSelector,
    VirtualRecord,
)
from thermo_agents.selection.selection_config import OptimizationConfig


class TestOptimalRecordSelectorEdgeCases:
    """Test edge cases for OptimalRecordSelector."""

    @pytest.fixture
    def selector(self):
        """Create OptimalRecordSelector instance."""
        return OptimalRecordSelector()

    def test_empty_records_list(self, selector):
        """Test handling of empty records list."""
        result = selector.optimize_selected_records(
            selected_records=[],
            target_range=(298, 1000),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )
        assert result == []

    def test_single_record_no_optimization(self, selector):
        """Test that single record cannot be optimized further."""
        record = DatabaseRecord(
            rowid=1,
            formula="Test",
            first_name="Test",
            phase="g",
            tmin=100,
            tmax=200,
            h298=0,
            s298=0,
            f1=10.0,
            f2=0.1,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=0,
            tboil=0,
            reliability_class=1,
        )

        result = selector.optimize_selected_records(
            selected_records=[record],
            target_range=(150, 180),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        assert len(result) == 1
        assert result[0] == record

    def test_zero_base_data_complex_compound(self, selector):
        """Test handling of complex compounds with H298=0, S298=0."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Complex",
                first_name="Complex",
                phase="s",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,  # Zero base data for complex compound
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            )
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 180),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,  # Complex compound
        )

        # Should handle gracefully but log warning
        assert len(result) == 1
        assert result[0].h298 == 0
        assert result[0].s298 == 0

    def test_zero_base_data_elemental_compound(self, selector):
        """Test handling of elemental compounds with H298=0, S298=0 (acceptable)."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Fe",
                first_name="Iron",
                phase="s",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,  # Zero base data for elemental compound
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            )
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 180),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=True,  # Elemental compound
        )

        # Should accept zero base data for elemental compounds
        assert len(result) == 1

    def test_no_phase_transitions(self, selector):
        """Test optimization when no phase transitions are specified."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 250),
            all_available_records=pd.DataFrame(),
            melting=None,  # No transitions
            boiling=None,  # No transitions
            is_elemental=False,
        )

        # Should work without phase transitions
        assert len(result) >= 1

    def test_different_reliability_classes(self, selector):
        """Test handling of records with different reliability classes."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=3,  # Worst class
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=150,
                tmax=250,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,  # Best class
            ),
        ]

        data = []
        for record in records:
            data.append(
                {
                    "rowid": record.rowid,
                    "Formula": record.formula,
                    "FirstName": record.first_name,
                    "Phase": record.phase,
                    "Tmin": record.tmin,
                    "Tmax": record.tmax,
                    "H298": record.h298,
                    "S298": record.s298,
                    "f1": record.f1,
                    "f2": record.f2,
                    "f3": record.f3,
                    "f4": record.f4,
                    "f5": record.f5,
                    "f6": record.f6,
                    "MeltingPoint": record.tmelt,
                    "BoilingPoint": record.tboil,
                    "ReliabilityClass": record.reliability_class,
                }
            )
        all_records_df = pd.DataFrame(data)

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(175, 190),
            all_available_records=all_records_df,
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should prefer record with better reliability class
        assert len(result) >= 1
        assert any(r.reliability_class == 1 for r in result)

    def test_identical_reliability_classes(self, selector):
        """Test handling when all records have identical reliability classes."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 250),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should select based on other criteria (temperature coverage)
        assert len(result) >= 1

    def test_different_coefficients_no_virtual_merge(self, selector):
        """Test that records with different coefficients cannot be virtually merged."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0,
                s298=0,
                f1=12.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,  # Different f1
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        can_merge = selector._can_merge_virtually(records)
        assert can_merge is False

    def test_phase_transition_on_boundary(self, selector):
        """Test handling when phase transition occurs exactly on record boundary."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="s",
                tmin=100,
                tmax=273.15,
                h298=0,
                s298=0,  # Ends exactly at melting point
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="l",
                tmin=273.15,
                tmax=373.15,
                h298=0,
                s298=0,  # Starts exactly at melting point
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(200, 300),
            all_available_records=pd.DataFrame(),
            melting=273.15,
            boiling=373.15,
            is_elemental=False,
        )

        # Should handle boundary case correctly
        assert len(result) == 2

    def test_large_temperature_gap(self, selector):
        """Test handling of large gaps between records."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=1000,
                tmax=1100,
                h298=0,
                s298=0,  # Large gap of 800K
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 1050),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should detect gap and handle appropriately
        assert len(result) >= 1

    def test_overlapping_records(self, selector):
        """Test handling of overlapping temperature ranges."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=300,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=400,
                h298=0,
                s298=0,  # Overlaps with record 1
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 350),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle overlapping records
        assert len(result) >= 1

    def test_identical_records(self, selector):
        """Test handling of completely identical records."""
        base_record = DatabaseRecord(
            rowid=1,
            formula="Test",
            first_name="Test",
            phase="g",
            tmin=100,
            tmax=200,
            h298=0,
            s298=0,
            f1=10.0,
            f2=0.1,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=0,
            tboil=0,
            reliability_class=1,
        )

        # Create identical record with different ID
        identical_record = DatabaseRecord(
            rowid=2,
            formula="Test",
            first_name="Test",
            phase="g",
            tmin=100,
            tmax=200,
            h298=0,
            s298=0,
            f1=10.0,
            f2=0.1,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=0,
            tboil=0,
            reliability_class=1,
        )

        records = [base_record, identical_record]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 180),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle duplicates (may keep both or select best)
        assert len(result) >= 1

    def test_extreme_temperature_ranges(self, selector):
        """Test handling of extreme temperature ranges."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=1,
                tmax=10,
                h298=0,
                s298=0,  # Very low temperature
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=5000,
                tmax=10000,
                h298=0,
                s298=0,  # Very high temperature
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(5, 8000),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle extreme ranges
        assert len(result) >= 1

    def test_invalid_target_range(self, selector):
        """Test handling of invalid target temperature ranges."""
        record = DatabaseRecord(
            rowid=1,
            formula="Test",
            first_name="Test",
            phase="g",
            tmin=100,
            tmax=200,
            h298=0,
            s298=0,
            f1=10.0,
            f2=0.1,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmelt=0,
            tboil=0,
            reliability_class=1,
        )

        # Test inverted range (Tmin > Tmax)
        result = selector.optimize_selected_records(
            selected_records=[record],
            target_range=(300, 200),  # Inverted range
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle gracefully (may return empty or original)
        assert isinstance(result, list)

    def test_missing_attributes_in_records(self, selector):
        """Test handling of records with missing attributes."""

        # Create a record-like object with missing attributes
        class IncompleteRecord:
            def __init__(self):
                self.rowid = 1
                self.formula = "Test"
                self.phase = "g"
                self.tmin = 100
                self.tmax = 200
                # Missing other attributes

        record = IncompleteRecord()

        result = selector.optimize_selected_records(
            selected_records=[record],
            target_range=(150, 180),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle missing attributes gracefully
        assert isinstance(result, list)

    def test_virtual_record_explain_merge(self, selector):
        """Test VirtualRecord explain_merge method."""
        source_records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        virtual_record = selector._create_virtual_record(source_records)
        explanation = virtual_record.explain_merge()

        assert "Virtual record merged from 2 records" in explanation
        assert "100-200K" in explanation
        assert "200-300K" in explanation
        assert "100-300K" in explanation

    def test_cache_overflow(self, selector):
        """Test behavior when virtual record cache overflows."""
        # Create many small virtual records to fill cache
        for i in range(150):  # More than max_virtual_records (100)
            source_records = [
                DatabaseRecord(
                    rowid=i,
                    formula=f"Test{i}",
                    first_name="Test",
                    phase="g",
                    tmin=100 + i,
                    tmax=200 + i,
                    h298=0,
                    s298=0,
                    f1=10.0,
                    f2=0.1,
                    f3=0.0,
                    f4=0.0,
                    f5=0.0,
                    f6=0.0,
                    tmelt=0,
                    tboil=0,
                    reliability_class=1,
                )
            ]

            virtual_record = selector._create_virtual_record(source_records)
            assert isinstance(virtual_record, VirtualRecord)

        # Cache should be limited but still functional
        assert (
            len(selector._virtual_record_cache) <= selector.config.max_virtual_records
        )

    def test_very_small_coefficients_differences(self, selector):
        """Test coefficient comparison with very small differences."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=200,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
            DatabaseRecord(
                rowid=2,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=200,
                tmax=300,
                h298=0,
                s298=0,
                f1=10.0,
                f2=0.1000001,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,  # Very small difference
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        # Should be able to merge (difference within tolerance)
        can_merge = selector._can_merge_virtually(records)
        assert can_merge is True

    def test_pandas_series_records(self, selector):
        """Test handling of pandas Series as records."""
        # Create a DataFrame and extract Series
        data = {
            "rowid": [1],
            "Formula": ["Test"],
            "FirstName": ["Test"],
            "Phase": ["g"],
            "Tmin": [100.0],
            "Tmax": [200.0],
            "H298": [0.0],
            "S298": [0.0],
            "f1": [10.0],
            "f2": [0.1],
            "f3": [0.0],
            "f4": [0.0],
            "f5": [0.0],
            "f6": [0.0],
            "MeltingPoint": [0.0],
            "BoilingPoint": [0.0],
            "ReliabilityClass": [1],
        }
        df = pd.DataFrame(data)
        record = df.iloc[0]  # pandas Series

        result = selector.optimize_selected_records(
            selected_records=[record],
            target_range=(150, 180),
            all_available_records=df,
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should handle pandas Series records
        assert len(result) == 1

    def test_optimization_with_no_improvement(self, selector):
        """Test case where optimization cannot improve the score."""
        records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=100,
                tmax=400,
                h298=0,
                s298=0,  # Single optimal record
                f1=10.0,
                f2=0.1,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            )
        ]

        result = selector.optimize_selected_records(
            selected_records=records,
            target_range=(150, 350),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should return original record (no improvement possible)
        assert len(result) == 1
        assert result[0].rowid == 1


if __name__ == "__main__":
    pytest.main([__file__])
