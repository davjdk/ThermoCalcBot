# ThermoSystem

## Обзор

ThermoSystem — высокопроизводительная система термодинамических агентов с гибридной архитектурой, сочетающей LLM-компоненты для извлечения параметров с детерминированными модулями для поиска, расчётов и форматирования данных. Система поддерживает два типа запросов: табличные данные веществ и термодинамические расчёты реакций.

## Ключевые возможности

### Два типа запросов

1. **Табличные данные веществ** — получение термодинамических свойств (Cp, H, S, G) отдельного вещества в заданном температурном диапазоне
2. **Расчёт реакций** — термодинамический анализ химических реакций с расчётом ΔH, ΔS, ΔG, K (константа равновесия) реакции

### Многофазные расчёты

- **Автоматическое определение фазовых сегментов** и переходов (плавление, кипение, сублимация)
- **StaticDataManager** для кэширования распространённых веществ из YAML-файлов
- **ThermodynamicEngine** с численным интегрированием по формулам Шомейта
- **Поддержка Unicode** — химические формулы с подстрочными индексами (H₂O, CO₂)

## Архитектурные компоненты

### 1. Гибридная архитектура (Hybrid Architecture)

**LLM-компонент:**
- `ThermodynamicAgent` — извлечение параметров из естественного языка
- Использует PydanticAI + OpenRouter API для структурированного вывода
- Модель: `ExtractedReactionParameters` с валидацией через Pydantic

**Детерминированные компоненты:**
- `CompoundDataLoader` — двухстадийная загрузка данных (YAML кэш → база данных)
- `RecordRangeBuilder` — трехуровневая стратегия отбора записей
- `ThermodynamicEngine` — расчёты по формулам Шомейта с численным интегрированием
- `ReactionEngine` — расчёт ΔH, ΔS, ΔG, K для реакций
- `UnifiedReactionFormatter` — профессиональное форматирование результатов через tabulate

### 2. Оркестратор системы

**ThermoOrchestrator** (единственный оркестратор):
- Интегрированная core-логика для полного цикла обработки запросов
- Автоматическая интеграция StaticDataManager для YAML кэша
- Поддержка фазовых переходов и сегментов через PhaseTransitionDetector
- Двухстадийный поиск в базе данных (точное совпадение → расширенный поиск)
- Форматтеры: UnifiedReactionFormatter, CompoundInfoFormatter, TableFormatter, InterpretationFormatter
- Оптимизированная обработка с прямыми вызовами компонентов без message passing overhead

### 3. Система поиска и SQL генерации

**SQLBuilder:**
- Детерминированная генерация SQL запросов
- Многоуровневые стратегии поиска (точная формула → широкие паттерны)
- CommonCompoundsResolver для распространённых веществ (H2O, CO2, NH3, CH4, O2, N2, H2, HCl, CH3OH, C2H5OH)
- Поддержка ионных соединений и композитных формул
- Кэширование запросов (90%+ hit rate)

**CompoundSearcher:**
- Координация между SQLBuilder и DatabaseConnector
- Логирование через SessionLogger
- Интеграция StaticDataManager для YAML кэша
- Статистика поиска и покрытия данных

**DatabaseConnector:**
- Надёжное подключение к SQLite базе
- Кэширование соединения
- Статистика выполнения запросов

### 4. Core-логика обработки данных

**CompoundDataLoader:**
- Двухстадийная стратегия загрузки данных (YAML кэш → база данных)
- Интеграция StaticDataManager и DatabaseConnector
- Оптимизация поиска распространенных веществ

**PhaseTransitionDetector:**
- Определение точек плавления и кипения
- Автоматическое распознавание фазовых переходов
- Поддержка сублимации для специфических веществ

**RecordRangeBuilder:**
- Трехуровневая стратегия отбора записей для температурного диапазона
- Приоритизация по классу надёжности (ReliabilityClass 1-4)
- Оптимальный выбор записей для покрытия диапазона
- **Оптимизация записей** (v2.3+): минимизация количества записей с сохранением точности

**PhaseResolver:**
- Определение фазовых состояний на основе температуры
- Поддержка переходов: плавление, кипение, сублимация
- Интеграция с PhaseSegmentBuilder для построения фазовых сегментов

**ReactionEngine:**
- Полный расчёт термодинамики реакции (ΔH, ΔS, ΔG, K)
- Парсинг уравнений реакций с поддержкой до 10 веществ
- Обработка стехиометрических коэффициентов
- Расчёт константы равновесия K через ln(K) = -ΔG/(R·T)

### 5. Термодинамический движок

**ThermodynamicEngine:**
- **Формулы Шомейта** для расчёта Cp(T):
  ```
  Cp(T) = f1 + f2*T/1000 + f3*T^(-2)*10^5 + f4*T^2/10^6 + f5*T^(-3)*10^3 + f6*T^3*10^(-9)
  ```
- **Численное интегрирование** для H(T), S(T), G(T) через numpy/scipy
- Расчёт энтальпии: H(T) = H₂₉₈ + ∫(Cp(T)dT) от 298K до T
- Расчёт энтропии: S(T) = S₂₉₈ + ∫(Cp(T)/T dT) от 298K до T
- Расчёт энергии Гиббса: G(T) = H(T) - T·S(T)
- Поддержка многофазных расчётов с фазовыми переходами

**ThermodynamicCalculator (базовый калькулятор):**
- Простые расчёты термодинамических свойств
- Используется для однофазных случаев
- Интеграция с ThermodynamicEngine для сложных случаев

### 6. StaticDataManager (YAML кэш)

**Назначение:**
- Быстрый доступ к данным распространённых веществ
- Избегание лишних обращений к базе данных
- Предвычисленные фазовые переходы

**Поддерживаемые вещества:**
- H2O (вода), CO2, CO, O2, Cl2, HCl, NaCl, FeO, C (углерод)
- YAML файлы в `data/static_compounds/`

**Структура YAML:**
```yaml
formula: H2O
phases:
  - phase: s
    temperature_range: [0, 273.15]
    coefficients: {f1, f2, f3, f4, f5, f6}
    thermodynamic_data: {H298, S298, Cp298}
  - phase: l
    temperature_range: [273.15, 373.15]
    ...
transitions:
  - type: melting
    temperature: 273.15
    enthalpy: 6010.0
```

### 7. Форматирование вывода

**UnifiedReactionFormatter:**
- Унифицированное форматирование результатов расчётов реакций
- Интеграция CompoundInfoFormatter, TableFormatter, InterpretationFormatter
- Табличный вывод через `tabulate`
- Unicode формулы (H₂O вместо H2O) и стрелки (→)

**CompoundInfoFormatter:**
- Форматирование информации о веществах
- Базовые свойства: H₂₉₈, S₂₉₈, Cp₂₉₈, класс надёжности, фаза
- Температурные диапазоны записей

**TableFormatter:**
- Профессиональное форматирование таблиц результатов
- Таблица свойств по температуре: T, Cp, H, S, G
- Таблица результатов реакции: T, ΔH, ΔS, ΔG, ln(K), K
- Настраиваемые стили и форматы чисел

**InterpretationFormatter:**
- Интерпретация результатов расчётов
- Анализ спонтанности реакции (ΔG < 0)
- Объяснение физического смысла результатов

### 8. Оптимизация выбора записей (v2.3+)

**OptimalRecordSelector:**
- **Алгоритм постобработки** после трёхуровневой стратегии отбора
- **Формула оптимальности**: Score = w₁·(1/N) + w₂·(Avg_reliability/3) + w₃·Transition_coverage
- **Веса**: w₁=0.5 (минимизация записей), w₂=0.3 (качество данных), w₃=0.2 (покрытие переходов)
- **Виртуальное объединение** записей с идентичными коэффициентами Шомейта
- **Поддержка VirtualRecord** для объединённых записей

**VirtualRecord:**
- Наследует DatabaseRecord с флагом `is_virtual=True`
- Объединяет несколько физических записей в одну виртуальную
- Сохраняет ссылки на исходные записи в `source_records`
- Объединённый температурный диапазон: `merged_tmin`, `merged_tmax`
- Условия объединения: одинаковая фаза, непрерывность диапазона, идентичные коэффициенты

**OptimizationConfig:**
- Настраиваемые параметры оптимизации
- Допуски: `gap_tolerance_k=1.0K`, `transition_tolerance_k=10.0K`
- Точность сравнения коэффициентов: `coeffs_comparison_tolerance=1e-6`
- Ограничения производительности: `max_optimization_time_ms=50ms`

**Интеграция с существующими компонентами:**
- `RecordRangeBuilder.get_optimal_compound_records_for_range()` — метод с оптимизацией
- `CompoundDataLoader.get_raw_compound_data_with_optimization_support()` — поддержка флага `use_optimization`
- `PhaseSegmentBuilder` — поддержка VirtualRecord при построении фазовых сегментов

**Примеры оптимизации:**
- **H2O**: 4→3 записи (виртуальное объединение газовых записей 3+4)
- **CeCl3**: 3→2 записи (устранение дублирования жидкой фазы)
- **SiO2**: 4→4 записи (уже оптимально, нет улучшения)

### 9. Система логирования

**SessionLogger:**
- Context manager для логирования каждой сессии запроса
- Автоматическое создание файлов в `logs/sessions/`
- Структурированные логи с временными метками
- Раздельные логи для info/debug/error

**ThermoAgentsLogger:**
- Унифицированное логирование для всех компонентов
- Уровни: DEBUG, INFO, WARNING, ERROR
- Ротация логов по размеру

## Поток выполнения

### 1. Обработка запроса (process_query)

```
User Query
    ↓
ThermodynamicAgent (LLM) → ExtractedReactionParameters
    ↓
Классификация типа запроса
    ↓
┌─────────────────────────┬──────────────────────────┐
│   Табличные данные      │   Расчёт реакции         │
├─────────────────────────┼──────────────────────────┤
│ CompoundDataLoader      │ CompoundDataLoader       │
│   ↓                     │   (для каждого вещества) │
│ PhaseTransitionDetector │   ↓                      │
│   ↓                     │ PhaseTransitionDetector  │
│ RecordRangeBuilder      │   ↓                      │
│   ↓ (оптимизация)        │ RecordRangeBuilder       │
│ ThermodynamicEngine     │   ↓ (оптимизация)         │
│   ↓                     │ ReactionEngine           │
│ UnifiedReactionFormatter│   ↓                      │
│                         │ UnifiedReactionFormatter │
└─────────────────────────┴──────────────────────────┘
    ↓
Formatted Response (text with tables)
```

### 2. Детальная последовательность (для расчёта реакции)

1. **Извлечение параметров** (LLM, ~500-1000ms):
   - Парсинг уравнения реакции (до 10 веществ)
   - Извлечение температурного диапазона
   - Нормализация формул и стехиометрии

2. **Поиск для каждого вещества** (детерминированный, ~50-200ms):
   - CompoundDataLoader проверяет YAML кэш (StaticDataManager)
   - Если нет в кэше → SQLBuilder генерирует запрос с fallback стратегиями
   - DatabaseConnector выполняет запрос

3. **Определение фазовых переходов** (детерминированный, ~10-50ms):
   - PhaseTransitionDetector определяет MeltingPoint и BoilingPoint
   - Анализ температурных диапазонов записей

4. **Отбор записей** (детерминированный, ~10-30ms):
   - RecordRangeBuilder применяет трехуровневую стратегию отбора
   - Приоритизация по классу надёжности (ReliabilityClass 1-4)
   - Оптимальное покрытие температурного диапазона

5. **Оптимизация записей** (детерминированный, ~5-50ms, v2.3+):
   - OptimalRecordSelector минимизирует количество записей
   - Виртуальное объединение записей с идентичными коэффициентами
   - Поддержка фазовых переходов и валидация покрытия
   - Формула оптимальности: Score = 0.5·(1/N) + 0.3·(Avg_reliability/3) + 0.2·Transition_coverage

6. **Расчёты** (детерминированный, ~100-300ms):
   - ThermodynamicEngine по формулам Шомейта
   - Численное интегрирование для H, S, G
   - ReactionEngine для расчёта ΔH, ΔS, ΔG, K реакции

6. **Форматирование** (детерминированный, <100ms):
   - UnifiedReactionFormatter генерирует итоговый отчёт
   - CompoundInfoFormatter для информации о веществах
   - TableFormatter для таблиц результатов
   - InterpretationFormatter для интерпретации результатов

**Общее время:** ~1-2 секунды для полного цикла (зависит от LLM API)
**Дополнительно v2.3+:** +5-50ms на оптимизацию записей

## Производительность

### Метрики производительности

**Время ответа (полный цикл):**
- Среднее время: 1-2 секунды (включая LLM API)
- LLM извлечение параметров: 500-1000ms
- Поиск: 50-200ms
- Определение фазовых переходов: 10-50ms
- Отбор записей: 10-30ms
- Расчёты: 100-300ms
- Форматирование: <100ms

**Эффективность кэша:**
- SQL запросы: 90%+ hit rate (LRU cache в SQLBuilder)
- YAML кэш (StaticDataManager): мгновенный доступ для 10+ веществ

**Использование памяти:**
- Базовое использование: ~50MB
- С активным кэшем: ~150MB
- StaticDataManager (YAML): ~5MB

### Оптимизации

1. **Кэширование:**
   - LRU кэш для SQL запросов (lru_cache в SQLBuilder)
   - YAML кэш для распространённых веществ (StaticDataManager)

2. **Двухстадийная загрузка:**
   - Приоритет YAML кэшу для распространённых веществ
   - Fallback к базе данных при отсутствии в кэше

3. **Трехуровневая стратегия отбора:**
   - RecordRangeBuilder оптимально выбирает записи
   - Минимальное количество записей для покрытия диапазона
   - Приоритизация по ReliabilityClass

4. **Прямые вызовы:**
   - Без message passing overhead
   - Синхронные вызовы детерминированных компонентов
   - Асинхронные вызовы только для LLM

## Компоненты системы

### Модель данных

**models/extraction.py:**
- `ExtractedReactionParameters` — параметры реакции из LLM
  - `query_type`: "compound_data" или "reaction_calculation"
  - `balanced_equation`: str
  - `all_compounds/reactants/products`: List[CompoundInfo] (до 10 веществ)
  - `temperature_range_k`: Tuple[float, float]
  - `temperature_step_k`: float (25-250K)
  - `extraction_confidence`: float (0.0-1.0)

**models/search.py:**
- `DatabaseRecord` — запись из термодинамической базы
- `CompoundSearchResult` — результат поиска одного вещества

**models/static_data.py:**
- `StaticPhaseData` — данные фазы из YAML
- `StaticCompoundData` — полные данные вещества из YAML

### Основные классы

**Оркестратор:**
- `ThermoOrchestrator` — единственный оркестратор системы с интегрированной core-логикой
- `ThermoOrchestratorConfig` — конфигурация оркестратора

**Поиск и SQL:**
- `SQLBuilder` — генератор SQL запросов
- `CommonCompoundsResolver` — резолвер распространённых веществ
- `CompoundSearcher` — координатор поиска
- `DatabaseConnector` — подключение к SQLite

**Core-логика:**
- `CompoundDataLoader` — двухстадийная загрузка данных (YAML кэш → БД)
- `PhaseTransitionDetector` — определение фазовых переходов
- `RecordRangeBuilder` — трехуровневая стратегия отбора записей
- `ThermodynamicEngine` — расчёты по формулам Шомейта
- `ReactionEngine` — расчёт ΔH, ΔS, ΔG, K для реакций

**Фазовая обработка:**
- `PhaseResolver` — определение фазовых состояний
- `PhaseSegmentBuilder` — построение фазовых сегментов

**Форматирование:**
- `UnifiedReactionFormatter` — унифицированное форматирование результатов
- `CompoundInfoFormatter` — информация о веществах
- `TableFormatter` — табличное представление данных
- `InterpretationFormatter` — интерпретация результатов

**Утилиты:**
- `StaticDataManager` — управление YAML кэшем
- `SessionLogger` — логирование сессий
- `chem_utils` — химические утилиты (ионные формулы, композиты)

## Мониторинг и логирование

### SessionLogger

**Context Manager для каждой сессии:**
```python
with SessionLogger() as session_logger:
    orchestrator = create_orchestrator(db_path, session_logger)
    response = await orchestrator.process_query(query)
```

**Функции:**
- Автоматическое создание файлов логов в `logs/sessions/`
- Временные метки для каждой записи
- Уровни: info, debug, error, warning
- Структурированный вывод (разделители, отступы)
- Автоматическое закрытие при выходе из контекста

**Файлы логов:**
- `session_YYYYMMDD_HHMMSS.log` — основной лог сессии
- Ротация по датам
- Хранение в `logs/sessions/`

### Системное логирование

**Стандартное Python logging:**
- Уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Форматирование: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Логгеры для каждого модуля

**Логируемые события:**
- Инициализация компонентов
- Выполнение SQL запросов
- Результаты фильтрации
- Ошибки и исключения
- Метрики производительности

## Конфигурация системы

### ThermoOrchestratorConfig

```python
from thermo_agents.orchestrator import (
    ThermoOrchestrator,
    ThermoOrchestratorConfig
)

config = ThermoOrchestratorConfig(
    # LLM настройки
    llm_api_key=os.getenv("OPENROUTER_API_KEY"),
    llm_base_url="https://openrouter.ai/api/v1",
    llm_model="openai/gpt-4o",
    
    # База данных и YAML кэш
    db_path=Path("data/thermo_data.db"),
    static_data_dir=Path("data/static_compounds"),
    
    # Таймауты
    max_retries=2,
    timeout_seconds=90
)

# Создание оркестратора
orchestrator = ThermoOrchestrator(config, session_logger=logger)
```

### Переменные окружения (.env)

```bash
# LLM API
OPENROUTER_API_KEY=your_api_key_here
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o

# База данных
DB_PATH=data/thermo_data.db

# Логирование
LOG_LEVEL=INFO
```

### Конфигурация для разработки

```python
# Режим разработки с детальным логированием
dev_config = ThermoOrchestratorConfig(
    llm_api_key=os.getenv("OPENROUTER_API_KEY"),
    llm_base_url=os.getenv("LLM_BASE_URL"),
    llm_model=os.getenv("LLM_DEFAULT_MODEL"),
    db_path=Path("data/thermo_data.db"),
    static_data_dir=Path("data/static_compounds")
)

# Создание с SessionLogger для детального логирования
with SessionLogger() as session_logger:
    orchestrator = ThermoOrchestrator(dev_config, session_logger)
    response = await orchestrator.process_query(query)
```

## API Reference

### Основное использование

```python
import asyncio
from pathlib import Path
from thermo_agents.orchestrator import (
    ThermoOrchestrator,
    ThermoOrchestratorConfig
)
from thermo_agents.session_logger import SessionLogger

# Создание конфигурации
config = ThermoOrchestratorConfig(
    llm_api_key="your_key",
    llm_base_url="https://openrouter.ai/api/v1",
    llm_model="openai/gpt-4o",
    db_path=Path("data/thermo_data.db")
)

# Обработка запроса с логированием
async def process_query_example():
    with SessionLogger() as logger:
        orchestrator = ThermoOrchestrator(config, session_logger=logger)
        
        # Табличные данные
        response1 = await orchestrator.process_query(
            "Дай таблицу для H2O при 300-600K с шагом 50 градусов"
        )
        
        # Расчёт реакции
        response2 = await orchestrator.process_query(
            "2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K"
        )
        
        return response1, response2

# Запуск
asyncio.run(process_query_example())
```

### Примеры запросов

**Табличные данные веществ:**
- `"Дай таблицу для H2O при 300-600K с шагом 50 градусов"`
- `"Свойства CO2 от 298 до 1000K"`
- `"Термодинамические данные для Fe2O3 при 400-800K"`

**Расчёты реакций:**
- `"2 H2 + O2 → 2 H2O при 298-1000K"`
- `"Fe2O3 + 3 C → 2 Fe + 3 CO при 800-1200K"`
- `"Реагирует ли сероводород с оксидом железа(II) при 500-700°C?"`
- `"WO3 + 3 H2 → W + 3 H2O при 600-900K"` (до 10 веществ)

### Создание оркестратора (helper function)

```python
from main import create_orchestrator

# Автоматическая конфигурация из .env
orchestrator = create_orchestrator(
    db_path="data/thermo_data.db",
    session_logger=None  # или передать SessionLogger
)
```

## Обработка ошибок

### Типы ошибок

1. **LLM ошибки:**
   - Timeout API запросов
   - Невалидный ответ от LLM
   - Ошибки извлечения параметров
   - **Обработка:** retry логика (до 4 попыток), fallback к базовым значениям

2. **База данных:**
   - Отсутствие соединения с SQLite
   - Пустые результаты поиска
   - Невалидные SQL запросы
   - **Обработка:** информативные сообщения, логирование запросов

3. **Отбор записей:**
   - Отсутствие записей после трехуровневой стратегии
   - Несовместимость фаз с температурой
   - Недостаточное покрытие температурного диапазона
   - **Обработка:** fallback стратегии, расширение критериев поиска

4. **Расчёты:**
   - Отсутствие коэффициентов Шомейта
   - Выход за пределы допустимого диапазона температур
   - Ошибки численного интегрирования
   - **Обработка:** использование стандартных значений (H₂₉₈, S₂₉₈)

5. **Системные:**
   - Переполнение кэша
   - Недостаточная память
   - **Обработка:** автоматическая очистка кэша, логирование

### Стратегии восстановления

**Graceful Degradation:**
- При отсутствии данных в базе → проверка StaticDataManager
- При ошибках расчётов → вывод базовых свойств (H₂₉₈, S₂₉₈, Cp₂₉₈)
- При частичных данных → расчёт только доступных свойств

**Информативные сообщения:**
- Описание проблемы для пользователя
- Рекомендации по исправлению (проверить формулу, указать фазу)
- Логирование в SessionLogger для отладки

**Retry логика:**
- LLM запросы: до 4 попыток с экспоненциальной задержкой
- SQL запросы: 1 попытка (детерминированные ошибки)

## Тестирование

### Структура тестов

**tests/** — директория с тестами
- **unit/** — модульные тесты компонентов
- **integration/** — интеграционные тесты (end-to-end, multi-phase, validation)
- **formatting/** — тесты форматтеров
- **search/** — тесты поиска и SQL
- **test_filtering/** — тесты FilterPipeline
- **performance/** — тесты производительности
- **regression/** — регрессионные тесты

### Запуск тестов

```bash
# Все тесты
uv run pytest

# Конкретная группа
uv run pytest tests/integration/

# С покрытием
uv run pytest --cov=src/thermo_agents

# Конкретный тест
uv run pytest tests/integration/test_multi_phase_end_to_end.py -v
```

### Ключевые интеграционные тесты

**test_end_to_end.py:**
- Полный цикл: запрос → извлечение → поиск → расчёты → форматирование
- Проверка многофазных расчётов
- Валидация фазовых переходов

**test_full_pipeline.py:**
- Тестирование полного конвейера обработки
- Проверка core-логики компонентов
- Валидация промежуточных результатов

**test_compound_validation_integration.py:**
- Проверка поиска распространённых веществ
- Валидация StaticDataManager
- Тестирование fallback стратегий

### Примеры тестов

```python
import pytest
from thermo_agents.orchestrator import (
    ThermoOrchestrator,
    ThermoOrchestratorConfig
)

@pytest.mark.asyncio
async def test_reaction_calculation():
    config = ThermoOrchestratorConfig(
        llm_api_key="test_key",
        db_path=Path("data/thermo_data.db")
    )
    orchestrator = ThermoOrchestrator(config)
    
    query = "2 H2 + O2 → 2 H2O при 298-1000K"
    response = await orchestrator.process_query(query)
    
    assert "H₂O" in response or "H2O" in response
    assert "ΔH" in response or "Delta H" in response
```

## Развертывание

### Требования

- **Python:** 3.12+
- **Пакетный менеджер:** uv (рекомендуется) или pip
- **База данных:** SQLite с термодинамическими данными (thermo_data.db)
- **LLM API:** OpenRouter или совместимый (OpenAI-like API)
- **Память:** 512MB+ RAM для оптимальной работы
- **ОС:** Windows, Linux, macOS

### Установка

```bash
# 1. Клонирование репозитория
git clone <repository-url>
cd agents_for_david

# 2. Установка зависимостей с uv
uv sync

# 3. Активация виртуального окружения
uv shell

# 4. Проверка установки
uv run python --version
```

### Конфигурация окружения

Создайте файл `.env` в корне проекта:

```bash
# LLM API настройки
OPENROUTER_API_KEY=your_api_key_here
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=openai/gpt-4o

# База данных
DB_PATH=data/thermo_data.db

# Логирование
LOG_LEVEL=INFO

# Опционально: многофазные расчёты
STATIC_CACHE_DIR=data/static_compounds
INTEGRATION_POINTS=100
```

### Запуск

**Интерактивный режим:**
```bash
uv run python main.py
```

**Тестовый режим:**
```bash
uv run python main.py --test
```

**Через модуль:**
```python
import asyncio
from main import main_interactive

asyncio.run(main_interactive())
```

### Проверка работоспособности

```bash
# Запуск тестов
uv run pytest tests/integration/test_end_to_end.py -v

# Проверка базы данных
uv run python -c "import sqlite3; conn = sqlite3.connect('data/thermo_data.db'); print('DB OK')"

# Проверка импортов
uv run python -c "from thermo_agents.orchestrator import ThermoOrchestrator; print('Import OK')"
```

## Структура проекта

```
agents_for_david/
├── main.py                          # Точка входа (интерактивный режим)
├── pyproject.toml                   # Конфигурация проекта и зависимости
├── pytest.ini                       # Конфигурация pytest
├── README.md                        # Основная документация
├── .env                             # Переменные окружения (не в git)
│
├── data/                            # Данные
│   ├── thermo_data.db              # SQLite база термодинамических данных
│   └── static_compounds/           # YAML кэш распространённых веществ
│       ├── H2O.yaml
│       ├── CO2.yaml
│       └── ...
│
├── docs/                            # Документация
│   ├── ARCHITECTURE.md             # Архитектура системы (этот файл)
│   ├── user_guide.md               # Руководство пользователя
│   └── examples_query.md           # Примеры запросов
│
├── src/thermo_agents/              # Основной код
│   ├── __init__.py
│   ├── orchestrator.py             # Единственный оркестратор
│   ├── thermodynamic_agent.py      # LLM агент извлечения параметров
│   ├── operations.py               # Система операций
│   ├── prompts.py                  # Промпты для LLM
│   ├── session_logger.py           # Логирование сессий
│   ├── thermo_agents_logger.py     # Системное логирование
│   ├── agent_storage.py            # Хранилище для message passing
│   │
│   ├── search/                     # Модуль поиска
│   │   ├── sql_builder.py         # Генератор SQL запросов
│   │   ├── compound_searcher.py   # Координатор поиска
│   │   ├── database_connector.py  # Подключение к SQLite
│   │   └── compound_index.py      # Индексация соединений
│   │
│   ├── core_logic/                 # Core-логика обработки
│   │   ├── compound_data_loader.py      # Двухстадийная загрузка данных
│   │   ├── phase_transition_detector.py # Определение фазовых переходов
│   │   ├── record_range_builder.py      # Трехуровневая стратегия отбора
│   │   ├── thermodynamic_engine.py      # Расчёты по Шомейту
│   │   └── reaction_engine.py           # Расчёт ΔH, ΔS, ΔG, K
│   │
│   ├── filtering/                  # Модуль фильтрации
│   │   ├── phase_resolver.py      # Определение фазовых состояний
│   │   ├── phase_segment_builder.py # Построение фазовых сегментов
│   │   ├── precomputed_data.py    # Предвычисленные данные
│   │   └── constants.py           # Константы фильтрации
│   │
│   ├── calculations/               # Модуль расчётов
│   │   └── thermodynamic_calculator.py  # Базовый калькулятор
│   │
│   ├── formatting/                 # Модуль форматирования
│   │   ├── unified_reaction_formatter.py # Унифицированный форматтер
│   │   ├── compound_info_formatter.py    # Информация о веществах
│   │   ├── table_formatter.py            # Табличное форматирование
│   │   └── interpretation_formatter.py   # Интерпретация результатов
│   │
│   ├── models/                     # Модели данных
│   │   ├── extraction.py          # ExtractedReactionParameters
│   │   ├── search.py              # DatabaseRecord, CompoundSearchResult
│   │   └── static_data.py         # StaticCompoundData
│   │
│   ├── storage/                    # Хранилище и кэширование
│   │   ├── static_data_manager.py # YAML кэш менеджер
│   │   ├── simple_storage.py      # Простое хранилище
│   │   └── typed_storage.py       # Типизированное хранилище
│   │
│   ├── temperature/                # Температурные утилиты
│   │
│   └── utils/                      # Утилиты
│       └── chem_utils.py          # Химические утилиты
│
├── tests/                          # Тесты
│   ├── unit/                      # Модульные тесты
│   ├── integration/               # Интеграционные тесты
│   │   ├── test_end_to_end.py
│   │   ├── test_full_pipeline.py
│   │   └── test_compound_validation_integration.py
│   ├── formatting/                # Тесты форматтеров
│   ├── search/                    # Тесты поиска
│   ├── test_filtering/            # Тесты фильтрации
│   ├── performance/               # Тесты производительности
│   └── validation/                # Регрессионные тесты
│
├── logs/                          # Логи
│   └── sessions/                  # Логи сессий (автоматически создаётся)
│
└── examples/                       # Примеры использования
    ├── basic_usage.py
    ├── reaction_calculation_example.py
    ├── compound_data_example.py
    └── ...
```

## Зависимости

### Основные библиотеки

- **pydantic-ai** (1.0.8) — LLM агент с валидацией через Pydantic
- **anthropic** (>=0.40.0) — LLM провайдеры
- **pandas** (>=2.2.0) — обработка данных
- **scipy** (>=1.16.2) — численное интегрирование
- **tabulate** (>=0.9.0) — форматирование таблиц
- **python-dotenv** (>=1.0.0) — загрузка переменных окружения
- **aiohttp** (>=3.9.0) — асинхронные HTTP запросы
- **psutil** (>=5.9.0) — мониторинг системы

### Разработка

- **pytest** (>=8.4.2) — фреймворк тестирования
- **pytest-asyncio** — асинхронные тесты
- **pytest-cov** — покрытие кода

### Установка

```bash
# Основные зависимости
uv sync

# Только разработческие
uv sync --group dev
```

---

**Дата обновления:** 8 ноября 2025  
**Статус:** Production Ready