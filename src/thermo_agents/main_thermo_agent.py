"""
Термодинамический агент для извлечения параметров из запросов пользователя.

Реализует только первый шаг обработки: извлечение параметров из текста запроса
с использованием EXTRACT_INPUTS_PROMPT.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Добавляем src в путь для корректных импортов
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from thermo_agents.prompts import EXTRACT_INPUTS_PROMPT
from thermo_agents.sql_agent import SQLAgentConfig, SQLQueryResult, generate_sql_query
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


class ProcessingResult(BaseModel):
    """Результат полной обработки запроса с SQL."""

    extracted_params: ExtractedParameters  # Извлеченные параметры
    sql_query: str  # Сгенерированный SQL запрос
    explanation: str  # Объяснение SQL запроса
    expected_columns: List[str]  # Ожидаемые колонки


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

    # SQL агент конфигурация
    sql_agent_config: Optional[SQLAgentConfig] = None

    # Инициализация зависимостей
    def __post_init__(self):
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.setLevel(getattr(logging, self.log_level.upper(), logging.INFO))

        # Инициализируем SQL агент конфигурацию если не задана
        if self.sql_agent_config is None:
            self.sql_agent_config = SQLAgentConfig(
                llm_api_key=self.llm_api_key,
                llm_base_url=self.llm_base_url,
                llm_model=self.llm_model,
                db_path=self.db_path,
                log_level=self.log_level,
                debug=self.debug,
                logger=self.logger,
                session_logger=self.session_logger,
            )


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
            dependencies.session_logger.log_extracted_parameters(result.output)
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


async def process_thermodynamic_query_with_sql(
    user_query: str, dependencies: Optional[ThermoAgentConfig] = None
) -> ProcessingResult:
    """
    Полная обработка термодинамического запроса с генерацией SQL.

    Выполняет два шага:
    1. Извлечение параметров из запроса
    2. Генерация SQL запроса на основе извлеченных параметров
    """
    if dependencies is None:
        dependencies = ThermoAgentConfig()

    dependencies.logger.info(f"Полная обработка запроса: {user_query[:100]}...")

    if dependencies.session_logger:
        dependencies.session_logger.log_user_input(user_query)
        dependencies.session_logger.log_info("Начало полной обработки")

    try:
        # Шаг 1: Извлечение параметров
        extracted_params = await process_thermodynamic_query(user_query, dependencies)

        # Шаг 2: Генерация SQL запроса
        if dependencies.sql_agent_config:
            sql_result = await generate_sql_query(
                extracted_params.sql_query_hint, dependencies.sql_agent_config
            )
        else:
            # Fallback если SQL агент не настроен
            sql_result = SQLQueryResult(
                sql_query="SELECT Formula, FirstName, Phase, H298, S298 FROM compounds LIMIT 10;",
                explanation="Базовый запрос (SQL агент не настроен)",
                expected_columns=["Formula", "FirstName", "Phase", "H298", "S298"],
            )

        dependencies.logger.info("SQL запрос успешно сгенерирован")

        if dependencies.session_logger:
            dependencies.session_logger.log_info("Полная обработка завершена")

        return ProcessingResult(
            extracted_params=extracted_params,
            sql_query=sql_result.sql_query,
            explanation=sql_result.explanation,
            expected_columns=sql_result.expected_columns,
        )

    except Exception as e:
        dependencies.logger.error(f"Ошибка полной обработки: {e}")

        if dependencies.session_logger:
            dependencies.session_logger.log_error(str(e))

        # Возвращаем базовый результат в случае ошибки
        return ProcessingResult(
            extracted_params=ExtractedParameters(
                intent="unknown",
                compounds=[],
                temperature_k=298.15,
                temperature_range_k=[200, 2000],
                phases=[],
                properties=["basic"],
                sql_query_hint="Error occurred during processing",
            ),
            sql_query="SELECT Formula, FirstName, Phase, H298, S298 FROM compounds LIMIT 10;",
            explanation="Базовый запрос в случае ошибки",
            expected_columns=["Formula", "FirstName", "Phase", "H298", "S298"],
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
    print()

    # Тестируем полную обработку с SQL генерацией
    print("🔍 Выполняем полную обработку с генерацией SQL...")
    result = await process_thermodynamic_query_with_sql(test_query, thermo_agent_config)

    print("✅ Обработка завершена:")
    print()
    print("📋 Извлеченные параметры:")
    print(f"🎯 Intent: {result.extracted_params.intent}")
    print(f"🧪 Соединения: {result.extracted_params.compounds}")
    print(f"🌡️ Температура: {result.extracted_params.temperature_k} K")
    print(f"📊 Диапазон: {result.extracted_params.temperature_range_k}")
    print(f"🔬 Фазы: {result.extracted_params.phases}")
    print(f"📋 Свойства: {result.extracted_params.properties}")
    print(f"💡 SQL подсказка: {result.extracted_params.sql_query_hint}")
    print()
    print("💾 Сгенерированный SQL:")
    print(f"📝 SQL: {result.sql_query}")
    print(f"📊 Ожидаемые колонки: {result.expected_columns}")
    print(f"💡 Объяснение: {result.extracted_params.sql_query_hint}")


if __name__ == "__main__":
    asyncio.run(main())
