"""
Тесты для main_thermo_agent.py
"""

import asyncio
import logging

from thermo_agents.main_thermo_agent import (
    ThermoAgentConfig,
    process_thermodynamic_query_with_sql,
)


async def main():
    """Точка входа для тестирования агента."""
    logging.basicConfig(level=logging.INFO)

    # Создаем зависимости для проверки настроек
    thermo_agent_config = ThermoAgentConfig()

    print("🚀 Запуск агента извлечения параметров")
    print(f"📋 Модель LLM: {thermo_agent_config.llm_model}")
    print(f"🔗 Базовый URL: {thermo_agent_config.llm_base_url}")
    print(f"🗄️ Путь к БД: {thermo_agent_config.db_path}")
    print(f"📊 Уровень логирования: {thermo_agent_config.log_level}")
    print(f"🐛 Debug режим: {thermo_agent_config.debug}")
    print()

    # Пример запроса
    test_query = (
        "При какой температуре идет взаимодействие карбида вольфрама с магнием?"
    )

    print(f"Запрос: {test_query}")
    print()

    # Тестируем полную обработку с SQL генерацией
    print("🔍 Выполняем полную обработку с генерацией SQL...")
    result = await process_thermodynamic_query_with_sql(test_query, thermo_agent_config)

    print("✅ Обработка завершена:")
    print()
    print("📋 Извлеченные параметры:")
    print(f"🎯 Intent: {result.extracted_params.intent}")
    print(f"🧪 Соединения: {result.extracted_params.compounds}")
    print(f"🌡️ Температура: {result.extracted_params.temperature_k} K")
    print(f"📊 Диапазон: {result.extracted_params.temperature_range_k}")
    print(f"🔬 Фазы: {result.extracted_params.phases}")
    print(f"📋 Свойства: {result.extracted_params.properties}")
    print(f"💡 SQL подсказка: {result.extracted_params.sql_query_hint}")
    print()
    print("💾 Сгенерированный SQL:")
    print(f"📝 SQL: {result.sql_query}")
    print(f"📊 Ожидаемые колонки: {result.expected_columns}")
    print(f"💡 Объяснение: {result.extracted_params.sql_query_hint}")


if __name__ == "__main__":
    asyncio.run(main())
