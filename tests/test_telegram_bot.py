"""
Тестовый скрипт для проверки работы Telegram бота ThermoSystem.

Использование:
    python test_telegram_bot.py

Этот скрипт проверяет:
1. Конфигурацию бота
2. Инициализацию компонентов
3. Базовую функциональность обработки запросов
"""

import asyncio
import logging
import sys
from pathlib import Path
import pytest

# Добавление пути к исходникам
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.telegram import ThermoSystemTelegramBot, TelegramBotConfig


@pytest.mark.asyncio
async def test_config():
    """Тест конфигурации."""
    print("🔧 Тест конфигурации...")

    try:
        config = TelegramBotConfig.from_env()
        print(f"✅ Конфигурация загружена")

        # Валидация
        errors = config.validate_config()
        if errors:
            print(f"❌ Ошибки конфигурации:")
            for error in errors:
                print(f"  • {error}")
            return False
        else:
            print(f"✅ Конфигурация валидна")
            return True

    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False


@pytest.mark.asyncio
async def test_bot_initialization():
    """Тест инициализации бота."""
    print("\n🤖 Тест инициализации бота...")

    try:
        config = TelegramBotConfig.from_env()
        bot = ThermoSystemTelegramBot(config)

        # Инициализация
        await bot.initialize()
        print(f"✅ Бот успешно инициализирован")

        # Информация о боте
        bot_info = bot.get_bot_info()
        print(f"📊 Информация о боте:")
        print(f"  • Username: {bot_info['bot_username']}")
        print(f"  • Mode: {bot_info['mode']}")
        print(f"  • Max users: {bot_info['max_concurrent_users']}")
        print(f"  • Rate limit: {bot_info['rate_limit_per_minute']}/min")

        # Остановка
        await bot.stop()
        print(f"✅ Бот успешно остановлен")

        return True

    except Exception as e:
        print(f"❌ Ошибка инициализации бота: {e}")
        import traceback
        traceback.print_exc()
        return False


@pytest.mark.asyncio
async def test_sample_query():
    """Тест обработки примера запроса."""
    print("\n🧪 Тест обработки запроса...")

    try:
        config = TelegramBotConfig.from_env()
        bot = ThermoSystemTelegramBot(config)

        await bot.initialize()

        # Проверка адаптера
        if not bot.thermo_adapter:
            print("❌ ThermoAdapter не инициализирован")
            return False

        # Тестовый запрос
        test_query = "H2O свойства при 300-400K"
        print(f"📝 Тестовый запрос: {test_query}")

        response, needs_file = await bot.thermo_adapter.process_query(test_query, 12345)

        if isinstance(response, str):
            print(f"✅ Ответ получен (длина: {len(response)} символов)")
            # Выводим начало ответа
            print(f"📄 Начало ответа:\n{response[:200]}...")

        elif hasattr(response, 'text'):
            print(f"✅ BotResponse получен (длина: {len(response.text)} символов)")
            print(f"📄 Начало ответа:\n{response.text[:200]}...")

        else:
            print(f"✅ Ответ получен типа: {type(response)}")

        await bot.stop()
        return True

    except Exception as e:
        print(f"❌ Ошибка обработки запроса: {e}")
        import traceback
        traceback.print_exc()
        return False


@pytest.mark.asyncio
async def test_session_management():
    """Тест управления сессиями."""
    print("\n👥 Тест управления сессиями...")

    try:
        config = TelegramBotConfig.from_env()
        bot = ThermoSystemTelegramBot(config)

        await bot.initialize()

        # Проверка session manager
        if not bot.session_manager:
            print("❌ SessionManager не инициализирован")
            return False

        # Получение статистики
        stats = bot.session_manager.get_system_stats()
        print(f"📊 Статистика системы:")
        print(f"  • Всего сессий: {stats['total_sessions']}")
        print(f"  • Активных сессий: {stats['active_sessions']}")
        print(f"  • Память: {stats['memory_usage_mb']:.1f} MB")

        await bot.stop()
        return True

    except Exception as e:
        print(f"❌ Ошибка управления сессиями: {e}")
        return False


async def main():
    """Основная функция тестирования."""
    print("🚀 Запуск тестов ThermoSystem Telegram Bot\n")

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    tests = [
        ("Конфигурация", test_config),
        ("Инициализация бота", test_bot_initialization),
        ("Управление сессиями", test_session_management),
        ("Обработка запросов", test_sample_query),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        try:
            if await test_func():
                passed += 1
                print(f"✅ Тест '{test_name}' пройден")
            else:
                print(f"❌ Тест '{test_name}' провален")
        except Exception as e:
            print(f"💥 Тест '{test_name}' завершился с ошибкой: {e}")

    print(f"\n{'='*60}")
    print(f"📊 Результаты тестов: {passed}/{total} пройдено")

    if passed == total:
        print("🎉 Все тесты успешно пройдены!")
        return 0
    else:
        print("⚠️ Некоторые тесты не пройдены")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)