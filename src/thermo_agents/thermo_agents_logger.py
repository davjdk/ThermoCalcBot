"""
Модуль логирования для thermo_agents.

Создаёт отдельный лог-файл для каждой сессии общения.
"""

import logging
from datetime import datetime
from pathlib import Path

import yaml


class SessionLogger:
    """Логгер для сессий общения с агентом."""

    def __init__(self, logs_dir: str = "logs/sessions"):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.logs_dir / f"session_{self.session_id}.log"
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Настройка логгера для сессии."""
        logger = logging.getLogger(f"thermo_agents_session_{self.session_id}")
        logger.setLevel(logging.INFO)

        # Создание обработчика для файла
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # Форматтер
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)

        # Добавление обработчика
        logger.addHandler(file_handler)

        return logger

    def log_user_input(self, user_input: str):
        """Логирование ввода пользователя."""
        self.logger.info(f"USER: {user_input}")

    def log_agent_response(self, response: str):
        """Логирование ответа агента."""
        self.logger.info(f"AGENT: {response}")

    def log_error(self, error: str):
        """Логирование ошибки."""
        self.logger.error(f"ERROR: {error}")

    def log_info(self, message: str):
        """Логирование информационного сообщения."""
        self.logger.info(f"INFO: {message}")

    def log_extracted_parameters(self, params):
        """Логирование извлеченных параметров."""
        self.logger.info("EXTRACTED PARAMETERS:")
        self.logger.info(f"  Intent: {params.intent}")
        self.logger.info(f"  Compounds: {params.compounds}")
        self.logger.info(f"  Temperature: {params.temperature_k} K")
        self.logger.info(f"  Temperature Range: {params.temperature_range_k}")
        self.logger.info(f"  Phases: {params.phases}")
        self.logger.info(f"  Properties: {params.properties}")
        self.logger.info(f"  SQL Hint: {params.sql_query_hint}")

        try:
            import json
            json_output = json.dumps(params.model_dump(), ensure_ascii=False, indent=2)
            self.logger.info("  JSON Output:")
            self.logger.info(json_output)
        except Exception as e:
            self.logger.error(f"  Error serializing JSON: {e}")

    def log_sql_generation(
        self, sql_query: str, expected_columns: list, explanation: str
    ):
        """Логирование сгенерированного SQL запроса."""
        self.logger.info("GENERATED SQL:")
        self.logger.info(f"  SQL Query: {sql_query}")
        self.logger.info(f"  Expected Columns: {expected_columns}")
        self.logger.info(f"  Explanation: {explanation}")

    def log_processing_start(self, user_query: str):
        """Логирование начала обработки запроса."""
        self.logger.info(f"START PROCESSING: {user_query}")

    def log_processing_end(self):
        """Логирование завершения обработки."""
        self.logger.info("PROCESSING COMPLETED")

    def log_database_query(
        self, sql_query: str, row_count: int, columns: list, formatted_table: str = ""
    ):
        """Логирование результатов запроса к базе данных."""
        self.logger.info("DATABASE QUERY RESULTS:")
        self.logger.info(f"  SQL Query: {sql_query}")
        self.logger.info(f"  Row Count: {row_count}")
        self.logger.info(f"  Columns: {columns}")
        if formatted_table:
            self.logger.info("  Results Table:")
            # Разбиваем таблицу на строки для лучшего форматирования в логе
            for line in formatted_table.split("\n"):
                self.logger.info(f"    {line}")

    def format_table(self, columns: list, rows: list, max_rows: int = 10) -> str:
        """
        Форматирование данных в виде таблицы для логирования.

        Args:
            columns: Список названий колонок
            rows: Список строк данных
            max_rows: Максимальное количество строк для отображения

        Returns:
            Отформатированная таблица в виде строки
        """
        if not columns or not rows:
            return "No data to display"

        # Ограничиваем количество строк
        display_rows = rows[:max_rows]
        if len(rows) > max_rows:
            display_rows.append(["..."] * len(columns))

        # Вычисляем ширину колонок
        col_widths = []
        for i, col in enumerate(columns):
            # Ширина колонки = max(длина названия, max(длина значений в колонке))
            col_name_len = len(str(col))
            max_value_len = max([len(str(row[i])) for row in display_rows] + [0])
            col_widths.append(max(col_name_len, max_value_len, 3))  # минимум 3 символа

        # Создаем разделитель
        separator = "+" + "+".join("-" * (width + 2) for width in col_widths) + "+"

        # Создаем заголовок
        header = (
            "|"
            + "|".join(
                f" {str(col):<{width}} " for col, width in zip(columns, col_widths)
            )
            + "|"
        )

        # Создаем строки данных
        data_lines = []
        for row in display_rows:
            line = (
                "|"
                + "|".join(
                    f" {str(cell):<{width}} " for cell, width in zip(row, col_widths)
                )
                + "|"
            )
            data_lines.append(line)

        # Собираем таблицу
        table_lines = [separator, header, separator] + data_lines + [separator]

        return "\n".join(table_lines)

    def log_query_results_table(self, sql_query: str, columns: list, rows: list):
        """
        Логирование результатов запроса с базовой информацией.

        Args:
            sql_query: Выполненный SQL запрос
            columns: Список названий колонок
            rows: Список строк данных
        """
        row_count = len(rows)

        self.logger.info(f"Executed query, found {row_count} rows")
        self.logger.info("QUERY RESULTS:")
        self.logger.info(f"  SQL: {sql_query}")

        if rows:
            self.logger.info(f"  Total rows: {row_count}")
        else:
            self.logger.info("  No data returned")

    def log_final_results_table(self, records: list, columns: list) -> str:
        """
        Создает таблицу финальных результатов как для логирования, так и для пользователя.

        Args:
            records: Список записей (словарей)
            columns: Список колонок для отображения

        Returns:
            Отформатированная таблица в виде строки
        """
        if not records:
            return "Нет данных для отображения"

        # Формируем данные для таблицы
        table_rows = []
        for record in records:
            row = []
            for col in columns:
                value = record.get(col, "")
                # Форматируем числовые значения для лучшей читаемости
                if isinstance(value, float):
                    if abs(value) < 0.001 and value != 0.0:
                        row.append(f"{value:.2e}")
                    else:
                        row.append(f"{value:.4g}")
                else:
                    row.append(str(value))
            table_rows.append(row)

        # Создаем таблицу
        return self.format_table(columns, table_rows, max_rows=len(records))

    def close(self):
        """Закрытие сессии."""
        self.logger.info("SESSION ENDED")
        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)


def create_session_logger(logs_dir: str = "logs/sessions") -> SessionLogger:
    """Создание нового логгера сессии."""
    return SessionLogger(logs_dir)
