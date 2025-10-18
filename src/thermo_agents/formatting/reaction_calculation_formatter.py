"""
Форматтер для вывода расчётов термодинамики реакций.

Поддерживает Unicode символы для химических формул и математических выражений.
"""

from typing import List, Tuple

import numpy as np

from ..calculations.thermodynamic_calculator import ThermodynamicCalculator
from ..models.extraction import ExtractedReactionParameters
from ..models.search import CompoundSearchResult, DatabaseRecord


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
            if not result.records_found:
                lines.append(f"{result.compound_formula} — ❌ НЕ НАЙДЕНО В БАЗЕ ДАННЫХ")
                lines.append("")
                continue

            record = result.records_found[0]
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
            if result.records_found:
                record = result.records_found[0]
                # Получаем коэффициент из распарсенного уравнения
                stoich = stoichiometry.get(result.compound_formula, 1)
                reactant_data.append((record, stoich))

        for result in products:
            if result.records_found:
                record = result.records_found[0]
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
