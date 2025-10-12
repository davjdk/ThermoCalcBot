"""
Модуль логирования для thermo_agents.

Создаёт отдельный лог-файл для каждой сессии общения.
Все действия агентов записываются как операции в рамках сессии.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Any, Dict

from tabulate import tabulate
from .operations import OperationLogger, OperationType


class SessionLogger:
    """Логгер для сессий общения с агентами на основе операций."""

    def __init__(self, logs_dir: str = "logs/sessions", storage=None):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.logs_dir / f"session_{self.session_id}.log"
        self.logger = self._setup_logger()

        # Инициализация логгера операций
        self.operation_logger = OperationLogger(self.logger, self.session_id)

        # Хранилище для создания снимков
        self.storage = storage

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

    def log_info(self, message: str):
        """Логирование информационного сообщения (не операции)."""
        self.logger.info(f"INFO: {message}")

    def log_error(self, message: str):
        """Логирование сообщения об ошибке (не операции)."""
        self.logger.error(f"ERROR: {message}")

    def create_operation_context(
        self,
        agent_name: str,
        operation_type: OperationType,
        correlation_id: Optional[str] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
    ):
        """
        Создать контекстный менеджер для операции.

        Args:
            agent_name: Имя агента
            operation_type: Тип операции
            correlation_id: ID корреляции
            source_agent: Агент-источник
            target_agent: Агент-получатель

        Returns:
            Контекстный менеджер операции
        """
        from .operations import OperationContext
        return OperationContext(
            operation_logger=self.operation_logger,
            agent_name=agent_name,
            operation_type=operation_type,
            correlation_id=correlation_id,
            source_agent=source_agent,
            target_agent=target_agent,
        )

    def is_operations_enabled(self) -> bool:
        """Проверить включена ли система операций (всегда True)."""
        return True

    def format_table(self, headers: List[str], rows: List[List[Any]], max_rows: Optional[int] = None) -> str:
        """
        Форматирует данные в виде таблицы с использованием tabulate.

        Args:
            headers: Список заголовков колонок
            rows: Список строк с данными
            max_rows: Максимальное количество строк для отображения

        Returns:
            Отформатированная таблица в виде строки
        """
        if not rows:
            return "No data to display"

        # Ограничиваем количество строк если нужно
        display_rows = rows[:max_rows] if max_rows else rows

        try:
            # Используем tabulate для форматирования
            formatted = tabulate(
                display_rows,
                headers=headers,
                tablefmt="grid",  # Используем grid для красивого форматирования
                floatfmt=".4g",   # Форматирование чисел с плавающей точкой
                missingval="N/A"  # Значение для пустых ячеек
            )
            return formatted
        except Exception as e:
            self.logger.error(f"Error formatting table: {e}")
            # Fallback - простой формат без tabulate
            result = "| " + " | ".join(headers) + " |\n"
            result += "|" + "|".join(["-" * (len(h) + 2) for h in headers]) + "|\n"
            for row in display_rows:
                result += "| " + " | ".join(str(cell) for cell in row) + " |\n"
            return result

    def log_compound_data_table(self, compound_results: List[Dict], title: str = "COMPOUND SEARCH RESULTS"):
        """
        Логировать данные по соединениям в виде таблицы.

        Args:
            compound_results: Список результатов по соединениям
            title: Заголовок таблицы
        """
        if not compound_results:
            self.log_info(f"{title}: No compounds found")
            return

        # Формируем данные для таблицы
        headers = ["Compound", "Records Count", "Confidence", "Temperature Range (K)", "Phases"]
        rows = []

        for result in compound_results:
            compound = result.get("compound", "Unknown")
            records_count = len(result.get("selected_records", []))
            confidence = result.get("confidence", 0.0)

            # Определяем температурный диапазон из записей
            selected_records = result.get("selected_records", [])
            if selected_records:
                t_min = min(record.get("Tmin", 0) for record in selected_records)
                t_max = max(record.get("Tmax", 0) for record in selected_records)
                temp_range = f"{t_min}-{t_max}"
            else:
                temp_range = "N/A"

            # Собираем уникальные фазы
            phases = list(set(record.get("Phase", "") for record in selected_records))
            phases_str = ", ".join(filter(None, phases)) if phases else "N/A"

            rows.append([compound, records_count, f"{confidence:.2f}", temp_range, phases_str])

        # Форматируем и логируем таблицу
        table = self.format_table(headers, rows)
        self.log_info(f"{title}:\n{table}")

    def log_detailed_compound_records(self, compound: str, records: List[Dict], title: str = None):
        """
        Логировать детальные записи по соединению.

        Args:
            compound: Химическая формула соединения
            records: Список записей по соединению
            title: Заголовок (если None, генерируется автоматически)
        """
        if not records:
            self.log_info(f"DETAILED RESULTS FOR {compound}: No records found")
            return

        if title is None:
            title = f"DETAILED RESULTS FOR {compound}"

        # Формируем данные для таблицы
        headers = ["Formula", "Phase", "Tmin (K)", "Tmax (K)", "H298 (J/mol)", "S298 (J/mol·K)",
                   "Melting Point (°C)", "Boiling Point (°C)"]
        rows = []

        for record in records:
            formula = record.get("Formula", compound)
            phase = record.get("Phase", "N/A")
            t_min = record.get("Tmin", "N/A")
            t_max = record.get("Tmax", "N/A")
            h298 = record.get("H298", "N/A")
            s298 = record.get("S298", "N/A")
            melting_point = record.get("MeltingPoint", "N/A")
            boiling_point = record.get("BoilingPoint", "N/A")

            rows.append([formula, phase, t_min, t_max, h298, s298, melting_point, boiling_point])

        # Форматируем и логируем таблицу
        table = self.format_table(headers, rows)
        self.log_info(f"{title}:\n{table}")

    def log_search_metadata(self, metadata: Dict, title: str = "SEARCH METADATA"):
        """
        Логировать метаданные поиска.

        Args:
            metadata: Словарь с метаданными
            title: Заголовок
        """
        self.log_info(f"{title}:")
        for key, value in metadata.items():
            self.log_info(f"  {key}: {value}")

    @property
    def current_session_file(self) -> Optional[Path]:
        """Получить путь к текущему файлу сессии."""
        return self.log_file if self.log_file.exists() else None

    def close(self):
        """Закрытие сессии."""
        self.logger.info("SESSION ENDED")

        # Отменяем все активные операции
        self.operation_logger.cancel_all_operations("Session ended")

        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)


def create_session_logger(logs_dir: str = "logs/sessions", storage=None) -> SessionLogger:
    """Создание нового логгера сессии."""
    return SessionLogger(logs_dir, storage)