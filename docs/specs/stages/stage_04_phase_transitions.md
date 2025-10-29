# Этап 4: Интеграция фазовых переходов

## Общая информация

- **Этап:** 4 из 6
- **Название:** Интеграция фазовых переходов
- **Статус:** Запланирован
- **Приоритет:** Высокий
- **Длительность (оценка):** 4-5 дней
- **Зависимости:** Этапы 1-3 (полные данные, сегменты, выбор записей)

## Проблема

После Этапов 1-3 система сможет работать с множественными записями и фазовыми сегментами, но не будет учитывать энтальпии фазовых переходов (ΔH_fusion, ΔH_vaporization), что критически важно для корректных термодинамических расчётов.

**Текущие ограничения:**
1. Расчёты H(T) не учитывают скачки энтальпии при переходах
2. Отсутствует учёт энтропии переходов (ΔS = ΔH/T)
3. Нет корректной обработки Gibbs free энергии через фазовые границы
4. Физическая некорректность расчётов при температурах переходов

**Пример проблемы с FeO:**
```
При T = 1650K (плавление):
H(1650K⁻, s) = -240.5 кДж/моль
H(1650K⁺, l) должна быть = H(1650K⁻, s) + ΔH_fusion

Текущая система: H(1650K⁺, l) = H(1650K⁻, s) ❌
Корректно: H(1650K⁺, l) = H(1650K⁻, s) + 31.5 кДж/моль ✓
```

## Цель этапа

Реализовать корректный учёт фазовых переходов в термодинамических расчётах, обеспечивая физическую корректность энтальпии, энтропии и энергии Гиббса через точки плавления и кипения.

## Задачи этапа

### 1. Расширение моделей фазовых переходов

**Файл:** `src/thermo_agents/models/search.py`

**Задачи:**
- Расширить `PhaseTransition` для хранения полных данных
- Добавить энтальпии переходов из базы данных
- Реализовать расчёт энтропии переходов
- Добавить валидацию данных переходов

```python
@dataclass
class PhaseTransition:
    transition_type: str  # 'melting', 'boiling', 'sublimation'
    temperature: float
    enthalpy_change: float  # ΔH в кДж/моль
    entropy_change: float   # ΔS = ΔH/T в Дж/(моль·K)
    from_phase: str
    to_phase: str
    reliability: float = 1.0  # Надёжность данных

    def __post_init__(self):
        if self.entropy_change == 0 and self.enthalpy_change != 0:
            self.entropy_change = (self.enthalpy_change * 1000) / self.temperature
```

### 2. Создание PhaseTransitionCalculator

**Файл:** `src/thermo_agents/calculations/phase_transition_calculator.py`

**Задачи:**
- Создать специализированный калькулятор для фазовых переходов
- Реализовать расчёт свойств в точках переходов
- Обеспечить корректную обработку скачков свойств
- Реализовать валидацию термодинамической согласованности

```python
@dataclass
class PhaseTransitionCalculator:
    def calculate_properties_at_transition(
        self,
        transition: PhaseTransition,
        h_before: float,
        s_before: float
    ) -> Tuple[float, float, float]  # H, S, G после перехода

    def validate_transition_thermodynamics(
        self,
        transition: PhaseTransition
    ) -> bool

    def calculate_transition_corrections(
        self,
        from_segment: PhaseSegment,
        to_segment: PhaseSegment,
        transition: PhaseTransition,
        temperature: float
    ) -> Dict[str, float]
```

### 3. Обновление ThermodynamicCalculator

**Файл:** `src/thermo_agents/calculations/thermodynamic_calculator.py`

**Задачи:**
- Интегрировать учёт фазовых переходов в основные расчёты
- Реализовать автоматическое обнаружение точек перехода
- Обеспечить корректный расчёт свойств через границы фаз
- Реализовать кэширование результатов переходов

**Основные изменения:**
```python
class ThermodynamicCalculator:
    def calculate_properties_with_transitions(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> ThermodynamicProperties

    def calculate_table_with_transitions(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Tuple[float, float],
        num_points: int = 100
    ) -> ThermodynamicTable

    def _handle_phase_transition(
        self,
        transition: PhaseTransition,
        h_before: float,
        s_before: float
    ) -> Tuple[float, float]

    def _detect_transition_at_temperature(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature: float
    ) -> Optional[PhaseTransition]
```

### 4. Создание TransitionDataManager

**Файл:** `src/thermo_agents/calculations/transition_data_manager.py`

**Задачи:**
- Управлять данными фазовых переходов
- Извлекать энтальпии из базы данных
- Рассчитывать недостающие данные
- Кэшировать результаты для быстрого доступа

```python
@dataclass
class TransitionDataManager:
    def extract_transition_data(
        self,
        records: List[DatabaseRecord]
    ) -> List[PhaseTransition]

    def calculate_missing_enthalpies(
        self,
        records: List[DatabaseRecord]
    ) -> Dict[str, float]

    def validate_transition_consistency(
        self,
        transitions: List[PhaseTransition]
    ) -> List[str]  # Список предупреждений

    def cache_transition_data(
        self,
        formula: str,
        transitions: List[PhaseTransition]
    ) -> None
```

### 5. Интеграция в MultiPhaseReactionCalculator

**Файл:** `src/thermo_agents/calculations/reaction_calculator.py`

**Задачи:**
- Обновить для учёта фазовых переходов в реакциях
- Реализовать корректный расчёт ΔH, ΔS, ΔG через границы
- Обеспечить учёт разных фаз веществ в реакции
- Реализовать информирование о фазовых изменениях

```python
@dataclass
class MultiPhaseReactionCalculator:
    def calculate_reaction_with_transitions(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature: float
    ) -> ReactionProperties

    def detect_reaction_phase_changes(
        self,
        temperature_range: Tuple[float, float],
        all_compounds_data: List[MultiPhaseCompoundData]
    ) -> List[Tuple[float, str, str]]  # (T, compound, transition_type)

    def calculate_reaction_transition_effects(
        self,
        transition_temps: List[float],
        reaction_data: ReactionData
    ) -> Dict[float, Dict[str, float]]
```

## Логика учёта фазовых переходов

### Термодинамическая основа

1. **Энтальпия перехода:**
   ```
   H(T_trans⁺) = H(T_trans⁻) + ΔH_transition
   ```

2. **Энтропия перехода (при равновесии):**
   ```
   ΔS_transition = ΔH_transition / T_trans
   S(T_trans⁺) = S(T_trans⁻) + ΔS_transition
   ```

3. **Энергия Гиббса в точке перехода:**
   ```
   G(T_trans) = H(T_trans) - T_trans × S(T_trans)
   ```

### Алгоритм расчёта с переходами

```python
def calculate_properties_with_transitions(compound_data, temperature):
    # 1. Определить текущий сегмент
    segment = find_segment_for_temperature(compound_data, temperature)

    # 2. Проверить наличие перехода
    transition = detect_transition_at_temperature(compound_data, temperature)

    if transition is None:
        # Обычный расчёт в пределах фазы
        return calculate_properties_in_segment(segment, temperature)
    else:
        # Расчёт в точке перехода
        # Сначала рассчитать свойства до перехода
        h_before, s_before = calculate_properties_before_transition(segment, temperature)

        # Применить скачок свойств
        h_after = h_before + transition.enthalpy_change
        s_after = s_before + transition.entropy_change
        g_after = h_after - temperature * s_after

        return ThermodynamicProperties(
            temperature=temperature,
            enthalpy=h_after,
            entropy=s_after,
            gibbs_energy=g_after,
            phase=transition.to_phase
        )
```

### Источники данных о переходах

1. **Из базы данных:**
   - Поля `h_fusion`, `h_vaporization` если доступны
   - Температуры `tmelt`, `tboil`

2. **Расчёт из H₂₉₈ разных фаз:**
   ```python
   ΔH_fusion ≈ H₂₉₈(liquid) - H₂₉₈(solid)
   ```

3. **Эвристические значения:**
   ```python
   # Металлы: 2-10 кДж/моль
   # Соли: 20-50 кДж/моль
   # Молекулярные: 5-30 кДж/моль
   ```

### Пример для FeO

```
FeO фазовые переходы:
1. Плавление при T = 1650K, ΔH_fusion = 31.5 кДж/моль
2. Кипение при T = 3687K, ΔH_vaporization = 340.0 кДж/моль

Расчёт H(T):
- T = 1649K (твёрдая фаза): H = -240.5 кДж/моль
- T = 1650K (плавление): H = -240.5 + 31.5 = -209.0 кДж/моль
- T = 1651K (жидкая фаза): H = -209.0 + интеграл от 1650K

Аналогично для S(T) и G(T)
```

## Критерии завершения

### Функциональные критерии

1. **Расчёт переходов:**
   - [ ] Энтальпия корректно изменяется на ΔH в точках перехода
   - [ ] Энтропия корректно изменяется на ΔH/T в точках перехода
   - [ ] G(T) непрерывен в точках равновесия
   - [ ] Фаза корректно обновляется после перехода

2. **Данные переходов:**
   - [ ] Энтальпии извлекаются из базы данных когда доступны
   - [ ] Отсутствующие данные рассчитываются или оцениваются
   - [ ] Валидация проверяет термодинамическую согласованность

3. **Интеграция:**
   - [ ] `ThermodynamicCalculator` учитывает переходы
   - [ ] Реакционные расчёты корректно обрабатывают фазовые изменения
   - [ ] Таблицы свойств включают точки переходов

4. **Производительность:**
   - [ ] Учёт переходов не замедляет расчёты значительно
   - [ ] Кэширование переходов работает эффективно

### Технические критерии

1. **Качество кода:**
   - [ ] Все новые классы имеют полную документацию
   - [ ] Unit тесты покрывают все типы переходов
   - [ ] Интеграционные тесты проверяют реальные сценарии
   - [ ] Покрытие кода тестами ≥ 85%

2. **Надёжность:**
   - [ ] Корректная обработка отсутствующих данных
   - [ ] Валидация термодинамической согласованности
   - [ ] Информативные предупреждения о проблемах

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_phase_transition_calculator.py`

```python
class TestPhaseTransitionCalculator:
    def test_calculate_properties_at_transition(self)
    def test_validate_transition_thermodynamics(self)
    def test_calculate_transition_corrections(self)
    def test_handle_multiple_transitions(self)
    def test_edge_cases_thermodynamics(self)
```

**Файл:** `tests/unit/test_transition_data_manager.py`

```python
class TestTransitionDataManager:
    def test_extract_transition_data(self)
    def test_calculate_missing_enthalpies(self)
    def test_validate_transition_consistency(self)
    def test_cache_transition_data(self)
```

### Интеграционные тесты

**Файл:** `tests/integration/test_stage_04_phase_transitions.py`

```python
class TestStage4PhaseTransitions:
    async def test_feo_phase_transitions(self)
    async def test_water_phase_transitions(self)
    async def test_reaction_with_phase_changes(self)
    async def test_multiple_compounds_transitions(self)
    async def test_transition_thermodynamics_consistency(self)
    async def test_performance_with_transitions(self)
```

### Регрессионные тесты

```python
class TestStage4Regression:
    def test_single_phase_compatibility(self)
    def test_no_transition_data_handling(self)
    def test_backward_compatibility(self)
```

## Риски и митигации

### Риск 1: Отсутствие данных о переходах
- **Проблема:** Не для всех веществ есть ΔH_fusion/ΔH_vaporization
- **Митигация:** Эвристические оценки, расчёт из разницы H₂₉₈, информирование пользователя

### Риск 2: Неконсистентность данных
- **Проблема:** Разные источники дают разные значения энтальпий
- **Митигация:** Валидация, выбор наиболее надёжных источников, предупреждения

### Риск 3: Термодинамическая некорректность
- **Проблема:** Нарушение законов термодинамики при расчётах
- **Митигация:** Валидация результатов, проверка знаков ΔH, разумные границы

### Риск 4: Производительность
- **Проблема:** Дополнительные расчёты замедляют систему
- **Митигация:** Кэширование, оптимизация, предвычисления

## Документация

### Обновить:
1. **ThermodynamicCalculator API** — документировать методы с переходами
2. **Phase Transitions Guide** — руководство по фазовым переходам
3. **Data Sources Documentation** — источники данных о переходах

### Создать:
1. **Transition Thermodynamics** — теоретическая основа
2. **Validation Rules** — правила валидации данных
3. **Performance Optimization** — оптимизация расчётов

## Временная шкала

- **День 1:** Расширение моделей и создание `PhaseTransitionCalculator`
- **День 2:** Обновление `ThermodynamicCalculator` для учёта переходов
- **День 3:** Создание `TransitionDataManager` и интеграция данных
- **День 4:** Обновление реакционных расчётов и тестирование
- **День 5:** Оптимизация, документация, финальное тестирование

## Ответственные

- **Разработчик:** Основной разработчик
- **Code Review:** Ведущий архитектор
- **Тестирование:** QA-инженер

## Критерии успеха

1. **FeO пример:** Корректные скачки H и S при 1650K и 3687K
2. **Термодинамика:** Все расчёты термодинамически корректны
3. **Данные:** Используются все доступные данные о переходах
4. **Производительность:** Расчёты с переходами занимают <2 секунд
5. **Тесты:** Все тесты проходят, покрытие ≥ 85%
6. **Интеграция:** Готов к Этапу 5 (оркестратор и форматирование)

---

**Статус:** Готов к реализации после Этапов 1-3
**Следующий этап:** Этап 5: Обновление оркестратора и форматирования