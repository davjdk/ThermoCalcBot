# Этап 3: Упрощение AgentStorage

**Длительность**: 2-3 дня
**Приоритет**: Средний
**Риски**: Средние
**Зависимости**: Этапы 1-2 завершены

## Обзор

На этом этапе мы упрощаем `AgentStorage`, который реализует сложную систему сообщений (Message Queue), до простого Key-Value хранилища с поддержкой TTL. Текущая реализация избыточна для MVP и усложняет понимание архитектуры.

---

## Задача 3.1: Анализ текущего состояния AgentStorage

**Файл**: `src/thermo_agents/agent_storage.py`

### Текущая функциональность
- **Message Queue система** с корреляционными ID
- **Agent-to-Agent коммуникация** через очереди сообщений
- **TTL поддержка** для временных данных
- **Сессионное управление состояниями**
- **Диагностика и отладка взаимодействий**

### Проблемы текущей реализации
1. **Избыточность**: Сложная MQ система используется минимально
2. **Сложность**: Message Queue паттерн усложняет понимание
3. **Недоиспользование**: Большинство функций не используются в MVP
4. **Поддержка**: Сложная логика усложняет отладку и развитие

### Анализ использования
```bash
# Проверить текущее использование AgentStorage
grep -r "AgentStorage\|send_message\|receive_messages" src/ --include="*.py"
```

---

## Задача 3.2: Проектирование упрощённого хранилища

### Новая архитектура

```python
# src/thermo_agents/storage/simple_storage.py
from typing import Any, Optional, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading

@dataclass
class StorageEntry:
    """Запись в хранилище с TTL."""
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

class SimpleAgentStorage:
    """Упрощённое Key-Value хранилище с поддержкой TTL."""

    def __init__(self, default_ttl_seconds: int = 3600):
        self._storage: Dict[str, StorageEntry] = {}
        self._lock = threading.RLock()
        self.default_ttl = timedelta(seconds=default_ttl_seconds)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Сохранить значение с опциональным TTL."""

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение или default."""

    def delete(self, key: str) -> bool:
        """Удалить ключ. Возвращает True если ключ существовал."""

    def exists(self, key: str) -> bool:
        """Проверить существование ключа."""

    def clear(self) -> None:
        """Очистить всё хранилище."""

    def cleanup_expired(self) -> int:
        """Удалить просроченные записи. Возвращает количество удалённых."""

    def keys(self, pattern: Optional[str] = None) -> list[str]:
        """Получить список ключей (опционально с фильтром)."""

    def size(self) -> int:
        """Количество активных записей."""
```

---

## Задача 3.3: Миграция существующей функциональности

### Сохраняемые методы
- `set(key, value, ttl_seconds)` - основная операция записи
- `get(key, default)` - основная операция чтения
- `delete(key)` - удаление
- `exists(key)` - проверка существования
- `clear()` - очистка

### Удаляемые/упрощаемые методы
- `send_message()` → заменить на `set()`
- `receive_messages()` → заменить на `get()` с паттерном
- `_message_queue` → удалить
- `correlation_id` логика → упростить

### Обратная совместимость

```python
# Оставить совместимость для существующего кода
class AgentStorage(SimpleAgentStorage):
    """Backward compatible wrapper."""

    def send_message(self, source_agent: str, target_agent: str,
                    message_type: str, payload: Any,
                    correlation_id: Optional[str] = None) -> str:
        """Совместимый метод для отправки сообщений."""
        key = f"msg_{target_agent}_{correlation_id or self._generate_id()}"
        self.set(key, {
            "source_agent": source_agent,
            "target_agent": target_agent,
            "message_type": message_type,
            "payload": payload,
            "correlation_id": correlation_id
        })
        return key

    def receive_messages(self, target_agent: str) -> list:
        """Совместимый метод для получения сообщений."""
        pattern = f"msg_{target_agent}_*"
        messages = []
        for key in self.keys(pattern):
            msg = self.get(key)
            if msg:
                messages.append(msg)
                self.delete(key)  # Удалить после прочтения
        return messages
```

---

## Задача 3.4: Обновление ThermodynamicAgent

**Файл**: `src/thermo_agents/thermodynamic_agent.py`

### Текущее использование
```python
# Пример текущего кода
storage.send_message(
    source_agent="thermo",
    target_agent="searcher",
    message_type="request",
    payload={"formula": "H2O"},
    correlation_id=corr_id
)
messages = storage.receive_messages(target_agent="searcher")
```

### Новое использование
```python
# После рефакторинга
storage.set(f"search_request_{corr_id}", {"formula": "H2O"})
request = storage.get(f"search_request_{corr_id}")
# или для результатов
storage.set(f"search_result_{corr_id}", {"results": [...]})
result = storage.get(f"search_result_{corr_id}")
```

### План миграции
1. **Проанализировать текущее использование** в ThermodynamicAgent
2. **Заменить Message Queue вызовы** на простые set/get
3. **Обновить тесты** для ThermodynamicAgent
4. **Проверить функциональность**

---

## Задача 3.5: Обновление тестов

**Файлы**:
- `tests/unit/test_agent_storage.py`
- `tests/integration/test_thermodynamic_agent.py`

### Новые тесты для SimpleAgentStorage

1. **Базовая функциональность**:
   - set/get/delete/exists операции
   - TTL функциональность
   - Очистка просроченных записей

2. **Потоковая безопасность**:
   - Параллельные операции
   - Блокировки и race conditions

3. **Производительность**:
   - Скорость операций
   - Потребление памяти
   - Масштабирование

4. **Обратная совместимость**:
   - Работоспособность старых API
   - Корректность миграции

---

## Порядок выполнения

### Шаг 1: Подготовка (0.5 дня)
```bash
# Создать ветку
git checkout -b refactor/stage-3-agent-storage

# Анализ текущего использования
grep -rn "AgentStorage\|send_message\|receive_messages" src/ tests/
```

### Шаг 2: Реализация SimpleAgentStorage (1 день)
1. Создать `src/thermo_agents/storage/simple_storage.py`
2. Реализовать базовый функционал
3. Добавить backward compatibility wrapper
4. Написать тесты

### Шаг 3: Миграция ThermodynamicAgent (1 день)
1. Обновить использование в `thermodynamic_agent.py`
2. Заменить Message Queue вызовы на set/get
3. Обновить связанные тесты
4. Проверить функциональность

### Шаг 4: Валидация (0.5 дня)
```bash
# Запустить все тесты
uv run pytest tests/ -v

# Интеграционные тесты
uv run pytest tests/integration/ -v

# Проверить производительность
uv run pytest tests/unit/test_agent_storage.py::test_performance -v
```

---

## Ожидаемые результаты

### Упрощение архитектуры
- ✅ **Снижение сложности**: Простое Key-Value хранилище вместо Message Queue
- ✅ **Улучшение читаемости**: Меньше кода, проще понимание
- ✅ **Снижение coupling**: Прямые вызовы вместо сложной маршрутизации

### Сохранение функциональности
- ✅ **Все возможности сохранены**: TTL, управление состояниями
- ✅ **Обратная совместимость**: Существующий код продолжает работать
- ✅ **Производительность**: Не ниже текущей

### Улучшение поддержки
- ✅ **Простота отладки**: Легко отслеживать состояние
- ✅ **Тестирование**: Проще писать и поддерживать тесты
- ✅ **Расширение**: Легко добавлять новые функции

---

## Критерии завершения

- [ ] SimpleAgentStorage реализован и протестирован
- [ ] ThermodynamicAgent обновлён для работы с новым API
- [ ] Все существующие тесты проходят
- [ ] Обратная совместимость обеспечена
- [ ] Документация обновлена
- [ ] Code review завершён
- [ ] Ветка слита с основной

---

## Риски и митигация

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Поломка ThermodynamicAgent | Средняя | Высокое | Сохранить backward compatibility, полное тестирование |
| Увеличение времени выполнения | Низкая | Среднее | Бенчмарки до и после, оптимизация hot paths |
| Проблемы с concurrency | Низкая | Среднее | Thread-safe реализация, тесты на race conditions |

---

## Будущие расширения

После упрощения можно добавить:

1. **Persistence**: Сохранение в файл/БД
2. **Redis интеграция**: Для распределённых систем
3. **Асинхронные операции**: Async/await поддержка
4. **Кэширование**: LRU/MRU стратегии
5. **Метрики**: Статистика использования хранилища

---

## Следующий этап

После завершения Этапа 3 можно переходить к **Этапу 4: Стандартизация**, который унифицирует именование, импорты и константы во всей кодовой базе.