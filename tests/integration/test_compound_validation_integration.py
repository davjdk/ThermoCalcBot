"""
Интеграционные тесты для валидации соединений против уравнения реакции.

Тестируют полный pipeline:
1. LLM извлечение параметров с названиями веществ
2. Поиск соединений в БД
3. Валидация через ReactionValidator (Stage 0)
4. Последующие стадии фильтрации
5. Агрегация результатов
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from pathlib import Path

from thermo_agents.orchestrator import ThermoOrchestrator, create_orchestrator
from thermo_agents.models.extraction import ExtractedReactionParameters
from thermo_agents.models.search import DatabaseRecord
from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage


class TestCompoundValidationIntegration:
    """Интеграционные тесты валидации соединений."""

    @pytest.fixture
    def mock_thermodynamic_agent(self):
        """Мок для ThermodynamicAgent с извлечением названий."""
        agent = AsyncMock()
        agent.extract_parameters.return_value = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={
                "TiF4": ["Titanium(IV) fluoride", "Titanium tetrafluoride"],
                "Mg": ["Magnesium"],
                "Ti": ["Titanium"],
                "MgF2": ["Magnesium fluoride", "Sellaite"]
            }
        )
        return agent

    @pytest.fixture
    def mock_compound_searcher(self):
        """Мок для CompoundSearcher с результатами поиска."""
        searcher = Mock()

        def mock_search_compound(compound, temperature_range):
            # Возвращаем разные результаты для разных соединений
            if compound == "TiF4":
                return Mock(
                    compound=compound,
                    records_found=[
                        DatabaseRecord(
                            Formula="TiF4(g)",
                            FirstName="Titanium tetrafluoride",
                            Phase="g",
                            Tmin=298.15,
                            Tmax=1500.0,
                            ReliabilityClass=1
                        )
                    ],
                    search_successful=True
                )
            elif compound == "Mg":
                return Mock(
                    compound=compound,
                    records_found=[
                        DatabaseRecord(
                            Formula="Mg(g)",
                            FirstName="Magnesium",
                            Phase="g",
                            Tmin=298.15,
                            Tmax=2000.0,
                            ReliabilityClass=1
                        ),
                        DatabaseRecord(
                            Formula="MgI(g)",
                            FirstName="Magnesium monoiodide",
                            Phase="g",
                            Tmin=298.15,
                            Tmax=1000.0,
                            ReliabilityClass=2
                        )
                    ],
                    search_successful=True
                )
            elif compound == "Ti":
                return Mock(
                    compound=compound,
                    records_found=[
                        DatabaseRecord(
                            Formula="Ti(s)",
                            FirstName="Titanium",
                            Phase="s",
                            Tmin=298.15,
                            Tmax=1941.0,
                            ReliabilityClass=1
                        ),
                        DatabaseRecord(
                            Formula="Ti(-g)",
                            FirstName="Titanium ion",
                            Phase="g",
                            Tmin=298.15,
                            Tmax=5000.0,
                            ReliabilityClass=3
                        )
                    ],
                    search_successful=True
                )
            elif compound == "MgF2":
                return Mock(
                    compound=compound,
                    records_found=[
                        DatabaseRecord(
                            Formula="MgF2(s)",
                            FirstName="Magnesium fluoride",
                            Phase="s",
                            Tmin=298.15,
                            Tmax=1500.0,
                            ReliabilityClass=1
                        )
                    ],
                    search_successful=True
                )
            else:
                return Mock(compound=compound, records_found=[], search_successful=False)

        searcher.search_compound = mock_search_compound
        return searcher

    @pytest.fixture
    def mock_orchestrator_components(self):
        """Создает моки для всех компонентов оркестратора."""
        from thermo_agents.filtering.filter_pipeline import FilterPipeline
        from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
        from thermo_agents.aggregation.table_formatter import TableFormatter
        from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter

        filter_pipeline = Mock(spec=FilterPipeline)
        reaction_aggregator = Mock(spec=ReactionAggregator)
        table_formatter = Mock(spec=TableFormatter)
        statistics_formatter = Mock(spec=StatisticsFormatter)

        # Настраиваем моки для возврата разумных значений
        filter_pipeline.execute.return_value = Mock(
            filtered_records=[],
            is_found=True,
            stage_statistics=[],
            failure_stage=None,
            failure_reason=None
        )

        reaction_aggregator.aggregate_reaction_data.return_value = Mock(
            reaction_equation="TiF4 + 2Mg → Ti + 2MgF2",
            found_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            missing_compounds=[],
            completeness_status="complete",
            warnings=[],
            recommendations=[],
            detailed_statistics={},
            summary_table_formatted="| Test Table |"
        )

        table_formatter.format_summary_table.return_value = "| Test Table |"
        statistics_formatter.format_detailed_statistics.return_value="📈 Statistics: All good"

        return {
            "filter_pipeline": filter_pipeline,
            "reaction_aggregator": reaction_aggregator,
            "table_formatter": table_formatter,
            "statistics_formatter": statistics_formatter
        }

    @pytest.mark.asyncio
    async def test_end_to_end_validation_with_names(
        self,
        mock_thermodynamic_agent,
        mock_compound_searcher,
        mock_orchestrator_components
    ):
        """Тест полного цикла валидации с названиями веществ."""
        from thermo_agents.orchestrator import ThermoOrchestrator, OrchestratorConfig
        from thermo_agents.agent_storage import AgentStorage

        # Создаем оркестратор с моками
        config = OrchestratorConfig(storage=AgentStorage())
        orchestrator = ThermoOrchestrator(
            thermodynamic_agent=mock_thermodynamic_agent,
            compound_searcher=mock_compound_searcher,
            filter_pipeline=mock_orchestrator_components["filter_pipeline"],
            reaction_aggregator=mock_orchestrator_components["reaction_aggregator"],
            table_formatter=mock_orchestrator_components["table_formatter"],
            statistics_formatter=mock_orchestrator_components["statistics_formatter"],
            config=config
        )

        # Выполняем запрос
        response = await orchestrator.process_query(
            "Возможно ли взаимодействие TiF4 с Mg при температуре 900-1500K?"
        )

        # Проверяем, что LLM извлек параметры с названиями
        mock_thermodynamic_agent.extract_parameters.assert_called_once_with(
            "Возможно ли взаимодействие TiF4 с Mg при температуре 900-1500K?"
        )

        # Проверяем, что поиск был выполнен для всех соединений
        assert mock_compound_searcher.search_compound.call_count == 4

        # Проверяем, что фильтрация была вызвана с правильными параметрами
        assert mock_orchestrator_components["filter_pipeline"].execute.call_count == 4

        # Проверяем, что агрегация была вызвана
        mock_orchestrator_components["reaction_aggregator"].aggregate_reaction_data.assert_called_once()

        # Проверяем финальный ответ
        assert response is not None
        assert isinstance(response, str)
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_validation_stage_filtering_mgi_problematic_case(self):
        """Тест фильтрации проблемного случая с MgI вместо Mg."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext

        # Создаем stage валидации
        validation_stage = ReactionValidationStage(min_confidence_threshold=0.7)

        # Создаем проблемные записи как в ТЗ
        records = [
            DatabaseRecord(
                Formula="MgI(g)",
                FirstName="Magnesium monoiodide",
                Phase="g",
                Tmin=298.15,
                Tmax=1000.0,
                ReliabilityClass=2
            ),
            DatabaseRecord(
                Formula="Mg(g)",
                FirstName="Magnesium",
                Phase="g",
                Tmin=298.15,
                Tmax=2000.0,
                ReliabilityClass=1
            )
        ]

        # Создаем контекст с параметрами реакции
        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={"Mg": ["Magnesium"]}
        )

        context = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="Mg",
            reaction_params=reaction_params
        )

        # Применяем валидацию
        filtered_records = validation_stage.filter(records, context)

        # Проверяем, что Mg(g) выбран вместо MgI(g)
        assert len(filtered_records) == 1
        assert filtered_records[0].Formula == "Mg(g)"
        assert filtered_records[0].FirstName == "Magnesium"

        # Проверяем статистику
        stats = validation_stage.get_statistics()
        assert stats['validation_applied'] == True
        assert stats['records_before'] == 2
        assert stats['records_after_threshold'] == 1
        assert stats['best_confidence'] > 0.9

    @pytest.mark.asyncio
    async def test_validation_stage_titanium_ion_filtering(self):
        """Тест фильтрации иона титана вместо металлического Ti."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext

        validation_stage = ReactionValidationStage(min_confidence_threshold=0.7)

        records = [
            DatabaseRecord(
                Formula="Ti(-g)",
                FirstName="Titanium ion",
                Phase="g",
                Tmin=298.15,
                Tmax=5000.0,
                ReliabilityClass=3
            ),
            DatabaseRecord(
                Formula="Ti(s)",
                FirstName="Titanium",
                Phase="s",
                Tmin=298.15,
                Tmax=1941.0,
                ReliabilityClass=1
            )
        ]

        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={"Ti": ["Titanium"]}
        )

        context = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="Ti",
            reaction_params=reaction_params
        )

        filtered_records = validation_stage.filter(records, context)

        # Проверяем, что Ti(s) выбран вместо Ti(-g)
        assert len(filtered_records) == 1
        assert filtered_records[0].Formula == "Ti(s)"
        assert filtered_records[0].FirstName == "Titanium"

    @pytest.mark.asyncio
    async def test_validation_with_missing_llm_names(self):
        """Тест валидации при отсутствии названий от LLM."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext

        validation_stage = ReactionValidationStage(min_confidence_threshold=0.5)

        records = [
            DatabaseRecord(
                Formula="MgF2(s)",
                FirstName="Magnesium fluoride",
                Phase="s",
                Tmin=298.15,
                Tmax=1500.0,
                ReliabilityClass=1
            )
        ]

        # Параметры реакции без названий
        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={}  # Пустые названия
        )

        context = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="MgF2",
            reaction_params=reaction_params
        )

        filtered_records = validation_stage.filter(records, context)

        # Должно работать на основе формулы даже без названий
        assert len(filtered_records) == 1
        assert filtered_records[0].Formula == "MgF2(s)"

        # Проверяем статистику
        stats = validation_stage.get_statistics()
        assert stats['name_validation_enabled'] == True
        assert stats['best_confidence'] == 0.7  # Только формула, 70% вес

    @pytest.mark.asyncio
    async def test_real_orchestrator_with_validation(self, tmp_path):
        """Тест реального оркестратора с валидацией."""
        # Создаем временную БД для теста
        test_db_path = tmp_path / "test_thermo.db"

        # Создаем мок для LLM
        with patch('thermo_agents.thermodynamic_agent.PydanticAI') as mock_llm:
            mock_llm_instance = AsyncMock()
            mock_llm_instance.run.return_value = ExtractedReactionParameters(
                balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
                all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
                reactants=["TiF4", "Mg"],
                products=["Ti", "MgF2"],
                temperature_range_k=(900, 1500),
                extraction_confidence=0.95,
                missing_fields=[],
                compound_names={
                    "TiF4": ["Titanium(IV) fluoride", "Titanium tetrafluoride"],
                    "Mg": ["Magnesium"],
                    "Ti": ["Titanium"],
                    "MgF2": ["Magnesium fluoride", "Sellaite"]
                }
            )
            mock_llm.return_value = mock_llm_instance

            # Мокаем поиск в БД, чтобы не требовать реальную БД
            with patch('thermo_agents.search.database_connector.DatabaseConnector') as mock_db:
                mock_connector = Mock()
                mock_connector.execute_query.return_value = []  # Пустые результаты для простоты
                mock_db.return_value = mock_connector

                try:
                    # Создаем оркестратор
                    orchestrator = create_orchestrator(str(test_db_path))

                    # Выполняем запрос
                    response = await orchestrator.process_query(
                        "Возможно ли взаимодействие TiF4 с Mg при температуре 900-1500K?"
                    )

                    # Проверяем, что ответ получен
                    assert response is not None
                    assert isinstance(response, str)

                    # Очищаем
                    await orchestrator.shutdown()

                except Exception as e:
                    # Если создание оркестратора не удалось из-за отсутствия БД,
                    # это нормально для тестового окружения
                    if "no such table" in str(e).lower() or "database" in str(e).lower():
                        pytest.skip(f"Database not available for integration test: {e}")
                    else:
                        raise

    def test_validation_confidence_thresholds(self):
        """Тест различных порогов confidence для валидации."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext

        # Создаем записи с разным confidence
        records = [
            DatabaseRecord(
                Formula="Mg(g)",
                FirstName="Magnesium",
                Phase="g",
                Tmin=298.15,
                Tmax=2000.0,
                ReliabilityClass=1
            ),
            DatabaseRecord(
                Formula="MgI(g)",
                FirstName="Magnesium monoiodide",  # Не точное название
                Phase="g",
                Tmin=298.15,
                Tmax=1000.0,
                ReliabilityClass=2
            ),
            DatabaseRecord(
                Formula="MgCl2(g)",
                FirstName="Magnesium chloride",  # Совсем другое название
                Phase="g",
                Tmin=298.15,
                Tmax=800.0,
                ReliabilityClass=3
            )
        ]

        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={"Mg": ["Magnesium"]}
        )

        context = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="Mg",
            reaction_params=reaction_params
        )

        # Тест с высоким порогом
        high_threshold_stage = ReactionValidationStage(min_confidence_threshold=0.9)
        high_filtered = high_threshold_stage.filter(records, context)
        assert len(high_filtered) <= 2  # Только записи с высоким confidence

        # Тест с низким порогом
        low_threshold_stage = ReactionValidationStage(min_confidence_threshold=0.3)
        low_filtered = low_threshold_stage.filter(records, context)
        assert len(low_filtered) >= len(high_filtered)  # Больше записей проходит

        # Тест с очень низким порогом
        very_low_threshold_stage = ReactionValidationStage(min_confidence_threshold=0.1)
        very_low_filtered = very_low_threshold_stage.filter(records, context)
        assert len(very_low_filtered) >= len(low_filtered)  # Еще больше записей

    def test_validation_error_handling(self):
        """Тест обработки ошибок в валидации."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext

        validation_stage = ReactionValidationStage()

        # Тест без параметров реакции
        context_without_reaction = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="Mg",
            reaction_params=None
        )

        records = [
            DatabaseRecord(
                Formula="Mg(g)",
                FirstName="Magnesium",
                Phase="g",
                Tmin=298.15,
                Tmax=2000.0,
                ReliabilityClass=1
            )
        ]

        # Должно вернуть записи без изменений
        filtered_records = validation_stage.filter(records, context_without_reaction)
        assert len(filtered_records) == 1
        assert filtered_records[0] == records[0]

        # Проверяем статистику
        stats = validation_stage.get_statistics()
        assert stats['validation_applied'] == False
        assert 'No reaction parameters' in stats['reason']

    def test_validation_summary_statistics(self):
        """Тест сводной статистики валидации."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage

        validation_stage = ReactionValidationStage()

        # Создаем mock результаты валидации
        from thermo_agents.filtering.reaction_validator import ValidationResult, CompoundValidationResult

        mock_results = {
            "Mg": CompoundValidationResult(
                target_formula="Mg",
                target_role="reactant",
                all_results=[
                    ValidationResult(
                        record=Mock(Formula="Mg(g)"),
                        formula_match_score=1.0,
                        name_match_score=1.0,
                        total_confidence=1.0,
                        role_match=True,
                        reasoning="Perfect match"
                    )
                ],
                best_result=Mock(total_confidence=1.0),
                validation_summary="Perfect match found"
            ),
            "TiF4": CompoundValidationResult(
                target_formula="TiF4",
                target_role="reactant",
                all_results=[],
                best_result=None,
                validation_summary="No records found"
            )
        }

        validation_stage._last_validation_results = mock_results

        summary = validation_stage.get_validation_summary()

        assert summary['validation_applied'] == True
        assert summary['total_compounds'] == 2
        assert summary['compounds_with_results'] == 1
        assert summary['compounds_without_results'] == 1
        assert summary['average_confidence'] == 0.5  # (1.0 + 0.0) / 2
        assert 'Mg' in summary['compounds_detail']
        assert 'TiF4' in summary['compounds_detail']


class TestValidationPipelinePerformance:
    """Тесты производительности валидации."""

    def test_validation_performance_large_dataset(self):
        """Тест производительности на большом наборе данных."""
        from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
        from thermo_agents.filtering.filter_pipeline import FilterContext
        import time

        validation_stage = ReactionValidationStage()

        # Создаем большой набор записей
        records = []
        for i in range(1000):
            records.append(DatabaseRecord(
                Formula=f"Mg{i:03d}(g)",
                FirstName=f"Magnesium compound {i}",
                Phase="g",
                Tmin=298.15,
                Tmax=2000.0,
                ReliabilityClass=1
            ))

        # Добавляем одну правильную запись
        records.append(DatabaseRecord(
            Formula="Mg(g)",
            FirstName="Magnesium",
            Phase="g",
            Tmin=298.15,
            Tmax=2000.0,
            ReliabilityClass=1
        ))

        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={"Mg": ["Magnesium"]}
        )

        context = FilterContext(
            temperature_range=(900, 1500),
            compound_formula="Mg",
            reaction_params=reaction_params
        )

        # Замеряем время
        start_time = time.time()
        filtered_records = validation_stage.filter(records, context)
        end_time = time.time()

        execution_time = end_time - start_time

        # Проверяем результаты
        assert len(filtered_records) == 1
        assert filtered_records[0].Formula == "Mg(g)"

        # Проверяем производительность (должно быть достаточно быстро)
        assert execution_time < 5.0, f"Validation took too long: {execution_time:.2f}s"

        # Проверяем статистику
        stats = validation_stage.get_statistics()
        assert stats['records_before'] == 1001
        assert stats['records_after_threshold'] == 1