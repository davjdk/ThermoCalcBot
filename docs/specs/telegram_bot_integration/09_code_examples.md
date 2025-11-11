# Стадия 9: Примеры реализации

**Статус:** Ready for implementation
**Версия:** 1.0
**Дата:** 9 ноября 2025

---

## 📋 Обзор

Этот документ содержит полные примеры кода для всех основных компонентов Telegram бота ThermoSystem. Примеры готовы к использованию и следуют best practices для production кода.

## 🤖 1. Основной класс бота

### 1.1. ThermoSystemTelegramBot

```python
# src/thermo_agents/telegram_bot/bot.py
import asyncio
import logging
import signal
from typing import Optional
from dataclasses import dataclass

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler
)
from telegram.ext import ContextTypes
from telegram import ParseMode, ChatAction

from src.thermo_agents.orchestrator import create_orchestrator
from src.thermo_agents.telegram_bot.handlers import BotCommandHandlers, TelegramMessageHandler
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from src.thermo_agents.telegram_bot.managers.session_manager import SessionManager
from src.thermo_agents.telegram_bot.managers.smart_response import SmartResponseHandler
from src.thermo_agents.telegram_bot.formatters.telegram_formatter import TelegramResponseFormatter

logger = logging.getLogger(__name__)

class ThermoSystemTelegramBot:
    """
    Основной класс Telegram бота для интеграции с ThermoSystem

    Features:
    - Асинхронная обработка запросов
    - Polling и Webhook режимы
    - Graceful shutdown
    - Health checks
    - Monitoring integration
    """

    def __init__(self, config: TelegramBotConfig):
        """Инициализация бота с конфигурацией"""
        self.config = config
        self.orchestrator = create_orchestrator()
        self.session_manager = SessionManager(max_sessions=config.max_concurrent_users)

        # Инициализация Telegram приложения
        self.application = Application.builder().token(config.bot_token).build()

        # Инициализация компонентов
        self._initialize_components()

        # Настройка обработчиков
        self._setup_handlers()

        # Настройка graceful shutdown
        self._setup_graceful_shutdown()

        logger.info(f"ThermoSystem Telegram Bot initialized (mode: {config.mode})")

    def _initialize_components(self):
        """Инициализация компонентов бота"""
        # Форматер ответов
        self.response_formatter = TelegramResponseFormatter()

        # Smart response handler
        self.smart_response = SmartResponseHandler(
            message_threshold=self.config.auto_file_threshold,
            enable_file_downloads=self.config.enable_file_downloads
        )

        # Обработчики команд и сообщений
        self.command_handlers = BotCommandHandlers(
            self.orchestrator,
            self.session_manager,
            self.config
        )

        self.message_handler = TelegramMessageHandler(
            self.orchestrator,
            self.session_manager,
            self.response_formatter,
            self.smart_response
        )

    def _setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        # Команды
        self.application.add_handler(CommandHandler("start", self.command_handlers.start))
        self.application.add_handler(CommandHandler("help", self.command_handlers.help))
        self.application.add_handler(CommandHandler("calculate", self.command_handlers.calculate))
        self.application.add_handler(CommandHandler("status", self.command_handlers.status))
        self.application.add_handler(CommandHandler("examples", self.command_handlers.examples))
        self.application.add_handler(CommandHandler("about", self.command_handlers.about))

        # Текстовые сообщения (не команды)
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.message_handler.handle_text)
        )

        # Callback queries для inline кнопок
        self.application.add_handler(CallbackQueryHandler(self._handle_callback_query))

        # Error handler
        self.application.add_error_handler(self._handle_error)

    def _setup_graceful_shutdown(self):
        """Настройка graceful shutdown"""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.shutdown())
            )

    async def start(self):
        """Запуск бота"""
        try:
            logger.info(f"Starting ThermoSystem Telegram Bot in {self.config.mode} mode...")

            if self.config.mode == "polling":
                await self.application.run_polling()
            elif self.config.mode == "webhook":
                await self.application.run_webhook(
                    listen="0.0.0.0",
                    port=8443,
                    url_path="telegram",
                    webhook_url=self.config.webhook_url
                )
            else:
                raise ValueError(f"Unknown mode: {self.config.mode}")

        except Exception as e:
            logger.error(f"Bot startup failed: {e}")
            await self.shutdown()
            raise

    async def shutdown(self):
        """Graceful shutdown бота"""
        logger.info("Shutting down ThermoSystem Telegram Bot...")

        try:
            # Закрытие активных сессий
            await self.session_manager.close_all_sessions()

            # Остановка приложения
            await self.application.stop()
            await self.application.shutdown()

            logger.info("Bot shutdown completed successfully")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def health_check(self) -> dict:
        """Health check для мониторинга"""
        from src.thermo_agents.search.database_connector import DatabaseConnector

        health_status = {
            "status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "components": {}
        }

        # Проверка базы данных
        db_healthy = False
        try:
            db_connector = DatabaseConnector(self.config.db_path)
            db_connector.connect()
            db_healthy = True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")

        health_status["components"]["database"] = {
            "status": "healthy" if db_healthy else "unhealthy"
        }

        # Проверка LLM API
        llm_healthy = False
        try:
            test_response = await self.orchestrator.thermodynamic_agent.test_connection()
            llm_healthy = test_response is not None
        except Exception as e:
            logger.error(f"LLM API health check failed: {e}")

        health_status["components"]["llm_api"] = {
            "status": "healthy" if llm_healthy else "unhealthy"
        }

        # Общий статус
        unhealthy_components = [
            name for name, comp in health_status["components"].items()
            if comp["status"] != "healthy"
        ]

        if unhealthy_components:
            health_status["status"] = "degraded" if len(unhealthy_components) == 1 else "unhealthy"

        # Дополнительная информация
        health_status.update({
            "active_sessions": len(self.session_manager.active_sessions),
            "bot_mode": self.config.mode,
            "uptime": self._get_uptime_seconds()
        })

        return health_status

    def _get_uptime_seconds(self) -> float:
        """Получение uptime бота"""
        import time
        return time.time() - getattr(self, '_start_time', time.time())

    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback запросов от inline кнопок"""
        query = update.callback_query
        await query.answer()  # Закрытие загрузки

        # Обработка callback данных
        callback_data = query.data
        if callback_data == "help_detailed":
            await self.command_handlers.help(update, context)
        elif callback_data.startswith("example_"):
            example_number = callback_data.split("_")[1]
            await self._send_example(update, context, example_number)

    async def _send_example(self, update: Update, context: ContextTypes.DEFAULT_TYPE, example_number: str):
        """Отправка примера запроса"""
        examples = {
            "1": "H2O properties at 300-500K",
            "2": "2 H2 + O2 → 2 H2O at 298-1000K",
            "3": "CO2 thermodynamic data from 298K to 800K",
            "4": "Properties of NH3 from 273K to 373K"
        }

        example = examples.get(example_number, examples["1"])

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📝 *Пример запроса:*\n\n`{example}`\n\n*Скопируйте и отправьте этот запрос*",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Глобальный обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")

        # Отправка сообщения об ошибке пользователю (если возможно)
        if update and hasattr(update, 'effective_chat'):
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="😔 *Произошла внутренняя ошибка*\n\nПопробуйте повторить запрос позже.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")

        # Отправка алерта администратору
        if self.config.admin_user_id:
            await self._send_admin_alert(context.error)

    async def _send_admin_alert(self, error: Exception):
        """Отправка алерта администратору"""
        try:
            from telegram import Bot

            bot = Bot(token=self.config.bot_token)
            error_message = f"🚨 *Bot Error Alert*\n\n" \
                          f"Error: `{type(error).__name__}: {error}`\n" \
                          f"Time: `{asyncio.get_event_loop().time()}`"

            await bot.send_message(
                chat_id=self.config.admin_user_id,
                text=error_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to send admin alert: {e}")

# Entry point для запуска бота
async def main():
    """Main entry point"""
    import os

    # Загрузка конфигурации
    config = TelegramBotConfig.from_env()

    # Валидация конфигурации
    errors = config.validate()
    if errors:
        logger.error("Configuration errors:")
        for error in errors:
            logger.error(f"  - {error}")
        return

    # Создание и запуск бота
    bot = ThermoSystemTelegramBot(config)
    bot._start_time = asyncio.get_event_loop().time()  # Установка start time

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Запуск бота
    asyncio.run(main())
```

## 📝 2. Обработчики команд

### 2.1. BotCommandHandlers

```python
# src/thermo_agents/telegram_bot/handlers/bot_command_handlers.py
import asyncio
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram import ParseMode, ChatAction

from src.thermo_agents.orchestrator import ThermoOrchestrator
from src.thermo_agents.telegram_bot.managers.session_manager import SessionManager
from src.thermo_agents.telegram_bot.config import TelegramBotConfig

logger = logging.getLogger(__name__)

class BotCommandHandlers:
    """
    Обработчики команд Telegram бота

    Обрабатывает команды: /start, /help, /calculate, /status, /examples, /about
    """

    def __init__(self, orchestrator: ThermoOrchestrator,
                 session_manager: SessionManager, config: TelegramBotConfig):
        self.orchestrator = orchestrator
        self.session_manager = session_manager
        self.config = config

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - приветствие пользователя"""
        user = update.effective_user
        chat_id = update.effective_chat.id

        # Создание сессии
        session = self.session_manager.get_or_create_session(
            user_id=user.id,
            username=user.username
        )

        welcome_text = (
            f"🔥 *Добро пожаловать в ThermoCalcBot!* 🔥\n\n"
            f"Ваш AI-помощник по термодинамическим расчётам\n\n"
            f"🧪 *Что я умею:*\n"
            f"• Расчёт термодинамических свойств веществ\n"
            f"• Анализ химических реакций\n"
            f"• Построение таблиц с данными\n"
            f"• Многофазные расчёты с фазовыми переходами\n\n"
            f"📝 *Как использовать:*\n"
            f"Просто отправьте запрос на естественном языке:\n"
            f"`H2O свойства при 300-500K`\n"
            f"`2 H2 + O2 → 2 H2O при 298K`\n\n"
            f"❓ *Нужна помощь?* Используйте /help"
        )

        # Создание inline клавиатуры
        keyboard = [
            [
                InlineKeyboardButton("📚 Справка", callback_data="help_detailed"),
                InlineKeyboardButton("📋 Примеры", callback_data="examples_list")
            ],
            [
                InlineKeyboardButton("📊 Статус", callback_data="bot_status"),
                InlineKeyboardButton("ℹ️ О системе", callback_data="about_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

        logger.info(f"User {user.username}({user.id}) started bot")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - подробная справка"""
        chat_id = update.effective_chat.id

        help_text = (
            "📚 *Справка по ThermoCalcBot*\n\n"
            "🧪 *Основные возможности:*\n\n"
            "• 📊 **Термодинамические свойства:**\n"
            "  `H2O свойства при 300-500K`\n"
            "  `CO2 данные от 298 до 800K`\n\n"
            "• ⚗️ **Химические реакции:**\n"
            "  `2 H2 + O2 → 2 H2O`\n"
            "  `CH4 + 2 O2 → CO2 + 2 H2O`\n\n"
            "• 📈 **Многофазные системы:**\n"
            "  `H2O фазовые переходы 273-373K`\n\n"
            "📝 *Формат запросов:*\n"
            "• Температурный диапазон: `300-500K` или `300K`\n"
            "• Шаг: `с шагом 50K` или `every 50K`\n"
            "• Фазы: `газовая`, `жидкая`, `твёрдая`\n\n"
            "🎯 *Команды:*\n"
            "• `/calculate <запрос>` - выполнить расчёт\n"
            "• `/examples` - посмотреть примеры\n"
            "• `/status` - статус бота\n"
            "• `/about` - о системе\n\n"
            "💡 *Совет:* Бот автоматически определит тип запроса и отправит результат в виде сообщения или файла!"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=help_text,
            parse_mode=ParseMode.MARKDOWN
        )

    async def calculate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /calculate - выполнить расчёт"""
        chat_id = update.effective_chat.id

        # Получение запроса после команды
        if context.args:
            query = " ".join(context.args)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="📝 *Использование:*\n\n`/calculate <ваш запрос>`\n\n"
                     "Например: `/calculate H2O свойства при 300K`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Обработка запроса через message handler
        from src.thermo_agents.telegram_bot.handlers.message_handler import TelegramMessageHandler

        # Создание временного message handler
        message_handler = TelegramMessageHandler(
            self.orchestrator,
            self.session_manager
        )

        # Создание mock update
        update.message.text = query
        await message_handler.handle_text(update, context)

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - статус бота и системы"""
        chat_id = update.effective_chat.id

        # Получение статистики сессий
        session_stats = self.session_manager.get_session_stats()
        active_sessions = self.session_manager.get_active_session_count()

        # Получение системной информации
        import psutil
        import time
        import os

        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage('/')

        status_text = (
            "📊 *Статус ThermoCalcBot*\n\n"
            f"🤖 *Бот активен:* ✅ Работает\n"
            f"👥 *Активных сессий:* {active_sessions}\n"
            f"📈 *Всего запросов:* {session_stats.get('total_requests', 0):,}\n"
            f"⏱️ *Среднее время сессии:* {session_stats.get('avg_session_duration', 0):.1f}s\n\n"
            f"💻 *Системные ресурсы:*\n"
            f"🧠 *Память:* {memory_info.percent}% ({memory_info.used // 1024 // 1024}MB / {memory_info.total // 1024 // 1024}MB)\n"
            f"💾 *Диск:* {disk_info.percent}% ({disk_info.free // 1024 // 1024 // 1024}GB свободно)\n\n"
            f"⚙️ *Конфигурация:*\n"
            f"🔧 *Макс. пользователей:* {self.config.max_concurrent_users}\n"
            f"📁 *Файлы:* {'Включены' if self.config.enable_file_downloads else 'Выключены'}\n"
            f"📊 *Аналитика:* {'Включена' if self.config.enable_analytics else 'Выключена'}"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=status_text,
            parse_mode=ParseMode.MARKDOWN
        )

    async def examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /examples - примеры запросов"""
        chat_id = update.effective_chat.id

        examples_text = (
            "📋 *Примеры запросов*\n\n"
            "🧪 *Термодинамические свойства:*\n"
            "1. `H2O свойства при 300-500K с шагом 50K`\n"
            "2. `CO2 данные от 298 до 800K`\n"
            "3. `Аммиак NH3 свойства 273-373K`\n"
            "4. `Метан CH4 термодинамика 298K`\n\n"
            "⚗️ *Химические реакции:*\n"
            "5. `2 H2 + O2 → 2 H2O при 298-1000K`\n"
            "6. `CH4 + 2 O2 → CO2 + 2 H2O`\n"
            "7. `N2 + 3 H2 ⇌ 2 NH3` (обратимая реакция)\n"
            "8. `C + O2 → CO2` сгорание углерода\n\n"
            "🔄 *Фазовые переходы:*\n"
            "9. `H2O фазовые переходы 273-373K`\n"
            "10. `Лёд ↔ вода ↔ пар температурная зависимость`\n\n"
            "💡 *Совет:* Просто скопируйте пример и отправьте его боту!"
        )

        # Создание inline клавиатуры с примерами
        keyboard = [
            [InlineKeyboardButton("🧪 H2O свойства", callback_data="example_1")],
            [InlineKeyboardButton("⚗️ Реакция горения", callback_data="example_2")],
            [InlineKeyboardButton("🔄 Фазовый переход", callback_data="example_3")],
            [InlineKeyboardButton("📋 Больше примеров", callback_data="examples_list")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id,
            text=examples_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

    async def about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /about - информация о системе"""
        chat_id = update.effective_chat.id

        about_text = (
            "ℹ️ *О ThermoCalcBot*\n\n"
            "🔥 *ThermoSystem Telegram Bot* v2.2\n\n"
            "🧪 **Основная система:**\n"
            "• ThermoSystem v2.2 - AI термодинамические расчёты\n"
            "• База данных: 316,000+ термодинамических записей\n"
            "• LLM-powered извлечение параметров\n"
            "• Многофазные расчёты с фазовыми переходами\n\n"
            "⚙️ **Технологии:**\n"
            "• Python 3.12+ с asyncio\n"
            "• OpenRouter LLM API\n"
            "• SQLite база данных\n"
            "• python-telegram-bot v20.7+\n\n"
            "📊 **Возможности:**\n"
            "• Расчёт термодинамических свойств\n"
            "• Анализ химических реакций\n"
            "• Поддержка Unicode формул (H₂O, CO₂)\n"
            "• Экспорт результатов в TXT файлы\n"
            "• Асинхронная обработка запросов\n\n"
            "👨‍💻 **Разработка:**\n"
            "Интеграция с ThermoSystem AI Agent Framework\n"
            "Современная архитектура с высоким покрытием тестами\n\n"
            "📧 **Поддержка:**\n"
            "Используйте /help для получения справки"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=about_text,
            parse_mode=ParseMode.MARKDOWN
        )
```

## 📨 3. Обработчик сообщений

### 3.1. TelegramMessageHandler

```python
# src/thermo_agents/telegram_bot/handlers/message_handler.py
import asyncio
import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram import ParseMode, ChatAction

from src.thermo_agents.orchestrator import ThermoOrchestrator
from src.thermo_agents.telegram_bot.managers.session_manager import SessionManager
from src.thermo_agents.telegram_bot.formatters.telegram_formatter import TelegramResponseFormatter
from src.thermo_agents.telegram_bot.managers.smart_response import SmartResponseHandler

logger = logging.getLogger(__name__)

class TelegramMessageHandler:
    """
    Обработчик текстовых сообщений Telegram бота

    Features:
    - Асинхронная обработка запросов
    - Индикация набора текста
    - Session logging
    - Error handling с fallback
    - Smart response formatting
    """

    def __init__(self,
                 orchestrator: ThermoOrchestrator,
                 session_manager: SessionManager,
                 response_formatter: Optional[TelegramResponseFormatter] = None,
                 smart_response: Optional[SmartResponseHandler] = None):
        self.orchestrator = orchestrator
        self.session_manager = session_manager
        self.response_formatter = response_formatter or TelegramResponseFormatter()
        self.smart_response = smart_response

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Основной метод обработки текстовых сообщений

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
        """
        user = update.effective_user
        chat_id = update.effective_chat.id
        query = update.message.text.strip()

        # Валидация запроса
        if not self._validate_query(query):
            await self._send_validation_error(update, context)
            return

        # Создание или получение сессии
        session = self.session_manager.get_or_create_session(
            user_id=user.id,
            username=user.username
        )

        # Создание logger для сессии
        from src.thermo_agents.telegram_bot.managers.session_manager import TelegramSessionLogger
        session_logger = TelegramSessionLogger(user.id, user.username)

        try:
            # Логирование запроса
            session_logger.log_user_request(query)

            # Отправка индикатора набора текста
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING
            )

            # Выполнение расчёта
            start_time = time.time()
            response = await self.orchestrator.process_query(query)
            processing_time = time.time() - start_time

            # Проверка результата
            if not response or response.strip() == "":
                await self._send_empty_response_error(update, context)
                return

            # Форматирование и отправка ответа
            await self._send_formatted_response(update, context, response, session_logger)

            # Логирование успешного завершения
            session_logger.log_bot_response(len(response), processing_time)

        except Exception as e:
            # Логирование ошибки
            session_logger.error(f"Error processing query: {e}")

            # Отправка сообщения об ошибке
            await self._send_error_message(update, context, str(e))

        finally:
            # Закрытие logger сессии
            session_logger.__exit__(None, None, None)

    def _validate_query(self, query: str) -> bool:
        """
        Валидация входного запроса

        Args:
            query: Текст запроса

        Returns:
            bool: True если запрос валидный
        """
        # Проверка длины
        if len(query) < 3:
            return False

        if len(query) > 1000:
            return False

        # Проверка на запрещенные паттерны
        forbidden_patterns = [
            '<script>', 'javascript:', 'http://', 'https://',
            'exec(', 'eval(', 'import os', 'import sys'
        ]

        query_lower = query.lower()
        for pattern in forbidden_patterns:
            if pattern in query_lower:
                return False

        return True

    async def _send_validation_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправка сообщения об ошибке валидации"""
        error_text = (
            "😔 *Неверный формат запроса*\n\n"
            "Запрос должен содержать 3-1000 символов и не включать:\n"
            "• HTML теги\n"
            "• JavaScript код\n"
            "• Ссылки\n\n"
            "Попробуйте переформулировать запрос или используйте /help"
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=error_text,
            parse_mode=ParseMode.MARKDOWN
        )

    async def _send_empty_response_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отправка сообщения о пустом ответе"""
        error_text = (
            "🤔 *Не удалось обработать запрос*\n\n"
            "Попробуйте:\n"
            "• Переформулировать запрос\n"
            "• Проверить правильность химических формул\n"
            "• Использовать другие параметры температуры\n\n"
            "Используйте /examples для просмотра примеров"
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=error_text,
            parse_mode=ParseMode.MARKDOWN
        )

    async def _send_error_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, error_message: str):
        """
        Отправка сообщения об ошибке с детальной информацией

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            error_message: Детальное сообщение об ошибке
        """
        # Категоризация ошибки
        error_category = self._categorize_error(error_message)

        # Генерация user-friendly сообщения
        user_message = self._generate_user_error_message(error_category, error_message)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=user_message,
            parse_mode=ParseMode.MARKDOWN
        )

    def _categorize_error(self, error_message: str) -> str:
        """
        Категоризация ошибки для выбора соответствующего сообщения

        Args:
            error_message: Текст ошибки

        Returns:
            str: Категория ошибки
        """
        error_lower = error_message.lower()

        if any(keyword in error_lower for keyword in ['timeout', 'time out']):
            return 'timeout'
        elif any(keyword in error_lower for keyword in ['database', 'sql', 'sqlite']):
            return 'database'
        elif any(keyword in error_lower for keyword in ['llm', 'openrouter', 'api']):
            return 'llm_api'
        elif any(keyword in error_lower for keyword in ['extract', 'parse', 'formula']):
            return 'parsing'
        elif any(keyword in error_lower for keyword in ['memory', 'ram']):
            return 'memory'
        else:
            return 'general'

    def _generate_user_error_message(self, category: str, error_message: str) -> str:
        """
        Генерация user-friendly сообщения об ошибке

        Args:
            category: Категория ошибки
            error_message: Детальное сообщение об ошибке

        Returns:
            str: User-friendly сообщение
        """
        messages = {
            'timeout': (
                "⏰ *Превышено время ожидания*\n\n"
                "Запрос слишком сложный или система перегружена.\n\n"
                "Попробуйте:\n"
                "• Уменьшить температурный диапазон\n"
                "• Увеличить шаг по температуре\n"
                "• Повторить запрос через несколько минут"
            ),
            'database': (
                "🗄️ *Ошибка базы данных*\n\n"
                "Временные проблемы с доступом к данным.\n\n"
                "Попробуйте повторить запрос через минуту.\n"
                "Если проблема сохранится, используйте /examples"
            ),
            'llm_api': (
                "🤖 *Сервис временно недоступен*\n\n"
                "AI сервис обработки запросов перегружен.\n\n"
                "Попробуйте:\n"
                "• Повторить запрос через минуту\n"
                "• Использовать более простую формулировку"
            ),
            'parsing': (
                "📝 *Ошибка анализа запроса*\n\n"
                "Не удалось распознать химические формулы или параметры.\n\n"
                "Проверьте:\n"
                "• Правильность написания химических формул\n"
                "• Корректность температурного диапазона\n\n"
                "Используйте /examples для корректных форматов"
            ),
            'memory': (
                "💾 *Недостаточно памяти*\n\n"
                "Система временно перегружена.\n\n"
                "Попробуйте:\n"
                "• Уменьшить сложность запроса\n"
                "• Повторить запрос через несколько минут"
            ),
            'general': (
                "😔 *Произошла ошибка*\n\n"
                "Неизвестная ошибка при обработке запроса.\n\n"
                "Попробуйте:\n"
                "• Переформулировать запрос\n"
                "• Использовать /examples для справки\n"
                "• Повторить запрос позже"
            )
        }

        base_message = messages.get(category, messages['general'])

        # Добавление технической информации в debug режиме
        import os
        if os.getenv("DEBUG_MODE", "false").lower() == "true":
            base_message += f"\n\n`{error_message[:200]}`"

        return base_message

    async def _send_formatted_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                     response: str, session_logger):
        """
        Отправка отформатированного ответа

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            response: Ответ от ThermoOrchestrator
            session_logger: Logger сессии
        """
        # Использование smart response handler если доступен
        if self.smart_response:
            await self.smart_response.send_response(update, context, response)
        else:
            # Базовая отправка сообщений
            formatted_responses = await self.response_formatter.format_response(response)

            for i, part in enumerate(formatted_responses):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=part,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )

                # Небольшая задержка между частями для больших сообщений
                if len(formatted_responses) > 1 and i < len(formatted_responses) - 1:
                    await asyncio.sleep(1)
```

## 📁 4. Менеджеры и утилиты

### 4.1. SmartResponseHandler

```python
# src/thermo_agents/telegram_bot/managers/smart_response.py
import asyncio
import logging
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram import ParseMode

from src.thermo_agents.telegram_bot.managers.file_handler import TelegramFileHandler

logger = logging.getLogger(__name__)

class SmartResponseHandler:
    """
    Умный обработчик ответов - автоматически выбирает формат отправки
    (сообщение или файл) в зависимости от контента
    """

    def __init__(self,
                 message_threshold: int = 3000,
                 file_handler: Optional[TelegramFileHandler] = None,
                 enable_file_downloads: bool = True):
        self.message_threshold = message_threshold
        self.file_handler = file_handler
        self.enable_file_downloads = enable_file_downloads

    async def send_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                          response: str, reaction_info: str = "") -> bool:
        """
        Умная отправка ответа (сообщение или файл)

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            response: Ответ для отправки
            reaction_info: Информация о реакции для имени файла

        Returns:
            bool: True если отправка успешна
        """
        try:
            # Проверка нужно ли использовать файл
            should_use_file = self._should_use_file(response)

            if should_use_file and self.enable_file_downloads and self.file_handler:
                # Отправка как файла
                return await self._send_as_file(update, context, response, reaction_info)
            else:
                # Отправка как сообщений
                return await self._send_as_messages(update, context, response)

        except Exception as e:
            logger.error(f"Error in smart response: {e}")
            return False

    def _should_use_file(self, response: str) -> bool:
        """
        Определение нужно ли использовать файловый формат

        Args:
            response: Текст ответа

        Returns:
            bool: True если нужно использовать файл
        """
        # Критерии для использования файла

        # 1. Длина ответа
        if len(response) >= self.message_threshold:
            return True

        # 2. Наличие больших таблиц
        if self._has_large_tables(response):
            return True

        # 3. Сложное форматирование
        if self._has_complex_formatting(response):
            return True

        # 4. Много данных (много строк)
        if response.count('\n') > 100:
            return True

        return False

    def _has_large_tables(self, response: str) -> bool:
        """
        Проверка на наличие больших таблиц в ответе

        Args:
            response: Текст ответа

        Returns:
            bool: True если есть большие таблицы
        """
        lines = response.split('\n')
        table_rows = [line for line in lines if '|' in line]
        return len(table_rows) > 20

    def _has_complex_formatting(self, response: str) -> bool:
        """
        Проверка на сложное форматирование

        Args:
            response: Текст ответа

        Returns:
            bool: True если есть сложное форматирование
        """
        return (
            response.count('┌') > 10 or    # Unicode таблицы
            response.count('─') > 50 or    # Линии таблиц
            response.count('\t') > 20 or   # Табуляция
            response.count('═') > 10       # Двойные линии
        )

    async def _send_as_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                           response: str, reaction_info: str) -> bool:
        """
        Отправка ответа как файла

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            response: Текст ответа
            reaction_info: Информация о реакции

        Returns:
            bool: True если отправка успешна
        """
        try:
            # Отправка файла через file handler
            success = await self.file_handler.send_file(
                update, context, response, reaction_info
            )

            if success:
                # Отправка краткого summary в чате
                summary = self._extract_summary(response)
                summary_message = (
                    f"✅ *Расчёт завершён!*\n\n{summary}\n\n"
                    f"💾 *Полный отчёт в прикреплённом файле*"
                )

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=summary_message,
                    parse_mode=ParseMode.MARKDOWN
                )

            return success

        except Exception as e:
            logger.error(f"Error sending as file: {e}")
            # Fallback на отправку как сообщения
            return await self._send_as_messages(update, context, response)

    async def _send_as_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                               response: str) -> bool:
        """
        Отправка ответа как сообщений (с разделением если нужно)

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            response: Текст ответа

        Returns:
            bool: True если отправка успешна
        """
        try:
            from src.thermo_agents.telegram_bot.formatters.telegram_formatter import TelegramResponseFormatter

            formatter = TelegramResponseFormatter()
            formatted_parts = await formatter.format_response(response)

            for i, part in enumerate(formatted_parts):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=part,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )

                # Небольшая задержка между частями
                if len(formatted_parts) > 1:
                    await asyncio.sleep(0.5)

            return True

        except Exception as e:
            logger.error(f"Error sending as messages: {e}")
            return False

    def _extract_summary(self, response: str) -> str:
        """
        Извлечение краткого summary из полного ответа

        Args:
            response: Полный ответ

        Returns:
            str: Краткий summary
        """
        lines = response.split('\n')
        summary_lines = []

        # Поиск ключевой информации
        for line in lines[:50]:  # Проверяем первые 50 строк
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in [
                'уравнение:', 'реакция:', 'температурный диапазон:',
                'δh', 'k =', 't =', 'вещество:', 'соединение:'
            ]):
                summary_lines.append(line.strip())

        # Если ничего не найдено, берем первые строки
        if not summary_lines:
            for line in lines[:5]:
                if line.strip():
                    summary_lines.append(line.strip())

        # Ограничиваем количество строк
        summary = '\n'.join(summary_lines[:5])

        # Ограничиваем длину
        if len(summary) > 300:
            summary = summary[:297] + "..."

        return summary if summary else "Термодинамический расчёт выполнен"
```

### 4.2. TelegramFileHandler

```python
# src/thermo_agents/telegram_bot/managers/file_handler.py
import os
import tempfile
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram import ParseMode

logger = logging.getLogger(__name__)

class TelegramFileHandler:
    """
    Управление временными файлами для отправки через Telegram

    Features:
    - Создание временных файлов с уникальными именами
    - Unicode нормализация для имён файлов
    - Автоматическая очистка старых файлов
    - Проверка размера файлов
    - Профессиональное форматирование TXT отчётов
    """

    def __init__(self,
                 temp_dir: str = "temp/telegram_files",
                 cleanup_hours: int = 24,
                 max_file_size_mb: int = 20):
        self.temp_dir = Path(temp_dir)
        self.cleanup_hours = cleanup_hours
        self.max_file_size_mb = max_file_size_mb
        self.active_files = {}  # user_id -> file_info

        # Создание директории
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Запуск фоновой очистки
        asyncio.create_task(self._periodic_cleanup())

    async def create_temp_file(self, content: str, user_id: int, reaction_info: str = "") -> str:
        """
        Создание временного файла с уникальным именем

        Args:
            content: Содержимое файла
            user_id: ID пользователя
            reaction_info: Информация о реакции для имени файла

        Returns:
            str: Путь к созданному файлу
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Генерация имени файла
        safe_reaction = self._sanitize_filename(reaction_info)
        if safe_reaction:
            filename = f"thermo_report_{safe_reaction}_{timestamp}.txt"
        else:
            filename = f"thermo_report_{user_id}_{timestamp}.txt"

        file_path = self.temp_dir / filename

        # Запись файла с UTF-8 кодировкой
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Регистрация файла
        self.active_files[user_id] = {
            'path': str(file_path),
            'filename': filename,
            'created_at': datetime.now(),
            'size': len(content)
        }

        logger.info(f"Created temp file: {filename} ({len(content)} chars)")
        return str(file_path)

    async def send_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                       content: str, reaction_info: str = "") -> bool:
        """
        Отправка контента как файла через Telegram

        Args:
            update: Telegram Update объект
            context: Telegram Context объект
            content: Содержимое для отправки
            reaction_info: Информация о реакции для имени файла

        Returns:
            bool: True если отправка успешна
        """
        try:
            # Проверка размера файла
            file_size_mb = len(content.encode('utf-8')) / (1024 * 1024)

            if file_size_mb > self.max_file_size_mb:
                logger.warning(f"File size {file_size_mb:.2f}MB exceeds limit {self.max_file_size_mb}MB")
                await self._send_file_size_error(update, context, file_size_mb)
                return False

            # Создание временного файла
            file_path = await self.create_temp_file(content, update.effective_user.id, reaction_info)
            filename = Path(file_path).name

            # Чтение файла и создание InputFile
            with open(file_path, 'rb') as f:
                file_content = f.read()
                input_file = InputFile(file_content, filename=filename)

            # Отправка файла
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=input_file,
                caption=self._generate_caption(content, reaction_info),
                parse_mode=ParseMode.MARKDOWN
            )

            logger.info(f"File sent successfully: {filename}")
            return True

        except Exception as e:
            logger.error(f"Error sending file: {e}")
            return False

    def _generate_caption(self, content: str, reaction_info: str) -> str:
        """
        Генерация подписи к файлу

        Args:
            content: Содержимое файла
            reaction_info: Информация о реакции

        Returns:
            str: Caption для файла
        """
        char_count = len(content)
        kb_size = char_count / 1024

        caption = (
            f"📊 *Детальный термодинамический отчёт*\n\n"
        )

        if reaction_info:
            caption += f"**Расчёт:** {reaction_info}\n"

        caption += (
            f"**Размер:** {char_count:,} символов ({kb_size:.1f} KB)\n"
            f"**Создан:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💾 *Сохраните файл для офлайн анализа*"
        )

        return caption

    async def _send_file_size_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  file_size_mb: float):
        """Отправка сообщения об ошибке размера файла"""
        error_text = (
            f"⚠️ *Файл слишком большой*\n\n"
            f"Размер отчёта: {file_size_mb:.2f}MB превышает лимит Telegram ({self.max_file_size_mb}MB).\n\n"
            f"Попробуйте:\n"
            f"• Уменьшить температурный диапазон\n"
            f"• Увеличить шаг по температуре\n"
            f"• Упростить запрос"
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=error_text,
            parse_mode=ParseMode.MARKDOWN
        )

    def _sanitize_filename(self, filename: str) -> str:
        """
        Очистка имени файла от недопустимых символов с Unicode нормализацией

        Args:
            filename: Исходное имя файла

        Returns:
            str: Очищенное имя файла
        """
        import re
        import unicodedata

        # Нормализация Unicode
        filename = unicodedata.normalize('NFKC', filename)

        # Преобразование подстрочных индексов в обычные цифры
        subscript_map = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
        filename = filename.translate(subscript_map)

        # Преобразование надстрочных индексов
        superscript_map = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789')
        filename = filename.translate(superscript_map)

        # Замена специальных символов
        filename = filename.replace('→', '_to_')
        filename = filename.replace('⇌', '_eq_')
        filename = filename.replace('↔', '_eq_')
        filename = filename.replace('→', '_to_')
        filename = filename.replace('←', '_from_')

        # Удаление недопустимых символов
        filename = re.sub(r'[^\w\s-]', '_', filename)

        # Замена пробелов на подчеркивания
        filename = re.sub(r'\s+', '_', filename)

        # Удаление множественных подчеркиваний
        filename = re.sub(r'_+', '_', filename)

        # Ограничение длины и удаление подчеркиваний по краям
        filename = filename.strip('_')[:50]

        return filename

    async def _periodic_cleanup(self):
        """Периодическая очистка старых файлов"""
        while True:
            try:
                await asyncio.sleep(3600)  # Проверка каждый час
                await self._cleanup_old_files()
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def _cleanup_old_files(self):
        """Очистка файлов старше cleanup_hours"""
        cutoff_time = datetime.now() - timedelta(hours=self.cleanup_hours)
        deleted_count = 0

        try:
            for file_path in self.temp_dir.glob("*.txt"):
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Error deleting file {file_path}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old files")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def get_file_stats(self) -> dict:
        """
        Получение статистики по файлам

        Returns:
            dict: Статистика по файлам
        """
        try:
            files = list(self.temp_dir.glob("*.txt"))
            total_size = sum(f.stat().st_size for f in files)

            return {
                'total_files': len(files),
                'total_size_mb': total_size / (1024 * 1024),
                'active_sessions': len(self.active_files),
                'temp_directory': str(self.temp_dir)
            }
        except Exception as e:
            logger.error(f"Error getting file stats: {e}")
            return {
                'total_files': 0,
                'total_size_mb': 0,
                'active_sessions': 0,
                'temp_directory': str(self.temp_dir)
            }

    async def cleanup_user_files(self, user_id: int):
        """
        Очистка файлов конкретного пользователя

        Args:
            user_id: ID пользователя
        """
        if user_id in self.active_files:
            file_info = self.active_files[user_id]
            try:
                file_path = Path(file_info['path'])
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Cleaned up file for user {user_id}: {file_info['filename']}")
                del self.active_files[user_id]
            except Exception as e:
                logger.error(f"Error cleaning up user {user_id} files: {e}")
```

---

## 📝 Резюме

**Примеры кода предоставляют:**

1. **Полный функционал:**
   - Основной класс бота с обработкой ошибок
   - Обработчики всех команд и сообщений
   - Умная система отправки файлов
   - Session management и logging

2. **Production-ready код:**
   - Graceful shutdown
   - Error handling с fallback
   - Health checks и monitoring
   - Security considerations

3. **Масштабируемость:**
   - Асинхронная обработка
   - Rate limiting и protection
   - Smart response optimization
   - Resource management

4. **UX оптимизация:**
   - Progress indicators
   - Inline keyboards
   - Markdown formatting
   - Error messages с советами

**Следующий этап:** [10_appendices.md](10_appendices.md) - Приложения и справочные материалы.