# Этап 3: Создание форматтеров

**Статус:** Не начат  
**Приоритет:** Средний  
**Зависимости:** Этап 2

---

## Цель

Создать два специализированных форматтера для вывода результатов:
- `CompoundDataFormatter` — для запросов типа `compound_data`
- `ReactionCalculationFormatter` — для запросов типа `reaction_calculation`

---

## Основные задачи

### 3.1. CompoundDataFormatter

**Файл:** `src/thermo_agents/formatting/compound_data_formatter.py` (новый модуль)

**Функционал:**
- Форматирование базовых свойств вещества
- Генерация таблицы термодинамических свойств (Cp, H, S, G) по температуре
- Использование библиотеки `tabulate` для табличного вывода
- Обработка случаев "вещество не найдено"

**Методы:**
- `format_response(result, T_min, T_max, step_k)` — основной метод
- `_format_basic_properties(record)` — базовые свойства
- `_format_thermodynamic_table(table)` — таблица с использованием tabulate

### 3.2. ReactionCalculationFormatter

**Файл:** `src/thermo_agents/formatting/reaction_calculation_formatter.py` (новый модуль)

**Функционал:**
- Форматирование уравнения реакции с Unicode символами (→, ⇄, подстрочные индексы)
- Вывод описания метода расчёта с математическими формулами
- Компактное представление данных веществ
- Результаты расчёта ΔH, ΔS, ΔG по температурам
- Заключение о термодинамической выгодности реакции

**Методы:**
- `format_response(params, reactants, products, step_k)` — основной метод
- `_format_equation(equation)` — форматирование с Unicode
- `_format_calculation_method()` — описание метода
- `_format_substances_data(reactants, products)` — компактные данные веществ
- `_format_results(reactants, products, T_values)` — результаты расчёта

### 3.3. Тестирование форматтеров

**Файлы:** 
- `tests/test_compound_data_formatter.py` (новый)
- `tests/test_reaction_calculation_formatter.py` (новый)

**Тесты:**
- Корректность форматирования таблиц
- Unicode-преобразования для формул
- Обработка граничных случаев
- Snapshot-тесты для проверки полного вывода

---

## Критерии приёмки

- ✅ Оба форматтера реализованы и документированы
- ✅ Вывод соответствует спецификации из `output_spec.md`
- ✅ Unicode-символы корректно отображаются
- ✅ Таблицы форматируются с использованием `tabulate`
- ✅ Все тесты проходят
- ✅ Примеры вывода добавлены в документацию

---

## Детальные подзадачи

### 3.1.1. Реализация CompoundDataFormatter.__init__()

**Файл:** `src/thermo_agents/formatting/compound_data_formatter.py`

**Код:**
```python
from tabulate import tabulate
from src.thermo_agents.calculations.thermodynamic_calculator import (
    ThermodynamicCalculator,
    ThermodynamicTable
)

class CompoundDataFormatter:
    """Форматтер для вывода табличных данных веществ."""
    
    def __init__(self, calculator: ThermodynamicCalculator):
        self.calculator = calculator
```

### 3.1.2. Реализация format_response()

**Основной метод:**
```python
def format_response(
    self,
    result: CompoundSearchResult,
    T_min: float,
    T_max: float,
    step_k: int = 100
) -> str:
    """Генерация полного ответа для запроса данных по веществу."""
    if not result.records_found:
        return self._format_not_found_response(result.formula)
    
    record = result.records_found[0]
    
    lines = []
    lines.append(f"📊 Термодинамические данные: {record.Formula}")
    lines.append("")
    lines.append("Базовые свойства:")
    lines.append(self._format_basic_properties(record))
    lines.append("")
    
    try:
        table = self.calculator.generate_table(record, T_min, T_max, step_k)
        lines.append("Термодинамические свойства по температуре:")
        lines.append(self._format_thermodynamic_table(table))
    except ValueError as e:
        lines.append(f"⚠️ Ошибка генерации таблицы: {e}")
    
    lines.append("")
    lines.append("Примечания:")
    lines.append(f"  - Шаг по температуре: {step_k} K")
    lines.append("  - Все значения рассчитаны с использованием уравнений Шомейта")
    
    return "\n".join(lines)
```

### 3.1.3. Форматирование базовых свойств

**Метод:**
```python
def _format_basic_properties(self, record: DatabaseRecord) -> str:
    """Форматирование базовых свойств вещества."""
    props = []
    
    props.append(f"  Формула: {record.Formula}")
    if record.Name:
        props.append(f"  Название: {record.Name}")
    
    phase_map = {'s': 'solid', 'l': 'liquid', 'g': 'gas', 'aq': 'aqueous'}
    phase_desc = phase_map.get(record.Phase, record.Phase)
    props.append(f"  Фаза: {record.Phase} ({phase_desc})")
    
    props.append(f"  T_диапазон: {record.Tmin or 'N/A'}-{record.Tmax or 'N/A'} K")
    
    if record.H298 is not None:
        props.append(f"  H298: {record.H298} кДж/моль")
    if record.S298 is not None:
        props.append(f"  S298: {record.S298} Дж/(моль·K)")
    
    cp_coeffs = [f"f{i}={getattr(record, f'f{i}', 0) or 0:.3f}" for i in range(1, 7)]
    props.append(f"  Cp_коэффициенты: {', '.join(cp_coeffs)}")
    
    return "\n".join(props)
```

### 3.1.4. Форматирование таблицы с tabulate

**Метод:**
```python
def _format_thermodynamic_table(self, table: ThermodynamicTable) -> str:
    """Форматирование таблицы с использованием tabulate."""
    headers = [
        "T(K)",
        "Cp\nДж/(моль·K)",
        "H\nкДж/моль",
        "S\nДж/(моль·K)",
        "G\nкДж/моль"
    ]
    
    table_data = []
    for prop in table.properties:
        row = [
            f"{prop.T:.0f}",
            f"{prop.Cp:.2f}",
            f"{prop.H / 1000:.2f}",
            f"{prop.S:.2f}",
            f"{prop.G / 1000:.2f}"
        ]
        table_data.append(row)
    
    return tabulate(table_data, headers=headers, tablefmt="grid")
```

### 3.2.1. Реализация ReactionCalculationFormatter

**Файл:** `src/thermo_agents/formatting/reaction_calculation_formatter.py`

**Основная структура:**
```python
class ReactionCalculationFormatter:
    """Форматтер для вывода расчётов термодинамики реакций."""
    
    def __init__(self, calculator: ThermodynamicCalculator):
        self.calculator = calculator
    
    def format_response(
        self,
        params: ExtractedReactionParameters,
        reactants: List[CompoundSearchResult],
        products: List[CompoundSearchResult],
        step_k: int = 100
    ) -> str:
        """Генерация полного ответа для расчёта реакции."""
        # ...
```

### 3.2.2. Форматирование уравнения с Unicode

**Метод:**
```python
def _format_equation(self, equation: str) -> str:
    """
    Форматирование уравнения с Unicode символами.
    
    Замены:
    - -> → →
    - Цифры в формулах → подстрочные индексы (H2O → H₂O)
    """
    formatted = equation.replace("->", "→").replace("=", "→")
    
    subscript_map = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'
    }
    
    result = []
    prev_char = ''
    for char in formatted:
        if char.isdigit() and (prev_char.isalpha() or prev_char == ')'):
            result.append(subscript_map.get(char, char))
        else:
            result.append(char)
        prev_char = char
    
    return ''.join(result)
```

### 3.2.3. Вывод метода расчёта

**Метод:**
```python
def _format_calculation_method(self) -> str:
    """Описание метода расчёта с математическими формулами."""
    return """Метод расчёта:

1. Энтальпия реакции: ΔH°(T) = ΣH°_продукты - ΣH°_реагенты
2. Энтропия реакции: ΔS°(T) = ΣS°_продукты - ΣS°_реагенты  
3. Энергия Гиббса: ΔG°(T) = ΔH°(T) - T·ΔS°(T)

Где:
  H°(T) = H°₂₉₈ + ∫₂₉₈ᵀ Cp(T)dT
  S°(T) = S°₂₉₈ + ∫₂₉₈ᵀ [Cp(T)/T]dT
  Cp(T) = f₁ + f₂T/1000 + f₃T⁻²·10⁵ + f₄T²/10⁶ + f₅T⁻³·10³ + f₆T³·10⁻⁹"""
```

### 3.2.4. Компактное форматирование данных веществ

**Метод:**
```python
def _format_substances_data(
    self,
    reactants: List[CompoundSearchResult],
    products: List[CompoundSearchResult]
) -> str:
    """Компактное представление данных веществ."""
    lines = []
    
    for result in reactants + products:
        if not result.records_found:
            lines.append(f"{result.formula} — ❌ НЕ НАЙДЕНО")
            continue
        
        record = result.records_found[0]
        name = record.Name or "Unknown"
        
        lines.append(f"{record.Formula} — {name}")
        lines.append(f"  Фаза: {record.Phase} | T_применимости: {record.Tmin}-{record.Tmax} K")
        lines.append(f"  H298: {record.H298} кДж/моль | S298: {record.S298} Дж/(моль·K)")
        
        cp_coeffs = [f"{getattr(record, f'f{i}', 0) or 0:.3f}" for i in range(1, 7)]
        lines.append(f"  Cp: [{', '.join(cp_coeffs)}]")
        lines.append("")
    
    return "\n".join(lines)
```

### 3.2.5. Вывод результатов расчёта

**Метод:**
```python
def _format_results(
    self,
    reactants: List[Tuple[DatabaseRecord, int]],
    products: List[Tuple[DatabaseRecord, int]],
    T_values: np.ndarray
) -> str:
    """Форматирование результатов расчёта ΔH, ΔS, ΔG."""
    lines = []
    
    # Расчёт количества молей продукта для нормировки
    product_moles = sum(nu for _, nu in products)
    
    for T in T_values:
        delta_H, delta_S, delta_G = self.calculator.calculate_reaction_properties(
            reactants, products, T
        )
        
        # Нормировка на моль продукта
        delta_H_norm = delta_H / 1000 / product_moles
        delta_S_norm = delta_S / product_moles
        delta_G_norm = delta_G / 1000 / product_moles
        
        lines.append(
            f"{T:.0f} K: ΔH° = {delta_H_norm:.2f} кДж/моль | "
            f"ΔS° = {delta_S_norm:.2f} Дж/(К·моль) | "
            f"ΔG° = {delta_G_norm:.2f} кДж/моль"
        )
    
    return "\n".join(lines)
```

### 3.3.1. Тесты CompoundDataFormatter

**Файл:** `tests/test_compound_data_formatter.py`

**Тесты:**
```python
def test_format_basic_properties(formatter, h2o_record):
    """Проверка форматирования базовых свойств"""
    output = formatter._format_basic_properties(h2o_record)
    
    assert "Формула: H2O" in output
    assert "Фаза: g (gas)" in output
    assert "H298:" in output

def test_format_thermodynamic_table(formatter, h2o_table):
    """Проверка табличного вывода"""
    output = formatter._format_thermodynamic_table(h2o_table)
    
    assert "T(K)" in output
    assert "Cp" in output
    assert "┌" in output  # Проверка границ таблицы (grid format)
```

### 3.3.2. Snapshot-тесты

**Использование pytest-snapshot:**
```python
def test_full_output_snapshot(formatter, snapshot):
    """Snapshot-тест для полного вывода"""
    result = create_h2o_search_result()
    output = formatter.format_response(result, 300, 600, 100)
    
    snapshot.assert_match(output, "h2o_compound_data.txt")
```

---

## Unicode символы

### Карта символов
- → (U+2192) — стрелка реакции
- ⇄ (U+21C4) — обратимая реакция
- Δ (U+0394) — дельта (изменение)
- ° (U+00B0) — градус (стандартные условия)
- ∫ (U+222B) — интеграл
- ₀₁₂₃₄ (U+2080-2089) — подстрочные индексы

---

