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
        self.logger.info(
            f"Processing message: {message.id} from {message.source_agent}"
        )

        try:
            # Извлекаем запрос пользователя из сообщения
            user_query = message.payload.get("user_query")
            if not user_query:
                raise ValueError("No user_query in message payload")

            # Извлекаем параметры используя PydanticAI агента
            try:
                self.logger.info(f"Starting parameter extraction for query: {user_query[:100]}...")
                # Увеличиваем таймаут до 10 секунд для LLM ответа
                import asyncio
                result = await asyncio.wait_for(
                    self.agent.run(user_query, deps=self.config),
                    timeout=10.0  # 10 секунд на ответ модели
                )
                extracted_params = result.output

                self.logger.info(
                    f"Successfully extracted parameters: {extracted_params.intent}, compounds: {extracted_params.compounds}"
                )
            except asyncio.TimeoutError:
                self.logger.error(f"LLM timeout after 10 seconds, using fallback extraction")
                extracted_params = self._fallback_extraction(user_query)
            except Exception as e:
                # Обрабатываем различные типы ошибок PydanticAI
                error_msg = str(e)
                self.logger.error(f"Parameter extraction error: {error_msg}")

                if "finish_reason" in error_msg and "None" in error_msg:
                    self.logger.error(f"PydanticAI validation error for finish_reason=None, using fallback")
                    # Используем базовые параметры при ошибке валидации
                    extracted_params = ExtractedParameters(
                        intent="lookup",  # Предполагаем, что это поиск по умолчанию
                        compounds=[],  # Пустой список соединений, будет заполнен позже
                        temperature_k=298.15,
                        temperature_range_k=[200, 2000],
                        phases=[],
                        properties=["basic"],
                        sql_query_hint=f"Error occurred during parameter extraction, query: {user_query}",
                        reaction_equation=None,
                    )
                elif "Exceeded maximum retries" in error_msg:
                    self.logger.error(f"PydanticAI exceeded retries, using fallback extraction")
                    # Пытаемся извлечь базовые параметры из запроса
                    extracted_params = self._fallback_extraction(user_query)
                elif "validation" in error_msg.lower():
                    self.logger.error(f"PydanticAI validation error, using fallback")
                    extracted_params = self._fallback_extraction(user_query)
                else:
                    # Для других ошибок пробрасываем исключение дальше
                    self.logger.error(f"Unknown PydanticAI error, re-raising: {e}")
                    raise e

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

            # Логирование для сессии
            if self.config.session_logger:
                self.config.session_logger.log_extracted_parameters(extracted_params)

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

            if self.config.session_logger:
                self.config.session_logger.log_error(str(e))

    async def process_single_query(self, user_query: str) -> ExtractedParameters:
        """
        Обработать одиночный запрос (для совместимости и тестирования).

        Args:
            user_query: Запрос пользователя

        Returns:
            Извлеченные параметры
        """
        try:
            import asyncio
            result = await asyncio.wait_for(
                self.agent.run(user_query, deps=self.config),
                timeout=10.0  # 10 секунд на ответ модели
            )
            return result.output
        except Exception as e:
            self.logger.error(f"Error in single query processing: {e}")
            error_msg = str(e)

            # Обрабатываем ошибку PydanticAI с finish_reason=None
            if "finish_reason" in error_msg and "None" in error_msg:
                self.logger.error(f"PydanticAI validation error for finish_reason=None, using fallback: {e}")
                # Возвращаем базовые параметры с общим поиском
                return ExtractedParameters(
                    intent="lookup",  # Предполагаем, что это поиск по умолчанию
                    compounds=[],  # Пустой список соединений, будет заполнен позже
                    temperature_k=298.15,
                    temperature_range_k=[200, 2000],
                    phases=[],
                    properties=["basic"],
                    sql_query_hint=f"Error occurred during parameter extraction, query: {user_query}",
                    reaction_equation=None,
                )
            else:
                # Возвращаем базовые параметры в случае других ошибок
                return ExtractedParameters(
                    intent="unknown",
                    compounds=[],
                    temperature_k=298.15,
                    temperature_range_k=[200, 2000],
                    phases=[],
                    properties=["basic"],
                    sql_query_hint="Error occurred during parameter extraction",
                )

    def _fallback_extraction(self, user_query: str) -> ExtractedParameters:
        """
        Резервное извлечение параметров при сбоях PydanticAI.

        Args:
            user_query: Запрос пользователя

        Returns:
            Базовые ExtractedParameters
        """
        self.logger.warning(f"Using fallback extraction for query: {user_query[:100]}...")

        # Простая эвристика для определения intent
        query_lower = user_query.lower()
        if any(word in query_lower for word in ['реакц', 'взаимод', 'превращ', 'получ', 'образует']):
            intent = "reaction"
        elif any(word in query_lower for word in ['температур', 'когда', 'при какой', 'услов']):
            intent = "calculation"
        else:
            intent = "lookup"

        # Базовая попытка извлечь химические соединения (простые паттерны)
        import re

        # Ищем простые химические формулы
        compound_pattern = r'\b([A-Z][a-z]?[0-9]*[A-Za-z0-9]*)\b'
        compounds = list(set(re.findall(compound_pattern, user_query)))

        # Фильтруем очевидные не-химические слова
        stop_words = {'температура', 'при', 'какой', 'реакция', 'взаимодействие', 'как', 'какая'}
        compounds = [c for c in compounds if c not in stop_words and len(c) > 1]

        # Температура по умолчанию
        temperature_k = 298.15

        # Ищем температуру в запросе
        temp_pattern = r'(\d+)\s*°?[CcC]'
        temp_match = re.search(temp_pattern, user_query)
        if temp_match:
            temp_c = float(temp_match.group(1))
            temperature_k = temp_c + 273.15

        return ExtractedParameters(
            intent=intent,
            compounds=compounds[:5],  # Максимум 5 соединений
            temperature_k=temperature_k,
            temperature_range_k=[temperature_k - 100, temperature_k + 200],
            phases=['s'] * len(compounds),  # По умолчанию твердые
            properties=['all'] if intent == 'reaction' else ['basic'],
            sql_query_hint=f"Fallback extraction: {user_query[:100]}",
            reaction_equation=None,
        )

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
