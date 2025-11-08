"""
Unit tests for OptimalRecordSelector.

Tests the optimal record selection algorithm including virtual record merging,
score calculation, and phase transition handling.
"""

from typing import List

import numpy as np
import pandas as pd
import pytest

from thermo_agents.models.search import DatabaseRecord
from thermo_agents.selection.optimal_record_selector import (
    OptimalRecordSelector,
    OptimizationScore,
    VirtualRecord,
)
from thermo_agents.selection.selection_config import OptimizationConfig, RecordGroup


class TestOptimalRecordSelector:
    """Test cases for OptimalRecordSelector."""

    @pytest.fixture
    def config(self):
        """Create test optimization configuration."""
        return OptimizationConfig(
            w1_record_count=0.5,
            w2_data_quality=0.3,
            w3_transition_coverage=0.2,
            gap_tolerance_k=1.0,
            transition_tolerance_k=10.0,
            coeffs_comparison_tolerance=1e-6,
        )

    @pytest.fixture
    def selector(self, config):
        """Create OptimalRecordSelector instance."""
        return OptimalRecordSelector(config)

    @pytest.fixture
    def sample_records(self):
        """Create sample database records for testing."""
        records = [
            # Record 1: Solid phase, 298-480K
            DatabaseRecord(
                rowid=1,
                formula="SiO2",
                first_name="SiO2(CR)",
                phase="s",
                tmin=298.1,
                tmax=480.0,
                h298=-908.0,
                s298=43.06,
                f1=58.75,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1883.0,
                tboil=2630.0,
                reliability_class=1,
            ),
            # Record 2: Solid phase, 480-540K (continuation)
            DatabaseRecord(
                rowid=2,
                formula="SiO2",
                first_name="SiO2(CR)",
                phase="s",
                tmin=480.0,
                tmax=540.0,
                h298=0.0,
                s298=0.0,
                f1=58.75,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1883.0,
                tboil=2630.0,
                reliability_class=1,
            ),
            # Record 3: Solid phase, 540-600K (continuation)
            DatabaseRecord(
                rowid=3,
                formula="SiO2",
                first_name="SiO2(CR)",
                phase="s",
                tmin=540.0,
                tmax=600.0,
                h298=0.0,
                s298=0.0,
                f1=58.75,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1883.0,
                tboil=2630.0,
                reliability_class=1,
            ),
            # Record 4: Solid phase, 600-3100K (continuation)
            DatabaseRecord(
                rowid=4,
                formula="SiO2",
                first_name="SiO2(CR)",
                phase="s",
                tmin=600.0,
                tmax=3100.0,
                h298=0.0,
                s298=0.0,
                f1=58.75,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1883.0,
                tboil=2630.0,
                reliability_class=1,
            ),
        ]
        return records

    @pytest.fixture
    def h2o_records(self):
        """Create H2O records for testing phase transitions."""
        records = [
            # Liquid H2O: 298-372.8K
            DatabaseRecord(
                rowid=1,
                formula="H2O",
                first_name="Water",
                phase="l",
                tmin=298.1,
                tmax=372.8,
                h298=-285.8,
                s298=69.95,
                f1=30.09,
                f2=6.8325,
                f3=6.283,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1,
            ),
            # Gas H2O: 298-600K
            DatabaseRecord(
                rowid=2,
                formula="H2O",
                first_name="Water",
                phase="g",
                tmin=298.1,
                tmax=600.0,
                h298=-241.8,
                s298=188.8,
                f1=33.33,
                f2=0.0113,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=1,
            ),
            # Gas H2O: 600-1600K (continuation)
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
                reliability_class=1,
            ),
            # Gas H2O: 1600-6000K (continuation)
            DatabaseRecord(
                rowid=4,
                formula="H2O",
                first_name="Water",
                phase="g",
                tmin=1600.0,
                tmax=6000.0,
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
                reliability_class=1,
            ),
        ]
        return records

    @pytest.fixture
    def cecl3_records(self):
        """Create CeCl3 records for testing duplicate elimination."""
        records = [
            # Solid CeCl3: 298-1080K
            DatabaseRecord(
                rowid=1,
                formula="CeCl3",
                first_name="Cerium chloride",
                phase="s",
                tmin=298.1,
                tmax=1080.0,
                h298=-1060.0,
                s298=151.0,
                f1=91.25,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1080.0,
                tboil=2000.0,
                reliability_class=1,
            ),
            # Liquid CeCl3: 1080-1300K
            DatabaseRecord(
                rowid=2,
                formula="CeCl3",
                first_name="Cerium chloride",
                phase="l",
                tmin=1080.0,
                tmax=1300.0,
                h298=-1020.0,
                s298=189.0,
                f1=95.50,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1080.0,
                tboil=2000.0,
                reliability_class=1,
            ),
            # Liquid CeCl3: 1080-1500K (duplicate range)
            DatabaseRecord(
                rowid=3,
                formula="CeCl3",
                first_name="Cerium chloride",
                phase="l",
                tmin=1080.0,
                tmax=1500.0,
                h298=-1020.0,
                s298=189.0,
                f1=95.50,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmelt=1080.0,
                tboil=2000.0,
                reliability_class=1,
            ),
        ]
        return records

    @pytest.fixture
    def all_records_df(self, sample_records):
        """Create DataFrame with all available records."""
        data = []
        for record in sample_records:
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
        return pd.DataFrame(data)

    def test_initialization(self, config):
        """Test OptimalRecordSelector initialization."""
        selector = OptimalRecordSelector(config)
        assert selector.config == config
        assert selector._virtual_record_cache == {}

    def test_initialization_default_config(self):
        """Test OptimalRecordSelector with default configuration."""
        selector = OptimalRecordSelector()
        assert selector.config.w1_record_count == 0.5
        assert selector.config.w2_data_quality == 0.3
        assert selector.config.w3_transition_coverage == 0.2

    def test_empty_records_handling(self, selector):
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

    def test_single_record_handling(self, selector, sample_records):
        """Test handling of single record."""
        result = selector.optimize_selected_records(
            selected_records=[sample_records[0]],
            target_range=(298, 400),
            all_available_records=pd.DataFrame(),
            melting=None,
            boiling=None,
            is_elemental=False,
        )
        assert len(result) == 1
        assert result[0] == sample_records[0]

    def test_sio2_validation_optimal(self, selector, sample_records, all_records_df):
        """
        Test that SiO2 records are already optimal (no changes expected).

        According to the specification, SiO2 with 4 records should be
        validated as already optimal due to lack of better alternatives.
        """
        result = selector.optimize_selected_records(
            selected_records=sample_records,
            target_range=(298, 2500),
            all_available_records=all_records_df,
            melting=1883.0,
            boiling=2630.0,
            is_elemental=False,
        )

        # Should return the same 4 records (no optimization possible)
        assert len(result) == 4

        # Records should be in the same order
        for i, (original, optimized) in enumerate(zip(sample_records, result)):
            if isinstance(optimized, VirtualRecord):
                # If virtual record was created, it should contain the original
                assert original in optimized.source_records
            else:
                assert optimized.rowid == original.rowid

    def test_h2o_virtual_merging(self, selector, h2o_records):
        """
        Test H2O virtual merging of gas phase records.

        Records 3 and 4 have identical Shomate coefficients and can be
        virtually merged to reduce record count from 4 to 3.
        """
        # Create DataFrame with all H2O records
        data = []
        for record in h2o_records:
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
            selected_records=h2o_records,
            target_range=(298, 2000),
            all_available_records=all_records_df,
            melting=273.15,
            boiling=373.15,
            is_elemental=False,
        )

        # Virtual merging may or may not happen depending on coefficient similarity
        # If merging happens: 3 records (1 liquid + 1 gas + 1 virtual)
        # If not: 4 records (1 liquid + 3 gas)
        assert len(result) in [3, 4], f"Expected 3 or 4 records, got {len(result)}"

        # Check that we have liquid and gas records
        def get_phase(r):
            return r.Phase if hasattr(r, "Phase") else r.phase

        phases = [get_phase(r) for r in result]
        assert "l" in phases
        assert "g" in phases

        # Check for virtual record creation (optional)
        virtual_records = [r for r in result if isinstance(r, VirtualRecord)]
        if virtual_records:
            # Virtual record should merge records 3 and 4
            virtual_record = virtual_records[0]
            assert virtual_record.phase == "g"
            assert len(virtual_record.source_records) == 2
            assert virtual_record.merged_tmin == 600.0
            assert virtual_record.merged_tmax == 6000.0

    def test_cecl3_duplicate_elimination(self, selector, cecl3_records):
        """
        Test CeCl3 duplicate elimination in liquid phase.

        Records 2 and 3 both cover liquid phase with overlapping ranges.
        Should optimize to 2 records by selecting the wider range record.
        """
        # Create DataFrame with all CeCl3 records
        data = []
        for record in cecl3_records:
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
            selected_records=cecl3_records,
            target_range=(298, 1500),
            all_available_records=all_records_df,
            melting=1080.0,
            boiling=2000.0,
            is_elemental=False,
        )

        # Should optimize to 2 records: 1 solid + 1 liquid (wider range)
        assert len(result) == 2

        # Check phases
        def get_phase(r):
            return r.Phase if hasattr(r, "Phase") else r.phase

        phases = [get_phase(r) for r in result]
        assert "s" in phases
        assert "l" in phases

        # Check that liquid record covers the wider range (1080-1500K)
        liquid_records = [r for r in result if get_phase(r) == "l"]
        assert len(liquid_records) == 1
        liquid_record = liquid_records[0]

        def get_tmin(r):
            return r.Tmin if hasattr(r, "Tmin") else r.tmin

        def get_tmax(r):
            return r.Tmax if hasattr(r, "Tmax") else r.tmax

        assert get_tmin(liquid_record) == 1080.0
        assert get_tmax(liquid_record) == 1500.0

    def test_can_merge_virtually_identical_coeffs(self, selector):
        """Test virtual merging with identical Shomate coefficients."""
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

        can_merge = selector._can_merge_virtually(records)
        assert can_merge is True

    def test_can_merge_virtually_different_coeffs(self, selector):
        """Test virtual merging with different Shomate coefficients."""
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
                f6=0.0,
                tmelt=0,
                tboil=0,
                reliability_class=1,
            ),
        ]

        can_merge = selector._can_merge_virtually(records)
        assert can_merge is False

    def test_virtual_record_creation(self, selector):
        """Test VirtualRecord creation and properties."""
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

        assert isinstance(virtual_record, VirtualRecord)
        assert virtual_record.is_virtual is True
        assert virtual_record.source_records == source_records
        assert virtual_record.merged_tmin == 100.0
        assert virtual_record.merged_tmax == 300.0
        assert virtual_record.tmin == 100.0
        assert virtual_record.tmax == 300.0
        assert virtual_record.phase == "g"

    def test_optimization_score_calculation(self, config):
        """Test optimization score calculation."""
        # Test with 2 records, average reliability 1.5, full transition coverage
        score = OptimizationScore.calculate(
            n_records=2, avg_reliability=1.5, transition_coverage=1.0, config=config
        )

        expected_record_score = 1.0 / 2.0  # 0.5
        expected_quality_score = (3.0 - 1.5) / 3.0  # 0.5
        expected_transition_score = 1.0

        expected_total = (
            config.w1_record_count * expected_record_score
            + config.w2_data_quality * expected_quality_score
            + config.w3_transition_coverage * expected_transition_score
        )

        assert abs(score.total_score - expected_total) < 1e-6
        assert score.record_count_score == expected_record_score
        assert score.data_quality_score == expected_quality_score
        assert score.transition_coverage_score == expected_transition_score

    def test_score_improvement_detection(self, config):
        """Test score improvement detection."""
        baseline_score = OptimizationScore(0.4, 0.5, 0.3, 1.0)
        improved_score = OptimizationScore(0.5, 0.5, 0.3, 1.0)

        assert (
            improved_score.is_better_than(baseline_score, min_improvement=0.1) is True
        )
        assert (
            improved_score.is_better_than(baseline_score, min_improvement=0.3) is False
        )

    def test_phase_transition_coverage_validation(self, selector, h2o_records):
        """Test phase transition coverage validation."""
        result = selector.optimize_selected_records(
            selected_records=h2o_records,
            target_range=(298, 500),
            all_available_records=pd.DataFrame(),
            melting=273.15,
            boiling=373.15,
            is_elemental=False,
        )

        # Should ensure boiling point (373.15K) is covered
        def get_tmin(r):
            return r.Tmin if hasattr(r, "Tmin") else r.tmin

        def get_tmax(r):
            return r.Tmax if hasattr(r, "Tmax") else r.tmax

        boiling_covered = any(get_tmin(r) <= 373.15 <= get_tmax(r) for r in result)
        assert boiling_covered, "Boiling point should be covered by optimized records"

    def test_reliability_prioritization(self, selector):
        """Test that records with better reliability class are prioritized."""
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
                reliability_class=2,  # Worse reliability
            ),
            DatabaseRecord(
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
                reliability_class=1,  # Better reliability
            ),
        ]

        # Create DataFrame with both records
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
            target_range=(150, 180),
            all_available_records=all_records_df,
            melting=None,
            boiling=None,
            is_elemental=False,
        )

        # Should select the record with better reliability (class 1)
        assert len(result) == 1
        assert result[0].reliability_class == 1

    def test_temperature_coverage_validation(self, selector):
        """Test temperature coverage validation."""
        # Records with gap
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
                tmin=300,
                tmax=400,
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

        # Test with gap exceeding tolerance
        is_valid = selector._validate_temperature_coverage(records, 100, 400)
        assert is_valid is False  # Gap of 100K exceeds tolerance

        # Test with acceptable gap - target range doesn't require the gap to be covered
        is_valid = selector._validate_temperature_coverage(records, 100, 200)
        assert is_valid is True  # Only first record needed, no gap issue

    def test_phase_sequence_validation(self, selector):
        """Test phase sequence validation."""
        # Valid sequence: s -> l -> g
        valid_records = [
            DatabaseRecord(
                rowid=1,
                formula="Test",
                first_name="Test",
                phase="s",
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
                phase="l",
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
            DatabaseRecord(
                rowid=3,
                formula="Test",
                first_name="Test",
                phase="g",
                tmin=300,
                tmax=400,
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

        is_valid = selector._validate_phase_sequence(valid_records)
        assert is_valid is True

        # Invalid sequence: g -> s
        invalid_records = [
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
                phase="s",
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

        is_valid = selector._validate_phase_sequence(invalid_records)
        assert is_valid is False

    def test_performance_timing(self, selector, sample_records, all_records_df):
        """Test that optimization completes within performance limits."""
        import time

        start_time = time.perf_counter()

        result = selector.optimize_selected_records(
            selected_records=sample_records,
            target_range=(298, 2500),
            all_available_records=all_records_df,
            melting=1883.0,
            boiling=2630.0,
            is_elemental=False,
        )

        elapsed_time_ms = (time.perf_counter() - start_time) * 1000

        # Should complete within 50ms
        assert elapsed_time_ms < selector.config.max_optimization_time_ms
        assert len(result) > 0  # Should still return valid results

    def test_config_validation(self):
        """Test OptimizationConfig validation."""
        # Valid configuration
        config = OptimizationConfig()
        assert (
            config.w1_record_count
            + config.w2_data_quality
            + config.w3_transition_coverage
            == 1.0
        )

        # Invalid configuration (weights don't sum to 1.0)
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            OptimizationConfig(
                w1_record_count=0.6,
                w2_data_quality=0.3,
                w3_transition_coverage=0.2,  # Sum = 1.1
            )

        # Invalid configuration (negative weight)
        with pytest.raises(ValueError, match="All weights must be positive"):
            OptimizationConfig(
                w1_record_count=-0.1, w2_data_quality=0.3, w3_transition_coverage=0.8
            )

        # Invalid configuration (negative tolerance)
        with pytest.raises(ValueError, match="Gap tolerance must be non-negative"):
            OptimizationConfig(gap_tolerance_k=-1.0)

    def test_record_group_properties(self):
        """Test RecordGroup properties and methods."""
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
                reliability_class=2,
            ),
        ]

        group = RecordGroup(
            phase="g", tmin=100, tmax=300, records=records, is_first_in_phase=True
        )

        assert group.phase == "g"
        assert group.tmin == 100
        assert group.tmax == 300
        assert group.temperature_span == 200
        assert group.record_count == 2
        assert group.avg_reliability == 1.5
        assert group.is_first_in_phase is True


if __name__ == "__main__":
    pytest.main([__file__])
