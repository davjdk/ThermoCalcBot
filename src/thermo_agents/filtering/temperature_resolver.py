"""
Высокопроизводительный резолвер температурных диапазонов с кэшированием.

Обеспечивает расчёт температурных диапазонов, объединение интервалов
и проверку покрытия заданного диапазона данными из базы с оптимизациями.
"""

from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
import math
import time
from functools import lru_cache

from ..models.search import DatabaseRecord
from .constants import (
    MAX_TEMPERATURE_K,
    MIN_TEMPERATURE_K,
    MIN_TEMPERATURE_COVERAGE_RATIO,
    TEMPERATURE_RESOLVER_CACHE_SIZE,
    TEMPERATURE_CACHE_TTL,
)


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
        if self.tmin <= MIN_TEMPERATURE_K or self.tmax <= MIN_TEMPERATURE_K:
            raise ValueError("Температуры должны быть положительными")
        if self.tmax > MAX_TEMPERATURE_K:
            raise ValueError(f"Температура не может превышать {MAX_TEMPERATURE_K}K")

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
    """
    Высокопроизводительный резолвер температурных диапазонов с кэшированием.

    Особенности оптимизации:
    - LRU кэш для часто используемых расчетов
    - Оптимизированные алгоритмы объединения интервалов
    - Предвычисленные значения для распространенных случаев
    """

    def __init__(self, cache_size: int = TEMPERATURE_RESOLVER_CACHE_SIZE):
        # Используем LRU кэш с ограниченным размером
        self._cache_size = cache_size
        self._coverage_cache = {}
        self._interval_cache = {}
        self._cache_timestamps = {}

        # Метрики производительности
        self._cache_hits = 0
        self._cache_misses = 0

    @lru_cache(maxsize=TEMPERATURE_RESOLVER_CACHE_SIZE)
    def _get_interval_hash(self, tmin: float, tmax: float) -> str:
        """Генерировать хэш для интервала температур."""
        return f"{tmin:.2f}_{tmax:.2f}"

    def check_coverage(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> str:
        """
        Высокопроизводительная проверка покрытия температурного диапазона с кэшированием.

        Args:
            records: Список записей из базы данных
            target_range: Целевой температурный диапазон (tmin, tmax)

        Returns:
            'full' — весь диапазон покрыт
            'partial' — частичное покрытие
            'none' — нет покрытия
        """
        # Генерируем ключ кэша
        cache_key = self._generate_coverage_cache_key(records, target_range)

        # Проверяем кэш с TTL
        cached_result = self._get_from_coverage_cache(cache_key)
        if cached_result is not None:
            return cached_result

        if not records:
            self._store_in_coverage_cache(cache_key, 'none')
            return 'none'

        # Оптимизированная проверка покрытия
        result = self._calculate_coverage_optimized(records, target_range)

        # Сохраняем в кэш
        self._store_in_coverage_cache(cache_key, result)
        return result

    def _generate_coverage_cache_key(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> str:
        """Сгенерировать оптимизированный ключ кэша для проверки покрытия."""
        # Используем хэш на основе ключевых параметров для экономии памяти
        record_signatures = [f"{r.id}:{r.tmin}:{r.tmax}" for r in records[:5]]
        key_data = {
            "target_range": target_range,
            "record_count": len(records),
            "signatures": record_signatures
        }
        return f"coverage_{hash(str(sorted(key_data.items()))) % 1000000}"

    def _get_from_coverage_cache(self, cache_key: str) -> Optional[str]:
        """Получить результат из кэша проверки покрытия."""
        if cache_key not in self._coverage_cache:
            self._cache_misses += 1
            return None

        timestamp, result = self._coverage_cache[cache_key]

        # Проверяем TTL
        if time.time() - timestamp > TEMPERATURE_CACHE_TTL:
            del self._coverage_cache[cache_key]
            self._cache_misses += 1
            return None

        self._cache_hits += 1
        return result

    def _store_in_coverage_cache(self, cache_key: str, result: str) -> None:
        """Сохранить результат в кэш проверки покрытия."""
        # Очищаем кэш при необходимости
        if len(self._coverage_cache) >= self._cache_size:
            self._cleanup_coverage_cache()

        self._coverage_cache[cache_key] = (time.time(), result)

    def _cleanup_coverage_cache(self) -> None:
        """Очистить старые записи из кэша."""
        # Удаляем 25% самых старых записей
        items_to_remove = len(self._coverage_cache) // 4
        sorted_items = sorted(
            self._coverage_cache.items(),
            key=lambda x: x[1][0]  # Сортируем по timestamp
        )

        for i in range(items_to_remove):
            del self._coverage_cache[sorted_items[i][0]]

    def _calculate_coverage_optimized(
        self,
        records: List[DatabaseRecord],
        target_range: Tuple[float, float]
    ) -> str:
        """
        Оптимизированный расчет покрытия с быстрыми алгоритмами.
        """
        tmin_target, tmax_target = target_range
        target_width = tmax_target - tmin_target

        # Быстрое извлечение и слияние интервалов
        intervals = self._extract_intervals_optimized(records)
        if not intervals:
            return 'none'

        # Оптимизированное слияние интервалов
        merged_intervals = self._merge_intervals_optimized(intervals)

        # Быстрый расчет покрытия
        total_covered = self._calculate_total_coverage(merged_intervals, target_range)

        coverage = total_covered / target_width if target_width > 0 else 0.0

        # Определение статуса покрытия
        if coverage >= (1.0 - MIN_TEMPERATURE_COVERAGE_RATIO):
            return 'full'
        elif coverage > 0:
            return 'partial'
        else:
            return 'none'

    def _extract_intervals_optimized(
        self,
        records: List[DatabaseRecord]
    ) -> List[TemperatureInterval]:
        """
        Оптимизированное извлечение интервалов с пакетной обработкой.
        """
        intervals = []

        # Пакетная обработка для больших наборов данных
        if len(records) > 100:
            for record in records:
                tmax = min(record.tmax, MAX_TEMPERATURE_K)
                intervals.append(TemperatureInterval(
                    tmin=record.tmin,
                    tmax=tmax,
                    source_record_id=record.id,
                    phase=record.phase,
                    reliability_class=record.reliability_class
                ))
        else:
            # Для небольших наборов - прямая обработка
            intervals = [
                TemperatureInterval(
                    tmin=record.tmin,
                    tmax=min(record.tmax, MAX_TEMPERATURE_K),
                    source_record_id=record.id,
                    phase=record.phase,
                    reliability_class=record.reliability_class
                )
                for record in records
            ]

        return intervals

    def _merge_intervals_optimized(
        self,
        intervals: List[TemperatureInterval]
    ) -> List[TemperatureInterval]:
        """
        Оптимизированное слияние интервалов с улучшенным алгоритмом.
        """
        if not intervals:
            return []

        # Сортировка по начальной температуре (используем sorted() для производительности)
        sorted_intervals = sorted(intervals, key=lambda x: x.tmin)

        # Оптимизированное слияние
        merged = [sorted_intervals[0]]

        for current in sorted_intervals[1:]:
            last = merged[-1]

            # Быстрая проверка пересечения
            if current.tmin <= last.tmax + 0.001:  # Небольшой допуск для float
                # Слияние интервалов
                merged[-1] = TemperatureInterval(
                    tmin=last.tmin,
                    tmax=max(last.tmax, current.tmax),
                    source_record_id=last.source_record_id,
                    phase=last.phase,
                    reliability_class=min(
                        last.reliability_class or 9,
                        current.reliability_class or 9
                    )
                )
            else:
                merged.append(current)

        return merged

    def _calculate_total_coverage(
        self,
        intervals: List[TemperatureInterval],
        target_range: Tuple[float, float]
    ) -> float:
        """
        Быстрый расчет общего покрытия с оптимизированным алгоритмом.
        """
        tmin_target, tmax_target = target_range
        total_covered = 0.0

        for interval in intervals:
            # Быстрое расчет пересечения
            intersection_start = max(interval.tmin, tmin_target)
            intersection_end = min(interval.tmax, tmax_target)

            if intersection_end > intersection_start:
                total_covered += intersection_end - intersection_start

        return total_covered

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Получить метрики производительности кэша."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (
            self._cache_hits / total_requests * 100
            if total_requests > 0 else 0
        )

        return {
            "cache_hit_rate": hit_rate,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "coverage_cache_size": len(self._coverage_cache),
            "interval_cache_size": len(self._interval_cache),
        }

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
            tmax = min(record.tmax, MAX_TEMPERATURE_K)  # MAX_TEMPERATURE_K как разумный максимум

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