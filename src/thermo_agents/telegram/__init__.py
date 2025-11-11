"""
Telegram Bot Integration for ThermoSystem

Модуль интеграции Telegram бота с ThermoSystem v2.2.
Обеспечивает умную обработку файлов и доставку результатов через Telegram API.
"""

from .file_handler import TelegramFileHandler
from .smart_response import SmartResponseHandler
from .config import FileHandlerConfig, TelegramBotConfig
from .metrics import FileSystemMetrics, MetricsCollector

# Legacy imports для обратной совместимости
from .bot import ThermoSystemTelegramBot
from .models import (
    UserSession, BotCommand, BotResponse, FileResponse,
    CommandStatus, MessageType, ProgressMessage
)
from .session_manager import SessionManager, RateLimiter
from .thermo_adapter import ThermoAdapter, ResponseFormatter, FileGenerator

__all__ = [
    # File Handling System (новые компоненты)
    "TelegramFileHandler",
    "SmartResponseHandler",
    "FileHandlerConfig",
    "FileSystemMetrics",
    "MetricsCollector",

    # Configuration
    "TelegramBotConfig",

    # Legacy components (для обратной совместимости)
    "ThermoSystemTelegramBot",
    "UserSession",
    "BotCommand",
    "BotResponse",
    "FileResponse",
    "CommandStatus",
    "MessageType",
    "ProgressMessage",
    "SessionManager",
    "RateLimiter",
    "ThermoAdapter",
    "ResponseFormatter",
    "FileGenerator",
]

__version__ = "1.1.0"