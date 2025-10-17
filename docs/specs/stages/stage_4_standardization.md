# Этап 4: Стандартизация кодовой базы

**Длительность**: 3-4 дня
**Приоритет**: Высокий
**Риски**: Низкие
**Зависимости**: Этапы 1-3 завершены

## Обзор

На этом этапе мы приводим кодовую базу к единым стандартам: унифицируем именование полей, стандартизируем импорты, извлекаем магические числа в константы и добавляем документацию. Это значительно улучшит читаемость и поддерживаемость кода.

---

## Задача 4.1: Единообразие именования фазовых переходов

### Проблема
Несогласованность в именовании полей фазовых переходов:
- В `DatabaseRecord`: `tmelt`, `tboil` (алиасы `MeltingPoint`, `BoilingPoint`)
- В реальной БД: `MeltingPoint`, `BoilingPoint`
- В коде фильтрации: смесь обоих подходов

### Решение
🔧 **СТАНДАРТИЗИРОВАТЬ на snake_case везде в Python коде**

### Файлы для обновления
- `src/thermo_agents/models/search.py` (DatabaseRecord)
- `src/thermo_agents/filtering/phase_resolver.py`
- `src/thermo_agents/filtering/temperature_resolver.py`
- `src/thermo_agents/filtering/filter_stages.py`

### План миграции

```python
# До (смешанный подход)
record.MeltingPoint  # из БД
record.tmelt         # в модели

# После (единый подход)
record.tmelt         # primary поле
record.tboil         # primary поле
# MeltingPoint/BoilingPoint как алиасы для совместимости
```

**Шаги**:
1. Обновить `DatabaseRecord` модель для использования `tmelt`, `tboil`
2. Добавить property-алиасы для обратной совместимости
3. Обновить все использования в коде фильтрации
4. Обновить тесты
5. Запустить валидацию

---

## Задача 4.2: Консолидация импортов

### Проблема
Множественные относительные импорты и дублирование:
```python
from src.thermo_agents.models.search import CompoundSearchResult  # Absolute
from ..models.search import DatabaseRecord  # Relative
```

### Решение
🔧 **СТАНДАРТИЗИРОВАТЬ на абсолютные импорты**

### Мотивация
- Согласно инструкциям в `.github/copilot-instructions.md`
- Улучшение читаемости и понятности зависимостей
- Упрощение рефакторинга и анализа кода

### План миграции

```bash
# Найти все относительные импорты
find src/ -name "*.py" -exec grep -l "from \.\." {} \;

# Заменить паттерны
from ..models.search import DatabaseRecord
# на
from src.thermo_agents.models.search import DatabaseRecord

from .utils import helper
# на
from src.thermo_agents.current_module.utils import helper
```

**Автоматизация**:
```python
# скрипт для автоматической замены
import os
import re

def fix_imports(file_path):
    with open(file_path, 'r') as f:
        content = f.read()

    # Заменить относительные импорты
    content = re.sub(r'from \.\.(\w+)\.', r'from src.thermo_agents.\1.', content)
    content = re.sub(r'from \.(\w+)', r'from src.thermo_agents.\1', content)

    with open(file_path, 'w') as f:
        f.write(content)
```

### Файлы для обновления
Все файлы в `src/thermo_agents/`:
- `filtering/*.py`
- `search/*.py`
- `aggregation/*.py`
- `models/*.py`
- `thermodynamic_agent.py`
- `orchestrator.py`
- `agent_storage.py`

---

## Задача 4.3: Извлечение магических чисел в константы

### Проблема
Использование магических чисел в коде фильтрации и scoring:
- `0.6`, `0.4` в `PhaseBasedTemperatureStage` (веса)
- `100`, `200`, `1500` в `PhaseResolver` (температурные пороги)
- `3` в `fallback` (top-N записей)

### Решение
🔧 **ИЗВЛЕЧЬ в именованные константы в начале модулей**

### Новые константы

```python
# src/thermo_agents/filtering/constants.py

# Temperature thresholds for phase estimation (Kelvin)
SOLID_PHASE_MAX_TEMP = 200
LIQUID_PHASE_TYPICAL_MIN = 273
LIQUID_PHASE_TYPICAL_MAX = 373
GAS_PHASE_MIN_TEMP = 1500

# Scoring weights
DEFAULT_RELIABILITY_WEIGHT = 0.6
DEFAULT_COVERAGE_WEIGHT = 0.4

# Fallback configuration
FALLBACK_TOP_RECORDS_COUNT = 3
FALLBACK_MIN_RECORDS_THRESHOLD = 1

# Filtering thresholds
MIN_TEMPERATURE_COVERAGE_RATIO = 0.5
MAX_RELIABILITY_CLASS = 3  # Classes 1-3 considered high quality

# Database query limits
DEFAULT_QUERY_LIMIT = 100
MAX_QUERY_LIMIT = 1000
```

### Файлы для обновления

1. **phase_based_temperature_stage.py**:
   ```python
   # До
   weight_reliability = 0.6
   weight_coverage = 0.4

   # После
   from src.thermo_agents.filtering.constants import (
       DEFAULT_RELIABILITY_WEIGHT,
       DEFAULT_COVERAGE_WEIGHT
   )
   weight_reliability = DEFAULT_RELIABILITY_WEIGHT
   weight_coverage = DEFAULT_COVERAGE_WEIGHT
   ```

2. **phase_resolver.py**:
   ```python
   # До
   if temp < 200:
       return "s"
   elif temp < 1500:
       return "l"

   # После
   from src.thermo_agents.filtering.constants import (
       SOLID_PHASE_MAX_TEMP,
       GAS_PHASE_MIN_TEMP
   )
   if temp < SOLID_PHASE_MAX_TEMP:
       return "s"
   elif temp < GAS_PHASE_MIN_TEMP:
       return "l"
   ```

3. **filter_pipeline.py**:
   ```python
   # До
   if len(records) < 3:
       return fallback_records[:3]

   # После
   from src.thermo_agents.filtering.constants import (
       FALLBACK_TOP_RECORDS_COUNT,
       FALLBACK_MIN_RECORDS_THRESHOLD
   )
   if len(records) < FALLBACK_MIN_RECORDS_THRESHOLD:
       return fallback_records[:FALLBACK_TOP_RECORDS_COUNT]
   ```

---

## Задача 4.4: Упрощение сложных условий

### Проблема
Множественные вложенные условия в фильтрации затрудняют понимание логики:
- `filter_pipeline.py`: `_prefilter_exclude_ions()` с вложенными if
- `phase_resolver.py`: `_determine_phase()` с сложной логикой
- `reaction_validator.py`: Nested conditions в `validate_reaction()`

### Решение
🔧 **УПРОСТИТЬ через early returns и извлечение условий в методы**

### Пример рефакторинга

**До**:
```python
def complex_condition(arg1, arg2, arg3):
    if arg1:
        if arg2:
            if arg3:
                return result1
            else:
                return result2
        else:
            return result3
    else:
        return result4
```

**После**:
```python
def complex_condition(arg1, arg2, arg3):
    if not arg1:
        return result4
    if not arg2:
        return result3
    if not arg3:
        return result2
    return result1

# Или с извлечением условий
def complex_condition(arg1, arg2, arg3):
    if not _is_valid_primary_condition(arg1):
        return result4
    if not _is_valid_secondary_condition(arg2):
        return result3
    if not _is_valid_final_condition(arg3):
        return result2
    return result1

def _is_valid_primary_condition(arg1) -> bool:
    """Валидация основного условия."""
    return arg1 is not None and arg1 > 0
```

### Конкретные файлы для рефакторинга

1. **filter_pipeline.py**:
   - `_prefilter_exclude_ions()` → extract `should_exclude_ionic_form()`
   - `_apply_fallback()` → extract conditions in separate methods

2. **phase_resolver.py**:
   - `_determine_phase()` → use early returns
   - `estimate_phase_from_temperature()` → extract helper methods

3. **reaction_validator.py**:
   - `validate_reaction()` → simplify nested conditions
   - `_check_element_balance()` → use early returns

---

## Задача 4.5: Добавление документации

### Проблема
Неполная документация в некоторых модулях, отсутствие примеров использования.

### Решение
✏️ **ДОБАВИТЬ docstrings в формате Google Style ко всем публичным классам и методам**

### Стандарт документации

```python
def method(self, param: str, optional_param: int = 0) -> Result:
    """Краткое описание метода.

    Подробное описание функциональности метода,
    включая edge cases и особенности реализации.

    Args:
        param: Описание обязательного параметра
        optional_param: Описание опционального параметра

    Returns:
        Описание возвращаемого значения

    Raises:
        ValueError: Когда и почему возникает ошибка
        TypeError: При неверном типе параметра

    Example:
        >>> result = method("test", optional_param=5)
        >>> result.status
        'success'
    """
    pass
```

### Файлы для обновления
Все модули в `src/thermo_agents/` без полной документации:
- Основные классы во всех модулях
- Публичные методы в компонентах
- Функции в `utils/`
- Модели в `models/`

---

## Порядок выполнения

### Шаг 1: Подготовка (0.5 дня)
```bash
# Создать ветку
git checkout -b refactor/stage-4-standardization

# Создать файл констант
touch src/thermo_agents/filtering/constants.py

# Найти все магические числа
grep -rn "\b[0-9]\+\b" src/thermo_agents/filtering/ | grep -v "#"
```

### Шаг 2: Стандартизация именования (1 день)
1. Обновить `DatabaseRecord` для `tmelt`/`tboil`
2. Добавить property-алиасы
3. Обновить использования в коде
4. Обновить тесты

### Шаг 3: Консолидация импортов (0.5 дня)
1. Написать скрипт для автоматической замены
2. Применить ко всем файлам
3. Проверить корректность

### Шаг 4: Константы и условия (1 день)
1. Извлечь магические числа в `constants.py`
2. Обновить все использования
3. Упростить вложенные условия
4. Тестирование

### Шаг 5: Документация (1 день)
1. Добавить docstrings ко всем публичным API
2. Проверить форматирование
3. Обновить README

### Шаг 6: Валидация (0.5 дня)
```bash
# Запустить все тесты
uv run pytest tests/ -v

# Проверить стиль кода
uv run ruff check src/thermo_agents/
uv run ruff format src/thermo_agents/

# Проверить импорты
uv run python -m py_compile src/thermo_agents/**/*.py
```

---

## Ожидаемые результаты

### Улучшение качества кода
- ✅ **Единообразие**: Консистентное именование и стиль
- ✅ **Читаемость**: Понятные константы вместо магических чисел
- ✅ **Поддерживаемость**: Простые условия вместо вложенных конструкций
- ✅ **Документация**: Полные docstrings для всех публичных API

### Инструменты и процессы
- ✅ **Автоматизация**: Скрипты для миграции импортов
- ✅ **Валидация**: Linting и форматирование
- ✅ **Тестирование**: Все тесты продолжают проходить

### Стандарты
- ✅ **PEP 8**: Соответствие стандартам Python
- ✅ **Google Style**: Единый формат документации
- ✅ **Абсолютные импорты**: Понятные зависимости

---

## Критерии завершения

- [ ] Все поля фазовых переходов используют snake_case (`tmelt`, `tboil`)
- [ ] Все импорты абсолютные и консистентные
- [ ] Магические числа извлечены в `constants.py`
- [ ] Сложные условия упрощены через early returns
- [ ] Все публичные классы и методы имеют docstrings
- [ ] Все тесты проходят
- [ ] Linting не показывает ошибок
- [ ] Code review завершён

---

## Автоматизация валидации

Добавить в `pyproject.toml`:
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "D"]
ignore = ["D203", "D212"]

[tool.ruff.isort]
known-first-party = ["src"]

[tool.ruff.pydocstyle]
convention = "google"
```

---

## Следующий этап

После завершения Этапа 4 можно переходить к **Этапу 5: Архитектурные улучшения**, который включает рефакторинг fallback стратегий и разделение сложных компонентов.