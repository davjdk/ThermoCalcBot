"""
Конфигурация Telegram бота для ThermoSystem.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class TelegramBotConfig(BaseModel):
    """Конфигурация Telegram бота."""

    # Basic bot configuration
    bot_token: str = Field(..., description="Telegram Bot API token")
    bot_username: str = Field("@ThermoCalcBot", description="Username бота")

    # ThermoSystem integration
    thermo_db_path: Path = Field("data/thermo_data.db", description="Путь к БД ThermoSystem")
    thermo_static_data_dir: Path = Field("data/static_compounds", description="Директория с YAML кэшем")

    # LLM configuration
    llm_api_key: str = Field(..., description="API ключ для LLM")
    llm_base_url: str = Field("https://openrouter.ai/api/v1", description="URL LLM API")
    llm_model: str = Field("openai/gpt-4o", description="Модель LLM")

    # Performance settings
    max_concurrent_users: int = Field(20, description="Максимум одновременных пользователей")
    request_timeout_seconds: int = Field(90, description="Таймаут запросов к LLM")
    bot_timeout_seconds: int = Field(30, description="Таймаут для Telegram Bot API")

    # File handling
    temp_file_dir: Path = Field("temp/telegram_files", description="Директория для временных файлов")
    max_file_size_mb: int = Field(20, description="Максимальный размер файла (MB)")
    file_cleanup_hours: int = Field(24, description="Часы до очистки временных файлов")

    # Message formatting
    max_message_length: int = Field(4096, description="Максимальная длина сообщения")
    response_format_threshold: int = Field(3000, description="Порог для отправки файла вместо сообщения")

    # Logging and monitoring
    log_level: str = Field("INFO", description="Уровень логирования")
    enable_session_logging: bool = Field(True, description="Включить логирование сессий")
    session_log_dir: Path = Field("logs/telegram_sessions", description="Директория для логов сессий")

    # Rate limiting
    rate_limit_messages_per_minute: int = Field(30, description="Лимит сообщений в минуту")
    rate_limit_burst: int = Field(5, description="Всплеск сообщений")

    @classmethod
    def from_env(cls) -> "TelegramBotConfig":
        """Создание конфигурации из переменных окружения."""
        return cls(
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            thermo_db_path=Path(os.getenv("DB_PATH", "data/thermo_data.db")),
            thermo_static_data_dir=Path(os.getenv("STATIC_CACHE_DIR", "data/static_compounds")),
            llm_api_key=os.getenv("OPENROUTER_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            llm_model=os.getenv("LLM_DEFAULT_MODEL", "openai/gpt-4o"),
            temp_file_dir=Path(os.getenv("TEMP_FILE_DIR", "temp/telegram_files")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            session_log_dir=Path(os.getenv("TELEGRAM_SESSION_LOG_DIR", "logs/telegram_sessions")),
        )

    def validate_config(self) -> list[str]:
        """Проверка конфигурации и возврат ошибок."""
        errors = []

        if not self.bot_token:
            errors.append("TELEGRAM_BOT_TOKEN не указан")

        if not self.llm_api_key:
            errors.append("OPENROUTER_API_KEY не указан")

        if not self.thermo_db_path.exists():
            errors.append(f"База данных не найдена: {self.thermo_db_path}")

        return errors


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