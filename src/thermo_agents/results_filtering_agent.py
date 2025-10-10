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
    max_retries: int = 3  # Увеличено с 2 до 3 для улучшенной надежности


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
        self.logger.info(
            f"Processing results filtering request: {message.id} from {message.source_agent}"
        )

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

                self.logger.info(f"Filtering {len(rows)} records for {len(compounds)} compounds")
                if self.config.session_logger:
                    self.config.session_logger.log_info(
                        f"RESULTS FILTERING START: {len(rows)} records, target temp {target_temperature}K"
                    )

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

                self.logger.info(f"Filtering response sent to {target_agent}")

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

        except Exception as e:
            self.logger.error(f"Error processing filtering message {message.id}: {e}")

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
        Использование LLM для выбора наиболее релевантных записей.

        Args:
            records: Предварительно отфильтрованные записи
            columns: Названия колонок
            compounds: Список запрашиваемых веществ
            phases: Список запрашиваемых фаз
            temperature_range: Температурный диапазон
            target_temperature: Целевая температура

        Returns:
            Результат LLM-фильтрации
        """
        # Подготавливаем данные для LLM в YAML формате с ID записей
        records_with_ids = []
        for i, record in enumerate(records[:50]):  # Ограничиваем для LLM
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
        }

        # Конвертируем в YAML для лучшей читаемости LLM
        yaml_data = yaml.dump(analysis_data, default_flow_style=False, allow_unicode=True)

        prompt = f"""Analyze the following thermodynamic database records and select the most relevant ones for the requested compounds and conditions:

{yaml_data}

Your task is to select the optimal set of records that:
1. Best represents each requested compound in the correct phase
2. Provides good coverage of the temperature range {temperature_range[0]}-{temperature_range[1]}K
3. Includes complete thermodynamic data where possible

Consider that multiple records per compound may be needed for full temperature range coverage."""

        try:
            # Генерируем фильтрацию с уменьшенным тайм-аутом
            result = await asyncio.wait_for(
                self.agent.run(prompt, deps=self.config),
                timeout=30.0  # Уменьшено с 45 до 30 секунд для ускорения
            )

            # Проверяем результат на finish_reason=None и другие проблемы OpenAI API
            if hasattr(result, 'usage') and result.usage is None:
                self.logger.warning("OpenAI API returned None usage - using fallback filtering")
                return self._fallback_filter(records, compounds, phases)

            # Проверяем на пустой результат
            if result.output is None:
                self.logger.warning("OpenAI API returned None output - using fallback filtering")
                return self._fallback_filter(records, compounds, phases)

            return result.output

        except asyncio.TimeoutError:
            self.logger.error("LLM filtering timeout - using fallback filtering")
            return self._fallback_filter(records, compounds, phases)
        except Exception as e:
            # Обрабатываем конкретную ошибку finish_reason=None
            error_str = str(e)
            if "finish_reason" in error_str and "None" in error_str:
                self.logger.error("OpenAI API finish_reason=None error - using fallback filtering")
            else:
                self.logger.error(f"Error in LLM filtering: {e}")
            # Возвращаем базовую фильтрацию по формулам с улучшенной логикой
            return self._fallback_filter(records, compounds, phases)

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

    def _fallback_filter(self, records: List[Dict[str, Any]], compounds: List[str], phases: List[str]) -> FilteredResult:
        """Улучшенная резервная фильтрация без LLM."""
        selected = []
        reasoning = "Fallback filtering: selected records matching requested formulas and phases"

        # Улучшенный отбор по формулам и фазам
        if phases and len(phases) == len(compounds):
            # Если фазы указаны для каждого соединения
            for compound, phase in zip(compounds, phases):
                best_match = None
                best_score = -1

                for record in records:
                    formula = record.get("Formula", "")
                    record_phase = record.get("Phase", "")

                    # Проверяем точное совпадение формулы и фазы
                    if formula == compound and record_phase == phase:
                        # Проверяем качество записи (наличие всех необходимых полей)
                        score = 0
                        if record.get("H298") is not None: score += 1
                        if record.get("S298") is not None: score += 1
                        if record.get("Tmin") is not None and record.get("Tmax") is not None: score += 1

                        # Выбираем запись с максимальным количеством данных
                        if score > best_score:
                            best_score = score
                            best_match = record

                if best_match:
                    selected.append(best_match)
        else:
            # Если фазы не указаны или их количество не совпадает
            for compound in compounds:
                best_match = None
                best_score = -1

                for record in records:
                    formula = record.get("Formula", "")
                    record_phase = record.get("Phase", "")

                    # Проверяем совпадение формулы (любая фаза)
                    if formula == compound:
                        score = 0
                        if record.get("H298") is not None: score += 1
                        if record.get("S298") is not None: score += 1
                        if record.get("Tmin") is not None and record.get("Tmax") is not None: score += 1

                        if score > best_score:
                            best_score = score
                            best_match = record

                if best_match:
                    selected.append(best_match)

        # Создаем SelectedEntry объекты для fallback
        selected_entries = []
        for record in selected:
            # Находим оригинальный ID записи в исходном массиве
            original_id = records.index(record) if record in records else len(selected_entries)
            selected_entries.append(SelectedEntry(
                compound=record.get("Formula", ""),
                selected_id=original_id,
                reasoning=f"Fallback selected: {record.get('Formula', '')} ({record.get('Phase', '')})"
            ))

        # Определяем отсутствующие соединения
        found_compounds = [record.get("Formula", "") for record in selected]
        missing_compounds = [c for c in compounds if c not in found_compounds]

        return FilteredResult(
            selected_entries=selected_entries,
            phase_determinations={},
            missing_compounds=missing_compounds,
            excluded_entries_count=len(records) - len(selected),
            overall_confidence=0.6 if missing_compounds else 0.8,  # Выше уверенность если все найдены
            warnings=["Used enhanced fallback filtering due to LLM error"] +
                     [f"Missing compounds: {missing_compounds}"] if missing_compounds else [],
            filter_summary=reasoning
        )

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