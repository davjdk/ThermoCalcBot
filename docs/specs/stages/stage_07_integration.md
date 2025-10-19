# Stage 07: Интеграция и end-to-end тесты (Big Bang)

## Цель
Выполнить одномоментное внедрение всех изменений из Stage 01-06 в основной код системы, заменив старую логику расчётов новой многофазной архитектурой.

## Статус
🟢 Реализовано и протестировано

## Стратегия внедрения
**Big Bang (одномоментное внедрение)** — полная замена старой логики на новую многофазную систему без промежуточных флагов.

### Преимущества выбранной стратегии
- ✅ Нет дублирования кода (старая + новая логика)
- ✅ Чистая архитектура без технического долга
- ✅ Быстрое внедрение (нет постепенной миграции)
- ✅ Упрощённое тестирование (один путь выполнения)

### Риски и митигация
- ⚠️ **Риск:** Невозможность быстрого отката при критических багах
  - **Митигация:** Резервная копия БД и кода перед внедрением
  - **Митигация:** Тщательное тестирование перед деплоем
  - **Митигация:** Git-ветка с возможностью revert
  
- ⚠️ **Риск:** Регрессия существующего функционала
  - **Митигация:** Полный набор regression-тестов
  - **Митигация:** Сравнительное тестирование старой vs новой версии

## Входные данные
- ✅ Stage 01: `CompoundSearcher.search_all_phases()` реализован
- ✅ Stage 02: `TemperatureSegment` и `PhaseTransition` готовы
- ✅ Stage 03: `MultiPhaseProperties` и валидация данных
- ✅ Stage 04: `StaticDataManager` и YAML кэш
- ✅ Stage 05: `ThermodynamicCalculator.calculate_multi_phase_properties()` работает
- ✅ Stage 06: Форматтеры для многофазного вывода

## Выходные данные
- Обновлённый `ThermodynamicAgent` (только многофазная логика)
- Обновлённый `Orchestrator` с интеграцией всех компонентов
- End-to-end тесты для всех сценариев
- Обновлённая документация пользователя
- **Удалённый** старый код одиночных расчётов

## Изменяемые файлы
- `src/thermo_agents/thermodynamic_agent.py` ✏️ Полная замена логики
- `src/thermo_agents/orchestrator.py` ✏️ Интеграция новых компонентов
- `src/thermo_agents/operations.py` ✏️ Обновление операций
- Все старые тесты одиночных расчётов ❌ Удаление/обновление

## Зависимости
- Все предыдущие стадии (01-06) **полностью завершены**

## Алгоритм действий (Big Bang Strategy)

### Шаг 1: Удаление старой логики одиночных расчётов

**Файл:** `src/thermo_agents/thermodynamic_agent.py`

#### ❌ Удалить полностью:
1. **Метод `_calculate_single_phase()`** — старая логика одиночного расчёта
   ```python
   def _calculate_single_phase(self, formula: str, T_min: float, T_max: float, 
                                step_k: int, compound_names: Optional[List[str]]) -> str:
       # Вся реализация удаляется
   ```

2. **Метод `_needs_multi_phase_calculation()`** — проверка необходимости многофазного расчёта (больше не нужна, всегда используем многофазный)
   ```python
   def _needs_multi_phase_calculation(self, formula: str, T_max: float, 
                                      compound_names: Optional[List[str]] = None) -> bool:
       # Вся реализация удаляется
   ```

3. **Параметр `use_multi_phase`** из `__init__()` — больше не нужен флаг выбора режима
   ```python
   def __init__(self, ..., use_multi_phase: bool = True):  # ← Удалить параметр
       self.use_multi_phase = use_multi_phase  # ← Удалить присвоение
   ```

4. **Условная логика** в `calculate_compound_properties()`:
   ```python
   # ❌ УДАЛИТЬ:
   needs_multi_phase = self._needs_multi_phase_calculation(...)
   if needs_multi_phase and self.use_multi_phase:
       return self._calculate_multi_phase(...)
   else:
       return self._calculate_single_phase(...)
   ```

#### ✏️ Заменить на:
```python
def calculate_compound_properties(
    self,
    formula: str,
    T_min: float,
    T_max: float,
    step_k: int = 100,
    compound_names: Optional[List[str]] = None
) -> str:
    """
    Расчёт термодинамических свойств вещества (многофазный).
    """
    self.logger.info(f"Многофазный расчёт для {formula}, T_range=({T_min}, {T_max})K")
    
    # Поиск всех фаз (всегда многофазный подход)
    search_result = self.compound_searcher.search_all_phases(
        formula=formula,
        max_temperature=T_max,
        compound_names=compound_names
    )
    
    if not search_result.records:
        return f"❌ Вещество {formula} не найдено в БД"
    
    # Многофазный расчёт
    mp_result = self.calculator.calculate_multi_phase_properties(
        records=search_result.records,
        T_target=T_max
    )
    
    # Форматирование и возврат результата
    # ... (существующий код _calculate_multi_phase)
```

---

### Шаг 2: Обновление Orchestrator с интеграцией StaticDataManager

**Файл:** `src/thermo_agents/orchestrator.py`

#### ✏️ Изменить `__init__()`:

**Было (старая версия):**
```python
def __init__(self, db_path: str):
    self.db_connector = DatabaseConnector(db_path)
    self.sql_builder = SQLBuilder()
    self.compound_searcher = CompoundSearcher(
        sql_builder=self.sql_builder,
        db_connector=self.db_connector
        # ← Нет StaticDataManager
    )
    self.calculator = ThermodynamicCalculator()
    # ← Нет конфигурации многофазных расчётов
```

**Стало (новая версия):**
```python
def __init__(
    self,
    db_path: str,
    static_cache_dir: str = "data/static_compounds/",
    integration_points: int = 400
):
    """Инициализация оркестратора с многофазной поддержкой."""
    self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    # Инициализация StaticDataManager
    self.static_data_manager = StaticDataManager(
        data_dir=Path(static_cache_dir)
    )
    self.logger.info(f"✅ StaticDataManager: {static_cache_dir}")
    
    # Инициализация компонентов с новыми зависимостями
    self.db_connector = DatabaseConnector(db_path)
    self.sql_builder = SQLBuilder()
    
    # CompoundSearcher с поддержкой YAML кэша
    self.compound_searcher = CompoundSearcher(
        sql_builder=self.sql_builder,
        db_connector=self.db_connector,
        static_data_manager=self.static_data_manager  # ← Новая зависимость
    )
    
    # ThermodynamicCalculator с настройкой интегрирования
    self.calculator = ThermodynamicCalculator(
        num_integration_points=integration_points
    )
    
    # Formatter и Agent
    self.formatter = ReactionCalculationFormatter()
    self.agent = ThermodynamicAgent(
        compound_searcher=self.compound_searcher,
        calculator=self.calculator,
        formatter=self.formatter
        # ← Больше нет параметра use_multi_phase
    )
```

#### ❌ Удалить (если существует):
- Любые упоминания `use_multi_phase=False` или условную логику выбора режима
- Старые методы создания `CompoundSearcher` без `StaticDataManager`

---

### Шаг 3: Добавление конфигурации

**Файл:** `src/thermo_agents/orchestrator.py` (в начале файла)

#### ➕ Добавить:
```python
# Конфигурация многофазных расчётов
MULTI_PHASE_CONFIG = {
    "use_static_cache": True,  # Использовать YAML кэш
    "static_cache_dir": "data/static_compounds/",
    "min_segments_for_warning": 5,  # Предупреждать если > 5 сегментов
    "integration_points": 400,  # Точек для численного интегрирования
    "max_temperature": 6000.0,  # Максимальная температура расчёта (K)
}
```

**Использование конфигурации:**
```python
# В __init__():
static_cache_dir: str = MULTI_PHASE_CONFIG["static_cache_dir"],
integration_points: int = MULTI_PHASE_CONFIG["integration_points"]
```

---

### Шаг 4: Обновление логирования

**Файлы:** 
- `src/thermo_agents/thermodynamic_agent.py`
- `src/thermo_agents/search/compound_searcher.py`
- `src/thermo_agents/calculations/thermodynamic_calculator.py`

#### ➕ Добавить новые логи:

**В `CompoundSearcher.search_all_phases()`:**
```python
if self.static_data_manager:
    cached_data = self.static_data_manager.get_compound(formula)
    if cached_data:
        self.logger.info(f"⚡ Использован YAML кэш для {formula}")
        return self._convert_cached_to_search_result(cached_data)
```

**В `ThermodynamicCalculator.calculate_multi_phase_properties()`:**
```python
self.logger.info(
    f"Многофазный расчёт: {len(segments)} сегментов, "
    f"{len(phase_transitions)} переходов"
)

for transition in phase_transitions:
    self.logger.info(
        f"Фазовый переход: {transition.from_phase}→{transition.to_phase} "
        f"при {transition.temperature}K"
    )
```

**При обнаружении пробелов в покрытии:**
```python
if gap_detected:
    self.logger.warning(
        f"⚠️ Пробел в покрытии: {T_end_prev}K - {T_start_next}K "
        f"для {formula}"
    )
```

---

### Шаг 5: Удаление/обновление старых тестов

**Действия:**

#### ❌ Удалить тесты, специфичные для старой логики:
1. `tests/test_thermodynamic_agent.py` — если тестирует только одиночные расчёты
2. Любые тесты с `use_multi_phase=False`
3. Тесты метода `_calculate_single_phase()`

#### ✏️ Обновить существующие тесты:
```python
# Было:
def test_single_phase_calculation():
    agent = ThermodynamicAgent(..., use_multi_phase=False)
    result = agent.calculate_compound_properties("O2", 298, 500, 100)
    # ...

# Стало:
def test_o2_multi_phase_calculation():
    agent = ThermodynamicAgent(...)  # ← Нет параметра use_multi_phase
    result = agent.calculate_compound_properties("O2", 298, 500, 100)
    # Проверки адаптированы под многофазный формат
    assert "[Сегмент" in result or "O2" in result
```

#### ➕ Добавить новые regression-тесты:
```python
# tests/regression/test_old_queries_with_new_code.py
def test_simple_query_works_as_before():
    """Проверка, что простые запросы работают с новой системой."""
    orchestrator = Orchestrator(db_path="test.db")
    result = orchestrator.process_query("Рассчитай O2 при 500K")
    
    # Должен быть корректный ответ (хотя формат может немного отличаться)
    assert "O2" in result
    assert "500" in result
```

---

### Шаг 6: End-to-end тестирование

**Новые интеграционные тесты:**

#### ➕ Создать:
1. **`tests/integration/test_h2o_full_pipeline.py`** — H2O через s→l→g фазы
2. **`tests/integration/test_feo_multi_phase.py`** — FeO при 1700K (5 сегментов из ТЗ)
3. **`tests/integration/test_cao_sio2_reaction.py`** — Реакция с множественными переходами
4. **`tests/integration/test_yaml_cache_priority.py`** — Приоритет YAML → БД
5. **`tests/integration/test_all_phase_transitions.py`** — Все типы переходов (s→l, l→g, s→g)

**Сценарии покрытия:**
- ✅ Расчёт через 1 фазу (простой случай)
- ✅ Расчёт через 2 фазы (s→l или l→g)
- ✅ Расчёт через 3 фазы (s→l→g)
- ✅ Расчёт с пробелами в данных
- ✅ Расчёт с перекрывающимися диапазонами
- ✅ YAML кэш vs БД
- ✅ Реакции с несколькими веществами

---

### Шаг 7: Обновление operations.py

**Файл:** `src/thermo_agents/operations.py`

#### ✏️ Изменить все функции, использующие `ThermodynamicAgent`:

**Было:**
```python
def calculate_compound_data(formula: str, T_min: float, T_max: float, 
                           step_k: int = 100, use_multi_phase: bool = True):
    agent = ThermodynamicAgent(..., use_multi_phase=use_multi_phase)
    # ...
```

**Стало:**
```python
def calculate_compound_data(formula: str, T_min: float, T_max: float, 
                           step_k: int = 100):
    # ← Удалён параметр use_multi_phase
    agent = ThermodynamicAgent(...)  # ← Нет флага, всегда многофазный
    # ...
```

#### ❌ Удалить:
- Все параметры `use_multi_phase` из сигнатур функций
- Условную логику выбора между старым и новым подходом

## Критерии завершения (Big Bang)

### Код
- [ ] **Удалён** старый метод `_calculate_single_phase()` из `ThermodynamicAgent`
- [ ] **Удалён** метод `_needs_multi_phase_calculation()` из `ThermodynamicAgent`
- [ ] **Удалён** параметр `use_multi_phase` из всех компонентов
- [ ] **Удалена** условная логика выбора между одиночным и многофазным расчётом
- [ ] `ThermodynamicAgent` использует **только** многофазную логику
- [ ] `Orchestrator` инициализирует `StaticDataManager` по умолчанию
- [ ] `CompoundSearcher` всегда вызывает `search_all_phases()`
- [ ] Конфигурация `MULTI_PHASE_CONFIG` добавлена и используется
- [ ] Логирование многофазных операций работает везде

### Тесты
- [ ] **Удалены/обновлены** все тесты со старой логикой
- [ ] End-to-end тесты покрывают все ключевые сценарии (≥95%)
- [ ] Regression-тесты проверяют, что старые запросы работают
- [ ] Performance-тесты: типовой запрос < 500ms
- [ ] Все интеграционные тесты проходят (H2O, FeO, CaO+SiO2)

### Документация
- [ ] Документация пользователя обновлена (удалены упоминания флагов)
- [ ] README.md обновлён с примерами многофазных расчётов
- [ ] Примеры в `examples/` обновлены под новый API

### Качество
- [ ] Нет регрессий: все старые запросы работают корректно
- [ ] Производительность не деградировала (сравнение с baseline)
- [ ] Покрытие тестами ≥ 95% для изменённых файлов
- [ ] Code review пройден
- [ ] Git-ветка готова к merge в main

## Тесты (Big Bang Strategy)

### Unit-тесты (обновлённые)
- `tests/test_thermodynamic_agent_multiphase.py` — **только** многофазная логика
- `tests/test_orchestrator_multiphase.py` — тесты оркестратора без флагов

### Интеграционные тесты (новые)
- `tests/integration/test_h2o_full_pipeline.py` — H2O через s→l→g
- `tests/integration/test_feo_multi_phase.py` — FeO при 1700K (из ТЗ)
- `tests/integration/test_cao_sio2_reaction.py` — Реакция с переходами
- `tests/integration/test_yaml_cache_priority.py` — Приоритет YAML → БД
- `tests/integration/test_all_phase_transitions.py` — Все типы переходов

### Performance-тесты
- `tests/performance/test_multi_phase_speed.py` — Скорость многофазного расчёта
- `tests/performance/test_yaml_cache_impact.py` — Влияние YAML кэша на производительность

### Regression-тесты (критически важны)
- `tests/regression/test_old_queries_work.py` — Старые запросы работают с новой системой
- `tests/regression/test_output_format_compatibility.py` — Формат вывода совместим
- `tests/regression/test_calculation_accuracy.py` — Точность расчётов не изменилась

### Удаляемые тесты
- ❌ `tests/test_single_phase_*.py` — тесты старой одиночной логики
- ❌ Любые тесты с `use_multi_phase=False`
- ❌ Тесты методов `_calculate_single_phase()` и `_needs_multi_phase_calculation()`

## Риски (Big Bang Strategy)

### 🔴 Критические риски
- **Полная замена логики**: Невозможность быстрого отката без revert коммита
  - *Митигация*: Создать релизную ветку `release/v2-single-phase` перед внедрением
  - *Митигация*: Тщательное тестирование на dev-окружении минимум 3 дня
  - *Митигация*: Готовый план отката (rollback) с инструкциями
  
- **Регрессия существующего функционала**: Изменения могут сломать работающие запросы
  - *Митигация*: Полный набор regression-тестов (≥50 старых запросов)
  - *Митигация*: Сравнительное тестирование: старая vs новая версия
  - *Митигация*: Запуск всех существующих тестов перед merge

### 🟠 Высокие риски
- **Производительность**: Многофазные расчёты могут быть медленнее одиночных
  - *Митигация*: YAML кэш для 50+ распространённых веществ
  - *Митигация*: Профилирование с `cProfile` перед релизом
  - *Митигация*: Benchmark-тесты: новая система не медленнее >30% старой
  - *Митигация*: Кэширование результатов интегрирования

- **Изменение формата вывода**: Пользователи могут быть не готовы к новому формату
  - *Митигация*: Обновить документацию с примерами нового формата
  - *Митигация*: Уведомление пользователей о изменениях
  - *Митигация*: FAQ с объяснением преимуществ новой системы

### 🟡 Средние риски
- **Сложность отладки**: Многофазная логика сложнее для диагностики проблем
  - *Митигация*: Подробное логирование каждого шага (DEBUG уровень)
  - *Митигация*: Детальные сообщения об ошибках с указанием сегмента
  - *Митигация*: Валидация данных на каждом этапе

- **Неполнота данных БД**: Могут обнаружиться пробелы в данных
  - *Митигация*: Расширение YAML кэша для проблемных веществ
  - *Митигация*: Понятные сообщения об ошибках с рекомендациями
  - *Митигация*: Fallback на одиночную запись при критических пробелах

### 🟢 Низкие риски
- **Конфигурация**: Неправильные настройки по умолчанию
  - *Митигация*: Валидация `MULTI_PHASE_CONFIG` при старте
  - *Митигация*: Документированные значения с обоснованием

---

## План отката (Rollback Plan)

В случае критических проблем после внедрения:

### Быстрый откат (< 10 минут)
```bash
# 1. Вернуться к предыдущей версии
git revert <commit-hash-of-big-bang-merge>
git push origin main

# 2. Переключиться на резервную ветку
git checkout release/v2-single-phase
git push origin release/v2-single-phase --force-with-lease

# 3. Перезапустить сервисы
# (зависит от деплоя)
```

### Проверка после отката
- [ ] Запустить все старые тесты
- [ ] Проверить 10 типовых запросов пользователей
- [ ] Убедиться в восстановлении производительности
- [ ] Уведомить команду о откате

## Примечания

### Обоснование выбора Big Bang

**Почему отказались от Feature Flag (постепенного внедрения)?**

1. **Дублирование кода**: Поддержка двух логик (старой + новой) увеличивает технический долг
2. **Сложность тестирования**: Необходимо тестировать оба пути выполнения
3. **Архитектурная чистота**: Многофазный подход является правильным решением проблемы из ТЗ
4. **Все стадии завершены**: Stage 01-06 полностью протестированы и готовы к интеграции

**Условия для Big Bang:**
- ✅ Все предыдущие стадии (01-06) завершены и протестированы
- ✅ Есть полный набор regression-тестов
- ✅ Возможен быстрый откат через Git
- ✅ Команда готова к интенсивному тестированию

---

### План внедрения (Big Bang)

**День 0: Подготовка**
- Создать релизную ветку `release/v2-single-phase` (точка отката)
- Запустить полный набор тестов на старой версии (baseline)
- Подготовить документацию для пользователей
- Уведомить команду о предстоящих изменениях

**День 1: Внедрение кода**
- ✏️ Удалить старую логику из `ThermodynamicAgent`
- ✏️ Обновить `Orchestrator` с `StaticDataManager`
- ✏️ Обновить `operations.py`
- ➕ Добавить конфигурацию `MULTI_PHASE_CONFIG`
- ➕ Добавить новое логирование
- 🧪 Запустить все unit-тесты

**День 2-3: Тестирование**
- 🧪 Запустить интеграционные тесты (H2O, FeO, CaO+SiO2)
- 🧪 Запустить regression-тесты (старые запросы)
- 🧪 Запустить performance-тесты (сравнение с baseline)
- 🐛 Исправить обнаруженные баги
- 📊 Профилирование производительности

**День 4: Финальные проверки**
- ✅ Все тесты проходят (≥95% покрытие)
- ✅ Производительность приемлема (не хуже +30% от baseline)
- ✅ Документация обновлена
- ✅ Code review пройден
- ✅ План отката подготовлен

**День 5: Деплой**
- 🚀 Merge в `main`
- 🚀 Деплой на production
- 👀 Мониторинг метрик (время ответа, ошибки)
- 📢 Уведомление пользователей об обновлении

**День 6-7: Мониторинг**
- 📊 Анализ метрик производительности
- 🐛 Горячие исправления (hotfixes) при необходимости
- 📝 Документирование lessons learned
- 🎉 Успех или откат (если критические проблемы)

---

### Мониторинг после внедрения

**Ключевые метрики:**
1. **Производительность:**
   - Время ответа (p50, p95, p99)
   - Сравнение с baseline старой версии
   - Процент запросов > 1 секунда

2. **Качество:**
   - Количество ошибок расчёта (должно быть 0)
   - Процент успешных запросов (должно быть ≥99%)
   - Процент использования YAML кэша

3. **Использование:**
   - Количество многофазных расчётов
   - Средняя длина сегментов
   - Типы запросов пользователей

**Алерты:**
- 🔴 Критический: Время ответа p95 > 2 секунды
- 🔴 Критический: Процент ошибок > 5%
- 🟠 Предупреждение: Время ответа p95 > 1 секунда
- 🟠 Предупреждение: Процент ошибок > 1%
- 🟡 Информация: Пробелы в покрытии для распространённых веществ

**Действия при алертах:**
- Критический алерт → рассмотреть откат
- Предупреждение → анализ и оптимизация
- Информация → добавление в backlog

---

### Связь с другими этапами

**Интеграция всех стадий:**
- **Stage 01** → `CompoundSearcher.search_all_phases()` используется везде
- **Stage 02** → `TemperatureSegment` и `PhaseTransition` в логике расчётов
- **Stage 03** → `MultiPhaseProperties` как основной результат
- **Stage 04** → `StaticDataManager` интегрирован в `Orchestrator`
- **Stage 05** → `ThermodynamicCalculator.calculate_multi_phase_properties()` основной метод
- **Stage 06** → Форматтеры для многофазного вывода используются в `ThermodynamicAgent`

**Удаляемые компоненты:**
- ❌ Старая логика одиночных расчётов
- ❌ Методы `_calculate_single_phase()`, `_needs_multi_phase_calculation()`
- ❌ Параметры `use_multi_phase` везде
- ❌ Условная логика выбора режима
- ❌ Тесты для старой логики

---

## Примеры кода (Big Bang - только новая логика)

### Пример 1: Новый ThermodynamicAgent (БЕЗ старой логики)

```python
# src/thermo_agents/thermodynamic_agent.py
# ❌ УДАЛЕНО: use_multi_phase, _needs_multi_phase_calculation, _calculate_single_phase

from typing import Optional, List
import logging
from .search.compound_searcher import CompoundSearcher
from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter

class ThermodynamicAgent:
    """Агент для многофазных термодинамических расчётов."""
    
    def __init__(
        self,
        compound_searcher: CompoundSearcher,
        calculator: ThermodynamicCalculator,
        formatter: ReactionCalculationFormatter
        # ❌ УДАЛЁН: use_multi_phase: bool = True
    ):
        self.compound_searcher = compound_searcher
        self.calculator = calculator
        self.formatter = formatter
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_compound_properties(
        self,
        formula: str,
        T_min: float,
        T_max: float,
        step_k: int = 100,
        compound_names: Optional[List[str]] = None
    ) -> str:
        """
        Расчёт термодинамических свойств вещества (ТОЛЬКО многофазный).
        
        ❌ УДАЛЕНО: Условная логика выбора между одиночным и многофазным
        ✅ ВСЕГДА: Многофазный расчёт через search_all_phases()
        """
        self.logger.info(f"Многофазный расчёт для {formula}, T_range=({T_min}, {T_max})K")
        
        # ✅ Поиск всех фаз (ВСЕГДА)
        search_result = self.compound_searcher.search_all_phases(
            formula=formula,
            max_temperature=T_max,
            compound_names=compound_names
        )
        
        if not search_result.records:
            return f"❌ Вещество {formula} не найдено в БД"
        
        self.logger.info(
            f"Найдено {len(search_result.records)} записей, "
            f"{search_result.phase_count} фаз"
        )
        
        # ✅ Многофазный расчёт
        mp_result = self.calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=T_max
        )
        
        # ✅ Форматирование многофазного вывода
        output = self.formatter.format_compound_data_multi_phase(
            formula=formula,
            compound_name=search_result.records[0].name or formula,
            multi_phase_result=mp_result
        )
        
        # Построение таблицы с добавлением точек фазовых переходов
        temperatures = list(range(int(T_min), int(T_max) + 1, step_k))
        
        for transition in mp_result.phase_transitions:
            if T_min <= transition.temperature <= T_max:
                if transition.temperature not in temperatures:
                    temperatures.append(transition.temperature)
        
        temperatures = sorted(temperatures)
        
        # Расчёт для каждой температуры
        table_data = []
        for T in temperatures:
            mp_T = self.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                T_target=T
            )
            table_data.append({
                "T": T,
                "H": mp_T.H_final / 1000,  # кДж/моль
                "S": mp_T.S_final,
                "G": mp_T.G_final / 1000,
                "Cp": mp_T.Cp_final
            })
        
        table_output = self.formatter.format_properties_table(table_data)
        
        return f"{output}\n\n{table_output}"
    
    # ❌ УДАЛЕНЫ МЕТОДЫ:
    # - _needs_multi_phase_calculation() 
    # - _calculate_multi_phase() (логика перенесена в calculate_compound_properties)
    # - _calculate_single_phase()
```

### Пример 2: Новый Orchestrator (БЕЗ флагов)

```python
# src/thermo_agents/orchestrator.py
# ❌ УДАЛЕНО: use_multi_phase параметр и условная логика

import logging
from pathlib import Path
from .thermodynamic_agent import ThermodynamicAgent
from .search.compound_searcher import CompoundSearcher
from .search.database_connector import DatabaseConnector
from .search.sql_builder import SQLBuilder
from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .storage.static_data_manager import StaticDataManager

# ✅ Конфигурация многофазных расчётов (ВСЕГДА включено)
MULTI_PHASE_CONFIG = {
    "use_static_cache": True,
    "static_cache_dir": "data/static_compounds/",
    "min_segments_for_warning": 5,
    "integration_points": 400,
    "max_temperature": 6000.0,
}

class Orchestrator:
    """Оркестратор термодинамических расчётов (ТОЛЬКО многофазные)."""
    
    def __init__(
        self,
        db_path: str,
        static_cache_dir: str = None,
        integration_points: int = None
        # ❌ УДАЛЁН: use_multi_phase: Optional[bool] = None
    ):
        """
        Инициализация оркестратора.
        
        Args:
            db_path: Путь к БД
            static_cache_dir: Путь к YAML кэшу (по умолчанию из конфига)
            integration_points: Точек интегрирования (по умолчанию из конфига)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # ✅ Конфигурация (без флага use_multi_phase)
        self.static_cache_dir = (
            static_cache_dir or MULTI_PHASE_CONFIG["static_cache_dir"]
        )
        self.integration_points = (
            integration_points or MULTI_PHASE_CONFIG["integration_points"]
        )
        
        self.logger.info(
            f"Инициализация оркестратора (многофазный режим): "
            f"static_cache={self.static_cache_dir}, "
            f"integration_points={self.integration_points}"
        )
        
        # ✅ Инициализация компонентов
        self.db_connector = DatabaseConnector(db_path)
        self.sql_builder = SQLBuilder()
        
        # ✅ StaticDataManager (ВСЕГДА инициализируется)
        try:
            self.static_data_manager = StaticDataManager(
                data_dir=Path(self.static_cache_dir)
            )
            self.logger.info("✅ StaticDataManager инициализирован")
        except Exception as e:
            self.logger.warning(f"⚠️ StaticDataManager недоступен: {e}")
            self.static_data_manager = None
        
        # ✅ CompoundSearcher с StaticDataManager
        self.compound_searcher = CompoundSearcher(
            sql_builder=self.sql_builder,
            db_connector=self.db_connector,
            static_data_manager=self.static_data_manager
        )
        
        # ✅ ThermodynamicCalculator с настройкой
        self.calculator = ThermodynamicCalculator(
            num_integration_points=self.integration_points
        )
        
        # ✅ Formatter
        self.formatter = ReactionCalculationFormatter()
        
        # ✅ ThermodynamicAgent (БЕЗ параметра use_multi_phase)
        self.agent = ThermodynamicAgent(
            compound_searcher=self.compound_searcher,
            calculator=self.calculator,
            formatter=self.formatter
            # ❌ УДАЛЁН: use_multi_phase=self.use_multi_phase
        )
    
    def process_query(self, user_query: str) -> str:
        """
        Обработка пользовательского запроса (ТОЛЬКО многофазный расчёт).
        
        Args:
            user_query: Запрос пользователя
            
        Returns:
            Отформатированный ответ
        """
        self.logger.info(f"⚡ Многофазный расчёт для запроса: {user_query}")
        
        # Существующая логика классификации и обработки
        # ... (без условной логики use_multi_phase)
        
        return response

# ❌ УДАЛЕНО:
# - Параметр use_multi_phase из __init__
# - Присвоение self.use_multi_phase
# - Условная логика if self.use_multi_phase
# - Передача use_multi_phase в ThermodynamicAgent
```

---

### Пример 3: Обновлённый operations.py

```python
# src/thermo_agents/operations.py
# ❌ УДАЛЕНЫ: все параметры use_multi_phase

from typing import Optional, List
from .orchestrator import Orchestrator

def calculate_compound_data(
    formula: str, 
    T_min: float, 
    T_max: float, 
    step_k: int = 100,
    compound_names: Optional[List[str]] = None
    # ❌ УДАЛЁН: use_multi_phase: bool = True
) -> str:
    """
    Расчёт термодинамических свойств вещества.
    
    ВСЕГДА использует многофазный расчёт.
    """
    orchestrator = Orchestrator(db_path="data/thermo.db")
    # ❌ УДАЛЕНО: передача use_multi_phase
    
    return orchestrator.agent.calculate_compound_properties(
        formula=formula,
        T_min=T_min,
        T_max=T_max,
        step_k=step_k,
        compound_names=compound_names
    )

def calculate_reaction(
    reaction_str: str,
    T_min: float,
    T_max: float,
    step_k: int = 100
    # ❌ УДАЛЁН: use_multi_phase: bool = True
) -> str:
    """
    Расчёт термодинамики реакции.
    
    ВСЕГДА использует многофазный расчёт для всех веществ.
    """
    orchestrator = Orchestrator(db_path="data/thermo.db")
    # ❌ УДАЛЕНО: передача use_multi_phase
    
    # Парсинг реакции и расчёт
    # ... (без условной логики use_multi_phase)
    
    return result
```

---

### Пример 4: End-to-end тест (Big Bang)

```python
# tests/integration/test_multi_phase_end_to_end.py

import pytest
from src.thermo_agents.orchestrator import Orchestrator

@pytest.fixture
def orchestrator(tmp_path):
    """Оркестратор с временным кэшем."""
    test_db_path = "tests/fixtures/test_thermo.db"
    
    return Orchestrator(
        db_path=test_db_path,
        # ❌ УДАЛЁН: use_multi_phase=True (больше не нужен)
        static_cache_dir=str(tmp_path / "static_compounds")
    )

def test_feo_1700k_end_to_end(orchestrator):
    """End-to-end тест расчёта FeO при 1700K (пример из ТЗ)."""
    query = "Рассчитай термодинамические свойства FeO от 298K до 1700K"
    
    response = orchestrator.process_query(query)
    
    # Проверки многофазного вывода
    assert "FeO" in response
    assert "[Сегмент" in response  # ✅ ВСЕГДА многофазный формат
    assert "ФАЗОВЫЙ ПЕРЕХОД" in response
    assert "s → l" in response
    assert "1650" in response  # Tmelt
    
    # Проверка, что использовано несколько сегментов
    assert response.count("[Сегмент") >= 3

def test_h2o_phase_transitions_end_to_end(orchestrator):
    """End-to-end тест H2O через фазовые переходы."""
    query = "Рассчитай свойства H2O от 200K до 500K"
    
    response = orchestrator.process_query(query)
    
    # Проверки
    assert "H2O" in response or "Water" in response
    assert "273" in response or "Tmelt" in response  # Плавление
    assert "373" in response or "Tboil" in response  # Кипение

def test_reaction_cao_sio2_end_to_end(orchestrator):
    """End-to-end тест реакции CaO + SiO2 → CaSiO3."""
    query = "Рассчитай реакцию CaO + SiO2 = CaSiO3 от 298K до 1773K"
    
    response = orchestrator.process_query(query)
    
    # Проверки
    assert "CaO" in response
    assert "SiO2" in response
    assert "CaSiO3" in response
    assert "Данные веществ:" in response
    assert "Результаты расчёта:" in response

def test_yaml_cache_priority(tmp_path):
    """Тест приоритета YAML кэша над БД."""
    # Создать YAML файл для H2O
    yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  description: "Test Water"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -241826.0
      s298: 188.83
      f1: 33.066
      f2: 2.563
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    
    cache_dir = tmp_path / "static_compounds"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "H2O.yaml").write_text(yaml_content)
    
    # Создать оркестратор с кэшем
    orch = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(cache_dir)
    )
    
    query = "Рассчитай H2O при 500K"
    response = orch.process_query(query)
    
    # Проверка использования YAML кэша
    assert "H2O" in response
    assert "Test Water" in response or "Water" in response

# ❌ УДАЛЁН: test_backward_compatibility с use_multi_phase=False
# Теперь нет возможности отключить многофазный режим
```

---

### Пример 5: Regression-тест (адаптированный)

```python
# tests/regression/test_old_queries_work.py
# Проверка, что старые запросы работают с новой многофазной системой

import pytest
from src.thermo_agents.orchestrator import Orchestrator

# Список старых запросов, которые должны продолжать работать
OLD_QUERIES = [
    "Рассчитай O2 при 500K",
    "Данные по N2 от 298K до 1000K",
    "Реакция 2H2 + O2 = 2H2O при 1000K",
    "Покажи свойства CO2",
]

@pytest.mark.parametrize("query", OLD_QUERIES)
def test_old_query_works_with_multiphase(query):
    """
    Regression-тест: старые запросы работают с новой многофазной системой.
    
    ❌ УДАЛЕНО: Тестирование с use_multi_phase=False
    ✅ ВСЕГДА: Только многофазный режим
    """
    orchestrator = Orchestrator(
        db_path="tests/fixtures/test_thermo.db"
        # ❌ УДАЛЁН: use_multi_phase=True/False
    )
    
    try:
        response = orchestrator.process_query(query)
        
        # Базовые проверки
        assert len(response) > 50, "Ответ слишком короткий"
        assert "❌" not in response, "Ответ содержит ошибку"
        
        # ✅ Новая проверка: формат может быть многофазным
        # Это нормально, так как мы всегда используем многофазный расчёт
        
    except Exception as e:
        pytest.fail(f"Запрос '{query}' вызвал ошибку: {e}")

def test_simple_query_format_change():
    """
    Тест изменения формата вывода.
    
    Старые простые запросы теперь могут возвращать многофазный формат.
    Это ОЖИДАЕМОЕ ИЗМЕНЕНИЕ после Big Bang.
    """
    orchestrator = Orchestrator(db_path="tests/fixtures/test_thermo.db")
    
    query = "Рассчитай H2O от 298K до 500K"
    response = orchestrator.process_query(query)
    
    # Формат может включать "[Сегмент" (это нормально)
    assert "H2O" in response or "Water" in response
    assert "298" in response or "500" in response
    
    # Проверка корректности данных, а не формата
    # (формат изменился, но данные должны быть правильными)

# ❌ УДАЛЁН: test_old_format_with_flag_disabled()
# Больше нет флага для отключения многофазного режима
```

---

### Пример 6: Тест производительности

```python
# tests/performance/test_multi_phase_performance.py

import pytest
import time
from src.thermo_agents.orchestrator import Orchestrator

def test_multi_phase_query_performance():
    """Тест производительности многофазного запроса."""
    orchestrator = Orchestrator(db_path="tests/fixtures/test_thermo.db")
    
    query = "Рассчитай FeO от 298K до 1700K с шагом 100K"
    
    start = time.time()
    response = orchestrator.process_query(query)
    elapsed = time.time() - start
    
    # Типовой многофазный запрос должен занять < 500ms
    assert elapsed < 0.5, f"Запрос занял {elapsed*1000:.1f}ms (ожидалось < 500ms)"
    
    # Проверка корректности
    assert "FeO" in response
    assert len(response) > 100

@pytest.mark.parametrize("formula,max_T,expected_time", [
    ("H2O", 500, 0.3),
    ("FeO", 1700, 0.5),
    ("SiO2", 1500, 0.4),
    ("CO2", 1000, 0.3),
])
def test_performance_by_compound(formula, max_T, expected_time):
    """Тест производительности для различных веществ."""
    orchestrator = Orchestrator(db_path="tests/fixtures/test_thermo.db")
    
    query = f"Рассчитай {formula} от 298K до {max_T}K"
    
    start = time.time()
    response = orchestrator.process_query(query)
    elapsed = time.time() - start
    
    assert elapsed < expected_time, (
        f"{formula}: {elapsed*1000:.1f}ms > {expected_time*1000:.0f}ms"
    )
    
    # Проверка корректности
    assert formula in response

def test_yaml_cache_performance_boost(tmp_path):
    """Тест ускорения от YAML кэша."""
    # Создать YAML файл для быстрого доступа
    yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -241826.0
      s298: 188.83
      f1: 33.066
      f2: 2.563
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
  metadata:
    source_database: "test.db"
"""
    
    cache_dir = tmp_path / "static_compounds"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "H2O.yaml").write_text(yaml_content)
    
    # С кэшем
    orch_with_cache = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(cache_dir)
    )
    
    # Без кэша (пустая директория)
    empty_cache = tmp_path / "empty_cache"
    empty_cache.mkdir()
    orch_no_cache = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(empty_cache)
    )
    
    query = "Рассчитай H2O при 500K"
    
    # Измерение с кэшем
    start = time.time()
    orch_with_cache.process_query(query)
    time_with_cache = time.time() - start
    
    # Измерение без кэша
    start = time.time()
    orch_no_cache.process_query(query)
    time_no_cache = time.time() - start
    
    # YAML кэш должен быть быстрее (или хотя бы не медленнее)
    assert time_with_cache <= time_no_cache * 1.2, (
        f"YAML кэш медленнее: {time_with_cache:.3f}s vs {time_no_cache:.3f}s"
    )
```

---

## Резюме изменений кода (Big Bang)

### ❌ Что УДАЛЯЕТСЯ полностью:

**В `ThermodynamicAgent`:**
- Параметр `use_multi_phase: bool` из `__init__()`
- Метод `_needs_multi_phase_calculation()`
- Метод `_calculate_single_phase()`
- Условная логика `if needs_multi_phase and self.use_multi_phase:`
- Логирование "Использование одиночного расчёта"

**В `Orchestrator`:**
- Параметр `use_multi_phase` из `__init__()`
- Присвоение `self.use_multi_phase`
- Условная инициализация `if MULTI_PHASE_CONFIG["use_static_cache"]:`
- Передача `use_multi_phase` в `ThermodynamicAgent`
- Ключ `"enabled"` из `MULTI_PHASE_CONFIG`

**В `operations.py`:**
- Параметр `use_multi_phase` из всех функций
- Условная логика выбора режима расчёта

**В тестах:**
- Все тесты с `use_multi_phase=False`
- Метод `test_backward_compatibility()` с отключением флага
- Тесты методов `_calculate_single_phase()` и `_needs_multi_phase_calculation()`
- Файлы `tests/test_single_phase_*.py`

### ✅ Что ОСТАЁТСЯ/ДОБАВЛЯЕТСЯ:

**В `ThermodynamicAgent`:**
- Только метод `calculate_compound_properties()` с многофазной логикой
- Всегда вызов `search_all_phases()` вместо `search_compound()`
- Логирование "Многофазный расчёт для {formula}"

**В `Orchestrator`:**
- StaticDataManager инициализируется всегда
- CompoundSearcher всегда получает StaticDataManager
- ThermodynamicCalculator с настройкой integration_points
- Упрощённая инициализация без условной логики

**В тестах:**
- Regression-тесты адаптированы под многофазный формат
- Performance-тесты сравнивают с baseline
- End-to-end тесты для всех сценариев
- Тесты YAML кэша и приоритетов
