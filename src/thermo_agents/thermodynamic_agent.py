"""
Инкапсулированный термодинамический агент.

Работает независимо через систему хранилища, не вызывается напрямую.
Слушает сообщения из хранилища и отвечает через него же.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .agent_storage import AgentStorage, get_storage
from .operations import OperationType
from .prompts import EXTRACT_INPUTS_PROMPT
from .thermo_agents_logger import SessionLogger


class ExtractedParameters(BaseModel):
    """Извлеченные параметры из запроса пользователя."""

    intent: str  # "lookup", "calculation", "reaction", "comparison"
    compounds: List[str]  # Химические формулы (включая все реагенты и продукты)
    temperature_k: float  # Температура в Кельвинах
    temperature_range_k: List[float]  # Диапазон температур [min, max]
    phases: List[str]  # Фазовые состояния ["s", "l", "g", "aq"]
    properties: List[str]  # Требуемые свойства ["basic", "all", "thermal"]
    sql_query_hint: str  # Подсказка для генерации SQL
    reaction_equation: Optional[str] = None  # Уравнение реакции (для intent="reaction")


class IndividualSearchRequest(BaseModel):
    """Запрос на индивидуальный поиск соединений."""

    compounds: List[str]  # Список соединений для поиска
    common_params: Dict  # Общие параметры (температура, фазы)
    search_strategy: str  # Стратегия поиска
    correlation_id: str  # ID для корреляции
    original_query: str  # Оригинальный запрос пользователя


class IndividualCompoundResult(BaseModel):
    """Результат поиска для одного соединения."""

    compound: str  # Химическая формула
    search_results: List[Dict]  # Результаты поиска
    selected_records: List[Dict]  # Отобранные записи
    confidence: float  # Уверенность в результате
    errors: List[str]  # Ошибки поиска


class AggregatedResults(BaseModel):
    """Агрегированные результаты по всем соединениям."""

    individual_results: List[IndividualCompoundResult]  # Результаты по веществам
    summary_table: List[Dict]  # Сводная таблица
    overall_confidence: float  # Общая уверенность
    missing_compounds: List[str]  # Отсутствующие вещества
    warnings: List[str]  # Предупреждения
    data_completeness_status: str = "complete"  # "complete" или "incomplete"
    is_complete_reaction: bool = True  # True если все данные найдены


@dataclass
class ThermoAgentConfig:
    """Конфигурация термодинамического агента."""

    agent_id: str = "thermo_agent"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 1.0  # Интервал проверки новых сообщений (секунды)
    max_retries: int = 4


class ThermodynamicAgent:
    """
    Инкапсулированный термодинамический агент.

    Работает автономно:
    - Слушает входящие сообщения из хранилища
    - Обрабатывает запросы на извлечение параметров
    - Отправляет результаты обратно через хранилище
    - Не имеет прямых зависимостей от других агентов
    """

    def __init__(self, config: ThermoAgentConfig):
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
                "capabilities": [
                    "extract_parameters",
                    "normalize_formulas",
                    "convert_temperature",
                ],
            },
        )

        self.logger.info(f"ThermodynamicAgent '{self.agent_id}' initialized")

    def _initialize_agent(self) -> Agent:
        """Создание PydanticAI агента для извлечения параметров."""
        provider = OpenAIProvider(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )

        model = OpenAIChatModel(self.config.llm_model, provider=provider)

        agent = Agent(
            model,
            deps_type=ThermoAgentConfig,
            output_type=ExtractedParameters,
            system_prompt=EXTRACT_INPUTS_PROMPT,
            retries=self.config.max_retries,
        )

        # Добавляем инструменты для работы с хранилищем
        @agent.tool
        async def save_to_storage(
            ctx: RunContext[ThermoAgentConfig],
            key: str,
            value: Dict,
            ttl: Optional[int] = None,
        ) -> bool:
            """Сохранить данные в хранилище."""
            ctx.deps.storage.set(key, value, ttl)
            ctx.deps.logger.debug(f"Saved to storage: {key}")
            return True

        @agent.tool
        async def load_from_storage(
            ctx: RunContext[ThermoAgentConfig], key: str
        ) -> Optional[Dict]:
            """Загрузить данные из хранилища."""
            value = ctx.deps.storage.get(key)
            ctx.deps.logger.debug(f"Loaded from storage: {key} = {value}")
            return value

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
                    self.agent_id, message_type="extract_parameters"
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
        # Используем операцию для логирования
        operation_context = None
        if self.config.session_logger and self.config.session_logger.is_operations_enabled():
            operation_context = self.config.session_logger.create_operation_context(
                agent_name=self.agent_id,
                operation_type=OperationType.EXTRACT_PARAMETERS,
                source_agent=message.source_agent,
                correlation_id=message.id,
            )
            operation_context.set_storage_snapshot_provider(lambda: self.storage.get_storage_snapshot(include_content=True))
            operation = operation_context.__enter__()
        else:
            operation = None

        try:
            # Извлекаем запрос пользователя из сообщения
            user_query = message.payload.get("user_query")
            if not user_query:
                raise ValueError("No user_query in message payload")

            # Устанавливаем входные данные для операции
            input_data = {"user_query": user_query[:200]}  # Ограничиваем для лога
            if operation:
                operation.set_input_data(input_data)

            # Извлекаем параметры используя PydanticAI агента
            try:
                self.logger.info(f"Starting parameter extraction for query: {user_query[:100]}...")
                # Увеличиваем таймаут до 30 секунд с учетом network задержек
                import asyncio
                result = await asyncio.wait_for(
                    self.agent.run(user_query, deps=self.config),
                    timeout=30.0  # 30 секунд на ответ модели + network
                )
                extracted_params = result.output

                self.logger.info(
                    f"Successfully extracted parameters: {extracted_params.intent}, compounds: {extracted_params.compounds}"
                )

                # Дополнительное логирование для реакции
                if extracted_params.intent == "reaction" and extracted_params.reaction_equation:
                    if self.config.session_logger:
                        self.config.session_logger.log_info(f"EXTRACTED REACTION: {extracted_params.reaction_equation}")
                    self.logger.info(f"Extracted reaction equation: {extracted_params.reaction_equation}")

                # TEMPORARY DEBUG LOGGING - TO BE REMOVED LATER
                # Логируем извлеченные параметры
                if self.config.session_logger:
                    # Логируем базовые параметры
                    extraction_metadata = {
                        "query_intent": extracted_params.intent,
                        "compounds_count": len(extracted_params.compounds),
                        "compounds": ", ".join(extracted_params.compounds),
                        "temperature_celsius": round(extracted_params.temperature_k - 273.15, 2),
                        "temperature_k": extracted_params.temperature_k,
                        "temperature_range_celsius": f"{round(extracted_params.temperature_range_k[0] - 273.15, 2)}-{round(extracted_params.temperature_range_k[1] - 273.15, 2)}",
                        "temperature_range_k": f"{extracted_params.temperature_range_k[0]}-{extracted_params.temperature_range_k[1]}",
                        "phases": ", ".join(extracted_params.phases),
                        "properties": ", ".join(extracted_params.properties),
                        "has_sql_hint": bool(extracted_params.sql_query_hint)
                    }
                    self.config.session_logger.log_search_metadata(extraction_metadata, "EXTRACTED PARAMETERS")

                    # Если это реакция, логируем детальную информацию о соединениях
                    if extracted_params.intent == "reaction" and extracted_params.compounds:
                        # Создаем заготовку для будущих результатов поиска
                        compound_placeholders = []
                        for compound in extracted_params.compounds:
                            compound_placeholders.append({
                                "compound": compound,
                                "selected_records": [],  # Будет заполнено позже
                                "confidence": 0.0       # Будет рассчитано позже
                            })

                        self.config.session_logger.log_compound_data_table(
                            compound_placeholders,
                            "COMPOUNDS TO SEARCH (pre-search status)"
                        )
            except asyncio.TimeoutError:
                self.logger.error(f"Network timeout after 30 seconds - cannot extract parameters")
                raise ValueError(f"Не удалось извлечь параметры: превышено время ожидания ответа от модели. Попробуйте упростить запрос.")
            except Exception as e:
                # При любой ошибке LLM сообщаем о невозможности извлечения параметров
                error_msg = str(e)
                self.logger.error(f"Parameter extraction failed: {error_msg}")

                # Дополнительное логирование для трассировки
                if self.config.session_logger:
                    self.config.session_logger.log_error(f"EXTRACTION FAILED: {error_msg[:200]}")

                # Определяем тип ошибки для более понятного сообщения пользователю
                if "status_code: 401" in error_msg or "No auth credentials" in error_msg:
                    user_msg = "Ошибка аутентификации: проверьте API ключ для доступа к модели."
                    self.logger.error("Authentication error detected - missing or invalid API key")
                elif "status_code: 429" in error_msg or "rate limit" in error_msg.lower():
                    user_msg = "Превышен лимит запросов к модели. Попробуйте повторить запрос позже."
                    self.logger.error("Rate limit error detected - too many requests")
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    user_msg = "Сетевая ошибка: проверьте подключение к интернету."
                    self.logger.error("Network connectivity error detected")
                elif "timeout" in error_msg.lower():
                    user_msg = "Превышено время ожидания ответа от модели. Попробуйте упростить запрос."
                    self.logger.error("Timeout error detected - possible network issues")
                else:
                    user_msg = f"Не удалось извлечь параметры: {error_msg[:100]}..."
                    self.logger.error(f"Unknown error type: {type(e).__name__}")

                raise ValueError(user_msg)

            # Сохраняем результат в хранилище
            result_key = f"thermo_result_{message.id}"
            self.storage.set(result_key, extracted_params.model_dump(), ttl_seconds=600)

            # Отправляем ответное сообщение
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="response",
                correlation_id=message.id,
                payload={
                    "status": "success",
                    "result_key": result_key,
                    "extracted_params": extracted_params.model_dump(),
                },
            )

            # Готовим результат для логирования операции
            operation_result = {
                "intent": extracted_params.intent,
                "compounds_count": len(extracted_params.compounds),
                "compounds": extracted_params.compounds[:5],  # Максимум 5 соединений в логе
                "temperature_k": extracted_params.temperature_k,
                "has_sql_hint": bool(extracted_params.sql_query_hint),
                "result_key": result_key,
            }

            # Добавляем информацию о маршрутизации
            next_agent = None
            if extracted_params.compounds and extracted_params.intent == "reaction":
                next_agent = "individual_search_agent"
            elif extracted_params.sql_query_hint:
                next_agent = "sql_agent"

            if next_agent:
                operation_result["next_agent"] = next_agent

            # Устанавливаем результат операции
            if operation_context:
                operation_context.set_result(operation_result)

            # Дополнительная информация в лог (теперь это часть операции)
            if self.config.session_logger:
                self.config.session_logger.log_info(f"EXTRACTION COMPLETE: {extracted_params.intent}, {len(extracted_params.compounds)} compounds")

            # Если найдены соединения и нужна индивидуальная обработка, отправляем запрос Individual Search Agent
            if extracted_params.compounds and extracted_params.intent == "reaction":
                # Создаем запрос на индивидуальный поиск
                search_request = IndividualSearchRequest(
                    compounds=extracted_params.compounds,
                    common_params={
                        "temperature_k": extracted_params.temperature_k,
                        "temperature_range_k": extracted_params.temperature_range_k,
                        "phases": extracted_params.phases,
                        "properties": extracted_params.properties,
                    },
                    search_strategy="individual_compound_search",
                    correlation_id=message.id,
                    original_query=user_query,
                )

                # Отправляем запрос Individual Search Agent
                individual_search_message_id = self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="individual_search_agent",
                    message_type="individual_search_request",
                    correlation_id=message.id,
                    payload={
                        "search_request": search_request.model_dump(),
                        "extracted_params": extracted_params.model_dump(),
                        "original_query": user_query,
                    },
                )
                self.logger.info(f"Forwarded to Individual Search Agent: {individual_search_message_id}")

            # Если нужна генерация SQL (для нерекакционных запросов), отправляем сообщение SQL агенту
            elif extracted_params.sql_query_hint:
                sql_message_id = self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="sql_agent",
                    message_type="generate_query",
                    correlation_id=message.id,
                    payload={
                        "sql_hint": extracted_params.sql_query_hint,
                        "extracted_params": extracted_params.model_dump(),
                        "original_query": user_query,
                    },
                )
                self.logger.info(f"Forwarded to SQL agent: {sql_message_id}")

            # Завершаем операцию успешно
            if operation_context:
                operation_context.__exit__(None, None, None)

        except Exception as e:
            self.logger.error(f"Error processing message {message.id}: {e}")

            # Отправляем сообщение об ошибке
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="error",
                correlation_id=message.id,
                payload={"status": "error", "error": str(e)},
            )

            # Завершаем операцию с ошибкой
            if operation_context:
                operation_context.__exit__(type(e), e, e.__traceback__)

            # Дополнительная информация в лог (теперь это часть операции)
            if self.config.session_logger:
                self.config.session_logger.log_info(f"EXTRACTION ERROR: {str(e)[:100]}")

    async def process_single_query(self, user_query: str) -> ExtractedParameters:
        """
        Обработать одиночный запрос (для совместимости и тестирования).

        Args:
            user_query: Запрос пользователя

        Returns:
            Извлеченные параметры

        Raises:
            ValueError: Если не удалось извлечь параметры после повторных попыток
        """
        max_retries = 3
        base_timeout = 30.0

        for attempt in range(max_retries):
            try:
                import asyncio
                timeout = base_timeout * (attempt + 1)  # Увеличиваем таймаут с каждой попыткой

                result = await asyncio.wait_for(
                    self.agent.run(user_query, deps=self.config),
                    timeout=timeout
                )
                return result.output

            except asyncio.TimeoutError:
                self.logger.error(f"Timeout in single query processing (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise ValueError(f"Не удалось извлечь параметры: превышено время ожидания ответа от модели после {max_retries} попыток. Попробуйте упростить запрос.")
                await asyncio.sleep(1)  # Небольшая задержка перед повторной попыткой

            except Exception as e:
                self.logger.error(f"Error in single query processing (attempt {attempt + 1}/{max_retries}): {e}")
                error_msg = str(e)

                # Дополнительное логирование для трассировки
                if self.config.session_logger:
                    self.config.session_logger.log_error(f"SINGLE QUERY FAILED (attempt {attempt + 1}): {error_msg[:200]}")

                # Определяем тип ошибки для более понятного сообщения
                if "status_code: 401" in error_msg or "No auth credentials" in error_msg:
                    raise ValueError("Ошибка аутентификации: проверьте API ключ для доступа к модели.")
                elif "status_code: 429" in error_msg or "rate limit" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Превышен лимит запросов к модели. Попробуйте повторить запрос позже.")
                    await asyncio.sleep(5)  # Ждем перед повторной попыткой при rate limit
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Сетевая ошибка: проверьте подключение к интернету.")
                    await asyncio.sleep(2)  # Ждем перед повторной попыткой при проблемах сети
                elif "timeout" in error_msg.lower():
                    if attempt == max_retries - 1:
                        raise ValueError("Превышено время ожидания ответа от модели. Попробуйте упростить запрос.")
                    await asyncio.sleep(1)
                else:
                    if attempt == max_retries - 1:
                        raise ValueError(f"Не удалось извлечь параметры после {max_retries} попыток: {error_msg[:100]}...")
                    await asyncio.sleep(1)

        # Этот код не должен быть достигнут, так как все ошибки обрабатываются выше
        raise ValueError(f"Не удалось извлечь параметры после {max_retries} попыток.")

  
    def get_status(self) -> Dict:
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {"agent_id": self.agent_id, "running": self.running, "session": session}


# =============================================================================
# ФАБРИКТНЫЕ ФУНКЦИИ
# =============================================================================


def create_thermo_agent(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str = "openai:gpt-4o",
    storage: Optional[AgentStorage] = None,
    logger: Optional[logging.Logger] = None,
) -> ThermodynamicAgent:
    """
    Создать термодинамического агента.

    Args:
        llm_api_key: API ключ для LLM
        llm_base_url: URL для LLM API
        llm_model: Модель LLM
        storage: Хранилище (или будет использовано глобальное)
        logger: Логгер

    Returns:
        Настроенный термодинамический агент
    """
    config = ThermoAgentConfig(
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        storage=storage or get_storage(),
        logger=logger or logging.getLogger(__name__),
    )

    return ThermodynamicAgent(config)


async def run_thermo_agent_standalone(config: ThermoAgentConfig):
    """
    Запустить агента в standalone режиме для тестирования.

    Args:
        config: Конфигурация агента
    """
    agent = ThermodynamicAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()
        print("Agent stopped")
