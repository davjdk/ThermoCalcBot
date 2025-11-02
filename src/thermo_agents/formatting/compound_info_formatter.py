"""
Форматирование информации о веществах для единого вывода реакции.

Включает информацию о фазах, источниках данных, температурных диапазонах,
фазовых переходах и использованных записях из БД.
"""

import pandas as pd
from typing import List, Optional, Dict, Any


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
        compound_names: List[str]
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
        name = first_record.get('FirstName') or compound_names[0] if compound_names else "Неизвестное вещество"
        lines.append(f"{formula_subscript} — {name}")

        # Собираем информацию по фазам
        phases = {}
        min_temp = float('inf')
        max_temp = float('-inf')

        for record in records_used:
            phase = record.get('Phase', 'unknown')
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(record)

            tmin = record.get('Tmin', 0)
            tmax = record.get('Tmax', 0)
            min_temp = min(min_temp, tmin)
            max_temp = max(max_temp, tmax)

        # Фазы и температурный диапазон
        phase_list = ", ".join(sorted(phases.keys()))
        lines.append(f"  Фаза: {phase_list} | T_применимости: {min_temp:.0f}-{max_temp:.0f} K")

        # H298 и S298 из первой записи
        h298 = first_record.get('H298', 0)
        s298 = first_record.get('S298', 0)
        lines.append(f"  H₂₉₈: {h298/1000:.3f} кДж/моль | S₂₉₈: {s298:.3f} Дж/(моль·K)")

        # Cp коэффициенты
        cp_coeffs = []
        for i in range(1, 7):
            coeff = first_record.get(f'f{i}', 0)
            cp_coeffs.append(f"{coeff:.6f}")
        lines.append(f"  Cp коэффициенты: [{', '.join(cp_coeffs)}]")

        # Источник данных
        reference = first_record.get('Reference', 'Неизвестно')
        reliability = first_record.get('ReliabilityClass', 0)
        lines.append(f"  Источник: {reference} (ReliabilityClass: {reliability})")

        # Информация о фазовых переходах
        transition_lines = []

        if melting_point is not None:
            transition_lines.append(f"    • Плавление при {melting_point:.0f} K (s → l)")

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

        lines.append(f"  Использовано записей: {total_records} ({', '.join(phase_stats)})")

        return "\n".join(lines)

    @staticmethod
    def format_source_info(is_yaml_cache: bool, search_stage: Optional[int] = None) -> str:
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