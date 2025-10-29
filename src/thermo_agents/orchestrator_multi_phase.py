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
from tabulate import tabulate

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
from .calculations.reaction_calculator import MultiPhaseReactionCalculator  # Stage 3
from .config.multi_phase_config import (
    MULTI_PHASE_CONFIG,
    get_static_cache_dir,
    get_integration_points,
    is_multi_phase_enabled,
)
from .filtering.filter_pipeline import FilterContext, FilterPipeline, FilterResult
from .filtering.temperature_range_resolver import TemperatureRangeResolver  # Stage 1
from .filtering.phase_segment_builder import PhaseSegmentBuilder  # Stage 2
from .formatting.compound_data_formatter import CompoundDataFormatter
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .models.extraction import ExtractedReactionParameters
from .models.search import CompoundSearchResult, MultiPhaseSearchResult, MultiPhaseCompoundData
from .models.aggregation import MultiPhaseReactionData  # Stage 5
from .search.compound_searcher import CompoundSearcher
from .search.database_connector import DatabaseConnector
from .search.sql_builder import SQLBuilder
from .storage.static_data_manager import StaticDataManager
from .thermodynamic_agent import ThermodynamicAgent
from .session_logger import SessionLogger


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

    def __init__(self, config: MultiPhaseOrchestratorConfig, session_logger: Optional[SessionLogger] = None):
        """
        Инициализация многофазного оркестратора.

        Args:
            config: Конфигурация оркестратора
            session_logger: Логгер сессии (опционально)
        """
        self.config = config
        self.logger = config.logger
        self.agent_id = "multi_phase_orchestrator"
        self.session_logger = session_logger

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

        # 3. CompoundSearcher с StaticDataManager и SessionLogger
        self.compound_searcher = CompoundSearcher(
            sql_builder=self.sql_builder,
            db_connector=self.db_connector,
            session_logger=self.session_logger,
            static_data_manager=self.static_data_manager
        )

        # 4. ThermodynamicCalculator с настройкой
        self.calculator = ThermodynamicCalculator(
            num_integration_points=self.integration_points
        )

        # 5. Форматтеры
        self.compound_formatter = CompoundDataFormatter(self.calculator)
        self.reaction_formatter = ReactionCalculationFormatter(self.calculator)

        # 6. FilterPipeline с SessionLogger - строим полный 6-стадийный конвейер
        from .filtering.filter_pipeline import FilterPipeline
        from .filtering.filter_stages import (
            DeduplicationStage, TemperatureFilterStage, PhaseSelectionStage,
            ReliabilityPriorityStage, FormulaConsistencyStage
        )
        from .filtering.phase_based_temperature_stage import PhaseBasedTemperatureStage
        from .filtering.phase_resolver import PhaseResolver
        from .filtering.temperature_resolver import TemperatureResolver

        # Stage 1: TemperatureRangeResolver for enhanced temperature range logic
        self.temperature_range_resolver = TemperatureRangeResolver()
        self.logger.info("✅ TemperatureRangeResolver (Stage 1) инициализирован")

        # Stage 2: PhaseSegmentBuilder for building phase segments
        self.phase_segment_builder = PhaseSegmentBuilder()
        self.logger.info("✅ PhaseSegmentBuilder (Stage 2) инициализирован")

        # Stage 3: MultiPhaseReactionCalculator for reaction calculations
        self.reaction_calculator = MultiPhaseReactionCalculator(
            thermodynamic_calculator=self.calculator
        )
        self.logger.info("✅ MultiPhaseReactionCalculator (Stage 3) инициализирован")

        # Создаем конвейер с SessionLogger
        self.filter_pipeline = FilterPipeline(session_logger=self.session_logger)

        # Стадия 1: Удаление дубликатов
        self.filter_pipeline.add_stage(DeduplicationStage())

        # Стадия 2: Температурная фильтрация
        self.filter_pipeline.add_stage(TemperatureFilterStage())

        # Стадия 3: Умная фазовая и температурная фильтрация
        self.filter_pipeline.add_stage(PhaseBasedTemperatureStage())

        # Стадия 4: Выбор фазы
        phase_resolver = PhaseResolver()
        self.filter_pipeline.add_stage(PhaseSelectionStage(phase_resolver))

        # Стадия 5: Проверка согласованности формул
        self.filter_pipeline.add_stage(FormulaConsistencyStage())

        # Стадия 6: Приоритизация по надежности
        self.filter_pipeline.add_stage(ReliabilityPriorityStage())

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

    async def process_query_with_multi_phase(self, user_query: str) -> str:
        """
        Enhanced processing with full Stage 1-4 integration.

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный ответ с полной многофазной информацией
        """
        try:
            self.logger.info(f"⚡ Stage 5: Enhanced multi-phase calculation for: {user_query}")

            # 1. Извлечение параметров (без изменений)
            if not self.thermodynamic_agent:
                return self._fallback_processing(user_query)

            params = await self.thermodynamic_agent.extract_parameters(user_query)
            self.logger.debug(f"Извлечённые параметры: query_type={params.query_type}")

            # 2. Поиск всех записей (без температурных ограничений)
            all_records = {}
            for compound in params.all_compounds:
                result = self.compound_searcher.search_compound(
                    compound,
                    temperature_range=None,  # ← КЛЮЧЕВОЕ ИЗМЕНЕНИЕ
                    max_records=200
                )
                all_records[compound] = result.records if result else []

            # 3. Определение полного расчётного диапазона
            calculation_range = self._determine_full_calculation_range(all_records)

            # 4. Построение фазовых сегментов
            multi_phase_data = self._build_multi_phase_data(all_records)

            # 5. Расчёты с учётом фазовых переходов
            if params.query_type == "reaction_calculation":
                reaction_data = await self.reaction_calculator.calculate_reaction_with_transitions(
                    multi_phase_data, params.stoichiometry, calculation_range
                )

                # 6. Форматирование с полной информацией
                return self.reaction_formatter.format_multi_phase_reaction(
                    reaction_data, params
                )
            else:  # compound_data
                return await self._process_compound_data_stage1(params)

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return f"❌ Ошибка обработки запроса: {str(e)}"

    def _determine_full_calculation_range(
        self,
        all_compounds_data: Dict[str, List]
    ) -> Tuple[float, float]:
        """
        Determine the full calculation range from all available data.

        Args:
            all_compounds_data: Dictionary of compound -> records

        Returns:
            Tuple of (min_temp, max_temp) for full calculation range
        """
        all_temps = []
        for compound, records in all_compounds_data.items():
            for record in records:
                if hasattr(record, 'Tmin') and hasattr(record, 'Tmax'):
                    all_temps.append(record.Tmin)
                    all_temps.append(record.Tmax)

        if not all_temps:
            return (298.0, 298.0)  # Default to standard conditions

        return (min(all_temps), max(all_temps))

    def _build_multi_phase_data(
        self,
        compounds_data: Dict[str, List]
    ) -> Dict[str, MultiPhaseCompoundData]:
        """
        Build multi-phase compound data from raw records.

        Args:
            compounds_data: Dictionary of compound -> records

        Returns:
            Dictionary of compound -> MultiPhaseCompoundData
        """
        multi_phase_data = {}

        for compound, records in compounds_data.items():
            if not records:
                continue

            # Build multi-phase data using PhaseSegmentBuilder
            multi_phase_compound = self.phase_segment_builder.build_compound_data(
                compound_formula=compound,
                records=records
            )

            multi_phase_data[compound] = multi_phase_compound

        return multi_phase_data

    async def _process_reaction_calculation_multi_phase(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Enhanced reaction calculation with Stage 5 multi-phase integration.

        Args:
            params: Извлеченные параметры

        Returns:
            Отформатированный ответ с полной многофазной информацией
        """
        try:
            # 1. Поиск всех записей для всех веществ (без температурных ограничений)
            all_records = {}
            for compound in params.all_compounds:
                self.logger.info(f"Поиск всех записей для {compound}...")

                search_result = self.compound_searcher.search_compound(
                    compound,
                    temperature_range=None,  # Полный поиск без ограничений
                    max_records=200
                )

                if not search_result or not search_result.records:
                    return f"❌ Не найдено вещество: {compound}"

                all_records[compound] = search_result.records

            # 2. Определение полного расчётного диапазона
            calculation_range = self._determine_full_calculation_range(all_records)
            self.logger.info(f"Полный расчётный диапазон: {calculation_range[0]:.0f}-{calculation_range[1]:.0f}K")

            # 3. Построение многофазных данных
            multi_phase_data = self._build_multi_phase_data(all_records)

            # 4. Определение стехиометрии (упрощённое)
            stoichiometry = {}
            for compound in params.reactants:
                stoichiometry[compound] = -1.0  # Реагенты имеют отрицательные коэффициенты
            for compound in params.products:
                stoichiometry[compound] = 1.0   # Продукты имеют положительные коэффициенты

            # 5. Создание данных реакции для Stage 5
            reaction_data = MultiPhaseReactionData(
                balanced_equation=params.balanced_equation,
                reactants=params.reactants,
                products=params.products,
                stoichiometry=stoichiometry,
                user_temperature_range=params.temperature_range_k,
                calculation_range=calculation_range,
                compounds_data=multi_phase_data,
                phase_changes=[],  # Будет заполнено расчётом
                calculation_table=[],  # Будет заполнено расчётом
                data_statistics={},
                calculation_method="multi_phase_v2",
                total_records_used=sum(len(records) for records in all_records.values()),
                phases_used=set()
            )

            # 6. Форматирование с использованием обновлённого форматтера
            return self.reaction_formatter.format_multi_phase_reaction(
                reaction_data, params
            )

        except Exception as e:
            self.logger.error(f"Ошибка в многофазном расчёте реакции: {e}")
            return f"❌ Ошибка расчёта реакции: {str(e)}"

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
                    return await self._process_compound_data_multi_phase(params)
                else:  # reaction_calculation
                    return await self._process_reaction_calculation_multi_phase(params)
            else:
                # Fallback - простая обработка без LLM
                return self._fallback_processing(user_query)

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return f"❌ Ошибка обработки запроса: {str(e)}"

    def _apply_deduplication(
        self,
        records: List[DatabaseRecord],
        compound_formula: str,
        temperature_range: Tuple[float, float]
    ) -> List[DatabaseRecord]:
        """
        Применить дедупликацию к записям с использованием FilterPipeline.

        Args:
            records: Список записей для дедупликации
            compound_formula: Формула соединения
            temperature_range: Температурный диапазон

        Returns:
            Список уникальных записей после дедупликации
        """
        if not records:
            return records

        # Создаем контекст фильтрации
        context = FilterContext(
            temperature_range=temperature_range,
            compound_formula=compound_formula,
            user_query=compound_formula
        )

        # Применяем конвейер фильтрации (содержащий только DeduplicationStage)
        result = self.filter_pipeline.execute(records, context)

        # Логирование результатов дедупликации
        if self.session_logger and result.filtered_records != records:
            # Конвертируем записи в словари для логирования
            original_dicts = [r.model_dump() for r in records]
            deduplicated_dicts = [r.model_dump() for r in result.filtered_records]
            execution_time = self.filter_pipeline.get_last_execution_time_ms() / 1000.0 if self.filter_pipeline.get_last_execution_time_ms() else 0.0

            self.session_logger.log_deduplicated_results(
                original_results=original_dicts,
                deduplicated_results=deduplicated_dicts,
                compound_formula=compound_formula,
                execution_time=execution_time
            )

        # Возвращаем отфильтрованные записи
        return result.filtered_records

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

        # Шаг 2: Дедупликация записей
        temperature_range = params.temperature_range_k
        deduplicated_records = self._apply_deduplication(
            records=search_result.records,
            compound_formula=formula,
            temperature_range=temperature_range
        )

        self.logger.info(
            f"После дедупликации: {len(deduplicated_records)} уникальных записей "
            f"(удалено {len(search_result.records) - len(deduplicated_records)} дубликатов)"
        )

        # Шаг 3: Многофазный расчёт
        mp_result = self.calculator.calculate_multi_phase_properties(
            records=deduplicated_records,
            trajectory=[T_max]  # Используем правильный параметр
        )

        # Шаг 4: Форматирование результата
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

    async def _process_compound_data_stage1(
        self,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Stage 1: Enhanced compound data processing with full temperature range logic.

        This method implements the core Stage 1 requirements:
        - Ignores user temperature limitations during database search
        - Uses TemperatureRangeResolver for optimal range determination
        - Provides comprehensive data utilization
        - Shows both requested and calculation ranges

        Args:
            params: Extracted reaction parameters

        Returns:
            Formatted response with Stage 1 enhancements
        """
        if not params.all_compounds:
            return "❌ Не указано вещество для поиска"

        formula = params.all_compounds[0]
        user_range = params.temperature_range_k

        self.logger.info(f"Stage 1: Enhanced search for {formula}")

        # Stage 1: Log range information
        if self.session_logger:
            self.session_logger.log_info("")
            separator = "═" * 70
            self.session_logger.log_info(separator)
            self.session_logger.log_info(f"🔄 Stage 1: Многофазный поиск с полной температурной логикой")
            self.session_logger.log_info(separator)
            self.session_logger.log_info(f"🎯 Запрошенный диапазон: {user_range[0]:.0f}-{user_range[1]:.0f}K")
            self.session_logger.log_info(f"🔍 Запускается поиск всех доступных записей...")

        # Step 1: Use Stage 1 enhanced search (ignores temperature limitations)
        search_result = self.compound_searcher.search_compound_stage1(
            formula=formula,
            user_temperature_range=user_range,
            compound_names=params.compound_names.get(formula, []) if params.compound_names else None
        )

        if not search_result.records_found:
            return f"❌ Вещество {formula} не найдено в БД"

        # Step 2: Determine optimal calculation range using TemperatureRangeResolver
        compounds_data = {formula: search_result.records_found}
        range_analysis = self.temperature_range_resolver.determine_calculation_range(
            compounds_data=compounds_data,
            user_range=user_range
        )

        # Update search result with Stage 1 information
        search_result.set_stage1_ranges(
            full_calculation_range=range_analysis.calculation_range,
            original_user_range=user_range
        )

        # Step 3: Apply Stage 1 filtering with full calculation range
        from .filtering.filter_pipeline import FilterPipeline
        stage1_pipeline = FilterPipeline(session_logger=self.session_logger)

        # Build the same 6-stage pipeline but with Stage 1 context
        from .filtering.filter_stages import (
            DeduplicationStage, TemperatureFilterStage, PhaseSelectionStage,
            ReliabilityPriorityStage, FormulaConsistencyStage
        )
        from .filtering.phase_based_temperature_stage import PhaseBasedTemperatureStage
        from .filtering.phase_resolver import PhaseResolver

        stage1_pipeline.add_stage(DeduplicationStage())
        stage1_pipeline.add_stage(TemperatureFilterStage())
        stage1_pipeline.add_stage(PhaseBasedTemperatureStage())

        phase_resolver = PhaseResolver()
        stage1_pipeline.add_stage(PhaseSelectionStage(phase_resolver))
        stage1_pipeline.add_stage(FormulaConsistencyStage())
        stage1_pipeline.add_stage(ReliabilityPriorityStage())

        # Create Stage 1 context with full calculation range
        stage1_context = stage1_pipeline.create_stage1_context(
            compound_formula=formula,
            user_temperature_range=user_range,
            full_calculation_range=range_analysis.calculation_range,
            reaction_params=params
        )

        # Execute Stage 1 filtering
        filter_result = stage1_pipeline.execute(search_result.records_found, stage1_context)
        filtered_records = filter_result.filtered_records

        self.logger.info(
            f"Stage 1: {len(search_result.records_found)} → {len(filtered_records)} записей после фильтрации"
        )

        # Step 4: Multi-phase calculation with full range
        T_calc_max = range_analysis.calculation_range[1]
        mp_result = self.calculator.calculate_multi_phase_properties(
            records=filtered_records,
            trajectory=[T_calc_max]
        )

        # Step 5: Enhanced formatting with Stage 1 information
        compound_name = search_result.records_found[0].name or formula

        # Format compound data
        output = self.compound_formatter.format_compound_data_multi_phase(
            formula=formula,
            compound_name=compound_name,
            multi_phase_result=mp_result
        )

        # Step 6: Build enhanced properties table
        T_min, T_max = range_analysis.calculation_range
        step_k = params.temperature_step_k

        # Include temperatures from user range plus phase transitions
        temperatures = list(range(int(T_min), int(T_max) + 1, step_k))

        # Add phase transition temperatures
        for transition in mp_result.phase_transitions:
            if T_min <= transition.temperature <= T_max:
                if transition.temperature not in temperatures:
                    temperatures.append(transition.temperature)

        temperatures = sorted(temperatures)

        # Calculate properties for each temperature
        table_rows = []
        headers = ["T(K)", "ΔH°", "ΔS°", "ΔG°", "Cp°"]

        for T in temperatures:
            if T_min <= T <= T_max:
                try:
                    result = self.calculator.calculate_multi_phase_properties(
                        records=filtered_records,
                        trajectory=[T]
                    )
                    row = result.segments[0] if result.segments else None

                    if row:
                        table_rows.append([
                            f"{T:.0f}",
                            f"{row.H_start:.2f}",
                            f"{row.S_start:.2f}",
                            f"{row.G_start:.2f}",
                            f"{row.Cp_start:.2f}"
                        ])
                except Exception as e:
                    self.logger.warning(f"Error calculating at T={T}: {e}")
                    table_rows.append([
                        f"{T:.0f}", "Error", "Error", "Error", "Error"
                    ])

        table_output = tabulate(table_rows, headers=headers, tablefmt="grid")

        # Step 7: Enhanced metadata with Stage 1 information
        metadata_lines = []
        metadata_lines.append("")
        metadata_lines.append("📈 Метаданные расчёта (Stage 1):")
        metadata_lines.append(f"  - Запрошенный диапазон: {user_range[0]:.0f}-{user_range[1]:.0f}K")
        metadata_lines.append(f"  - Расчётный диапазон: {range_analysis.calculation_range[0]:.0f}-{range_analysis.calculation_range[1]:.0f}K")

        if range_analysis.includes_298K:
            metadata_lines.append(f"  - ✅ Включает стандартные условия (298K)")
        else:
            metadata_lines.append(f"  - ⚠️  Не включает 298K")

        metadata_lines.append(f"  - Сегментов: {len(mp_result.segments)}")
        metadata_lines.append(f"  - Фазовых переходов: {len(mp_result.phase_transitions)}")
        metadata_lines.append(f"  - Найдено записей: {len(search_result.records_found)}")
        metadata_lines.append(f"  - После фильтрации: {len(filtered_records)}")

        # Add range expansion information
        expansion_info = search_result.get_range_expansion_info()
        if expansion_info.get("expanded", False):
            metadata_lines.append(f"  - 🔄 Расширение диапазона: {expansion_info.get('expansion_factor', 1.0):.1f}x")
            metadata_lines.append(f"    Записей в запрошенном диапазоне: {expansion_info.get('records_in_original_range', 0)}")
            metadata_lines.append(f"    Записей в полном диапазоне: {expansion_info.get('records_in_full_range', 0)}")

        # Add recommendations from TemperatureRangeResolver
        if range_analysis.recommendations:
            metadata_lines.append("")
            metadata_lines.append("💡 Рекомендации:")
            for rec in range_analysis.recommendations:
                metadata_lines.append(f"  - {rec}")

        # Add warnings
        if search_result.warnings:
            metadata_lines.append("")
            metadata_lines.append("⚠️ Предупреждения:")
            for warning in search_result.warnings:
                metadata_lines.append(f"  - {warning}")

        result = f"{output}\n\n{table_output}\n{''.join(metadata_lines)}"

        # Stage 1: Final logging
        if self.session_logger:
            self.session_logger.log_info("")
            self.session_logger.log_info(f"✅ Stage 1 завершён для {formula}")
            self.session_logger.log_info(f"   Найдено записей: {len(search_result.records_found)}")
            self.session_logger.log_info(f"   Расчётный диапазон: {range_analysis.calculation_range[0]:.0f}-{range_analysis.calculation_range[1]:.0f}K")
            separator = "═" * 70
            self.session_logger.log_info(separator)

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

            # Сохраняем оригинальное количество записей для логирования
            original_count = len(result.records)

            # Применяем дедупликацию к результатам поиска
            deduplicated_records = self._apply_deduplication(
                records=result.records,
                compound_formula=formula,
                temperature_range=params.temperature_range_k
            )

            # Обновляем результат с дедуплицированными записями
            result.records = deduplicated_records
            reactant_results.append(result)

            self.logger.info(
                f"Реагент {formula}: {len(deduplicated_records)} уникальных записей "
                f"(из {original_count} оригинальных)"
            )

        # Поиск продуктов
        product_results = []
        for formula in params.products:
            result = self.compound_searcher.search_all_phases(
                formula=formula,
                max_temperature=T_max
            )
            if not result.records:
                return f"❌ Не найдено вещество: {formula}"

            # Сохраняем оригинальное количество записей для логирования
            original_count = len(result.records)

            # Применяем дедупликацию к результатам поиска
            deduplicated_records = self._apply_deduplication(
                records=result.records,
                compound_formula=formula,
                temperature_range=params.temperature_range_k
            )

            # Обновляем результат с дедуплицированными записями
            result.records = deduplicated_records
            product_results.append(result)

            self.logger.info(
                f"Продукт {formula}: {len(deduplicated_records)} уникальных записей "
                f"(из {original_count} оригинальных)"
            )

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