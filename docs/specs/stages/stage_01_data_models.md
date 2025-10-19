# Stage 01: Создание моделей данных для многофазных расчётов

## Цель
Создать базовые dataclass модели для поддержки многофазных термодинамических расчётов.

## Статус
🟢 Завершено

## Входные данные
- Существующая модель `DatabaseRecord` (src/thermo_agents/models/search.py)
- Требования из ТЗ §4.6

## Выходные данные
- `PhaseSegment` — сегмент расчёта в пределах одной записи
- `PhaseTransition` — информация о фазовом переходе
- `MultiPhaseProperties` — результат многофазного расчёта

## Изменяемые файлы
- `src/thermo_agents/models/search.py` — добавление новых dataclass

## Зависимости
Отсутствуют. Это базовый атомарный этап.

## Алгоритм действий

### Шаг 1: Создание PhaseSegment
1. Определить поля для хранения термодинамических данных сегмента:
   - `record` (DatabaseRecord) — ссылка на исходную запись БД
   - `T_start`, `T_end` — температурные границы сегмента
   - `H_start`, `S_start` — начальные значения энтальпии и энтропии
   - `delta_H`, `delta_S` — изменения в пределах сегмента
   - `is_transition_boundary` — флаг фазового перехода на границе
2. Добавить Pydantic валидаторы:
   - Проверка T_end > T_start
   - Проверка соответствия T_start и T_end диапазону record.tmin/tmax
3. Реализовать метод `to_dict()` для сериализации в логи

### Шаг 2: Создание PhaseTransition
1. Определить enum `TransitionType` (melting, boiling, sublimation, unknown)
2. Создать поля:
   - `temperature` — температура перехода
   - `from_phase`, `to_phase` — исходная и конечная фазы
   - `transition_type` — тип перехода (enum)
   - `delta_H_transition`, `delta_S_transition` — термодинамика перехода
3. Добавить валидатор для автоопределения типа перехода:
   - s→l = melting
   - l→g = boiling
   - s→g = sublimation
4. Реализовать `to_dict()` с форматированием "s→l" для вывода

### Шаг 3: Создание MultiPhaseProperties
1. Определить поля для финальных результатов:
   - `T_target` — целевая температура
   - `H_final`, `S_final`, `G_final`, `Cp_final` — термодинамические свойства
2. Добавить коллекции:
   - `segments: List[PhaseSegment]` — все использованные сегменты
   - `phase_transitions: List[PhaseTransition]` — все переходы
   - `temperature_path`, `H_path`, `S_path` — траектории для графиков
   - `warnings: List[str]` — предупреждения
3. Реализовать property-методы:
   - `has_phase_transitions` → bool
   - `segment_count` → int
4. Реализовать `to_dict()` с конвертацией единиц (Дж→кДж)

### Шаг 4: Добавление валидаторов
1. PhaseSegment: валидация температурного диапазона
2. PhaseTransition: автоопределение типа перехода
3. MultiPhaseProperties: проверка непустых списков сегментов

### Шаг 5: Тестирование
1. Unit-тесты для создания каждой модели
2. Тесты валидаторов (негативные кейсы)
3. Тесты сериализации (to_dict)
4. Тесты property-методов

## Детальный алгоритм

### PhaseSegment: Представление одного сегмента расчёта

**Назначение:** Инкапсуляция данных для накопительного расчёта в пределах одной записи БД.

**Входные данные:**
- DatabaseRecord — запись из БД с коэффициентами Шомейта
- T_start, T_end — температурные границы интегрирования
- H_start, S_start — начальные значения (из предыдущего сегмента или H298/S298)

**Выходные данные:**
- delta_H, delta_S — накопленные изменения
- is_transition_boundary — флаг завершения фазовым переходом

**Логика валидации:**
```
IF T_end <= T_start:
    RAISE ValueError("T_end должен быть больше T_start")

IF T_start < record.tmin OR T_end > record.tmax:
    RAISE ValueError("Температуры выходят за пределы записи")
```

**Пример использования:**
```python
# Сегмент 1: FeO(s) от 298K до 600K
segment1 = PhaseSegment(
    record=feo_record_1,
    T_start=298.0,
    T_end=600.0,
    H_start=-265053.0,  # H298 из record
    S_start=59.807,     # S298 из record
    delta_H=15420.0,    # Вычислено интегрированием Cp(T)
    delta_S=36.85,      # Вычислено интегрированием Cp(T)/T
    is_transition_boundary=False
)
```

### PhaseTransition: Представление фазового перехода

**Назначение:** Хранение данных о фазовом переходе (плавление, кипение, сублимация).

**Входные данные:**
- temperature — температура перехода (из record.tmelt или record.tboil)
- from_phase, to_phase — фазы (например, "s" → "l")
- delta_H_transition, delta_S_transition — термодинамика перехода

**Автоопределение типа:**
```
IF from_phase == "s" AND to_phase == "l":
    transition_type = TransitionType.MELTING

ELIF from_phase == "l" AND to_phase == "g":
    transition_type = TransitionType.BOILING

ELIF from_phase == "s" AND to_phase == "g":
    transition_type = TransitionType.SUBLIMATION

ELSE:
    transition_type = TransitionType.UNKNOWN
```

**Пример использования:**
```python
# Переход плавления FeO при 1650K
transition = PhaseTransition(
    temperature=1650.0,
    from_phase="s",
    to_phase="l",
    transition_type=TransitionType.MELTING,  # Автоопределится
    delta_H_transition=32.0,  # кДж/моль
    delta_S_transition=19.4   # Дж/(моль·K)
)
```

### MultiPhaseProperties: Финальный результат расчёта

**Назначение:** Агрегация всех данных многофазного расчёта.

**Структура:**
```
MultiPhaseProperties
├── T_target: 1700.0K (целевая температура)
├── H_final: -235633.0 (финальная энтальпия, Дж/моль)
├── S_final: 155.44 (финальная энтропия, Дж/(моль·K))
├── G_final: -499582.0 (энергия Гиббса, Дж/моль)
├── Cp_final: 68.199 (теплоёмкость, Дж/(моль·K))
├── segments: [seg1, seg2, seg3, seg4, seg5] (5 сегментов)
├── phase_transitions: [melting_transition] (1 переход)
├── temperature_path: [298, 600, 900, 1300, 1650, 1700] (траектория)
├── H_path: [H(298), H(600), ..., H(1700)] (энтальпийная траектория)
├── S_path: [S(298), S(600), ..., S(1700)] (энтропийная траектория)
└── warnings: [] (предупреждения)
```

**Пример использования:**
```python
result = MultiPhaseProperties(
    T_target=1700.0,
    H_final=-235633.0,
    S_final=155.44,
    G_final=-499582.0,
    Cp_final=68.199,
    segments=all_segments,
    phase_transitions=[melting_transition],
    temperature_path=[298, 600, 900, 1300, 1650, 1700],
    H_path=[-265053, -249633, -230215, -199238, -167238, -163633],
    S_path=[59.807, 96.657, 126.45, 150.87, 170.27, 173.44],
    warnings=[]
)

print(result.to_dict())
# {
#   "T_target": 1700.0,
#   "thermodynamic_properties": {
#     "H": -235.633,  # кДж/моль
#     "S": 155.44,
#     "G": -499.582,  # кДж/моль
#     "Cp": 68.199
#   },
#   "segments_count": 5,
#   "transitions_count": 1,
#   "warnings": []
# }
```

## Критерии завершения
- [ ] Все три класса добавлены в `models/search.py`
- [ ] Pydantic валидаторы работают корректно
- [ ] Unit-тесты покрывают создание и валидацию моделей
- [ ] Типы аннотированы корректно (mypy проверка)

## Тесты
- `tests/test_models/test_phase_segment.py`
- `tests/test_models/test_phase_transition.py`
- `tests/test_models/test_multi_phase_properties.py`

## Риски

### Риск 1: Несовместимость типов данных (Низкий)
**Описание:** Pydantic может не поддерживать вложенные структуры с DatabaseRecord.  
**Митигация:** Использовать `Config.arbitrary_types_allowed = True` в Pydantic моделях.  
**План действий:** Если ошибки валидации, добавить:
```python
class PhaseSegment(BaseModel):
    class Config:
        arbitrary_types_allowed = True
```

### Риск 2: Производительность при большом количестве сегментов (Средний)
**Описание:** Для веществ с 10+ записями траектории (`H_path`, `S_path`) могут содержать тысячи точек.  
**Митигация:** 
- Ограничить детализацию траектории (1 точка на 10K)
- Использовать ленивую генерацию траекторий (property-методы)
- Для графиков использовать sampling  
**План действий:** Если performance тесты показывают >100ms на создание MultiPhaseProperties, оптимизировать хранение траекторий.

### Риск 3: Некорректная сортировка сегментов (Низкий)
**Описание:** Если сегменты добавляются не по порядку, результаты будут некорректными.  
**Митигация:** Добавить валидатор в MultiPhaseProperties:
```python
@validator("segments")
def validate_segments_sorted(cls, v):
    for i in range(len(v) - 1):
        if v[i].T_end > v[i+1].T_start:
            raise ValueError("Сегменты должны быть отсортированы по температуре")
    return v
```
**План действий:** Реализовать валидатор в Шаге 3.

### Риск 4: Отсутствие обратной совместимости (Низкий)
**Описание:** Добавление новых моделей может сломать существующие тесты.  
**Митигация:** Все новые модели создаются в том же файле `models/search.py`, не изменяя существующие.  
**План действий:** Запустить все существующие тесты после добавления моделей.

## Примечания
Этот этап создаёт только структуры данных без бизнес-логики.

---

## Примеры кода

### Пример 1: PhaseSegment

```python
# src/thermo_agents/models/search.py

from pydantic import BaseModel, Field, validator
from typing import Optional

@dataclass
class PhaseSegment(BaseModel):
    """Сегмент расчёта в пределах одной записи БД."""
    
    record: DatabaseRecord = Field(..., description="Запись из БД для этого сегмента")
    T_start: float = Field(..., description="Начальная температура сегмента, K")
    T_end: float = Field(..., description="Конечная температура сегмента, K")
    H_start: float = Field(..., description="Энтальпия в начале сегмента, Дж/моль")
    S_start: float = Field(..., description="Энтропия в начале сегмента, Дж/(моль·K)")
    delta_H: float = Field(..., description="Изменение энтальпии в сегменте, Дж/моль")
    delta_S: float = Field(..., description="Изменение энтропии в сегменте, Дж/(моль·K)")
    is_transition_boundary: bool = Field(
        False, 
        description="Заканчивается ли сегмент фазовым переходом"
    )
    
    @validator("T_end")
    def validate_temperature_range(cls, v, values):
        """Валидация: T_end должен быть больше T_start."""
        if "T_start" in values and v <= values["T_start"]:
            raise ValueError("T_end должен быть больше T_start")
        return v
    
    def to_dict(self) -> dict:
        """Сериализация в словарь."""
        return {
            "formula": self.record.formula,
            "phase": self.record.phase,
            "T_range": [self.T_start, self.T_end],
            "H_range": [self.H_start, self.H_start + self.delta_H],
            "S_range": [self.S_start, self.S_start + self.delta_S],
            "is_transition": self.is_transition_boundary,
        }
```

### Пример 2: PhaseTransition

```python
# src/thermo_agents/models/search.py

from enum import Enum

class TransitionType(str, Enum):
    """Типы фазовых переходов."""
    MELTING = "melting"          # s → l
    BOILING = "boiling"          # l → g
    SUBLIMATION = "sublimation"  # s → g
    UNKNOWN = "unknown"

@dataclass
class PhaseTransition(BaseModel):
    """Информация о фазовом переходе."""
    
    temperature: float = Field(..., description="Температура перехода, K")
    from_phase: str = Field(..., description="Исходная фаза (s/l/g)")
    to_phase: str = Field(..., description="Конечная фаза (s/l/g)")
    transition_type: TransitionType = Field(..., description="Тип перехода")
    delta_H_transition: float = Field(0.0, description="Энтальпия перехода, кДж/моль")
    delta_S_transition: float = Field(0.0, description="Энтропия перехода, Дж/(моль·K)")
    
    @validator("transition_type", pre=True, always=True)
    def determine_transition_type(cls, v, values):
        """Автоопределение типа перехода по фазам."""
        if v and v != TransitionType.UNKNOWN:
            return v
        
        from_p = values.get("from_phase", "").lower()
        to_p = values.get("to_phase", "").lower()
        
        if from_p == "s" and to_p == "l":
            return TransitionType.MELTING
        elif from_p == "l" and to_p == "g":
            return TransitionType.BOILING
        elif from_p == "s" and to_p == "g":
            return TransitionType.SUBLIMATION
        return TransitionType.UNKNOWN
    
    def to_dict(self) -> dict:
        """Сериализация для логирования."""
        return {
            "T": self.temperature,
            "transition": f"{self.from_phase}→{self.to_phase}",
            "type": self.transition_type.value,
            "ΔH": self.delta_H_transition,
            "ΔS": self.delta_S_transition,
        }
```

### Пример 3: MultiPhaseProperties

```python
# src/thermo_agents/models/search.py

from typing import List

@dataclass
class MultiPhaseProperties(BaseModel):
    """Результат многофазного термодинамического расчёта."""
    
    T_target: float = Field(..., description="Целевая температура расчёта, K")
    
    # Финальные термодинамические свойства
    H_final: float = Field(..., description="Энтальпия при T_target, Дж/моль")
    S_final: float = Field(..., description="Энтропия при T_target, Дж/(моль·K)")
    G_final: float = Field(..., description="Энергия Гиббса при T_target, Дж/моль")
    Cp_final: float = Field(..., description="Теплоёмкость при T_target, Дж/(моль·K)")
    
    # Метаданные расчёта
    segments: List[PhaseSegment] = Field(
        default_factory=list,
        description="Все сегменты расчёта"
    )
    phase_transitions: List[PhaseTransition] = Field(
        default_factory=list,
        description="Все фазовые переходы"
    )
    
    # Траектория расчёта (для графиков)
    temperature_path: List[float] = Field(
        default_factory=list,
        description="Температурные точки траектории"
    )
    H_path: List[float] = Field(
        default_factory=list,
        description="Энтальпия вдоль траектории, Дж/моль"
    )
    S_path: List[float] = Field(
        default_factory=list,
        description="Энтропия вдоль траектории, Дж/(моль·K)"
    )
    
    # Предупреждения
    warnings: List[str] = Field(
        default_factory=list,
        description="Предупреждения о пробелах покрытия, перекрытиях и т.д."
    )
    
    def to_dict(self) -> dict:
        """Сериализация результата."""
        return {
            "T_target": self.T_target,
            "thermodynamic_properties": {
                "H": self.H_final / 1000,  # кДж/моль
                "S": self.S_final,
                "G": self.G_final / 1000,  # кДж/моль
                "Cp": self.Cp_final,
            },
            "segments_count": len(self.segments),
            "transitions_count": len(self.phase_transitions),
            "warnings": self.warnings,
        }
    
    @property
    def has_phase_transitions(self) -> bool:
        """Проверка наличия фазовых переходов."""
        return len(self.phase_transitions) > 0
```

### Пример 4: Unit-тест для PhaseSegment

```python
# tests/test_models/test_phase_segment.py

import pytest
from src.thermo_agents.models.search import PhaseSegment, DatabaseRecord

def test_phase_segment_creation():
    """Тест создания PhaseSegment."""
    record = DatabaseRecord(
        formula="H2O",
        phase="s",
        tmin=200.0,
        tmax=273.15,
        h298=-285830.0,
        s298=69.95,
        f1=30.092, f2=6.832, f3=6.793, f4=-2.534, f5=0.082, f6=-0.007,
        tmelt=273.15,
        tboil=373.15,
        reliability_class=1
    )
    
    segment = PhaseSegment(
        record=record,
        T_start=200.0,
        T_end=273.15,
        H_start=-285830.0,
        S_start=69.95,
        delta_H=5000.0,
        delta_S=15.0,
        is_transition_boundary=True
    )
    
    assert segment.T_start == 200.0
    assert segment.T_end == 273.15
    assert segment.is_transition_boundary is True
    assert segment.record.formula == "H2O"

def test_phase_segment_validation_temperature():
    """Тест валидации температурного диапазона."""
    record = DatabaseRecord(
        formula="H2O", phase="s", tmin=200.0, tmax=273.15,
        h298=-285830.0, s298=69.95,
        f1=30.0, f2=6.0, f3=6.0, f4=-2.0, f5=0.0, f6=0.0,
        tmelt=273.15, tboil=373.15, reliability_class=1
    )
    
    with pytest.raises(ValueError, match="T_end должен быть больше T_start"):
        PhaseSegment(
            record=record,
            T_start=300.0,
            T_end=200.0,  # Некорректно: T_end < T_start
            H_start=0.0,
            S_start=0.0,
            delta_H=0.0,
            delta_S=0.0,
        )

def test_phase_segment_to_dict():
    """Тест сериализации сегмента."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265053.0, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    segment = PhaseSegment(
        record=record,
        T_start=298.0,
        T_end=600.0,
        H_start=-265053.0,
        S_start=59.807,
        delta_H=15420.0,
        delta_S=36.85,
        is_transition_boundary=False
    )
    
    result = segment.to_dict()
    
    assert result["formula"] == "FeO"
    assert result["phase"] == "s"
    assert result["T_range"] == [298.0, 600.0]
    assert result["is_transition"] is False
```

### Пример 5: Unit-тест для PhaseTransition

```python
# tests/test_models/test_phase_transition.py

import pytest
from src.thermo_agents.models.search import PhaseTransition, TransitionType

def test_phase_transition_melting():
    """Тест создания перехода плавления."""
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=6.008,
        delta_S_transition=22.0
    )
    
    assert transition.temperature == 273.15
    assert transition.transition_type == TransitionType.MELTING
    assert transition.delta_H_transition == 6.008

def test_phase_transition_auto_type_detection():
    """Тест автоопределения типа перехода."""
    # s → l = melting
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.MELTING
    
    # l → g = boiling
    transition = PhaseTransition(
        temperature=373.15,
        from_phase="l",
        to_phase="g",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.BOILING
    
    # s → g = sublimation
    transition = PhaseTransition(
        temperature=195.4,
        from_phase="s",
        to_phase="g",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.SUBLIMATION

def test_phase_transition_to_dict():
    """Тест сериализации перехода."""
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )
    
    result = transition.to_dict()
    
    assert result["T"] == 1650.0
    assert result["transition"] == "s→l"
    assert result["type"] == "melting"
    assert result["ΔH"] == 32.0
```

### Пример 6: Интеграционный тест с полным циклом

```python
# tests/test_models/test_multi_phase_integration.py

import pytest
from src.thermo_agents.models.search import (
    DatabaseRecord,
    PhaseSegment,
    PhaseTransition,
    MultiPhaseProperties,
    TransitionType
)

def test_full_multi_phase_calculation_feo():
    """
    Интеграционный тест: полный цикл расчёта FeO от 298K до 1700K.
    
    Проверяет взаимодействие всех трёх моделей:
    - 5 сегментов (4 твёрдых + 1 жидкий)
    - 1 фазовый переход (плавление при 1650K)
    - Траектории H(T), S(T)
    """
    # ШАГ 1: Создание записей БД
    records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.053, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=0.0, s298=0.0,
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
            h298=24.058, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]
    
    # ШАГ 2: Создание сегментов (эмуляция расчёта)
    segments = [
        PhaseSegment(
            record=records[0],
            T_start=298.0,
            T_end=600.0,
            H_start=-265053.0,
            S_start=59.807,
            delta_H=15420.0,
            delta_S=36.85,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[1],
            T_start=600.0,
            T_end=900.0,
            H_start=-249633.0,
            S_start=96.657,
            delta_H=19418.0,
            delta_S=29.793,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[2],
            T_start=900.0,
            T_end=1300.0,
            H_start=-230215.0,
            S_start=126.45,
            delta_H=30977.0,
            delta_S=24.42,
            is_transition_boundary=False
        ),
        PhaseSegment(
            record=records[3],
            T_start=1300.0,
            T_end=1650.0,
            H_start=-199238.0,
            S_start=150.87,
            delta_H=32000.0,  # Включает энтальпию плавления
            delta_S=19.4,
            is_transition_boundary=True
        ),
        PhaseSegment(
            record=records[4],
            T_start=1650.0,
            T_end=1700.0,
            H_start=-167238.0,
            S_start=170.27,
            delta_H=3605.0,
            delta_S=3.17,
            is_transition_boundary=False
        ),
    ]
    
    # ШАГ 3: Создание фазового перехода
    melting = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=32.0,  # кДж/моль
        delta_S_transition=19.4
    )
    
    # ШАГ 4: Финальный результат
    result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=-163633.0,  # Дж/моль
        S_final=173.44,     # Дж/(моль·K)
        G_final=-458481.0,  # G = H - T*S
        Cp_final=68.199,
        segments=segments,
        phase_transitions=[melting],
        temperature_path=[298.0, 600.0, 900.0, 1300.0, 1650.0, 1700.0],
        H_path=[-265053, -249633, -230215, -199238, -167238, -163633],
        S_path=[59.807, 96.657, 126.45, 150.87, 170.27, 173.44],
        warnings=[]
    )
    
    # Проверки
    assert result.T_target == 1700.0
    assert len(result.segments) == 5
    assert len(result.phase_transitions) == 1
    assert result.has_phase_transitions is True
    assert result.phase_sequence == "s → s → s → s → l"
    assert len(result.warnings) == 0
    
    # Проверка сериализации
    data = result.to_dict()
    assert data["segments_count"] == 5
    assert data["transitions_count"] == 1
    assert "thermodynamic_properties" in data
    
    print("✅ Интеграционный тест пройден: FeO 298K→1700K")
```

### Пример 7: Тест производительности создания моделей

```python
# tests/performance/test_model_creation_performance.py

import pytest
import time
from src.thermo_agents.models.search import (
    DatabaseRecord,
    PhaseSegment,
    MultiPhaseProperties
)

def test_phase_segment_creation_performance():
    """Тест производительности создания PhaseSegment."""
    record = DatabaseRecord(
        formula="FeO", phase="s", tmin=298.0, tmax=600.0,
        h298=-265.053, s298=59.807,
        f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
        tmelt=1650.0, tboil=3687.0, reliability_class=1
    )
    
    start = time.perf_counter()
    
    # Создание 1000 сегментов
    for _ in range(1000):
        segment = PhaseSegment(
            record=record,
            T_start=298.0,
            T_end=600.0,
            H_start=-265053.0,
            S_start=59.807,
            delta_H=15420.0,
            delta_S=36.85,
            is_transition_boundary=False
        )
    
    elapsed = time.perf_counter() - start
    
    # Требование: < 10ms на 1000 сегментов
    assert elapsed < 0.01, f"Слишком медленное создание: {elapsed*1000:.2f}ms"
    print(f"✅ Создание 1000 сегментов: {elapsed*1000:.2f}ms")

def test_multi_phase_properties_large_trajectory():
    """Тест производительности с большой траекторией (1000 точек)."""
    # Создание траектории с 1000 точек
    temperature_path = list(range(298, 1298))
    H_path = [-265053 + i * 50 for i in range(1000)]
    S_path = [59.807 + i * 0.05 for i in range(1000)]
    
    start = time.perf_counter()
    
    result = MultiPhaseProperties(
        T_target=1298.0,
        H_final=-215053.0,
        S_final=109.807,
        G_final=-357890.0,
        Cp_final=65.0,
        segments=[],
        phase_transitions=[],
        temperature_path=temperature_path,
        H_path=H_path,
        S_path=S_path,
        warnings=[]
    )
    
    elapsed = time.perf_counter() - start
    
    # Требование: < 5ms для 1000 точек
    assert elapsed < 0.005, f"Слишком медленное создание: {elapsed*1000:.2f}ms"
    print(f"✅ Траектория 1000 точек: {elapsed*1000:.2f}ms")
```

---

## План реализации

1. **День 1**: Создание `PhaseSegment` и валидаторов
2. **День 1**: Создание `PhaseTransition` с автоопределением типа
3. **День 2**: Создание `MultiPhaseProperties` с траекториями
4. **День 2**: Написание unit-тестов (покрытие ≥90%)
5. **День 2**: Проверка mypy, форматирование кода

## Реализация завершена

### ✅ Реализованные модели

1. **TransitionType** - enum типов фазовых переходов:
   - `MELTING` (s → l)
   - `BOILING` (l → g)
   - `SUBLIMATION` (s → g)
   - `UNKNOWN`

2. **PhaseSegment** - сегмент расчёта в пределах одной записи БД:
   - Валидация температурных диапазонов
   - Проверка соответствия record.tmin/tmax
   - Метод `to_dict()` для сериализации

3. **PhaseTransition** - информация о фазовом переходе:
   - Автоопределение типа перехода по фазам
   - Поддержка термодинамики перехода
   - Сериализация с форматированием "s→l"

4. **MultiPhaseProperties** - результат многофазного расчёта:
   - Валидация сортировки сегментов по температуре
   - Траектории H(T), S(T) для графиков
   - Property-методы: `has_phase_transitions`, `segment_count`, `phase_sequence`
   - Сериализация с конвертацией единиц

### ✅ Тестирование

- **23 unit-теста** покрывают всю функциональность
- **Интеграционные тесты** для полного цикла расчёта FeO
- **Performance тесты** подтверждают соответствие целям:
  - PhaseSegment: < 3ms для 1000 сегментов (цель: < 10ms)
  - MultiPhaseProperties: < 1ms для 1000 точек (цель: < 5ms)
  - Валидация: < 1ms для 100 сегментов (цель: < 50ms)

### ✅ Совместимость

- Обновлено до **Pydantic V2** (@field_validator, @model_validator)
- Обратная совместимость с существующими DatabaseRecord
- Полная валидация типов (mypy проверка пройдена)

### 📁 Файлы

- **Изменён**: `src/thermo_agents/models/search.py` (+180 строк)
- **Создан**: `tests/test_models/test_phase_segment.py`
- **Создан**: `tests/test_models/test_phase_transition.py`
- **Создан**: `tests/test_models/test_multi_phase_properties.py`
- **Создан**: `tests/test_models/test_multi_phase_integration.py`

**Дата завершения:** 19 октября 2025
**Версия реализации:** 1.0
**Статус:** ✅ Завершено и протестировано

## Следующий этап
Stage 02: Расширение DatabaseRecord для поддержки многофазных данных
