# Этап 5: Обновление оркестратора и форматирования

## Общая информация

- **Этап:** 5 из 6
- **Название:** Обновление оркестратора и форматирования
- **Статус:** Запланирован
- **Приоритет:** Высокий
- **Длительность (оценка):** 3-4 дня
- **Зависимости:** Этапы 1-4 (поиск, сегменты, записи, переходы)

## Проблема

После Этапов 1-4 все основные компоненты для многофазных расчётов будут готовы, но `MultiPhaseOrchestrator` и форматтеры не будут использовать новую функциональность. Пользователь не увидит преимуществ новой системы.

**Текущие ограничения:**
1. `MultiPhaseOrchestrator` использует старую логику
2. Форматтеры не показывают информацию о фазовых переходах
3. Пользователь видит только запрошенный диапазон, не полный
4. Нет информации о использованных фазах и записях

**Проблема с текущим выводом:**
```
Текущий вывод:
FeO — Iron(II) oxide
  Фаза: s | T_применимости: 600-900 K
  H₂₉₈: 0.000 кДж/моль | S₂₉₈: 0.000 Дж/(моль·K)  ← НЕВЕРНО

Ожидаемый вывод:
FeO — Iron(II) oxide
  Запрошенный диапазон: 773-973K
  Расчётный диапазон: 298-5000K (полное использование БД)
  Фазовые переходы: плавление при 1650K, кипение при 3687K
  Использованные фазы: s (298-1650K), l (1650-3687K)
  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)  ← ВЕРНО
```

## Цель этапа

Интегрировать все компоненты многофазной логики в основной оркестратор и обновить форматтеры для предоставления пользователю полной информации о выполненных расчётах.

## Задачи этапа

### 1. Модификация MultiPhaseOrchestrator

**Файл:** `src/thermo_agents/orchestrator_multi_phase.py`

**Задачи:**
- Интегрировать `TemperatureRangeResolver` для определения полного диапазона
- Использовать `PhaseSegmentBuilder` для построения сегментов
- Применять `MultiPhaseReactionCalculator` для расчётов
- Сохранять пользовательский диапазон для информирования
- Реализовать новую логику обработки запросов

**Основные изменения:**
```python
class MultiPhaseOrchestrator:
    async def process_query_with_multi_phase(
        self,
        query: str
    ) -> str

    async def _process_reaction_calculation_multi_phase(
        self,
        params: ExtractedReactionParameters
    ) -> str

    def _determine_full_calculation_range(
        self,
        all_compounds_data: Dict[str, MultiPhaseCompoundData]
    ) -> Tuple[float, float]

    def _build_multi_phase_data(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]]
    ) -> Dict[str, MultiPhaseCompoundData]
```

### 2. Обновление ReactionCalculationFormatter

**Файл:** `src/thermo_agents/formatting/reaction_calculation_formatter.py`

**Задачи:**
- Добавить отображение запрошенного vs расчётного диапазона
- Показывать информацию о фазовых переходах
- Отображать использованные фазы для каждого вещества
- Информировать о полном использовании данных из базы
- Добавить статистику по использованным записям

**Новые методы:**
```python
class ReactionCalculationFormatter:
    def format_multi_phase_reaction(
        self,
        reaction_data: MultiPhaseReactionData,
        params: ExtractedReactionParameters
    ) -> str

    def _format_range_information(
        self,
        user_range: Optional[Tuple[float, float]],
        calculation_range: Tuple[float, float]
    ) -> str

    def _format_phase_information(
        self,
        compounds_data: Dict[str, MultiPhaseCompoundData]
    ) -> str

    def _format_transition_information(
        self,
        transitions: Dict[str, List[PhaseTransition]]
    ) -> str

    def _format_data_usage_statistics(
        self,
        all_compounds_data: Dict[str, MultiPhaseCompoundData]
    ) -> str
```

### 3. Обновление CompoundDataFormatter

**Файл:** `src/thermo_agents/formatting/compound_data_formatter.py`

**Задачи:**
- Поддержать отображение многофазных данных
- Показывать фазовые сегменты в табличном виде
- Информировать о переходах между фазами
- Отображать статистику по записям

```python
class CompoundDataFormatter:
    def format_multi_phase_compound(
        self,
        compound_data: MultiPhaseCompoundData,
        temperature_range: Optional[Tuple[float, float]] = None
    ) -> str

    def _format_phase_segments_table(
        self,
        segments: List[PhaseSegment]
    ) -> str

    def _format_transitions_table(
        self,
        transitions: List[PhaseTransition]
    ) -> str

    def _format_records_summary(
        self,
        compound_data: MultiPhaseCompoundData
    ) -> str
```

### 4. Создание MultiPhaseReactionData

**Файл:** `src/thermo_agents/models/aggregation.py`

**Задачи:**
- Создать модель для хранения результатов многофазных расчётов
- Включить информацию о фазовых изменениях
- Сохранить статистику использования данных
- Добавить метаданные расчётов

```python
@dataclass
class MultiPhaseReactionData:
    balanced_equation: str
    reactants: List[str]
    products: List[str]
    stoichiometry: Dict[str, float]

    # Новые поля
    user_temperature_range: Optional[Tuple[float, float]]
    calculation_range: Tuple[float, float]
    compounds_data: Dict[str, MultiPhaseCompoundData]
    phase_changes: List[Tuple[float, str, str]]  # (T, compound, transition)

    # Результаты
    calculation_table: List[Dict[str, Any]]
    data_statistics: Dict[str, Any]

    # Метаданные
    calculation_method: str
    total_records_used: int
    phases_used: Set[str]
```

### 5. Обновление ExtractedReactionParameters

**Файл:** `src/thermo_agents/models/extraction.py`

**Задачи:**
- Добавить флаг для использования многофазных расчётов
- Улучшить валидацию температурных диапазонов
- Добавить метаданные о запросе

```python
@dataclass
class ExtractedReactionParameters:
    # ... существующие поля

    # Новые поля
    use_multi_phase: bool = True  # По умолчанию используем многофазные расчёты
    full_data_search: bool = True  # Игнорировать температурные ограничения при поиске
    user_preferences: Dict[str, Any] = field(default_factory=dict)
```

## Логика обновлённого оркестратора

### Новый поток выполнения

```python
async def process_query_with_multi_phase(self, query: str) -> str:
    # 1. Извлечение параметров (без изменений)
    params = await self.thermodynamic_agent.extract_parameters(query)

    # 2. Поиск всех записей (без температурных ограничений)
    all_records = {}
    for compound in params.all_compounds:
        result = await self.searcher.search_compound(
            compound,
            temperature_range=None,  # ← КЛЮЧЕВОЕ ИЗМЕНЕНИЕ
            max_records=200
        )
        all_records[compound] = result.records

    # 3. Определение полного расчётного диапазона
    calculation_range = self._determine_full_calculation_range(all_records)

    # 4. Построение фазовых сегментов
    multi_phase_data = self._build_multi_phase_data(all_records)

    # 5. Расчёты с учётом фазовых переходов
    if params.query_type == "reaction_calculation":
        reaction_data = await self.reaction_calculator.calculate_reaction_with_transitions(
            multi_phase_data, params.stoichiometry, calculation_range
        )

        # 6. Форматирование с полной информацией
        return self.reaction_formatter.format_multi_phase_reaction(
            reaction_data, params
        )
```

### Форматирование вывода

**Структура вывода для реакций:**
```
================================================================================
⚗️ Термодинамический расчёт реакции (Полная многофазная логика)
================================================================================

Уравнение: FeO + H₂S → FeS + H₂O

Запрошенный диапазон: 500-700°C (773-973K)
Расчётный диапазон: 298-5000K (максимальное использование базы данных)

ℹ️  ИНФОРМАЦИЯ: Расчёт выполнен с использованием всех доступных данных из базы.
    Это гарантирует корректность базовых термодинамических свойств (H₂₉₈, S₂₉₈)
    и учёт фазовых переходов.

Данные веществ:
--------------------------------------------------------------------------------
FeO — Iron(II) oxide
  Общий диапазон: 298-5000K
  Фазовые переходы: плавление при 1650K, кипение при 3687K
  Использованные фазы: s (298-1650K), l (1650-3687K), g (3687-5000K)
  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)
  Всего записей использовано: 6 из 6

H₂S — Hydrogen sulfide
  Общий диапазон: 298-5000K
  Фазовые переходы: плавление при 187.7K, кипение при 213.6K
  Использованные фазы: g (298-5000K)
  H₂₉₈: -20.502 кДж/моль | S₂₉₈: 205.752 Дж/(моль·K)
  Всего записей использовано: 27 из 47

[... другие вещества ...]

Результаты расчёта:
| T(K) | ΔH° (кДж/моль) | ΔS° (Дж/К·моль) | ΔG° (кДж/моль) | Фаза         | Комментарий                |
| ---- | -------------- | --------------- | -------------- | ------------ | -------------------------- |
| 298  | -33.45         | -45.23          | -19.97         | s,g          | Стандартные условия        |
| 773  | -28.12         | -42.11          | -4.58          | s,g          | ← Запрошенный диапазон      |
| 873  | -27.85         | -41.98          | -1.21          | s,g          |                            |
| 973  | -27.60         | -41.87          | +1.12          | s,g          | ← Запрошенный диапазон      |
| 1650 | -25.30         | -40.50          | +41.53         | s→l transition| Плавление FeO             |
| 3687 | -22.15         | -39.20          | +122.48        | l→g transition| Кипение FeO, H₂O           |
| 5000 | -18.90         | -38.10          | +171.60        | g,g          | Максимальная температура   |

Статистика расчёта:
- Всего использовано записей: 156 из 220
- Фазовых переходов учтено: 8
- Покрытие базы данных: 100% для всех веществ в диапазоне
- Время выполнения: 2.3 секунды
```

## Критерии завершения

### Функциональные критерии

1. **Интеграция оркестратора:**
   - [ ] `MultiPhaseOrchestrator` использует все компоненты Этапов 1-4
   - [ ] Пользовательский диапазон сохраняется для информации
   - [ ] Расчётный диапазон определяется автоматически
   - [ ] Многофазные данные строятся корректно

2. **Форматирование вывода:**
   - [ ] Показывается запрошенный vs расчётный диапазон
   - [ ] Отображается информация о фазовых переходах
   - [ ] Выводятся использованные фазы для каждого вещества
   - [ ] Информируется о полном использовании данных из базы

3. **Обратная связь пользователю:**
   - [ ] Понятные сообщения о многофазных расчётах
   - [ ] Информация о количестве использованных записей
   - [ ] Объяснение преимуществ нового подхода
   - [ ] Статистика выполнения расчётов

4. **Производительность:**
   - [ ] Время ответа ≤ 3 секунд
   - [ ] Использование памяти в нормальных пределах
   - [ ] Кэширование работает эффективно

### Технические критерии

1. **Качество кода:**
   - [ ] Все изменения имеют полную документацию
   - [ ] Unit тесты покрывают новую логику
   - [ ] Интеграционные тесты проверяют полный цикл
   - [ ] Покрытие кода тестами ≥ 85%

2. **Совместимость:**
   - [ ] Обратная совместимость с старыми форматами
   - [ ] Graceful degradation при ошибках
   - [ ] Корректная обработка граничных случаев

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_multi_phase_orchestrator.py`

```python
class TestMultiPhaseOrchestrator:
    async def test_process_query_with_multi_phase(self)
    async def test_determine_full_calculation_range(self)
    async def test_build_multi_phase_data(self)
    async def test_handle_missing_data(self)
    async def test_user_range_preservation(self)
```

### Интеграционные тесты

**Файл:** `tests/integration/test_stage_05_orchestrator_update.py`

```python
class TestStage5OrchestratorUpdate:
    async def test_feo_h2s_full_calculation(self)
    async def test_formatting_multi_phase_output(self)
    async def test_user_vs_calculation_range_display(self)
    async def test_phase_transition_information(self)
    async def test_data_usage_statistics(self)
    async def test_performance_full_pipeline(self)
```

### Тесты форматирования

```python
class TestStage5Formatting:
    def test_multi_phase_reaction_formatting(self)
    def test_compound_data_multi_phase_formatting(self)
    def test_range_information_display(self)
    def test_phase_transition_display(self)
    def test_statistics_display(self)
```

## Риски и митигации

### Риск 1: Увеличение времени ответа
- **Проблема:** Новая логика может замедлить обработку
- **Митигация:** Оптимизация, параллельная обработка, кэширование

### Риск 2: Сложность вывода
- **Проблема:** Много информации может запутать пользователя
- **Митигация:** Чёткая структура, возможность компактного режима

### Риск 3: Обратная совместимость
- **Проблема:** Старый код может ожидать другой формат
- **Митигация:** Adapter pattern, fallback методы

### Риск 4: Производительность форматирования
- **Проблема:** Большой объём данных может замедлить форматирование
- **Митигация:** Ленивая генерация таблиц, оптимизация строковых операций

## Документация

### Обновить:
1. **User Guide** — описание нового вывода
2. **API Reference** — обновленные методы оркестратора
3. **Architecture.md** — описание нового потока выполнения

### Создать:
1. **Multi-Phase Output Guide** — руководство по выводу
2. **Migration Guide v2.1→v2.2** — переход на новую версию
3. **Performance Guide** — оптимизация производительности

## Временная шкала

- **День 1:** Модификация `MultiPhaseOrchestrator` и интеграция компонентов
- **День 2:** Обновление `ReactionCalculationFormatter` и создание новых методов форматирования
- **День 3:** Обновление `CompoundDataFormatter` и моделей данных
- **День 4:** Тестирование, оптимизация, документация

## Ответственные

- **Разработчик:** Основной разработчик
- **Code Review:** Ведущий архитектор
- **UX/UI:** Специалист по пользовательскому опыту

## Критерии успеха

1. **FeO + H₂S пример:** Полный многофазный расчёт с корректным выводом
2. **Информативность:** Пользователь видит все преимущества нового подхода
3. **Производительность:** Время ответа ≤ 3 секунд
4. **Качество:** Весь вывод понятен и хорошо структурирован
5. **Тесты:** Все тесты проходят, покрытие ≥ 85%
6. **Готовность:** Система готова к финальному тестированию (Этап 6)

---

**Статус:** Готов к реализации после Этапов 1-4
**Следующий этап:** Этап 6: Тестирование и валидация