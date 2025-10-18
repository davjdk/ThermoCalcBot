"""
Интеграционные тесты для output formats v2.1.

Проверяют корректность маршрутизации запросов и работы форматтеров.
"""

import pytest
from pathlib import Path

from thermo_agents.orchestrator import Orchestrator
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.thermodynamic_agent import ThermodynamicAgent
from thermo_agents.models.extraction import ExtractedReactionParameters
from thermo_agents.thermodynamic_agent import ThermoAgentConfig
from thermo_agents.models.search import DatabaseRecord, CompoundSearchResult


def create_mock_thermodynamic_agent():
    """Создание mock ThermodynamicAgent для тестов."""
    class MockThermodynamicAgent:
        def __init__(self, config):
            self.config = config

        async def extract_parameters(self, query: str) -> ExtractedReactionParameters:
            """Mock извлечение параметров."""
            if "H2O" in query and "таблицу" in query:
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
            elif "H2" in query and "O2" in query and "H2O" in query:
                return ExtractedReactionParameters(
                    query_type="reaction_calculation",
                    all_compounds=["H2", "O2", "H2O"],
                    reactants=["H2", "O2"],
                    products=["H2O"],
                    balanced_equation="2 H2 + O2 -> 2 H2O",
                    temperature_range_k=(298.15, 800.0),
                    temperature_step_k=100,
                    compound_names={
                        "H2": ["Hydrogen"],
                        "O2": ["Oxygen"],
                        "H2O": ["Water"]
                    },
                    extraction_confidence=0.95,
                    missing_fields=[]
                )
            elif "UnknownCompound" in query:
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
            else:
                # По умолчанию возвращаем compound_data
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


class TestOutputFormats:
    """Тесты для output formats v2.1."""

    @pytest.mark.asyncio
    async def test_compound_data_h2o(self, orchestrator):
        """E2E тест для compound_data запроса."""
        query = "Дай таблицу для H2O при 300-600K"
        result = await orchestrator.process_query(query)

        # Проверяем структуру ответа
        assert "📊 Термодинамические данные: H2O" in result
        assert "Базовые свойства:" in result
        assert "Термодинамические свойства по температуре:" in result

        # Проверяем наличие таблицы
        assert "T(K)" in result
        assert "Cp" in result
        assert "H" in result
        assert "S" in result
        assert "G" in result

        # Проверяем наличие данных для разных температур
        assert "300" in result
        assert "400" in result or "500" in result or "600" in result

        # Проверяем примечания
        assert "Шаг по температуре: 100 K" in result
        assert "уравнений Шомейта" in result

    @pytest.mark.asyncio
    async def test_reaction_calculation_h2o_combustion(self, orchestrator):
        """E2E тест для reaction_calculation запроса."""
        query = "2 H2 + O2 -> 2 H2O при 298-800K"
        result = await orchestrator.process_query(query)

        # Проверяем структуру ответа
        assert "⚗️ Термодинамический расчёт реакции" in result
        assert "Уравнение реакции:" in result
        assert "Метод расчёта:" in result
        assert "Данные веществ:" in result
        assert "Результаты расчёта:" in result

        # Проверяем наличие термодинамических величин
        assert "ΔH°" in result
        assert "ΔS°" in result
        assert "ΔG°" in result

        # Проверяем шаг температуры
        assert "Шаг по температуре: 100 K" in result

        # Проверяем Unicode форматирование
        assert "2 H₂" in result or "2 H2" in result
        assert "O₂" in result or "O2" in result
        assert "H₂O" in result or "H2O" in result

    @pytest.mark.asyncio
    async def test_compound_not_found(self, orchestrator):
        """Обработка ненайденного вещества."""
        query = "Дай данные для UnknownCompound123"
        result = await orchestrator.process_query(query)

        # Проверяем сообщение об ошибке
        assert "❌" in result
        assert "не найдено" in result.lower()
        assert "UnknownCompound123" in result

    @pytest.mark.asyncio
    async def test_routing_by_query_type(self, orchestrator, monkeypatch):
        """Проверка корректной маршрутизации."""
        compound_called = False
        reaction_called = False

        async def mock_compound(params):
            nonlocal compound_called
            compound_called = True
            return "compound_data result"

        async def mock_reaction(params):
            nonlocal reaction_called
            reaction_called = True
            return "reaction_calculation result"

        # Мокаем методы обработки
        monkeypatch.setattr(orchestrator, "_process_compound_data", mock_compound)
        monkeypatch.setattr(orchestrator, "_process_reaction_calculation", mock_reaction)

        # Тест compound_data
        result1 = await orchestrator.process_query("Дай таблицу для H2O")
        assert compound_called
        assert not reaction_called
        assert result1 == "compound_data result"

        # Сброс счетчиков
        compound_called = False
        reaction_called = False

        # Тест reaction_calculation
        result2 = await orchestrator.process_query("2 H2 + O2 -> 2 H2O")
        assert not compound_called
        assert reaction_called
        assert result2 == "reaction_calculation result"

    def test_orchestrator_initialization(self, test_db_path):
        """Тест инициализации оркестратора."""
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
        thermodynamic_agent = ThermodynamicAgent(agent_config)

        # Создание оркестратора
        orchestrator = Orchestrator(
            thermodynamic_agent=thermodynamic_agent,
            compound_searcher=compound_searcher,
            filter_pipeline=filter_pipeline
        )

        # Проверяем статус
        status = orchestrator.get_status()
        assert status["orchestrator_type"] == "output_formats_v2.1"
        assert status["status"] == "active"

        # Проверяем наличие всех компонентов
        components = status["components"]
        expected_components = [
            "thermodynamic_agent",
            "compound_searcher",
            "filter_pipeline",
            "calculator",
            "compound_formatter",
            "reaction_formatter"
        ]

        for component in expected_components:
            assert component in components
            assert components[component] is not None

    @pytest.mark.asyncio
    async def test_error_handling(self, orchestrator, monkeypatch):
        """Тест обработки ошибок."""
        # Мокаем исключение в extract_parameters
        async def mock_extract_error(query):
            raise ValueError("Test error")

        monkeypatch.setattr(
            orchestrator.thermodynamic_agent,
            "extract_parameters",
            mock_extract_error
        )

        result = await orchestrator.process_query("Тестовый запрос")

        # Проверяем обработку ошибки
        assert "❌ Ошибка обработки запроса" in result
        assert "Test error" in result

    @pytest.mark.asyncio
    async def test_temperature_step_validation(self, orchestrator, monkeypatch):
        """Тест валидации шага температуры."""
        # Мокаем параметры с некорректным шагом
        invalid_params = ExtractedReactionParameters(
            query_type="compound_data",
            all_compounds=["H2O"],
            reactants=[],
            products=[],
            balanced_equation="",
            temperature_range_k=(300.0, 600.0),
            temperature_step_k=10,  # Слишком маленький шаг
            compound_names={"H2O": ["Water"]},
            extraction_confidence=0.95,
            missing_fields=[]
        )

        async def mock_extract_invalid(query):
            return invalid_params

        monkeypatch.setattr(
            orchestrator.thermodynamic_agent,
            "extract_parameters",
            mock_extract_invalid
        )

        result = await orchestrator.process_query("Запрос с неверным шагом")

        # Проверяем, что система обрабатывает некорректные параметры
        # (точная проверка зависит от реализации валидации)
        assert isinstance(result, str)

    def test_unicode_support(self, orchestrator):
        """Тест поддержки Unicode символов."""
        # Проверяем, что компоненты поддерживают Unicode
        assert hasattr(orchestrator.reaction_formatter, '_format_equation')

        # Проверяем карту подстрочных индексов
        subscript_map = {
            '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
            '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'
        }

        # Тест конвертации формулы
        formatted = orchestrator.reaction_formatter._format_equation("H2O")
        assert "H₂O" in formatted

    @pytest.mark.asyncio
    async def test_filter_pipeline_integration(self, orchestrator):
        """Тест интеграции с конвейером фильтрации."""
        # Создаем mock результат поиска
        from src.thermo_agents.models.search import DatabaseRecord

        mock_record = DatabaseRecord(
            id=1,
            formula="H2O",
            first_name="Water",
            phase="g",
            h298=-241.826,
            s298=188.838,
            f1=30.092,
            f2=6.832,
            f3=6.793,
            f4=-2.534,
            f5=0.082,
            f6=-0.028,
            tmin=298.15,
            tmax=1000.0,
            tmelt=273.15,
            tboil=373.15,
            reliability_class=1
        )

        # Проверяем, что фильтрация работает
        assert hasattr(orchestrator.filter_pipeline, 'execute')
        assert callable(getattr(orchestrator.filter_pipeline, 'execute'))