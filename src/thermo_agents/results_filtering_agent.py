"""
Агент для фильтрации и отбора наиболее релевантных результатов из базы данных.

Отвечает за:
- Температурную фильтрацию записей (частичное перекрытие диапазонов)
- LLM-анализ записей для выбора наиболее подходящих для каждого вещества и фазы
- Формирование финальной таблицы с релевантными данными
"""

from __future__ import annotations

import asyncio
import logging
import yaml
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .agent_storage import AgentStorage, get_storage
from .operations import OperationType
from .prompts import RESULT_FILTER_ENGLISH_PROMPT, SQL_FILTER_GENERATION_PROMPT
from .thermo_agents_logger import SessionLogger
from .timeout_manager import get_timeout_manager, OperationType as TimeoutOperationType


class SelectedEntry(BaseModel):
    """Выбранная запись с обоснованием."""
    compound: str
    selected_id: int
    reasoning: str

class FilteredResult(BaseModel):
    """Результат фильтрации записей."""

    selected_entries: List[SelectedEntry]  # Выбранные записи с ID
    phase_determinations: Dict[str, Dict[str, Any]]  # Анализ фаз
    missing_compounds: List[str]  # Отсутствующие соединения
    excluded_entries_count: int  # Количество исключенных записей
    overall_confidence: float  # Общая уверенность
    warnings: List[str]  # Предупреждения
    filter_summary: str  # Резюме фильтрации


class SQLFilterResult(BaseModel):
    """Результат генерации SQL WHERE условий."""

    sql_where_conditions: List[str]  # Сгенерированные WHERE условия
    order_by_clauses: List[str]  # ORDER BY условия
    limit_values: List[int]  # LIMIT значения
    reasoning: str  # Обоснование стратегии фильтрации
    phase_analysis: Dict[str, Any]  # Анализ фаз
    expected_results: Dict[str, Any]  # Ожидаемые результаты
    overall_confidence: float  # Общая уверенность
    warnings: List[str]  # Предупреждения


@dataclass
class ResultsFilteringAgentConfig:
    """Конфигурация агента фильтрации результатов."""

    agent_id: str = "results_filtering_agent"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 0.05  # Оптимизировано до 0.05с для немедленной обработки
    max_retries: int = 2  # Обновлено до 2 попыток согласно новой политике
    filtering_timeout: int = 60  # Уменьшено с 240 до 60 секунд
    sql_generation_timeout: int = 30  # Уменьшено с 45 до 30 секунд
    llm_filtering_timeout: int = 45  # Уменьшено с 60 до 45 секунд
    max_retry_attempts: int = 1  # Максимальное количество повторных запросов (1 retry = 2 попытки)


class ResultsFilteringAgent:
    """
    Агент для интеллектуальной фильтрации результатов базы данных.

    Обязанности:
    - Фильтрация записей по температурному диапазону (частичное перекрытие)
    - LLM-анализ для выбора наиболее релевантных записей для каждого вещества
    - Обеспечение покрытия всего запрашиваемого температурного диапазона
    - Формирование итоговой таблицы с обоснованием выбора
    """

    def __init__(self, config: ResultsFilteringAgentConfig):
        """Инициализация агента фильтрации результатов."""
        self.config = config
        self.agent_id = config.agent_id
        self.storage = config.storage
        self.logger = config.logger
        self.running = False

        # Время запуска для мониторинга
        import time
        self._start_time = time.time()

        # Инициализация TimeoutManager
        self.timeout_manager = get_timeout_manager(
            logger=self.config.logger,
            session_logger=self.config.session_logger,
            llm_base_url=self.config.llm_base_url
        )

        # Инициализация PydanticAI агента
        self.agent = self._initialize_agent()

        # Регистрация в хранилище
        self.storage.start_session(
            self.agent_id,
            {
                "status": "initialized",
                "capabilities": ["filter_results", "temperature_analysis", "compound_selection"],
                "configuration": {
                    "filtering_timeout": config.filtering_timeout,
                    "max_retry_attempts": config.max_retry_attempts,
                }
            },
        )

        self.logger.info(f"ResultsFilteringAgent '{self.agent_id}' initialized with timeout={config.filtering_timeout}s, max_retries={config.max_retry_attempts}")

        # Логируем инициализацию в сессионный логгер
        if self.config.session_logger:
            self.config.session_logger.log_info(f"AGENT INITIALIZED: {self.agent_id}, filtering_timeout={config.filtering_timeout}s")

    def _initialize_agent(self) -> Agent:
        """Создание PydanticAI агента для фильтрации результатов."""
        provider = OpenAIProvider(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )

        model = OpenAIChatModel(self.config.llm_model, provider=provider)

        system_prompt = RESULT_FILTER_ENGLISH_PROMPT

        agent = Agent(
            model,
            deps_type=ResultsFilteringAgentConfig,
            output_type=FilteredResult,
            system_prompt=system_prompt,
            retries=self.config.max_retries,
        )

        return agent

    async def start(self):
        """Запустить агента в режиме прослушивания сообщений."""
        self.running = True
        self.storage.update_session(self.agent_id, {"status": "running"})
        self.logger.info(f"Agent '{self.agent_id}' started listening for messages")

        while self.running:
            try:
                # Получаем сообщения обоих типов
                messages_filter = self.storage.receive_messages(
                    self.agent_id, message_type="filter_results"
                )
                messages_individual = self.storage.receive_messages(
                    self.agent_id, message_type="filter_individual_results"
                )

                # Объединяем сообщения
                all_messages = messages_filter + messages_individual

                # Обрабатываем каждое сообщение
                for message in all_messages:
                    await self._process_message(message)

                # Ждем перед следующей проверкой
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.logger.error(f"Error in results filtering agent loop: {e}")
                await asyncio.sleep(self.config.poll_interval * 2)

    async def stop(self):
        """Остановить агента."""
        self.running = False
        self.storage.update_session(self.agent_id, {"status": "stopped"})
        self.logger.info(f"Agent '{self.agent_id}' stopped")

    async def _process_message(self, message, retry_count: int = 0):
        """
        Обработать входящее сообщение для фильтрации результатов с механизмом повторных запросов.

        Args:
            message: Входящее сообщение
            retry_count: Текущая попытка повторного выполнения (0 для первой попытки)
        """
        # Отслеживаем время начала обработки для механизма abandon
        start_time = asyncio.get_event_loop().time()

        # Проверяем, не превышен ли общий таймаут для этого запроса
        if await self._abandon_request_if_timeout(message.correlation_id, start_time):
            return

        # Используем операцию для логирования
        operation_context = None
        if self.config.session_logger and self.config.session_logger.is_operations_enabled():
            operation_type = OperationType.INDIVIDUAL_FILTER if message.message_type == "filter_individual_results" else OperationType.FILTER_RESULTS
            operation_context = self.config.session_logger.create_operation_context(
                agent_name=self.agent_id,
                operation_type=operation_type,
                source_agent=message.source_agent,
                correlation_id=message.correlation_id,
            )
            operation_context.set_storage_snapshot_provider(lambda: self.storage.get_storage_snapshot(include_content=True))
            operation = operation_context.__enter__()
        else:
            operation = None

        # Логируем начало обработки с метриками
        self.logger.info(f"Processing filtering message {message.id} (attempt {retry_count + 1}, timeout: {self.config.filtering_timeout}s)")

        try:
            # Определяем тип сообщения
            message_type = message.message_type

            # Инициализируем extracted_params для использования в блоке finally/except
            extracted_params = {}

            if message_type == "filter_individual_results":
                # Индивидуальная фильтрация для одного соединения
                compound = message.payload.get("compound")
                common_params = message.payload.get("common_params", {})

                execution_result = message.payload.get("execution_result", {})
                if not execution_result.get("success"):
                    raise ValueError("No successful execution result to filter")

                rows = execution_result.get("rows", [])
                columns = execution_result.get("columns", [])
                target_temperature = common_params.get("temperature_k", 298.15)
                temperature_range = common_params.get("temperature_range_k", [298.15, 298.15])
                compounds = [compound]
                phases = common_params.get("phases", [])

                # Создаем extracted_params для совместимости
                extracted_params = {
                    "compounds": compounds,
                    "temperature_k": target_temperature,
                    "temperature_range_k": temperature_range,
                    "phases": phases
                }

                # Устанавливаем входные данные для операции
                input_data = {
                    "message_type": "individual",
                    "compound": compound,
                    "input_records": len(rows),
                    "target_temperature": target_temperature,
                    "phases": phases,
                }

                self.logger.info(f"Individual filtering for compound {compound}: {len(rows)} records")
                if self.config.session_logger:
                    self.config.session_logger.log_info(
                        f"INDIVIDUAL FILTERING START: {compound}, {len(rows)} records, target temp {target_temperature}K"
                    )
            else:
                # Стандартная фильтрация
                execution_result = message.payload.get("execution_result", {})
                extracted_params = message.payload.get("extracted_params", {})

                if not execution_result.get("success"):
                    raise ValueError("No successful execution result to filter")

                rows = execution_result.get("rows", [])
                columns = execution_result.get("columns", [])
                target_temperature = extracted_params.get("temperature_k", 298.15)
                temperature_range = extracted_params.get("temperature_range_k", [298.15, 298.15])
                compounds = extracted_params.get("compounds", [])
                phases = extracted_params.get("phases", [])

                # Устанавливаем входные данные для операции
                input_data = {
                    "message_type": "standard",
                    "compounds_count": len(compounds),
                    "input_records": len(rows),
                    "target_temperature": target_temperature,
                    "phases": phases,
                }

                self.logger.info(f"Filtering {len(rows)} records for {len(compounds)} compounds")
                if self.config.session_logger:
                    self.config.session_logger.log_info(
                        f"RESULTS FILTERING START: {len(rows)} records, target temp {target_temperature}K"
                    )

            # Устанавливаем входные данные для операции
            if operation:
                operation.set_input_data(input_data)

            # Шаг 1: Предварительная фильтрация по температурному диапазону
            temp_filtered_records = self._filter_by_temperature_range(
                rows, columns, temperature_range
            )

            self.logger.info(f"Temperature pre-filtering: {len(temp_filtered_records)} records remain")

            # Шаг 2: LLM-анализ для выбора наиболее релевантных записей
            if temp_filtered_records:
                # Логируем начало LLM фильтрации с метриками
                self.logger.info(f"Starting LLM filtering for {len(temp_filtered_records)} records, {len(compounds)} compounds")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"LLM FILTERING START: {len(temp_filtered_records)} records, compounds={compounds}")

                # Отслеживаем время выполнения
                llm_start_time = asyncio.get_event_loop().time()

                filtered_result = await self._llm_filter_records(
                    temp_filtered_records, columns, compounds, phases, temperature_range, target_temperature
                )

                # Логируем завершение с метриками производительности
                llm_elapsed = asyncio.get_event_loop().time() - llm_start_time
                self.logger.info(f"LLM filtering completed in {llm_elapsed:.2f}s: {len(filtered_result.selected_entries)} entries selected")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"LLM FILTERING COMPLETE: {llm_elapsed:.2f}s, {len(filtered_result.selected_entries)} selected")

                # Конвертируем selected_entries (ID) обратно в полные записи
                selected_records = self._convert_ids_to_records(filtered_result.selected_entries, temp_filtered_records)

                # Сохраняем результат в хранилище
                result_key = f"filtered_result_{message.id}"
                result_data = {
                    "filtered_result": filtered_result.model_dump(),
                    "selected_records": selected_records,  # Добавляем полные записи
                    "original_count": len(rows),
                    "temp_filtered_count": len(temp_filtered_records),
                    "final_count": len(selected_records),
                    "extracted_params": extracted_params,
                }

                self.storage.set(result_key, result_data, ttl_seconds=600)
                self.logger.info(f"Filtering result stored with key: {result_key}")

                # Логируем финальную отфильтрованную таблицу
                self._log_filtered_table(selected_records, filtered_result.filter_summary)

                # Определяем получателя ответа
                if message_type == "filter_individual_results":
                    # Для индивидуальных запросов отправляем Individual Search Agent
                    target_agent = "individual_search_agent"
                    response_message_type = "individual_filter_complete"
                    correlation_id = message.correlation_id
                else:
                    # Стандартные запросы отправляем SQL агенту
                    target_agent = "sql_agent"
                    response_message_type = "results_filtered"
                    correlation_id = message.correlation_id

                # Отправляем ответ
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent=target_agent,
                    message_type=response_message_type,
                    correlation_id=correlation_id,
                    payload={
                        "status": "success",
                        "result_key": result_key,
                        "filtered_result": filtered_result.model_dump(),
                        "search_results": temp_filtered_records,
                        "filtered_data": selected_records,
                        "confidence": self._calculate_individual_confidence(filtered_result, len(temp_filtered_records)),
                        "statistics": {
                            "original_count": len(rows),
                            "temp_filtered_count": len(temp_filtered_records),
                            "final_count": len(selected_records),
                        },
                    },
                )

                # Готовим результат для логирования операции
            operation_result = {
                "message_type": message_type,
                "input_records": len(rows),
                "temp_filtered_records": len(temp_filtered_records),
                "final_records": len(selected_records) if temp_filtered_records else 0,
                "result_key": result_key if temp_filtered_records else None,
                "target_agent": target_agent,
                "filtering_success": True,
            }

            if message_type == "individual":
                operation_result["compound"] = compound
            else:
                operation_result["compounds_count"] = len(compounds)

            # Устанавливаем результат операции
            if operation_context:
                operation_context.set_result(operation_result)

            self.logger.info(f"Filtering response sent to {target_agent}")

            # Завершаем операцию успешно
            if operation_context:
                operation_context.__exit__(None, None, None)

            else:
                # Нет записей после температурной фильтрации
                self.logger.warning("No records remain after temperature filtering")

                # Определяем получателя ответа
                if message_type == "filter_individual_results":
                    target_agent = "individual_search_agent"
                    response_message_type = "individual_filter_complete"
                else:
                    target_agent = "sql_agent"
                    response_message_type = "results_filtered"

                # Готовим результат операции (без результатов)
                operation_result = {
                    "message_type": message_type,
                    "input_records": len(rows),
                    "temp_filtered_records": 0,
                    "final_records": 0,
                    "filtering_success": False,
                    "reason": "No records after temperature filtering",
                }

                if message_type == "individual":
                    operation_result["compound"] = compound
                else:
                    operation_result["compounds_count"] = len(compounds)

                # Устанавливаем результат операции
                if operation_context:
                    operation_context.set_result(operation_result)

                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent=target_agent,
                    message_type=response_message_type,
                    correlation_id=message.correlation_id,
                    payload={
                        "status": "no_results",
                        "error": "No records found in the specified temperature range",
                        "search_results": [],
                        "filtered_data": [],
                        "confidence": 0.0,
                        "statistics": {
                            "original_count": len(rows),
                            "temp_filtered_count": 0,
                            "final_count": 0,
                        },
                    },
                )

                # Завершаем операцию успешно (но без результатов)
                if operation_context:
                    operation_context.__exit__(None, None, None)

        except Exception as e:
            self.logger.error(f"Error processing filtering message {message.id} (attempt {retry_count + 1}): {e}")

            # Используем TimeoutManager для определения возможности retry
            should_retry = self.timeout_manager.is_retryable_error(e) and retry_count < self.config.max_retry_attempts

            if should_retry:
                # Рассчитываем задержку с exponential backoff
                retry_delay = self.timeout_manager._calculate_retry_delay(
                    type('Config', (), {
                        'backoff_base': 2.0,
                        'jitter': True,
                        'base_timeout': self.config.filtering_timeout
                    })(),
                    retry_count
                )

                self.logger.info(f"Retrying filtering request {message.id} after {retry_delay:.1f}s (attempt {retry_count + 2})")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"FILTERING RETRY: {message.id}, attempt {retry_count + 2}, delay {retry_delay:.1f}s")

                # Отправляем запрос на повторное выполнение
                await asyncio.sleep(retry_delay)
                await self._process_message(message, retry_count + 1)
                return
            else:
                self.logger.info(f"Request {message.id} will not be retried: {type(e).__name__}")
                if self.config.session_logger:
                    self.config.session_logger.log_info(f"FILTERING NO RETRY: {message.id}, error {type(e).__name__}")

            # Завершаем операцию с ошибкой после всех попыток
            if operation_context:
                operation_context.__exit__(type(e), e, e.__traceback__)

            # Определяем получателя для ошибки
            if message.message_type == "filter_individual_results":
                target_agent = "individual_search_agent"
                response_message_type = "individual_filter_complete"
            else:
                target_agent = "sql_agent"
                response_message_type = "results_filtered"

            # Отправляем сообщение об ошибке с информацией о попытках
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=target_agent,
                message_type=response_message_type,
                correlation_id=message.correlation_id,
                payload={
                    "status": "error",
                    "error": f"{str(e)} (after {retry_count + 1} attempt{'s' if retry_count > 0 else ''})",
                    "search_results": [],
                    "filtered_data": [],
                    "confidence": 0.0,
                    "retry_attempts": retry_count + 1,
                },
            )

            if self.config.session_logger:
                self.config.session_logger.log_error(f"FILTERING ERROR (final): {str(e)} after {retry_count + 1} attempts")

    def _should_retry_request(self, error: Exception, retry_count: int) -> bool:
        """
        Определяет, нужно ли повторять запрос на основе типа ошибки и количества попыток.

        Args:
            error: Исключение, возникшее при обработке
            retry_count: Текущая попытка (0-based)

        Returns:
            True если запрос нужно повторить
        """
        # Проверяем лимит повторных запросов из конфигурации
        if retry_count >= self.config.max_retry_attempts:
            return False

        # Не повторяем при критических ошибках
        non_retryable_errors = (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            SyntaxError,
        )

        # Не повторяем при ошибках данных
        if isinstance(error, non_retryable_errors):
            self.logger.debug(f"Non-retryable error {type(error).__name__}: {str(error)[:50]}...")
            return False

        # Повторяем при таймаутах и сетевых ошибках
        if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
            self.logger.debug(f"Retryable timeout error: {str(error)[:50]}...")
            return True

        # Повторяем при ошибках LLM API
        error_str = str(error).lower()
        retryable_keywords = [
            "timeout", "connection", "network", "rate limit", "api",
            "http", "500", "502", "503", "504", "unavailable"
        ]

        if any(keyword in error_str for keyword in retryable_keywords):
            self.logger.debug(f"Retryable API error: {str(error)[:50]}...")
            return True

        # Не повторяем при ошибках SQL синтаксиса
        if "invalid syntax" in error_str or "sql error" in error_str:
            self.logger.debug(f"Non-retryable SQL error: {str(error)[:50]}...")
            return False

        # Повторяем при неизвестных ошибках в рамках лимита
        self.logger.debug(f"Unknown error type {type(error).__name__}, allowing retry within limits")
        return True

    async def _abandon_request_if_timeout(self, correlation_id: str, start_time: float) -> bool:
        """
        Механизм abandon-запроса при превышении общего таймаута.

        Args:
            correlation_id: ID запроса для отслеживания
            start_time: Время начала запроса

        Returns:
            True если запрос был отменен из-за таймаута
        """
        elapsed = asyncio.get_event_loop().time() - start_time

        if elapsed > self.config.filtering_timeout:
            self.logger.warning(f"Request {correlation_id} abandoned after {elapsed:.1f}s (timeout: {self.config.filtering_timeout}s)")

            # Отправляем сообщение об отмене запроса
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent="individual_search_agent",  # Отправляем Individual Search Agent
                message_type="filtering_abandoned",
                correlation_id=correlation_id,
                payload={
                    "status": "abandoned",
                    "reason": f"Request timeout after {elapsed:.1f}s",
                    "timeout_seconds": self.config.filtering_timeout,
                    "elapsed_seconds": elapsed,
                },
            )

            if self.config.session_logger:
                self.config.session_logger.log_info(f"REQUEST ABANDONED: {correlation_id} after {elapsed:.1f}s")

            return True

        return False

    def _filter_by_temperature_range(self, rows: List[List], columns: List[str], temperature_range: List[float]) -> List[Dict[str, Any]]:
        """
        Фильтрация записей по температурному диапазону (частичное перекрытие).

        Args:
            rows: Строки данных
            columns: Названия колонок
            temperature_range: Запрашиваемый температурный диапазон [min, max]

        Returns:
            Список записей с частичным перекрытием температурного диапазона
        """
        if not rows or not columns:
            return []

        # Найдем индексы колонок Tmin и Tmax
        tmin_idx = None
        tmax_idx = None

        for i, col in enumerate(columns):
            if col.lower() == 'tmin':
                tmin_idx = i
            elif col.lower() == 'tmax':
                tmax_idx = i

        if tmin_idx is None or tmax_idx is None:
            self.logger.warning("Temperature columns (Tmin/Tmax) not found, returning all records")
            # Конвертируем в словари
            return [dict(zip(columns, row)) for row in rows]

        target_min, target_max = temperature_range
        filtered_records = []

        for row in rows:
            try:
                record_tmin = float(row[tmin_idx]) if row[tmin_idx] is not None else 0
                record_tmax = float(row[tmax_idx]) if row[tmax_idx] is not None else 9999

                # Проверяем частичное перекрытие диапазонов
                # Перекрытие есть если: record_tmin <= target_max AND record_tmax >= target_min
                if record_tmin <= target_max and record_tmax >= target_min:
                    record_dict = dict(zip(columns, row))
                    filtered_records.append(record_dict)

            except (ValueError, TypeError, IndexError):
                # Если не удается конвертировать температуры, оставляем запись
                record_dict = dict(zip(columns, row))
                filtered_records.append(record_dict)

        return filtered_records

    async def _generate_sql_filters(
        self,
        compound: str,
        target_temperature: float,
        temperature_range: List[float],
        phases: List[str],
        available_formulas: List[str],
        total_records_count: int
    ) -> SQLFilterResult:
        """
        Генерация SQL WHERE условий с помощью LLM для оптимизированной фильтрации.

        Args:
            compound: Целевое соединение
            target_temperature: Целевая температура в Кельвинах
            temperature_range: Температурный диапазон [min, max]
            phases: Предпочтительные фазы
            available_formulas: Доступные формулы в базе данных
            total_records_count: Общее количество записей

        Returns:
            Сгенерированные SQL WHERE условия

        Raises:
            ValueError: Если не удалось сгенерировать фильтры
        """
        try:
            # Подготавливаем метаданные для LLM
            celsius_temp = target_temperature - 273.15

            # Формируем промпт с метаданными
            prompt = SQL_FILTER_GENERATION_PROMPT.format(
                compound=compound,
                target_temperature_k=target_temperature,
                celsius=celsius_temp,
                temperature_range_k=temperature_range,
                phases=phases,
                available_formulas=available_formulas,
                total_records_count=total_records_count,
                temp_min=temperature_range[0],
                temp_max=temperature_range[1]
            )

            self.logger.info(f"Generating SQL filters for {compound} with {len(available_formulas)} available formulas")

            # Создаем отдельный агент для генерации SQL фильтров
            provider = OpenAIProvider(
                api_key=self.config.llm_api_key,
                base_url=self.config.llm_base_url,
            )
            model = OpenAIChatModel(self.config.llm_model, provider=provider)

            sql_filter_agent = Agent(
                model,
                deps_type=ResultsFilteringAgentConfig,
                output_type=SQLFilterResult,
                system_prompt=SQL_FILTER_GENERATION_PROMPT,
                retries=2,  # Меньше попыток для генерации фильтров
            )

            # Генерируем SQL WHERE условия с использованием TimeoutManager
            self.logger.info(f"Generating SQL filters for {compound} using TimeoutManager")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL FILTER GENERATION START: {compound}")

            # Используем TimeoutManager для выполнения с retry механизмом
            async def generate_sql_filters():
                return await sql_filter_agent.run(prompt, deps=self.config)

            result = await self.timeout_manager.execute_with_retry(
                generate_sql_filters,
                TimeoutOperationType.SQL_GENERATION
            )

            sql_elapsed = result.usage.total_duration / 1_000_000_000 if hasattr(result, 'usage') else 0
            self.logger.info(f"SQL filters generated for {compound} in {sql_elapsed:.2f}s: {len(result.output.sql_where_conditions)} conditions")

            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL FILTER GENERATION COMPLETE: {compound}, {sql_elapsed:.2f}s, {len(result.output.sql_where_conditions)} conditions")

            return result.output

        except asyncio.TimeoutError:
            sql_elapsed = asyncio.get_event_loop().time() - sql_start_time
            self.logger.error(f"SQL filter generation timeout for {compound} after {sql_elapsed:.2f}s (limit: {self.config.sql_generation_timeout}s)")
            if self.config.session_logger:
                self.config.session_logger.log_error(f"SQL FILTER TIMEOUT: {compound} after {sql_elapsed:.2f}s")

            # Fallback к базовым условиям
            return self._create_fallback_sql_filters(compound, target_temperature, temperature_range)

        except Exception as e:
            sql_elapsed = asyncio.get_event_loop().time() - sql_start_time
            self.logger.error(f"SQL filter generation error for {compound} after {sql_elapsed:.2f}s: {e}")
            if self.config.session_logger:
                self.config.session_logger.log_error(f"SQL FILTER ERROR: {compound}, error='{str(e)}', elapsed={sql_elapsed:.2f}s")

            # Fallback к базовым условиям
            return self._create_fallback_sql_filters(compound, target_temperature, temperature_range)

    def _create_fallback_sql_filters(self, compound: str, target_temperature: float, temperature_range: List[float]) -> SQLFilterResult:
        """
        Создание базовых SQL WHERE условий при ошибке LLM.

        Args:
            compound: Целевое соединение
            target_temperature: Целевая температура
            temperature_range: Температурный диапазон

        Returns:
            Базовые SQL WHERE условия
        """
        temp_min, temp_max = temperature_range

        # Базовые условия в приоритете надежности
        conditions = [
            f"TRIM(Formula) = '{compound}' AND ({target_temperature} >= Tmin AND {target_temperature} <= Tmax) AND ReliabilityClass = 1",
            f"Formula LIKE '{compound}(%' AND ({target_temperature} >= Tmin AND {target_temperature} <= Tmax) AND ReliabilityClass <= 2",
            f"TRIM(Formula) = '{compound}' AND ReliabilityClass <= 3"
        ]

        order_clauses = [
            "ReliabilityClass ASC, ABS({target_temperature} - Tmin) ASC",
            "ReliabilityClass ASC",
            "ReliabilityClass ASC"
        ]

        return SQLFilterResult(
            sql_where_conditions=conditions,
            order_by_clauses=order_clauses,
            limit_values=[5, 10, 20],
            reasoning=f"Fallback SQL filter generation for {compound} using basic reliability and temperature criteria",
            phase_analysis={"recommended_phase": "auto", "confidence": 0.7, "reasoning": "Default phase selection"},
            expected_results={"min_records": 1, "max_records": 20, "optimal_records": 3},
            overall_confidence=0.6,
            warnings=["Using fallback SQL filter generation due to LLM unavailability"]
        )

    def _apply_sql_filters_locally(
        self,
        records: List[Dict[str, Any]],
        sql_filter_result: SQLFilterResult,
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Локальное применение сгенерированных SQL WHERE условий к записям.

        Args:
            records: Записи для фильтрации
            sql_filter_result: Сгенерированные SQL WHERE условия
            columns: Список колонок

        Returns:
            Отфильтрованные записи
        """
        if not records or not sql_filter_result.sql_where_conditions:
            return records

        try:
            # Применяем фильтры по приоритету
            for i, where_condition in enumerate(sql_filter_result.sql_where_conditions):
                order_by = sql_filter_result.order_by_clauses[i] if i < len(sql_filter_result.order_by_clauses) else sql_filter_result.order_by_clauses[0]
                limit_value = sql_filter_result.limit_values[i] if i < len(sql_filter_result.limit_values) else sql_filter_result.limit_values[-1]

                # Фильтруем записи
                filtered_records = self._evaluate_sql_condition(records, where_condition, columns)

                # Сортируем записи
                if filtered_records:
                    filtered_records = self._apply_ordering(filtered_records, order_by, columns)

                    # Ограничиваем количество записей
                    if len(filtered_records) > limit_value:
                        filtered_records = filtered_records[:limit_value]

                    self.logger.info(f"Applied SQL filter {i+1}: {len(filtered_records)} records remain (condition: {where_condition[:50]}...)")

                    # Если нашли достаточно записей, возвращаем результат
                    if len(filtered_records) >= min(1, sql_filter_result.expected_results.get("optimal_records", 1)):
                        return filtered_records

            # Если ни один фильтр не дал результатов, возвращаем все записи
            self.logger.warning("All SQL filters returned no results, returning original records")
            return records

        except Exception as e:
            self.logger.error(f"Error applying SQL filters locally: {e}")
            return records

    def _evaluate_sql_condition(self, records: List[Dict[str, Any]], where_condition: str, columns: List[str]) -> List[Dict[str, Any]]:
        """
        Оценка SQL WHERE условия для каждой записи.

        Args:
            records: Записи для фильтрации
            where_condition: SQL WHERE условие
            columns: Список колонок

        Returns:
            Отфильтрованные записи
        """
        filtered_records = []

        for record in records:
            try:
                # Создаем контекст для оценки SQL условия
                context = self._create_sql_evaluation_context(record, columns)

                # Оцениваем WHERE условие
                if self._evaluate_condition_safely(where_condition, context):
                    filtered_records.append(record)

            except Exception as e:
                self.logger.warning(f"Error evaluating SQL condition for record {record.get('Formula', 'unknown')}: {e}")
                # В случае ошибки, включаем запись (консервативный подход)
                filtered_records.append(record)

        return filtered_records

    def _create_sql_evaluation_context(self, record: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
        """
        Создание контекста для оценки SQL условий.

        Args:
            record: Запись
            columns: Список колонок

        Returns:
            Контекст с безопасными значениями для оценки
        """
        context = {}

        for i, col in enumerate(columns):
            value = record.get(col)
            if value is None:
                context[col] = None
            elif isinstance(value, str):
                # Экранируем строковые значения
                context[col] = value.replace("'", "''")
            else:
                context[col] = value

        # Добавляем безопасные функции
        context.update({
            'TRIM': lambda x: x.strip() if isinstance(x, str) else x,
            'ABS': abs,
            'COALESCE': lambda *args: next((a for a in args if a is not None), None)
        })

        return context

    def _evaluate_condition_safely(self, condition: str, context: Dict[str, Any]) -> bool:
        """
        Безопасная оценка SQL WHERE условия с улучшенной обработкой синтаксиса.

        Args:
            condition: SQL WHERE условие
            context: Контекст с переменными

        Returns:
            True если условие выполнено
        """
        try:
            # Улучшенная обработка SQL условий
            python_condition = self._convert_sql_to_python(condition, context)

            # Безопасная оценка с ограниченным контекстом
            allowed_names = self._create_safe_evaluation_context(context)

            # Оцениваем условие
            result = eval(python_condition, {"__builtins__": {}}, allowed_names)
            return bool(result)

        except Exception as e:
            # Детальное логирование ошибок
            self.logger.warning(f"Error evaluating SQL condition '{condition[:100]}...': {e}")
            if self.config.session_logger:
                self.config.session_logger.log_info(f"SQL EVALUATION ERROR: condition='{condition[:50]}...', error='{str(e)}'")

            # В случае ошибки оценки, возвращаем False (более безопасный подход)
            return False

    def _convert_sql_to_python(self, condition: str, context: Dict[str, Any]) -> str:
        """
        Преобразует SQL WHERE условие в Python expression с улучшенным синтаксисом.

        Args:
            condition: SQL WHERE условие
            context: Контекст для анализа переменных

        Returns:
            Python expression
        """
        python_condition = condition.strip()

        # Корректная замена SQL операторов с учетом пробелов
        replacements = [
            # Заменяем операторы в правильном порядке
            (" >= ", " >= "),
            (" <= ", " <= "),
            (" <> ", " != "),
            (" != ", " != "),
            (" = ", " == "),
            (" AND ", " and "),
            (" OR ", " or "),
            (" IS NULL ", " is None "),
            (" IS NOT NULL ", " is not None "),
        ]

        # Применяем замены
        for sql_op, py_op in replacements:
            python_condition = python_condition.replace(sql_op, py_op)

        # Обработка TRIM функции
        python_condition = python_condition.replace("TRIM(", "_trim_function(")

        # Обработка LIKE с шаблонами
        if " LIKE " in python_condition:
            python_condition = self._process_like_conditions(python_condition, context)

        # Заменяем множественные пробелы на один
        import re
        python_condition = re.sub(r'\s+', ' ', python_condition).strip()

        return python_condition

    def _create_safe_evaluation_context(self, base_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Создает безопасный контекст для eval с нужными функциями.

        Args:
            base_context: Базовый контекст с данными записи

        Returns:
            Безопасный контекст для оценки
        """
        allowed_names = {}

        # Добавляем переменные из контекста с безопасными значениями
        for key, value in base_context.items():
            if isinstance(value, str):
                # Безопасная обработка строк
                allowed_names[key] = value.replace("'", "\\'")
            else:
                allowed_names[key] = value

        # Безопасные функции
        def _trim_function(x):
            return x.strip() if isinstance(x, str) else x

        allowed_names.update({
            '_trim_function': _trim_function,
            'None': None,
            'True': True,
            'False': False,
            'abs': abs,
            'len': len,
            'str': str,
            'float': float,
            'int': int,
            'min': min,
            'max': max,
            'round': round
        })

        return allowed_names

    def _process_like_conditions(self, condition: str, context: Dict[str, Any]) -> str:
        """
        Обработка SQL LIKE условий.

        Args:
            condition: Условие с LIKE
            context: Контекст

        Returns:
            Обработанное условие
        """
        # Простая обработка для LIKE 'compound(%'
        # Находим patterns: Formula LIKE 'compound(%'
        import re

        pattern = r"(\w+)\s+LIKE\s+'([^']+)\(%\s*'\)"
        matches = re.findall(pattern, condition)

        for column, prefix in matches:
            # Заменяем на Python проверку
            python_check = f"(isinstance({column}, str) and {column}.startswith('{prefix}'))"
            condition = condition.replace(f"{column} LIKE '{prefix}(%'", python_check)

        return condition

    def _apply_ordering(self, records: List[Dict[str, Any]], order_by: str, columns: List[str]) -> List[Dict[str, Any]]:
        """
        Применение ORDER BY к записям.

        Args:
            records: Записи для сортировки
            order_by: ORDER BY условие
            columns: Список колонок

        Returns:
            Отсортированные записи
        """
        try:
            # Упрощенная реализация сортировки
            # Извлекаем колонки для сортировки
            if "ReliabilityClass" in order_by:
                return sorted(records, key=lambda x: (
                    x.get("ReliabilityClass", 999),
                    abs(x.get("Tmin", 298.15) - 298.15) if "Tmin" in order_by else 0
                ))
            elif "Tmin" in order_by:
                return sorted(records, key=lambda x: abs(x.get("Tmin", 298.15) - 298.15))
            else:
                return records  # Без сортировки по умолчанию

        except Exception as e:
            self.logger.warning(f"Error applying ordering '{order_by}': {e}")
            return records

    async def _llm_filter_records(
        self,
        records: List[Dict[str, Any]],
        columns: List[str],
        compounds: List[str],
        phases: List[str],
        temperature_range: List[float],
        target_temperature: float
    ) -> FilteredResult:
        """
        Оптимизированная фильтрация записей с использованием SQL WHERE генерации.

        Новая архитектура:
        1. Передаем метаданные в LLM для генерации SQL WHERE условий
        2. Применяем условия локально к записям
        3. Финальная селекция с оптимизированным количеством записей

        Args:
            records: Предварительно отфильтрованные записи
            columns: Названия колонок
            compounds: Список запрашиваемых веществ
            phases: Список запрашиваемых фаз
            temperature_range: Температурный диапазон
            target_temperature: Целевая температура

        Returns:
            Результат фильтрации
        """
        self.logger.info(f"Starting optimized SQL-based filtering for {len(compounds)} compounds, {len(records)} records")

        try:
            # Шаг 1: Подготавливаем метаданные вместо полных записей
            available_formulas = list(set([record.get("Formula", "") for record in records]))
            available_formulas = [f for f in available_formulas if f]

            # Шаг 2: Для каждого соединения генерируем SQL WHERE условия
            all_filtered_records = []
            selected_entries = []
            missing_compounds = []

            for compound in compounds:
                self.logger.info(f"Processing compound {compound} with SQL filter generation")

                try:
                    # Генерируем SQL WHERE условия через LLM
                    sql_filter_result = await self._generate_sql_filters(
                        compound=compound,
                        target_temperature=target_temperature,
                        temperature_range=temperature_range,
                        phases=phases,
                        available_formulas=[f for f in available_formulas if compound in f or f.startswith(compound)],
                        total_records_count=len([r for r in records if compound in r.get("Formula", "")])
                    )

                    # Применяем сгенерированные SQL WHERE условия локально
                    compound_records = [r for r in records if compound in r.get("Formula", "")]
                    filtered_compound_records = self._apply_sql_filters_locally(
                        compound_records, sql_filter_result, columns
                    )

                    if filtered_compound_records:
                        all_filtered_records.extend(filtered_compound_records)

                        # Выбираем лучшие записи для этого соединения
                        best_record = filtered_compound_records[0]  # Первая запись уже отсортирована
                        selected_entries.append(SelectedEntry(
                            compound=compound,
                            selected_id=len(all_filtered_records) - len(filtered_compound_records),
                            reasoning=f"SQL-filtered record for {compound}: {sql_filter_result.reasoning[:100]}..."
                        ))
                    else:
                        missing_compounds.append(compound)

                except Exception as e:
                    self.logger.error(f"Error processing compound {compound}: {e}")
                    missing_compounds.append(compound)

            # Шаг 3: Финальная оптимизация результатов с LLM (если нужно)
            if all_filtered_records and selected_entries:
                self.logger.info(f"SQL filtering completed: {len(all_filtered_records)} total records selected")

                # Создаем базовый результат без дополнительного LLM анализа
                return FilteredResult(
                    selected_entries=selected_entries,
                    phase_determinations={compound: {"phase": "auto", "confidence": 0.8, "reasoning": "SQL-based filtering"} for compound in compounds},
                    missing_compounds=missing_compounds,
                    excluded_entries_count=len(records) - len(all_filtered_records),
                    overall_confidence=0.85,  # Высокая уверенность в SQL подходе
                    warnings=[f"Optimized SQL filtering applied - reduced from {len(records)} to {len(all_filtered_records)} records"],
                    filter_summary=f"Applied optimized SQL WHERE filtering for {len(compounds)} compounds, selected {len(selected_entries)} best records"
                )
            else:
                # Fallback для отсутствующих записей
                self.logger.warning("No records found after SQL filtering, using fallback")
                return self._create_fallback_result(records, compounds, target_temperature)

        except Exception as e:
            self.logger.error(f"Error in optimized SQL filtering: {e}")
            # Fallback к традиционному подходу
            return await self._fallback_llm_filtering(records, columns, compounds, phases, temperature_range, target_temperature)

    def _create_fallback_result(self, records: List[Dict[str, Any]], compounds: List[str], target_temperature: float) -> FilteredResult:
        """
        Создание базового результата при отсутствии записей.

        Args:
            records: Записи
            compounds: Список соединений
            target_temperature: Целевая температура

        Returns:
            Базовый результат
        """
        selected_entries = []
        missing_compounds = []

        for compound in compounds:
            compound_records = [r for r in records if compound in r.get("Formula", "")]
            if compound_records:
                selected_entries.append(SelectedEntry(
                    compound=compound,
                    selected_id=records.index(compound_records[0]),
                    reasoning=f"Basic selection for {compound} at {target_temperature}K"
                ))
            else:
                missing_compounds.append(compound)

        return FilteredResult(
            selected_entries=selected_entries,
            phase_determinations={compound: {"phase": "auto", "confidence": 0.5, "reasoning": "Fallback selection"} for compound in compounds},
            missing_compounds=missing_compounds,
            excluded_entries_count=len(records) - len(selected_entries),
            overall_confidence=0.4,
            warnings=["Using fallback basic selection - SQL filtering unavailable"],
            filter_summary=f"Basic fallback selection for {len(compounds)} compounds"
        )

    async def _fallback_llm_filtering(
        self,
        records: List[Dict[str, Any]],
        columns: List[str],
        compounds: List[str],
        phases: List[str],
        temperature_range: List[float],
        target_temperature: float
    ) -> FilteredResult:
        """
        Fallback к традиционному LLM подходу при ошибке SQL фильтрации.

        Args:
            records: Записи для фильтрации
            columns: Колонки
            compounds: Соединения
            phases: Фазы
            temperature_range: Температурный диапазон
            target_temperature: Целевая температура

        Returns:
            Результат традиционной фильтрации
        """
        self.logger.warning("Falling back to traditional LLM filtering approach")

        try:
            # Ограничиваем количество записей для LLM
            max_records = min(20, len(records))
            records_subset = records[:max_records]

            # Подготавливаем данные для LLM (только метаданные)
            records_with_ids = []
            for i, record in enumerate(records_subset):
                record_with_id = {
                    "record_id": i,
                    "Formula": record.get("Formula", ""),
                    "Phase": record.get("Phase", ""),
                    "Tmin": record.get("Tmin"),
                    "Tmax": record.get("Tmax"),
                    "ReliabilityClass": record.get("ReliabilityClass", 999)
                }
                records_with_ids.append(record_with_id)

            # Создаем базовый промпт с метаданными
            analysis_data = {
                "requested_compounds": compounds,
                "requested_phases": phases,
                "temperature_range_k": temperature_range,
                "target_temperature_k": target_temperature,
                "available_records": records_with_ids,
                "total_records_count": len(records),
            }

            yaml_data = yaml.dump(analysis_data, default_flow_style=False, allow_unicode=True)

            prompt = f"""Select the most relevant thermodynamic database records for the requested compounds and conditions:

{yaml_data}

Select optimal records for each compound considering:
1. Formula matching (exact or variants)
2. Temperature range coverage
3. Phase appropriateness
4. Data reliability (ReliabilityClass)

Return JSON with selected entries and reasoning."""

            # Используем основной агент с коротким таймаутом
            result = await asyncio.wait_for(
                self.agent.run(prompt, deps=self.config),
                timeout=30.0  # Короткий таймаут для fallback
            )

            self.logger.info(f"Fallback LLM filtering successful: {len(result.output.selected_entries)} entries selected")
            return result.output

        except Exception as e:
            self.logger.error(f"Fallback LLM filtering also failed: {e}")
            # Финальный fallback - базовая температурная фильтрация
            return self._create_fallback_result(records, compounds, target_temperature)

    def _convert_ids_to_records(self, selected_entries: List[SelectedEntry], all_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Конвертирует selected_entries с ID обратно в полные записи.

        Args:
            selected_entries: Выбранные записи с ID
            all_records: Все доступные записи для поиска

        Returns:
            Список полных записей
        """
        selected_records = []

        for entry in selected_entries:
            # Ищем запись по ID (который является индексом в массиве)
            if 0 <= entry.selected_id < len(all_records):
                selected_records.append(all_records[entry.selected_id])
            else:
                self.logger.warning(f"Invalid record ID {entry.selected_id} for compound {entry.compound}")

        return selected_records

    def _calculate_individual_confidence(self, filtered_result: FilteredResult, total_records: int) -> float:
        """
        Рассчитать уверенность для индивидуального поиска.

        Args:
            filtered_result: Результат фильтрации
            total_records: Общее количество записей до фильтрации

        Returns:
            Уверенность от 0.0 до 1.0
        """
        if not filtered_result.selected_entries:
            return 0.0

        # Базовая уверенность из самого результата
        base_confidence = filtered_result.overall_confidence

        # Учитываем соотношение выбранных записей к общему количеству
        selection_ratio = len(filtered_result.selected_entries) / max(1, total_records)
        ratio_confidence = min(1.0, selection_ratio * 5)  # 20% записей = 1.0

        # Учитываем отсутствие предупреждений
        warning_penalty = len(filtered_result.warnings) * 0.1
        warning_confidence = max(0.0, 1.0 - warning_penalty)

        # Учитываем отсутствие отсутствующих соединений
        missing_penalty = len(filtered_result.missing_compounds) * 0.2
        missing_confidence = max(0.0, 1.0 - missing_penalty)

        # Комбинируем все факторы
        final_confidence = (
            base_confidence * 0.4 +
            ratio_confidence * 0.2 +
            warning_confidence * 0.2 +
            missing_confidence * 0.2
        )

        return min(1.0, max(0.0, final_confidence))

    
    def _log_filtered_table(self, selected_records: List[Dict[str, Any]], reasoning: str):
        """Логирует финальную отфильтрованную таблицу с выбранными записями."""
        if not selected_records:
            self.logger.info("No records selected after filtering")
            if self.config.session_logger:
                self.config.session_logger.log_info("FILTERED RESULTS: No records selected")
            return

        # Основные колонки для отображения
        key_columns = ['Formula', 'FirstName', 'Phase', 'H298', 'S298', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'Tmin', 'Tmax']

        self.logger.info(f"Filtered results: {len(selected_records)} selected records")

        # Отладочное логирование - что именно в selected_records
        self.logger.info(f"DEBUG: First record keys: {list(selected_records[0].keys()) if selected_records else 'No records'}")
        self.logger.info(f"DEBUG: First record data: {selected_records[0] if selected_records else 'No records'}")

        if self.config.session_logger:
            self.config.session_logger.log_info(f"FILTERED RESULTS TABLE ({len(selected_records)} records):")
            self.config.session_logger.log_info(f"REASONING: {reasoning}")

            # Формируем данные для таблицы
            table_rows = []
            for record in selected_records:
                row = []
                for col in key_columns:
                    value = record.get(col, "")
                    # Форматируем числовые значения для лучшей читаемости
                    if isinstance(value, float):
                        if abs(value) < 0.001 and value != 0.0:
                            row.append(f"{value:.2e}")
                        else:
                            row.append(f"{value:.4g}")
                    else:
                        row.append(str(value))
                table_rows.append(row)

            # Создаем таблицу через метод format_table из SessionLogger
            formatted_table = self.config.session_logger.format_table(key_columns, table_rows, max_rows=len(selected_records))

            # Логируем таблицу
            self.config.session_logger.log_info("SELECTED RECORDS:")
            for line in formatted_table.split('\n'):
                if line.strip():
                    self.config.session_logger.log_info(line)

    def get_status(self) -> Dict:
        """Получить статус агента с расширенными метриками."""
        session = self.storage.get_session(self.agent_id)

        # Собираем метрики производительности
        status = {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
            "configuration": {
                "filtering_timeout": self.config.filtering_timeout,
                "sql_generation_timeout": self.config.sql_generation_timeout,
                "llm_filtering_timeout": getattr(self.config, 'llm_filtering_timeout', 60),
                "max_retry_attempts": self.config.max_retry_attempts,
                "poll_interval": self.config.poll_interval,
            },
            "capabilities": [
                "filter_results",
                "temperature_analysis",
                "compound_selection",
                "sql_filter_generation",
                "retry_logic",
                "request_abandonment"
            ],
            "performance_metrics": {
                "active_filtering_requests": len([
                    msg for msg in self.storage.receive_messages(self.agent_id, message_type="filter_results")
                ]) + len([
                    msg for msg in self.storage.receive_messages(self.agent_id, message_type="filter_individual_results")
                ]),
                "storage_entries": len(self.storage.storage),
                "message_queue_size": len(self.storage.message_queue),
            }
        }

        # Логируем статус periodically
        if self.config.session_logger:
            self.config.session_logger.log_info(f"AGENT STATUS: {self.agent_id}, running={self.running}, queue_size={status['performance_metrics']['message_queue_size']}")

        return status

    def get_diagnostics(self) -> Dict:
        """
        Получить детальную диагностическую информацию для мониторинга.

        Returns:
            Словарь с диагностической информацией
        """
        import sys
        import psutil
        import os

        # Системные метрики
        process = psutil.Process(os.getpid())

        diagnostics = {
            "agent_info": {
                "agent_id": self.agent_id,
                "running": self.running,
                "uptime_seconds": getattr(self, '_start_time', 0),
            },
            "system_metrics": {
                "cpu_percent": process.cpu_percent(),
                "memory_mb": process.memory_info().rss / 1024 / 1024,
                "memory_percent": process.memory_percent(),
                "open_files": len(process.open_files()),
            },
            "configuration": {
                "filtering_timeout": self.config.filtering_timeout,
                "sql_generation_timeout": self.config.sql_generation_timeout,
                "max_retry_attempts": self.config.max_retry_attempts,
                "poll_interval": self.config.poll_interval,
                "max_retries": self.config.max_retries,
            },
            "storage_metrics": {
                "storage_entries": len(self.storage.storage),
                "message_queue_size": len(self.storage.message_queue),
                "active_sessions": len(self.storage.agent_sessions),
            },
            "health_check": {
                "storage_accessible": self._test_storage_access(),
                "logger_functional": self._test_logger_functionality(),
                "agent_responsive": self.running,
            }
        }

        return diagnostics

    def _test_storage_access(self) -> bool:
        """Проверяет доступность хранилища."""
        try:
            test_key = f"health_check_{self.agent_id}"
            self.storage.set(test_key, {"test": True}, ttl_seconds=1)
            result = self.storage.get(test_key)
            return result is not None
        except Exception as e:
            self.logger.error(f"Storage access test failed: {e}")
            return False

    def _test_logger_functionality(self) -> bool:
        """Проверяет функциональность логгера."""
        try:
            self.logger.debug("Health check: logger functional")
            return True
        except Exception as e:
            return False


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================


def create_results_filtering_agent(
    llm_api_key: str,
    llm_base_url: str,
    llm_model: str = "openai:gpt-4o",
    storage: Optional[AgentStorage] = None,
    logger: Optional[logging.Logger] = None,
    session_logger: Optional[SessionLogger] = None,
) -> ResultsFilteringAgent:
    """
    Создать агента фильтрации результатов.

    Args:
        llm_api_key: API ключ для LLM
        llm_base_url: URL для LLM API
        llm_model: Модель LLM
        storage: Хранилище (или будет использовано глобальное)
        logger: Логгер
        session_logger: Сессионный логгер

    Returns:
        Настроенный агент фильтрации результатов
    """
    config = ResultsFilteringAgentConfig(
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        storage=storage or get_storage(),
        logger=logger or logging.getLogger(__name__),
        session_logger=session_logger,
    )

    return ResultsFilteringAgent(config)


async def run_results_filtering_agent_standalone(config: ResultsFilteringAgentConfig):
    """
    Запустить агента фильтрации результатов в standalone режиме для тестирования.

    Args:
        config: Конфигурация агента
    """
    agent = ResultsFilteringAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()
        print("Results filtering agent stopped")