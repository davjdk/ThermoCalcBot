# Этап 3: Разработка модульной фильтрации

**Длительность:** 4-5 дней  
**Приоритет:** Высокий  
**Статус:** Не начат  
**Зависимости:** Этап 2

---

## Описание

Создание конвейерной системы фильтрации с модульной архитектурой. Заменяет Results Filtering Agent детерминированной логикой с прозрачной статистикой на каждой стадии.

---

## Основные задачи

### 1. Создать структуру модуля `filtering/`

**Структура каталога:**
```
src/thermo_agents/filtering/
├── __init__.py                 # Экспорты
├── filter_pipeline.py          # Конвейер фильтрации
├── filter_stages.py            # Реализация стадий
├── temperature_resolver.py     # Расчёт температурных диапазонов
└── phase_resolver.py           # Определение фаз
```

**Задачи:**
- [ ] Создать каталог `src/thermo_agents/filtering/`
- [ ] Создать файл `__init__.py` с экспортами

---

### 2. Реализовать `FilterPipeline`

**Файл:** `src/thermo_agents/filtering/filter_pipeline.py`

**Архитектура:**
```python
from typing import Protocol, List, Dict, Any
from dataclasses import dataclass

@dataclass
class FilterContext:
    """Контекст фильтрации, передаваемый между стадиями."""
    temperature_range: Tuple[float, float]
    compound_formula: str
    user_query: Optional[str] = None
    additional_params: Dict[str, Any] = None

class FilterStage(Protocol):
    """Базовый протокол для стадии фильтрации."""
    
    def filter(
        self, 
        records: List[DatabaseRecord], 
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """Применить фильтр к записям."""
        ...
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получить статистику последней фильтрации."""
        ...
    
    def get_stage_name(self) -> str:
        """Название стадии для отчётности."""
        ...

@dataclass
class FilterResult:
    """Результат выполнения конвейера фильтрации."""
    filtered_records: List[DatabaseRecord]
    stage_statistics: List[Dict[str, Any]]
    is_found: bool
    failure_stage: Optional[int] = None
    failure_reason: Optional[str] = None

class FilterPipeline:
    """Конвейер фильтрации с возможностью добавления новых стадий."""
    
    def __init__(self):
        self.stages: List[FilterStage] = []
        self.statistics: List[Dict[str, Any]] = []
    
    def add_stage(self, stage: FilterStage) -> 'FilterPipeline':
        """Добавить стадию в конвейер (поддержка fluent API)."""
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
        """
        current_records = records
        self.statistics = []
        
        for i, stage in enumerate(self.stages, start=1):
            # Применить фильтр
            filtered = stage.filter(current_records, context)
            
            # Собрать статистику
            stats = stage.get_statistics()
            stats['stage_number'] = i
            stats['stage_name'] = stage.get_stage_name()
            stats['records_before'] = len(current_records)
            stats['records_after'] = len(filtered)
            self.statistics.append(stats)
            
            # Проверка провала
            if len(filtered) == 0:
                return FilterResult(
                    filtered_records=[],
                    stage_statistics=self.statistics,
                    is_found=False,
                    failure_stage=i,
                    failure_reason=f"Нет записей после стадии: {stage.get_stage_name()}"
                )
            
            current_records = filtered
        
        return FilterResult(
            filtered_records=current_records,
            stage_statistics=self.statistics,
            is_found=True
        )
```

**Задачи:**
- [ ] Реализовать протокол `FilterStage`
- [ ] Реализовать класс `FilterPipeline`
- [ ] Добавить метод `add_stage()` с fluent API
- [ ] Реализовать метод `execute()` с детальной статистикой
- [ ] Добавить обработку провалов фильтрации

---

### 3. Реализовать стадии фильтрации

**Файл:** `src/thermo_agents/filtering/filter_stages.py`

#### Стадия 1: FormulaMatchStage (выполняется в SQL)
*Уже реализована в `sql_builder.py` на Этапе 1*

#### Стадия 2: TemperatureFilterStage
```python
class TemperatureFilterStage:
    """Фильтрация по температурному диапазону."""
    
    def __init__(self):
        self.last_stats = {}
    
    def filter(
        self, 
        records: List[DatabaseRecord], 
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Фильтрация записей по температурному диапазону.
        
        Логика:
        - Проверка пересечения [Tmin, Tmax] с [tmin_user, tmax_user]
        - Обработка NULL: Tmin=NULL → 0K, Tmax=NULL → ∞
        """
        tmin_user, tmax_user = context.temperature_range
        filtered = []
        
        for record in records:
            tmin_rec = record.tmin if record.tmin is not None else 0.0
            tmax_rec = record.tmax if record.tmax is not None else float('inf')
            
            # Проверка пересечения интервалов
            if tmin_rec <= tmax_user and tmax_rec >= tmin_user:
                filtered.append(record)
        
        self.last_stats = {
            'temperature_range': context.temperature_range,
            'records_in_range': len(filtered),
            'records_out_of_range': len(records) - len(filtered)
        }
        
        return filtered
    
    def get_statistics(self) -> Dict[str, Any]:
        return self.last_stats
    
    def get_stage_name(self) -> str:
        return "Температурная фильтрация"
```

#### Стадия 3: PhaseSelectionStage
```python
from src.thermo_agents.filtering.phase_resolver import PhaseResolver

class PhaseSelectionStage:
    """Фильтрация по фазовому составу с учётом переходов."""
    
    def __init__(self, phase_resolver: PhaseResolver):
        self.phase_resolver = phase_resolver
        self.last_stats = {}
    
    def filter(
        self, 
        records: List[DatabaseRecord], 
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Выбор записей с корректной фазой для температурного диапазона.
        
        Логика:
        1. Определить ожидаемую фазу при заданной температуре
        2. Приоритизировать записи с правильной фазой
        3. Учесть фазовые переходы (Tmelt, Tboil)
        """
        tmin, tmax = context.temperature_range
        t_mid = (tmin + tmax) / 2  # Средняя температура
        
        phase_scores = []
        for record in records:
            expected_phase = self.phase_resolver.get_phase_at_temperature(
                record, t_mid
            )
            score = self._calculate_phase_score(record, expected_phase)
            phase_scores.append((record, score))
        
        # Сортировка по соответствию фазе
        phase_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Выбор записей с ненулевым score
        filtered = [r for r, score in phase_scores if score > 0]
        
        self.last_stats = {
            'phase_matches': len(filtered),
            'phase_mismatches': len(records) - len(filtered)
        }
        
        return filtered
    
    def _calculate_phase_score(
        self, 
        record: DatabaseRecord, 
        expected_phase: str
    ) -> float:
        """Расчёт соответствия фазы (0-1)."""
        # Извлечь фазу из формулы или поля phase
        record_phase = self._extract_phase(record)
        
        if record_phase == expected_phase:
            return 1.0
        elif record_phase is None:
            return 0.5  # Неизвестная фаза - средний приоритет
        else:
            return 0.0  # Неправильная фаза
    
    def _extract_phase(self, record: DatabaseRecord) -> Optional[str]:
        """Извлечь фазу из записи."""
        # Проверить поле phase
        if record.phase:
            return record.phase
        
        # Извлечь из формулы: H2O(g) → 'g'
        if '(' in record.formula and ')' in record.formula:
            start = record.formula.index('(') + 1
            end = record.formula.index(')')
            return record.formula[start:end]
        
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        return self.last_stats
    
    def get_stage_name(self) -> str:
        return "Фазовая фильтрация"
```

#### Стадия 4: ReliabilityPriorityStage
```python
class ReliabilityPriorityStage:
    """Приоритизация по надёжности и полноте данных."""
    
    def __init__(self, max_records: int = 1):
        self.max_records = max_records
        self.last_stats = {}
    
    def filter(
        self, 
        records: List[DatabaseRecord], 
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Выбор топ-N записей по критериям:
        1. ReliabilityClass (1 > 2 > 3 > 4)
        2. Полнота термодинамических данных
        3. Наличие фазовых переходов
        """
        scored_records = []
        for record in records:
            score = self._calculate_priority_score(record)
            scored_records.append((record, score))
        
        # Сортировка по убыванию score
        scored_records.sort(key=lambda x: x[1], reverse=True)
        
        # Выбор топ-N
        filtered = [r for r, _ in scored_records[:self.max_records]]
        
        self.last_stats = {
            'total_candidates': len(records),
            'selected': len(filtered),
            'average_score': sum(s for _, s in scored_records) / len(scored_records) if scored_records else 0
        }
        
        return filtered
    
    def _calculate_priority_score(self, record: DatabaseRecord) -> float:
        """Расчёт приоритета записи."""
        score = 0.0
        
        # Критерий 1: ReliabilityClass (инвертируем: 1=лучший)
        if record.reliability_class:
            score += (5 - record.reliability_class) * 100
        
        # Критерий 2: Полнота термодинамических данных
        thermo_fields = [record.h298, record.s298, record.f1, record.f2, 
                         record.f3, record.f4, record.f5, record.f6]
        completeness = sum(1 for f in thermo_fields if f is not None) / len(thermo_fields)
        score += completeness * 50
        
        # Критерий 3: Наличие фазовых переходов
        if record.tmelt is not None or record.tboil is not None:
            score += 10
        
        return score
    
    def get_statistics(self) -> Dict[str, Any]:
        return self.last_stats
    
    def get_stage_name(self) -> str:
        return "Приоритизация по надёжности"
```

**Задачи:**
- [ ] Реализовать `TemperatureFilterStage`
- [ ] Реализовать `PhaseSelectionStage`
- [ ] Реализовать `ReliabilityPriorityStage`
- [ ] Добавить расширяемость для новых стадий

---

### 4. Реализовать `TemperatureResolver`

**Файл:** `src/thermo_agents/filtering/temperature_resolver.py`

```python
class TemperatureResolver:
    """Расчёт температурных диапазонов и проверка покрытия."""
    
    def check_coverage(
        self, 
        records: List[DatabaseRecord], 
        target_range: Tuple[float, float]
    ) -> str:
        """
        Проверка покрытия температурного диапазона.
        
        Returns:
            'full' — весь диапазон покрыт
            'partial' — частичное покрытие
            'none' — нет покрытия
        """
        if not records:
            return 'none'
        
        tmin_target, tmax_target = target_range
        
        # Объединить все диапазоны записей
        covered_ranges = []
        for record in records:
            tmin_rec = record.tmin if record.tmin is not None else 0.0
            tmax_rec = record.tmax if record.tmax is not None else float('inf')
            covered_ranges.append((tmin_rec, tmax_rec))
        
        # Проверить покрытие
        coverage = self._calculate_coverage(covered_ranges, (tmin_target, tmax_target))
        
        if coverage >= 0.99:  # 99% покрытия = полное
            return 'full'
        elif coverage > 0:
            return 'partial'
        else:
            return 'none'
    
    def _calculate_coverage(
        self, 
        ranges: List[Tuple[float, float]], 
        target: Tuple[float, float]
    ) -> float:
        """Расчёт процента покрытия (0.0-1.0)."""
        # Алгоритм объединения интервалов и расчёта покрытия
        # (детали опущены для краткости)
        ...
```

**Задачи:**
- [ ] Реализовать `check_coverage()`
- [ ] Реализовать алгоритм объединения интервалов
- [ ] Добавить тесты на граничные случаи

---

### 5. Реализовать `PhaseResolver`

**Файл:** `src/thermo_agents/filtering/phase_resolver.py`

```python
class PhaseResolver:
    """Определение агрегатного состояния при заданной температуре."""
    
    def get_phase_at_temperature(
        self, 
        record: DatabaseRecord, 
        temperature: float
    ) -> str:
        """
        Определить фазу вещества при заданной температуре.
        
        Логика:
        - T < Tmelt → твёрдое (s)
        - Tmelt <= T < Tboil → жидкое (l)
        - T >= Tboil → газ (g)
        - Если Tmelt/Tboil = NULL → использовать фазу из формулы
        
        Returns:
            's', 'l', 'g', 'aq', или None
        """
        # Если есть фазовые переходы
        if record.tmelt is not None and temperature < record.tmelt:
            return 's'
        
        if record.tboil is not None:
            if record.tmelt and record.tmelt <= temperature < record.tboil:
                return 'l'
            elif temperature >= record.tboil:
                return 'g'
        
        # Если нет данных о переходах → извлечь из формулы
        return self._extract_phase_from_formula(record.formula)
    
    def _extract_phase_from_formula(self, formula: str) -> Optional[str]:
        """Извлечь фазу из формулы типа H2O(g)."""
        if '(' in formula and ')' in formula:
            start = formula.index('(') + 1
            end = formula.index(')')
            phase = formula[start:end]
            if phase in ['s', 'l', 'g', 'aq']:
                return phase
        return None
```

**Задачи:**
- [ ] Реализовать `get_phase_at_temperature()`
- [ ] Обработать граничные случаи (Tmelt = Tboil, сублимация)
- [ ] Добавить тесты на примерах H2O, Fe, NaCl

---

### 6. Написать unit-тесты

**Тестовые файлы:**
- `tests/test_filter_pipeline.py`
- `tests/test_filter_stages.py`
- `tests/test_temperature_resolver.py`
- `tests/test_phase_resolver.py`

**Примеры тестов:**

```python
def test_temperature_filter_stage():
    stage = TemperatureFilterStage()
    records = [
        DatabaseRecord(formula='H2O', tmin=273, tmax=373),
        DatabaseRecord(formula='H2O(g)', tmin=373, tmax=2000),
        DatabaseRecord(formula='Fe', tmin=1000, tmax=2000),
    ]
    context = FilterContext(temperature_range=(298, 500), compound_formula='H2O')
    
    filtered = stage.filter(records, context)
    
    assert len(filtered) == 2  # H2O и H2O(g)
    assert 'Fe' not in [r.formula for r in filtered]
```

**Задачи:**
- [ ] Написать >30 unit-тестов
- [ ] Покрытие тестами >80%
- [ ] Тесты на интеграцию конвейера

---

## Артефакты этапа

### Файлы для создания:
1. `src/thermo_agents/filtering/filter_pipeline.py`
2. `src/thermo_agents/filtering/filter_stages.py`
3. `src/thermo_agents/filtering/temperature_resolver.py`
4. `src/thermo_agents/filtering/phase_resolver.py`
5. `tests/test_filter_*.py` (4 файла)

---

## Критерии завершения этапа

✅ **Обязательные:**
1. Конвейер `FilterPipeline` работает со всеми 4 стадиями
2. Детальная статистика собирается на каждой стадии
3. `PhaseResolver` корректно определяет фазу с учётом Tmelt/Tboil
4. `TemperatureResolver` проверяет покрытие диапазонов
5. Все unit-тесты проходят
6. Покрытие тестами >80%

---

## Риски

| Риск                             | Вероятность | Влияние | Митигация                           |
| -------------------------------- | ----------- | ------- | ----------------------------------- |
| Сложная логика фазовых переходов | Высокая     | Среднее | Прототипирование в Jupyter (Этап 0) |
| Неполные данные Tmelt/Tboil      | Высокая     | Среднее | Fallback на фазу из формулы         |

---

## Следующий этап

➡️ **Этап 4:** Агрегация и форматирование
