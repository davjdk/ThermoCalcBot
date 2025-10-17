"""Главный файл запуска термодинамической системы."""

import asyncio
import os
import sys
from pathlib import Path

# Устанавливаем кодировку для Windows
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dotenv import load_dotenv

from thermo_agents.agent_storage import AgentStorage
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter
from thermo_agents.aggregation.table_formatter import TableFormatter
from thermo_agents.filtering.complex_search_stage import ComplexFormulaSearchStage
from thermo_agents.filtering.filter_stages import (
    ReliabilityPriorityStage,
    TemperatureCoverageStage,
)
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.orchestrator import OrchestratorConfig, ThermoOrchestrator
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.thermo_agents_logger import create_session_logger
from thermo_agents.thermodynamic_agent import ThermoAgentConfig, ThermodynamicAgent

# Загрузка переменных окружения
load_dotenv()


def create_orchestrator(db_path: str = "data/thermo_data.db") -> ThermoOrchestrator:
    """
    Создание и настройка оркестратора термодинамической системы.

    Args:
        db_path: Путь к файлу базы данных

    Returns:
        Настроенный ThermoOrchestrator
    """
    # Инициализация хранилища
    storage = AgentStorage()

    # Единый session_logger для всей системы
    session_logger = create_session_logger()

    # LLM для извлечения параметров
    thermo_config = ThermoAgentConfig(
        agent_id="thermo_agent",
        llm_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("LLM_DEFAULT_MODEL", "openai/gpt-4o"),
        storage=storage,
        session_logger=session_logger,  # НОВОЕ: используем тот же logger
    )
    thermodynamic_agent = ThermodynamicAgent(thermo_config)

    # Поиск в БД
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(db_path)
    compound_searcher = CompoundSearcher(
        sql_builder, db_connector, session_logger=session_logger
    )  # НОВОЕ

    # Конвейер фильтрации с валидацией реакции (Stage 0)
    from thermo_agents.filtering.filter_pipeline import FilterPipelineBuilder

    filter_pipeline = (
        FilterPipelineBuilder(session_logger=session_logger)
        .with_reaction_validation(min_confidence_threshold=0.5)
        .build()
    )

    # Добавляем остальные стадии напрямую
    filter_pipeline.add_stage(ComplexFormulaSearchStage())
    # Заменяем TemperatureFilterStage на умную фазовую фильтрацию
    from thermo_agents.filtering.phase_based_temperature_stage import (
        PhaseBasedTemperatureStage,
    )

    filter_pipeline.add_stage(
        PhaseBasedTemperatureStage(
            exclude_ions=True,
            max_records_per_phase=1,
            reliability_weight=0.6,
            coverage_weight=0.4,
        )
    )
    # Старая фазовая селекция больше не нужна - логика встроена в PhaseBasedTemperatureStage
    # filter_pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    filter_pipeline.add_stage(
        ReliabilityPriorityStage(max_records=3)
    )  # Увеличиваем до 3 для множественных фаз
    filter_pipeline.add_stage(TemperatureCoverageStage(TemperatureResolver()))

    # Агрегация и форматирование
    reaction_aggregator = ReactionAggregator(max_compounds=10)
    table_formatter = TableFormatter()
    statistics_formatter = StatisticsFormatter()

    # Оркестратор
    orchestrator_config = OrchestratorConfig(storage=storage)
    orchestrator = ThermoOrchestrator(
        thermodynamic_agent=thermodynamic_agent,
        compound_searcher=compound_searcher,
        filter_pipeline=filter_pipeline,
        reaction_aggregator=reaction_aggregator,
        table_formatter=table_formatter,
        statistics_formatter=statistics_formatter,
        config=orchestrator_config,
    )

    return orchestrator


async def main_interactive():
    """Главная функция в режиме ожидания запросов пользователя."""
    # Инициализация
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator = create_orchestrator(str(db_path))

    print("\nТермодинамическая система v2.0")
    print("Гибридная архитектура: LLM + детерминированная логика\n")

    try:
        while True:
            # Ожидание запроса
            query = input("Введите запрос: ").strip()

            if not query:
                continue

            print()

            try:
                # Обработка запроса
                response = await orchestrator.process_query(query)

                # НОВОЕ: Логирование ответа в сессию
                session_logger = orchestrator.thermodynamic_agent.config.session_logger
                if session_logger:
                    session_logger.log_info("")
                    session_logger.log_info("=" * 60)
                    session_logger.log_info("РЕЗУЛЬТАТ:")
                    # Логируем response как есть, с эмодзи и таблицами
                    for line in response.split("\n"):
                        if line.strip():  # Пропускаем пустые строки
                            session_logger.log_info(line)
                    session_logger.log_info("=" * 60)

                print(response)
                print()
            except Exception as e:
                print(f"Ошибка обработки: {e}\n")

                # НОВОЕ: Логирование ошибки в сессию
                session_logger = orchestrator.thermodynamic_agent.config.session_logger
                if session_logger:
                    session_logger.log_error(f"Ошибка обработки: {e}")

    except KeyboardInterrupt:
        print("\n\nЗавершение работы...")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
    finally:
        await orchestrator.shutdown()


async def main_test():
    """Тестовый режим с предопределённым запросом."""
    # Инициализация
    db_path = Path(__file__).parent / "data" / "thermo_data.db"
    orchestrator = create_orchestrator(str(db_path))

    # Получаем session_logger из orchestrator для логирования начала сессии
    session_logger = orchestrator.thermodynamic_agent.config.session_logger
    if session_logger:
        session_logger.log_info("SESSION STARTED")
        session_logger.log_info("Термодинамическая система v2.0")

    print("\n" + "=" * 80)
    print("Термодинамическая система v2.0 - ТЕСТОВЫЙ РЕЖИМ")
    print("=" * 80)

    # Тестовый запрос
    test_query = "Возможно ли взаимодействие оксида бария с хлоридом аммония при 100 - 300 цельсия?"

    # НОВОЕ: Логирование запроса пользователя
    if session_logger:
        session_logger.log_info(f"Запрос пользователя: {test_query}")

    try:
        # Обработка запроса
        response = await orchestrator.process_query(test_query)

        # НОВОЕ: Логирование summary ответа в сессию
        if session_logger:
            session_logger.log_info("")
            session_logger.log_info("=" * 80)
            session_logger.log_info("СВОДНЫЕ РЕЗУЛЬТАТЫ СЕССИИ:")
            session_logger.log_info("=" * 80)
            # Логируем response как есть, с эмодзи и таблицами
            for line in response.split("\n"):
                if line.strip():  # Пропускаем пустые строки
                    session_logger.log_info(line)
            session_logger.log_info("=" * 80)

        # Убираем эмодзи и Unicode символы для совместимости с Windows
        response_clean = response.replace("✅", "[OK]").replace("❌", "[ОШИБКА]")
        response_clean = response_clean.replace("⚠️", "[ВНИМАНИЕ]").replace(
            "📊", "[ДАННЫЕ]"
        )
        response_clean = response_clean.replace("💡", "[СОВЕТ]")
        # Дополнительная замена Unicode символов
        response_clean = response_clean.replace("→", "->")
        response_clean = response_clean.replace("°", " deg ")

        print("\n[РЕЗУЛЬТАТ]")
        print(response_clean)
        print("\n" + "=" * 80)
        print("[ТЕСТ ЗАВЕРШЁН УСПЕШНО]")
        print("=" * 80)

        # НОВОЕ: Логирование завершения сессии
        if session_logger:
            session_logger.log_info("Общее время обработки: успешно завершено")
            session_logger.log_info("SESSION ENDED")

    except Exception as e:
        print(f"\n[ОШИБКА] Ошибка обработки: {e}")
        import traceback

        # НОВОЕ: Логирование ошибки в сессии
        if session_logger:
            session_logger.log_error(f"Ошибка обработки: {e}")
            session_logger.log_info("SESSION ENDED")

        traceback.print_exc()
    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Термодинамическая система v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python main.py                    # Интерактивный режим (по умолчанию)
  python main.py --test             # Тестовый режим с предопределённым запросом
        """,
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Запустить тестовый режим с предопределённым запросом",
    )

    args = parser.parse_args()

    try:
        if args.test:
            # Тестовый режим
            asyncio.run(main_test())
        else:
            # Интерактивный режим (по умолчанию)
            asyncio.run(main_interactive())
    except KeyboardInterrupt:
        print("\n\nЗавершение работы пользователем")
    except Exception as e:
        print(f"\n[ОШИБКА] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        print(f"\n[ОШИБКА] Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
