"""
Оркестратор термодинамической системы с интегрированной core-логикой.

Этап 2: Внедрение core-логики из calc_example.ipynb.
Парсинг LLM response + полноценные термодинамические расчеты.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from pathlib import Path

from .models.extraction import ExtractedReactionParameters
from .thermodynamic_agent import ThermodynamicAgent
from .session_logger import SessionLogger
from .search.database_connector import DatabaseConnector
from .storage.static_data_manager import StaticDataManager
from .core_logic import (
    CompoundDataLoader,
    PhaseTransitionDetector,
    RecordRangeBuilder,
    ThermodynamicEngine,
    ReactionEngine
)


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

    def __init__(self, config: ThermoOrchestratorConfig, session_logger: Optional[SessionLogger] = None):
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
                    llm_model=self.config.llm_model
                )
                self.logger.info("✅ ThermodynamicAgent инициализирован")
            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации ThermodynamicAgent: {e}")
                self.thermodynamic_agent = None
        else:
            self.thermodynamic_agent = None
            self.logger.warning("⚠️ ThermodynamicAgent не инициализирован (нет API ключа)")

        # База данных
        try:
            self.db_connector = DatabaseConnector(self.config.db_path)
            self.logger.info(f"✅ DatabaseConnector инициализирован: {self.config.db_path}")
        except Exception as e:
            self.logger.error(f"❌ Ошибка инициализации DatabaseConnector: {e}")
            self.db_connector = None

        # YAML-кэш (StaticDataManager)
        try:
            self.static_manager = StaticDataManager(self.config.static_data_dir)
            available_compounds = self.static_manager.list_available_compounds()
            self.logger.info(f"✅ StaticDataManager инициализирован: {len(available_compounds)} веществ")
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
                    self.logger
                )
                self.logger.info("✅ Core-логика компоненты инициализированы")
            except Exception as e:
                self.logger.error(f"❌ Ошибка инициализации core-логики: {e}")
                self.reaction_engine = None
        else:
            self.reaction_engine = None
            self.logger.warning("⚠️ Core-логика не инициализирована (проблемы с БД или StaticDataManager)")

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
                return "❌ LLM агент не инициализирован. Укажите API ключ в конфигурации."

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
                    model=getattr(self.thermodynamic_agent, 'model_name', 'unknown')
                )

            # 4. Расчет реакции через новый ReactionEngine
            if params.query_type == "reaction_calculation":
                if not self.reaction_engine:
                    return "❌ ReactionEngine не инициализирован. Проверьте конфигурацию БД и StaticDataManager."

                temperature_range = [298, 2500, 100]  # Фиксированный диапазон

                try:
                    df_result = self.reaction_engine.calculate_reaction(
                        params, temperature_range
                    )

                    # 5. Временное форматирование (будет улучшено на этапе 3)
                    return self._format_temporary_result(df_result, params)

                except Exception as e:
                    self.logger.error(f"Ошибка расчета реакции: {e}")
                    if self.session_logger:
                        self.session_logger.log_llm_error(str(e))
                    return f"❌ Ошибка расчета реакции: {str(e)}"

            else:
                return "⚠️ Обработка compound_data запросов будет добавлена позже"

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            if self.session_logger:
                self.session_logger.log_llm_error(str(e))
            return f"❌ Ошибка: {str(e)}"

    def _format_temporary_result(self, df_result: 'pd.DataFrame', params: ExtractedReactionParameters) -> str:
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
        df_display['T'] = df_display['T'].astype(int)
        df_display['ΔH (кДж/моль)'] = (df_display['delta_H'] / 1000).round(2)
        df_display['ΔS (Дж/(моль·K))'] = df_display['delta_S'].round(2)
        df_display['ΔG (кДж/моль)'] = (df_display['delta_G'] / 1000).round(2)
        df_display['ln(K)'] = df_display['ln_K'].round(4)

        # Обрабатываем очень большие/маленькие значения K
        def format_k(k_val):
            if pd.isna(k_val) or k_val == 0:
                return "0.00e+00"
            elif k_val == float('inf'):
                return "∞"
            elif abs(k_val) > 1e6 or abs(k_val) < 1e-6:
                return f"{k_val:.2e}"
            else:
                return f"{k_val:.2f}"

        df_display['K'] = df_display['K'].apply(format_k)

        # Выбираем колонки для отображения
        display_cols = ['T', 'ΔH (кДж/моль)', 'ΔS (Дж/(моль·K))', 'ΔG (кДж/моль)', 'ln(K)', 'K']
        df_display = df_display[display_cols]

        # Формируем вывод
        result_lines = [
            f"⚗️ Термодинамический расчет реакции",
            f"Уравнение: {equation}",
            f"Диапазон: 298-2500 K (шаг 100 K)",
            "",
            "Результаты расчета:",
            "=" * 80
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
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__ if self.thermodynamic_agent else None,
                "database_connector": type(self.db_connector).__name__ if self.db_connector else None,
                "static_data_manager": type(self.static_manager).__name__ if self.static_manager else None,
                "reaction_engine": type(self.reaction_engine).__name__ if self.reaction_engine else None,
            },
            "capabilities": {
                "parameter_extraction": bool(self.thermodynamic_agent),
                "calculations": bool(self.reaction_engine),  # Включено на этапе 2
                "database_search": bool(self.db_connector),  # Включено на этапе 2
                "yaml_cache": bool(self.static_manager),  # Включено на этапе 2
            }
        }