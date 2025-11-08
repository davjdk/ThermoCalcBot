"""
Единый форматтер для вывода результатов расчета реакции.

Объединяет всю информацию о реакции и результатах расчета в единый
красиво отформатированный вывод с использованием Unicode символов.
"""

from typing import Any, Dict, List, Optional

import pandas as pd

from ..models.extraction import ExtractedReactionParameters
from .compound_info_formatter import CompoundInfoFormatter
from .interpretation_formatter import InterpretationFormatter
from .table_formatter import TableFormatter


class UnifiedReactionFormatter:
    """
    Единый форматтер для вывода результатов расчета реакции.
    """

    def __init__(
        self,
        compound_info_formatter: CompoundInfoFormatter,
        table_formatter: TableFormatter,
        interpretation_formatter: InterpretationFormatter,
    ):
        self.compound_info = compound_info_formatter
        self.table_formatter = table_formatter
        self.interpretation = interpretation_formatter

    @staticmethod
    def convert_to_subscript(formula: str) -> str:
        """
        Конвертирует цифры в формуле в подстрочные индексы.
        """
        subscript_map = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
        return formula.translate(subscript_map)

    def format_reaction_result(
        self,
        params: ExtractedReactionParameters,
        df_result: pd.DataFrame,
        compounds_metadata: Dict[str, Any],
    ) -> str:
        """
        Форматирует полный результат расчета реакции.

        Структура вывода:

        ═══════════════════════════════════════════════════════════════════
        ⚗️ Термодинамический расчёт реакции
        ═══════════════════════════════════════════════════════════════════

        Уравнение реакции: {balanced_equation}

        Метод расчёта:
        [описание формул Шомейта]

        Данные веществ:
        {compound_info для каждого вещества}

        Результаты расчёта:
        {таблица с ΔH, ΔS, ΔG, ln(K), K}

        Шаг по температуре: 100 K
        Расчёты выполнены с использованием уравнений Шомейта

        Интерпретация результатов:
        {анализ спонтанности при разных T}

        ═══════════════════════════════════════════════════════════════════

        Args:
            params: Параметры из LLM
            df_result: DataFrame с результатами (T, ΔH, ΔS, ΔG, ln(K), K)
            compounds_metadata: {
                formula: {
                    'records_used': [список записей],
                    'melting_point': float,
                    'boiling_point': float,
                    'phase_transitions': [список переходов],
                    'is_yaml_cache': bool,
                    'search_stage': int
                }
            }

        Returns:
            Отформатированная строка для вывода пользователю
        """
        lines = []

        # Заголовок
        lines.append(
            "══════════════════════════════════════════════════════════════════"
        )
        lines.append("⚗️ Термодинамический расчёт реакции")
        lines.append(
            "══════════════════════════════════════════════════════════════════"
        )
        lines.append("")

        # Уравнение реакции
        equation_formatted = self._format_equation(params.balanced_equation)
        lines.append(f"Уравнение реакции: {equation_formatted}")
        lines.append("")

        # Метод расчёта
        lines.append("Метод расчёта:")
        lines.append(self._format_calculation_method())
        lines.append("")

        # Данные веществ
        all_compounds = params.all_compounds
        compound_names = getattr(params, "compound_names", {})

        for formula in all_compounds:
            names = compound_names.get(formula, []) if compound_names else []
            metadata = compounds_metadata.get(formula, {})

            # Добавляем таблицу данных вещества
            compound_table = self.compound_info.format_compound_data_table(
                formula=formula,
                records_used=metadata.get("records_used", []),
                compound_names=names,
            )

            if compound_table:
                lines.append(compound_table)

            # Добавляем таблицу термодинамических свойств вещества
            # Используем расширенный диапазон 298-2500K для полноты картины
            thermodynamic_table = (
                self.compound_info.format_compound_thermodynamic_table(
                    formula=formula,
                    records_used=metadata.get("records_used", []),
                    temperature_range_k=(298.0, 2500.0),
                    temperature_step_k=params.temperature_step_k,
                    compound_names=names,
                )
            )

            if thermodynamic_table:
                lines.append(thermodynamic_table)

        # Добавляем информацию о веществах в текстовом формате
        lines.append("Данные веществ:")
        lines.append("")

        for formula in all_compounds:
            names = compound_names.get(formula, []) if compound_names else []
            metadata = compounds_metadata.get(formula, {})

            # Форматируем информацию о веществе
            compound_info = self.compound_info.format_compound(
                formula=formula,
                records_used=metadata.get("records_used", []),
                melting_point=metadata.get("melting_point"),
                boiling_point=metadata.get("boiling_point"),
                compound_names=names,
            )

            # Добавляем информацию об источнике данных
            source_info = self.compound_info.format_source_info(
                is_yaml_cache=metadata.get("is_yaml_cache", False),
                search_stage=metadata.get("search_stage"),
            )
            compound_info = compound_info.replace(
                "  Источник:", f"  {source_info}\n  Источник:"
            )

            lines.append(compound_info)
            lines.append("")

        # Результаты расчёта
        lines.append("Результаты расчёта:")
        lines.append("")

        # Собираем информацию о фазовых переходах
        phase_transitions = {}
        for formula, metadata in compounds_metadata.items():
            transitions = metadata.get("phase_transitions", [])
            if transitions:
                phase_transitions[formula] = transitions

        # Форматируем таблицу результатов
        table_output = self.table_formatter.format_reaction_table(
            df_result, phase_transitions
        )
        lines.append(table_output)
        lines.append("")

        # Техническая информация о расчете
        temp_range = f"{df_result['T'].min():.0f}-{df_result['T'].max():.0f}"
        lines.append(f"Диапазон температур: {temp_range} K")
        lines.append("Шаг по температуре: 100 K")
        lines.append("Расчёты выполнены с использованием уравнений Шомейта")
        lines.append("")

        # Интерпретация результатов
        interpretation_output = self.interpretation.format_interpretation(
            df_result, params
        )
        lines.append(interpretation_output)
        lines.append("")

        # Технические рекомендации
        tech_recommendations = self.interpretation.format_technical_recommendations(
            df_result, params
        )
        lines.append(tech_recommendations)

        # Финальная линия
        lines.append(
            "══════════════════════════════════════════════════════════════════"
        )

        return "\n".join(lines)

    def _format_equation(self, equation: str) -> str:
        """
        Форматирование уравнения с Unicode символами.

        Args:
            equation: Строка с уравнением реакции

        Returns:
            Отформатированное уравнение с Unicode
        """
        # Заменяем стрелки на Unicode символы
        formatted = (
            equation.replace("->", " → ").replace("=>", " ⇌ ").replace("=", " → ")
        )

        # Конвертируем цифры в подстрочные индексы
        return self.convert_to_subscript(formatted)

    def _format_calculation_method(self) -> str:
        """
        Описание метода расчёта с математическими формулами.

        Returns:
            Отформатированное описание метода
        """
        return """1. Энтальпия реакции: ΔH(T) = Σνᵢ·Hᵢ(T) (продукты) - Σνⱼ·Hⱼ(T) (реагенты)
2. Энтропия реакции: ΔS(T) = Σνᵢ·Sᵢ(T) (продукты) - Σνⱼ·Sⱼ(T) (реагенты)
3. Энергия Гиббса: ΔG(T) = ΔH(T) - T·ΔS(T)
4. Константа равновесия: ln(K) = -ΔG(T)/(R·T), где R = 8.314 Дж/(моль·K)

Где термодинамические функции рассчитываются по уравнениям Шомейта:
  H(T) = H₂₉₈ + ∫₂₉₈ᵀ Cp(T)dT
  S(T) = S₂₉₈ + ∫₂₉₈ᵀ [Cp(T)/T]dT
  Cp(T) = f₁ + f₂·T/1000 + f₃·T⁻²·10⁵ + f₄·T²/10⁶ + f₅·T⁻³·10³ + f₆·T³·10⁻⁹"""

    def format_brief_result(
        self,
        params: ExtractedReactionParameters,
        df_result: pd.DataFrame,
        compounds_metadata: Dict[str, Any],
    ) -> str:
        """
        Форматирует краткий результат расчета (ключевые точки только).

        Args:
            params: Параметры из LLM
            df_result: DataFrame с результатами
            compounds_metadata: Метаданные о веществах

        Returns:
            Краткий отформатированный вывод
        """
        lines = []

        # Заголовок
        lines.append("⚗️ Термодинамический расчёт реакции (кратко)")
        lines.append("")

        # Уравнение реакции
        equation_formatted = self._format_equation(params.balanced_equation)
        lines.append(f"Уравнение: {equation_formatted}")
        lines.append("")

        # Ключевые температуры
        key_temps = self.interpretation.get_key_temperatures(df_result)
        lines.append("Ключевые точки:")

        for T, data in key_temps[:3]:  # Только первые 3 точки
            delta_G = data["delta_G"] / 1000  # кДж/моль
            K = data["K"]
            K_formatted = self.interpretation.format_equilibrium_constant(K)

            spontaneity = "спонтанная" if delta_G < 0 else "неспонтанная"
            lines.append(
                f"  {T:.0f}K: ΔG° = {delta_G:+.2f} кДж/моль, K = {K_formatted} ({spontaneity})"
            )

        # Температура инверсии
        T_inversion = self.interpretation.find_inversion_temperature(df_result)
        if T_inversion is not None:
            lines.append(f"  🎯 T инверсии: ~{T_inversion:.0f}K")

        lines.append("")

        # Практическая рекомендация
        ranges = self.interpretation.analyze_spontaneity_ranges(df_result)
        if "spontaneous" in ranges:
            T_min, _ = ranges["spontaneous"]
            lines.append(f"✅ Рекомендуемая температура: выше {T_min:.0f}K")
        else:
            lines.append("❌ Реакция термодинамически невыгодна во всем диапазоне")

        return "\n".join(lines)

    def format_error_message(self, error_message: str) -> str:
        """
        Форматирует сообщение об ошибке расчета.

        Args:
            error_message: Текст ошибки

        Returns:
            Отформатированное сообщение об ошибке
        """
        lines = [
            "══════════════════════════════════════════════════════════════════",
            "❌ Ошибка расчета термодинамики реакции",
            "══════════════════════════════════════════════════════════════════",
            "",
            f"Описание: {error_message}",
            "",
            "Возможные решения:",
            "  • Проверьте правильность химических формул",
            "  • Убедитесь, что все вещества присутствуют в базе данных",
            "  • Проверьте баланс атомов в уравнении реакции",
            "",
            "Если проблема persists, обратитесь к документации или системе поддержки.",
            "══════════════════════════════════════════════════════════════════",
        ]

        return "\n".join(lines)
