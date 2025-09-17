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
    max_retries: int = 2
    timeout_seconds: int = 60


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
        self.logger.info(f"Processing request: {request.user_query[:100]}...")
        trace = []

        try:
            # Сохраняем запрос в хранилище
            request_id = f"orchestrator_request_{id(request)}"
            self.storage.set(request_id, request.model_dump(), ttl_seconds=600)
            trace.append(f"Request saved with ID: {request_id}")

            # Шаг 1: Отправляем запрос thermo_agent
            thermo_message_id = self.storage.send_message(
                source_agent=self.agent_id,
                target_agent="thermo_agent",
                message_type="extract_parameters",
                payload={"user_query": request.user_query},
            )
            trace.append(f"Sent message to thermo_agent: {thermo_message_id}")

            # Ждем ответа от thermo_agent (в реальной системе это было бы асинхронно)
            # Здесь мы эмулируем получение ответа через хранилище
            extracted_params_key = f"thermo_result_{thermo_message_id}"

            # Ждем ответа от thermo_agent с таймаутом
            extracted_params = None
            start_time = asyncio.get_event_loop().time()
            while (
                asyncio.get_event_loop().time() - start_time
            ) < self.config.timeout_seconds:
                extracted_params = self.storage.get(extracted_params_key)
                if extracted_params:
                    break
                await asyncio.sleep(0.1)  # Проверяем каждые 0.1 секунды

            if extracted_params:
                trace.append("Received parameters from thermo_agent")

                # Шаг 2: Отправляем параметры sql_agent
                if extracted_params.get("sql_query_hint"):
                    sql_message_id = self.storage.send_message(
                        source_agent=self.agent_id,
                        target_agent="sql_agent",
                        message_type="generate_query",
                        payload={
                            "sql_hint": extracted_params["sql_query_hint"],
                            "parameters": extracted_params,
                        },
                    )
                    trace.append(f"Sent message to sql_agent: {sql_message_id}")

                    # Ждем ответа от sql_agent
                    sql_result_key = f"sql_result_{sql_message_id}"
                    sql_result = None
                    sql_start_time = asyncio.get_event_loop().time()
                    while (
                        asyncio.get_event_loop().time() - sql_start_time
                    ) < self.config.timeout_seconds:
                        sql_result = self.storage.get(sql_result_key)
                        if sql_result:
                            break
                        await asyncio.sleep(0.1)

                    if sql_result:
                        trace.append("Received SQL query from sql_agent")

                        # Собираем полный результат
                        return OrchestratorResponse(
                            success=True,
                            result={
                                "extracted_parameters": extracted_params,
                                "sql_query": sql_result.get("sql_query"),
                                "explanation": sql_result.get("explanation"),
                                "expected_columns": sql_result.get("expected_columns"),
                            },
                            trace=trace,
                        )
                    else:
                        trace.append("SQL agent response not ready")
                        # Логируем в сессионный лог
                        if self.config.session_logger:
                            self.config.session_logger.log_error(
                                "SQL agent did not respond to orchestrator"
                            )
                        return OrchestratorResponse(
                            success=False,
                            result={},
                            errors=["SQL agent did not respond"],
                            trace=trace,
                        )
                else:
                    # Только извлечение параметров, SQL не требуется
                    return OrchestratorResponse(
                        success=True,
                        result={"extracted_parameters": extracted_params},
                        trace=trace,
                    )
            else:
                trace.append("Thermo agent response not ready")
                # Логируем в сессионный лог
                if self.config.session_logger:
                    self.config.session_logger.log_error(
                        "Thermo agent did not respond to orchestrator"
                    )
                return OrchestratorResponse(
                    success=False,
                    result={},
                    errors=["Thermo agent did not respond"],
                    trace=trace,
                )
        except Exception as e:
            self.logger.error(f"Error processing request: {e}")
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
