"""
Модуль логирования для thermo_agents.

Создаёт отдельный лог-файл для каждой сессии общения.
Все действия агентов записываются как операции в рамках сессии.
"""

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tabulate import tabulate

from .operations import OperationType


@dataclass
class SimpleOperationTimer:
    """Простой контекст менеджер для измерения времени операций."""
    logger: 'SessionLogger'
    operation_type: str
    agent_name: str
    correlation_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __enter__(self):
        self.logger.log_info(
            f"Started operation: {self.operation_type} "
            f"[{self.agent_name}] "
            f"(ID: {self.operation_id[:8]})"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        if exc_type:
            self.logger.log_error(
                f"Failed operation: {self.operation_type} "
                f"[{self.agent_name}] "
                f"(ID: {self.operation_id[:8]}) "
                f"({duration_ms:.1f}ms) - {exc_val}"
            )
        else:
            self.logger.log_info(
                f"Completed operation: {self.operation_type} "
                f"[{self.agent_name}] "
                f"(ID: {self.operation_id[:8]}) "
                f"({duration_ms:.1f}ms)"
            )
        return False  # Не подавлять исключения


class SessionLogger:
    """
    Логгер для сессий общения с агентами.
    """

    def __init__(self, logs_dir: str = "logs/sessions", storage=None, session_id: Optional[str] = None):
        """
        Инициализация сессионного логгера.

        Args:
            logs_dir: Директория для логов
            storage: Хранилище
            session_id: ID сессии (генерируется если не указан)
        """
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Генерируем session_id если не указан
        if session_id is None:
            self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        else:
            self.session_id = session_id

        self.log_file = self.logs_dir / f"session_{self.session_id}.log"

        # Настраиваем стандартный логгер
        self.logger = logging.getLogger(f"session_logger_{self.session_id}")
        self.logger.setLevel(logging.INFO)

        # Очищаем существующие handlers
        self.logger.handlers.clear()

        # Создаем formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Хранилище для создания снимков
        self.storage = storage

        # Эмуляция operation_logger для совместимости
        self.operation_logger = self

    def _sanitize_message(self, message: str) -> str:
        """
        Очистить сообщение от проблемных Unicode символов.

        Args:
            message: Исходное сообщение

        Returns:
            Очищенное сообщение, безопасное для логирования
        """
        if not message:
            return message

        try:
            # Проверяем, можно ли закодировать в UTF-8
            message.encode("utf-8")
            return message
        except UnicodeEncodeError:
            # Заменяем проблемные символы
            sanitized = message.encode("utf-8", errors="replace").decode("utf-8")
            self.logger.warning(
                f"MESSAGE SANITIZED: Original contained problematic Unicode characters"
            )
            return sanitized

    def _sanitize_header(self, header: str) -> str:
        """
        Очистить заголовок таблицы от проблемных Unicode символов.

        Args:
            header: Заголовок таблицы

        Returns:
            Очищенный заголовок
        """
        try:
            header.encode("utf-8")
            return header
        except UnicodeEncodeError:
            # Заменяем проблемные символы в заголовках
            return header.encode("utf-8", errors="replace").decode("utf-8")

    def _sanitize_cell(self, cell: str) -> str:
        """
        Очистить ячейку таблицы от проблемных Unicode символов.

        Args:
            cell: Содержимое ячейки

        Returns:
            Очищенное содержимое
        """
        try:
            cell.encode("utf-8")
            return cell
        except UnicodeEncodeError:
            # Заменяем проблемные символы в ячейках
            return cell.encode("utf-8", errors="replace").decode("utf-8")

    def log_info(self, message: str):
        """Логирование информационного сообщения (не операции)."""
        sanitized_message = self._sanitize_message(message)
        self.logger.info(sanitized_message)

    def log_error(self, message: str):
        """Логирование сообщения об ошибке (не операции)."""
        sanitized_message = self._sanitize_message(message)
        self.logger.error(sanitized_message)

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
        # Создаем простой контекст менеджер для операций
        return SimpleOperationTimer(
            logger=self,
            operation_type=operation_type.value,
            agent_name=agent_name,
            correlation_id=correlation_id
        )

    def is_operations_enabled(self) -> bool:
        """Проверить включена ли система операций (всегда True)."""
        return True

    def format_table(
        self, headers: List[str], rows: List[List[Any]], max_rows: Optional[int] = None
    ) -> str:
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
            # Очищаем заголовки и данные от проблемных Unicode
            clean_headers = [self._sanitize_header(str(h)) for h in headers]
            clean_rows = []
            for row in display_rows:
                clean_row = []
                for cell in row:
                    clean_cell = self._sanitize_cell(str(cell))
                    clean_row.append(clean_cell)
                clean_rows.append(clean_row)

            # Используем tabulate для форматирования
            formatted = tabulate(
                clean_rows,
                headers=clean_headers,
                tablefmt="grid",  # Используем grid для красивого форматирования
                floatfmt=".4g",  # Форматирование чисел с плавающей точкой
                missingval="N/A",  # Значение для пустых ячеек
            )
            return formatted
        except Exception as e:
            self.logger.error(f"Error formatting table: {e}")
            # Fallback - простой формат без tabulate, с очисткой
            result = (
                "| "
                + " | ".join(self._sanitize_header(str(h)) for h in headers)
                + " |\n"
            )
            result += "|" + "|".join(["-" * (len(str(h)) + 2) for h in headers]) + "|\n"
            for row in display_rows:
                safe_row = [self._sanitize_cell(str(cell)) for cell in row]
                result += "| " + " | ".join(safe_row) + " |\n"
            return result

    def log_compound_data_table(
        self, compound_results: List[Dict], title: str = "COMPOUND SEARCH RESULTS"
    ):
        """
        Логировать данные по соединениям в виде таблицы.

        Args:
            compound_results: Список результатов по соединениям
            title: Заголовок таблицы
        """
        # Базовое логирование для совместимости
        if not compound_results:
            self.log_info(f"{title}: No compounds found")
            return

        # Формируем данные для таблицы
        headers = [
            "Compound",
            "Records Count",
            "Confidence",
            "Temperature Range (K)",
            "Phases",
        ]
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

            rows.append(
                [compound, records_count, f"{confidence:.2f}", temp_range, phases_str]
            )

        # Форматируем и логируем таблицу
        table = self.format_table(headers, rows)
        self.log_info(f"{title}:\n{table}")

    def log_detailed_compound_records(
        self, compound: str, records: List[Dict], title: str = None
    ):
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
        headers = [
            "Formula",
            "Phase",
            "Tmin (K)",
            "Tmax (K)",
            "H298 (J/mol)",
            "S298 (J/mol·K)",
            "Melting Point (°C)",
            "Boiling Point (°C)",
        ]
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

            rows.append(
                [formula, phase, t_min, t_max, h298, s298, melting_point, boiling_point]
            )

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
        # Базовое логирование
        self.log_info(f"{title}:")
        for key, value in metadata.items():
            self.log_info(f"  {key}: {value}")

    def log_stage_header(
        self, stage_number: int, stage_name: str, compound_formula: str
    ):
        """
        Логировать заголовок стадии фильтрации с визуальными разделителями.

        Args:
            stage_number: Номер стадии
            stage_name: Название стадии
            compound_formula: Формула вещества
        """
        separator = "═" * 63
        self.log_info(separator)
        self.log_info(
            f"СТАДИЯ {stage_number}: {stage_name} | Вещество: {compound_formula}"
        )
        self.log_info("─" * 63)

    def log_stage_statistics(self, stats: Dict[str, Any]):
        """
        Логировать статистику стадии фильтрации.

        Args:
            stats: Словарь со статистикой стадии
        """
        # Основные метрики
        records_before = stats.get("records_before", 0)
        records_after = stats.get("records_after", 0)
        reduction_rate = stats.get("reduction_rate", 0.0)
        execution_time_ms = stats.get("execution_time_ms", 0.0)

        self.log_info(f"Записей до фильтрации: {records_before}")
        self.log_info(f"Записей после фильтрации: {records_after}")
        self.log_info(f"Процент отсева: {reduction_rate:.1f}%")
        self.log_info(f"Время выполнения: {execution_time_ms:.1f} мс")

        # Специфичная информация для разных типов стадий
        stage_name = stats.get("stage_name", "").lower()

        if "температур" in stage_name or "temperature" in stage_name.lower():
            # Температурная фильтрация
            temp_range = stats.get("temperature_range")
            if temp_range:
                self.log_info(
                    f"Температурный диапазон: {temp_range[0]:.1f} - {temp_range[1]:.1f} K"
                )
            in_range = stats.get("records_in_range", 0)
            out_range = stats.get("records_out_range", 0)
            self.log_info(f"Записей в диапазоне: {in_range}")
            self.log_info(f"Записей вне диапазона: {out_range}")

        elif "фаз" in stage_name or "phase" in stage_name.lower():
            # Выбор фазового состояния
            phase_distribution = stats.get("phase_distribution", {})
            if phase_distribution:
                self.log_info("Распределение по фазам:")
                for phase, count in phase_distribution.items():
                    phase_name = self._get_phase_description(phase)
                    self.log_info(f"  {phase} ({phase_name}): {count} записей")

            expected_phase = stats.get("expected_phase")
            if expected_phase:
                expected_phase_name = self._get_phase_description(expected_phase)
                self.log_info(
                    f"Ожидаемая фаза: {expected_phase} ({expected_phase_name})"
                )

            correct_phases = stats.get("correct_phases", 0)
            incorrect_phases = stats.get("incorrect_phases", 0)
            if correct_phases > 0 or incorrect_phases > 0:
                self.log_info(f"Корректных фаз: {correct_phases}")
                self.log_info(f"Некорректных фаз: {incorrect_phases}")

        elif "надежност" in stage_name or "reliability" in stage_name.lower():
            # Приоритизация по классу надежности
            reliability_distribution = stats.get("reliability_distribution", {})
            if reliability_distribution:
                self.log_info("Распределение по классам надежности:")
                for rel_class, count in sorted(reliability_distribution.items()):
                    self.log_info(f"  Класс {rel_class}: {count} записей")

            max_records = stats.get("max_records", 0)
            if max_records > 0:
                self.log_info(f"Максимальное количество записей: {max_records}")

        elif "покрыт" in stage_name or "coverage" in stage_name.lower():
            # Проверка температурного покрытия
            coverage_percent = stats.get("coverage_percentage", 0.0)
            self.log_info(f"Покрытие диапазона: {coverage_percent:.1f}%")

            gaps = stats.get("temperature_gaps", [])
            if gaps:
                self.log_info(f"Пробелы в данных: {len(gaps)}")
                for i, gap in enumerate(gaps[:3], 1):  # Показываем первые 3 пробела
                    self.log_info(f"  Пробел {i}: {gap[0]:.1f} - {gap[1]:.1f} K")

        # Дополнительная статистика из метода get_statistics()
        # Исключаем избыточные метрики производительности
        excluded_keys = {
            "stage_number",
            "stage_name",
            "records_before",
            "records_after",
            "reduction_rate",
            "execution_time_ms",
            "performance",  # Исключаем все метрики производительности
            "mid_temperature",  # Исключаем среднюю температуру
            "average_score",  # Исключаем средний score
        }

        additional_stats = {k: v for k, v in stats.items() if k not in excluded_keys}

        if additional_stats:
            self.log_info("Дополнительная статистика:")
            for key, value in additional_stats.items():
                if isinstance(value, (int, float)):
                    self.log_info(f"  {key}: {value}")
                elif isinstance(value, dict):
                    self.log_info(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        self.log_info(f"    {sub_key}: {sub_value}")

    def format_records_table(self, records: List[Any], max_rows: int = 10) -> str:
        """
        Форматирует DatabaseRecord в таблицу согласно спецификации.

        Args:
            records: Список записей из БД (DatabaseRecord)
            max_rows: Максимальное количество строк (по умолчанию 10)

        Returns:
            Отформатированная таблица в формате grid
        """
        if not records:
            return "Нет данных для отображения"

        headers = [
            "Formula",
            "FirstName",
            "Phase",
            "Tmin-Tmax (K)",
            "Tmelt (K)",
            "Tboil (K)",
        ]
        rows = []

        for record in records[:max_rows]:
            # Извлекаем данные из DatabaseRecord
            formula = getattr(record, "formula", "N/A")
            # Сначала пробуем first_name (FirstName из БД), потом name
            first_name = getattr(record, "first_name", None) or getattr(
                record, "name", "N/A"
            )
            phase = getattr(record, "phase", "N/A")
            tmin = getattr(record, "tmin", None)
            tmax = getattr(record, "tmax", None)
            tmelt = getattr(record, "tmelt", None)
            tboil = getattr(record, "tboil", None)

            # Форматируем температурный диапазон
            if tmin is not None and tmax is not None:
                temp_range = f"{tmin:.2f} - {tmax:.2f}"
            else:
                temp_range = "N/A"

            # Форматируем Tmelt
            if tmelt is not None and tmelt > 0:
                tmelt_str = f"{int(tmelt)}"
            else:
                tmelt_str = "—"

            # Форматируем Tboil
            if tboil is not None and tboil > 0:
                tboil_str = f"{int(tboil)}"
            else:
                tboil_str = "—"

            rows.append([formula, first_name, phase, temp_range, tmelt_str, tboil_str])

        return tabulate(
            rows, headers=headers, tablefmt="grid", floatfmt=".2f", missingval="N/A"
        )

    def log_filter_stage_table(
        self, records: List[Any], compound_formula: str, stage_name: str
    ):
        """
        Логировать таблицу результатов стадии фильтрации.

        Args:
            records: Список записей для отображения
            compound_formula: Формула вещества
            stage_name: Название стадии
        """
        if not records:
            return

        # Форматируем таблицу (первые 10 записей)
        table = self.format_records_table(records[:10])

        # Добавляем информацию о количестве
        total_records = len(records)
        shown_records = min(total_records, 10)

        self.log_info("")  # Пустая строка перед таблицей

        if total_records > 10:
            self.log_info(
                f"Таблица данных (показано {shown_records} из {total_records} записей):"
            )
        else:
            self.log_info(f"Таблица данных ({total_records} записей):")

        self.log_info(table)

        # Если есть еще записи, показываем их количество
        if total_records > 10:
            self.log_info(
                f"[показаны первые {shown_records} из {total_records} записей]"
            )

    def log_llm_interaction(
        self,
        user_query: str,
        llm_response: Any,
        extracted_params: Optional[Any] = None,
        extraction_time_ms: float = 0.0,
    ):
        """
        Логировать взаимодействие с LLM: запрос, ответ и извлечённые параметры.

        Args:
            user_query: Исходный запрос пользователя
            llm_response: Полный ответ от LLM (объект result из pydantic_ai)
            extracted_params: Извлечённые параметры (ExtractedReactionParameters)
            extraction_time_ms: Время выполнения запроса в миллисекундах
        """
        # Базовое детализированное логирование
        separator = "═" * 63
        self.log_info(separator)
        self.log_info("LLM INTERACTION - ИЗВЛЕЧЕНИЕ ПАРАМЕТРОВ")
        self.log_info("─" * 63)

        # 1. Исходный запрос пользователя
        self.log_info("ИСХОДНЫЙ ЗАПРОС:")
        self.log_info(f"  {user_query}")
        self.log_info("")

        # 2. Время выполнения
        if extraction_time_ms > 0:
            self.log_info(f"ВРЕМЯ ВЫПОЛНЕНИЯ: {extraction_time_ms:.1f} мс")
            self.log_info("")

        # 3. Валидация структуры и извлечённые параметры
        if extracted_params:
            self.log_info("ИЗВЛЕЧЁННЫЕ ПАРАМЕТРЫ:")
            self.log_info("─" * 63)

            # Основные поля
            if hasattr(extracted_params, "balanced_equation"):
                self.log_info(
                    f"Уравнение реакции: {extracted_params.balanced_equation}"
                )

            if hasattr(extracted_params, "all_compounds"):
                self.log_info(
                    f"Количество веществ: {len(extracted_params.all_compounds)}"
                )
                self.log_info(
                    f"Все вещества: {', '.join(extracted_params.all_compounds)}"
                )

            if hasattr(extracted_params, "reactants"):
                self.log_info(f"Реагенты: {', '.join(extracted_params.reactants)}")

            if hasattr(extracted_params, "products"):
                self.log_info(f"Продукты: {', '.join(extracted_params.products)}")

            if hasattr(extracted_params, "temperature_range_k"):
                tmin, tmax = extracted_params.temperature_range_k
                self.log_info(f"Температурный диапазон: {tmin:.1f} - {tmax:.1f} K")
                self.log_info(f"  ({tmin - 273.15:.1f} - {tmax - 273.15:.1f} °C)")

            if hasattr(extracted_params, "extraction_confidence"):
                self.log_info(
                    f"Уверенность извлечения: {extracted_params.extraction_confidence:.2f}"
                )

            # 7. Статус полноты
            if hasattr(extracted_params, "is_complete"):
                is_complete = extracted_params.is_complete()
                status_symbol = "✓" if is_complete else "✗"
                status_text = "ПОЛНЫЕ" if is_complete else "НЕПОЛНЫЕ"
                self.log_info("")
                self.log_info(f"{status_symbol} СТАТУС: {status_text} данные")

        self.log_info(separator)
        self.log_info("")

    def _get_phase_description(self, phase: str) -> str:
        """
        Получить описание фазы на русском языке.

        Args:
            phase: Код фазы (s, l, g, aq, etc.)

        Returns:
            Описание фазы на русском языке
        """
        phase_descriptions = {
            "s": "твёрдая",
            "l": "жидкая",
            "g": "газообразная",
            "aq": "водный раствор",
            "a": "аморфная",
            "ao": "аморфная оксидная",
            "ai": "аморфная интерметаллида",
            "cr": "кристаллическая",
            "liq": "жидкость",
            "gas": "газ",
        }
        return phase_descriptions.get(phase.lower(), phase.lower())

    @property
    def current_session_file(self) -> Optional[Path]:
        """Получить путь к текущему файлу сессии."""
        return self.log_file if self.log_file.exists() else None

    def close(self):
        """Закрытие сессии."""
        self.log_info("SESSION ENDED")

        # Закрываем handlers
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()


def create_session_logger(
    logs_dir: str = "logs/sessions", storage=None
) -> SessionLogger:
    """Создание нового логгера сессии."""
    return SessionLogger(logs_dir, storage)
