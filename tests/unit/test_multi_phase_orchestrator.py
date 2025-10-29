"""
Unit tests for MultiPhaseOrchestrator - Stage 5 implementation.

Tests the enhanced orchestrator with full multi-phase integration.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio

from src.thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig
from src.thermo_agents.models.extraction import ExtractedReactionParameters
from src.thermo_agents.models.search import MultiPhaseCompoundData, PhaseSegment, PhaseTransition
from src.thermo_agents.models.aggregation import MultiPhaseReactionData


class TestMultiPhaseOrchestrator:
    """Test cases for MultiPhaseOrchestrator Stage 5 functionality."""

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
    def sample_params(self):
        """Create sample extracted reaction parameters."""
        return ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="FeO + H2S → FeS + H2O",
            all_compounds=["FeO", "H2S", "FeS", "H2O"],
            reactants=["FeO", "H2S"],
            products=["FeS", "H2O"],
            temperature_range_k=(773, 973),
            extraction_confidence=0.95,
            use_multi_phase=True,
            full_data_search=True,
            stoichiometry={"FeO": -1.0, "H2S": -1.0, "FeS": 1.0, "H2O": 1.0}
        )

    @pytest.mark.asyncio
    async def test_process_query_with_multi_phase(self, orchestrator, sample_params):
        """Test the enhanced process_query_with_multi_phase method."""
        # Mock the thermodynamic agent
        orchestrator.thermodynamic_agent = AsyncMock()
        orchestrator.thermodynamic_agent.extract_parameters.return_value = sample_params

        # Mock compound searcher
        mock_records = [Mock()]
        mock_search_result = Mock()
        mock_search_result.records = mock_records

        orchestrator.compound_searcher.search_compound.return_value = mock_search_result

        # Mock range determination
        orchestrator._determine_full_calculation_range = Mock(return_value=(298.0, 5000.0))

        # Mock multi-phase data building
        mock_multi_phase_data = {"FeO": Mock()}
        orchestrator._build_multi_phase_data = Mock(return_value=mock_multi_phase_data)

        # Mock reaction calculator
        mock_reaction_data = Mock()
        orchestrator.reaction_calculator.calculate_reaction_with_transitions.return_value = mock_reaction_data

        # Mock formatter
        orchestrator.reaction_formatter.format_multi_phase_reaction.return_value = "Formatted result"

        # Test the method
        result = await orchestrator.process_query_with_multi_phase("FeO + H2S reaction")

        # Assertions
        assert result == "Formatted result"
        orchestrator.thermodynamic_agent.extract_parameters.assert_called_once_with("FeO + H2S reaction")
        orchestrator.compound_searcher.search_compound.assert_called()
        orchestrator._determine_full_calculation_range.assert_called_once()
        orchestrator._build_multi_phase_data.assert_called_once()
        orchestrator.reaction_calculator.calculate_reaction_with_transitions.assert_called_once()
        orchestrator.reaction_formatter.format_multi_phase_reaction.assert_called_once()

    def test_determine_full_calculation_range(self, orchestrator):
        """Test the _determine_full_calculation_range method."""
        # Create mock records with different temperature ranges
        mock_record1 = Mock()
        mock_record1.Tmin = 298.0
        mock_record1.Tmax = 1650.0

        mock_record2 = Mock()
        mock_record2.Tmin = 1650.0
        mock_record2.Tmax = 3687.0

        mock_record3 = Mock()
        mock_record3.Tmin = 3687.0
        mock_record3.Tmax = 5000.0

        all_compounds_data = {
            "FeO": [mock_record1, mock_record2, mock_record3],
            "H2S": [mock_record1, mock_record3]
        }

        # Test the method
        result = orchestrator._determine_full_calculation_range(all_compounds_data)

        # Assertions
        assert result == (298.0, 5000.0)

    def test_determine_full_calculation_range_empty(self, orchestrator):
        """Test _determine_full_calculation_range with empty data."""
        result = orchestrator._determine_full_calculation_range({})
        assert result == (298.0, 298.0)

    def test_build_multi_phase_data(self, orchestrator):
        """Test the _build_multi_phase_data method."""
        # Create mock records
        mock_records = [Mock(), Mock()]

        # Mock the phase segment builder
        mock_multi_phase_compound = Mock(spec=MultiPhaseCompoundData)
        orchestrator.phase_segment_builder.build_compound_data.return_value = mock_multi_phase_compound

        compounds_data = {"FeO": mock_records}

        # Test the method
        result = orchestrator._build_multi_phase_data(compounds_data)

        # Assertions
        assert "FeO" in result
        assert result["FeO"] == mock_multi_phase_compound
        orchestrator.phase_segment_builder.build_compound_data.assert_called_once_with(
            compound_formula="FeO",
            records=mock_records
        )

    @pytest.mark.asyncio
    async def test_process_reaction_calculation_multi_phase(self, orchestrator, sample_params):
        """Test the enhanced _process_reaction_calculation_multi_phase method."""
        # Mock compound searcher
        mock_records = [Mock()]
        mock_records[0].Tmin = 298.0
        mock_records[0].Tmax = 5000.0

        mock_search_result = Mock()
        mock_search_result.records = mock_records

        orchestrator.compound_searcher.search_compound.return_value = mock_search_result

        # Mock supporting methods
        orchestrator._determine_full_calculation_range = Mock(return_value=(298.0, 5000.0))

        mock_multi_phase_data = {"FeO": Mock()}
        orchestrator._build_multi_phase_data = Mock(return_value=mock_multi_phase_data)

        # Mock formatter
        orchestrator.reaction_formatter.format_multi_phase_reaction.return_value = "Formatted result"

        # Test the method
        result = await orchestrator._process_reaction_calculation_multi_phase(sample_params)

        # Assertions
        assert result == "Formatted result"
        assert orchestrator.compound_searcher.search_compound.call_count == 4  # For 4 compounds

    @pytest.mark.asyncio
    async def test_process_reaction_calculation_multi_phase_missing_compound(self, orchestrator, sample_params):
        """Test _process_reaction_calculation_multi_phase with missing compound."""
        # Mock compound searcher to return None for one compound
        orchestrator.compound_searcher.search_compound.return_value = None

        # Test the method
        result = await orchestrator._process_reaction_calculation_multi_phase(sample_params)

        # Assertions
        assert "❌ Не найдено вещество" in result

    def test_get_status(self, orchestrator):
        """Test the get_status method."""
        status = orchestrator.get_status()

        assert status["orchestrator_type"] == "multi_phase"
        assert "status" in status
        assert "components" in status

    @pytest.mark.asyncio
    async def test_process_query_with_multi_phase_no_llm(self, orchestrator):
        """Test process_query_with_multi_phase when LLM is not available."""
        orchestrator.thermodynamic_agent = None

        result = await orchestrator.process_query_with_multi_phase("test query")

        assert "LLM агент недоступен" in result

    @pytest.mark.asyncio
    async def test_process_query_with_multi_phase_compound_data(self, orchestrator):
        """Test process_query_with_multi_phase for compound data queries."""
        # Mock for compound data query
        compound_params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="FeO",
            all_compounds=["FeO"],
            reactants=[],
            products=[],
            temperature_range_k=(773, 973),
            extraction_confidence=0.95
        )

        orchestrator.thermodynamic_agent = AsyncMock()
        orchestrator.thermodynamic_agent.extract_parameters.return_value = compound_params

        # Mock the compound data processing method
        orchestrator._process_compound_data_stage1 = AsyncMock(return_value="Compound data result")

        result = await orchestrator.process_query_with_multi_phase("FeO properties")

        assert result == "Compound data result"
        orchestrator._process_compound_data_stage1.assert_called_once_with(compound_params)


class TestMultiPhaseOrchestratorIntegration:
    """Integration tests for MultiPhaseOrchestrator."""

    @pytest.mark.asyncio
    async def test_feo_h2s_integration_workflow(self):
        """Test the complete FeO + H2S workflow as specified in Stage 5."""
        # This would be a comprehensive integration test
        # that tests the full workflow from query to formatted output
        # including all Stage 1-4 components integration

        # Mock all the dependencies
        with patch('src.thermo_agents.orchestrator_multi_phase.MultiPhaseOrchestratorConfig') as mock_config, \
             patch('src.thermo_agents.orchestrator_multi_phase.StaticDataManager'), \
             patch('src.thermo_agents.orchestrator_multi_phase.DatabaseConnector'), \
             patch('src.thermo_agents.orchestrator_multi_phase.CompoundSearcher'), \
             patch('src.thermo_agents.orchestrator_multi_phase.ThermodynamicCalculator'), \
             patch('src.thermo_agents.orchestrator_multi_phase.TemperatureRangeResolver'), \
             patch('src.thermo_agents.orchestrator_multi_phase.PhaseSegmentBuilder'), \
             patch('src.thermo_agents.orchestrator_multi_phase.MultiPhaseReactionCalculator'), \
             patch('src.thermo_agents.orchestrator_multi_phase.FilterPipeline'), \
             patch('src.thermo_agents.orchestrator_multi_phase.create_thermo_agent') as mock_create_agent:

            # Setup
            mock_config_instance = Mock()
            mock_config.return_value = mock_config_instance

            mock_agent = AsyncMock()
            mock_create_agent.return_value = mock_agent

            # Create orchestrator
            orchestrator = MultiPhaseOrchestrator(mock_config_instance)

            # Mock the agent response
            mock_params = ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="FeO + H2S → FeS + H2O",
                all_compounds=["FeO", "H2S", "FeS", "H2O"],
                reactants=["FeO", "H2S"],
                products=["FeS", "H2O"],
                temperature_range_k=(773, 973),
                extraction_confidence=0.95,
                use_multi_phase=True,
                full_data_search=True,
                stoichiometry={"FeO": -1.0, "H2S": -1.0, "FeS": 1.0, "H2O": 1.0}
            )

            mock_agent.extract_parameters.return_value = mock_params

            # Mock search results with full temperature range data
            mock_records = []
            for i in range(6):  # Simulate 6 records for FeO
                record = Mock()
                record.Tmin = 298.0 + i * 500
                record.Tmax = 298.0 + (i + 1) * 500
                mock_records.append(record)

            mock_search_result = Mock()
            mock_search_result.records = mock_records
            orchestrator.compound_searcher.search_compound.return_value = mock_search_result

            # Mock range determination to return full range
            orchestrator._determine_full_calculation_range = Mock(return_value=(298.0, 5000.0))

            # Mock multi-phase data building
            mock_mp_data = {}
            for compound in ["FeO", "H2S", "FeS", "H2O"]:
                mock_compound_data = Mock(spec=MultiPhaseCompoundData)
                mock_compound_data.records = mock_records[:2]  # Use 2 records per compound
                mock_compound_data.segments = [Mock(), Mock()]  # 2 segments each
                mock_compound_data.transitions = [Mock()]  # 1 transition each
                mock_mp_data[compound] = mock_compound_data

            orchestrator._build_multi_phase_data = Mock(return_value=mock_mp_data)

            # Mock reaction calculation
            mock_reaction_data = Mock(spec=MultiPhaseReactionData)
            mock_reaction_data.user_temperature_range = (773, 973)
            mock_reaction_data.calculation_range = (298, 5000)
            mock_reaction_data.compounds_data = mock_mp_data
            mock_reaction_data.phase_changes = [(1650, "FeO", "melting"), (3687, "FeO", "boiling")]
            mock_reaction_data.total_records_used = 8
            mock_reaction_data.get_phase_transition_count.return_value = 2
            mock_reaction_data.get_compounds_with_transitions.return_value = {"FeO"}
            mock_reaction_data.get_database_coverage_percentage.return_value = 100.0
            mock_reaction_data.phases_used = {"s", "l", "g"}

            orchestrator.reaction_calculator.calculate_reaction_with_transitions.return_value = mock_reaction_data

            # Mock formatter
            expected_output = "================================================================================\n⚗️ Термодинамический расчёт реакции (Полная многофазная логика)\n================================================================================"
            orchestrator.reaction_formatter.format_multi_phase_reaction.return_value = expected_output

            # Execute
            result = await orchestrator.process_query_with_multi_phase("FeO + H2S reaction")

            # Verify the complete workflow
            assert "Полная многофазная логика" in result
            mock_agent.extract_parameters.assert_called_once_with("FeO + H2S reaction")

            # Verify all compounds were searched without temperature restrictions
            assert orchestrator.compound_searcher.search_compound.call_count == 4
            for call in orchestrator.compound_searcher.search_compound.call_args_list:
                args, kwargs = call
                assert kwargs.get('temperature_range') is None  # Key Stage 5 feature
                assert kwargs.get('max_records') == 200

            # Verify range determination and data building
            orchestrator._determine_full_calculation_range.assert_called_once()
            orchestrator._build_multi_phase_data.assert_called_once()

            # Verify reaction calculation with transitions
            orchestrator.reaction_calculator.calculate_reaction_with_transitions.assert_called_once()

            # Verify Stage 5 formatting
            orchestrator.reaction_formatter.format_multi_phase_reaction.assert_called_once_with(
                mock_reaction_data, mock_params
            )