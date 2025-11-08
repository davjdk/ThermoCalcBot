"""
Форматирование информации о веществах для единого вывода реакции.

Включает информацию о фазах, источниках данных, температурных диапазонах,
фазовых переходах и использованных записях из БД.
"""

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from tabulate import tabulate


class CompoundInfoFormatter:
    """
    Форматирование информации о веществах.
    """

    @staticmethod
    def convert_to_subscript(formula: str) -> str:
        """
        Конвертирует цифры в формуле в подстрочные индексы.

        Примеры:
            Al2O3 → Al₂O₃
            H2O → H₂O
            SO2 → SO₂
        """
        subscript_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        return formula.translate(subscript_map)

    @staticmethod
    def format_compound(
        formula: str,
        records_used: List[pd.Series],
        melting_point: Optional[float],
        boiling_point: Optional[float],
        compound_names: List[str],
    ) -> str:
        """
        Форматирует информацию об одном веществе.

        Включает:
        - Формулу с подстрочными индексами (например, Al₂O₃)
        - Название (FirstName/SecondName из БД)
        - Фазы всех использованных записей
        - Температурный диапазон применимости
        - H₂₉₈ и S₂₉₈ (из первой записи)
        - Cp коэффициенты (f₁-f₆)
        - Источник данных (Reference) и ReliabilityClass
        - Информацию о фазовых переходах
        - Количество использованных записей по фазам

        Args:
            formula: Химическая формула
            records_used: Список использованных записей (pd.Series)
            melting_point: Температура плавления (K) или None
            boiling_point: Температура кипения (K) или None
            compound_names: Список имен из LLM response

        Returns:
            Отформатированная строка с информацией о веществе
        """
        if not records_used:
            return f"{CompoundInfoFormatter.convert_to_subscript(formula)} — ❌ Данные не найдены"

        lines = []

        # Основная информация
        formula_subscript = CompoundInfoFormatter.convert_to_subscript(formula)
        first_record = records_used[0]

        # Имя вещества
        name = (
            first_record.get("FirstName") or compound_names[0]
            if compound_names
            else "Неизвестное вещество"
        )
        lines.append(f"{formula_subscript} — {name}")

        # Собираем информацию по фазам
        phases = {}
        min_temp = float("inf")
        max_temp = float("-inf")

        for record in records_used:
            phase = record.get("Phase", "unknown")
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(record)

            tmin = record.get("Tmin", 0)
            tmax = record.get("Tmax", 0)
            min_temp = min(min_temp, tmin)
            max_temp = max(max_temp, tmax)

        # Фазы и температурный диапазон
        phase_list = ", ".join(sorted(phases.keys()))
        lines.append(
            f"  Фаза: {phase_list} | T_применимости: {min_temp:.0f}-{max_temp:.0f} K"
        )

        # H298 и S298 из первой записи
        h298 = first_record.get("H298", 0)
        s298 = first_record.get("S298", 0)
        lines.append(
            f"  H₂₉₈: {h298 / 1000:.3f} кДж/моль | S₂₉₈: {s298:.3f} Дж/(моль·K)"
        )

        # Cp коэффициенты
        cp_coeffs = []
        for i in range(1, 7):
            coeff = first_record.get(f"f{i}", 0)
            cp_coeffs.append(f"{coeff:.6f}")
        lines.append(f"  Cp коэффициенты: [{', '.join(cp_coeffs)}]")

        # Источник данных
        reference = first_record.get("Reference", "Неизвестно")
        reliability = first_record.get("ReliabilityClass", 0)
        lines.append(f"  Источник: {reference} (ReliabilityClass: {reliability})")

        # Информация о фазовых переходах
        transition_lines = []

        if melting_point is not None:
            transition_lines.append(
                f"    • Плавление при {melting_point:.0f} K (s → l)"
            )

        if boiling_point is not None:
            transition_lines.append(f"    • Кипение при {boiling_point:.0f} K (l → g)")

        if transition_lines:
            lines.append("  Фазовые переходы:")
            lines.extend(transition_lines)
        else:
            lines.append("  Фазовые переходы: нет")

        # Статистика использованных записей
        total_records = len(records_used)
        phase_stats = []
        for phase, phase_records in phases.items():
            phase_stats.append(f"{phase}: {len(phase_records)}")

        lines.append(
            f"  Использовано записей: {total_records} ({', '.join(phase_stats)})"
        )

        return "\n".join(lines)

    @staticmethod
    def format_source_info(
        is_yaml_cache: bool, search_stage: Optional[int] = None
    ) -> str:
        """
        Форматирует информацию об источнике данных.

        Args:
            is_yaml_cache: Были ли данные взяты из YAML-кэша
            search_stage: Стадия поиска в БД (1 или 2) если не YAML

        Returns:
            Отформатированная строка с информацией об источнике
        """
        if is_yaml_cache:
            return "⚡ Источник: YAML-кэш (мгновенный доступ)"
        elif search_stage == 1:
            return "🔍 Источник: База данных (стадия 1: формула + имя)"
        elif search_stage == 2:
            return "🔍 Источник: База данных (стадия 2: только формула)"
        else:
            return "🔍 Источник: База данных"

    @staticmethod
    def format_compound_data_table(
        formula: str, records_used: List[pd.Series], compound_names: List[str]
    ) -> str:
        """
        Форматирует таблицу данных о веществе согласно ТЗ.

        Структура:
        === Данные вещества: Al2O3 (Aluminium oxide) ===

        | Formula | FirstName       | Phase | Tmin   | Tmax   | H298     | S298  |
        | ------- | --------------- | ----- | ------ | ------ | -------- | ----- |
        | Al2O3   | Aluminium oxide | s     | 298.15 | 2327.0 | -1675840 | 50.92 |
        | Al2O3   | Aluminium oxide | l     | 2327.0 | 3000.0 | -1580000 | 125.5 |

        Args:
            formula: Химическая формула
            records_used: Список использованных записей
            compound_names: Список имен из LLM response

        Returns:
            Отформатированный раздел с таблицей данных вещества
        """
        if not records_used:
            return ""

        lines = []

        # Заголовок раздела
        name = (
            compound_names[0]
            if compound_names
            else records_used[0].get("FirstName", "Unknown")
        )
        lines.append(f"=== Данные вещества: {formula} ({name}) ===")
        lines.append("")

        # Подготавливаем данные для таблицы
        table_data = []
        headers = [
            "Formula",
            "FirstName",
            "Phase",
            "Tmin",
            "Tmax",
            "H298",
            "S298",
            "f1",
            "f2",
            "f3",
            "f4",
            "f5",
            "f6",
        ]

        for record in records_used:
            table_data.append(
                [
                    record.get("Formula", formula),
                    record.get("FirstName", name),
                    record.get("Phase", "unknown"),
                    f"{record.get('Tmin', 0):.1f}",
                    f"{record.get('Tmax', 0):.1f}",
                    f"{record.get('H298', 0):.0f}",
                    f"{record.get('S298', 0):.2f}",
                    f"{record.get('f1', 0):.6f}",
                    f"{record.get('f2', 0):.6f}",
                    f"{record.get('f3', 0):.6f}",
                    f"{record.get('f4', 0):.6f}",
                    f"{record.get('f5', 0):.6f}",
                    f"{record.get('f6', 0):.6f}",
                ]
            )

        # Форматируем таблицу
        formatted_table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            stralign="center",
            numalign="decimal",
        )

        lines.append(formatted_table)
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_compound_thermodynamic_table(
        formula: str,
        records_used: List[pd.Series],
        temperature_range_k: Tuple[float, float],
        temperature_step_k: float,
        compound_names: List[str],
    ) -> str:
        """
        Форматирует таблицу термодинамических свойств вещества (ΔH, ΔS, ΔG vs T).

        Создает таблицу с температурной зависимостью свойств вещества,
        с индикаторами смены записей из БД при переходе между температурными диапазонами.

        Структура:
        === Термодинамические свойства: H2O ===

        | T(K) | ΔH (кДж/моль) | ΔS (Дж/(моль·K)) | ΔG (кДж/моль) | Смена записи |
        |------|---------------|------------------|---------------|--------------|
        | 298  | -285.83       | 69.91            | -306.71       | запись 1     |
        | 398  | -283.12       | 74.15            | -312.54       | запись 1     |
        | 498  | -280.41       | 77.89            | -319.25       | запись 2     |

        Args:
            formula: Химическая формула
            records_used: Список использованных записей, отсортированных по температурным диапазонам
            temperature_range_k: Кортеж (T_min, T_max) в Кельвинах
            temperature_step_k: Шаг по температуре в Кельвинах
            compound_names: Список имен из LLM response

        Returns:
            Отформатированный раздел с таблицей термодинамических свойств
        """
        if not records_used:
            return ""

        import logging

        import numpy as np

        from ..core_logic.thermodynamic_engine import ThermodynamicEngine

        # Создаем временный логгер для движка
        logger = logging.getLogger(__name__)
        thermodynamic_engine = ThermodynamicEngine(logger)

        lines = []

        # Заголовок раздела
        name = (
            compound_names[0]
            if compound_names
            else records_used[0].get("FirstName", "Unknown")
        )
        lines.append(f"=== Термодинамические свойства: {formula} ===")
        lines.append("")

        T_min, T_max = temperature_range_k
        temperatures = np.arange(T_min, T_max + temperature_step_k, temperature_step_k)

        # Подготавливаем данные для таблицы
        table_data = []
        headers = [
            "T(K)",
            "ΔH (кДж/моль)",
            "ΔS (Дж/(моль·K))",
            "ΔG (кДж/моль)",
            "Смена записи",
        ]

        for i, T in enumerate(temperatures):
            # Находим подходящую запись для текущей температуры
            current_record = None
            record_index = 0

            for j, record in enumerate(records_used):
                tmin = record.get("Tmin", float("-inf"))
                tmax = record.get("Tmax", float("inf"))
                if tmin <= T <= tmax:
                    current_record = record
                    record_index = j + 1  # Нумерация с 1 для пользователя
                    break

            # Если запись не найдена, ищем последнюю запись с максимальным Tmax
            # и используем экстраполяцию
            use_extrapolation = False
            T_max_available = None

            if current_record is None:
                # Находим запись с максимальным Tmax
                max_record = max(records_used, key=lambda r: r.get("Tmax", 0))
                T_max_available = max_record.get("Tmax", 0)

                if T > T_max_available:
                    # Экстраполяция: используем последнюю запись
                    current_record = max_record
                    # Ищем индекс по rowid для корректной работы с pd.Series
                    max_rowid = (
                        max_record.get("rowid")
                        if isinstance(max_record, dict)
                        else (
                            max_record.rowid
                            if hasattr(max_record, "rowid")
                            else max_record.get("rowid", None)
                        )
                    )
                    record_index = next(
                        (
                            i + 1
                            for i, r in enumerate(records_used)
                            if (
                                r.get("rowid")
                                if isinstance(r, dict)
                                else (
                                    r.rowid
                                    if hasattr(r, "rowid")
                                    else r.get("rowid", None)
                                )
                            )
                            == max_rowid
                        ),
                        len(records_used),
                    )
                    use_extrapolation = True
                else:
                    # Температура ниже минимума - используем первую запись
                    current_record = records_used[0]
                    record_index = 1

            # Рассчитываем свойства для этой температуры
            try:
                if use_extrapolation and T_max_available:
                    # Используем экстраполяцию
                    properties = (
                        thermodynamic_engine.calculate_properties_with_extrapolation(
                            current_record, T, T_max_available
                        )
                    )
                else:
                    properties = thermodynamic_engine.calculate_properties(
                        current_record, T
                    )
                delta_H = properties["enthalpy"] / 1000  # Конвертируем в кДж/моль
                delta_S = properties["entropy"]
                delta_G = properties["gibbs_energy"] / 1000  # Конвертируем в кДж/моль

                # Определяем, нужно ли показывать смену записи
                record_change = f"запись {record_index}"

                # Проверяем, изменилась ли запись по сравнению с предыдущим шагом
                if i > 0:
                    prev_T = temperatures[i - 1]
                    prev_record = None
                    prev_record_index = 0

                    for j, record in enumerate(records_used):
                        tmin = record.get("Tmin", float("-inf"))
                        tmax = record.get("Tmax", float("inf"))
                        if tmin <= prev_T <= tmax:
                            prev_record = record
                            prev_record_index = j + 1
                            break

                    if prev_record is None:
                        prev_record = records_used[-1]
                        prev_record_index = len(records_used)

                    # Если запись не изменилась, оставляем ячейку пустой
                    if prev_record_index == record_index:
                        record_change = ""

                table_data.append(
                    [
                        f"{T:.0f}",
                        f"{delta_H:+.2f}",
                        f"{delta_S:+.2f}",
                        f"{delta_G:+.2f}",
                        record_change,
                    ]
                )

            except Exception as e:
                # В случае ошибки расчета, добавляем строку с прочерками
                table_data.append([f"{T:.0f}", "—", "—", "—", f"запись {record_index}"])

        # Форматируем таблицу
        formatted_table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            stralign="center",
            numalign="decimal",
        )

        lines.append(formatted_table)
        lines.append("")

        return "\n".join(lines)
