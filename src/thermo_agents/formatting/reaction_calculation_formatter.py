"""
Форматтер для вывода расчётов термодинамики реакций.

Поддерживает Unicode символы для химических формул и математических выражений.
"""

from typing import List, Tuple, Dict, Optional

import numpy as np

from ..calculations.thermodynamic_calculator import ThermodynamicCalculator
from ..models.extraction import ExtractedReactionParameters
from ..models.search import CompoundSearchResult, DatabaseRecord, MultiPhaseProperties, MultiPhaseSearchResult
from ..models.aggregation import MultiPhaseReactionData
from ..models.search import PhaseTransition


class ReactionCalculationFormatter:
    """Форматтер для вывода расчётов термодинамики реакций."""

    def __init__(self, calculator: ThermodynamicCalculator):
        """
        Инициализация форматтера.

        Args:
            calculator: Экземпляр ThermodynamicCalculator для расчетов
        """
        self.calculator = calculator

    def format_response(
        self,
        params: ExtractedReactionParameters,
        reactants: List[CompoundSearchResult],
        products: List[CompoundSearchResult],
        step_k: int = 100,
    ) -> str:
        """
        Генерация полного ответа для расчёта реакции.

        Args:
            params: Извлеченные параметры реакции
            reactants: Результаты поиска реагентов
            products: Результаты поиска продуктов
            step_k: Шаг по температуре

        Returns:
            Отформатированный текстовый ответ
        """
        lines = []

        # Заголовок
        lines.append("⚗️ Термодинамический расчёт реакции")
        lines.append("")

        # Уравнение реакции
        formatted_equation = self._format_equation(params.balanced_equation)
        lines.append(f"Уравнение реакции: {formatted_equation}")
        lines.append("")

        # Метод расчёта
        lines.append("Метод расчёта:")
        lines.append(self._format_calculation_method())
        lines.append("")

        # Данные веществ
        lines.append("Данные веществ:")
        lines.append(self._format_substances_data(reactants, products))
        lines.append("")

        # Результаты расчёта
        lines.append("Результаты расчёта:")
        T_values = np.arange(
            params.temperature_range_k[0],
            params.temperature_range_k[1] + step_k,
            step_k,
        )

        results = self._format_results(params, reactants, products, T_values)
        if results:
            lines.append(results)
        else:
            lines.append(
                "❌ Не удалось рассчитать свойства реакции (проверьте доступность данных)"
            )

        lines.append("")
        lines.append(f"Шаг по температуре: {step_k} K")
        lines.append("Расчёты выполнены с использованием уравнений Шомейта")

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
            equation.replace("->", " → ").replace("=>", " ⇄ ").replace("=", " → ")
        )

        # Карта подстрочных индексов
        subscript_map = {
            "0": "₀",
            "1": "₁",
            "2": "₂",
            "3": "₃",
            "4": "₄",
            "5": "₅",
            "6": "₆",
            "7": "₇",
            "8": "₈",
            "9": "₉",
        }

        # Преобразуем цифры в формулах в подстрочные индексы
        result = []
        prev_char = ""
        for char in formatted:
            if char.isdigit() and (prev_char.isalpha() or prev_char == ")"):
                result.append(subscript_map.get(char, char))
            else:
                result.append(char)
            prev_char = char

        return "".join(result)

    def _format_calculation_method(self) -> str:
        """
        Описание метода расчёта с математическими формулами.

        Returns:
            Отформатированное описание метода
        """
        return """1. Энтальпия реакции: ΔH°(T) = ΣH°_продукты - ΣH°_реагенты
2. Энтропия реакции: ΔS°(T) = ΣS°_продукты - ΣS°_реагенты
3. Энергия Гиббса: ΔG°(T) = ΔH°(T) - T·ΔS°(T)

Где:
  H°(T) = H°₂₉₈ + ∫₂₉₈ᵀ Cp(T)dT
  S°(T) = S°₂₉₈ + ∫₂₉₈ᵀ [Cp(T)/T]dT
  Cp(T) = f₁ + f₂T/1000 + f₃T⁻²·10⁵ + f₄T²/10⁶ + f₅T⁻³·10³ + f₆T³·10⁻⁹"""

    def _format_substances_data(
        self,
        reactants: List[CompoundSearchResult],
        products: List[CompoundSearchResult],
    ) -> str:
        """
        Компактное представление данных веществ.

        Args:
            reactants: Результаты поиска реагентов
            products: Результаты поиска продуктов

        Returns:
            Отформатированные данные веществ
        """
        lines = []

        all_substances = list(reactants) + list(products)

        for i, result in enumerate(all_substances):
            # Поддержка как старых, так и новых результатов поиска
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if not records:
                lines.append(f"{result.compound_formula} — ❌ НЕ НАЙДЕНО В БАЗЕ ДАННЫХ")
                lines.append("")
                continue

            record = records[0]
            name = record.first_name or "Неизвестное вещество"

            lines.append(f"{record.formula} — {name}")
            lines.append(
                f"  Фаза: {record.phase} | T_применимости: {record.tmin:.0f}-{record.tmax:.0f} K"
            )
            lines.append(
                f"  H₂₉₈: {record.h298:.3f} кДж/моль | S₂₉₈: {record.s298:.3f} Дж/(моль·K)"
            )

            # Коэффициенты теплоемкости
            cp_coeffs = []
            for j in range(1, 7):
                coeff = getattr(record, f"f{j}", 0.0)
                cp_coeffs.append(f"{coeff:.6f}")
            lines.append(f"  Cp коэффициенты: [{', '.join(cp_coeffs)}]")
            lines.append("")

        return "\n".join(lines)

    def _format_results(
        self,
        params: ExtractedReactionParameters,
        reactants: List[CompoundSearchResult],
        products: List[CompoundSearchResult],
        T_values: np.ndarray,
    ) -> str:
        """
        Форматирование результатов расчёта ΔH, ΔS, ΔG.

        Args:
            params: Параметры реакции с уравнением
            reactants: Результаты поиска реагентов
            products: Результаты поиска продуктов
            T_values: Массив температур

        Returns:
            Отформатированные результаты или пустая строка при ошибке
        """
        # Извлечение стехиометрических коэффициентов из уравнения
        stoichiometry = self._parse_stoichiometry(params.balanced_equation)

        # Подготовка данных веществ
        reactant_data = []
        product_data = []

        for result in reactants:
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if records:
                record = records[0]
                # Получаем коэффициент из распарсенного уравнения
                stoich = stoichiometry.get(result.compound_formula, 1)
                reactant_data.append((record, stoich))

        for result in products:
            records = result.records_found if hasattr(result, 'records_found') else result.records
            if records:
                record = records[0]
                stoich = stoichiometry.get(result.compound_formula, 1)
                product_data.append((record, stoich))

        if not reactant_data or not product_data:
            return ""

        # Расчёт количества молей продукта для нормировки
        product_moles = sum(nu for _, nu in product_data)

        lines = []

        # Заголовок таблицы результатов
        lines.append(
            "T(K)     | ΔH°(кДж/моль) | ΔS°(Дж/(К·моль)) | ΔG°(кДж/моль) | Комментарий"
        )
        lines.append("-" * 70)

        for T in T_values:
            try:
                delta_H, delta_S, delta_G = (
                    self.calculator.calculate_reaction_properties(
                        reactant_data, product_data, T
                    )
                )

                # Нормировка на моль продукта
                delta_H_norm = delta_H / 1000 / product_moles
                delta_S_norm = delta_S / product_moles
                delta_G_norm = delta_G / 1000 / product_moles

                # Комментарий о термодинамической выгодности
                if delta_G_norm < 0:
                    comment = "Экзергоническая (⇑ спонтанная)"
                elif delta_G_norm > 0:
                    comment = "Эндергоническая (⇓ неспонтанная)"
                else:
                    comment = "Равновесие"

                line = (
                    f"{T:7.0f} | {delta_H_norm:11.2f} | "
                    f"{delta_S_norm:15.2f} | {delta_G_norm:12.2f} | {comment}"
                )
                lines.append(line)

            except ValueError as e:
                line = f"{T:7.0f} | Ошибка расчёта: {str(e)[:40]}"
                lines.append(line)

        return "\n".join(lines)

    def _parse_stoichiometry(self, equation: str) -> dict:
        """
        Парсинг стехиометрических коэффициентов из уравнения реакции.

        Args:
            equation: Уравнение реакции (например, "2 W + 4 Cl2 + O2 → 2 WOCl4")

        Returns:
            Словарь {формула: коэффициент}
        """
        import re

        stoichiometry = {}

        # Убираем стрелки и разделяем на левую и правую части
        # Поддерживаемые стрелки: →, ->, =>, =, ⇄
        equation_clean = (
            equation.replace("→", "->")
            .replace("=>", "->")
            .replace("⇄", "->")
            .replace("=", "->")
        )

        # Разбираем обе части уравнения
        parts = equation_clean.split("->")
        if len(parts) != 2:
            # Если не удалось разбить, возвращаем пустой словарь
            return stoichiometry

        all_parts = [parts[0].strip(), parts[1].strip()]  # Левая и правая части

        for part in all_parts:
            # Разбиваем по "+"
            compounds = part.split("+")

            for compound in compounds:
                compound = compound.strip()

                # Паттерн: [коэффициент] формула[(фаза)]
                # Примеры: "2 W", "WOCl4", "4 Cl2", "O2"
                match = re.match(
                    r"^(\d+(?:\.\d+)?)\s*([A-Za-z][A-Za-z0-9]*)(?:\(.*\))?$", compound
                )

                if match:
                    coeff = float(match.group(1))
                    formula = match.group(2)
                    stoichiometry[formula] = int(coeff) if coeff.is_integer() else coeff
                else:
                    # Коэффициент не указан, значит 1
                    match_no_coeff = re.match(
                        r"^([A-Za-z][A-Za-z0-9]*)(?:\(.*\))?$", compound
                    )
                    if match_no_coeff:
                        formula = match_no_coeff.group(1)
                        stoichiometry[formula] = 1

        return stoichiometry

    def _extract_stoichiometry(self, query_formula: str, record_formula: str) -> int:
        """
        Извлечение стехиометрического коэффициента из формулы.

        Упрощенная реализация - в реальной системе нужно более сложное правило.

        Args:
            query_formula: Формула из запроса (может содержать коэффициент)
            record_formula: Формула из базы данных

        Returns:
            Стехиометрический коэффициент
        """
        # Если формулы совпадают, коэффициент = 1
        if query_formula.strip() == record_formula:
            return 1

        # Пытаемся извлечь коэффициент из начала строки
        import re

        match = re.match(
            r"^(\d+)\s*" + re.escape(record_formula), query_formula.strip()
        )
        if match:
            return int(match.group(1))

        # Если не удалось извлечь, предполагаем коэффициент = 1
        return 1

    def format_simple_results(
        self,
        params: ExtractedReactionParameters,
        reactants_data: List[Tuple[DatabaseRecord, int]],
        products_data: List[Tuple[DatabaseRecord, int]],
        temperatures: List[float],
    ) -> str:
        """
        Форматирование простых результатов для заданных температур.

        Args:
            params: Параметры реакции
            reactants_data: Данные реагентов [(record, stoich), ...]
            products_data: Данные продуктов [(record, stoich), ...]
            temperatures: Список температур

        Returns:
            Отформатированные результаты
        """
        lines = [
            f"📊 Результаты реакции: {self._format_equation(params.balanced_equation)}"
        ]
        lines.append("")

        # Расчёт количества молей продукта для нормировки
        product_moles = sum(nu for _, nu in products_data)

        for T in temperatures:
            try:
                delta_H, delta_S, delta_G = (
                    self.calculator.calculate_reaction_properties(
                        reactants_data, products_data, T
                    )
                )

                # Нормировка на моль продукта
                delta_H_norm = delta_H / 1000 / product_moles
                delta_S_norm = delta_S / product_moles
                delta_G_norm = delta_G / 1000 / product_moles

                lines.append(f"{T:.0f}K:")
                lines.append(f"  ΔH° = {delta_H_norm:+.2f} кДж/моль")
                lines.append(f"  ΔS° = {delta_S_norm:+.2f} Дж/(К·моль)")
                lines.append(f"  ΔG° = {delta_G_norm:+.2f} кДж/моль")

                if delta_G_norm < 0:
                    lines.append("  → Реакция термодинамически выгодна (спонтанная)")
                elif delta_G_norm > 0:
                    lines.append(
                        "  → Реакция термодинамически невыгодна (неспонтанная)"
                    )
                else:
                    lines.append("  → Реакция в равновесии")
                lines.append("")

            except ValueError as e:
                lines.append(f"{T:.0f}K: Ошибка расчёта - {e}")
                lines.append("")

        return "\n".join(lines)

    def format_comment_column(
        self,
        T: float,
        compounds_multi_phase: Dict[str, MultiPhaseProperties]
    ) -> str:
        """
        Форматирование колонки "Комментарий" с фазовыми переходами.

        Args:
            T: Текущая температура
            compounds_multi_phase: Словарь {формула: MultiPhaseProperties}

        Returns:
            Строка комментария (пустая если нет переходов)
        """
        comments = []

        for formula, mp_result in compounds_multi_phase.items():
            # Проверить, есть ли фазовый переход при температуре T
            for transition in mp_result.phase_transitions:
                if abs(transition.temperature - T) < 1.0:  # Допуск 1K
                    comment = self._format_transition_comment(
                        formula, transition
                    )
                    comments.append(comment)

            # Проверить смену записи без изменения фазы
            for segment in mp_result.segments:
                if abs(segment.T_end - T) < 1.0:
                    if segment.is_transition_boundary:
                        continue  # Уже добавлено как переход

                    # Смена записи в той же фазе
                    phase = segment.record.phase
                    comments.append(f"{formula}: {phase}→{phase} (смена записи)")

        return "; ".join(comments) if comments else ""

    def _format_transition_comment(
        self,
        formula: str,
        transition
    ) -> str:
        """
        Форматирование комментария для фазового перехода.

        Returns:
            Строка вида "FeO: s→l (плавление, ΔH=+32 кДж/моль)"
        """
        transition_names = {
            "melting": "плавление",
            "boiling": "кипение",
            "sublimation": "сублимация"
        }

        # Преобразуем enum в строку
        transition_type = transition.transition_type.value if hasattr(transition.transition_type, 'value') else str(transition.transition_type)

        transition_name = transition_names.get(
            transition_type,
            transition_type
        )

        comment = (
            f"{formula}: {transition.from_phase}→{transition.to_phase} "
            f"({transition_name}"
        )

        if abs(transition.delta_H_transition) > 0.01:
            comment += f", ΔH={transition.delta_H_transition:+.1f} кДж/моль"

        comment += ")"

        return comment

    def format_results_table_with_transitions(
        self,
        temperatures: List[float],
        delta_H: List[float],
        delta_S: List[float],
        delta_G: List[float],
        compounds_multi_phase: Dict[str, MultiPhaseProperties]
    ) -> str:
        """
        Форматирование таблицы результатов с колонкой "Комментарий".

        Returns:
            Отформатированная таблица
        """
        from tabulate import tabulate

        # Подготовка данных
        table_data = []
        for i, T in enumerate(temperatures):
            comment = self.format_comment_column(T, compounds_multi_phase)

            row = [
                f"{T:.0f}",
                f"{delta_H[i]:.2f}",
                f"{delta_S[i]:.2f}",
                f"{delta_G[i]:.2f}",
                comment
            ]
            table_data.append(row)

        # Заголовки
        headers = [
            "T(K)",
            "ΔH°(кДж/моль)",
            "ΔS°(Дж/(К·моль))",
            "ΔG°(кДж/моль)",
            "Комментарий"
        ]

        # Форматирование
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="simple",
            stralign="right"
        )

        return table

    def format_metadata(
        self,
        compounds_multi_phase: Dict[str, MultiPhaseProperties]
    ) -> str:
        """
        Форматирование метаданных о сегментах и переходах.

        Args:
            compounds_multi_phase: Словарь {формула: MultiPhaseProperties}

        Returns:
            Строка с метаданными
        """
        lines = []

        # Подсчёт сегментов
        segments_info = []
        total_segments = 0
        for formula, mp_result in compounds_multi_phase.items():
            count = len(mp_result.segments)
            total_segments += count

            # Определить типы фаз
            phases = list(set(seg.record.phase for seg in mp_result.segments))
            phase_desc = self._describe_phases(phases)

            segments_info.append(f"{formula}({count} {phase_desc})")

        lines.append(f"Использовано сегментов расчёта: {', '.join(segments_info)}")

        # Подсчёт фазовых переходов
        total_transitions = sum(
            len(mp.phase_transitions) for mp in compounds_multi_phase.values()
        )

        if total_transitions > 0:
            # Детали переходов
            transition_details = []
            for formula, mp_result in compounds_multi_phase.items():
                if mp_result.phase_transitions:
                    transition_details.append(f"{formula}")

            lines.append(
                f"Фазовых переходов обнаружено: {total_transitions} "
                f"({', '.join(transition_details)})"
            )
        else:
            lines.append("Фазовых переходов не обнаружено")

        # Шаг по температуре
        lines.append("Шаг по температуре: 100 K (плюс точки фазовых переходов)")

        return "\n".join(lines)

    def _describe_phases(self, phases: List[str]) -> str:
        """Описание фаз (твёрдых, жидких и т.д.)."""
        phase_counts = {
            "s": "твёрдых",
            "l": "жидких",
            "g": "газовых"
        }

        descriptions = []
        for phase in phases:
            if phase in phase_counts:
                descriptions.append(phase_counts[phase])

        return " + ".join(descriptions) if descriptions else "фаз"

    # ==================== STAGE 5: Multi-Phase Formatting Methods ====================

    def format_multi_phase_reaction(
        self,
        reaction_data: MultiPhaseReactionData,
        params: ExtractedReactionParameters
    ) -> str:
        """
        Format multi-phase reaction results with complete Stage 5 information.

        Args:
            reaction_data: Multi-phase reaction calculation results
            params: Extracted reaction parameters

        Returns:
            Formatted multi-phase reaction output
        """
        lines = []

        # Header with Stage 5 indication
        lines.append("================================================================================")
        lines.append("⚗️ Термодинамический расчёт реакции (Полная многофазная логика)")
        lines.append("================================================================================")
        lines.append("")

        # Reaction equation
        formatted_equation = self._format_equation(reaction_data.balanced_equation)
        lines.append(f"Уравнение: {formatted_equation}")
        lines.append("")

        # Range information (Stage 5 key feature)
        lines.append(self._format_range_information(
            reaction_data.user_temperature_range,
            reaction_data.calculation_range
        ))

        # Information about multi-phase calculations
        lines.append("ℹ️  ИНФОРМАЦИЯ: Расчёт выполнен с использованием всех доступных данных из базы.")
        lines.append("    Это гарантирует корректность базовых термодинамических свойств (H₂₉₈, S₂₉₈)")
        lines.append("    и учёт фазовых переходов.")
        lines.append("")

        # Compound data with phase information
        lines.append("Данные веществ:")
        lines.append("--------------------------------------------------------------------------------")
        lines.append(self._format_phase_information(reaction_data.compounds_data))
        lines.append("")

        # Phase transition information (Stage 5 enhancement)
        if reaction_data.phase_changes:
            lines.append("Фазовые переходы в реакции:")
            lines.append(self._format_transition_information(reaction_data.phase_changes))
            lines.append("")

        # Calculation results table
        lines.append("Результаты расчёта:")
        if reaction_data.calculation_table:
            lines.append(self._format_multi_phase_results_table(reaction_data.calculation_table))
        else:
            lines.append("❌ Таблица результатов недоступна")

        lines.append("")

        # Statistics and metadata (Stage 5)
        lines.append("Статистика расчёта:")
        lines.append(self._format_data_usage_statistics(reaction_data))

        return "\n".join(lines)

    def _format_range_information(
        self,
        user_range: Optional[Tuple[float, float]],
        calculation_range: Tuple[float, float]
    ) -> str:
        """
        Format user requested vs calculation range information.

        Args:
            user_range: User requested temperature range
            calculation_range: Actual calculation range

        Returns:
            Formatted range information
        """
        lines = []

        if user_range:
            lines.append(f"Запрошенный диапазон: {user_range[0]:.0f}-{user_range[1]:.0f}K")

        lines.append(f"Расчётный диапазон: {calculation_range[0]:.0f}-{calculation_range[1]:.0f}K (максимальное использование базы данных)")

        # Calculate range expansion if user range is provided
        if user_range:
            user_width = user_range[1] - user_range[0]
            calc_width = calculation_range[1] - calculation_range[0]
            expansion_factor = calc_width / user_width if user_width > 0 else 1.0

            if expansion_factor > 1.1:  # More than 10% expansion
                lines.append(f"🔄 Расширение диапазона: {expansion_factor:.1f}x для полноты данных")

        # Check if includes standard conditions
        if calculation_range[0] <= 298.15 <= calculation_range[1]:
            lines.append("✅ Включены стандартные условия (298K)")

        return "\n".join(lines)

    def _format_phase_information(
        self,
        compounds_data: Dict[str, MultiPhaseCompoundData]
    ) -> str:
        """
        Format phase information for all compounds.

        Args:
            compounds_data: Dictionary of compound -> multi-phase data

        Returns:
            Formatted phase information
        """
        lines = []

        for compound, mp_data in compounds_data.items():
            if not mp_data.records:
                lines.append(f"{compound} — ❌ НЕ НАЙДЕНО В БАЗЕ ДАННЫХ")
                continue

            # Basic compound information
            first_record = mp_data.records[0]
            compound_name = first_record.name or compound

            lines.append(f"{compound} — {compound_name}")

            # Range information
            min_temp = min(record.Tmin for record in mp_data.records)
            max_temp = max(record.Tmax for record in mp_data.records)
            lines.append(f"  Общий диапазон: {min_temp:.0f}-{max_temp:.0f}K")

            # Phase transitions
            if mp_data.transitions:
                lines.append("  Фазовые переходы:")
                for transition in mp_data.transitions:
                    lines.append(self._format_single_transition(transition, "    "))
            else:
                lines.append("  Фазовых переходов: нет")

            # Used phases
            used_phases = set()
            for segment in mp_data.segments:
                used_phases.add(segment.phase)

            if used_phases:
                phase_ranges = []
                for phase in sorted(used_phases):
                    phase_segments = [seg for seg in mp_data.segments if seg.phase == phase]
                    if phase_segments:
                        seg_min = min(seg.T_start for seg in phase_segments)
                        seg_max = max(seg.T_end for seg in phase_segments)
                        phase_ranges.append(f"{phase} ({seg_min:.0f}-{seg_max:.0f}K)")

                lines.append(f"  Использованные фазы: {', '.join(phase_ranges)}")

            # Standard properties (H298, S298)
            if first_record.h298 is not None and first_record.s298 is not None:
                lines.append(f"  H₂₉₈: {first_record.h298:.3f} кДж/моль | S₂₉₈: {first_record.s298:.3f} Дж/(моль·K)")

            # Records usage
            lines.append(f"  Всего записей использовано: {len(mp_data.records)} из {len(mp_data.records)}")

            # Warnings about calculation methods
            has_approximate = any(
                transition.calculation_method == "heuristic"
                for transition in mp_data.transitions
            )
            if has_approximate:
                lines.append("  ⚠️  Примечание: Некоторые энтальпии переходов рассчитаны приближённо.")

            lines.append("")

        return "\n".join(lines)

    def _format_transition_information(
        self,
        transitions: List[Tuple[float, str, str]]
    ) -> str:
        """
        Format phase transition information with calculation methods.

        Args:
            transitions: List of (temperature, compound, transition) tuples

        Returns:
            Formatted transition information
        """
        lines = []

        for T, compound, transition_desc in transitions:
            lines.append(f"  • {compound} при {T:.0f}K: {transition_desc}")

        return "\n".join(lines)

    def _format_single_transition(
        self,
        transition: PhaseTransition,
        indent: str = ""
    ) -> str:
        """
        Format a single phase transition with calculation method and reliability.

        Args:
            transition: Phase transition data
            indent: Indentation string

        Returns:
            Formatted transition string
        """
        line = f"{indent}• {transition.from_phase}→{transition.to_phase} при {transition.temperature:.0f}K"

        # Add enthalpy if available
        if transition.delta_H is not None:
            method_symbol = "≈" if transition.calculation_method == "heuristic" else ""
            line += f", ΔH = {method_symbol}{transition.delta_H:.1f} кДж/моль"

        # Add calculation method
        method_desc = {
            "calculated": "рассчитано из H298",
            "heuristic": "эвристическая оценка",
            "experimental": "экспериментальные данные"
        }.get(transition.calculation_method, transition.calculation_method)

        line += f" ({method_desc})"

        # Add warning if low reliability
        if transition.reliability == "low":
            line += " ⚠️"

        return line

    def _format_multi_phase_results_table(
        self,
        calculation_table: List[Dict[str, any]]
    ) -> str:
        """
        Format multi-phase calculation results table.

        Args:
            calculation_table: List of calculation result dictionaries

        Returns:
            Formatted results table
        """
        from tabulate import tabulate

        headers = ["T(K)", "ΔH° (кДж/моль)", "ΔS° (Дж/К·моль)", "ΔG° (кДж/моль)", "Фаза", "Комментарий"]

        table_data = []
        for row in calculation_table:
            table_data.append([
                f"{row.get('T', 0):.0f}",
                f"{row.get('delta_H', 0):.2f}",
                f"{row.get('delta_S', 0):.2f}",
                f"{row.get('delta_G', 0):.2f}",
                row.get('phase', ''),
                row.get('comment', '')
            ])

        return tabulate(table_data, headers=headers, tablefmt="grid")

    def _format_data_usage_statistics(
        self,
        reaction_data: MultiPhaseReactionData
    ) -> str:
        """
        Format data usage statistics for the reaction.

        Args:
            reaction_data: Multi-phase reaction data

        Returns:
            Formatted statistics
        """
        lines = []

        # Basic statistics
        lines.append(f"- Всего использовано записей: {reaction_data.total_records_used}")

        # Calculate total available records
        total_available = sum(
            len(compound_data.records)
            for compound_data in reaction_data.compounds_data.values()
        )
        coverage = reaction_data.get_database_coverage_percentage()
        lines.append(f"- Покрытие базы данных: {coverage:.1f}%")

        # Phase transitions
        transition_count = reaction_data.get_phase_transition_count()
        if transition_count > 0:
            compounds_with_transitions = reaction_data.get_compounds_with_transitions()
            lines.append(f"- Фазовых переходов учтено: {transition_count} ({', '.join(compounds_with_transitions)})")

            # Count calculation methods
            calculated_count = 0
            heuristic_count = 0
            for compound_data in reaction_data.compounds_data.values():
                for transition in compound_data.transitions:
                    if transition.calculation_method == "calculated":
                        calculated_count += 1
                    elif transition.calculation_method == "heuristic":
                        heuristic_count += 1

            methods = []
            if calculated_count > 0:
                methods.append(f"{calculated_count} calculated")
            if heuristic_count > 0:
                methods.append(f"{heuristic_count} heuristic")

            if methods:
                lines.append(f"- Методы расчёта переходов: {', '.join(methods)}")
        else:
            lines.append("- Фазовых переходов учтено: 0")

        # Phases used
        if reaction_data.phases_used:
            phase_names = {
                "s": "твёрдая",
                "l": "жидкая",
                "g": "газовая"
            }
            phases_russian = [phase_names.get(p, p) for p in sorted(reaction_data.phases_used)]
            lines.append(f"- Использованные фазы: {', '.join(phases_russian)}")

        return "\n".join(lines)
