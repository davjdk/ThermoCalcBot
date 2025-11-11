"""
Обработчик команд Telegram бота.

Поддерживаемые команды:
- /start - Приветствие и краткая справка
- /help - Подробная справка по использованию
- /status - Статус бота и текущая нагрузка
- /examples - Примеры запросов
- /about - Информация о системе
"""

import time
import psutil
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from ..config import TelegramBotConfig, BotStatus
from ..formatters.response_formatter import ResponseFormatter


class CommandHandler:
    """Обработчик команд Telegram бота."""

    def __init__(self, config: TelegramBotConfig, status: BotStatus):
        self.config = config
        self.status = status
        self.formatter = ResponseFormatter(config)

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /start."""
        welcome_message = """🔥 *Добро пожаловать в ThermoSystem Bot!*

Я — ваш помощник для термодинамических расчётов и анализа химических реакций.

📋 *Что я умею:*
• 📊 Получать таблицы термодинамических свойств веществ
• ⚗️ Расчитывать термодинамику химических реакций
• 📄 Генерировать детальные TXT файлы с результатами
• 🔍 Работать с многофазными системами и фазовыми переходами

🚀 *Быстрый старт:*
Просто отправьте мне запрос в естественном формате:
• `"Свойства H2O при 300-600K"`
• `"2 H2 + O2 → 2 H2O при 298-1000K"`

📖 *Полная справка:* /help
📊 *Статус системы:* /status
💡 *Примеры запросов:* /examples

Давайте начнём термодинамические расчёты! 🧪✨"""

        await update.message.reply_text(
            welcome_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /help."""
        help_message = self.formatter.format_help_message()

        await update.message.reply_text(
            help_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /status."""
        # Сбор информации о системе
        status_data = await self._collect_system_info()

        status_message = self.formatter.format_status_message(status_data)

        await update.message.reply_text(
            status_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def handle_examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /examples."""
        examples_message = """💡 *Примеры запросов к ThermoSystem*

📊 *Табличные данные веществ:*

1️⃣ *Базовые свойства:*
`Дай таблицу для H2O при 300-600K с шагом 50 градусов`

2️⃣ *Свойства CO2:*
`Свойства CO2 от 298 до 1000K`

3️⃣ *Оксид железа:*
`Термодинамические данные для Fe2O3 при 400-800K`

⚗️ *Расчёты реакций:*

1️⃣ *Водородная реакция:*
`2 H2 + O2 → 2 H2O при 298-1000K`

2️⃣ *Восстановление оксида железа:*
`Fe2O3 + 3 C → 2 Fe + 3 CO при 800-1200K`

3️⃣ *Вопрос о реакции:*
`Реагирует ли сероводород с оксидом железа(II) при 500-700°C?`

4️⃣ *Сложная реакция:*
`WO3 + 3 H2 → W + 3 H2O при 600-900K`

🎯 *Советы по форматированию:*

✅ *Правильно:*
• `2 H2 + O2 → 2 H2O`
• `Fe2O3 + 3 C → 2 Fe + 3 CO`
• `H2O при 300-600K`
• `CO2 от 298 до 1000K`

❌ *Неправильно:*
• `2h2+o2=2h2o` (используйте пробелы и →)
• `H2O 300K` (укажите диапазон)
• `водород` (используйте химические формулы)

📄 *Результаты:*
• Короткие ответы (<3000 символов) — как сообщения
• Детальные отчёты (>3000 символов) — как TXT файлы
• Максимальный размер файла: 20MB

🔥 *Попробуйте любой из этих примеров прямо сейчас!*"""

        await update.message.reply_text(
            examples_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def handle_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /about."""
        about_message = """🔬 *О ThermoSystem Telegram Bot*

📋 *Версия и информация:*
• **Версия:** 1.1 (9 ноября 2025)
• **Бот:** @ThermoCalcBot
• **Система:** ThermoSystem v2.2

⚙️ *Техническая архитектура:*
• **Ядро:** Гибридная архитектура (LLM + детерминированные компоненты)
• **База данных:** 316K записей термодинамических данных
• **LLM:** OpenAI GPT-4o через OpenRouter API
• **Форматирование:** Professional tables через tabulate

🧪 *Возможности системы:*
• **Типы расчётов:** Табличные данные + термодинамика реакций
• **Многофазность:** Поддержка фазовых переходов (твёрдый, жидкий, газ)
• **Точность:** Формулы Шомейта с численным интегрированием
• **Вещества:** До 10 соединений в реакции
• **Температуры:** 298K - 3000K с настраиваемым шагом

🔍 *Компоненты системы:*
• **ThermodynamicAgent:** Извлечение параметров из естественного языка
• **ThermoOrchestrator:** Основной оркестратор расчётов
• **CompoundSearcher:** Поиск в базе данных веществ
• **ThermodynamicEngine:** Расчёты по формулам Шомейта
• **ReactionEngine:** Расчёт ΔH, ΔS, ΔG, K для реакций

📊 *Производительность:*
• **Время ответа:** <10 секунд для сложных расчётов
• **Конкурентность:** До 20 одновременных пользователей
• **Надежность:** 99.9% uptime с graceful degradation
• **Файлы:** TXT отчёты до 20MB с Unicode поддержкой

🎯 *Спецификация:*
• Документация: [Telegram Bot Integration Specification](docs/specs/telegram_bot_integration/)
• Архитектура: [ThermoSystem Architecture](docs/ARCHITECTURE.md)

💬 *Поддержка:*
По вопросам и предложениям обращайтесь к разработчикам системы.

---
*Сгенерировано автоматически ThermoSystem v2.2*"""

        await update.message.reply_text(
            about_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def handle_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка неизвестных команд."""
        unknown_message = """❓ *Неизвестная команда*

Доступные команды:
/start - Начать работу
/help - Справка по использованию
/status - Статус бота
/examples - Примеры запросов
/about - О системе

Или просто отправьте мне термодинамический запрос в естественном формате! 🧪"""

        await update.message.reply_text(
            unknown_message,
            parse_mode="Markdown"
        )

        # Обновление статистики
        self.status.total_requests += 1
        self.status.successful_requests += 1

    async def _collect_system_info(self) -> dict:
        """Сбор информации о системе."""
        try:
            # Системная информация
            cpu_percent = psutil.cpu_percent()
            memory_info = psutil.virtual_memory()
            memory_mb = memory_info.used / 1024 / 1024

            # Информация о базе данных
            try:
                import sqlite3
                db_path = self.config.thermo_db_path
                if db_path.exists():
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM compounds")
                    db_records = cursor.fetchone()[0]
                    conn.close()
                else:
                    db_records = "N/A"
            except Exception:
                db_records = "N/A"

            return {
                "is_running": self.status.is_running,
                "uptime_seconds": time.time() - (self.status.start_time or time.time()),
                "active_users": self.status.active_users,
                "total_requests": self.status.total_requests,
                "successful_requests": self.status.successful_requests,
                "failed_requests": self.status.failed_requests,
                "average_response_time_ms": self.status.average_response_time_ms,
                "last_error": self.status.last_error,
                "cpu_percent": cpu_percent,
                "memory_mb": memory_mb,
                "db_records": db_records,
                "llm_model": self.config.llm_model,
                "max_concurrent_users": self.config.max_concurrent_users,
                "temp_files_count": await self._get_temp_files_count()
            }

        except Exception as e:
            return {
                "error": f"Ошибка сбора информации: {str(e)}",
                "is_running": self.status.is_running,
                "uptime_seconds": 0,
                "active_users": self.status.active_users,
                "total_requests": self.status.total_requests,
                "successful_requests": self.status.successful_requests,
                "failed_requests": self.status.failed_requests,
            }

    async def _get_temp_files_count(self) -> int:
        """Получение количества временных файлов."""
        try:
            import os
            temp_dir = self.config.temp_file_dir
            if temp_dir.exists():
                return len([f for f in os.listdir(temp_dir) if f.endswith('.txt')])
            return 0
        except Exception:
            return 0