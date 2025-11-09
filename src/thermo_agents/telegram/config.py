"""
Конфигурация для Telegram бота ThermoSystem.

Основные классы:
- TelegramBotConfig: Основная конфигурация бота
- BotLimits: Ограничения и лимиты
- FileConfig: Конфигурация файловой системы
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BotLimits:
    """Класс с ограничениями и лимитами бота."""
    max_concurrent_users: int = 20
    request_timeout_seconds: int = 60
    message_max_length: int = 4000
    rate_limit_requests_per_minute: int = 30
    max_file_size_mb: int = 20  # Лимит Telegram Bot API


@dataclass
class FileConfig:
    """Конфигурация файловой системы."""
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