# Этап 2: Рефакторинг системы логирования

**Длительность**: 2-3 дня
**Приоритет**: Средний
**Риски**: Средние
**Зависимости**: Этап 1 завершён

## Обзор

На этом этапе мы объединяем дублирующуюся функциональность `OperationLogger` и `SessionLogger` в единый, более мощный компонент логирования, который обеспечивает структурированное логирование всех операций системы.

---

## Задача 2.1: Анализ текущего состояния логирования

**Файлы**:
- `src/thermo_agents/operations.py`
- `src/thermo_agents/thermo_agents_logger.py`

### Текущее состояние
- `SessionLogger` - основное сессионное логирование с correlation IDs
- `OperationLogger` - структурированное логирование операций (мало используется)
- Частичное дублирование функциональности
- Разные подходы к форматированию вывода

### Проблемы
1. **Дублирование**: Оба компонента выполняют схожие функции
2. **Непоследовательность**: Разные форматы и подходы
3. **Сложность поддержки**: Две системы вместо одной
4. **Низкое использование**: `OperationLogger` используется минимально

---

## Задача 2.2: Проектирование унифицированного логгера

### Новая архитектура

```python
# src/thermo_agents/logging/unified_logger.py
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    PERFORMANCE = "PERFORMANCE"

@dataclass
class LogEntry:
    timestamp: datetime
    level: LogLevel
    session_id: str
    operation_type: Optional[str]
    message: str
    metadata: Dict[str, Any]
    correlation_id: Optional[str] = None
    duration_ms: Optional[float] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None

class UnifiedLogger:
    """Унифицированный логгер для всех операций системы."""

    def __init__(self, session_id: str, log_level: LogLevel = LogLevel.INFO):
        self.session_id = session_id
        self.log_level = log_level
        self.operations_stack: List[str] = []

    def start_operation(self, operation_type: str, **metadata) -> str:
        """Начать операцию с таймером."""

    def end_operation(self, operation_id: str, **metadata):
        """Завершить операцию и записать метрики."""

    def log(self, level: LogLevel, message: str, **metadata):
        """Записать сообщение с метаданными."""

    def debug(self, message: str, **metadata):
        """DEBUG уровень логирования."""

    def info(self, message: str, **metadata):
        """INFO уровень логирования."""

    def warning(self, message: str, **metadata):
        """WARNING уровень логирования."""

    def error(self, message: str, error: Optional[Exception] = None, **metadata):
        """ERROR уровень логирования."""

    def performance(self, operation: str, duration_ms: float, **metadata):
        """PERFORMANCE уровень логирования."""
```

---

## Задача 2.3: Миграция существующей функциональности

### Шаг 1: Создание UnifiedLogger

**Файл**: `src/thermo_agents/logging/unified_logger.py`

1. Создать новую директорию `src/thermo_agents/logging/`
2. Реализовать `UnifiedLogger` с полной функциональностью
3. Добавить backward compatibility методы

### Шаг 2: Обновление SessionLogger

**Файл**: `src/thermo_agents/thermo_agents_logger.py`

```python
# Обновить для использования UnifiedLogger как backend
from src.thermo_agents.logging.unified_logger import UnifiedLogger, LogLevel

class SessionLogger:
    """Совместимый wrapper для UnifiedLogger."""

    def __init__(self, session_id: str):
        self._logger = UnifiedLogger(session_id)
        self.session_id = session_id

    # Методы сохраняются для обратной совместимости
    def info(self, message: str, **kwargs):
        self._logger.info(message, **kwargs)

    def debug(self, message: str, **kwargs):
        self._logger.debug(message, **kwargs)

    def error(self, message: str, **kwargs):
        self._logger.error(message, **kwargs)
```

### Шаг 3: Миграция OperationLogger

**Файл**: `src/thermo_agents/operations.py`

```python
# Обновить для использования UnifiedLogger
from src.thermo_agents.logging.unified_logger import UnifiedLogger

# Удалить OperationLogger класс
# Оставить только модели Operation и OperationType для обратной совместимости
```

---

## Задача 2.4: Обновление всех точек использования

### Файлы для обновления

1. **Оркестратор** (`src/thermo_agents/orchestrator.py`):
   ```python
   # Заменить
   from src.thermo_agents.thermo_agents_logger import SessionLogger
   from src.thermo_agents.operations import OperationLogger

   # На
   from src.thermo_agents.logging.unified_logger import UnifiedLogger
   ```

2. **Модули поиска** (`src/thermo_agents/search/`):
   - `compound_searcher.py`
   - `database_connector.py`

3. **Модули фильтрации** (`src/thermo_agents/filtering/`):
   - `filter_pipeline.py`
   - `filter_stages.py`

4. **Модули агрегации** (`src/thermo_agents/aggregation/`):
   - `reaction_aggregator.py`

### Пример миграции

**До**:
```python
logger = SessionLogger(session_id)
operation_logger = OperationLogger()
operation_logger.start_operation("search_compound")
logger.info("Searching for compound")
operation_logger.end_operation({"result": "success"})
```

**После**:
```python
logger = UnifiedLogger(session_id)
operation_id = logger.start_operation("search_compound", compound="H2O")
logger.info("Searching for compound", compound="H2O")
logger.end_operation(operation_id, result="success")
```

---

## Задача 2.5: Написание тестов для UnifiedLogger

**Файл**: `tests/unit/test_unified_logger.py`

### Тесты для реализации

1. **Базовая функциональность**:
   - Создание логгера
   - Запись сообщений разных уровней
   - Форматирование вывода

2. **Операции**:
   - Начало и завершение операций
   - Расчёт длительности
   - Вложенные операции

3. **Метрики производительности**:
   - Запись CPU и памяти
   - Performance logging
   - Агрегация метрик

4. **Обратная совместимость**:
   - Совместимость с существующим SessionLogger API
   - Сохранение формата вывода

5. **Интеграционные тесты**:
   - Интеграция с существующими компонентами
   - Запись в файлы
   - Многопоточная безопасность

---

## Порядок выполнения

### Шаг 1: Подготовка (0.5 дня)
```bash
# Создать ветку
git checkout -b refactor/stage-2-logging

# Создать структуру
mkdir -p src/thermo_agents/logging
mkdir -p tests/unit/logging
```

### Шаг 2: Реализация (1 день)
1. Создать `UnifiedLogger` с полной функциональностью
2. Обновить `SessionLogger` как wrapper
3. Удалить/рефакторить `OperationLogger`
4. Создать тесты для нового логгера

### Шаг 3: Миграция (1 день)
1. Обновить все импорты в коде
2. Заменить использования OperationLogger
3. Запустить все тесты и исправить проблемы
4. Обновить документацию

### Шаг 4: Валидация (0.5 дня)
```bash
# Запустить все тесты
uv run pytest tests/ -v --tb=short

# Проверить покрытие
uv run pytest tests/ --cov=src/thermo_agents/logging

# Интеграционные тесты
uv run pytest tests/integration/test_end_to_end.py -v
```

---

## Ожидаемые результаты

### Улучшения качества кода
- ✅ Единая система логирования вместо двух дублирующихся
- ✅ Улучшенная структура логов с метаданными
- ✅ Лучшие метрики производительности
- ✅ Упрощение поддержки и развития

### Функциональность
- ✅ Все существующие функции сохранены
- ✅ Улучшенное отслеживание операций
- ✅ Богатые метрики производительности
- ✅ Улучшенная читаемость логов

### Производительность
- ✅ Низкий overhead на логирование
- ✅ Эффективная запись в файлы
- ✅ Опциональное асинхронное логирование

---

## Критерии завершения

- [ ] `UnifiedLogger` реализован и протестирован
- [ ] Все существующие тесты проходят
- [ ] Тесты покрытия для нового логгера (>90%)
- [ ] Все импорты обновлены в кодовой базе
- [ ] Документация обновлена
- [ ] Code review завершён
- [ ] Ветка слита с основной

---

## Обратная совместимость

Для обеспечения плавного перехода:

1. **Сохранить API `SessionLogger`** как thin wrapper
2. **Оставить модели из `operations.py`** для существующего кода
3. **Постепенная миграция** точек использования
4. **Документация по переходу** в CHANGELOG

---

## Следующий этап

После завершения Этапа 2 можно переходить к **Этапу 3: Упрощение AgentStorage**, который преобразует сложную Message Queue систему в простое Key-Value хранилище.