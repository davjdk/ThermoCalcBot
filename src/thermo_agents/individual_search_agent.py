"""
Individual Search Agent - координатор параллельного поиска соединений.

Обеспечивает индивидуальный поиск каждого вещества с последующей агрегацией результатов.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .agent_storage import AgentStorage, get_storage
from .thermo_agents_logger import SessionLogger
from .thermodynamic_agent import (
    AggregatedResults,
    IndividualCompoundResult,
    IndividualSearchRequest,
)
from .timeout_manager import get_timeout_manager, OperationType as TimeoutOperationType


@dataclass
class IndividualSearchAgentConfig:
    """Конфигурация Individual Search Agent."""

    agent_id: str = "individual_search_agent"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 0.05  # Оптимизировано до 0.05с для немедленной обработки
    max_retries: int = 2  # Обновлено до 2 попыток согласно новой политике
    timeout_seconds: int = 54  # Оптимизировано на основе анализа: 27с × 2 = 54с
    max_parallel_searches: int = 4  # Оптимизировано для баланса производительности


class IndividualSearchAgent:
    """
    Агент для координации параллельного индивидуального поиска соединений.

    Основные задачи:
    - Получать список веществ от Thermodynamic Agent
    - Координировать параллельные запросы к SQL Agent
    - Собирать результаты в единую структуру
    - Управлять таймаутами и ошибками
    """

    def __init__(self, config: IndividualSearchAgentConfig):
        """Инициализация агента."""
        self.config = config
        self.agent_id = config.agent_id
        self.storage = config.storage
        self.logger = config.logger
        self.running = False

        # Инициализация TimeoutManager
        self.timeout_manager = get_timeout_manager(
            logger=self.config.logger,
            session_logger=self.config.session_logger
        )

        # Регистрация в хранилище
        self.storage.start_session(
            self.agent_id,
            {
                "status": "initialized",
                "capabilities": [
                    "coordinate_individual_search",
                    "aggregate_results",
                    "handle_parallel_searches",
                ],
            },
        )

        self.logger.info(f"IndividualSearchAgent '{self.agent_id}' initialized")
        self._last_columns = []  # Сохраняем имена колонок для конвертации

    async def start(self):
        """Запустить агента в режиме прослушивания сообщений."""
        self.running = True
        self.storage.update_session(self.agent_id, {"status": "running"})
        self.logger.info(f"Agent '{self.agent_id}' started listening for messages")

        while self.running:
            try:
                # Получаем сообщения о запросах на индивидуальный поиск
                messages = self.storage.receive_messages(
                    self.agent_id,
                    message_type="individual_search_request"
                )

                # Обрабатываем каждое сообщение
                for message in messages:
                    await self._process_search_request(message)

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

    async def _process_search_request(self, message):
        """
        Обработать запрос на индивидуальный поиск.

        Args:
            message: Сообщение с запросом на поиск
        """
        self.logger.info(
            f"Processing search request: {message.id} from {message.source_agent}"
        )

        try:
            # Извлекаем данные запроса
            search_request_data = message.payload.get("search_request")
            if not search_request_data:
                raise ValueError("No search_request in message payload")

            search_request = IndividualSearchRequest(**search_request_data)

            # Логирование начала поиска
            if self.config.session_logger:
                self.config.session_logger.log_info(
                    f"Starting individual search for {len(search_request.compounds)} compounds"
                )

            # Выполняем параллельный поиск
            aggregated_results = await self._execute_parallel_search(
                search_request, correlation_id=message.id
            )

            # TEMPORARY DEBUG LOGGING - TO BE REMOVED LATER
            # Логируем результаты поиска соединений
            if self.config.session_logger:
                # Подготавливаем данные для логирования
                compound_results_for_logging = []
                for result in aggregated_results.individual_results:
                    compound_results_for_logging.append({
                        "compound": result.compound,
                        "selected_records": result.selected_records,
                        "confidence": result.confidence
                    })

                # Логируем сводную таблицу по соединениям
                self.config.session_logger.log_compound_data_table(
                    compound_results_for_logging,
                    "INDIVIDUAL SEARCH RESULTS - AGGREGATED DATA"
                )

                # Логируем метаданные поиска
                search_metadata = {
                    "original_query": search_request.original_query,
                    "compounds_count": len(search_request.compounds),
                    "compounds": ", ".join(search_request.compounds),
                    "temperature_k": search_request.common_params.get("temperature_k"),
                    "temperature_range_k": search_request.common_params.get("temperature_range_k"),
                    "phases": search_request.common_params.get("phases"),
                    "overall_confidence": aggregated_results.overall_confidence,
                    "missing_compounds": aggregated_results.missing_compounds,
                    "warnings_count": len(aggregated_results.warnings)
                }
                self.config.session_logger.log_search_metadata(search_metadata, "SEARCH METADATA")

            # Сохраняем результаты
            result_key = f"individual_search_result_{message.id}"
            self.storage.set(
                result_key,
                aggregated_results.model_dump(),
                ttl_seconds=1800  # 30 минут
            )

            # Отправляем ответ в orchestrator (а не source_agent) с подтверждением
            # Orchestrator ожидает сообщения individual_search_complete
            send_result = self.storage.send_message_with_ack(
                source_agent=self.agent_id,
                target_agent="orchestrator",
                message_type="individual_search_complete",
                correlation_id=message.id,
                payload={
                    "status": "success",
                    "result_key": result_key,
                    "aggregated_results": aggregated_results.model_dump(),
                },
                metadata={"critical": True, "requires_ack": True}
            )

            # Логируем результат отправки
            if send_result.get("target_active"):
                self.logger.info(f"Individual search result sent to orchestrator: {send_result['message_id']}")
            else:
                self.logger.warning(f"Orchestrator not active when sending result: {send_result.get('warning')}")

            self.logger.info(
                f"Individual search completed: {len(aggregated_results.individual_results)} compounds processed"
            )

        except Exception as e:
            self.logger.error(f"Error processing search request {message.id}: {e}")

            # Отправляем сообщение об ошибке в orchestrator с подтверждением
            error_send_result = self.storage.send_message_with_ack(
                source_agent=self.agent_id,
                target_agent="orchestrator",
                message_type="individual_search_complete",
                correlation_id=message.id,
                payload={"status": "error", "error": str(e)},
                metadata={"critical": True, "requires_ack": True}
            )

            # Логируем результат отправки ошибки
            if not error_send_result.get("target_active"):
                self.logger.warning(f"Orchestrator not active when sending error: {error_send_result.get('warning')}")

            if self.config.session_logger:
                self.config.session_logger.log_error(str(e))

    async def _execute_parallel_search(
        self,
        search_request: IndividualSearchRequest,
        correlation_id: str
    ) -> AggregatedResults:
        """
        Выполнить параллельный поиск для всех соединений.

        Args:
            search_request: Запрос на поиск
            correlation_id: ID для корреляции запросов

        Returns:
            Агрегированные результаты
        """
        compounds = search_request.compounds
        individual_results = []
        missing_compounds = []
        warnings = []

        # Ограничиваем количество параллельных поисков
        semaphore = asyncio.Semaphore(self.config.max_parallel_searches)

        # Создаем задачи для параллельного выполнения
        tasks = [
            self._search_single_compound(
                compound,
                search_request,
                semaphore,
                correlation_id
            )
            for compound in compounds
        ]

        # Выполняем задачи параллельно с таймаутом
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.timeout_seconds * len(compounds)
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"Parallel search timeout for {len(compounds)} compounds")
            # Обрабатываем partially completed результаты
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обрабатываем результаты
        for i, result in enumerate(results):
            compound = compounds[i]

            if isinstance(result, Exception):
                # Ошибка при поиске соединения
                self.logger.error(f"Error searching compound {compound}: {result}")
                individual_results.append(
                    IndividualCompoundResult(
                        compound=compound,
                        search_results=[],
                        selected_records=[],
                        confidence=0.0,
                        errors=[str(result)]
                    )
                )
                missing_compounds.append(compound)
                warnings.append(f"Failed to search compound {compound}: {result}")
            else:
                # Успешный поиск
                individual_results.append(result)
                # Проверяем, найдены ли данные для соединения
                if not result.selected_records or len(result.selected_records) == 0:
                    missing_compounds.append(compound)
                    warnings.append(f"No thermodynamic data found for compound {compound}")
                elif result.confidence < 0.5:
                    warnings.append(
                        f"Low confidence ({result.confidence:.2f}) for compound {compound}"
                    )

        # Создаем сводную таблицу
        summary_table = self._create_summary_table(individual_results)

        # Вычисляем общую уверенность
        overall_confidence = self._calculate_overall_confidence(individual_results)

        # Определяем статус полноты данных для реакции
        is_complete_reaction = len(missing_compounds) == 0
        data_completeness_status = "complete" if is_complete_reaction else "incomplete"

        # Добавляем специальное предупреждение для реакций с неполными данными
        if not is_complete_reaction and len(compounds) > 1:
            warnings.append(
                f"REACTION DATA INCOMPLETE: Missing thermodynamic data for {len(missing_compounds)} of {len(compounds)} compounds. "
                f"Missing compounds: {', '.join(missing_compounds)}"
            )

        return AggregatedResults(
            individual_results=individual_results,
            summary_table=summary_table,
            overall_confidence=overall_confidence,
            missing_compounds=missing_compounds,
            warnings=warnings,
            data_completeness_status=data_completeness_status,
            is_complete_reaction=is_complete_reaction
        )

    async def _search_single_compound(
        self,
        compound: str,
        search_request: IndividualSearchRequest,
        semaphore: asyncio.Semaphore,
        correlation_id: str
    ) -> IndividualCompoundResult:
        """
        Выполнить поиск для одного соединения.

        Args:
            compound: Химическая формула
            search_request: Общий запрос поиска
            semaphore: Семафор для ограничения параллелизма
            correlation_id: ID корреляции

        Returns:
            Результат поиска для соединения
        """
        async with semaphore:
            self.logger.info(f"DEBUG: Starting search for compound: {compound}")

            try:
                # Создаем уникальный ID для этого поиска
                search_id = f"search_{compound}_{correlation_id}_{uuid4().hex[:8]}"
                self.logger.info(f"DEBUG: Created search ID: {search_id}")

                # Отправляем запрос SQL Agent
                self.logger.info(f"DEBUG: Sending SQL generation request for compound {compound}")
                sql_message_id = self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="sql_agent",
                    message_type="generate_individual_query",
                    correlation_id=search_id,
                    payload={
                        "compound": compound,
                        "common_params": search_request.common_params,
                        "search_strategy": search_request.search_strategy,
                        "original_query": search_request.original_query,
                    },
                )
                self.logger.info(f"DEBUG: SQL request sent with message ID: {sql_message_id}")

                # Ожидаем ответа от SQL Agent с использованием TimeoutManager
                self.logger.info(f"DEBUG: Waiting for SQL result for compound {compound} using TimeoutManager")
                sql_result = await self.timeout_manager.execute_with_retry(
                    lambda: self._wait_for_sql_result(sql_message_id, timeout=180),
                    TimeoutOperationType.SQL_GENERATION
                )

                if sql_result.get("status") == "error":
                    error_msg = sql_result.get('error', 'Unknown SQL error')
                    self.logger.error(f"DEBUG: SQL Agent returned error for {compound}: {error_msg}")
                    raise Exception(f"SQL Agent error: {error_msg}")

                self.logger.info(f"DEBUG: SQL result received for compound {compound}, applying intelligent phase filtering")

                # Извлекаем данные из SQL результата
                search_results = sql_result.get("search_results", [])
                execution_result = sql_result.get("execution_result", {})

                # Сохраняем имена колонок для конвертации
                self._last_columns = execution_result.get("columns", [])

                temperature = search_request.common_params.get("temperature_k", 298.15)
                temperature_range = search_request.common_params.get("temperature_range_k", [298.15, 2000.0])

                # TEMPORARY DEBUG LOGGING - TO BE REMOVED LATER
                # Проверяем структуру данных до конвертации
                self.logger.info(f"DEBUG: Raw search_results type: {type(search_results)}")
                self.logger.info(f"DEBUG: execution_result keys: {list(execution_result.keys())}")
                self.logger.info(f"DEBUG: _last_columns: {self._last_columns}")
                if search_results:
                    self.logger.info(f"DEBUG: First result type: {type(search_results[0])}")
                    self.logger.info(f"DEBUG: First result: {search_results[0]}")
                    if len(search_results[0]) > 0:
                        self.logger.info(f"DEBUG: First result length: {len(search_results[0])}")

                # Конвертируем кортежи в словари
                converted_search_results = [
                    self._convert_row_to_dict(row) for row in search_results
                ]

                # TEMPORARY DEBUG LOGGING - TO BE REMOVED LATER
                # Проверяем структуру данных после конвертации
                if converted_search_results:
                    self.logger.info(f"DEBUG: First converted result: {converted_search_results[0]}")
                    self.logger.info(f"DEBUG: First converted result keys: {list(converted_search_results[0].keys())}")

                # Применяем интеллектуальный фильтр по фазам
                self.logger.info(f"DEBUG: Applying phase filter for {compound}: T={temperature}K, range={temperature_range}")
                filtered_data = self._filter_records_by_phase(converted_search_results, temperature, temperature_range)

                # Рассчитываем уверенность на основе качества отфильтрованных данных
                if filtered_data:
                    confidence = min(1.0, len(filtered_data) / 5.0)  # 5+ записей = высокая уверенность
                    if len(filtered_data) == 1:
                        confidence = min(0.9, confidence + 0.2)  # Одна запись - высокая точность
                else:
                    confidence = 0.0

                self.logger.info(f"DEBUG: Search completed for compound {compound}: {len(filtered_data)} records selected, confidence={confidence}")

                # TEMPORARY DEBUG LOGGING - TO BE REMOVED LATER
                # Логируем детальные результаты по соединению
                if self.config.session_logger and filtered_data:
                    # Ограничиваем количество записей для лога (максимум 10 для экономии места)
                    records_for_logging = filtered_data[:10]
                    self.config.session_logger.log_detailed_compound_records(
                        compound,
                        records_for_logging,
                        f"DETAILED RESULTS FOR {compound} (showing first {len(records_for_logging)} records)"
                    )

                    # Логируем сводную информацию по соединению
                    compound_summary = [{
                        "compound": compound,
                        "selected_records": filtered_data,
                        "confidence": confidence
                    }]
                    self.config.session_logger.log_compound_data_table(
                        compound_summary,
                        f"COMPOUND SUMMARY - {compound}"
                    )

                return IndividualCompoundResult(
                    compound=compound,
                    search_results=converted_search_results,
                    selected_records=filtered_data,
                    confidence=confidence,
                    errors=[]
                )

            except Exception as e:
                self.logger.error(f"DEBUG: Error searching compound {compound}: {e}")
                return IndividualCompoundResult(
                    compound=compound,
                    search_results=[],
                    selected_records=[],
                    confidence=0.0,
                    errors=[str(e)]
                )

    async def _wait_for_sql_result(self, message_id: str, timeout: int = 180) -> Dict:
        """Ожидать результат от SQL Agent с улучшенной обработкой."""
        start_time = asyncio.get_event_loop().time()
        self.logger.info(f"DEBUG: Waiting for SQL result for message {message_id}, timeout={timeout}s")

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Проверяем ответные сообщения
            messages = self.storage.receive_messages(
                self.agent_id,
                message_type="individual_sql_complete",
                correlation_id=message_id
            )

            if messages:
                self.logger.debug(f"DEBUG: Found {len(messages)} SQL result messages for {message_id}")

            for message in messages:
                status = message.payload.get("status")
                self.logger.debug(f"DEBUG: Received SQL message from {message.source_agent}: {status}")

                if status == "success":
                    self.logger.info(f"DEBUG: SQL result received successfully for message {message_id}")
                    return message.payload
                elif status == "error":
                    error_msg = message.payload.get("error", "Unknown error")
                    self.logger.error(f"DEBUG: SQL Agent returned error for message {message_id}: {error_msg}")
                    raise Exception(f"SQL Agent error: {error_msg}")

            # Уменьшаем задержку опроса для ускорения реакции
            await asyncio.sleep(0.2)

        elapsed = asyncio.get_event_loop().time() - start_time
        self.logger.error(f"DEBUG: SQL Agent timeout after {elapsed:.1f}s for message {message_id}")
        raise TimeoutError(f"SQL Agent response timeout for message {message_id} after {elapsed:.1f}s")

    # Метод _wait_for_filtering_result удален - больше не нужен, так как используется интеллектуальный фильтр в Individual Search Agent

    def _create_summary_table(self, individual_results: List[IndividualCompoundResult]) -> List[Dict]:
        """Создать сводную таблицу из результатов поиска."""
        summary_table = []

        for result in individual_results:
            if result.selected_records:
                # Добавляем лучшие записи для каждого соединения
                for record in result.selected_records:
                    summary_record = record.copy()
                    summary_record["compound"] = result.compound
                    summary_record["confidence"] = result.confidence
                    summary_table.append(summary_record)

        return summary_table

    def _filter_records_by_phase(self, records: List[Dict], temperature: float, temperature_range: List[float]) -> List[Dict]:
        """
        Интеллектуальный фильтр записей по фазовому состоянию на основе температурных данных.

        Args:
            records: Список записей из базы данных (уже сконвертированных в словари)
            temperature: Целевая температура в Кельвинах
            temperature_range: Температурный диапазон [min, max] в Кельвинах

        Returns:
            Отфильтрованный список записей с учетом фазовых состояний
        """
        if not records:
            return records

        filtered_records = []
        temp_min, temp_max = temperature_range

        # Анализируем каждую запись
        for record in records:
            # record теперь гарантированно словарь
            phase = record.get('Phase', '').lower()
            melting_point = record.get('MeltingPoint')
            boiling_point = record.get('BoilingPoint')

            # Если температурный диапазон охватывает все возможные фазы, включаем все
            if temp_min <= 273.15 and temp_max >= 3000:  # Очень широкий диапазон
                filtered_records.append(record)
                continue

            # Интеллектуальное определение фазы на основе температур плавления/кипения
            should_include = False

            if melting_point is not None and boiling_point is not None:
                melting_k = melting_point + 273.15
                boiling_k = boiling_point + 273.15

                # Определяем подходящую фазу для целевой температуры
                if temperature < melting_k:
                    # Твердая фаза
                    if phase == 's':
                        should_include = True
                elif melting_k <= temperature <= boiling_k:
                    # Жидкая фаза
                    if phase == 'l':
                        should_include = True
                elif temperature > boiling_k:
                    # Газообразная фаза
                    if phase == 'g':
                        should_include = True
            else:
                # Если нет данных о температурах плавления/кипения, используем химическую интуицию
                if temp_max < 500:  # Низкие температуры - скорее всего твердое
                    if phase in ['s', '']:
                        should_include = True
                elif temp_min > 1500:  # Высокие температуры - скорее всего газ
                    if phase in ['g', '']:
                        should_include = True
                else:  # Средние температуры - включаем все
                    should_include = True

            if should_include:
                filtered_records.append(record)

        return filtered_records

    def _convert_row_to_dict(self, row) -> Dict[str, Any]:
        """
        Конвертирует Row объект или кортеж в словарь.

        Args:
            row: Row объект из sqlite3 или кортеж

        Returns:
            Словарь с данными
        """
        if hasattr(row, 'keys'):
            # sqlite3.Row объект
            return dict(row)
        elif isinstance(row, (list, tuple)):
            # Кортеж с данными - нужен mapping имен колонок
            # Используем колонки из execution_result
            if hasattr(self, '_last_columns') and self._last_columns:
                return dict(zip(self._last_columns, row))
            else:
                # Fallback: возвращаем как есть, но это может вызвать ошибку
                return {f"col_{i}": val for i, val in enumerate(row)}
        else:
            # Уже словарь
            return row

    def _calculate_overall_confidence(self, individual_results: List[IndividualCompoundResult]) -> float:
        """Вычислить общую уверенность в результатах."""
        if not individual_results:
            return 0.0

        # Усреднение уверенности по всем найденным соединениям
        total_confidence = sum(result.confidence for result in individual_results)
        successful_results = len([r for r in individual_results if r.confidence > 0])

        if successful_results == 0:
            return 0.0

        return total_confidence / len(individual_results)

    def get_status(self) -> Dict:
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
            "config": {
                "max_parallel_searches": self.config.max_parallel_searches,
                "timeout_seconds": self.config.timeout_seconds,
            }
        }


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================

def create_individual_search_agent(
    storage: Optional[AgentStorage] = None,
    logger: Optional[logging.Logger] = None,
    max_parallel_searches: int = 5,
    timeout_seconds: int = 120,
) -> IndividualSearchAgent:
    """
    Создать Individual Search Agent.

    Args:
        storage: Хранилище (или будет использовано глобальное)
        logger: Логгер
        max_parallel_searches: Максимум параллельных поисков
        timeout_seconds: Таймаут для поиска одного вещества

    Returns:
        Настроенный Individual Search Agent
    """
    config = IndividualSearchAgentConfig(
        storage=storage or get_storage(),
        logger=logger or logging.getLogger(__name__),
        max_parallel_searches=max_parallel_searches,
        timeout_seconds=timeout_seconds,
    )

    return IndividualSearchAgent(config)


async def run_individual_search_agent_standalone(config: IndividualSearchAgentConfig):
    """
    Запустить агента в standalone режиме для тестирования.

    Args:
        config: Конфигурация агента
    """
    agent = IndividualSearchAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()
        print("Agent stopped")