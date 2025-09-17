"""
SQL агент для генерации запросов к термодинамической базе данных.

Реализует генерацию SQL запросов на основе параметров, извлеченных основным агентом.
Использует SQL_GENERATION_PROMPT для создания корректных запросов к базе данных compounds.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Добавляем src в путь для корректных импортов
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
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


class DatabaseQueryResult(BaseModel):
    """Результат выполнения SQL запроса к базе данных."""

    sql_query: str  # Выполненный SQL запрос
    columns: list[str]  # Названия колонок
    rows: list[list[Any]]  # Данные в виде списка списков
    row_count: int  # Количество найденных записей
    formatted_table: str  # Отформатированная таблица для вывода


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

    agent = Agent(
        model,
        deps_type=SQLAgentConfig,
        output_type=SQLQueryResult,
        system_prompt=SQL_GENERATION_PROMPT,
        retries=2,
    )

    # Добавляем инструмент для выполнения SQL запросов
    @agent.tool
    async def execute_database_query(
        ctx: RunContext[SQLAgentConfig], sql_query: str
    ) -> DatabaseQueryResult:
        """
        Выполняет SQL запрос к термодинамической базе данных и возвращает результаты.

        Args:
            ctx: Контекст с зависимостями SQL агента
            sql_query: SQL запрос для выполнения

        Returns:
            DatabaseQueryResult с результатами запроса
        """
        try:
            # Выполняем запрос
            result = execute_sql_query(ctx.deps.db_path, sql_query, ctx.deps.logger)

            # Логируем результаты
            if ctx.deps.session_logger:
                ctx.deps.session_logger.log_database_query(
                    sql_query, result.row_count, result.columns, result.formatted_table
                )

            # Выводим таблицу пользователю
            print("\n" + "=" * 80)
            print("📊 РЕЗУЛЬТАТЫ ЗАПРОСА К БАЗЕ ДАННЫХ")
            print("=" * 80)
            print(f"📝 SQL запрос: {sql_query}")
            print(f"📋 Найдено записей: {result.row_count}")
            print(f"📊 Колонки: {', '.join(result.columns)}")
            print("\n" + result.formatted_table)
            print("=" * 80 + "\n")

            return result

        except Exception as e:
            error_msg = f"Ошибка выполнения SQL запроса: {str(e)}"
            ctx.deps.logger.error(error_msg)

            if ctx.deps.session_logger:
                ctx.deps.session_logger.log_error(error_msg)

            # Возвращаем пустой результат в случае ошибки
            return DatabaseQueryResult(
                sql_query=sql_query,
                columns=[],
                rows=[],
                row_count=0,
                formatted_table="Ошибка выполнения запроса",
            )

    return agent


# =============================================================================
# ОСНОВНЫЕ ФУНКЦИИ
# =============================================================================


def validate_sql_hint(sql_hint: str) -> None:
    """
    Валидирует подсказку для генерации SQL запроса.

    Args:
        sql_hint: Подсказка для генерации SQL

    Raises:
        ValueError: Если подсказка недостаточно информативна
    """
    if not sql_hint or sql_hint.strip() == "":
        raise ValueError("Подсказка для SQL запроса не может быть пустой")

    # Проверяем, что подсказка содержит достаточно информации
    hint_lower = sql_hint.lower()

    # Если подсказка слишком общая или содержит только ошибки
    if any(
        phrase in hint_lower
        for phrase in [
            "запрос необходимо дополнительно конкретизировать",
            "недостаточно информации",
            "error occurred",
            "базовый запрос",
        ]
    ):
        raise ValueError(
            "Недостаточно информации для генерации SQL запроса. "
            "Пожалуйста, уточните ваш запрос, указав конкретные соединения, "
            "температурный диапазон или свойства, которые вас интересуют."
        )


async def generate_sql_query(
    sql_hint: str,
    dependencies: Optional[SQLAgentConfig] = None,
    execute_query: bool = False,
) -> tuple[SQLQueryResult, Optional[DatabaseQueryResult]]:
    """
    Генерация SQL запроса на основе подсказки и опциональное выполнение.

    Args:
        sql_hint: Подсказка для генерации SQL из основного агента
        dependencies: Зависимости SQL агента
        execute_query: Флаг выполнения сгенерированного запроса

    Returns:
        Кортеж из SQLQueryResult и опционального DatabaseQueryResult

    Raises:
        ValueError: Если подсказка недостаточно информативна
    """
    # Валидируем входные данные
    validate_sql_hint(sql_hint)

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

        # Логируем параметры перед вызовом API
        dependencies.logger.debug(
            f"Вызов OpenAI API для SQL генерации с параметрами: sql_hint='{sql_hint}', model='{dependencies.llm_model}', base_url='{dependencies.llm_base_url}'"
        )

        # Генерация SQL запроса
        result = await agent.run(sql_hint, deps=dependencies)

        # Логируем успешный ответ
        dependencies.logger.debug(
            f"Ответ от OpenAI API для SQL: output='{result.output}'"
        )
        # Попытка логировать finish_reason
        try:
            messages = result.all_messages()
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, "parts") and last_msg.parts:
                    part = last_msg.parts[-1]
                    if hasattr(part, "finish_reason"):
                        dependencies.logger.debug(
                            f"finish_reason: {part.finish_reason}"
                        )
        except Exception as log_e:
            dependencies.logger.debug(f"Не удалось получить finish_reason: {log_e}")

        dependencies.logger.info("SQL запрос успешно сгенерирован")

        if dependencies.session_logger:
            dependencies.session_logger.log_sql_generation(
                result.output.sql_query,
                result.output.expected_columns,
                result.output.explanation,
            )
            dependencies.session_logger.log_info("SQL запрос успешно сгенерирован")

        # Опциональное выполнение запроса
        db_result = None
        if execute_query:
            db_result = await execute_sql_query_direct(
                result.output.sql_query, dependencies
            )

        return result.output, db_result

    except Exception as e:
        error_msg = f"Ошибка генерации SQL запроса: {e}"
        dependencies.logger.error(error_msg)
        dependencies.logger.debug(
            f"Детали ошибки: type={type(e).__name__}, args={e.args}, traceback={__import__('traceback').format_exc()}"
        )

        if dependencies.session_logger:
            dependencies.session_logger.log_error(error_msg)

        # Не создаем базовый запрос, а информируем о необходимости уточнения
        raise ValueError(
            "Недостаточно информации для генерации SQL запроса. "
            "Пожалуйста, уточните ваш запрос, указав конкретные соединения, "
            "температурный диапазон или свойства, которые вас интересуют."
        )


# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================


def format_table_results(columns: list[str], rows: list[list[Any]]) -> str:
    """
    Форматирует результаты запроса в виде таблицы для вывода.

    Args:
        columns: Названия колонок
        rows: Данные в виде списка списков

    Returns:
        Отформатированная строка с таблицей
    """
    if not rows:
        return "Нет данных для отображения"

    # Вычисляем максимальную ширину для каждой колонки
    col_widths = []
    for i, col in enumerate(columns):
        # Ширина колонки = max(длина названия колонки, максимальная длина значения в этой колонке)
        max_value_width = (
            max(len(str(row[i]) if i < len(row) else "") for row in rows) if rows else 0
        )
        col_widths.append(max(len(col), max_value_width))

    # Создаем разделитель
    separator = "+" + "+".join("-" * (width + 2) for width in col_widths) + "+"

    # Создаем заголовок
    header = (
        "|"
        + "|".join(f" {col:<{col_widths[i]}} " for i, col in enumerate(columns))
        + "|"
    )

    # Создаем строки данных
    data_rows = []
    for row in rows:
        formatted_row = "|"
        for i, value in enumerate(row):
            if i < len(columns):
                formatted_row += f" {str(value):<{col_widths[i]}} |"
        data_rows.append(formatted_row)

    # Собираем таблицу
    table_lines = [separator, header, separator]
    table_lines.extend(data_rows)
    table_lines.append(separator)

    return "\n".join(table_lines)


@contextmanager
def get_db_connection(db_path: str):
    """
    Контекстный менеджер для соединения с SQLite базой данных.

    Args:
        db_path: Путь к файлу базы данных

    Yields:
        sqlite3.Connection: Соединение с базой данных
    """
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def execute_sql_query(
    db_path: str, sql_query: str, logger: logging.Logger
) -> DatabaseQueryResult:
    """
    Выполняет SQL запрос к базе данных и возвращает результаты.

    Args:
        db_path: Путь к файлу базы данных
        sql_query: SQL запрос для выполнения
        logger: Логгер для записи информации

    Returns:
        DatabaseQueryResult с результатами запроса

    Raises:
        Exception: При ошибке выполнения запроса
    """
    logger.info(f"Выполнение SQL запроса: {sql_query[:100]}...")

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()

            # Выполняем запрос
            cursor.execute(sql_query)

            # Получаем названия колонок
            columns = (
                [desc[0] for desc in cursor.description] if cursor.description else []
            )

            # Получаем все строки
            rows = cursor.fetchall()

            # Конвертируем строки в списки (из sqlite3.Row в list)
            data_rows = [list(row) for row in rows] if rows else []

            # Форматируем таблицу
            formatted_table = format_table_results(columns, data_rows)

            result = DatabaseQueryResult(
                sql_query=sql_query,
                columns=columns,
                rows=data_rows,
                row_count=len(data_rows),
                formatted_table=formatted_table,
            )

            logger.info(f"Запрос выполнен успешно. Найдено записей: {len(data_rows)}")
            return result

    except Exception as e:
        logger.error(f"Ошибка выполнения SQL запроса: {e}")
        raise Exception(f"Ошибка выполнения запроса: {str(e)}")


# =============================================================================
# ТЕСТИРОВАНИЕ
# =============================================================================


async def execute_sql_query_direct(
    sql_query: str, dependencies: Optional[SQLAgentConfig] = None
) -> DatabaseQueryResult:
    """
    Прямое выполнение SQL запроса без генерации через LLM.

    Args:
        sql_query: SQL запрос для выполнения
        dependencies: Зависимости SQL агента

    Returns:
        DatabaseQueryResult с результатами запроса
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

    dependencies.logger.info(f"Прямое выполнение SQL запроса: {sql_query[:100]}...")

    if dependencies.session_logger:
        dependencies.session_logger.log_info("Начало выполнения SQL запроса")

    try:
        # Выполняем запрос
        result = execute_sql_query(dependencies.db_path, sql_query, dependencies.logger)

        # Логируем результаты
        if dependencies.session_logger:
            dependencies.session_logger.log_database_query(
                sql_query, result.row_count, result.columns, result.formatted_table
            )

        # Выводим таблицу пользователю
        print("\n" + "=" * 80)
        print("📊 РЕЗУЛЬТАТЫ ЗАПРОСА К БАЗЕ ДАННЫХ")
        print("=" * 80)
        print(f"📝 SQL запрос: {sql_query}")
        print(f"📋 Найдено записей: {result.row_count}")
        print(f"📊 Колонки: {', '.join(result.columns)}")
        print("\n" + result.formatted_table)
        print("=" * 80 + "\n")

        return result

    except Exception as e:
        dependencies.logger.error(f"Ошибка выполнения SQL запроса: {e}")

        if dependencies.session_logger:
            dependencies.session_logger.log_error(str(e))

        # Возвращаем пустой результат в случае ошибки
        return DatabaseQueryResult(
            sql_query=sql_query,
            columns=[],
            rows=[],
            row_count=0,
            formatted_table="Ошибка выполнения запроса",
        )
