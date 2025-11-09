"""
Обработчики сообщений для Telegram бота.

- MessageHandler: обработка текстовых сообщений и интеграция с ThermoSystem
"""

from .message_handler import MessageHandler

__all__ = [
    "MessageHandler",
]