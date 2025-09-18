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
from typing import Any, Dict, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .agent_storage import AgentStorage, get_storage
from .prompts import SQL_GENERATION_PROMPT
from .thermo_agents_logger import SessionLogger


class SQLQueryResult(BaseModel):
    """Результат генерации SQL запроса."""

    sql_query: str  # Сгенерированный SQL запрос
    explanation: str  # Краткое объяснение запроса
    expected_columns: list[str]  # Ожидаемые колонки в результате


# SQLValidationResult class removed - validation no longer needed


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
        self.storage.start_session(
            self.agent_id,
            {
                "status": "initialized",
                "capabilities": ["generate_sql", "execute_query", "explain_query"],
                "database": config.db_path,
            },
        )

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

        # NO TOOLS - Agent should only generate SQL queries without database access

        return agent

    @staticmethod
    def _clean_sql_query_static(sql_query: str) -> str:
        """
        Очистка SQL запроса от HTML entities и разделение на отдельные statements.

        Args:
            sql_query: Исходный SQL запрос

        Returns:
            Очищенный SQL запрос (только первый statement)
        """
        import html
        import re

        # Декодируем HTML entities
        cleaned = html.unescape(sql_query)

        # Удаляем лишние пробелы и переносы строк
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Разделяем на statements по точке с запятой
        statements = [stmt.strip() for stmt in cleaned.split(';') if stmt.strip()]

        # Возвращаем только первый statement
        if statements:
            first_statement = statements[0]
            # Убеждаемся, что нет HTML entities в операторах сравнения
            first_statement = first_statement.replace('&lt;=', '<=').replace('&gt;=', '>=')
            first_statement = first_statement.replace('&lt;', '<').replace('&gt;', '>')
            first_statement = first_statement.replace('&amp;', '&')
            return first_statement

        return cleaned

    def _clean_sql_query(self, sql_query: str) -> str:
        """Wrapper для статического метода очистки SQL запросов."""
        return self._clean_sql_query_static(sql_query)

    # Validation and refinement agent methods removed - no longer needed

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
                    self.agent_id, message_type="generate_query"
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
        self.logger.info(
            f"Processing message: {message.id} from {message.source_agent}"
        )

        try:
            # Извлекаем данные из сообщения
            sql_hint = message.payload.get("sql_hint")
            extracted_params = message.payload.get("extracted_params", {})

            self.logger.info(f"Processing SQL hint: {sql_hint[:100] if sql_hint else 'None'}...")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL GENERATION START: Processing message {message.id}")

            if not sql_hint:
                raise ValueError("No sql_hint in message payload")

            # Генерируем SQL запрос используя PydanticAI агента с тайм-аутом
            self.logger.info("Starting SQL query generation...")
            result = await asyncio.wait_for(
                self.agent.run(sql_hint, deps=self.config),
                timeout=60.0  # 60 секунд тайм-аут для генерации
            )
            sql_result = result.output

            self.logger.info(f"Generated SQL query: {sql_result.sql_query}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL GENERATION COMPLETE: Query length {len(sql_result.sql_query)}")

            # Дополнительная очистка запроса перед выполнением
            sql_result.sql_query = self._clean_sql_query(sql_result.sql_query)
            self.logger.info("SQL query cleaned")

            # Сохраняем результат в хранилище
            result_key = f"sql_result_{message.id}"
            result_data = {
                "sql_query": sql_result.sql_query,
                "explanation": sql_result.explanation,
                "expected_columns": sql_result.expected_columns,
                "extracted_params": extracted_params,
            }

            self.logger.info(f"Prepared result data with key: {result_key}")

            # Отправляем SQL запрос агенту базы данных для выполнения
            self.logger.info("Sending SQL query to database agent for execution...")
            db_message_id = self.storage.send_message(
                source_agent=self.agent_id,
                target_agent="database_agent",
                message_type="execute_sql",
                payload={
                    "sql_query": sql_result.sql_query,
                    "extracted_params": extracted_params,
                },
            )
            self.logger.info(f"SQL query sent to database_agent: {db_message_id}")

            # Ждем результат от агента базы данных
            db_result = None
            db_start_time = asyncio.get_event_loop().time()
            timeout = 30  # 30 секунд на выполнение SQL

            while (asyncio.get_event_loop().time() - db_start_time) < timeout:
                # Получаем сообщения от агента базы данных
                db_messages = self.storage.receive_messages(
                    self.agent_id, message_type="sql_executed"
                )

                for db_msg in db_messages:
                    if db_msg.correlation_id == db_message_id and db_msg.source_agent == "database_agent":
                        self.logger.info(f"Received database result: {db_msg.payload.get('status')}")
                        if db_msg.payload.get("status") == "success":
                            db_result = db_msg.payload.get("execution_result")
                            break

                if db_result:
                    break
                await asyncio.sleep(0.1)

            # Добавляем результат выполнения к данным
            if db_result:
                result_data["execution_result"] = db_result
                self.logger.info(f"Database execution successful: {db_result.get('row_count', 0)} rows")

                # Ждем результат фильтрации от агента фильтрации результатов
                if db_result.get("success") and db_result.get("row_count", 0) > 0:
                    self.logger.info("Waiting for filtering agent results...")
                    filtering_result = None
                    filtering_start_time = asyncio.get_event_loop().time()
                    filtering_timeout = 30  # 30 секунд на фильтрацию

                    while (asyncio.get_event_loop().time() - filtering_start_time) < filtering_timeout:
                        # Получаем сообщения от агента фильтрации
                        filtering_messages = self.storage.receive_messages(
                            self.agent_id, message_type="results_filtered"
                        )

                        for filter_msg in filtering_messages:
                            # Проверяем correlation_id (должен соответствовать исходному message ID)
                            if (filter_msg.source_agent == "results_filtering_agent" and
                                filter_msg.correlation_id == message.id):
                                self.logger.info(f"Received filtering result: {filter_msg.payload.get('status')}")
                                if filter_msg.payload.get("status") == "success":
                                    filtering_result = filter_msg.payload.get("filtered_result")
                                    break
                                elif filter_msg.payload.get("status") == "no_results":
                                    self.logger.warning("No records found after filtering")
                                    break

                        if filtering_result:
                            break
                        await asyncio.sleep(0.1)

                    # Добавляем результат фильтрации к данным
                    if filtering_result:
                        result_data["filtered_result"] = filtering_result
                        self.logger.info(f"Filtering successful: {len(filtering_result.get('selected_records', []))} relevant records")
                    else:
                        self.logger.warning("Filtering agent did not respond in time, using raw database results")
            else:
                self.logger.warning("Database agent did not respond in time")
                result_data["execution_result"] = {
                    "success": False,
                    "error": "Database agent timeout",
                    "rows": [],
                    "row_count": 0,
                }

            self.logger.info(f"Storing result with key: {result_key}")
            self.storage.set(result_key, result_data, ttl_seconds=600)
            self.logger.info("Result stored successfully")

            # Отправляем ответное сообщение
            self.logger.info(f"Sending response to {message.source_agent}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SENDING RESPONSE: To {message.source_agent}, key={result_key}")

            try:
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent=message.source_agent,
                    message_type="response",
                    correlation_id=message.id,
                    payload={
                        "status": "success",
                        "result_key": result_key,
                        "sql_result": result_data,
                    },
                )
                self.logger.info(f"Response sent successfully to {message.source_agent}")
            except Exception as e:
                self.logger.error(f"Error sending response: {e}")

            # Логирование для сессии
            if self.config.session_logger:
                self.config.session_logger.log_sql_generation(
                    sql_result.sql_query,
                    sql_result.expected_columns,
                    sql_result.explanation,
                )

            # Если есть оркестратор в цепочке, уведомляем его
            if message.source_agent == "thermo_agent":
                self.logger.info("Sending notification to orchestrator")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"NOTIFYING ORCHESTRATOR: correlation_id={message.correlation_id}")

                try:
                    self.storage.send_message(
                        source_agent=self.agent_id,
                        target_agent="orchestrator",
                        message_type="sql_ready",
                        correlation_id=message.correlation_id,
                        payload={
                            "result_key": result_key,
                            "sql_query": sql_result.sql_query,
                        },
                    )
                    self.logger.info("Orchestrator notification sent successfully")
                except Exception as e:
                    self.logger.error(f"Error sending orchestrator notification: {e}")

            self.logger.info("Message processing completed successfully")

        except Exception as e:
            self.logger.error(f"Error processing message {message.id}: {e}")
            if self.config.session_logger:
                self.config.session_logger.log_error(f"SQL AGENT ERROR: {str(e)}")

            # Отправляем сообщение об ошибке
            self.logger.info(f"Sending error response to {message.source_agent}")
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="error",
                correlation_id=message.id,
                payload={"status": "error", "error": str(e)},
            )

            # Уведомляем оркестратор об ошибке, если нужно
            if message.source_agent == "thermo_agent":
                self.logger.info("Sending error notification to orchestrator")
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="orchestrator",
                    message_type="sql_error",
                    correlation_id=message.correlation_id,
                    payload={"status": "error", "error": str(e)},
                )

            if self.config.session_logger:
                self.config.session_logger.log_error(str(e))

    # SQL execution and filtering methods removed - agent only generates queries

    # SQL validation and refinement methods removed - no longer needed

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
                expected_columns=[],
            )

    def get_status(self) -> Dict:
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
            "database": self.config.db_path,
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
