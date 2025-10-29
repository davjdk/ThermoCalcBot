"""
Performance Optimization Module for Stage 3.

This module provides performance optimization features for multi-record
calculations, including intelligent caching, lazy loading, and computational
optimizations.

Техническое описание:
Модуль оптимизации производительности для Этапа 3.
Предоставляет функции оптимизации для расчётов с множественными записями,
включая интеллектуальное кэширование, ленивую загрузку и вычислительные
оптимизации.

Основные функции:

1. Интеллектуальное кэширование результатов расчётов
2. Ленивая загрузка данных и вычислений
3. Векторизация операций для массивных расчётов
4. Оптимизация использования памяти
5. Мониторинг производительности и профилирование

Ключевые алгоритмы:

- LRU кэширование с адаптивным размером
- Предвычисление часто используемых значений
- Пакетная обработка температурных точек
- Оптимизированные численные методы интегрирования

Интеграция:
- Используется ThermodynamicCalculator для оптимизации расчётов
- Интегрируется с MultiPhaseCompoundData для кэширования данных
- Работает с RecordTransitionManager для быстрых переходов
"""

import time
import functools
import threading
from collections import OrderedDict, defaultdict
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass
import logging

import numpy as np

from ..models.search import MultiPhaseCompoundData, DatabaseRecord
from .thermodynamic_calculator import ThermodynamicProperties

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for optimization tracking."""

    calculation_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_time: float = 0.0
    average_time: float = 0.0
    cache_hit_rate: float = 0.0
    memory_usage_mb: float = 0.0

    def update_hit_rate(self):
        """Update cache hit rate."""
        total_requests = self.cache_hits + self.cache_misses
        self.cache_hit_rate = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0

    def update_average_time(self):
        """Update average calculation time."""
        if self.calculation_count > 0:
            self.average_time = self.total_time / self.calculation_count


class LRUCache:
    """Thread-safe LRU cache with adaptive sizing."""

    def __init__(self, max_size: int = 1000, cleanup_interval: int = 100):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items in cache
            cleanup_interval: Number of operations between cleanups
        """
        self.max_size = max_size
        self.cleanup_interval = cleanup_interval
        self._cache = OrderedDict()
        self._lock = threading.RLock()
        self._operations_count = 0

    def get(self, key: Any) -> Optional[Any]:
        """Get item from cache."""
        with self._lock:
            self._operations_count += 1

            if key not in self._cache:
                return None

            # Move to end (most recently used)
            value = self._cache.pop(key)
            self._cache[key] = value

            # Cleanup if needed
            if self._operations_count % self.cleanup_interval == 0:
                self._cleanup()

            return value

    def put(self, key: Any, value: Any) -> None:
        """Put item in cache."""
        with self._lock:
            self._operations_count += 1

            if key in self._cache:
                # Update existing item
                self._cache.pop(key)

            elif len(self._cache) >= self.max_size:
                # Remove least recently used item
                self._cache.popitem(last=False)

            self._cache[key] = value

            # Cleanup if needed
            if self._operations_count % self.cleanup_interval == 0:
                self._cleanup()

    def _cleanup(self):
        """Cleanup expired or least useful items."""
        # Remove items that haven't been accessed recently
        if len(self._cache) > self.max_size * 0.8:
            # Keep only 80% of most recently used items
            items_to_remove = len(self._cache) - int(self.max_size * 0.8)
            for _ in range(items_to_remove):
                self._cache.popitem(last=False)

    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)

    def clear(self):
        """Clear cache."""
        with self._lock:
            self._cache.clear()


class PerformanceOptimizer:
    """
    Performance optimizer for multi-record thermodynamic calculations.

    This class provides intelligent caching, lazy loading, and computational
    optimizations to improve performance of Stage 3 calculations.
    """

    def __init__(self, cache_size: int = 1000):
        """
        Initialize performance optimizer.

        Args:
            cache_size: Maximum size of LRU cache
        """
        self.property_cache = LRUCache(max_size=cache_size)
        self.transition_cache = LRUCache(max_size=cache_size // 2)
        self.integration_cache = LRUCache(max_size=cache_size // 4)

        self.metrics = PerformanceMetrics()
        self._lock = threading.RLock()

        logger.info(f"PerformanceOptimizer initialized with cache_size={cache_size}")

    def cached_property_calculation(
        self,
        calculator_func: Callable,
        record: DatabaseRecord,
        temperature: float
    ) -> ThermodynamicProperties:
        """
        Cached wrapper for thermodynamic property calculations.

        Args:
            calculator_func: Function to calculate properties
            record: Database record
            temperature: Temperature in Kelvin

        Returns:
            ThermodynamicProperties with caching
        """
        cache_key = f"prop_{record.id}_{temperature:.6f}"

        # Try cache first
        cached_result = self.property_cache.get(cache_key)
        if cached_result is not None:
            with self._lock:
                self.metrics.cache_hits += 1
                self.metrics.update_hit_rate()
            return cached_result

        # Calculate and cache
        with self._lock:
            self.metrics.cache_misses += 1
            self.metrics.update_hit_rate()

        start_time = time.time()
        result = calculator_func(record, temperature)
        calculation_time = time.time() - start_time

        # Update metrics
        with self._lock:
            self.metrics.calculation_count += 1
            self.metrics.total_time += calculation_time
            self.metrics.update_average_time()

        # Cache result
        self.property_cache.put(cache_key, result)

        return result

    def batch_property_calculation(
        self,
        calculator_func: Callable,
        record: DatabaseRecord,
        temperatures: List[float]
    ) -> List[ThermodynamicProperties]:
        """
        Batch calculation of properties for multiple temperatures.

        This method optimizes performance by:
        1. Checking cache for all temperatures first
        2. Grouping uncached temperatures for batch calculation
        3. Using vectorized operations where possible

        Args:
            calculator_func: Function to calculate properties
            record: Database record
            temperatures: List of temperatures in Kelvin

        Returns:
            List of ThermodynamicProperties for each temperature
        """
        results = []
        uncached_temps = []
        uncached_indices = []

        # Check cache for all temperatures
        for i, temp in enumerate(temperatures):
            cache_key = f"prop_{record.id}_{temp:.6f}"
            cached_result = self.property_cache.get(cache_key)

            if cached_result is not None:
                results.append(cached_result)
                with self._lock:
                    self.metrics.cache_hits += 1
            else:
                results.append(None)  # Placeholder
                uncached_temps.append(temp)
                uncached_indices.append(i)
                with self._lock:
                    self.metrics.cache_misses += 1

        # Batch calculate uncached temperatures
        if uncached_temps:
            start_time = time.time()

            # For now, calculate individually (could be optimized further)
            for temp, idx in zip(uncached_temps, uncached_indices):
                result = calculator_func(record, temp)
                results[idx] = result

                # Cache individual result
                cache_key = f"prop_{record.id}_{temp:.6f}"
                self.property_cache.put(cache_key, result)

            calculation_time = time.time() - start_time

            # Update metrics
            with self._lock:
                self.metrics.calculation_count += len(uncached_temps)
                self.metrics.total_time += calculation_time
                self.metrics.update_average_time()

        self.metrics.update_hit_rate()
        return results

    def precompute_common_temperatures(
        self,
        calculator_func: Callable,
        compound_data: MultiPhaseCompoundData,
        temperature_step: float = 10.0
    ) -> None:
        """
        Precompute properties for common temperature ranges.

        Args:
            calculator_func: Function to calculate properties
            compound_data: MultiPhaseCompoundData to precompute for
            temperature_step: Temperature step for precomputation
        """
        t_min, t_max = compound_data.get_available_range()

        # Generate temperature grid
        temperatures = np.arange(t_min, t_max + temperature_step, temperature_step)

        logger.info(f"Precomputing properties for {len(temperatures)} temperatures")

        precomputed_count = 0
        start_time = time.time()

        for temp in temperatures:
            try:
                record = compound_data.get_record_at_temperature(temp)
                cache_key = f"prop_{record.id}_{temp:.6f}"

                # Only compute if not already cached
                if self.property_cache.get(cache_key) is None:
                    result = calculator_func(record, temp)
                    self.property_cache.put(cache_key, result)
                    precomputed_count += 1

            except ValueError:
                # Skip temperatures outside range
                continue

        precomputation_time = time.time() - start_time
        logger.info(
            f"Precomputed {precomputed_count} properties in {precomputation_time:.3f}s"
        )

    def optimize_temperature_grid(
        self,
        t_min: float,
        t_max: float,
        num_points: int,
        adaptive_refinement: bool = True
    ) -> np.ndarray:
        """
        Generate optimized temperature grid for calculations.

        Args:
            t_min: Minimum temperature
            t_max: Maximum temperature
            num_points: Target number of points
            adaptive_refinement: Use adaptive refinement near transitions

        Returns:
            Optimized temperature array
        """
        if not adaptive_refinement:
            return np.linspace(t_min, t_max, num_points)

        # Adaptive grid with more points near expected transition temperatures
        # For now, use simple approach with denser grid at lower temperatures
        base_grid = np.linspace(t_min, t_max, num_points)

        # Add more points in lower temperature range (where most transitions occur)
        low_temp_range = (t_max - t_min) * 0.3
        low_temp_points = int(num_points * 0.6)

        low_temp_grid = np.linspace(t_min, t_min + low_temp_range, low_temp_points)
        high_temp_grid = np.linspace(t_min + low_temp_range, t_max, num_points - low_temp_points)

        # Combine and deduplicate
        combined_grid = np.unique(np.concatenate([low_temp_grid, high_temp_grid]))

        return combined_grid

    def get_memory_usage(self) -> float:
        """
        Estimate memory usage of caches in MB.

        Returns:
            Memory usage in megabytes
        """
        import sys

        total_size = 0

        # Estimate cache sizes
        total_size += self.property_cache.size() * 200  # Rough estimate per property
        total_size += self.transition_cache.size() * 100  # Rough estimate per transition
        total_size += self.integration_cache.size() * 150  # Rough estimate per integration

        return total_size / (1024 * 1024)  # Convert to MB

    def get_performance_report(self) -> Dict[str, Any]:
        """
        Get comprehensive performance report.

        Returns:
            Dictionary with performance metrics and statistics
        """
        self.metrics.memory_usage_mb = self.get_memory_usage()

        return {
            "calculation_metrics": {
                "total_calculations": self.metrics.calculation_count,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "cache_hit_rate": f"{self.metrics.cache_hit_rate:.1f}%",
                "total_time": f"{self.metrics.total_time:.3f}s",
                "average_time": f"{self.metrics.average_time:.6f}s"
            },
            "cache_statistics": {
                "property_cache_size": self.property_cache.size(),
                "transition_cache_size": self.transition_cache.size(),
                "integration_cache_size": self.integration_cache.size(),
                "estimated_memory_usage": f"{self.metrics.memory_usage_mb:.2f} MB"
            },
            "performance_score": self._calculate_performance_score()
        }

    def _calculate_performance_score(self) -> str:
        """
        Calculate overall performance score.

        Returns:
            Performance score as string (Excellent/Good/Fair/Poor)
        """
        if self.metrics.calculation_count == 0:
            return "No data"

        # Score based on cache hit rate and average calculation time
        hit_rate_score = min(self.metrics.cache_hit_rate / 100, 1.0) * 50
        time_score = max(0, (1.0 - min(self.metrics.average_time / 0.001, 1.0)) * 50)

        total_score = hit_rate_score + time_score

        if total_score >= 80:
            return "Excellent"
        elif total_score >= 60:
            return "Good"
        elif total_score >= 40:
            return "Fair"
        else:
            return "Poor"

    def clear_caches(self):
        """Clear all performance caches."""
        self.property_cache.clear()
        self.transition_cache.clear()
        self.integration_cache.clear()

        logger.info("All performance caches cleared")

    def reset_metrics(self):
        """Reset performance metrics."""
        self.metrics = PerformanceMetrics()
        logger.info("Performance metrics reset")


# Global performance optimizer instance
_global_optimizer = None


def get_performance_optimizer() -> PerformanceOptimizer:
    """Get or create global performance optimizer instance."""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = PerformanceOptimizer()
    return _global_optimizer


def optimize_performance(cache_size: int = 1000):
    """
    Decorator for optimizing performance of thermodynamic calculation functions.

    Args:
        cache_size: Size of LRU cache to use
    """
    def decorator(func):
        optimizer = get_performance_optimizer()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # For functions that calculate thermodynamic properties
            if func.__name__ in ['calculate_properties', 'calculate_properties_multi_record']:
                # Extract record and temperature from arguments
                if len(args) >= 2:
                    record = args[0] if func.__name__ == 'calculate_properties' else args[1]
                    temperature = args[1] if func.__name__ == 'calculate_properties' else args[2]

                    if isinstance(record, DatabaseRecord) and isinstance(temperature, (int, float)):
                        return optimizer.cached_property_calculation(func, record, temperature)

            return func(*args, **kwargs)

        return wrapper
    return decorator


class ProfiledCalculation:
    """Context manager for profiling calculations."""

    def __init__(self, operation_name: str):
        """
        Initialize profiler.

        Args:
            operation_name: Name of operation being profiled
        """
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        """Start profiling."""
        self.start_time = time.time()
        logger.debug(f"Starting operation: {self.operation_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End profiling and log results."""
        if self.start_time:
            duration = time.time() - self.start_time
            logger.debug(f"Operation '{self.operation_name}' completed in {duration:.6f}s")

            # Update global metrics
            optimizer = get_performance_optimizer()
            with optimizer._lock:
                optimizer.metrics.calculation_count += 1
                optimizer.metrics.total_time += duration
                optimizer.metrics.update_average_time()