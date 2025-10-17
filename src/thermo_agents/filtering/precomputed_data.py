"""
Предвычисленные данные для фазовых переходов и термодинамических констант.

Этот модуль содержит предвычисленные значения для распространенных соединений
и фазовых переходов для ускорения расчетов и минимизации повторных вычислений.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from functools import lru_cache

from .constants import (
    PRECOMPUTED_PHASE_TRANSITIONS,
    SOLID_PHASE_MAX_TEMP,
    LIQUID_PHASE_MIN_TEMP,
    LIQUID_PHASE_MAX_TEMP,
    GAS_PHASE_MIN_TEMP,
)


@dataclass
class PhaseTransitionData:
    """Данные о фазовых переходах соединения."""
    formula: str
    melting_point: Optional[float]  # K
    boiling_point: Optional[float]  # K
    sublimation_point: Optional[float]  # K
    decomposition_point: Optional[float]  # K
    phase_stability: Dict[str, Tuple[float, float]]  # фаза -> (tmin, tmax)


class PrecomputedDataManager:
    """
    Менеджер предвычисленных данных для высокопроизводительных расчетов.

    Предоставляет быстрый доступ к предвычисленным термодинамическим данным
    и фазовым переходам для распространенных соединений.
    """

    def __init__(self):
        # Инициализация предвычисленных данных
        self._phase_transitions = self._initialize_phase_transitions()
        self._compound_properties = self._initialize_compound_properties()
        self._temperature_phase_map = self._initialize_temperature_phase_map()

    def _initialize_phase_transitions(self) -> Dict[str, PhaseTransitionData]:
        """Инициализировать предвычисленные данные о фазовых переходах."""
        transitions = {}

        # Вода и ее изотопы
        transitions["H2O"] = PhaseTransitionData(
            formula="H2O",
            melting_point=273.15,  # 0°C
            boiling_point=373.15,  # 100°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 273.15),      # твердое от 0K до 0°C
                "l": (273.15, 373.15),   # жидкое от 0°C до 100°C
                "g": (373.15, 2000.0),   # газообразное от 100°C
            }
        )

        # Аммиак
        transitions["NH3"] = PhaseTransitionData(
            formula="NH3",
            melting_point=195.4,   # -77.75°C
            boiling_point=239.82,  # -33.34°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 195.4),
                "l": (195.4, 239.82),
                "g": (239.82, 1000.0),
            }
        )

        # Диоксид углерода
        transitions["CO2"] = PhaseTransitionData(
            formula="CO2",
            melting_point=194.65,  # -78.5°C (сублимация)
            boiling_point=None,    # Не кипит при атмосферном давлении
            sublimation_point=194.65,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 194.65),
                "g": (194.65, 2000.0),
            }
        )

        # Метан
        transitions["CH4"] = PhaseTransitionData(
            formula="CH4",
            melting_point=90.7,    # -182.45°C
            boiling_point=111.65,  # -161.5°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 90.7),
                "l": (90.7, 111.65),
                "g": (111.65, 1000.0),
            }
        )

        # Кислород
        transitions["O2"] = PhaseTransitionData(
            formula="O2",
            melting_point=54.36,   # -218.79°C
            boiling_point=90.2,    # -182.95°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 54.36),
                "l": (54.36, 90.2),
                "g": (90.2, 1000.0),
            }
        )

        # Азот
        transitions["N2"] = PhaseTransitionData(
            formula="N2",
            melting_point=63.15,   # -210°C
            boiling_point=77.36,   # -195.79°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 63.15),
                "l": (63.15, 77.36),
                "g": (77.36, 1000.0),
            }
        )

        # Водород
        transitions["H2"] = PhaseTransitionData(
            formula="H2",
            melting_point=13.99,   # -259.16°C
            boiling_point=20.28,   # -252.87°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 13.99),
                "l": (13.99, 20.28),
                "g": (20.28, 1000.0),
            }
        )

        # Хлорид водорода
        transitions["HCl"] = PhaseTransitionData(
            formula="HCl",
            melting_point=158.93,  # -114.22°C
            boiling_point=188.11,  # -85.04°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 158.93),
                "l": (158.93, 188.11),
                "g": (188.11, 1000.0),
            }
        )

        # Метанол
        transitions["CH3OH"] = PhaseTransitionData(
            formula="CH3OH",
            melting_point=175.15,  # -98°C
            boiling_point=337.33,  # 64.18°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 175.15),
                "l": (175.15, 337.33),
                "g": (337.33, 1000.0),
            }
        )

        # Этанол
        transitions["C2H5OH"] = PhaseTransitionData(
            formula="C2H5OH",
            melting_point=159.05,  # -114.1°C
            boiling_point=351.44,  # 78.29°C
            sublimation_point=None,
            decomposition_point=None,
            phase_stability={
                "s": (0.0, 159.05),
                "l": (159.05, 351.44),
                "g": (351.44, 1000.0),
            }
        )

        return transitions

    def _initialize_compound_properties(self) -> Dict[str, Dict[str, float]]:
        """Инициализировать предвычисленные свойства соединений."""
        properties = {}

        # Стандартные термодинамические свойства (H298, S298)
        properties["H2O"] = {
            "H298": -285830.0,  # J/mol (жидкая вода)
            "S298": 69.95,      # J/(mol·K)
            "Cp_solid": 37.5,   # J/(mol·K) (лед)
            "Cp_liquid": 75.3,  # J/(mol·K) (вода)
            "Cp_gas": 33.6,     # J/(mol·K) (пар)
        }

        properties["CO2"] = {
            "H298": -393509.0,  # J/mol (газ)
            "S298": 213.74,     # J/(mol·K)
            "Cp_gas": 44.0,     # J/(mol·K)
        }

        properties["NH3"] = {
            "H298": -45900.0,   # J/mol (газ)
            "S298": 192.77,     # J/(mol·K)
            "Cp_gas": 35.1,     # J/(mol·K)
        }

        properties["CH4"] = {
            "H298": -74870.0,   # J/mol (газ)
            "S298": 186.25,     # J/(mol·K)
            "Cp_gas": 35.7,     # J/(mol·K)
        }

        properties["O2"] = {
            "H298": 0.0,        # J/mol (газ, стандартное состояние)
            "S298": 205.147,    # J/(mol·K)
            "Cp_gas": 29.4,     # J/(mol·K)
        }

        properties["N2"] = {
            "H298": 0.0,        # J/mol (газ, стандартное состояние)
            "S298": 191.609,    # J/(mol·K)
            "Cp_gas": 29.1,     # J/(mol·K)
        }

        properties["H2"] = {
            "H298": 0.0,        # J/mol (газ, стандартное состояние)
            "S298": 130.68,     # J/(mol·K)
            "Cp_gas": 28.8,     # J/(mol·K)
        }

        return properties

    def _initialize_temperature_phase_map(self) -> Dict[Tuple[float, float], str]:
        """Инициализировать карту температур в фазы для быстрых определений."""
        phase_map = {}

        # Определяем фазы по температурным диапазонам
        # (температура, диапазон_вокруг_температуры) -> наиболее вероятная фаза

        # Очень низкие температуры - твердая фаза
        for temp in range(0, 50, 5):  # 0K to 50K
            phase_map[(temp, 10)] = "s"

        # Низкие температуры - твердая фаза
        for temp in range(50, 200, 10):  # 50K to 200K
            phase_map[(temp, 20)] = "s"

        # Средние температуры - зависит от соединения
        for temp in range(200, 400, 20):  # 200K to 400K
            phase_map[(temp, 30)] = "l"  # Предполагаем жидкую фазу

        # Высокие температуры - газообразная фаза
        for temp in range(400, 1000, 50):  # 400K to 1000K
            phase_map[(temp, 50)] = "g"

        # Очень высокие температуры - газообразная фаза
        for temp in range(1000, 5000, 200):  # 1000K to 5000K
            phase_map[(temp, 100)] = "g"

        return phase_map

    @lru_cache(maxsize=1000)
    def get_phase_transition(self, formula: str) -> Optional[PhaseTransitionData]:
        """
        Получить предвычисленные данные о фазовых переходах.

        Args:
            formula: Химическая формула соединения

        Returns:
            Данные о фазовых переходах или None если нет предвычисленных данных
        """
        # Нормализуем формулу
        clean_formula = self._normalize_formula(formula)
        return self._phase_transitions.get(clean_formula)

    @lru_cache(maxsize=1000)
    def get_compound_properties(self, formula: str) -> Optional[Dict[str, float]]:
        """
        Получить предвычисленные свойства соединения.

        Args:
            formula: Химическая формула соединения

        Returns:
            Словарь свойств или None если нет предвычисленных данных
        """
        clean_formula = self._normalize_formula(formula)
        return self._compound_properties.get(clean_formula)

    @lru_cache(maxsize=500)
    def estimate_phase_by_temperature(
        self,
        formula: str,
        temperature: float
    ) -> Optional[str]:
        """
        Быстрая оценка фазы по температуре с использованием предвычисленных данных.

        Args:
            formula: Химическая формула соединения
            temperature: Температура в Кельвинах

        Returns:
            Предполагаемая фаза или None
        """
        # Сначала проверяем предвычисленные данные
        transition_data = self.get_phase_transition(formula)
        if transition_data:
            return self._get_phase_from_transition_data(transition_data, temperature)

        # Используем общую карту температур
        return self._get_phase_from_temperature_map(temperature)

    def _normalize_formula(self, formula: str) -> str:
        """Нормализовать химическую формулу для поиска в предвычисленных данных."""
        # Удаляем фазовые обозначения
        clean = formula.split('(')[0].strip()
        return clean.upper()

    def _get_phase_from_transition_data(
        self,
        data: PhaseTransitionData,
        temperature: float
    ) -> Optional[str]:
        """Определить фазу из предвычисленных данных о переходах."""
        for phase, (tmin, tmax) in data.phase_stability.items():
            if tmin <= temperature <= tmax:
                return phase
        return None

    def _get_phase_from_temperature_map(self, temperature: float) -> Optional[str]:
        """Определить фазу из карты температур."""
        # Ищем ближайший температурный диапазон
        for (temp, range_width), phase in self._temperature_phase_map.items():
            if abs(temperature - temp) <= range_width:
                return phase
        return None

    def get_precomputed_melting_point(self, formula: str) -> Optional[float]:
        """Получить предвычисленную точку плавления."""
        transition_data = self.get_phase_transition(formula)
        return transition_data.melting_point if transition_data else None

    def get_precomputed_boiling_point(self, formula: str) -> Optional[float]:
        """Получить предвычисленную точку кипения."""
        transition_data = self.get_phase_transition(formula)
        return transition_data.boiling_point if transition_data else None

    def is_common_compound(self, formula: str) -> bool:
        """Проверить, является ли соединение распространенным."""
        clean_formula = self._normalize_formula(formula)
        return clean_formula in self._phase_transitions

    def get_available_compounds(self) -> List[str]:
        """Получить список соединений с предвычисленными данными."""
        return list(self._phase_transitions.keys())

    def clear_cache(self) -> None:
        """Очистить кэш предвычисленных данных."""
        self.get_phase_transition.cache_clear()
        self.get_compound_properties.cache_clear()
        self.estimate_phase_by_temperature.cache_clear()


# Глобальный экземпляр для доступа к предвычисленным данным
precomputed_data_manager = PrecomputedDataManager()


def get_precomputed_phase_transition(formula: str) -> Optional[PhaseTransitionData]:
    """Удобная функция для получения предвычисленных данных о фазовых переходах."""
    return precomputed_data_manager.get_phase_transition(formula)


def get_precomputed_compound_properties(formula: str) -> Optional[Dict[str, float]]:
    """Удобная функция для получения предвычисленных свойств соединения."""
    return precomputed_data_manager.get_compound_properties(formula)


def estimate_phase_fast(formula: str, temperature: float) -> Optional[str]:
    """Быстрая оценка фазы с использованием предвычисленных данных."""
    return precomputed_data_manager.estimate_phase_by_temperature(formula, temperature)