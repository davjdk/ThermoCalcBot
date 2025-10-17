"""
Конвейерная система фильтрации термодинамических данных.

Оптимизированная версия для прямых вызовов без message passing.
Реализует модульную архитектуру с высокой производительностью и предсказуемостью.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..filtering.constants import DEFAULT_QUERY_LIMIT
from ..models.extraction import ExtractedReactionParameters
from ..models.search import DatabaseRecord
from ..utils.chem_utils import (
    is_ionic_formula,
    is_ionic_name,
    query_contains_charge,
    expand_composite_candidates,
)


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
    """
    Оптимизированный конвейер фильтрации для прямых вызовов.

    Особенности оптимизации:
    - Убрана зависимость от session_logger
    - Прямые вызовы стадий без message passing
    - Упрощенная архитектура для предсказуемости
    - Сохранена статистика для отладки
    """

    def __init__(self):
        self.stages: List[FilterStage] = []
        self.statistics: List[Dict[str, Any]] = []
        self._last_execution_time_ms: Optional[float] = None

    def _prefilter_exclude_ions(
        self, records: List[DatabaseRecord], query: Optional[str] = None
    ) -> Tuple[List[DatabaseRecord], List[DatabaseRecord]]:
        """
        Prefilter: Исключить ионные формы, если пользователь не запрашивал их явно.

        Оптимизированная версия без логирования для производительности.

        Args:
            records: Список записей для фильтрации
            query: Поисковый запрос пользователя

        Returns:
            Tuple[non_ionic_records, ionic_records]
        """
        if not query or query_contains_charge(query):
            # Пользователь явно запросил ионную форму или запрос пуст
            return records, []

        # Разделяем записи на ионные и неионные
        ionic_records = []
        non_ionic_records = []

        for record in records:
            is_ionic = False

            # Проверяем формулу на ионность
            if record.formula and is_ionic_formula(record.formula):
                is_ionic = True

            # Проверяем название на ионность
            if not is_ionic and hasattr(record, 'first_name') and record.first_name and is_ionic_name(record.first_name):
                is_ionic = True

            if is_ionic:
                ionic_records.append(record)
            else:
                non_ionic_records.append(record)

        return non_ionic_records, ionic_records

    def _apply_fallback(
        self,
        initial_records: List[DatabaseRecord],
        ionic_records: List[DatabaseRecord],
        prefilter_applied: bool,
        context: FilterContext,
    ) -> List[DatabaseRecord]:
        """
        Применить fallback-стратегии для восстановления записей.

        Оптимизированная версия без логирования для производительности.

        Args:
            initial_records: Исходные записи до фильтрации
            ionic_records: Исключённые ионные записи
            prefilter_applied: Был ли применен prefilter
            context: Контекст фильтрации

        Returns:
            Список восстановленных записей или пустой список
        """
        query = context.user_query or context.compound_formula
        result_records = []

        # Fallback 1: Восстановление ионных записей (если они были исключены)
        if prefilter_applied and ionic_records:
            # Ионные записи - это крайняя мера, но если ничего больше не работает
            result_records.extend(ionic_records)

        # Fallback 2: Поиск составных формул (например, Li2O*TiO2 для Li2TiO3)
        if not result_records and initial_records:
            composite_candidates = expand_composite_candidates(query, initial_records)
            if composite_candidates:
                result_records.extend(composite_candidates)

        # Fallback 3: Вернуть top-N исходных записей с пометкой relaxed
        if not result_records and initial_records:
            # Сортируем по надёжности и берём top-3
            sorted_records = sorted(
                initial_records,
                key=lambda r: getattr(r, 'ReliabilityClass', 'D'),
            )[:3]
            result_records.extend(sorted_records)

        return result_records

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

        Оптимизированная версия для прямых вызовов без message passing.
        Проходит по всем стадиям последовательно и собирает статистику.

        Args:
            records: Список записей для фильтрации
            context: Контекст фильтрации

        Returns:
            Результат фильтрации с детальной статистикой
        """
        import time

        start_time = time.time()
        initial_records = records.copy()  # Сохраняем исходные данные для fallback
        current_records = records
        self.statistics = []
        ionic_records = []  # Сохраняем исключённые ионные записи
        prefilter_applied = False

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

        # Prefilter: исключение ионов
        query = context.user_query or context.compound_formula
        if query and not query_contains_charge(query):
            current_records, ionic_records = self._prefilter_exclude_ions(
                current_records, query
            )
            prefilter_applied = len(ionic_records) > 0

            if prefilter_applied:
                # Добавляем статистику prefilter
                self.statistics.append(
                    {
                        "stage_number": 0.5,
                        "stage_name": "Prefilter: исключение ионов",
                        "records_before": len(initial_records),
                        "records_after": len(current_records),
                        "reduction_rate": len(ionic_records) / len(initial_records)
                        if initial_records
                        else 0.0,
                        "execution_time_ms": 0.0,
                        "ionic_records_excluded": len(ionic_records),
                    }
                )

        for i, stage in enumerate(self.stages, start=1):
            stage_start_time = time.time()

            # Применить фильтр (прямой вызов)
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

            # Проверка провала
            if len(filtered) == 0:
                # Fallback: пробуем восстановить записи если все стадии провалились
                fallback_records = self._apply_fallback(
                    initial_records, ionic_records, prefilter_applied, context
                )

                if fallback_records:
                    total_time = (time.time() - start_time) * 1000
                    self._last_execution_time_ms = total_time

                    # Добавляем статистику fallback
                    self.statistics.append(
                        {
                            "stage_number": i + 0.5,
                            "stage_name": "Fallback: восстановление записей",
                            "records_before": 0,
                            "records_after": len(fallback_records),
                            "reduction_rate": 0.0,
                            "execution_time_ms": 0.0,
                            "fallback_applied": True,
                            "fallback_records_found": len(fallback_records),
                        }
                    )

                    return FilterResult(
                        filtered_records=fallback_records,
                        stage_statistics=self.statistics.copy(),
                        is_found=True,
                        failure_reason=None,
                    )
                else:
                    # Fallback не помог, возвращаем провал
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

            # Оптимизация: если осталась 1 запись, дальнейшая фильтрация не нужна
            # НО: не применяем до PhaseBasedTemperatureStage, так как фазовая фильтрация критична
            stage_name = stage.get_stage_name()
            is_before_phase_filter = "фазам" not in stage_name.lower()

            if len(current_records) == 1 and not is_before_phase_filter:
                total_time = (time.time() - start_time) * 1000
                self._last_execution_time_ms = total_time

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
    """
    Builder для создания и конфигурации конвейера фильтрации.

    Оптимизированная версия без dependencies от session_logger.
    """

    def __init__(self):
        self.pipeline = FilterPipeline()

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

    def with_phase_based_temperature_filter(self, **kwargs) -> "FilterPipelineBuilder":
        """Добавить умную стадию фильтрации по фазам и температуре."""
        from .phase_based_temperature_stage import PhaseBasedTemperatureStage

        self.pipeline.add_stage(PhaseBasedTemperatureStage(**kwargs))
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
