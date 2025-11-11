"""
Оркестратор термодинамической системы с интегрированной core-логикой.

Этап 2: Внедрение core-логики из calc_example.ipynb.
Парсинг LLM response + полноценные термодинамические расчеты.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .core_logic import (
    CompoundDataLoader,
    PhaseTransitionDetector,
    ReactionEngine,
    RecordRangeBuilder,
    ThermodynamicEngine,
)
from .formatting import (
    CompoundInfoFormatter,
    InterpretationFormatter,
    TableFormatter,
    UnifiedReactionFormatter,
)
from .models.extraction import ExtractedReactionParameters
from .search.database_connector import DatabaseConnector
from .session_logger import SessionLogger
from .storage.static_data_manager import StaticDataManager
from .thermodynamic_agent import ThermodynamicAgent


@dataclass
class ThermoOrchestratorConfig:
    """
    Конфигурация термодинамического оркестратора.
    """

    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    max_retries: int = 2
    timeout_seconds: int = 90

    # LLM компоненты
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"

    # База данных
    db_path: Path = field(default_factory=lambda: Path("data/thermo_data.db"))
    static_data_dir: Path = field(default_factory=lambda: Path("data/static_compounds"))


class ThermoOrchestrator:
    """
    Термодинамический оркестратор с core-логикой из calc_example.ipynb.

    Этап 2 рефакторинга:
    - Парсинг LLM response
    - Полноценные термодинамические расчеты
    - YAML-кэш для распространенных веществ
    - Двухстадийный поиск в БД
    - Трехуровневая стратегия отбора записей
    """

    def __init__(
        self,
        config: ThermoOrchestratorConfig,
        session_logger: Optional[SessionLogger] = None,
    ):
        """
        Инициализация оркестратора с core-логикой.

        Args:
            config: Конфигурация оркестратора
            session_logger: Логгер сессии (опционально)
        """
        self.config = config
        self.logger = config.logger
        self.agent_id = "core_logic_orchestrator"
        self.session_logger = session_logger

        self.logger.info("Инициализация оркестратора с core-логикой (Этап 2)")

        # Инициализация компонентов
        self._initialize_components()

    def _initialize_components(self):
        """Инициализация компонентов системы."""
        # ThermodynamicAgent (LLM)
        if self.config.llm_api_key:
            try:
                from .thermodynamic_agent import create_thermo_agent

                self.thermodynamic_agent = create_thermo_agent(
                    llm_api_key=self.config.llm_api_key,
                    llm_base_url=self.config.llm_base_url,
                    llm_model=self.config.llm_model,
                )
                self.logger.info("✅ ThermodynamicAgent инициализирован")
            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации ThermodynamicAgent: {e}")
                self.thermodynamic_agent = None
        else:
            self.thermodynamic_agent = None
            self.logger.warning(
                "⚠️ ThermodynamicAgent не инициализирован (нет API ключа)"
            )

        # База данных
        try:
            self.db_connector = DatabaseConnector(self.config.db_path)
            self.logger.info(
                f"✅ DatabaseConnector инициализирован: {self.config.db_path}"
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации DatabaseConnector: {e}")
            self.db_connector = None

        # YAML-кэш (StaticDataManager)
        try:
            self.static_manager = StaticDataManager(self.config.static_data_dir)
            available_compounds = self.static_manager.list_available_compounds()
            self.logger.info(
                f"✅ StaticDataManager инициализирован: {len(available_compounds)} веществ"
            )
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации StaticDataManager: {e}")
            self.static_manager = None

        # Core-логика компоненты
        if self.db_connector and self.static_manager:
            try:
                self.compound_loader = CompoundDataLoader(
                    self.db_connector, self.static_manager, self.logger
                )
                self.phase_detector = PhaseTransitionDetector()
                self.range_builder = RecordRangeBuilder(self.logger)
                self.thermo_engine = ThermodynamicEngine(self.logger)
                self.reaction_engine = ReactionEngine(
                    self.compound_loader,
                    self.phase_detector,
                    self.range_builder,
                    self.thermo_engine,
                    self.logger,
                )
                self.logger.info("✅ Core-логика компоненты инициализированы")

                # Новые форматтеры (Этап 3)
                self.compound_info_formatter = CompoundInfoFormatter()
                self.table_formatter = TableFormatter()
                self.interpretation_formatter = InterpretationFormatter()
                self.unified_formatter = UnifiedReactionFormatter(
                    self.compound_info_formatter,
                    self.table_formatter,
                    self.interpretation_formatter,
                )
                self.logger.info("✅ Новые форматтеры инициализированы (Этап 3)")

            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации core-логики: {e}")
                self.reaction_engine = None
                self.unified_formatter = None
        else:
            self.reaction_engine = None
            self.unified_formatter = None
            self.logger.warning(
                "⚠️ Core-логика не инициализирована (проблемы с БД или StaticDataManager)"
            )

    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса с использованием новой core-логики.

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный ответ с результатами расчетов
        """
        try:
            # 1. Логирование запроса
            if self.session_logger:
                self.session_logger.log_llm_request(user_query)

            # 2. Извлечение параметров через LLM
            if not self.thermodynamic_agent:
                return (
                    "❌ LLM агент не инициализирован. Укажите API ключ в конфигурации."
                )

            # Измеряем время выполнения
            import time

            start_time = time.time()

            params = await self.thermodynamic_agent.extract_parameters(user_query)

            duration = time.time() - start_time

            # 3. Логирование ответа LLM с временем выполнения
            if self.session_logger:
                self.session_logger.log_llm_response(
                    params.model_dump(),
                    duration=duration,
                    model=getattr(self.thermodynamic_agent, "model_name", "unknown"),
                )

            # 4. Расчет реакции через новый ReactionEngine
            if params.query_type == "reaction_calculation":
                if not self.reaction_engine:
                    return "❌ ReactionEngine не инициализирован. Проверьте конфигурацию БД и StaticDataManager."

                temperature_range = [298, 2500, 100]  # Фиксированный диапазон

                try:
                    # Используем новый метод с метаданными для форматтера
                    df_result, compounds_metadata = (
                        self.reaction_engine.calculate_reaction_with_metadata(
                            params, temperature_range
                        )
                    )

                    # 5. НОВОЕ: Форматирование через UnifiedReactionFormatter
                    if self.unified_formatter:
                        formatted_result = (
                            self.unified_formatter.format_reaction_result(
                                params, df_result, compounds_metadata
                            )
                        )
                    else:
                        # Fallback на временный форматтер если новые не инициализированы
                        formatted_result = self._format_temporary_result(
                            df_result, params
                        )

                    # 6. Логирование результата
                    if self.session_logger:
                        self.session_logger.log_info(
                            f"Расчет завершен: {len(df_result)} температурных точек"
                        )

                    return formatted_result

                except Exception as e:
                    self.logger.error(f"Ошибка расчета реакции: {e}")
                    if self.session_logger:
                        self.session_logger.log_llm_error(str(e))
                    return f"❌ Ошибка расчета реакции: {str(e)}"

            else:  # compound_data
                return await self._process_compound_data(params)

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            if self.session_logger:
                self.session_logger.log_llm_error(str(e))
            return f"❌ Ошибка: {str(e)}"

    def _is_elemental(self, formula: str) -> bool:
        """
        Определяет, является ли формула простым веществом (элементом).

        Простое вещество: один химический элемент (с индексом или без).
        Примеры: O2, H2, C, Fe, S, Cl2.
        Сложное вещество: два и более элементов.
        Примеры: H2O, CO2, CrCl3, Fe2O3.

        Args:
            formula: Химическая формула

        Returns:
            True если простое вещество, False если сложное
        """
        import re

        # Паттерн: заглавная буква + опционально строчная + опционально цифры
        # Примеры: O2, H2, C, Fe, Cl2
        pattern = r"^[A-Z][a-z]?\d*$"
        return bool(re.match(pattern, formula))

    async def _process_compound_data(self, params: ExtractedReactionParameters) -> str:
        """
        Обработка compound_data запросов (термодинамические свойства одного вещества).

        Args:
            params: Извлеченные параметры с query_type="compound_data"

        Returns:
            Отформатированная строка с таблицей свойств вещества
        """
        try:
            # 1. Валидация параметров
            if not params.all_compounds or len(params.all_compounds) == 0:
                return "❌ Не указано вещество для получения термодинамических свойств"

            formula = params.all_compounds[0]
            compound_names = (
                params.compound_names.get(formula, []) if params.compound_names else []
            )

            # Логирование начала обработки
            self.logger.info(f"Processing compound_data query for: {formula}")
            if self.session_logger:
                self.session_logger.log_info(f"Запрос свойств вещества: {formula}")

            # 2. Загрузка данных через существующий CompoundDataLoader
            df, is_yaml_cache, search_stage = (
                self.compound_loader.get_raw_compound_data_with_metadata(
                    formula, compound_names
                )
            )

            if df.empty:
                self.logger.warning(f"No data found for compound: {formula}")
                return (
                    f"❌ Не удалось найти данные для вещества *{formula}*\n\n"
                    "Возможные причины:\n"
                    "• Вещество отсутствует в базе данных\n"
                    "• Опечатка в химической формуле\n"
                    "• Используйте распространенные вещества: H2O, CO2, Fe2O3, CuO\n\n"
                    "_Сгенерировано ThermoSystem Telegram Bot_"
                )

            # Логирование источника данных
            source = "YAML-кэш" if is_yaml_cache else f"БД (стадия {search_stage})"
            self.logger.info(f"Data loaded from {source}: {len(df)} records")
            if self.session_logger:
                self.session_logger.log_info(
                    f"Источник данных: {source}, записей: {len(df)}"
                )

            # 3. Определение фазовых переходов через существующий PhaseTransitionDetector
            melting_point, boiling_point = (
                self.phase_detector.get_most_common_melting_boiling_points(df)
            )

            # Логирование фазовых переходов
            if melting_point or boiling_point:
                transitions = []
                if melting_point:
                    transitions.append(f"плавление {melting_point:.0f}K")
                if boiling_point:
                    transitions.append(f"кипение {boiling_point:.0f}K")
                self.logger.info(
                    f"Phase transitions detected: {', '.join(transitions)}"
                )

            # 4. Выбор записей через RecordRangeBuilder для температурного диапазона
            # Определяем, является ли вещество простым (элемент)
            is_elemental = self._is_elemental(formula)

            # Выбираем записи, покрывающие запрошенный температурный диапазон
            selected_records = self.range_builder.get_compound_records_for_range(
                df=df,
                t_range=params.temperature_range_k,
                melting=melting_point,
                boiling=boiling_point,
                tolerance=1.0,
                is_elemental=is_elemental,
            )

            # Логирование выбранных записей
            self.logger.info(
                f"Selected {len(selected_records)} records for range {params.temperature_range_k}"
            )
            if self.session_logger:
                phase_counts = {}
                for rec in selected_records:
                    phase = rec["Phase"]
                    phase_counts[phase] = phase_counts.get(phase, 0) + 1
                self.session_logger.log_info(
                    f"Выбрано записей: {len(selected_records)} "
                    f"({', '.join(f'{k}: {v}' for k, v in phase_counts.items())})"
                )

            # Преобразуем pd.Series в dict для форматтеров
            records_list = [dict(rec) for rec in selected_records]

            # 5. Форматирование через существующие форматтеры
            # Формируем полный ответ с информацией о веществе и таблицами
            lines = []

            # Заголовок
            lines.append("📊 *СВОЙСТВА ВЕЩЕСТВА*")
            lines.append("")

            # Информация о веществе с фазовыми переходами (как для реакций)
            compound_info = self.compound_info_formatter.format_compound(
                formula=formula,
                records_used=records_list,
                melting_point=melting_point,
                boiling_point=boiling_point,
                compound_names=compound_names,
            )
            lines.append(compound_info)
            lines.append("")

            # Таблица данных о записях (коэффициенты Cp как для реакций)
            compound_data_table = (
                self.compound_info_formatter.format_compound_data_table(
                    formula=formula,
                    records_used=records_list,
                    compound_names=compound_names,
                )
            )
            lines.append(compound_data_table)

            # Таблица термодинамических свойств (ΔH, ΔS, ΔG vs T)
            thermodynamic_table = (
                self.compound_info_formatter.format_compound_thermodynamic_table(
                    formula=formula,
                    records_used=records_list,
                    temperature_range_k=params.temperature_range_k,
                    temperature_step_k=params.temperature_step_k,
                    compound_names=compound_names,
                )
            )
            lines.append(thermodynamic_table)

            # 4. Формирование итогового ответа
            source_info = f"_Источник данных: {source}_"
            footer = "\n_Сгенерировано ThermoSystem Telegram Bot_"

            result = "\n".join(lines) + "\n" + source_info + footer

            # Логирование завершения
            if self.session_logger:
                self.session_logger.log_info(
                    "Обработка compound_data завершена успешно"
                )

            return result

        except Exception as e:
            self.logger.error(f"Ошибка обработки compound_data: {e}")
            if self.session_logger:
                self.session_logger.log_error(f"Ошибка compound_data: {str(e)}")
            return f"❌ Ошибка при получении свойств вещества: {str(e)}"

    def _format_temporary_result(
        self, df_result: "pd.DataFrame", params: ExtractedReactionParameters
    ) -> str:
        """
        Временное форматирование результатов расчета.

        Args:
            df_result: DataFrame с результатами расчета
            params: Извлеченные параметры реакции

        Returns:
            Отформатированная строка с таблицей результатов
        """
        import pandas as pd

        equation = params.balanced_equation

        # Форматируем таблицу для красивого вывода
        df_display = df_result.copy()
        df_display["T"] = df_display["T"].astype(int)
        df_display["ΔH (кДж/моль)"] = (df_display["delta_H"] / 1000).round(2)
        df_display["ΔS (Дж/(моль·K))"] = df_display["delta_S"].round(2)
        df_display["ΔG (кДж/моль)"] = (df_display["delta_G"] / 1000).round(2)
        df_display["ln(K)"] = df_display["ln_K"].round(4)

        # Обрабатываем очень большие/маленькие значения K
        def format_k(k_val):
            if pd.isna(k_val) or k_val == 0:
                return "0.00e+00"
            elif k_val == float("inf"):
                return "∞"
            elif abs(k_val) > 1e6 or abs(k_val) < 1e-6:
                return f"{k_val:.2e}"
            else:
                return f"{k_val:.2f}"

        df_display["K"] = df_display["K"].apply(format_k)

        # Выбираем колонки для отображения
        display_cols = [
            "T",
            "ΔH (кДж/моль)",
            "ΔS (Дж/(моль·K))",
            "ΔG (кДж/моль)",
            "ln(K)",
            "K",
        ]
        df_display = df_display[display_cols]

        # Формируем вывод
        result_lines = [
            f"⚗️ Термодинамический расчет реакции",
            f"Уравнение: {equation}",
            f"Диапазон: 298-2500 K (шаг 100 K)",
            "",
            "Результаты расчета:",
            "=" * 80,
        ]

        # Добавляем таблицу
        result_lines.append(df_display.to_string(index=False))
        result_lines.append("=" * 80)
        result_lines.append(f"Всего точек: {len(df_result)}")

        return "\n".join(result_lines)

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора."""
        return {
            "orchestrator_type": "core_logic_stage_2",
            "status": "active",
            "components": {
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__
                if self.thermodynamic_agent
                else None,
                "database_connector": type(self.db_connector).__name__
                if self.db_connector
                else None,
                "static_data_manager": type(self.static_manager).__name__
                if self.static_manager
                else None,
                "reaction_engine": type(self.reaction_engine).__name__
                if self.reaction_engine
                else None,
            },
            "capabilities": {
                "parameter_extraction": bool(self.thermodynamic_agent),
                "calculations": bool(self.reaction_engine),  # Включено на этапе 2
                "database_search": bool(self.db_connector),  # Включено на этапе 2
                "yaml_cache": bool(self.static_manager),  # Включено на этапе 2
            },
        }
