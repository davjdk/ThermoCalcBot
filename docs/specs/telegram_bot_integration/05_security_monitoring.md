# Стадия 5: Безопасность и мониторинг

**Статус:** Ready for implementation
**Версия:** 1.0
**Дата:** 9 ноября 2025

---

## 📋 Обзор

Этот документ определяет требования безопасности, мониторинга и обработки ошибок для Telegram бота ThermoSystem. Безопасность критически важна при работе с токеном бота и данными пользователей.

## 🔐 1. Безопасность

### 1.1. Защита токена

**Токен бота должен храниться исключительно:**
- В переменных окружения (`.env` файл)
- Не в коде, не в git, не в документации
- Использовать механизм `.env.example` для шаблона

```bash
# .env (никогда не коммитить!)
TELEGRAM_BOT_TOKEN=8556976404:AAH_Zxj-yWY9DRSWQVcn5FOq03_mgIim80o
```

### 1.2. Доступ и аутентификация

**Опциональные механизмы контроля:**
- Белый список разрешённых пользователей (user_id)
- Чёрный список злоупотребляющих пользователей
- Rate limiting для предотвращения DDoS атак
- Временная блокировка при превышении лимитов

### 1.3. Валидация входных данных

**Класс QueryValidator:**
```python
class QueryValidator:
    MAX_QUERY_LENGTH = 1000
    FORBIDDEN_PATTERNS = [
        r'[<>]',                    # HTML теги
        r'javascript:',            # JavaScript URL
        r'http[s]?://',            # HTTP ссылки
        r'exec\(',                 # Выполнение кода
        r'eval\(',                 # Eval функции
    ]

    @staticmethod
    def validate_query(query: str) -> ValidationResult:
        """Проверка безопасности запроса"""
        # 1. Проверка длины
        if len(query) > QueryValidator.MAX_QUERY_LENGTH:
            return ValidationResult(False, "Query too long")

        # 2. Проверка запрещенных паттернов
        for pattern in QueryValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return ValidationResult(False, "Forbidden pattern detected")

        # 3. Sanitization HTML/JS
        sanitized = html.escape(query)

        # 4. Валидация химических формул
        if not QueryValidator._validate_chemical_formulas(sanitized):
            return ValidationResult(False, "Invalid chemical formulas")

        return ValidationResult(True, "Valid")
```

### 1.4. Защита от SQL Injection

**Все запросы к базе данных должны использовать:**
- Parameterized queries через `sqlite3` модуль
- ORM стиль работы с БД
- Никаких direct string concatenation для SQL

```python
# ✅ Правильно - parameterized query
cursor.execute(
    "SELECT * FROM compounds WHERE formula LIKE ?",
    (f"%{compound_name}%",)
)

# ❌ Неправильно - SQL injection уязвимость
cursor.execute(
    f"SELECT * FROM compounds WHERE formula LIKE '%{compound_name}%'"
)
```

### 1.5. Конфиденциальность и GDPR

**Политика хранения данных:**
- Логирование только ID пользователей (не имён и ников)
- Хранение сессий в зашифрованном виде
- Автоматическое удаление старых логов (30 дней)
- Возможность удаления пользовательских данных по запросу

**Уровни логирования:**
- `INFO`: ID пользователя, запрос, время обработки
- `DEBUG`: Детальная отладочная информация (только в dev)
- `ERROR`: Детали ошибок с контекстом

## 📊 2. Мониторинг

### 2.1. Ключевые метрики

**Метрики производительности:**
```python
class BotMetrics:
    """Сбор ключевых метрик бота"""

    def __init__(self):
        self.request_count = 0
        self.successful_requests = 0
        self.error_count = 0
        self.avg_response_time = 0.0
        self.active_sessions = 0
        self.start_time = time.time()

    def record_request(self, processing_time: float, success: bool):
        """Запись метрик запроса"""
        self.request_count += 1
        if success:
            self.successful_requests += 1
        else:
            self.error_count += 1

        # Обновление среднего времени ответа
        total_time = self.avg_response_time * (self.request_count - 1) + processing_time
        self.avg_response_time = total_time / self.request_count

    def get_stats(self) -> dict:
        """Получение статистики"""
        uptime = time.time() - self.start_time
        error_rate = (self.error_count / self.request_count * 100) if self.request_count > 0 else 0

        return {
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "successful_requests": self.successful_requests,
            "error_rate_percent": error_rate,
            "avg_response_time_seconds": self.avg_response_time,
            "active_sessions": self.active_sessions,
            "requests_per_minute": self.request_count / (uptime / 60) if uptime > 0 else 0
        }
```

**Топ-10 популярных запросов:**
```python
class QueryAnalytics:
    """Аналитика запросов"""

    def __init__(self):
        self.query_counts = defaultdict(int)
        self.compound_frequency = defaultdict(int)
        self.reaction_frequency = defaultdict(int)

    def record_query(self, query: str, extracted_params: ExtractedReactionParameters):
        """Запрос аналитики"""
        # Нормализация запроса
        normalized_query = self._normalize_query(query)
        self.query_counts[normalized_query] += 1

        # Частота соединений
        for compound in extracted_params.compounds:
            self.compound_frequency[compound.compound_name] += 1

        # Частота реакций (если указано)
        if extracted_params.has_reaction:
            reaction_key = self._generate_reaction_key(extracted_params)
            self.reaction_frequency[reaction_key] += 1

    def get_top_queries(self, limit: int = 10) -> List[tuple]:
        """Топ запросов"""
        return sorted(
            self.query_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
```

### 2.2. Health Checks

**Комплексная проверка состояния системы:**
```python
async def health_check() -> Dict[str, Any]:
    """Проверка здоровья всех компонентов системы"""

    health_status = {
        "overall_status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    # 1. Проверка базы данных
    db_healthy = await _check_database_health()
    health_status["components"]["database"] = {
        "status": "healthy" if db_healthy else "unhealthy",
        "response_time_ms": db_healthy["response_time_ms"] if isinstance(db_healthy, dict) else None
    }

    # 2. Проверка LLM API
    llm_healthy = await _check_llm_api_health()
    health_status["components"]["llm_api"] = {
        "status": "healthy" if llm_healthy else "unhealthy",
        "response_time_ms": llm_healthy["response_time_ms"] if isinstance(llm_healthy, dict) else None
    }

    # 3. Проверка файловой системы
    fs_healthy = await _check_filesystem_health()
    health_status["components"]["filesystem"] = {
        "status": "healthy" if fs_healthy else "unhealthy",
        "available_space_gb": fs_healthy["available_space_gb"] if isinstance(fs_healthy, dict) else None
    }

    # 4. Проверка памяти
    memory_healthy = await _check_memory_health()
    health_status["components"]["memory"] = {
        "status": "healthy" if memory_healthy else "degraded",
        "usage_percent": memory_healthy["usage_percent"] if isinstance(memory_healthy, dict) else None
    }

    # Определение общего статуса
    unhealthy_components = [
        name for name, comp in health_status["components"].items()
        if comp["status"] != "healthy"
    ]

    if unhealthy_components:
        health_status["overall_status"] = "degraded" if len(unhealthy_components) == 1 else "unhealthy"

    return health_status

async def _check_database_health() -> Union[bool, dict]:
    """Проверка подключения к базе данных"""
    try:
        start_time = time.time()
        db_connector = DatabaseConnector()

        # Тестовый запрос
        result = db_connector.execute_query("SELECT COUNT(*) as count FROM compounds LIMIT 1")

        response_time = (time.time() - start_time) * 1000

        return {
            "status": "healthy",
            "response_time_ms": response_time,
            "record_count": result[0]["count"] if result else 0
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

async def _check_llm_api_health() -> Union[bool, dict]:
    """Проверка доступности LLM API"""
    try:
        start_time = time.time()

        # Тестовый запрос к LLM
        thermodynamic_agent = ThermodynamicAgent()
        test_result = await thermodynamic_agent.extract_parameters(
            "H2O properties at 298K", test_mode=True
        )

        response_time = (time.time() - start_time) * 1000

        return {
            "status": "healthy",
            "response_time_ms": response_time,
            "test_successful": test_result is not None
        }
    except Exception as e:
        logger.error(f"LLM API health check failed: {e}")
        return False
```

### 2.3. Алерты и уведомления

**Критические ситуации для алертов:**
- Бот недоступен >5 минут
- Ошибки LLM API >10% запросов
- База данных недоступна
- Превышение лимитов Telegram API
- Использование памяти >80%
- Дисковое пространство <1GB

**Система алертов:**
```python
class AlertManager:
    """Управление алертами и уведомлениями"""

    def __init__(self, admin_user_id: int = None):
        self.admin_user_id = admin_user_id
        self.alert_cooldown = {}
        self.alert_thresholds = {
            "error_rate_percent": 10,
            "memory_usage_percent": 80,
            "disk_space_gb": 1,
            "response_time_seconds": 30
        }

    async def check_and_send_alerts(self, metrics: dict, health_status: dict):
        """Проверка порогов и отправка алертов"""

        # Проверка error rate
        error_rate = metrics.get("error_rate_percent", 0)
        if error_rate > self.alert_thresholds["error_rate_percent"]:
            await self._send_alert(
                "high_error_rate",
                f"⚠️ Высокий процент ошибок: {error_rate:.1f}%"
            )

        # Проверка памяти
        memory_usage = health_status["components"].get("memory", {}).get("usage_percent", 0)
        if memory_usage > self.alert_thresholds["memory_usage_percent"]:
            await self._send_alert(
                "high_memory_usage",
                f"⚠️ Высокое использование памяти: {memory_usage}%"
            )

        # Проверка дискового пространства
        disk_space = health_status["components"].get("filesystem", {}).get("available_space_gb", 0)
        if disk_space < self.alert_thresholds["disk_space_gb"]:
            await self._send_alert(
                "low_disk_space",
                f"⚠️ Мало места на диске: {disk_space:.1f} GB"
            )

    async def _send_alert(self, alert_type: str, message: str):
        """Отправка алерта администратору"""

        # Проверка cooldown для избежания спама
        if alert_type in self.alert_cooldown:
            time_since_last = time.time() - self.alert_cooldown[alert_type]
            if time_since_last < 300:  # 5 минут cooldown
                return

        # Обновление времени последнего алерта
        self.alert_cooldown[alert_type] = time.time()

        # Отправка администратору
        if self.admin_user_id:
            try:
                await bot.send_message(
                    chat_id=self.admin_user_id,
                    text=f"🚨 *ThermoCalcBot Alert*\n\n{message}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
```

## 🛡️ 3. Обработка ошибок

### 3.1. Graceful Degradation

**Стратегии обработки сбоев:**
- LLM недоступен → Детерминированные ответы на базовые запросы
- База данных недоступна → Кэшированные ответы + уведомление
- Файловая система недоступна → Только текстовые ответы
- Telegram API недоступен → Queue + retry механизм

### 3.2. Категории ошибок

**Классификация ошибок:**
```python
class ErrorCategory(Enum):
    """Категории ошибок для обработки"""
    USER_INPUT = "user_input"           # Ошибка ввода пользователя
    LLM_API = "llm_api"                # Ошибка LLM API
    DATABASE = "database"              # Ошибка базы данных
    TELEGRAM_API = "telegram_api"      # Ошибка Telegram API
    FILESYSTEM = "filesystem"          # Ошибка файловой системы
    SYSTEM = "system"                  # Системная ошибка

class ErrorHandler:
    """Централизованная обработка ошибок"""

    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_messages = {
            ErrorCategory.USER_INPUT: "😔 *Неверный формат запроса*\n\nПопробуйте переформулировать или используйте /help",
            ErrorCategory.LLM_API: "🤖 *Сервис временно недоступен*\n\nПопробуйте повторить запрос через минуту",
            ErrorCategory.DATABASE: "🗄️ *База данных недоступна*\n\nПопробуйте позже или используйте /examples",
            ErrorCategory.TELEGRAM_API: "📱 *Ошибка Telegram API*\n\nПопробуйте повторить запрос",
            ErrorCategory.FILESYSTEM: "📁 *Ошибка файловой системы*\n\nПопробуйте отправить запрос заново",
            ErrorCategory.SYSTEM: "⚙️ *Внутренняя ошибка системы*\n\nМы уже работаем над исправлением"
        }

    async def handle_error(self, error: Exception, context: dict) -> str:
        """Обработка ошибки и возврат сообщения для пользователя"""

        # Категоризация ошибки
        category = self._categorize_error(error)

        # Логирование ошибки
        self._log_error(error, category, context)

        # Получение сообщения для пользователя
        user_message = self.error_messages.get(category, self.error_messages[ErrorCategory.SYSTEM])

        # Добавление детальной информации для разработки
        if context.get("is_debug_mode", False):
            user_message += f"\n\n`{str(error)}`"

        return user_message

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Определение категории ошибки"""

        error_message = str(error).lower()
        error_type = type(error).__name__

        if "openrouter" in error_message or "llm" in error_message:
            return ErrorCategory.LLM_API
        elif "database" in error_message or "sqlite" in error_message or "sql" in error_message:
            return ErrorCategory.DATABASE
        elif "telegram" in error_message or "bot" in error_message:
            return ErrorCategory.TELEGRAM_API
        elif "file" in error_message or "path" in error_message or "permission" in error_message:
            return ErrorCategory.FILESYSTEM
        elif "validation" in error_message or "extract" in error_message:
            return ErrorCategory.USER_INPUT
        else:
            return ErrorCategory.SYSTEM

    def _log_error(self, error: Exception, category: ErrorCategory, context: dict):
        """Логирование ошибки"""

        self.error_counts[category] += 1

        logger.error(
            f"Error [{category.value}]: {type(error).__name__}: {error}",
            extra={
                "user_id": context.get("user_id"),
                "query": context.get("query"),
                "category": category.value,
                "error_count": self.error_counts[category]
            }
        )
```

## 🔍 4. Логирование и трассировка

### 4.1. SessionLogger для Telegram

**Расширенное логирование сессий:**
```python
class TelegramSessionLogger(SessionLogger):
    """Логирование сессий Telegram бота"""

    def __init__(self, user_id: int, username: str = None):
        super().__init__()
        self.user_id = user_id
        self.username = username
        self.session_start = time.time()
        self.request_count = 0

        # Создание файла лога сессии
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = f"logs/telegram_sessions/user_{user_id}_{timestamp}.log"

        self.info(f"Session started for user {username}({user_id})")

    def log_user_request(self, query: str):
        """Логирование запроса пользователя"""
        self.request_count += 1
        session_time = time.time() - self.session_start
        self.info(f"Request #{self.request_count}: {query} (session_time: {session_time:.2f}s)")

    def log_llm_extraction(self, confidence: float, extraction_time: float):
        """Логирование извлечения параметров LLM"""
        self.info(f"LLM extraction completed: confidence={confidence:.2f}, time={extraction_time:.2f}s")

    def log_database_search(self, compounds_found: int, search_time: float):
        """Логирование поиска в базе данных"""
        self.info(f"Database search: {compounds_found} compounds found in {search_time:.2f}s")

    def log_calculation_completed(self, calculation_time: float):
        """Логирование завершения расчётов"""
        self.info(f"Thermodynamic calculations completed in {calculation_time:.2f}s")

    def log_bot_response(self, response_length: int, processing_time: float):
        """Логирование ответа бота"""
        total_time = time.time() - self.session_start
        self.info(
            f"Response sent: {response_length} chars, "
            f"processing_time={processing_time:.2f}s, "
            f"total_session_time={total_time:.2f}s"
        )

    def log_file_sent(self, filename: str, file_size_kb: float):
        """Логирование отправки файла"""
        self.info(f"File sent: {filename} ({file_size_kb:.1f} KB)")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        session_time = time.time() - self.session_start
        if exc_type:
            self.error(f"Session ended with error: {exc_val}")
        else:
            self.info(f"Session completed successfully: {self.request_count} requests in {session_time:.2f}s")
```

### 4.2. Структурированное логирование

**Формат логов для анализа:**
```json
{
  "timestamp": "2025-11-09T10:30:15.123Z",
  "level": "INFO",
  "session_id": "user_123456789_20251109_103015",
  "user_id": 123456789,
  "username": "john_doe",
  "event": "user_request",
  "data": {
    "query": "H2O properties 300-500K",
    "request_number": 1,
    "session_time": 15.23
  }
}
```

---

## 📝 Резюме

**Ключевые требования безопасности и мониторинга:**

1. **Безопасность:**
   - Токен только в переменных окружения
   - Валидация входных данных
   - Защита от SQL injection
   - Rate limiting и контроль доступа

2. **Мониторинг:**
   - Health checks для всех компонентов
   - Метрики производительности и использования
   - Алерты для критических ситуаций
   - Аналитика запросов и пользователей

3. **Обработка ошибок:**
   - Graceful degradation при сбоях
   - Категоризация ошибок
   - Понятные сообщения пользователям
   - Детальное логирование для отладки

4. **Логирование:**
   - Сессионное логирование
   - Структурированный формат
   - Автоматическая очистка старых логов
   - Защита приватных данных пользователей

**Следующий этап:** [06_configuration_deployment.md](06_configuration_deployment.md) - Конфигурация окружения и развёртывание.