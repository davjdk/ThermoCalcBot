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

        # Добавляем инструменты
        @agent.tool
        async def execute_query(
            ctx: RunContext[SQLAgentConfig], sql_query: str
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

                # Очистка SQL запроса от HTML entities и множественных statements
                cleaned_query = SQLGenerationAgent._clean_sql_query_static(sql_query)

                cursor.execute(cleaned_query)
                columns = (
                    [desc[0] for desc in cursor.description]
                    if cursor.description
                    else []
                )
                rows = cursor.fetchall()

                # Конвертируем в списки
                data_rows = [list(row) for row in rows] if rows else []

                conn.close()

                # Логируем результаты в виде таблицы через session_logger
                if ctx.deps.session_logger:
                    ctx.deps.session_logger.log_query_results_table(
                        sql_query=sql_query, columns=columns, rows=data_rows
                    )
                else:
                    ctx.deps.logger.info(f"Executed query, found {len(data_rows)} rows")

                return {
                    "success": True,
                    "columns": columns,
                    "rows": data_rows,
                    "row_count": len(data_rows),
                }

            except Exception as e:
                ctx.deps.logger.error(f"Query execution error: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "columns": [],
                    "rows": [],
                    "row_count": 0,
                }

        @agent.tool
        async def get_table_schema(
            ctx: RunContext[SQLAgentConfig], table_name: str = "compounds"
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
                            "primary_key": bool(col[5]),
                        }
                        for col in columns
                    ],
                    "row_count": count,
                }

            except Exception as e:
                ctx.deps.logger.error(f"Schema query error: {e}")
                return {"error": str(e)}

        @agent.tool
        async def save_query_result(
            ctx: RunContext[SQLAgentConfig], key: str, result: Dict[str, Any]
        ) -> bool:
            """Сохранить результат запроса в хранилище."""
            ctx.deps.storage.set(key, result, ttl_seconds=600)
            return True

        @agent.tool
        async def filter_by_temperature_range(
            ctx: RunContext[SQLAgentConfig],
            query_results: Dict[str, Any],
            target_temperature_k: float
        ) -> Dict[str, Any]:
            """
            Автоматическая постфильтрация результатов по температурному диапазону.

            Args:
                ctx: Контекст выполнения
                query_results: Результаты SQL запроса
                target_temperature_k: Целевая температура в Кельвинах

            Returns:
                Отфильтрованные результаты
            """
            if not query_results.get("success", False):
                return query_results

            columns = query_results.get("columns", [])
            rows = query_results.get("rows", [])

            # Найдем индексы колонок Tmin и Tmax
            tmin_idx = None
            tmax_idx = None

            for i, col in enumerate(columns):
                if col.lower() == 'tmin':
                    tmin_idx = i
                elif col.lower() == 'tmax':
                    tmax_idx = i

            if tmin_idx is None or tmax_idx is None:
                ctx.deps.logger.warning("Temperature range columns (Tmin/Tmax) not found, skipping temperature filtering")
                return query_results

            # Фильтруем строки по температурному диапазону
            filtered_rows = []
            excluded_count = 0

            for row in rows:
                try:
                    tmin = float(row[tmin_idx]) if row[tmin_idx] is not None else 0
                    tmax = float(row[tmax_idx]) if row[tmax_idx] is not None else 9999

                    # Проверяем, входит ли целевая температура в диапазон
                    if tmin <= target_temperature_k <= tmax:
                        filtered_rows.append(row)
                    else:
                        excluded_count += 1

                except (ValueError, TypeError, IndexError):
                    # Если не удается конвертировать температуры, оставляем строку
                    filtered_rows.append(row)

            # Логируем результаты фильтрации
            ctx.deps.logger.info(f"Temperature filtering at {target_temperature_k}K: {len(filtered_rows)} records match, {excluded_count} excluded")

            if ctx.deps.session_logger:
                ctx.deps.session_logger.log_info(
                    f"TEMPERATURE FILTER: Target={target_temperature_k}K, "
                    f"Matched={len(filtered_rows)}, Excluded={excluded_count}"
                )

            return {
                "success": True,
                "columns": columns,
                "rows": filtered_rows,
                "row_count": len(filtered_rows),
                "temperature_filter_applied": True,
                "target_temperature_k": target_temperature_k,
                "excluded_by_temperature": excluded_count
            }

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

            self.logger.info(f"Generated SQL query: {sql_result.sql_query[:100]}...")
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

            # Если включено автоматическое выполнение, выполняем запрос
            if self.config.auto_execute:
                self.logger.info("Starting SQL execution...")
                execution_result = await self._execute_query(sql_result.sql_query)

                # Дополнительная проверка на ошибки выполнения
                if not execution_result.get("success", False):
                    self.logger.error(f"SQL execution failed: {execution_result.get('error', 'Unknown error')}")
                    if self.config.session_logger:
                        self.config.session_logger.log_error(
                            f"SQL EXECUTION ERROR: {execution_result.get('error', 'Unknown error')}"
                        )
                else:
                    self.logger.info(f"SQL execution successful, {execution_result.get('row_count', 0)} rows returned")

                    # Применяем автоматическую фильтрацию по температуре, если указана температура
                    target_temperature = extracted_params.get("temperature_k")
                    self.logger.info(f"Temperature filtering check: target_temp={target_temperature}, success={execution_result.get('success', False)}")

                    if target_temperature and execution_result.get("success", False):
                        self.logger.info(f"Applying automatic temperature filtering at {target_temperature}K...")
                        execution_result = await self._filter_by_temperature_range(
                            execution_result, target_temperature
                        )
                        self.logger.info(f"Temperature filtering completed: {execution_result.get('row_count', 0)} records match temperature range")
                    else:
                        self.logger.warning(f"Temperature filtering skipped: target_temp={target_temperature}, success={execution_result.get('success')}")

                result_data["execution_result"] = execution_result

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

    async def _execute_query(self, sql_query: str) -> Dict[str, Any]:
        """
        Выполнить SQL запрос к базе данных.

        Args:
            sql_query: SQL запрос

        Returns:
            Результаты выполнения
        """
        try:
            # Очистка SQL запроса от HTML entities и множественных statements
            cleaned_query = self._clean_sql_query(sql_query)

            conn = sqlite3.connect(self.config.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(cleaned_query)
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )
            rows = cursor.fetchall()

            # Конвертируем в списки
            data_rows = [list(row) for row in rows] if rows else []

            conn.close()

            return {
                "success": True,
                "columns": columns,
                "rows": data_rows,
                "row_count": len(data_rows),
            }

        except Exception as e:
            self.logger.error(f"Query execution error: {e}")
            return {"success": False, "error": str(e)}

    async def _filter_by_temperature_range(
        self, query_results: Dict[str, Any], target_temperature_k: float
    ) -> Dict[str, Any]:
        """
        Автоматическая постфильтрация результатов по температурному диапазону.

        Args:
            query_results: Результаты SQL запроса
            target_temperature_k: Целевая температура в Кельвинах

        Returns:
            Отфильтрованные результаты
        """
        if not query_results.get("success", False):
            return query_results

        columns = query_results.get("columns", [])
        rows = query_results.get("rows", [])

        # Найдем индексы колонок Tmin и Tmax
        tmin_idx = None
        tmax_idx = None

        for i, col in enumerate(columns):
            if col.lower() == 'tmin':
                tmin_idx = i
            elif col.lower() == 'tmax':
                tmax_idx = i

        if tmin_idx is None or tmax_idx is None:
            self.logger.warning("Temperature range columns (Tmin/Tmax) not found, skipping temperature filtering")
            return query_results

        # Фильтруем строки по температурному диапазону
        filtered_rows = []
        excluded_count = 0

        for row in rows:
            try:
                tmin = float(row[tmin_idx]) if row[tmin_idx] is not None else 0
                tmax = float(row[tmax_idx]) if row[tmax_idx] is not None else 9999

                # Проверяем, входит ли целевая температура в диапазон
                if tmin <= target_temperature_k <= tmax:
                    filtered_rows.append(row)
                else:
                    excluded_count += 1

            except (ValueError, TypeError, IndexError):
                # Если не удается конвертировать температуры, оставляем строку
                filtered_rows.append(row)

        # Логируем результаты фильтрации
        self.logger.info(f"Temperature filtering at {target_temperature_k}K: {len(filtered_rows)} records match, {excluded_count} excluded")

        if self.config.session_logger:
            self.config.session_logger.log_info(
                f"TEMPERATURE FILTER: Target={target_temperature_k}K, "
                f"Matched={len(filtered_rows)}, Excluded={excluded_count}"
            )

        return {
            "success": True,
            "columns": columns,
            "rows": filtered_rows,
            "row_count": len(filtered_rows),
            "temperature_filter_applied": True,
            "target_temperature_k": target_temperature_k,
            "excluded_by_temperature": excluded_count
        }

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
    auto_execute: bool = False,
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
        auto_execute=auto_execute,
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
