"""
AI Agents Project - Главный модуль с интерактивным режимом
"""

import asyncio

from src.thermo_agents.main_thermo_agent import (
    ThermoAgentConfig,
    initialize_thermo_agent,
)
from src.thermo_agents.sql_agent import execute_sql_query_direct, generate_sql_query
from src.thermo_agents.thermo_agents_logger import create_session_logger


def main():
    """Основная функция приложения с интерактивным режимом."""
    print("🤖 Thermo Agents - Интерактивный режим")
    print("Введите ваш запрос или 'exit' для выхода.")
    print()

    # Инициализация конфигурации агента
    config = ThermoAgentConfig()

    # Создание логгера сессии
    session_logger = create_session_logger()
    config.session_logger = session_logger
    # Также обновляем session_logger в sql_agent_config
    if config.sql_agent_config:
        config.sql_agent_config.session_logger = session_logger
    session_logger.log_info("Сессия начата")

    # Инициализация агентов
    thermo_agent = initialize_thermo_agent(config)
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
                    != "Запрос необходимо дополнительно конкретизировать для извлечения параметров"
                ):
                    print("🔄 Вызов SQL агента через A2A...")
                    try:
                        # Используем generate_sql_query напрямую для большей надежности
                        sql_output, _ = asyncio.run(
                            generate_sql_query(
                                extracted.sql_query_hint,
                                dependencies=config.sql_agent_config,
                                execute_query=False,  # Не выполняем автоматически, сделаем это ниже
                            )
                        )

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

                        # Выполняем SQL запрос и выводим результаты
                        print("🔍 Выполнение SQL запроса...")
                        try:
                            asyncio.run(
                                execute_sql_query_direct(
                                    sql_output.sql_query, config.sql_agent_config
                                )
                            )
                            print("✅ Запрос выполнен успешно!")
                        except Exception as e:
                            print(f"❌ Ошибка выполнения SQL запроса: {e}")
                            session_logger.log_error(f"SQL execution error: {str(e)}")
                            print()
                    except Exception as e:
                        print(f"❌ Ошибка генерации SQL: {e}")
                        session_logger.log_error(str(e))
                        print("ℹ️ Продолжение без SQL генерации")
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
