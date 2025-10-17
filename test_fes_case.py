"""Тестирование случая с FeS для проверки отбора фаз по температуре плавления."""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Импортируем create_orchestrator из main
from main import create_orchestrator


async def main():
    """Тестовый запуск для случая CaO + FeS."""

    orchestrator = create_orchestrator()

    # Запрос из логов
    query = "Возможно ли взаимодействие оксида кальция и сульфида железа при 600 - 1200 цельсия?"

    print("=" * 80)
    print("ТЕСТ: Проверка отбора фаз для FeS")
    print("=" * 80)
    print(f"Запрос: {query}")
    print("=" * 80)
    print()

    try:
        result = await orchestrator.process_query(query)
        print(result)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import asyncio
import sys
from pathlib import Path

# Импортируем create_orchestrator из main
from main import create_orchestrator

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.filtering.complex_search_stage import ComplexFormulaSearchStage
from thermo_agents.filtering.filter_stages import (
    ReliabilityPriorityStage,
    TemperatureCoverageStage,
)
from thermo_agents.filtering.phase_based_temperature_stage import (
    PhaseBasedTemperatureStage,
)
from thermo_agents.filtering.reaction_validation_stage import ReactionValidationStage
from thermo_agents.orchestrator import OrchestratorConfig, ThermoOrchestrator
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.thermo_agents_logger import create_session_logger
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent

# Загрузка переменных окружения
load_dotenv()


def create_orchestrator(db_path: str = "data/thermo_data.db") -> ThermoOrchestrator:
    """Создание оркестратора с полным пайплайном фильтрации."""

    # 1. База данных
    connector = DatabaseConnector(db_path=db_path)
    sql_builder = SQLBuilder()
    searcher = CompoundSearcher(db_connector=connector, sql_builder=sql_builder)

    # 2. Агент термодинамики с LLM
    agent_config = ThermoAgentConfig(temperature=0.7, max_tokens=2000)

    thermo_agent = ThermodynamicAgent(config=agent_config)

    # 3. Конвейер фильтрации
    filter_stages = [
        ReactionValidationStage(confidence_threshold=0.5, enable_name_validation=True),
        ComplexFormulaSearchStage(),
        PhaseBasedTemperatureStage(exclude_ions=True, max_records_per_phase=1),
        ReliabilityPriorityStage(max_records=3),
        TemperatureCoverageStage(min_coverage_percent=0.0),
    ]

    # 4. Агрегация и форматирование
    aggregator = ReactionAggregator(max_compounds=10)
    table_formatter = TableFormatter()
    stats_formatter = StatisticsFormatter()

    # 5. Логгер
    logger = create_session_logger()

    # 6. Оркестратор
    orchestrator_config = OrchestratorConfig(
        max_compounds=10, temperature_range=(273.15, 6000.0)
    )

    orchestrator = ThermoOrchestrator(
        config=orchestrator_config,
        thermo_agent=thermo_agent,
        compound_searcher=searcher,
        filter_stages=filter_stages,
        aggregator=aggregator,
        table_formatter=table_formatter,
        statistics_formatter=stats_formatter,
        logger=logger,
    )

    return orchestrator


async def main():
    """Тестовый запуск для случая CaO + FeS."""

    orchestrator = create_orchestrator()

    # Запрос из логов
    query = "Возможно ли взаимодействие оксида кальция и сульфида железа при 600 - 1200 цельсия?"

    print("=" * 80)
    print("ТЕСТ: Проверка отбора фаз для FeS")
    print("=" * 80)
    print(f"Запрос: {query}")
    print("=" * 80)
    print()

    try:
        result = await orchestrator.process_query(query)
        print(result)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
