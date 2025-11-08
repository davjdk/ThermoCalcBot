# Техническое задание: Оптимизация алгоритма выбора записей

## Контекст

При расчёте термодинамических свойств система выбирает набор записей из БД для покрытия заданного температурного диапазона. Текущая реализация может выбирать избыточное количество записей с перекрывающимися или узкими диапазонами.

## Проблема

Анализ сессионных логов показывает систематическое избыточное количество записей для различных соединений:

### Конкретные примеры из сессионных логов:

**1. SiO2(CR) - Классический случай избыточности:**
- **Диапазон запроса:** 298-698K
- **Текущий выбор:** 4 записи
  - `SiO2(CR)`, s, 298.1-480K, H298=-908 кДж/моль, S298=43.06 Дж/(моль·К)
  - `SiO2(CR)`, s, 480-540K, H298=0, S298=0 (continuation)
  - `SiO2(CR)`, s, 540-600K, H298=0, S298=0 (continuation)
  - `SiO2(CR)`, s, 600-3100K, H298=0, S298=0 (continuation)
- **Проблема:** записи 2-4 имеют нулевые базовые значения, что создаёт разрывы на границах

**2. H2O - Многократное пересечение в газовой фазе:**
- **Текущий выбор:** 4 записи (l: 1, g: 3)
  - Жидкость: 298.1-372.8K (涵盖 точку кипения 373.15K)
  - Газ: 298.1-600K, 600-1600K, 1600-6000K (пересекающиеся диапазоны)
- **Оптимум:** 2 записи (жидкость до точки кипения + газ для всего остального диапазона)

**3. CeCl3 - Дублирование жидкой фазы:**
- **Текущий выбор:** 3 записи (s: 1, l: 2)
  - Твёрдая: 298.1-1080K
  - Жидкость: 1080-1300K И 1080-1500K (пересечение 20K)
- **Проблема:** дублирующий диапазон в жидкой фазе

**4. Множественные случаи с 4+ записями:**
- Из логов: `"Использовано записей: 4 (s: 4)"` для различных соединений
- Систематический паттерн избыточности для сложных фазовых диаграмм

### Успешные примеры (уже оптимальны):

**1. NH3 - Идеальное покрытие:**
- **Текущий выбор:** 2 записи (g: 2)
- **Диапазоны:** 298.1-1000K, 1000-6000K
- **Статус:** оптимально, без пересечений

**2. NH4Cl - Покрытие фазового перехода:**
- **Текущий выбор:** 2 записи (s: 2)
- **Диапазоны:** 298.1-457.9K, 457.9-800K
- **Переход:** 793K (плавление) корректно покрыт

## Цель

Оптимизировать выбор записей для покрытия температурного диапазона с учётом трёх факторов:
1. **Минимизация количества записей** (базовая цель)
2. **Максимизация качества данных** (приоритет ReliabilityClass 1)
3. **Покрытие фазовых переходов** (обеспечение точности при переходах)

**Формула оптимальности:**
```
Score = w1 * (1/N_records) + w2 * (Avg_reliability / 3) + w3 * Transition_coverage
где:
  w1 = 0.5 (вес минимизации записей)
  w2 = 0.3 (вес качества данных)
  w3 = 0.2 (вес покрытия переходов)
  N_records = количество выбранных записей
  Avg_reliability = средний класс надёжности (1-3, где 1 — лучший)
  Transition_coverage = доля покрытых фазовых переходов (0-1)
```

## Требования

### Обязательные (Hard Constraints)

1. **Покрытие стартовой температуры:** Первая запись должна покрывать 298K (Tmin ≤ 298K ≤ Tmax)
2. **Полное покрытие диапазона:** Выбранные записи покрывают весь диапазон [target_min, target_max]K без разрывов (gap tolerance ≤ 1K)
3. **Валидность фазовых переходов:** Последовательность фаз должна соответствовать физике: s → l → g (без обратных переходов)
4. **Наличие базовых данных:** Для сложных веществ (is_elemental=False) первая запись каждой фазы должна иметь H298≠0 И S298≠0

### Желательные (Soft Constraints, ранжированные по приоритету)

1. **Приоритет 1 — Минимизация записей:**
   - При равном качестве выбирать набор с меньшим количеством записей
   - Предпочтение записям с широким температурным диапазоном (Tmax - Tmin > 500K)

2. **Приоритет 2 — Качество данных:**
   - Приоритет записям с ReliabilityClass = 1 (74.66% данных в базе)
   - При равном количестве записей выбирать набор с лучшим средним классом надёжности

3. **Приоритет 3 — Покрытие фазовых переходов:**
   - Обеспечить наличие записей, покрывающих tmelt ± 10K и tboil ± 10K
   - Предпочтение записям, которые перекрывают точки переходов (включают переход внутри диапазона)

### Алгоритм

#### Интеграция с существующей трёхуровневой стратегией

Оптимизация встраивается в `RecordRangeBuilder.get_compound_records_for_range()` как **четвёртый этап** после трёхуровневого поиска:

**Текущая логика (сохраняется):**
1. Стратегия 1: Поиск записи для ожидаемой фазы с Tmin ≈ current_T (±tolerance)
2. Стратегия 2: Fallback — любая запись с Tmin ≈ current_T, где >50% диапазона в правильной фазе
3. Стратегия 3: Последний шанс — запись, покрывающая current_T (Tmin < current_T < Tmax)

**Новый этап 4 — Постобработка и оптимизация:**

```python
def optimize_selected_records(
    selected_records: List[pd.Series],
    target_range: Tuple[float, float],
    melting: Optional[float],
    boiling: Optional[float],
    is_elemental: bool
) -> List[pd.Series]:
    """
    Оптимизирует набор записей после трёхуровневого отбора.
    
    Основные операции:
    1. Объединение смежных записей одной фазы
    2. Замена множественных коротких записей на одну длинную
    3. Приоритизация ReliabilityClass=1 при равных условиях
    4. Валидация покрытия фазовых переходов
    
    Args:
        selected_records: Записи после трёхуровневого отбора
        target_range: (T_start, T_end)
        melting/boiling: Температуры переходов
        is_elemental: Флаг простого/сложного вещества
        
    Returns:
        Оптимизированный список записей (N_optimal ≤ N_initial)
    """
    pass
```

#### Детальный алгоритм оптимизации

**Шаг 1: Анализ текущего набора**
```python
# Извлечь метрики набора
N_records = len(selected_records)
phases_used = [r["Phase"] for r in selected_records]
temp_ranges = [(r["Tmin"], r["Tmax"]) for r in selected_records]
reliability_classes = [r["ReliabilityClass"] for r in selected_records]

# Вычислить baseline score
baseline_score = calculate_score(N_records, reliability_classes, target_range, melting, boiling)
```

**Шаг 2: Поиск альтернативных наборов**
```python
# Для каждой группы смежных записей одной фазы
for phase_group in group_by_phase(selected_records):
    # Проверить возможность замены на одну запись
    alternative_records = find_covering_records(
        df=all_available_records,
        phase=phase_group.phase,
        tmin=phase_group.tmin,
        tmax=phase_group.tmax
    )
    
    # Если нашли запись, полностью покрывающую группу
    if alternative_records:
        # Отфильтровать по критериям качества
        valid_alternatives = filter_by_constraints(
            alternative_records,
            is_elemental=is_elemental,
            require_base_data=(phase_group.is_first_in_phase)
        )
        
        # Выбрать лучшую по ReliabilityClass
        best_alternative = min(valid_alternatives, key=lambda r: r["ReliabilityClass"])
        
        # Если замена улучшает score
        new_score = calculate_score_after_replacement(phase_group, best_alternative)
        if new_score > baseline_score:
            replace_group_with_record(phase_group, best_alternative)
            baseline_score = new_score
```

**Шаг 3: Валидация фазовых переходов**
```python
# Проверить покрытие tmelt ± 10K
if melting:
    covering_record = find_record_covering(optimized_records, melting)
    if not covering_record:
        # Добавить запись для покрытия перехода
        transition_record = find_best_record_for_transition(
            all_available_records, melting, tolerance=10
        )
        optimized_records = insert_in_order(optimized_records, transition_record)

# Аналогично для tboil
```

**Шаг 4: Финальная валидация**
```python
# Проверка обязательных требований
assert validate_coverage(optimized_records, target_range)
assert validate_phase_sequence(optimized_records)
assert validate_base_data(optimized_records, is_elemental)

return optimized_records
```

#### Псевдокод:

```python
def select_optimal_records(records, target_range):
    """
    Выбирает минимальный набор записей для покрытия температурного диапазона

    Args:
        records: List[DatabaseRecord] - все доступные записи
        target_range: Tuple[float, float] - (t_min, t_max) требуемый диапазон

    Returns:
        List[DatabaseRecord] - оптимальный набор записей
    """
    target_min, target_max = target_range

    # 1. Фильтрация по пересечению с диапазоном
    candidate_records = [
        r for r in records
        if r.tmin <= target_max and r.tmax >= target_min
    ]

    if not candidate_records:
        return []

    # 2. Сортировка по приоритету: класс надёжности > ширина диапазона
    candidate_records.sort(key=lambda r: (r.reliability_class, -(r.tmax - r.tmin)))

    # 3. Выбор стартовой записи (максимальное покрытие от target_min)
    selected = []
    current_coverage = target_min

    while current_coverage < target_max:
        # Найти запись с максимальным расширением покрытия
        best_record = None
        best_extension = 0

        for record in candidate_records:
            if record.tmin <= current_coverage:
                extension = record.tmax - current_coverage
                if extension > best_extension:
                    best_extension = extension
                    best_record = record

        if not best_record:
            break  # Нет записей для расширения покрытия

        selected.append(best_record)
        current_coverage = best_record.tmax

        # Удалить использованную запись из кандидатов
        candidate_records.remove(best_record)

    # 4. Проверка фазовых переходов
    selected = ensure_phase_transitions(selected, target_range)

    return selected

def ensure_phase_transitions(selected_records, target_range):
    """
    Обеспечивает покрытие фазовых переходов в выбранных записях
    """
    # Проверка температур плавления и кипения
    # Добавление записей при необходимости
    # Объединение пересекающихся записей
    return selected_records
```

#### Пример работы алгоритма для SiO2

**Входные данные:**
- Целевой диапазон: [298, 2500]K
- Доступные записи в базе данных:
  1. `SiO2(CR)`, s, 298.1-480K, H298=-908 кДж/моль, S298=43.06 Дж/(моль·К), ReliabilityClass=1
  2. `SiO2(CR)`, s, 480-540K, H298=0, S298=0, ReliabilityClass=1 (continuation)
  3. `SiO2(CR)`, s, 540-600K, H298=0, S298=0, ReliabilityClass=1 (continuation)
  4. `SiO2(CR)`, s, 600-3100K, H298=0, S298=0, ReliabilityClass=1 (continuation)

**Текущая логика (трёхуровневая стратегия):**
- Выбирает все 4 записи последовательно для полного покрытия
- Результат: N=4 записи

**Новая логика (оптимизация):**

**Шаг 1: Анализ после трёхуровневого отбора**
```python
selected_records = [record_1, record_2, record_3, record_4]
baseline_score = calculate_score(
    N_records=4,
    reliability_classes=[1, 1, 1, 1],
    transition_coverage=0.0  # нет фазовых переходов
)
# baseline_score = 0.5*(1/4) + 0.3*(1/3) + 0.2*0.0 = 0.125 + 0.1 = 0.225
```

**Шаг 2: Поиск альтернатив**
```python
# Все 4 записи имеют фазу 's' и смежные диапазоны
# Ищем одну запись, покрывающую весь диапазон 298-2500K
alternatives = search_db(
    formula="SiO2",
    phase="s",
    tmin_max=298,
    tmax_min=2500
)

# Находим запись 4: SiO2(CR), s, 600-3100K
# НО: она НЕ покрывает 298K (Tmin=600K > 298K)
# Поэтому не можем использовать её как единственную запись

# Проверяем комбинации:
# Вариант А: записи 1 + 4
combined_A = [record_1, record_4]  # 298-480K + 600-3100K
gap = 600 - 480 = 120K  # РАЗРЫВ! Нарушение требования

# Вариант Б: записи 1 + 2 + 4
combined_B = [record_1, record_2, record_4]  # 298-480K + 480-540K + 600-3100K
gap = 600 - 540 = 60K  # РАЗРЫВ! Нарушение требования

# Вариант В: записи 1 + 3 + 4
combined_C = [record_1, record_3, record_4]  # 298-480K + 540-600K + 600-3100K
gap = 540 - 480 = 60K  # РАЗРЫВ! Нарушение требования
```

**Шаг 3: Проверка виртуального объединения**
```python
# Проверяем, можем ли считать записи 1-4 как "виртуально объединённые"
# Условия для виртуального объединения:
# 1. Одна фаза (s) — ✓
# 2. Смежные диапазоны (gap ≤ 1K) — ✗ (есть разрывы между записями)
# 3. Одинаковые коэффициенты Шомейта (f1-f6) — требуется проверка

# ПРОВЕРКА В БАЗЕ ДАННЫХ: сравнение коэффициентов
record_1.coeffs = [f1_1, f2_1, f3_1, f4_1, f5_1, f6_1]
record_2.coeffs = [f1_2, f2_2, f3_2, f4_2, f5_2, f6_2]
# Если f1_1 ≠ f1_2 или f2_1 ≠ f2_2 и т.д. → НЕЛЬЗЯ объединить
# Коэффициенты различаются → записи представляют разные полиномы Шомейта
```

**Итоговое решение для SiO2:**
```python
# Оптимальный набор остаётся 4 записи
# ПРИЧИНА: отсутствие альтернативных записей, полностью покрывающих диапазон
# без разрывов и с корректными коэффициентами

optimized_records = [record_1, record_2, record_3, record_4]
optimized_score = 0.225  # Без изменений

# ВЫВОД: Для SiO2 текущий выбор УЖЕ ОПТИМАЛЕН
# Алгоритм корректно определяет, что замена невозможна
```

**Логирование оптимизации:**
```
[OptimalRecordSelector] Анализ набора для SiO2(CR) в диапазоне 298-2500K
[OptimalRecordSelector] Текущий набор: 4 записи (s: 4)
[OptimalRecordSelector] Поиск альтернативных покрытий для фазы 's' (298-2500K)
[OptimalRecordSelector] Найдено 0 записей, полностью покрывающих диапазон
[OptimalRecordSelector] Проверка виртуального объединения: невозможно (разные коэффициенты Шомейта)
[OptimalRecordSelector] ✓ Оптимизация завершена: 4 записи (без изменений)
[OptimalRecordSelector] Score: 0.225 (baseline: 0.225)
```

#### Обработка фазовых переходов

**Пример для H2O:**

**Входные данные:**
- Целевой диапазон: [298, 2000]K
- Фазовые переходы: Tmelt = 273K, Tboil = 373.15K
- Доступные записи в базе:
  1. H2O, l, 298.1-372.8K, H298=-285.8 кДж/моль, S298=69.95 Дж/(моль·К), ReliabilityClass=1
  2. H2O, g, 298.1-600K, H298=-241.8 кДж/моль, S298=188.8 Дж/(моль·К), ReliabilityClass=1
  3. H2O, g, 600-1600K, H298=0, S298=0, ReliabilityClass=1
  4. H2O, g, 1600-6000K, H298=0, S298=0, ReliabilityClass=1

**Текущая логика (трёхуровневая стратегия):**
- При T=298K выбирает запись 1 (l, 298-372.8K)
- При T=372.8K переключается на фазу g, выбирает запись 2 (g, 298-600K)
- При T=600K выбирает запись 3 (g, 600-1600K)
- При T=1600K выбирает запись 4 (g, 1600-6000K)
- **Результат:** 4 записи (l: 1, g: 3)

**Новая логика (оптимизация):**

**Шаг 1: Анализ фазовых сегментов**
```python
# Определяем сегменты на основе фазовых переходов
segments = [
    PhaseSegment(phase='l', tmin=298, tmax=373.15),   # до кипения
    PhaseSegment(phase='g', tmin=373.15, tmax=2000)   # после кипения
]

# Для каждого сегмента выбираем оптимальные записи
```

**Шаг 2: Оптимизация сегмента жидкости**
```python
# Сегмент l: [298, 373.15]K
liquid_records = [record_1]  # Единственная запись для жидкости
# ОПТИМУМ: 1 запись (изменений нет)
```

**Шаг 3: Оптимизация сегмента газа**
```python
# Сегмент g: [373.15, 2000]K
gas_records = [record_2, record_3, record_4]  # Текущий выбор

# Ищем альтернативы:
# Запись 2 покрывает 298-600K → частично покрывает сегмент [373.15, 600]K
# Запись 3 покрывает 600-1600K
# Запись 4 покрывает 1600-6000K → полностью покрывает остаток до 2000K

# ПРОВЕРКА: можно ли использовать только запись 2?
if record_2.tmax >= 2000:  # 600K < 2000K — НЕТ
    # Нужны дополнительные записи

# ПРОВЕРКА: можно ли объединить записи 3 и 4?
# record_3: 600-1600K, H298=0, S298=0
# record_4: 1600-6000K, H298=0, S298=0
# Обе имеют нулевые базовые значения — можно объединить виртуально
# НО нужно проверить идентичность коэффициентов Шомейта

if coeffs_equal(record_3, record_4):
    # Заменяем записи 3+4 на виртуальную запись 3-4
    virtual_record = VirtualRecord(
        phase='g', tmin=600, tmax=6000,
        coeffs=record_3.coeffs,
        h298=0, s298=0,
        reliability=1,
        source_records=[record_3, record_4]
    )
    gas_records_optimized = [record_2, virtual_record]
else:
    # Коэффициенты различаются — нельзя объединить
    gas_records_optimized = [record_2, record_3, record_4]
```

**Шаг 4: Финальная валидация покрытия перехода**
```python
# Проверяем покрытие tboil = 373.15K
# Требование: запись должна покрывать 373.15 ± 10K = [363.15, 383.15]K

# record_1 (l): 298-372.8K → НЕ покрывает 373.15K (372.8 < 373.15)
# record_2 (g): 298-600K → покрывает 373.15K ✓

# ПРОБЛЕМА: разрыв между фазами при 373.15K
# record_1.tmax = 372.8K
# record_2.tmin = 298K (но мы используем с 373.15K)

# РЕШЕНИЕ: использовать обе записи с перекрытием
optimized_records = [
    record_1,  # l, 298-372.8K (покрывает жидкую фазу до точки кипения)
    record_2   # g, 373.15-600K (начинаем использовать с точки кипения)
]

# Для диапазона 600-2000K используем записи 3+4 или виртуальную
if virtual_record:
    optimized_records.append(virtual_record)
else:
    optimized_records.extend([record_3, record_4])
```

**Итоговое решение для H2O:**
```python
# Вариант А (если коэффициенты записей 3 и 4 идентичны):
optimized_records = [record_1, record_2, virtual_record_3_4]
# РЕЗУЛЬТАТ: 3 записи (было 4) — оптимизация на 25%

# Вариант Б (если коэффициенты различаются):
optimized_records = [record_1, record_2, record_3, record_4]
# РЕЗУЛЬТАТ: 4 записи (без изменений) — текущий выбор оптимален
```

**Логирование:**
```
[OptimalRecordSelector] Анализ набора для H2O в диапазоне 298-2000K
[OptimalRecordSelector] Фазовые переходы: tmelt=273K, tboil=373.15K
[OptimalRecordSelector] Сегмент 1 (l): [298, 373.15]K — 1 запись (оптимум)
[OptimalRecordSelector] Сегмент 2 (g): [373.15, 2000]K — 3 записи
[OptimalRecordSelector] Проверка виртуального объединения записей 3+4 (g, 600-6000K)
[OptimalRecordSelector] Коэффициенты Шомейта: идентичны ✓
[OptimalRecordSelector] Создана виртуальная запись: g, 600-6000K
[OptimalRecordSelector] ✓ Оптимизация завершена: 3 записи (было 4, экономия 25%)
[OptimalRecordSelector] Score: 0.283 (baseline: 0.225, улучшение +26%)
```

### Ограничения

1. **Сохранение трёхуровневой стратегии:** Оптимизация НЕ заменяет текущую логику, а дополняет её постобработкой
2. **Запрет на нарушение физики фазовых переходов:** Последовательность фаз s → l → g должна соблюдаться
3. **Требование базовых данных для сложных веществ:** Для is_elemental=False первая запись каждой фазы должна иметь H298≠0 И S298≠0
4. **Максимальный допуск разрывов:** Gap между смежными записями ≤ 1K
5. **Производительность:** Время оптимизации не должно превышать 20% от времени трёхуровневого отбора (целевое значение: <50ms на вещество)
6. **Обратная совместимость:** Флаг `use_optimal_selection=False` должен давать идентичные результаты текущей реализации
7. **Валидация коэффициентов Шомейта:** Виртуальное объединение записей возможно только при идентичности коэффициентов f1-f6 (точность сравнения: ±1e-6)

## Критерии приёмки

### Количественные метрики

**Оптимизация количества записей (с учётом реалистичности):**
- [ ] H2O: 3 записи вместо 4 для диапазона 298-2000K (при идентичности коэффициентов Шомейта в записях 3-4)
- [ ] CeCl3: 2 записи вместо 3 для диапазона 298-1500K (устранение дублирования жидкой фазы)
- [ ] NH3: 2 записи (валидация — набор уже оптимален, изменений не требуется)
- [ ] SiO2: 4 записи (валидация — набор оптимален при наличии разных коэффициентов, изменений не требуется)
- [ ] Среднее сокращение количества записей: ≥15% для тестового набора из 20 соединений
- [ ] Максимальное сокращение: до 40% для случаев с избыточным дублированием

**Производительность:**
- [ ] Время оптимизации: <50ms на одно вещество (среднее по 100 запусков)
- [ ] Overhead относительно трёхуровневого отбора: <20%
- [ ] Общее время расчётов (включая термодинамику): не увеличивается более чем на 5%
- [ ] Дополнительное использование памяти: <10MB для кэша виртуальных записей

**Точность расчётов:**
- [ ] Термодинамические свойства (Cp, H, S, G): совпадают с точностью ±0.01% (улучшено с ±0.1%)
- [ ] Константы равновесия реакций: совпадают с точностью ±0.05%
- [ ] Температуры фазовых переходов: абсолютное совпадение (0K разница)
- [ ] Энтальпии переходов (ΔH_fusion, ΔH_vap): совпадают с точностью ±0.1 кДж/моль

### Качественные критерии

**Функциональность:**
- [ ] Полное покрытие температурных диапазонов без разрывов (gap ≤ 1K)
- [ ] Корректное покрытие фазовых переходов (±10K tolerance)
- [ ] Приоритизация по ReliabilityClass (1 > 2 > 3)
- [ ] Корректная обработка виртуального объединения записей при идентичности коэффициентов Шомейта
- [ ] Обработка граничных случаев:
  - Пустые результаты после трёхуровневого отбора
  - Единственная запись (возврат без изменений)
  - Все записи имеют одинаковый ReliabilityClass
  - Отсутствие фазовых переходов
  - Записи с H298=0, S298=0 для сложных веществ

**Тестирование:**
- [ ] Все существующие интеграционные тесты проходят без регрессий
- [ ] Добавлен комплекс unit-тестов для OptimalRecordSelector:
  - `test_optimize_h2o_records()` — оптимизация газовой фазы
  - `test_optimize_cecl3_records()` — устранение дублирования
  - `test_validate_sio2_optimal()` — валидация оптимальности
  - `test_validate_nh3_optimal()` — валидация оптимальности
  - `test_virtual_record_merging()` — объединение записей
  - `test_phase_transition_coverage()` — покрытие переходов
  - `test_reliability_prioritization()` — приоритизация по классу
- [ ] Добавлены интеграционные тесты для реальных данных:
  - `test_full_pipeline_with_optimization()` — полный цикл с оптимизацией
  - `test_multi_compound_reaction_optimization()` — реакции с 5+ веществами
  - `test_optimization_performance_benchmark()` — производительность
- [ ] Регрессионные тесты для точности расчётов:
  - `test_thermodynamic_properties_accuracy()` — Cp, H, S, G
  - `test_reaction_equilibrium_accuracy()` — константы равновесия
  - `test_phase_transition_enthalpy_accuracy()` — энтальпии переходов

**Обратная совместимость:**
- [ ] Флаг `use_optimal_selection=False` даёт идентичные результаты текущей реализации (100% совпадение)
- [ ] Сохранение текущего API RecordRangeBuilder без breaking changes
- [ ] Возможность постепенного включения оптимизации через конфигурацию
- [ ] Логирование решений оптимизации для отладки и аудита

## Детальные тестовые сценарии

### Сценарий 1: SiO2 (кристаллический) - Валидация оптимальности

**Входные данные:**
- Соединение: SiO2(CR)
- Температурный диапазон: [298, 2500]K
- Текущие записи: 4 (298.1-480K, 480-540K, 540-600K, 600-3100K)

**Ожидаемый результат:**
- Оптимальные записи: 4 (БЕЗ ИЗМЕНЕНИЙ — текущий набор уже оптимален)
- Причина: отсутствие записей, полностью покрывающих диапазон, и различающиеся коэффициенты Шомейта
- Покрытие: полное, без разрывов
- Точность расчетов: ±0.01% относительно текущей реализации

**Валидация:**
```python
def test_sio2_optimization_validation():
    """Проверка, что алгоритм корректно определяет оптимальность текущего набора."""
    
    # Текущее поведение
    current_records = get_current_records("SiO2(CR)", (298, 2500))
    assert len(current_records) == 4
    
    # Оптимизация
    optimized_records = optimize_records(current_records, (298, 2500))
    
    # Ожидаем отсутствие изменений
    assert len(optimized_records) == 4
    assert all(r1.id == r2.id for r1, r2 in zip(current_records, optimized_records))
    
    # Проверка логирования обоснования
    assert "текущий набор оптимален" in optimization_log
    assert "различающиеся коэффициенты Шомейта" in optimization_log
    
    # Проверка точности
    current_props = calculate_properties(current_records, [298, 1000, 2000, 2500])
    optimized_props = calculate_properties(optimized_records, [298, 1000, 2000, 2500])
    
    for temp in [298, 1000, 2000, 2500]:
        # Улучшенная точность: ±0.01%
        assert relative_error(current_props[temp].Cp, optimized_props[temp].Cp) < 0.0001
        assert relative_error(current_props[temp].H, optimized_props[temp].H) < 0.0001
        assert relative_error(current_props[temp].S, optimized_props[temp].S) < 0.0001
        assert relative_error(current_props[temp].G, optimized_props[temp].G) < 0.0001
```

### Сценарий 2: H2O - Многофазный тест с виртуальным объединением

**Входные данные:**
- Соединение: H2O
- Температурный диапазон: [298, 2000]K
- Фазовые переходы: Tmelt = 273K, Tboil = 373.15K
- Текущие записи: 4 (жидкость: 1, газ: 3)
  1. H2O, l, 298.1-372.8K, H298=-285.8, S298=69.95, RC=1
  2. H2O, g, 298.1-600K, H298=-241.8, S298=188.8, RC=1
  3. H2O, g, 600-1600K, H298=0, S298=0, RC=1
  4. H2O, g, 1600-6000K, H298=0, S298=0, RC=1

**Ожидаемый результат:**
- Оптимальные записи: 3 (жидкость: 1, газ: 2 физические + 1 виртуальная)
  - Запись 1: l, 298-372.8K (без изменений)
  - Запись 2: g, 298-600K (без изменений)
  - Виртуальная запись 3-4: g, 600-6000K (объединение при идентичности коэффициентов)
- Условие оптимизации: коэффициенты Шомейта записей 3 и 4 идентичны (проверка с точностью ±1e-6)
- Покрытие фазового перехода: tboil=373.15K покрывается записями 1 и 2 с перекрытием

**Валидация:**
```python
def test_h2o_phase_transition_with_virtual_merging():
    """Проверка многофазной оптимизации с виртуальным объединением."""
    
    current_records = get_current_records("H2O", (298, 2000))
    assert len(current_records) == 4
    
    # Проверка условий для виртуального объединения
    record_3 = current_records[2]  # g, 600-1600K
    record_4 = current_records[3]  # g, 1600-6000K
    
    assert record_3.h298 == 0 and record_3.s298 == 0
    assert record_4.h298 == 0 and record_4.s298 == 0
    
    coeffs_identical = all(
        abs(record_3.coeffs[i] - record_4.coeffs[i]) < 1e-6
        for i in range(6)  # f1-f6
    )
    
    # Оптимизация
    optimized_records = optimize_records(current_records, (298, 2000))
    
    if coeffs_identical:
        # Ожидаем виртуальное объединение
        assert len(optimized_records) == 3
        
        # Проверка виртуальной записи
        virtual_record = optimized_records[2]
        assert virtual_record.is_virtual == True
        assert virtual_record.phase == 'g'
        assert virtual_record.tmin == 600
        assert virtual_record.tmax == 6000
        assert len(virtual_record.source_records) == 2
    else:
        # Коэффициенты различаются — объединение невозможно
        assert len(optimized_records) == 4
    
    # Проверка покрытия фазового перехода
    liquid_record = find_phase_record(optimized_records, 'l')
    gas_record = find_phase_record(optimized_records, 'g')
    
    assert liquid_record.tmax >= 372.8  # Покрытие до точки кипения
    assert gas_record.tmin <= 373.15    # Начало газовой фазы
    
    # Проверка точности при фазовом переходе
    T_transition = 373.15
    liquid_props = calculate_at_temperature(liquid_record, T_transition - 0.01)
    gas_props = calculate_at_temperature(gas_record, T_transition + 0.01)
    
    # Разрыв энтропии при испарении должен сохраниться
    assert gas_props.S > liquid_props.S
    delta_S_vap = gas_props.S - liquid_props.S
    assert 105 < delta_S_vap < 115  # Ожидаемая энтропия испарения ~109 Дж/(моль·К)
    
    # Проверка улучшения score при виртуальном объединении
    if coeffs_identical:
        score_current = calculate_score(current_records)
        score_optimized = calculate_score(optimized_records)
        assert score_optimized > score_current
        improvement = (score_optimized - score_current) / score_current
        assert improvement >= 0.20  # Минимум 20% улучшение
```

### Сценарий 3: CeCl3 - Устранение дублирования жидкой фазы

**Входные данные:**
- Соединение: CeCl3
- Температурный диапазон: [298, 1500]K
- Текущие записи: 3 (твёрдая: 1, жидкость: 2 с пересечением)
  1. CeCl3, s, 298.1-1080K, H298=-1060 кДж/моль, S298=151 Дж/(моль·К), RC=1
  2. CeCl3, l, 1080-1300K, H298=-1020 кДж/моль, S298=189 Дж/(моль·К), RC=1
  3. CeCl3, l, 1080-1500K, H298=-1020 кДж/моль, S298=189 Дж/(моль·К), RC=1

**Ожидаемый результат:**
- Оптимальные записи: 2 (твёрдая: 1, жидкость: 1)
  - Запись 1: s, 298-1080K (без изменений)
  - Запись 3: l, 1080-1500K (выбрана как покрывающая весь целевой диапазон жидкой фазы)
  - Запись 2 удалена (дублирование диапазона 1080-1300K)
- Критерий выбора: запись 3 имеет более широкий диапазон (1080-1500K vs 1080-1300K)

**Валидация:**
```python
def test_cecl3_duplicate_elimination():
    """Проверка устранения дублирования жидкой фазы."""
    
    current_records = get_current_records("CeCl3", (298, 1500))
    assert len(current_records) == 3
    
    # Проверка наличия дублирования
    liquid_records = [r for r in current_records if r.phase == 'l']
    assert len(liquid_records) == 2
    
    # Проверка пересечения диапазонов
    overlap_start = max(liquid_records[0].tmin, liquid_records[1].tmin)
    overlap_end = min(liquid_records[0].tmax, liquid_records[1].tmax)
    overlap_duration = overlap_end - overlap_start
    assert overlap_duration == 220  # 1300 - 1080 = 220K
    
    # Оптимизация
    optimized_records = optimize_records(current_records, (298, 1500))
    
    # Ожидаем устранение дублирования
    assert len(optimized_records) == 2
    
    # Проверка структуры
    solid_records = [r for r in optimized_records if r.phase == 's']
    liquid_records_opt = [r for r in optimized_records if r.phase == 'l']
    
    assert len(solid_records) == 1
    assert len(liquid_records_opt) == 1
    
    # Проверка выбора записи с более широким диапазоном
    selected_liquid = liquid_records_opt[0]
    assert selected_liquid.tmin == 1080
    assert selected_liquid.tmax == 1500
    
    # Проверка покрытия фазового перехода
    tmelt = 1080  # Температура плавления
    assert solid_records[0].tmax == tmelt
    assert liquid_records_opt[0].tmin == tmelt
    
    # Проверка улучшения score
    score_current = calculate_score(current_records)
    score_optimized = calculate_score(optimized_records)
    assert score_optimized > score_current
    
    # Проверка сокращения записей
    reduction = (len(current_records) - len(optimized_records)) / len(current_records)
    assert reduction == 0.333  # 33% сокращение (3 → 2)
```

### Сценарий 4: NH3 - Валидация уже оптимального выбора

**Входные данные:**
- Соединение: NH3
- Температурный диапазон: [298, 3000]K
- Текущие записи: 2 (газ: 2, уже оптимально)
  1. NH3, g, 298.1-1000K, H298=-45.9 кДж/моль, S298=192.8 Дж/(моль·К), RC=1
  2. NH3, g, 1000-6000K, H298=0, S298=0, RC=1

**Ожидаемый результат:**
- Оптимальные записи: 2 (БЕЗ ИЗМЕНЕНИЙ — текущий набор уже оптимален)
- Подтверждение, что алгоритм не ухудшает уже оптимальные случаи
- Score остаётся неизменным

**Валидация:**
```python
def test_nh3_already_optimal():
    """Проверка, что алгоритм не модифицирует уже оптимальные наборы."""
    
    current_records = get_current_records("NH3", (298, 3000))
    assert len(current_records) == 2
    
    # Проверка отсутствия пересечений
    assert current_records[0].tmax == current_records[1].tmin  # Смежные диапазоны
    
    # Проверка фазовой однородности
    assert all(r.phase == 'g' for r in current_records)
    
    # Проверка наличия базовых данных в первой записи
    assert current_records[0].h298 != 0
    assert current_records[0].s298 != 0
    
    # Оптимизация
    optimized_records = optimize_records(current_records, (298, 3000))
    
    # Ожидаем отсутствие изменений
    assert len(optimized_records) == 2
    assert all(r1.id == r2.id for r1, r2 in zip(current_records, optimized_records))
    
    # Проверка score
    score_current = calculate_score(current_records)
    score_optimized = calculate_score(optimized_records)
    assert abs(score_current - score_optimized) < 1e-9  # Идентичные score
    
    # Проверка логирования
    assert "текущий набор оптимален" in optimization_log
    assert "изменений не требуется" in optimization_log
```

### Сценарий 5: Реакция Fe2O3 + 3C = 2Fe + 3CO - Интеграционный тест

**Входные данные:**
- Реакция: Fe2O3 + 3C → 2Fe + 3CO
- Температурный диапазон: [298, 1500]K
- Текущие записи:
  - Fe2O3: 3 записи (s: 3)
  - C (графит): 2 записи (s: 2)
  - Fe: 3 записи (s: 2, l: 1)
  - CO: 2 записи (g: 2)
  - **Итого:** 10 записей

**Ожидаемый результат:**
- Оптимизированные записи: 7-9 записей (зависит от структуры данных)
  - Fe2O3: 2-3 записи (возможно виртуальное объединение)
  - C: 2 записи (оптимум)
  - Fe: 2-3 записи (покрытие плавления при ~1811K)
  - CO: 2 записи (оптимум)
- Точность расчётов ΔH, ΔS, ΔG: ±0.05%
- Сохранение температуры инверсии реакции (если есть)

**Валидация:**
```python
def test_fe2o3_reaction_optimization():
    """Интеграционный тест оптимизации многокомпонентной реакции."""
    
    reaction = "Fe2O3 + 3C → 2Fe + 3CO"
    temp_range = (298, 1500)
    
    # Текущие результаты (без оптимизации)
    current_data = calculate_reaction(reaction, temp_range, use_optimization=False)
    
    # Оптимизированные результаты
    optimized_data = calculate_reaction(reaction, temp_range, use_optimization=True)
    
    # Проверка сокращения записей
    assert current_data.total_records >= optimized_data.total_records
    
    reduction = (current_data.total_records - optimized_data.total_records) / current_data.total_records
    assert 0.10 <= reduction <= 0.40  # Сокращение от 10% до 40%
    
    # Проверка точности термодинамики
    test_temperatures = [298, 500, 800, 1000, 1200, 1500]
    
    for temp in test_temperatures:
        current_props = current_data.get_properties(temp)
        optimized_props = optimized_data.get_properties(temp)
        
        # Улучшенная точность: ±0.05%
        assert relative_error(current_props.dH, optimized_props.dH) < 0.0005
        assert relative_error(current_props.dS, optimized_props.dS) < 0.0005
        assert relative_error(current_props.dG, optimized_props.dG) < 0.0005
        
        # Константа равновесия
        if optimized_props.K > 0:
            assert relative_error(current_props.K, optimized_props.K) < 0.0005
    
    # Проверка фазовых переходов Fe (плавление ~1811K)
    if 1811 in range(temp_range[0], temp_range[1]):
        fe_records_current = current_data.get_compound_records("Fe")
        fe_records_optimized = optimized_data.get_compound_records("Fe")
        
        # Должны покрывать переход
        assert any(r.phase == 's' and r.tmax >= 1811 for r in fe_records_optimized)
        assert any(r.phase == 'l' and r.tmin <= 1811 for r in fe_records_optimized)
    
    # Проверка производительности
    assert optimized_data.calculation_time <= current_data.calculation_time * 1.05
```

### Сценарий 6: Производительность

**Измерения:**
- Время оптимизации для 20 соединений (по 100 запусков каждое)
- Время полного расчёта реакции с 5+ соединениями
- Использование памяти при кэшировании виртуальных записей
- Overhead относительно текущей реализации

**Критерии:**
- Оптимизация одного вещества: <50ms (среднее)
- Полный расчёт реакции (5 веществ): <3 секунды
- Память: дополнительный overhead <10MB
- Overhead: <20% относительно времени трёхуровневого отбора

**Валидация:**
```python
def test_optimization_performance():
    """Бенчмарк производительности оптимизации."""
    
    test_compounds = [
        "H2O", "CO2", "NH3", "CH4", "O2", "N2", "H2", "HCl",
        "SiO2", "Fe2O3", "CaCO3", "Al2O3", "CuO", "ZnO", "MgO",
        "NaCl", "KCl", "CeCl3", "WO3", "TiO2"
    ]
    
    temp_range = (298, 2000)
    n_runs = 100
    
    # Измерение времени оптимизации для каждого соединения
    optimization_times = []
    
    for compound in test_compounds:
        records = get_current_records(compound, temp_range)
        
        times = []
        for _ in range(n_runs):
            start = time.perf_counter()
            optimized = optimize_records(records, temp_range)
            end = time.perf_counter()
            times.append((end - start) * 1000)  # в миллисекундах
        
        avg_time = sum(times) / len(times)
        optimization_times.append(avg_time)
        
        # Проверка для каждого соединения
        assert avg_time < 50, f"{compound}: {avg_time:.2f}ms > 50ms"
    
    # Общая статистика
    overall_avg = sum(optimization_times) / len(optimization_times)
    assert overall_avg < 30, f"Среднее время {overall_avg:.2f}ms > 30ms"
    
    # Измерение overhead
    for compound in test_compounds:
        records = get_current_records(compound, temp_range)
        
        # Время трёхуровневого отбора
        start = time.perf_counter()
        three_level_records = three_level_selection(compound, temp_range)
        three_level_time = time.perf_counter() - start
        
        # Время с оптимизацией
        start = time.perf_counter()
        optimized_records = optimize_records(three_level_records, temp_range)
        optimization_time = time.perf_counter() - start
        
        # Проверка overhead
        overhead = optimization_time / three_level_time
        assert overhead < 0.20, f"{compound}: overhead {overhead*100:.1f}% > 20%"
    
    # Измерение памяти
    import tracemalloc
    tracemalloc.start()
    
    # Создание 100 виртуальных записей
    virtual_records = []
    for i in range(100):
        vr = create_virtual_record([records[0], records[1]])
        virtual_records.append(vr)
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    memory_mb = peak / (1024 * 1024)
    assert memory_mb < 10, f"Использование памяти {memory_mb:.2f}MB > 10MB"
```

### Сценарий 7: Граничные случаи

**Тестовые случаи:**

1. **Пустые результаты после трёхуровневого отбора:** `selected_records = []` → возврат `[]`
2. **Единственная запись:** `[single_record]` → возврат без изменений
3. **Записи с H298=0, S298=0 для сложных веществ:** работает с warning в логах
4. **Отсутствие фазовых переходов:** `melting=None, boiling=None` → оптимизация без учёта переходов
5. **Разные ReliabilityClass:** приоритет RC=1 > RC=2 > RC=3
6. **Одинаковый ReliabilityClass:** выбор по максимальному покрытию (Tmax - Tmin)
7. **Различающиеся коэффициенты Шомейта:** виртуальное объединение НЕ выполняется
8. **Фазовый переход на границе записи:** обе записи сохраняются

**Код валидации:** см. `tests/unit/test_optimal_record_selector_edge_cases.py`

## План реализации

### Этап 1: Разработка OptimalRecordSelector (5 дней)

**День 1-2: Создание основного класса и моделей**
- **Файл:** `src/thermo_agents/core_logic/optimal_record_selector.py`
- **Компоненты:**
  - `OptimalRecordSelector` класс с методами:
    - `optimize_selected_records()` — основной метод постобработки после трёхуровневого отбора
    - `calculate_optimization_score()` — расчёт формулы оптимальности
    - `find_alternative_records()` — поиск альтернативных наборов записей
    - `can_merge_virtually()` — проверка возможности виртуального объединения
    - `create_virtual_record()` — создание виртуальной записи из нескольких физических
    - `validate_coverage()` — валидация полного покрытия диапазона
    - `validate_phase_transitions()` — валидация покрытия фазовых переходов
  - `VirtualRecord` класс (наследует DatabaseRecord):
    - `is_virtual: bool = True`
    - `source_records: List[DatabaseRecord]` — исходные записи для объединения
    - `merged_tmin, merged_tmax` — объединённый температурный диапазон
  - `OptimizationConfig` — конфигурация параметров:
    - `w1, w2, w3` — веса формулы оптимальности (0.5, 0.3, 0.2)
    - `gap_tolerance_k: float = 1.0` — максимальный допустимый разрыв
    - `transition_tolerance_k: float = 10.0` — tolerance для покрытия переходов
    - `coeffs_comparison_tolerance: float = 1e-6` — точность сравнения коэффициентов

**День 3: Реализация алгоритма оптимизации**
- Имплементация жадного алгоритма поиска альтернатив
- Реализация логики виртуального объединения
- Имплементация расчёта score и сравнения вариантов

**День 4: Интеграция с существующими моделями**
- Адаптация под `DatabaseRecord` и `pd.Series`
- Поддержка `ReliabilityClass` (1-3)
- Интеграция с `PhaseTransitionDetector`

**День 5: Базовое unit-тестирование**
- Тесты для `can_merge_virtually()` и `create_virtual_record()`
- Тесты для `calculate_optimization_score()`
- Тесты граничных случаев (пустые наборы, единственная запись)

### Этап 2: Интеграция с RecordRangeBuilder (3 дня)

**День 6-7: Модификация RecordRangeBuilder**
- **Файл:** `src/thermo_agents/core_logic/record_range_builder.py`
- **Изменения:**
  - Добавление метода `get_optimal_compound_records_for_range()`:
    ```python
    def get_optimal_compound_records_for_range(
        self,
        df: pd.DataFrame,
        t_range: List[float],
        melting: Optional[float],
        boiling: Optional[float],
        tolerance: float = 1.0,
        is_elemental: Optional[bool] = None,
        use_optimization: bool = False
    ) -> List[pd.Series]:
        """
        Возвращает оптимизированный набор записей для покрытия диапазона.
        
        Логика:
        1. Вызов существующего get_compound_records_for_range() (трёхуровневая стратегия)
        2. Если use_optimization=True, передача результата в OptimalRecordSelector
        3. Возврат оптимизированного набора
        
        Args:
            use_optimization: Флаг включения оптимизации (по умолчанию False)
        """
        # Шаг 1: Трёхуровневая стратегия (текущая логика)
        selected_records = self.get_compound_records_for_range(
            df, t_range, melting, boiling, tolerance, is_elemental
        )
        
        # Шаг 2: Оптимизация (опционально)
        if use_optimization and self.optimizer:
            optimized_records = self.optimizer.optimize_selected_records(
                selected_records=selected_records,
                target_range=tuple(t_range),
                all_available_records=df,
                melting=melting,
                boiling=boiling,
                is_elemental=is_elemental
            )
            return optimized_records
        
        return selected_records
    ```
  - Добавление поля `self.optimizer: Optional[OptimalRecordSelector]` в конструктор
  - Сохранение обратной совместимости через флаг `use_optimization=False`

**День 8: Обратная совместимость и тестирование**
- Проверка идентичности результатов при `use_optimization=False`
- Валидация производительности (overhead <20%)
- Тестирование на существующих интеграционных тестах

### Этап 3: Обновление CompoundDataLoader и PhaseSegmentBuilder (2 дня)

**День 9: Интеграция с CompoundDataLoader**
- **Файл:** `src/thermo_agents/core_logic/compound_data_loader.py`
- **Модификации:**
  - Передача флага `use_optimization` в RecordRangeBuilder
  - Обновление методов загрузки данных для поддержки виртуальных записей
  - Логирование решений оптимизации через SessionLogger

**День 10: Адаптация PhaseSegmentBuilder**
- **Файл:** `src/thermo_agents/filtering/phase_segment_builder.py`
- **Модификации:**
  - Поддержка VirtualRecord в методах построения сегментов
  - Корректная обработка виртуальных записей при расчёте фазовых сегментов
  - Валидация непрерывности с учётом виртуальных объединений

### Этап 4: Комплексное тестирование (5 дней)

**День 11-12: Unit тесты**
- **Файл:** `tests/unit/test_optimal_record_selector.py`
- **Тестовые сценарии:**
  - `test_sio2_validation_optimal()` — проверка определения оптимальности текущего набора
  - `test_h2o_virtual_merging()` — виртуальное объединение газовых записей
  - `test_cecl3_duplicate_elimination()` — устранение дублирования жидкой фазы
  - `test_nh3_already_optimal()` — валидация неизменности оптимальных наборов
  - `test_can_merge_virtually()` — проверка условий виртуального объединения
  - `test_calculate_score()` — корректность формулы оптимальности
  - `test_reliability_prioritization()` — приоритизация по ReliabilityClass
  
- **Файл:** `tests/unit/test_optimal_record_selector_edge_cases.py`
  - `test_empty_records()` — пустой набор записей
  - `test_single_record()` — единственная запись
  - `test_zero_base_data_complex()` — H298=0, S298=0 для сложного вещества
  - `test_no_phase_transitions()` — отсутствие фазовых переходов
  - `test_different_reliability_classes()` — разные классы надёжности
  - `test_identical_reliability_classes()` — одинаковые классы
  - `test_different_coefficients()` — различающиеся коэффициенты Шомейта
  - `test_phase_transition_on_boundary()` — фазовый переход на границе

**День 13-14: Интеграционные тесты**
- **Файл:** `tests/integration/test_optimal_selection_integration.py`
- **Сценарии:**
  - `test_full_pipeline_with_optimization()` — полный цикл с включённой оптимизацией
  - `test_fe2o3_reaction_optimization()` — многокомпонентная реакция
  - `test_multi_phase_optimization()` — многофазные расчёты с переходами
  - `test_backward_compatibility()` — идентичность результатов при `use_optimization=False`

- **Файл:** `tests/integration/test_optimization_performance.py`
  - `test_optimization_time_per_compound()` — время оптимизации <50ms
  - `test_overhead_vs_three_level()` — overhead <20%
  - `test_memory_usage()` — дополнительная память <10MB
  - `test_full_reaction_calculation_time()` — полный расчёт реакции

**День 15: Регрессионные тесты**
- **Файл:** `tests/integration/test_accuracy_regression.py`
- **Проверки:**
  - `test_thermodynamic_properties_accuracy()` — Cp, H, S, G (±0.01%)
  - `test_reaction_equilibrium_accuracy()` — константы равновесия K (±0.05%)
  - `test_phase_transition_enthalpy()` — энтальпии переходов (±0.1 кДж/моль)
  - `test_temperature_inversion_preservation()` — сохранение точек инверсии реакций

### Этап 5: Валидация, документация и развёртывание (3 дня)

**День 16: Валидация точности на реальных данных**
- Запуск оптимизации на 100+ соединениях из базы данных
- Сравнение результатов расчётов с текущей реализацией (точность ±0.01%)
- Анализ случаев, где оптимизация не сокращает количество записей
- Проверка сохранения точности в константах равновесия реакций

**День 17: Оптимизация производительности**
- Профилирование алгоритма оптимизации (`cProfile`, `line_profiler`)
- Оптимизация узких мест (кэширование, векторизация)
- Проверка соблюдения ограничения overhead <20%
- Тестирование на больших наборах данных (реакции с 10+ веществами)

**День 18: Документация и подготовка к развёртыванию**
- Обновление `docs/ARCHITECTURE.md`:
  - Добавление раздела "Оптимизация выбора записей"
  - Описание VirtualRecord и OptimalRecordSelector
  - Диаграммы потоков выполнения с оптимизацией
- Создание `docs/optimal_selection_guide.md`:
  - Руководство по включению оптимизации
  - Примеры использования
  - Интерпретация логов оптимизации
- Обновление docstrings в изменённых модулях
- Создание PR в основную ветку с детальным описанием изменений

## Итоговая структура файлов

### Новые файлы (3):
```
src/thermo_agents/core_logic/
  └── optimal_record_selector.py    # OptimalRecordSelector, VirtualRecord, OptimizationConfig

tests/unit/
  └── test_optimal_record_selector.py          # Unit тесты оптимизатора
  └── test_optimal_record_selector_edge_cases.py  # Граничные случаи

tests/integration/
  └── test_optimal_selection_integration.py    # Интеграционные тесты
  └── test_optimization_performance.py         # Тесты производительности
  └── test_accuracy_regression.py              # Регрессионные тесты

docs/
  └── optimal_selection_guide.md               # Руководство по оптимизации
```

### Модифицируемые файлы (4):
```
src/thermo_agents/core_logic/
  └── record_range_builder.py          # Добавление get_optimal_compound_records_for_range()
  └── compound_data_loader.py          # Поддержка use_optimization флага

src/thermo_agents/filtering/
  └── phase_segment_builder.py         # Поддержка VirtualRecord

docs/
  └── ARCHITECTURE.md                   # Обновление с разделом оптимизации
```

### Всего: 7 новых файлов, 4 модификации

## Оценка трудозатрат

**Общая продолжительность:** 18 рабочих дней (3.6 недели)

**Распределение по этапам:**
- Этап 1 (Разработка OptimalRecordSelector): 5 дней (28%)
- Этап 2 (Интеграция с RecordRangeBuilder): 3 дня (17%)
- Этап 3 (Обновление компонентов): 2 дня (11%)
- Этап 4 (Комплексное тестирование): 5 дней (28%)
- Этап 5 (Валидация и документация): 3 дня (17%)

**Критический путь:** Этапы 1 → 2 → 3 → 4 → 5 (последовательное выполнение)

**Риски и резервы:**
- +2 дня на непредвиденные сложности при интеграции
- +1 день на исправление регрессий в тестах
- **Итого с резервами:** 21 день (4.2 недели)

## Файлы для изменения

### Новые файлы:
- `src/thermo_agents/selection/__init__.py`
- `src/thermo_agents/selection/optimal_record_selector.py`
- `src/thermo_agents/selection/selection_config.py`
- `tests/unit/test_optimal_record_selector.py`
- `tests/integration/test_optimal_selection_integration.py`

### Модифицируемые файлы:
- `src/thermo_agents/core_logic/record_range_builder.py`
- `src/thermo_agents/filtering/phase_segment_builder.py`
- `src/thermo_agents/search/compound_searcher.py`
- `tests/unit/test_record_selector.py`
- `docs/ARCHITECTURE.md`

## Риски и митигация

### Высокий приоритет

**1. Потеря точности расчётов**
- **Риск:** Виртуальное объединение записей или замена наборов может привести к отклонениям в термодинамических свойствах
- **Митигация:**
  - Жёсткая валидация: отклонение ±0.01% для Cp, H, S, G
  - Регрессионные тесты для всех существующих расчётов
  - Сравнение результатов на 100+ реальных соединениях из базы
  - Проверка идентичности коэффициентов Шомейта с точностью ±1e-6 перед объединением
- **Индикаторы:** Провал регрессионных тестов, отклонения >0.01%
- **План восстановления:** Откат к трёхуровневой стратегии через `use_optimization=False`

**2. Нарушение фазовых переходов**
- **Риск:** Оптимизация может некорректно обработать записи на границах фазовых переходов
- **Митигация:**
  - Явная валидация покрытия tmelt ± 10K и tboil ± 10K
  - Запрет на объединение записей разных фаз
  - Сохранение текущей логики `PhaseTransitionDetector`
  - Детальное логирование решений об объединении/замене записей
- **Индикаторы:** Разрывы в свойствах при переходах, некорректные энтальпии переходов
- **План восстановления:** Добавление дополнительных проверок в `validate_phase_transitions()`

**3. Обратная несовместимость**
- **Риск:** Изменения в RecordRangeBuilder могут нарушить существующую функциональность
- **Митигация:**
  - Флаг `use_optimization=False` по умолчанию (opt-in подход)
  - 100% прохождение существующих интеграционных тестов без изменений
  - Сохранение существующего API без breaking changes
  - Постепенное включение оптимизации через конфигурацию
- **Индикаторы:** Провал существующих тестов, изменение результатов при `use_optimization=False`
- **План восстановления:** Изоляция оптимизации в отдельный метод без модификации текущего

### Средний приоритет

**4. Ухудшение производительности**
- **Риск:** Overhead оптимизации превышает 20% относительно времени трёхуровневого отбора
- **Митигация:**
  - Профилирование на каждом этапе разработки (cProfile, line_profiler)
  - Кэширование результатов поиска альтернативных записей
  - Оптимизация алгоритма сравнения коэффициентов Шомейта
  - Цель: средняя оптимизация <50ms на вещество
- **Индикаторы:** Время оптимизации >50ms, overhead >20%
- **План восстановления:** Оптимизация узких мест, упрощение алгоритма

**5. Недостаточное сокращение записей**
- **Риск:** Реальное сокращение <15% вместо ожидаемых 15-40%
- **Митигация:**
  - Анализ структуры данных в базе на предмет возможностей оптимизации
  - Тестирование на реальных данных из сессионных логов
  - Адаптивная настройка весов формулы оптимальности (w1, w2, w3)
  - Расширение критериев виртуального объединения (с сохранением точности)
- **Индикаторы:** Среднее сокращение <15% на тестовом наборе
- **План восстановления:** Анализ случаев отсутствия оптимизации, корректировка алгоритма

**6. Сложность отладки виртуальных записей**
- **Риск:** Трудности в диагностике проблем при использовании виртуальных записей
- **Митигация:**
  - Детальное логирование создания виртуальных записей
  - Сохранение ссылок на исходные записи в `VirtualRecord.source_records`
  - Специальные методы отладки: `VirtualRecord.explain_merge()`
  - Расширенный вывод в SessionLogger с описанием оптимизации
- **Индикаторы:** Частые вопросы об источнике данных в виртуальных записях
- **План восстановления:** Добавление детализированного логирования, инструментов визуализации

### Низкий приоритет

**7. Сложные граничные случаи в реальных данных**
- **Риск:** Непредвиденные комбинации записей в базе данных, не покрытые тестами
- **Митигация:**
  - Расширенное тестирование на реальных данных (100+ соединений)
  - Детальное логирование всех решений алгоритма через SessionLogger
  - Graceful degradation: при невозможности оптимизации возврат к исходному набору
  - Накопление статистики использования для выявления паттернов
- **Индикаторы:** Ошибки при обработке специфических соединений
- **План восстановления:** Добавление специальных правил для проблемных случаев

**8. Конфликт с будущими изменениями в базе данных**
- **Риск:** Изменения структуры или содержания базы данных могут нарушить логику оптимизации
- **Митигация:**
  - Абстракция через интерфейсы (DatabaseRecord, VirtualRecord)
  - Версионирование алгоритма оптимизации
  - Валидация структуры данных при загрузке
  - Документирование зависимостей от структуры БД
- **Индикаторы:** Ошибки после обновления базы данных
- **План восстановления:** Обновление валидации, адаптация алгоритма

**9. Использование памяти при большом количестве виртуальных записей**
- **Риск:** Накопление виртуальных записей в памяти при обработке множества соединений
- **Митигация:**
  - Ограничение кэша виртуальных записей (LRU cache)
  - Мониторинг использования памяти в performance тестах
  - Автоматическая очистка неиспользуемых виртуальных записей
  - Цель: дополнительное использование <10MB
- **Индикаторы:** Рост памяти >10MB при обработке реакций
- **План восстановления:** Оптимизация хранения, уменьшение размера VirtualRecord

## Метрики успеха проекта

### Обязательные критерии (Must Have):
1. ✅ Все существующие интеграционные тесты проходят без регрессий
2. ✅ Точность расчётов сохраняется в пределах ±0.01%
3. ✅ Обратная совместимость: `use_optimization=False` → идентичные результаты
4. ✅ Overhead производительности <20% от времени трёхуровневого отбора

### Целевые критерии (Should Have):
5. 🎯 Среднее сокращение записей ≥15% на тестовом наборе из 20 соединений
6. 🎯 Время оптимизации <50ms на одно вещество
7. 🎯 Дополнительное использование памяти <10MB
8. 🎯 100% покрытие кода unit-тестами для OptimalRecordSelector

### Желательные критерии (Nice to Have):
9. ⭐ Сокращение записей до 40% для случаев с избыточным дублированием
10. ⭐ Автоматическое выявление и логирование паттернов оптимизации
11. ⭐ Документация с примерами интерпретации логов оптимизации

---

**Версия документа:** 3.0 (конкретизированная)
**Дата обновления:** 9 ноября 2025
**Статус:** Готово к реализации
**Автор конкретизации:** GitHub Copilot

**Основные изменения от v2.0:**
- Добавлена чёткая формула оптимальности с весами (w1=0.5, w2=0.3, w3=0.2)
- Конкретизирован алгоритм как постобработка после трёхуровневой стратегии (этап 4)
- Исправлены нереалистичные ожидания для SiO2 (4→4 записи, текущий набор оптимален)
- Детализирован пример для H2O с механизмом виртуального объединения газовых записей
- Уточнены критерии приёмки с реалистичными метриками (15-40% сокращение вместо 30%)
- Расширен план реализации с 16 до 18 дней с конкретными задачами по дням
- Добавлены 8 детальных граничных случаев с кодом валидации
- Детализированы риски (9 сценариев) с планами митигации и восстановления
- Добавлены метрики успеха проекта (Must Have / Should Have / Nice to Have)
- Уточнена точность расчётов: ±0.01% вместо ±0.1%
