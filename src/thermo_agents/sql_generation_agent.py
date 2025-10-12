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
from .message_validator import MessageValidator, ValidationResult
from .operations import OperationType
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
    poll_interval: float = 0.5  # Уменьшено с 1.0 до 0.5с для ускорения реакции
    max_retries: int = 4  # Увеличено с 3 до 4 для улучшенной надежности


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

        # Инициализация валидатора сообщений
        self.message_validator = MessageValidator(logger=self.logger)

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

        self.logger.info(f"SQLGenerationAgent '{self.agent_id}' initialized with message validation")

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

    def _create_individual_sql_hint(self, compound: str, common_params: Dict) -> str:
        """
        Создать оптимизированную SQL подсказку для поиска одного соединения.

        Args:
            compound: Химическая формула
            common_params: Общие параметры поиска

        Returns:
            Оптимизированная SQL подсказка
        """
        temperature = common_params.get("temperature_k", 298.15)
        phases = common_params.get("phases", [])
        properties = common_params.get("properties", ["basic"])

        # Создаем специфичную подсказку для одного соединения
        sql_hint = f"""
        Сгенерируй SQL запрос для поиска одного химического соединения {compound} в таблице compounds.

        Требования:
        1. Используй TRIM(Formula) = '{compound}' для точного совпадения
        2. Добавь Formula LIKE '{compound}(%' для фазовых/ионных вариантов
        3. Примени температурную фильтрацию: температура {temperature}K должна быть в диапазоне [Tmin, Tmax]
        4. Сортируй по ReliabilityClass ASC (1 = самые надежные данные)
        5. Используй LIMIT 100 для контроля результатов
        6. Приоритизуй фазы: {', '.join(phases) if phases else 'любые'}

        Пример структуры:
        SELECT * FROM compounds WHERE
        (TRIM(Formula) = '{compound}' OR Formula LIKE '{compound}(%')
        AND (Tmin IS NULL OR Tmax IS NULL OR ({temperature} >= Tmin AND {temperature} <= Tmax)))
        ORDER BY ReliabilityClass ASC
        LIMIT 100
        """
        return sql_hint.strip()

    def _calculate_confidence(self, result_data: Dict) -> float:
        """
        Рассчитать уверенность в результате поиска.

        Args:
            result_data: Данные результата выполнения

        Returns:
            Уверенность от 0.0 до 1.0
        """
        execution_result = result_data.get("execution_result", {})
        filtered_result = result_data.get("filtered_result", {})

        if not execution_result.get("success", False):
            return 0.0

        row_count = execution_result.get("row_count", 0)
        if row_count == 0:
            return 0.0

        # Базовая уверенность на основе количества найденных записей
        base_confidence = min(1.0, row_count / 10.0)  # 10+ записей = 1.0

        # Учитываем наличие отфильтрованных результатов
        if filtered_result.get("selected_records"):
            filtered_count = len(filtered_result["selected_records"])
            filter_confidence = min(1.0, filtered_count / 3.0)  # 3+ записи = 1.0
            return (base_confidence + filter_confidence) / 2.0

        return base_confidence

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
                # Получаем новые сообщения (оба типа сообщений)
                messages_query = self.storage.receive_messages(
                    self.agent_id, message_type="generate_query"
                )
                messages_individual = self.storage.receive_messages(
                    self.agent_id, message_type="generate_individual_query"
                )

                # Объединяем сообщения
                all_messages = messages_query + messages_individual

                # Обрабатываем каждое сообщение
                for message in all_messages:
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
        # Используем операцию для логирования
        operation_context = None
        if self.config.session_logger and self.config.session_logger.is_operations_enabled():
            operation_context = self.config.session_logger.create_operation_context(
                agent_name=self.agent_id,
                operation_type=OperationType.GENERATE_QUERY,
                source_agent=message.source_agent,
                correlation_id=message.id,
            )
            operation_context.set_storage_snapshot_provider(lambda: self.storage.get_storage_snapshot(include_content=True))
            operation = operation_context.__enter__()
        else:
            operation = None

        try:
            # Валидация сообщения с использованием универсального валидатора
            validation_report = self.message_validator.validate_message(message)
            if not validation_report.is_valid:
                error_messages = [error.message for error in validation_report.errors]
                raise ValueError(f"Message validation failed: {'; '.join(error_messages)}")

            # Логируем предупреждения валидации
            if validation_report.warnings:
                warning_messages = [warning.message for warning in validation_report.warnings]
                self.logger.warning(f"Message validation warnings: {'; '.join(warning_messages)}")

            # Определяем тип сообщения
            message_type = message.payload.get("compound") and "individual" or "standard"

            if message_type == "individual":
                # Индивидуальный запрос для одного соединения
                compound = message.payload.get("compound")
                common_params = message.payload.get("common_params", {})
                search_strategy = message.payload.get("search_strategy", "individual_compound_search")

                if not compound:
                    raise ValueError("No compound in individual search message payload")

                # Создаем оптимизированную SQL подсказку для одного соединения
                sql_hint = self._create_individual_sql_hint(compound, common_params)
                extracted_params = {
                    "compounds": [compound],
                    "temperature_k": common_params.get("temperature_k", 298.15),
                    "temperature_range_k": common_params.get("temperature_range_k", [200, 2000]),
                    "phases": common_params.get("phases", []),
                    "properties": common_params.get("properties", ["basic"]),
                    "intent": "individual_lookup",
                }

                # Устанавливаем входные данные для операции
                input_data = {
                    "message_type": "individual",
                    "compound": compound,
                    "temperature_k": extracted_params["temperature_k"],
                    "phases": extracted_params["phases"],
                }

                self.logger.info(f"Processing individual search for compound: {compound}")
            else:
                # Стандартный запрос
                sql_hint = message.payload.get("sql_hint")
                extracted_params = message.payload.get("extracted_params", {})

                # Устанавливаем входные данные для операции
                input_data = {
                    "message_type": "standard",
                    "sql_hint": sql_hint[:100] if sql_hint else "None",
                    "compounds_count": len(extracted_params.get("compounds", [])),
                }

                self.logger.info(f"Processing SQL hint: {sql_hint[:100] if sql_hint else 'None'}...")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"SQL GENERATION START: Processing message {message.id}")

                if not sql_hint:
                    raise ValueError("No sql_hint in message payload")

            # Устанавливаем входные данные для операции
            if operation:
                operation.set_input_data(input_data)

            # Генерируем SQL запрос используя PydanticAI агента с увеличенным тайм-аутом
            self.logger.info("Starting SQL query generation...")
            result = await asyncio.wait_for(
                self.agent.run(sql_hint, deps=self.config),
                timeout=120.0  # Увеличено с 60 до 120 секунд для генерации
            )
            sql_result = result.output

            self.logger.info(f"Generated SQL query: {sql_result.sql_query}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL GENERATION COMPLETE: Query length {len(sql_result.sql_query)}")

            # Дополнительная очистка запроса перед выполнением
            sql_result.sql_query = self._clean_sql_query(sql_result.sql_query)
            self.logger.info("SQL query cleaned")

            # Валидация сгенерированного SQL запроса
            if not sql_result.sql_query or not sql_result.sql_query.strip():
                raise ValueError("Generated SQL query is empty after cleaning")

            if len(sql_result.sql_query.strip()) < 10:
                raise ValueError(f"Generated SQL query too short: {sql_result.sql_query}")

            # Проверка на наличие базовых SQL конструкций
            sql_upper = sql_result.sql_query.upper()
            if not any(keyword in sql_upper for keyword in ['SELECT', 'FROM']):
                raise ValueError(f"Generated SQL query lacks basic SQL structure: {sql_result.sql_query[:100]}...")

            self.logger.info(f"SQL query validation passed: {len(sql_result.sql_query)} characters")

            # Сохраняем результат в хранилище
            result_key = f"sql_result_{message.id}"
            result_data = {
                "sql_query": sql_result.sql_query,
                "explanation": sql_result.explanation,
                "expected_columns": sql_result.expected_columns,
                "extracted_params": extracted_params,
            }

            self.logger.info(f"Prepared result data with key: {result_key}")

            # Определяем тип обработки результатов
            if message_type == "individual":
                # Для индивидуального запроса отправляем напрямую к Results Filtering Agent
                self.logger.info("Sending SQL query to database agent for individual execution...")
                db_message_id = self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="database_agent",
                    message_type="execute_individual_sql",
                    correlation_id=message.id,
                    payload={
                        "sql_query": sql_result.sql_query,
                        "compound": extracted_params["compounds"][0],
                        "common_params": common_params if message_type == "individual" else {},
                        "request_source": "individual_search_agent",
                    },
                )
            else:
                # Стандартная обработка
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
                    filtering_timeout = 60  # Увеличено с 30 до 60 секунд на фильтрацию

                    while (asyncio.get_event_loop().time() - filtering_start_time) < filtering_timeout:
                        # Получаем сообщения от агента фильтрации
                        filtering_messages = self.storage.receive_messages(
                            self.agent_id, message_type="results_filtered"
                        )

                        if filtering_messages:
                            self.logger.debug(f"DEBUG: Found {len(filtering_messages)} filtering messages")

                        for filter_msg in filtering_messages:
                            # Проверяем correlation_id (должен соответствовать исходному message ID)
                            if (filter_msg.source_agent == "results_filtering_agent" and
                                filter_msg.correlation_id == message.id):
                                status = filter_msg.payload.get("status")
                                self.logger.info(f"Received filtering result: {status}")
                                if status == "success":
                                    filtering_result = filter_msg.payload.get("filtered_result")
                                    break
                                elif status == "no_results":
                                    self.logger.warning("No records found after filtering")
                                    break
                                elif status == "error":
                                    self.logger.error(f"Filtering agent error: {filter_msg.payload.get('error')}")
                                    break

                        if filtering_result:
                            break
                        # Уменьшаем задержку для ускорения реакции
                        await asyncio.sleep(0.2)

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
            if message_type == "individual":
                # Для индивидуальных запросов отправляем Individual Search Agent
                target_agent = "individual_search_agent"
                response_message_type = "individual_sql_complete"
            else:
                # Стандартные запросы
                target_agent = message.source_agent
                response_message_type = "response"

            self.logger.info(f"Sending {response_message_type} to {target_agent}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SENDING {response_message_type.upper()}: To {target_agent}, key={result_key}")

            try:
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent=target_agent,
                    message_type=response_message_type,
                    correlation_id=message.id,
                    payload={
                        "status": "success",
                        "result_key": result_key,
                        "sql_result": result_data,
                        "search_results": result_data.get("execution_result", {}).get("rows", []),
                        "filtered_data": result_data.get("filtered_result", {}).get("selected_records", []),
                        "confidence": self._calculate_confidence(result_data),
                    },
                )
                self.logger.info(f"{response_message_type} sent successfully to {target_agent}")
            except Exception as e:
                self.logger.error(f"Error sending response: {e}")

            # Дополнительная информация в лог (теперь это часть операции)
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL GENERATED: {len(sql_result.sql_query)} chars, {len(sql_result.expected_columns)} columns expected")

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

            # Готовим результат для логирования операции
            operation_result = {
                "message_type": message_type,
                "sql_query_length": len(sql_result.sql_query),
                "expected_columns": len(sql_result.expected_columns),
                "result_key": result_key,
                "database_execution": bool(db_result),
            }

            if db_result:
                operation_result["row_count"] = db_result.get("row_count", 0)
                operation_result["execution_success"] = db_result.get("success", False)

            if result_data.get("filtered_result"):
                operation_result["filtered_records"] = len(result_data["filtered_result"].get("selected_records", []))

            # Добавляем информацию о маршрутизации
            if message_type == "individual":
                operation_result["target_agent"] = "individual_search_agent"
            else:
                operation_result["target_agent"] = message.source_agent

            # Устанавливаем результат операции
            if operation_context:
                operation_context.set_result(operation_result)

            self.logger.info("Message processing completed successfully")

            # Завершаем операцию успешно
            if operation_context:
                operation_context.__exit__(None, None, None)

        except Exception as e:
            self.logger.error(f"Error processing message {message.id}: {e}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL AGENT ERROR: {str(e)[:100]}")

            # Завершаем операцию с ошибкой
            if operation_context:
                operation_context.__exit__(type(e), e, e.__traceback__)

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
                self.config.session_logger.log_info(f"SQL ERROR: {str(e)[:100]}")

    # SQL execution and filtering methods removed - agent only generates queries

    # SQL validation and refinement methods removed - no longer needed

    async def process_single_query(self, sql_hint: str) -> SQLQueryResult:
        """
        Обработать одиночный запрос (для совместимости и тестирования).

        Args:
            sql_hint: Подсказка для SQL генерации

        Returns:
            Результат генерации SQL

        Raises:
            ValueError: Если не удалось сгенерировать SQL запрос после повторных попыток
        """
        max_retries = 3
        base_timeout = 60.0

        for attempt in range(max_retries):
            try:
                import asyncio
                timeout = base_timeout * (attempt + 1)  # Увеличиваем таймаут с каждой попыткой

                result = await asyncio.wait_for(
                    self.agent.run(sql_hint, deps=self.config),
                    timeout=timeout
                )
                return result.output

            except asyncio.TimeoutError:
                self.logger.error(f"Timeout in SQL generation (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise ValueError(f"Не удалось сгенерировать SQL запрос: превышено время ожидания ответа от модели после {max_retries} попыток. Попробуйте упростить запрос.")
                await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Error in SQL generation (attempt {attempt + 1}/{max_retries}): {e}")
                error_msg = str(e)

                # Дополнительное логирование для трассировки
                if self.config.session_logger:
                    self.config.session_logger.log_error(f"SQL GENERATION FAILED (attempt {attempt + 1}): {error_msg[:200]}")

                # Определяем тип ошибки для более понятного сообщения
                if "status_code: 401" in error_msg or "No auth credentials" in error_msg:
                    raise ValueError("Ошибка аутентификации: проверьте API ключ для доступа к модели.")
                elif "status_code: 429" in error_msg or "rate limit" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Превышен лимит запросов к модели. Попробуйте повторить запрос позже.")
                    await asyncio.sleep(5)
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Сетевая ошибка: проверьте подключение к интернету.")
                    await asyncio.sleep(2)
                elif "timeout" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Превышено время ожидания ответа от модели. Попробуйте упростить запрос.")
                    await asyncio.sleep(1)
                else:
                    if attempt == max_retries - 1:
                        raise ValueError(f"Не удалось сгенерировать SQL запрос после {max_retries} попыток: {error_msg[:100]}...")
                    await asyncio.sleep(1)

        # Этот код не должен быть достигнут, так как все ошибки обрабатываются выше
        raise ValueError(f"Не удалось сгенерировать SQL запрос после {max_retries} попыток.")

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
