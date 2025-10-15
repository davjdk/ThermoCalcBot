"""
Резолвер температурных диапазонов и проверки покрытия.

Обеспечивает расчёт температурных диапазонов, объединение интервалов
и проверку покрытия заданного диапазона данными из базы.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
import math

from ..models.search import DatabaseRecord


@dataclass
class TemperatureInterval:
    """Интервал температур с дополнительной информацией."""
    tmin: float
    tmax: float
    source_record_id: Optional[int] = None
    phase: Optional[str] = None
    reliability_class: Optional[int] = None

    def __post_init__(self):
        """Валидация интервала."""
        if self.tmin > self.tmax:
            raise ValueError("Минимальная температура не может быть больше максимальной")
        if self.tmin <= 0 or self.tmax <= 0:
            raise ValueError("Температуры должны быть положительными")

    @property
    def width(self) -> float:
        """Ширина интервала."""
        return self.tmax - self.tmin

    def contains(self, temperature: float) -> bool:
        """Проверяет, содержится ли температура в интервале."""
        return self.tmin <= temperature <= self.tmax

    def overlaps_with(self, other: 'TemperatureInterval') -> bool:
        """Проверяет пересечение с другим интервалом."""
        return not (self.tmax < other.tmin or self.tmin > other.tmax)

    def intersection(self, other: 'TemperatureInterval') -> Optional['TemperatureInterval']:
        """Возвращает пересечение с другим интервалом."""
        if not self.overlaps_with(other):
            return None

        return TemperatureInterval(
            tmin=max(self.tmin, other.tmin),
            tmax=min(self.tmax, other.tmax)
        )

    def union(self, other: 'TemperatureInterval') -> 'TemperatureInterval':
        """Возвращает объединение с другим интервалом."""
        if not self.overlaps_with(other):
            raise ValueError("Интервалы не пересекаются")

        return TemperatureInterval(
            tmin=min(self.tmin, other.tmin),
            tmax=max(self.tmax, other.tmax),
            # Сохраняем более надёжные данные
            source_record_id=self.source_record_id if (self.reliability_class or 9) <= (other.reliability_class or 9) else other.source_record_id,
            phase=self.phase if (self.reliability_class or 9) <= (other.reliability_class or 9) else other.phase,
            reliability_class=min(self.reliability_class or 9, other.reliability_class or 9)
        )


class TemperatureResolver:
    """Расчёт температурных диапазонов и проверка покрытия."""

    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def check_coverage(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> str:
        """
        Проверка покрытия температурного диапазона.

        Args:
            records: Список записей из базы данных
            target_range: Целевой температурный диапазон (tmin, tmax)

        Returns:
            'full' — весь диапазон покрыт
            'partial' — частичное покрытие
            'none' — нет покрытия
        """
        cache_key = f"coverage_{len(records)}_{target_range[0]}_{target_range[1]}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not records:
            self._cache[cache_key] = 'none'
            return 'none'

        tmin_target, tmax_target = target_range
        target_width = tmax_target - tmin_target

        # Объединить все диапазоны записей
        intervals = self._extract_intervals(records)
        if not intervals:
            self._cache[cache_key] = 'none'
            return 'none'

        # Объединить пересекающиеся интервалы
        merged_intervals = self._merge_intervals(intervals)

        # Рассчитать общее покрытие
        total_covered = 0.0
        for interval in merged_intervals:
            # Пересечение с целевым диапазоном
            intersection_start = max(interval.tmin, tmin_target)
            intersection_end = min(interval.tmax, tmax_target)
            if intersection_end > intersection_start:
                total_covered += intersection_end - intersection_start

        coverage = total_covered / target_width if target_width > 0 else 0.0

        result = 'none'
        if coverage >= 0.99:  # 99% покрытия = полное
            result = 'full'
        elif coverage > 0:
            result = 'partial'

        self._cache[cache_key] = result
        return result

    def get_covered_ranges(
        self,
        records: List[DatabaseRecord],
        target_range: Optional[Tuple[float, float]] = None
    ) -> List[TemperatureInterval]:
        """
        Получить объединённые температурные диапазоны из записей.

        Args:
            records: Список записей из базы данных
            target_range: Опциональный целевой диапазон для ограничения

        Returns:
            Список объединённых интервалов
        """
        intervals = self._extract_intervals(records)
        if not intervals:
            return []

        merged_intervals = self._merge_intervals(intervals)

        # Если задан целевой диапазон, ограничиваем интервалы
        if target_range:
            tmin_target, tmax_target = target_range
            limited_intervals = []
            for interval in merged_intervals:
                limited_start = max(interval.tmin, tmin_target)
                limited_end = min(interval.tmax, tmax_target)
                if limited_end > limited_start:
                    limited_interval = TemperatureInterval(
                        tmin=limited_start,
                        tmax=limited_end,
                        phase=interval.phase,
                        reliability_class=interval.reliability_class
                    )
                    limited_intervals.append(limited_interval)
            merged_intervals = limited_intervals

        return merged_intervals

    def get_gaps(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> List[TemperatureInterval]:
        """
        Найти пробелы в покрытии температурного диапазона.

        Args:
            records: Список записей из базы данных
            target_range: Целевой температурный диапазон

        Returns:
            Список интервалов без покрытия
        """
        covered_ranges = self.get_covered_ranges(records, target_range)
        tmin_target, tmax_target = target_range

        if not covered_ranges:
            return [TemperatureInterval(tmin_target, tmax_target)]

        # Сортируем по начальной температуре
        covered_ranges.sort(key=lambda x: x.tmin)

        gaps = []
        current_temp = tmin_target

        for interval in covered_ranges:
            if interval.tmin > current_temp:
                # Есть пробел перед этим интервалом
                gaps.append(TemperatureInterval(current_temp, interval.tmin))
            current_temp = max(current_temp, interval.tmax)

        # Проверяем пробел после последнего интервала
        if current_temp < tmax_target:
            gaps.append(TemperatureInterval(current_temp, tmax_target))

        return gaps

    def _extract_intervals(self, records: List[DatabaseRecord]) -> List[TemperatureInterval]:
        """
        Извлечь температурные интервалы из записей.

        Note: According to database analysis, Tmin and Tmax are 100% populated,
        so we don't need to handle NULL values.
        """
        intervals = []
        for record in records:
            # В базе данных Tmin и Tmax всегда заполнены (100% покрытие)
            # Ограничиваем очень большие значения разумным максимумом
            tmax = min(record.tmax, 10000.0)  # 10000K как разумный максимум

            interval = TemperatureInterval(
                tmin=record.tmin,
                tmax=tmax,
                source_record_id=record.id,
                phase=record.phase,
                reliability_class=record.reliability_class
            )
            intervals.append(interval)

        return intervals

    def _merge_intervals(self, intervals: List[TemperatureInterval]) -> List[TemperatureInterval]:
        """Объединить пересекающиеся интервалы."""
        if not intervals:
            return []

        # Сортируем по начальной температуре
        sorted_intervals = sorted(intervals, key=lambda x: x.tmin)
        merged = [sorted_intervals[0]]

        for current in sorted_intervals[1:]:
            last = merged[-1]

            if current.tmin <= last.tmax:
                # Интервалы пересекаются или смежные, объединяем
                merged_interval = TemperatureInterval(
                    tmin=last.tmin,
                    tmax=max(last.tmax, current.tmax),
                    # Сохраняем лучшие данные
                    phase=last.phase if (last.reliability_class or 9) <= (current.reliability_class or 9) else current.phase,
                    reliability_class=min(last.reliability_class or 9, current.reliability_class or 9)
                )
                merged[-1] = merged_interval
            else:
                merged.append(current)

        return merged

    def calculate_coverage_percentage(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> float:
        """
        Рассчитать процент покрытия температурного диапазона.

        Args:
            records: Список записей из базы данных
            target_range: Целевой температурный диапазон

        Returns:
            Процент покрытия (0.0 - 1.0)
        """
        tmin_target, tmax_target = target_range
        target_width = tmax_target - tmin_target

        if target_width <= 0:
            return 0.0

        covered_ranges = self.get_covered_ranges(records, target_range)
        total_covered = sum(interval.width for interval in covered_ranges)

        return min(total_covered / target_width, 1.0)

    def get_temperature_statistics(self, records: List[DatabaseRecord]) -> Dict[str, Any]:
        """
        Получить статистическую информацию о температурных данных.

        Args:
            records: Список записей из базы данных

        Returns:
            Словарь со статистической информацией
        """
        if not records:
            return {
                'total_records': 0,
                'records_with_temperatures': 0,
                'min_temperature': None,
                'max_temperature': None,
                'avg_range_width': 0.0,
                'total_coverage_width': 0.0
            }

        intervals = self._extract_intervals(records)
        merged_intervals = self._merge_intervals(intervals)

        stats = {
            'total_records': len(records),
            'records_with_temperatures': len(intervals),
            'unique_intervals': len(merged_intervals),
            'min_temperature': min(interval.tmin for interval in intervals),
            'max_temperature': max(interval.tmax for interval in intervals),
        }

        if intervals:
            stats['avg_range_width'] = sum(interval.width for interval in intervals) / len(intervals)
            stats['total_coverage_width'] = sum(interval.width for interval in merged_intervals)

        return stats

    def clear_cache(self) -> None:
        """Очистить кэш результатов."""
        self._cache.clear()