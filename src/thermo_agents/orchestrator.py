"""
Оркестратор для координации работы термодинамической системы v2.0.

Рефакторингованная версия с использованием детерминированной логики
вместо LLM-агентов для поиска, фильтрации и агрегации данных.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from .agent_storage import AgentStorage, get_storage

# Определение поддержки Unicode для консоли
try:
    USE_EMOJI = sys.stdout.encoding and "utf" in sys.stdout.encoding.lower()
except AttributeError:
    USE_EMOJI = False

# Символы с fallback для Windows
SYMBOLS = {
    "success": "✅" if USE_EMOJI else "[OK]",
    "error": "❌" if USE_EMOJI else "[ОШИБКА]",
    "warning": "⚠️" if USE_EMOJI else "[ВНИМАНИЕ]",
    "data": "📊" if USE_EMOJI else "[ДАННЫЕ]",
    "idea": "💡" if USE_EMOJI else "[СОВЕТ]",
}


from .aggregation.reaction_aggregator import ReactionAggregator
from .aggregation.statistics_formatter import StatisticsFormatter
from .aggregation.table_formatter import TableFormatter
from .filtering.filter_pipeline import FilterContext, FilterPipeline, FilterResult
from .models.aggregation import AggregatedReactionData, FilterStatistics
from .models.search import CompoundSearchResult
from .models.extraction import ExtractedReactionParameters
from .search.compound_searcher import CompoundSearcher
from .thermodynamic_agent import ThermodynamicAgent


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

    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    max_retries: int = 2
    timeout_seconds: int = 90


class ThermoOrchestrator:
    """
    Упрощённый оркестратор термодинамической системы v2.0.

    Основные обязанности:
    - Извлечение параметров через ThermodynamicAgent (LLM)
    - Поиск и фильтрация через детерминированные модули
    - Агрегация результатов и форматирование ответов
    """

    def __init__(
        self,
        thermodynamic_agent: ThermodynamicAgent,
        compound_searcher: CompoundSearcher,
        filter_pipeline: FilterPipeline,
        reaction_aggregator: ReactionAggregator,
        table_formatter: TableFormatter,
        statistics_formatter: StatisticsFormatter,
        config: Optional[OrchestratorConfig] = None,
    ):
        """
        Инициализация оркестратора с новыми компонентами.

        Args:
            thermodynamic_agent: Агент извлечения параметров
            compound_searcher: Модуль поиска соединений
            filter_pipeline: Конвейер фильтрации
            reaction_aggregator: Агрегатор данных реакции
            table_formatter: Форматирование таблиц
            statistics_formatter: Форматирование статистики
            config: Конфигурация оркестратора
        """
        self.thermodynamic_agent = thermodynamic_agent
        self.compound_searcher = compound_searcher
        self.filter_pipeline = filter_pipeline
        self.reaction_aggregator = reaction_aggregator
        self.table_formatter = table_formatter
        self.statistics_formatter = statistics_formatter

        self.config = config or OrchestratorConfig()
        self.storage = self.config.storage
        self.logger = self.config.logger

        # Регистрация в хранилище
        self.agent_id = "orchestrator_v2"
        self.storage.start_session(self.agent_id, {"status": "ready"})

    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса пользователя.

        Новый поток:
        1. Извлечение параметров (LLM)
        2. Поиск для каждого вещества (детерминированный)
        3. Фильтрация для каждого вещества (детерминированный)
        4. Агрегация результатов
        5. Форматирование ответа

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный текстовый ответ
        """
        try:
            # Шаг 1: Извлечение параметров
            params = await self.thermodynamic_agent.extract_parameters(user_query)

            # Шаг 2-3: Поиск и фильтрация для каждого вещества
            compound_results = []
            for compound in params.all_compounds:
                result = await self._search_and_filter_compound(
                    compound, params.temperature_range_k, params
                )
                compound_results.append(result)

            # Шаг 4: Агрегация
            aggregated_data = self.reaction_aggregator.aggregate_reaction_data(
                reaction_equation=params.balanced_equation,
                compounds_results=compound_results,
            )

            # Форматирование таблицы
            aggregated_data.summary_table_formatted = (
                self.table_formatter.format_summary_table(compound_results)
            )

            # Шаг 5: Форматирование ответа
            response = self._format_response(aggregated_data)

            return response

        except Exception as e:
            import traceback

            print(f"DEBUG: Exception details:")
            print(f"  Type: {type(e)}")
            print(f"  Message: {str(e)}")
            traceback.print_exc()
            return self._format_error_response(str(e))

    async def _search_and_filter_compound(
        self,
        compound: str,
        temperature_range: Tuple[float, float],
        reaction_params: Optional[ExtractedReactionParameters] = None
    ) -> CompoundSearchResult:
        """Поиск и фильтрация для одного вещества."""
        # Поиск
        search_result = self.compound_searcher.search_compound(
            compound, temperature_range
        )

        # Фильтрация с параметрами реакции
        filter_context = FilterContext(
            temperature_range=temperature_range,
            compound_formula=compound,
            reaction_params=reaction_params
        )

        filter_result = self.filter_pipeline.execute(
            search_result.records_found, filter_context
        )

        # Обновление результата
        search_result.records_found = filter_result.filtered_records
        search_result.filter_statistics = self._build_filter_statistics(filter_result)

        return search_result

    def _build_filter_statistics(self, filter_result: FilterResult) -> FilterStatistics:
        """Преобразование FilterResult в FilterStatistics."""
        stats = filter_result.stage_statistics

        # Защита от некорректных данных
        if not isinstance(stats, list):
            print(f"DEBUG: stats is not a list, it's {type(stats)}: {stats}")
            stats = []

        return FilterStatistics(
            stage_1_initial_matches=stats[0]["records_before"] if len(stats) > 0 else 0,
            stage_1_description=stats[0]["stage_name"] if len(stats) > 0 else "",
            stage_2_temperature_filtered=stats[1]["records_after"]
            if len(stats) > 1
            else 0,
            stage_2_description=stats[1]["stage_name"] if len(stats) > 1 else "",
            stage_3_phase_selected=stats[2]["records_after"] if len(stats) > 2 else 0,
            stage_3_description=stats[2]["stage_name"] if len(stats) > 2 else "",
            stage_4_final_selected=stats[3]["records_after"] if len(stats) > 3 else 0,
            stage_4_description=stats[3]["stage_name"] if len(stats) > 3 else "",
            is_found=filter_result.is_found,
            failure_stage=filter_result.failure_stage,
            failure_reason=filter_result.failure_reason,
        )

    def _format_response(self, data: AggregatedReactionData) -> str:
        """
        Форматирование финального ответа пользователю.

        Формат:
        ✅ Термодинамические данные для реакции:
           [equation] при [T_range]K

        📊 Найденные данные (tabulate):
        [таблица]

        📈 Детальная статистика фильтрации:
        [дерево статистики]

        ⚠️ Предупреждения:
        [список предупреждений]

        ❌ Ненайденные вещества:
        [список]
        """
        lines = []

        # Заголовок
        if data.completeness_status == "complete":
            lines.append("✅ Термодинамические данные для реакции:")
        elif data.completeness_status == "partial":
            lines.append("⚠️ Частичные термодинамические данные для реакции:")
        else:
            lines.append("❌ Термодинамические данные для реакции:")

        lines.append(f"   {data.reaction_equation}")
        lines.append("")

        # Таблица данных (только если есть найденные вещества)
        if data.found_compounds:
            lines.append("📊 Найденные данные:")
            lines.append(data.summary_table_formatted)
            lines.append("")

        # Детальная статистика
        lines.append(
            self.statistics_formatter.format_detailed_statistics(
                data.detailed_statistics
            )
        )

        # Предупреждения
        if data.warnings:
            lines.append("⚠️ Предупреждения:")
            for warning in data.warnings:
                lines.append(f"   - {warning}")
            lines.append("")

        # Ненайденные вещества
        if data.missing_compounds:
            lines.append("❌ Ненайденные вещества:")
            lines.append(f"   {', '.join(data.missing_compounds)}")
            lines.append("")

        # Рекомендации
        if data.recommendations:
            lines.append("💡 Рекомендация:")
            for rec in data.recommendations:
                lines.append(f"   {rec}")
            lines.append("")

        return "\n".join(lines)

    def _format_error_response(self, error_message: str) -> str:
        """Форматирование ответа об ошибке."""
        return f"""
❌ Ошибка обработки запроса:
   {error_message}

💡 Попробуйте:
   - Уточнить формулы веществ
   - Указать температурный диапазон
   - Упростить запрос
"""

    async def process_request(
        self, request: OrchestratorRequest
    ) -> OrchestratorResponse:
        """
        Обработать запрос пользователя для обратной совместимости.

        Args:
            request: Запрос пользователя

        Returns:
            Результат обработки
        """
        try:
            response_text = await self.process_query(request.user_query)
            return OrchestratorResponse(
                success=True,
                result={"response": response_text},
                trace=["Processed via new orchestrator v2"],
            )
        except Exception as e:
            return OrchestratorResponse(
                success=False,
                result={},
                errors=[str(e)],
                trace=["Error in new orchestrator v2"],
            )

    async def shutdown(self):
        """Завершить работу оркестратора."""
        self.logger.info("Shutting down orchestrator v2")
        self.storage.end_session(self.agent_id)

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора и системы."""
        return {
            "orchestrator": self.storage.get_session(self.agent_id),
            "storage_stats": self.storage.get_stats(),
            "active_agents": list(self.storage._agent_sessions.keys()),
        }
