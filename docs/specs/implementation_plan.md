# План имплементации: Минимальные изменения

## Суть решения

**Два основных изменения:**

### 1. Динамическая смена референсных значений H₂₉₈/S₂₉₈
- Добавить опциональный параметр `reference_record` в `calculate_properties()`
- Добавить вспомогательный метод `_select_reference_record()`

### 2. Определение простых веществ через LLM
- Добавить поле `is_elemental` в `ExtractedReactionParameters`
- Обновить промпт LLM для определения типа вещества
- Применить правило: **простые вещества имеют H₂₉₈ = 0.0**

**Итого: 2 файла, ~100 строк кода**

---

## Изменения в коде

### ЧАСТЬ 1: Модель извлечения параметров

#### Файл: `src/thermo_agents/models/extraction.py`

**Изменение 1: Добавить поле `is_elemental` в класс `ExtractedReactionParameters`** (после строки ~190)

**Добавить:**
```python
is_elemental: Optional[bool] = Field(
    default=None,
    description=(
        "Является ли вещество простым (состоит из одного элемента). "
        "True для O2, N2, H2, C, Fe, Cl2 и т.п. "
        "False для H2O, CO2, NH3, NaCl и других сложных веществ. "
        "Только для query_type='compound_data' (одно вещество). "
        "Для простых веществ H₂₉₈ = 0.0 кДж/моль по определению."
    )
)
```

**Изменение 2: Добавить валидатор** (после существующих валидаторов, строка ~210)

**Добавить:**
```python
@field_validator('is_elemental')
@classmethod
def validate_is_elemental(cls, v, info):
    """Проверка корректности флага is_elemental."""
    query_type = info.data.get('query_type')
    all_compounds = info.data.get('all_compounds', [])
    
    # is_elemental применим только для compound_data (одно вещество)
    if v is not None and query_type != 'compound_data':
        raise ValueError(
            "Поле is_elemental применимо только для query_type='compound_data'"
        )
    
    if v is not None and len(all_compounds) > 1:
        raise ValueError(
            "Поле is_elemental применимо только для запросов с одним веществом"
        )
    
    return v
```

---

### ЧАСТЬ 2: Термодинамический калькулятор

#### Файл: `src/thermo_agents/calculations/thermodynamic_calculator.py`

#### Изменение 1: Метод `calculate_properties()` (строки 164-226)

**Было:**
```python
def calculate_properties(
    self,
    record: DatabaseRecord,
    T: float
) -> ThermodynamicProperties:
```

**Стало:**
```python
def calculate_properties(
    self,
    record: DatabaseRecord,
    T: float,
    reference_record: Optional[DatabaseRecord] = None,
    is_elemental: Optional[bool] = None  # ← НОВЫЙ ПАРАМЕТР
) -> ThermodynamicProperties:
```

**Изменение в теле метода (строки 205-208):**

**Было:**
```python
# Базовые значения при 298.15K
h298 = getattr(record, 'h298', 0.0)
s298 = getattr(record, 's298', 0.0)
H298 = h298 * 1000.0  # кДж/моль → Дж/моль
S298 = s298  # Дж/(моль·K)
```

**Стало:**
```python
# Базовые значения при 298.15K
# Если передана референсная запись, берём h298/s298 из неё
if reference_record is not None:
    h298 = getattr(reference_record, 'h298', 0.0)
    s298 = getattr(reference_record, 's298', 0.0)
else:
    # Legacy behaviour: используем текущую запись
    h298 = getattr(record, 'h298', 0.0)
    s298 = getattr(record, 's298', 0.0)

# Применяем правило для простых веществ
if is_elemental is True:
    h298 = 0.0  # Для простых веществ H298 всегда 0 по определению

H298 = h298 * 1000.0  # кДж/моль → Дж/моль
S298 = s298  # Дж/(моль·K)
```

**Обновление docstring:**
```python
"""
Расчёт всех термодинамических свойств при температуре T.

Формулы:
- H(T) = H298 + ∫[298→T] Cp(T) dT
- S(T) = S298 + ∫[298→T] Cp(T)/T dT
- G(T) = H(T) - T*S(T)

Args:
    record: Запись из базы данных с коэффициентами для расчёта Cp(T)
    T: Температура, K
    reference_record: Опциональная запись-источник для h298/s298.
                      Если None, используются значения из record.
                      Используется для многофазных расчётов, где референсные
                      значения могут отличаться от коэффициентов текущей записи.
    is_elemental: True если вещество простое (O2, N2, Fe, C...).
                  Для простых веществ H298 принудительно устанавливается в 0.0.
                  False для сложных веществ (H2O, CO2, NH3...).
                  None если тип неизвестен (legacy поведение).

Returns:
    ThermodynamicProperties при температуре T

Raises:
    ValueError: Если температура вне допустимого диапазона

Examples:
    >>> # Сложное вещество (вода)
    >>> props = calculator.calculate_properties(h2o_record, 500.0, is_elemental=False)
    
    >>> # Простое вещество (кислород)
    >>> props = calculator.calculate_properties(o2_record, 500.0, is_elemental=True)
    >>> assert props.H == 0.0  # H298 = 0 для простых веществ
"""
```

---

#### Изменение 2: Новый метод `_select_reference_record()` (добавить после строки 560)

```python
def _select_reference_record(
    self,
    records: List[DatabaseRecord],
    current_index: int,
    is_elemental: Optional[bool] = None
) -> DatabaseRecord:
    """
    Выбор референсной записи для расчёта H(T) и S(T) в многофазных системах.
    
    Алгоритм (из calc_example.ipynb):
    0. Простое вещество (is_elemental=True) → H298=0.0 принудительно
    1. Первая запись (idx=0) → использует саму себя
    2. Смена фазы + валидные h298/s298 (не нули) → новая запись
    3. Смена фазы + нулевые h298/s298 → первая запись предыдущей фазы
    4. Та же фаза → первая запись текущей фазы
    
    Args:
        records: Список записей, отсортированный по tmin
        current_index: Индекс текущей записи
        is_elemental: True если вещество простое (H298=0 по определению)
    
    Returns:
        DatabaseRecord, который следует использовать как источник h298/s298
    
    Examples:
        >>> # NH4Cl: запись 0 (s, 298-457K), запись 1 (s, 457-800K)
        >>> ref0 = calc._select_reference_record([rec0, rec1], 0)  # rec0
        >>> ref1 = calc._select_reference_record([rec0, rec1], 1)  # rec0 (та же фаза)
        
        >>> # CeCl3: запись 0 (s, 298-1080K), запись 1 (l, 1080-1300K, h298=0)
        >>> ref1 = calc._select_reference_record([rec0, rec1], 1)  # rec0 (нулевые значения)
        
        >>> # O2: простое вещество
        >>> ref0 = calc._select_reference_record([rec0], 0, is_elemental=True)  # rec0
        >>> # H298 будет принудительно 0.0 в calculate_properties()
    """
    current = records[current_index]
    
    # Правило 0: Для простых веществ H298 всегда 0
    # (применяется на уровне calculate_properties через параметр is_elemental)
    
    # Правило 1: первая запись использует саму себя
    if current_index == 0:
        return current
    
    previous = records[current_index - 1]
    phase_changed = current.phase != previous.phase
    
    # Правило 2 и 3: смена фазы
    if phase_changed:
        # Проверяем, есть ли валидные данные в текущей записи
        has_valid_h298 = abs(getattr(current, 'h298', 0.0)) > 1e-6
        has_valid_s298 = abs(getattr(current, 's298', 0.0)) > 1e-6
        
        if has_valid_h298 or has_valid_s298:
            # Правило 2: есть валидные данные → используем текущую запись
            return current
        else:
            # Правило 3: нулевые значения → ищем первую запись предыдущей фазы
            for i in range(current_index - 1, -1, -1):
                if i == 0 or records[i].phase != records[i - 1].phase:
                    return records[i]
    
    # Правило 4: та же фаза → находим первую запись текущей фазы
    for i in range(current_index, -1, -1):
        if i == 0 or records[i].phase != records[i - 1].phase:
            return records[i]
    
    # Fallback (не должно сюда дойти)
    return current
```

---

#### Изменение 3: Использование в `calculate_properties_multi_record()` (строки 592-620)

**Найти место в методе, где вызывается `calculate_properties()`:**

```python
# Get the appropriate record for this temperature
active_record = compound_data.get_record_at_temperature(temperature)

# Calculate base properties using the selected record
base_properties = self.calculate_properties(active_record, temperature)
```

**Заменить на:**

```python
# Get the appropriate record for this temperature
active_record = compound_data.get_record_at_temperature(temperature)

# Извлекаем is_elemental из метаданных (если есть)
is_elemental = getattr(compound_data, 'is_elemental', None)

# Определяем референсную запись для многофазных расчётов
all_records = compound_data.records
if len(all_records) > 1:
    # Находим индекс активной записи
    try:
        active_index = next(
            i for i, rec in enumerate(all_records) 
            if rec.id == active_record.id
        )
        reference_record = self._select_reference_record(
            all_records, 
            active_index,
            is_elemental=is_elemental  # ← Передаём флаг
        )
    except (StopIteration, AttributeError):
        # Fallback: используем активную запись
        reference_record = active_record
else:
    # Одна запись → использует саму себя
    reference_record = None  # None означает текущую запись

# Calculate base properties using the selected record
base_properties = self.calculate_properties(
    active_record, 
    temperature,
    reference_record=reference_record,
    is_elemental=is_elemental  # ← Передаём флаг
)
```

---

### ЧАСТЬ 3: Промпт для LLM

#### Файл: `src/thermo_agents/prompts.py`

**Добавить в системный промпт инструкцию для определения типа вещества:**

```python
SYSTEM_PROMPT_TEMPLATE = """
...
[Существующие инструкции]
...

## Определение типа вещества (is_elemental)

Если запрос касается ОДНОГО вещества (query_type="compound_data"), определи:

**Простое вещество (is_elemental=True):**
- Состоит из ОДНОГО химического элемента
- Примеры: O2, N2, H2, Cl2, Br2, I2 (двухатомные газы)
- C (графит), S (ромбическая), P (белый фосфор)
- Fe, Cu, Al, Au, Ag, Zn (металлы)

**Сложное вещество (is_elemental=False):**
- Состоит из ДВУХ и более химических элементов
- Примеры: H2O, CO2, NH3, NaCl, CaCO3, H2SO4

**Для запросов с несколькими веществами (query_type="reaction_calculation"):**
- Установи is_elemental=null

**Важно:** Для простых веществ в стандартном состоянии (298.15 K):
- H₂₉₈ = 0.0 кДж/моль (энтальпия образования из элементов)
- S₂₉₈ ≠ 0.0 Дж/(моль·K) (энтропия может быть ненулевой)

Примеры:
- "Покажи данные для кислорода O2" → is_elemental=True
- "Найди свойства воды H2O" → is_elemental=False
- "Реакция 2H2 + O2 → 2H2O" → is_elemental=null (реакция)
...
"""
```

---

## Проверка изменений

### 1. Запустить существующие тесты
```powershell
pytest tests/ -v
```

### 2. Запустить ноутбук
```powershell
# Открыть docs/calc_example.ipynb
# Выполнить все ячейки
# Проверить графики H(T) и S(T) на отсутствие разрывов
```

### 3. Создать простой тест
```python
# tests/unit/test_reference_selection.py

def test_first_record_uses_itself(thermodynamic_calculator):
    """Первая запись использует саму себя как референс."""
    records = [create_mock_record(h298=-100, s298=50)]
    ref = thermodynamic_calculator._select_reference_record(records, 0)
    assert ref == records[0]

def test_phase_change_with_zero_values(thermodynamic_calculator):
    """Смена фазы с нулевыми h298/s298 сохраняет предыдущую референсную запись."""
    records = [
        create_mock_record(phase='s', h298=-100, s298=50),
        create_mock_record(phase='l', h298=0.0, s298=0.0)
    ]
    ref = thermodynamic_calculator._select_reference_record(records, 1)
    assert ref == records[0]  # Должна вернуться первая запись

def test_phase_change_with_valid_values(thermodynamic_calculator):
    """Смена фазы с валидными h298/s298 использует новую запись."""
    records = [
        create_mock_record(phase='s', h298=-100, s298=50),
        create_mock_record(phase='l', h298=-80, s298=60)
    ]
    ref = thermodynamic_calculator._select_reference_record(records, 1)
    assert ref == records[1]  # Должна вернуться вторая запись

def test_elemental_compound_has_zero_h298(thermodynamic_calculator):
    """Простое вещество имеет H298=0.0."""
    record = create_mock_record(h298=-100, s298=50)  # В базе может быть ненулевое значение
    props = thermodynamic_calculator.calculate_properties(
        record, 
        298.15,
        is_elemental=True  # Флаг простого вещества
    )
    # H298 должна быть принудительно установлена в 0
    assert abs(props.H) < 1e-6  # H(298K) ≈ 0 Дж/моль
    assert props.S != 0.0  # S298 может быть ненулевой

def test_complex_compound_uses_database_h298(thermodynamic_calculator):
    """Сложное вещество использует H298 из базы данных."""
    record = create_mock_record(h298=-241.8, s298=188.8)  # H2O
    props = thermodynamic_calculator.calculate_properties(
        record, 
        298.15,
        is_elemental=False  # Флаг сложного вещества
    )
    # H298 должна быть из базы данных
    assert abs(props.H / 1000 - (-241.8)) < 1e-6  # H(298K) = -241.8 кДж/моль

def test_is_elemental_validation_in_extraction_model():
    """Валидация поля is_elemental в ExtractedReactionParameters."""
    from src.thermo_agents.models.extraction import ExtractedReactionParameters
    
    # is_elemental применим только для compound_data
    with pytest.raises(ValueError, match="применимо только для query_type='compound_data'"):
        ExtractedReactionParameters(
            query_type="reaction_calculation",
            all_compounds=["H2", "O2", "H2O"],
            is_elemental=True,  # ← Ошибка: реакция, а не одно вещество
            # ... остальные поля
        )
    
    # is_elemental применим только для одного вещества
    with pytest.raises(ValueError, match="применимо только для запросов с одним веществом"):
        ExtractedReactionParameters(
            query_type="compound_data",
            all_compounds=["H2O", "CO2"],  # ← Два вещества
            is_elemental=True,
            # ... остальные поля
        )
```

---

## Итого изменений

**Файлов:** 3  
- `models/extraction.py` — добавить поле `is_elemental` и валидатор
- `calculations/thermodynamic_calculator.py` — логика референсных записей
- `prompts.py` — инструкция для LLM

**Новых методов:** 1 (`_select_reference_record()`)  
**Изменённых методов:** 2 (`calculate_properties()`, `calculate_properties_multi_record()`)  
**Новых полей в модели:** 1 (`is_elemental`)  
**Строк кода:** ~100 новых, ~15 изменённых  

**Обратная совместимость:** ✅ Гарантирована (опциональные параметры)  
**Риски:** ❌ Минимальные (изолированные изменения)  
**Тестирование:** ✅ Покрывается существующими + 6 новых тестов

---

## Следующий шаг

Запросить подтверждение и приступить к имплементации?
