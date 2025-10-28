"""
Оптимизированный оркестратор для координации работы термодинамической системы v2.0.

Рефакторингованная версия с использованием детерминированной логики
и прямых вызовов без message passing для максимальной производительности.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

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
from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .filtering.filter_pipeline import FilterContext, FilterPipeline, FilterResult
from .formatting.compound_data_formatter import CompoundDataFormatter
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .models.aggregation import AggregatedReactionData, FilterStatistics
from .models.extraction import ExtractedReactionParameters
from .models.search import CompoundSearchResult
from .search.compound_searcher import CompoundSearcher
from .thermodynamic_agent import ThermodynamicAgent
from .session_logger import SessionLogger


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
    """
    Оптимизированная конфигурация оркестратора без dependencies от AgentStorage.
    """
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    max_retries: int = 2
    timeout_seconds: int = 90


class ThermoOrchestrator:
    """
    Оптимизированный оркестратор термодинамической системы v2.0.

    Основные обязанности:
    - Извлечение параметров через ThermodynamicAgent (LLM)
    - Поиск и фильтрация через детерминированные модули с прямыми вызовами
    - Агрегация результатов и форматирование ответов
    - Высокая производительность без message passing overhead
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
        Инициализация оптимизированного оркестратора.

        Args:
            thermodynamic_agent: Агент извлечения параметров
            compound_searcher: Модуль поиска соединений
            filter_pipeline: Оптимизированный конвейер фильтрации
            reaction_aggregator: Агрегатор данных реакции
            table_formatter: Форматирование таблиц
            statistics_formatter: Форматирование статистики
            config: Оптимизированная конфигурация оркестратора
        """
        self.thermodynamic_agent = thermodynamic_agent
        self.compound_searcher = compound_searcher
        self.filter_pipeline = filter_pipeline
        self.reaction_aggregator = reaction_aggregator
        self.table_formatter = table_formatter
        self.statistics_formatter = statistics_formatter

        self.config = config or OrchestratorConfig()
        self.logger = self.config.logger

        # Оптимизация: убрана зависимость от AgentStorage
        self.agent_id = "orchestrator_v2_optimized"

    async def process_query(self, user_query: str) -> str:
        """
        Оптимизированная обработка запроса пользователя с прямыми вызовами.

        Поток выполнения:
        1. Извлечение параметров (LLM)
        2. Поиск для каждого вещества (детерминированный, прямой вызов)
        3. Фильтрация для каждого вещества (детерминированный, прямой вызов)
        4. Агрегация результатов (прямой вызов)
        5. Форматирование ответа (прямой вызов)

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
        reaction_params: Optional[ExtractedReactionParameters] = None,
    ) -> CompoundSearchResult:
        """
        Оптимизированный поиск и фильтрация для одного вещества.

        Особенности оптимизации:
        - Прямые вызовы без message passing
        - Убраны лишние зависимости от storage
        - Быстрая обработка с детерминированной логикой
        """
        # Извлекаем названия соединений из параметров реакции
        compound_names = None
        if reaction_params and reaction_params.compound_names:
            compound_names = reaction_params.compound_names.get(compound, [])

        # Поиск
        search_result = self.compound_searcher.search_compound(
            compound, temperature_range, compound_names=compound_names
        )

        # Фильтрация с параметрами реакции
        filter_context = FilterContext(
            temperature_range=temperature_range,
            compound_formula=compound,
            reaction_params=reaction_params,
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
        """
        Оптимизированное завершение работы оркестратора.

        Убрана зависимость от AgentStorage для быстрого завершения.
        """
        self.logger.info("Shutting down optimized orchestrator v2")

    def get_status(self) -> Dict[str, Any]:
        """
        Получить базовый статус оркестратора без dependencies от storage.
        """
        return {
            "orchestrator_id": self.agent_id,
            "status": "optimized",
            "components": {
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__,
                "compound_searcher": type(self.compound_searcher).__name__,
                "filter_pipeline": type(self.filter_pipeline).__name__,
                "reaction_aggregator": type(self.reaction_aggregator).__name__,
                "table_formatter": type(self.table_formatter).__name__,
                "statistics_formatter": type(self.statistics_formatter).__name__,
            }
        }


class Orchestrator:
    """
    Оркестратор с маршрутизацией запросов по типам для output formats v2.1.

    Поддерживает два типа запросов:
    - compound_data: запросы данных по отдельным веществам
    - reaction_calculation: расчёты термодинамики реакций
    """

    def __init__(
        self,
        thermodynamic_agent: ThermodynamicAgent,
        compound_searcher: CompoundSearcher,
        filter_pipeline: FilterPipeline,
        config: Optional[OrchestratorConfig] = None,
        session_logger: Optional[SessionLogger] = None,
    ):
        """
        Инициализация оркестратора с маршрутизацией.

        Args:
            thermodynamic_agent: Агент извлечения параметров
            compound_searcher: Поисковик соединений
            filter_pipeline: Конвейер фильтрации
            config: Конфигурация оркестратора
            session_logger: Логгер сессии (опционально)
        """
        self.thermodynamic_agent = thermodynamic_agent
        self.compound_searcher = compound_searcher
        self.filter_pipeline = filter_pipeline
        self.session_logger = session_logger

        # Новые компоненты для форматирования v2.1
        self.calculator = ThermodynamicCalculator()
        self.compound_formatter = CompoundDataFormatter(self.calculator)
        self.reaction_formatter = ReactionCalculationFormatter(self.calculator)

        self.config = config or OrchestratorConfig()
        self.logger = self.config.logger

    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса пользователя с маршрутизацией по типу.

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный ответ
        """
        try:
            self.logger.info(f"Обработка запроса: {user_query}")

            # Логирование запроса пользователя
            if self.session_logger:
                self.session_logger.log_llm_request(user_query)

            # Извлечение параметров с замером времени
            import time
            start_time = time.time()

            try:
                params = await self.thermodynamic_agent.extract_parameters(user_query)
                duration = time.time() - start_time

                # Логирование успешного ответа LLM
                if self.session_logger:
                    params_dict = params.model_dump()
                    self.session_logger.log_llm_response(
                        response=params_dict,
                        duration=duration,
                        model=getattr(self.thermodynamic_agent, 'model_name', 'unknown')
                    )
            except Exception as e:
                duration = time.time() - start_time
                # Логирование ошибки LLM
                if self.session_logger:
                    self.session_logger.log_llm_error(e, raw_response="")
                raise

            self.logger.debug(f"Извлечённые параметры: query_type={params.query_type}")

            # Маршрутизация по типу запроса
            if params.query_type == "compound_data":
                self.logger.info("Маршрутизация → compound_data")
                return await self._process_compound_data(params)
            else:  # reaction_calculation
                self.logger.info("Маршрутизация → reaction_calculation")
                return await self._process_reaction_calculation(params)

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return f"❌ Ошибка обработки запроса: {str(e)}"

    async def _process_compound_data(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Обработка запроса данных по веществу.

        Шаги:
        1. Поиск вещества в базе
        2. Фильтрация записей (фаза, температура)
        3. Форматирование результата
        """
        if not params.all_compounds:
            return "❌ Не указано вещество для поиска"

        formula = params.all_compounds[0]
        T_min, T_max = params.temperature_range_k

        # Поиск вещества
        search_result = self.compound_searcher.search_compound(
            formula=formula,
            temperature_range=(T_min, T_max),
            compound_names=params.compound_names.get(formula, []) if params.compound_names else None
        )

        if not search_result.records_found:
            return f"❌ Вещество {formula} не найдено в базе данных"

        # Фильтрация записей
        filter_context = FilterContext(
            temperature_range=(T_min, T_max),
            compound_formula=formula,
            reaction_params=params
        )

        filter_result = self.filter_pipeline.execute(
            search_result.records_found, filter_context
        )

        if not filter_result.filtered_records:
            return f"❌ Не найдено записей для {formula} в диапазоне {T_min}-{T_max}K"

        # Обновление результата поиска
        search_result.records_found = filter_result.filtered_records

        # Форматирование
        return self.compound_formatter.format_response(
            result=search_result,
            T_min=T_min,
            T_max=T_max,
            step_k=params.temperature_step_k
        )

    async def _process_reaction_calculation(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Обработка запроса расчёта реакции.

        Шаги:
        1. Поиск всех веществ реакции
        2. Фильтрация по фазе и температуре
        3. Расчёт термодинамики
        4. Форматирование результата
        """
        T_min, T_max = params.temperature_range_k
        T_mid = (T_min + T_max) / 2

        # Поиск реагентов
        reactant_results = []
        for formula in params.reactants:
            result = self.compound_searcher.search_compound(
                formula=formula,
                temperature_range=(T_min, T_max),
                compound_names=params.compound_names.get(formula, []) if params.compound_names else None
            )
            reactant_results.append(result)

        # Поиск продуктов
        product_results = []
        for formula in params.products:
            result = self.compound_searcher.search_compound(
                formula=formula,
                temperature_range=(T_min, T_max),
                compound_names=params.compound_names.get(formula, []) if params.compound_names else None
            )
            product_results.append(result)

        # Проверка, что все вещества найдены
        all_results = reactant_results + product_results
        missing = [r.compound_formula for r in all_results if not r.records_found]
        if missing:
            return f"❌ Не найдены вещества: {', '.join(missing)}"

        # Фильтрация записей по температурному диапазону
        for result in all_results:
            filter_context = FilterContext(
                temperature_range=(T_min, T_max),
                compound_formula=result.compound_formula,
                reaction_params=params
            )

            filter_result = self.filter_pipeline.execute(
                result.records_found, filter_context
            )
            result.records_found = filter_result.filtered_records

        # Форматирование
        return self.reaction_formatter.format_response(
            params=params,
            reactants=reactant_results,
            products=product_results,
            step_k=params.temperature_step_k
        )

    async def shutdown(self):
        """
        Завершение работы оркестратора.
        """
        self.logger.info("Shutting down orchestrator v2.1")

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора."""
        return {
            "orchestrator_type": "output_formats_v2.1",
            "status": "active",
            "components": {
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__,
                "compound_searcher": type(self.compound_searcher).__name__,
                "filter_pipeline": type(self.filter_pipeline).__name__,
                "calculator": type(self.calculator).__name__,
                "compound_formatter": type(self.compound_formatter).__name__,
                "reaction_formatter": type(self.reaction_formatter).__name__,
            }
        }
