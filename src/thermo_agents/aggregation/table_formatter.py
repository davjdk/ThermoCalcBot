"""
TableFormatter - форматирование результатов в таблицы через tabulate.

Класс отвечает за форматирование термодинамических данных в удобные
для чтения таблицы с соблюдением строгого порядка колонок.
"""

from tabulate import tabulate
from typing import List
from src.thermo_agents.models.search import CompoundSearchResult, DatabaseRecord


class TableFormatter:
    """Форматирование результатов в таблицы через tabulate."""

    def __init__(self):
        """Инициализация форматера таблиц."""
        self.headers = [
            "Формула",
            "Фаза",
            "T_диапазон (K)",
            "H298 (кДж/моль)",
            "S298 (Дж/моль·K)",
            "Cp_коэффициенты (f1-f6)",
            "Надёжность (класс)"
        ]

    def format_summary_table(
        self,
        compounds_results: List[CompoundSearchResult]
    ) -> str:
        """
        Форматирование сводной таблицы термодинамических свойств.

        Колонки (порядок строго соблюдается):
        1. Формула
        2. Фаза
        3. T_диапазон (K)
        4. H298 (кДж/моль)
        5. S298 (Дж/моль·K)
        6. Cp_коэффициенты (f1-f6)
        7. Надёжность (класс)

        Args:
            compounds_results: Результаты поиска по веществам

        Returns:
            Отформатированная таблица в формате 'grid'
        """
        table_data = []

        for result in compounds_results:
            if not result.records_found:
                continue

            # Взять первую (приоритетную) запись
            record = result.records_found[0]

            row = [
                self._format_formula(record),
                self._format_phase(record),
                self._format_temperature_range(record),
                self._format_h298(record),
                self._format_s298(record),
                self._format_cp_coefficients(record),
                self._format_reliability(record)
            ]

            table_data.append(row)

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=self.headers, tablefmt="grid")

    def format_detailed_table(
        self,
        compounds_results: List[CompoundSearchResult],
        max_records_per_compound: int = 3
    ) -> str:
        """
        Форматирование детальной таблицы с несколькими записями на вещество.

        Args:
            compounds_results: Результаты поиска по веществам
            max_records_per_compound: Максимальное количество записей на вещество

        Returns:
            Отформатированная детальная таблица
        """
        table_data = []

        for result in compounds_results:
            if not result.records_found:
                continue

            # Добавить заголовок вещества
            table_data.append([f"** {result.compound_formula} **", "", "", "", "", "", ""])

            # Добавить записи вещества
            for i, record in enumerate(result.records_found[:max_records_per_compound]):
                row = [
                    self._format_formula(record) if i == 0 else "",
                    self._format_phase(record),
                    self._format_temperature_range(record),
                    self._format_h298(record),
                    self._format_s298(record),
                    self._format_cp_coefficients(record),
                    self._format_reliability(record)
                ]
                table_data.append(row)

            # Добавить разделитель
            table_data.append(["", "", "", "", "", "", ""])

        # Удалить последний разделитель
        if table_data and table_data[-1] == ["", "", "", "", "", "", ""]:
            table_data.pop()

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=self.headers, tablefmt="grid")

    def _format_formula(self, record: DatabaseRecord) -> str:
        """Форматирование формулы (убрать фазу в скобках, если есть)."""
        if not record.formula:
            return "?"

        formula = record.formula
        if '(' in formula:
            return formula[:formula.index('(')].strip()
        return formula.strip()

    def _format_phase(self, record: DatabaseRecord) -> str:
        """Извлечение фазы."""
        if record.phase:
            return record.phase

        # Извлечь из формулы
        if record.formula and '(' in record.formula and ')' in record.formula:
            start = record.formula.index('(') + 1
            end = record.formula.index(')')
            return record.formula[start:end].strip()

        return "?"

    def _format_temperature_range(self, record: DatabaseRecord) -> str:
        """Форматирование температурного диапазона."""
        if record.tmin is None or record.tmax is None:
            return "?"

        tmin = int(record.tmin) if record.tmin is not None else 0
        tmax = int(record.tmax) if record.tmax is not None else float('inf')

        if tmax == float('inf'):
            return f"{tmin}-∞"
        else:
            return f"{tmin}-{tmax}"

    def _format_h298(self, record: DatabaseRecord) -> str:
        """Форматирование энтальпии."""
        if record.h298 is None or not hasattr(record, 'h298'):
            return "—"
        return f"{record.h298:.1f}"

    def _format_s298(self, record: DatabaseRecord) -> str:
        """Форматирование энтропии."""
        if record.s298 is None or not hasattr(record, 's298'):
            return "—"
        return f"{record.s298:.1f}"

    def _format_cp_coefficients(self, record: DatabaseRecord) -> str:
        """Форматирование коэффициентов теплоёмкости."""
        coeffs = [record.f1, record.f2, record.f3, record.f4, record.f5, record.f6]

        # Если все NULL
        if all(c is None for c in coeffs):
            return "—"

        # Форматирование с сокращением
        formatted = []
        for c in coeffs[:3]:  # Первые 3 коэффициента
            if c is not None:
                formatted.append(f"{c:.2e}" if abs(c) < 0.01 else f"{c:.3f}")
            else:
                formatted.append("—")

        return ", ".join(formatted) + ", ..."

    def _format_reliability(self, record: DatabaseRecord) -> str:
        """Форматирование класса надёжности."""
        if record.reliability_class is None:
            return "?"
        return str(record.reliability_class)

    def format_compact_table(
        self,
        compounds_results: List[CompoundSearchResult]
    ) -> str:
        """
        Форматирование компактной таблицы только с основной информацией.

        Колонки:
        1. Формула
        2. Фаза
        3. T_диапазон (K)
        4. H298 (кДж/моль)
        5. Надёжность

        Args:
            compounds_results: Результаты поиска по веществам

        Returns:
            Отформатированная компактная таблица
        """
        compact_headers = [
            "Формула",
            "Фаза",
            "T_диапазон (K)",
            "H298 (кДж/моль)",
            "Надёжность"
        ]

        table_data = []

        for result in compounds_results:
            if not result.records_found:
                continue

            record = result.records_found[0]
            row = [
                self._format_formula(record),
                self._format_phase(record),
                self._format_temperature_range(record),
                self._format_h298(record),
                self._format_reliability(record)
            ]
            table_data.append(row)

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=compact_headers, tablefmt="grid")