# Этап 1: Модификация поиска и фильтрации данных

## Общая информация

- **Этап:** 1 из 6
- **Название:** Модификация поиска и фильтрации данных
- **Статус:** Запланирован
- **Приоритет:** Критический
- **Длительность (оценка):** 3-4 дня

## Проблема

Текущая система использует температурный диапазон из запроса пользователя для фильтрации записей в базе данных. Это приводит к потере критически важных данных:

- **Пример:** FeO в диапазоне 773-973K
  - Система выбирает запись 600-900K с H₂₉₈ = 0.0
  - Отбрасывает запись 298-600K с H₂₉₈ = -265.053 кДж/моль
- **Результат:** Некорректные расчёты термодинамических свойств

## Цель этапа

Игнорировать пользовательский температурный диапазон на этапах поиска и фильтрации данных, обеспечивая доступ ко всем записям из базы данных.

## Задачи этапа

### 1. Создание TemperatureRangeResolver

**Файл:** `src/thermo_agents/filtering/temperature_range_resolver.py`

**Задачи:**
- Создать класс `TemperatureRangeResolver`
- Реализовать метод `determine_calculation_range()` для определения общего диапазона
- Реализовать метод `validate_range_coverage()` для проверки покрытия данных
- Логика определения диапазона:
  - Собрать все tmin/tmax из записей всех веществ
  - Найти пересечение диапазонов
  - Расширить до 298K если возможно
  - Вернуть корректный диапазон для расчётов

**Сигнатура:**
```python
@dataclass
class TemperatureRangeResolver:
    def determine_calculation_range(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]]
    ) -> Tuple[float, float]

    def validate_range_coverage(
        self,
        compounds_data: Dict[str, List[DatabaseRecord]],
        temp_range: Tuple[float, float]
    ) -> Dict[str, bool]
```

### 2. Модификация CompoundSearcher

**Файл:** `src/thermo_agents/search/compound_searcher.py`

**Задачи:**
- Убрать передачу `temperature_range` в `SQLBuilder`
- Модифицировать метод `search_compound()` для поиска всех записей
- Добавить параметр `ignore_temperature_range: bool = True`
- Обновить логирование для информирования о полном поиске

**Изменения в методах:**
```python
async def search_compound(
    self,
    formula: str,
    temperature_range: Optional[Tuple[float, float]] = None,  # Игнорируется
    phase: Optional[str] = None,
    max_records: int = 100
) -> CompoundSearchResult:
```

### 3. Модификация FilterPipeline

**Файл:** `src/thermo_agents/filtering/filter_pipeline.py`

**Задачи:**
- Изменить `TemperatureFilterStage` для использования полного диапазона
- Модифицировать конвейер для обработки всех записей без температурных ограничений
- Обновить `PhaseBasedTemperatureStage` для работы с полным набором данных
- Добавить информирование о количестве найденных записей

**Изменения в стадиях:**
```python
class TemperatureFilterStage(FilterStage):
    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> FilterResult:
        # ИСПОЛЬЗУЕТ ПОЛНЫЙ ДИАПАЗОН, не пользовательский
        target_range = context.full_calculation_range  # Новый параметр
```

### 4. Обновление моделей данных

**Файл:** `src/thermo_agents/models/search.py`

**Задачи:**
- Добавить поле `full_calculation_range: Tuple[float, float]` в `CompoundSearchResult`
- Добавить поле `original_user_range: Optional[Tuple[float, float]]`
- Обновить валидацию моделей

```python
@dataclass
class CompoundSearchResult:
    formula: str
    records: List[DatabaseRecord]
    full_calculation_range: Tuple[float, float]
    original_user_range: Optional[Tuple[float, float]] = None
    # ... остальные поля
```

### 5. Модификация MultiPhaseOrchestrator

**Файл:** `src/thermo_agents/orchestrator_multi_phase.py`

**Задачи:**
- Интегрировать `TemperatureRangeResolver`
- Изменить логику передачи параметров в `CompoundSearcher`
- Сохранять пользовательский диапазон для форматирования
- Использовать полный диапазон для расчётов

## Критерии завершения

### Функциональные критерии

1. **Поиск всех записей:**
   - [ ] Для FeO находится 6 записей (текущее: 1)
   - [ ] Для H2S находится >10 записей (текущее: 1)
   - [ ] Для всех веществ находятся все доступные записи

2. **Определение диапазона:**
   - [ ] `TemperatureRangeResolver` корректно определяет общий диапазон
   - [ ] Диапазон включает 298K если данные доступны
   - [ ] Диапазон является пересечением всех веществ

3. **Фильтрация:**
   - [ ] `FilterPipeline` не отбрасывает записи по температурному диапазону
   - [ ] Сохраняется логика фильтрации по фазам
   - [ ] Удаляются только дубликаты и некорректные записи

4. **Интеграция:**
   - [ ] `MultiPhaseOrchestrator` использует новый подход
   - [ ] Пользовательский диапазон сохраняется для вывода
   - [ ] Расчёты используют полный диапазон

### Технические критерии

1. **Производительность:**
   - [ ] Время поиска не увеличилось >10%
   - [ ] Использование памяти в пределах нормы
   - [ ] Кэширование продолжает работать

2. **Качество кода:**
   - [ ] Все новые классы имеют docstrings
   - [ ] Добавлены unit тесты для `TemperatureRangeResolver`
   - [ ] Обновлены интеграционные тесты
   - [ ] Покрытие кода тестами ≥ 85%

## Тестирование

### Unit тесты

**Файл:** `tests/unit/test_temperature_range_resolver.py`

```python
class TestTemperatureRangeResolver:
    def test_determine_calculation_range_simple(self)
    def test_determine_calculation_range_with_298K(self)
    def test_determine_calculation_range_complex_intersection(self)
    def test_validate_range_coverage(self)
```

### Интеграционные тесты

**Файл:** `tests/integration/test_stage_01_search_modification.py`

```python
class TestStage1SearchModification:
    async def test_feo_full_search(self)
    async def test_h2s_full_search(self)
    async def test_multi_compound_range_determination(self)
    async def test_temperature_range_ignored_in_search(self)
```

### Регрессионные тесты

- Проверить, что существующие запросы продолжают работать
- Убедиться, что результаты не ухудшились для корректных случаев

## Риски и митигации

### Риск 1: Увеличение объёма данных
- **Проблема:** Система может обрабатывать в 10-100 раз больше записей
- **Митигация:** Оптимизировать кэширование, использовать ленивую загрузку

### Риск 2: Обратная совместимость
- **Проблема:** Старый код может ожидать отфильтрованные данные
- **Митигация:** Добавить флаг `use_legacy_mode` для обратной совместимости

### Риск 3: Производительность
- **Проблема:** Увеличение времени обработки
- **Митигация:** Параллельная обработка, оптимизация SQL запросов

## Документация

### Обновить:
1. **ARCHITECTURE.md** — описать новый подход к поиску
2. **API Reference** — обновить сигнатуры методов
3. **Примеры использования** — показать новую логику

### Создать:
1. **TemperatureRangeResolver.md** — документация компонента
2. **Migration_Guide.md** — руководство по миграции на v2.2

## Зависимости

### Входящие:
- Анализ проблемы из `multiphases_spec.md` ✅
- Архитектура системы v2.1 ✅

### Исходящие:
- Этап 2: Построение фазовых сегментов (требует полные данные)
- Этап 3: Автоматический выбор записей
- Все последующие этапы

## Временная шкала

- **День 1:** Создание `TemperatureRangeResolver` и базовых тестов
- **День 2:** Модификация `CompoundSearcher` и `FilterPipeline`
- **День 3:** Интеграция в `MultiPhaseOrchestrator` и обновление моделей
- **День 4:** Тестирование, отладка, документация

## Ответственные

- **Разработчик:** Основной разработчик
- **Code Review:** Ведущий архитектор
- **Тестирование:** QA-инженер

## Критерии успеха

1. **FeO тест:** Находится 6 записей вместо 1
2. **H₂₉₈ корректность:** Используется запись с H₂₉₈ = -265.053
3. **Производительность:** Время ответа ≤ 3 секунд
4. **Тесты:** Все тесты проходят, покрытие ≥ 85%

---

**Статус:** Готов к реализации
**Следующий этап:** Этап 2: Построение фазовых сегментов