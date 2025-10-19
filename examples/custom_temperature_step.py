"""
Демонстрация использования кастомного шага температуры.

Показывает различия в детализации таблиц при разных шагах.
"""

import asyncio
import logging
from pathlib import Path

# Добавляем путь к src для импорта
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.thermodynamic_agent import ThermoAgentConfig

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_mock_thermodynamic_agent():
    """Создание mock ThermodynamicAgent для демонстрации."""
    class MockThermodynamicAgent:
        def __init__(self, config):
            self.config = config

        async def extract_parameters(self, query: str):
            """Mock извлечение параметров."""
            # Извлекаем шаг температуры из запроса
            step_k = 100  # по умолчанию
            if "25" in query:
                step_k = 25
            elif "50" in query:
                step_k = 50
            elif "100" in query:
                step_k = 100
            elif "150" in query:
                step_k = 150

            if "H2O" in query and "300-400K" in query:
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["H2O"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (300.0, 400.0),
                    "temperature_step_k": step_k,
                    "compound_names": {"H2O": ["Water"]},
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            elif "CO2" in query and "400-1000K" in query:
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["CO2"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (400.0, 1000.0),
                    "temperature_step_k": step_k,
                    "compound_names": {"CO2": ["Carbon dioxide"]},
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            else:
                # По умолчанию H2O
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["H2O"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (300.0, 400.0),
                    "temperature_step_k": 100,
                    "compound_names": {"H2O": ["Water"]},
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }

    return MockThermodynamicAgent


async def main():
    """
    Основная функция демонстрации работы с кастомными шагами.
    """
    print("=== Демонстрация кастомного шага температуры ===\n")

    # Инициализация компонентов
    db_path = "data/thermo_data.db"

    try:
        # Проверяем существование базы данных
        if not Path(db_path).exists():
            print(f"❌ База данных не найдена: {db_path}")
            print("Убедитесь, что база данных существует перед запуском примера")
            return

        # Создание компонентов
        db_connector = DatabaseConnector(db_path)
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
        orchestrator = Orchestrator(
            thermodynamic_agent=thermodynamic_agent,
            compound_searcher=compound_searcher,
            filter_pipeline=filter_pipeline
        )

        print("✅ Оркестратор успешно инициализирован")
        print()

        # Пример 1: Детальная таблица (шаг 25K)
        print("🔬 Пример 1: Детальная таблица (шаг 25K)")
        query1 = "H2O при 300-400K с шагом 25 градусов"
        print(f"Запрос: {query1}")
        print("-" * 60)

        result1 = await orchestrator.process_query(query1)
        print(result1)
        print()

        # Пример 2: Средняя детализация (шаг 50K)
        print("🔬 Пример 2: Средняя детализация (шаг 50K)")
        query2 = "H2O при 300-400K каждые 50 кельвинов"
        print(f"Запрос: {query2}")
        print("-" * 60)

        result2 = await orchestrator.process_query(query2)
        print(result2)
        print()

        # Пример 3: Обзорная таблица (шаг 100K)
        print("🔬 Пример 3: Обзорная таблица (шаг 100K)")
        query3 = "Свойства H2O при 300-400K"
        print(f"Запрос: {query3}")
        print("-" * 60)

        result3 = await orchestrator.process_query(query3)
        print(result3)
        print()

        # Пример 4: Большой диапазон с разным шагом
        print("🔬 Пример 4: Большой диапазон (шаг 150K)")
        query4 = "CO2 при 400-1000K с шагом 150 градусов"
        print(f"Запрос: {query4}")
        print("-" * 60)

        result4 = await orchestrator.process_query(query4)
        print(result4)
        print()

        # Сравнительный анализ
        print("📊 Сравнительный анализ:")
        print("-" * 60)
        print("Шаг 25K:   Максимальная детализация, 5 точек данных")
        print("Шаг 50K:   Хорошая детализация, 3 точки данных")
        print("Шаг 100K:  Стандартная детализация, 2 точки данных")
        print("Шаг 150K:  Обзорная детализация, 5 точек данных на 600K диапазон")
        print()
        print("Рекомендации:")
        print("- Используйте шаг 25K для критических областей (фазовые переходы)")
        print("- Используйте шаг 50K для детального анализа")
        print("- Используйте шаг 100K для стандартных расчётов")
        print("- Используйте шаг 150-250K для обзоров больших диапазонов")

    except Exception as e:
        logger.error(f"Ошибка в примере: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())