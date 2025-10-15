"""Главный файл запуска термодинамической системы."""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.filtering.filter_stages import (
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.complex_search_stage import ComplexFormulaSearchStage
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter
from thermo_agents.orchestrator import ThermoOrchestrator, OrchestratorConfig
from thermo_agents.agent_storage import AgentStorage
from thermo_agents.thermo_agents_logger import create_session_logger

# Загрузка переменных окружения
load_dotenv()


def create_orchestrator(db_path: str = "data/thermo_data.db") -> ThermoOrchestrator:
    """
    Создание и настройка оркестратора термодинамической системы.

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        Настроенный ThermoOrchestrator
    """
    # Инициализация хранилища
    storage = AgentStorage()

    # LLM для извлечения параметров
    thermo_config = ThermoAgentConfig(
        agent_id="thermo_agent",
        llm_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("LLM_DEFAULT_MODEL", "openai/gpt-4o"),
        storage=storage,
        session_logger=create_session_logger(),
    )
    thermodynamic_agent = ThermodynamicAgent(thermo_config)

    # Поиск в БД
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(db_path)
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    # Конвейер фильтрации
    filter_pipeline = FilterPipeline()
    filter_pipeline.add_stage(ComplexFormulaSearchStage())
    filter_pipeline.add_stage(TemperatureFilterStage())
    filter_pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    filter_pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
    filter_pipeline.add_stage(TemperatureCoverageStage(TemperatureResolver()))

    # Агрегация и форматирование
    reaction_aggregator = ReactionAggregator(max_compounds=10)
    table_formatter = TableFormatter()
    statistics_formatter = StatisticsFormatter()

    # Оркестратор
    orchestrator_config = OrchestratorConfig(storage=storage)
    orchestrator = ThermoOrchestrator(
        thermodynamic_agent=thermodynamic_agent,
        compound_searcher=compound_searcher,
        filter_pipeline=filter_pipeline,
        reaction_aggregator=reaction_aggregator,
        table_formatter=table_formatter,
        statistics_formatter=statistics_formatter,
        config=orchestrator_config
    )

    return orchestrator


async def main():
    """Главная функция для демонстрации работы системы."""
    # Инициализация
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator = create_orchestrator(str(db_path))

    print("Термодинамическая система v2.0")
    print("Гибридная архитектура: LLM + детерминированная логика")
    print("=" * 60)

    # Пример запроса
    query = "Хлорирование оксида титана при 600-900K"
    print(f"Запрос: {query}\n")

    try:
        # Обработка
        response = await orchestrator.process_query(query)
        print(response)
    except Exception as e:
        print(f"Ошибка: {e}")
        print("Убедитесь, что OPENROUTER_API_KEY указан в .env файле")
    finally:
        # Завершаем работу
        await orchestrator.shutdown()


class ThermoSystem:
    """
    Расширенная система управления с интерактивным режимом.

    Provides interactive CLI interface for the thermodynamic system.
    """

    def __init__(self):
        """Инициализация системы."""
        self.orchestrator = None
        self.session_logger = create_session_logger()

    async def start(self):
        """Запуск системы в интерактивном режиме."""
        # Инициализация
        db_path = Path(__file__).parent / "data" / "thermo_data.db"
        self.orchestrator = create_orchestrator(str(db_path))

        print("\n" + "=" * 80)
        print("THERMO AGENTS v2.0 - Interactive Mode")
        print("Using hybrid architecture: LLM + deterministic modules")
        print("=" * 80)
        print("Commands:")
        print("  • Type your thermodynamic query")
        print("  • 'status' - Show system status")
        print("  • 'clear' - Clear message history")
        print("  • 'exit' - Exit the system")
        print("=" * 80 + "\n")

        await self.interactive_mode()

    async def interactive_mode(self):
        """Интерактивный режим работы."""
        while True:
            try:
                user_input = input("Query> ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    print("Shutting down...")
                    break

                elif user_input.lower() == "status":
                    print("✅ System operational")
                    print(f"📊 Database: {Path(__file__).parent / 'data' / 'thermo_data.db'}")
                    print(f"🔧 LLM Model: {os.getenv('LLM_DEFAULT_MODEL', 'openai/gpt-4o')}")

                elif user_input.lower() == "clear":
                    self.orchestrator.storage.clear()
                    print("[OK] Storage cleared")

                else:
                    # Обработка термодинамического запроса
                    await self.process_query(user_input)

                print()

            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
            except Exception as e:
                print(f"[ERROR] Error: {e}")

    async def process_query(self, query: str):
        """Обработка термодинамического запроса."""
        print(f"\nProcessing: {query}")
        print("-" * 60)

        try:
            response = await self.orchestrator.process_query(query)
            print(response)
        except Exception as e:
            print(f"\n[ERROR] {e}")

    async def shutdown(self):
        """Завершение работы системы."""
        if self.orchestrator:
            await self.orchestrator.shutdown()
        if self.session_logger:
            self.session_logger.close()


async def interactive_main():
    """Точка входа для интерактивного режима."""
    system = ThermoSystem()
    try:
        await system.start()
    finally:
        await system.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Термодинамическая система v2.0")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Запустить демо-режим с одним примером"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Запустить интерактивный режим"
    )

    args = parser.parse_args()

    try:
        if args.interactive:
            asyncio.run(interactive_main())
        else:
            # По умолчанию - демо режим
            asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutdown by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")