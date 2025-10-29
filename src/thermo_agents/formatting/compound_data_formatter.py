"""
Форматтер для вывода данных по отдельным веществам.

Использует библиотеку tabulate для табличного вывода и ThermodynamicCalculator
для расчета термодинамических свойств.
"""

from typing import Optional, Dict, Tuple, List
from tabulate import tabulate

from ..calculations.thermodynamic_calculator import (
    ThermodynamicCalculator,
    ThermodynamicTable
)
from ..models.search import DatabaseRecord, CompoundSearchResult, MultiPhaseProperties, MultiPhaseSearchResult, MultiPhaseCompoundData, PhaseSegment


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
        # Поддержка как старых, так и новых результатов поиска
        records = result.records_found if hasattr(result, 'records_found') else result.records
        if not records:
            return self._format_not_found_response(result.compound_formula if hasattr(result, 'compound_formula') else result.formula)

        record = records[0]

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

    # ==================== STAGE 5: Enhanced Multi-Phase Formatting Methods ====================

    def format_multi_phase_compound(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Optional[Tuple[float, float]] = None
    ) -> str:
        """
        Format multi-phase compound data with enhanced Stage 5 information.

        Args:
            compound_data: Multi-phase compound data
            temperature_range: Optional temperature range to highlight

        Returns:
            Formatted multi-phase compound output
        """
        lines = []

        if not compound_data.records:
            return f"❌ Нет данных для вещества"

        # Basic compound information
        first_record = compound_data.records[0]
        compound_name = first_record.name or "Неизвестное вещество"
        formula = compound_data.compound_formula

        lines.append(f"{formula} — {compound_name}")

        # Overall range information
        min_temp = min(record.Tmin for record in compound_data.records)
        max_temp = max(record.Tmax for record in compound_data.records)
        lines.append(f"  Общий диапазон: {min_temp:.0f}-{max_temp:.0f}K")

        # Phase segments table
        if compound_data.segments:
            lines.append("")
            lines.append("  Фазовые сегменты:")
            lines.append(self._format_phase_segments_table(compound_data.segments))

        # Phase transitions table
        if compound_data.transitions:
            lines.append("")
            lines.append("  Фазовые переходы:")
            lines.append(self._format_transitions_table(compound_data.transitions))

        # Records summary
        lines.append("")
        lines.append(self._format_records_summary(compound_data))

        # Temperature range information
        if temperature_range:
            lines.append("")
            if min_temp <= temperature_range[0] <= max_temp:
                lines.append(f"  ✅ Запрошенный диапазон {temperature_range[0]:.0f}-{temperature_range[1]:.0f}K покрыт")
            else:
                lines.append(f"  ⚠️  Запрошенный диапазон {temperature_range[0]:.0f}-{temperature_range[1]:.0f}K выходит за пределы данных")

        return "\n".join(lines)

    def _format_phase_segments_table(
        self,
        segments: List[PhaseSegment]
    ) -> str:
        """
        Format phase segments as a table.

        Args:
            segments: List of phase segments

        Returns:
            Formatted segments table
        """
        from tabulate import tabulate

        headers = ["Фаза", "T-диапазон (K)", "Записей", "H298 (кДж/моль)", "S298 (Дж/моль·K)"]

        table_data = []
        for segment in segments:
            phase = segment.phase
            t_range = f"{segment.T_start:.0f}-{segment.T_end:.0f}"
            records_count = len(segment.records) if hasattr(segment, 'records') else 1

            # Get H298 and S298 from the first record in segment
            if segment.records:
                h298 = segment.records[0].h298 / 1000 if segment.records[0].h298 is not None else 0.0
                s298 = segment.records[0].s298 if segment.records[0].s298 is not None else 0.0
            else:
                h298 = 0.0
                s298 = 0.0

            table_data.append([
                phase,
                t_range,
                records_count,
                f"{h298:.3f}",
                f"{s298:.3f}"
            ])

        return tabulate(table_data, headers=headers, tablefmt="grid")

    def _format_transitions_table(
        self,
        transitions: List
    ) -> str:
        """
        Format phase transitions as a table with calculation methods.

        Args:
            transitions: List of phase transitions

        Returns:
            Formatted transitions table
        """
        from tabulate import tabulate

        headers = ["Переход", "T (K)", "ΔH (кДж/моль)", "ΔS (Дж/моль·K)", "Метод", "Надёжность"]

        table_data = []
        for transition in transitions:
            from_phase = transition.from_phase
            to_phase = transition.to_phase
            temp = f"{transition.temperature:.0f}"

            # Format enthalpy with approximation symbol if heuristic
            delta_h = transition.delta_H if transition.delta_H is not None else 0.0
            if transition.calculation_method == "heuristic":
                delta_h_str = f"≈{delta_h:.1f}"
            else:
                delta_h_str = f"{delta_h:.1f}"

            delta_s = transition.delta_S if transition.delta_S is not None else 0.0
            if transition.calculation_method == "heuristic":
                delta_s_str = f"≈{delta_s:.2f}"
            else:
                delta_s_str = f"{delta_s:.2f}"

            # Method description
            method_desc = {
                "calculated": "рассчитано",
                "heuristic": "эвристика",
                "experimental": "эксперимент"
            }.get(transition.calculation_method, transition.calculation_method)

            # Reliability indicator
            reliability_symbol = {
                "high": "✅",
                "medium": "⚠️",
                "low": "❌"
            }.get(transition.reliability, "❓")

            table_data.append([
                f"{from_phase}→{to_phase}",
                temp,
                delta_h_str,
                delta_s_str,
                method_desc,
                reliability_symbol
            ])

        return tabulate(table_data, headers=headers, tablefmt="grid")

    def _format_records_summary(
        self,
        compound_data: MultiPhaseCompoundData
    ) -> str:
        """
        Format summary of records usage.

        Args:
            compound_data: Multi-phase compound data

        Returns:
            Formatted records summary
        """
        lines = []

        total_records = len(compound_data.records)
        total_segments = len(compound_data.segments)
        total_transitions = len(compound_data.transitions)

        lines.append(f"  Всего записей: {total_records}")
        lines.append(f"  Сегментов: {total_segments}")
        lines.append(f"  Фазовых переходов: {total_transitions}")

        # Phase distribution
        phases = set()
        for segment in compound_data.segments:
            phases.add(segment.phase)

        if phases:
            phase_names = {
                "s": "твёрдая",
                "l": "жидкая",
                "g": "газовая",
                "aq": "водный раствор"
            }
            phases_russian = [phase_names.get(p, p) for p in sorted(phases)]
            lines.append(f"  Фазы: {', '.join(phases_russian)}")

        # Calculation methods for transitions
        if compound_data.transitions:
            methods = set()
            for transition in compound_data.transitions:
                methods.add(transition.calculation_method)

            method_names = {
                "calculated": "рассчитанные",
                "heuristic": "эвристические",
                "experimental": "экспериментальные"
            }
            methods_russian = [method_names.get(m, m) for m in sorted(methods)]
            lines.append(f"  Методы расчёта переходов: {', '.join(methods_russian)}")

            # Warning about heuristic methods
            if "heuristic" in methods:
                lines.append("  ⚠️  Некоторые переходы рассчитаны эвристически")

        return "\n".join(lines)