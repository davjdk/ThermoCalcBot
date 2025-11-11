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

    def calculate_properties(
        self, record: pd.Series, T: float, reference_record: pd.Series = None
    ) -> Dict[str, float]:
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
            record: Строка DataFrame с коэффициентами (f1-f6) для текущего T-диапазона
            T: Температура расчета (K)
            reference_record: Референсная запись с H₂₉₈ и S₂₉₈. Если None, используется record.
                             Это позволяет избежать скачков при смене записи внутри одной фазы.

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

        # Вспомогательная функция для получения значения из записи (поддержка pd.Series и DatabaseRecord)
        def get_value(rec, key: str, default=0):
            """Получает значение из записи, поддерживая и словари/pd.Series, и Pydantic модели."""
            if hasattr(rec, "get"):  # pd.Series или словарь
                return rec.get(key, default)
            else:  # Pydantic модель (DatabaseRecord)
                return getattr(rec, key.lower(), default)

        # Проверка температурного диапазона с допуском ±0.2K для избежания ложных предупреждений
        # (298.0 vs 298.15K считаются эквивалентными)
        tolerance = 0.2
        tmin = get_value(record, "tmin", float("-inf"))
        tmax = get_value(record, "tmax", float("inf"))

        if tmin != float("-inf") and tmax != float("inf"):
            if T < (tmin - tolerance) or T > (tmax + tolerance):
                formula = get_value(record, "formula", "unknown")
                self.logger.warning(
                    f"⚠ Температура {T}K выходит за пределы "
                    f"{tmin}-{tmax}K для {formula}"
                )

        # Извлечение коэффициентов Шомейта из текущей записи
        f1 = get_value(record, "f1", 0)
        f2 = get_value(record, "f2", 0)
        f3 = get_value(record, "f3", 0)
        f4 = get_value(record, "f4", 0)
        f5 = get_value(record, "f5", 0)
        f6 = get_value(record, "f6", 0)

        # Валидация коэффициентов Шомейта
        if not self._has_valid_shomate_coefficients(f1, f2, f3, f4, f5, f6):
            formula = get_value(record, "formula", "unknown")
            phase = get_value(record, "phase", "")
            tmin = get_value(record, "tmin", 0)
            tmax = get_value(record, "tmax", 0)

            self.logger.error(
                f"❌ Запись для {formula} (фаза: {phase}, T: {tmin}-{tmax}K) "
                f"имеет все нулевые коэффициенты Шомейта (f1-f6). "
                f"Расчет термодинамических свойств невозможен."
            )

            # Возвращаем нулевые значения с предупреждением
            return {
                "cp": 0.0,
                "enthalpy": 0.0,
                "entropy": 0.0,
                "gibbs_energy": 0.0,
            }

        # Извлечение H₂₉₈ и S₂₉₈ из референсной записи (если указана) или текущей
        if reference_record is not None:
            H298 = get_value(reference_record, "h298", 0)
            S298 = get_value(reference_record, "s298", 0)
        else:
            H298 = get_value(record, "h298", 0)
            S298 = get_value(record, "s298", 0)

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

    def calculate_properties_piecewise(
        self,
        records: list,
        T: float,
        reference_record: pd.Series = None,
    ) -> Dict[str, float]:
        """
        Расчет термодинамических свойств с КУСОЧНЫМ интегрированием через все записи фазы.

        КРИТИЧЕСКИ ВАЖНО: Интегрирование от 298.15K до T нельзя выполнять с коэффициентами
        одной записи, если T выходит за её диапазон. Нужно интегрировать ПОЭТАПНО:

        Например, для SO2 при T=2098K:
        - ∫(298→700)Cp₁(T)dT  (запись 1: 298-700K)
        - ∫(700→2000)Cp₂(T)dT (запись 2: 700-2000K)
        - ∫(2000→2098)Cp₃(T)dT (запись 3: 2000-3000K)

        Args:
            records: Список ВСЕХ записей фазы, отсортированных по Tmin
            T: Целевая температура
            reference_record: Запись с H₂₉₈ и S₂₉₈ (обычно первая запись фазы)

        Returns:
            Словарь с термодинамическими свойствами
        """

        # Вспомогательная функция
        def get_value(rec, key: str, default=0):
            if hasattr(rec, "get"):
                return rec.get(key, default)
            else:
                return getattr(rec, key.lower(), default)

        # Сортируем записи по Tmin
        sorted_records = sorted(records, key=lambda r: get_value(r, "tmin", 0))

        # Используем первую запись как reference, если не указана
        if reference_record is None:
            reference_record = sorted_records[0]

        H298 = get_value(reference_record, "h298", 0)
        S298 = get_value(reference_record, "s298", 0)

        # Функция для расчета Cp по коэффициентам записи
        def cp_function(temp: float, record) -> float:
            f1 = get_value(record, "f1", 0)
            f2 = get_value(record, "f2", 0)
            f3 = get_value(record, "f3", 0)
            f4 = get_value(record, "f4", 0)
            f5 = get_value(record, "f5", 0)
            f6 = get_value(record, "f6", 0)

            # Валидация коэффициентов для каждой записи
            if not self._has_valid_shomate_coefficients(f1, f2, f3, f4, f5, f6):
                formula = get_value(record, "formula", "unknown")
                phase = get_value(record, "phase", "")
                tmin = get_value(record, "tmin", 0)
                tmax = get_value(record, "tmax", 0)

                self.logger.error(
                    f"❌ Запись для {formula} (фаза: {phase}, T: {tmin}-{tmax}K) "
                    f"имеет все нулевые коэффициенты Шомейта при кусочном интегрировании."
                )
                return 0.0

            temp = float(temp)
            return (
                f1
                + f2 * temp / 1000
                + f3 * (temp**-2 if temp != 0 else 0) * 100_000
                + f4 * temp**2 / 1_000_000
                + f5 * (temp**-3 if temp != 0 else 0) * 1_000
                + f6 * temp**3 * 10 ** (-9)
            )

        # Находим запись для целевой температуры T
        target_record = None
        for rec in sorted_records:
            tmin = get_value(rec, "tmin", float("-inf"))
            tmax = get_value(rec, "tmax", float("inf"))
            if tmin <= T <= tmax:
                target_record = rec
                break

        if target_record is None:
            # Если T вне всех диапазонов, используем последнюю запись
            target_record = sorted_records[-1]

        # Кусочное интегрирование от 298.15K до T
        delta_H_total = 0.0
        delta_S_total = 0.0
        T_start = self.T_ref
        num_points = 100

        for record in sorted_records:
            tmin = get_value(record, "tmin", float("-inf"))
            tmax = get_value(record, "tmax", float("inf"))

            # Определяем границы интегрирования для текущей записи
            if T <= tmin:
                # T ниже этой записи - пропускаем
                continue
            elif T_start >= tmax:
                # Уже прошли эту запись - пропускаем
                continue

            # Границы сегмента интегрирования
            segment_start = max(T_start, tmin)
            segment_end = min(T, tmax)

            if segment_end <= segment_start:
                continue

            # Интегрируем на этом сегменте
            temp_points = np.linspace(segment_start, segment_end, num_points)
            cp_values = np.array([cp_function(t, record) for t in temp_points])

            delta_H_segment = np.trapz(cp_values, temp_points)
            delta_S_segment = np.trapz(cp_values / temp_points, temp_points)

            delta_H_total += delta_H_segment
            delta_S_total += delta_S_segment

            # Обновляем начало для следующей записи
            T_start = segment_end

            # Если достигли целевой температуры, выходим
            if segment_end >= T:
                break

        # Финальные значения
        enthalpy = H298 * 1000 + delta_H_total
        entropy = S298 + delta_S_total
        cp = cp_function(T, target_record)
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

    def _calculate_cp_direct(self, record: pd.Series, T: float) -> float:
        """
        Прямой расчет Cp для записи по формуле Шомейта.

        Args:
            record: Запись с коэффициентами Шомейта
            T: Температура в Кельвинах

        Returns:
            Теплоемкость Cp в Дж/(моль·K)
        """
        def get_value(rec, key, default=0):
            return rec.get(key, default) if isinstance(rec, dict) else getattr(rec, key, default)

        f1 = get_value(record, "f1", 0)
        f2 = get_value(record, "f2", 0)
        f3 = get_value(record, "f3", 0)
        f4 = get_value(record, "f4", 0)
        f5 = get_value(record, "f5", 0)
        f6 = get_value(record, "f6", 0)

        temp = float(T)
        return (
            f1 + f2 * temp / 1000
            + f3 * (temp**-2 if temp != 0 else 0) * 100_000
            + f4 * temp**2 / 1_000_000
            + f5 * (temp**-3 if temp != 0 else 0) * 1_000
            + f6 * temp**3 * 10**(-9)
        )

    def _has_valid_shomate_coefficients(
        self, f1: float, f2: float, f3: float, f4: float, f5: float, f6: float
    ) -> bool:
        """
        Проверяет, имеют ли коэффициенты Шомейта хотя бы одно ненулевое значение.

        Args:
            f1-f6: Коэффициенты Шомейта

        Returns:
            True если хотя бы один коэффициент не равен нулю, иначе False
        """
        # Допуск для численных ошибок
        tolerance = 1e-10

        # Проверяем, что хотя бы один коэффициент не равен нулю
        coefficients = [f1, f2, f3, f4, f5, f6]
        return any(abs(coef) > tolerance for coef in coefficients)
