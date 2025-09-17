"""
AI Agents Project - Главный модуль с интерактивным режимом
"""

import asyncio

from src.thermo_agents.main_thermo_agent import (
    ThermoAgentConfig,
    process_thermodynamic_query,
)
from src.thermo_agents.thermo_agents_logger import create_session_logger


def main():
    """Основная функция приложения с интерактивным режимом."""
    print("🤖 Thermo Agents - Интерактивный режим")
    print("Введите ваш запрос или 'exit' для выхода.")
    print()

    # Инициализация конфигурации агента
    config = ThermoAgentConfig()
    config.logger.info("Инициализация агента завершена")

    # Создание логгера сессии
    session_logger = create_session_logger()
    config.session_logger = session_logger
    session_logger.log_info("Сессия начата")

    try:
        while True:
            user_input = input("Ваш запрос: ").strip()

            if user_input.lower() in ["exit", "quit", "q"]:
                print("Завершение сессии...")
                session_logger.log_info("Пользователь завершил сессию")
                break

            if not user_input:
                continue

            # Обработка запроса
            try:
                result = asyncio.run(process_thermodynamic_query(user_input, config))

                # Вывод результата
                print("\n✅ Параметры извлечены:")
                print(f"🎯 Intent: {result.intent}")
                print(f"🧪 Соединения: {result.compounds}")
                print(f"🌡️ Температура: {result.temperature_k} K")
                print(f"📊 Диапазон: {result.temperature_range_k}")
                print(f"🔬 Фазы: {result.phases}")
                print(f"📋 Свойства: {result.properties}")
                print(f"💡 SQL подсказка: {result.sql_query_hint}")
                print()

            except Exception as e:
                print(f"❌ Ошибка обработки запроса: {e}")
                session_logger.log_error(str(e))
                print()

    except KeyboardInterrupt:
        print("\nПрерывание пользователем...")
        session_logger.log_info("Сессия прервана пользователем")

    finally:
        # Закрытие сессии
        session_logger.close()
        print("Сессия завершена. Лог сохранён.")


if __name__ == "__main__":
    main()
