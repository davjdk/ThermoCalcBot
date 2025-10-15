# Этап 5: Обновление Thermodynamic Agent

**Длительность:** 1-2 дня  
**Приоритет:** Средний  
**Статус:** Не начат  
**Зависимости:** Этап 4

---

## Описание

Обновление агента извлечения параметров для работы с новой архитектурой. Единственный LLM-агент в системе, отвечающий за парсинг естественного языка.

---

## Основные задачи

### 1. Обновить модель `ExtractedReactionParameters`

**Файл:** `src/thermo_agents/models/extraction.py`

**Новая модель:**
```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Tuple, Optional

class ExtractedReactionParameters(BaseModel):
    """Параметры реакции, извлечённые из запроса пользователя."""
    
    balanced_equation: str = Field(
        ...,
        description="Уравненное уравнение реакции, например: 'TiO2 + 2HCl → TiCl4 + H2O'"
    )
    
    all_compounds: List[str] = Field(
        ...,
        max_length=10,
        description="Все вещества в реакции (до 10 веществ)"
    )
    
    reactants: List[str] = Field(
        ...,
        description="Список реагентов (левая часть уравнения)"
    )
    
    products: List[str] = Field(
        ...,
        description="Список продуктов (правая часть уравнения)"
    )
    
    temperature_range_k: Tuple[float, float] = Field(
        ...,
        description="Температурный диапазон в Кельвинах (tmin, tmax)"
    )
    
    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность извлечения (0.0-1.0)"
    )
    
    missing_fields: List[str] = Field(
        default_factory=list,
        description="Список полей, которые не удалось извлечь"
    )
    
    @field_validator('all_compounds')
    @classmethod
    def validate_compounds_count(cls, v):
        """Проверка максимального количества веществ."""
        if len(v) > 10:
            raise ValueError(f"Превышено максимальное количество веществ: {len(v)} > 10")
        return v
    
    @field_validator('temperature_range_k')
    @classmethod
    def validate_temperature_range(cls, v):
        """Проверка корректности температурного диапазона."""
        tmin, tmax = v
        if tmin < 0:
            raise ValueError(f"Tmin не может быть отрицательной: {tmin}")
        if tmax <= tmin:
            raise ValueError(f"Tmax должен быть больше Tmin: {tmax} <= {tmin}")
        if tmax > 10000:
            raise ValueError(f"Tmax слишком высокая: {tmax} > 10000K")
        return v
    
    def is_complete(self) -> bool:
        """Проверка полноты извлечённых данных."""
        required_fields = [
            'balanced_equation',
            'reactants',
            'products',
            'temperature_range_k'
        ]
        return len(self.missing_fields) == 0 and all(
            getattr(self, field) for field in required_fields
        )
```

**Задачи:**
- [ ] Создать `src/thermo_agents/models/extraction.py`
- [ ] Реализовать модель с валидацией
- [ ] Добавить метод `is_complete()`
- [ ] Написать unit-тесты для валидаторов

---

### 2. Обновить промпт для извлечения

**Файл:** `src/thermo_agents/prompts.py`

**Новый промпт:**
```python
THERMODYNAMIC_EXTRACTION_PROMPT = """
Ты — эксперт по термодинамике и химии. Твоя задача — извлечь параметры химической реакции из запроса пользователя.

# Входные данные:
Запрос пользователя: {user_query}

# Задача:
Извлеки следующие параметры:
1. **Уравненное уравнение реакции** — сбалансируй стехиометрические коэффициенты
2. **Список всех веществ** (до 10 веществ, включая реагенты и продукты)
3. **Реагенты** (левая часть уравнения)
4. **Продукты** (правая часть уравнения)
5. **Температурный диапазон** в Кельвинах (tmin, tmax)

# Важные правила:
- Стехиометрические коэффициенты НЕ используются в дальнейшей логике поиска
- Максимум 10 веществ в реакции
- Температурный диапазон обязателен (если не указан, используй 298-1000K по умолчанию)
- Формулы веществ — без фаз в скобках (например, "H2O", а не "H2O(g)")

# Примеры:

## Пример 1:
Запрос: "Хлорирование оксида титана при 600-900K"
Ответ:
{{
  "balanced_equation": "TiO2 + 2Cl2 → TiCl4 + O2",
  "all_compounds": ["TiO2", "Cl2", "TiCl4", "O2"],
  "reactants": ["TiO2", "Cl2"],
  "products": ["TiCl4", "O2"],
  "temperature_range_k": [600, 900],
  "extraction_confidence": 0.95,
  "missing_fields": []
}}

## Пример 2:
Запрос: "Восстановление оксида железа водородом"
Ответ:
{{
  "balanced_equation": "Fe2O3 + 3H2 → 2Fe + 3H2O",
  "all_compounds": ["Fe2O3", "H2", "Fe", "H2O"],
  "reactants": ["Fe2O3", "H2"],
  "products": ["Fe", "H2O"],
  "temperature_range_k": [298, 1000],
  "extraction_confidence": 0.85,
  "missing_fields": ["temperature_range"]
}}

## Пример 3 (сложная реакция):
Запрос: "Синтез аммиака из азота и водорода при 400-500°C"
Ответ:
{{
  "balanced_equation": "N2 + 3H2 → 2NH3",
  "all_compounds": ["N2", "H2", "NH3"],
  "reactants": ["N2", "H2"],
  "products": ["NH3"],
  "temperature_range_k": [673, 773],
  "extraction_confidence": 1.0,
  "missing_fields": []
}}

# Твой ответ (JSON):
"""

**Задачи:**
- [ ] Обновить промпт с поддержкой до 10 веществ
- [ ] Убрать упоминания о важности стехиометрических коэффициентов
- [ ] Добавить примеры с разным количеством веществ (2-10)
- [ ] Протестировать промпт на реальных запросах

---

### 3. Добавить валидацию обязательных полей

**Файл:** `src/thermo_agents/thermodynamic_agent.py`

**Обновлённый метод:**
```python
class ThermodynamicAgent:
    """Агент извлечения параметров из естественного языка."""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    async def extract_parameters(
        self, 
        user_query: str
    ) -> ExtractedReactionParameters:
        """
        Извлечение параметров из запроса пользователя.
        
        Args:
            user_query: Запрос на естественном языке
            
        Returns:
            ExtractedReactionParameters
            
        Raises:
            ValidationError: Если извлечённые данные некорректны
        """
        # Формирование промпта
        prompt = THERMODYNAMIC_EXTRACTION_PROMPT.format(user_query=user_query)
        
        # Запрос к LLM
        response = await self.llm_client.generate(prompt)
        
        # Парсинг JSON
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM вернул некорректный JSON: {e}")
        
        # Валидация через Pydantic
        try:
            params = ExtractedReactionParameters(**data)
        except ValidationError as e:
            raise ValueError(f"Некорректные параметры: {e}")
        
        # Проверка полноты
        if not params.is_complete():
            missing = ", ".join(params.missing_fields)
            raise ValueError(
                f"Не удалось извлечь обязательные поля: {missing}. "
                f"Пожалуйста, уточните запрос."
            )
        
        return params
```

**Задачи:**
- [ ] Обновить метод `extract_parameters()`
- [ ] Добавить обработку `ValidationError`
- [ ] Добавить проверку `is_complete()`
- [ ] Добавить информативные сообщения об ошибках

---

### 4. Убрать зависимость от стехиометрических коэффициентов

**Изменения:**
- Стехиометрические коэффициенты извлекаются для `balanced_equation`, но **НЕ используются** в логике поиска
- Все вещества в списке `all_compounds` обрабатываются независимо
- Поиск в БД выполняется для каждого вещества отдельно, без учёта коэффициентов

**Пример:**
```python
# Уравнение: "2H2 + O2 → 2H2O"
# Коэффициенты: 2, 1, 2 — НЕ влияют на поиск

# Логика поиска:
for compound in ["H2", "O2", "H2O"]:
    search_compound(compound, temperature_range)  # Без учёта коэффициентов
```

**Задачи:**
- [ ] Убедиться, что стехиометрические коэффициенты не влияют на логику
- [ ] Обновить документацию
- [ ] Добавить тест, подтверждающий независимость поиска от коэффициентов

---

### 5. Написать unit-тесты

**Файл:** `tests/test_thermodynamic_agent.py`

**Тестовые случаи:**

**TC1: Простая реакция**
```python
async def test_extract_simple_reaction():
    agent = ThermodynamicAgent(llm_client)
    query = "Горение водорода при 500-800K"
    
    params = await agent.extract_parameters(query)
    
    assert params.balanced_equation == "2H2 + O2 → 2H2O"
    assert len(params.all_compounds) == 3
    assert params.is_complete()
```

**TC2: Реакция с 10 веществами**
```python
async def test_extract_complex_reaction():
    agent = ThermodynamicAgent(llm_client)
    query = "Сложная реакция с 10 веществами..."
    
    params = await agent.extract_parameters(query)
    
    assert len(params.all_compounds) <= 10
    assert params.is_complete()
```

**TC3: Неполный запрос**
```python
async def test_extract_incomplete_query():
    agent = ThermodynamicAgent(llm_client)
    query = "Реакция без температуры"
    
    with pytest.raises(ValueError, match="Не удалось извлечь"):
        await agent.extract_parameters(query)
```

**Задачи:**
- [ ] Написать >10 unit-тестов
- [ ] Тестировать валидацию температурного диапазона
- [ ] Тестировать валидацию количества веществ
- [ ] Использовать моки для LLM

---

## Артефакты этапа

### Файлы для создания/обновления:
1. `src/thermo_agents/models/extraction.py` (новый)
2. `src/thermo_agents/prompts.py` (обновить)
3. `src/thermo_agents/thermodynamic_agent.py` (обновить)
4. `tests/test_thermodynamic_agent.py` (обновить)

---

## Критерии завершения этапа

✅ **Обязательные:**
1. Модель `ExtractedReactionParameters` обновлена с валидацией
2. Промпт поддерживает до 10 веществ
3. Стехиометрические коэффициенты не влияют на логику поиска
4. Все unit-тесты проходят
5. Валидация обязательных полей работает корректно

---

## Риски

| Риск                         | Вероятность | Влияние | Митигация                 |
| ---------------------------- | ----------- | ------- | ------------------------- |
| LLM извлекает >10 веществ    | Низкая      | Среднее | Валидация в Pydantic      |
| LLM не балансирует уравнения | Средняя     | Низкое  | Добавить примеры в промпт |

---

## Следующий этап

➡️ **Этап 6:** Рефакторинг Orchestrator
