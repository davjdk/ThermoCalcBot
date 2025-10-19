"""
TableFormatter - форматирование результатов в таблицы через tabulate.

Класс отвечает за форматирование термодинамических данных в удобные
для чтения таблицы с соблюдением строгого порядка колонок.
"""

from typing import List

from tabulate import tabulate

from ..models.search import CompoundSearchResult, DatabaseRecord, MultiPhaseSearchResult


class TableFormatter:
    """Форматирование результатов в таблицы через tabulate."""

    def __init__(self):
        """Инициализация форматера таблиц."""
        self.headers = [
            "Формула",
            "Название",
            "Фаза",
            "T_диапазон (K)",
            "Tmelt (K)",
            "Tboil (K)",
            "H298 (кДж/моль)",
            "S298 (Дж/моль·K)",
            "Cp_коэффициенты (f1-f6)",
            "Надёжность (класс)",
        ]

    def format_summary_table(
        self, compounds_results: List[CompoundSearchResult]
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
            # Поддержка как старых, так и новых результатов поиска
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if not records:
                continue

            # Взять ВСЕ записи для вещества (могут быть разные фазы)
            for record in records:
                row = [
                    self._format_formula(record),
                    self._format_name(record),
                    self._format_phase(record),
                    self._format_temperature_range(record),
                    self._format_melting_point(record),
                    self._format_boiling_point(record),
                    self._format_h298(record),
                    self._format_s298(record),
                    self._format_cp_coefficients(record),
                    self._format_reliability(record),
                ]

                table_data.append(row)

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=self.headers, tablefmt="grid")

    def format_detailed_table(
        self,
        compounds_results: List[CompoundSearchResult],
        max_records_per_compound: int = 3,
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
            # Поддержка как старых, так и новых результатов поиска
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if not records:
                continue

            # Добавить заголовок вещества
            table_data.append(
                [f"** {result.compound_formula} **", "", "", "", "", "", "", "", "", ""]
            )

            # Добавить записи вещества
            for i, record in enumerate(records[:max_records_per_compound]):
                row = [
                    self._format_formula(record) if i == 0 else "",
                    self._format_name(record),
                    self._format_phase(record),
                    self._format_temperature_range(record),
                    self._format_melting_point(record),
                    self._format_boiling_point(record),
                    self._format_h298(record),
                    self._format_s298(record),
                    self._format_cp_coefficients(record),
                    self._format_reliability(record),
                ]
                table_data.append(row)

            # Добавить разделитель
            table_data.append(["", "", "", "", "", "", "", "", "", ""])

        # Удалить последний разделитель
        if table_data and table_data[-1] == ["", "", "", "", "", "", "", "", "", ""]:
            table_data.pop()

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=self.headers, tablefmt="grid")

    def _format_formula(self, record: DatabaseRecord) -> str:
        """Форматирование формулы (убрать фазу в скобках, если есть)."""
        if not record.formula:
            return "?"

        formula = record.formula
        if "(" in formula:
            return formula[: formula.index("(")].strip()
        return formula.strip()

    def _format_phase(self, record: DatabaseRecord) -> str:
        """Извлечение фазы."""
        if record.phase:
            return record.phase

        # Извлечь из формулы
        if record.formula and "(" in record.formula and ")" in record.formula:
            start = record.formula.index("(") + 1
            end = record.formula.index(")")
            return record.formula[start:end].strip()

        return "?"

    def _format_temperature_range(self, record: DatabaseRecord) -> str:
        """Форматирование температурного диапазона."""
        if record.tmin is None or record.tmax is None:
            return "?"

        tmin = int(record.tmin) if record.tmin is not None else 0
        tmax = int(record.tmax) if record.tmax is not None else float("inf")

        if tmax == float("inf"):
            return f"{tmin}-∞"
        else:
            return f"{tmin}-{tmax}"

    def _format_melting_point(self, record: DatabaseRecord) -> str:
        """Форматирование температуры плавления."""
        if not hasattr(record, "tmelt") or record.tmelt is None or record.tmelt <= 0:
            return "—"
        return f"{int(record.tmelt)}"

    def _format_boiling_point(self, record: DatabaseRecord) -> str:
        """Форматирование температуры кипения."""
        if not hasattr(record, "tboil") or record.tboil is None or record.tboil <= 0:
            return "—"
        return f"{int(record.tboil)}"

    def _format_h298(self, record: DatabaseRecord) -> str:
        """Форматирование энтальпии."""
        if record.h298 is None or not hasattr(record, "h298"):
            return "—"
        return f"{record.h298:.1f}"

    def _format_s298(self, record: DatabaseRecord) -> str:
        """Форматирование энтропии."""
        if record.s298 is None or not hasattr(record, "s298"):
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

    def _format_name(self, record: DatabaseRecord) -> str:
        """Форматирование названия соединения."""
        # Используем first_name (FirstName из базы), если доступно
        if (
            hasattr(record, "first_name")
            and record.first_name
            and record.first_name != "N/A"
        ):
            return record.first_name

        # Fallback на name, если доступно
        if hasattr(record, "name") and record.name and record.name != "N/A":
            return record.name

        return "N/A"

    def _format_reliability(self, record: DatabaseRecord) -> str:
        """Форматирование класса надёжности."""
        if record.reliability_class is None:
            return "?"
        return str(record.reliability_class)

    def format_compact_table(
        self, compounds_results: List[CompoundSearchResult]
    ) -> str:
        """
        Форматирование компактной таблицы только с основной информацией.

        Колонки:
        1. Формула
        2. Название
        3. Фаза
        4. T_диапазон (K)
        5. H298 (кДж/моль)
        6. Надёжность

        Args:
            compounds_results: Результаты поиска по веществам

        Returns:
            Отформатированная компактная таблица
        """
        compact_headers = [
            "Формула",
            "Название",
            "Фаза",
            "T_диапазон (K)",
            "H298 (кДж/моль)",
            "Надёжность",
        ]

        table_data = []

        for result in compounds_results:
            # Поддержка как старых, так и новых результатов поиска
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if not records:
                continue

            record = records[0]
            row = [
                self._format_formula(record),
                self._format_name(record),
                self._format_phase(record),
                self._format_temperature_range(record),
                self._format_h298(record),
                self._format_reliability(record),
            ]
            table_data.append(row)

        if not table_data:
            return "Нет данных для отображения"

        return tabulate(table_data, headers=compact_headers, tablefmt="grid")
