# Этап 3: Автоматический выбор записей

## Общая информация

- **Этап:** 3 из 6
- **Название:** Автоматический выбор записей
- **Статус:** Запланирован
- **Приоритет:** Критический
- **Длительность (оценка):** 3-4 дня
- **Зависимости:** Этап 1 (полные данные), Этап 2 (фазовые сегменты)

## Проблема

После Этапа 2 система сможет строить фазовые сегменты, но `ThermodynamicCalculator` не сможет эффективно работать с многократными записями внутри каждого сегмента.

**Текущие ограничения:**
1. `ThermodynamicCalculator` ожидает одну запись на вещество
2. Нет логики переключения между записями при изменении температуры
3. Потеря данных на границах температурных диапазонов записей
4. Отсутствие бесшовной интеграции между записями

**Пример проблемы с FeO:**
```
Сегмент s [298-1650K] содержит 3 записи:
- Record 1: 298-600K, H298 = -265.053 ✓
- Record 2: 600-900K, H298 = 0.0 ❌
- Record 3: 900-1300K, H298 = 0.0 ❌

Проблема: Как бесшовно перейти от Record 1 к Record 2 при T=600K?
```

## Цель этапа

Реализовать бесшовное переключение между записями внутри фазовых сегментов, обеспечивая непрерывность термодинамических расчётов через все температурные диапазоны.

## Задачи этапа

### 1. Модификация ThermodynamicCalculator

**Файл:** `src/thermo_agents/calculations/thermodynamic_calculator.py`

**Задачи:**
- Обновить для работы с `MultiPhaseCompoundData`
- Реализовать метод для работы с многократными записями
- Добавить логику переключения между записями
- Обеспечить непрерывность расчётов через границы диапазонов

**Основные изменения:**
```python
class ThermodynamicCalculator:
    def calculate_properties_multi_record(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> ThermodynamicProperties

    def calculate_table_multi_record(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Tuple[float, float],
        num_points: int = 100
    ) -> ThermodynamicTable

    def _select_active_record(
        self,
        segment: PhaseSegment,
        temperature: float
    ) -> DatabaseRecord

    def _handle_record_transition(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        temperature: float
    ) -> Tuple[float, float]
```

### 2. Создание RecordTransitionManager

**Файл:** `src/thermo_agents/calculations/record_transition_manager.py`

**Задачи:**
- Создать класс для управления переходами между записями
- Реализовать логику бесшовного переключения
- Обеспечить сохранение непрерывности H и S
- Обработать возможные разрывы в данных

```python
@dataclass
class RecordTransitionManager:
    def ensure_continuity(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition_temp: float
    ) -> Tuple[float, float]

    def calculate_transition_corrections(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        temperature: float
    ) -> Dict[str, float]

    def validate_record_compatibility(
        self,
        record1: DatabaseRecord,
        record2: DatabaseRecord
    ) -> bool
```

### 3. Расширение MultiPhaseCompoundData

**Файл:** `src/thermo_agents/models/search.py`

**Задачи:**
- Добавить методы для работы с записями
- Реализовать кэширование активных записей
- Добавить предвычисленные переходы между записями

```python
@dataclass
class MultiPhaseCompoundData:
    # ... существующие поля

    # Новые поля
    record_transitions: Dict[Tuple[int, int], RecordTransition] = field(default_factory=dict)
    active_records_cache: Dict[float, DatabaseRecord] = field(default_factory=dict)

    def get_record_at_temperature(self, temperature: float) -> DatabaseRecord
    def get_transition_between_records(self, id1: int, id2: int) -> Optional[RecordTransition]
    def precompute_transitions(self) -> None
```

### 4. Обновление RecordSelector

**Файл:** `src/thermo_agents/filtering/record_selector.py`

**Задачи:**
- Обновить для работы с `MultiPhaseCompoundData`
- Реализовать кэширование выбранных записей
- Добавить предсказание следующей записи

```python
class RecordSelector:
    def select_record_for_temperature(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> DatabaseRecord

    def predict_next_record(
        self,
        current_record: DatabaseRecord,
        temperature: float,
        step: float
    ) -> Optional[DatabaseRecord]

    def build_record_sequence(
        self,
        segment: PhaseSegment
    ) -> List[DatabaseRecord]
```

### 5. Интеграция в расчёты реакций

**Файл:** `src/thermo_agents/calculations/reaction_calculator.py` (новый файл)

**Задачи:**
- Создать калькулятор для многофазных реакций
- Реализовать учёт разных записей для разных веществ
- Обеспечить бесшовные расчёты ΔH, ΔS, ΔG

```python
@dataclass
class MultiPhaseReactionCalculator:
    def calculate_reaction_properties(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature: float
    ) -> ReactionProperties

    def calculate_reaction_table(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature_range: Tuple[float, float],
        num_points: int = 50
    ) -> ReactionTable
```

## Логика выбора записей

### Алгоритм работы

1. **Построение последовательности записей:**
   ```python
   def build_record_sequence(segment):
       # Сортировка записей по tmin
       sorted_records = sorted(segment.records, key=lambda r: r.tmin)

       # Проверка покрытия диапазона
       for i, record in enumerate(sorted_records):
           if i > 0:
               prev = sorted_records[i-1]
               assert abs(record.tmin - prev.tmax) < 1e-6

       return sorted_records
   ```

2. **Выбор активной записи:**
   ```python
   def select_record_for_temperature(compound_data, temperature):
       for segment in compound_data.phase_segments:
           if segment.temp_range[0] <= temperature <= segment.temp_range[1]:
               return select_record_in_segment(segment, temperature)
       raise ValueError("Temperature out of range")
   ```

3. **Обработка переходов между записями:**
   ```python
   def handle_record_transition(from_record, to_record, temperature):
       # Проверка непрерывности H(T)
       H_from = calculate_H(from_record, temperature)
       H_to = calculate_H(to_record, temperature)

       if abs(H_from - H_to) > 1e-6:
           # Коррекция для обеспечения непрерывности
           correction = H_from - H_to
           return correction, 0  # ΔH_correction, ΔS_correction

       return 0, 0
   ```

### Пример для FeO

```
Фазовый сегмент s [298-1650K]:
Последовательность записей:
1. Record 1: 298-600K, H298 = -265.053
2. Record 2: 600-900K, H298 = 0.0
3. Record 3: 900-1300K, H298 = 0.0
4. Record 4: 1300-1650K, H298 = 0.0

Логика расчёта:
- T = 298-600K: Используем Record 1 с H298 = -265.053
- T = 600K: Переход к Record 2 с коррекцией ΔH
- T = 600-900K: Используем Record 2 с накопленной коррекцией
- T = 900K: Переход к Record 3 с сохранением непрерывности
- И т.д. до 1650K
```

## Критерии завершения

### Функциональные критерии

1. **Выбор записей:**
   - [ ] Для каждой температуры выбирается корректная запись
   - [ ] Переходы между записями происходят на границах диапазонов
   - [ ] Нет разрывов в расчётах термодинамических свойств

2. **Непрерывность расчётов:**
   - [ ] H(T) непрерывен через границы записей
   - [ ] S(T) непрерывен через границы записей
   - [ ] G(T) непрерывен через границы записей

3. **Производительность:**
   - [ ] Выбор записи занимает <1мс
   - [ ] Расчёт таблицы с множественными записями работает быстро
   - [ ] Кэширование записей работает эффективно

4. **Интеграция:**
   - [ ] `ThermodynamicCalculator` работает с `MultiPhaseCompoundData`
   - [ ] Реакции рассчитываются с учётом множественных записей
   - [ ] Форматирование вывода корректно работает

### Технические критерии

1. **Качество кода:**
   - [ ] Все новые классы имеют полную документацию
   - [ ] Unit тесты покрывают все основные сценарии
   - [ ] Интеграционные тесты проверяют работу всей системы
   - [ ] Покрытие кода тестами ≥ 85%

2. **Надёжность:**
   - [ ] Корректная обработка граничных случаев
   - [ ] Валидация данных перед расчётами
   - [ ] Информативные сообщения об ошибках

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_record_transition_manager.py`

```python
class TestRecordTransitionManager:
    def test_ensure_continuity_same_records(self)
    def test_ensure_continuity_different_records(self)
    def test_calculate_transition_corrections(self)
    def test_validate_record_compatibility(self)
    def test_handle_edge_cases(self)
```

**Файл:** `tests/unit/test_multi_record_calculator.py`

```python
class TestMultiRecordCalculator:
    def test_calculate_properties_multi_record(self)
    def test_calculate_table_multi_record(self)
    def test_select_active_record(self)
    def test_handle_record_transition(self)
```

### Интеграционные тесты

**Файл:** `tests/integration/test_stage_03_record_selection.py`

```python
class TestStage3RecordSelection:
    async def test_feo_multi_record_calculation(self)
    async def test_h2s_multi_record_calculation(self)
    async def test_water_multi_record_calculation(self)
    async def test_reaction_with_multi_records(self)
    async def test_temperature_continuity(self)
    async def test_performance_with_large_datasets(self)
```

### Регрессионные тесты

```python
class TestStage3Regression:
    def test_single_record_compatibility(self)
    def test_backward_compatibility(self)
    def test_edge_temperature_ranges(self)
```

## Риски и митигации

### Риск 1: Разрывы в данных
- **Проблема:** Записи могут иметь неконсистентные значения на границах
- **Митигация:** Автоматическая коррекция, информирование пользователя

### Риск 2: Производительность
- **Проблема:** Множественные расчёты для каждого температурного шага
- **Митигация:** Кэширование, оптимизация алгоритмов

### Риск 3: Сложность отладки
- **Проблема:** Сложно отслеживать переключение между записями
- **Митигация:** Детальное логирование, визуализация переходов

### Риск 4: Обратная совместимость
- **Проблема:** Старый код может не работать с новыми данными
- **Митигация:** Adapter pattern, fallback методы

## Документация

### Обновить:
1. **ThermodynamicCalculator API** — документировать новые методы
2. **Record Selection Guide** — руководство по выбору записей
3. **Performance Notes** — оптимизация производительности

### Создать:
1. **Record Transitions Documentation** — описание алгоритмов переходов
2. **Multi-Record Calculation Examples** — примеры использования

## Временная шкала

- **День 1:** Модификация `ThermodynamicCalculator` для работы с множественными записями
- **День 2:** Создание `RecordTransitionManager` и логики переходов
- **День 3:** Интеграция в реакционные расчёты и тестирование
- **День 4:** Оптимизация производительности, документация, финальные тесты

## Ответственные

- **Разработчик:** Основной разработчик
- **Code Review:** Ведущий архитектор
- **Тестирование:** QA-инженер

## Критерии успеха

1. **FeO пример:** Корректные расчёты через все 4 записи в твёрдой фазе
2. **Непрерывность:** H(T), S(T), G(T) непрерывны через все границы
3. **Производительность:** Расчёт таблицы 50 точек <1 секунда
4. **Тесты:** Все тесты проходят, покрытие ≥ 85%
5. **Интеграция:** Готов к Этапу 4 (фазовые переходы)

---

**Статус:** Готов к реализации после Этапов 1-2
**Следующий этап:** Этап 4: Интеграция фазовых переходов