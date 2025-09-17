"""
AI Agents Project - Главный модуль с интерактивным режимом
"""

import asyncio

from src.thermo_agents.main_thermo_agent import (
    ThermoAgentConfig,
    initialize_thermo_agent,
)
from src.thermo_agents.sql_agent import initialize_sql_agent
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

    # Инициализация агентов
    thermo_agent = initialize_thermo_agent(config)
    sql_agent = initialize_sql_agent(config.sql_agent_config)
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
                # Шаг 1: Thermo агент извлекает параметры
                session_logger.log_processing_start(user_input)
                thermo_result = asyncio.run(thermo_agent.run(user_input, deps=config))
                extracted = thermo_result.output

                # Логирование извлеченных параметров
                session_logger.log_extracted_parameters(extracted)

                # Вывод извлеченных параметров
                print("\n✅ Параметры извлечены:")
                print(f"🎯 Intent: {extracted.intent}")
                print(f"🧪 Соединения: {extracted.compounds}")
                print(f"🌡️ Температура: {extracted.temperature_k} K")
                print(f"📊 Диапазон: {extracted.temperature_range_k}")
                print(f"🔬 Фазы: {extracted.phases}")
                print(f"📋 Свойства: {extracted.properties}")
                print(f"💡 SQL подсказка: {extracted.sql_query_hint}")
                print()

                # Шаг 2: Если есть SQL подсказка, Thermo агент вызывает SQL агент через A2A
                if (
                    extracted.sql_query_hint
                    and extracted.sql_query_hint
                    != "Error occurred during parameter extraction"
                ):
                    print("🔄 Вызов SQL агента через A2A...")
                    sql_result = asyncio.run(
                        sql_agent.run(
                            extracted.sql_query_hint,
                            deps=config.sql_agent_config,
                        )
                    )
                    sql_output = sql_result.output

                    # Логирование SQL генерации
                    session_logger.log_sql_generation(
                        sql_output.sql_query,
                        sql_output.expected_columns,
                        sql_output.explanation,
                    )

                    print("✅ SQL запрос сгенерирован:")
                    print(f"📝 SQL: {sql_output.sql_query}")
                    print(f"📋 Ожидаемые колонки: {sql_output.expected_columns}")
                    print(f"💡 Объяснение: {sql_output.explanation}")
                    print()
                else:
                    print("ℹ️ SQL генерация не требуется")
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
