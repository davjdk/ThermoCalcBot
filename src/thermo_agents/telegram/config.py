"""
File Handler Configuration - Конфигурация системы обработки файлов

Определяет параметры файловой системы, умных ответов и очистки.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os
from pathlib import Path
from dotenv import load_dotenv

@dataclass
class FileHandlerConfig:
    """Конфигурация системы обработки файлов"""

    # Directory configuration
    temp_file_dir: str = "temp/telegram_files"
    cleanup_hours: int = 24
    max_file_size_mb: int = 20  # Лимит Telegram Bot API

    # Smart response configuration
    auto_file_threshold: int = 3000  # символов
    max_table_rows: int = 20
    max_unicode_lines: int = 10

    # File naming
    max_filename_length: int = 50
    filename_timestamp_format: str = "%Y%m%d_%H%M%S"

    # Performance
    enable_file_compression: bool = False
    max_concurrent_file_operations: int = 5

    # Security
    sanitize_filenames: bool = True
    allowed_extensions: List[str] = None

    def __post_init__(self):
        """Валидация и пост-инициализация"""
        if self.allowed_extensions is None:
            self.allowed_extensions = ['.txt']

        # Убедимся, что temp_file_dir это Path
        if isinstance(self.temp_file_dir, str):
            self.temp_file_dir = Path(self.temp_file_dir)

    @classmethod
    def from_env(cls) -> 'FileHandlerConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(
            temp_file_dir=os.getenv("TEMP_FILE_DIR", "temp/telegram_files"),
            cleanup_hours=int(os.getenv("FILE_CLEANUP_HOURS", "24")),
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
            auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
            max_table_rows=int(os.getenv("MAX_TABLE_ROWS", "20")),
            max_unicode_lines=int(os.getenv("MAX_UNICODE_LINES", "10")),
            max_filename_length=int(os.getenv("MAX_FILENAME_LENGTH", "50")),
            enable_file_compression=os.getenv("ENABLE_FILE_COMPRESSION", "false").lower() == "true",
            max_concurrent_file_operations=int(os.getenv("MAX_CONCURRENT_FILE_OPERATIONS", "5")),
            sanitize_filenames=os.getenv("SANITIZE_FILENAMES", "true").lower() == "true"
        )

    def validate(self) -> List[str]:
        """Валидация конфигурации"""
        errors = []

        if self.cleanup_hours <= 0:
            errors.append("FILE_CLEANUP_HOURS must be positive")

        if self.max_file_size_mb <= 0 or self.max_file_size_mb > 50:
            errors.append("MAX_FILE_SIZE_MB must be between 1 and 50")

        if self.auto_file_threshold < 1000:
            errors.append("AUTO_FILE_THRESHOLD must be at least 1000 characters")

        if self.max_table_rows < 5:
            errors.append("MAX_TABLE_ROWS must be at least 5")

        if self.max_filename_length < 10:
            errors.append("MAX_FILENAME_LENGTH must be at least 10")

        if self.max_concurrent_file_operations < 1:
            errors.append("MAX_CONCURRENT_FILE_OPERATIONS must be at least 1")

        return errors

    def to_dict(self) -> dict:
        """Преобразование в словарь для логирования"""
        return {
            'temp_file_dir': str(self.temp_file_dir),
            'cleanup_hours': self.cleanup_hours,
            'max_file_size_mb': self.max_file_size_mb,
            'auto_file_threshold': self.auto_file_threshold,
            'max_table_rows': self.max_table_rows,
            'max_unicode_lines': self.max_unicode_lines,
            'max_filename_length': self.max_filename_length,
            'filename_timestamp_format': self.filename_timestamp_format,
            'enable_file_compression': self.enable_file_compression,
            'max_concurrent_file_operations': self.max_concurrent_file_operations,
            'sanitize_filenames': self.sanitize_filenames,
            'allowed_extensions': self.allowed_extensions
        }

    def ensure_temp_directory(self) -> Path:
        """Создание временной директории если она не существует"""
        self.temp_file_dir.mkdir(parents=True, exist_ok=True)
        return self.temp_file_dir


# Legacy compatibility classes
@dataclass
class BotLimits:
    """Класс с ограничениями и лимитами бота (legacy)."""
    max_concurrent_users: int = 20
    request_timeout_seconds: int = 60
    message_max_length: int = 4000
    rate_limit_requests_per_minute: int = 30
    max_file_size_mb: int = 20  # Лимит Telegram Bot API


@dataclass
class FileConfig:
    """Конфигурация файловой системы (legacy)."""
    enable_file_downloads: bool = True
    auto_file_threshold: int = 3000  # Символов
    file_cleanup_hours: int = 24
    temp_file_dir: Path = Path("temp/telegram_files")


@dataclass
class TelegramBotConfig:
    """Основная конфигурация Telegram бота."""

    # Telegram API
    bot_token: str
    bot_username: str = "ThermoCalcBot"
    webhook_url: Optional[str] = None
    mode: str = "polling"  # polling или webhook

    # ThermoSystem интеграция
    thermo_db_path: Path = Path("data/thermo_data.db")
    openrouter_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4o"

    # Ограничения и файлы
    limits: BotLimits = field(default_factory=BotLimits)
    file_config: FileConfig = field(default_factory=FileConfig)

    # Дополнительные настройки
    admin_user_id: Optional[int] = None
    log_bot_errors: bool = True

    @classmethod
    def from_env(cls) -> "TelegramBotConfig":
        """Создание конфигурации из переменных окружения."""
        # Явно загружаем .env файл из директории проекта
        # Ищем .env в текущей рабочей директории и в родительских директориях
        current_dir = Path.cwd()
        env_path = current_dir / ".env"

        # Если не нашли в текущей директории, ищем в родительских
        if not env_path.exists():
            # Идем вверх по дереву директорий в поисках .env
            search_dir = current_dir
            for _ in range(5):  # ищем до 5 уровней вверх
                search_dir = search_dir.parent
                test_path = search_dir / ".env"
                if test_path.exists():
                    env_path = test_path
                    break

        print(f"DEBUG: Загружаем .env из пути: {env_path}")
        print(f"DEBUG: Файл существует: {env_path.exists()}")
        result = load_dotenv(env_path)
        print(f"DEBUG: load_dotenv() результат: {result}")
        print(f"DEBUG: OPENROUTER_API_KEY после загрузки: {os.getenv('OPENROUTER_API_KEY', 'NOT_FOUND')[:20]}...")
        print(f"DEBUG: TELEGRAM_BOT_TOKEN после загрузки: {os.getenv('TELEGRAM_BOT_TOKEN', 'NOT_FOUND')[:20]}...")

        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "ThermoCalcBot"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            mode=os.getenv("TELEGRAM_MODE", "polling"),

            thermo_db_path=Path(os.getenv("DB_PATH", "data/thermo_data.db")),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            llm_model=os.getenv("LLM_DEFAULT_MODEL", "openai/gpt-4o"),

            limits=BotLimits(
                max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "20")),
                request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
                message_max_length=int(os.getenv("MESSAGE_MAX_LENGTH", "4000")),
                rate_limit_requests_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "30")),
                max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20"))
            ),

            file_config=FileConfig(
                enable_file_downloads=os.getenv("ENABLE_FILE_DOWNLOADS", "true").lower() == "true",
                auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
                file_cleanup_hours=int(os.getenv("FILE_CLEANUP_HOURS", "24")),
                temp_file_dir=Path(os.getenv("TEMP_FILE_DIR", "temp/telegram_files"))
            ),

            admin_user_id=int(os.getenv("TELEGRAM_ADMIN_USER_ID")) if os.getenv("TELEGRAM_ADMIN_USER_ID") else None,
            log_bot_errors=os.getenv("LOG_BOT_ERRORS", "true").lower() == "true"
        )

    def validate_config(self) -> list[str]:
        """Валидация конфигурации. Возвращает список ошибок."""
        errors = []

        # Проверка обязательных полей
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN обязателен")

        if not self.openrouter_api_key:
            errors.append("OPENROUTER_API_KEY обязателен")

        # Проверка файла базы данных
        if not self.thermo_db_path.exists():
            errors.append(f"База данных не найдена: {self.thermo_db_path}")

        # Проверка режима работы
        if self.mode not in ["polling", "webhook"]:
            errors.append("TELEGRAM_MODE должен быть 'polling' или 'webhook'")

        # Проверка webhook конфигурации
        if self.mode == "webhook" and not self.webhook_url:
            errors.append("TELEGRAM_WEBHOOK_URL обязателен для webhook режима")

        # Проверка лимитов
        if self.limits.max_concurrent_users < 1 or self.limits.max_concurrent_users > 1000:
            errors.append("MAX_CONCURRENT_USERS должен быть между 1 и 1000")

        if self.limits.request_timeout_seconds < 10 or self.limits.request_timeout_seconds > 300:
            errors.append("REQUEST_TIMEOUT_SECONDS должен быть между 10 и 300")

        # Проверка файловой конфигурации
        if self.file_config.auto_file_threshold < 1000 or self.file_config.auto_file_threshold > 10000:
            errors.append("AUTO_FILE_THRESHOLD должен быть между 1000 и 10000")

        return errors