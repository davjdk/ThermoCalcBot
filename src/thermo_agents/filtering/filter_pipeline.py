"""
Конвейерная система фильтрации термодинамических данных.

Реализует модульную архитектуру с возможностью добавления новых стадий фильтрации.
Каждая стадия собирает детальную статистику о своей работе.
"""

from typing import Protocol, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
import psutil
import os

from ..models.search import DatabaseRecord


class PerformanceMonitor:
    """Мониторинг производительности для стадий фильтрации."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())

    def get_memory_usage(self) -> Dict[str, float]:
        """Получить информацию о памяти в MB."""
        memory_info = self.process.memory_info()
        return {
            'rss_mb': memory_info.rss / 1024 / 1024,  # Resident Set Size
            'vms_mb': memory_info.vms / 1024 / 1024,  # Virtual Memory Size
            'percent': self.process.memory_percent()
        }

    def get_cpu_percent(self) -> float:
        """Получить загрузку CPU."""
        return self.process.cpu_percent()

    def get_data_volume_mb(self, records: List[DatabaseRecord]) -> float:
        """Оценить объем данных в записях."""
        if not records:
            return 0.0

        # Приблизительная оценка размера одной записи
        # Formula: 50 байт, Phase: 10 байт, floats: 8*8 байт, другие поля: 100 байт
        estimated_size_per_record = 50 + 10 + (8 * 8) + 100  # ~214 байт

        total_size = len(records) * estimated_size_per_record
        return total_size / 1024 / 1024  # в MB


@dataclass
class FilterContext:
    """Контекст фильтрации, передаваемый между стадиями."""
    temperature_range: Tuple[float, float]
    compound_formula: str
    user_query: Optional[str] = None
    additional_params: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Валидация контекста после инициализации."""
        if self.temperature_range[0] > self.temperature_range[1]:
            raise ValueError("Минимальная температура не может быть больше максимальной")
        if not self.compound_formula:
            raise ValueError("Формула соединения не может быть пустой")

        if self.additional_params is None:
            self.additional_params = {}


class FilterStage(ABC):
    """Базовый абстрактный класс для стадии фильтрации."""

    def __init__(self):
        self.last_stats: Dict[str, Any] = {}

    @abstractmethod
    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """Применить фильтр к записям."""
        pass

    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику последней фильтрации."""
        return self.last_stats.copy()

    @abstractmethod
    def get_stage_name(self) -> str:
        """Название стадии для отчётности."""
        pass


@dataclass
class FilterResult:
    """Результат выполнения конвейера фильтрации."""
    filtered_records: List[DatabaseRecord]
    stage_statistics: List[Dict[str, Any]]
    is_found: bool
    failure_stage: Optional[int] = None
    failure_reason: Optional[str] = None

    @property
    def total_filtered(self) -> int:
        """Общее количество отфильтрованных записей."""
        return len(self.filtered_records)

    @property
    def successful_stages(self) -> int:
        """Количество успешно выполненных стадий."""
        return len(self.stage_statistics) if self.is_found else (self.failure_stage or 0) - 1


class FilterPipeline:
    """Конвейер фильтрации с возможностью добавления новых стадий."""

    def __init__(self, session_logger: Optional[Any] = None):
        self.stages: List[FilterStage] = []
        self.statistics: List[Dict[str, Any]] = []
        self._last_execution_time_ms: Optional[float] = None
        self.session_logger = session_logger  # НОВОЕ
        self.performance_monitor = PerformanceMonitor()  # НОВОЕ

    def add_stage(self, stage: FilterStage) -> 'FilterPipeline':
        """
        Добавить стадию в конвейер (поддержка fluent API).

        Args:
            stage: Стадия фильтрации для добавления

        Returns:
            Self для поддержки chain-вызовов
        """
        if not isinstance(stage, FilterStage):
            raise TypeError("Стадия должна наследоваться от FilterStage")

        self.stages.append(stage)
        return self

    def execute(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> FilterResult:
        """
        Выполнить конвейер фильтрации.

        Проходит по всем стадиям последовательно:
        1. FormulaMatchStage (уже выполнена в CompoundSearcher)
        2. TemperatureFilterStage
        3. PhaseSelectionStage
        4. ReliabilityPriorityStage

        Собирает статистику на каждой стадии.

        Args:
            records: Список записей для фильтрации
            context: Контекст фильтрации

        Returns:
            Результат фильтрации с детальной статистикой
        """
        import time
        start_time = time.time()

        current_records = records
        self.statistics = []

        # Добавляем начальную статистику
        self.statistics.append({
            'stage_number': 0,
            'stage_name': 'Начальные данные',
            'records_before': len(records),
            'records_after': len(records),
            'reduction_rate': 0.0,
            'execution_time_ms': 0.0
        })

        for i, stage in enumerate(self.stages, start=1):
            stage_start_time = time.time()

            # НОВОЕ: логирование заголовка стадии
            if self.session_logger:
                self.session_logger.log_stage_header(
                    stage_number=i,
                    stage_name=stage.get_stage_name(),
                    compound_formula=context.compound_formula
                )

            # Собрать метрики перед фильтрацией
            memory_before = self.performance_monitor.get_memory_usage()
            cpu_before = self.performance_monitor.get_cpu_percent()
            data_volume_before = self.performance_monitor.get_data_volume_mb(current_records)

            # Применить фильтр
            filtered = stage.filter(current_records, context)
            stage_execution_time = (time.time() - stage_start_time) * 1000

            # Собрать метрики после фильтрации
            memory_after = self.performance_monitor.get_memory_usage()
            cpu_after = self.performance_monitor.get_cpu_percent()
            data_volume_after = self.performance_monitor.get_data_volume_mb(filtered)

            # Собрать статистику
            stats = stage.get_statistics()
            stats.update({
                'stage_number': i,
                'stage_name': stage.get_stage_name(),
                'records_before': len(current_records),
                'records_after': len(filtered),
                'reduction_rate': (len(current_records) - len(filtered)) / len(current_records) if current_records else 0.0,
                'execution_time_ms': stage_execution_time,
                # НОВЫЕ метрики производительности
                'performance': {
                    'memory_before_mb': memory_before['rss_mb'],
                    'memory_after_mb': memory_after['rss_mb'],
                    'memory_delta_mb': memory_after['rss_mb'] - memory_before['rss_mb'],
                    'cpu_before_percent': cpu_before,
                    'cpu_after_percent': cpu_after,
                    'data_volume_before_mb': data_volume_before,
                    'data_volume_after_mb': data_volume_after,
                    'data_volume_reduction_mb': data_volume_before - data_volume_after,
                    'records_per_ms': len(current_records) / stage_execution_time if stage_execution_time > 0 else 0
                }
            })
            self.statistics.append(stats)

            # НОВОЕ: логирование статистики и таблицы
            if self.session_logger:
                self.session_logger.log_stage_statistics(stats)

                if len(filtered) > 0:
                    self.session_logger.log_filter_stage_table(
                        records=filtered[:15],  # первые 15
                        compound_formula=context.compound_formula,
                        stage_name=stage.get_stage_name()
                    )

            # Проверка провала
            if len(filtered) == 0:
                total_time = (time.time() - start_time) * 1000
                self._last_execution_time_ms = total_time

                return FilterResult(
                    filtered_records=[],
                    stage_statistics=self.statistics.copy(),
                    is_found=False,
                    failure_stage=i,
                    failure_reason=f"Нет записей после стадии: {stage.get_stage_name()}"
                )

            current_records = filtered

        total_time = (time.time() - start_time) * 1000
        self._last_execution_time_ms = total_time

        # Добавляем финальную статистику
        self.statistics.append({
            'stage_number': len(self.stages) + 1,
            'stage_name': 'Завершение',
            'records_before': len(records),
            'records_after': len(current_records),
            'total_reduction_rate': (len(records) - len(current_records)) / len(records) if records else 0.0,
            'total_execution_time_ms': total_time,
            'stages_executed': len(self.stages)
        })

        return FilterResult(
            filtered_records=current_records,
            stage_statistics=self.statistics.copy(),
            is_found=True
        )

    def get_last_execution_time_ms(self) -> Optional[float]:
        """Получить время последнего выполнения в миллисекундах."""
        return self._last_execution_time_ms

    def get_stage_names(self) -> List[str]:
        """Получить названия всех стадий в конвейере."""
        return [stage.get_stage_name() for stage in self.stages]

    def clear_stages(self) -> 'FilterPipeline':
        """Очистить все стадии из конвейера."""
        self.stages.clear()
        return self

    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Получить сводную информацию о конвейере."""
        return {
            'total_stages': len(self.stages),
            'stage_names': self.get_stage_names(),
            'last_execution_time_ms': self._last_execution_time_ms,
            'statistics_count': len(self.statistics)
        }


class FilterPipelineBuilder:
    """Builder для создания и конфигурации конвейера фильтрации."""

    def __init__(self, session_logger: Optional[Any] = None):
        self.pipeline = FilterPipeline(session_logger=session_logger)

    def with_temperature_filter(self, **kwargs) -> 'FilterPipelineBuilder':
        """Добавить стадию температурной фильтрации."""
        from .filter_stages import TemperatureFilterStage
        self.pipeline.add_stage(TemperatureFilterStage(**kwargs))
        return self

    def with_phase_selection(self, phase_resolver, **kwargs) -> 'FilterPipelineBuilder':
        """Добавить стадию выбора фазы."""
        from .filter_stages import PhaseSelectionStage
        self.pipeline.add_stage(PhaseSelectionStage(phase_resolver=phase_resolver, **kwargs))
        return self

    def with_reliability_priority(self, **kwargs) -> 'FilterPipelineBuilder':
        """Добавить стадию приоритизации по надёжности."""
        from .filter_stages import ReliabilityPriorityStage
        self.pipeline.add_stage(ReliabilityPriorityStage(**kwargs))
        return self

    def build(self) -> FilterPipeline:
        """Построить и вернуть готовый конвейер."""
        return self.pipeline