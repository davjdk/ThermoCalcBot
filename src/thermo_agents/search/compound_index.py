"""
Высокопроизводительный индексатор соединений для быстрых поисков.

Предоставляет индексацию и кэширование для оптимизации поиска
химических соединений в базе данных.
"""

from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass
import time
import re
from collections import defaultdict

from ..filtering.constants import (
    COMPOUND_INDEX_CACHE_SIZE,
    FORMULA_PREFIX_CACHE_SIZE,
    PRECOMPUTED_PHASE_TRANSITIONS,
)
from ..models.search import DatabaseRecord


@dataclass
class CompoundIndex:
    """Индекс для быстрого поиска соединений."""

    formula_prefixes: Dict[str, List[int]]  # Префиксы формул -> ID записей
    compound_names: Dict[str, List[int]]  # Названия соединений -> ID записей
    reliability_index: Dict[int, int]  # ID -> класс надежности
    phase_index: Dict[str, List[int]]  # Фазы -> ID записей
    temperature_index: Dict[Tuple[float, float], List[int]]  # Темп. диапазоны -> ID
    last_updated: float
    total_records: int


class CompoundIndexer:
    """
    Высокопроизводительный индексатор соединений с кэшированием.

    Особенности:
    - Индексация по префиксам формул для быстрых поисков
    - Кэширование результатов поиска
    - Оптимизированные алгоритмы для больших наборов данных
    """

    def __init__(self, cache_size: int = COMPOUND_INDEX_CACHE_SIZE):
        self.cache_size = cache_size
        self._index: Optional[CompoundIndex] = None
        self._prefix_cache: Dict[str, List[int]] = {}
        self._search_cache: Dict[str, Tuple[List[int], float]] = {}

        # Метрики производительности
        self._cache_hits = 0
        self._cache_misses = 0
        self._search_count = 0

        # Предвычисленные паттерны для распространенных соединений
        self._common_patterns = self._initialize_common_patterns()

    def _initialize_common_patterns(self) -> Dict[str, List[str]]:
        """Инициализировать предвычисленные паттерны для распространенных соединений."""
        return {
            "H2O": ["H2O", "H2O(l)", "H2O(g)", "H2O(s)", "WATER"],
            "CO2": ["CO2", "CO2(g)", "CARBON_DIOXIDE"],
            "NH3": ["NH3", "NH3(g)", "AMMONIA"],
            "CH4": ["CH4", "CH4(g)", "METHANE"],
            "O2": ["O2", "O2(g)", "OXYGEN"],
            "N2": ["N2", "N2(g)", "NITROGEN"],
            "H2": ["H2", "H2(g)", "HYDROGEN"],
        }

    def build_index(self, records: List[DatabaseRecord]) -> None:
        """
        Построить индекс для набора записей.

        Args:
            records: Список записей для индексации
        """
        start_time = time.time()

        formula_prefixes = defaultdict(list)
        compound_names = defaultdict(list)
        reliability_index = {}
        phase_index = defaultdict(list)
        temperature_index = defaultdict(list)

        for record in records:
            if not record.id:
                continue

            # Индексация по префиксам формул
            self._index_formula_prefixes(record.formula, record.id, formula_prefixes)

            # Индексация по названиям (если доступны)
            if hasattr(record, 'first_name') and record.first_name:
                names = self._extract_compound_names(record.first_name)
                for name in names:
                    compound_names[name.upper()].append(record.id)

            # Индексация по надежности
            if record.reliability_class:
                reliability_index[record.id] = record.reliability_class

            # Индексация по фазам
            if record.phase:
                phase_index[record.phase].append(record.id)

            # Индексация по температурным диапазонам
            if record.tmin is not None and record.tmax is not None:
                # Создаем coarse-grained индекс по диапазонам (с шагом 100K)
                tmin_bucket = int(record.tmin // 100) * 100
                tmax_bucket = int(record.tmax // 100) * 100
                temperature_index[(tmin_bucket, tmax_bucket)].append(record.id)

        # Сохраняем индекс
        self._index = CompoundIndex(
            formula_prefixes=dict(formula_prefixes),
            compound_names=dict(compound_names),
            reliability_index=reliability_index,
            phase_index=dict(phase_index),
            temperature_index=dict(temperature_index),
            last_updated=time.time(),
            total_records=len(records)
        )

        # Очищаем кэши при перестроении индекса
        self._prefix_cache.clear()
        self._search_cache.clear()

        build_time = time.time() - start_time
        print(f"Index built in {build_time:.3f}s for {len(records)} records")

    def _index_formula_prefixes(
        self,
        formula: str,
        record_id: int,
        prefix_index: Dict[str, List[int]]
    ) -> None:
        """
        Проиндексировать префиксы формулы для быстрых поисков.

        Args:
            formula: Химическая формула
            record_id: ID записи
            prefix_index: Индекс префиксов для обновления
        """
        if not formula:
            return

        # Извлекаем атомные префиксы (H, He, Li, Be, B, C, N, O, F, Ne, etc.)
        elements = re.findall(r'[A-Z][a-z]?', formula)

        # Создаем префиксы разной длины
        for i in range(1, min(len(elements), 4) + 1):
            prefix = ''.join(elements[:i])
            prefix_index[prefix].append(record_id)

        # Добавляем полную формулу
        prefix_index[formula].append(record_id)

        # Добавляем формулу с фазой (если есть)
        if '(' in formula and ')' in formula:
            base_formula = formula.split('(')[0]
            prefix_index[base_formula].append(record_id)

    def _extract_compound_names(self, name_str: str) -> List[str]:
        """Извлечь возможные названия соединения из строки."""
        if not name_str:
            return []

        names = []

        # Базовое название
        names.append(name_str.strip())

        # Разделение по запятым и точкам с запятой
        for separator in [',', ';']:
            if separator in name_str:
                names.extend([n.strip() for n in name_str.split(separator)])

        # Удаление дубликатов и пустых строк
        return list(set(filter(None, names)))

    def search_by_formula_prefix(self, prefix: str) -> List[int]:
        """
        Быстрый поиск по префиксу формулы.

        Args:
            prefix: Префикс формулы для поиска

        Returns:
            Список ID записей, соответствующих префиксу
        """
        if not self._index:
            return []

        # Проверяем кэш
        if prefix in self._prefix_cache:
            self._cache_hits += 1
            return self._prefix_cache[prefix].copy()

        self._cache_misses += 1

        # Поиск в индексе
        matching_ids = []

        # Прямой поиск префикса
        if prefix in self._index.formula_prefixes:
            matching_ids.extend(self._index.formula_prefixes[prefix])

        # Поиск по частичным совпадениям
        for indexed_prefix, ids in self._index.formula_prefixes.items():
            if indexed_prefix.startswith(prefix):
                matching_ids.extend(ids)

        # Удаляем дубликаты и кэшируем результат
        unique_ids = list(set(matching_ids))

        # Кэшируем результат
        if len(self._prefix_cache) < self.cache_size:
            self._prefix_cache[prefix] = unique_ids.copy()

        return unique_ids

    def search_common_compound(self, formula: str) -> List[int]:
        """
        Поиск распространенных соединений с предвычисленными паттернами.

        Args:
            formula: Формула для поиска

        Returns:
            Список ID записей для распространенного соединения
        """
        if not self._index:
            return []

        # Проверяем предвычисленные паттерны
        formula_clean = re.sub(r'\([^)]*\)', '', formula)  # Удаляем фазовые обозначения

        if formula_clean in self._common_patterns:
            patterns = self._common_patterns[formula_clean]
            matching_ids = []

            for pattern in patterns:
                ids = self.search_by_formula_prefix(pattern)
                matching_ids.extend(ids)

            return list(set(matching_ids))

        # Если не в распространенных, используем обычный поиск
        return self.search_by_formula_prefix(formula)

    def filter_by_reliability(
        self,
        record_ids: List[int],
        max_reliability_class: int = 3
    ) -> List[int]:
        """
        Отфильтровать записи по классу надежности.

        Args:
            record_ids: Список ID записей
            max_reliability_class: Максимальный допустимый класс надежности

        Returns:
            Отфильтрованный список ID записей
        """
        if not self._index:
            return record_ids

        filtered_ids = []
        for record_id in record_ids:
            reliability = self._index.reliability_index.get(record_id, 9)  # По умолчанию плохая надежность
            if reliability <= max_reliability_class:
                filtered_ids.append(record_id)

        return filtered_ids

    def filter_by_temperature_range(
        self,
        record_ids: List[int],
        temperature_range: Tuple[float, float]
    ) -> List[int]:
        """
        Отфильтровать записи по температурному диапазону.

        Args:
            record_ids: Список ID записей
            temperature_range: Температурный диапазон (tmin, tmax)

        Returns:
            Отфильтрованный список ID записей
        """
        if not self._index:
            return record_ids

        tmin, tmax = temperature_range
        filtered_ids = []

        # Используем coarse-grained индекс для быстрой фильтрации
        tmin_bucket = int(tmin // 100) * 100
        tmax_bucket = int(tmax // 100) * 100

        # Проверяем пересечение с температурными бакетами
        for bucket_start, bucket_end in range(tmin_bucket - 100, tmax_bucket + 101, 100):
            bucket_key = (bucket_start, bucket_end)
            if bucket_key in self._index.temperature_index:
                bucket_ids = self._index.temperature_index[bucket_key]
                filtered_ids.extend([rid for rid in bucket_ids if rid in record_ids])

        return list(set(filtered_ids))

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Получить метрики производительности индексатора."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (
            self._cache_hits / total_requests * 100
            if total_requests > 0 else 0
        )

        return {
            "cache_hit_rate": hit_rate,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "prefix_cache_size": len(self._prefix_cache),
            "search_cache_size": len(self._search_cache),
            "index_built": self._index is not None,
            "total_records": self._index.total_records if self._index else 0,
            "search_count": self._search_count,
        }

    def clear_cache(self) -> None:
        """Очистить все кэши."""
        self._prefix_cache.clear()
        self._search_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def is_index_fresh(self, max_age_seconds: int = 3600) -> bool:
        """
        Проверить, свежий ли индекс.

        Args:
            max_age_seconds: Максимальный возраст индекса в секундах

        Returns:
            True если индекс свежий, иначе False
        """
        if not self._index:
            return False

        age = time.time() - self._index.last_updated
        return age < max_age_seconds