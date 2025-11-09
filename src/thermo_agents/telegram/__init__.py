"""
Telegram bot integration for ThermoSystem.

Основные компоненты:
- ThermoSystemTelegramBot: Главный класс бота
- TelegramBotConfig: Конфигурация бота
- SessionManager: Управление сессиями пользователей
- ThermoAdapter: Адаптер для интеграции с ThermoSystem
"""

from .bot import ThermoSystemTelegramBot
from .config import TelegramBotConfig, BotLimits, FileConfig
from .models import (
    UserSession, BotCommand, BotResponse, FileResponse,
    CommandStatus, MessageType, ProgressMessage
)
from .session_manager import SessionManager, RateLimiter
from .thermo_adapter import ThermoAdapter, ResponseFormatter, FileGenerator

__all__ = [
    # Основные классы
    "ThermoSystemTelegramBot",
    "TelegramBotConfig",

    # Конфигурация
    "BotLimits",
    "FileConfig",

    # Модели
    "UserSession",
    "BotCommand",
    "BotResponse",
    "FileResponse",
    "CommandStatus",
    "MessageType",
    "ProgressMessage",

    # Управление
    "SessionManager",
    "RateLimiter",

    # Интеграция
    "ThermoAdapter",
    "ResponseFormatter",
    "FileGenerator",
]