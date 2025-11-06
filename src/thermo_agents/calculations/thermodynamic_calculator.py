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
from collections import defaultdict

from ..models.search import DatabaseRecord
from ..models.search import PhaseSegment, PhaseTransition, MultiPhaseProperties, TransitionType, MultiPhaseCompoundData


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
        T: float,
        reference_record: Optional[DatabaseRecord] = None,
        is_elemental: Optional[bool] = None
    ) -> ThermodynamicProperties:
        """
        Расчёт всех термодинамических свойств при температуре T.

        Формулы:
        - H(T) = H298 + ∫[298→T] Cp(T) dT
        - S(T) = S298 + ∫[298→T] Cp(T)/T dT
        - G(T) = H(T) - T*S(T)

        Args:
            record: Запись из базы данных с коэффициентами для расчёта Cp(T)
            T: Температура, K
            reference_record: Опциональная запись-источник для h298/s298.
                              Если None, используются значения из record.
                              Используется для многофазных расчётов, где референсные
                              значения могут отличаться от коэффициентов текущей записи.
            is_elemental: True если вещество простое (O2, N2, Fe, C...).
                          Для простых веществ H298 принудительно устанавливается в 0.0.
                          False для сложных веществ (H2O, CO2, NH3...).
                          None если тип неизвестен (legacy поведение).

        Returns:
            ThermodynamicProperties при температуре T

        Raises:
            ValueError: Если температура вне допустимого диапазона

        Examples:
            >>> # Сложное вещество (вода)
            >>> props = calculator.calculate_properties(h2o_record, 500.0, is_elemental=False)

            >>> # Простое вещество (кислород)
            >>> props = calculator.calculate_properties(o2_record, 500.0, is_elemental=True)
            >>> assert props.H == 0.0  # H298 = 0 для простых веществ
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
        # Если передана референсная запись, берём h298/s298 из неё
        if reference_record is not None:
            h298 = getattr(reference_record, 'h298', 0.0)
            s298 = getattr(reference_record, 's298', 0.0)
        else:
            # Legacy behaviour: используем текущую запись
            h298 = getattr(record, 'h298', 0.0)
            s298 = getattr(record, 's298', 0.0)

        # Применяем правило для простых веществ
        if is_elemental is True:
            h298 = 0.0  # Для простых веществ H298 всегда 0 по определению

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

    # Stage 3: Multi-record calculation methods

    def _select_reference_record(
        self,
        records: List[DatabaseRecord],
        current_index: int,
        is_elemental: Optional[bool] = None
    ) -> DatabaseRecord:
        """
        Выбор референсной записи для расчёта H(T) и S(T) в многофазных системах.

        Алгоритм (из calc_example.ipynb):
        0. Простое вещество (is_elemental=True) → H298=0.0 принудительно
        1. Первая запись (idx=0) → использует саму себя
        2. Смена фазы + валидные h298/s298 (не нули) → новая запись
        3. Смена фазы + нулевые h298/s298 → первая запись предыдущей фазы
        4. Та же фаза → первая запись текущей фазы

        Args:
            records: Список записей, отсортированный по tmin
            current_index: Индекс текущей записи
            is_elemental: True если вещество простое (H298=0 по определению)

        Returns:
            DatabaseRecord, который следует использовать как источник h298/s298

        Examples:
            >>> # NH4Cl: запись 0 (s, 298-457K), запись 1 (s, 457-800K)
            >>> ref0 = calc._select_reference_record([rec0, rec1], 0)  # rec0
            >>> ref1 = calc._select_reference_record([rec0, rec1], 1)  # rec0 (та же фаза)

            >>> # CeCl3: запись 0 (s, 298-1080K), запись 1 (l, 1080-1300K, h298=0)
            >>> ref1 = calc._select_reference_record([rec0, rec1], 1)  # rec0 (нулевые значения)

            >>> # O2: простое вещество
            >>> ref0 = calc._select_reference_record([rec0], 0, is_elemental=True)  # rec0
            >>> # H298 будет принудительно 0.0 в calculate_properties()
        """
        current = records[current_index]

        # Правило 0: Для простых веществ H298 всегда 0
        # (применяется на уровне calculate_properties через параметр is_elemental)

        # Правило 1: первая запись использует саму себя
        if current_index == 0:
            return current

        previous = records[current_index - 1]
        phase_changed = current.phase != previous.phase

        # Правило 2 и 3: смена фазы
        if phase_changed:
            # Проверяем, есть ли валидные данные в текущей записи
            has_valid_h298 = abs(getattr(current, 'h298', 0.0)) > 1e-6
            has_valid_s298 = abs(getattr(current, 's298', 0.0)) > 1e-6

            if has_valid_h298 or has_valid_s298:
                # Правило 2: есть валидные данные → используем текущую запись
                return current
            else:
                # Правило 3: нулевые значения → ищем первую запись предыдущей фазы
                for i in range(current_index - 1, -1, -1):
                    if i == 0 or records[i].phase != records[i - 1].phase:
                        return records[i]

        # Правило 4: та же фаза → находим первую запись текущей фазы
        for i in range(current_index, -1, -1):
            if i == 0 or records[i].phase != records[i - 1].phase:
                return records[i]

        # Fallback (не должно сюда дойти)
        return current

    def calculate_properties_multi_record(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> ThermodynamicProperties:
        """
        Calculate thermodynamic properties using multi-record logic (Stage 3).

        This method implements the core Stage 3 functionality for calculating
        properties when a compound has multiple database records within
        phase segments, ensuring seamless transitions between records.

        Args:
            compound_data: MultiPhaseCompoundData with all records and segments
            temperature: Target temperature in Kelvin

        Returns:
            ThermodynamicProperties at the specified temperature

        Raises:
            ValueError: If temperature is outside available range
        """
        # Get the appropriate record for this temperature
        active_record = compound_data.get_record_at_temperature(temperature)

        # Извлекаем is_elemental из метаданных (если есть)
        is_elemental = getattr(compound_data, 'is_elemental', None)

        # Определяем референсную запись для многофазных расчётов
        all_records = compound_data.records
        if len(all_records) > 1:
            # Находим индекс активной записи
            try:
                active_index = next(
                    i for i, rec in enumerate(all_records)
                    if rec.id == active_record.id
                )
                reference_record = self._select_reference_record(
                    all_records,
                    active_index,
                    is_elemental=is_elemental  # ← Передаём флаг
                )
            except (StopIteration, AttributeError):
                # Fallback: используем активную запись
                reference_record = active_record
        else:
            # Одна запись → использует саму себя
            reference_record = None  # None означает текущую запись

        # Calculate base properties using the selected record
        base_properties = self.calculate_properties(
            active_record,
            temperature,
            reference_record=reference_record,
            is_elemental=is_elemental  # ← Передаём флаг
        )

        # Check if we need transition corrections
        # For now, return base properties (transitions will be handled in more complex scenarios)
        return base_properties

    def calculate_table_multi_record(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Tuple[float, float],
        num_points: int = 100
    ) -> ThermodynamicTable:
        """
        Generate thermodynamic table using multi-record logic (Stage 3).

        This method creates a temperature table that seamlessly handles
        transitions between multiple database records within phase segments.

        Args:
            compound_data: MultiPhaseCompoundData with all records and segments
            temperature_range: Temperature range (Tmin, Tmax) in Kelvin
            num_points: Number of temperature points to calculate

        Returns:
            ThermodynamicTable with properties across the temperature range

        Raises:
            ValueError: If temperature range is invalid or outside available range
        """
        T_min, T_max = temperature_range
        if T_min >= T_max:
            raise ValueError("T_min must be less than T_max")

        # Check against available range
        available_range = compound_data.get_available_range()
        if T_min < available_range[0] or T_max > available_range[1]:
            raise ValueError(
                f"Requested range [{T_min}, {T_max}]K exceeds available range "
                f"[{available_range[0]}, {available_range[1]}]K"
            )

        # Generate temperature points
        temperatures = np.linspace(T_min, T_max, num_points)

        # Calculate properties for each temperature
        properties = []
        transitions_encountered = []

        for T in temperatures:
            try:
                props = self.calculate_properties_multi_record(compound_data, T)
                properties.append(props)

                # Check for record transitions (simplified for now)
                # In full implementation, this would track when we switch records
                if len(properties) > 1:
                    prev_record = compound_data.get_record_at_temperature(temperatures[temperatures < T][-1])
                    curr_record = compound_data.get_record_at_temperature(T)
                    if prev_record.id != curr_record.id:
                        transitions_encountered.append(T)

            except ValueError as e:
                # Skip problematic temperatures but continue
                continue

        return ThermodynamicTable(
            formula=compound_data.compound_formula,
            phase="multi",  # Indicate multi-phase/multi-record
            temperature_range=(T_min, T_max),
            properties=properties
        )

    def _select_active_record(
        self,
        segment: PhaseSegment,
        temperature: float
    ) -> DatabaseRecord:
        """
        Select the active database record for a segment at given temperature.

        This method implements the core Stage 3 logic for choosing which
        database record to use within a phase segment based on temperature.

        Args:
            segment: Phase segment containing records
            temperature: Target temperature in Kelvin

        Returns:
            Active DatabaseRecord for the temperature

        Raises:
            ValueError: If no record covers the specified temperature
        """
        # For now, segments have one record each
        # In full implementation, this would select from multiple records
        if segment.T_start <= temperature <= segment.T_end:
            return segment.record

        raise ValueError(
            f"Temperature {temperature}K is outside segment range "
            f"[{segment.T_start}, {segment.T_end}]K"
        )

    def _handle_record_transition(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        temperature: float
    ) -> Tuple[float, float]:
        """
        Handle transition between two database records.

        This method calculates the corrections needed to maintain
        thermodynamic continuity when switching from one record to another.

        Args:
            from_record: Source database record
            to_record: Target database record
            temperature: Temperature at which transition occurs

        Returns:
            Tuple of (delta_H_correction, delta_S_correction)
        """
        from .record_transition_manager import RecordTransitionManager

        transition_manager = RecordTransitionManager()
        return transition_manager.ensure_continuity(from_record, to_record, temperature)

    # Stage 3: Performance optimization integration

    def calculate_properties_optimized(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> ThermodynamicProperties:
        """
        Calculate thermodynamic properties with performance optimization.

        This method uses the performance optimizer for caching and
        acceleration of repeated calculations.

        Args:
            compound_data: MultiPhaseCompoundData with all records and segments
            temperature: Target temperature in Kelvin

        Returns:
            ThermodynamicProperties at the specified temperature
        """
        from .performance_optimizer import get_performance_optimizer, ProfiledCalculation

        optimizer = get_performance_optimizer()

        with ProfiledCalculation(f"calculate_properties_{compound_data.compound_formula}_{temperature:.1f}"):
            # Get active record
            active_record = compound_data.get_record_at_temperature(temperature)

            # Use optimized calculation
            def calc_func(record, temp):
                return self.calculate_properties(record, temp)

            return optimizer.cached_property_calculation(calc_func, active_record, temperature)

    def generate_table_optimized(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Tuple[float, float],
        num_points: int = 100
    ) -> ThermodynamicTable:
        """
        Generate optimized thermodynamic table with performance enhancements.

        Args:
            compound_data: MultiPhaseCompoundData with all records and segments
            temperature_range: Temperature range (Tmin, Tmax) in Kelvin
            num_points: Number of temperature points to calculate

        Returns:
            Optimized ThermodynamicTable with properties across the temperature range
        """
        from .performance_optimizer import get_performance_optimizer, ProfiledCalculation

        optimizer = get_performance_optimizer()

        with ProfiledCalculation(f"generate_table_{compound_data.compound_formula}_{num_points}_points"):
            T_min, T_max = temperature_range

            # Generate optimized temperature grid
            temperatures = optimizer.optimize_temperature_grid(T_min, T_max, num_points)

            # Batch calculation for better performance
            properties = []

            # Group by record for batch processing
            record_groups = defaultdict(list)
            for i, T in enumerate(temperatures):
                try:
                    record = compound_data.get_record_at_temperature(T)
                    record_groups[record.id].append((i, T))
                except ValueError:
                    continue

            # Calculate properties for each record group
            for record_id, temp_indices in record_groups.items():
                record = compound_data.get_record_at_temperature(temp_indices[0][1])
                temps = [temp for _, temp in temp_indices]

                def calc_func(rec, temp):
                    return self.calculate_properties(rec, temp)

                batch_results = optimizer.batch_property_calculation(calc_func, record, temps)

                # Place results back in correct order
                for (i, _), result in zip(temp_indices, batch_results):
                    if result is not None:
                        properties.append((i, result))

            # Sort by temperature
            properties.sort(key=lambda x: x[0])
            sorted_properties = [prop for _, prop in properties]

            return ThermodynamicTable(
                formula=compound_data.compound_formula,
                phase="multi_optimized",
                temperature_range=temperature_range,
                properties=sorted_properties
            )

    # Stage 4: Phase transition integration methods

    def calculate_properties_with_transitions(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> ThermodynamicProperties:
        """
        Calculate thermodynamic properties with phase transition handling (Stage 4).

        This method implements Stage 4 functionality by correctly accounting for
        enthalpy and entropy jumps at phase transition points (melting, boiling).

        Args:
            compound_data: MultiPhaseCompoundData with transitions
            temperature: Target temperature in Kelvin

        Returns:
            ThermodynamicProperties at the specified temperature with transition corrections

        Raises:
            ValueError: If temperature is outside available range
        """
        from .transition_data_manager import TransitionDataManager
        from .phase_transition_calculator import PhaseTransitionCalculator

        logger.debug(f"Расчёт свойств с учётом переходов для {compound_data.compound_formula} при T={temperature:.1f}K")

        # Get base properties without transitions
        base_properties = self.calculate_properties_multi_record(compound_data, temperature)

        # Extract transition data from records
        transition_manager = TransitionDataManager(self)
        transitions = transition_manager.extract_transition_data(compound_data.records)

        if not transitions:
            logger.debug(f"Нет переходов для {compound_data.compound_formula}")
            return base_properties

        # Sort transitions by temperature
        transitions.sort(key=lambda t: t.temperature)

        # Check if temperature matches any transition point
        transition_calculator = PhaseTransitionCalculator(self)
        current_transition = transition_calculator.detect_transition_at_temperature(
            transitions, temperature
        )

        if current_transition is None:
            # No transition at this temperature - return base properties
            return base_properties

        logger.info(
            f"Обнаружен переход {current_transition.from_phase}→{current_transition.to_phase} "
            f"при T={temperature:.1f}K для {compound_data.compound_formula}"
        )

        # Calculate properties just before transition
        temp_before = temperature - 0.001  # Small epsilon
        try:
            properties_before = self.calculate_properties_multi_record(compound_data, temp_before)
        except ValueError:
            # If we can't calculate before, use current
            properties_before = base_properties

        # Apply transition corrections
        properties_after = transition_calculator.calculate_properties_at_transition(
            current_transition,
            properties_before.enthalpy,
            properties_before.entropy,
            properties_before.heat_capacity
        )

        # Create updated properties object
        transitioned_properties = ThermodynamicProperties(
            T=temperature,
            H=properties_after[0],  # Enthalpy after transition
            S=properties_after[1],  # Entropy after transition
            G=properties_after[2],  # Gibbs energy after transition
            Cp=properties_after[3]  # Heat capacity after transition
        )

        logger.debug(
            f"Свойства после перехода: H={transitioned_properties.H:.0f} Дж/моль, "
            f"S={transitioned_properties.S:.1f} Дж/(моль·K), "
            f"G={transitioned_properties.G:.0f} Дж/моль"
        )

        return transitioned_properties

    def calculate_table_with_transitions(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Tuple[float, float],
        num_points: int = 100
    ) -> ThermodynamicTable:
        """
        Generate thermodynamic table with phase transition handling (Stage 4).

        Creates a temperature table that correctly handles enthalpy and entropy
        jumps at phase transition points, ensuring thermodynamic consistency.

        Args:
            compound_data: MultiPhaseCompoundData with transitions
            temperature_range: Temperature range (Tmin, Tmax) in Kelvin
            num_points: Number of temperature points to calculate

        Returns:
            ThermodynamicTable with transition-aware properties

        Raises:
            ValueError: If temperature range is invalid
        """
        from .transition_data_manager import TransitionDataManager
        from .phase_transition_calculator import PhaseTransitionCalculator

        logger.info(
            f"Создание таблицы с переходами для {compound_data.compound_formula} "
            f"в диапазоне {temperature_range[0]:.1f}-{temperature_range[1]:.1f}K"
        )

        # Extract transition data
        transition_manager = TransitionDataManager(self)
        transitions = transition_manager.extract_transition_data(compound_data.records)

        if not transitions:
            # No transitions - use existing multi-record method
            return self.calculate_table_multi_record(compound_data, temperature_range, num_points)

        # Sort transitions by temperature
        transitions.sort(key=lambda t: t.temperature)

        # Create temperature grid that includes transition points
        T_min, T_max = temperature_range
        base_temperatures = np.linspace(T_min, T_max, num_points)

        # Add transition temperatures to the grid
        transition_temps = [t.temperature for t in transitions if T_min <= t.temperature <= T_max]
        all_temperatures = sorted(list(set(base_temperatures) | set(transition_temps)))

        logger.debug(f"Сетка температур включает {len(transition_temps)} точек перехода")

        # Calculate properties with transition handling
        properties = []
        current_phase = None

        for temp in all_temperatures:
            try:
                temp_properties = self.calculate_properties_with_transitions(compound_data, temp)
                properties.append(temp_properties)

                # Log phase changes
                if current_phase != temp_properties.phase:
                    logger.info(
                        f"Смена фазы {compound_data.compound_formula} при T={temp:.1f}K: "
                        f"{current_phase} → {temp_properties.phase}"
                    )
                    current_phase = temp_properties.phase

            except ValueError as e:
                logger.warning(f"Не удалось рассчитать свойства при T={temp:.1f}K: {e}")
                continue

        if not properties:
            raise ValueError(f"Не удалось рассчитать свойства ни в одной точке диапазона")

        return ThermodynamicTable(
            formula=compound_data.compound_formula,
            phase="multi_with_transitions",
            temperature_range=temperature_range,
            properties=properties
        )

    def _handle_phase_transition(
        self,
        transition: PhaseTransition,
        h_before: float,
        s_before: float
    ) -> Tuple[float, float]:
        """
        Handle phase transition by applying enthalpy and entropy jumps.

        Args:
            transition: Phase transition data
            h_before: Enthalpy before transition (J/mol)
            s_before: Entropy before transition (J/(mol·K))

        Returns:
            Tuple[float, float]: (H_after, S_after) with transition corrections
        """
        # Apply enthalpy jump
        h_after = h_before + (transition.delta_H_transition * 1000)  # кДж → Дж

        # Apply entropy jump
        s_after = s_before + transition.delta_S_transition

        logger.debug(
            f"Применён переход {transition.from_phase}→{transition.to_phase}: "
            f"ΔH={transition.delta_H_transition:.3f} кДж/моль, "
            f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K)"
        )

        return h_after, s_after

    def _detect_transition_at_temperature(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> Optional[PhaseTransition]:
        """
        Detect if there's a phase transition at the specified temperature.

        Args:
            compound_data: MultiPhaseCompoundData with transitions
            temperature: Temperature to check (K)

        Returns:
            Optional[PhaseTransition]: Transition at this temperature or None
        """
        from .transition_data_manager import TransitionDataManager

        # Extract transitions if not already done
        transition_manager = TransitionDataManager(self)
        transitions = transition_manager.extract_transition_data(compound_data.records)

        # Check for transition at this temperature
        for transition in transitions:
            if abs(transition.temperature - temperature) < 1e-3:  # Small tolerance
                return transition

        return None