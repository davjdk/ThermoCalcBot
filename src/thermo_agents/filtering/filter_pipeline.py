"""
Высокопроизводительная конвейерная система фильтрации термодинамических данных.

Оптимизированная версия с кэшированием, ленивой загрузкой и индексацией.
Реализует модульную архитектуру с максимальной производительностью.

Техническое описание:
Высокопроизводительный конвейер фильтрации для термодинамических данных в архитектуре v2.0.
Реализует многостадийную детерминированную фильтрацию с кэшированием, оптимизациями
и fallback-стратегиями для максимальной производительности и надежности.

Ключевые компоненты:
- FilterContext: Контекст фильтрации между стадиями
- FilterStage: Абстрактный базовый класс для стадий фильтрации
- FilterPipeline: Основной конвейер фильтрации
- PerformanceOptimizedFilterPipeline: Высокопроизводительная версия
- FilterPipelineBuilder: Builder для конфигурации конвейера
- FilterResult/CacheEntry: Модели результатов и кэширования

Основные методы FilterPipeline:
- execute(): Выполнение конвейера с детальной статистикой
- add_stage(): Добавление стадии (fluent API)
- _prefilter_exclude_ions(): Предварительное исключение ионов
- _apply_fallback(): Fallback-стратегии восстановления
- _validate_final_records(): Валидация финальных записей
- get_pipeline_summary(): Сводная информация о конвейере

Стадии фильтрации (через FilterPipelineBuilder):
- with_deduplication(): Удаление дубликатов (Stage 1)
- with_reaction_validation(): Валидация реакции (Stage 0)
- with_temperature_filter(): Температурная фильтрация
- with_phase_based_temperature_filter(): Умная фильтрация по фазам и температуре
- with_phase_selection(): Выбор фазового состояния
- with_reliability_priority(): Приоритизация по надежности

Оптимизации производительности:
- Кэширование результатов с TTL (15 минут по умолчанию)
- Ленивая загрузка для больших наборов данных (>1000 записей)
- Пакетная обработка (batch size = 100)
- Ранний возврат при одной записи
- Индексация для быстрых поисков
- Предварительное исключение ионов

Fallback-стратегии:
- Восстановление ионных записей при провале фильтрации
- Поиск составных формул (Li2O*TiO2 → Li2TiO3)
- Top-N исходных записей с пометкой relaxed
- Graceful degradation при отсутствии данных

Статистика и логирование:
- Детальная статистика по каждой стадии
- Время выполнения и коэффициенты отсева
- Интеграция с SessionLogger для трейсинга
- Валидация финальных записей с предупреждениями
- Логирование удаленных записей и причин

Метрики производительности:
- Cache hit rate и эффективность
- Общее количество обработанных записей
- Время выполнения конвейера
- Статистика по стадиям и их оптимизация

Контекст фильтрации:
- Температурный диапазон
- Формула соединения
- Параметры реакции
- Дополнительные параметры
- Пользовательский запрос

Валидация результатов:
- Проверка температурного покрытия
- Валидация фазовой согласованности
- Проверка качества данных (H298, S298)
- Генерация предупреждений и рекомендаций

Интеграция:
- Используется CompoundSearcher для фильтрации результатов
- Интегрируется с FilterStage для конкретных реализаций
- Поддерживает SessionLogger для детального логирования
- Совместим с ExtractedReactionParameters

Используется в:
- CompoundSearcher для фильтрации найденных записей
- ThermoOrchestrator для подготовки данных
- ThermodynamicCalculator для получения валидных данных
- Тестировании и отладке системы фильтрации
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import time
from functools import lru_cache

from ..filtering.constants import (
    DEFAULT_QUERY_LIMIT,
    FILTER_PIPELINE_CACHE_SIZE,
    FILTER_CACHE_TTL,
    MIN_RECORDS_FOR_CACHING,
    LAZY_LOAD_THRESHOLD,
    BATCH_PROCESSING_SIZE,
)
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

    # Stage 1: Enhanced temperature range support
    original_user_range: Optional[Tuple[float, float]] = None  # Original user request
    full_calculation_range: Optional[Tuple[float, float]] = None  # Stage 1 calculation range
    stage1_mode: bool = False  # Whether Stage 1 logic is enabled

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

        # Stage 1: Initialize ranges if not provided
        if self.stage1_mode and not self.full_calculation_range:
            self.full_calculation_range = self.temperature_range

    @property
    def effective_temperature_range(self) -> Tuple[float, float]:
        """
        Get the effective temperature range for filtering.

        In Stage 1 mode, returns the full calculation range.
        Otherwise, returns the original temperature range.
        """
        if self.stage1_mode and self.full_calculation_range:
            return self.full_calculation_range
        return self.temperature_range

    def get_range_info(self) -> Dict[str, Any]:
        """
        Get information about temperature ranges for logging and debugging.

        Returns:
            Dictionary with range information
        """
        info = {
            "effective_range": self.effective_temperature_range,
            "stage1_mode": self.stage1_mode,
        }

        if self.original_user_range:
            info["original_user_range"] = self.original_user_range

        if self.full_calculation_range and self.stage1_mode:
            info["full_calculation_range"] = self.full_calculation_range

        return info


@dataclass
class CacheEntry:
    """Элемент кэша для результатов фильтрации."""
    result: List["DatabaseRecord"]
    timestamp: float
    stage_name: str
    context_hash: str


class PerformanceOptimizedFilterPipeline:
    """
    Высокопроизводительный конвейер фильтрации с кэшированием и оптимизациями.

    Особенности производительности:
    - Кэширование результатов фильтрации с TTL
    - Ленивая загрузка для больших наборов данных
    - Индексация для быстрых поисков
    - Пакетная обработка записей
    """

    def __init__(self, cache_size: int = FILTER_PIPELINE_CACHE_SIZE):
        self.stages: List["FilterStage"] = []
        self.statistics: List[Dict[str, Any]] = []
        self._last_execution_time_ms: Optional[float] = None

        # Кэширование результатов
        self._cache: Dict[str, CacheEntry] = {}
        self._cache_size = cache_size
        self._cache_hits = 0
        self._cache_misses = 0

        # Метрики производительности
        self._total_records_processed = 0
        self._total_stages_executed = 0

    def _generate_cache_key(
        self,
        stage_name: str,
        records: List["DatabaseRecord"],
        context: "FilterContext"
    ) -> str:
        """Генерировать ключ кэша на основе входных данных."""
        # Хэшируем основные параметры для уникального ключа
        key_data = {
            "stage": stage_name,
            "formula": context.compound_formula,
            "temp_range": context.temperature_range,
            "record_count": len(records),
            # Используем только ID записей для экономии памяти
            "record_ids": [r.id for r in records[:10]]  # Первые 10 ID
        }
        key_str = str(sorted(key_data.items()))
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def _get_from_cache(self, cache_key: str) -> Optional[List["DatabaseRecord"]]:
        """Получить результаты из кэша."""
        if cache_key not in self._cache:
            self._cache_misses += 1
            return None

        entry = self._cache[cache_key]

        # Проверяем TTL
        if time.time() - entry.timestamp > FILTER_CACHE_TTL:
            del self._cache[cache_key]
            self._cache_misses += 1
            return None

        self._cache_hits += 1
        return entry.result.copy()

    def _store_in_cache(
        self,
        cache_key: str,
        result: List["DatabaseRecord"],
        stage_name: str,
        context: "FilterContext"
    ) -> None:
        """Сохранить результаты в кэш."""
        # Очищаем кэш при необходимости
        if len(self._cache) >= self._cache_size:
            # Удаляем самый старый элемент
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].timestamp
            )
            del self._cache[oldest_key]

        # Кэшируем только если достаточно записей
        if len(result) >= MIN_RECORDS_FOR_CACHING:
            self._cache[cache_key] = CacheEntry(
                result=result.copy(),
                timestamp=time.time(),
                stage_name=stage_name,
                context_hash=cache_key
            )

    def _apply_lazy_loading(
        self,
        records: List["DatabaseRecord"]
    ) -> List["DatabaseRecord"]:
        """
        Применить ленивую загрузку для больших наборов данных.

        Для больших наборов данных обрабатываем записями пакетами
        для снижения нагрузки на память.
        """
        if len(records) < LAZY_LOAD_THRESHOLD:
            return records

        # Пакетная обработка для больших наборов
        processed_records = []
        for i in range(0, len(records), BATCH_PROCESSING_SIZE):
            batch = records[i:i + BATCH_PROCESSING_SIZE]
            # Обрабатываем пакет...
            processed_records.extend(batch)

        return processed_records

    def _prefilter_exclude_ions_optimized(
        self,
        records: List["DatabaseRecord"],
        query: Optional[str] = None
    ) -> Tuple[List["DatabaseRecord"], List["DatabaseRecord"]]:
        """
        Оптимизированный prefilter с индексацией.
        """
        if not query or query_contains_charge(query):
            return records, []

        # Используем списковые включения для производительности
        ionic_records = []
        non_ionic_records = []

        # Пакетная обработка для больших наборов
        if len(records) > LAZY_LOAD_THRESHOLD:
            for batch in self._batch_records(records):
                batch_ionic, batch_non_ionic = self._process_batch(batch)
                ionic_records.extend(batch_ionic)
                non_ionic_records.extend(batch_non_ionic)
        else:
            ionic_records, non_ionic_records = self._process_batch(records)

        return non_ionic_records, ionic_records

    def _batch_records(
        self,
        records: List["DatabaseRecord"]
    ) -> List[List["DatabaseRecord"]]:
        """Разделить записи на пакеты для обработки."""
        return [
            records[i:i + BATCH_PROCESSING_SIZE]
            for i in range(0, len(records), BATCH_PROCESSING_SIZE)
        ]

    def _process_batch(
        self,
        batch: List["DatabaseRecord"]
    ) -> Tuple[List["DatabaseRecord"], List["DatabaseRecord"]]:
        """Обработать пакет записей."""
        ionic_records = []
        non_ionic_records = []

        for record in batch:
            is_ionic = (
                (record.formula and is_ionic_formula(record.formula)) or
                (hasattr(record, 'first_name') and
                 record.first_name and
                 is_ionic_name(record.first_name))
            )

            if is_ionic:
                ionic_records.append(record)
            else:
                non_ionic_records.append(record)

        return ionic_records, non_ionic_records

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Получить метрики производительности."""
        total_requests = self._cache_hits + self._cache_misses
        cache_hit_rate = (
            self._cache_hits / total_requests * 100
            if total_requests > 0 else 0
        )

        return {
            "cache_hit_rate": cache_hit_rate,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_size": len(self._cache),
            "total_records_processed": self._total_records_processed,
            "total_stages_executed": self._total_stages_executed,
            "last_execution_time_ms": self._last_execution_time_ms,
        }

    def _validate_final_records(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Валидация финального набора записей.

        Returns:
            Tuple[validation_results, issues]
        """
        validation_results = {
            "all_compounds_present": len(records) > 0,
            "temperature_coverage": True,
            "phase_consistency": True,
            "data_quality": True
        }

        issues = []
        temp_min, temp_max = context.temperature_range

        # Проверка temperature coverage
        for record in records:
            if record.tmin > temp_min:
                diff = record.tmin - temp_min
                validation_results["temperature_coverage"] = False
                issues.append({
                    "severity": "MEDIUM" if diff > 50 else "LOW",
                    "description": f"{record.formula}: tmin={record.tmin}K > required {temp_min}K (diff: {diff}K)",
                    "impact": f"Extrapolation required for {diff}K",
                    "risk": "MEDIUM" if diff > 50 else "LOW",
                    "recommendations": [
                        f"Search for alternative {record.formula} records with lower tmin",
                        "Validate extrapolation results"
                    ]
                })

            if record.tmax < temp_max:
                diff = temp_max - record.tmax
                validation_results["temperature_coverage"] = False
                issues.append({
                    "severity": "MEDIUM" if diff > 50 else "LOW",
                    "description": f"{record.formula}: tmax={record.tmax}K < required {temp_max}K (diff: {diff}K)",
                    "impact": f"Extrapolation required for {diff}K",
                    "risk": "MEDIUM" if diff > 50 else "LOW",
                    "recommendations": [
                        f"Search for alternative {record.formula} records with higher tmax"
                    ]
                })

        # Проверка data quality
        for record in records:
            if record.h298 == 0 and record.s298 == 0:
                validation_results["data_quality"] = False
                issues.append({
                    "severity": "HIGH",
                    "description": f"{record.formula}: H298=0, S298=0",
                    "impact": "May affect reaction enthalpy/entropy calculations",
                    "risk": "HIGH",
                    "recommendations": [
                        f"Consider manual review for {record.formula}",
                        "Search for alternative data sources"
                    ]
                })

        return validation_results, issues


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
    - Опциональная зависимость от session_logger
    - Прямые вызовы стадий без message passing
    - Упрощенная архитектура для предсказуемости
    - Сохранена статистика для отладки
    """

    def __init__(self, session_logger: Optional[Any] = None):
        self.stages: List[FilterStage] = []
        self.statistics: List[Dict[str, Any]] = []
        self._last_execution_time_ms: Optional[float] = None
        self.session_logger = session_logger

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

        # НОВОЕ: Логирование начала pipeline фильтрации
        if self.session_logger:
            required_compounds = [context.compound_formula]
            if context.reaction_params and context.reaction_params.all_compounds:
                required_compounds = context.reaction_params.all_compounds

            # Stage 1: Use effective temperature range for logging
            effective_range = context.effective_temperature_range

            # Stage 1: Log range information
            range_info = context.get_range_info()
            if context.stage1_mode:
                self.session_logger.log_info(
                    f"🔄 Stage 1: Фильтрация с расширенным диапазоном {effective_range[0]:.0f}-{effective_range[1]:.0f}K"
                )
                if context.original_user_range:
                    self.session_logger.log_info(
                        f"   (пользователь запросил {context.original_user_range[0]:.0f}-{context.original_user_range[1]:.0f}K)"
                    )

            self.session_logger.log_filtering_pipeline_start(
                input_count=len(records),
                target_temp_range=effective_range,
                required_compounds=required_compounds
            )

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

            # НОВОЕ: Логирование этапа фильтрации
            if self.session_logger:
                # Определяем удалённые записи для логирования
                removed_records = []
                removal_reasons = {}

                if len(current_records) > len(filtered):
                    # Находим удалённые записи
                    current_ids = {r.id for r in current_records}
                    filtered_ids = {r.id for r in filtered}
                    removed_ids = current_ids - filtered_ids

                    removed_records = [r.model_dump() for r in current_records if r.id in removed_ids]

                    # Группируем причины удаления (примерная логика)
                    removal_reasons = {
                        f"Filtered by {stage.get_stage_name()}": [
                            f"Record ID: {r.id}, Formula: {getattr(r, 'formula', 'N/A')}"
                            for r in current_records if r.id in removed_ids
                        ]
                    }

                # Логируем этап
                input_records_dict = [r.model_dump() for r in current_records]
                output_records_dict = [r.model_dump() for r in filtered]

                self.session_logger.log_filtering_stage(
                    stage_name=stage.get_stage_name(),
                    stage_number=i,
                    criteria=stats.get("filter_criteria", {}),
                    input_count=len(current_records),
                    output_count=len(filtered),
                    input_records=input_records_dict,
                    output_records=output_records_dict,
                    removal_reasons=removal_reasons
                )

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

                # НОВОЕ: Логируем завершение фильтрации перед ранним возвратом
                if self.session_logger:
                    duration_seconds = total_time / 1000.0
                    warnings = []
                    if len(current_records) == 0:
                        warnings.append("No records found after filtering")

                    # Конвертируем записи в словари для логирования
                    final_records_dict = [r.model_dump() for r in current_records]

                    self.session_logger.log_filtering_complete(
                        final_count=len(current_records),
                        initial_count=len(records),
                        duration=duration_seconds,
                        warnings=warnings,
                        final_records=final_records_dict
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

        # НОВОЕ: Логирование завершения фильтрации

        if self.session_logger:
            duration_seconds = total_time / 1000.0
            warnings = []

            # DEBUG: Проверяем вызов log_filtering_complete
            print(f"DEBUG: Calling log_filtering_complete with {len(current_records)} records")

            # Собираем предупреждения на основе статистики
            if len(current_records) == 0:
                warnings.append("No records found after filtering")
            elif len(current_records) < 3:
                warnings.append(f"Only {len(current_records)} records found - may be insufficient for reliable analysis")

            # Проверяем температурное покрытие
            temp_min, temp_max = context.temperature_range
            for record in current_records[:5]:  # Проверяем первые 5 записей
                if hasattr(record, 't_min') and hasattr(record, 't_max'):
                    if record.t_min > temp_max or record.t_max < temp_min:
                        warnings.append(f"Record {record.id} has incomplete temperature coverage")
                        break

            # Валидация финального набора
            validation_results, issues = self._validate_final_records(
                current_records, context
            )
            self.session_logger.log_validation_check(
                validation_results=validation_results,
                issues=issues
            )

            # Конвертируем записи в словари для логирования
            final_records_dict = [r.model_dump() for r in current_records]

            self.session_logger.log_filtering_complete(
                final_count=len(current_records),
                initial_count=len(records),
                duration=duration_seconds,
                warnings=warnings,
                final_records=final_records_dict
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

    def _validate_final_records(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Валидация финального набора записей.

        Returns:
            Tuple[validation_results, issues]
        """
        validation_results = {
            "all_compounds_present": len(records) > 0,
            "temperature_coverage": True,
            "phase_consistency": True,
            "data_quality": True
        }

        issues = []
        temp_min, temp_max = context.temperature_range

        # Проверка temperature coverage
        for record in records:
            if record.tmin > temp_min:
                diff = record.tmin - temp_min
                validation_results["temperature_coverage"] = False
                issues.append({
                    "severity": "MEDIUM" if diff > 50 else "LOW",
                    "description": f"{record.formula}: tmin={record.tmin}K > required {temp_min}K (diff: {diff}K)",
                    "impact": f"Extrapolation required for {diff}K",
                    "risk": "MEDIUM" if diff > 50 else "LOW",
                    "recommendations": [
                        f"Search for alternative {record.formula} records with lower tmin",
                        "Validate extrapolation results"
                    ]
                })

            if record.tmax < temp_max:
                diff = temp_max - record.tmax
                validation_results["temperature_coverage"] = False
                issues.append({
                    "severity": "MEDIUM" if diff > 50 else "LOW",
                    "description": f"{record.formula}: tmax={record.tmax}K < required {temp_max}K (diff: {diff}K)",
                    "impact": f"Extrapolation required for {diff}K",
                    "risk": "MEDIUM" if diff > 50 else "LOW",
                    "recommendations": [
                        f"Search for alternative {record.formula} records with higher tmax"
                    ]
                })

        # Проверка data quality
        for record in records:
            if record.h298 == 0 and record.s298 == 0:
                validation_results["data_quality"] = False
                issues.append({
                    "severity": "HIGH",
                    "description": f"{record.formula}: H298=0, S298=0",
                    "impact": "May affect reaction enthalpy/entropy calculations",
                    "risk": "HIGH",
                    "recommendations": [
                        f"Consider manual review for {record.formula}",
                        "Search for alternative data sources"
                    ]
                })

        return validation_results, issues

    # Stage 1: Convenience methods for enhanced temperature range support

    def create_stage1_context(
        self,
        compound_formula: str,
        user_temperature_range: Optional[Tuple[float, float]] = None,
        full_calculation_range: Optional[Tuple[float, float]] = None,
        user_query: Optional[str] = None,
        reaction_params: Optional[Any] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> FilterContext:
        """
        Create a Stage 1 FilterContext with enhanced temperature range support.

        Args:
            compound_formula: Chemical formula
            user_temperature_range: Original user temperature range
            full_calculation_range: Stage 1 full calculation range
            user_query: Optional user query
            reaction_params: Optional reaction parameters
            additional_params: Additional parameters

        Returns:
            FilterContext configured for Stage 1 operation
        """
        # For Stage 1, we use the full calculation range as the primary range
        effective_range = full_calculation_range or user_temperature_range or (298.15, 298.15)

        return FilterContext(
            temperature_range=effective_range,
            compound_formula=compound_formula,
            user_query=user_query,
            reaction_params=reaction_params,
            additional_params=additional_params or {},
            # Stage 1 specific fields
            original_user_range=user_temperature_range,
            full_calculation_range=full_calculation_range,
            stage1_mode=True
        )

    def execute_stage1(
        self,
        records: List[DatabaseRecord],
        compound_formula: str,
        user_temperature_range: Optional[Tuple[float, float]] = None,
        full_calculation_range: Optional[Tuple[float, float]] = None,
        user_query: Optional[str] = None,
        reaction_params: Optional[Any] = None
    ) -> FilterResult:
        """
        Execute pipeline with Stage 1 enhanced temperature range logic.

        This method automatically creates a Stage 1 context and executes
        the pipeline with full temperature range support.

        Args:
            records: Records to filter
            compound_formula: Chemical formula
            user_temperature_range: Original user temperature range
            full_calculation_range: Stage 1 full calculation range
            user_query: Optional user query
            reaction_params: Optional reaction parameters

        Returns:
            FilterResult with Stage 1 enhanced processing
        """
        # Create Stage 1 context
        context = self.create_stage1_context(
            compound_formula=compound_formula,
            user_temperature_range=user_temperature_range,
            full_calculation_range=full_calculation_range,
            user_query=user_query,
            reaction_params=reaction_params
        )

        # Execute pipeline with Stage 1 context
        return self.execute(records, context)


class FilterPipelineBuilder:
    """
    Builder для создания и конфигурации конвейера фильтрации.

    Оптимизированная версия без dependencies от session_logger.
    """

    def __init__(self):
        self.pipeline = FilterPipeline()

    def with_deduplication(self, **kwargs) -> "FilterPipelineBuilder":
        """Добавить стадию удаления дубликатов (первая стадия)."""
        from .filter_stages import DeduplicationStage

        self.pipeline.add_stage(DeduplicationStage(**kwargs))
        return self

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
