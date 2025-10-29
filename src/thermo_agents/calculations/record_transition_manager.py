"""
Record Transition Manager for Stage 3 Multi-Record Calculations.

This module implements the logic for managing seamless transitions between
multiple database records within phase segments, ensuring thermodynamic
continuity across record boundaries.

Техническое описание:
Менеджер переходов между записями для Этапа 3 многофазных расчётов.
Реализует логику бесшовного переключения между записями базы данных
внутри фазовых сегментов, обеспечивая непрерывность термодинамических
свойств на границах записей.

Основные функции:

1. Обеспечение непрерывности H(T) и S(T) на границах записей
2. Расчёт корректирующих коэффициентов для переходов
3. Валидация совместимости записей
4. Обработка разрывов в данных
5. Кэширование результатов переходов

Ключевые алгоритмы:

- Вычисление H(T) и S(T) на границах записей
- Определение необходимых коррекций ΔH и ΔS
- Проверка термодинамической согласованности
- Генерация предупреждений о проблемах с данными

Интеграция:
- Используется MultiPhaseCompoundData для предвычисления переходов
- Интегрируется с ThermodynamicCalculator для расчётов с множественными записями
- Поддерживает PhaseSegment для контекста фазовых переходов
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..models.search import DatabaseRecord, RecordTransition


@dataclass
class TransitionCorrection:
    """Correction needed for thermodynamic continuity across record transition."""

    delta_H: float = 0.0  # Enthalpy correction, J/mol
    delta_S: float = 0.0  # Entropy correction, J/(mol·K)
    warning: Optional[str] = None
    is_natural_continuity: bool = True

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "delta_H": self.delta_H,
            "delta_S": self.delta_S,
            "warning": self.warning,
            "natural_continuity": self.is_natural_continuity
        }


class RecordTransitionManager:
    """
    Manager for seamless transitions between database records.

    This class implements the core Stage 3 logic for handling transitions
    between multiple records within phase segments, ensuring that
    thermodynamic properties remain continuous across record boundaries.
    """

    def __init__(self, tolerance: float = 1e-6):
        """
        Initialize the transition manager.

        Args:
            tolerance: Numerical tolerance for continuity checks
        """
        self.tolerance = tolerance
        self._transition_cache: Dict[Tuple[int, int, float], TransitionCorrection] = {}

    def calculate_transition_corrections(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition_temperature: float
    ) -> Dict[str, float]:
        """
        Calculate corrections needed to maintain thermodynamic continuity.

        This method computes the enthalpy and entropy corrections needed
        to ensure that H(T) and S(T) remain continuous when switching
        from one database record to another.

        Args:
            from_record: Source database record
            to_record: Target database record
            transition_temperature: Temperature at which transition occurs

        Returns:
            Dictionary with corrections and metadata:
            - delta_H: Enthalpy correction (J/mol)
            - delta_S: Entropy correction (J/(mol·K))
            - warning: Optional warning message
        """
        # Check cache first
        cache_key = (from_record.id or 0, to_record.id or 0, transition_temperature)
        if cache_key in self._transition_cache:
            correction = self._transition_cache[cache_key]
            return {
                "delta_H": correction.delta_H,
                "delta_S": correction.delta_S,
                "warning": correction.warning
            }

        # Calculate thermodynamic properties at transition temperature
        H_from, S_from = self._calculate_properties_at_temperature(
            from_record, transition_temperature
        )
        H_to, S_to = self._calculate_properties_at_temperature(
            to_record, transition_temperature
        )

        # Calculate corrections needed for continuity
        delta_H_correction = H_from - H_to
        delta_S_correction = S_from - S_to

        # Determine if transition is naturally continuous
        is_continuous = (
            abs(delta_H_correction) < self.tolerance and
            abs(delta_S_correction) < self.tolerance
        )

        # Generate warning if corrections are significant
        warning = None
        if not is_continuous:
            if abs(delta_H_correction) > 1000:  # > 1 kJ/mol
                warning = (
                    f"Значительный разрыв энтальпии на границе записей: "
                    f"ΔH = {delta_H_correction/1000:.3f} кДж/моль при T = {transition_temperature}K"
                )
            elif abs(delta_S_correction) > 10:  # > 10 J/(mol·K)
                warning = (
                    f"Значительный разрыв энтропии на границе записей: "
                    f"ΔS = {delta_S_correction:.3f} Дж/(моль·K) при T = {transition_temperature}K"
                )
            else:
                warning = (
                    f"Малые разрывы термодинамических свойств на границе записей "
                    f"при T = {transition_temperature}K"
                )

        # Create correction object
        correction = TransitionCorrection(
            delta_H=delta_H_correction,
            delta_S=delta_S_correction,
            warning=warning,
            is_natural_continuity=is_continuous
        )

        # Cache the result
        self._transition_cache[cache_key] = correction

        return {
            "delta_H": delta_H_correction,
            "delta_S": delta_S_correction,
            "warning": warning
        }

    def ensure_continuity(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition_temp: float
    ) -> Tuple[float, float]:
        """
        Ensure thermodynamic continuity across record transition.

        Args:
            from_record: Source record
            to_record: Target record
            transition_temp: Transition temperature

        Returns:
            Tuple of (delta_H_correction, delta_S_correction)
        """
        corrections = self.calculate_transition_corrections(
            from_record, to_record, transition_temp
        )

        return corrections["delta_H"], corrections["delta_S"]

    def validate_record_compatibility(
        self,
        record1: DatabaseRecord,
        record2: DatabaseRecord
    ) -> bool:
        """
        Validate if two records are compatible for transition.

        Args:
            record1: First record
            record2: Second record

        Returns:
            True if records are compatible for transition
        """
        # Check if records touch by temperature
        if abs(record1.tmax - record2.tmin) > 1e-3:
            return False

        # Check if they have the same phase
        if record1.phase != record2.phase:
            return False

        # Check if they have the same compound (formula)
        if record1.formula != record2.formula:
            return False

        return True

    def _calculate_properties_at_temperature(
        self,
        record: DatabaseRecord,
        temperature: float
    ) -> Tuple[float, float]:
        """
        Calculate H(T) and S(T) for a record at given temperature.

        Args:
            record: Database record with thermodynamic data
            temperature: Temperature in Kelvin

        Returns:
            Tuple of (H, S) at specified temperature
        """
        if not record.tmin <= temperature <= record.tmax:
            raise ValueError(
                f"Temperature {temperature}K is outside record range "
                f"[{record.tmin}, {record.tmax}]K"
            )

        # Calculate heat capacity at temperature using NASA polynomials
        Cp_T = self._calculate_heat_capacity(record, temperature)

        # Calculate enthalpy change from 298K to target temperature
        # ΔH = ∫(298→T) Cp(T) dT
        delta_H = self._integrate_heat_capacity(record, 298.15, temperature)

        # Calculate entropy change from 298K to target temperature
        # ΔS = ∫(298→T) Cp(T)/T dT
        delta_S = self._integrate_entropy(record, 298.15, temperature)

        # Total enthalpy and entropy at target temperature
        H_T = record.h298 + delta_H
        S_T = record.s298 + delta_S

        return H_T, S_T

    def _calculate_heat_capacity(self, record: DatabaseRecord, temperature: float) -> float:
        """
        Calculate heat capacity using NASA polynomial coefficients.

        Cp(T) = f1 + f2*T + f3*T^2 + f4*T^3 + f5*T^4 + f6*T^5

        Args:
            record: Database record with NASA coefficients
            temperature: Temperature in Kelvin

        Returns:
            Heat capacity at temperature, J/(mol·K)
        """
        T = temperature
        T2 = T * T
        T3 = T2 * T
        T4 = T3 * T
        T5 = T4 * T

        Cp = (
            record.f1 +
            record.f2 * T +
            record.f3 * T2 +
            record.f4 * T3 +
            record.f5 * T4 +
            record.f6 * T5
        )

        return Cp

    def _integrate_heat_capacity(
        self,
        record: DatabaseRecord,
        T_start: float,
        T_end: float
    ) -> float:
        """
        Integrate heat capacity to get enthalpy change.

        ΔH = ∫(T_start→T_end) Cp(T) dT

        Args:
            record: Database record with NASA coefficients
            T_start: Start temperature
            T_end: End temperature

        Returns:
            Enthalpy change, J/mol
        """
        # Analytical integration of NASA polynomial
        # ∫(f1 + f2*T + f3*T^2 + f4*T^3 + f5*T^4 + f6*T^5) dT
        # = f1*ΔT + f2*(T²²/2) + f3*(T³³/3) + f4*(T⁴⁴/4) + f5*(T⁵⁵/5) + f6*(T⁶⁶/6)

        def antiderivative(T: float) -> float:
            return (
                record.f1 * T +
                record.f2 * T * T / 2 +
                record.f3 * T * T * T / 3 +
                record.f4 * T * T * T * T / 4 +
                record.f5 * T * T * T * T * T / 5 +
                record.f6 * T * T * T * T * T * T / 6
            )

        return antiderivative(T_end) - antiderivative(T_start)

    def _integrate_entropy(
        self,
        record: DatabaseRecord,
        T_start: float,
        T_end: float
    ) -> float:
        """
        Integrate Cp(T)/T to get entropy change.

        ΔS = ∫(T_start→T_end) Cp(T)/T dT

        Args:
            record: Database record with NASA coefficients
            T_start: Start temperature
            T_end: End temperature

        Returns:
            Entropy change, J/(mol·K)
        """
        # Analytical integration of Cp(T)/T
        # ∫(f1/T + f2 + f3*T + f4*T²² + f5*T³³ + f6*T⁴⁴) dT
        # = f1*ln(T) + f2*T + f3*T²²/2 + f4*T³³/3 + f5*T⁴⁴/4 + f6*T⁵⁵/5

        def antiderivative(T: float) -> float:
            return (
                record.f1 * math.log(T) +
                record.f2 * T +
                record.f3 * T * T / 2 +
                record.f4 * T * T * T / 3 +
                record.f5 * T * T * T * T / 4 +
                record.f6 * T * T * T * T * T / 5
            )

        return antiderivative(T_end) - antiderivative(T_start)

    def clear_cache(self) -> None:
        """Clear the transition cache."""
        self._transition_cache.clear()

    def get_cache_size(self) -> int:
        """Get the number of cached transitions."""
        return len(self._transition_cache)

    def analyze_transition_quality(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition_temperature: float
    ) -> Dict[str, any]:
        """
        Analyze the quality of a transition between records.

        Args:
            from_record: Source record
            to_record: Target record
            transition_temperature: Temperature of transition

        Returns:
            Dictionary with transition quality analysis
        """
        corrections = self.calculate_transition_corrections(
            from_record, to_record, transition_temperature
        )

        # Calculate percentage differences
        H_from, S_from = self._calculate_properties_at_temperature(
            from_record, transition_temperature
        )
        H_to, S_to = self._calculate_properties_at_temperature(
            to_record, transition_temperature
        )

        H_diff_percent = abs(H_from - H_to) / abs(H_from) * 100 if H_from != 0 else 0
        S_diff_percent = abs(S_from - S_to) / abs(S_from) * 100 if S_from != 0 else 0

        # Determine quality rating
        delta_H = corrections["delta_H"]
        delta_S = corrections["delta_S"]

        if abs(delta_H) < self.tolerance and abs(delta_S) < self.tolerance:
            quality = "excellent"
        elif abs(delta_H) < 100 and abs(delta_S) < 1:  # < 100 J/mol, < 1 J/(mol·K)
            quality = "good"
        elif abs(delta_H) < 1000 and abs(delta_S) < 10:  # < 1 kJ/mol, < 10 J/(mol·K)
            quality = "acceptable"
        else:
            quality = "poor"

        return {
            "quality": quality,
            "delta_H": delta_H,
            "delta_S": delta_S,
            "H_difference_percent": H_diff_percent,
            "S_difference_percent": S_diff_percent,
            "warning": corrections["warning"],
            "is_continuous": abs(delta_H) < self.tolerance and abs(delta_S) < self.tolerance
        }