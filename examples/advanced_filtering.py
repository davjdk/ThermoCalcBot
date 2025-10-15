"""
Пример настройки кастомной фильтрации термодинамических данных.

Демонстрирует различные конфигурации FilterPipeline для
специфических сценариев использования.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

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


def create_strict_pipeline(db_connector, sql_builder):
    """Создает строгий конвейер фильтрации."""
    pipeline = FilterPipeline()

    # Строгий поиск только точных совпадений
    pipeline.add_stage(TemperatureFilterStage())
    pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=1))  # Только лучшая запись

    return pipeline


def create_permissive_pipeline(db_connector, sql_builder):
    """Создает допустимый конвейер фильтрации."""
    pipeline = FilterPipeline()

    # Разрешительный поиск с комплексным поиском
    pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    pipeline.add_stage(TemperatureFilterStage())
    pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=5))  # Топ-5 записей
    pipeline.add_stage(TemperatureCoverageStage(TemperatureResolver()))

    return pipeline


def create_high_temperature_pipeline(db_connector, sql_builder):
    """Создает конвейер для высокотемпературных приложений."""
    pipeline = FilterPipeline()

    # Сначала комплексный поиск (могут понадобиться разные соединения)
    pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    pipeline.add_stage(TemperatureFilterStage())
    pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    # Высокий приоритет для температурного покрытия
    pipeline.add_stage(TemperatureCoverageStage(TemperatureResolver()))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=3))

    return pipeline


def create_research_pipeline(db_connector, sql_builder):
    """Создает конвейер для исследовательских целей."""
    pipeline = FilterPipeline()

    # Максимальное количество данных для анализа
    pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    pipeline.add_stage(TemperatureFilterStage())
    pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=10))  # Много записей
    pipeline.add_stage(TemperatureCoverageStage(TemperatureResolver()))

    return pipeline


async def demo_filtering_comparison():
    """Сравнение различных стратегий фильтрации."""
    print("🔬 Сравнение стратегий фильтрации")
    print("=" * 60)

    # Инициализация
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    compound = "Fe"
    temp_range = (1000, 2000)  # Высокие температуры

    print(f"Анализ соединения: {compound}")
    print(f"Температурный диапазон: {temp_range[0]}-{temp_range[1]}K")
    print()

    # Получаем исходные данные
    search_result = compound_searcher.search_compound(compound, temp_range)

    if not search_result or not search_result.records_found:
        print(f"❌ Данные для {compound} не найдены")
        return

    print(f"📊 Найдено записей: {len(search_result.records_found)}")
    print()

    # Различные конвейеры
    pipelines = {
        "Строгий фильтр": create_strict_pipeline(db_connector, sql_builder),
        "Допустимый фильтр": create_permissive_pipeline(db_connector, sql_builder),
        "Высокотемпературный": create_high_temperature_pipeline(db_connector, sql_builder),
        "Исследовательский": create_research_pipeline(db_connector, sql_builder),
    }

    filter_context = FilterContext(
        temperature_range=temp_range,
        compound_formula=compound
    )

    for name, pipeline in pipelines.items():
        print(f"🔧 {name}:")
        print("-" * 40)

        try:
            filter_result = pipeline.execute(search_result.records_found, filter_context)

            if filter_result and filter_result.filtered_records:
                print(f"✅ Отфильтровано: {len(filter_result.filtered_records)} записей")

                # Показываем первую запись для примера
                if filter_result.filtered_records:
                    record = filter_result.filtered_records[0]
                    print(f"   📄 Пример: {record.get('Formula', 'N/A')}")
                    print(f"   🌡️ T: {record.get('Tmin', 'N/A')}-{record.get('Tmax', 'N/A')}K")
                    print(f"   🔄 Фаза: {record.get('Phase', 'N/A')}")
                    print(f"   ⭐ Надежность: {record.get('ReliabilityClass', 'N/A')}")

                # Статистика по стадиям
                if filter_result.stage_statistics:
                    print("   📈 Статистика:")
                    for i, stage in enumerate(filter_result.stage_statistics, 1):
                        print(f"      Стадия {i}: {stage.get('records_before', 0)} → {stage.get('records_after', 0)}")
            else:
                print("❌ Записи не прошли фильтрацию")

        except Exception as e:
            print(f"❌ Ошибка: {e}")

        print()


async def demo_temperature_filtering():
    """Демонстрация температурной фильтрации."""
    print("🌡️ Демонстрация температурной фильтрации")
    print("=" * 60)

    # Инициализация
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    compound = "H2O"
    temp_ranges = [
        (250, 300),   # Низкие температуры
        (298, 350),   # Комнатная температура
        (400, 500),   # Средние температуры
        (800, 1000),  # Высокие температуры
    ]

    print(f"Анализ соединения: {compound}")
    print()

    for temp_range in temp_ranges:
        print(f"🌡️ Диапазон {temp_range[0]}-{temp_range[1]}K:")
        print("-" * 40)

        try:
            # Поиск
            search_result = compound_searcher.search_compound(compound, temp_range)

            if search_result and search_result.records_found:
                print(f"   📊 Найдено: {len(search_result.records_found)} записей")

                # Фильтрация
                pipeline = FilterPipeline()
                pipeline.add_stage(TemperatureFilterStage())
                pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))

                filter_context = FilterContext(
                    temperature_range=temp_range,
                    compound_formula=compound
                )

                filter_result = pipeline.execute(search_result.records_found, filter_context)

                if filter_result and filter_result.filtered_records:
                    # Анализ фаз
                    phases = set()
                    for record in filter_result.filtered_records:
                        phase = record.get('Phase', 'N/A')
                        phases.add(phase)

                    print(f"   ✅ Отфильтровано: {len(filter_result.filtered_records)} записей")
                    print(f"   🔄 Фазы: {', '.join(sorted(phases))}")

                    # Температурные диапазоны
                    temps = [(r.get('Tmin', 0), r.get('Tmax', 0)) for r in filter_result.filtered_records[:3]]
                    print(f"   📈 Диапазоны: {', '.join([f'{t[0]}-{t[1]}K' for t in temps])}")
                else:
                    print("   ❌ Не отфильтровано ни одной записи")
            else:
                print("   ❌ Данные не найдены")

        except Exception as e:
            print(f"   ❌ Ошибка: {e}")

        print()


async def demo_phase_resolution():
    """Демонстрация разрешения фазовых состояний."""
    print("🔄 Демонстрация разрешения фаз")
    print("=" * 60)

    # Инициализация
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    compounds = ["H2O", "Fe", "CO2"]
    temp_ranges = [
        (200, 273),   # Низкие температуры
        (273, 373),   # Температуры плавления/кипения
        (373, 473),   # Выше кипения
    ]

    phase_resolver = PhaseResolver()

    for temp_range in temp_ranges:
        print(f"🌡️ Температурный диапазон: {temp_range[0]}-{temp_range[1]}K")
        print("-" * 40)

        for compound in compounds:
            try:
                search_result = compound_searcher.search_compound(compound, temp_range)

                if search_result and search_result.records_found:
                    # Анализ фаз
                    phases = {}
                    for record in search_result.records_found[:10]:  # Первые 10 записей
                        phase = record.get('Phase', 'unknown')
                        if phase not in phases:
                            phases[phase] = 0
                        phases[phase] += 1

                    # Разрешение фазы
                    resolved_phase = phase_resolver.resolve_phase(
                        compound, temp_range[0], phases
                    )

                    print(f"   {compound}:")
                    print(f"      📊 Найдено фаз: {dict(phases)}")
                    print(f"      🎯 Рекомендуемая: {resolved_phase}")
                else:
                    print(f"   {compound}: ❌ Данные не найдены")

            except Exception as e:
                print(f"   {compound}: ❌ Ошибка - {e}")

        print()


async def demo_reliability_filtering():
    """Демонстрация фильтрации по надежности."""
    print("⭐ Демонстрация фильтрации по надежности")
    print("=" * 60)

    # Инициализация
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    compound = "CO2"
    temp_range = (298, 500)

    print(f"Анализ соединения: {compound} при {temp_range[0]}-{temp_range[1]}K")
    print()

    try:
        search_result = compound_searcher.search_compound(compound, temp_range)

        if not search_result or not search_result.records_found:
            print(f"❌ Данные для {compound} не найдены")
            return

        print(f"📊 Всего найдено: {len(search_result.records_found)} записей")

        # Анализ надежности
        reliability_classes = {}
        for record in search_result.records_found:
            rel_class = record.get('ReliabilityClass', 'unknown')
            if rel_class not in reliability_classes:
                reliability_classes[rel_class] = 0
            reliability_classes[rel_class] += 1

        print("📈 Распределение по классам надежности:")
        for rel_class, count in sorted(reliability_classes.items()):
            print(f"   Класс {rel_class}: {count} записей")

        print()

        # Различные стратегии фильтрации по надежности
        strategies = [1, 3, 5]  # Максимальное количество записей

        for max_records in strategies:
            print(f"🎯 Стратегия: топ-{max_records} наиболее надежных записей")
            print("-" * 30)

            pipeline = FilterPipeline()
            pipeline.add_stage(ReliabilityPriorityStage(max_records=max_records))

            filter_context = FilterContext(
                temperature_range=temp_range,
                compound_formula=compound
            )

            filter_result = pipeline.execute(search_result.records_found, filter_context)

            if filter_result and filter_result.filtered_records:
                for i, record in enumerate(filter_result.filtered_records, 1):
                    rel_class = record.get('ReliabilityClass', 'N/A')
                    formula = record.get('Formula', 'N/A')
                    temp_range_rec = f"{record.get('Tmin', 'N/A')}-{record.get('Tmax', 'N/A')}K"
                    print(f"   {i}. {formula} (Класс {rel_class}, {temp_range_rec})")
            else:
                print("   ❌ Записи не отфильтрованы")

            print()

    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def main():
    """Главная функция демонстрации расширенной фильтрации."""
    print("🚀 Термодинамическая система v2.0 - Расширенная фильтрация")
    print("=" * 60)
    print()

    await demo_filtering_comparison()
    await demo_temperature_filtering()
    await demo_phase_resolution()
    await demo_reliability_filtering()

    print("=" * 60)
    print("✅ Демонстрация расширенной фильтрации завершена")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())