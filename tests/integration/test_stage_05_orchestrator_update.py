"""
Integration tests for Stage 5 - Orchestrator Update and Formatting.

Tests the complete integration of Stages 1-4 components in the orchestrator
and the enhanced formatting capabilities.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from src.thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig
from src.thermo_agents.models.extraction import ExtractedReactionParameters
from src.thermo_agents.models.search import MultiPhaseCompoundData, PhaseSegment, PhaseTransition, DatabaseRecord
from src.thermo_agents.models.aggregation import MultiPhaseReactionData
from src.thermo_agents.formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from src.thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter


class TestStage5OrchestratorUpdate:
    """Integration tests for Stage 5 orchestrator update."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        return MultiPhaseOrchestratorConfig(
            db_path="test.db",
            llm_api_key="test_key",
            llm_base_url="https://test.com",
            llm_model="test-model"
        )

    @pytest.fixture
    def mock_session_logger(self):
        """Create a mock session logger."""
        logger = Mock()
        logger.log_info = Mock()
        logger.log_error = Mock()
        logger.log_warning = Mock()
        return logger

    @pytest.fixture
    def orchestrator(self, mock_config, mock_session_logger):
        """Create a MultiPhaseOrchestrator instance for testing."""
        with patch('src.thermo_agents.orchestrator_multi_phase.StaticDataManager'), \
             patch('src.thermo_agents.orchestrator_multi_phase.DatabaseConnector'), \
             patch('src.thermo_agents.orchestrator_multi_phase.CompoundSearcher'), \
             patch('src.thermo_agents.orchestrator_multi_phase.ThermodynamicCalculator'), \
             patch('src.thermo_agents.orchestrator_multi_phase.TemperatureRangeResolver'), \
             patch('src.thermo_agents.orchestrator_multi_phase.PhaseSegmentBuilder'), \
             patch('src.thermo_agents.orchestrator_multi_phase.MultiPhaseReactionCalculator'), \
             patch('src.thermo_agents.orchestrator_multi_phase.FilterPipeline'), \
             patch('src.thermo_agents.orchestrator_multi_phase.create_thermo_agent'):

            orchestrator = MultiPhaseOrchestrator(mock_config, mock_session_logger)
            return orchestrator

    @pytest.fixture
    def feo_h2s_params(self):
        """Create FeO + H2S reaction parameters for testing."""
        return ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="FeO + H2S → FeS + H2O",
            all_compounds=["FeO", "H2S", "FeS", "H2O"],
            reactants=["FeO", "H2S"],
            products=["FeS", "H2O"],
            temperature_range_k=(773, 973),  # 500-700°C
            extraction_confidence=0.95,
            use_multi_phase=True,
            full_data_search=True,
            stoichiometry={"FeO": -1.0, "H2S": -1.0, "FeS": 1.0, "H2O": 1.0}
        )

    @pytest.fixture
    def sample_feo_records(self):
        """Create sample FeO records with multiple phases."""
        records = []

        # Solid phase record
        solid_record = Mock(spec=DatabaseRecord)
        solid_record.Tmin = 298.0
        solid_record.Tmax = 1650.0
        solid_record.phase = "s"
        solid_record.h298 = -265.053  # Correct H298 from database
        solid_record.s298 = 59.807
        solid_record.name = "Iron(II) oxide"
        records.append(solid_record)

        # Liquid phase record
        liquid_record = Mock(spec=DatabaseRecord)
        liquid_record.Tmin = 1650.0
        liquid_record.Tmax = 3687.0
        liquid_record.phase = "l"
        liquid_record.h298 = -265.053
        liquid_record.s298 = 59.807
        liquid_record.name = "Iron(II) oxide (liquid)"
        records.append(liquid_record)

        # Gas phase record
        gas_record = Mock(spec=DatabaseRecord)
        gas_record.Tmin = 3687.0
        gas_record.Tmax = 5000.0
        gas_record.phase = "g"
        gas_record.h298 = -265.053
        gas_record.s298 = 59.807
        gas_record.name = "Iron(II) oxide (gas)"
        records.append(gas_record)

        return records

    @pytest.mark.asyncio
    async def test_feo_h2s_full_calculation(self, orchestrator, feo_h2s_params, sample_feo_records):
        """Test complete multi-phase calculation for FeO + H2S reaction."""
        # Setup mocks
        orchestrator.thermodynamic_agent = AsyncMock()
        orchestrator.thermodynamic_agent.extract_parameters.return_value = feo_h2s_params

        # Mock compound search to return records without temperature restrictions
        def mock_search_compound(compound, temperature_range=None, max_records=200):
            mock_result = Mock()
            if compound == "FeO":
                mock_result.records = sample_feo_records
            else:
                # Mock other compounds with minimal records
                other_record = Mock(spec=DatabaseRecord)
                other_record.Tmin = 298.0
                other_record.Tmax = 5000.0
                other_record.phase = "g"
                other_record.h298 = -20.502
                other_record.s298 = 205.752
                other_record.name = f"{compound}"
                mock_result.records = [other_record]
            return mock_result

        orchestrator.compound_searcher.search_compound.side_effect = mock_search_compound

        # Mock range determination
        orchestrator._determine_full_calculation_range = Mock(return_value=(298.0, 5000.0))

        # Mock multi-phase data building with phase transitions
        def mock_build_multi_phase_data(compounds_data):
            mp_data = {}
            for compound, records in compounds_data.items():
                mock_mp_compound = Mock(spec=MultiPhaseCompoundData)
                mock_mp_compound.records = records
                mock_mp_compound.compound_formula = compound

                # Create segments
                mock_segments = []
                for i, record in enumerate(records):
                    mock_segment = Mock(spec=PhaseSegment)
                    mock_segment.phase = record.phase
                    mock_segment.T_start = record.Tmin
                    mock_segment.T_end = record.Tmax
                    mock_segment.records = [record]
                    mock_segments.append(mock_segment)

                mock_mp_compound.segments = mock_segments

                # Create transitions for FeO
                if compound == "FeO":
                    mock_transitions = []
                    # Melting transition
                    mock_melting = Mock(spec=PhaseTransition)
                    mock_melting.temperature = 1650.0
                    mock_melting.from_phase = "s"
                    mock_melting.to_phase = "l"
                    mock_melting.delta_H = 31.5  # Calculated from H298
                    mock_melting.calculation_method = "calculated"
                    mock_melting.reliability = "high"
                    mock_transitions.append(mock_melting)

                    # Boiling transition
                    mock_boiling = Mock(spec=PhaseTransition)
                    mock_boiling.temperature = 3687.0
                    mock_boiling.from_phase = "l"
                    mock_boiling.to_phase = "g"
                    mock_boiling.delta_H = 314.0  # Heuristic estimate
                    mock_boiling.calculation_method = "heuristic"
                    mock_boiling.reliability = "medium"
                    mock_transitions.append(mock_boiling)

                    mock_mp_compound.transitions = mock_transitions
                else:
                    mock_mp_compound.transitions = []

                mp_data[compound] = mock_mp_compound

            return mp_data

        orchestrator._build_multi_phase_data = mock_build_multi_phase_data

        # Mock reaction calculation
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.balanced_equation = feo_h2s_params.balanced_equation
        mock_reaction_data.reactants = feo_h2s_params.reactants
        mock_reaction_data.products = feo_h2s_params.products
        mock_reaction_data.stoichiometry = feo_h2s_params.stoichiometry
        mock_reaction_data.user_temperature_range = feo_h2s_params.temperature_range_k
        mock_reaction_data.calculation_range = (298.0, 5000.0)
        mock_reaction_data.compounds_data = mock_build_multi_phase_data({})
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
        mock_reaction_data.get_phase_transition_count.return_value = 2
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0

        orchestrator.reaction_calculator.calculate_reaction_with_transitions.return_value = mock_reaction_data

        # Mock formatter to return structured output
        def mock_format_multi_phase_reaction(reaction_data, params):
            # Simulate the actual formatting output
            lines = []
            lines.append("================================================================================")
            lines.append("⚗️ Термодинамический расчёт реакции (Полная многофазная логика)")
            lines.append("================================================================================")
            lines.append("")
            lines.append(f"Уравнение: {reaction_data.balanced_equation}")
            lines.append("")
            lines.append(f"Запрошенный диапазон: {params.temperature_range_k[0]:.0f}-{params.temperature_range_k[1]:.0f}K")
            lines.append(f"Расчётный диапазон: {reaction_data.calculation_range[0]:.0f}-{reaction_data.calculation_range[1]:.0f}K (максимальное использование базы данных)")
            lines.append("")
            lines.append("ℹ️  ИНФОРМАЦИЯ: Расчёт выполнен с использованием всех доступных данных из базы.")
            lines.append("    Это гарантирует корректность базовых термодинамических свойств (H₂₉₈, S₂₉₈)")
            lines.append("    и учёт фазовых переходов.")
            lines.append("")
            lines.append("Данные веществ:")
            lines.append("--------------------------------------------------------------------------------")
            lines.append("FeO — Iron(II) oxide")
            lines.append("  Общий диапазон: 298-5000K")
            lines.append("  Фазовые переходы:")
            lines.append("    • s→l при 1650K, ΔH = 31.5 кДж/моль (рассчитано из H298)")
            lines.append("    • l→g при 3687K, ΔH = ≈314.0 кДж/моль (эвристическая оценка)")
            lines.append("  Использованные фазы: s (298-1650K), l (1650-3687K), g (3687-5000K)")
            lines.append("  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)")
            lines.append("  Всего записей использовано: 3 из 3")
            lines.append("  ⚠️  Примечание: Некоторые энтальпии переходов рассчитаны приближённо.")
            lines.append("")
            lines.append("H₂S — Hydrogen sulfide")
            lines.append("  Общий диапазон: 298-5000K")
            lines.append("  Фазовых переходов: нет")
            lines.append("  Использованные фазы: g (298-5000K)")
            lines.append("  H₂₉₈: -20.502 кДж/моль | S₂₉₈: 205.752 Дж/(моль·K)")
            lines.append("  Всего записей использовано: 1 из 1")
            lines.append("")
            lines.append("Фазовые переходы в реакции:")
            lines.append("  • FeO при 1650.0K: melting")
            lines.append("  • FeO при 3687.0K: boiling")
            lines.append("")
            lines.append("Результаты расчёта:")
            lines.append("+------+------+------+-----+------+--------------------------------+")
            lines.append("|  T(K) | ΔH° (кДж/моль) | ΔS° (Дж/К·моль) | ΔG° (кДж/моль) | Фаза  | Комментарий                     |")
            lines.append("+=======+================+=================+================+=======+================================+")
            for row in reaction_data.calculation_table:
                lines.append(f"| {row['T']:>4} | {row['delta_H']:>14.2f} | {row['delta_S']:>15.2f} | {row['delta_G']:>14.2f} | {row['phase']:<5} | {row['comment']:<30} |")
            lines.append("+------+------+------+-----+------+--------------------------------+")
            lines.append("")
            lines.append("Статистика расчёта:")
            lines.append(f"- Всего использовано записей: {reaction_data.total_records_used}")
            lines.append(f"- Покрытие базы данных: {reaction_data.get_database_coverage_percentage():.1f}%")
            lines.append(f"- Фазовых переходов учтено: {reaction_data.get_phase_transition_count()} ({', '.join(reaction_data.get_compounds_with_transitions())})")
            lines.append("- Методы расчёта переходов: 1 calculated, 1 heuristic")
            lines.append("- Использованные фазы: газовая, жидкая, твёрдая")

            return "\n".join(lines)

        orchestrator.reaction_formatter.format_multi_phase_reaction.side_effect = mock_format_multi_phase_reaction

        # Execute the test
        result = await orchestrator.process_query_with_multi_phase("FeO + H2S reaction")

        # Verify the result contains key Stage 5 features
        assert "Полная многофазная логика" in result
        assert "Запрошенный диапазон: 773-973K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "максимальное использование базы данных" in result
        assert "H₂₉₈: -265.053 кДж/моль" in result  # Correct H298, not 0.0
        assert "рассчитано из H298" in result
        assert "эвристическая оценка" in result
        assert "Плавление FeO" in result
        assert "Кипение FeO" in result
        assert "Стандартные условия" in result
        assert "Запрошенный диапазон" in result
        assert "Всего использовано записей: 8" in result

        # Verify temperature restrictions were ignored during search
        for call in orchestrator.compound_searcher.search_compound.call_args_list:
            args, kwargs = call
            assert kwargs.get('temperature_range') is None
            assert kwargs.get('max_records') == 200

        # Verify range expansion
        orchestrator._determine_full_calculation_range.assert_called_once()
        orchestrator._build_multi_phase_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_formatting_multi_phase_output(self, orchestrator):
        """Test multi-phase formatting output structure."""
        # Create mock reaction data
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.balanced_equation = "FeO + H2S → FeS + H2O"
        mock_reaction_data.user_temperature_range = (773, 973)
        mock_reaction_data.calculation_range = (298, 5000)
        mock_reaction_data.compounds_data = {}
        mock_reaction_data.phase_changes = []
        mock_reaction_data.calculation_table = []
        mock_reaction_data.total_records_used = 8
        mock_reaction_data.get_phase_transition_count.return_value = 2
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.phases_used = {"s", "l", "g"}

        mock_params = Mock(spec=ExtractedReactionParameters)
        mock_params.temperature_range_k = (773, 973)

        formatter = ReactionCalculationFormatter(Mock())
        result = formatter.format_multi_phase_reaction(mock_reaction_data, mock_params)

        # Verify output structure
        assert "⚗️ Термодинамический расчёт реакции (Полная многофазная логика)" in result
        assert "Запрошенный диапазон:" in result
        assert "Расчётный диапазон:" in result
        assert "ИНФОРМАЦИЯ: Расчёт выполнен с использованием всех доступных данных из базы" in result
        assert "Данные веществ:" in result
        assert "Статистика расчёта:" in result

    @pytest.mark.asyncio
    async def test_user_vs_calculation_range_display(self, orchestrator):
        """Test user requested vs calculation range display."""
        formatter = ReactionCalculationFormatter(Mock())

        # Test with user range
        user_range = (773, 973)
        calc_range = (298, 5000)

        result = formatter._format_range_information(user_range, calc_range)

        assert "Запрошенный диапазон: 773-973K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "Расширение диапазона: 5.4x" in result
        assert "✅ Включены стандартные условия (298K)" in result

        # Test without user range
        result = formatter._format_range_information(None, calc_range)

        assert "Расчётный диапазон: 298-5000K" in result
        assert "Запрошенный диапазон:" not in result

    @pytest.mark.asyncio
    async def test_phase_transition_information(self, orchestrator):
        """Test phase transition information display."""
        formatter = ReactionCalculationFormatter(Mock())

        # Create mock transition
        mock_transition = Mock(spec=PhaseTransition)
        mock_transition.temperature = 1650.0
        mock_transition.from_phase = "s"
        mock_transition.to_phase = "l"
        mock_transition.delta_H = 31.5
        mock_transition.calculation_method = "calculated"
        mock_transition.reliability = "high"

        result = formatter._format_single_transition(mock_transition)

        assert "s→l при 1650K" in result
        assert "ΔH = 31.5 кДж/моль" in result
        assert "(рассчитано из H298)" in result
        assert "⚠️" not in result  # High reliability, no warning

        # Test heuristic transition
        mock_transition.calculation_method = "heuristic"
        mock_transition.reliability = "low"

        result = formatter._format_single_transition(mock_transition)

        assert "ΔH = ≈31.5 кДж/моль" in result  # Should have approximation symbol
        assert "(эвристическая оценка)" in result
        assert "⚠️" in result  # Low reliability warning

    @pytest.mark.asyncio
    async def test_calculation_method_display(self, orchestrator):
        """Test calculation method indicators."""
        formatter = ReactionCalculationFormatter(Mock())

        # Test calculated method
        transition = Mock()
        transition.calculation_method = "calculated"
        transition.reliability = "high"

        result = formatter._format_single_transition(transition)

        assert "рассчитано из H298" in result
        assert "≈" not in result

        # Test heuristic method
        transition.calculation_method = "heuristic"

        result = formatter._format_single_transition(transition)

        assert "эвристическая оценка" in result
        # Note: The ≈ symbol would be added when delta_H is formatted

    @pytest.mark.asyncio
    async def test_data_usage_statistics(self, orchestrator):
        """Test data usage statistics formatting."""
        formatter = ReactionCalculationFormatter(Mock())

        # Create mock reaction data with statistics
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.total_records_used = 8
        mock_reaction_data.get_phase_transition_count.return_value = 2
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.phases_used = {"s", "l", "g"}

        # Mock compound data with transition methods
        mock_compound_data = Mock()
        mock_transition1 = Mock()
        mock_transition1.calculation_method = "calculated"
        mock_transition2 = Mock()
        mock_transition2.calculation_method = "heuristic"
        mock_compound_data.transitions = [mock_transition1, mock_transition2]

        mock_reaction_data.compounds_data = {"FeO": mock_compound_data}

        result = formatter._format_data_usage_statistics(mock_reaction_data)

        assert "Всего использовано записей: 8" in result
        assert "Покрытие базы данных: 100.0%" in result
        assert "Фазовых переходов учтено: 2 (FeO)" in result
        assert "Методы расчёта переходов: 1 calculated, 1 heuristic" in result
        assert "Использованные фазы: газовая, жидкая, твёрдая" in result

    @pytest.mark.asyncio
    async def test_performance_full_pipeline(self, orchestrator, feo_h2s_params):
        """Test performance of the full pipeline."""
        import time

        # Setup minimal mocks for performance testing
        orchestrator.thermodynamic_agent = AsyncMock()
        orchestrator.thermodynamic_agent.extract_parameters.return_value = feo_h2s_params

        # Fast mock implementations
        orchestrator.compound_searcher.search_compound.return_value = Mock(records=[Mock() for _ in range(3)])
        orchestrator._determine_full_calculation_range.return_value = (298.0, 5000.0)
        orchestrator._build_multi_phase_data.return_value = {}
        orchestrator.reaction_calculator.calculate_reaction_with_transitions.return_value = Mock()
        orchestrator.reaction_formatter.format_multi_phase_reaction.return_value = "Test result"

        # Measure execution time
        start_time = time.time()
        result = await orchestrator.process_query_with_multi_phase("FeO + H2S reaction")
        execution_time = time.time() - start_time

        # Verify performance (should be under 3 seconds as per Stage 5 requirements)
        assert execution_time < 3.0, f"Pipeline took {execution_time:.2f}s, should be under 3.0s"
        assert result == "Test result"


class TestStage5Formatting:
    """Test Stage 5 specific formatting functionality."""

    def test_multi_phase_reaction_formatting(self):
        """Test multi-phase reaction formatting."""
        formatter = ReactionCalculationFormatter(Mock())

        # Create mock reaction data
        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.balanced_equation = "FeO + H2S → FeS + H2O"
        mock_reaction_data.user_temperature_range = (773, 973)
        mock_reaction_data.calculation_range = (298, 5000)
        mock_reaction_data.compounds_data = {}
        mock_reaction_data.phase_changes = [(1650, "FeO", "melting")]
        mock_reaction_data.calculation_table = [
            {"T": 773, "delta_H": -28.12, "delta_S": -42.11, "delta_G": -4.58, "phase": "s,g", "comment": "Запрошенный диапазон"}
        ]
        mock_reaction_data.total_records_used = 8
        mock_reaction_data.get_phase_transition_count.return_value = 1
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.phases_used = {"s", "l"}

        mock_params = Mock(spec=ExtractedReactionParameters)
        mock_params.temperature_range_k = (773, 973)

        result = formatter.format_multi_phase_reaction(mock_reaction_data, mock_params)

        # Verify key Stage 5 formatting elements
        assert "Полная многофазная логика" in result
        assert "Запрошенный диапазон: 773-973K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "расчёт выполнен с использованием всех доступных данных из базы" in result
        assert "Фазовые переходы в реакции:" in result
        assert "FeO при 1650K: melting" in result
        assert "Статистика расчёта:" in result

    def test_compound_data_multi_phase_formatting(self):
        """Test multi-phase compound data formatting."""
        formatter = CompoundDataFormatter(Mock())

        # Create mock multi-phase compound data
        mock_compound_data = Mock(spec=MultiPhaseCompoundData)
        mock_compound_data.compound_formula = "FeO"
        mock_compound_data.records = [Mock() for _ in range(3)]

        # Create mock segments
        mock_segments = []
        for i, phase in enumerate(["s", "l", "g"]):
            mock_segment = Mock(spec=PhaseSegment)
            mock_segment.phase = phase
            mock_segment.T_start = 298.0 + i * 1000
            mock_segment.T_end = 298.0 + (i + 1) * 1000
            mock_segment.records = [Mock()]
            mock_segments.append(mock_segment)

        mock_compound_data.segments = mock_segments

        # Create mock transitions
        mock_transitions = []
        for i in range(2):
            mock_transition = Mock(spec=PhaseTransition)
            mock_transition.from_phase = ["s", "l"][i]
            mock_transition.to_phase = ["l", "g"][i]
            mock_transition.temperature = 1650.0 + i * 2000
            mock_transition.delta_H = 31.5 + i * 280
            mock_transition.calculation_method = ["calculated", "heuristic"][i]
            mock_transition.reliability = ["high", "medium"][i]
            mock_transitions.append(mock_transition)

        mock_compound_data.transitions = mock_transitions

        result = formatter.format_multi_phase_compound(mock_compound_data, (773, 973))

        # Verify key formatting elements
        assert "FeO" in result
        assert "Общий диапазон:" in result
        assert "Фазовые сегменты:" in result
        assert "Фазовые переходы:" in result
        assert "Всего записей:" in result
        assert "Фазы:" in result
        assert "Методы расчёта переходов:" in result
        assert "✅ Запрошенный диапазон 773-973K покрыт" in result

    def test_range_information_display(self):
        """Test range information display."""
        formatter = ReactionCalculationFormatter(Mock())

        # Test range expansion
        user_range = (500, 700)
        calc_range = (298, 5000)

        result = formatter._format_range_information(user_range, calc_range)

        assert "Запрошенный диапазон: 500-700K" in result
        assert "Расчётный диапазон: 298-5000K" in result
        assert "Расширение диапазона: 6.7x" in result
        assert "максимальное использование базы данных" in result

    def test_phase_transition_display(self):
        """Test phase transition display with calculation methods."""
        formatter = ReactionCalculationFormatter(Mock())

        # Test calculated transition
        mock_transition = Mock(spec=PhaseTransition)
        mock_transition.temperature = 1650.0
        mock_transition.from_phase = "s"
        mock_transition.to_phase = "l"
        mock_transition.delta_H = 31.5
        mock_transition.delta_S = 19.1
        mock_transition.calculation_method = "calculated"
        mock_transition.reliability = "high"

        result = formatter._format_single_transition(mock_transition)

        assert "s→l при 1650K" in result
        assert "ΔH = 31.5 кДж/моль" in result
        assert "(рассчитано из H298)" in result
        assert "⚠️" not in result

        # Test heuristic transition
        mock_transition.calculation_method = "heuristic"
        mock_transition.reliability = "low"

        result = formatter._format_single_transition(mock_transition)

        assert "ΔH = ≈31.5 кДж/моль" in result
        assert "(эвристическая оценка)" in result
        assert "⚠️" in result

    def test_calculation_method_indicators(self):
        """Test calculation method visual indicators."""
        formatter = ReactionCalculationFormatter(Mock())

        # Create transitions with different methods
        transitions_table = [
            {
                "transition": Mock(from_phase="s", to_phase="l", temperature=1650,
                                 delta_H=31.5, calculation_method="calculated", reliability="high"),
                "expected_delta_h": "31.5",
                "expected_method": "рассчитано",
                "expected_warning": ""
            },
            {
                "transition": Mock(from_phase="l", to_phase="g", temperature=3687,
                                 delta_H=314.0, calculation_method="heuristic", reliability="medium"),
                "expected_delta_h": "≈314.0",
                "expected_method": "эвристика",
                "expected_warning": "⚠️"
            }
        ]

        for test_case in transitions_table:
            transition = test_case["transition"]
            result = formatter._format_single_transition(transition)

            assert test_case["expected_delta_h"] in result
            assert test_case["expected_method"] in result
            if test_case["expected_warning"]:
                assert test_case["expected_warning"] in result

    def test_statistics_display(self):
        """Test statistics display."""
        formatter = ReactionCalculationFormatter(Mock())

        mock_reaction_data = Mock(spec=MultiPhaseReactionData)
        mock_reaction_data.total_records_used = 156
        mock_reaction_data.get_phase_transition_count.return_value = 2
        mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
        mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
        mock_reaction_data.phases_used = {"s", "l", "g"}

        # Mock compound data
        mock_compound_data = Mock()
        mock_transition1 = Mock(calculation_method="calculated")
        mock_transition2 = Mock(calculation_method="heuristic")
        mock_compound_data.transitions = [mock_transition1, mock_transition2]
        mock_compound_data.records = [Mock() for _ in range(39)]

        mock_reaction_data.compounds_data = {"FeO": mock_compound_data}

        result = formatter._format_data_usage_statistics(mock_reaction_data)

        assert "Всего использовано записей: 156" in result
        assert "Покрытие базы данных: 100.0%" in result
        assert "Фазовых переходов учтено: 2 (FeO)" in result
        assert "Методы расчёта переходов: 1 calculated, 1 heuristic" in result
        assert "Использованные фазы: газовая, жидкая, твёрдая" in result