"""
Оркестратор для координации работы термодинамических агентов.

Реализует паттерн координатора из PydanticAI для управления
взаимодействием между агентами через хранилище.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .agent_storage import AgentStorage, get_storage
from .operations import OperationType
from .thermo_agents_logger import SessionLogger


class OrchestratorRequest(BaseModel):
    """Запрос к оркестратору."""

    user_query: str  # Исходный запрос пользователя
    request_type: str = "thermodynamic"  # Тип запроса
    options: Dict[str, Any] = Field(default_factory=dict)  # Дополнительные опции


class OrchestratorResponse(BaseModel):
    """Ответ от оркестратора."""

    success: bool  # Успешность обработки
    result: Dict[str, Any]  # Результаты обработки
    errors: list[str] = Field(default_factory=list)  # Список ошибок
    trace: list[str] = Field(default_factory=list)  # Трассировка выполнения


@dataclass
class OrchestratorConfig:
    """Конфигурация оркестратора."""

    llm_api_key: str
    llm_base_url: str
    llm_model: str
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    max_retries: int = 3  # Увеличено с 2 до 3 для улучшенной надежности
    timeout_seconds: int = 120  # Увеличено с 60 до 120 секунд для синхронизации с другими агентами


class ThermoOrchestrator:
    """
    Оркестратор для координации работы термодинамических агентов.

    Основные обязанности:
    - Маршрутизация запросов к соответствующим агентам
    - Координация взаимодействия между агентами через хранилище
    - Управление состоянием обработки запросов
    - Обработка ошибок и повторные попытки
    """

    def __init__(self, config: OrchestratorConfig):
        """
        Инициализация оркестратора.

        Args:
            config: Конфигурация оркестратора
        """
        self.config = config
        self.storage = config.storage
        self.logger = config.logger
        self.agent = self._initialize_agent()

        # Регистрация в хранилище
        self.agent_id = "orchestrator"
        self.storage.start_session(self.agent_id, {"status": "ready"})

    def _initialize_agent(self) -> Agent:
        """Инициализация PydanticAI агента для оркестратора."""
        provider = OpenAIProvider(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )

        model = OpenAIChatModel(self.config.llm_model, provider=provider)

        agent = Agent(
            model,
            deps_type=OrchestratorConfig,
            output_type=OrchestratorResponse,
            system_prompt="""You are an orchestrator coordinating thermodynamic agents.
            Route requests to appropriate agents and manage their interactions through the storage system.
            Ensure all agents communicate via messages, not direct calls.""",
            retries=self.config.max_retries,
        )

        # Добавляем инструменты для управления агентами
        @agent.tool
        async def route_to_thermo_agent(
            ctx: RunContext[OrchestratorConfig], user_query: str
        ) -> Dict[str, Any]:
            """
            Направить запрос к термодинамическому агенту для извлечения параметров.

            Args:
                ctx: Контекст выполнения
                user_query: Запрос пользователя

            Returns:
                Результат обработки агентом
            """
            # Отправляем сообщение термо-агенту через хранилище
            message_id = ctx.deps.storage.send_message(
                source_agent="orchestrator",
                target_agent="thermo_agent",
                message_type="extract_parameters",
                payload={"user_query": user_query},
            )

            ctx.deps.logger.info(f"Sent message {message_id} to thermo_agent")

            # Сохраняем в хранилище для агента
            ctx.deps.storage.set(
                f"request_{message_id}",
                {"query": user_query, "status": "pending"},
                ttl_seconds=300,
            )

            return {
                "message_id": message_id,
                "status": "sent",
                "target": "thermo_agent",
            }

        @agent.tool
        async def route_to_sql_agent(
            ctx: RunContext[OrchestratorConfig],
            sql_hint: str,
            extracted_params: Dict[str, Any],
        ) -> Dict[str, Any]:
            """
            Направить запрос к SQL агенту для генерации запроса.

            Args:
                ctx: Контекст выполнения
                sql_hint: Подсказка для SQL генерации
                extracted_params: Извлеченные параметры

            Returns:
                Результат обработки агентом
            """
            # Отправляем сообщение SQL агенту через хранилище
            message_id = ctx.deps.storage.send_message(
                source_agent="orchestrator",
                target_agent="sql_agent",
                message_type="generate_query",
                payload={"sql_hint": sql_hint, "extracted_params": extracted_params},
            )

            ctx.deps.logger.info(f"Sent message {message_id} to sql_agent")

            # Сохраняем в хранилище для агента
            ctx.deps.storage.set(
                f"sql_request_{message_id}",
                {"sql_hint": sql_hint, "params": extracted_params, "status": "pending"},
                ttl_seconds=300,
            )

            return {"message_id": message_id, "status": "sent", "target": "sql_agent"}

        @agent.tool
        async def check_agent_response(
            ctx: RunContext[OrchestratorConfig], agent_id: str, message_id: str
        ) -> Optional[Dict[str, Any]]:
            """
            Проверить ответ от агента.

            Args:
                ctx: Контекст выполнения
                agent_id: ID агента
                message_id: ID исходного сообщения

            Returns:
                Ответ агента или None если еще не готов
            """
            # Получаем сообщения от агента
            messages = ctx.deps.storage.receive_messages(
                "orchestrator", message_type="response"
            )

            # Ищем ответ на наше сообщение
            for msg in messages:
                if msg.correlation_id == message_id:
                    ctx.deps.logger.info(f"Received response from {msg.source_agent}")
                    return msg.payload

            return None

        @agent.tool
        async def get_storage_data(
            ctx: RunContext[OrchestratorConfig], key: str
        ) -> Any:
            """
            Получить данные из хранилища.

            Args:
                ctx: Контекст выполнения
                key: Ключ для доступа к данным

            Returns:
                Данные из хранилища
            """
            return ctx.deps.storage.get(key)

        @agent.tool
        async def set_storage_data(
            ctx: RunContext[OrchestratorConfig],
            key: str,
            value: Any,
            ttl_seconds: Optional[int] = None,
        ) -> bool:
            """
            Сохранить данные в хранилище.

            Args:
                ctx: Контекст выполнения
                key: Ключ для сохранения
                value: Данные
                ttl_seconds: Время жизни в секундах

            Returns:
                True если успешно сохранено
            """
            ctx.deps.storage.set(key, value, ttl_seconds)
            return True

        return agent

    async def process_request(
        self, request: OrchestratorRequest
    ) -> OrchestratorResponse:
        """
        Обработать запрос пользователя.

        Координирует работу агентов через хранилище:
        1. Направляет запрос к thermo_agent для извлечения параметров
        2. Получает результат через хранилище
        3. Направляет параметры к sql_agent для генерации SQL
        4. Возвращает полный результат

        Args:
            request: Запрос пользователя

        Returns:
            Результат обработки всеми агентами
        """
        # Используем операцию для логирования координации
        operation_context = None
        if self.config.session_logger and self.config.session_logger.is_operations_enabled():
            operation_context = self.config.session_logger.create_operation_context(
                agent_name=self.agent_id,
                operation_type=OperationType.PROCESS_REQUEST,
                correlation_id=f"orch_req_{id(request)}",
            )
            operation_context.set_storage_snapshot_provider(lambda: self.storage.get_storage_snapshot(include_content=True))
            operation = operation_context.__enter__()
        else:
            operation = None

        try:
            # Инициализация трассировки
            trace = []

            # Устанавливаем входные данные для операции
            input_data = {
                "user_query": request.user_query[:200],  # Ограничиваем для лога
                "request_type": request.request_type,
            }

            if operation:
                operation.set_input_data(input_data)

            # Сохраняем запрос в хранилище
            request_id = f"orchestrator_request_{id(request)}"
            self.storage.set(request_id, request.model_dump(), ttl_seconds=600)

            # Шаг 1: Отправляем запрос thermo_agent
            thermo_message_id = self.storage.send_message(
                source_agent=self.agent_id,
                target_agent="thermo_agent",
                message_type="extract_parameters",
                payload={"user_query": request.user_query},
            )

            # Ждем ответа от thermo_agent через сообщения с улучшенным логированием
            extracted_params = None
            start_time = asyncio.get_event_loop().time()
            self.logger.info(f"DEBUG: Waiting for thermo_agent response, timeout={self.config.timeout_seconds}s, message_id={thermo_message_id}")

            while (
                asyncio.get_event_loop().time() - start_time
            ) < self.config.timeout_seconds:
                # Получаем сообщения от thermo агента (и response, и error)
                response_messages = self.storage.receive_messages(
                    self.agent_id, message_type="response"
                )
                error_messages = self.storage.receive_messages(
                    self.agent_id, message_type="error"
                )

                all_messages = response_messages + error_messages

                if all_messages:
                    self.logger.debug(f"DEBUG: Found {len(all_messages)} messages for thermo_agent")

                # Ищем ответ на наше сообщение
                for msg in all_messages:
                    if msg.correlation_id == thermo_message_id and msg.source_agent == "thermo_agent":
                        status = msg.payload.get("status")
                        self.logger.info(f"DEBUG: Received {msg.message_type} from thermo_agent: {status}")

                        if msg.message_type == "error" or status == "error":
                            error_msg = msg.payload.get("error", "Unknown error")
                            self.logger.error(f"DEBUG: Thermo agent returned error: {error_msg}")
                            trace.append(f"Thermo agent error: {error_msg}")
                            if self.config.session_logger:
                                self.config.session_logger.log_error(f"Thermo agent error: {error_msg}")

                            # Завершаем операцию с ошибкой
                            if operation_context:
                                operation_context.__exit__(ValueError, ValueError(error_msg), None)

                            return OrchestratorResponse(
                                success=False,
                                result={},
                                errors=[f"Не удалось извлечь параметры из запроса: {error_msg}"],
                                trace=trace,
                            )

                        elif status == "success":
                            extracted_params = msg.payload.get("extracted_params")
                            if self.config.session_logger:
                                self.config.session_logger.log_info(f"THERMO AGENT RESPONSE: Success with {len(extracted_params.get('compounds', []))} compounds")
                            break

                if extracted_params:
                    break
                # Уменьшаем задержку для ускорения реакции
                await asyncio.sleep(0.05)  # Уменьшено с 0.1 до 0.05 секунд

            if extracted_params:
                trace.append("Received parameters from thermo_agent")

                # Валидация извлеченных параметров
                compounds = extracted_params.get("compounds", [])
                intent = extracted_params.get("intent", "lookup")

                # Проверяем, что извлечены соединения
                if not compounds or len(compounds) == 0:
                    trace.append("No compounds extracted - cannot proceed")
                    if self.config.session_logger:
                        self.config.session_logger.log_error(
                            f"No compounds extracted from query: {request.user_query[:100]}"
                        )

                    # Завершаем операцию с ошибкой извлечения
                    if operation_context:
                        operation_context.__exit__(ValueError, ValueError("No compounds extracted"), None)

                    return OrchestratorResponse(
                        success=False,
                        result={},
                        errors=["Не удалось извлечь химические соединения из запроса. Пожалуйста, уточните запрос, используя химические формулы или названия веществ."],
                        trace=trace,
                    )

                # Для реакций должно быть как минимум 2 соединения
                if intent == "reaction" and len(compounds) < 2:
                    trace.append(f"Reaction intent with only {len(compounds)} compounds - insufficient")
                    if self.config.session_logger:
                        self.config.session_logger.log_error(
                            f"Reaction query with insufficient compounds: {len(compounds)} compounds from query: {request.user_query[:100]}"
                        )

                    # Завершаем операцию с ошибкой
                    if operation_context:
                        operation_context.__exit__(ValueError, ValueError("Insufficient compounds for reaction"), None)

                    return OrchestratorResponse(
                        success=False,
                        result={},
                        errors=[f"Для анализа реакции необходимо указать как минимум 2 соединения. Извлечено соединений: {len(compounds)}."],
                        trace=trace,
                    )

                # Определяем тип обработки на основе intent

                if intent == "reaction" and extracted_params.get("compounds"):
                    # Для реакций используем Individual Search Agent
                    trace.append("Processing reaction via Individual Search Agent")

                    # Ждем результата от Individual Search Agent с улучшенным логированием
                    individual_result = None
                    individual_start_time = asyncio.get_event_loop().time()
                    timeout_seconds = self.config.timeout_seconds * 2  # Увеличенный таймаут для индивидуального поиска
                    self.logger.info(f"DEBUG: Waiting for Individual Search Agent, timeout={timeout_seconds}s, correlation_id={thermo_message_id}")

                    while (
                        asyncio.get_event_loop().time() - individual_start_time
                    ) < timeout_seconds:
                        # Получаем сообщения от Individual Search Agent
                        messages = self.storage.receive_messages(
                            self.agent_id, message_type="individual_search_complete"
                        )

                        if messages:
                            self.logger.debug(f"DEBUG: Found {len(messages)} individual search messages")

                        # Ищем результат с правильным correlation_id
                        for msg in messages:
                            if msg.correlation_id == thermo_message_id and msg.source_agent == "individual_search_agent":
                                status = msg.payload.get("status")
                                self.logger.info(f"DEBUG: Received individual search result: {status}")
                                if status == "success":
                                    result_key = msg.payload.get("result_key")
                                    if result_key:
                                        # Получаем полный результат из хранилища
                                        individual_result = self.storage.get(result_key)
                                        if individual_result:
                                            if self.config.session_logger:
                                                self.config.session_logger.log_info(f"INDIVIDUAL SEARCH COMPLETE: {len(individual_result.get('individual_results', []))} compounds processed")
                                        break
                                elif status == "error":
                                    self.logger.error(f"DEBUG: Individual Search Agent error: {msg.payload.get('error')}")
                                    trace.append(f"Individual Search Agent error: {msg.payload.get('error')}")
                                    break

                        if individual_result:
                            break
                        # Уменьшаем задержку для ускорения реакции
                        await asyncio.sleep(0.05)  # Уменьшено с 0.1 до 0.05 секунд

                    if individual_result:
                        trace.append("Received aggregated results from Individual Search Agent")

                        # Готовим результат операции
                        operation_result = {
                            "request_id": request_id,
                            "status": "success",
                            "compounds_count": len(extracted_params.get("compounds", [])),
                            "processing_type": "individual_search",
                            "individual_results_count": len(individual_result.get("individual_results", [])),
                            "overall_confidence": individual_result.get("overall_confidence"),
                        }

                        # Устанавливаем результат операции
                        if operation_context:
                            operation_context.set_result(operation_result)

                        # Собираем полный результат для реакции
                        response = OrchestratorResponse(
                            success=True,
                            result={
                                "extracted_parameters": extracted_params,
                                "aggregated_results": individual_result.get("aggregated_results"),
                                "summary_table": individual_result.get("summary_table"),
                                "overall_confidence": individual_result.get("overall_confidence"),
                                "individual_results": individual_result.get("individual_results"),
                                "missing_compounds": individual_result.get("missing_compounds"),
                                "warnings": individual_result.get("warnings"),
                                "processing_type": "individual_search",
                            },
                            trace=trace,
                        )

                        # Завершаем операцию успешно
                        if operation_context:
                            operation_context.__exit__(None, None, None)

                        return response
                    else:
                        trace.append("Individual Search Agent result not ready")
                        if self.config.session_logger:
                            self.config.session_logger.log_error(
                                "Individual Search Agent did not complete processing in time"
                            )

                        # Завершаем операцию с ошибкой
                        if operation_context:
                            operation_context.__exit__(TimeoutError, TimeoutError("Individual Search Agent timeout"), None)

                        return OrchestratorResponse(
                            success=False,
                            result={},
                            errors=["Individual Search Agent did not complete processing in time"],
                            trace=trace,
                        )

                elif extracted_params.get("sql_query_hint"):
                    # Для нерекакционных запросов используем стандартный SQL агент
                    trace.append("Waiting for SQL agent result (triggered by thermo_agent)")

                    # Ждем сообщения "sql_ready" от SQL агента
                    sql_result = None
                    sql_start_time = asyncio.get_event_loop().time()
                    while (
                        asyncio.get_event_loop().time() - sql_start_time
                    ) < self.config.timeout_seconds:
                        # Получаем сообщения от SQL агента
                        messages = self.storage.receive_messages(
                            self.agent_id, message_type="sql_ready"
                        )

                        # Ищем результат с правильным correlation_id
                        for msg in messages:
                            if msg.correlation_id == thermo_message_id and msg.source_agent == "sql_agent":
                                self.logger.info(f"Received sql_ready from sql_agent: {msg.payload}")
                                result_key = msg.payload.get("result_key")
                                if result_key:
                                    # Получаем полный результат из хранилища
                                    sql_result = self.storage.get(result_key)
                                    break

                        if sql_result:
                            break
                        await asyncio.sleep(0.1)

                    if sql_result:
                        trace.append("Received SQL query and execution result from sql_agent")

                        # Готовим результат операции
                        operation_result = {
                            "request_id": request_id,
                            "status": "success",
                            "compounds_count": len(extracted_params.get("compounds", [])),
                            "processing_type": "standard_search",
                            "sql_success": bool(sql_result.get("execution_result", {}).get("success")),
                            "row_count": sql_result.get("execution_result", {}).get("row_count", 0),
                        }

                        # Устанавливаем результат операции
                        if operation_context:
                            operation_context.set_result(operation_result)

                        # Собираем полный результат
                        response = OrchestratorResponse(
                            success=True,
                            result={
                                "extracted_parameters": extracted_params,
                                "sql_query": sql_result.get("sql_query"),
                                "explanation": sql_result.get("explanation"),
                                "expected_columns": sql_result.get("expected_columns"),
                                "execution_result": sql_result.get("execution_result"),
                                "processing_type": "standard_search",
                            },
                            trace=trace,
                        )

                        # Завершаем операцию успешно
                        if operation_context:
                            operation_context.__exit__(None, None, None)

                        return response
                    else:
                        trace.append("SQL agent result not ready")
                        if self.config.session_logger:
                            self.config.session_logger.log_error(
                                "SQL agent did not complete processing in time"
                            )

                        # Завершаем операцию с ошибкой
                        if operation_context:
                            operation_context.__exit__(TimeoutError, TimeoutError("SQL agent timeout"), None)

                        return OrchestratorResponse(
                            success=False,
                            result={},
                            errors=["SQL agent did not complete processing in time"],
                            trace=trace,
                        )
                else:
                    # Только извлечение параметров, SQL не требуется
                    # Готовим результат операции
                    operation_result = {
                        "request_id": request_id,
                        "status": "success",
                        "compounds_count": len(extracted_params.get("compounds", [])),
                        "processing_type": "parameter_extraction_only",
                    }

                    # Устанавливаем результат операции
                    if operation_context:
                        operation_context.set_result(operation_result)

                    response = OrchestratorResponse(
                        success=True,
                        result={"extracted_parameters": extracted_params},
                        trace=trace,
                    )

                    # Завершаем операцию успешно
                    if operation_context:
                        operation_context.__exit__(None, None, None)

                    return response
            else:
                trace.append("Thermo agent response not ready")
                # Логируем в сессионный лог
                if self.config.session_logger:
                    self.config.session_logger.log_error(
                        "Thermo agent did not respond to orchestrator"
                    )

                # Завершаем операцию с ошибкой
                if operation_context:
                    operation_context.__exit__(TimeoutError, TimeoutError("Thermo agent timeout"), None)

                return OrchestratorResponse(
                    success=False,
                    result={},
                    errors=["Не удалось извлечь параметры из запроса - превышено время ожидания. Пожалуйста, попробуйте упростить запрос или использовать более точные химические формулы."],
                    trace=trace,
                )
        except Exception as e:
            self.logger.error(f"Error processing request: {e}")

            # Завершаем операцию с ошибкой
            if operation_context:
                operation_context.__exit__(type(e), e, e.__traceback__)

            return OrchestratorResponse(
                success=False, result={}, errors=[str(e)], trace=trace
            )


    async def shutdown(self):
        """Завершить работу оркестратора."""
        self.logger.info("Shutting down orchestrator")
        self.storage.end_session(self.agent_id)

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора и системы."""
        return {
            "orchestrator": self.storage.get_session(self.agent_id),
            "storage_stats": self.storage.get_stats(),
            "active_agents": list(self.storage._agent_sessions.keys()),
        }
