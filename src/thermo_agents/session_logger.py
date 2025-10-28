"""
Модуль для логирования сессий пользователя.
Каждая сессия = один пользовательский запрос.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Dict, List
import uuid
import json
from tabulate import tabulate


class SessionLogger:
    """
    Логгер для записи детальной информации о пользовательской сессии.

    Attributes:
        session_id: Уникальный идентификатор сессии
        log_file: Путь к файлу лога
        start_time: Время начала сессии
    """

    def __init__(self, logs_dir: Path = Path("logs/sessions")):
        """
        Инициализация логгера сессии.

        Args:
            logs_dir: Директория для сохранения логов
        """
        self.session_id = self._generate_session_id()
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Генерация имени файла: session_YYYYMMDD_HHMMSS_<id>.log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}_{self.session_id}.log"
        self.log_file = self.logs_dir / filename

        self.start_time = datetime.now()
        self._file_handle = open(self.log_file, "w", encoding="utf-8")

        # Запись заголовка сессии
        self._write_header()

    def _generate_session_id(self) -> str:
        """Генерация уникального ID сессии (6 символов hex)."""
        return uuid.uuid4().hex[:6]

    def _write_header(self) -> None:
        """Запись заголовка лог-файла."""
        separator = "=" * 80
        self._write(separator)
        self._write(f"SESSION START: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"SESSION ID: {self.session_id}")
        self._write(f"LOG FILE: {self.log_file}")
        self._write(separator)
        self._write("")
        self._write("Symbols legend:")
        self._write("  ✓ - Success / Data OK")
        self._write("  ○ - Not specified / Optional")
        self._write("  ⚠ - Warning / Potential issue")
        self._write("  ❌ - Error / Critical problem")
        self._write("")

    def _write(self, text: str = "") -> None:
        """Запись строки в файл."""
        self._file_handle.write(text + "\n")
        self._file_handle.flush()  # Немедленная запись на диск

    def close(self, status: str = "SUCCESS") -> None:
        """
        Закрытие сессии и файла лога.

        Args:
            status: Статус завершения сессии (SUCCESS/ERROR)
        """
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        separator = "=" * 80
        self._write("")
        self._write(separator)
        self._write(f"SESSION END: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self._write(f"TOTAL DURATION: {duration:.1f}s")
        self._write(f"STATUS: {status}")
        self._write(separator)

        self._file_handle.close()

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        status = "ERROR" if exc_type else "SUCCESS"
        self.close(status)

    def log_llm_request(self, query: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Логирование пользовательского запроса к LLM.

        Args:
            query: Текст запроса пользователя
            metadata: Дополнительные метаданные (опционально)
        """
        separator = "=" * 80
        self._write(separator)
        self._write(f"[LLM REQUEST] {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        self._write(separator)
        self._write(f"User query:")
        self._write(query)
        self._write("")
        self._write(f"Query length: {len(query)} characters")
        self._write(f"Query type: text")

        if metadata:
            self._write("\nMetadata:")
            for key, value in metadata.items():
                self._write(f"  {key}: {value}")

        self._write("")

    def log_llm_response(
        self,
        response: Dict[str, Any],
        duration: float,
        model: str = "gpt-4-turbo",
        temperature: float = 0.0,
        max_tokens: int = 1000
    ) -> None:
        """
        Логирование ответа от LLM.

        Args:
            response: Parsed JSON-ответ от LLM
            duration: Время обработки в секундах
            model: Название модели LLM
            temperature: Температура модели
            max_tokens: Максимальное количество токенов
        """
        separator = "=" * 80
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        self._write(separator)
        self._write(f"[LLM RESPONSE] {timestamp} (duration: {duration:.3f}s)")
        self._write(separator)
        self._write(f"Model: {model}")
        self._write(f"Temperature: {temperature}")
        self._write(f"Max tokens: {max_tokens}")
        self._write("")

        # Сырой JSON
        self._write("Raw response (JSON):")
        formatted_json = json.dumps(response, indent=2, ensure_ascii=False)
        self._write(formatted_json)
        self._write("")

        # Извлечённые параметры
        self._write("Extracted parameters:")
        for key, value in response.items():
            status = "✓" if value else "○"
            display_value = value if value else "not specified"
            self._write(f"  {status} {key}: {display_value}")

        self._write("")
        self._write("Status: SUCCESS")
        self._write("")

    def log_llm_error(self, error: Exception, raw_response: str = "") -> None:
        """
        Логирование ошибки при обработке LLM-ответа.

        Args:
            error: Объект исключения
            raw_response: Сырой ответ от LLM (если есть)
        """
        import traceback

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        self._write(f"[LLM ERROR] {timestamp}")
        self._write(f"Error type: {type(error).__name__}")
        self._write(f"Error message: {str(error)}")
        self._write("")

        if raw_response:
            self._write("Raw response:")
            self._write(raw_response)
            self._write("")

        self._write("Traceback:")
        self._write(traceback.format_exc())
        self._write("")

    def log_database_search(
        self,
        sql_query: str,
        parameters: Dict[str, Any],
        results: List[Dict[str, Any]],
        execution_time: float,
        context: str = ""
    ) -> None:
        """
        Логирование поиска в базе данных.

        Args:
            sql_query: SQL-запрос
            parameters: Параметры запроса
            results: Результаты запроса (список словарей)
            execution_time: Время выполнения в секундах
            context: Контекст поиска (описание)
        """
        separator = "=" * 80
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        self._write(separator)
        self._write(f"[DATABASE SEARCH] {timestamp}")
        self._write(separator)

        if context:
            self._write(f"Search context: {context}")

        # Параметры поиска
        if "formulas" in parameters:
            formulas_str = ", ".join(f"'{f}'" for f in parameters["formulas"])
            self._write(f"Compounds to search: [{formulas_str}]")
        self._write("")

        # SQL запрос
        self._write("SQL Query:")
        # Форматирование SQL для читаемости
        for line in sql_query.strip().split("\n"):
            self._write(f"  {line}")
        self._write("")

        # Параметры с подстановкой
        self._write("Parameters (substituted):")
        for key, value in parameters.items():
            self._write(f"  {key}: {value}")
        self._write("")

        # Статистика
        self._write(f"Execution time: {execution_time*1000:.1f} ms")
        self._write(f"Total records found: {len(results)}")
        display_count = min(30, len(results))
        self._write(f"Records to display: {display_count} (first batch)")
        self._write("")

        # Результаты в виде таблицы (вывод отключен по требованию пользователя)
        # Таблицы с дубликатами из базы данных больше не показываются
        # if results:
        #     self._write(separator)
        #     self._write(f"[SEARCH RESULTS] First {display_count} records")
        #     self._write(separator)
        #
        #     # Берём первые 30 записей
        #     display_results = results[:30]
        #
        #     # Форматирование через tabulate
        #     table_data = []
        #     headers = list(display_results[0].keys())
        #
        #     for row in display_results:
        #         formatted_row = []
        #         for key in headers:
        #             value = row[key]
        #             # Сокращение длинных значений
        #             if isinstance(value, str) and len(value) > 50:
        #                 value = value[:47] + "..."
        #             formatted_row.append(value)
        #         table_data.append(formatted_row)
        #
        #     # Создание таблицы
        #     table = tabulate(
        #         table_data,
        #         headers=headers,
        #         tablefmt="grid",
        #         numalign="right",
        #         stralign="left"
        #     )
        #     self._write(table)
        #
        #     if len(results) > 30:
        #         remaining = len(results) - 30
        #         self._write(f"\n... and {remaining} more records (not shown)")

        self._write("")

        # Группировка по формулам (опционально)
        self._log_formula_distribution(results)

    def log_deduplicated_results(
        self,
        original_results: List[Dict[str, Any]],
        deduplicated_results: List[Dict[str, Any]],
        compound_formula: str,
        execution_time: float = 0.0
    ) -> None:
        """
        Логирование результатов после дедупликации.

        Args:
            original_results: Оригинальные результаты с дубликатами
            deduplicated_results: Результаты после удаления дубликатов
            compound_formula: Формула соединения
            execution_time: Время выполнения дедупликации
        """
        separator = "=" * 80
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        self._write(separator)
        self._write(f"[DEDUPLICATION RESULTS] {timestamp}")
        self._write(separator)

        self._write(f"Compound: {compound_formula}")
        self._write(f"Original records: {len(original_results)}")
        self._write(f"Deduplicated records: {len(deduplicated_results)}")
        self._write(f"Duplicates removed: {len(original_results) - len(deduplicated_results)}")
        self._write(f"Deduplication rate: {((len(original_results) - len(deduplicated_results)) / len(original_results) * 100):.1f}%")
        self._write(f"Execution time: {execution_time*1000:.1f} ms")
        self._write("")

        # Результаты в виде таблицы после дедупликации
        if deduplicated_results:
            self._write(separator)
            self._write(f"[RESULTS AFTER DEDUPLICATION] All {len(deduplicated_results)} unique records")
            self._write(separator)

            # Форматирование через tabulate
            table_data = []
            headers = list(deduplicated_results[0].keys())

            for row in deduplicated_results:
                formatted_row = []
                for key in headers:
                    value = row[key]
                    # Сокращение длинных значений
                    if isinstance(value, str) and len(value) > 50:
                        value = value[:47] + "..."
                    formatted_row.append(value)
                table_data.append(formatted_row)

            # Создание таблицы
            table = tabulate(
                table_data,
                headers=headers,
                tablefmt="grid",
                numalign="right",
                stralign="left"
            )
            self._write(table)

        self._write("")

        # Группировка по формулам после дедупликации
        self._log_formula_distribution(deduplicated_results)

    def _log_formula_distribution(self, results: List[Dict[str, Any]]) -> None:
        """Логирование распределения результатов по формулам."""
        from collections import defaultdict

        formula_groups = defaultdict(list)
        for record in results:
            formula = record.get("formula", "UNKNOWN")
            phase = record.get("phase", "?")
            formula_groups[formula].append(phase)

        self._write("Grouped by formula:")
        for formula, phases in sorted(formula_groups.items()):
            phase_str = ", ".join(phases)
            self._write(f"  {formula}: {len(phases)} records ({phase_str})")

        self._write("")

    def _log_phase_distribution(
        self,
        records: List[Dict[str, Any]],
        label: str = "Phase distribution"
    ) -> None:
        """
        Логирование распределения по фазам для каждой формулы.

        Args:
            records: Список записей
            label: Заголовок секции
        """
        from collections import defaultdict

        # Группируем по формуле и фазе
        formula_phases = defaultdict(lambda: defaultdict(int))
        for record in records:
            formula = record.get("formula", "UNKNOWN")
            phase = record.get("phase", "?")
            formula_phases[formula][phase] += 1

        # Форматируем вывод
        parts = []
        for formula in sorted(formula_phases.keys()):
            phases = formula_phases[formula]
            phase_str = ", ".join(f"{p}:{count}" for p, count in sorted(phases.items()))
            parts.append(f"{formula}[{phase_str}]")

        distribution = ", ".join(parts)
        self._write(f"{label}: {distribution}")

    def log_filtering_stage(
        self,
        stage_name: str,
        stage_number: int,
        criteria: Dict[str, Any],
        input_count: int,
        output_count: int,
        input_records: Optional[List[Dict[str, Any]]] = None,
        output_records: Optional[List[Dict[str, Any]]] = None,
        removal_reasons: Optional[Dict[str, List[str]]] = None
    ) -> None:
        """
        Логирование одного этапа фильтрации.

        Args:
            stage_name: Название этапа
            stage_number: Номер этапа
            criteria: Критерии фильтрации
            input_count: Количество записей на входе
            output_count: Количество записей на выходе
            input_records: Записи на входе (для phase distribution)
            output_records: Записи на выходе (для phase distribution)
            removal_reasons: Причины удаления (группированные)
        """
        separator = "-" * 80

        self._write(separator)
        self._write(f"STAGE {stage_number}: {stage_name}")
        self._write(separator)

        # Критерии
        self._write("Criteria:")
        for key, value in criteria.items():
            self._write(f"  - {key}: {value}")
        self._write("")

        # Статистика
        removed = input_count - output_count
        self._write(f"Input records: {input_count}")
        self._write(f"Output records: {output_count}")
        self._write(f"Removed: {removed} records")
        self._write("")

        # Причины удаления (топ-3)
        if removal_reasons:
            # Сортируем причины по количеству удалённых записей
            sorted_reasons = sorted(
                removal_reasons.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )

            self._write("Removal reasons (top 3):")
            for reason, examples in sorted_reasons[:3]:
                self._write(f"  • {reason}: {len(examples)} records")
                self._write("    Examples:")
                for example in examples[:3]:  # Первые 3 примера
                    self._write(f"      - {example}")
                if len(examples) > 3:
                    self._write(f"      ... and {len(examples) - 3} more")
                self._write("")
        self._write("")

        # Phase distribution
        if input_records and output_records:
            self._write("Phase distribution:")
            self._log_phase_distribution(input_records, label="  Before")
            self._log_phase_distribution(output_records, label="  After")
            self._write("")

        # Результаты после этапа (первые 30) - только для STAGE 1 (дедупликация) и последней стадии
        if output_count > 0 and output_records:
            # Выводим таблицу после STAGE 1 (дедупликация)
            if stage_number == 1 or stage_name.lower().find("дубликат") != -1:
                self._write(f"Records after stage {stage_number} (first 30):")
                self._log_records_table(output_records, max_records=30)
            # Для других стадий таблицы не выводим
        self._write("")

    def log_filtering_pipeline_start(
        self,
        input_count: int,
        target_temp_range: tuple,
        required_compounds: List[str]
    ) -> None:
        """Начало pipeline фильтрации."""
        separator = "=" * 80
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Сохраняем целевой температурный диапазон для использования в warnings
        self._target_temp_min = target_temp_range[0]
        self._target_temp_max = target_temp_range[1]

        self._write(separator)
        self._write(f"[FILTERING PIPELINE] {timestamp}")
        self._write(separator)
        self._write(f"Input: {input_count} records from database search")
        self._write(f"Target temperature range: {target_temp_range[0]}-{target_temp_range[1]} K")
        compounds_str = ", ".join(f"'{c}'" for c in required_compounds)
        self._write(f"Required compounds: [{compounds_str}]")
        self._write("")

    def log_filtering_complete(
        self,
        final_count: int,
        initial_count: int,
        duration: float,
        warnings: List[str],
        final_records: List[Dict[str, Any]]
    ) -> None:
        """Завершение pipeline фильтрации."""
        separator = "=" * 80
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        removed = initial_count - final_count
        removal_pct = (removed / initial_count * 100) if initial_count > 0 else 0

        self._write(separator)
        self._write(f"[FILTERING COMPLETE] {timestamp} (duration: {duration*1000:.0f}ms)")
        self._write(separator)
        self._write(f"Final records: {final_count}")
        self._write(f"Records removed: {removed} ({removal_pct:.1f}%)")
        self._write(f"Warnings: {len(warnings)}")
        self._write(f"Errors: 0")
        self._write("")

        # Предупреждения (вывод убран по требованию пользователя)
        if warnings:
            self._write(f"Warnings: {len(warnings)} warnings detected")
            self._write("")

        # Финальный датасет
        if final_records:
            display_count = min(30, len(final_records))
            self._write(f"Final dataset (first {display_count}):")

            # Форматирование через tabulate
            self._log_records_table(final_records, max_records=30)
        self._write("")

    def _log_records_table(self, records: List[Dict[str, Any]], max_records: int = 30) -> None:
        """Логирование записей в виде таблицы."""
        if not records:
            return

        display_records = records[:max_records]
        headers = list(display_records[0].keys())
        table_data = []

        for record in display_records:
            row = []
            for key in headers:
                value = record[key]

                # Проверка на критичные проблемы
                if key in ["h298", "s298"] and value == 0:
                    value = f"{value} ❌"  # Критичная проблема
                # Проверка temperature coverage (если доступна информация)
                elif key == "t_max" and hasattr(self, '_target_temp_max'):
                    if value < self._target_temp_max:
                        value = f"{value}⚠"  # Warning
                elif key == "t_min" and hasattr(self, '_target_temp_min'):
                    if value > self._target_temp_min:
                        value = f"{value}⚠"  # Warning
                # Сокращение длинных строк
                elif isinstance(value, str) and len(value) > 30:
                    value = value[:27] + "..."

                row.append(value)
            table_data.append(row)

        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            numalign="right"
        )
        self._write(table)

        if len(records) > max_records:
            remaining = len(records) - max_records
            self._write(f"\n... and {remaining} more records (not shown)")

    def log_info(self, message: str) -> None:
        """
        Простой метод логирования информационных сообщений.

        Args:
            message: Информационное сообщение
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        self._write(f"[INFO] {timestamp}: {message}")

    def log_validation_check(
        self,
        validation_results: Dict[str, Any],
        issues: List[Dict[str, Any]]
    ) -> None:
        """Логирование результатов валидации."""
        separator = "-" * 80

        self._write(separator)
        self._write("STAGE 5: Final Validation")
        self._write(separator)

        # Чеки валидации
        self._write("Validation checks:")
        for check_name, result in validation_results.items():
            status = "✓" if result else "⚠"
            check_display = check_name.replace("_", " ").title()
            self._write(f"  {status} {check_display}: {result}")
        self._write("")

        # Пропускаем вывод проблем и рекомендаций по требованию пользователя
        # Секция "Issues detected:" и "Recommendations:" удалены
        if issues:
            # Только подсчитываем количество проблем для статистики
            issue_count = len(issues)
            if issue_count > 0:
                self._write(f"Validation completed with {issue_count} issue(s) detected")
        self._write("")