"""
Основной класс Telegram бота для ThermoSystem.

Интеграция всех компонентов в единое приложение.
"""

import asyncio
import signal
import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from .config import TelegramBotConfig, BotStatus
from .commands.command_handler import CommandHandler
from .handlers.message_handler import MessageHandler
from .utils.session_manager import SessionManager
from .utils.rate_limiter import RateLimiter
from .utils.thermo_integration import ThermoIntegration


class ThermoSystemTelegramBot:
    """Основной класс Telegram бота."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.status = BotStatus()
        self.application: Optional[Application] = None

        # Инициализация компонентов
        self.session_manager = SessionManager(config)
        self.rate_limiter = RateLimiter(config)
        self.thermo_integration = ThermoIntegration(config)

        # Обработчики
        self.command_handler = CommandHandler(config, self.status)
        self.message_handler = MessageHandler(config, self.status, self.thermo_integration)

        # Настройка логирования
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Настройка логирования."""
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=getattr(logging, self.config.log_level.upper())
        )

        self.logger = logging.getLogger(__name__)

    async def start(self) -> None:
        """Запуск бота."""
        try:
            self.logger.info("Запуск ThermoSystem Telegram Bot...")

            # Валидация конфигурации
            config_errors = self.config.validate_config()
            if config_errors:
                self.logger.error(f"Ошибки конфигурации: {config_errors}")
                raise ValueError(f"Конфигурация неверна: {config_errors}")

            # Проверка здоровья компонентов
            health = await self.thermo_integration.health_check()
            if health["status"] != "healthy":
                self.logger.warning(f"Некоторые компоненты нездоровы: {health}")

            # Создание приложения
            self.application = Application.builder().token(self.config.bot_token).build()

            # Регистрация обработчиков
            self._register_handlers()

            # Настройка graceful shutdown
            self._setup_signal_handlers()

            # Запуск фоновой очистки файлов
            asyncio.create_task(self._periodic_cleanup())

            # Обновление статуса
            self.status.is_running = True
            self.status.start_time = time.time()

            self.logger.info("Бот успешно запущен!")

            # Запуск polling
            await self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                timeout=self.config.bot_timeout_seconds
            )

        except Exception as e:
            self.logger.error(f"Ошибка запуска бота: {e}")
            self.status.is_running = False
            raise

    async def stop(self) -> None:
        """Остановка бота."""
        try:
            self.logger.info("Остановка бота...")

            # Обновление статуса
            self.status.is_running = False

            # Остановка приложения
            if self.application:
                await self.application.stop()
                await self.application.shutdown()

            # Очистка компонентов
            await self.session_manager.shutdown()
            await self.rate_limiter.cleanup()

            # Очистка временных файлов
            await self._cleanup_temp_files()

            self.logger.info("Бот успешно остановлен.")

        except Exception as e:
            self.logger.error(f"Ошибка остановки бота: {e}")

    def _register_handlers(self) -> None:
        """Регистрация обработчиков команд и сообщений."""
        if not self.application:
            raise ValueError("Application не инициализирован")

        # Команды
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("status", self._handle_status))
        self.application.add_handler(CommandHandler("examples", self._handle_examples))
        self.application.add_handler(CommandHandler("about", self._handle_about))

        # Текстовые сообщения
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        # Неизвестные команды
        self.application.add_handler(MessageHandler(filters.COMMAND, self._handle_unknown))

        # Обработка ошибок
        self.application.add_error_handler(self._handle_error)

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /start."""
        try:
            # Создание сессии
            user_id = update.effective_user.id
            await self.session_manager.start_session(
                user_id,
                update.effective_user.username,
                update.effective_user.first_name
            )

            # Обработка команды
            await self.command_handler.handle_start(update, context)

        except Exception as e:
            self.logger.error(f"Ошибка обработки /start: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке команды")

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /help."""
        try:
            await self.command_handler.handle_help(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка обработки /help: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке команды")

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /status."""
        try:
            await self.command_handler.handle_status(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка обработки /status: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке команды")

    async def _handle_examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /examples."""
        try:
            await self.command_handler.handle_examples(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка обработки /examples: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке команды")

    async def _handle_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /about."""
        try:
            await self.command_handler.handle_about(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка обработки /about: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке команды")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка текстовых сообщений."""
        try:
            user_id = update.effective_user.id

            # Проверка rate limiting
            can_proceed, rate_limit_message = await self.rate_limiter.check_rate_limit(user_id)
            if not can_proceed:
                await update.message.reply_text(rate_limit_message)
                return

            # Проверка сессии
            if not self.session_manager.is_user_active(user_id):
                can_start = await self.session_manager.start_session(
                    user_id,
                    update.effective_user.username,
                    update.effective_user.first_name
                )
                if not can_start:
                    await update.message.reply_text(
                        "🚫 Система перегружена. Пожалуйста, попробуйте позже."
                    )
                    return

            # Обновление активности
            await self.session_manager.update_activity(user_id)

            # Обработка сообщения
            await self.message_handler.handle_message(update, context)

        except Exception as e:
            self.logger.error(f"Ошибка обработки сообщения: {e}")
            await self._send_error_message(update, "Произошла ошибка при обработке сообщения")

    async def _handle_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка неизвестных команд."""
        try:
            await self.command_handler.handle_unknown(update, context)
        except Exception as e:
            self.logger.error(f"Ошибка обработки неизвестной команды: {e}")

    async def _handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка ошибок приложения."""
        self.logger.error(f"Exception while handling an update: {context.error}")

        # Обновление статуса
        self.status.last_error = str(context.error)
        self.status.failed_requests += 1

        # Отправка сообщения об ошибке если возможно
        try:
            if update and hasattr(update, 'message') and update.message:
                await self._send_error_message(
                    update,
                    "Произошла внутренняя ошибка. Пожалуйста, попробуйте позже."
                )
        except Exception:
            pass  # Игнорируем ошибки при отправке сообщения об ошибке

    async def _send_error_message(self, update: Update, message: str) -> None:
        """Отправка сообщения об ошибке."""
        try:
            if update.message:
                await update.message.reply_text(f"❌ {message}")
        except Exception as e:
            self.logger.error(f"Ошибка отправки сообщения об ошибке: {e}")

    async def _periodic_cleanup(self) -> None:
        """Периодическая очистка временных файлов."""
        while self.status.is_running:
            try:
                # Ожидание 1 часа
                await asyncio.sleep(3600)

                if not self.status.is_running:
                    break

                # Очистка файлов
                from .formatters.file_handler import FileHandler
                file_handler = FileHandler(self.config)
                cleaned_count = await file_handler.cleanup_old_files()

                if cleaned_count > 0:
                    self.logger.info(f"Очищено временных файлов: {cleaned_count}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Ошибка периодической очистки: {e}")

    async def _cleanup_temp_files(self) -> None:
        """Очистка временных файлов при остановке."""
        try:
            from .formatters.file_handler import FileHandler
            file_handler = FileHandler(self.config)
            await file_handler.cleanup_old_files()
        except Exception as e:
            self.logger.error(f"Ошибка очистки временных файлов: {e}")

    def _setup_signal_handlers(self) -> None:
        """Настройка обработчиков сигналов для graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Получен сигнал {signum}, начинаю graceful shutdown...")
            asyncio.create_task(self.stop())

        # Регистрация обработчиков
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def get_bot_statistics(self) -> dict:
        """Получение статистики бота."""
        try:
            return {
                "status": self.status.dict(),
                "sessions": self.session_manager.get_user_statistics(),
                "rate_limits": self.rate_limiter.get_global_rate_info(),
                "health": await self.thermo_integration.health_check()
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {e}")
            return {"error": str(e)}