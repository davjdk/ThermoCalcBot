"""
Термодинамический калькулятор для расчета свойств веществ и реакций.

Реализует детерминированные расчеты на основе формул Шомейта
и коэффициентов из термодинамической базы данных.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple
from functools import lru_cache

from ..models.search import DatabaseRecord


@dataclass
class ThermodynamicProperties:
    """Термодинамические свойства при заданной температуре."""
    T: float  # Температура, K
    Cp: float  # Теплоёмкость, Дж/(моль·K)
    H: float  # Энтальпия, Дж/моль
    S: float  # Энтропия, Дж/(моль·K)
    G: float  # Энергия Гиббса, Дж/моль

    def to_dict(self) -> dict:
        """Преобразование в словарь с кДж для энтальпии и энергии Гиббса."""
        return {
            'T': self.T,
            'Cp': self.Cp,
            'H': self.H / 1000,  # Дж → кДж
            'S': self.S,
            'G': self.G / 1000   # Дж → кДж
        }


@dataclass
class ThermodynamicTable:
    """Таблица термодинамических свойств по диапазону температур."""
    formula: str
    phase: str
    temperature_range: Tuple[float, float]
    properties: List[ThermodynamicProperties]

    def to_dict(self) -> dict:
        """Преобразование в словарь для форматтера."""
        return {
            'formula': self.formula,
            'phase': self.phase,
            'T_range': self.temperature_range,
            'data': [prop.to_dict() for prop in self.properties]
        }


class ThermodynamicCalculator:
    """
    Детерминированный калькулятор термодинамических свойств.

    Использует формулы Шомейта для расчета теплоемкости и численное
    интегрирование для расчета энтальпии, энтропии и энергии Гиббса.
    """

    def __init__(self, num_integration_points: int = 400):
        """
        Инициализация калькулятора.

        Args:
            num_integration_points: Количество точек для численного интегрирования
        """
        self.T_REF = 298.15  # Стандартная температура, K
        self.num_integration_points = num_integration_points

    def calculate_cp(self, record: DatabaseRecord, T: float) -> float:
        """
        Расчёт теплоёмкости Cp(T) по формуле Шомейта.

        Формула:
        Cp(T) = f1 + f2*T/1000 + f3*T^(-2)*10^5 +
                f4*T^2/10^6 + f5*T^(-3)*10^3 + f6*T^3*10^(-9)

        Args:
            record: Запись из базы данных с коэффициентами f1-f6
            T: Температура, K

        Returns:
            Cp в Дж/(моль·K)
        """
        T = float(T)
        f1 = getattr(record, 'f1', 0.0)
        f2 = getattr(record, 'f2', 0.0)
        f3 = getattr(record, 'f3', 0.0)
        f4 = getattr(record, 'f4', 0.0)
        f5 = getattr(record, 'f5', 0.0)
        f6 = getattr(record, 'f6', 0.0)

        return (
            f1
            + f2 * T / 1000.0
            + f3 * 100_000.0 / (T ** 2)
            + f4 * T**2 / 1_000_000.0
            + f5 * 1_000.0 / (T ** 3)
            + f6 * T**3 * 1e-9
        )

    @lru_cache(maxsize=1000)
    def _cached_integration(
        self,
        record_id: int,
        f1: float, f2: float, f3: float, f4: float, f5: float, f6: float,
        H298: float, S298: float,
        T: float
    ) -> Tuple[float, float, float, float]:
        """
        Кэшированное численное интегрирование для (record_id, T).

        Returns:
            (Cp, H, S, G) при температуре T
        """
        # Текущая теплоёмкость
        Cp = (
            f1
            + f2 * T / 1000.0
            + f3 * 100_000.0 / (T ** 2)
            + f4 * T**2 / 1_000_000.0
            + f5 * 1_000.0 / (T ** 3)
            + f6 * T**3 * 1e-9
        )

        # Если T ≈ 298.15K, интегрирование не требуется
        if abs(T - self.T_REF) < 1e-9:
            H = H298
            S = S298
            G = H - T * S
            return (Cp, H, S, G)

        # Численное интегрирование
        T_grid = np.linspace(self.T_REF, T, self.num_integration_points)

        # Векторизованный расчет Cp для всех точек сетки
        Cp_grid = (
            f1
            + f2 * T_grid / 1000.0
            + f3 * 100_000.0 / (T_grid ** 2)
            + f4 * T_grid**2 / 1_000_000.0
            + f5 * 1_000.0 / (T_grid ** 3)
            + f6 * T_grid**3 * 1e-9
        )

        # ΔH = ∫ Cp(T) dT
        delta_H = np.trapz(Cp_grid, T_grid)

        # ΔS = ∫ Cp(T)/T dT
        delta_S = np.trapz(Cp_grid / T_grid, T_grid)

        # Финальные значения
        H = H298 + delta_H
        S = S298 + delta_S
        G = H - T * S

        return (Cp, H, S, G)

    def calculate_properties(
        self,
        record: DatabaseRecord,
        T: float
    ) -> ThermodynamicProperties:
        """
        Расчёт всех термодинамических свойств при температуре T.

        Формулы:
        - H(T) = H298 + ∫[298→T] Cp(T) dT
        - S(T) = S298 + ∫[298→T] Cp(T)/T dT
        - G(T) = H(T) - T*S(T)

        Args:
            record: Запись из базы данных
            T: Температура, K

        Returns:
            ThermodynamicProperties при температуре T

        Raises:
            ValueError: Если температура вне допустимого диапазона
        """
        # Валидация температурного диапазона
        tmin = getattr(record, 'tmin', None)
        tmax = getattr(record, 'tmax', None)
        formula = getattr(record, 'formula', 'Unknown')
        phase = getattr(record, 'phase', 'Unknown')

        if tmin and T < tmin:
            raise ValueError(
                f"T={T}K ниже минимальной температуры {tmin}K "
                f"для {formula} ({phase})"
            )
        if tmax and T > tmax:
            raise ValueError(
                f"T={T}K выше максимальной температуры {tmax}K "
                f"для {formula} ({phase})"
            )

        # Базовые значения при 298.15K
        h298 = getattr(record, 'h298', 0.0)
        s298 = getattr(record, 's298', 0.0)
        H298 = h298 * 1000.0  # кДж/моль → Дж/моль
        S298 = s298  # Дж/(моль·K)

        # Коэффициенты
        f1 = getattr(record, 'f1', 0.0)
        f2 = getattr(record, 'f2', 0.0)
        f3 = getattr(record, 'f3', 0.0)
        f4 = getattr(record, 'f4', 0.0)
        f5 = getattr(record, 'f5', 0.0)
        f6 = getattr(record, 'f6', 0.0)

        # Кэшированный расчет
        Cp, H, S, G = self._cached_integration(
            record.id if hasattr(record, 'id') else id(record),
            f1, f2, f3, f4, f5, f6,
            H298, S298,
            T
        )

        return ThermodynamicProperties(T=T, Cp=Cp, H=H, S=S, G=G)

    def generate_table(
        self,
        record: DatabaseRecord,
        T_min: float,
        T_max: float,
        step_k: int = 100
    ) -> ThermodynamicTable:
        """
        Генерация таблицы термодинамических свойств.

        Args:
            record: Запись из базы данных
            T_min: Минимальная температура, K
            T_max: Максимальная температура, K
            step_k: Шаг по температуре, K (25-250)

        Returns:
            ThermodynamicTable с рассчитанными свойствами

        Raises:
            ValueError: Если шаг температуры вне диапазона 25-250K
        """
        if not (25 <= step_k <= 250):
            raise ValueError(f"Шаг температуры должен быть в диапазоне 25-250K, получено: {step_k}")

        # Ограничение диапазона пределами Tmin-Tmax записи
        tmin = getattr(record, 'tmin', T_min)
        tmax = getattr(record, 'tmax', T_max)
        effective_T_min = max(T_min, tmin)
        effective_T_max = min(T_max, tmax)

        # Округление T_min вверх до ближайшего кратного step_k
        T_start = int(np.ceil(effective_T_min / step_k) * step_k)

        # Генерация сетки температур
        T_values = np.arange(T_start, effective_T_max + 1, step_k)

        # Расчёт свойств для каждой температуры
        properties = []
        for T in T_values:
            try:
                props = self.calculate_properties(record, T)
                properties.append(props)
            except ValueError:
                # Пропуск температур вне диапазона
                continue

        return ThermodynamicTable(
            formula=getattr(record, 'formula', 'Unknown'),
            phase=getattr(record, 'phase', 'Unknown'),
            temperature_range=(effective_T_min, effective_T_max),
            properties=properties
        )

    def calculate_reaction_properties(
        self,
        reactants: List[Tuple[DatabaseRecord, int]],  # [(record, stoich), ...]
        products: List[Tuple[DatabaseRecord, int]],
        T: float
    ) -> Tuple[float, float, float]:
        """
        Расчёт ΔH, ΔS, ΔG реакции при заданной температуре.

        Формулы:
        - ΔH°(T) = Σ(νᵢ * Hᵢ(T))_products - Σ(νⱼ * Hⱼ(T))_reactants
        - ΔS°(T) = Σ(νᵢ * Sᵢ(T))_products - Σ(νⱼ * Sⱼ(T))_reactants
        - ΔG°(T) = ΔH°(T) - T*ΔS°(T)

        Args:
            reactants: Список кортежей (запись, стехиометрический коэффициент)
            products: Список кортежей (запись, стехиометрический коэффициент)
            T: Температура, K

        Returns:
            (ΔH, ΔS, ΔG) в Дж/моль, Дж/(моль·K), Дж/моль
        """
        delta_H = 0.0
        delta_S = 0.0

        # Вклад продуктов (положительный)
        for record, nu in products:
            props = self.calculate_properties(record, T)
            delta_H += nu * props.H
            delta_S += nu * props.S

        # Вклад реагентов (отрицательный)
        for record, nu in reactants:
            props = self.calculate_properties(record, T)
            delta_H -= nu * props.H
            delta_S -= nu * props.S

        # Энергия Гиббса
        delta_G = delta_H - T * delta_S

        return (delta_H, delta_S, delta_G)