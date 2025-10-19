"""
Термодинамический калькулятор для расчета свойств веществ и реакций.

Реализует детерминированные расчеты на основе формул Шомейта
и коэффициентов из термодинамической базы данных.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from functools import lru_cache
from scipy.integrate import quad

from ..models.search import DatabaseRecord
from ..models.search import PhaseSegment, PhaseTransition, MultiPhaseProperties, TransitionType


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

    def calculate_multi_phase_properties(
        self,
        records: List[DatabaseRecord],
        trajectory: Optional[List[float]] = None,
        include_phase_transitions: bool = True
    ) -> MultiPhaseProperties:
        """
        Расчёт многофазных термодинамических свойств по траектории температур.

        Алгоритм:
        1. Сортировка записей по Tmin
        2. Создание PhaseSegment для каждой записи
        3. Определение фазовых переходов между сегментами
        4. Накопительное интегрирование по всей траектории
        5. Учёт фазовых переходов (если включены)

        Args:
            records: Список записей DatabaseRecord, отсортированный по Tmin
            trajectory: Список температур для траектории расчёта. Если None, используется [298.15, 1700.0]
            include_phase_transitions: Включать фазовые переходы в расчёт

        Returns:
            MultiPhaseProperties с результатами расчёта

        Raises:
            ValueError: Если записи не отсортированы или имеют пробелы
        """
        if not records:
            raise ValueError("Список записей не может быть пустым")

        # Шаг 1: Сортировка записей по Tmin
        sorted_records = sorted(records, key=lambda r: r.tmin or float('inf'))

        # Шаг 2: Проверка корректности сортировки
        for i in range(len(sorted_records) - 1):
            current = sorted_records[i]
            next_record = sorted_records[i + 1]

            if current.tmax and next_record.tmin:
                if current.tmax < next_record.tmin - 1e-6:  # Допуск на ошибки округления
                    raise ValueError(
                        f"Обнаружен пробел между записями: {current.phase} "
                        f"({current.tmin}-{current.tmax}K) и {next_record.phase} "
                        f"({next_record.tmin}-{next_record.tmax}K)"
                    )

        # Шаг 3: Создание PhaseSegment для каждой записи
        segments = []
        for record in sorted_records:
            phase_segment = PhaseSegment.from_database_record(record)
            segments.append(phase_segment)

        # Шаг 4: Определение фазовых переходов
        transitions = []
        if include_phase_transitions and len(segments) > 1:
            transitions = self._identify_phase_transitions(segments)

        # Шаг 5: Определение траектории расчёта
        if trajectory is None:
            trajectory = [298.15, 1700.0]

        # Шаг 6: Накопительное интегрирование
        cumulative_H = 0.0
        cumulative_S = 0.0

        for segment in segments:
            # Определяем температурный диапазон для этого сегмента
            segment_temps = [T for T in trajectory if segment.T_start <= T <= segment.T_end]

            if not segment_temps:
                continue

            # Интегрируем в пределах сегмента
            for T in segment_temps:
                if T == 298.15:
                    # Базовые значения при 298.15K
                    H_at_T = segment.H_start
                    S_at_T = segment.S_start
                else:
                    # Интегрирование от 298.15K до T
                    if T > 298.15:
                        delta_H, _ = self._integrate_enthalpy(segment, 298.15, T)
                        _, delta_S = self._integrate_entropy(segment, 298.15, T)
                        H_at_T = segment.H_start + delta_H
                        S_at_T = segment.S_start + delta_S
                    else:
                        # Интегрирование от T до 298.15K (обратное направление)
                        delta_H, _ = self._integrate_enthalpy(segment, T, 298.15)
                        _, delta_S = self._integrate_entropy(segment, T, 298.15)
                        H_at_T = segment.H_start - delta_H
                        S_at_T = segment.S_start - delta_S

                # Накопительные значения (учитываем уже пройденные сегменты)
                if len(segments) > 1:
                    # Для многофазных систем добавляем разницу с предыдущим сегментом
                    cumulative_H = H_at_T
                    cumulative_S = S_at_T
                else:
                    cumulative_H = H_at_T
                    cumulative_S = S_at_T

        # Шаг 7: Учёт фазовых переходов
        if include_phase_transitions:
            for transition in transitions:
                # Проверяем, входит ли температура перехода в траекторию
                if any(abs(T - transition.temperature) < 1e-6 for T in trajectory):
                    cumulative_H += transition.delta_H_transition * 1000.0  # Convert kJ to J
                    cumulative_S += transition.delta_S_transition

        # Шаг 8: Создание результата
        T_target = trajectory[-1] if trajectory else 1700.0
        G_target = cumulative_H - T_target * cumulative_S
        Cp_target = self._calculate_cp_at_temperature(sorted_records[-1], T_target)

        return MultiPhaseProperties(
            T_target=T_target,
            H_final=cumulative_H,
            S_final=cumulative_S,
            G_final=G_target,
            Cp_final=Cp_target,
            segments=segments,
            phase_transitions=transitions
        )

    def _identify_phase_transitions(self, segments: List[PhaseSegment]) -> List[PhaseTransition]:
        """
        Определение фазовых переходов между сегментами.

        Args:
            segments: Список сегментов, отсортированный по температуре

        Returns:
            Список фазовых переходов
        """
        transitions = []

        for i in range(len(segments) - 1):
            current = segments[i]
            next_segment = segments[i + 1]

            # Проверяем, есть ли граница между сегментами
            if current.T_end and next_segment.T_start:
                T_transition = (current.T_end + next_segment.T_start) / 2.0

                # Определяем тип перехода
                transition_type = self._determine_transition_type(current.record.phase, next_segment.record.phase)

                if transition_type:
                    # Оцениваем изменение энтальпии и энтропии
                    # Для простоты используем разницу в H_start и S_start как приближение
                    delta_H = next_segment.H_start - current.H_start
                    delta_S = next_segment.S_start - current.S_start

                    transition = PhaseTransition(
                        temperature=T_transition,
                        from_phase=current.record.phase,
                        to_phase=next_segment.record.phase,
                        transition_type=transition_type,
                        delta_H_transition=delta_H / 1000.0,  # Convert to kJ/mol
                        delta_S_transition=delta_S if T_transition > 0 else 0.0
                    )
                    transitions.append(transition)

        return transitions

    def _determine_transition_type(self, from_phase: str, to_phase: str) -> Optional[TransitionType]:
        """
        Определение типа фазового перехода.

        Args:
            from_phase: Исходная фаза
            to_phase: Конечная фаза

        Returns:
            Тип перехода или None, если переход не определен
        """
        transition_matrix = {
            ('s', 'l'): TransitionType.MELTING,
            ('l', 'g'): TransitionType.BOILING,
            ('s', 'g'): TransitionType.SUBLIMATION,
        }

        return transition_matrix.get((from_phase, to_phase))

    def _integrate_enthalpy(self, segment: PhaseSegment, T1: float, T2: float) -> Tuple[float, Optional[float]]:
        """
        Интегрирование теплоёмкости для расчёта изменения энтальпии.

        ΔH = ∫[T1→T2] Cp(T) dT

        Args:
            segment: Сегмент с коэффициентами
            T1: Начальная температура
            T2: Конечная температура

        Returns:
            (ΔH, ошибка интегрирования)
        """
        record = segment.record
        def Cp_T(T):
            return (
                getattr(record, 'f1', 0.0)
                + getattr(record, 'f2', 0.0) * T / 1000.0
                + getattr(record, 'f3', 0.0) * 100_000.0 / (T ** 2)
                + getattr(record, 'f4', 0.0) * T**2 / 1_000_000.0
                + getattr(record, 'f5', 0.0) * 1_000.0 / (T ** 3)
                + getattr(record, 'f6', 0.0) * T**3 * 1e-9
            )

        delta_H, error = quad(Cp_T, T1, T2, epsabs=1e-9, epsrel=1e-9)
        return delta_H, error

    def _integrate_entropy(self, segment: PhaseSegment, T1: float, T2: float) -> Tuple[float, Optional[float]]:
        """
        Интегрирование Cp/T для расчёта изменения энтропии.

        ΔS = ∫[T1→T2] Cp(T)/T dT

        Args:
            segment: Сегмент с коэффициентами
            T1: Начальная температура
            T2: Конечная температура

        Returns:
            (ΔS, ошибка интегрирования)
        """
        record = segment.record
        def Cp_T_over_T(T):
            Cp_T = (
                getattr(record, 'f1', 0.0)
                + getattr(record, 'f2', 0.0) * T / 1000.0
                + getattr(record, 'f3', 0.0) * 100_000.0 / (T ** 2)
                + getattr(record, 'f4', 0.0) * T**2 / 1_000_000.0
                + getattr(record, 'f5', 0.0) * 1_000.0 / (T ** 3)
                + getattr(record, 'f6', 0.0) * T**3 * 1e-9
            )
            return Cp_T / T

        delta_S, error = quad(Cp_T_over_T, T1, T2, epsabs=1e-12, epsrel=1e-9)
        return delta_S, error

    def _create_segment_from_record(self, record: DatabaseRecord) -> PhaseSegment:
        """
        Create PhaseSegment from DatabaseRecord for testing.

        Args:
            record: DatabaseRecord with thermodynamic data

        Returns:
            PhaseSegment initialized from record
        """
        return PhaseSegment.from_database_record(record)

    def _calculate_cp_at_temperature(self, record: DatabaseRecord, T: float) -> float:
        """
        Расчёт теплоёмкости в заданной температуре.

        Args:
            record: Запись из базы данных
            T: Температура, K

        Returns:
            Cp в Дж/(моль·K)
        """
        return self.calculate_cp(record, T)