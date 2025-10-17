# Этап 5: Архитектурные улучшения

**Длительность**: 5-7 дней
**Приоритет**: Высокий
**Риски**: Средние
**Зависимости**: Этапы 1-4 завершены

## Обзор

На этом этапе мы выполняем глубокие архитектурные улучшения: рефакторим fallback-логику в стратегии, разделяем сложные компоненты и добавляем Protocol definitions для явных интерфейсов. Это значительно улучшит модульность и тестируемость системы.

---

## Задача 5.1: Рефакторинг fallback логики в FilterPipeline

### Проблема
`FilterPipeline` имеет сложную логику fallback с множественными проверками и условиями (200+ строк в `_apply_fallback` и related methods). Это нарушает Single Responsibility Principle и усложняет тестирование.

### Решение
🔧 **РЕФАКТОРИТЬ fallback-логику в отдельные стратегии**

### Новая архитектура

```python
# src/thermo_agents/filtering/fallback_strategies.py
from typing import List, Protocol, Dict, Any
from abc import ABC, abstractmethod
from ..models.search import DatabaseRecord
from ..filtering.filter_pipeline import FilterContext

class FallbackStrategy(Protocol):
    """Протокол для стратегий fallback."""

    def apply(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Применить стратегию fallback.

        Args:
            context: Контекст фильтрации
            records: Доступные записи

        Returns:
            Отфильтрованные записи или пустой список
        """
        ...

class BaseFallbackStrategy(ABC):
    """Базовый класс для стратегий fallback."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def apply(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        pass

    def can_apply(self, context: FilterContext) -> bool:
        """Проверить, можно ли применить стратегию."""
        return True

class IonicRecordsFallback(BaseFallbackStrategy):
    """Fallback на ионные формы соединений."""

    def __init__(self):
        super().__init__("ionic_records")

    def apply(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Включить ионные формы если нет других данных."""
        if not self.can_apply(context):
            return []

        ionic_records = [
            record for record in records
            if self._is_ionic_form(record.Formula)
        ]

        context.logger.info(f"Fallback: included {len(ionic_records)} ionic records")
        return ionic_records[:3]  # TOP-N

    def _is_ionic_form(self, formula: str) -> bool:
        """Проверить, является ли формула ионной."""
        # Логика детекции ионных форм
        return "+" in formula or "-" in formula

class CompositeFormulaFallback(BaseFallbackStrategy):
    """Fallback на составные формулы."""

    def __init__(self):
        super().__init__("composite_formula")

    def apply(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Искать составные формулы (Li2O*TiO2 для Li2TiO3)."""
        if not self.can_apply(context):
            return []

        # Логика поиска составных формул
        composite_candidates = self._expand_composite_candidates(context.compound_formula)

        matching_records = []
        for candidate in composite_candidates:
            matches = [
                record for record in records
                if candidate in record.Formula
            ]
            matching_records.extend(matches)

        context.logger.info(f"Fallback: found {len(matching_records)} composite matches")
        return matching_records[:3]

    def _expand_composite_candidates(self, formula: str) -> List[str]:
        """Расширить составные формулы в кандидаты."""
        # Логика расширения составных формул
        pass

class TopRecordsFallback(BaseFallbackStrategy):
    """Fallback на top-N наиболее надёжные записи."""

    def __init__(self, top_n: int = 3):
        super().__init__("top_records")
        self.top_n = top_n

    def apply(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Вернуть top-N записей отсортированных по надёжности."""
        if not records:
            return []

        # Сортировка по надёжности (ReliabilityClass)
        sorted_records = sorted(records, key=lambda r: r.ReliabilityClass)

        top_records = sorted_records[:self.top_n]
        context.logger.warning(f"Fallback: returning top {len(top_records)} records")

        return top_records

class FallbackManager:
    """Менеджер стратегий fallback."""

    def __init__(self, strategies: List[FallbackStrategy]):
        self.strategies = strategies

    def apply_fallback(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Применить стратегии fallback по порядку."""
        for strategy in self.strategies:
            try:
                result = strategy.apply(context, records)
                if result:
                    context.logger.info(f"Fallback successful with {strategy.name}")
                    return result
            except Exception as e:
                context.logger.error(f"Fallback strategy {strategy.name} failed: {e}")
                continue

        context.logger.error("All fallback strategies failed")
        return []
```

### Интеграция в FilterPipeline

```python
# src/thermo_agents/filtering/filter_pipeline.py
from .fallback_strategies import (
    FallbackManager,
    IonicRecordsFallback,
    CompositeFormulaFallback,
    TopRecordsFallback
)

class FilterPipeline:
    def __init__(self, config: FilterConfig):
        # ... существующий код ...

        # Инициализация fallback стратегий
        self.fallback_manager = FallbackManager([
            IonicRecordsFallback(),
            CompositeFormulaFallback(),
            TopRecordsFallback(top_n=3)
        ])

    def _apply_fallback(self, context: FilterContext, records: List[DatabaseRecord]) -> List[DatabaseRecord]:
        """Применить стратегии fallback."""
        return self.fallback_manager.apply_fallback(context, records)
```

---

## Задача 5.2: Разделение PhaseBasedTemperatureStage

### Проблема
`PhaseBasedTemperatureStage` объединяет слишком много логики (температура + фаза + scoring + выбор), что нарушает Single Responsibility Principle и усложняет тестирование.

### Решение
🔧 **РАЗДЕЛИТЬ на два отдельных компонента**:
- `TemperatureFilterStage` - фильтрация по температуре
- `PhaseSelectionStage` - умный выбор фазы с учётом скоринга

### Новая архитектура

```python
# src/thermo_agents/filtering/temperature_filter_stage.py
from typing import List
from .filter_stages import FilterStage, FilterContext
from ..models.search import DatabaseRecord
from .constants import MIN_TEMPERATURE_COVERAGE_RATIO

class TemperatureFilterStage(FilterStage):
    """Стадия фильтрации по температурному диапазону."""

    def __init__(self):
        super().__init__("temperature_filter")

    def filter(self, records: List[DatabaseRecord], context: FilterContext) -> List[DatabaseRecord]:
        """Отфильтровать записи по температурному покрытию."""
        if not context.temperature_range:
            return records

        temp_min, temp_max = context.temperature_range
        filtered_records = []

        for record in records:
            if self._has_temperature_coverage(record, temp_min, temp_max):
                filtered_records.append(record)

        context.logger.info(f"Temperature filter: {len(filtered_records)}/{len(records)} records remain")
        return filtered_records

    def _has_temperature_coverage(self, record: DatabaseRecord, temp_min: float, temp_max: float) -> bool:
        """Проверить покрытие температурного диапазона."""
        # Учёт фазовых переходов
        if self._is_phase_transition_in_range(record, temp_min, temp_max):
            return True

        # Базовое покрытие диапазона
        if (record.tmin <= temp_min and record.tmax >= temp_max):
            return True

        # Частичное покрытие
        coverage_ratio = self._calculate_coverage_ratio(record, temp_min, temp_max)
        return coverage_ratio >= MIN_TEMPERATURE_COVERAGE_RATIO

    def _is_phase_transition_in_range(self, record: DatabaseRecord, temp_min: float, temp_max: float) -> bool:
        """Проверить, есть ли фазовый переход в диапазоне."""
        # Логика проверки фазовых переходов
        pass

    def _calculate_coverage_ratio(self, record: DatabaseRecord, temp_min: float, temp_max: float) -> float:
        """Рассчитать долю покрытия температурного диапазона."""
        # Логика расчёта покрытия
        pass

# src/thermo_agents/filtering/phase_selection_stage.py
from typing import List, Optional
from .filter_stages import FilterStage, FilterContext
from ..models.search import DatabaseRecord
from .constants import DEFAULT_RELIABILITY_WEIGHT, DEFAULT_COVERAGE_WEIGHT

class PhaseSelectionStage(FilterStage):
    """Стадия умного выбора фазы с учётом скоринга."""

    def __init__(self, reliability_weight: float = DEFAULT_RELIABILITY_WEIGHT,
                 coverage_weight: float = DEFAULT_COVERAGE_WEIGHT):
        super().__init__("phase_selection")
        self.reliability_weight = reliability_weight
        self.coverage_weight = coverage_weight

    def filter(self, records: List[DatabaseRecord], context: FilterContext) -> List[DatabaseRecord]:
        """Выбрать оптимальные записи по фазам с учётом скоринга."""
        if not records:
            return []

        # Группировка по фазам
        phase_groups = self._group_by_phase(records)
        best_records = []

        for phase, phase_records in phase_groups.items():
            best_record = self._select_best_record(phase_records, context)
            if best_record:
                best_records.append(best_record)

        context.logger.info(f"Phase selection: {len(best_records)} phases selected")
        return best_records

    def _group_by_phase(self, records: List[DatabaseRecord]) -> Dict[str, List[DatabaseRecord]]:
        """Сгруппировать записи по фазам."""
        phases = {}
        for record in records:
            phase = record.Phase
            if phase not in phases:
                phases[phase] = []
            phases[phase].append(record)
        return phases

    def _select_best_record(self, phase_records: List[DatabaseRecord], context: FilterContext) -> Optional[DatabaseRecord]:
        """Выбрать лучшую запись для фазы."""
        if not phase_records:
            return None

        # Скоринг записей
        scored_records = []
        for record in phase_records:
            score = self._calculate_record_score(record, context)
            scored_records.append((record, score))

        # Сортировка по скору
        scored_records.sort(key=lambda x: x[1], reverse=True)
        return scored_records[0][0]

    def _calculate_record_score(self, record: DatabaseRecord, context: FilterContext) -> float:
        """Рассчитать综合 скор для записи."""
        reliability_score = self._calculate_reliability_score(record)
        coverage_score = self._calculate_coverage_score(record, context)

        total_score = (
            self.reliability_weight * reliability_score +
            self.coverage_weight * coverage_score
        )

        return total_score

    def _calculate_reliability_score(self, record: DatabaseRecord) -> float:
        """Рассчитать скор надёжности."""
        # Инверсия класса надёжности (1 = лучший)
        return 1.0 / record.ReliabilityClass

    def _calculate_coverage_score(self, record: DatabaseRecord, context: FilterContext) -> float:
        """Рассчитать скор температурного покрытия."""
        if not context.temperature_range:
            return 1.0

        temp_min, temp_max = context.temperature_range
        coverage_ratio = self._calculate_temperature_coverage(record, temp_min, temp_max)
        return coverage_ratio
```

### Обновление конвейера

```python
# src/thermo_agents/filtering/filter_pipeline.py
from .temperature_filter_stage import TemperatureFilterStage
from .phase_selection_stage import PhaseSelectionStage

class FilterPipeline:
    def __init__(self, config: FilterConfig):
        # ... существующий код ...

        # Обновление стадий фильтрации
        self.stages = [
            ReactionValidationStage(),
            ComplexSearchStage(),
            TemperatureFilterStage(),  # Новая стадия
            PhaseSelectionStage(),     # Новая стадия
            ReliabilityPriorityStage(),
            TemperatureCoverageStage()
        ]
```

---

## Задача 5.3: Добавление Protocol definitions

### Проблема
Некоторые компоненты не имеют явных интерфейсов, что затрудняет mock testing и расширение.

### Решение
🔧 **ДОБАВИТЬ Protocol definitions для ключевых абстракций**

### Новые протоколы

```python
# src/thermo_agents/protocols.py
from typing import Protocol, List, Tuple, Optional, Dict, Any
from abc import abstractmethod

# Протоколы для поиска
class CompoundSearcherProtocol(Protocol):
    """Протокол для поиска соединений в базе данных."""

    def search_compound(
        self,
        formula: str,
        temperature_range: Optional[Tuple[float, float]] = None,
        phase: Optional[str] = None,
        limit: int = 100
    ) -> 'CompoundSearchResult':
        """Найти соединение в базе данных."""
        ...

# Протоколы для фильтрации
class FilterStageProtocol(Protocol):
    """Протокол для стадии фильтрации."""

    def filter(
        self,
        records: List['DatabaseRecord'],
        context: 'FilterContext'
    ) -> List['DatabaseRecord']:
        """Отфильтровать записи."""
        ...

    def get_stage_name(self) -> str:
        """Получить имя стадии."""
        ...

class FilterPipelineProtocol(Protocol):
    """Протокол для конвейера фильтрации."""

    def apply_filters(
        self,
        records: List['DatabaseRecord'],
        context: 'FilterContext'
    ) -> List['DatabaseRecord']:
        """Применить все фильтры."""
        ...

    def get_filter_statistics(self) -> 'FilterStatistics':
        """Получить статистику фильтрации."""
        ...

# Протоколы для агрегации
class ReactionAggregatorProtocol(Protocol):
    """Протокол для агрегации данных реакции."""

    def aggregate_reaction_data(
        self,
        compounds_results: List['CompoundSearchResult'],
        reaction_params: 'ExtractedReactionParameters'
    ) -> 'AggregatedReactionData':
        """Агрегировать данные по реакции."""
        ...

# Протоколы для форматирования
class TableFormatterProtocol(Protocol):
    """Протокол для форматирования таблиц."""

    def format_table(
        self,
        data: 'AggregatedReactionData',
        format_style: str = "fancy_grid"
    ) -> str:
        """Отформатировать данные в таблицу."""
        ...

class StatisticsFormatterProtocol(Protocol):
    """Протокол для форматирования статистики."""

    def format_statistics(
        self,
        data: 'AggregatedReactionData'
    ) -> str:
        """Отформатировать статистику."""
        ...

# Протоколы для логирования
class LoggerProtocol(Protocol):
    """Протокол для логирования."""

    def info(self, message: str, **kwargs) -> None:
        """Записать информационное сообщение."""
        ...

    def error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Записать сообщение об ошибке."""
        ...

    def debug(self, message: str, **kwargs) -> None:
        """Записать отладочное сообщение."""
        ...

# Протоколы для хранения
class StorageProtocol(Protocol):
    """Протокол для хранения данных."""

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Сохранить значение."""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение."""
        ...

    def delete(self, key: str) -> bool:
        """Удалить значение."""
        ...

    def exists(self, key: str) -> bool:
        """Проверить существование."""
        ...
```

### Обновление компонентов для использования протоколов

```python
# src/thermo_agents/orchestrator.py
from src.thermo_agents.protocols import (
    CompoundSearcherProtocol,
    FilterPipelineProtocol,
    ReactionAggregatorProtocol,
    LoggerProtocol
)

class ThermoOrchestrator:
    def __init__(
        self,
        searcher: CompoundSearcherProtocol,
        filter_pipeline: FilterPipelineProtocol,
        aggregator: ReactionAggregatorProtocol,
        logger: LoggerProtocol
    ):
        self.searcher = searcher
        self.filter_pipeline = filter_pipeline
        self.aggregator = aggregator
        self.logger = logger
```

---

## Порядок выполнения

### Шаг 1: Подготовка (1 день)
```bash
# Создать ветку
git checkout -b refactor/stage-5-architecture

# Создать структуру
mkdir -p src/thermo_agents/filtering/strategies
mkdir -p tests/unit/strategies
```

### Шаг 2: Рефакторинг fallback стратегий (2 дня)
1. Создать протоколы и базовые классы
2. Реализовать конкретные стратегии
3. Создать FallbackManager
4. Интегрировать в FilterPipeline
5. Написать тесты для каждой стратегии

### Шаг 3: Разделение PhaseBasedTemperatureStage (2 дня)
1. Создать TemperatureFilterStage
2. Создать PhaseSelectionStage
3. Обновить FilterPipeline
4. Мигрировать тесты
5. Валидация функциональности

### Шаг 4: Добавление Protocol definitions (1 день)
1. Создать файл protocols.py
2. Определить все необходимые протоколы
3. Обновить компоненты для использования протоколов
4. Обновить тесты для mock объектов

### Шаг 5: Валидация (1 день)
```bash
# Запустить все тесты
uv run pytest tests/ -v

# Интеграционные тесты
uv run pytest tests/integration/ -v

# Проверить архитектурные метрики
uv run radon cc src/thermo_agents/ -a
```

---

## Ожидаемые результаты

### Улучшение архитектуры
- ✅ **Single Responsibility**: Каждый компонент имеет одну ответственность
- ✅ **Open/Closed**: Легко добавлять новые стратегии фильтрации
- ✅ **Dependency Inversion**: Зависимость от абстракций (протоколов)
- ✅ **Strategy Pattern**: Гибкая система fallback стратегий

### Качество кода
- ✅ **Тестируемость**: Легко тестировать отдельные стратегии
- ✅ **Читаемость**: Понятная структура и разделение ответственности
- ✅ **Поддерживаемость**: Легко добавлять новые функции
- ✅ **Расширяемость**: Протоколы позволяют реализовывать новые компоненты

### Производительность
- ✅ **Модульность**: Независимая оптимизация компонентов
- ✅ **Переиспользование**: Компоненты можно использовать в разных контекстах
- ✅ **Параллелизм**: Легко распараллеливать независимые стадии

---

## Критерии завершения

- [ ] Fallback стратегии реализованы и протестированы
- [ ] PhaseBasedTemperatureStage разделён на два компонента
- [ ] Protocol definitions созданы и используются
- [ ] Все существующие тесты проходят
- [ ] Новые тесты для стратегий написаны
- [ ] Cyclomatic complexity снижен на 20%
- [ ] Code review завершён
- [ ] Ветка слита с основной

---

## Метрики архитектуры

До и после рефакторинга:
- **Cyclomatic complexity**: Снижение на 20%
- **Coupling**: Снижение взаимозависимостей
- **Cohesion**: Повышение связанности внутри модулей
- **Testability**: Улучшение покрытия и тестируемости

---

## Следующий этап

После завершения Этапа 5 можно переходить к **Этапу 6: Оптимизация**, который включает кэширование, ленивую инициализацию и улучшение типизации.