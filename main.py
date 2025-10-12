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
from thermo_agents.database_agent import DatabaseAgentConfig, DatabaseAgent
from thermo_agents.sql_generation_agent import SQLAgentConfig, SQLGenerationAgent
# Results Filtering Agent удален - функциональность перенесена в Individual Search Agent
from thermo_agents.individual_search_agent import IndividualSearchAgentConfig, IndividualSearchAgent
from thermo_agents.thermo_agents_logger import create_session_logger
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent

# Загрузка переменных окружения
load_dotenv()


class ThermoSystem:
    """
    Главная система управления агентами.

    Координирует запуск и остановку всех агентов,
    обеспечивает их взаимодействие через хранилище.
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

        # Инициализация агентов
        self.thermo_agent = None
        self.sql_agent = None
        self.database_agent = None
        # Results Filtering Agent удален - функциональность перенесена в Individual Search Agent
        self.individual_search_agent = None
        self.orchestrator = None

        # Задачи для агентов
        self.agent_tasks = []

        self.logger.info("ThermoSystem initialized")

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
        """Инициализация всех агентов системы."""
        self.logger.info("Initializing agents...")

        # Термодинамический агент
        thermo_config = ThermoAgentConfig(
            agent_id="thermo_agent",
            llm_api_key=self.config["llm_api_key"],
            llm_base_url=self.config["llm_base_url"],
            llm_model=self.config["llm_model"],
            storage=self.storage,
            logger=logging.getLogger("thermo_agent"),
            session_logger=self.session_logger,
            poll_interval=2.0,  # Увеличенный интервал для учета времени LLM
        )
        self.thermo_agent = ThermodynamicAgent(thermo_config)

        # SQL агент
        sql_config = SQLAgentConfig(
            agent_id="sql_agent",
            llm_api_key=self.config["llm_api_key"],
            llm_base_url=self.config["llm_base_url"],
            llm_model=self.config["llm_model"],
            db_path=self.config["db_path"],
            storage=self.storage,
            logger=logging.getLogger("sql_agent"),
            session_logger=self.session_logger,
            poll_interval=2.0,  # Увеличенный интервал
        )
        self.sql_agent = SQLGenerationAgent(sql_config)

        # Агент базы данных
        database_config = DatabaseAgentConfig(
            agent_id="database_agent",
            db_path=self.config["db_path"],
            storage=self.storage,
            logger=logging.getLogger("database_agent"),
            session_logger=self.session_logger,
            poll_interval=2.0,  # Увеличенный интервал
        )
        self.database_agent = DatabaseAgent(database_config)

        # Results Filtering Agent удален - функциональность перенесена в Individual Search Agent
        # Интеллектуальный фильтр фаз теперь встроен в Individual Search Agent

        # Individual Search Agent (оптимизированная конфигурация v2.0)
        individual_search_config = IndividualSearchAgentConfig(
            agent_id="individual_search_agent",
            storage=self.storage,
            logger=logging.getLogger("individual_search_agent"),
            session_logger=self.session_logger,
            poll_interval=0.05,  # Оптимизировано до 0.05с для немедленной обработки
            max_retries=2,  # Обновлено до 2 попыток согласно новой политике
            timeout_seconds=54,  # Оптимизировано на основе анализа: 27с × 2 = 54с
            max_parallel_searches=4,  # Оптимизировано для баланса производительности
        )
        self.individual_search_agent = IndividualSearchAgent(individual_search_config)

        # Оркестратор (оптимизированная конфигурация v2.0)
        orchestrator_config = OrchestratorConfig(
            llm_api_key=self.config["llm_api_key"],
            llm_base_url=self.config["llm_base_url"],
            llm_model=self.config["llm_model"],
            storage=self.storage,
            logger=logging.getLogger("orchestrator"),
            session_logger=self.session_logger,
            max_retries=2,  # Обновлено до 2 попыток согласно новой политике
            timeout_seconds=60,  # Оптимизировано на основе анализа: общий таймаут 60с
        )
        self.orchestrator = ThermoOrchestrator(orchestrator_config)

        self.logger.info("All agents initialized successfully")

    async def start_agents(self):
        """Запуск всех агентов в отдельных задачах."""
        self.logger.info("Starting agents...")

        # Создаем задачи для каждого агента (Results Filtering Agent удален)
        self.agent_tasks = [
            asyncio.create_task(self.thermo_agent.start(), name="thermo_agent_task"),
            asyncio.create_task(self.sql_agent.start(), name="sql_agent_task"),
            asyncio.create_task(self.database_agent.start(), name="database_agent_task"),
            asyncio.create_task(self.individual_search_agent.start(), name="individual_search_agent_task"),
        ]

        # Даем агентам время на инициализацию
        await asyncio.sleep(1)

        self.logger.info("All agents started")
        self.print_system_status()

    async def stop_agents(self):
        """Остановка всех агентов."""
        self.logger.info("Stopping agents...")

        # Останавливаем агентов (Results Filtering Agent удален)
        if self.thermo_agent:
            await self.thermo_agent.stop()
        if self.sql_agent:
            await self.sql_agent.stop()
        if self.database_agent:
            await self.database_agent.stop()
        # Results Filtering Agent был удален - функциональность перенесена в Individual Search Agent
        if self.individual_search_agent:
            await self.individual_search_agent.stop()
        if self.orchestrator:
            await self.orchestrator.shutdown()

        # Отменяем задачи
        for task in self.agent_tasks:
            task.cancel()

        # Ждем завершения задач
        await asyncio.gather(*self.agent_tasks, return_exceptions=True)

        self.logger.info("All agents stopped")

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

        # Статус агентов
        print(f"Active Agents: {', '.join(stats['agents'])}")

        # Статус компонентов
        if self.thermo_agent:
            thermo_status = self.thermo_agent.get_status()
            print(
                f"  • Thermo Agent: {thermo_status['session'].get('status', 'unknown')}"
            )

        if self.sql_agent:
            sql_status = self.sql_agent.get_status()
            print(f"  • SQL Agent: {sql_status['session'].get('status', 'unknown')}")

        if self.orchestrator:
            orch_status = self.orchestrator.get_status()
            print(
                f"  • Orchestrator: {orch_status['orchestrator'].get('status', 'unknown')}"
            )

        print("=" * 80 + "\n")

    async def process_user_query(self, query: str):
        """
        Обработка запроса пользователя через оркестратор.

        Args:
            query: Запрос пользователя
        """
        print(f"\nProcessing: {query}")
        print("-" * 60)

        try:
            # Создаем запрос для оркестратора
            request = OrchestratorRequest(
                user_query=query, request_type="thermodynamic"
            )

            # Обрабатываем через оркестратор
            response = await self.orchestrator.process_request(request)

            if response.success:
                result = response.result

                # Проверяем статус полноты данных для реакций
                is_complete_reaction = result.get("is_complete_reaction", True)
                processing_type = result.get("processing_type", "")
                missing_compounds = result.get("missing_compounds", [])

                # Вывод сообщения для неполных данных реакции
                if not is_complete_reaction and processing_type == "individual_search" and "user_message" in result:
                    print("\n" + "="*80)
                    print(result["user_message"])
                    print("="*80)

                # Вывод извлеченных параметров
                if "extracted_parameters" in result:
                    params = result["extracted_parameters"]
                    print("\n[OK] Extracted Parameters:")
                    print(f"  [Intent] {params.get('intent', 'unknown')}")
                    print(f"  [Compounds] {params.get('compounds', [])}")
                    print(f"  [Temperature] {params.get('temperature_k', 298.15)} K")
                    print(f"  [Phases] {params.get('phases', [])}")

                # Вывод результатов индивидуального поиска (для реакций)
                if processing_type == "individual_search" and "individual_results" in result:
                    individual_results = result["individual_results"]

                    print(f"\n[Individual Search Results]:")
                    print(f"  [Processed] {len(individual_results)} compounds")
                    print(f"  [Success] {result.get('overall_confidence', 0):.2f} confidence")

                    if missing_compounds:
                        print(f"  [WARNING] Missing data for: {', '.join(missing_compounds)}")

                    # Показываем таблицы для каждого соединения
                    for compound_result in individual_results:
                        compound_name = compound_result.get("compound", "Unknown")
                        selected_records = compound_result.get("selected_records", [])
                        confidence = compound_result.get("confidence", 0)
                        errors = compound_result.get("errors", [])

                        print(f"\n[Results for {compound_name}]:")
                        print(f"  [Confidence] {confidence:.2f}")
                        print(f"  [Records found] {len(selected_records)}")

                        if errors:
                            print(f"  [ERRORS] {', '.join(errors)}")

                        # Показываем таблицу данных
                        if selected_records:
                            print("\n" + "-"*80)

                            # Определяем ключевые колонки для отображения
                            key_columns = ["Formula", "FirstName", "Phase", "H298", "S298", "Tmin", "Tmax", "MeltingPoint", "BoilingPoint"]
                            available_columns = []

                            # Используем первую запись для определения доступных колонок
                            first_record = selected_records[0] if selected_records else {}
                            for col in key_columns:
                                if col in first_record:
                                    available_columns.append(col)

                            # Заголовок таблицы
                            header = " | ".join(f"{col:>12}" for col in available_columns)
                            print(header)
                            print("-" * len(header))

                            # Строки данных
                            for record in selected_records[:5]:  # Показываем первые 5 записей для экономии места
                                row_values = []
                                for col in available_columns:
                                    value = record.get(col, "N/A")
                                    if isinstance(value, (int, float)):
                                        if isinstance(value, float):
                                            row_values.append(f"{value:>12.2f}")
                                        else:
                                            row_values.append(f"{value:>12}")
                                    else:
                                        # Обрабатываем None и пустые значения
                                        if value is None or value == "":
                                            value = "N/A"
                                        row_values.append(f"{str(value)[:12]:>12}")
                                print(" | ".join(row_values))

                            if len(selected_records) > 5:
                                print(f"... and {len(selected_records) - 5} more records")

                            print("-"*80)
                        else:
                            print("  [No thermodynamic data found]")

                # Вывод SQL запроса (для стандартных запросов)
                if "sql_query" in result:
                    print("\n[OK] Generated SQL:")
                    print(f"  [Query] {result['sql_query']}")
                    if "explanation" in result:
                        print(f"  [Explanation] {result['explanation']}")

                # Вывод результатов выполнения (для стандартных запросов)
                if "execution_result" in result:
                    exec_result = result["execution_result"]
                    if exec_result.get("success"):
                        print("\n[OK] Raw Query Results:")
                        print(f"  [Found] {exec_result.get('row_count', 0)} total records")
                        if exec_result.get("columns"):
                            print(f"  [Columns] {', '.join(exec_result['columns'])}")
                    else:
                        print(
                            f"\n[ERROR] Query Error: {exec_result.get('error', 'Unknown error')}"
                        )

                # Вывод предупреждений
                if "warnings" in result and result["warnings"]:
                    print(f"\n[WARNINGS]:")
                    for warning in result["warnings"]:
                        print(f"  - {warning}")

                # Вывод отфильтрованных результатов (для старых запросов)
                if "filtered_result" in result:
                    filtered = result["filtered_result"]
                    selected_records = filtered.get("selected_records", [])

                    print(f"\n[Filtered Results (LLM Selected)]:")
                    print(f"  [Selected] {len(selected_records)} most relevant records")

                    if filtered.get("reasoning"):
                        print(f"  [Reasoning] {filtered['reasoning']}")

                    # Показываем таблицу отфильтрованных результатов
                    if selected_records:
                        print("\n[Selected Thermodynamic Data]:")
                        print("-" * 100)

                        # Определяем ключевые колонки для отображения
                        key_columns = ["Formula", "FirstName", "Phase", "H298", "S298", "Tmin", "Tmax"]
                        available_columns = []

                        for col in key_columns:
                            if col in selected_records[0]:
                                available_columns.append(col)

                        # Заголовок таблицы
                        header = " | ".join(f"{col:>12}" for col in available_columns)
                        print(header)
                        print("-" * len(header))

                        # Строки данных
                        for record in selected_records[:10]:  # Показываем первые 10 записей
                            row_values = []
                            for col in available_columns:
                                value = record.get(col, "N/A")
                                if isinstance(value, (int, float)):
                                    row_values.append(f"{value:>12.2f}" if isinstance(value, float) else f"{value:>12}")
                                else:
                                    row_values.append(f"{str(value)[:12]:>12}")
                            print(" | ".join(row_values))

                        if len(selected_records) > 10:
                            print(f"... and {len(selected_records) - 10} more records")

                        print("-" * 100)
            else:
                print(f"\n[ERROR] Processing Error: {', '.join(response.errors)}")

            # Trace для отладки
            if self.config["debug"] and response.trace:
                print("\n[Trace]:")
                for step in response.trace:
                    print(f"  - {step}")

        except Exception as e:
            print(f"\n[ERROR] System Error: {e}")
            self.logger.error(f"Error processing query: {e}", exc_info=True)

    async def interactive_mode(self):
        """Интерактивный режим работы с системой."""
        print("\n" + "=" * 80)
        print("THERMO AGENTS v2.0 - Interactive Mode")
        print("Using fully encapsulated Agent-to-Agent architecture")
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
