# Stage 02: Расширение DatabaseRecord для многофазных данных

## Цель
Добавить в `DatabaseRecord` методы для работы с многофазными данными и идентификации распространённых веществ.

## Статус
🔴 Не начато

## Входные данные
- Существующий `DatabaseRecord` (src/thermo_agents/models/search.py)
- Stage 01 завершён (модели PhaseSegment, PhaseTransition созданы)

## Выходные данные
- Методы `DatabaseRecord.is_base_record()` — проверка, является ли запись базовой (H298≠0)
- Методы `DatabaseRecord.covers_temperature()` — проверка покрытия температуры
- Методы `DatabaseRecord.has_phase_transition_at()` — проверка фазового перехода

## Изменяемые файлы
- `src/thermo_agents/models/search.py` — расширение класса DatabaseRecord

## Зависимости
- Stage 01 (модели данных)

## Алгоритм действий

### Шаг 1: Добавление is_base_record()
1. Реализовать метод проверки базовой записи:
   - Базовая запись: H298≠0 ИЛИ S298≠0
   - Продолжающая запись: H298=0 И S298=0
2. Использовать порог сравнения: `abs(value) > 1e-6`
3. Применение: определение начальной точки расчёта

### Шаг 2: Добавление covers_temperature(T)
1. Простая проверка вхождения:
   - `return self.tmin <= T <= self.tmax`
2. Применение: фильтрация записей по целевой температуре

### Шаг 3: Добавление has_phase_transition_at(T)
1. Проверка совпадения с Tmelt:
   - `if abs(T - self.tmelt) < tolerance and self.tmelt > 0: return "melting"`
2. Проверка совпадения с Tboil:
   - `if abs(T - self.tboil) < tolerance and self.tboil > 0: return "boiling"`
3. Использовать tolerance=1e-3 для учёта ошибок округления
4. Применение: идентификация фазовых переходов

### Шаг 4: Добавление get_transition_type(next_record)
1. Проверка изменения фазы:
   - Если `self.phase == next_record.phase` → None
2. Проверка соприкосновения:
   - Если `abs(self.tmax - next_record.tmin) > 1e-3` → None
3. Формирование строки перехода:
   - `f"{self.phase}→{next_record.phase}"`
4. Применение: генерация информации о переходах для логов

### Шаг 5: Вспомогательные методы
1. `get_temperature_range()` — возврат (Tmin, Tmax)
2. `overlaps_with(other)` — проверка перекрытия диапазонов
3. Применение: валидация и диагностика

### Шаг 6: Тестирование
1. Unit-тесты для каждого метода
2. Тесты edge cases (граничные температуры, переходы)
3. Интеграционные тесты с CompoundSearcher

## Детальный алгоритм

### is_base_record(): Определение базовой записи

**Назначение:** Определить, является ли запись стартовой точкой расчёта или требует накопления из предыдущих сегментов.

**Логика:**
```
IF abs(record.h298) > THRESHOLD OR abs(record.s298) > THRESHOLD:
    RETURN True  # Базовая запись
ELSE:
    RETURN False  # Продолжающая запись, требует накопления
```

**Константы:**
- `THRESHOLD = 1e-6` (порог для учёта ошибок округления)

**Примеры:**
- FeO (298-600K): H298=-265.053 кДж/моль → **базовая**
- FeO (600-900K): H298=0.0, S298=0.0 → **продолжающая**

**Применение в многофазном расчёте:**
```python
if not first_record.is_base_record():
    raise ValueError(
        f"Первая запись для {formula} не является базовой. "
        f"Невозможно начать расчёт без H298 и S298."
    )
```

### covers_temperature(T): Проверка покрытия температуры

**Назначение:** Определить, применима ли запись для температуры T.

**Логика:**
```
RETURN (record.tmin <= T <= record.tmax)
```

**Граничные случаи:**
- T = Tmin: включается (>=)
- T = Tmax: включается (<=)
- T < Tmin или T > Tmax: не включается

**Применение:**
```python
# Фильтрация записей для T=1700K
applicable_records = [
    rec for rec in all_records
    if rec.covers_temperature(1700.0)
]
```

### has_phase_transition_at(T): Идентификация фазового перехода

**Назначение:** Определить, происходит ли фазовый переход при температуре T.

**Логика:**
```
tolerance = 1e-3  # 0.001 K

IF abs(T - record.tmelt) < tolerance AND record.tmelt > 0:
    RETURN "melting"

IF abs(T - record.tboil) < tolerance AND record.tboil > 0:
    RETURN "boiling"

RETURN None
```

**Примеры:**
- FeO: Tmelt=1650K → `has_phase_transition_at(1650.0)` = "melting"
- H2O: Tboil=373.15K → `has_phase_transition_at(373.15)` = "boiling"
- Промежуточная T: `has_phase_transition_at(500.0)` = None

**Применение:**
```python
if record.has_phase_transition_at(T_segment_end):
    # Добавить PhaseTransition в результат
    transition = PhaseTransition(
        temperature=T_segment_end,
        from_phase=record.phase,
        to_phase=next_record.phase,
        transition_type=TransitionType.MELTING
    )
```

### get_transition_type(next_record): Определение типа перехода

**Назначение:** Определить тип фазового перехода между двумя последовательными записями.

**Алгоритм:**
```
# Шаг 1: Проверка одинаковой фазы
IF self.phase == next_record.phase:
    RETURN None  # Нет перехода

# Шаг 2: Проверка соприкосновения диапазонов
gap = abs(self.tmax - next_record.tmin)
IF gap > 1e-3:
    RETURN None  # Записи не соприкасаются

# Шаг 3: Формирование строки перехода
from_phase = self.phase.lower()
to_phase = next_record.phase.lower()

RETURN f"{from_phase}→{to_phase}"
```

**Примеры:**
```python
# FeO (s, 1300-1650K) → FeO (l, 1650-5000K)
transition = record_s4.get_transition_type(record_l)
# → "s→l" (плавление)

# FeO (s, 298-600K) → FeO (s, 600-900K)
transition = record_s1.get_transition_type(record_s2)
# → None (та же фаза)

# Несоприкасающиеся записи (пробел)
transition = record_gap1.get_transition_type(record_gap2)
# → None (gap > 1e-3)
```

**Применение:**
```python
for i in range(len(records) - 1):
    transition_type = records[i].get_transition_type(records[i + 1])
    if transition_type:
        logger.info(f"Фазовый переход: {transition_type} при T={records[i].tmax}K")
```

## Критерии завершения
- [ ] Методы добавлены в `DatabaseRecord`
- [ ] Unit-тесты покрывают все методы
- [ ] Документация обновлена

## Тесты
- `tests/test_models/test_database_record_extensions.py`

## Риски

### Риск 1: Ошибки округления при сравнении температур (Средний)
**Описание:** Температуры могут иметь небольшие ошибки округления (например, 273.15 vs 273.1500000001), что приведёт к ложным negative в проверках.  
**Митигация:** Использовать tolerance=1e-3 во всех сравнениях с плавающей точкой.  
**План действий:**
```python
# Вместо:
if T == self.tmelt:
    
# Использовать:
if abs(T - self.tmelt) < 1e-3:
```

### Риск 2: Некорректное определение перехода при пробелах (Средний)
**Описание:** Если между записями есть пробел (gap), метод `get_transition_type()` должен возвращать None, а не некорректный переход.  
**Митигация:** Проверка `abs(self.tmax - next_record.tmin) < tolerance`.  
**План действий:** Добавить unit-тест для gap случая:
```python
def test_get_transition_type_with_gap():
    # record1: 298-500K
    # record2: 600-900K (пробел 500-600K)
    assert record1.get_transition_type(record2) is None
```

### Риск 3: Пустые или None значения фаз (Низкий)
**Описание:** Если `record.phase` или `next_record.phase` равны None, метод `get_transition_type()` может упасть.  
**Митигация:** Добавить проверку:
```python
if not self.phase or not next_record.phase:
    return None
```
**План действий:** Реализовать defensive programming в Шаге 4.

### Риск 4: Влияние на существующий код (Низкий)
**Описание:** Добавление новых методов может замедлить импорт модуля или сломать существующие зависимости.  
**Митигация:** Методы не изменяют существующие поля, только добавляют новые. Импорт останется быстрым.  
**План действий:** Запустить существующие тесты после изменений.

### Риск 5: Производительность при частых вызовах (Низкий)
**Описание:** Методы `covers_temperature()` и `is_base_record()` будут вызываться тысячи раз в циклах поиска.  
**Митигация:** Все методы — O(1) операции, без циклов и вызовов БД.  
**Ожидаемая производительность:** < 0.1 мкс на вызов.  
**План действий:** Если performance тесты показывают деградацию, добавить кэширование результатов.

## Примечания
Эти методы будут использоваться в CompoundSearcher и ThermodynamicCalculator.

---

## Примеры кода

### Пример 1: Расширение DatabaseRecord

```python
# src/thermo_agents/models/search.py

class DatabaseRecord(BaseModel):
    """
    Представление записи из термодинамической БД.
    ... (существующие поля)
    """
    
    # Существующие поля...
    
    def is_base_record(self) -> bool:
        """
        Проверка, является ли запись базовой (содержит H298≠0 и S298≠0).
        
        Базовая запись имеет собственные термодинамические значения при 298K.
        Записи с H298=0 и S298=0 требуют накопления из предыдущих сегментов.
        
        Returns:
            True если H298≠0 или S298≠0
        """
        return abs(self.h298) > 1e-6 or abs(self.s298) > 1e-6
    
    def covers_temperature(self, T: float) -> bool:
        """
        Проверка, покрывает ли запись заданную температуру.
        
        Args:
            T: Температура в Кельвинах
            
        Returns:
            True если Tmin ≤ T ≤ Tmax
        """
        return self.tmin <= T <= self.tmax
    
    def has_phase_transition_at(self, T: float, tolerance: float = 1e-3) -> Optional[str]:
        """
        Проверка наличия фазового перехода при температуре T.
        
        Args:
            T: Температура в Кельвинах
            tolerance: Допуск для сравнения температур
            
        Returns:
            Тип перехода ("melting", "boiling") или None
        """
        if abs(T - self.tmelt) < tolerance and self.tmelt > 0:
            return "melting"
        if abs(T - self.tboil) < tolerance and self.tboil > 0:
            return "boiling"
        return None
    
    def get_transition_type(self, next_record: "DatabaseRecord") -> Optional[str]:
        """
        Определение типа фазового перехода между текущей и следующей записью.
        
        Args:
            next_record: Следующая запись по температуре
            
        Returns:
            Тип перехода ("s→l", "l→g", "s→g") или None
        """
        if self.phase == next_record.phase:
            return None  # Нет изменения фазы
        
        # Проверка, что записи соприкасаются по температуре
        if abs(self.tmax - next_record.tmin) > 1e-3:
            return None  # Нет соприкосновения
        
        from_phase = (self.phase or "").lower()
        to_phase = (next_record.phase or "").lower()
        
        return f"{from_phase}→{to_phase}"
    
    def get_temperature_range(self) -> Tuple[float, float]:
        """
        Получение температурного диапазона записи.
        
        Returns:
            Кортеж (Tmin, Tmax)
        """
        return (self.tmin, self.tmax)
    
    def overlaps_with(self, other: "DatabaseRecord") -> bool:
        """
        Проверка перекрытия температурных диапазонов двух записей.
        
        Args:
            other: Другая запись для сравнения
            
        Returns:
            True если диапазоны перекрываются
        """
        return not (self.tmax < other.tmin or self.tmin > other.tmax)
```

### Пример 2: Unit-тесты для расширений

```python
# tests/test_models/test_database_record_extensions.py

import pytest
from src.thermo_agents.models.search import DatabaseRecord

@pytest.fixture
def base_record():
    """Базовая запись с H298≠0."""
    return DatabaseRecord(
        formula="FeO",
        phase="s",
        tmin=298.0,
        tmax=600.0,
        h298=-265.053,  # кДж/моль → Дж/моль
        s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )

@pytest.fixture
def continuation_record():
    """Продолжающая запись с H298=0."""
    return DatabaseRecord(
        formula="FeO",
        phase="s",
        tmin=600.0,
        tmax=900.0,
        h298=0.0,  # Требует накопления
        s298=0.0,
        f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )

@pytest.fixture
def liquid_record():
    """Запись для жидкой фазы."""
    return DatabaseRecord(
        formula="FeO",
        phase="l",
        tmin=1650.0,
        tmax=5000.0,
        h298=24.058,
        s298=14.581,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0,
        tboil=3687.0,
        reliability_class=1
    )


def test_is_base_record(base_record, continuation_record):
    """Тест определения базовой записи."""
    assert base_record.is_base_record() is True
    assert continuation_record.is_base_record() is False


def test_covers_temperature(base_record):
    """Тест покрытия температуры."""
    assert base_record.covers_temperature(298.0) is True
    assert base_record.covers_temperature(450.0) is True
    assert base_record.covers_temperature(600.0) is True
    assert base_record.covers_temperature(200.0) is False
    assert base_record.covers_temperature(700.0) is False


def test_has_phase_transition_at(base_record):
    """Тест определения фазового перехода."""
    assert base_record.has_phase_transition_at(1650.0) == "melting"
    assert base_record.has_phase_transition_at(3687.0) == "boiling"
    assert base_record.has_phase_transition_at(1000.0) is None


def test_get_transition_type(base_record, continuation_record, liquid_record):
    """Тест определения типа перехода между записями."""
    # s → s (та же фаза)
    transition = base_record.get_transition_type(continuation_record)
    assert transition is None  # Нет изменения фазы
    
    # s → l (плавление)
    solid_to_liquid = DatabaseRecord(
        formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
        h298=0.0, s298=0.0,
        f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    transition = solid_to_liquid.get_transition_type(liquid_record)
    assert transition == "s→l"


def test_get_temperature_range(base_record):
    """Тест получения температурного диапазона."""
    tmin, tmax = base_record.get_temperature_range()
    assert tmin == 298.0
    assert tmax == 600.0


def test_overlaps_with():
    """Тест проверки перекрытия диапазонов."""
    record1 = DatabaseRecord(
        formula="H2O", phase="s", tmin=200.0, tmax=273.15,
        h298=-285.83, s298=69.95,
        f1=30.0, f2=6.0, f3=6.0, f4=-2.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )
    
    record2 = DatabaseRecord(
        formula="H2O", phase="l", tmin=273.15, tmax=373.15,
        h298=-285.83, s298=69.95,
        f1=75.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )
    
    record3 = DatabaseRecord(
        formula="H2O", phase="g", tmin=500.0, tmax=1000.0,
        h298=-241.83, s298=188.83,
        f1=33.0, f2=2.5, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )
    
    # record1 и record2 соприкасаются (273.15)
    assert record1.overlaps_with(record2) is True
    
    # record2 и record3 не перекрываются
    assert record2.overlaps_with(record3) is False
```

### Пример 3: Использование в CompoundSearcher

```python
# src/thermo_agents/search/compound_searcher.py

def search_all_phases(
    self,
    formula: str,
    max_temperature: float,
    compound_names: Optional[List[str]] = None
) -> List[DatabaseRecord]:
    """
    Поиск всех фаз вещества с покрытием до max_temperature.
    
    Использует методы DatabaseRecord для фильтрации.
    """
    # ... (поиск в БД)
    
    # Фильтрация: оставить только записи, покрывающие нужный диапазон
    relevant_records = [
        rec for rec in all_records
        if rec.tmin <= max_temperature  # Используем новый метод
    ]
    
    # Сортировка по температуре
    relevant_records.sort(key=lambda r: r.tmin)
    
    # Проверка базовой записи
    if relevant_records and not relevant_records[0].is_base_record():
        self.logger.warning(
            f"Первая запись для {formula} не является базовой (H298=0)"
        )
    
    # Проверка фазовых переходов между записями
    transitions = []
    for i in range(len(relevant_records) - 1):
        transition_type = relevant_records[i].get_transition_type(
            relevant_records[i + 1]
        )
        if transition_type:
            transitions.append({
                "T": relevant_records[i].tmax,
                "type": transition_type
            })
    
    return relevant_records
```

### Пример 4: Интеграционный тест с полным циклом FeO

```python
# tests/integration/test_database_record_methods.py

import pytest
from src.thermo_agents.models.search import DatabaseRecord

def test_feo_full_chain_with_new_methods():
    """
    Интеграционный тест: проверка всех новых методов на реальном примере FeO.
    
    Сценарий:
    - 5 записей FeO (4 твёрдых + 1 жидкая)
    - Проверка базовой записи
    - Проверка покрытия температур
    - Проверка фазовых переходов
    - Проверка типов переходов между записями
    """
    # ШАГ 1: Создание 5 записей FeO
    records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.053, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=0.0, s298=0.0,  # Продолжающая запись
            f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=900.0, tmax=1300.0,
            h298=0.0, s298=0.0,
            f1=90.408, f2=-38.021, f3=-83.811, f4=15.358, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
            h298=0.0, s298=0.0,
            f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24.058, s298=14.581,  # Базовая запись для жидкой фазы
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]
    
    # ШАГ 2: Проверка is_base_record()
    assert records[0].is_base_record() is True, "Первая запись должна быть базовой"
    assert records[1].is_base_record() is False, "Вторая запись — продолжающая"
    assert records[2].is_base_record() is False
    assert records[3].is_base_record() is False
    assert records[4].is_base_record() is True, "Жидкая фаза имеет свои H298/S298"
    
    # ШАГ 3: Проверка covers_temperature()
    assert records[0].covers_temperature(298.0) is True
    assert records[0].covers_temperature(450.0) is True
    assert records[0].covers_temperature(600.0) is True
    assert records[0].covers_temperature(700.0) is False, "За пределами диапазона"
    
    assert records[4].covers_temperature(1700.0) is True
    assert records[4].covers_temperature(3000.0) is True
    assert records[4].covers_temperature(1500.0) is False, "Ниже Tmin жидкости"
    
    # ШАГ 4: Проверка has_phase_transition_at()
    for rec in records:
        assert rec.has_phase_transition_at(1650.0) == "melting", "Все записи знают о Tmelt"
        assert rec.has_phase_transition_at(3687.0) == "boiling", "Все записи знают о Tboil"
        assert rec.has_phase_transition_at(1000.0) is None, "Нет перехода при 1000K"
    
    # ШАГ 5: Проверка get_transition_type()
    # s → s (та же фаза, нет перехода)
    assert records[0].get_transition_type(records[1]) is None
    assert records[1].get_transition_type(records[2]) is None
    assert records[2].get_transition_type(records[3]) is None
    
    # s → l (плавление)
    transition = records[3].get_transition_type(records[4])
    assert transition == "s→l", f"Ожидался переход s→l, получен {transition}"
    
    # ШАГ 6: Проверка get_temperature_range()
    tmin, tmax = records[0].get_temperature_range()
    assert tmin == 298.0
    assert tmax == 600.0
    
    # ШАГ 7: Проверка overlaps_with()
    assert records[0].overlaps_with(records[1]) is True, "Записи соприкасаются при 600K"
    assert records[3].overlaps_with(records[4]) is True, "Записи соприкасаются при 1650K"
    assert records[0].overlaps_with(records[2]) is False, "Записи не перекрываются"
    
    print("✅ Все новые методы работают корректно на примере FeO")

def test_edge_case_gap_between_records():
    """Тест edge case: пробел между записями."""
    record1 = DatabaseRecord(
        formula="X", phase="s", tmin=298.0, tmax=500.0,
        h298=-100.0, s298=50.0,
        f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1000.0, tboil=2000.0, reliability_class=1
    )
    
    record2 = DatabaseRecord(
        formula="X", phase="s", tmin=600.0, tmax=1000.0,  # Пробел 500-600K
        h298=0.0, s298=0.0,
        f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1000.0, tboil=2000.0, reliability_class=1
    )
    
    # Должно вернуть None из-за пробела
    assert record1.get_transition_type(record2) is None
    
    # overlaps_with должен вернуть False
    assert record1.overlaps_with(record2) is False

def test_edge_case_none_phases():
    """Тест edge case: записи с None в фазах."""
    record1 = DatabaseRecord(
        formula="X", phase=None, tmin=298.0, tmax=500.0,
        h298=-100.0, s298=50.0,
        f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=0.0, tboil=0.0, reliability_class=1
    )
    
    record2 = DatabaseRecord(
        formula="X", phase="s", tmin=500.0, tmax=1000.0,
        h298=0.0, s298=0.0,
        f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=0.0, tboil=0.0, reliability_class=1
    )
    
    # Должно обработать None фазу
    transition = record1.get_transition_type(record2)
    assert transition == "→s"  # Пустая строка для None фазы
```

### Пример 5: Performance тест для новых методов

```python
# tests/performance/test_database_record_performance.py

import pytest
import time
from src.thermo_agents.models.search import DatabaseRecord

def test_covers_temperature_performance():
    """Тест производительности метода covers_temperature()."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    start = time.perf_counter()
    
    # 100,000 вызовов
    for _ in range(100_000):
        _ = record.covers_temperature(450.0)
    
    elapsed = time.perf_counter() - start
    
    # Требование: < 10ms для 100k вызовов
    assert elapsed < 0.01, f"Слишком медленно: {elapsed*1000:.2f}ms"
    
    per_call = (elapsed / 100_000) * 1_000_000  # микросекунды
    print(f"✅ covers_temperature(): {per_call:.3f} мкс/вызов")

def test_is_base_record_performance():
    """Тест производительности метода is_base_record()."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    start = time.perf_counter()
    
    # 100,000 вызовов
    for _ in range(100_000):
        _ = record.is_base_record()
    
    elapsed = time.perf_counter() - start
    
    # Требование: < 5ms для 100k вызовов
    assert elapsed < 0.005, f"Слишком медленно: {elapsed*1000:.2f}ms"
    
    per_call = (elapsed / 100_000) * 1_000_000
    print(f"✅ is_base_record(): {per_call:.3f} мкс/вызов")

def test_get_transition_type_performance():
    """Тест производительности метода get_transition_type()."""
    record1 = DatabaseRecord(
        formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
        h298=0.0, s298=0.0,
        f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    record2 = DatabaseRecord(
        formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
        h298=24.058, s298=14.581,
        f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    start = time.perf_counter()
    
    # 50,000 вызовов
    for _ in range(50_000):
        _ = record1.get_transition_type(record2)
    
    elapsed = time.perf_counter() - start
    
    # Требование: < 10ms для 50k вызовов
    assert elapsed < 0.01, f"Слишком медленно: {elapsed*1000:.2f}ms"
    
    per_call = (elapsed / 50_000) * 1_000_000
    print(f"✅ get_transition_type(): {per_call:.3f} мкс/вызов")
```

---

## План реализации

1. **День 1**: Добавление методов в `DatabaseRecord`
2. **День 1**: Написание unit-тестов
3. **День 2**: Интеграция с `CompoundSearcher` (подготовка к Stage 03)

## Следующий этап
Stage 03: Реализация поиска всех фаз вещества (CompoundSearcher.search_all_phases)
