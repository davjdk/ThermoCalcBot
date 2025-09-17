"""
SQL агент для генерации запросов к термодинамической базе данных.

Реализует генерацию SQL запросов на основе параметров, извлеченных основным агентом.
Использует SQL_GENERATION_PROMPT для создания корректных запросов к базе данных compounds.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Добавляем src в путь для корректных импортов
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from thermo_agents.prompts import SQL_GENERATION_PROMPT
from thermo_agents.thermo_agents_logger import SessionLogger

# =============================================================================
# МОДЕЛИ ДАННЫХ
# =============================================================================


class SQLQueryResult(BaseModel):
    """Результат генерации SQL запроса."""

    sql_query: str  # Сгенерированный SQL запрос
    explanation: str  # Краткое объяснение запроса
    expected_columns: list[str]  # Ожидаемые колонки в результате


# =============================================================================
# ЗАВИСИМОСТИ SQL АГЕНТА
# =============================================================================


@dataclass
class SQLAgentConfig:
    """Общие зависимости для SQL агента."""

    # Настройки из .env файла
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    db_path: str
    log_level: str
    debug: bool

    # Логгер
    logger: logging.Logger
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
# SQL АГЕНТ
# =============================================================================


def initialize_sql_agent(deps: SQLAgentConfig) -> Agent:
    """Создание SQL агента с настройками из зависимостей."""
    # Провайдер для OpenRouter
    provider = OpenAIProvider(
        api_key=deps.llm_api_key,
        base_url=deps.llm_base_url,
    )

    # Основная модель (OpenRouter via OpenAIChatModel)
    model = OpenAIChatModel(deps.llm_model, provider=provider)

    return Agent(
        model,
        deps_type=SQLAgentConfig,
        output_type=SQLQueryResult,
        system_prompt=SQL_GENERATION_PROMPT,
        retries=2,
    )


# =============================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =============================================================================


async def generate_sql_query(
    sql_hint: str, dependencies: Optional[SQLAgentConfig] = None
) -> SQLQueryResult:
    """
    Генерация SQL запроса на основе подсказки.

    Args:
        sql_hint: Подсказка для генерации SQL из основного агента
        dependencies: Зависимости SQL агента

    Returns:
        SQLQueryResult с сгенерированным запросом
    """
    if dependencies is None:
        # Создаем базовые зависимости если не переданы
        dependencies = SQLAgentConfig(
            llm_api_key="",
            llm_base_url="",
            llm_model="openai:gpt-4o",
            db_path="data/thermo_data.db",
            log_level="INFO",
            debug=False,
            logger=logging.getLogger(__name__),
        )

    dependencies.logger.info(
        f"Генерация SQL запроса для подсказки: {sql_hint[:100]}..."
    )

    if dependencies.session_logger:
        dependencies.session_logger.log_info("Начало генерации SQL запроса")

    try:
        # Создание агента с настройками из зависимостей
        agent = initialize_sql_agent(dependencies)

        # Генерация SQL запроса
        result = await agent.run(sql_hint, deps=dependencies)

        dependencies.logger.info("SQL запрос успешно сгенерирован")

        if dependencies.session_logger:
            dependencies.session_logger.log_sql_generation(
                result.output.sql_query,
                result.output.expected_columns,
                result.output.explanation,
            )
            dependencies.session_logger.log_info("SQL запрос успешно сгенерирован")

        return result.output

    except Exception as e:
        dependencies.logger.error(f"Ошибка генерации SQL запроса: {e}")

        if dependencies.session_logger:
            dependencies.session_logger.log_error(str(e))

        # Возвращаем базовый результат в случае ошибки
        return SQLQueryResult(
            sql_query="SELECT Formula, FirstName, Phase, H298, S298 FROM compounds LIMIT 10;",
            explanation="Базовый запрос в случае ошибки генерации",
            expected_columns=["Formula", "FirstName", "Phase", "H298", "S298"],
        )


# =============================================================================
# ТЕСТИРОВАНИЕ
# =============================================================================


async def main():
    """Точка входа для тестирования SQL агента."""
    logging.basicConfig(level=logging.INFO)

    # Создаем базовые зависимости для тестирования
    sql_agent_config = SQLAgentConfig(
        llm_api_key="",  # В реальном использовании брать из .env
        llm_base_url="",
        llm_model="openai:gpt-4o",
        db_path="data/thermo_data.db",
        log_level="INFO",
        debug=False,
        logger=logging.getLogger(__name__),
    )

    print("🚀 Запуск SQL агента")
    print(f"📋 Модель LLM: {sql_agent_config.llm_model}")
    print(f"🗄️ Путь к БД: {sql_agent_config.db_path}")
    print()

    # Пример подсказки для генерации SQL
    test_hint = (
        "Find thermodynamic data for TiO2(s), Cl2(g), TiCl4(g), and O2(g) "
        "in temperature range 573-873K. Include H298, S298, and heat capacity "
        "coefficients f1-f6 for reaction analysis."
    )

    print(f"Подсказка: {test_hint}")

    result = await generate_sql_query(test_hint, sql_agent_config)

    print("✅ SQL запрос сгенерирован:")
    print(f"📝 SQL: {result.sql_query}")
    print(f"📋 Ожидаемые колонки: {result.expected_columns}")
    print(f"💡 Объяснение: {result.explanation}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
