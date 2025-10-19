"""
Пример использования Orchestrator для запроса данных по веществу (compound_data).

Демонстрирует работу новой системы маршрутизации запросов v2.1.
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
            if "H2O" in query and "таблицу" in query:
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["H2O"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (300.0, 600.0),
                    "temperature_step_k": 100,
                    "compound_names": {"H2O": ["Water"]},
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            elif "WCl6" in query:
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["WCl6"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (400.0, 1000.0),
                    "temperature_step_k": 50,
                    "compound_names": {"WCl6": ["Tungsten hexachloride"]},
                    "extraction_confidence": 0.95,
                    "missing_fields": []
                }
            else:
                return {
                    "query_type": "compound_data",
                    "all_compounds": ["UnknownCompound"],
                    "reactants": [],
                    "products": [],
                    "balanced_equation": "",
                    "temperature_range_k": (298.15, 500.0),
                    "temperature_step_k": 100,
                    "compound_names": {},
                    "extraction_confidence": 0.5,
                    "missing_fields": ["compound_not_found"]
                }

    return MockLLMClient()


async def main():
    """
    Основная функция демонстрации работы оркестратора.
    """
    print("=== Демонстрация Orchestrator: Compound Data Queries ===\n")

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
        print(f"📊 Статус: {orchestrator.get_status()}")
        print("\n" + "="*60 + "\n")

        # Пример 1: Базовый запрос
        print("🔬 Пример 1: Запрос таблицы для H2O")
        query1 = "Дай таблицу для H2O при 300-600K"
        print(f"Запрос: {query1}")

        result1 = await orchestrator.process_query(query1)
        print(f"Результат:\n{result1}")
        print("\n" + "="*60 + "\n")

        # Пример 2: Запрос с кастомным шагом
        print("🔬 Пример 2: Свойства WCl6 с шагом 50K")
        query2 = "Свойства WCl6 при 400-1000K с шагом 50 градусов"
        print(f"Запрос: {query2}")

        result2 = await orchestrator.process_query(query2)
        print(f"Результат:\n{result2}")
        print("\n" + "="*60 + "\n")

        # Пример 3: Запрос несуществующего вещества
        print("🔬 Пример 3: Запрос несуществующего вещества")
        query3 = "Дай данные для UnknownCompound123"
        print(f"Запрос: {query3}")

        result3 = await orchestrator.process_query(query3)
        print(f"Результат:\n{result3}")

    except Exception as e:
        logger.error(f"Ошибка в примере: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())