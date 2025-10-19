"""
Многофазный оркестратор термодинамической системы.

Интегрирует многофазные расчёты с StaticDataManager и обновлёнными компонентами.
Использует Big Bang стратегию - всегда многофазные расчёты.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
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

from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .config.multi_phase_config import (
    MULTI_PHASE_CONFIG,
    get_static_cache_dir,
    get_integration_points,
    is_multi_phase_enabled,
)
from .filtering.filter_pipeline import FilterContext, FilterPipeline, FilterResult
from .formatting.compound_data_formatter import CompoundDataFormatter
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .models.extraction import ExtractedReactionParameters
from .models.search import CompoundSearchResult, MultiPhaseSearchResult
from .search.compound_searcher import CompoundSearcher
from .search.database_connector import DatabaseConnector
from .search.sql_builder import SQLBuilder
from .storage.static_data_manager import StaticDataManager
from .thermodynamic_agent import ThermodynamicAgent


@dataclass
class MultiPhaseOrchestratorConfig:
    """
    Конфигурация многофазного оркестратора.
    """
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    max_retries: int = 2
    timeout_seconds: int = 90

    # Настройки многофазных расчётов
    static_cache_dir: Optional[str] = None
    integration_points: Optional[int] = None

    # Базовые компоненты
    db_path: str = "data/thermo_data.db"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"


class MultiPhaseOrchestrator:
    """
    Многофазный оркестратор термодинамической системы.

    Особенности:
    - ВСЕГДА использует многофазные расчёты (Big Bang стратегия)
    - Интегрирован StaticDataManager для YAML кэша
    - Поддержка фазовых переходов
    - Автоматическое определение сегментов
    """

    def __init__(self, config: MultiPhaseOrchestratorConfig):
        """
        Инициализация многофазного оркестратора.

        Args:
            config: Конфигурация оркестратора
        """
        self.config = config
        self.logger = config.logger
        self.agent_id = "multi_phase_orchestrator"

        # Настройка многофазных параметров
        self.static_cache_dir = (
            config.static_cache_dir or MULTI_PHASE_CONFIG["static_cache_dir"]
        )
        self.integration_points = (
            config.integration_points or MULTI_PHASE_CONFIG["integration_points"]
        )

        self.logger.info(
            f"Инициализация многофазного оркестратора: "
            f"static_cache={self.static_cache_dir}, "
            f"integration_points={self.integration_points}"
        )

        # Инициализация компонентов
        self._initialize_components()

    def _initialize_components(self):
        """Инициализация всех компонентов системы."""
        # 1. StaticDataManager (ВСЕГДА инициализируется)
        try:
            self.static_data_manager = StaticDataManager(
                data_dir=Path(self.static_cache_dir)
            )
            self.logger.info("✅ StaticDataManager инициализирован")
        except Exception as e:
            self.logger.warning(f"⚠️ StaticDataManager недоступен: {e}")
            self.static_data_manager = None

        # 2. Базовые компоненты поиска
        self.db_connector = DatabaseConnector(self.config.db_path)
        self.sql_builder = SQLBuilder()

        # 3. CompoundSearcher с StaticDataManager
        self.compound_searcher = CompoundSearcher(
            sql_builder=self.sql_builder,
            db_connector=self.db_connector,
            static_data_manager=self.static_data_manager
        )

        # 4. ThermodynamicCalculator с настройкой
        self.calculator = ThermodynamicCalculator(
            num_integration_points=self.integration_points
        )

        # 5. Форматтеры
        self.compound_formatter = CompoundDataFormatter(self.calculator)
        self.reaction_formatter = ReactionCalculationFormatter(self.calculator)

        # 6. FilterPipeline
        self.filter_pipeline = FilterPipeline()

        # 7. ThermodynamicAgent (LLM)
        if self.config.llm_api_key:
            from .thermodynamic_agent import ThermoAgentConfig, create_thermo_agent
            agent_config = ThermoAgentConfig(
                llm_api_key=self.config.llm_api_key,
                llm_base_url=self.config.llm_base_url,
                llm_model=self.config.llm_model,
                logger=self.logger
            )
            self.thermodynamic_agent = create_thermo_agent(
                llm_api_key=self.config.llm_api_key,
                llm_base_url=self.config.llm_base_url,
                llm_model=self.config.llm_model
            )
        else:
            self.thermodynamic_agent = None
            self.logger.warning("⚠️ ThermodynamicAgent не инициализирован (нет API ключа)")

    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса пользователя (ВСЕГДА многофазный расчёт).

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный ответ
        """
        try:
            self.logger.info(f"⚡ Многофазный расчёт для запроса: {user_query}")

            # Если есть LLM агент, используем его для извлечения параметров
            if self.thermodynamic_agent:
                params = await self.thermodynamic_agent.extract_parameters(user_query)
                self.logger.debug(f"Извлечённые параметры: query_type={params.query_type}")

                # Маршрутизация по типу запроса
                if params.query_type == "compound_data":
                    return await self._process_compound_data_multi_phase(params)
                else:  # reaction_calculation
                    return await self._process_reaction_calculation_multi_phase(params)
            else:
                # Fallback - простая обработка без LLM
                return self._fallback_processing(user_query)

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return f"❌ Ошибка обработки запроса: {str(e)}"

    async def _process_compound_data_multi_phase(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Обработка запроса данных по веществу (многофазный).

        Args:
            params: Извлеченные параметры

        Returns:
            Отформатированный ответ
        """
        if not params.all_compounds:
            return "❌ Не указано вещество для поиска"

        formula = params.all_compounds[0]
        T_max = params.temperature_range_k[1]  # Используем максимальную температуру

        self.logger.info(f"Многофазный поиск для {formula} до {T_max}K")

        # Шаг 1: Поиск всех фаз (ВСЕГДА многофазный)
        search_result = self.compound_searcher.search_all_phases(
            formula=formula,
            max_temperature=T_max,
            compound_names=params.compound_names.get(formula, []) if params.compound_names else None
        )

        if not search_result.records:
            return f"❌ Вещество {formula} не найдено в БД"

        self.logger.info(
            f"Найдено {len(search_result.records)} записей, "
            f"{search_result.phase_count} фаз"
        )

        # Шаг 2: Многофазный расчёт
        mp_result = self.calculator.calculate_multi_phase_properties(
            records=search_result.records,
            trajectory=[T_max]  # Используем правильный параметр
        )

        # Шаг 3: Форматирование результата
        compound_name = search_result.records[0].name or formula

        # Форматирование данных вещества
        output = self.compound_formatter.format_compound_data_multi_phase(
            formula=formula,
            compound_name=compound_name,
            multi_phase_result=mp_result
        )

        # Шаг 4: Построение таблицы свойств
        T_min, T_max = params.temperature_range_k
        step_k = params.temperature_step_k

        # Добавляем точки фазовых переходов в таблицу
        temperatures = list(range(int(T_min), int(T_max) + 1, step_k))

        for transition in mp_result.phase_transitions:
            if T_min <= transition.temperature <= T_max:
                if transition.temperature not in temperatures:
                    temperatures.append(transition.temperature)

        temperatures = sorted(temperatures)

        # Расчёт для каждой температуры
        table_data = []
        for T in temperatures:
            mp_T = self.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                trajectory=[T]  # Используем правильный параметр
            )
            table_data.append({
                "T": T,
                "H": mp_T.H_final / 1000,  # кДж/моль
                "S": mp_T.S_final,
                "G": mp_T.G_final / 1000,
                "Cp": mp_T.Cp_final
            })

        # Форматирование таблицы
        from tabulate import tabulate

        headers = ["T(K)", "H(кДж/моль)", "S(Дж/(моль·K))", "G(кДж/моль)", "Cp(Дж/(моль·K))"]
        table_rows = []

        for row in table_data:
            table_rows.append([
                f"{row['T']:.0f}",
                f"{row['H']:.2f}",
                f"{row['S']:.2f}",
                f"{row['G']:.2f}",
                f"{row['Cp']:.2f}"
            ])

        table_output = tabulate(table_rows, headers=headers, tablefmt="grid")

        # Шаг 5: Добавление метаданных
        metadata_lines = []
        metadata_lines.append("")
        metadata_lines.append("📈 Метаданные расчёта:")
        metadata_lines.append(f"  - Сегментов: {len(mp_result.segments)}")
        metadata_lines.append(f"  - Фазовых переходов: {len(mp_result.phase_transitions)}")
        metadata_lines.append(f"  - Использован YAML кэш: {'Да' if self.static_data_manager and self.static_data_manager.is_available(formula) else 'Нет'}")

        # Предупреждения
        if search_result.warnings:
            metadata_lines.append("")
            metadata_lines.append("⚠️ Предупреждения:")
            for warning in search_result.warnings:
                metadata_lines.append(f"  - {warning}")

        result = f"{output}\n\n{table_output}\n{''.join(metadata_lines)}"

        return result

    async def _process_reaction_calculation_multi_phase(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Обработка запроса расчёта реакции (многофазный).

        Args:
            params: Извлеченные параметры

        Returns:
            Отформатированный ответ
        """
        # TODO: Реализовать многофазные расчёты реакций
        # Временно используем существующий форматтер
        T_min, T_max = params.temperature_range_k
        T_mid = (T_min + T_max) / 2

        # Поиск реагентов и продуктов (многофазный)
        reactant_results = []
        for formula in params.reactants:
            result = self.compound_searcher.search_all_phases(
                formula=formula,
                max_temperature=T_max
            )
            if not result.records:
                return f"❌ Не найдено вещество: {formula}"
            reactant_results.append(result)

        # Поиск продуктов
        product_results = []
        for formula in params.products:
            result = self.compound_searcher.search_all_phases(
                formula=formula,
                max_temperature=T_max
            )
            if not result.records:
                return f"❌ Не найдено вещество: {formula}"
            product_results.append(result)

        # Временно используем существующий форматтер
        return self.reaction_formatter.format_response(
            params=params,
            reactants=reactant_results,
            products=product_results,
            step_k=params.temperature_step_k
        )

    def _fallback_processing(self, user_query: str) -> str:
        """
        Fallback обработка без LLM агента.

        Args:
            user_query: Запрос пользователя

        Returns:
            Простой ответ
        """
        return (
            f"❌ LLM агент недоступен. "
            f"Укажите API ключ в конфигурации для обработки запроса: '{user_query}'"
        )

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора."""
        return {
            "orchestrator_type": "multi_phase",
            "status": "active",
            "static_cache_enabled": is_multi_phase_enabled(),
            "static_cache_dir": self.static_cache_dir,
            "integration_points": self.integration_points,
            "components": {
                "static_data_manager": type(self.static_data_manager).__name__ if self.static_data_manager else None,
                "compound_searcher": type(self.compound_searcher).__name__,
                "calculator": type(self.calculator).__name__,
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__ if self.thermodynamic_agent else None,
            }
        }