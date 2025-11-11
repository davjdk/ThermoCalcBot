"""
Основной скрипт для запуска Telegram бота ThermoSystem.

Использование:
    python telegram_bot.py

Переменные окружения в .env:
    TELEGRAM_BOT_TOKEN - токен Telegram бота
    OPENROUTER_API_KEY - API ключ для LLM
    DB_PATH - путь к базе данных ThermoSystem
"""

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Добавление пути к исходникам
sys.path.insert(0, str(Path(__file__).parent / "src"))

from thermo_agents.telegram import TelegramBotConfig, ThermoSystemTelegramBot


async def main():
    """Основная функция запуска бота."""
    try:
        # Загрузка конфигурации
        print("🔧 Загрузка конфигурации...")
        config = TelegramBotConfig.from_env()

        # Валидация конфигурации
        errors = config.validate_config()
        if errors:
            print(f"❌ Ошибки конфигурации:")
            for error in errors:
                print(f"  • {error}")
            print("\nПроверьте переменные окружения в файле .env")
            return 1

        print(f"✅ Конфигурация загружена:")
        print(f"  • База данных: {config.thermo_db_path}")
        print(f"  • LLM модель: {config.llm_model}")
        print(f"  • Макс. пользователей: {config.limits.max_concurrent_users}")
        print(f"  • Директория временных файлов: {config.file_config.temp_file_dir}")

        # Создание и запуск бота
        print("\n🚀 Запуск ThermoSystem Telegram Bot...")
        bot = ThermoSystemTelegramBot(config)

        # Запуск бота (будет работать до получения сигнала остановки)
        await bot.start()

        return 0

    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
        return 0
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        logging.exception("Критическая ошибка при запуске бота")
        return 1


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("logs/telegram_bot.log", encoding="utf-8"),
        ],
    )

    # Создание директории для логов
    Path("logs").mkdir(exist_ok=True)

    # Запуск
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
