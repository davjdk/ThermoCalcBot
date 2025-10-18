"""
Пример использования Orchestrator для расчёта термодинамики реакции (reaction_calculation).

Демонстрирует работу новой системы маршрутизации запросов v2.1 для реакций.
"""

import asyncio
import logging
from pathlib import Path

# Добавляем путь к src для импорта
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.orchestrator import Orchestrator
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.thermodynamic_agent import ThermodynamicAgent
from thermo_agents.thermodynamic_agent import ThermoAgentConfig

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_llm_client():
    """
    Создание mock LLM клиента для демонстрации.

    В реальном приложении здесь будет подключение к OpenRouter API.
    """
    class MockLLMClient:
        async def extract_parameters(self, query: str) -> dict:
            """
            Mock извлечение параметров для демонстрации.
            """
            if "W" in query and "Cl2" in query and "O2" in query and "WOCl4" in query:
                return {
                    "query_type": "reaction_calculation",
                    "all_compounds": ["W", "Cl2", "O2", "WOCl4"],
                    "reactants": ["W", "Cl2", "O2"],
                    "products": ["WOCl4"],
                    "balanced_equation": "2 W + 4 Cl2 + O2 -> 2 WOCl4",
                    "temperature_range_k": (600.0, 900.0),
                    "temperature_step_k": 100,
                    "compound_names": {
                        "W": ["Tungsten"],
                        "Cl2": ["Chlorine"],
                        "O2": ["Oxygen"],
                        "WOCl4": ["Tungsten oxychloride"]
                    },
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            elif "H2" in query and "O2" in query and "H2O" in query:
                return {
                    "query_type": "reaction_calculation",
                    "all_compounds": ["H2", "O2", "H2O"],
                    "reactants": ["H2", "O2"],
                    "products": ["H2O"],
                    "balanced_equation": "2 H2 + O2 -> 2 H2O",
                    "temperature_range_k": (298.15, 800.0),
                    "temperature_step_k": 100,
                    "compound_names": {
                        "H2": ["Hydrogen"],
                        "O2": ["Oxygen"],
                        "H2O": ["Water"]
                    },
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            else:
                return {
                    "query_type": "reaction_calculation",
                    "all_compounds": ["Unknown1", "Unknown2"],
                    "reactants": ["Unknown1"],
                    "products": ["Unknown2"],
                    "balanced_equation": "Unknown1 -> Unknown2",
                    "temperature_range_k": (298.15, 500.0),
                    "temperature_step_k": 100,
                    "compound_names": {},
                    "extraction_confidence": 0.5,
                    "missing_fields": ["compounds_not_found"]
                }

    return MockLLMClient()


async def main():
    """
    Основная функция демонстрации работы оркестратора для реакций.
    """
    print("=== Демонстрация Orchestrator: Reaction Calculation Queries ===\n")

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

        # Создание LLM клиента и агента
        llm_client = create_llm_client()
        agent_config = ThermoAgentConfig(
            llm_base_url="mock://localhost",
            llm_default_model="mock-model",
            max_retries=1,
            timeout_seconds=30
        )
        thermodynamic_agent = ThermodynamicAgent(llm_client, agent_config)

        # Создание оркестратора
        orchestrator = Orchestrator(
            thermodynamic_agent=thermodynamic_agent,
            compound_searcher=compound_searcher,
            filter_pipeline=filter_pipeline
        )

        print("✅ Оркестратор успешно инициализирован")
        print(f"⚗️ Статус: {orchestrator.get_status()}")
        print("\n" + "="*60 + "\n")

        # Пример 1: Хлорирование вольфрама
        print("🔬 Пример 1: Хлорирование вольфрама")
        query1 = "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
        print(f"Запрос: {query1}")

        result1 = await orchestrator.process_query(query1)
        print(f"Результат:\n{result1}")
        print("\n" + "="*60 + "\n")

        # Пример 2: Образование воды
        print("🔬 Пример 2: Образование воды")
        query2 = "2 H2 + O2 -> 2 H2O при 298-800K"
        print(f"Запрос: {query2}")

        result2 = await orchestrator.process_query(query2)
        print(f"Результат:\n{result2}")
        print("\n" + "="*60 + "\n")

        # Пример 3: Реакция с несуществующими веществами
        print("🔬 Пример 3: Реакция с несуществующими веществами")
        query3 = "Unknown1 + Unknown2 -> Unknown3"
        print(f"Запрос: {query3}")

        result3 = await orchestrator.process_query(query3)
        print(f"Результат:\n{result3}")

    except Exception as e:
        logger.error(f"Ошибка в примере: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())