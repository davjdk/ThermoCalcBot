"""
Обработчики команд и сообщений для Telegram бота.

Основные классы:
- CommandHandler: Обработчик команд бота
- MessageHandler: Обработчик текстовых сообщений
- CallbackHandler: Обработчик callback'ов (для интерактивных элементов)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from .config import TelegramBotConfig
from .models import (
    BotResponse, MessageType, CommandStatus, ProgressMessage,
    BOT_COMMANDS
)
from .session_manager import SessionManager
from .thermo_adapter import ThermoAdapter

logger = logging.getLogger(__name__)


class CommandHandler:
    """Обработчик команд Telegram бота."""

    def __init__(self, config: TelegramBotConfig, session_manager: SessionManager, thermo_adapter: ThermoAdapter):
        self.config = config
        self.session_manager = session_manager
        self.thermo_adapter = thermo_adapter

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик команды /start."""
        user = update.effective_user
        session = self.session_manager.get_or_create_session(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Обновляем статистику команды
        BOT_COMMANDS["start"].increment_usage()

        welcome_text = f"""
🔥 *Добро пожаловать в ThermoSystem Telegram Bot!*

Привет, {user.first_name}! Я ваш помощник для термодинамических расчётов.

🚀 *Что я могу делать:*
• Расчёт термодинамики химических реакций
• Получение таблиц свойств веществ
• Анализ фазовых переходов
• Генерация профессиональных отчётов

📝 *Примеры запросов:*
`2 H2 + O2 → 2 H2O при 298-1000K`
`Свойства CO2 от 298 до 1000K`
`Дай таблицу для H2O при 300-600K`

💡 *Используйте /help для подробной справки*

_ThermoSystem v2.2 - Термодинамическая система с LLM-интеграцией_
        """.strip()

        return BotResponse(
            text=welcome_text,
            message_type=MessageType.COMMAND,
            command="/start",
            user_id=user.id,
            use_markdown=True
        )

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик команды /help."""
        user = update.effective_user
        session = self.session_manager.get_or_create_session(user.id, user.username, user.first_name, user.last_name)
        BOT_COMMANDS["help"].increment_usage()

        # Получаем аргументы команды
        args = context.args if context.args else []
        topic = args[0].lower() if args else None

        if topic == "расчеты" or topic == "расчеты":
            help_text = """
🔥 *Справка по термодинамическим расчётам*

📊 *Типы запросов:*

1. **Расчёты реакций:**
   ```
   2 H2 + O2 → 2 H2O при 298-1000K
   Fe2O3 + 3 C → 2 Fe + 3 CO при 800-1200K
   CH4 + 2 O2 → CO2 + 2 H2O при 500-900K
   ```

2. **Свойства веществ:**
   ```
   Свойства H2O при 300-600K
   Таблица для CO2 от 298 до 1000K
   Термодинамические данные CH4 при 400-800K
   ```

3. **Аналитические запросы:**
   ```
   Реагирует ли сероводород с оксидом железа(II) при 500-700°C?
   Условия для реакции CO + H2O → CO2 + H2
   ```

📝 *Формат температур:*
- Кельвины: `298K`, `500K`
- Диапазоны: `298-1000K`, `от 298 до 1000K`
- Цельсий: `25°C` (авто-конвертация)

⚡ *Формат ответов:*
- Короткие результаты: Telegram сообщение
- Длинные таблицы: TXT файл
- Unicode формулы: H₂O, CO₂, →

🚨 *Ограничения:*
- Максимум 10 веществ в реакции
- Температурный диапазон: 200-2000K
- 30 запросов в минуту
            """.strip()

        else:
            help_text = """
📚 *Справка по ThermoSystem Telegram Bot*

🔧 *Основные команды:*
/start - Приветствие и краткая справка
/help - Подробная справка (темы: расчеты, файлы)
/status - Статус бота и нагрузка
/examples - Примеры запросов
/about - Информация о системе

📝 *Прямые запросы (без команд):**
```
2 H2 + O2 → 2 H2O при 298-1000K
Свойства CO2 от 298 до 1000K
Дай таблицу для H2O при 300-600K с шагом 50K
```

🎯 *Что я могу рассчитать:*
• Термодинамику химических реакций (ΔH, ΔS, ΔG, K)
• Свойства веществ (Cp, H, S, G) по температуре
• Фазовые переходы (плавление, кипение, сублимация)
• Константы равновесия реакций
• Многофазные системы

📄 *Файловая система:*
- Автоматическая отправка TXT файлов для больших отчетов
- Файлы хранятся 24 часа
- Поддержка файлов до 20MB

⚡ *Функции:*
• Асинхронная обработка (<10 сек)
• Unicode химические формулы
• Progress индикаторы
• Graceful error handling

🚨 *Лимиты:*
• 30 запросов в минуту
• 20 одновременных пользователей
• 1000 символов в запросе

💡 *Советы:*
• Используйте Unicode стрелки: → вместо ->
• Указывайте фазу вещества при необходимости
• Для сложных запросов используйте /help расчеты
            """.strip()

        return BotResponse(
            text=help_text,
            message_type=MessageType.COMMAND,
            command="/help",
            user_id=user.id,
            use_markdown=True
        )

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик команды /status."""
        user = update.effective_user
        session = self.session_manager.get_or_create_session(user.id, user.username, user.first_name, user.last_name)
        BOT_COMMANDS["status"].increment_usage()

        # Получаем статистику системы
        system_stats = self.session_manager.get_system_stats()
        thermo_status = await self.thermo_adapter.get_system_status()

        # Формируем статус
        status_text = f"""
📊 *Статус ThermoSystem Telegram Bot*

🔧 *Система:*
• Статус: {thermo_status.get('status', 'Неизвестно')}
• Последняя проверка: {datetime.now().strftime('%H:%M:%S')}

👥 *Пользователи:*
• Активных сессий: {system_stats['active_sessions']}
• Всего сессий: {system_stats['total_sessions']}
• Обрабатывается запросов: {system_stats['processing_sessions']}

⚡ *Производительность:*
• Максимум пользователей: {system_stats['max_concurrent_users']}
• Лимит запросов/мин: {system_stats['rate_limit_per_minute']}
• Память: ~{system_stats['memory_usage_mb']:.1f} MB

📈 *Ваша сессия:*
• Запросов отправлено: {session.message_count}
• Последняя активность: {session.last_activity.strftime('%H:%M:%S')}
• Статус: {"Обрабатывается запрос" if session.current_query else "Ожидание"}

💾 *Файлы:*
• Временные файлы: {len(session.temp_files)}
• Автоочистка: {self.config.file_config.file_cleanup_hours} часов
        """.strip()

        return BotResponse(
            text=status_text,
            message_type=MessageType.COMMAND,
            command="/status",
            user_id=user.id,
            use_markdown=True
        )

    async def handle_examples(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик команды /examples."""
        user = update.effective_user
        session = self.session_manager.get_or_create_session(user.id, user.username, user.first_name, user.last_name)
        BOT_COMMANDS["examples"].increment_usage()

        examples_text = """
📚 *Примеры запросов для ThermoSystem*

🔥 *Расчёты реакций:*
```
2 H2 + O2 → 2 H2O при 298-1000K
CH4 + 2 O2 → CO2 + 2 H2O при 500-900K
Fe2O3 + 3 C → 2 Fe + 3 CO при 800-1200K
WO3 + 3 H2 → W + 3 H2O при 600-900K
```

📊 *Свойства веществ:*
```
Свойства H2O при 300-600K с шагом 50K
Таблица для CO2 от 298 до 1000K
Термодинамические данные CH4 при 400-800K
Свойства Fe2O3 от 500 до 1200K
```

🔬 *Аналитические запросы:*
```
Реагирует ли сероводород с оксидом железа(II) при 500-700°C?
Условия для реакции CO + H2O → CO2 + H2
Равновесие реакции NH3 синтеза при различных температурах
```

💡 *Сложные системы:*
```
2 W + 4 Cl2 + O2 → 2 WOCl4 при 600-900K
CuSO4 + 2 NH3 · H2O → Cu(OH)2 + (NH4)2SO4
```

⚗️ *Фазовые переходы:*
```
Свойства H2O включая фазовые переходы
Плавление и кипение Fe2O3
Сублимация CO2 при низких температурах
```

🎯 *Советы:*
• Используйте K для температуры (Кельвин)
• Указывайте точные химические формулы
• Для сложных запросов используйте температурные диапазоны
• Формулы поддерживают Unicode: H₂O, CO₂, →

💾 *Результаты:*
- Маленькие таблицы → Telegram сообщение
- Большие расчёты → TXT файл
- Все результаты включают интерпретацию
        """.strip()

        return BotResponse(
            text=examples_text,
            message_type=MessageType.COMMAND,
            command="/examples",
            user_id=user.id,
            use_markdown=True
        )

    async def handle_about(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик команды /about."""
        user = update.effective_user
        session = self.session_manager.get_or_create_session(user.id, user.username, user.first_name, user.last_name)
        BOT_COMMANDS["about"].increment_usage()

        about_text = """
ℹ️ *О ThermoSystem Telegram Bot*

🔬 *Версия:* v1.1 (9 ноября 2025)

🏗️ *Архитектура:*
• ThermoOrchestrator v2.2 - гибридная архитектура
• LLM-компонент: извлечение параметров из естественного языка
• Детерминированные компоненты: расчёты по формулам Шомейта
• База данных: 316,434 термодинамических записей

⚡ *Технологии:*
• Python 3.12+ с asyncio
• python-telegram-bot>=20.7
• PydanticAI для LLM интеграции
• OpenRouter API для доступа к GPT-4
• SQLite для термодинамических данных

📊 *Возможности:*
• Термодинамические расчёты реакций
• Многофазные системы (s/l/g/aq)
• Фазовые переходы и интерполяция
• Профессиональные отчёты в TXT формате
• Unicode химические формулы

🔧 *Методы расчёта:*
• Формулы Шомейта для теплоёмкости
• Численное интегрирование для H, S, G
• Уравнение изобары-изотермы Вант-Гоффа
• Трехуровневая стратегия отбора данных

🚀 *Производительность:*
• <10 секунд для сложных расчётов
• Поддержка 20 одновременных пользователей
• 99.9% uptime с graceful degradation
• Автоматическая оптимизация записей

📝 *Разработка:*
• Спецификация: модульная документация
• Тестирование: unit, integration, E2E
• Безопасность: валидация и rate limiting
• Мониторинг: детальное логирование

🌐 *Источник данных:*
Термодинамическая база данных с коэффициентами Шомейта для стандартных соединений

💻 *Исходный код:*
[ссылка на GitHub репозиторий]

📞 *Поддержка:*
@ThermoCalcBot
        """.strip()

        return BotResponse(
            text=about_text,
            message_type=MessageType.COMMAND,
            command="/about",
            user_id=user.id,
            use_markdown=True
        )


class MessageHandler:
    """Обработчик текстовых сообщений."""

    def __init__(self, config: TelegramBotConfig, session_manager: SessionManager, thermo_adapter: ThermoAdapter):
        self.config = config
        self.session_manager = session_manager
        self.thermo_adapter = thermo_adapter

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[BotResponse]:
        """Обработчик текстовых сообщений."""
        user = update.effective_user
        message = update.message

        if not message or not message.text:
            return None

        query = message.text.strip()

        # Получаем сессию пользователя
        session = self.session_manager.get_or_create_session(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

        # Проверяем, может ли пользователь сделать запрос
        can_make_request, rate_limit_message = self.session_manager.can_user_make_request(user.id)

        if not can_make_request:
            return BotResponse(
                text=rate_limit_message,
                message_type=MessageType.ERROR,
                status=CommandStatus.ERROR,
                user_id=user.id,
                original_query=query,
                use_markdown=True
            )

        # Проверяем, не обрабатывается ли уже запрос
        if self.session_manager.is_user_processing(user.id):
            return BotResponse(
                text="⏳ *Ваш предыдущий запрос ещё обрабатывается*\n\nПодождите завершения перед отправкой нового.",
                message_type=MessageType.ERROR,
                status=CommandStatus.ERROR,
                user_id=user.id,
                original_query=query,
                use_markdown=True
            )

        # Начинаем обработку запроса
        session.start_processing(query)

        try:
            # Регистрируем запрос в rate limiter
            self.session_manager.rate_limiter.record_request(user.id)

            # Отправляем прогресс индикатор
            progress_response = BotResponse(
                text="🔍 *Обработка запроса...*\n\nАнализирую ваш термодинамический запрос...",
                message_type=MessageType.PROGRESS,
                user_id=user.id,
                original_query=query,
                use_markdown=True
            )

            # Обрабатываем запрос через ThermoAdapter
            response, needs_file = await self.thermo_adapter.process_query(query, user.id)

            # Завершаем обработку
            session.finish_processing()

            return response

        except Exception as e:
            # В случае ошибки, завершаем обработку
            session.finish_processing()
            logger.error(f"Error processing message from user {user.id}: {e}")

            return BotResponse(
                text="❌ *Ошибка обработки запроса*\n\n"
                     f"Произошла непредвиденная ошибка. Попробуйте переформулировать запрос или обратитесь к /help.",
                message_type=MessageType.ERROR,
                status=CommandStatus.ERROR,
                user_id=user.id,
                original_query=query,
                use_markdown=True
            )

    async def handle_unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotResponse:
        """Обработчик неизвестной команды."""
        user = update.effective_user
        command = update.message.text

        unknown_command_text = f"""
❓ *Неизвестная команда*

Команда `{command}` не найдена.

📚 *Доступные команды:*
/start - Начать работу
/help - Справка
/calculate - Расчёт (или отправьте запрос напрямую)
/status - Статус системы
/examples - Примеры запросов
/about - О системе

💡 *Вы можете отправлять запросы напрямую:*
```
2 H2 + O2 → 2 H2O при 298-1000K
Свойства CO2 от 298 до 1000K
```
        """.strip()

        return BotResponse(
            text=unknown_command_text,
            message_type=MessageType.ERROR,
            status=CommandStatus.ERROR,
            user_id=user.id,
            command=command,
            use_markdown=True
        )