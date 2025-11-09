"""
Конфигурация Telegram бота ThermoSystem

Модуль содержит централизованную конфигурацию для всех компонентов бота,
включая параметры Telegram API, настройки производительности, обработки файлов,
администрирования и функциональные флаги.
"""

import os
from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel, Field


@dataclass
class TelegramBotConfig:
    """Конфигурация Telegram бота"""

    # Telegram API
    bot_token: str
    bot_username: str
    webhook_url: Optional[str] = None
    mode: str = "polling"  # polling или webhook

    # Performance limits
    max_concurrent_users: int = 20
    request_timeout_seconds: int = 60
    message_max_length: int = 4000
    rate_limit_per_minute: int = 30

    # File handling
    enable_file_downloads: bool = True
    auto_file_threshold: int = 3000
    file_cleanup_hours: int = 24
    max_file_size_mb: int = 20
    temp_file_dir: str = "temp/telegram_files"

    # Admin settings
    admin_user_id: Optional[int] = None
    log_errors_to_admin: bool = True

    # Feature flags
    enable_user_auth: bool = False
    enable_analytics: bool = True
    enable_progress_indicators: bool = True

    # Logging
    log_level: str = "INFO"
    log_requests: bool = True
    log_responses: bool = True

    # Database
    db_path: str = "data/thermo_data.db"
    static_data_dir: str = "data/static_compounds"

    @classmethod
    def from_env(cls) -> 'TelegramBotConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            bot_username=os.getenv("TELEGRAM_BOT_USERNAME", "ThermoCalcBot"),
            webhook_url=os.getenv("TELEGRAM_WEBHOOK_URL"),
            mode=os.getenv("TELEGRAM_MODE", "polling"),

            max_concurrent_users=int(os.getenv("MAX_CONCURRENT_USERS", "20")),
            request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
            message_max_length=int(os.getenv("MESSAGE_MAX_LENGTH", "4000")),
            rate_limit_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "30")),

            enable_file_downloads=os.getenv("ENABLE_FILE_DOWNLOADS", "true").lower() == "true",
            auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
            file_cleanup_hours=int(os.getenv("FILE_CLEANUP_HOURS", "24")),
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
            temp_file_dir=os.getenv("TEMP_FILE_DIR", "temp/telegram_files"),

            admin_user_id=int(os.getenv("TELEGRAM_ADMIN_USER_ID", "0")) if os.getenv("TELEGRAM_ADMIN_USER_ID") else None,
            log_errors_to_admin=os.getenv("LOG_BOT_ERRORS", "true").lower() == "true",

            enable_user_auth=os.getenv("ENABLE_USER_AUTH", "false").lower() == "true",
            enable_analytics=os.getenv("ENABLE_ANALYTICS", "true").lower() == "true",
            enable_progress_indicators=os.getenv("ENABLE_PROGRESS_INDICATORS", "true").lower() == "true",

            log_level=os.getenv("LOG_LEVEL", "INFO"),
            log_requests=os.getenv("LOG_REQUESTS", "true").lower() == "true",
            log_responses=os.getenv("LOG_RESPONSES", "true").lower() == "true",

            db_path=os.getenv("DB_PATH", "data/thermo_data.db"),
            static_data_dir=os.getenv("STATIC_DATA_DIR", "data/static_compounds")
        )

    def validate(self) -> List[str]:
        """Валидация конфигурации"""
        errors = []

        # Обязательные поля
        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN is required")

        if not self.bot_username:
            errors.append("TELEGRAM_BOT_USERNAME is required")

        # Валидация режима работы
        if self.mode not in ["polling", "webhook"]:
            errors.append("TELEGRAM_MODE must be 'polling' or 'webhook'")

        # Валидация webhook
        if self.mode == "webhook" and not self.webhook_url:
            errors.append("TELEGRAM_WEBHOOK_URL is required for webhook mode")

        # Валидация лимитов
        if self.max_concurrent_users <= 0:
            errors.append("MAX_CONCURRENT_USERS must be positive")

        if self.request_timeout_seconds <= 0:
            errors.append("REQUEST_TIMEOUT_SECONDS must be positive")

        if self.message_max_length <= 0:
            errors.append("MESSAGE_MAX_LENGTH must be positive")

        # Валидация файлов
        if self.auto_file_threshold <= 0:
            errors.append("AUTO_FILE_THRESHOLD must be positive")

        if self.max_file_size_mb <= 0:
            errors.append("MAX_FILE_SIZE_MB must be positive")

        # Проверка путей
        db_file = Path(self.db_path)
        if not db_file.exists():
            # Создаем предупреждение, а не ошибку, так как база может быть создана позже
            print(f"⚠️ Warning: Database file not found: {self.db_path}")

        return errors

    def is_production(self) -> bool:
        """Проверка production окружения"""
        return (
            self.mode == "webhook" and
            self.log_level == "INFO" and
            self.max_concurrent_users >= 50
        )

    def is_development(self) -> bool:
        """Проверка development окружения"""
        return (
            self.mode == "polling" and
            self.log_level in ["DEBUG", "INFO"]
        )

    def create_directories(self) -> None:
        """Создание необходимых директорий"""
        directories = [
            self.temp_file_dir,
            "logs/telegram_sessions",
            "logs/telegram_errors",
            Path(self.db_path).parent,
            Path(self.static_data_dir).parent,
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def get_log_level_int(self) -> int:
        """Преобразование строкового уровня логирования в числовой для logging"""
        level_mapping = {
            "DEBUG": 10,
            "INFO": 20,
            "WARNING": 30,
            "ERROR": 40,
            "CRITICAL": 50
        }
        return level_mapping.get(self.log_level.upper(), 20)

    def __str__(self) -> str:
        """Строковое представление конфигурации (без токена!)"""
        return (
            f"TelegramBotConfig(\n"
            f"  bot_username={self.bot_username},\n"
            f"  mode={self.mode},\n"
            f"  webhook_url={self.webhook_url},\n"
            f"  max_concurrent_users={self.max_concurrent_users},\n"
            f"  request_timeout_seconds={self.request_timeout_seconds},\n"
            f"  message_max_length={self.message_max_length},\n"
            f"  rate_limit_per_minute={self.rate_limit_per_minute},\n"
            f"  enable_file_downloads={self.enable_file_downloads},\n"
            f"  auto_file_threshold={self.auto_file_threshold},\n"
            f"  max_file_size_mb={self.max_file_size_mb},\n"
            f"  log_level={self.log_level},\n"
            f"  admin_user_id={self.admin_user_id},\n"
            f"  enable_user_auth={self.enable_user_auth},\n"
            f"  enable_analytics={self.enable_analytics},\n"
            f"  db_path={self.db_path}\n"
            f")"
        )


class BotStatus(BaseModel):
    """Статус бота для мониторинга."""

    is_running: bool = False
    start_time: Optional[str] = None
    active_users: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time_ms: float = 0.0
    last_error: Optional[str] = None
    uptime_seconds: float = 0.0