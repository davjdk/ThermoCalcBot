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
from .thermo_agents_logger import SessionLogger


class FilteredResult(BaseModel):
    """Результат фильтрации записей."""

    selected_records: List[Dict[str, Any]]  # Выбранные записи
    reasoning: str  # Обоснование выбора
    temperature_coverage: Dict[str, Any]  # Анализ покрытия температурного диапазона
    compounds_analysis: Dict[str, Any]  # Анализ по веществам


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
    poll_interval: float = 1.0
    max_retries: int = 2


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

        system_prompt = """You are a thermodynamic data filtering expert. Your task is to select the most relevant database records for specific compounds and phases within a given temperature range.

TASK:
1. Analyze all provided database records
2. For each requested compound and phase, select the MOST RELEVANT records that:
   - Cover the requested temperature range (even partial overlap is acceptable)
   - Represent the correct chemical formula and phase
   - Provide the best thermodynamic data quality

SELECTION CRITERIA:
- Temperature range coverage: Records should overlap with the requested temperature range
- Phase accuracy: Must match the requested phase (s/l/g/aq)
- Formula accuracy: Must match the requested chemical formula
- Data completeness: Prefer records with complete thermodynamic data (H298, S298, f1-f6)
- Temperature range width: For broad coverage, multiple records per compound may be needed

IMPORTANT RULES:
- If multiple records exist for the same compound and phase, select the one with the best temperature range coverage
- If no single record covers the entire temperature range, select multiple complementary records
- Always prioritize phase-accurate matches
- Provide clear reasoning for your selections

OUTPUT FORMAT:
- selected_records: List of chosen database records
- reasoning: Detailed explanation of selection criteria and decisions
- temperature_coverage: Analysis of how well the selection covers the requested temperature range
- compounds_analysis: Per-compound analysis of the selections made"""

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
                # Получаем сообщения на фильтрацию результатов
                messages = self.storage.receive_messages(
                    self.agent_id, message_type="filter_results"
                )

                # Обрабатываем каждое сообщение
                for message in messages:
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
            # Извлекаем данные из сообщения
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

                # Сохраняем результат в хранилище
                result_key = f"filtered_result_{message.id}"
                result_data = {
                    "filtered_result": filtered_result.model_dump(),
                    "original_count": len(rows),
                    "temp_filtered_count": len(temp_filtered_records),
                    "final_count": len(filtered_result.selected_records),
                    "extracted_params": extracted_params,
                }

                self.storage.set(result_key, result_data, ttl_seconds=600)
                self.logger.info(f"Filtering result stored with key: {result_key}")

                # Логируем финальную отфильтрованную таблицу
                self._log_filtered_table(filtered_result.selected_records, filtered_result.reasoning)

                # Отправляем ответ SQL агенту (который ожидает результат)
                # Поскольку database_agent пересылает correlation_id от SQL агента,
                # нам нужно найти, кто изначально отправил запрос SQL агенту
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="sql_agent",  # Всегда отправляем SQL агенту
                    message_type="results_filtered",
                    correlation_id=message.correlation_id,  # Используем исходный correlation_id
                    payload={
                        "status": "success",
                        "result_key": result_key,
                        "filtered_result": filtered_result.model_dump(),
                        "statistics": {
                            "original_count": len(rows),
                            "temp_filtered_count": len(temp_filtered_records),
                            "final_count": len(filtered_result.selected_records),
                        },
                    },
                )

                self.logger.info("Filtering response sent to sql_agent")

            else:
                # Нет записей после температурной фильтрации
                self.logger.warning("No records remain after temperature filtering")
                self.storage.send_message(
                    source_agent=self.agent_id,
                    target_agent="sql_agent",  # Всегда отправляем SQL агенту
                    message_type="results_filtered",
                    correlation_id=message.correlation_id,  # Используем исходный correlation_id
                    payload={
                        "status": "no_results",
                        "error": "No records found in the specified temperature range",
                        "statistics": {
                            "original_count": len(rows),
                            "temp_filtered_count": 0,
                            "final_count": 0,
                        },
                    },
                )

        except Exception as e:
            self.logger.error(f"Error processing filtering message {message.id}: {e}")

            # Отправляем сообщение об ошибке SQL агенту
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent="sql_agent",  # Всегда отправляем SQL агенту
                message_type="results_filtered",
                correlation_id=message.correlation_id,  # Используем исходный correlation_id
                payload={"status": "error", "error": str(e)},
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
        # Подготавливаем данные для LLM в YAML формате
        analysis_data = {
            "requested_compounds": compounds,
            "requested_phases": phases,
            "temperature_range_k": temperature_range,
            "target_temperature_k": target_temperature,
            "available_records": records[:50],  # Ограничиваем для LLM
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
            # Генерируем фильтрацию с тайм-аутом
            result = await asyncio.wait_for(
                self.agent.run(prompt, deps=self.config),
                timeout=90.0  # 90 секунд на анализ
            )

            return result.output

        except Exception as e:
            self.logger.error(f"Error in LLM filtering: {e}")
            # Возвращаем базовую фильтрацию по формулам
            return self._fallback_filter(records, compounds, phases)

    def _fallback_filter(self, records: List[Dict[str, Any]], compounds: List[str], phases: List[str]) -> FilteredResult:
        """Резервная фильтрация без LLM."""
        selected = []
        reasoning = "Fallback filtering: selected records matching requested formulas and phases"

        # Простой отбор по формулам и фазам
        for compound, phase in zip(compounds, phases):
            for record in records:
                formula = record.get("Formula", "")
                record_phase = record.get("Phase", "")

                if (formula == compound or formula == f"{compound}({phase})") and record_phase == phase:
                    selected.append(record)
                    break

        return FilteredResult(
            selected_records=selected,
            reasoning=reasoning,
            temperature_coverage={"status": "basic_matching"},
            compounds_analysis={"method": "formula_phase_matching"}
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