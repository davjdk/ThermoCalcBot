"""
Конвейерная система фильтрации термодинамических данных.

Реализует модульную архитектуру с возможностью добавления новых стадий фильтрации.
Каждая стадия собирает детальную статистику о своей работе.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..models.extraction import ExtractedReactionParameters
from ..models.search import DatabaseRecord


@dataclass
class FilterContext:
    """Контекст фильтрации, передаваемый между стадиями."""

    temperature_range: Tuple[float, float]
    compound_formula: str
    user_query: Optional[str] = None
    additional_params: Optional[Dict[str, Any]] = None
    reaction_params: Optional[ExtractedReactionParameters] = None  # НОВОЕ

    def __post_init__(self):
        """Валидация контекста после инициализации."""
        if self.temperature_range[0] > self.temperature_range[1]:
            raise ValueError(
                "Минимальная температура не может быть больше максимальной"
            )
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
        self, records: List[DatabaseRecord], context: FilterContext
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
        return (
            len(self.stage_statistics)
            if self.is_found
            else (self.failure_stage or 0) - 1
        )


class FilterPipeline:
    """Конвейер фильтрации с возможностью добавления новых стадий."""

    def __init__(self, session_logger: Optional[Any] = None):
        self.stages: List[FilterStage] = []
        self.statistics: List[Dict[str, Any]] = []
        self._last_execution_time_ms: Optional[float] = None
        self.session_logger = session_logger

    def add_stage(self, stage: FilterStage) -> "FilterPipeline":
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
        self, records: List[DatabaseRecord], context: FilterContext
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
        self.statistics.append(
            {
                "stage_number": 0,
                "stage_name": "Начальные данные",
                "records_before": len(records),
                "records_after": len(records),
                "reduction_rate": 0.0,
                "execution_time_ms": 0.0,
            }
        )

        for i, stage in enumerate(self.stages, start=1):
            stage_start_time = time.time()

            # НОВОЕ: логирование заголовка стадии
            if self.session_logger:
                self.session_logger.log_stage_header(
                    stage_number=i,
                    stage_name=stage.get_stage_name(),
                    compound_formula=context.compound_formula,
                )

                # НОВОЕ: логирование таблицы ДО фильтрации (чтобы видеть все записи)
                if len(current_records) > 0:
                    self.session_logger.log_info(
                        f"Записей до фильтрации: {len(current_records)}"
                    )
                    self.session_logger.log_filter_stage_table(
                        records=current_records[:10],  # первые 10 ДО фильтрации
                        compound_formula=context.compound_formula,
                        stage_name=f"{stage.get_stage_name()} (ДО фильтрации)",
                    )

            # Применить фильтр
            filtered = stage.filter(current_records, context)
            stage_execution_time = (time.time() - stage_start_time) * 1000

            # Собрать статистику
            stats = stage.get_statistics()
            stats.update(
                {
                    "stage_number": i,
                    "stage_name": stage.get_stage_name(),
                    "records_before": len(current_records),
                    "records_after": len(filtered),
                    "reduction_rate": (len(current_records) - len(filtered))
                    / len(current_records)
                    if current_records
                    else 0.0,
                    "execution_time_ms": stage_execution_time,
                }
            )
            self.statistics.append(stats)

            # НОВОЕ: логирование статистики и таблицы ПОСЛЕ фильтрации
            if self.session_logger:
                self.session_logger.log_stage_statistics(stats)

                if len(filtered) > 0:
                    self.session_logger.log_filter_stage_table(
                        records=filtered[:10],  # первые 10 ПОСЛЕ фильтрации
                        compound_formula=context.compound_formula,
                        stage_name=f"{stage.get_stage_name()} (ПОСЛЕ фильтрации)",
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
                    failure_reason=f"Нет записей после стадии: {stage.get_stage_name()}",
                )

            current_records = filtered

            # НОВОЕ: Оптимизация - если осталась 1 запись, дальнейшая фильтрация не нужна
            if len(current_records) == 1:
                total_time = (time.time() - start_time) * 1000
                self._last_execution_time_ms = total_time

                if self.session_logger:
                    self.session_logger.log_info("")
                    self.session_logger.log_info(
                        f"✓ Осталась 1 запись после стадии {i} ({stage.get_stage_name()}). "
                        f"Пропуск оставшихся {len(self.stages) - i} стадий."
                    )
                    self.session_logger.log_info("")

                # Добавляем статистику о пропущенных стадиях
                for j in range(i + 1, len(self.stages) + 1):
                    skipped_stage = (
                        self.stages[j - 1] if j - 1 < len(self.stages) else None
                    )
                    self.statistics.append(
                        {
                            "stage_number": j,
                            "stage_name": skipped_stage.get_stage_name()
                            if skipped_stage
                            else "Unknown",
                            "records_before": 1,
                            "records_after": 1,
                            "reduction_rate": 0.0,
                            "execution_time_ms": 0.0,
                            "skipped": True,
                            "skip_reason": "Единственная запись найдена на предыдущей стадии",
                        }
                    )

                return FilterResult(
                    filtered_records=current_records,
                    stage_statistics=self.statistics.copy(),
                    is_found=True,
                )

        total_time = (time.time() - start_time) * 1000
        self._last_execution_time_ms = total_time

        # Добавляем финальную статистику
        self.statistics.append(
            {
                "stage_number": len(self.stages) + 1,
                "stage_name": "Завершение",
                "records_before": len(records),
                "records_after": len(current_records),
                "total_reduction_rate": (len(records) - len(current_records))
                / len(records)
                if records
                else 0.0,
                "total_execution_time_ms": total_time,
                "stages_executed": len(self.stages),
            }
        )

        return FilterResult(
            filtered_records=current_records,
            stage_statistics=self.statistics.copy(),
            is_found=True,
        )

    def get_last_execution_time_ms(self) -> Optional[float]:
        """Получить время последнего выполнения в миллисекундах."""
        return self._last_execution_time_ms

    def get_stage_names(self) -> List[str]:
        """Получить названия всех стадий в конвейере."""
        return [stage.get_stage_name() for stage in self.stages]

    def clear_stages(self) -> "FilterPipeline":
        """Очистить все стадии из конвейера."""
        self.stages.clear()
        return self

    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Получить сводную информацию о конвейере."""
        return {
            "total_stages": len(self.stages),
            "stage_names": self.get_stage_names(),
            "last_execution_time_ms": self._last_execution_time_ms,
            "statistics_count": len(self.statistics),
        }


class FilterPipelineBuilder:
    """Builder для создания и конфигурации конвейера фильтрации."""

    def __init__(self, session_logger: Optional[Any] = None):
        self.pipeline = FilterPipeline(session_logger=session_logger)

    def with_reaction_validation(self, **kwargs) -> "FilterPipelineBuilder":
        """Добавить стадию валидации реакции (Stage 0)."""
        from .reaction_validation_stage import ReactionValidationStage

        self.pipeline.add_stage(ReactionValidationStage(**kwargs))
        return self

    def with_temperature_filter(self, **kwargs) -> "FilterPipelineBuilder":
        """Добавить стадию температурной фильтрации."""
        from .filter_stages import TemperatureFilterStage

        self.pipeline.add_stage(TemperatureFilterStage(**kwargs))
        return self

    def with_phase_selection(self, phase_resolver, **kwargs) -> "FilterPipelineBuilder":
        """Добавить стадию выбора фазы."""
        from .filter_stages import PhaseSelectionStage

        self.pipeline.add_stage(
            PhaseSelectionStage(phase_resolver=phase_resolver, **kwargs)
        )
        return self

    def with_reliability_priority(self, **kwargs) -> "FilterPipelineBuilder":
        """Добавить стадию приоритизации по надёжности."""
        from .filter_stages import ReliabilityPriorityStage

        self.pipeline.add_stage(ReliabilityPriorityStage(**kwargs))
        return self

    def build(self) -> FilterPipeline:
        """Построить и вернуть готовый конвейер."""
        return self.pipeline
