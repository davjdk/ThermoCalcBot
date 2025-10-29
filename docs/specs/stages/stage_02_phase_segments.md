# Этап 2: Построение фазовых сегментов

## Общая информация

- **Этап:** 2 из 6
- **Название:** Построение фазовых сегментов
- **Статус:** Запланирован
- **Приоритет:** Критический
- **Длительность (оценка):** 4-5 дней
- **Зависимости:** Этап 1 (полные данные из базы)

## Проблема

После Этапа 1 система будет находить все записи для веществ, но не сможет эффективно их использовать для многофазных расчётов. Текущая система предполагает использование одной фазы и одной записи на вещество.

**Проблемы с текущим подходом:**
1. Нет понимания фазовых переходов (s→l→g)
2. Нет автоматического определения температурных сегментов
3. Нет логики переключения между записями в одной фазе
4. Отсутствует учёт температур плавления/кипения

## Цель этапа

Создать систему автоматического построения фазовых сегментов для каждого вещества, обеспечивающую бесшовную работу с многократными записями и фазовыми переходами.

## Задачи этапа

### 1. Расширение моделей данных

**Файл:** `src/thermo_agents/models/search.py`

**Задачи:**
- Создать модель `PhaseSegment` для описания сегмента одной фазы
- Создать модель `PhaseTransition` для описания переходов
- Создать модель `MultiPhaseCompoundData` для агрегации всех сегментов
- Обновить `CompoundSearchResult` для поддержки многофазных данных

```python
@dataclass
class PhaseSegment:
    phase: str  # 's', 'l', 'g', 'aq'
    temperature_range: Tuple[float, float]
    records: List[DatabaseRecord]
    active_record: Optional[DatabaseRecord] = None

@dataclass
class PhaseTransition:
    transition_type: str  # 'melting', 'boiling', 'sublimation'
    temperature: float
    enthalpy_change: float  # ΔH в кДж/моль
    from_phase: str
    to_phase: str

@dataclass
class MultiPhaseCompoundData:
    formula: str
    phase_segments: List[PhaseSegment]
    phase_transitions: List[PhaseTransition]
    total_range: Tuple[float, float]
    melting_point: Optional[float] = None
    boiling_point: Optional[float] = None
```

### 2. Создание PhaseSegmentBuilder

**Файл:** `src/thermo_agents/filtering/phase_segment_builder.py`

**Задачи:**
- Создать класс `PhaseSegmentBuilder`
- Реализовать построение фазовых сегментов на основе всех записей
- Реализовать определение точек переходов (tmelt, tboil)
- Реализовать распределение записей по сегментам

**Основные методы:**
```python
@dataclass
class PhaseSegmentBuilder:
    def build_phase_segments(
        self,
        records: List[DatabaseRecord],
        temperature_range: Tuple[float, float]
    ) -> MultiPhaseCompoundData

    def _extract_transition_temperatures(
        self,
        records: List[DatabaseRecord]
    ) -> Tuple[Optional[float], Optional[float]]

    def _create_phase_segments(
        self,
        records: List[DatabaseRecord],
        temp_range: Tuple[float, float],
        tmelt: Optional[float],
        tboil: Optional[float]
    ) -> List[PhaseSegment]

    def _assign_records_to_segments(
        self,
        records: List[DatabaseRecord],
        segments: List[PhaseSegment]
    ) -> None
```

### 3. Модификация PhaseResolver

**Файл:** `src/thermo_agents/filtering/phase_resolver.py`

**Задачи:**
- Обновить для работы с `MultiPhaseCompoundData`
- Добавить метод `resolve_phase_at_temperature()`
- Реализовать определение активного сегмента для температуры
- Добавить логику выбора правильной записи в сегменте

```python
class PhaseResolver:
    def resolve_phase_at_temperature(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> Tuple[str, PhaseSegment]

    def get_active_record(
        self,
        segment: PhaseSegment,
        temperature: float
    ) -> DatabaseRecord
```

### 4. Создание RecordSelector

**Файл:** `src/thermo_agents/filtering/record_selector.py`

**Задачи:**
- Создать утилиту для выбора оптимальной записи
- Реализовать логику переключения между записями
- Обеспечить бесшовные переходы между температурными диапазонами

```python
@dataclass
class RecordSelector:
    def select_record_for_temperature(
        self,
        records: List[DatabaseRecord],
        temperature: float
    ) -> DatabaseRecord

    def find_transition_points(
        self,
        records: List[DatabaseRecord]
    ) -> List[Tuple[float, DatabaseRecord, DatabaseRecord]]
```

### 5. Интеграция в FilterPipeline

**Файл:** `src/thermo_agents/filtering/filter_pipeline.py`

**Задачи:**
- Добавить новую стадию `PhaseSegmentBuildingStage`
- Интегрировать `PhaseSegmentBuilder` в конвейер
- Обновить выходные данные для поддержки многофазных результатов
- Модифицировать существующие стадии для работы с сегментами

```python
class PhaseSegmentBuildingStage(FilterStage):
    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> FilterResult:
        # Построение фазовых сегментов из всех записей
```

## Логика построения сегментов

### Алгоритм работы

1. **Извлечение температур переходов:**
   ```
   tmelt = records[0].tmelt  # Обычно одинаковы во всех записях
   tboil = records[0].tboil
   ```

2. **Создание сегментов:**
   ```
   if start_temp < tmelt:
       solid_segment = PhaseSegment('s', [start_temp, min(tmelt, end_temp)])

   if tmelt <= start_temp < tboil or overlap with [tmelt, tboil]:
       liquid_segment = PhaseSegment('l', [max(tmelt, start_temp), min(tboil, end_temp)])

   if end_temp >= tboil:
       gas_segment = PhaseSegment('g', [max(tboil, start_temp), end_temp])
   ```

3. **Распределение записей:**
   ```
   for record in records:
       if record.phase == 's':
           solid_segment.records.append(record)
       elif record.phase == 'l':
           liquid_segment.records.append(record)
       elif record.phase == 'g':
           gas_segment.records.append(record)
   ```

4. **Оптимизация записей в сегментах:**
   - Сортировка по tmin
   - Определение активной записи для каждого диапазона
   - Проверка покрытия температурного диапазона

### Пример для FeO

```
Входные данные:
- 6 записей: 3(s), 1(l), 2(g)
- tmelt = 1650K, tboil = 3687K
- Расчётный диапазон: 298-5000K

Результат:
PhaseSegment 1: s, [298, 1650), records: [298-600K, 600-900K, 900-1300K]
PhaseTransition: melting at 1650K, ΔH = 31.5 кДж/моль
PhaseSegment 2: l, [1650, 3687), records: [1650-5000K]
PhaseTransition: boiling at 3687K, ΔH = 340.0 кДж/моль
PhaseSegment 3: g, [3687, 5000], records: [400-2100K]
```

## Критерии завершения

### Функциональные критерии

1. **Построение сегментов:**
   - [ ] Для FeO создаётся 3 сегмента (s, l, g)
   - [ ] Правильно определяются tmelt и tboil
   - [ ] Записи корректно распределяются по сегментам
   - [ ] Температурные диапазоны покрываются без пробелов

2. **Переходы между фазами:**
   - [ ] Создаются объекты `PhaseTransition`
   - [ ] Температуры переходов соответствуют tmelt/tboil
   - [ ] Определяются энтальпии переходов

3. **Выбор записей:**
   - [ ] Для каждой температуры выбирается корректная запись
   - [ ] Переключение между записями происходит на границах диапазонов
   - [ ] Отсутствуют разрывы в покрытии температур

4. **Интеграция:**
   - [ ] `FilterPipeline` создаёт `MultiPhaseCompoundData`
   - [ ] `PhaseResolver` работает с сегментами
   - [ ] Данные передаются в `ThermodynamicCalculator`

### Технические критерии

1. **Производительность:**
   - [ ] Построение сегментов занимает <100мс на вещество
   - [ ] Использование памяти увеличивается умеренно
   - [ ] Кэширование работает для сегментов

2. **Качество кода:**
   - [ ] Все новые классы имеют полную документацию
   - [ ] Добавлены unit тесты для всех компонентов
   - [ ] Интеграционные тесты покрывают основные сценарии
   - [ ] Покрытие кода тестами ≥ 85%

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_phase_segment_builder.py`

```python
class TestPhaseSegmentBuilder:
    def test_build_simple_segments(self)
    def test_build_segments_with_transitions(self)
    def test_extract_transition_temperatures(self)
    def test_assign_records_to_segments(self)
    def test_handle_missing_transitions(self)
    def test_complex_phase_coverage(self)
```

**Файл:** `tests/unit/test_record_selector.py`

```python
class TestRecordSelector:
    def test_select_record_for_temperature(self)
    def test_find_transition_points(self)
    def test_handle_edge_temperatures(self)
    def test_multiple_records_same_range(self)
```

### Интеграционные тесты

**Файл:** `tests/integration/test_stage_02_phase_segments.py`

```python
class TestStage2PhaseSegments:
    async def test_feo_phase_segments(self)
    async def test_h2s_phase_segments(self)
    async def test_water_phase_segments(self)
    async def test_multi_compound_consistency(self)
    async def test_edge_case_single_phase(self)
    async def test_phase_transitions_integration(self)
```

### Тесты производительности

```python
class TestStage2Performance:
    def test_segment_building_performance(self)
    def test_memory_usage_optimization(self)
    def test_large_dataset_handling(self)
```

## Риски и митигации

### Риск 1: Сложность определения переходов
- **Проблема:** Не все вещества имеют полные данные о переходах
- **Митигация:** Эвристические методы, fallback к стандартным значениям

### Риск 2: Неконсистентность данных
- **Проблема:** Разные tmelt/tboil в записях одного вещества
- **Митигация:** Валидация и выбор наиболее надёжных данных

### Риск 3: Пробелы в покрытии температур
- **Проблема:** Некоторые диапазоны могут не покрываться записями
- **Митигация:** Экстраполяция, информирование пользователя

### Риск 4: Производительность
- **Проблема:** Усложнение логики может замедлить обработку
- **Митигация:** Кэширование, оптимизация алгоритмов

## Документация

### Обновить:
1. **ARCHITECTURE.md** — описать архитектуру сегментов
2. **Models Reference** — документировать новые модели
3. **Filter Pipeline** — описать новую стадию

### Создать:
1. **Phase Segments Guide** — руководство по использованию сегментов
2. **Algorithm Documentation** — детальное описание алгоритмов

## Временная шкала

- **День 1:** Создание моделей данных и базовой структуры
- **День 2:** Реализация `PhaseSegmentBuilder` и базовой логики
- **День 3:** Создание `RecordSelector` и интеграция с `PhaseResolver`
- **День 4:** Интеграция в `FilterPipeline` и тестирование
- **День 5:** Оптимизация, документация, финальное тестирование

## Ответственные

- **Разработчик:** Основной разработчик
- **Code Review:** Ведущий архитектор
- **Тестирование:** QA-инженер

## Критерии успеха

1. **FeO пример:** Создаёт 3 корректных сегмента с переходами
2. **Все вещества:** Работает для любых данных из базы
3. **Производительность:** <100мс на построение сегментов
4. **Тесты:** Все тесты проходят, покрытие ≥ 85%
5. **Интеграция:** Готов к Этапу 3 (автоматический выбор записей)

---

**Статус:** Готов к реализации после Этапа 1
**Следующий этап:** Этап 3: Автоматический выбор записей