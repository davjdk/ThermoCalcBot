"""
AI Agents Project - Главный модуль с интерактивным режимом
"""

import asyncio
import logging

from src.thermo_agents.main_thermo_agent import (
    ThermoAgentConfig,
    process_thermodynamic_query_with_sql,
)
from src.thermo_agents.sql_agent import execute_sql_query_direct
from src.thermo_agents.thermo_agents_logger import create_session_logger


def main():
    """Основная функция приложения с интерактивным режимом."""
    print("🤖 Thermo Agents - Интерактивный режим")
    print("Введите ваш запрос или 'exit' для выхода.")
    print()

    # Инициализация конфигурации агента
    config = ThermoAgentConfig()
    config.log_level = "DEBUG"  # Включаем DEBUG логи для отладки
    config.logger.setLevel(
        logging.DEBUG
    )  # Устанавливаем уровень для существующего логгера

    # Создание логгера сессии
    session_logger = create_session_logger()
    config.session_logger = session_logger
    # Также обновляем session_logger в sql_agent_config
    if config.sql_agent_config:
        config.sql_agent_config.session_logger = session_logger
        config.sql_agent_config.log_level = (
            "DEBUG"  # Включаем DEBUG логи для SQL агента
        )
        config.sql_agent_config.logger.setLevel(
            logging.DEBUG
        )  # Устанавливаем уровень для логгера SQL агента
    session_logger.log_info("Сессия начата")

    # Инициализация агентов
    # thermo_agent = initialize_thermo_agent(config)  # Не нужен, используем функции напрямую
    config.logger.info("Агенты инициализированы")

    try:
        while True:
            user_input = input("Ваш запрос: ").strip()

            if user_input.lower() in ["exit", "quit", "q"]:
                print("Завершение сессии...")
                session_logger.log_info("Пользователь завершил сессию")
                break

            if not user_input:
                continue

            # Обработка запроса с использованием A2A
            try:
                # Используем полную обработку
                session_logger.log_processing_start(user_input)
                result = asyncio.run(
                    process_thermodynamic_query_with_sql(user_input, config)
                )

                # Логирование извлеченных параметров
                session_logger.log_extracted_parameters(result.extracted_params)

                # Вывод извлеченных параметров
                print("\n✅ Параметры извлечены:")
                print(f"🎯 Intent: {result.extracted_params.intent}")
                print(f"🧪 Соединения: {result.extracted_params.compounds}")
                print(f"🌡️ Температура: {result.extracted_params.temperature_k} K")
                print(f"📊 Диапазон: {result.extracted_params.temperature_range_k}")
                print(f"🔬 Фазы: {result.extracted_params.phases}")
                print(f"📋 Свойства: {result.extracted_params.properties}")
                print(f"💡 SQL подсказка: {result.extracted_params.sql_query_hint}")
                print()

                # Вывод SQL
                print("✅ SQL запрос сгенерирован:")
                print(f"📝 SQL: {result.sql_query}")
                print(f"📋 Ожидаемые колонки: {result.expected_columns}")
                print(f"💡 Объяснение: {result.explanation}")
                print()

                # Логирование SQL генерации
                session_logger.log_sql_generation(
                    result.sql_query,
                    result.expected_columns,
                    result.explanation,
                )

                # Выполняем SQL запрос и выводим результаты
                print("🔍 Выполнение SQL запроса...")
                try:
                    asyncio.run(
                        execute_sql_query_direct(
                            result.sql_query, config.sql_agent_config
                        )
                    )
                    print("✅ Запрос выполнен успешно!")
                except Exception as e:
                    print(f"❌ Ошибка выполнения SQL запроса: {e}")
                    session_logger.log_error(f"SQL execution error: {str(e)}")
                    print()

                session_logger.log_processing_end()

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

if __name__ == "__main__":
    main()
