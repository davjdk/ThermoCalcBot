# Этап 7: Удаление старой логики и рефакторинг

## Общая информация

- **Этап:** 7 из 7
- **Название:** Удаление старой логики и рефакторинг
- **Статус:** Запланирован
- **Приоритет:** Критический
- **Длительность (оценка):** 3-4 дня
- **Зависимости:** Этапы 1-6 (полная реализация и валидация)

## Обоснование необходимости

После успешной реализации Этапов 1-6 система будет иметь новую многофазную логику, параллельно с которой будет существовать старая логика. Дублирование кода недопустимо по следующим причинам:

1. **Технический долг:** Два разных подхода создают путаницу в коде
2. **Поддержка:** Удвоение усилий по поддержке и отладке
3. **Производительность:** Лишний код увеличивает размер и сложность
4. **Надёжность:** Старая логика может содержать ошибки
5. **Безопасность:** Старый код может иметь уязвимости

## Цель этапа

Полностью удалить старую логику поиска и фильтрации данных, оставив только новую многофазную систему. Обеспечить чистоту и простоту кодовой базы.

## Задачи этапа

### 1. Аудит старой логики

**Задачи:**
- Провести полный аудит кодовой базы для поиска старой логики
- Составить реестр всех файлов и методов, содержащих старый подход
- Определить зависимости между старыми компонентами
- Проверить использование старых компонентов в других частях системы

**Файлы для анализа:**
```python
# Потенциальные файлы со старой логикой:
src/thermo_agents/search/sql_builder.py
src/thermo_agents/search/compound_searcher.py
src/thermo_agents/filtering/filter_pipeline.py
src/thermo_agents/filtering/filter_stages.py
src/thermo_agents/filtering/temperature_resolver.py
src/thermo_agents/calculations/thermodynamic_calculator.py
src/thermo_agents/orchestrator.py
src/thermo_agents/orchestrator_multi_phase.py
```

**Результаты аудита:**
- Список всех старых методов и классов
- Карта зависимостей
- Файлы, которые можно полностью удалить
- Файлы, которые нужно рефакторить

### 2. Удаление старых компонентов поиска

**Файл:** `src/thermo_agents/search/sql_builder.py`

**Действия:**
- Удалить метод `build_temperature_filtered_query()`
- Удалить параметр `temperature_range` из `build_compound_query()`
- Удалить старые SQL паттерны с температурной фильтрацией
- Оставить только базовые методы построения запросов

**Было:**
```python
def build_compound_query(
    self,
    formula: str,
    temperature_range: Optional[Tuple[float, float]] = None,  # ← УДАЛИТЬ
    phase: Optional[str] = None,
    max_records: int = 100
) -> str:
    if temperature_range:
        query += f" AND tmin <= {temperature_range[1]} AND tmax >= {temperature_range[0]}"
```

**Стало:**
```python
def build_compound_query(
    self,
    formula: str,
    phase: Optional[str] = None,
    max_records: int = 100
) -> str:
    # Только базовая фильтрация без температурных ограничений
```

### 3. Удаление старой фильтрации

**Файл:** `src/thermo_agents/filtering/filter_pipeline.py`

**Действия:**
- Удалить `TemperatureFilterStage`
- Удалить `PhaseBasedTemperatureStage`
- Удалить параметр `temperature_range` из `FilterContext`
- Упростить конвейер, оставив только `PhaseSegmentBuildingStage`

**Было:**
```python
class FilterPipeline:
    def __init__(self):
        self.stages = [
            TemperatureFilterStage(),         # ← УДАЛИТЬ
            PhaseBasedTemperatureStage(),     # ← УДАЛИТЬ
            DuplicateRemovalStage(),
            ComplexSearchStage(),
            PhaseSegmentBuildingStage()       # ← ОСТАВИТЬ
        ]
```

**Стало:**
```python
class FilterPipeline:
    def __init__(self):
        self.stages = [
            DuplicateRemovalStage(),
            ComplexSearchStage(),
            PhaseSegmentBuildingStage()
        ]
```

### 4. Удаление старого оркестратора

**Файл:** `src/thermo_agents/orchestrator.py`

**Действия:**
- Полностью удалить старый `ThermoOrchestrator`
- Переименовать `MultiPhaseOrchestrator` в `ThermoOrchestrator`
- Обновить все импорты в проекте
- Удалить параметры `use_multi_phase` из конфигураций

**Было:**
```python
# Старый оркестратор - УДАЛИТЬ
class ThermoOrchestrator:
    def process_query(self, query: str) -> str:
        # Старая логика с температурными ограничениями

# Новый оркестратор - ПЕРЕИМЕНОВАТЬ
class MultiPhaseOrchestrator:
    async def process_query_with_multi_phase(self, query: str) -> str:
        # Новая многофазная логика
```

**Стало:**
```python
# Единый оркестратор
class ThermoOrchestrator:
    async def process_query(self, query: str) -> str:
        # Только многофазная логика
```

### 5. Обновление моделей данных

**Файл:** `src/thermo_agents/models/search.py`

**Действия:**
- Удалить `CompoundSearchResult` (старый)
- Оставить только `MultiPhaseCompoundData`
- Удалить `FilterContext` с температурными параметрами
- Упростить модели, убрав поля для обратной совместимости

**Было:**
```python
@dataclass
class CompoundSearchResult:                     # ← УДАЛИТЬ
    formula: str
    records: List[DatabaseRecord]
    temperature_range: Tuple[float, float]      # ← Старый подход

@dataclass
class FilterContext:
    user_temperature_range: Optional[Tuple[float, float]]  # ← УДАЛИТЬ
    calculation_range: Tuple[float, float]                 # ← Оставить
```

**Стало:**
```python
@dataclass
class MultiPhaseCompoundData:                   # ← ОСТАВИТЬ
    formula: str
    phase_segments: List[PhaseSegment]
    total_range: Tuple[float, float]
```

### 6. Обновление конфигураций

**Файл:** `src/thermo_agents/models/extraction.py`

**Действия:**
- Удалить `use_multi_phase` из `ExtractedReactionParameters`
- Удалить `full_data_search` из конфигураций
- Упростить конфигурацию, убрав флаги совместимости

**Было:**
```python
@dataclass
class ExtractedReactionParameters:
    use_multi_phase: bool = True          # ← УДАЛИТЬ
    full_data_search: bool = True         # ← УДАЛИТЬ
```

**Стало:**
```python
@dataclass
class ExtractedReactionParameters:
    # Параметры без флагов совместимости
```

### 7. Обновление основного приложения

**Файл:** `main.py`

**Действия:**
- Удалить логику выбора оркестратора
- Использовать только `ThermoOrchestrator` (переименованный)
- Удалить параметры командной строки для старого режима

**Было:**
```python
def main():
    use_multi_phase = args.multi_phase
    if use_multi_phase:
        orchestrator = MultiPhaseOrchestrator()
    else:
        orchestrator = ThermoOrchestrator()
```

**Стало:**
```python
def main():
    # Только новый оркестратор
    orchestrator = ThermoOrchestrator()
```

### 8. Обновление тестов

**Действия:**
- Удалить тесты для старой логики
- Обновить интеграционные тесты
- Удалить тесты обратной совместимости
- Обновить фикстуры и mock'и

**Файлы для обновления:**
```python
tests/unit/test_compound_searcher.py          # Удалить старые тесты
tests/integration/test_legacy_compatibility.py # Удалить полностью
tests/integration/test_end_to_end.py          # Обновить для новой логики
```

### 9. Обновление документации

**Действия:**
- Обновить `ARCHITECTURE.md` - убрать описание старой логики
- Обновить `CLAUDE.md` - убрать упоминания старого режима
- Обновить API документацию
- Удалить документацию по обратной совместимости

### 10. Финальная чистка кода

**Задачи:**
- Запустить `flake8` и `black` для форматирования
- Удалить неиспользуемые импорты
- Обновить `__all__` списки в модулях
- Проверить типизацию (`mypy`)

## Критерии завершения

### Функциональные критерии

1. **Удаление старой логики:**
   - [ ] Все старые классы и методы удалены
   - [ ] Параметры обратной совместимости удалены
   - [ ] Старые файлы полностью удалены или рефакторены

2. **Единый подход:**
   - [ ] Только многофазная логика в системе
   - [ ] Один оркестратор вместо двух
   - [ ] Единые модели данных

3. **Чистота кода:**
   - [ ] Нет дублирования функциональности
   - [ ] Нет неиспользуемого кода
   - [ ] Код соответствует стандартам форматирования

### Технические критерии

1. **Производительность:**
   - [ ] Время работы не увеличилось
   - [ ] Использование памяти уменьшилось
   - [ ] Размер кодовой базы уменьшился на 15-20%

2. **Надёжность:**
   - [ ] Все тесты проходят
   - [ ] Нет ошибок импорта
   - [ ] Система работает стабильно

## Тестирование после удаления

### Smoke тесты

```python
class TestLegacyRemoval:
    async def test_feo_calculation_works(self)
    async def test_water_phase_transitions_work(self)
    async def test_multi_compound_reaction_works(self)
    async def test_performance_maintained(self)
```

### Регрессионные тесты

```python
class TestRegressionAfterRemoval:
    def test_all_api_endpoints_respond(self)
    def test_no_import_errors(self)
    def test_configuration_works(self)
    def test_logging_functions(self)
```

## Риски и митигации

### Риск 1: Скрытые зависимости
- **Проблема:** Неочевидные зависимости от старой логики
- **Митигация:** Тщательный аудит, исчерпывающее тестирование

### Риск 2: Потеря функциональности
- **Проблема:** Случайное удаление нужного кода
- **Митигация:** Постепенное удаление, тестирование на каждом шаге

### Риск 3: Проблемы с импортами
- **Проблема:** Сломанные импорты после удаления
- **Митигация:** Проверка всех импортов, обновление зависимостей

### Риск 4: Обратная совместимость API
- **Проблема:** Внешние системы могут зависеть от старого API
- **Митигация:** Анализ использования, создание compatibility layer при необходимости

## Документация изменений

### Обновить:
1. **CHANGELOG.md** - описание удаления старой логики
2. **MIGRATION.md** - руководство по переходу на v2.2
3. **ARCHITECTURE.md** - обновлённая архитектура
4. **API Reference** - актуальное API

### Создать:
1. **Legacy Removal Summary** - отчёт об удалении
2. **Code Reduction Metrics** - метрики упрощения кода

## Временная шкала

- **День 1:** Аудит старой логики и составление реестра
- **День 2:** Удаление старых компонентов поиска и фильтрации
- **День 3:** Удаление старого оркестратора и обновление моделей
- **День 4:** Обновление тестов, документации и финальная чистка

## Ответственные

- **Разработчик:** Основная работа по удалению кода
- **Архитектор:** Надзор за сохранением архитектурной целостности
- **QA-инженер:** Тестирование после удаления

## Критерии успеха

1. **Старая логика полностью удалена:** Ни одного следа старого подхода
2. **Система работает стабильно:** Все функции корректны
3. **Код стал проще:** Уменьшение сложности и объёма
4. **Тесты проходят:** Полное покрытие функциональности
5. **Документация актуальна:** Отражает текущее состояние

## Финальный результат

После Этапа 7 система будет:
- **Чистой:** Только многофазная логика без дублирования
- **Простой:** Единый подход к термодинамическим расчётам
- **Надёжной:** Без старых ошибок и уязвимостей
- **Легкой в поддержке:** Минимальный объём кода
- **Современной:** Соответствие лучшим практикам разработки

**Версия системы:** ThermoSystem v2.2 (чистая многофазная)

---

**Статус:** Запланирован после Этапа 6
**Результат:** Чистая, современная система с единой многофазной логикой