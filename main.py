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
from thermo_agents.orchestrator import OrchestratorConfig, OrchestratorRequest, ThermoOrchestrator
from thermo_agents.sql_generation_agent import SQLAgentConfig, SQLGenerationAgent
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent
from thermo_agents.thermo_agents_logger import create_session_logger

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
        # Настройка логирования
        self.setup_logging()
        
        # Загрузка конфигурации
        self.config = self.load_config()
        
        # Инициализация хранилища
        self.storage = get_storage()
        
        # Создание логгера сессии
        self.session_logger = create_session_logger()
        
        # Инициализация агентов
        self.thermo_agent = None
        self.sql_agent = None
        self.orchestrator = None
        
        # Задачи для агентов
        self.agent_tasks = []
        
        self.logger.info("ThermoSystem initialized")
    
    def setup_logging(self):
        """Настройка системы логирования."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self):
        """Загрузка конфигурации из переменных окружения."""
        return {
            'llm_api_key': os.getenv('OPENROUTER_API_KEY', ''),
            'llm_base_url': os.getenv('LLM_BASE_URL', ''),
            'llm_model': os.getenv('LLM_DEFAULT_MODEL', 'openai:gpt-4o'),
            'db_path': os.getenv('DB_PATH', 'data/thermo_data.db'),
            'log_level': os.getenv('LOG_LEVEL', 'INFO'),
            'debug': os.getenv('DEBUG', 'false').lower() == 'true'
        }
    
    def initialize_agents(self):
        """Инициализация всех агентов системы."""
        self.logger.info("Initializing agents...")
        
        # Термодинамический агент
        thermo_config = ThermoAgentConfig(
            agent_id="thermo_agent",
            llm_api_key=self.config['llm_api_key'],
            llm_base_url=self.config['llm_base_url'],
            llm_model=self.config['llm_model'],
            storage=self.storage,
            logger=logging.getLogger("thermo_agent"),
            session_logger=self.session_logger,
            poll_interval=0.5  # Быстрый отклик
        )
        self.thermo_agent = ThermodynamicAgent(thermo_config)
        
        # SQL агент
        sql_config = SQLAgentConfig(
            agent_id="sql_agent",
            llm_api_key=self.config['llm_api_key'],
            llm_base_url=self.config['llm_base_url'],
            llm_model=self.config['llm_model'],
            db_path=self.config['db_path'],
            storage=self.storage,
            logger=logging.getLogger("sql_agent"),
            session_logger=self.session_logger,
            poll_interval=0.5,
            auto_execute=True  # Автоматически выполнять запросы
        )
        self.sql_agent = SQLGenerationAgent(sql_config)
        
        # Оркестратор
        orchestrator_config = OrchestratorConfig(
            llm_api_key=self.config['llm_api_key'],
            llm_base_url=self.config['llm_base_url'],
            llm_model=self.config['llm_model'],
            storage=self.storage,
            logger=logging.getLogger("orchestrator"),
            session_logger=self.session_logger
        )
        self.orchestrator = ThermoOrchestrator(orchestrator_config)
        
        self.logger.info("All agents initialized successfully")
    
    async def start_agents(self):
        """Запуск всех агентов в отдельных задачах."""
        self.logger.info("Starting agents...")
        
        # Создаем задачи для каждого агента
        self.agent_tasks = [
            asyncio.create_task(
                self.thermo_agent.start(),
                name="thermo_agent_task"
            ),
            asyncio.create_task(
                self.sql_agent.start(),
                name="sql_agent_task"
            )
        ]
        
        # Даем агентам время на инициализацию
        await asyncio.sleep(1)
        
        self.logger.info("All agents started")
        self.print_system_status()
    
    async def stop_agents(self):
        """Остановка всех агентов."""
        self.logger.info("Stopping agents...")
        
        # Останавливаем агентов
        if self.thermo_agent:
            await self.thermo_agent.stop()
        if self.sql_agent:
            await self.sql_agent.stop()
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
        print("🚀 THERMO AGENTS SYSTEM v2.0 - STATUS")
        print("=" * 80)
        
        # Статус хранилища
        stats = self.storage.get_stats()
        print(f"📦 Storage: {stats['storage_entries']} entries, "
              f"{stats['message_queue_size']} messages in queue")
        
        # Статус агентов
        print(f"🤖 Active Agents: {', '.join(stats['agents'])}")
        
        # Статус компонентов
        if self.thermo_agent:
            thermo_status = self.thermo_agent.get_status()
            print(f"  • Thermo Agent: {thermo_status['session'].get('status', 'unknown')}")
        
        if self.sql_agent:
            sql_status = self.sql_agent.get_status()
            print(f"  • SQL Agent: {sql_status['session'].get('status', 'unknown')}")
        
        if self.orchestrator:
            orch_status = self.orchestrator.get_status()
            print(f"  • Orchestrator: {orch_status['orchestrator'].get('status', 'unknown')}")
        
        print("=" * 80 + "\n")
    
    async def process_user_query(self, query: str):
        """
        Обработка запроса пользователя через оркестратор.
        
        Args:
            query: Запрос пользователя
        """
        print(f"\n🔍 Processing: {query}")
        print("-" * 60)
        
        try:
            # Создаем запрос для оркестратора
            request = OrchestratorRequest(
                user_query=query,
                request_type="thermodynamic"
            )
            
            # Обрабатываем через оркестратор
            response = await self.orchestrator.process_request(request)
            
            if response.success:
                result = response.result
                
                # Вывод извлеченных параметров
                if 'extracted_parameters' in result:
                    params = result['extracted_parameters']
                    print("\n✅ Extracted Parameters:")
                    print(f"  🎯 Intent: {params.get('intent', 'unknown')}")
                    print(f"  🧪 Compounds: {params.get('compounds', [])}")
                    print(f"  🌡️ Temperature: {params.get('temperature_k', 298.15)} K")
                    print(f"  📊 Phases: {params.get('phases', [])}")
                
                # Вывод SQL запроса
                if 'sql_query' in result:
                    print("\n✅ Generated SQL:")
                    print(f"  📝 Query: {result['sql_query']}")
                    if 'explanation' in result:
                        print(f"  💡 Explanation: {result['explanation']}")
                
                # Вывод результатов выполнения
                if 'execution_result' in result:
                    exec_result = result['execution_result']
                    if exec_result.get('success'):
                        print(f"\n✅ Query Results:")
                        print(f"  📋 Found {exec_result.get('row_count', 0)} records")
                        if exec_result.get('columns'):
                            print(f"  📊 Columns: {', '.join(exec_result['columns'])}")
                    else:
                        print(f"\n❌ Query Error: {exec_result.get('error', 'Unknown error')}")
            else:
                print(f"\n❌ Processing Error: {', '.join(response.errors)}")
            
            # Trace для отладки
            if self.config['debug'] and response.trace:
                print("\n🔍 Trace:")
                for step in response.trace:
                    print(f"  • {step}")
            
        except Exception as e:
            print(f"\n❌ System Error: {e}")
            self.logger.error(f"Error processing query: {e}", exc_info=True)
    
    async def interactive_mode(self):
        """Интерактивный режим работы с системой."""
        print("\n" + "=" * 80)
        print("🤖 THERMO AGENTS v2.0 - Interactive Mode")
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
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Shutting down...")
                    break
                
                elif user_input.lower() == 'status':
                    self.print_system_status()
                
                elif user_input.lower() == 'clear':
                    self.storage.clear()
                    print("✅ Storage cleared")
                
                else:
                    # Обработка термодинамического запроса
                    await self.process_user_query(user_input)
                
                print()  # Пустая строка для читабельности
                
            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
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
            
            print("\n✅ System shutdown complete")


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
        print(f"\n❌ Fatal error: {e}")
        logging.error(f"Fatal error: {e}", exc_info=True)