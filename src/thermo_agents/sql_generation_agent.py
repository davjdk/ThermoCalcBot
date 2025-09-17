"""
Инкапсулированный SQL агент для генерации запросов.

Работает независимо через систему хранилища, не вызывается напрямую.
Слушает сообщения из хранилища и отвечает через него же.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from thermo_agents.agent_storage import AgentStorage, get_storage
from thermo_agents.prompts import SQL_GENERATION_PROMPT
from thermo_agents.thermo_agents_logger import SessionLogger


class SQLQueryResult(BaseModel):
    """Результат генерации SQL запроса."""

    sql_query: str  # Сгенерированный SQL запрос
    explanation: str  # Краткое объяснение запроса
    expected_columns: list[str]  # Ожидаемые колонки в результате


@dataclass
class SQLAgentConfig:
    """Конфигурация SQL агента."""

    agent_id: str = "sql_agent"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"
    db_path: str = "data/thermo_data.db"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 1.0  # Интервал проверки новых сообщений (секунды)
    max_retries: int = 2
    auto_execute: bool = False  # Автоматически выполнять SQL запросы


class SQLGenerationAgent:
    """
    Инкапсулированный SQL агент.
    
    Работает автономно:
    - Слушает входящие сообщения из хранилища
    - Генерирует SQL запросы на основе извлеченных параметров
    - Опционально выполняет запросы к базе данных
    - Отправляет результаты обратно через хранилище
    - Не имеет прямых зависимостей от других агентов
    """

    def __init__(self, config: SQLAgentConfig):
        """
        Инициализация агента.
        
        Args:
            config: Конфигурация агента
        """
        self.config = config
        self.agent_id = config.agent_id
        self.storage = config.storage
        self.logger = config.logger
        self.running = False
        
        # Инициализация PydanticAI агента
        self.agent = self._initialize_agent()
        
        # Регистрация в хранилище
        self.storage.start_session(self.agent_id, {
            "status": "initialized",
            "capabilities": ["generate_sql", "execute_query", "explain_query"],
            "database": config.db_path
        })
        
        self.logger.info(f"SQLGenerationAgent '{self.agent_id}' initialized")

    def _initialize_agent(self) -> Agent:
        """Создание PydanticAI агента для генерации SQL."""
        provider = OpenAIProvider(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )

        model = OpenAIChatModel(self.config.llm_model, provider=provider)

        agent = Agent(
            model,
            deps_type=SQLAgentConfig,
            output_type=SQLQueryResult,
            system_prompt=SQL_GENERATION_PROMPT,
            retries=self.config.max_retries,
        )

        # Добавляем инструменты
        @agent.tool
        async def execute_query(
            ctx: RunContext[SQLAgentConfig],
            sql_query: str
        ) -> Dict[str, Any]:
            """
            Выполнить SQL запрос к базе данных.
            
            Args:
                ctx: Контекст выполнения
                sql_query: SQL запрос
                
            Returns:
                Результаты запроса
            """
            try:
                conn = sqlite3.connect(ctx.deps.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute(sql_query)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                
                # Конвертируем в списки
                data_rows = [list(row) for row in rows] if rows else []
                
                conn.close()
                
                ctx.deps.logger.info(f"Executed query, found {len(data_rows)} rows")
                
                return {
                    "success": True,
                    "columns": columns,
                    "rows": data_rows,
                    "row_count": len(data_rows)
                }
                
            except Exception as e:
                ctx.deps.logger.error(f"Query execution error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "columns": [],
                    "rows": [],
                    "row_count": 0
                }

        @agent.tool
        async def get_table_schema(
            ctx: RunContext[SQLAgentConfig],
            table_name: str = "compounds"
        ) -> Dict[str, Any]:
            """
            Получить схему таблицы.
            
            Args:
                ctx: Контекст выполнения
                table_name: Имя таблицы
                
            Returns:
                Информация о схеме таблицы
            """
            try:
                conn = sqlite3.connect(ctx.deps.db_path)
                cursor = conn.cursor()
                
                # Получаем информацию о колонках
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                # Получаем количество записей
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                
                conn.close()
                
                return {
                    "table_name": table_name,
                    "columns": [
                        {
                            "name": col[1],
                            "type": col[2],
                            "nullable": not col[3],
                            "primary_key": bool(col[5])
                        } for col in columns
                    ],
                    "row_count": count
                }
                
            except Exception as e:
                ctx.deps.logger.error(f"Schema query error: {e}")
                return {"error": str(e)}

        @agent.tool
        async def save_query_result(
            ctx: RunContext[SQLAgentConfig],
            key: str,
            result: Dict[str, Any]
        ) -> bool:
            """Сохранить результат запроса в хранилище."""
            ctx.deps.storage.set(key, result, ttl_seconds=600)
            return True

        return agent

    async def start(self):
        """
        Запустить агента в режиме прослушивания сообщений.
        
        Агент будет работать в цикле, проверяя новые сообщения
        и обрабатывая их асинхронно.
        """
        self.running = True
        self.storage.update_session(self.agent_id, {"status": "running"})
        self.logger.info(f"Agent '{self.agent_id}' started listening for messages")

        while self.running:
            try:
                # Получаем новые сообщения
                messages = self.storage.receive_messages(
                    self.agent_id,
                    message_type="generate_query"
                )

                # Обрабатываем каждое сообщение
                for message in messages:
                    await self._process_message(message)

                # Ждем перед следующей проверкой
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.logger.error(f"Error in agent loop: {e}")
                await asyncio.sleep(self.config.poll_interval * 2)

    async def stop(self):
        """Остановить агента."""
        self.running = False
        self.storage.update_session(self.agent_id, {"status": "stopped"})
        self.logger.info(f"Agent '{self.agent_id}' stopped")

    async def _process_message(self, message):
        """
        Обработать входящее сообщение.
        
        Args:
            message: Сообщение из хранилища
        """
        self.logger.info(f"Processing message: {message.id} from {message.source_agent}")

        try:
            # Извлекаем данные из сообщения
            sql_hint = message.payload.get("sql_hint")
            extracted_params = message.payload.get("extracted_params", {})
            
            if not sql_hint:
                raise ValueError("No sql_hint in message payload")

            # Генерируем SQL запрос используя PydanticAI агента
            result = await self.agent.run(sql_hint, deps=self.config)
            sql_result = result.output

            self.logger.info(f"Generated SQL query: {sql_result.sql_query[:100]}...")

            # Сохраняем результат в хранилище
            result_key = f"sql_result_{message.id}"
            result_data = {
                "sql_query": sql_result.sql_query,
                "explanation": sql_result.explanation,
                "expected_columns": sql_result.expected_columns,
                "extracted_params": extracted_params
            }

            # Если включено автоматическое выполнение, выполняем запрос
            if self.config.auto_execute:
                execution_result = await self._execute_query(sql_result.sql_query)
                result_data["execution_result"] = execution_result

            self.storage.set(result_key, result_data, ttl_seconds=600)

            # Отправляем ответное сообщение
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="response",
                correlation_id=message.id,
                payload={
                    "status": "success",
                    "result_key": result_key,
                    "sql_result": result_data
                }
            )

            # Логирование для сессии
            if self.config.session_logger:
                self.config.session_logger.log_sql_generation(
                    sql_result.sql_query,
                    sql_result.expected_columns,
                    sql_result.explanation
                )

            # Если есть оркестратор в цепочке, уведомляем его
            if message.source_agent == "thermo_agent":
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="orchestrator",
                    message_type="sql_ready",
                    correlation_id=message.correlation_id,
                    payload={
                        "result_key": result_key,
                        "sql_query": sql_result.sql_query
                    }
                )

        except Exception as e:
            self.logger.error(f"Error processing message {message.id}: {e}")

            # Отправляем сообщение об ошибке
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="error",
                correlation_id=message.id,
                payload={
                    "status": "error",
                    "error": str(e)
                }
            )

            if self.config.session_logger:
                self.config.session_logger.log_error(str(e))

    async def _execute_query(self, sql_query: str) -> Dict[str, Any]:
        """
        Выполнить SQL запрос к базе данных.
        
        Args:
            sql_query: SQL запрос
            
        Returns:
            Результаты выполнения
        """
        try:
            conn = sqlite3.connect(self.config.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(sql_query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            # Конвертируем в списки
            data_rows = [list(row) for row in rows] if rows else []
            
            conn.close()
            
            return {
                "success": True,
                "columns": columns,
                "rows": data_rows,
                "row_count": len(data_rows)
            }
            
        except Exception as e:
            self.logger.error(f"Query execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def process_single_query(self, sql_hint: str) -> SQLQueryResult:
        """
        Обработать одиночный запрос (для совместимости и тестирования).
        
        Args:
            sql_hint: Подсказка для SQL генерации
            
        Returns:
            Результат генерации SQL
        """
        try:
            result = await self.agent.run(sql_hint, deps=self.config)
            return result.output
        except Exception as e:
            self.logger.error(f"Error in single query processing: {e}")
            return SQLQueryResult(
                sql_query="SELECT * FROM compounds LIMIT 1",
                explanation="Error occurred during SQL generation",
                expected_columns=[]
            )

    def get_status(self) -> Dict:
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
            "database": self.config.db_path
        }


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================

def create_sql_agent(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str = "openai:gpt-4o",
    db_path: str = "data/thermo_data.db",
    storage: Optional[AgentStorage] = None,
    logger: Optional[logging.Logger] = None,
    auto_execute: bool = False
) -> SQLGenerationAgent:
    """
    Создать SQL агента.
    
    Args:
        llm_api_key: API ключ для LLM
        llm_base_url: URL для LLM API
        llm_model: Модель LLM
        db_path: Путь к базе данных
        storage: Хранилище (или будет использовано глобальное)
        logger: Логгер
        auto_execute: Автоматически выполнять SQL запросы
        
    Returns:
        Настроенный SQL агент
    """
    config = SQLAgentConfig(
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        db_path=db_path,
        storage=storage or get_storage(),
        logger=logger or logging.getLogger(__name__),
        auto_execute=auto_execute
    )
    
    return SQLGenerationAgent(config)


async def run_sql_agent_standalone(config: SQLAgentConfig):
    """
    Запустить агента в standalone режиме для тестирования.
    
    Args:
        config: Конфигурация агента
    """
    agent = SQLGenerationAgent(config)
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()
        print("Agent stopped")