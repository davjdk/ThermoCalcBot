# ThermoSystem v2.1

## Обзор

ThermoSystem — высокопроизводительная система термодинамических агентов с гибридной архитектурой, сочетающей LLM-компоненты для извлечения параметров с детерминированными модулями для поиска, фильтрации, расчётов и форматирования данных. Система поддерживает два типа запросов: табличные данные веществ и термодинамические расчёты реакций.

## Ключевые возможности v2.1

### Два типа запросов

1. **Табличные данные веществ** — получение термодинамических свойств (Cp, H, S, G) отдельного вещества в заданном температурном диапазоне
2. **Расчёт реакций** — термодинамический анализ химических реакций с расчётом ΔH, ΔS, ΔG реакции

### Многофазные расчёты (Big Bang Strategy)

- **Автоматическое определение фазовых сегментов** и переходов (плавление, кипение, сублимация)
- **StaticDataManager** для кэширования распространённых веществ из YAML-файлов
- **ThermodynamicCalculator** с численным интегрированием по формулам Шомейта
- **Поддержка Unicode** — химические формулы с подстрочными индексами (H₂O, CO₂)

## Архитектурные компоненты

### 1. Гибридная архитектура (Hybrid Architecture)

**LLM-компонент:**
- `ThermodynamicAgent` — извлечение параметров из естественного языка
- Использует PydanticAI + OpenRouter API для структурированного вывода
- Модель: `ExtractedReactionParameters` с валидацией через Pydantic

**Детерминированные компоненты:**
- `CompoundSearcher` — многоуровневый поиск соединений (формула, название, common compounds)
- `FilterPipeline` — 6-стадийный конвейер фильтрации записей
- `ThermodynamicCalculator` — расчёты по формулам Шомейта с численным интегрированием
- `CompoundDataFormatter` и `ReactionCalculationFormatter` — профессиональное форматирование через tabulate

### 2. Оркестраторы системы

**MultiPhaseOrchestrator** (основной, рекомендуемый):
- **Big Bang стратегия** — ВСЕГДА использует многофазные расчёты
- Автоматическая интеграция StaticDataManager для YAML кэша
- Поддержка фазовых переходов и сегментов
- 6-стадийный FilterPipeline с SessionLogger
- Форматтеры: CompoundDataFormatter + ReactionCalculationFormatter

**ThermoOrchestrator** (legacy, для совместимости):
- Оптимизированная обработка с прямыми вызовами компонентов
- Без message passing overhead
- Используется в legacy кодовой базе

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

### 4. Конвейер фильтрации (FilterPipeline)

**6 стадий обработки:**

1. **DeduplicationStage** — удаление дубликатов записей
2. **TemperatureFilterStage** — базовая температурная фильтрация
3. **PhaseBasedTemperatureStage** — умная фазовая и температурная фильтрация с PhaseResolver
4. **PhaseSelectionStage** — выбор наиболее подходящей фазы
5. **FormulaConsistencyStage** — проверка согласованности формул
6. **ReliabilityPriorityStage** — приоритизация по классу надёжности (1-4)

**Оптимизации:**
- Кэширование результатов с TTL (5 минут)
- Ленивая загрузка для больших наборов данных
- Пакетная обработка записей
- Индексация для быстрых поисков
- Hit rate кэша: 98%+

**PhaseResolver:**
- Определение фазовых состояний на основе температуры
- Поддержка переходов: плавление, кипение, сублимация
- Эвристики для различных классов веществ (металлы, неметаллы, соли)

### 5. Термодинамический калькулятор

**ThermodynamicCalculator:**
- **Формулы Шомейта** для расчёта Cp(T):
  ```
  Cp(T) = f1 + f2*T/1000 + f3*T^(-2)*10^5 + f4*T^2/10^6 + f5*T^(-3)*10^3 + f6*T^3*10^(-9)
  ```
- **Численное интегрирование** для H(T), S(T), G(T) через scipy.integrate.quad
- Настраиваемое количество точек интегрирования (по умолчанию 100-400)
- Поддержка многофазных расчётов с фазовыми переходами
- LRU-кэширование для повторяющихся расчётов

**Типы данных:**
- `ThermodynamicProperties` — свойства при заданной температуре (T, Cp, H, S, G)
- `ThermodynamicTable` — таблица свойств по диапазону температур
- `MultiPhaseProperties` — многофазные расчёты с сегментами и переходами

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

**CompoundDataFormatter:**
- Табличный вывод через `tabulate`
- Unicode формулы (H₂O вместо H2O)
- Базовые свойства: H₂₉₈, S₂₉₈, Cp₂₉₈, класс надёжности
- Таблица свойств по температуре: T, Cp, H, S, G

**ReactionCalculationFormatter:**
- Форматирование уравнения реакции с Unicode стрелками (→)
- Описание метода расчёта
- Данные веществ (формулы, фазы)
- Таблица результатов реакции: T, ΔH, ΔS, ΔG

### 8. Система логирования

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
│ CompoundSearcher        │ CompoundSearcher         │
│   ↓                     │   (для каждого вещества) │
│ FilterPipeline          │   ↓                      │
│   ↓                     │ FilterPipeline           │
│ ThermodynamicCalculator │   ↓                      │
│   ↓                     │ ThermodynamicCalculator  │
│ CompoundDataFormatter   │   ↓                      │
│                         │ ReactionCalculationFormatter │
└─────────────────────────┴──────────────────────────┘
    ↓
Formatted Response (text with tables)
```

### 2. Детальная последовательность (для расчёта реакции)

1. **Извлечение параметров** (LLM, ~500-1000ms):
   - Парсинг уравнения реакции
   - Извлечение температурного диапазона
   - Нормализация формул и стехиометрии

2. **Поиск для каждого вещества** (детерминированный, ~50-200ms):
   - SQLBuilder генерирует запрос с fallback стратегиями
   - DatabaseConnector выполняет запрос
   - StaticDataManager проверяет YAML кэш (если доступен)

3. **Фильтрация** (детерминированный, ~10-50ms):
   - 6 стадий последовательной фильтрации
   - Кэширование промежуточных результатов
   - PhaseResolver для определения фаз

4. **Расчёты** (детерминированный, ~100-300ms):
   - ThermodynamicCalculator по формулам Шомейта
   - Численное интегрирование для H, S, G
   - Расчёт ΔH, ΔS, ΔG реакции

5. **Форматирование** (детерминированный, <100ms):
   - Генерация таблиц через tabulate
   - Unicode форматирование формул
   - Структурированный текстовый вывод

**Общее время:** ~1-2 секунды для полного цикла (зависит от LLM API)

## Производительность

### Метрики производительности

**Время ответа (полный цикл):**
- Среднее время: 1-2 секунды (включая LLM API)
- LLM извлечение параметров: 500-1000ms
- Поиск + фильтрация: 60-250ms
- Расчёты: 100-300ms
- Форматирование: <100ms
- Кэшированные повторные запросы: <100ms

**Эффективность кэша:**
- SQL запросы: 90%+ hit rate
- Фильтрация: 98%+ hit rate
- Расчёты (LRU): зависит от повторяемости запросов
- StaticDataManager: мгновенный доступ для 10+ веществ

**Использование памяти:**
- Базовое использование: ~50MB
- С активным кэшем: ~150MB
- StaticDataManager (YAML): ~5MB
- FilterPipeline кэш: настраиваемый (по умолчанию 1000 записей)

### Оптимизации

1. **Кэширование:**
   - LRU кэш для SQL запросов
   - TTL-кэш для результатов фильтрации
   - LRU кэш для термодинамических расчётов

2. **Ленивые вычисления:**
   - Загрузка данных только при необходимости
   - Пакетная обработка больших наборов

3. **Индексация:**
   - Префиксные индексы для формул
   - Температурные индексы для диапазонов

4. **Прямые вызовы:**
   - Без message passing overhead
   - Синхронные вызовы детерминированных компонентов

## Компоненты системы

### Модель данных

**models/extraction.py:**
- `ExtractedReactionParameters` — параметры реакции из LLM
  - `balanced_equation`: str
  - `reactants/products`: List[CompoundInfo]
  - `temperature_range_k`: Tuple[float, float]
  - `stoichiometry`: Dict[str, float]

**models/search.py:**
- `DatabaseRecord` — запись из термодинамической базы
- `CompoundSearchResult` — результат поиска одного вещества
- `MultiPhaseSearchResult` — результат многофазного поиска
- `PhaseSegment` — сегмент одной фазы
- `PhaseTransition` — фазовый переход (плавление, кипение, сублимация)

**models/aggregation.py:**
- `AggregatedReactionData` — агрегированные данные реакции
- `FilterStatistics` — статистика фильтрации

**models/static_data.py:**
- `StaticPhaseData` — данные фазы из YAML
- `StaticCompoundData` — полные данные вещества из YAML

### Основные классы

**Оркестраторы:**
- `MultiPhaseOrchestrator` — основной оркестратор с многофазными расчётами
- `ThermoOrchestrator` — legacy оркестратор (для совместимости)
- `MultiPhaseOrchestratorConfig` — конфигурация оркестратора

**Поиск и SQL:**
- `SQLBuilder` — генератор SQL запросов
- `CommonCompoundsResolver` — резолвер распространённых веществ
- `CompoundSearcher` — координатор поиска
- `DatabaseConnector` — подключение к SQLite

**Фильтрация:**
- `FilterPipeline` — конвейер фильтрации
- `FilterStage` (ABC) — базовый класс стадии
- `DeduplicationStage`, `TemperatureFilterStage`, `PhaseBasedTemperatureStage`, 
  `PhaseSelectionStage`, `FormulaConsistencyStage`, `ReliabilityPriorityStage`
- `PhaseResolver` — определение фазовых состояний
- `TemperatureResolver` — разрешение температурных диапазонов

**Расчёты:**
- `ThermodynamicCalculator` — расчёты по формулам Шомейта
- `ThermodynamicProperties` — свойства при температуре
- `ThermodynamicTable` — таблица свойств

**Форматирование:**
- `CompoundDataFormatter` — табличные данные веществ
- `ReactionCalculationFormatter` — расчёты реакций

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

### MultiPhaseOrchestratorConfig

```python
from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)

config = MultiPhaseOrchestratorConfig(
    # База данных
    db_path="data/thermo_data.db",
    
    # LLM настройки
    llm_api_key=os.getenv("OPENROUTER_API_KEY"),
    llm_base_url="https://openrouter.ai/api/v1",
    llm_model="openai/gpt-4o",
    
    # Многофазные расчёты
    static_cache_dir="data/static_compounds",
    integration_points=100,  # Точность численного интегрирования
    
    # Таймауты
    max_retries=2,
    timeout_seconds=90
)

# Создание оркестратора
orchestrator = MultiPhaseOrchestrator(config, session_logger=logger)
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
dev_config = MultiPhaseOrchestratorConfig(
    db_path="data/thermo_data.db",
    llm_api_key=os.getenv("OPENROUTER_API_KEY"),
    llm_base_url=os.getenv("LLM_BASE_URL"),
    llm_model=os.getenv("LLM_DEFAULT_MODEL"),
    static_cache_dir="data/static_compounds",
    integration_points=100,
)

# Создание с SessionLogger для детального логирования
with SessionLogger() as session_logger:
    orchestrator = MultiPhaseOrchestrator(dev_config, session_logger)
    response = await orchestrator.process_query(query)
```

## API Reference

### Основное использование

```python
import asyncio
from pathlib import Path
from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)
from thermo_agents.session_logger import SessionLogger

# Создание конфигурации
config = MultiPhaseOrchestratorConfig(
    db_path="data/thermo_data.db",
    llm_api_key="your_key",
    llm_base_url="https://openrouter.ai/api/v1",
    llm_model="openai/gpt-4o"
)

# Обработка запроса с логированием
async def process_query_example():
    with SessionLogger() as logger:
        orchestrator = MultiPhaseOrchestrator(config, session_logger=logger)
        
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

3. **Фильтрация:**
   - Отсутствие записей после фильтрации
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

**test_multi_phase_end_to_end.py:**
- Полный цикл: запрос → извлечение → поиск → фильтрация → расчёты → форматирование
- Проверка многофазных расчётов
- Валидация фазовых переходов

**test_full_pipeline.py:**
- Тестирование FilterPipeline со всеми 6 стадиями
- Проверка кэширования
- Валидация промежуточных результатов

**test_compound_validation_integration.py:**
- Проверка поиска распространённых веществ
- Валидация StaticDataManager
- Тестирование fallback стратегий

### Примеры тестов

```python
import pytest
from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)

@pytest.mark.asyncio
async def test_reaction_calculation():
    config = MultiPhaseOrchestratorConfig(
        db_path="data/thermo_data.db",
        llm_api_key="test_key"
    )
    orchestrator = MultiPhaseOrchestrator(config)
    
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
uv run pytest tests/integration/test_multi_phase_end_to_end.py -v

# Проверка базы данных
uv run python -c "import sqlite3; conn = sqlite3.connect('data/thermo_data.db'); print('DB OK')"

# Проверка импортов
uv run python -c "from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator; print('Import OK')"
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
│   ├── orchestrator.py             # Legacy оркестратор
│   ├── orchestrator_multi_phase.py # Основной многофазный оркестратор
│   ├── thermodynamic_agent.py      # LLM агент извлечения параметров
│   ├── operations.py               # Система операций
│   ├── prompts.py                  # Промпты для LLM
│   ├── session_logger.py           # Логирование сессий
│   ├── thermo_agents_logger.py     # Системное логирование
│   │
│   ├── search/                     # Модуль поиска
│   │   ├── sql_builder.py         # Генератор SQL запросов
│   │   ├── compound_searcher.py   # Координатор поиска
│   │   ├── database_connector.py  # Подключение к SQLite
│   │   └── common_compounds.py    # Резолвер распространённых веществ
│   │
│   ├── filtering/                  # Модуль фильтрации
│   │   ├── filter_pipeline.py     # Конвейер фильтрации
│   │   ├── filter_stages.py       # Базовые стадии фильтрации
│   │   ├── phase_based_temperature_stage.py
│   │   ├── phase_resolver.py      # Определение фазовых состояний
│   │   ├── temperature_resolver.py
│   │   └── constants.py           # Константы фильтрации
│   │
│   ├── calculations/               # Модуль расчётов
│   │   └── thermodynamic_calculator.py  # Расчёты по Шомейту
│   │
│   ├── formatting/                 # Модуль форматирования
│   │   ├── compound_data_formatter.py       # Табличные данные
│   │   └── reaction_calculation_formatter.py # Расчёты реакций
│   │
│   ├── models/                     # Модели данных
│   │   ├── extraction.py          # ExtractedReactionParameters
│   │   ├── search.py              # DatabaseRecord, CompoundSearchResult
│   │   ├── aggregation.py         # AggregatedReactionData
│   │   └── static_data.py         # StaticCompoundData
│   │
│   ├── storage/                    # Хранилище и кэширование
│   │   └── static_data_manager.py # YAML кэш менеджер
│   │
│   ├── config/                     # Конфигурация
│   │   └── multi_phase_config.py  # Настройки многофазных расчётов
│   │
│   └── utils/                      # Утилиты
│       └── chem_utils.py          # Химические утилиты
│
├── tests/                          # Тесты
│   ├── unit/                      # Модульные тесты
│   ├── integration/               # Интеграционные тесты
│   ├── formatting/                # Тесты форматтеров
│   ├── search/                    # Тесты поиска
│   ├── test_filtering/            # Тесты фильтрации
│   ├── performance/               # Тесты производительности
│   └── regression/                # Регрессионные тесты
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

## Будущие улучшения

### Краткосрочные (v2.2)

1. **Расширение StaticDataManager:**
   - Добавление большего количества распространённых веществ
   - Автоматическая генерация YAML из базы данных
   - Валидация и обновление кэша

2. **Улучшение производительности:**
   - Параллельный поиск для нескольких веществ
   - Оптимизация численного интегрирования
   - Предвычисление часто запрашиваемых диапазонов

3. **Расширение форматирования:**
   - Вывод графиков (через matplotlib)
   - Экспорт в CSV, JSON
   - Поддержка LaTeX формул

### Среднесрочные (v3.0)

1. **Web API:**
   - REST API через FastAPI
   - WebSocket для real-time обновлений
   - OpenAPI документация

2. **Дополнительные типы расчётов:**
   - Химическое равновесие
   - Константы равновесия
   - Диаграммы Эллингема

3. **Multi-LLM поддержка:**
   - Выбор модели для разных задач
   - Fallback между провайдерами
   - Локальные LLM (llama.cpp)

### Долгосрочные

1. **GUI приложение:**
   - Десктоп приложение (Electron, PyQt)
   - Интерактивные графики
   - Сохранение истории расчётов

2. **Расширенная база данных:**
   - Кинетические данные
   - Электрохимические свойства
   - Данные по растворимости

3. **Масштабирование:**
   - Распределённое кэширование (Redis)
   - Горизонтальное масштабирование
   - Load balancing для LLM API

## История изменений

### v2.1 (текущая)
- ✅ Многофазные расчёты (Big Bang стратегия)
- ✅ StaticDataManager для YAML кэша
- ✅ ThermodynamicCalculator с численным интегрированием
- ✅ 6-стадийный FilterPipeline
- ✅ Два типа запросов: табличные данные и реакции
- ✅ SessionLogger для детального логирования
- ✅ Unicode поддержка в форматировании

### v2.0 (архив)
- Гибридная архитектура (LLM + детерминированная логика)
- CompoundSearcher с многоуровневым поиском
- ReactionAggregator для агрегации данных
- TableFormatter через tabulate

### v1.x (legacy)
- Полностью LLM-based архитектура
- Агенты для каждой задачи
- Message passing между агентами

---

**Версия:** 2.1  
**Дата обновления:** 29 октября 2025  
**Статус:** Production Ready  
**Автор документации:** AI Assistant (GitHub Copilot)