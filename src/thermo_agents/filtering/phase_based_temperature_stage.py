"""
Стадия фильтрации с умным разделением по фазам на основе температурных переходов.

Эта стадия анализирует запрошенный температурный диапазон и определяет,
какие фазы необходимы для полного покрытия. Если диапазон пересекает
фазовые переходы (MeltingPoint, BoilingPoint), выбирается несколько записей
для разных фаз.
"""

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from thermo_agents.filtering.filter_pipeline import FilterContext, FilterStage
from thermo_agents.models.search import DatabaseRecord


@dataclass
class PhaseRange:
    """Температурный диапазон для конкретной фазы."""

    phase: str  # 's', 'l', 'g'
    tmin: float
    tmax: float
    priority: int  # Приоритет выбора (1 - наивысший)


class PhaseBasedTemperatureStage(FilterStage):
    """
    Умная фильтрация с разделением температурного диапазона по фазам.

    Алгоритм:
    1. Анализирует запрошенный диапазон [T_user_min, T_user_max]
    2. Определяет типичные точки фазовых переходов из записей
    3. Разделяет диапазон на поддиапазоны для каждой фазы:
       - [T_user_min, T_melt) → твердая (s)
       - [T_melt, T_boil) → жидкая (l)
       - [T_boil, T_user_max] → газовая (g)
    4. Для каждого поддиапазона выбирает наилучшую запись соответствующей фазы
    5. Исключает ионизированные формы (если не указано явно пользователем)
    """

    def __init__(
        self,
        exclude_ions: bool = True,
        max_records_per_phase: int = 1,
        reliability_weight: float = 0.6,
        coverage_weight: float = 0.4,
    ):
        """
        Args:
            exclude_ions: Исключать ли ионизированные формы (CO2(+g) и т.п.)
            max_records_per_phase: Максимум записей на одну фазу
            reliability_weight: Вес надёжности при выборе лучшей записи (0-1)
            coverage_weight: Вес температурного покрытия при выборе (0-1)
        """
        super().__init__()
        self.exclude_ions = exclude_ions
        self.max_records_per_phase = max_records_per_phase
        self.reliability_weight = reliability_weight
        self.coverage_weight = coverage_weight

    def filter(
        self, records: List[DatabaseRecord], context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Применяет умную фильтрацию с разделением по фазам.

        Args:
            records: Исходные записи из БД
            context: Контекст с температурным диапазоном пользователя

        Returns:
            Список записей, оптимально покрывающих диапазон по фазам
        """
        start_time = time.time()
        tmin_user, tmax_user = context.temperature_range

        # Шаг 1: Исключаем ионизированные формы
        if self.exclude_ions:
            records = self._filter_out_ions(records)

        if not records:
            self.last_stats = {
                "phase_ranges": [],
                "records_before": 0,
                "records_after": 0,
                "execution_time_ms": (time.time() - start_time) * 1000,
                "warning": "No records after ion filtering",
            }
            return []

        initial_count = len(records)

        # Шаг 2: Определяем характерные точки фазовых переходов
        phase_transition_points = self._find_phase_transitions(records)

        # Шаг 3: Разделяем пользовательский диапазон на фазовые поддиапазоны
        phase_ranges = self._split_temperature_range(
            tmin_user, tmax_user, phase_transition_points
        )

        # Шаг 4: Для каждого фазового диапазона выбираем лучшие записи
        selected_records = []
        phase_coverage = {}

        for phase_range in phase_ranges:
            best_records = self._select_best_records_for_phase(
                records, phase_range, context
            )
            selected_records.extend(best_records)
            phase_coverage[phase_range.phase] = {
                "range": (phase_range.tmin, phase_range.tmax),
                "records_found": len(best_records),
                "coverage": self._calculate_coverage_percentage(
                    best_records, phase_range.tmin, phase_range.tmax
                ),
            }

        # Удаляем дубликаты (если одна запись подходит для нескольких фаз)
        selected_records = self._remove_duplicates(selected_records)

        execution_time = (time.time() - start_time) * 1000

        # Формируем детальную статистику
        self.last_stats = {
            "records_before": initial_count,
            "records_after": len(selected_records),
            "ions_excluded": self.exclude_ions,
            "phase_ranges_detected": len(phase_ranges),
            "phase_ranges": [
                {
                    "phase": pr.phase,
                    "tmin": pr.tmin,
                    "tmax": pr.tmax,
                    "priority": pr.priority,
                }
                for pr in phase_ranges
            ],
            "phase_coverage": phase_coverage,
            "phase_transitions": phase_transition_points,
            "execution_time_ms": execution_time,
            "filter_efficiency": (
                (initial_count - len(selected_records)) / initial_count * 100
                if initial_count > 0
                else 0
            ),
        }

        return selected_records

    def _filter_out_ions(self, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """
        Исключает ионизированные формы веществ.

        Ионные формы определяются по наличию +/- в скобках в формуле:
        - CO2(+g) - ион
        - CO2(g) - нейтральная форма
        - H2O(+) - ион
        """
        non_ion_records = []

        for record in records:
            if not self._is_ionic_form(record.formula):
                non_ion_records.append(record)

        return non_ion_records

    def _is_ionic_form(self, formula: str) -> bool:
        """
        Проверяет, является ли формула ионизированной.

        Паттерны ионных форм:
        - (+ ), (+g), (+l), (+s)
        - (- ), (-g), (-l), (-s)
        - (+2), (-3) и т.д.
        """
        # Поиск зарядов в скобках
        ion_pattern = r"\([+-]\d*[glsaq]?\)"
        return bool(re.search(ion_pattern, formula))

    def _find_phase_transitions(
        self, records: List[DatabaseRecord]
    ) -> Dict[str, float]:
        """
        Определяет характерные точки фазовых переходов из записей.

        Использует MeltingPoint и BoilingPoint из записей для определения
        типичных температур переходов для данного вещества.

        Returns:
            Dict с ключами 'melting_point' и 'boiling_point'
        """
        melting_points = []
        boiling_points = []

        for record in records:
            if record.tmelt is not None and record.tmelt > 0:
                melting_points.append(record.tmelt)
            if record.tboil is not None and record.tboil > 0:
                boiling_points.append(record.tboil)

        # Берём медианные значения (более устойчивы к выбросам)
        transitions = {}

        if melting_points:
            melting_points.sort()
            transitions["melting_point"] = melting_points[len(melting_points) // 2]

        if boiling_points:
            boiling_points.sort()
            transitions["boiling_point"] = boiling_points[len(boiling_points) // 2]

        return transitions

    def _split_temperature_range(
        self, tmin: float, tmax: float, phase_transitions: Dict[str, float]
    ) -> List[PhaseRange]:
        """
        Разделяет температурный диапазон на фазовые поддиапазоны.

        Логика:
        - Если T_max < T_melt → только твердая фаза
        - Если T_min > T_boil → только газовая фаза
        - Если диапазон пересекает переходы → несколько фаз

        Args:
            tmin: Минимальная температура пользователя (K)
            tmax: Максимальная температура пользователя (K)
            phase_transitions: Точки фазовых переходов

        Returns:
            Список PhaseRange для покрытия диапазона
        """
        ranges = []
        t_melt = phase_transitions.get("melting_point")
        t_boil = phase_transitions.get("boiling_point")

        # Случай 1: Нет информации о переходах - возвращаем весь диапазон без фазы
        if t_melt is None and t_boil is None:
            # Попробуем угадать по температуре
            if tmax < 400:  # Вероятно, твердое или жидкое
                ranges.append(PhaseRange("s", tmin, tmax, priority=1))
            elif tmin > 1500:  # Вероятно, газ
                ranges.append(PhaseRange("g", tmin, tmax, priority=1))
            else:
                ranges.append(PhaseRange("l", tmin, tmax, priority=1))
            return ranges

        # Случай 2: Есть точка плавления
        if t_melt is not None:
            # Твердая фаза до точки плавления
            if tmin < t_melt and tmax >= tmin:
                solid_tmax = min(t_melt, tmax)
                ranges.append(PhaseRange("s", tmin, solid_tmax, priority=1))

        # Случай 3: Жидкая фаза между плавлением и кипением
        if t_melt is not None and t_boil is not None:
            liquid_tmin = max(t_melt, tmin)
            liquid_tmax = min(t_boil, tmax)
            if liquid_tmin < liquid_tmax:
                ranges.append(PhaseRange("l", liquid_tmin, liquid_tmax, priority=2))
        elif t_melt is not None and t_boil is None:
            # Нет точки кипения - жидкость до конца диапазона
            liquid_tmin = max(t_melt, tmin)
            if liquid_tmin < tmax:
                ranges.append(PhaseRange("l", liquid_tmin, tmax, priority=2))

        # Случай 4: Газовая фаза выше точки кипения
        if t_boil is not None:
            if tmax > t_boil and tmin < tmax:
                gas_tmin = max(t_boil, tmin)
                ranges.append(PhaseRange("g", gas_tmin, tmax, priority=3))

        # Если не нашли ни одного диапазона, создаём универсальный
        if not ranges:
            # Определяем фазу по температуре
            avg_temp = (tmin + tmax) / 2
            if t_melt and avg_temp < t_melt:
                phase = "s"
            elif t_boil and avg_temp > t_boil:
                phase = "g"
            else:
                phase = "l"
            ranges.append(PhaseRange(phase, tmin, tmax, priority=1))

        return ranges

    def _select_best_records_for_phase(
        self,
        records: List[DatabaseRecord],
        phase_range: PhaseRange,
        context: FilterContext,
    ) -> List[DatabaseRecord]:
        """
        Выбирает лучшие записи для конкретной фазы и температурного диапазона.

        Критерии:
        1. Фаза записи соответствует требуемой
        2. Температурный диапазон записи покрывает phase_range
        3. Надёжность данных (ReliabilityClass)
        4. Полнота термодинамических данных

        Returns:
            Список лучших записей (до max_records_per_phase штук)
        """
        candidates = []

        for record in records:
            # Проверяем соответствие фазы
            if not self._matches_phase(record, phase_range.phase):
                continue

            # Проверяем температурное покрытие
            coverage = self._calculate_temperature_overlap(
                record, phase_range.tmin, phase_range.tmax
            )

            if coverage <= 0:
                continue

            # Рассчитываем общий score
            score = self._calculate_record_score(record, coverage)

            candidates.append((record, score))

        # Сортируем по убыванию score
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Берём топ-N записей
        return [rec for rec, _ in candidates[: self.max_records_per_phase]]

    def _matches_phase(self, record: DatabaseRecord, target_phase: str) -> bool:
        """
        Проверяет, соответствует ли фаза записи целевой фазе.

        Учитывает:
        - Поле Phase в записи
        - Фазу из формулы H2O(g)
        """
        record_phase = record.phase

        # Извлекаем фазу из формулы, если не указана явно
        if not record_phase or record_phase in ("?", "NULL", ""):
            record_phase = self._extract_phase_from_formula(record.formula)

        # Нормализуем фазы
        phase_map = {
            "s": "s",
            "solid": "s",
            "cr": "s",
            "crystalline": "s",
            "l": "l",
            "liquid": "l",
            "g": "g",
            "gas": "g",
            "vapor": "g",
            "aq": "aq",
            "aqueous": "aq",
        }

        normalized_record = phase_map.get(record_phase, record_phase)
        normalized_target = phase_map.get(target_phase, target_phase)

        return normalized_record == normalized_target

    def _extract_phase_from_formula(self, formula: str) -> Optional[str]:
        """Извлекает фазу из формулы типа H2O(g)."""
        match = re.search(r"\(([glsaq])\)", formula)
        return match.group(1) if match else None

    def _calculate_temperature_overlap(
        self, record: DatabaseRecord, tmin: float, tmax: float
    ) -> float:
        """
        Рассчитывает процент перекрытия температурных диапазонов.

        Returns:
            Процент перекрытия (0.0 - 1.0)
        """
        # Диапазон записи
        rec_tmin = record.tmin
        rec_tmax = record.tmax

        # Находим пересечение
        overlap_min = max(rec_tmin, tmin)
        overlap_max = min(rec_tmax, tmax)

        if overlap_min >= overlap_max:
            return 0.0

        overlap_length = overlap_max - overlap_min
        target_length = tmax - tmin

        return overlap_length / target_length if target_length > 0 else 0.0

    def _calculate_record_score(self, record: DatabaseRecord, coverage: float) -> float:
        """
        Рассчитывает общий score записи для приоритизации.

        Score = reliability_weight * reliability_score + coverage_weight * coverage

        Args:
            record: Запись БД
            coverage: Процент температурного покрытия (0-1)

        Returns:
            Общий score (0-1)
        """
        # Надёжность: ReliabilityClass 1 → score=1.0, class 5 → score=0.0
        reliability_score = self._calculate_reliability_score(record)

        # Взвешенная сумма
        total_score = (
            self.reliability_weight * reliability_score
            + self.coverage_weight * coverage
        )

        return total_score

    def _calculate_reliability_score(self, record: DatabaseRecord) -> float:
        """
        Преобразует ReliabilityClass в score (1.0 - лучший, 0.0 - худший).

        ReliabilityClass: 1 (best) → 2 → 3 → 0 → 4 → 5 (worst)
        """
        reliability_map = {1: 1.0, 2: 0.8, 3: 0.6, 0: 0.4, 4: 0.2, 5: 0.0}

        return reliability_map.get(record.reliability_class, 0.5)

    def _calculate_coverage_percentage(
        self, records: List[DatabaseRecord], tmin: float, tmax: float
    ) -> float:
        """
        Рассчитывает процент покрытия диапазона записями.

        Returns:
            Процент покрытия (0-100)
        """
        if not records:
            return 0.0

        # Находим объединение всех диапазонов записей
        covered_ranges = []
        for record in records:
            overlap_min = max(record.tmin, tmin)
            overlap_max = min(record.tmax, tmax)
            if overlap_min < overlap_max:
                covered_ranges.append((overlap_min, overlap_max))

        if not covered_ranges:
            return 0.0

        # Объединяем пересекающиеся диапазоны
        covered_ranges.sort()
        merged = [covered_ranges[0]]

        for current in covered_ranges[1:]:
            last = merged[-1]
            if current[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)

        # Считаем общее покрытие
        total_covered = sum(end - start for start, end in merged)
        total_range = tmax - tmin

        return (total_covered / total_range * 100) if total_range > 0 else 0.0

    def _remove_duplicates(self, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """
        Удаляет дубликаты записей по уникальным идентификаторам.

        Сохраняет порядок записей.
        """
        seen_ids = set()
        unique_records = []

        for record in records:
            # Используем id или комбинацию formula + phase + tmin
            record_id = (
                record.id
                if record.id
                else (record.formula, record.phase, record.tmin, record.tmax)
            )

            if record_id not in seen_ids:
                seen_ids.add(record_id)
                unique_records.append(record)

        return unique_records

    def get_stage_name(self) -> str:
        return "Умная фильтрация по фазам и температуре"
