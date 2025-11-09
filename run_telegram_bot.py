#!/usr/bin/env python3
"""
Демонстрационный скрипт для запуска ThermoSystem Telegram Bot.

Использование:
1. Убедитесь, что все зависимости установлены:
   uv sync

2. Создайте файл .env с необходимыми переменными:
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   OPENROUTER_API_KEY=your_openrouter_api_key
   DB_PATH=data/thermo_data.db
   ADMIN_USER_ID=your_telegram_user_id  # опционально

3. Запустите бота:
   uv run python run_telegram_bot.py

4. Для тестового режима с ограниченной функциональностью:
   uv run python run_telegram_bot.py --test
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent / "src"))

from thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from thermo_agents.telegram_bot.config import TelegramBotConfig
from thermo_agents.telegram_bot.utils.error_handler import TelegramBotErrorHandler


def setup_signal_handlers(bot):
    """Настройка обработчиков сигналов для graceful shutdown."""
    def signal_handler(signum, frame):
        print(f"\nПолучен сигнал {signum}, выполняю graceful shutdown...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def run_bot(config: TelegramBotConfig, test_mode: bool = False):
    """Запуск бота."""
    print("🚀 Запуск ThermoSystem Telegram Bot...")
    print(f"📝 Режим: {'Тестовый' if test_mode else 'Продуктивный'}")
    print(f"🤖 Bot Username: {config.bot_username}")

    if test_mode:
        print("⚠️  Тестовый режим: ограниченная функциональность")
        # В тестовом режиме можно уменьшить лимиты
        config.max_concurrent_users = 5
        config.request_timeout_seconds = 30

    try:
        # Проверка конфигурации
        config_errors = config.validate_config()
        if config_errors:
            print(f"❌ Ошибки конфигурации:")
            for error in config_errors:
                print(f"   • {error}")
            return False

        # Создание и запуск бота
        bot = ThermoSystemTelegramBot(config)

        # Настройка сигналов
        setup_signal_handlers(bot)

        print("✅ Бот успешно инициализирован")
        print("🔄 Запуск обработки сообщений...")
        print("📱 Нажмите Ctrl+C для остановки")

        # Запуск бота
        await bot.start()

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка при запуске бота")
        return False
    finally:
        print("👋 Бот остановлен")

    return True


async def test_components(config: TelegramBotConfig):
    """Тестирование компонентов перед запуском."""
    print("🧪 Тестирование компонентов...")

    try:
        # Тест импорта всех необходимых модулей
        from thermo_agents.telegram_bot.utils.thermo_integration import ThermoIntegration
        from thermo_agents.telegram_bot.utils.health_checker import HealthChecker
        from thermo_agents.telegram_bot.handlers.message_handler import MessageHandler
        from thermo_agents.telegram_bot.handlers.callback_handler import CallbackHandler
        from thermo_agents.telegram_bot.managers.smart_response import SmartResponseHandler

        print("✅ Все модули успешно импортированы")

        # Тест интеграции с ThermoSystem
        thermo_integration = ThermoIntegration(config)
        if thermo_integration.orchestrator:
            print("✅ ThermoOrchestrator успешно инициализирован")
        else:
            print("⚠️  ThermoOrchestrator не инициализирован")

        # Тест базы данных
        if config.thermo_db_path.exists():
            file_size = config.thermo_db_path.stat().st_size
            print(f"✅ База данных найдена: {file_size / 1024 / 1024:.1f}MB")
        else:
            print(f"❌ База данных не найдена: {config.thermo_db_path}")
            return False

        # Тест health checker
        health_checker = HealthChecker(config, thermo_integration)
        print("✅ Health Checker успешно инициализирован")

        print("🎉 Все тесты пройдены!")
        return True

    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        logging.exception("Ошибка при тестировании компонентов")
        return False


def print_banner():
    """Вывод баннера."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                ThermoSystem Telegram Bot                      ║
║                     v1.1 (2025)                              ║
║                                                              ║
║  🔬 Термодинамические расчёты в Telegram                     ║
║  📊 Интеграция с ThermoSystem v2.2                           ║
║  🤖 Умная система ответов                                     ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_help():
    """Вывод справки."""
    help_text = """
Использование:
    python run_telegram_bot.py [опции]

Опции:
    --test, -t    Запуск в тестовом режиме
    --help, -h    Показать эту справку
    --check, -c   Только проверить компоненты, не запускать бота

Переменные окружения (.env файл):
    TELEGRAM_BOT_TOKEN          Токен Telegram бота (обязательно)
    OPENROUTER_API_KEY         API ключ для OpenRouter (обязательно)
    DB_PATH                    Путь к базе данных (default: data/thermo_data.db)
    ADMIN_USER_ID              ID администратора (опционально)
    LOG_LEVEL                  Уровень логирования (default: INFO)
    MAX_CONCURRENT_USERS      Максимум пользователей (default: 20)
    TELEGRAM_MODE              Режим работы: polling или webhook (default: polling)

Пример:
    uv run python run_telegram_bot.py --test
"""
    print(help_text)


async def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(
        description="ThermoSystem Telegram Bot - термодинамические расчёты в Telegram",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Запуск в тестовом режиме с ограниченной функциональностью"
    )
    parser.add_argument(
        "--check", "-c",
        action="store_true",
        help="Только проверить компоненты, не запускать бота"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Детальный вывод логов"
    )

    args = parser.parse_args()

    # Настройка логирования
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('logs/telegram_bot.log', encoding='utf-8')
        ]
    )

    # Создание директории для логов
    Path("logs").mkdir(exist_ok=True)

    # Вывод баннера
    print_banner()

    try:
        # Загрузка конфигурации
        print("⚙️  Загрузка конфигурации...")
        config = TelegramBotConfig.from_env()
        print(f"✅ Конфигурация загружена")
        print(f"   • Bot Username: {config.bot_username}")
        print(f"   • Max пользователей: {config.max_concurrent_users}")
        print(f"   • База данных: {config.thermo_db_path}")

        # Тестирование компонентов
        if not await test_components(config):
            print("❌ Тестирование компонентов не пройдено")
            return 1

        if args.check:
            print("✅ Проверка компонентов завершена успешно")
            return 0

        # Запуск бота
        success = await run_bot(config, test_mode=args.test)
        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n🛑 Программа прервана пользователем")
        return 0
    except Exception as e:
        print(f"❌ Непредвиденная ошибка: {e}")
        logging.exception("Непредвиденная ошибка")
        return 1


if __name__ == "__main__":
    # Для Windows корректная обработка asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    exit_code = asyncio.run(main())
    sys.exit(exit_code)