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
from .prompts import RESULT_FILTER_ENGLISH_PROMPT
from .thermo_agents_logger import SessionLogger


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
    poll_interval: float = 0.2  # Оптимизировано с 1.0 до 0.2с
    max_retries: int = 4  # Увеличено с 3 до 4 для улучшенной надежности


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

        # Инициализация PydanticAI агента
        self.agent = self._initialize_agent()

        # Регистрация в хранилище
        self.storage.start_session(
            self.agent_id,
            {
                "status": "initialized",
                "capabilities": ["filter_results", "temperature_analysis", "compound_selection"],
            },
        )

        self.logger.info(f"ResultsFilteringAgent '{self.agent_id}' initialized")

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

    async def _process_message(self, message):
        """Обработать входящее сообщение для фильтрации результатов."""
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
                filtered_result = await self._llm_filter_records(
                    temp_filtered_records, columns, compounds, phases, temperature_range, target_temperature
                )

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
            self.logger.error(f"Error processing filtering message {message.id}: {e}")

            # Завершаем операцию с ошибкой
            if operation_context:
                operation_context.__exit__(type(e), e, e.__traceback__)

            # Определяем получателя для ошибки
            if message.message_type == "filter_individual_results":
                target_agent = "individual_search_agent"
                response_message_type = "individual_filter_complete"
            else:
                target_agent = "sql_agent"
                response_message_type = "results_filtered"

            # Отправляем сообщение об ошибке
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=target_agent,
                message_type=response_message_type,
                correlation_id=message.correlation_id,
                payload={
                    "status": "error",
                    "error": str(e),
                    "search_results": [],
                    "filtered_data": [],
                    "confidence": 0.0,
                },
            )

            if self.config.session_logger:
                self.config.session_logger.log_error(f"FILTERING ERROR: {str(e)}")

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
        Использование LLM для выбора наиболее релевантных записей с retry механизмом.

        Args:
            records: Предварительно отфильтрованные записи
            columns: Названия колонок
            compounds: Список запрашиваемых веществ
            phases: Список запрашиваемых фаз
            temperature_range: Температурный диапазон
            target_temperature: Целевая температура

        Returns:
            Результат LLM-фильтрации

        Raises:
            ValueError: Если не удалось выполнить LLM фильтрацию после всех попыток
        """
        max_llm_retries = 3
        base_timeout = 90.0  # Увеличено с 30 до 90 секунд

        last_error = None

        for attempt in range(max_llm_retries):
            try:
                # Увеличиваем таймаут с каждой попыткой
                current_timeout = base_timeout * (attempt + 1)

                # Уменьшаем объем данных для LLM при каждой попытке
                records_subset = records[:max(5, 50 - attempt * 15)]

                # Обновляем данные для LLM
                records_with_ids = []
                for i, record in enumerate(records_subset):
                    record_with_id = record.copy()
                    record_with_id["record_id"] = i
                    records_with_ids.append(record_with_id)

                analysis_data = {
                    "requested_compounds": compounds,
                    "requested_phases": phases,
                    "temperature_range_k": temperature_range,
                    "target_temperature_k": target_temperature,
                    "available_records": records_with_ids,
                    "total_records_count": len(records),
                    "attempt": attempt + 1,
                }

                yaml_data = yaml.dump(analysis_data, default_flow_style=False, allow_unicode=True)

                retry_prompt = f"""Analyze the following thermodynamic database records and select the most relevant ones for the requested compounds and conditions:

{yaml_data}

Your task is to select the optimal set of records that:
1. Best represents each requested compound in the correct phase
2. Provides good coverage of the temperature range {temperature_range[0]}-{temperature_range[1]}K
3. Includes complete thermodynamic data where possible

Consider that multiple records per compound may be needed for full temperature range coverage."""

                if attempt > 0:
                    retry_prompt += f"\n\nThis is retry attempt {attempt + 1}/{max_llm_retries}. Please focus on the most critical selections."

                self.logger.info(f"LLM filtering attempt {attempt + 1}/{max_llm_retries} with {len(records_subset)} records")

                # Генерируем фильтрацию с увеличенным таймаутом
                result = await asyncio.wait_for(
                    self.agent.run(retry_prompt, deps=self.config),
                    timeout=current_timeout
                )

                # Проверяем результат на finish_reason=None и другие проблемы OpenAI API
                if hasattr(result, 'usage') and result.usage is None:
                    raise ValueError("OpenAI API returned None usage")

                # Проверяем на пустой результат
                if result.output is None:
                    raise ValueError("OpenAI API returned None output")

                self.logger.info(f"LLM filtering successful on attempt {attempt + 1}")
                return result.output

            except asyncio.TimeoutError:
                last_error = f"LLM filtering timeout on attempt {attempt + 1}/{max_llm_retries}"
                self.logger.error(last_error)
                if attempt < max_llm_retries - 1:
                    await asyncio.sleep(2)  # Задержка перед повторной попыткой

            except Exception as e:
                error_str = str(e)
                last_error = f"LLM filtering error on attempt {attempt + 1}/{max_llm_retries}: {error_str}"

                # Обрабатываем конкретную ошибку finish_reason=None
                if "finish_reason" in error_str and "None" in error_str:
                    self.logger.error("OpenAI API finish_reason=None error")
                elif "status_code: 401" in error_str or "No auth credentials" in error_str:
                    raise ValueError("Ошибка аутентификации: проверьте API ключ для доступа к модели.")
                elif "status_code: 429" in error_str or "rate limit" in error_str.lower():
                    self.logger.error("Rate limit error detected")
                    if attempt < max_llm_retries - 1:
                        await asyncio.sleep(5)  # Ждем перед повторной попыткой
                else:
                    self.logger.error(last_error)

                if attempt < max_llm_retries - 1:
                    await asyncio.sleep(1)  # Задержка перед повторной попыткой

        # Если все попытки неудачны, используем базовую температурную фильтрацию без fallback
        self.logger.error(f"All LLM filtering attempts failed: {last_error}")

        # Создаем минимальный результат на основе температурной фильтрации
        selected_entries = []
        for i, record in enumerate(records[:10]):  # Берем первые 10 записей
            selected_entries.append(SelectedEntry(
                compound=record.get("Formula", ""),
                selected_id=i,
                reasoning=f"Temperature filtered record (LLM unavailable)"
            ))

        missing_compounds = [c for c in compounds if c not in [r.get("Formula", "") for r in records[:10]]]

        return FilteredResult(
            selected_entries=selected_entries,
            phase_determinations={},
            missing_compounds=missing_compounds,
            excluded_entries_count=len(records) - len(selected_entries),
            overall_confidence=0.3,  # Низкая уверенность без LLM
            warnings=[f"LLM filtering failed after {max_llm_retries} attempts: {last_error}"] +
                     [f"Missing compounds: {missing_compounds}"] if missing_compounds else [],
            filter_summary="Basic temperature filtering applied (LLM unavailable)"
        )

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
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
        }


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