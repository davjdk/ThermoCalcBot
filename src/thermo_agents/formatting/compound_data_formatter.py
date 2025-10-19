"""
Форматтер для вывода данных по отдельным веществам.

Использует библиотеку tabulate для табличного вывода и ThermodynamicCalculator
для расчета термодинамических свойств.
"""

from typing import Optional, Dict
from tabulate import tabulate

from ..calculations.thermodynamic_calculator import (
    ThermodynamicCalculator,
    ThermodynamicTable
)
from ..models.search import DatabaseRecord, CompoundSearchResult, MultiPhaseProperties


class CompoundDataFormatter:
    """Форматтер для вывода табличных данных веществ."""

    def __init__(self, calculator: ThermodynamicCalculator):
        """
        Инициализация форматтера.

        Args:
            calculator: Экземпляр ThermodynamicCalculator для расчетов
        """
        self.calculator = calculator

    def format_response(
        self,
        result: CompoundSearchResult,
        T_min: float,
        T_max: float,
        step_k: int = 100
    ) -> str:
        """
        Генерация полного ответа для запроса данных по веществу.

        Args:
            result: Результат поиска вещества
            T_min: Минимальная температура для таблицы, K
            T_max: Максимальная температура для таблицы, K
            step_k: Шаг по температуре, K

        Returns:
            Отформатированный текстовый ответ
        """
        if not result.records_found:
            return self._format_not_found_response(result.formula)

        record = result.records_found[0]

        lines = []
        lines.append(f"📊 Термодинамические данные: {record.formula}")
        lines.append("")
        lines.append("Базовые свойства:")
        lines.append(self._format_basic_properties(record))
        lines.append("")

        try:
            table = self.calculator.generate_table(record, T_min, T_max, step_k)
            lines.append("Термодинамические свойства по температуре:")
            lines.append(self._format_thermodynamic_table(table))
        except ValueError as e:
            lines.append(f"⚠️ Ошибка генерации таблицы: {e}")

        lines.append("")
        lines.append("Примечания:")
        lines.append(f"  - Шаг по температуре: {step_k} K")
        lines.append("  - Все значения рассчитаны с использованием уравнений Шомейта")
        lines.append("  - T: температура, Cp: теплоемкость, H: энтальпия, S: энтропия, G: энергия Гиббса")

        return "\n".join(lines)

    def _format_not_found_response(self, formula: str) -> str:
        """
        Форматирование ответа для случая, когда вещество не найдено.

        Args:
            formula: Формула вещества, которое не было найдено

        Returns:
            Отформатированное сообщение об ошибке
        """
        lines = [
            f"❌ Вещество '{formula}' не найдено в базе данных",
            "",
            "Возможные причины:",
            "  - Неверная формула или название вещества",
            "  - Вещество отсутствует в термодинамической базе данных",
            "  - Неправильный формат запроса",
            "",
            "Попробуйте:",
            "  - Проверить правильность написания формулы",
            "  - Использовать альтернативное название вещества",
            "  - Указать фазовое состояние (s, l, g, aq)"
        ]

        return "\n".join(lines)

    def _format_basic_properties(self, record: DatabaseRecord) -> str:
        """
        Форматирование базовых свойств вещества.

        Args:
            record: Запись из базы данных

        Returns:
            Отформатированный текст со свойствами
        """
        props = []

        # Формула и название
        props.append(f"  Формула: {record.formula}")
        if record.first_name:
            props.append(f"  Название: {record.first_name}")
        if record.second_name:
            props.append(f"  Альтернативное название: {record.second_name}")

        # Фаза
        phase_map = {
            's': 'solid (твердое)',
            'l': 'liquid (жидкость)',
            'g': 'gas (газ)',
            'aq': 'aqueous (водный раствор)'
        }
        phase_desc = phase_map.get(record.phase, record.phase)
        props.append(f"  Фаза: {record.phase} ({phase_desc})")

        # Температурный диапазон
        props.append(f"  Температурный диапазон: {record.tmin:.0f}-{record.tmax:.0f} K")

        # Стандартные свойства
        if record.h298 is not None:
            props.append(f"  H298 (энтальпия): {record.h298:.3f} кДж/моль")
        if record.s298 is not None:
            props.append(f"  S298 (энтропия): {record.s298:.3f} Дж/(моль·K)")

        # Фазовые переходы
        props.append(f"  Точка плавления: {record.tmelt:.1f} K ({record.tmelt - 273.15:.1f}°C)")
        props.append(f"  Точка кипения: {record.tboil:.1f} K ({record.tboil - 273.15:.1f}°C)")

        # Коэффициенты теплоемкости
        cp_coeffs = []
        for i in range(1, 7):
            coeff = getattr(record, f'f{i}', 0.0)
            cp_coeffs.append(f"f{i}={coeff:.6f}")
        props.append(f"  Коэффициенты Cp: {', '.join(cp_coeffs)}")

        # Качество данных
        reliability_desc = {
            1: "Высокое",
            2: "Среднее",
            3: "Низкое"
        }
        reliability_text = reliability_desc.get(record.reliability_class, f"Класс {record.reliability_class}")
        props.append(f"  Надежность данных: {reliability_text} (класс {record.reliability_class})")

        return "\n".join(props)

    def _format_thermodynamic_table(self, table: ThermodynamicTable) -> str:
        """
        Форматирование таблицы с использованием tabulate.

        Args:
            table: Таблица термодинамических свойств

        Returns:
            Отформатированная таблица
        """
        headers = [
            "T(K)",
            "Cp\nДж/(моль·K)",
            "H\nкДж/моль",
            "S\nДж/(моль·K)",
            "G\nкДж/моль"
        ]

        table_data = []
        for props in table.properties:
            row = [
                f"{props.T:.0f}",
                f"{props.Cp:.2f}",
                f"{props.H / 1000:.2f}",
                f"{props.S:.2f}",
                f"{props.G / 1000:.2f}"
            ]
            table_data.append(row)

        # Используем grid формат для красивых таблиц
        formatted_table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            stralign="center",
            numalign="decimal"
        )

        # Добавляем легенду
        legend = (
            "\nЛегенда:\n"
            "  T - температура\n"
            "  Cp - изобарная теплоемкость\n"
            "  H - энтальпия\n"
            "  S - энтропия\n"
            "  G - энергия Гиббса"
        )

        return formatted_table + legend

    def format_simple_table(
        self,
        record: DatabaseRecord,
        T_values: list[float]
    ) -> str:
        """
        Форматирование простой таблицы для заданных температур.

        Args:
            record: Запись из базы данных
            T_values: Список температур

        Returns:
            Отформатированная таблица
        """
        lines = [f"📊 Свойства вещества {record.formula}"]
        lines.append("")

        headers = ["T(K)", "Cp(Дж/(моль·K))", "H(кДж/моль)", "S(Дж/(моль·K))", "G(кДж/моль)"]
        table_data = []

        for T in T_values:
            try:
                props = self.calculator.calculate_properties(record, T)
                row = [
                    f"{props.T:.0f}",
                    f"{props.Cp:.2f}",
                    f"{props.H / 1000:.2f}",
                    f"{props.S:.2f}",
                    f"{props.G / 1000:.2f}"
                ]
                table_data.append(row)
            except ValueError as e:
                row = [f"{T:.0f}", f"Ошибка: {e}", "-", "-", "-"]
                table_data.append(row)

        lines.append(tabulate(table_data, headers=headers, tablefmt="grid"))
        return "\n".join(lines)

    def format_compound_data_multi_phase(
        self,
        formula: str,
        compound_name: str,
        multi_phase_result: MultiPhaseProperties
    ) -> str:
        """
        Форматирование раздела "Данные веществ" для многофазного расчёта.

        Args:
            formula: Химическая формула
            compound_name: Название вещества
            multi_phase_result: Результат многофазного расчёта

        Returns:
            Отформатированная строка
        """
        lines = []
        lines.append(f"{formula} — {compound_name}")

        segment_num = 1
        for i, segment in enumerate(multi_phase_result.segments):
            # Заголовок сегмента
            lines.append("")
            lines.append(
                f"  [Сегмент {segment_num}] Фаза: {segment.record.phase} | "
                f"T_применимости: {segment.T_start:.0f}-{segment.T_end:.0f} K"
            )

            # H298 и S298
            if segment.record.is_base_record():
                lines.append(
                    f"  H₂₉₈: {segment.record.h298 / 1000:.3f} кДж/моль | "
                    f"S₂₉₈: {segment.record.s298:.3f} Дж/(моль·K)"
                )
            else:
                lines.append(
                    f"  H₂₉₈: 0.000 кДж/моль (накопленное) | "
                    f"S₂₉₈: 0.000 Дж/(моль·K) (накопленное)"
                )

            # Cp коэффициенты
            cp_coeffs = [
                segment.record.f1, segment.record.f2, segment.record.f3,
                segment.record.f4, segment.record.f5, segment.record.f6
            ]
            cp_str = ", ".join(f"{c:.3f}" for c in cp_coeffs)
            lines.append(f"  Cp коэффициенты: [{cp_str}]")

            # Дополнительная информация
            if segment.record.first_name:
                lines.append(f"  Источник: {segment.record.first_name}")
            if segment.record.reliability_class:
                reliability_desc = {1: "высокая", 2: "средняя", 3: "низкая"}
                lines.append(f"  Надёжность: {segment.record.reliability_class} ({reliability_desc.get(segment.record.reliability_class, 'неизвестная')})")

            # Фазовый переход после сегмента
            if segment.is_transition_boundary:
                # Ищем соответствующий переход
                transition_idx = i - 1  # Переход после предыдущего сегмента
                if 0 <= transition_idx < len(multi_phase_result.phase_transitions):
                    transition = multi_phase_result.phase_transitions[transition_idx]
                    lines.append("")
                    # Преобразуем enum в строку
                    transition_type = transition.transition_type.value if hasattr(transition.transition_type, 'value') else str(transition.transition_type)
                    lines.append(
                        f"  [ФАЗОВЫЙ ПЕРЕХОД при {transition.temperature:.0f}K: "
                        f"{transition.from_phase} → {transition.to_phase} ({transition_type})]"
                    )
                    if abs(transition.delta_H_transition) > 0.01:
                        lines.append(
                            f"  ΔH_{transition_type}: {transition.delta_H_transition:.2f} кДж/моль | "
                            f"ΔS_{transition_type}: {transition.delta_S_transition:.2f} Дж/(моль·K)"
                        )

            segment_num += 1

        return "\n".join(lines)