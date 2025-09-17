"""
Тесты для sql_agent.py
"""

import asyncio
import logging

from thermo_agents.sql_agent import SQLAgentConfig, generate_sql_query


async def main():
    """Точка входа для тестирования SQL агента."""
    logging.basicConfig(level=logging.INFO)

    # Создаем базовые зависимости для тестирования
    sql_agent_config = SQLAgentConfig(
        llm_api_key="",  # В реальном использовании брать из .env
        llm_base_url="",
        llm_model="openai:gpt-4o",
        db_path="data/thermo_data.db",
        log_level="INFO",
        debug=False,
        logger=logging.getLogger(__name__),
    )

    print("🚀 Запуск SQL агента")
    print(f"📋 Модель LLM: {sql_agent_config.llm_model}")
    print(f"🗄️ Путь к БД: {sql_agent_config.db_path}")
    print()

    # Пример подсказки для генерации SQL
    test_hint = (
        "Find thermodynamic data for TiO2(s), Cl2(g), TiCl4(g), and O2(g) "
        "in temperature range 573-873K. Include H298, S298, and heat capacity "
        "coefficients f1-f6 for reaction analysis."
    )

    print(f"Подсказка: {test_hint}")
    print()

    # Генерируем и выполняем SQL запрос
    sql_result, db_result = await generate_sql_query(
        test_hint, sql_agent_config, execute_query=True
    )

    print("✅ SQL запрос сгенерирован:")
    print(f"📝 SQL: {sql_result.sql_query}")
    print(f"📋 Ожидаемые колонки: {sql_result.expected_columns}")
    print(f"💡 Объяснение: {sql_result.explanation}")
    print()

    if db_result:
        print("📊 Результаты выполнения запроса:")
        print(f"📋 Найдено записей: {db_result.row_count}")
        print(f"📊 Колонки: {', '.join(db_result.columns)}")
        print("\n" + db_result.formatted_table)
    else:
        print("❌ Запрос не был выполнен")


if __name__ == "__main__":
    asyncio.run(main())
