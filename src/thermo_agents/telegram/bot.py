"""
Основной класс Telegram бота ThermoSystem.

Основные классы:
- ThermoSystemTelegramBot: Главный класс бота
- BotErrorHandler: Обработчик ошибок бота
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, ContextTypes, Defaults, filters
from telegram.ext import CommandHandler as TelegramCommandHandler
from telegram.ext import MessageHandler as TelegramMessageHandler

from .config import TelegramBotConfig
from .handlers import CommandHandler as BotCommandHandler
from .handlers import MessageHandler as BotMessageHandler
from .models import BotResponse, FileResponse, MessageType
from .session_manager import SessionManager
from .thermo_adapter import ThermoAdapter

logger = logging.getLogger(__name__)


class BotErrorHandler:
    """Обработчик ошибок бота."""

    @staticmethod
    async def error_handler(
        update: Optional[Update], context: ContextTypes.DEFAULT_TYPE
    ):
        """Глобальный обработчик ошибок."""
        logger.error(f"Exception while handling update {update}: {context.error}")

        if update and update.effective_user:
            user_id = update.effective_user.id

            # Отправляем сообщение об ошибке пользователю
            error_message = (
                "😔 *Произошла системная ошибка*\n\n"
                "Попробуйте повторить запрос позже или используйте /help"
            )

            try:
                await update.message.reply_text(error_message, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send error message to user {user_id}: {e}")


class ThermoSystemTelegramBot:
    """Основной класс Telegram бота ThermoSystem."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.application: Optional[Application] = None
        self.session_manager: Optional[SessionManager] = None
        self.thermo_adapter: Optional[ThermoAdapter] = None
        self.command_handler: Optional[BotCommandHandler] = None
        self.message_handler: Optional[BotMessageHandler] = None

        self._running = False
        self._stop_event = asyncio.Event()

    async def initialize(self):
        """Инициализация бота."""
        try:
            logger.info("Initializing ThermoSystem Telegram Bot...")

            # Создаем менеджер сессий
            self.session_manager = SessionManager(
                max_concurrent_users=self.config.limits.max_concurrent_users
            )
            await self.session_manager.start()

            # Создаем адаптер для ThermoSystem
            self.thermo_adapter = ThermoAdapter(self.config)
            await self.thermo_adapter.initialize()

            # Создаем обработчики
            self.command_handler = BotCommandHandler(
                self.config, self.session_manager, self.thermo_adapter
            )
            self.message_handler = BotMessageHandler(
                self.config, self.session_manager, self.thermo_adapter
            )

            # Создаем приложение Telegram
            from telegram import LinkPreviewOptions
            from telegram.request import HTTPXRequest

            # Создаем кастомный request с увеличенными таймаутами
            request = HTTPXRequest(
                connection_pool_size=8,
                connect_timeout=30.0,
                read_timeout=30.0,
                write_timeout=30.0,
                pool_timeout=30.0,
            )

            self.application = (
                Application.builder()
                .token(self.config.bot_token)
                .request(request)
                .defaults(
                    Defaults(
                        parse_mode="Markdown",
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
                )
                .build()
            )

            # Регистрируем обработчики команд
            self._register_handlers()

            # Регистрируем обработчик ошибок
            self.application.add_error_handler(BotErrorHandler.error_handler)

            logger.info("Bot initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise

    def _register_handlers(self):
        """Регистрация обработчиков."""
        if not self.application:
            raise RuntimeError("Application not initialized")

        # Обработчики команд
        self.application.add_handler(
            TelegramCommandHandler("start", self._wrap_command_handler("start"))
        )
        self.application.add_handler(
            TelegramCommandHandler("help", self._wrap_command_handler("help"))
        )
        self.application.add_handler(
            TelegramCommandHandler("calculate", self._wrap_command_handler("calculate"))
        )
        self.application.add_handler(
            TelegramCommandHandler("status", self._wrap_command_handler("status"))
        )
        self.application.add_handler(
            TelegramCommandHandler("examples", self._wrap_command_handler("examples"))
        )
        self.application.add_handler(
            TelegramCommandHandler("about", self._wrap_command_handler("about"))
        )

        # Обработчик текстовых сообщений (не команд)
        self.application.add_handler(
            TelegramMessageHandler(
                filters.TEXT & ~filters.COMMAND, self._wrap_message_handler()
            )
        )

        # Обработчик неизвестных команд
        self.application.add_handler(
            TelegramMessageHandler(
                filters.COMMAND, self._wrap_unknown_command_handler()
            )
        )

    def _wrap_command_handler(self, command_name: str):
        """Обертка для обработчиков команд."""

        async def wrapped_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                if not self.command_handler:
                    return

                # Получаем соответствующий метод
                method_name = f"handle_{command_name}"
                method = getattr(self.command_handler, method_name, None)

                if method:
                    response = await method(update, context)
                    await self._send_response(update, response)
                else:
                    logger.error(f"Command handler method {method_name} not found")

            except Exception as e:
                logger.error(f"Error in command handler {command_name}: {e}")
                await self._send_error_response(update, str(e))

        return wrapped_handler

    def _wrap_message_handler(self):
        """Обертка для обработчика текстовых сообщений."""

        async def wrapped_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                if not self.message_handler:
                    return

                response = await self.message_handler.handle_text_message(
                    update, context
                )
                if response:
                    await self._send_response(update, response)

            except Exception as e:
                logger.error(f"Error in message handler: {e}")
                await self._send_error_response(update, str(e))

        return wrapped_handler

    def _wrap_unknown_command_handler(self):
        """Обертка для обработчика неизвестных команд."""

        async def wrapped_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            try:
                if not self.message_handler:
                    return

                response = await self.message_handler.handle_unknown_command(
                    update, context
                )
                await self._send_response(update, response)

            except Exception as e:
                logger.error(f"Error in unknown command handler: {e}")
                await self._send_error_response(update, str(e))

        return wrapped_handler

    async def _send_response(self, update: Update, response):
        """Отправить ответ пользователю."""
        try:
            if not update.message:
                return

            if isinstance(response, FileResponse):
                # Отправляем файл
                await update.message.reply_document(
                    document=response.file_path.open("rb"),
                    caption=response.caption,
                    parse_mode="Markdown",
                )

                # Добавляем файл в сессию пользователя для последующей очистки
                if response.user_id:
                    session = self.session_manager.get_session(response.user_id)
                    if session:
                        session.add_temp_file(response.file_path)

            elif isinstance(response, BotResponse):
                # Отправляем текстовое сообщение
                await update.message.reply_text(
                    text=response.text,
                    parse_mode=response.parse_mode if response.use_markdown else None,
                    disable_web_page_preview=True,
                )

            else:
                logger.error(f"Unknown response type: {type(response)}")

        except Exception as e:
            logger.error(f"Error sending response: {e}")
            # Пробуем отправить простое сообщение об ошибке
            try:
                await update.message.reply_text(
                    "Ошибка при отправке ответа. Попробуйте еще раз."
                )
            except:
                pass  # Если и это не удалось, просто логируем

    async def _send_error_response(self, update: Update, error_message: str):
        """Отправить сообщение об ошибке."""
        try:
            if update.message:
                await update.message.reply_text(
                    "😔 *Произошла ошибка*\n\n"
                    "Попробуйте повторить запрос или используйте /help",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.error(f"Failed to send error response: {e}")

    async def start(self):
        """Запуск бота."""
        if self._running:
            logger.warning("Bot is already running")
            return

        try:
            await self.initialize()

            logger.info(f"Starting bot in {self.config.mode} mode...")
            self._running = True

            if self.config.mode == "polling":
                # Запуск в режиме polling с async API
                await self.application.initialize()
                await self.application.start()
                await self.application.updater.start_polling(
                    drop_pending_updates=True, allowed_updates=Update.ALL_TYPES
                )
                logger.info("✅ Bot started successfully! Listening for updates...")

                # Ожидание события остановки вместо бесконечного цикла
                await self._stop_event.wait()
                logger.info("Stop event received, shutting down...")

            elif self.config.mode == "webhook":
                # Запуск в режиме webhook
                await self.application.run_webhook(
                    listen="0.0.0.0",
                    port=8443,
                    url_path="telegram",
                    webhook_url=self.config.webhook_url,
                    drop_pending_updates=True,
                )
            else:
                raise ValueError(f"Unknown mode: {self.config.mode}")

        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            self._running = False
            raise

    async def stop(self):
        """Остановка бота."""
        if not self._running:
            return

        logger.info("Stopping bot...")
        self._running = False

        # Устанавливаем событие остановки
        self._stop_event.set()

        try:
            # Остановка polling/updater
            if self.application and self.application.updater:
                await self.application.updater.stop()

            # Остановка приложения
            if self.application:
                await self.application.stop()
                await self.application.shutdown()

            # Остановка компонентов
            if self.session_manager:
                await self.session_manager.stop()

            if self.thermo_adapter:
                await self.thermo_adapter.shutdown()

            logger.info("Bot stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

    def get_bot_info(self) -> dict:
        """Получить информацию о боте."""
        return {
            "bot_username": self.config.bot_username,
            "mode": self.config.mode,
            "max_concurrent_users": self.config.limits.max_concurrent_users,
            "rate_limit_per_minute": self.config.limits.rate_limit_requests_per_minute,
            "running": self._running,
            "file_config": {
                "enabled": self.config.file_config.enable_file_downloads,
                "threshold": self.config.file_config.auto_file_threshold,
                "cleanup_hours": self.config.file_config.file_cleanup_hours,
            },
        }
