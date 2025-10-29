"""
Unit tests for filter stages.

Tests all concrete filter stage implementations including
temperature filtering, phase selection, and reliability prioritization.
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
from src.thermo_agents.filtering.filter_stages import (
    PhaseSelectionStage, ReliabilityPriorityStage
)
from src.thermo_agents.filtering.phase_resolver import PhaseResolver




class TestPhaseSelectionStage:
    """Test cases for PhaseSelectionStage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.phase_resolver = PhaseResolver()
        self.stage = PhaseSelectionStage(self.phase_resolver)
        self.context = FilterContext(
            compound_formula="H2O"
        )

    def create_test_records(self) -> List[DatabaseRecord]:
        """Create test database records with various phases."""
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
                reliability_class=1
            ),
            DatabaseRecord(
                id=4,
                formula="H2O",
                phase=None,  # No phase specified
                tmin=250.0,
                tmax=400.0,
                h298=-270.0,
                s298=120.0,
                f1=22.0,
                f2=7.0,
                f3=0.6,
                f4=-0.06,
                f5=0.006,
                f6=-0.0006,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=2
            )
        ]

    def test_phase_selection_liquid_temperature(self):
        """Test phase selection at liquid temperature range."""
        records = self.create_test_records()
        filtered = self.stage.filter(records, self.context)

        # At 325K (middle of 300-350K), water should be liquid
        # Should prefer record 2 (liquid phase)
        assert len(filtered) >= 1

        # The liquid record should have the highest score
        liquid_record = next(r for r in records if r.phase == 'l')
        assert liquid_record in filtered

    def test_phase_selection_solid_temperature(self):
        """Test phase selection at solid temperature range."""
        context = FilterContext(
            compound_formula="H2O"
        )
        records = self.create_test_records()
        filtered = self.stage.filter(records, context)

        # At 260K, water should be solid
        # Should prefer record 3 (solid phase)
        solid_record = next(r for r in records if r.phase == 's')
        assert solid_record in filtered

    def test_phase_selection_gas_temperature(self):
        """Test phase selection at gas temperature range."""
        context = FilterContext(
            compound_formula="H2O"
        )
        records = self.create_test_records()
        filtered = self.stage.filter(records, self.context)

        # At 450K, water should be gas
        # Should prefer record 1 (gas phase)
        gas_record = next(r for r in records if r.phase == 'g')
        assert gas_record in filtered

    def test_phase_selection_statistics(self):
        """Test phase selection statistics collection."""
        records = self.create_test_records()
        self.stage.filter(records, self.context)

        stats = self.stage.get_statistics()

        assert 'phase_matches' in stats
        assert 'phase_mismatches' in stats
        assert 'phase_analysis' in stats
        assert 'mid_temperature' in stats
        assert 'execution_time_ms' in stats
        assert 'average_score' in stats

        # Check phase analysis structure
        phase_analysis = stats['phase_analysis']
        assert 'correct' in phase_analysis
        assert 'unknown' in phase_analysis
        assert 'incorrect' in phase_analysis

    def test_phase_scoring(self):
        """Test phase scoring logic."""
        # Test correct phase match
        score = self.stage._calculate_phase_score(
            DatabaseRecord(
                id=1,
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
            'l'
        )
        assert score == 1.0

        # Test unknown phase
        score = self.stage._calculate_phase_score(
            DatabaseRecord(
                id=1,
                formula="H2O",
                phase=None,
                tmin=250.0,
                tmax=400.0,
                h298=-270.0,
                s298=120.0,
                f1=22.0,
                f2=7.0,
                f3=0.6,
                f4=-0.06,
                f5=0.006,
                f6=-0.0006,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=2
            ),
            'l'
        )
        assert score == 0.5

        # Test incorrect phase
        score = self.stage._calculate_phase_score(
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
            's'
        )
        assert score == 0.0

    def test_phase_extraction(self):
        """Test phase extraction from records."""
        # From phase field
        record1 = DatabaseRecord(
            id=1,
            formula="H2O",
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
        )
        assert self.stage._extract_phase(record1) == 'l'

        # From formula
        record2 = DatabaseRecord(
            id=2,
            formula="H2O(g)",
            phase=None,
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
        assert self.stage._extract_phase(record2) == 'g'

        # No phase available
        record3 = DatabaseRecord(
            id=3,
            formula="H2O",
            phase=None,
            tmin=250.0,
            tmax=400.0,
            h298=-270.0,
            s298=120.0,
            f1=22.0,
            f2=7.0,
            f3=0.6,
            f4=-0.06,
            f5=0.006,
            f6=-0.0006,
            tmelt=273.0,
            tboil=373.0,
            reliability_class=2
        )
        assert self.stage._extract_phase(record3) is None

    def test_get_stage_name(self):
        """Test stage name."""
        assert self.stage.get_stage_name() == "Фазовая фильтрация"


class TestReliabilityPriorityStage:
    """Test cases for ReliabilityPriorityStage."""

    def setup_method(self):
        """Set up test fixtures."""
        self.stage = ReliabilityPriorityStage(max_records=2)
        self.context = FilterContext(
            compound_formula="H2O"
        )

    def create_test_records(self) -> List[DatabaseRecord]:
        """Create test database records with various reliability classes."""
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
                reliability_class=1  # Best reliability
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
                reliability_class=2  # Good reliability
            ),
            DatabaseRecord(
                id=3,
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
                reliability_class=3  # Lower reliability
            ),
            DatabaseRecord(
                id=4,
                formula="H2O",
                phase=None,
                tmin=250.0,
                tmax=400.0,
                h298=-270.0,
                s298=120.0,
                f1=22.0,
                f2=7.0,
                f3=0.6,
                f4=-0.06,
                f5=0.006,
                f6=-0.0006,
                tmelt=273.0,
                tboil=373.0,
                reliability_class=1  # Best reliability
            )
        ]

    def test_reliability_priority_selection(self):
        """Test priority selection based on reliability class."""
        records = self.create_test_records()
        filtered = self.stage.filter(records, self.context)

        # Should select top 2 records based on reliability
        assert len(filtered) == 2

        # Should include records with reliability class 1 (best)
        reliability_classes = [r.reliability_class for r in filtered]
        assert 1 in reliability_classes

        # Should be sorted by priority (best first)
        assert filtered[0].reliability_class <= filtered[1].reliability_class

    def test_reliability_priority_single_record(self):
        """Test priority selection with max_records=1."""
        stage = ReliabilityPriorityStage(max_records=1)
        records = self.create_test_records()
        filtered = stage.filter(records, self.context)

        assert len(filtered) == 1
        assert filtered[0].reliability_class == 1  # Best reliability

    def test_reliability_priority_statistics(self):
        """Test reliability priority statistics collection."""
        records = self.create_test_records()
        self.stage.filter(records, self.context)

        stats = self.stage.get_statistics()

        assert 'total_candidates' in stats
        assert 'selected' in stats
        assert 'max_records' in stats
        assert 'reliability_distribution' in stats
        assert 'average_completeness' in stats
        assert 'average_score' in stats
        assert 'execution_time_ms' in stats

        assert stats['total_candidates'] == 4
        assert stats['selected'] == 2
        assert stats['max_records'] == 2

        # Check reliability distribution
        rel_dist = stats['reliability_distribution']
        assert 1 in rel_dist
        assert 2 in rel_dist
        assert 3 in rel_dist

    def test_priority_score_calculation(self):
        """Test priority score calculation."""
        # Record with best reliability, phase transitions, wide range
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
        score1 = self.stage._calculate_priority_score(record1)

        # Record with lower reliability, no phase transitions, narrow range
        record2 = DatabaseRecord(
            id=2,
            formula="H2O",
            phase=None,
            tmin=300.0,
            tmax=350.0,
            h298=-270.0,
            s298=120.0,
            f1=22.0,
            f2=7.0,
            f3=0.6,
            f4=-0.06,
            f5=0.006,
            f6=-0.0006,
            tmelt=273.0,
            tboil=373.0,
            reliability_class=3
        )
        score2 = self.stage._calculate_priority_score(record2)

        assert score1 > score2

    def test_completeness_calculation(self):
        """Test completeness calculation."""
        record = DatabaseRecord(
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

        completeness = self.stage._calculate_completeness(record)
        assert completeness == 1.0  # All fields are populated in database

    def test_get_stage_name(self):
        """Test stage name."""
        assert self.stage.get_stage_name() == "Приоритизация по надёжности"