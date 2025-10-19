# Stage 07: Интеграция и end-to-end тесты

## Цель
Интегрировать все изменения в оркестратор и обеспечить работу системы end-to-end.

## Статус
🔴 Не начато

## Входные данные
- Stage 01-06 завершены
- Существующий `ThermodynamicAgent` и оркестратор

## Выходные данные
- Обновлённый оркестратор
- End-to-end тесты
- Документация пользователя

## Изменяемые файлы
- `src/thermo_agents/thermodynamic_agent.py`
- `src/thermo_agents/orchestrator.py`

## Зависимости
- Все предыдущие стадии (01-06)

## Алгоритм действий

### Шаг 1: Обновление ThermodynamicAgent

**Текущая логика:**
- Получает одну запись от `CompoundSearcher.search_compound()`
- Использует `ThermodynamicCalculator.calculate_properties()`
- Возвращает одну термодинамическую точку

**Новая логика:**
1. Определить, требуется ли многофазный расчёт:
   - Если T > Tmax текущей записи → многофазный
   - Если пользователь явно запросил многофазный расчёт
2. Если многофазный:
   - Вызвать `CompoundSearcher.search_all_phases()`
   - Вызвать `ThermodynamicCalculator.calculate_multi_phase_properties()`
   - Использовать обновлённый форматтер из Stage 06
3. Если одиночный:
   - Использовать старую логику (обратная совместимость)

### Шаг 2: Обновление Orchestrator

**Изменения в логике обработки запросов:**
1. Добавить параметр `use_multi_phase: bool = True` (по умолчанию включено)
2. Передавать `StaticDataManager` в `CompoundSearcher`
3. Определять максимальную температуру из запроса пользователя
4. Передавать флаг многофазного расчёта в `ThermodynamicAgent`

### Шаг 3: Обновление конфигурации

**Добавить в конфиг:**
```python
MULTI_PHASE_CONFIG = {
    "enabled": True,  # Включить многофазные расчёты
    "use_static_cache": True,  # Использовать YAML кэш
    "static_cache_dir": "data/static_compounds/",
    "min_segments_for_warning": 5,  # Предупреждать если > 5 сегментов
    "integration_points": 400,  # Точек для интегрирования
}
```

### Шаг 4: Добавление логирования

**Новые логи:**
1. "⚡ Использован YAML кэш для {formula}"
2. "Многофазный расчёт: {n} сегментов, {m} переходов"
3. "⚠️ Пробел в покрытии: {T1}K - {T2}K"
4. "Фазовый переход: {phase1}→{phase2} при {T}K"

### Шаг 5: Обратная совместимость

**Обеспечить:**
1. Старый API (одиночная запись) продолжает работать
2. Старые тесты проходят без изменений
3. Флаг `use_multi_phase=False` отключает новый функционал
4. Форматтер поддерживает оба режима

### Шаг 6: End-to-end тестирование

**Сценарии тестов:**
1. **H2O при 1500K**: расчёт через s, l, g фазы
2. **FeO при 1700K**: пример из ТЗ с 5 сегментами
3. **Реакция CaO + SiO2**: несколько веществ с переходами
4. **Обратная совместимость**: старые запросы работают
5. **YAML кэш**: проверка приоритета YAML → БД
6. **Производительность**: расчёт < 500ms для типового запроса

## Критерии завершения
- [ ] `ThermodynamicAgent` поддерживает многофазные расчёты
- [ ] `Orchestrator` корректно определяет необходимость многофазного расчёта
- [ ] `StaticDataManager` интегрирован с `CompoundSearcher`
- [ ] Конфигурация MULTI_PHASE_CONFIG добавлена
- [ ] Логирование многофазных операций работает
- [ ] Обратная совместимость: старые тесты проходят
- [ ] End-to-end тесты покрывают все ключевые сценарии (≥95%)
- [ ] Документация пользователя обновлена
- [ ] Производительность: типовой запрос < 500ms
- [ ] Нет регрессий в существующем функционале

## Тесты

### Unit-тесты
- `tests/test_thermodynamic_agent_multiphase.py` — тесты агента
- `tests/test_orchestrator_multiphase.py` — тесты оркестратора

### Интеграционные тесты
- `tests/integration/test_h2o_full_pipeline.py` — H2O через s→l→g
- `tests/integration/test_feo_multi_phase.py` — FeO при 1700K (из ТЗ)
- `tests/integration/test_cao_sio2_reaction.py` — Реакция с переходами
- `tests/integration/test_yaml_cache_priority.py` — Приоритет YAML → БД
- `tests/integration/test_backward_compatibility.py` — Старые запросы работают

### Performance-тесты
- `tests/performance/test_multi_phase_speed.py` — Скорость расчёта

### Regression-тесты
- `tests/regression/test_existing_queries.py` — Старые запросы не сломались

## Риски

### Высокие риски
- **Регрессия существующего функционала**: Изменения могут сломать работающий код
  - *Митигация*: Обширные regression-тесты
  - *Митигация*: Флаг `use_multi_phase=False` для отката
  - *Митигация*: Пошаговая интеграция с проверкой после каждого шага

### Средние риски
- **Производительность**: Многофазные расчёты могут быть медленнее
  - *Митигация*: YAML кэш для распространённых веществ
  - *Митигация*: Профилирование и оптимизация узких мест
  - *Митигация*: Кэширование результатов интегрирования

- **Сложность отладки**: Многофазная логика сложнее для диагностики проблем
  - *Митигация*: Подробное логирование каждого шага
  - *Митигация*: Детальные сообщения об ошибках
  - *Митигация*: Валидация данных на каждом этапе

### Низкие риски
- **Конфигурация**: Неправильные настройки могут привести к некорректным результатам
  - *Митигация*: Валидация конфигурации при старте
  - *Митигация*: Документированные значения по умолчанию

## Примечания

### Стратегия внедрения

**Вариант 1: Big Bang (одномоментное внедрение)**
- ❌ Высокий риск регрессий
- ❌ Сложно откатить изменения
- ✅ Быстрое внедрение

**Вариант 2: Feature Flag (постепенное внедрение)** ← **Рекомендуется**
- ✅ Низкий риск регрессий
- ✅ Можно откатить без изменений кода
- ✅ Возможность A/B тестирования
- ❌ Требует дополнительной логики

**Выбранный вариант:** Feature Flag с параметром `use_multi_phase`

### План миграции

**Фаза 1: Внедрение (1-2 недели)**
1. Интеграция Stage 01-06
2. Флаг `use_multi_phase=False` по умолчанию
3. Тестирование на dev окружении

**Фаза 2: Бета-тестирование (1 неделя)**
1. Флаг `use_multi_phase=True` для избранных пользователей
2. Сбор обратной связи
3. Исправление багов

**Фаза 3: Полное внедрение (1 неделя)**
1. Флаг `use_multi_phase=True` по умолчанию
2. Мониторинг производительности и ошибок
3. Документация для пользователей

**Фаза 4: Очистка (после 1 месяца стабильной работы)**
1. Удаление старой логики (если не нужна)
2. Удаление флага `use_multi_phase`
3. Оптимизация кода

### Мониторинг после внедрения

**Ключевые метрики:**
1. Время ответа на запрос (p50, p95, p99)
2. Количество ошибок расчёта
3. Процент использования YAML кэша
4. Количество многофазных расчётов vs одиночных
5. Средняя длина сегментов в расчёте

**Алерты:**
- Время ответа > 1 секунда (p95)
- Процент ошибок > 1%
- Пробелы в покрытии для распространённых веществ

### Связь с другими этапами
- Интегрирует все этапы 01-06
- Использует YAML кэш из Stage 04
- Использует многофазный калькулятор из Stage 05
- Использует обновлённый форматтер из Stage 06

---

## Примеры кода

### Пример 1: Обновление ThermodynamicAgent

```python
# src/thermo_agents/thermodynamic_agent.py

from typing import Optional, List
from .search.compound_searcher import CompoundSearcher
from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .storage.static_data_manager import StaticDataManager

class ThermodynamicAgent:
    """Агент для термодинамических расчётов."""
    
    def __init__(
        self,
        compound_searcher: CompoundSearcher,
        calculator: ThermodynamicCalculator,
        formatter: ReactionCalculationFormatter,
        use_multi_phase: bool = True
    ):
        self.compound_searcher = compound_searcher
        self.calculator = calculator
        self.formatter = formatter
        self.use_multi_phase = use_multi_phase
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
        Расчёт термодинамических свойств вещества.
        
        Автоматически определяет необходимость многофазного расчёта.
        """
        self.logger.info(f"Расчёт для {formula}, T_range=({T_min}, {T_max})K")
        
        # Определить, нужен ли многофазный расчёт
        needs_multi_phase = self._needs_multi_phase_calculation(
            formula, T_max, compound_names
        )
        
        if needs_multi_phase and self.use_multi_phase:
            self.logger.info("Использование многофазного расчёта")
            return self._calculate_multi_phase(
                formula, T_min, T_max, step_k, compound_names
            )
        else:
            self.logger.info("Использование одиночного расчёта")
            return self._calculate_single_phase(
                formula, T_min, T_max, step_k, compound_names
            )
    
    def _needs_multi_phase_calculation(
        self,
        formula: str,
        T_max: float,
        compound_names: Optional[List[str]] = None
    ) -> bool:
        """
        Определение необходимости многофазного расчёта.
        
        Returns:
            True если нужен многофазный расчёт
        """
        # Поиск одной записи
        single_result = self.compound_searcher.search_compound(
            formula=formula,
            temperature_range=None,
            phase=None,
            limit=1,
            compound_names=compound_names
        )
        
        if not single_result.records_found:
            return True  # Попробуем многофазный
        
        record = single_result.records_found[0]
        
        # Если T_max выходит за пределы одной записи
        if T_max > record.tmax:
            self.logger.info(
                f"T_max={T_max}K > record.Tmax={record.tmax}K, "
                "требуется многофазный расчёт"
            )
            return True
        
        # Если известно, что есть фазовые переходы
        if record.tmelt > 0 and record.tmelt < T_max:
            self.logger.info(
                f"Tmelt={record.tmelt}K в диапазоне, требуется многофазный расчёт"
            )
            return True
        
        return False
    
    def _calculate_multi_phase(
        self,
        formula: str,
        T_min: float,
        T_max: float,
        step_k: int,
        compound_names: Optional[List[str]]
    ) -> str:
        """Многофазный расчёт."""
        # Поиск всех фаз
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
        
        # Многофазный расчёт
        mp_result = self.calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=T_max
        )
        
        # Форматирование вывода
        output = self.formatter.format_compound_data_multi_phase(
            formula=formula,
            compound_name=search_result.records[0].name or formula,
            multi_phase_result=mp_result
        )
        
        # Добавить таблицу по температурам
        temperatures = list(range(int(T_min), int(T_max) + 1, step_k))
        
        # Добавить точки фазовых переходов
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
    
    def _calculate_single_phase(
        self,
        formula: str,
        T_min: float,
        T_max: float,
        step_k: int,
        compound_names: Optional[List[str]]
    ) -> str:
        """Одиночный расчёт (обратная совместимость)."""
        # Существующая логика
        # ...
```

### Пример 2: Обновление Orchestrator

```python
# src/thermo_agents/orchestrator.py

from typing import Optional
from pathlib import Path
from .thermodynamic_agent import ThermodynamicAgent
from .search.compound_searcher import CompoundSearcher
from .search.database_connector import DatabaseConnector
from .search.sql_builder import SQLBuilder
from .calculations.thermodynamic_calculator import ThermodynamicCalculator
from .formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from .storage.static_data_manager import StaticDataManager

# Конфигурация
MULTI_PHASE_CONFIG = {
    "enabled": True,
    "use_static_cache": True,
    "static_cache_dir": "data/static_compounds/",
    "min_segments_for_warning": 5,
    "integration_points": 400,
}

class Orchestrator:
    """Оркестратор термодинамических расчётов."""
    
    def __init__(
        self,
        db_path: str,
        use_multi_phase: Optional[bool] = None,
        static_cache_dir: Optional[str] = None
    ):
        """
        Инициализация оркестратора.
        
        Args:
            db_path: Путь к БД
            use_multi_phase: Использовать многофазные расчёты (по умолчанию из конфига)
            static_cache_dir: Путь к YAML кэшу (по умолчанию из конфига)
        """
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Конфигурация
        self.use_multi_phase = (
            use_multi_phase 
            if use_multi_phase is not None 
            else MULTI_PHASE_CONFIG["enabled"]
        )
        
        self.static_cache_dir = (
            static_cache_dir 
            or MULTI_PHASE_CONFIG["static_cache_dir"]
        )
        
        self.logger.info(
            f"Инициализация оркестратора: "
            f"multi_phase={self.use_multi_phase}, "
            f"static_cache={self.use_static_cache}"
        )
        
        # Инициализация компонентов
        self.db_connector = DatabaseConnector(db_path)
        self.sql_builder = SQLBuilder()
        
        # StaticDataManager (если включён кэш)
        self.static_data_manager = None
        if MULTI_PHASE_CONFIG["use_static_cache"]:
            try:
                self.static_data_manager = StaticDataManager(
                    data_dir=Path(self.static_cache_dir)
                )
                self.logger.info("✅ StaticDataManager инициализирован")
            except Exception as e:
                self.logger.warning(f"⚠️ StaticDataManager недоступен: {e}")
        
        # CompoundSearcher с StaticDataManager
        self.compound_searcher = CompoundSearcher(
            sql_builder=self.sql_builder,
            db_connector=self.db_connector,
            static_data_manager=self.static_data_manager
        )
        
        # ThermodynamicCalculator
        self.calculator = ThermodynamicCalculator(
            num_integration_points=MULTI_PHASE_CONFIG["integration_points"]
        )
        
        # Formatter
        self.formatter = ReactionCalculationFormatter()
        
        # ThermodynamicAgent
        self.agent = ThermodynamicAgent(
            compound_searcher=self.compound_searcher,
            calculator=self.calculator,
            formatter=self.formatter,
            use_multi_phase=self.use_multi_phase
        )
    
    def process_query(self, user_query: str) -> str:
        """
        Обработка пользовательского запроса.
        
        Args:
            user_query: Запрос пользователя
            
        Returns:
            Отформатированный ответ
        """
        self.logger.info(f"Обработка запроса: {user_query}")
        
        # Существующая логика классификации и обработки
        # ...
        
        # Логирование использования многофазных расчётов
        if self.use_multi_phase:
            self.logger.info("⚡ Многофазные расчёты включены")
        
        return response
```

### Пример 3: End-to-end тест

```python
# tests/integration/test_multi_phase_end_to_end.py

import pytest
from src.thermo_agents.orchestrator import Orchestrator

@pytest.fixture
def orchestrator(tmp_path):
    """Оркестратор с временным кэшем."""
    # Копируем тестовую БД
    test_db_path = "tests/fixtures/test_thermo.db"
    
    return Orchestrator(
        db_path=test_db_path,
        use_multi_phase=True,
        static_cache_dir=str(tmp_path / "static_compounds")
    )

def test_feo_1700k_end_to_end(orchestrator):
    """End-to-end тест расчёта FeO при 1700K."""
    query = "Рассчитай термодинамические свойства FeO от 298K до 1700K"
    
    response = orchestrator.process_query(query)
    
    # Проверки вывода
    assert "FeO" in response
    assert "[Сегмент" in response
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
    assert "373" in response or "Tboil" in response  # Кипение (если есть)

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
    
    # Проверка, что SiO2 имеет переходы
    if "SiO2" in response:
        assert "s→s" in response or "кристобалит" in response

def test_yaml_cache_priority(orchestrator, tmp_path):
    """Тест приоритета YAML кэша над БД."""
    # Создать YAML файл для H2O в временном кэше
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
    
    # Создать оркестратор с этим кэшем
    orch = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        use_multi_phase=True,
        static_cache_dir=str(cache_dir)
    )
    
    query = "Рассчитай H2O при 500K"
    response = orch.process_query(query)
    
    # Проверка, что использован YAML кэш
    # (это можно увидеть в логах или метаданных ответа)
    assert "H2O" in response
    assert "Test Water" in response or "Water" in response

def test_backward_compatibility(orchestrator):
    """Тест обратной совместимости со старыми запросами."""
    # Отключить многофазные расчёты
    orchestrator.use_multi_phase = False
    orchestrator.agent.use_multi_phase = False
    
    query = "Рассчитай свойства O2 от 298K до 500K"
    response = orchestrator.process_query(query)
    
    # Должно работать как раньше (одна запись)
    assert "O2" in response
    assert "[Сегмент" not in response  # Нет многофазного формата
```

### Пример 4: Тест производительности

```python
# tests/performance/test_multi_phase_performance.py

import pytest
import time
from src.thermo_agents.orchestrator import Orchestrator

def test_multi_phase_query_performance():
    """Тест производительности многофазного запроса."""
    orchestrator = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        use_multi_phase=True
    )
    
    query = "Рассчитай FeO от 298K до 1700K с шагом 100K"
    
    start = time.time()
    response = orchestrator.process_query(query)
    elapsed = time.time() - start
    
    # Типовой запрос должен занять < 500ms
    assert elapsed < 0.5, f"Запрос занял {elapsed*1000:.1f}ms (ожидалось < 500ms)"
    
    # Проверка корректности
    assert "FeO" in response
    assert len(response) > 100  # Есть содержимое

@pytest.mark.parametrize("formula,max_T,expected_time", [
    ("H2O", 500, 0.3),
    ("FeO", 1700, 0.5),
    ("SiO2", 1500, 0.4),
])
def test_performance_by_compound(formula, max_T, expected_time):
    """Тест производительности для различных веществ."""
    orchestrator = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        use_multi_phase=True
    )
    
    query = f"Рассчитай {formula} от 298K до {max_T}K"
    
    start = time.time()
    response = orchestrator.process_query(query)
    elapsed = time.time() - start
    
    assert elapsed < expected_time, (
        f"{formula}: {elapsed*1000:.1f}ms > {expected_time*1000:.0f}ms"
    )
```

### Пример 5: Regression-тест

```python
# tests/regression/test_existing_queries.py

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
def test_old_query_still_works(query):
    """Regression-тест: старые запросы работают с новым кодом."""
    orchestrator = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        use_multi_phase=True  # Включено, но не должно ломать старые запросы
    )
    
    try:
        response = orchestrator.process_query(query)
        
        # Базовые проверки
        assert len(response) > 50, "Ответ слишком короткий"
        assert "❌" not in response, "Ответ содержит ошибку"
        
    except Exception as e:
        pytest.fail(f"Запрос '{query}' вызвал ошибку: {e}")

def test_old_format_with_flag_disabled():
    """Тест старого формата с отключённым многофазным расчётом."""
    orchestrator = Orchestrator(
        db_path="tests/fixtures/test_thermo.db",
        use_multi_phase=False  # Явно отключено
    )
    
    query = "Рассчитай H2O от 298K до 500K"
    response = orchestrator.process_query(query)
    
    # Должен быть старый формат (без "[Сегмент")
    assert "[Сегмент" not in response
    assert "H2O" in response or "Water" in response
```
