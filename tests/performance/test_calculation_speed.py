"""
Performance тесты для output formats v2.1.

Проверяют скорость работы калькулятора и оркестратора.
"""

import pytest
import time
import asyncio
from pathlib import Path

from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from thermo_agents.models.search import DatabaseRecord
from thermo_agents.orchestrator import Orchestrator
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.models.extraction import ExtractedReactionParameters
from thermo_agents.thermodynamic_agent import ThermoAgentConfig


def get_h2o_record():
    """Получить тестовую запись для H2O."""
    return DatabaseRecord(
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


def get_co2_record():
    """Получить тестовую запись для CO2."""
    return DatabaseRecord(
        id=2,
        formula="CO2",
        first_name="Carbon dioxide",
        phase="g",
        h298=-393.522,
        s298=213.795,
        f1=24.997,
        f2=55.187,
        f3=-33.691,
        f4=7.948,
        f5=-0.136,
        f6=-3.641,
        tmin=298.15,
        tmax=1000.0,
        tmelt=194.65,
        tboil=194.65,
        reliability_class=1
    )


@pytest.fixture
def calculator():
    """Калькулятор для тестов."""
    return ThermodynamicCalculator()


class TestPerformance:
    """Performance тесты для output formats v2.1."""

    def test_single_table_generation_speed(self, calculator):
        """Benchmark генерации таблицы для одного вещества."""
        record = get_h2o_record()

        start_time = time.time()
        result = calculator.generate_table(record, 300, 600, 100)
        duration = time.time() - start_time

        # Проверка времени < 100ms
        assert duration < 0.1, f"Генерация таблицы заняла {duration:.3f}s, ожидалось < 0.1s"
        assert len(result.properties) == 4  # (600-300)/100 + 1 = 4 точки

    def test_single_table_generation_speed_many_points(self, calculator):
        """Benchmark генерации большой таблицы."""
        record = get_h2o_record()

        start_time = time.time()
        result = calculator.generate_table(record, 300, 1300, 10)  # 101 точка
        duration = time.time() - start_time

        # Проверка времени < 200ms для 101 точки
        assert duration < 0.2, f"Генерация таблицы заняла {duration:.3f}s, ожидалось < 0.2s"
        assert len(result.properties) == 101

    def test_single_property_calculation_speed(self, calculator):
        """Benchmark расчёта свойств для одной температуры."""
        record = get_h2o_record()

        start_time = time.time()
        result = calculator.calculate_properties(record, 500.0)
        duration = time.time() - start_time

        # Проверка времени < 10ms
        assert duration < 0.01, f"Расчёт свойств занял {duration:.3f}s, ожидалось < 0.01s"
        assert result.T == 500.0

    def test_reaction_calculation_speed(self, calculator):
        """Benchmark расчёта реакции."""
        h2o = get_h2o_record()
        co2 = get_co2_record()

        # Реакция: H2O + CO2 -> H2CO3 (условная)
        start_time = time.time()
        result = calculator.calculate_reaction_properties(
            reactants=[(h2o, 1), (co2, 1)],
            products=[(h2o, 1)],  # Простая реакция для теста
            T=500.0
        )
        duration = time.time() - start_time

        # Проверка времени < 20ms
        assert duration < 0.02, f"Расчёт реакции занял {duration:.3f}s, ожидалось < 0.02s"
        assert len(result) == 3  # ΔH, ΔS, ΔG

    def test_multiple_temperature_calculations(self, calculator):
        """Benchmark расчётов для множества температур."""
        record = get_h2o_record()
        temperatures = [300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]

        start_time = time.time()
        results = []
        for T in temperatures:
            result = calculator.calculate_properties(record, T)
            results.append(result)
        duration = time.time() - start_time

        # Проверка среднего времени < 5ms на точку
        avg_time = duration / len(temperatures)
        assert avg_time < 0.005, f"Среднее время {avg_time:.3f}s, ожидалось < 0.005s"
        assert len(results) == len(temperatures)

    @pytest.mark.slow
    def test_load_100_table_generations(self, calculator):
        """Нагрузочный тест: 100 генераций таблиц."""
        record = get_h2o_record()

        start_time = time.time()
        results = []
        for i in range(100):
            result = calculator.generate_table(record, 300, 600, 50)
            results.append(result)
        duration = time.time() - start_time

        # Среднее время < 50ms на таблицу
        avg_time = duration / 100
        assert avg_time < 0.05, f"Среднее время {avg_time:.3f}s, ожидалось < 0.05s"
        assert len(results) == 100

    @pytest.mark.slow
    def test_load_1000_property_calculations(self, calculator):
        """Нагрузочный тест: 1000 расчётов свойств."""
        record = get_h2o_record()

        start_time = time.time()
        results = []
        for i in range(1000):
            T = 300.0 + (i % 50) * 10  # Температуры от 300 до 800
            result = calculator.calculate_properties(record, T)
            results.append(result)
        duration = time.time() - start_time

        # Среднее время < 2ms на расчёт
        avg_time = duration / 1000
        assert avg_time < 0.002, f"Среднее время {avg_time:.3f}s, ожидалось < 0.002s"
        assert len(results) == 1000

    def test_caching_performance(self, calculator):
        """Тест производительности кеширования."""
        record = get_h2o_record()

        # Первый расчёт (без кеша)
        start_time = time.time()
        result1 = calculator.calculate_properties(record, 500.0)
        first_duration = time.time() - start_time

        # Второй расчёт (с кешем)
        start_time = time.time()
        result2 = calculator.calculate_properties(record, 500.0)
        second_duration = time.time() - start_time

        # Кешированный расчёт должен быть быстрее
        assert second_duration < first_duration, "Кеширование не ускорило расчёт"
        assert result1.T == result2.T
        assert result1.Cp == result2.Cp

    @pytest.mark.slow
    async def test_orchestrator_query_speed(self):
        """Benchmark скорости обработки запросов оркестратором."""
        # Создание mock агента
        class MockFastAgent:
            def __init__(self, config):
                self.config = config

            async def extract_parameters(self, query: str) -> ExtractedReactionParameters:
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

        # Проверяем наличие базы данных
        test_db_path = str(Path(__file__).parent.parent.parent / "data" / "thermo_data.db")
        if not Path(test_db_path).exists():
            pytest.skip("База данных не найдена")

        # Создание оркестратора
        db_connector = DatabaseConnector(test_db_path)
        sql_builder = SQLBuilder()
        compound_searcher = CompoundSearcher(sql_builder, db_connector)
        filter_pipeline = FilterPipeline()
        agent_config = ThermoAgentConfig(llm_base_url="mock://localhost")
        thermodynamic_agent = MockFastAgent(agent_config)

        orchestrator = Orchestrator(
            thermodynamic_agent=thermodynamic_agent,
            compound_searcher=compound_searcher,
            filter_pipeline=filter_pipeline
        )

        # Тест скорости обработки запросов
        query = "Дай таблицу для H2O при 300-600K"

        start_time = time.time()
        result = await orchestrator.process_query(query)
        duration = time.time() - start_time

        # Проверка времени < 2 секунд
        assert duration < 2.0, f"Обработка запроса заняла {duration:.3f}s, ожидалось < 2.0s"
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.slow
    async def test_orchestrator_load_test(self):
        """Нагрузочный тест оркестратора."""
        # Создание mock агента
        class MockFastAgent:
            def __init__(self, config):
                self.config = config

            async def extract_parameters(self, query: str) -> ExtractedReactionParameters:
                if "H2O" in query:
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
                else:
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

        # Проверяем наличие базы данных
        test_db_path = str(Path(__file__).parent.parent.parent / "data" / "thermo_data.db")
        if not Path(test_db_path).exists():
            pytest.skip("База данных не найдена")

        # Создание оркестратора
        db_connector = DatabaseConnector(test_db_path)
        sql_builder = SQLBuilder()
        compound_searcher = CompoundSearcher(sql_builder, db_connector)
        filter_pipeline = FilterPipeline()
        agent_config = ThermoAgentConfig(llm_base_url="mock://localhost")
        thermodynamic_agent = MockFastAgent(agent_config)

        orchestrator = Orchestrator(
            thermodynamic_agent=thermodynamic_agent,
            compound_searcher=compound_searcher,
            filter_pipeline=filter_pipeline
        )

        # Тестовые запросы
        queries = [
            "Дай таблицу для H2O при 300-600K",
            "CO2 + H2 -> CO + H2O при 500-800K"
        ]

        start_time = time.time()
        results = []

        # 50 последовательных запросов
        for i in range(50):
            query = queries[i % len(queries)]
            result = await orchestrator.process_query(query)
            results.append(result)

        duration = time.time() - start_time
        avg_time = duration / 50

        # Среднее время < 1 секунды на запрос
        assert avg_time < 1.0, f"Среднее время {avg_time:.3f}s, ожидалось < 1.0s"
        assert len(results) == 50

    def test_memory_usage_large_table(self, calculator):
        """Тест использования памяти для больших таблиц."""
        import sys

        record = get_h2o_record()

        # Генерация большой таблицы
        result = calculator.generate_table(record, 200, 2000, 5)  # 361 точка

        # Проверка размера объекта
        size = sys.getsizeof(result.properties)
        assert size < 1024 * 1024, f"Таблица занимает {size} байт, ожидалось < 1MB"
        assert len(result.properties) == 361

    def test_concurrent_calculations(self, calculator):
        """Тест параллельных расчётов."""
        import concurrent.futures
        import threading

        record = get_h2o_record()
        temperatures = [300.0, 400.0, 500.0, 600.0, 700.0]

        def calculate_temp(T):
            return calculator.calculate_properties(record, T)

        # Параллельные расчёты
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(calculate_temp, T) for T in temperatures]
            results = [future.result() for future in futures]
        duration = time.time() - start_time

        # Параллельные расчёты должны быть быстрее последовательных
        assert duration < 0.1, f"Параллельные расчёты заняли {duration:.3f}s"
        assert len(results) == len(temperatures)