"""
Базовый пример использования термодинамической системы v2.0.

Демонстрирует простое использование оркестратора для анализа
химических реакций и получения термодинамических данных.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline, FilterContext
from thermo_agents.filtering.filter_stages import (
    ComplexFormulaSearchStage,
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter
from thermo_agents.orchestrator import ThermoOrchestrator, OrchestratorConfig
from thermo_agents.agent_storage import AgentStorage


async def create_orchestrator(db_path: str = "data/thermo_data.db"):
    """Создает и настраивает оркестратор."""

    # Инициализация хранилища
    storage = AgentStorage()

    # Термодинамический агент (LLM)
    thermo_config = ThermoAgentConfig(
        agent_id="demo_thermo_agent",
        llm_api_key="your_api_key_here",  # Замените на реальный ключ
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="openai/gpt-4o-mini",
        storage=storage,
        session_logger=None,
    )
    thermo_agent = ThermodynamicAgent(thermo_config)

    # Детерминированные компоненты поиска
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(db_path)
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    # Конвейер фильтрации
    filter_pipeline = FilterPipeline()
    filter_pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    filter_pipeline.add_stage(TemperatureFilterStage())

    # Резолверы
    temperature_resolver = TemperatureResolver()
    phase_resolver = PhaseResolver()

    filter_pipeline.add_stage(PhaseSelectionStage(phase_resolver))
    filter_pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
    filter_pipeline.add_stage(TemperatureCoverageStage(temperature_resolver))

    # Компоненты агрегации
    reaction_aggregator = ReactionAggregator(max_compounds=10)
    table_formatter = TableFormatter()
    statistics_formatter = StatisticsFormatter()

    # Оркестратор v2.0
    config = OrchestratorConfig(storage=storage)
    orchestrator = ThermoOrchestrator(
        thermodynamic_agent=thermo_agent,
        compound_searcher=compound_searcher,
        filter_pipeline=filter_pipeline,
        reaction_aggregator=reaction_aggregator,
        table_formatter=table_formatter,
        statistics_formatter=statistics_formatter,
        config=config
    )

    return orchestrator


async def demo_simple_search(orchestrator):
    """Демонстрация простого поиска соединения."""
    print("=" * 60)
    print("🔬 Демонстрация 1: Простой поиск соединения")
    print("=" * 60)

    query = "Термодинамические данные для воды при 298K"
    print(f"Запрос: {query}")
    print("-" * 40)

    try:
        response = await orchestrator.process_query(query)
        print(response)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        print("💡 Убедитесь, что OPENROUTER_API_KEY указан в .env файле")

    print()


async def demo_simple_reaction(orchestrator):
    """Демонстрация простой реакции."""
    print("=" * 60)
    print("⚗️ Демонстрация 2: Простая химическая реакция")
    print("=" * 60)

    query = "Горение водорода: 2H2 + O2 -> 2H2O при 500-800K"
    print(f"Запрос: {query}")
    print("-" * 40)

    try:
        response = await orchestrator.process_query(query)
        print(response)
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    print()


async def demo_complex_reaction(orchestrator):
    """Демонстрация сложной реакции с фазовыми переходами."""
    print("=" * 60)
    print("🌡️ Демонстрация 3: Реакция с фазовыми переходами")
    print("=" * 60)

    query = "Свойства воды при 250-400K (твёрдое→жидкое→газ)"
    print(f"Запрос: {query}")
    print("-" * 40)

    try:
        response = await orchestrator.process_query(query)
        print(response)
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    print()


async def demo_complex_compounds(orchestrator):
    """Демонстрация работы со сложными соединениями."""
    print("=" * 60)
    print("🧪 Демонстрация 4: Сложные химические соединения")
    print("=" * 60)

    query = "Хлорирование оксида титана: TiO2 + 2Cl2 -> TiCl4 + O2 при 600-900K"
    print(f"Запрос: {query}")
    print("-" * 40)

    try:
        response = await orchestrator.process_query(query)
        print(response)
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    print()


async def demo_temperature_ranges(orchestrator):
    """Демонстрация различных температурных диапазонов."""
    print("=" * 60)
    print("🌡️ Демонстрация 5: Различные температурные диапазоны")
    print("=" * 60)

    queries = [
        "Железо при комнатной температуре (298K)",
        "Железо при высоких температурах (1000-1500K)",
        "Железо при экстремальных температурах (2000-3000K)"
    ]

    for i, query in enumerate(queries, 1):
        print(f"Запрос {i}: {query}")
        print("-" * 40)

        try:
            response = await orchestrator.process_query(query)
            # Показываем только первые строки для экономии места
            lines = response.split('\n')[:15]
            print('\n'.join(lines))
            if len(response.split('\n')) > 15:
                print("... (результат сокращен)")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

        print()


async def demo_performance_test(orchestrator):
    """Демонстрация производительности с множественными запросами."""
    print("=" * 60)
    print("⚡ Демонстрация 6: Тест производительности")
    print("=" * 60)

    import time

    compounds = ["H2O", "CO2", "NH3", "CH4", "N2", "O2"]

    print(f"Обработка {len(compounds)} соединений...")
    start_time = time.time()

    for compound in compounds:
        query = f"Свойства {compound} при 298-500K"
        try:
            response = await orchestrator.process_query(query)
            # Извлекаем только ключевую информацию для теста
            if "✅" in response or "⚠️" in response:
                status = "✅ Найдено"
            else:
                status = "❌ Не найдено"
            print(f"  {compound}: {status}")
        except Exception as e:
            print(f"  {compound}: ❌ Ошибка - {e}")

    end_time = time.time()
    total_time = end_time - start_time

    print(f"\n⏱️ Время выполнения: {total_time:.2f} секунд")
    print(f"📊 Среднее время на соединение: {total_time/len(compounds):.2f} секунд")
    print()


async def main():
    """Главная функция демонстрации."""
    print("🚀 Термодинамическая система v2.0 - Базовая демонстрация")
    print("=" * 60)
    print("Гибридная архитектура: LLM + детерминированная логика")
    print()

    # Проверка наличия API ключа
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key or api_key == "your_api_key_here":
        print("⚠️ Внимание: OPENROUTER_API_KEY не найден в .env файле")
        print("Пожалуйста, добавьте ваш API ключ в файл .env:")
        print("OPENROUTER_API_KEY=your_actual_api_key_here")
        print()
        print("Продолжаем демонстрацию с детерминированными компонентами...")
        print()

    try:
        # Создаем оркестратор
        orchestrator = await create_orchestrator()

        # Запускаем демонстрации
        await demo_simple_search(orchestrator)
        await demo_simple_reaction(orchestrator)
        await demo_complex_reaction(orchestrator)
        await demo_complex_compounds(orchestrator)
        await demo_temperature_ranges(orchestrator)
        await demo_performance_test(orchestrator)

        # Завершаем работу
        await orchestrator.shutdown()

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        print("💡 Убедитесь, что:")
        print("   1. База данных доступна (data/thermo_data.db)")
        print("   2. Установлены все зависимости (uv sync)")
        print("   3. OPENROUTER_API_KEY указан в .env файле")

    print("\n" + "=" * 60)
    print("✅ Демонстрация завершена")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())