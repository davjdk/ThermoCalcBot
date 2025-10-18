# Этап 2: Создание ThermodynamicCalculator

**Статус:** Не начат  
**Приоритет:** Высокий  
**Зависимости:** Этап 1

---

## Цель

Создать детерминированный калькулятор термодинамических свойств на основе формул Шомейта. Перенести логику из Jupyter notebook `docs/сhlorination_of_tungsten.ipynb` в производственный код.

---

## Основные задачи

### 2.1. Создание структур данных

**Файл:** `src/thermo_agents/calculations/thermodynamic_calculator.py` (новый модуль)

**Компоненты:**
- `ThermodynamicProperties` — свойства при одной температуре (T, Cp, H, S, G)
- `ThermodynamicTable` — таблица свойств по диапазону температур

### 2.2. Реализация ThermodynamicCalculator

**Методы:**
- `calculate_cp(record, T)` — расчёт теплоёмкости по формуле Шомейта
- `calculate_properties(record, T)` — расчёт H, S, G при температуре T
- `generate_table(record, T_min, T_max, step_k)` — генерация таблицы по диапазону
- `calculate_reaction_properties(reactants, products, T)` — расчёт ΔH, ΔS, ΔG реакции

### 2.3. Численное интегрирование

**Реализация:**
- Метод трапеций (NumPy `trapz`) для расчёта ∫Cp(T)dT и ∫Cp(T)/T dT
- 400 точек интегрирования (по умолчанию)
- Валидация температурного диапазона (Tmin-Tmax из базы)

### 2.4. Модульные тесты

**Файл:** `tests/test_thermodynamic_calculator.py` (новый)

**Тесты:**
- Расчёт Cp для известных веществ (сравнение с notebook)
- Расчёт H, S, G при разных температурах
- Генерация таблиц с разными шагами
- Расчёт реакций (проверка на известных примерах)
- Обработка граничных случаев (T вне диапазона)

---

## Критерии приёмки

- ✅ Класс `ThermodynamicCalculator` реализован и документирован
- ✅ Все методы проходят unit-тесты
- ✅ Результаты совпадают с расчётами из notebook (погрешность < 0.1%)
- ✅ Обработка ошибок для температур вне диапазона
- ✅ Производительность: генерация таблицы 100 точек < 100ms

---

## Детальные подзадачи

### 2.1.1. Создание dataclass для ThermodynamicProperties

**Файл:** `src/thermo_agents/calculations/thermodynamic_calculator.py`

**Код:**
```python
from dataclasses import dataclass

@dataclass
class ThermodynamicProperties:
    """Термодинамические свойства при заданной температуре."""
    T: float  # Температура, K
    Cp: float  # Теплоёмкость, Дж/(моль·K)
    H: float  # Энтальпия, Дж/моль
    S: float  # Энтропия, Дж/(моль·K)
    G: float  # Энергия Гиббса, Дж/моль
```

**Мотивация:**
- Явная типизация результатов расчётов
- Удобство работы с данными (именованные поля вместо кортежей)
- Автоматическая генерация `__repr__` для отладки

### 2.1.2. Создание dataclass для ThermodynamicTable

**Код:**
```python
@dataclass
class ThermodynamicTable:
    """Таблица термодинамических свойств по диапазону температур."""
    formula: str
    phase: str
    temperature_range: Tuple[float, float]
    properties: List[ThermodynamicProperties]
    
    def to_dict(self) -> dict:
        """Преобразование в словарь для форматтера."""
        return {
            'formula': self.formula,
            'phase': self.phase,
            'T_range': self.temperature_range,
            'data': [
                {
                    'T': prop.T,
                    'Cp': prop.Cp,
                    'H': prop.H / 1000,  # Дж → кДж
                    'S': prop.S,
                    'G': prop.G / 1000   # Дж → кДж
                }
                for prop in self.properties
            ]
        }
```

### 2.2.1. Реализация calculate_cp()

**Метод:**
```python
def calculate_cp(self, record: DatabaseRecord, T: float) -> float:
    """
    Расчёт теплоёмкости Cp(T) по формуле Шомейта.
    
    Формула:
    Cp(T) = f1 + f2*T/1000 + f3*T^(-2)*10^5 + 
            f4*T^2/10^6 + f5*T^(-3)*10^3 + f6*T^3*10^(-9)
    
    Args:
        record: Запись из базы данных с коэффициентами f1-f6
        T: Температура, K
    
    Returns:
        Cp в Дж/(моль·K)
    """
    T = float(T)
    f1 = record.f1 or 0.0
    f2 = record.f2 or 0.0
    f3 = record.f3 or 0.0
    f4 = record.f4 or 0.0
    f5 = record.f5 or 0.0
    f6 = record.f6 or 0.0
    
    return (
        f1
        + f2 * T / 1000.0
        + f3 * T**(-2) * 100_000.0
        + f4 * T**2 / 1_000_000.0
        + f5 * T**(-3) * 1_000.0
        + f6 * T**3 * 1e-9
    )
```

**Источник:** Ячейка notebook с функцией `cp_function_from_row`

### 2.2.2. Реализация численного интегрирования

**Метод calculate_properties():**
```python
def calculate_properties(
    self, 
    record: DatabaseRecord, 
    T: float
) -> ThermodynamicProperties:
    """
    Расчёт всех термодинамических свойств при температуре T.
    
    Формулы:
    - H(T) = H298 + ∫[298→T] Cp(T) dT
    - S(T) = S298 + ∫[298→T] Cp(T)/T dT  
    - G(T) = H(T) - T*S(T)
    """
    # Валидация температурного диапазона
    if record.Tmin and T < record.Tmin:
        raise ValueError(
            f"T={T}K ниже минимальной температуры {record.Tmin}K "
            f"для {record.Formula} ({record.Phase})"
        )
    if record.Tmax and T > record.Tmax:
        raise ValueError(
            f"T={T}K выше максимальной температуры {record.Tmax}K "
            f"для {record.Formula} ({record.Phase})"
        )
    
    # Базовые значения при 298.15K
    H298 = (record.H298 or 0.0) * 1000.0  # кДж/моль → Дж/моль
    S298 = record.S298 or 0.0  # Дж/(моль·K)
    
    # Текущая теплоёмкость
    Cp = self.calculate_cp(record, T)
    
    # Если T ≈ 298.15K, интегрирование не требуется
    if abs(T - self.T_REF) < 1e-9:
        H = H298
        S = S298
        G = H - T * S
        return ThermodynamicProperties(T=T, Cp=Cp, H=H, S=S, G=G)
    
    # Численное интегрирование
    T_grid = np.linspace(self.T_REF, T, self.num_integration_points)
    Cp_grid = np.array([self.calculate_cp(record, t) for t in T_grid])
    
    # ΔH = ∫ Cp(T) dT
    delta_H = np.trapz(Cp_grid, T_grid)
    
    # ΔS = ∫ Cp(T)/T dT
    delta_S = np.trapz(Cp_grid / T_grid, T_grid)
    
    # Финальные значения
    H = H298 + delta_H
    S = S298 + delta_S
    G = H - T * S
    
    return ThermodynamicProperties(T=T, Cp=Cp, H=H, S=S, G=G)
```

### 2.2.3. Реализация generate_table()

**Метод:**
```python
def generate_table(
    self,
    record: DatabaseRecord,
    T_min: float,
    T_max: float,
    step_k: int = 100
) -> ThermodynamicTable:
    """
    Генерация таблицы термодинамических свойств.
    
    Args:
        record: Запись из базы данных
        T_min: Минимальная температура, K
        T_max: Максимальная температура, K
        step_k: Шаг по температуре, K (25-250)
    
    Returns:
        ThermodynamicTable с рассчитанными свойствами
    """
    if not (25 <= step_k <= 250):
        raise ValueError(f"Шаг должен быть в диапазоне 25-250K")
    
    # Ограничение диапазона пределами Tmin-Tmax записи
    effective_T_min = max(T_min, record.Tmin or T_min)
    effective_T_max = min(T_max, record.Tmax or T_max)
    
    # Округление T_min вверх до ближайшего кратного step_k
    T_start = int(np.ceil(effective_T_min / step_k) * step_k)
    
    # Генерация сетки температур
    T_values = np.arange(T_start, effective_T_max + 1, step_k)
    
    # Расчёт свойств для каждой температуры
    properties = []
    for T in T_values:
        try:
            props = self.calculate_properties(record, T)
            properties.append(props)
        except ValueError:
            # Пропуск температур вне диапазона
            continue
    
    return ThermodynamicTable(
        formula=record.Formula,
        phase=record.Phase,
        temperature_range=(effective_T_min, effective_T_max),
        properties=properties
    )
```

### 2.2.4. Реализация calculate_reaction_properties()

**Метод для расчёта реакций:**
```python
def calculate_reaction_properties(
    self,
    reactants: List[Tuple[DatabaseRecord, int]],  # [(record, stoich), ...]
    products: List[Tuple[DatabaseRecord, int]],
    T: float
) -> Tuple[float, float, float]:
    """
    Расчёт ΔH, ΔS, ΔG реакции при заданной температуре.
    
    Формулы:
    - ΔH°(T) = Σ(νᵢ * Hᵢ(T))_products - Σ(νⱼ * Hⱼ(T))_reactants
    - ΔS°(T) = Σ(νᵢ * Sᵢ(T))_products - Σ(νⱼ * Sⱼ(T))_reactants
    - ΔG°(T) = ΔH°(T) - T*ΔS°(T)
    
    Returns:
        (ΔH, ΔS, ΔG) в Дж/моль, Дж/(моль·K), Дж/моль
    """
    delta_H = 0.0
    delta_S = 0.0
    
    # Вклад продуктов (положительный)
    for record, nu in products:
        props = self.calculate_properties(record, T)
        delta_H += nu * props.H
        delta_S += nu * props.S
    
    # Вклад реагентов (отрицательный)
    for record, nu in reactants:
        props = self.calculate_properties(record, T)
        delta_H -= nu * props.H
        delta_S -= nu * props.S
    
    # Энергия Гиббса
    delta_G = delta_H - T * delta_S
    
    return (delta_H, delta_S, delta_G)
```

### 2.3.1. Векторизация для оптимизации

**Опциональная оптимизация:**
```python
def generate_table_vectorized(
    self,
    record: DatabaseRecord,
    T_values: np.ndarray
) -> ThermodynamicTable:
    """
    Векторизованная генерация таблицы (~5x быстрее).
    
    Использует NumPy для параллельных вычислений Cp(T).
    """
    # Векторный расчёт Cp для всех T одновременно
    T = T_values
    f1, f2, f3, f4, f5, f6 = [
        record.f1 or 0.0,
        record.f2 or 0.0,
        record.f3 or 0.0,
        record.f4 or 0.0,
        record.f5 or 0.0,
        record.f6 or 0.0
    ]
    
    Cp_grid = (
        f1 
        + f2 * T / 1000.0 
        + f3 * T**(-2) * 100_000.0 
        + f4 * T**2 / 1_000_000.0
        + f5 * T**(-3) * 1_000.0
        + f6 * T**3 * 1e-9
    )
    
    # Векторное интегрирование для H и S
    # ...
```

### 2.4.1. Тесты расчёта Cp

**Файл:** `tests/test_thermodynamic_calculator.py`

**Тест:**
```python
import pytest
from src.thermo_agents.calculations.thermodynamic_calculator import (
    ThermodynamicCalculator
)

class TestThermodynamicCalculator:
    
    @pytest.fixture
    def calculator(self):
        return ThermodynamicCalculator()
    
    def test_calculate_cp_h2o_at_500k(self, calculator):
        """Проверка Cp(H2O, 500K) по данным из notebook"""
        # record_H2O с коэффициентами из базы
        record = get_h2o_record()  # Mock
        
        Cp = calculator.calculate_cp(record, 500.0)
        
        # Ожидаемое значение из notebook
        expected_Cp = 36.32  # Дж/(моль·K)
        assert abs(Cp - expected_Cp) < 0.01  # Погрешность < 0.01
```

### 2.4.2. Тесты интегрирования

**Тест H(T) и S(T):**
```python
def test_calculate_properties_h2o_at_400k(self, calculator):
    """Проверка H, S, G для H2O при 400K"""
    record = get_h2o_record()
    
    props = calculator.calculate_properties(record, 400.0)
    
    # Ожидаемые значения из notebook
    assert abs(props.H / 1000 - (-238.36)) < 0.1  # кДж/моль
    assert abs(props.S - 198.79) < 0.1  # Дж/(моль·K)
    assert abs(props.G / 1000 - (-317.88)) < 0.1  # кДж/моль
```

### 2.4.3. Тесты граничных случаев

```python
def test_temperature_below_tmin_raises_error(self, calculator):
    """T < Tmin → ValueError"""
    record = get_h2o_record()  # Tmin=298K
    
    with pytest.raises(ValueError, match="ниже минимальной температуры"):
        calculator.calculate_properties(record, 200.0)

def test_temperature_above_tmax_raises_error(self, calculator):
    """T > Tmax → ValueError"""
    record = get_h2o_record()  # Tmax=1500K
    
    with pytest.raises(ValueError, match="выше максимальной температуры"):
        calculator.calculate_properties(record, 2000.0)
```

### 2.4.4. Тесты реакций

```python
def test_calculate_reaction_w_chlorination(self, calculator):
    """Проверка реакции 2W + 4Cl2 + O2 → 2WOCl4 при 600K"""
    # Получение записей
    W = get_w_record()
    Cl2 = get_cl2_record()
    O2 = get_o2_record()
    WOCl4 = get_wocl4_record()
    
    delta_H, delta_S, delta_G = calculator.calculate_reaction_properties(
        reactants=[(W, 2), (Cl2, 4), (O2, 1)],
        products=[(WOCl4, 2)],
        T=600.0
    )
    
    # Нормировка на моль продукта
    delta_H_per_mol = delta_H / 1000 / 2  # кДж/моль
    
    # Ожидаемое из notebook
    expected_delta_H = -523.45  # кДж/моль
    assert abs(delta_H_per_mol - expected_delta_H) < 1.0
```

---

## Миграция кода из notebook

### Шаг 1: Извлечение функций
- Скопировать `cp_function_from_row` → `calculate_cp`
- Скопировать логику интегрирования из `H_S_G_from_row` → `calculate_properties`

### Шаг 2: Адаптация под DatabaseRecord
- Заменить работу с pandas DataFrame на Pydantic модели
- Обновить названия полей (H298, S298, f1-f6)

### Шаг 3: Добавление обработки ошибок
- Валидация температурного диапазона
- Обработка None значений в коэффициентах

---

## Оптимизации производительности

### Кэширование интегралов
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def _cached_integration(
    self, 
    record_id: int,
    T: float
) -> Tuple[float, float]:
    """Кэш для (record_id, T) → (delta_H, delta_S)"""
    # ...
```

### Batch processing
```python
def calculate_properties_batch(
    self,
    record: DatabaseRecord,
    T_values: List[float]
) -> List[ThermodynamicProperties]:
    """Оптимизированный расчёт для массива температур"""
    # Векторизованные вычисления
    # ...
```

---

