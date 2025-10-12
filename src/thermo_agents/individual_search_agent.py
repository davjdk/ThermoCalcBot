"""
Individual Search Agent - координатор параллельного поиска соединений.

Обеспечивает индивидуальный поиск каждого вещества с последующей агрегацией результатов.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4

from .agent_storage import AgentStorage, get_storage
from .thermo_agents_logger import SessionLogger
from .thermodynamic_agent import (
    AggregatedResults,
    IndividualCompoundResult,
    IndividualSearchRequest,
)


@dataclass
class IndividualSearchAgentConfig:
    """Конфигурация Individual Search Agent."""

    agent_id: str = "individual_search_agent"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 0.5  # Уменьшено с 1.0 до 0.5с для ускорения реакции
    max_retries: int = 3  # Увеличено с 2 до 3 для улучшенной надежности
    timeout_seconds: int = 300  # Увеличено с 90 до 300 секунд для обработки сложных запросов
    max_parallel_searches: int = 6  # Увеличено с 4 до 6 для улучшения производительности


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

            # Сохраняем результаты
            result_key = f"individual_search_result_{message.id}"
            self.storage.set(
                result_key,
                aggregated_results.model_dump(),
                ttl_seconds=1800  # 30 минут
            )

            # Отправляем ответ
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="individual_search_complete",
                correlation_id=message.id,
                payload={
                    "status": "success",
                    "result_key": result_key,
                    "aggregated_results": aggregated_results.model_dump(),
                },
            )

            self.logger.info(
                f"Individual search completed: {len(aggregated_results.individual_results)} compounds processed"
            )

        except Exception as e:
            self.logger.error(f"Error processing search request {message.id}: {e}")

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
                if result.confidence < 0.5:
                    warnings.append(
                        f"Low confidence ({result.confidence:.2f}) for compound {compound}"
                    )

        # Создаем сводную таблицу
        summary_table = self._create_summary_table(individual_results)

        # Вычисляем общую уверенность
        overall_confidence = self._calculate_overall_confidence(individual_results)

        return AggregatedResults(
            individual_results=individual_results,
            summary_table=summary_table,
            overall_confidence=overall_confidence,
            missing_compounds=missing_compounds,
            warnings=warnings
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

                # Ожидаем ответа от SQL Agent
                self.logger.info(f"DEBUG: Waiting for SQL result for compound {compound}")
                sql_result = await self._wait_for_sql_result(sql_message_id, timeout=180)  # Используем фиксированный таймаут 180 секунд

                if sql_result.get("status") == "error":
                    error_msg = sql_result.get('error', 'Unknown SQL error')
                    self.logger.error(f"DEBUG: SQL Agent returned error for {compound}: {error_msg}")
                    raise Exception(f"SQL Agent error: {error_msg}")

                self.logger.info(f"DEBUG: SQL result received for compound {compound}, waiting for filtering")

                # SQL Agent отправит запрос к Database Agent, затем к Filtering Agent
                # Ждем финального результата от Filtering Agent
                self.logger.info(f"DEBUG: Waiting for filtering result for compound {compound}")
                final_result = await self._wait_for_filtering_result(search_id, timeout=180)  # Используем фиксированный таймаут 180 секунд

                if final_result.get("status") == "error":
                    error_msg = final_result.get('error', 'Unknown filtering error')
                    self.logger.error(f"DEBUG: Filtering Agent returned error for {compound}: {error_msg}")
                    raise Exception(f"Filtering Agent error: {error_msg}")

                # Формируем результат для одного соединения
                filtered_data = final_result.get("filtered_data", [])
                confidence = final_result.get("confidence", 0.0)

                self.logger.info(f"DEBUG: Search completed for compound {compound}: {len(filtered_data)} records selected, confidence={confidence}")

                return IndividualCompoundResult(
                    compound=compound,
                    search_results=final_result.get("search_results", []),
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

    async def _wait_for_filtering_result(self, search_id: str, timeout: int = 180) -> Dict:
        """Ожидать результат от Filtering Agent с улучшенной обработкой."""
        start_time = asyncio.get_event_loop().time()
        self.logger.info(f"DEBUG: Waiting for filtering result for search {search_id}, timeout={timeout}s")

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Проверяем сообщения о завершении фильтрации
            messages = self.storage.receive_messages(
                self.agent_id,
                message_type="individual_filter_complete",
                correlation_id=search_id
            )

            if messages:
                self.logger.debug(f"DEBUG: Found {len(messages)} filtering result messages for {search_id}")

            for message in messages:
                status = message.payload.get("status")
                self.logger.debug(f"DEBUG: Received filtering message from {message.source_agent}: {status}")

                if status == "success":
                    self.logger.info(f"DEBUG: Filtering result received successfully for search {search_id}")
                    return message.payload
                elif status == "error":
                    error_msg = message.payload.get("error", "Unknown filtering error")
                    self.logger.error(f"DEBUG: Filtering Agent returned error for search {search_id}: {error_msg}")
                    raise Exception(f"Filtering Agent error: {error_msg}")
                elif status == "no_results":
                    self.logger.warning(f"DEBUG: Filtering Agent found no results for search {search_id}")
                    return message.payload

            # Уменьшаем задержку опроса для ускорения реакции
            await asyncio.sleep(0.2)

        elapsed = asyncio.get_event_loop().time() - start_time
        self.logger.error(f"DEBUG: Filtering Agent timeout after {elapsed:.1f}s for search {search_id}")
        raise TimeoutError(f"Filtering Agent response timeout for search {search_id} after {elapsed:.1f}s")

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