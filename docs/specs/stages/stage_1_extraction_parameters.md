# Этап 1: Расширение ExtractedReactionParameters и обновление промпта

**Статус:** Не начат  
**Приоритет:** Высокий  
**Зависимости:** Нет

---

## Цель

Добавить поддержку классификации запросов пользователя на два типа:
- `compound_data` — запрос данных по отдельному веществу
- `reaction_calculation` — расчёт термодинамики реакции

Расширить модель `ExtractedReactionParameters` для хранения типа запроса и шага температуры.

---

## Основные задачи

### 1.1. Расширение модели ExtractedReactionParameters

**Файл:** `src/thermo_agents/models/extraction.py`

**Изменения:**
- Добавить поле `query_type: Literal["compound_data", "reaction_calculation"]`
- Добавить поле `temperature_step_k: int = 100` (диапазон 25-250K)
- Добавить валидаторы для проверки согласованности данных

### 1.2. Обновление промпта THERMODYNAMIC_EXTRACTION_PROMPT

**Файл:** `src/thermo_agents/prompts.py`

**Изменения:**
- Добавить инструкции по классификации типа запроса
- Добавить правила извлечения `temperature_step_k` из запроса пользователя
- Добавить примеры для обоих типов запросов
- Обновить JSON-схему ответа

### 1.3. Создание тестов классификации

**Файл:** `tests/test_query_classification.py` (новый)

**Содержание:**
- Тесты для `compound_data` (одно вещество, без реакции)
- Тесты для `reaction_calculation` (реакция с несколькими веществами)
- Тесты валидации `temperature_step_k`
- Тесты согласованности полей модели

---

## Критерии приёмки

- ✅ Модель `ExtractedReactionParameters` содержит новые поля
- ✅ Валидаторы корректно проверяют согласованность данных
- ✅ Промпт включает примеры классификации для обоих типов запросов
- ✅ Все тесты проходят успешно
- ✅ Документация обновлена

---

## Детальные подзадачи

### 1.1.1. Добавление полей в ExtractedReactionParameters

**Местоположение:** `src/thermo_agents/models/extraction.py`

**Код:**
```python
from typing import Literal
from pydantic import BaseModel, Field, field_validator

class ExtractedReactionParameters(BaseModel):
    # Существующие поля...
    balanced_equation: str
    all_compounds: List[str]
    reactants: List[str]
    products: List[str]
    temperature_range_k: Tuple[float, float]
    extraction_confidence: float
    missing_fields: List[str]
    compound_names: Dict[str, List[str]]
    
    # НОВЫЕ ПОЛЯ
    query_type: Literal["compound_data", "reaction_calculation"] = Field(
        ...,
        description="Тип запроса: данные по веществу или расчёт реакции"
    )
    
    temperature_step_k: int = Field(
        default=100,
        ge=25,
        le=250,
        description="Шаг температуры для таблиц, K (25-250)"
    )
```

**Мотивация:**
- `query_type` позволяет маршрутизировать обработку на уровне Orchestrator
- `temperature_step_k` даёт пользователю контроль над детализацией таблиц

**Риски:**
- Ломающее изменение: старые тесты могут сломаться
- Необходимость обновления всех мест создания `ExtractedReactionParameters`

### 1.1.2. Добавление валидаторов

**Валидатор для query_type:**
```python
@field_validator('query_type')
@classmethod
def validate_query_type_consistency(cls, v, info):
    """Проверка согласованности query_type с другими полями."""
    values = info.data
    
    if v == "compound_data":
        # Для compound_data должно быть одно вещество
        if len(values.get('all_compounds', [])) > 1:
            raise ValueError(
                f"compound_data должен содержать одно вещество, "
                f"получено: {len(values['all_compounds'])}"
            )
        # Реагенты и продукты должны быть пустыми
        if values.get('reactants') or values.get('products'):
            raise ValueError(
                "compound_data не должен содержать reactants/products"
            )
    
    elif v == "reaction_calculation":
        # Для reaction_calculation должна быть реакция
        if len(values.get('all_compounds', [])) < 2:
            raise ValueError(
                f"reaction_calculation требует минимум 2 вещества, "
                f"получено: {len(values.get('all_compounds', []))}"
            )
        # Должно быть уравнение реакции
        if not values.get('balanced_equation') or values['balanced_equation'] == "N/A":
            raise ValueError(
                "reaction_calculation требует balanced_equation"
            )
    
    return v
```

**Валидатор для temperature_step_k:**
```python
@field_validator('temperature_step_k')
@classmethod
def validate_temperature_step(cls, v):
    """Проверка шага температуры."""
    if not (25 <= v <= 250):
        raise ValueError(
            f"temperature_step_k должен быть в диапазоне 25-250K, получено: {v}"
        )
    # Рекомендация: шаг должен быть кратен 25
    if v % 25 != 0:
        import warnings
        warnings.warn(
            f"Рекомендуется использовать шаг кратный 25K "
            f"(25, 50, 100, 150, 200, 250), получено: {v}K"
        )
    return v
```

### 1.2.1. Обновление промпта: секция классификации

**Местоположение:** `src/thermo_agents/prompts.py`

**Добавить в промпт:**
```markdown
# ПРАВИЛА КЛАССИФИКАЦИИ:

## compound_data (данные по веществу):
✓ Запрос содержит одно вещество
✓ Нет символов реакции (→, =, ⇄, <=>)
✓ Ключевые слова: "данные", "свойства", "таблица для", "информация о"
✓ Примеры:
  - "Дай таблицу для H2O при 300-600K"
  - "Свойства WCl6 с шагом 50 градусов"
  - "Термодинамические данные для воды"

## reaction_calculation (расчёт реакции):
✓ Присутствуют 2+ вещества
✓ Есть символы реакции (→, =, ⇄, <=>)
✓ Ключевые слова: "реакция", "рассчитай", "баланс", "термодинамика"
✓ Примеры:
  - "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
  - "Рассчитай термодинамику хлорирования вольфрама"
```

### 1.2.2. Обновление промпта: извлечение temperature_step_k

**Добавить инструкции:**
```markdown
6. **Шаг температуры** (temperature_step_k)
   - Извлекается из фраз: "с шагом X градусов", "каждые X кельвинов", "через X K"
   - Диапазон: 25-250K
   - По умолчанию: 100K
   - Примеры: 
     * "с шагом 50 градусов" → 50
     * "каждые 25K" → 25
     * "через 150 кельвинов" → 150
```

### 1.2.3. Добавление примеров в промпт

**Примеры для compound_data:**
```json
// Запрос: "Дай таблицу для H2O при 300-600K с шагом 50 градусов"
{
  "query_type": "compound_data",
  "temperature_step_k": 50,
  "balanced_equation": "",
  "all_compounds": ["H2O"],
  "reactants": [],
  "products": [],
  "temperature_range_k": [300, 600],
  "extraction_confidence": 1.0,
  "compound_names": {"H2O": ["Water", "вода"]}
}
```

**Примеры для reaction_calculation:**
```json
// Запрос: "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K, считай каждые 25 кельвинов"
{
  "query_type": "reaction_calculation",
  "temperature_step_k": 25,
  "balanced_equation": "2 W + 4 Cl2 + O2 → 2 WOCl4",
  "all_compounds": ["W", "Cl2", "O2", "WOCl4"],
  "reactants": ["W", "Cl2", "O2"],
  "products": ["WOCl4"],
  "temperature_range_k": [600, 900],
  "extraction_confidence": 1.0,
  "compound_names": {
    "W": ["Tungsten", "Wolfram"],
    "Cl2": ["Chlorine"],
    "O2": ["Oxygen"],
    "WOCl4": ["Tungsten oxychloride"]
  }
}
```

### 1.3.1. Создание тестового файла

**Файл:** `tests/test_query_classification.py`

**Структура:**
```python
import pytest
from src.thermo_agents.models.extraction import ExtractedReactionParameters

class TestQueryClassification:
    """Тесты классификации типов запросов."""
    
    def test_compound_data_single_substance(self):
        """Один вещество → compound_data"""
        # ...
    
    def test_reaction_calculation_with_arrow(self):
        """Наличие → и 2+ вещества → reaction_calculation"""
        # ...
    
    def test_temperature_step_validation(self):
        """Проверка валидации шага температуры"""
        # ...
    
    def test_consistency_validation_compound_data_multiple_substances(self):
        """compound_data с несколькими веществами → ошибка"""
        # ...
```

### 1.3.2. Тесты валидации temperature_step_k

**Тест-кейсы:**
```python
@pytest.mark.parametrize("step_k,expected_valid", [
    (25, True),   # Минимум
    (50, True),   # Валидный
    (100, True),  # По умолчанию
    (250, True),  # Максимум
    (10, False),  # Слишком маленький
    (300, False), # Слишком большой
    (37, True),   # Некратный 25 (warning, но валидный)
])
def test_temperature_step_boundaries(step_k, expected_valid):
    if expected_valid:
        params = ExtractedReactionParameters(
            query_type="compound_data",
            temperature_step_k=step_k,
            all_compounds=["H2O"],
            # ... остальные поля
        )
        assert params.temperature_step_k == step_k
    else:
        with pytest.raises(ValueError):
            ExtractedReactionParameters(
                query_type="compound_data",
                temperature_step_k=step_k,
                all_compounds=["H2O"],
                # ...
            )
```

### 1.3.3. Тесты согласованности полей

**Примеры:**
```python
def test_compound_data_must_have_one_compound():
    """compound_data требует ровно одно вещество"""
    with pytest.raises(ValueError, match="одно вещество"):
        ExtractedReactionParameters(
            query_type="compound_data",
            all_compounds=["H2O", "CO2"],  # Два!
            # ...
        )

def test_reaction_calculation_requires_equation():
    """reaction_calculation требует уравнение реакции"""
    with pytest.raises(ValueError, match="balanced_equation"):
        ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="",  # Пустое!
            all_compounds=["H2O", "CO2"],
            # ...
        )
```

---

## План миграции

### Шаг 1: Обратная совместимость
- Сделать `query_type` опциональным на переходный период
- Добавить автоматическое определение типа в `__init__` при отсутствии явного значения

### Шаг 2: Обновление существующих тестов
- Найти все места создания `ExtractedReactionParameters`
- Добавить значения для новых полей

### Шаг 3: Документирование изменений
- Обновить `CHANGELOG.md`
- Добавить migration guide для пользователей API

---

