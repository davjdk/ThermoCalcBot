"""
Thermodynamic engine for single compound calculations.

This module implements the thermodynamic property calculations from calc_example.ipynb
using the Shomate equations for heat capacity.
"""

import logging
from typing import Dict

import numpy as np
import pandas as pd


class ThermodynamicEngine:
    """
    Расчет Cp, H, S, G для одного вещества при заданной температуре.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.T_ref = 298.15  # Референсная температура (K)

    def calculate_properties(self, record: pd.Series, T: float) -> Dict[str, float]:
        """
        Расчет термодинамических свойств при температуре T.

        Формулы:

        Cp(T) = f₁ + f₂·T/1000 + f₃·T⁻²·10⁵ + f₄·T²/10⁶ + f₅·T⁻³·10³ + f₆·T³·10⁻⁹

        ΔH = ∫₂₉₈ᵀ Cp(T) dT  (численное интегрирование)
        H(T) = H₂₉₈ + ΔH

        ΔS = ∫₂₉₈ᵀ [Cp(T)/T] dT  (численное интегрирование)
        S(T) = S₂₉₈ + ΔS

        G(T) = H(T) - T·S(T)

        Args:
            record: Строка DataFrame с коэффициентами (f1-f6, H298, S298, Tmin, Tmax)
            T: Температура расчета (K)

        Returns:
            {
                'cp': теплоемкость (Дж/(моль·K)),
                'enthalpy': энтальпия (Дж/моль),
                'entropy': энтропия (Дж/(моль·K)),
                'gibbs_energy': энергия Гиббса (Дж/моль)
            }

        Предупреждения:
            - ⚠ Температура {T}K выходит за пределы {Tmin}-{Tmax}K для {formula}

        Численное интегрирование:
            - Метод: трапеций (np.trapz)
            - Точек интегрирования: 100
        """
        # Проверка температурного диапазона с допуском ±0.2K для избежания ложных предупреждений
        # (298.0 vs 298.15K считаются эквивалентными)
        tolerance = 0.2
        if "Tmin" in record and "Tmax" in record:
            if T < (record["Tmin"] - tolerance) or T > (record["Tmax"] + tolerance):
                formula = record.get("Formula", "unknown")
                self.logger.warning(
                    f"⚠ Температура {T}K выходит за пределы "
                    f"{record['Tmin']}-{record['Tmax']}K для {formula}"
                )

        # Извлечение коэффициентов
        f1 = record.get("f1", 0)
        f2 = record.get("f2", 0)
        f3 = record.get("f3", 0)
        f4 = record.get("f4", 0)
        f5 = record.get("f5", 0)
        f6 = record.get("f6", 0)
        H298 = record.get("H298", 0)
        S298 = record.get("S298", 0)

        # Функция для расчета теплоемкости при любой температуре
        def cp_function(temp: float) -> float:
            temp = float(temp)  # Ensure temp is float
            return (
                f1
                + f2 * temp / 1000
                + f3 * (temp**-2 if temp != 0 else 0) * 100_000
                + f4 * temp**2 / 1_000_000
                + f5 * (temp**-3 if temp != 0 else 0) * 1_000
                + f6 * temp**3 * 10 ** (-9)
            )

        # Теплоемкость при текущей температуре
        cp = cp_function(T)

        # Если T равно референсной температуре, интегрирование не нужно
        if abs(T - self.T_ref) < 1e-6:
            enthalpy = H298 * 1000  # Конвертируем из кДж в Дж
            entropy = S298
            gibbs_energy = enthalpy - T * entropy
            return {
                "cp": cp,
                "enthalpy": enthalpy,
                "entropy": entropy,
                "gibbs_energy": gibbs_energy,
            }

        # Численное интегрирование для изменения энтальпии (ΔH)
        # ΔH = ∫(T_ref to T) Cp(T) dT
        num_points = 100  # Количество точек для численного интегрирования
        temp_points = np.linspace(self.T_ref, T, num_points)
        cp_values = np.array([cp_function(t) for t in temp_points])
        delta_H = np.trapz(cp_values, temp_points)

        # Численное интегрирование для изменения энтропии (ΔS)
        # ΔS = ∫(T_ref to T) Cp(T)/T dT
        cp_over_T = cp_values / temp_points
        delta_S = np.trapz(cp_over_T, temp_points)

        # Расчет финальных значений энтальпии и энтропии
        enthalpy = H298 * 1000 + delta_H  # Конвертируем H298 из кДж в Дж
        entropy = S298 + delta_S

        # Расчет энергии Гиббса
        gibbs_energy = enthalpy - T * entropy

        return {
            "cp": cp,
            "enthalpy": enthalpy,
            "entropy": entropy,
            "gibbs_energy": gibbs_energy,
        }

    def calculate_properties_with_extrapolation(
        self, record: pd.Series, T: float, T_max_available: float
    ) -> Dict[str, float]:
        """
        Расчет термодинамических свойств с экстраполяцией для T > Tmax.

        Если T > Tmax записи, используется экстраполяция с постоянной теплоёмкостью
        при T_max:
        - Cp(T) = Cp(T_max) для всех T > T_max
        - H(T) = H(T_max) + Cp(T_max) × (T - T_max)
        - S(T) = S(T_max) + Cp(T_max) × ln(T / T_max)

        Args:
            record: Строка DataFrame с коэффициентами
            T: Целевая температура расчета (K)
            T_max_available: Максимальная доступная температура записи (K)

        Returns:
            Словарь с термодинамическими свойствами
        """
        # Если T в пределах диапазона, используем обычный расчёт
        if T <= T_max_available:
            return self.calculate_properties(record, T)

        # Экстраполяция: рассчитываем свойства при T_max
        props_at_max = self.calculate_properties(record, T_max_available)

        cp_at_max = props_at_max["cp"]
        H_at_max = props_at_max["enthalpy"]
        S_at_max = props_at_max["entropy"]

        # Экстраполируем с постоянной теплоёмкостью
        delta_H_extra = cp_at_max * (T - T_max_available)
        delta_S_extra = cp_at_max * np.log(T / T_max_available)

        enthalpy = H_at_max + delta_H_extra
        entropy = S_at_max + delta_S_extra
        gibbs_energy = enthalpy - T * entropy

        formula = record.get("Formula", "unknown")
        self.logger.debug(
            f"🔼 Экстраполяция для {formula}: T={T}K > T_max={T_max_available}K, "
            f"Cp={cp_at_max:.2f} Дж/(моль·K)"
        )

        return {
            "cp": cp_at_max,  # Постоянная теплоёмкость
            "enthalpy": enthalpy,
            "entropy": entropy,
            "gibbs_energy": gibbs_energy,
        }
