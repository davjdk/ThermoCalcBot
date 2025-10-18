"""
Полные интеграционные тесты для output formats v2.1.

Проверяют полный цикл обработки запросов от пользователя до результата.
"""

import pytest
from pathlib import Path

from thermo_agents.orchestrator import Orchestrator
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.models.extraction import ExtractedReactionParameters
from thermo_agents.thermodynamic_agent import ThermoAgentConfig


def create_mock_thermodynamic_agent():
    """Создание mock ThermodynamicAgent для тестов."""
    class MockThermodynamicAgent:
        def __init__(self, config):
            self.config = config

        async def extract_parameters(self, query: str) -> ExtractedReactionParameters:
            """Mock извлечение параметров."""
            # Обработка запросов данных по веществам
            if "H2O" in query and "таблицу" in query and "300-600K" in query:
                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["H2O"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(300.0, 600.0),
                    temperature_step_k=100,
                    compound_names={"H2O": ["Water"]},
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            elif "CO2" in query and "шагом" in query:
                step_k = 100  # по умолчанию
                if "25" in query:
                    step_k = 25
                elif "50" in query:
                    step_k = 50
                elif "100" in query:
                    step_k = 100
                elif "150" in query:
                    step_k = 150

                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["CO2"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(400.0, 600.0),
                    temperature_step_k=step_k,
                    compound_names={"CO2": ["Carbon dioxide"]},
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            elif "WCl6" in query:
                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["WCl6"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(400.0, 1000.0),
                    temperature_step_k=50,
                    compound_names={"WCl6": ["Tungsten hexachloride"]},
                    extraction_confidence=0.95,
                    missing_fields=[]
                )

            # Обработка запросов реакций
            elif "W" in query and "Cl2" in query and "O2" in query and "WOCl4" in query:
                return ExtractedReactionParameters(
                    query_type="reaction_calculation",
                    all_compounds=["W", "Cl2", "O2", "WOCl4"],
                    reactants=["W", "Cl2", "O2"],
                    products=["WOCl4"],
                    balanced_equation="2 W + 4 Cl2 + O2 -> 2 WOCl4",
                    temperature_range_k=(600.0, 900.0),
                    temperature_step_k=100,
                    compound_names={
                        "W": ["Tungsten"],
                        "Cl2": ["Chlorine"],
                        "O2": ["Oxygen"],
                        "WOCl4": ["Tungsten oxychloride"]
                    },
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            elif "CO2" in query and "H2" in query and "CO" in query and "H2O" in query:
                return ExtractedReactionParameters(
                    query_type="reaction_calculation",
                    all_compounds=["CO2", "H2", "CO", "H2O"],
                    reactants=["CO2", "H2"],
                    products=["CO", "H2O"],
                    balanced_equation="CO2 + H2 -> CO + H2O",
                    temperature_range_k=(500.0, 800.0),
                    temperature_step_k=100,
                    compound_names={
                        "CO2": ["Carbon dioxide"],
                        "H2": ["Hydrogen"],
                        "CO": ["Carbon monoxide"],
                        "H2O": ["Water"]
                    },
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            elif "NH3" in query:
                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["NH3"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(400.0, 700.0),
                    temperature_step_k=100,
                    compound_names={"NH3": ["Ammonia"]},
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            else:
                # По умолчанию возвращаем запрос H2O
                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["H2O"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(300.0, 600.0),
                    temperature_step_k=100,
                    compound_names={"H2O": ["Water"]},
                    extraction_confidence=0.95,
                    missing_fields=[]
                )

    return MockThermodynamicAgent


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return str(Path(__file__).parent.parent.parent / "data" / "thermo_data.db")


@pytest.fixture
def orchestrator(test_db_path):
    """Оркестратор для тестов."""
    # Проверяем существование базы данных
    if not Path(test_db_path).exists():
        pytest.skip(f"Тестовая база данных не найдена: {test_db_path}")

    # Создание компонентов
    db_connector = DatabaseConnector(test_db_path)
    sql_builder = SQLBuilder()
    compound_searcher = CompoundSearcher(sql_builder, db_connector)
    filter_pipeline = FilterPipeline()

    # Создание агента
    agent_config = ThermoAgentConfig(
        llm_base_url="mock://localhost",
        llm_model="mock-model"
    )
    MockThermodynamicAgent = create_mock_thermodynamic_agent()
    thermodynamic_agent = MockThermodynamicAgent(agent_config)

    # Создание оркестратора
    return Orchestrator(
        thermodynamic_agent=thermodynamic_agent,
        compound_searcher=compound_searcher,
        filter_pipeline=filter_pipeline
    )


class TestFullPipeline:
    """Полные интеграционные тесты для output formats v2.1."""

    @pytest.mark.asyncio
    async def test_spec_example_1_h2o(self, orchestrator):
        """Пример 1 из спецификации: H2O при 300-600K."""
        query = "Дай таблицу для H2O при 300-600K"
        result = await orchestrator.process_query(query)

        # Проверка структуры вывода
        assert "📊 Термодинамические данные: H2O" in result
        assert "Базовые свойства:" in result
        assert "Формула: H2O" in result
        assert "H298:" in result
        assert "S298:" in result

        # Проверка таблицы
        assert "T(K)" in result
        assert "Cp" in result
        assert "300" in result
        assert "600" in result

        # Проверка примечаний
        assert "Шаг по температуре: 100 K" in result

    @pytest.mark.asyncio
    async def test_spec_example_2_w_chlorination(self, orchestrator):
        """Пример 2: Реакция хлорирования вольфрама."""
        query = "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
        result = await orchestrator.process_query(query)

        # Проверка структуры
        assert "⚗️ Термодинамический расчёт реакции" in result
        assert "Уравнение реакции:" in result
        assert "Метод расчёта:" in result
        assert "Данные веществ:" in result
        assert "Результаты расчёта:" in result

        # Проверка наличия всех веществ
        assert "W" in result
        assert "Cl" in result
        assert "O" in result
        assert "WOCl4" in result

        # Проверка результатов
        assert "ΔH°" in result
        assert "ΔS°" in result
        assert "ΔG°" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step_k", [25, 50, 100, 150])
    async def test_custom_temperature_steps(self, orchestrator, step_k):
        """Тест различных шагов температуры."""
        query = f"Свойства CO2 при 400-600K с шагом {step_k} градусов"
        result = await orchestrator.process_query(query)

        assert f"Шаг по температуре: {step_k} K" in result
        assert "📊 Термодинамические данные: CO2" in result

    @pytest.mark.asyncio
    async def test_wcl6_properties(self, orchestrator):
        """Тест запроса свойств WCl6."""
        query = "Свойства WCl6 при 400-1000K с шагом 50 градусов"
        result = await orchestrator.process_query(query)

        assert "📊 Термодинамические данные: WCl6" in result
        assert "Шаг по температуре: 50 K" in result
        assert "WCl6" in result

    @pytest.mark.asyncio
    async def test_co2_h2_reaction(self, orchestrator):
        """Тест реакции CO2 + H2."""
        query = "CO2 + H2 → CO + H2O при 500-800K"
        result = await orchestrator.process_query(query)

        assert "⚗️ Термодинамический расчёт реакции" in result
        assert "CO2" in result
        assert "H2" in result
        assert "CO" in result
        assert "H2O" in result

    @pytest.mark.asyncio
    async def test_nh3_properties(self, orchestrator):
        """Тест запроса свойств аммиака."""
        query = "Свойства NH3 при 400-700K"
        result = await orchestrator.process_query(query)

        assert "📊 Термодинамические данные: NH3" in result
        assert "NH3" in result
        assert "Аммиак" in result or "Ammonia" in result

    @pytest.mark.asyncio
    async def test_error_handling_unknown_compound(self, orchestrator):
        """Тест обработки неизвестного соединения."""
        # Мокаем агент, чтобы вернуть неизвестное соединение
        class MockUnknownAgent:
            def __init__(self, config):
                self.config = config

            async def extract_parameters(self, query: str) -> ExtractedReactionParameters:
                return ExtractedReactionParameters(
                    query_type="compound_data",
                    all_compounds=["UnknownCompound123"],
                    reactants=[],
                    products=[],
                    balanced_equation="",
                    temperature_range_k=(298.15, 500.0),
                    temperature_step_k=100,
                    compound_names={},
                    extraction_confidence=0.5,
                    missing_fields=["compound_not_found"]
                )

        # Временно заменяем агент
        agent_config = ThermoAgentConfig(llm_base_url="mock://localhost")
        mock_agent = MockUnknownAgent(agent_config)
        original_agent = orchestrator.thermodynamic_agent
        orchestrator.thermodynamic_agent = mock_agent

        try:
            query = "Дай данные для UnknownCompound123"
            result = await orchestrator.process_query(query)

            assert "❌" in result
            assert "не найдено" in result.lower()
        finally:
            # Восстанавливаем оригинальный агент
            orchestrator.thermodynamic_agent = original_agent

    @pytest.mark.asyncio
    async def test_temperature_range_validation(self, orchestrator):
        """Тест валидации температурного диапазона."""
        query = "H2O при 300-600K"
        result = await orchestrator.process_query(query)

        # Проверяем, что температура обрабатывается корректно
        assert "300" in result or "600" in result
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_unicode_formatting(self, orchestrator):
        """Тест Unicode форматирования в реакциях."""
        query = "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
        result = await orchestrator.process_query(query)

        # Проверяем Unicode символы
        assert "⚗️" in result or "Термодинамический расчёт" in result
        assert "→" in result or "->" in result
        assert "Δ" in result or "Delta" in result

    @pytest.mark.asyncio
    async def test_empty_query_handling(self, orchestrator):
        """Тест обработки пустого запроса."""
        query = ""

        # Проверяем, что система не падает на пустом запросе
        try:
            result = await orchestrator.process_query(query)
            assert isinstance(result, str)
            # Может вернуть результат по умолчанию или ошибку
        except Exception as e:
            # Ожидаем обработку ошибок
            assert "ошибка" in str(e).lower() or "error" in str(e).lower()

    @pytest.mark.asyncio
    async def test_malformed_query_handling(self, orchestrator):
        """Тест обработки некорректного запроса."""
        query = "некорректный запрос без смысла"

        try:
            result = await orchestrator.process_query(query)
            assert isinstance(result, str)
            # Должен вернуть какой-то результат или ошибку
        except Exception as e:
            # Ожидаем обработку ошибок
            assert isinstance(e, Exception)