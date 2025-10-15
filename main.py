"""
AI Agents Project v2.0 - Главный модуль с инкапсулированными агентами

Демонстрирует правильную A2A архитектуру из PydanticAI:
- Агенты работают независимо и общаются через хранилище
- Никаких прямых вызовов между агентами
- Оркестратор координирует работу через сообщения
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

from thermo_agents.agent_storage import AgentStorage, get_storage
from thermo_agents.orchestrator import (
    OrchestratorConfig,
    OrchestratorRequest,
    ThermoOrchestrator,
)
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent
from thermo_agents.thermo_agents_logger import create_session_logger

# Новые детерминированные модули
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline
from thermo_agents.filtering.filter_stages import (
    ComplexFormulaSearchStage,
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter

# Загрузка переменных окружения
load_dotenv()


class ThermoSystem:
    """
    Главная система управления агентами v2.0.

    Координирует работу детерминированных модулей и LLM-агентов,
    обеспечивает их взаимодействие через оркестратор.
    """

    def __init__(self):
        """Инициализация системы."""
        # Инициализация хранилища
        self.storage = get_storage()

        # Создание логгера сессии
        self.session_logger = create_session_logger()

        # Настройка логирования
        self.setup_logging(self.session_logger.log_file)

        # Загрузка конфигурации
        self.config = self.load_config()

        # Инициализация компонентов
        self.thermo_agent = None
        self.compound_searcher = None
        self.filter_pipeline = None
        self.reaction_aggregator = None
        self.table_formatter = None
        self.statistics_formatter = None
        self.orchestrator = None

        # Задачи для агентов
        self.agent_tasks = []

        self.logger.info("ThermoSystem v2.0 initialized")

    def setup_logging(self, log_file_path: Path):
        """Настройка системы логирования."""
        # Настройка корневого логгера
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        # Удаление существующих обработчиков
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # Файловый обработчик для сессии
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        self.logger = logging.getLogger(__name__)

    def load_config(self):
        """Загрузка конфигурации из переменных окружения."""
        return {
            "llm_api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "llm_base_url": os.getenv("LLM_BASE_URL", ""),
            "llm_model": os.getenv("LLM_DEFAULT_MODEL", "openai:gpt-4o"),
            "db_path": os.getenv("DB_PATH", "data/thermo_data.db"),
            "log_level": os.getenv("LOG_LEVEL", "INFO"),
            "debug": os.getenv("DEBUG", "false").lower() == "true",
        }

    def initialize_agents(self):
        """Инициализация компонентов системы."""
        self.logger.info("Initializing components...")

        # Термодинамический агент (LLM)
        thermo_config = ThermoAgentConfig(
            agent_id="thermo_agent",
            llm_api_key=self.config["llm_api_key"],
            llm_base_url=self.config["llm_base_url"],
            llm_model=self.config["llm_model"],
            storage=self.storage,
            logger=logging.getLogger("thermo_agent"),
            session_logger=self.session_logger,
            poll_interval=2.0,
        )
        self.thermo_agent = ThermodynamicAgent(thermo_config)

        # Детерминированные компоненты поиска
        sql_builder = SQLBuilder()
        db_connector = DatabaseConnector(self.config["db_path"])
        self.compound_searcher = CompoundSearcher(sql_builder, db_connector)

        # Конвейер фильтрации
        self.filter_pipeline = FilterPipeline()
        self.filter_pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
        self.filter_pipeline.add_stage(TemperatureFilterStage())

        # Резолверы
        temperature_resolver = TemperatureResolver()
        phase_resolver = PhaseResolver()

        self.filter_pipeline.add_stage(PhaseSelectionStage(phase_resolver))
        self.filter_pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
        self.filter_pipeline.add_stage(TemperatureCoverageStage(temperature_resolver))

        # Компоненты агрегации и форматирования
        self.reaction_aggregator = ReactionAggregator(max_compounds=10)
        self.table_formatter = TableFormatter()
        self.statistics_formatter = StatisticsFormatter()

        # Оркестратор v2.0 с новыми компонентами
        orchestrator_config = OrchestratorConfig(
            storage=self.storage,
            logger=logging.getLogger("orchestrator_v2"),
            session_logger=self.session_logger,
            max_retries=2,
            timeout_seconds=90,
        )
        self.orchestrator = ThermoOrchestrator(
            thermodynamic_agent=self.thermo_agent,
            compound_searcher=self.compound_searcher,
            filter_pipeline=self.filter_pipeline,
            reaction_aggregator=self.reaction_aggregator,
            table_formatter=self.table_formatter,
            statistics_formatter=self.statistics_formatter,
            config=orchestrator_config
        )

        self.logger.info("All components initialized successfully")

    async def start_agents(self):
        """Запуск термодинамического агента."""
        self.logger.info("Starting components...")

        # Создаем задачу только для термодинамического агента
        if self.thermo_agent:
            self.agent_tasks = [
                asyncio.create_task(self.thermo_agent.start(), name="thermo_agent_task"),
            ]
            await asyncio.sleep(1)  # Даем время на инициализацию

        self.logger.info("Components started")
        self.print_system_status()

    async def stop_agents(self):
        """Остановка компонентов."""
        self.logger.info("Stopping components...")

        # Останавливаем термодинамический агент
        if self.thermo_agent:
            await self.thermo_agent.stop()

        # Завершаем работу оркестратора
        if self.orchestrator:
            await self.orchestrator.shutdown()

        # Отменяем задачи
        for task in self.agent_tasks:
            task.cancel()

        # Ждем завершения задач
        await asyncio.gather(*self.agent_tasks, return_exceptions=True)

        self.logger.info("Components stopped")

    def print_system_status(self):
        """Вывод статуса системы."""
        print("\n" + "=" * 80)
        print("THERMO AGENTS SYSTEM v2.0 - STATUS")
        print("=" * 80)

        # Статус хранилища
        stats = self.storage.get_stats()
        print(
            f"Storage: {stats['storage_entries']} entries, "
            f"{stats['message_queue_size']} messages in queue"
        )

        # Статус активных компонентов
        print(f"Active Components: {', '.join(stats['agents'])}")

        # Статус термодинамического агента
        if self.thermo_agent:
            thermo_status = self.thermo_agent.get_status()
            print(
                f"  • Thermo Agent: {thermo_status['session'].get('status', 'unknown')}"
            )

        # Статус оркестратора
        if self.orchestrator:
            orch_status = self.orchestrator.get_status()
            print(
                f"  • Orchestrator v2: {orch_status['orchestrator'].get('status', 'unknown')}"
            )

        # Детерминированные модули (всегда активны)
        print("  • Deterministic Modules:")
        print("    - CompoundSearcher: ready")
        print("    - FilterPipeline: ready")
        print("    - ReactionAggregator: ready")
        print("    - TableFormatter: ready")
        print("    - StatisticsFormatter: ready")

        print("=" * 80 + "\n")

    async def process_user_query(self, query: str):
        """
        Обработка запроса пользователя через новый оркестратор.

        Args:
            query: Запрос пользователя
        """
        print(f"\nProcessing: {query}")
        print("-" * 60)

        try:
            # Обрабатываем через новый оркестратор v2
            response = await self.orchestrator.process_query(query)

            # Вывод отформатированного ответа
            print(response)

        except Exception as e:
            print(f"\n[ERROR] System Error: {e}")
            self.logger.error(f"Error processing query: {e}", exc_info=True)

    async def interactive_mode(self):
        """Интерактивный режим работы с системой."""
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

        while True:
            try:
                # Получаем ввод пользователя
                user_input = input("Query> ").strip()

                if not user_input:
                    continue

                # Обработка команд
                if user_input.lower() in ["exit", "quit", "q"]:
                    print("Shutting down...")
                    break

                elif user_input.lower() == "status":
                    self.print_system_status()

                elif user_input.lower() == "clear":
                    self.storage.clear()
                    print("[OK] Storage cleared")

                else:
                    # Обработка термодинамического запроса
                    await self.process_user_query(user_input)

                print()  # Пустая строка для читабельности

            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
            except Exception as e:
                print(f"[ERROR] Error: {e}")
                self.logger.error(f"Interactive mode error: {e}", exc_info=True)

    async def run(self):
        """Главный метод запуска системы."""
        try:
            # Инициализация агентов
            self.initialize_agents()

            # Запуск агентов
            await self.start_agents()

            # Интерактивный режим
            await self.interactive_mode()

        finally:
            # Остановка агентов
            await self.stop_agents()

            # Закрытие логгера сессии
            if self.session_logger:
                self.session_logger.close()

            print("\n[OK] System shutdown complete")


async def main():
    """Точка входа в приложение."""
    system = ThermoSystem()
    await system.run()


if __name__ == "__main__":
    # Запуск асинхронного приложения
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nShutdown by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        logging.error(f"Fatal error: {e}", exc_info=True)
