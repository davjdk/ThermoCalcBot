# Архитектура и дизайн системы

**Проект:** ThermoSystem Telegram Bot Integration
**Версия документа:** 1.1
**Дата:** 9 ноября 2025

---

## 🏗️ 1. Компонентная архитектура

### 1.1. Общая архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────────┐
│                      Telegram Bot API                           │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                ThermoSystemTelegramBot                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  MessageHandler │  │  CommandHandler │  │ ResponseFormatter│ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  SessionManager │  │  RateLimiter    │  │  ErrorHandler   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  FileHandler    │  │ SmartResponse   │  │  HealthChecker  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                   ThermoOrchestrator v2.2                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ThermodynamicAgent│  │  Search System  │  │Calculation Engine│ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  Data Loading   │  │  Filtering      │  │  Formatting     │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│              База данных и статические данные                   │
│  ┌─────────────────┐              ┌─────────────────┐          │
│  │thermo_data.db   │              │YAML кэш файлов  │          │
│  │   316K записей  │              │   распространён │          │
│  └─────────────────┘              │   ных веществ    │          │
│                                   └─────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2. Структура модуля Telegram бота

```
src/thermo_agents/telegram_bot/
├── __init__.py
├── bot.py                     # Основной класс бота
├── handlers/
│   ├── __init__.py
│   ├── message_handler.py     # Обработка текстовых сообщений
│   ├── bot_command_handlers.py # Обработка команд (/start, /help)
│   └── callback_handler.py    # Обработка inline кнопок
├── formatters/
│   ├── __init__.py
│   ├── telegram_formatter.py  # Адаптация вывода для Telegram
│   └── message_splitter.py    # Разделение длинных сообщений
├── managers/
│   ├── __init__.py
│   ├── session_manager.py     # Управление сессиями бота
│   ├── rate_limiter.py        # Ограничение запросов
│   ├── file_handler.py        # Управление временными файлами
│   └── smart_response.py      # Умная отправка (сообщение/файл)
├── config.py                  # Конфигурация бота
└── utils.py                   # Утилиты для Telegram
```

### 1.3. Основные компоненты

#### 1.3.1. ThermoSystemTelegramBot (Основной класс)

**Ответственности:**
- Инициализация Telegram приложения
- Настройка обработчиков команд и сообщений
- Управление жизненным циклом бота
- Graceful shutdown

**Ключевые методы:**
```python
class ThermoSystemTelegramBot:
    def __init__(self, config: TelegramBotConfig)
    def _setup_handlers(self) -> None
    async def start(self) -> None
    async def shutdown(self) -> None
    async def health_check(self) -> dict
```

#### 1.3.2. MessageHandler (Обработчик сообщений)

**Ответственности:**
- Обработка текстовых сообщений пользователей
- Интеграция с ThermoOrchestrator
- Отправка прогресс индикаторов
- Форматирование ответов для Telegram

**Ключевые методы:**
```python
class TelegramMessageHandler:
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE)
    async def _send_typing_indicator(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE)
    async def _handle_calculation_response(self, update: Update, response: str, context: ContextTypes.DEFAULT_TYPE)
```

#### 1.3.3. CommandHandlers (Обработчики команд)

**Ответственности:**
- Обработка системных команд (/start, /help, /status)
- Валидация параметров команд
- Генерация справочной информации
- Обработка административных команд

**Ключевые методы:**
```python
class BotCommandHandlers:
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE)
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE)
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE)
    async def examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE)
```

#### 1.3.4. TelegramResponseFormatter (Форматирование ответов)

**Ответственности:**
- Адаптация вывода под ограничения Telegram
- Markdown форматирование
- Разделение длинных сообщений
- Unicode обработка химических формул

**Ключевые методы:**
```python
class TelegramResponseFormatter:
    async def format_response(self, response: str) -> List[str]
    def _split_long_message(self, message: str) -> List[str]
    def _apply_markdown_formatting(self, text: str) -> str
    def _adapt_unicode_symbols(self, text: str) -> str
```

---

## 🔄 2. Поток обработки запроса

### 2.1. Детальный поток обработки

```
User Message (Telegram)
    ↓
1. Message Parsing & Validation
    ├─ Telegram Update object parsing
    ├─ Input sanitization & validation
    └─ Query length & content checks
    ↓
2. Command Recognition
    ├─ Check for system commands (/start, /help, /status)
    ├─ Extract command parameters if any
    └─ Route to appropriate handler
    ↓
3. Session Management
    ├─ Create or retrieve user session
    ├─ Initialize TelegramSessionLogger
    ├─ Log user request details
    └─ Update session activity tracking
    ↓
4. Pre-processing
    ├─ Send typing indicator (ChatAction.TYPING)
    ├─ Validate query format & content
    └─ Check rate limits
    ↓
5. ThermoOrchestrator Integration
    ├─ orchestrator.process_query(query)
    │   ├─ ThermodynamicAgent.extract_parameters()
    │   ├─ Compound Search (SQL Builder)
    │   ├─ Data Loading & Filtering
    │   ├─ Thermodynamic Calculations
    │   └─ Response Formatting
    └─ Receive full response string
    ↓
6. Response Processing
    ├─ Analyze response length & complexity
    ├─ Determine message vs file strategy
    ├─ Format for Telegram limitations
    └─ Apply Markdown & Unicode formatting
    ↓
7. Smart Response Delivery
    ├─ If <3000 chars → Send as message(s)
    └─ If ≥3000 chars → Send as TXT file
        ├─ FileHandler.create_temp_file()
        ├─ TelegramFileHandler.send_file()
        └─ Send summary message
    ↓
8. Post-processing
    ├─ Log response metrics
    ├─ Update session statistics
    ├─ Cleanup temporary resources
    └─ Error handling & user feedback
```

### 2.2. Асинхронная обработка

**Concurrency Strategy:**
```python
class MessageQueue:
    def __init__(self, max_concurrent=20):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.processing_tasks = set()
        self.active_sessions = {}

    async def add_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        async with self.semaphore:
            task = asyncio.create_task(self.process_message(update, context))
            self.processing_tasks.add(task)
            task.add_done_callback(self.processing_tasks.discard)
```

**Async Pipeline:**
1. **Input Validation** - ~10ms
2. **Session Setup** - ~5ms
3. **ThermoOrchestrator Processing** - 2000ms-8000ms (основное время)
4. **Response Formatting** - ~100ms
5. **Delivery** - 100ms-5000ms (зависит от размера)

### 2.3. Error Handling Flow

```
Error Detection
    ↓
Classification
    ├─ User Input Errors → Immediate feedback
    ├─ System Errors → Retry logic
    ├─ External API Errors → Fallback responses
    └─ Critical Errors → Admin notification
    ↓
Recovery Strategy
    ├─ Retry (max 3 attempts)
    ├─ Graceful degradation
    ├─ User-friendly error messages
    └─ Logging & monitoring
```

---

## 🔧 3. API и интеграция

### 3.1. Telegram Bot API интеграция

#### 3.1.1. Режимы работы

**Development - Polling режим:**
```python
# Для разработки и тестирования
async def start_polling(self):
    await self.application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
```

**Production - Webhook режим:**
```python
# Для продакшена
async def start_webhook(self):
    await self.application.run_webhook(
        listen="0.0.0.0",
        port=8443,
        url_path="telegram",
        webhook_url=self.config.webhook_url,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )
```

#### 3.1.2. Обработчики событий

**Command Handlers:**
```python
# Системные команды
CommandHandler("start", bot_command_handler.start)
CommandHandler("help", bot_command_handler.help)
CommandHandler("calculate", bot_command_handler.calculate)
CommandHandler("status", bot_command_handler.status)
CommandHandler("examples", bot_command_handler.examples)
CommandHandler("about", bot_command_handler.about)

# Административные команды
CommandHandler("admin_status", admin_handler.admin_status)  # Only admin_user_id
CommandHandler("broadcast", admin_handler.broadcast)      # Only admin_user_id
```

**Message Handlers:**
```python
# Текстовые сообщения (не команды)
MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    message_handler.handle_text
)

# Callback запросы (inline кнопки)
CallbackQueryHandler(
    callback_handler.handle_callback,
    pattern=r'^calc_'
)
```

### 3.2. ThermoOrchestrator интеграция

#### 3.2.1. Адаптерный паттерн

**ThermoAdapter:**
```python
class ThermoAdapter:
    def __init__(self, orchestrator: ThermoOrchestrator):
        self.orchestrator = orchestrator

    async def process_telegram_query(
        self,
        query: str,
        user_session: TelegramSessionLogger
    ) -> str:
        try:
            # Логирование запроса
            user_session.log_thermo_request(query)

            # Обработка через ThermoOrchestrator
            response = await self.orchestrator.process_query(query)

            # Логирование ответа
            user_session.log_thermo_response(len(response))

            return response

        except Exception as e:
            user_session.log_thermo_error(str(e))
            raise
```

#### 3.2.2. Data Flow Integration

**Request Processing:**
```python
async def handle_calculation_request(
    self,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_query = update.message.text

    with TelegramSessionLogger(
        user_id=update.effective_user.id,
        username=update.effective_user.username
    ) as session_logger:

        # Отправка статуса "calculating"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )

        # Выполнение расчёта через адаптер
        response = await self.thermo_adapter.process_telegram_query(
            user_query,
            session_logger
        )

        # Умная отправка ответа
        await self.smart_response_handler.send_response(
            update, context, response, user_query
        )
```

---

## 📁 4. Управление данными

### 4.1. Сессионное управление

#### 4.1.1. UserSession модель

```python
@dataclass
class UserSession:
    user_id: int
    username: Optional[str]
    chat_id: int
    start_time: float
    last_activity: float
    request_count: int = 0
    error_count: int = 0
    total_processing_time: float = 0.0

    @property
    def is_active(self) -> bool:
        return time.time() - self.last_activity < 3600  # 1 час

    @property
    def session_duration(self) -> float:
        return time.time() - self.start_time

    @property
    def average_processing_time(self) -> float:
        return self.total_processing_time / self.request_count if self.request_count > 0 else 0
```

#### 4.1.2. SessionManager

```python
class SessionManager:
    def __init__(self, max_sessions: int = 1000):
        self.max_sessions = max_sessions
        self.active_sessions: Dict[int, UserSession] = {}
        self.session_stats = defaultdict(int)

    def get_or_create_session(self, user_id: int, username: Optional[str] = None, chat_id: Optional[int] = None) -> UserSession:
        if user_id in self.active_sessions and self.active_sessions[user_id].is_active:
            session = self.active_sessions[user_id]
            session.last_activity = time.time()
            session.request_count += 1
        else:
            session = UserSession(
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                start_time=time.time(),
                last_activity=time.time()
            )
            self.active_sessions[user_id] = session

        self._cleanup_old_sessions()
        return session
```

### 4.2. Rate Limiting

#### 4.2.1. Token Bucket Algorithm

```python
class TokenBucketRateLimiter:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
        self.user_buckets = defaultdict(lambda: {'tokens': capacity, 'last_refill': time.time()})

    async def check_rate_limit(self, user_id: int) -> bool:
        bucket = self.user_buckets[user_id]
        now = time.time()

        # Refill tokens based on time elapsed
        time_passed = now - bucket['last_refill']
        bucket['tokens'] = min(self.capacity, bucket['tokens'] + time_passed * self.refill_rate)
        bucket['last_refill'] = now

        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            return True
        return False
```

#### 4.2.2. Global Rate Limiting

```python
class GlobalRateLimiter:
    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.request_timestamps = deque()
        self._lock = asyncio.Lock()

    async def check_global_limit(self) -> bool:
        async with self._lock:
            now = time.time()
            # Remove old requests (older than 1 minute)
            while self.request_timestamps and now - self.request_timestamps[0] > 60:
                self.request_timestamps.popleft()

            if len(self.request_timestamps) < self.requests_per_minute:
                self.request_timestamps.append(now)
                return True
            return False
```

---

## 🔄 5. Обработка сообщений

### 5.1. Message Pipeline

#### 5.1.1. Input Validation

```python
class QueryValidator:
    MAX_QUERY_LENGTH = 1000
    FORBIDDEN_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'http[s]?://',
        r'--',  # SQL injection
        r'/\*.*?\*/'  # SQL comments
    ]

    @staticmethod
    def validate_query(query: str) -> ValidationResult:
        # Length validation
        if len(query) > QueryValidator.MAX_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                error=f"Query too long (max {QueryValidator.MAX_QUERY_LENGTH} chars)"
            )

        # Security validation
        for pattern in QueryValidator.FORBIDDEN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    error="Query contains forbidden content"
                )

        # Chemical formula validation (basic)
        if not QueryValidator._has_chemical_content(query):
            return ValidationResult(
                is_valid=False,
                error="Query doesn't contain recognizable chemical content"
            )

        return ValidationResult(is_valid=True)
```

### 5.2. Response Processing

#### 5.2.1. Smart Response Strategy

```python
class SmartResponseHandler:
    def __init__(self, file_handler: TelegramFileHandler, message_threshold: int = 3000):
        self.file_handler = file_handler
        self.message_threshold = message_threshold

    async def send_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        response: str,
        query: str = ""
    ) -> bool:
        try:
            should_use_file = self._should_use_file(response)

            if should_use_file:
                return await self._send_as_file(update, context, response, query)
            else:
                return await self._send_as_messages(update, context, response)

        except Exception as e:
            logger.error(f"Error sending response: {e}")
            await self._send_error_message(update, context, str(e))
            return False

    def _should_use_file(self, response: str) -> bool:
        return (
            len(response) >= self.message_threshold or
            self._has_large_tables(response) or
            self._has_complex_formatting(response)
        )
```

---

## 🎯 6. Component Dependencies

### 6.1. Dependency Injection

```python
@dataclass
class TelegramBotDependencies:
    orchestrator: ThermoOrchestrator
    config: TelegramBotConfig
    session_manager: SessionManager
    rate_limiter: RateLimiter
    file_handler: TelegramFileHandler
    response_formatter: TelegramResponseFormatter
    smart_response_handler: SmartResponseHandler

class ThermoSystemTelegramBot:
    def __init__(self, deps: TelegramBotDependencies):
        self.deps = deps
        self.application = Application.builder().token(deps.config.bot_token).build()
        self._setup_handlers()
```

### 6.2. Configuration Management

```python
@dataclass
class TelegramBotConfig:
    # Telegram API
    bot_token: str
    bot_username: str
    webhook_url: Optional[str] = None
    mode: str = "polling"

    # Performance
    max_concurrent_users: int = 20
    request_timeout_seconds: int = 60
    message_max_length: int = 4000

    # Features
    enable_file_downloads: bool = True
    auto_file_threshold: int = 3000
    enable_analytics: bool = True

    # Security
    admin_user_id: Optional[int] = None
    log_errors_to_admin: bool = True

    @classmethod
    def from_env(cls) -> 'TelegramBotConfig':
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "ThermoCalcBot"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            mode=os.getenv("TELEGRAM_MODE", "polling"),
            max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "20")),
            enable_file_downloads=os.getenv("ENABLE_FILE_DOWNLOADS", "true").lower() == "true",
            auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
            admin_user_id=int(os.getenv("TELEGRAM_ADMIN_USER_ID", "0")) if os.getenv("TELEGRAM_ADMIN_USER_ID") else None
        )
```

---

## 📈 7. Performance Optimizations

### 7.1. Caching Strategy

```python
class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds

    async def get_cached_response(self, query_hash: str) -> Optional[str]:
        if query_hash in self.cache:
            cached_data = self.cache[query_hash]
            if time.time() - cached_data['timestamp'] < self.ttl:
                return cached_data['response']
            else:
                del self.cache[query_hash]
        return None

    async def cache_response(self, query_hash: str, response: str):
        self.cache[query_hash] = {
            'response': response,
            'timestamp': time.time()
        }
```

### 7.2. Connection Pooling

```python
class DatabaseConnectionPool:
    def __init__(self, db_path: str, max_connections: int = 10):
        self.db_path = db_path
        self.max_connections = max_connections
        self.pool = asyncio.Queue(maxsize=max_connections)
        self._pool_initialized = False

    async def initialize_pool(self):
        if not self._pool_initialized:
            for _ in range(self.max_connections):
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                await self.pool.put(conn)
            self._pool_initialized = True

    async def get_connection(self):
        return await self.pool.get()

    async def return_connection(self, conn):
        await self.pool.put(conn)
```

---

## 📋 8. Следующие шаги

После изучения архитектуры перейдите к документу **[04_file_handling_system.md](./04_file_handling_system.md)** для детального ознакомления с системой обработки файлов и умными ответами.

---

**Документ подготовлен для:** System Architects и Senior Python разработчиков
**Целевая аудитория:** Команда разработки ThermoSystem
**Сложность архитектуры:** Средняя-Высокая (async, concurrency, distributed systems)