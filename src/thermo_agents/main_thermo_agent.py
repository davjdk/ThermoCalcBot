"""
Термодинамический агент для извлечения параметров из запросов пользователя.

Реализует только первый шаг обработки: извлечение параметров из текста запроса
с использованием EXTRACT_INPUTS_PROMPT.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from thermo_agents.prompts import EXTRACT_INPUTS_PROMPT
from thermo_agents.thermo_agents_logger import SessionLogger

# Загрузка переменных окружения из .env файла
load_dotenv()

# =============================================================================
# МОДЕЛИ ДАННЫХ
# =============================================================================


class ExtractedParameters(BaseModel):
    """Извлеченные параметры из запроса пользователя."""

    intent: str  # "lookup", "calculation", "reaction", "comparison"
    compounds: List[str]  # Химические формулы
    temperature_k: float  # Температура в Кельвинах
    temperature_range_k: List[float]  # Диапазон температур [min, max]
    phases: List[str]  # Фазовые состояния ["s", "l", "g", "aq"]
    properties: List[str]  # Требуемые свойства ["basic", "all", "thermal"]
    sql_query_hint: str  # Подсказка для генерации SQL


# =============================================================================
# ЗАВИСИМОСТИ АГЕНТОВ
# =============================================================================


@dataclass
class ThermoAgentConfig:
    """Общие зависимости для агентов системы."""

    # Настройки из .env файла
    llm_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_model: str = field(
        default_factory=lambda: os.getenv("LLM_DEFAULT_MODEL", "openai:gpt-4o")
    )
    db_path: str = field(
        default_factory=lambda: os.getenv("DB_PATH", "data/thermo_data.db")
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    # Логгер
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None

    # Инициализация зависимостей
    def __post_init__(self):
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(getattr(logging, self.log_level.upper(), logging.INFO))


# =============================================================================
# ОРКЕСТРАТОР АГЕНТ
# =============================================================================


def initialize_thermo_agent(deps: ThermoAgentConfig) -> Agent:
    """Создание агента-оркестратора с настройками из зависимостей."""
    # Провайдер для OpenRouter
    provider = OpenAIProvider(
        api_key=deps.llm_api_key,
        base_url=deps.llm_base_url,
    )

    # Основная модель (OpenRouter via OpenAIChatModel)
    model = OpenAIChatModel(deps.llm_model, provider=provider)

    return Agent(
        model,
        deps_type=ThermoAgentConfig,
        output_type=ExtractedParameters,
        system_prompt=EXTRACT_INPUTS_PROMPT,
        retries=2,
    )


# =============================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =============================================================================


async def process_thermodynamic_query(
    user_query: str, dependencies: Optional[ThermoAgentConfig] = None
) -> ExtractedParameters:
    """
    Извлечение параметров из термодинамического запроса пользователя.

    Использует EXTRACT_INPUTS_PROMPT для анализа текста запроса и извлечения:
    - Тип запроса (intent)
    - Химические соединения (compounds)
    - Температуру и диапазон
    - Фазовые состояния
    - Требуемые свойства
    - Подсказку для SQL генерации
    """
    if dependencies is None:
        dependencies = ThermoAgentConfig()

    dependencies.logger.info(f"Извлечение параметров из запроса: {user_query[:100]}...")

    if dependencies.session_logger:
        dependencies.session_logger.log_user_input(user_query)
        dependencies.session_logger.log_info("Начало извлечения параметров")

    try:
        # Создание агента с настройками из зависимостей
        agent = initialize_thermo_agent(dependencies)

        # Извлечение параметров из запроса
        result = await agent.run(user_query, deps=dependencies)

        dependencies.logger.info(
            f"Параметры успешно извлечены: {len(result.output.compounds)} соединений"
        )

        if dependencies.session_logger:
            response_str = f"Intent: {result.output.intent}, Compounds: {result.output.compounds}, Temp: {result.output.temperature_k}K"
            dependencies.session_logger.log_agent_response(response_str)
            dependencies.session_logger.log_info("Параметры успешно извлечены")

        return result.output

    except Exception as e:
        dependencies.logger.error(f"Ошибка извлечения параметров: {e}")

        if dependencies.session_logger:
            dependencies.session_logger.log_error(str(e))

        # Возвращаем базовые параметры в случае ошибки
        return ExtractedParameters(
            intent="unknown",
            compounds=[],
            temperature_k=298.15,
            temperature_range_k=[200, 2000],
            phases=[],
            properties=["basic"],
            sql_query_hint="Error occurred during parameter extraction",
        )


async def main():
    """Точка входа для тестирования агента."""
    logging.basicConfig(level=logging.INFO)

    # Создаем зависимости для проверки настроек
    thermo_agent_config = ThermoAgentConfig()

    print("🚀 Запуск агента извлечения параметров")
    print(f"📋 Модель LLM: {thermo_agent_config.llm_model}")
    print(f"🔗 Базовый URL: {thermo_agent_config.llm_base_url}")
    print(f"🗄️ Путь к БД: {thermo_agent_config.db_path}")
    print(f"📊 Уровень логирования: {thermo_agent_config.log_level}")
    print(f"🐛 Debug режим: {thermo_agent_config.debug}")
    print()

    # Пример запроса
    test_query = (
        "При какой температуре идет взаимодействие карбида вольфрама с магнием?"
    )

    print(f"Запрос: {test_query}")

    result = await process_thermodynamic_query(test_query)

    print("✅ Параметры извлечены:")
    print(f"🎯 Intent: {result.intent}")
    print(f"🧪 Соединения: {result.compounds}")
    print(f"🌡️ Температура: {result.temperature_k} K")
    print(f"📊 Диапазон: {result.temperature_range_k}")
    print(f"🔬 Фазы: {result.phases}")
    print(f"📋 Свойства: {result.properties}")
    print(f"💡 SQL подсказка: {result.sql_query_hint}")


if __name__ == "__main__":
    asyncio.run(main())
