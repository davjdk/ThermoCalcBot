"""
Tests for Stage 5 formatting functionality.

Tests the enhanced formatting capabilities for multi-phase calculations
with calculation methods, visual indicators, and comprehensive information display.
"""

import pytest
from unittest.mock import Mock

from src.thermo_agents.formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from src.thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from src.thermo_agents.models.search import MultiPhaseCompoundData, PhaseSegment, PhaseTransition
from src.thermo_agents.models.aggregation import MultiPhaseReactionData
from src.thermo_agents.models.extraction import ExtractedReactionParameters


class TestStage5Formatting:
    """Test Stage 5 specific formatting enhancements."""

    @pytest.fixture
    def calculator(self):
        """Create a mock calculator."""
        return Mock()

    @pytest.fixture
    def reaction_formatter(self, calculator):
        """Create a reaction calculation formatter."""
        return ReactionCalculationFormatter(calculator)

    @pytest.fixture
    def compound_formatter(self, calculator):
        """Create a compound data formatter."""
        return CompoundDataFormatter(calculator)

    @pytest.fixture
    def sample_feo_compound_data(self):
        """Create sample FeO multi-phase compound data."""
        mock_compound_data = Mock(spec=MultiPhaseCompoundData)
        mock_compound_data.compound_formula = "FeO"

        # Create mock records
        mock_records = []
        for i in range(3):
            record = Mock()
            record.Tmin = 298.0 + i * 1000
            record.Tmax = 298.0 + (i + 1) * 1000
            record.phase = ["s", "l", "g"][i]
            record.h298 = -265.053
            record.s298 = 59.807
            record.name = "Iron(II) oxide"
            mock_records.append(record)

        mock_compound_data.records = mock_records

        # Create mock segments
        mock_segments = []
        for i, (record, phase) in enumerate(zip(mock_records, ["s", "l", "g"])):
            mock_segment = Mock(spec=PhaseSegment)
            mock_segment.phase = phase
            mock_segment.T_start = record.Tmin
            mock_segment.T_end = record.Tmax
            mock_segment.records = [record]
            mock_segments.append(mock_segment)

        mock_compound_data.segments = mock_segments

        # Create mock transitions
        mock_transitions = []
        # Melting transition (calculated)
        mock_melting = Mock(spec=PhaseTransition)
        mock_melting.temperature = 1650.0
        mock_melting.from_phase = "s"
        mock_melting.to_phase = "l"
        mock_melting.delta_H = 31.5
        mock_melting.delta_S = 19.1
        mock_melting.calculation_method = "calculated"
        mock_melting.reliability = "high"
        mock_transitions.append(mock_melting)

        # Boiling transition (heuristic)
        mock_boiling = Mock(spec=PhaseTransition)
        mock_boiling.temperature = 3687.0
        mock_boiling.from_phase = "l"
        mock_boiling.to_phase = "g"
        mock_boiling.delta_H = 314.0
        mock_boiling.delta_S = 85.2
        mock_boiling.calculation_method = "heuristic"
        mock_boiling.reliability = "medium"
        mock_transitions.append(mock_boiling)

        mock_compound_data.transitions = mock_transitions

        return mock_compound_data

    @pytest.fixture
    def sample_reaction_data(self, sample_feo_compound_data):
        """Create sample multi-phase reaction data."""
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.balanced_equation = "FeO + H2S → FeS + H2O"
        mock_reaction_data.reactants = ["FeO", "H2S"]
        mock_reaction_data.products = ["FeS", "H2O"]
        mock_reaction_data.stoichiometry = {"FeO": -1.0, "H2S": -1.0, "FeS": 1.0, "H2O": 1.0}
        mock_reaction_data.user_temperature_range = (773, 973)  # 500-700°C
        mock_reaction_data.calculation_range = (298.0, 5000.0)
        mock_reaction_data.compounds_data = {"FeO": sample_feo_compound_data}
        mock_reaction_data.phase_changes = [
            (1650.0, "FeO", "melting"),
            (3687.0, "FeO", "boiling")
        ]
        mock_reaction_data.calculation_table = [
            {"T": 298, "delta_H": -33.45, "delta_S": -45.23, "delta_G": -19.97, "phase": "s,g", "comment": "Стандартные условия"},
            {"T": 773, "delta_H": -28.12, "delta_S": -42.11, "delta_G": -4.58, "phase": "s,g", "comment": "Запрошенный диапазон"},
            {"T": 973, "delta_H": -27.60, "delta_S": -41.87, "delta_G": +1.12, "phase": "s,g", "comment": "Запрошенный диапазон"},
            {"T": 1650, "delta_H": -25.30, "delta_S": -40.50, "delta_G": +41.53, "phase": "s→l", "comment": "Плавление FeO"},
            {"T": 3687, "delta_H": -22.15, "delta_S": -39.20, "delta_G": +122.48, "phase": "l→g", "comment": "Кипение FeO"},
            {"T": 5000, "delta_H": -18.90, "delta_S": -38.10, "delta_G": +171.60, "phase": "g,g", "comment": "Максимальная температура"}
        ]
        mock_reaction_data.data_statistics = {}
        mock_reaction_data.calculation_method = "multi_phase_v2"
        mock_reaction_data.total_records_used = 8
        mock_reaction_data.phases_used = {"s", "l", "g"}

        # Mock methods
        mock_reaction_data.get_phase_transition_count.return_value = 2
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.get_range_expansion_factor.return_value = 5.1

        return mock_reaction_data

    @pytest.fixture
    def sample_params(self):
        """Create sample extracted reaction parameters."""
        return Mock(spec=ExtractedReactionParameters)
        sample_params.temperature_range_k = (773, 973)

    def test_multi_phase_reaction_formatting(self, reaction_formatter, sample_reaction_data, sample_params):
        """Test multi-phase reaction formatting with Stage 5 enhancements."""
        result = reaction_formatter.format_multi_phase_reaction(sample_reaction_data, sample_params)

        # Verify Stage 5 specific formatting elements
        assert "Полная многофазная логика" in result
        assert "Запрошенный диапазон: 773-973K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "максимальное использование базы данных" in result
        assert "ИНФОРМАЦИЯ: Расчёт выполнен с использованием всех доступных данных из базы" in result
        assert "Данные веществ:" in result
        assert "Фазовые переходы в реакции:" in result
        assert "Результаты расчёта:" in result
        assert "Статистика расчёта:" in result

    def test_range_information_display(self, reaction_formatter):
        """Test range information formatting."""
        # Test with user range
        user_range = (773, 973)
        calc_range = (298, 5000)

        result = reaction_formatter._format_range_information(user_range, calc_range)

        assert "Запрошенный диапазон: 773-973K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "Расширение диапазона: 5.1x" in result
        assert "✅ Включены стандартные условия (298K)" in result

        # Test without user range
        result = reaction_formatter._format_range_information(None, calc_range)

        assert "Расчётный диапазон: 298-5000K" in result
        assert "Запрошенный диапазон:" not in result
        assert "Расширение диапазона:" not in result

    def test_phase_information_display(self, reaction_formatter, sample_feo_compound_data):
        """Test phase information formatting."""
        compounds_data = {"FeO": sample_feo_compound_data}

        result = reaction_formatter._format_phase_information(compounds_data)

        # Verify phase information elements
        assert "FeO — Iron(II) oxide" in result
        assert "Общий диапазон: 298-5000K" in result
        assert "Фазовые переходы:" in result
        assert "s→l при 1650K" in result
        assert "l→g при 3687K" in result
        assert "Использованные фазы:" in result
        assert "H₂₉₈: -265.053 кДж/моль" in result
        assert "S₂₉₈: 59.807 Дж/(моль·K)" in result
        assert "Всего записей использовано: 3" in result

    def test_phase_transition_display(self, reaction_formatter):
        """Test phase transition information display."""
        # Test calculated transition
        calculated_transition = Mock(spec=PhaseTransition)
        calculated_transition.temperature = 1650.0
        calculated_transition.from_phase = "s"
        calculated_transition.to_phase = "l"
        calculated_transition.delta_H = 31.5
        calculated_transition.calculation_method = "calculated"
        calculated_transition.reliability = "high"

        result = reaction_formatter._format_single_transition(calculated_transition)

        assert "s→l при 1650K" in result
        assert "ΔH = 31.5 кДж/моль" in result
        assert "(рассчитано из H298)" in result
        assert "≈" not in result  # No approximation symbol for calculated
        assert "⚠️" not in result  # No warning for high reliability

        # Test heuristic transition
        heuristic_transition = Mock(spec=PhaseTransition)
        heuristic_transition.temperature = 3687.0
        heuristic_transition.from_phase = "l"
        heuristic_transition.to_phase = "g"
        heuristic_transition.delta_H = 314.0
        heuristic_transition.calculation_method = "heuristic"
        heuristic_transition.reliability = "low"

        result = reaction_formatter._format_single_transition(heuristic_transition)

        assert "l→g при 3687K" in result
        assert "ΔH = ≈314.0 кДж/моль" in result
        assert "(эвристическая оценка)" in result
        assert "⚠️" in result  # Warning for low reliability

    def test_calculation_method_indicators(self, reaction_formatter):
        """Test calculation method visual indicators."""
        test_cases = [
            {
                "method": "calculated",
                "delta_H": 31.5,
                "expected_symbol": "",  # No approximation symbol
                "expected_desc": "рассчитано из H298",
                "reliability": "high",
                "expected_warning": ""
            },
            {
                "method": "heuristic",
                "delta_H": 314.0,
                "expected_symbol": "≈",  # Approximation symbol
                "expected_desc": "эвристическая оценка",
                "reliability": "medium",
                "expected_warning": ""
            },
            {
                "method": "heuristic",
                "delta_H": 280.0,
                "expected_symbol": "≈",  # Approximation symbol
                "expected_desc": "эвристическая оценка",
                "reliability": "low",
                "expected_warning": "⚠️"
            }
        ]

        for test_case in test_cases:
            transition = Mock(spec=PhaseTransition)
            transition.temperature = 2000.0
            transition.from_phase = "s"
            transition.to_phase = "l"
            transition.delta_H = test_case["delta_H"]
            transition.calculation_method = test_case["method"]
            transition.reliability = test_case["reliability"]

            result = reaction_formatter._format_single_transition(transition)

            assert f"ΔH = {test_case['expected_symbol']}{test_case['delta_H']:.1f} кДж/моль" in result
            assert f"({test_case['expected_desc']})" in result
            if test_case["expected_warning"]:
                assert test_case["expected_warning"] in result

    def test_data_usage_statistics(self, reaction_formatter, sample_reaction_data):
        """Test data usage statistics formatting."""
        result = reaction_formatter._format_data_usage_statistics(sample_reaction_data)

        assert "Всего использовано записей: 8" in result
        assert "Покрытие базы данных: 100.0%" in result
        assert "Фазовых переходов учтено: 2 (FeO)" in result
        assert "Методы расчёта переходов: 1 calculated, 1 heuristic" in result
        assert "Использованные фазы: газовая, жидкая, твёрдая" in result

    def test_multi_phase_results_table(self, reaction_formatter):
        """Test multi-phase results table formatting."""
        calculation_table = [
            {"T": 298, "delta_H": -33.45, "delta_S": -45.23, "delta_G": -19.97, "phase": "s,g", "comment": "Стандартные условия"},
            {"T": 1650, "delta_H": -25.30, "delta_S": -40.50, "delta_G": +41.53, "phase": "s→l", "comment": "Плавление FeO"},
            {"T": 3687, "delta_H": -22.15, "delta_S": -39.20, "delta_G": +122.48, "phase": "l→g", "comment": "Кипение FeO"}
        ]

        result = reaction_formatter._format_multi_phase_results_table(calculation_table)

        assert "T(K)" in result
        assert "ΔH° (кДж/моль)" in result
        assert "ΔS° (Дж/К·моль)" in result
        assert "ΔG° (кДж/моль)" in result
        assert "Фаза" in result
        assert "Комментарий" in result
        assert "298" in result
        assert "1650" in result
        assert "3687" in result
        assert "Плавление FeO" in result
        assert "Кипение FeO" in result

    def test_compound_data_multi_phase_formatting(self, compound_formatter, sample_feo_compound_data):
        """Test multi-phase compound data formatting."""
        result = compound_formatter.format_multi_phase_compound(sample_feo_compound_data, (773, 973))

        # Verify compound data formatting elements
        assert "FeO — Iron(II) oxide" in result
        assert "Общий диапазон: 298-5000K" in result
        assert "Фазовые сегменты:" in result
        assert "Фазовые переходы:" in result
        assert "Всего записей: 3" in result
        assert "Сегментов: 3" in result
        assert "Фазовых переходов: 2" in result
        assert "Фазы: газовая, жидкая, твёрдая" in result
        assert "Методы расчёта переходов: рассчитанные, эвристические" in result
        assert "✅ Запрошенный диапазон 773-973K покрыт" in result
        assert "⚠️  Некоторые переходы рассчитаны эвристически" in result

    def test_phase_segments_table(self, compound_formatter):
        """Test phase segments table formatting."""
        # Create mock segments
        mock_segments = []
        phases = ["s", "l", "g"]
        for i, phase in enumerate(phases):
            mock_segment = Mock(spec=PhaseSegment)
            mock_segment.phase = phase
            mock_segment.T_start = 298.0 + i * 1000
            mock_segment.T_end = 298.0 + (i + 1) * 1000
            mock_record = Mock()
            mock_record.h298 = -265.053
            mock_record.s298 = 59.807
            mock_segment.records = [mock_record]
            mock_segments.append(mock_segment)

        result = compound_formatter._format_phase_segments_table(mock_segments)

        assert "Фаза" in result
        assert "T-диапазон (K)" in result
        assert "Записей" in result
        assert "H298 (кДж/моль)" in result
        assert "S298 (Дж/моль·K)" in result
        assert "s" in result
        assert "l" in result
        assert "g" in result
        assert "298-1298" in result
        assert "1298-2298" in result
        assert "2298-3298" in result
        assert "-265.053" in result  # H298 value
        assert "59.807" in result   # S298 value

    def test_transitions_table(self, compound_formatter):
        """Test transitions table formatting with calculation methods."""
        # Create mock transitions
        mock_transitions = []

        # Calculated transition
        calc_transition = Mock(spec=PhaseTransition)
        calc_transition.from_phase = "s"
        calc_transition.to_phase = "l"
        calc_transition.temperature = 1650.0
        calc_transition.delta_H = 31.5
        calc_transition.delta_S = 19.1
        calc_transition.calculation_method = "calculated"
        calc_transition.reliability = "high"
        mock_transitions.append(calc_transition)

        # Heuristic transition
        heuristic_transition = Mock(spec=PhaseTransition)
        heuristic_transition.from_phase = "l"
        heuristic_transition.to_phase = "g"
        heuristic_transition.temperature = 3687.0
        heuristic_transition.delta_H = 314.0
        heuristic_transition.delta_S = 85.2
        heuristic_transition.calculation_method = "heuristic"
        heuristic_transition.reliability = "medium"
        mock_transitions.append(heuristic_transition)

        result = compound_formatter._format_transitions_table(mock_transitions)

        assert "Переход" in result
        assert "T (K)" in result
        assert "ΔH (кДж/моль)" in result
        assert "ΔS (Дж/моль·K)" in result
        assert "Метод" in result
        assert "Надёжность" in result
        assert "s→l" in result
        assert "l→g" in result
        assert "1650" in result
        assert "3687" in result
        assert "31.5" in result  # No approximation symbol for calculated
        assert "≈314.0" in result  # Approximation symbol for heuristic
        assert "рассчитано" in result
        assert "эвристика" in result
        assert "✅" in result  # High reliability
        assert "⚠️" in result  # Medium reliability

    def test_records_summary(self, compound_formatter, sample_feo_compound_data):
        """Test records summary formatting."""
        result = compound_formatter._format_records_summary(sample_feo_compound_data)

        assert "Всего записей: 3" in result
        assert "Сегментов: 3" in result
        assert "Фазовых переходов: 2" in result
        assert "Фазы: газовая, жидкая, твёрдая" in result
        assert "Методы расчёта переходов: рассчитанные, эвристические" in result
        assert "⚠️  Некоторые переходы рассчитаны эвристически" in result

    def test_stage_5_header_formatting(self, reaction_formatter):
        """Test Stage 5 specific header formatting."""
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.balanced_equation = "FeO + H2S → FeS + H2O"
        mock_reaction_data.user_temperature_range = (773, 973)
        mock_reaction_data.calculation_range = (298, 5000)
        mock_reaction_data.compounds_data = {}
        mock_reaction_data.phase_changes = []
        mock_reaction_data.calculation_table = []
        mock_reaction_data.total_records_used = 8
        mock_reaction_data.get_phase_transition_count.return_value = 0
        mock_reaction_data.get_compounds_with_transitions.return_value = set()
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.phases_used = set()

        mock_params = Mock()
        mock_params.temperature_range_k = (773, 973)

        result = reaction_formatter.format_multi_phase_reaction(mock_reaction_data, mock_params)

        # Verify Stage 5 header
        assert "================================================================================" in result
        assert "⚗️ Термодинамический расчёт реакции (Полная многофазная логика)" in result
        assert "================================================================================" in result

    def test_visual_indicators_usage(self, reaction_formatter):
        """Test proper usage of visual indicators (≈, ⚠️, ✅)."""
        # Test different transitions with various methods and reliabilities
        test_transitions = [
            {"method": "calculated", "reliability": "high", "expected_symbols": []},
            {"method": "calculated", "reliability": "medium", "expected_symbols": []},
            {"method": "calculated", "reliability": "low", "expected_symbols": ["⚠️"]},
            {"method": "heuristic", "reliability": "high", "expected_symbols": ["≈"]},
            {"method": "heuristic", "reliability": "medium", "expected_symbols": ["≈"]},
            {"method": "heuristic", "reliability": "low", "expected_symbols": ["≈", "⚠️"]},
            {"method": "experimental", "reliability": "high", "expected_symbols": []},
        ]

        for test_case in test_transitions:
            transition = Mock(spec=PhaseTransition)
            transition.temperature = 2000.0
            transition.from_phase = "s"
            transition.to_phase = "l"
            transition.delta_H = 100.0
            transition.delta_S = 50.0
            transition.calculation_method = test_case["method"]
            transition.reliability = test_case["reliability"]

            result = reaction_formatter._format_single_transition(transition)

            # Check for approximation symbol in heuristic methods
            if test_case["method"] == "heuristic":
                assert "≈" in result, f"Expected ≈ symbol for {test_case['method']} method"
            else:
                assert "≈" not in result, f"No ≈ symbol expected for {test_case['method']} method"

            # Check for warning symbols in low reliability
            if test_case["reliability"] == "low":
                assert "⚠️" in result, f"Expected ⚠️ symbol for {test_case['reliability']} reliability"
            else:
                # Medium reliability might also show warnings in some implementations
                if test_case["reliability"] != "medium":
                    assert "⚠️" not in result, f"No ⚠️ symbol expected for {test_case['reliability']} reliability"

    def test_range_expansion_information(self, reaction_formatter):
        """Test range expansion information display."""
        # Test minimal expansion (< 10%)
        user_range = (400, 600)
        calc_range = (298, 700)  # Only ~2.3x expansion

        result = reaction_formatter._format_range_information(user_range, calc_range)

        assert "Расширение диапазона: 2.3x" in result

        # Test significant expansion (> 10%)
        user_range = (800, 900)
        calc_range = (298, 5000)  # ~9.4x expansion

        result = reaction_formatter._format_range_information(user_range, calc_range)

        assert "Расширение диапазона: 9.4x" in result
        assert "для полноты данных" in result

    def test_temperature_range_coverage_display(self, compound_formatter):
        """Test temperature range coverage display."""
        mock_compound_data = Mock(spec=MultiPhaseCompoundData)
        mock_compound_data.compound_formula = "FeO"
        mock_compound_data.records = [Mock(Tmin=298, Tmax=5000)]
        mock_compound_data.segments = []
        mock_compound_data.transitions = []

        # Test covered range
        result = compound_formatter.format_multi_phase_compound(mock_compound_data, (773, 973))
        assert "✅ Запрошенный диапазон 773-973K покрыт" in result

        # Test uncovered range (outside available data)
        result = compound_formatter.format_multi_phase_compound(mock_compound_data, (6000, 7000))
        assert "⚠️  Запрошенный диапазон 6000-7000K выходит за пределы данных" in result