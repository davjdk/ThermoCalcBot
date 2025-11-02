"""
Упрощенный оркестратор термодинамической системы.

Этап 1: Удаление избыточной логики после LLM response.
Оставлен только парсинг ответа LLM и минимальная валидация извлеченных параметров.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .models.extraction import ExtractedReactionParameters
from .thermodynamic_agent import ThermodynamicAgent
from .session_logger import SessionLogger


@dataclass
class ThermoOrchestratorConfig:
    """
    Конфигурация термодинамического оркестратора.
    """
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    max_retries: int = 2
    timeout_seconds: int = 90

    # Базовые компоненты
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "openai:gpt-4o"


class ThermoOrchestrator:
    """
    Упрощенный термодинамический оркестратор системы.

    Этап 1 рефакторинга:
    - Только парсинг LLM response
    - Минимальная валидация извлеченных параметров
    - Временная заглушка для расчетов (будет реализовано на этапе 2)
    """

    def __init__(self, config: ThermoOrchestratorConfig, session_logger: Optional[SessionLogger] = None):
        """
        Инициализация упрощенного оркестратора.

        Args:
            config: Конфигурация оркестратора
            session_logger: Логгер сессии (опционально)
        """
        self.config = config
        self.logger = config.logger
        self.agent_id = "simplified_orchestrator"
        self.session_logger = session_logger

        self.logger.info("Инициализация упрощенного оркестратора (Этап 1)")

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

    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса пользователя.

        ЭТАП 1: Только парсинг LLM response, без дальнейшей обработки.

        Args:
            user_query: Запрос на естественном языке

        Returns:
            Отформатированный ответ с извлеченными параметрами
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

            # 4. ВРЕМЕННАЯ ЗАГЛУШКА (будет заменена на этапе 2)
            return f"✅ Параметры извлечены:\n{params.model_dump_json(indent=2)}\n\n⚠️ Расчеты временно недоступны (ожидается этап 2)"

        except Exception as e:
            self.logger.error(f"Ошибка обработки запроса: {e}")
            return f"❌ Ошибка: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """Получить статус оркестратора."""
        return {
            "orchestrator_type": "simplified_stage_1",
            "status": "active",
            "components": {
                "thermodynamic_agent": type(self.thermodynamic_agent).__name__ if self.thermodynamic_agent else None,
            },
            "capabilities": {
                "parameter_extraction": bool(self.thermodynamic_agent),
                "calculations": False,  # Временно отключено на этапе 1
                "database_search": False,  # Временно отключено на этапе 1
            }
        }