#!/usr/bin/env python3
"""
Development runner for ThermoCalcBot

Скрипт для запуска Telegram бота в development режиме с автоматической
настройкой окружения и валидацией конфигурации.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional

# Добавление src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def setup_dev_environment() -> None:
    """Настройка development окружения"""

    # Установка development окружения
    os.environ["ENVIRONMENT"] = "development"

    # Создание необходимых директорий
    directories = [
        "logs/telegram_sessions",
        "logs/telegram_errors",
        "temp/telegram_files",
        "backup",
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✅ Created directory: {directory}")

    # Загрузка .env.dev если существует
    env_dev_path = Path(__file__).parent.parent / ".env.dev"
    if env_dev_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_dev_path)
            print(f"✅ Loaded environment from: {env_dev_path}")
        except ImportError:
            print("⚠️ python-dotenv not installed, skipping .env.dev loading")
            print("   Install with: pip install python-dotenv")

    print("✅ Development environment configured")

async def run_dev_bot() -> None:
    """Запуск бота в development режиме"""

    setup_dev_environment()

    try:
        from thermo_agents.telegram_bot.config import TelegramBotConfig
        from thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
    except ImportError as e:
        print(f"❌ Failed to import bot modules: {e}")
        print("   Make sure you're in the project root and dependencies are installed")
        sys.exit(1)

    # Загрузка конфигурации
    config = TelegramBotConfig.from_env()

    # Валидация конфигурации
    errors = config.validate()
    if errors:
        print("❌ Configuration errors:")
        for error in errors:
            print(f"   - {error}")

        # Проверяем наличие обязательных переменных
        if not config.bot_token:
            print("\n💡 To fix bot_token error:")
            print("   1. Create a bot with @BotFather")
            print("   2. Copy the token to .env.dev or environment variables")
            print("   3. Set TELEGRAM_BOT_TOKEN=your_token_here")

        if not os.getenv("OPENROUTER_API_KEY"):
            print("\n💡 To fix LLM API key error:")
            print("   1. Get API key from https://openrouter.ai/")
            print("   2. Set OPENROUTER_API_KEY=your_key_here")

        return

    # Проверка файлов базы данных
    db_path = Path(config.db_path)
    if not db_path.exists():
        print(f"⚠️ Database not found: {db_path}")
        print("   Using development database or downloading required...")

        # Создание development базы данных если нужно
        if "dev" in config.db_path and not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created database directory: {db_path.parent}")

    # Вывод информации о конфигурации
    print(f"\n🤖 Starting ThermoCalcBot in development mode...")
    print(f"   Username: @{config.bot_username}")
    print(f"   Mode: {config.mode}")
    print(f"   Max users: {config.max_concurrent_users}")
    print(f"   Log level: {config.log_level}")
    print(f"   Database: {config.db_path}")
    print(f"   File threshold: {config.auto_file_threshold} chars")

    if config.is_development():
        print("   🐛 Debug features enabled")

    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('logs/telegram_errors/dev_bot.log', encoding='utf-8')
        ]
    )

    logger = logging.getLogger(__name__)

    # Создание и запуск бота
    try:
        bot = ThermoSystemTelegramBot(config)
        logger.info("Bot instance created successfully")

        await bot.start()

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        logger.info("Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
        logger.error(f"Bot error: {e}", exc_info=True)
    finally:
        print("🧹 Cleaning up...")
        try:
            await bot.shutdown()
            print("✅ Bot shutdown complete")
        except Exception as e:
            print(f"⚠️ Shutdown error: {e}")
            logger.error(f"Shutdown error: {e}")

def main() -> None:
    """Основная функция"""

    print("🚀 ThermoCalcBot Development Runner")
    print("=" * 40)

    # Проверка версии Python
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        sys.exit(1)

    try:
        asyncio.run(run_dev_bot())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()