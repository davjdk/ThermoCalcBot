# Этап 4: Модификация Orchestrator

**Статус:** Не начат  
**Приоритет:** Средний  
**Зависимости:** Этап 3

---

## Цель

Добавить маршрутизацию в `Orchestrator` для обработки двух типов запросов с использованием соответствующих форматтеров.

---

## Основные задачи

### 4.1. Обновление Orchestrator

**Файл:** `src/thermo_agents/orchestrator.py`

**Изменения:**
- Добавить инициализацию `ThermodynamicCalculator`, `CompoundDataFormatter`, `ReactionCalculationFormatter`
- Модифицировать метод `process_query()` для маршрутизации по `query_type`
- Создать методы `_process_compound_data()` и `_process_reaction_calculation()`

### 4.2. Реализация _process_compound_data()

**Логика:**
1. Извлечение параметров через `ThermodynamicAgent.extract_parameters()`
2. Поиск вещества через `CompoundSearcher`
3. Выбор лучшей записи через `FilterPipeline`
4. Форматирование результата через `CompoundDataFormatter`

### 4.3. Реализация _process_reaction_calculation()

**Логика:**
1. Извлечение параметров (реакция, температурный диапазон)
2. Поиск всех веществ реакции
3. Фильтрация записей по фазе и температуре
4. Расчёт термодинамики через `ThermodynamicCalculator`
5. Форматирование результата через `ReactionCalculationFormatter`

### 4.4. Обновление примеров использования

**Файлы:**
- `examples/compound_data_example.py` (новый)
- `examples/reaction_calculation_example.py` (новый)

### 4.5. Интеграционные тесты

**Файл:** `tests/integration/test_output_formats.py` (новый)

**Тесты:**
- E2E тест для запроса `compound_data`
- E2E тест для запроса `reaction_calculation`
- Проверка корректной маршрутизации по типу запроса
- Обработка ошибок (вещество не найдено, некорректный запрос)

---

## Критерии приёмки

- ✅ `Orchestrator` корректно маршрутизирует запросы
- ✅ Оба типа запросов обрабатываются полностью
- ✅ Интеграционные тесты проходят
- ✅ Примеры использования работают
- ✅ Логирование добавлено для отладки
- ✅ Обработка ошибок на всех уровнях

---

## Детальные подзадачи

### 4.1.1. Добавление новых зависимостей в Orchestrator.__init__()

**Файл:** `src/thermo_agents/orchestrator.py`

**Изменения:**
```python
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from src.thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from src.thermo_agents.formatting.reaction_calculation_formatter import ReactionCalculationFormatter

class Orchestrator:
    def __init__(self, db_path: str, llm_client):
        # Существующие компоненты
        self.db_connector = DatabaseConnector(db_path)
        self.compound_searcher = CompoundSearcher(self.db_connector)
        self.filter_pipeline = FilterPipeline()
        self.thermodynamic_agent = ThermodynamicAgent(llm_client)
        
        # НОВЫЕ компоненты
        self.calculator = ThermodynamicCalculator()
        self.compound_formatter = CompoundDataFormatter(self.calculator)
        self.reaction_formatter = ReactionCalculationFormatter(self.calculator)
```

### 4.1.2. Модификация process_query() для маршрутизации

**Изменения:**
```python
async def process_query(self, user_query: str) -> str:
    """
    Обработка запроса пользователя с маршрутизацией по типу.
    """
    try:
        # Извлечение параметров
        params = await self.thermodynamic_agent.extract_parameters(user_query)
        
        # Маршрутизация по типу запроса
        if params.query_type == "compound_data":
            return await self._process_compound_data(params)
        else:  # reaction_calculation
            return await self._process_reaction_calculation(params)
    
    except Exception as e:
        logger.error(f"Ошибка обработки запроса: {e}")
        return f"❌ Ошибка обработки запроса: {str(e)}"
```

### 4.2.1. Реализация _process_compound_data()

**Метод:**
```python
async def _process_compound_data(
    self, 
    params: ExtractedReactionParameters
) -> str:
    """
    Обработка запроса данных по веществу.
    
    Шаги:
    1. Поиск вещества в базе
    2. Фильтрация записей (фаза, температура)
    3. Форматирование результата
    """
    formula = params.all_compounds[0]
    T_min, T_max = params.temperature_range_k
    
    # Поиск вещества
    search_result = await self.compound_searcher.search_compound(
        formula=formula,
        temperature_k=T_min  # Используем T_min для поиска
    )
    
    if not search_result.records_found:
        return f"❌ Вещество {formula} не найдено в базе данных"
    
    # Фильтрация записей
    filtered = self.filter_pipeline.filter_records(
        records=search_result.records_found,
        temperature_range=(T_min, T_max)
    )
    
    if not filtered:
        return f"❌ Не найдено записей для {formula} в диапазоне {T_min}-{T_max}K"
    
    # Обновление результата поиска
    search_result.records_found = filtered
    
    # Форматирование
    return self.compound_formatter.format_response(
        result=search_result,
        T_min=T_min,
        T_max=T_max,
        step_k=params.temperature_step_k
    )
```

### 4.3.1. Реализация _process_reaction_calculation()

**Метод:**
```python
async def _process_reaction_calculation(
    self,
    params: ExtractedReactionParameters
) -> str:
    """
    Обработка запроса расчёта реакции.
    
    Шаги:
    1. Поиск всех веществ реакции
    2. Фильтрация по фазе и температуре
    3. Расчёт термодинамики
    4. Форматирование результата
    """
    T_min, T_max = params.temperature_range_k
    T_mid = (T_min + T_max) / 2
    
    # Поиск реагентов
    reactant_results = []
    for formula in params.reactants:
        result = await self.compound_searcher.search_compound(
            formula=formula,
            temperature_k=T_mid
        )
        reactant_results.append(result)
    
    # Поиск продуктов
    product_results = []
    for formula in params.products:
        result = await self.compound_searcher.search_compound(
            formula=formula,
            temperature_k=T_mid
        )
        product_results.append(result)
    
    # Проверка, что все вещества найдены
    all_results = reactant_results + product_results
    missing = [r.formula for r in all_results if not r.records_found]
    if missing:
        return f"❌ Не найдены вещества: {', '.join(missing)}"
    
    # Фильтрация записей по температурному диапазону
    for result in all_results:
        filtered = self.filter_pipeline.filter_records(
            records=result.records_found,
            temperature_range=(T_min, T_max)
        )
        result.records_found = filtered
    
    # Форматирование
    return self.reaction_formatter.format_response(
        params=params,
        reactants=reactant_results,
        products=product_results,
        step_k=params.temperature_step_k
    )
```

### 4.3.2. Извлечение стехиометрических коэффициентов

**Вспомогательный метод:**
```python
def _extract_stoichiometry(
    self, 
    equation: str
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Извлечение стехиометрических коэффициентов из уравнения.
    
    Пример: "2 W + 4 Cl2 → 2 WOCl4"
    Результат: ({"W": 2, "Cl2": 4}, {"WOCl4": 2})
    """
    # Разделение на реагенты и продукты
    parts = equation.replace("→", "=").replace("->", "=").split("=")
    if len(parts) != 2:
        raise ValueError(f"Некорректное уравнение реакции: {equation}")
    
    reactants_str, products_str = parts
    
    # Парсинг стехиометрии
    import re
    pattern = r'(\d+)?\s*([A-Za-z0-9()]+)'
    
    def parse_side(side_str):
        compounds = {}
        for match in re.finditer(pattern, side_str):
            coeff, formula = match.groups()
            coeff = int(coeff) if coeff else 1
            compounds[formula.strip()] = coeff
        return compounds
    
    reactants = parse_side(reactants_str)
    products = parse_side(products_str)
    
    return reactants, products
```

### 4.4.1. Создание примера compound_data

**Файл:** `examples/compound_data_example.py`

**Код:**
```python
import asyncio
from src.thermo_agents.orchestrator import Orchestrator

async def main():
    orchestrator = Orchestrator(
        db_path="data/thermodynamic_database.db",
        llm_client=create_llm_client()
    )
    
    # Пример 1: Базовый запрос
    query1 = "Дай таблицу для H2O при 300-600K"
    result1 = await orchestrator.process_query(query1)
    print(result1)
    print("\n" + "="*60 + "\n")
    
    # Пример 2: С кастомным шагом
    query2 = "Свойства WCl6 при 400-1000K с шагом 50 градусов"
    result2 = await orchestrator.process_query(query2)
    print(result2)

if __name__ == "__main__":
    asyncio.run(main())
```

### 4.4.2. Создание примера reaction_calculation

**Файл:** `examples/reaction_calculation_example.py`

**Код:**
```python
import asyncio
from src.thermo_agents.orchestrator import Orchestrator

async def main():
    orchestrator = Orchestrator(
        db_path="data/thermodynamic_database.db",
        llm_client=create_llm_client()
    )
    
    # Пример: Хлорирование вольфрама
    query = "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
    result = await orchestrator.process_query(query)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

### 4.5.1. Интеграционные тесты

**Файл:** `tests/integration/test_output_formats.py`

**Тесты:**
```python
import pytest
from src.thermo_agents.orchestrator import Orchestrator

class TestOutputFormats:
    
    @pytest.fixture
    def orchestrator(self):
        return Orchestrator(
            db_path="data/test_database.db",
            llm_client=create_mock_llm()
        )
    
    @pytest.mark.asyncio
    async def test_compound_data_h2o(self, orchestrator):
        """E2E тест для compound_data запроса"""
        query = "Дай таблицу для H2O при 300-600K"
        result = await orchestrator.process_query(query)
        
        assert "📊 Термодинамические данные: H2O" in result
        assert "Базовые свойства:" in result
        assert "T(K)" in result  # Таблица присутствует
        assert "Cp" in result
    
    @pytest.mark.asyncio
    async def test_reaction_calculation_w_chlorination(self, orchestrator):
        """E2E тест для reaction_calculation запроса"""
        query = "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
        result = await orchestrator.process_query(query)
        
        assert "⚗️ Термодинамический расчёт реакции" in result
        assert "Метод расчёта:" in result
        assert "ΔH°" in result
        assert "ΔS°" in result
        assert "ΔG°" in result
    
    @pytest.mark.asyncio
    async def test_compound_not_found(self, orchestrator):
        """Обработка ненайденного вещества"""
        query = "Дай данные для UnknownCompound123"
        result = await orchestrator.process_query(query)
        
        assert "❌" in result
        assert "не найдено" in result.lower()
```

### 4.5.2. Тесты маршрутизации

**Тест:**
```python
@pytest.mark.asyncio
async def test_routing_by_query_type(orchestrator, monkeypatch):
    """Проверка корректной маршрутизации"""
    compound_called = False
    reaction_called = False
    
    async def mock_compound(params):
        nonlocal compound_called
        compound_called = True
        return "compound_data result"
    
    async def mock_reaction(params):
        nonlocal reaction_called
        reaction_called = True
        return "reaction_calculation result"
    
    monkeypatch.setattr(orchestrator, "_process_compound_data", mock_compound)
    monkeypatch.setattr(orchestrator, "_process_reaction_calculation", mock_reaction)
    
    # Тест compound_data
    await orchestrator.process_query("Данные для H2O")
    assert compound_called
    assert not reaction_called
    
    # Тест reaction_calculation
    compound_called = False
    await orchestrator.process_query("H2 + Cl2 → 2 HCl")
    assert reaction_called
```

---

## Логирование

### Добавление логов
```python
import logging
logger = logging.getLogger(__name__)

async def process_query(self, user_query: str) -> str:
    logger.info(f"Обработка запроса: {user_query}")
    
    params = await self.thermodynamic_agent.extract_parameters(user_query)
    logger.debug(f"Извлечённые параметры: query_type={params.query_type}")
    
    if params.query_type == "compound_data":
        logger.info("Маршрутизация → compound_data")
        return await self._process_compound_data(params)
    else:
        logger.info("Маршрутизация → reaction_calculation")
        return await self._process_reaction_calculation(params)
```

---

## Обработка ошибок

### Уровни обработки
1. **Orchestrator** — общие ошибки, логирование
2. **Форматтеры** — специфичные ошибки форматирования
3. **Calculator** — ошибки вычислений (T вне диапазона)

---

