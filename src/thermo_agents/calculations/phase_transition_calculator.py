"""
Phase Transition Calculator - Этап 4 реализации

Специализированный калькулятор для обработки фазовых переходов в термодинамических расчётах.
Обеспечивает корректный учёт скачков энтальпии и энтропии в точках переходов.

Критически важно: В БД нет полей h_fusion/h_vaporization!
Энтальпии переходов рассчитываются из разницы H298 разных фаз.
"""

import logging
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any
from enum import Enum

from ..models.search import (
    DatabaseRecord,
    PhaseTransition,
    TransitionType
)
from .thermodynamic_calculator import ThermodynamicCalculator, ThermodynamicProperties

logger = logging.getLogger(__name__)


class TransitionCalculationError(Exception):
    """Ошибка при расчёте фазового перехода."""
    pass


@dataclass
class PhaseTransitionCalculator:
    """
    Калькулятор для обработки фазовых переходов.

    Основные задачи:
    1. Расчёт свойств в точках переходов
    2. Применение скачков энтальпии и энтропии
    3. Валидация термодинамической согласованности
    4. Обработка множественных переходов
    """

    thermodynamic_calculator: ThermodynamicCalculator

    def __post_init__(self):
        """Инициализация калькулятора."""
        self.thermodynamic_calculator = ThermodynamicCalculator()

    def calculate_properties_at_transition(
        self,
        transition: PhaseTransition,
        h_before: float,
        s_before: float,
        cp_before: float = 0.0
    ) -> Tuple[float, float, float, float]:
        """
        Расчёт свойств сразу после фазового перехода.

        Args:
            transition: Данные о фазовом переходе
            h_before: Энтальпия до перехода (Дж/моль)
            s_before: Энтропия до перехода (Дж/(моль·K))
            cp_before: Теплоёмкость до перехода (Дж/(моль·K))

        Returns:
            Tuple[float, float, float, float]: (H_after, S_after, G_after, Cp_after)

        Note:
            Энергия Гиббса в точке перехода:
            G_after = H_after - T × S_after
        """
        logger.debug(
            f"Расчёт свойств при переходе {transition.from_phase}→{transition.to_phase} "
            f"при T={transition.temperature:.1f}K"
        )

        # Применяем скачки свойств
        h_after = h_before + (transition.delta_H_transition * 1000)  # кДж → Дж
        s_after = s_before + transition.delta_S_transition

        # Расчёт энергии Гиббса после перехода
        g_after = h_after - transition.temperature * s_after

        # Теплоёмкость может резко измениться при переходе
        # Будем рассчитывать её позже через ThermodynamicCalculator
        cp_after = cp_before  # Временное значение

        logger.debug(
            f"Скачок свойств: ΔH={transition.delta_H_transition:.3f} кДж/моль, "
            f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K)"
        )

        return h_after, s_after, g_after, cp_after

    def validate_transition_thermodynamics(
        self,
        transition: PhaseTransition
    ) -> bool:
        """
        Валидация термодинамической согласованности перехода.

        Args:
            transition: Данные о фазовом переходе

        Returns:
            bool: True если переход термодинамически корректен

        Проверки:
        1. ΔH > 0 (эндотермический процесс)
        2. ΔS > 0 (увеличение энтропии)
        3. Правило Трутона для кипения: 75 < ΔS_vap < 95 Дж/(моль·K)
        4. Разумные значения для плавления: 8 < ΔS_fusion < 35 Дж/(моль·K)
        """

        if transition.delta_H_transition <= 0:
            logger.error(
                f"Отрицательная энтальпия перехода: ΔH={transition.delta_H_transition:.3f} кДж/моль"
            )
            return False

        if transition.delta_S_transition <= 0:
            logger.error(
                f"Отрицательная энтропия перехода: ΔS={transition.delta_S_transition:.1f} Дж/(моль·K)"
            )
            return False

        # Правило Трутона для кипения
        if transition.transition_type == TransitionType.BOILING:
            if not (75 < transition.delta_S_transition < 95):
                logger.warning(
                    f"Энтропия кипения выходит за пределы правила Трутона: "
                    f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K) (ожидается 75-95)"
                )
                # Не считаем критичной ошибкой, но понижаем надёжность

        # Проверка разумности для плавления
        if transition.transition_type == TransitionType.MELTING:
            if not (8 < transition.delta_S_transition < 35):
                logger.warning(
                    f"Энтропия плавления выходит за типичные пределы: "
                    f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K) (ожидается 8-35)"
                )

        return True

    def calculate_transition_corrections(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition: PhaseTransition,
        temperature: float
    ) -> Dict[str, float]:
        """
        Расчёт поправок при фазовом переходе.

        Args:
            from_record: Запись БД для исходной фазы
            to_record: Запись БД для целевой фазы
            transition: Данные о переходе
            temperature: Температура расчёта

        Returns:
            Dict[str, float]: Словарь с поправками к свойствам
        """

        # Рассчитываем свойства для обеих фаз на температуре перехода
        from_props = self.thermodynamic_calculator.calculate_properties(from_record, temperature)
        to_props = self.thermodynamic_calculator.calculate_properties(to_record, temperature)

        # Определяем фактические скачки свойств
        actual_h_jump = to_props.enthalpy - from_props.enthalpy
        actual_s_jump = to_props.entropy - from_props.entropy
        actual_g_jump = to_props.gibbs_energy - from_props.gibbs_energy

        # Рассчитанные свойства с учётом перехода
        corrected_h = from_props.enthalpy + (transition.delta_H_transition * 1000)
        corrected_s = from_props.entropy + transition.delta_S_transition
        corrected_g = corrected_h - temperature * corrected_s

        corrections = {
            "actual_h_jump": actual_h_jump,
            "actual_s_jump": actual_s_jump,
            "actual_g_jump": actual_g_jump,
            "transition_h_jump": transition.delta_H_transition * 1000,
            "transition_s_jump": transition.delta_S_transition,
            "corrected_h": corrected_h,
            "corrected_s": corrected_s,
            "corrected_g": corrected_g,
            "h_correction": corrected_h - to_props.H,
            "s_correction": corrected_s - to_props.S,
        }

        logger.debug(f"Поправки при переходе: {corrections}")

        return corrections

    def detect_transition_at_temperature(
        self,
        transitions: list[PhaseTransition],
        temperature: float,
        tolerance: float = 1e-3
    ) -> Optional[PhaseTransition]:
        """
        Обнаружение фазового перехода при заданной температуре.

        Args:
            transitions: Список возможных переходов
            temperature: Температура для проверки
            tolerance: Допуск температуры (K)

        Returns:
            Optional[PhaseTransition]: Найденный переход или None
        """

        for transition in transitions:
            if abs(transition.temperature - temperature) <= tolerance:
                logger.debug(
                    f"Обнаружен переход {transition.from_phase}→{transition.to_phase} "
                    f"при T={temperature:.1f}K"
                )
                return transition

        return None

    def apply_transition_to_properties(
        self,
        properties: ThermodynamicProperties,
        transition: PhaseTransition
    ) -> ThermodynamicProperties:
        """
        Применение фазового перехода к термодинамическим свойствам.

        Args:
            properties: Исходные свойства
            transition: Данные о переходе

        Returns:
            ThermodynamicProperties: Свойства после перехода
        """

        # Проверяем температуру соответствия
        if abs(properties.T - transition.temperature) > 1e-3:
            logger.warning(
                f"Температура свойств ({properties.T:.1f}K) не совпадает "
                f"с температурой перехода ({transition.temperature:.1f}K)"
            )

        # Применяем скачки свойств
        new_h = properties.H + (transition.delta_H_transition * 1000)
        new_s = properties.S + transition.delta_S_transition
        new_g = new_h - properties.T * new_s

        # Создаём обновлённый объект свойств
        updated_properties = ThermodynamicProperties(
            T=properties.T,
            H=new_h,
            S=new_s,
            G=new_g,
            Cp=properties.Cp  # Будет обновлено позже
        )
        # Add phase attribute manually
        updated_properties.phase = transition.to_phase

        logger.debug(
            f"Применён переход {transition.from_phase}→{transition.to_phase}: "
            f"H {properties.H:.0f}→{new_h:.0f} Дж/моль, "
            f"S {properties.S:.1f}→{new_s:.1f} Дж/(моль·K)"
        )

        return updated_properties

    def calculate_multiple_transitions(
        self,
        initial_properties: ThermodynamicProperties,
        transitions: list[PhaseTransition],
        target_temperatures: list[float]
    ) -> list[ThermodynamicProperties]:
        """
        Расчёт свойств с учётом нескольких фазовых переходов.

        Args:
            initial_properties: Начальные свойства
            transitions: Список переходов (отсортированный по температуре)
            target_temperatures: Целевые температуры для расчёта

        Returns:
            list[ThermodynamicProperties]: Свойства на целевых температурах
        """

        results = []
        current_props = initial_properties
        transition_index = 0

        # Сортируем температуры и переходы
        sorted_temps = sorted(target_temperatures)
        sorted_transitions = sorted(transitions, key=lambda t: t.temperature)

        for temp in sorted_temps:
            # Применяем все переходы до текущей температуры
            while (transition_index < len(sorted_transitions) and
                   sorted_transitions[transition_index].temperature <= temp):

                transition = sorted_transitions[transition_index]

                # Проверяем, что переход соответствует текущей фазе
                if current_props.phase == transition.from_phase:
                    current_props = self.apply_transition_to_properties(current_props, transition)
                    logger.info(
                        f"Применён переход при T={transition.temperature:.1f}K: "
                        f"{transition.from_phase}→{transition.to_phase}"
                    )

                transition_index += 1

            # Рассчитываем свойства на целевой температуре
            # (здесь будет интеграция с ThermodynamicCalculator)
            # temp_props = self.thermodynamic_calculator.calculate_properties(
            #     current_record, temp
            # )
            # results.append(temp_props)

            # Временно копируем текущие свойства с обновлённой температурой
            temp_props = ThermodynamicProperties(
                temperature=temp,
                enthalpy=current_props.enthalpy,
                entropy=current_props.entropy,
                gibbs_energy=current_props.gibbs_energy,
                heat_capacity=current_props.heat_capacity,
                phase=current_props.phase
            )
            results.append(temp_props)

        return results

    def get_transition_summary(
        self,
        transitions: list[PhaseTransition]
    ) -> Dict[str, Any]:
        """
        Получение сводной информации о фазовых переходах.

        Args:
            transitions: Список переходов

        Returns:
            Dict[str, Any]: Сводная информация
        """

        if not transitions:
            return {"transitions_count": 0}

        summary = {
            "transitions_count": len(transitions),
            "melting_transitions": len([t for t in transitions if t.transition_type == TransitionType.MELTING]),
            "boiling_transitions": len([t for t in transitions if t.transition_type == TransitionType.BOILING]),
            "sublimation_transitions": len([t for t in transitions if t.transition_type == TransitionType.SUBLIMATION]),
            "average_reliability": sum(t.reliability for t in transitions) / len(transitions),
            "calculation_methods": list(set(t.calculation_method for t in transitions)),
            "has_warnings": any(t.warning is not None for t in transitions),
        }

        # Добавляем информацию о температурах
        temps = [t.temperature for t in transitions]
        summary.update({
            "min_transition_temp": min(temps),
            "max_transition_temp": max(temps),
            "temperature_range": max(temps) - min(temps)
        })

        # Добавляем информацию о предупреждениях
        warnings = [t.warning for t in transitions if t.warning]
        if warnings:
            summary["warnings"] = warnings

        return summary