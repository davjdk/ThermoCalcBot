"""
Демонстрация многофазных термодинамических расчётов (Stage 07).

Показывает работу новой архитектуры с Big Bang стратегией.
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к исходникам
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig
from thermo_agents.config.multi_phase_config import MULTI_PHASE_CONFIG


async def demo_basic_usage():
    """Демонстрация базового использования."""
    print("🚀 Демонстрация многофазных термодинамических расчётов (Stage 07)")
    print("=" * 60)

    # Конфигурация
    config = MultiPhaseOrchestratorConfig(
        db_path="data/thermo_data.db",
        static_cache_dir="data/static_compounds/",
        integration_points=200,  # Уменьшено для скорости демо
        llm_api_key="",  # Без LLM для простоты
    )

    # Создание оркестратора
    print("📋 Создание многофазного оркестратора...")
    orchestrator = MultiPhaseOrchestrator(config)

    # Проверка статуса
    status = orchestrator.get_status()
    print(f"✅ Оркестратор создан:")
    print(f"   - Тип: {status['orchestrator_type']}")
    print(f"   - Статус: {status['status']}")
    print(f"   - YAML кэш: {'включен' if status['static_cache_enabled'] else 'отключен'}")
    print(f"   - Точек интегрирования: {status['integration_points']}")
    print()

    # Конфигурация
    print("⚙️ Конфигурация многофазных расчётов:")
    print(f"   - Использовать статический кэш: {MULTI_PHASE_CONFIG['use_static_cache']}")
    print(f"   - Директория кэша: {MULTI_PHASE_CONFIG['static_cache_dir']}")
    print(f"   - Точек интегрирования: {MULTI_PHASE_CONFIG['integration_points']}")
    print(f"   - Максимальная температура: {MULTI_PHASE_CONFIG['max_temperature']}K")
    print()

    # Обработка запросов
    queries = [
        "H2O свойства",
        "CO2 при 600K",
        "Свойства O2",
    ]

    for query in queries:
        print(f"🔍 Запрос: {query}")
        try:
            response = await orchestrator.process_query(query)
            print(f"📄 Ответ ({len(response)} символов):")
            # Показываем первые 300 символов ответа
            preview = response[:300] + "..." if len(response) > 300 else response
            print(preview)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        print("-" * 40)

    print()
    print("🎉 Демонстрация завершена!")


async def demo_yaml_cache():
    """Демонстрация работы YAML кэша."""
    print("\n🗂️ Демонстрация YAML кэша")
    print("=" * 30)

    from thermo_agents.storage.static_data_manager import StaticDataManager

    # Создаем временный YAML файл для H2O
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir) / "static_compounds"
        cache_dir.mkdir(parents=True, exist_ok=True)

        yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  description: "Demo water data"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -241826.0
      s298: 188.83
      f1: 30.00
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      reliability_class: 1
  metadata:
    source_database: "demo"
    extracted_date: "2025-10-19"
    version: "1.0"
"""

        yaml_file = cache_dir / "H2O.yaml"
        yaml_file.write_text(yaml_content)

        # Создаем менеджер
        manager = StaticDataManager(cache_dir)

        print(f"📁 Директория кэша: {cache_dir}")
        print(f"📄 YAML файл для H2O: {yaml_file.exists()}")
        print(f"🔍 Доступность H2O в кэше: {manager.is_available('H2O')}")

        # Загрузка данных
        if manager.is_available("H2O"):
            data = manager.load_compound("H2O")
            if data:
                print(f"✅ Загружены данные для {data.formula}:")
                print(f"   - Названия: {data.common_names}")
                print(f"   - Фаз: {len(data.phases)}")
                print(f"   - Описание: {data.description}")


async def demo_search_and_calculation():
    """Демонстрация поиска и расчётов."""
    print("\n🔬 Демонстрация поиска и расчётов")
    print("=" * 35)

    config = MultiPhaseOrchestratorConfig(
        db_path="data/thermo_data.db",
        static_cache_dir="data/static_compounds/",
        integration_points=100,
        llm_api_key="",
    )

    orchestrator = MultiPhaseOrchestrator(config)

    # Демонстрация поиска
    print("🔍 Поиск многофазных данных для H2O...")
    try:
        search_result = orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        if search_result.records:
            print(f"✅ Найдено {len(search_result.records)} записей")
            print(f"📊 Фаз: {search_result.phase_count}")
            print(f"🌡️ Покрытие: {search_result.coverage_start:.0f}-{search_result.coverage_end:.0f}K")
            print(f"✓ Покрытие 298K: {'Да' if search_result.covers_298K else 'Нет'}")

            if search_result.tmelt:
                print(f"🧊 T плавления: {search_result.tmelt:.0f}K")
            if search_result.tboil:
                print(f"💨 T кипения: {search_result.tboil:.0f}K")

            # Многофазный расчёт
            print("\n🧮 Многофазный расчёт при 400K...")
            mp_result = orchestrator.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                T_target=400.0
            )

            print(f"✅ Результат расчёта:")
            print(f"   - Финальная теплоёмкость: {mp_result.Cp_final:.2f} Дж/(моль·K)")
            print(f"   - Финальная энтальпия: {mp_result.H_final/1000:.2f} кДж/моль")
            print(f"   - Финальная энтропия: {mp_result.S_final:.2f} Дж/(моль·K)")
            print(f"   - Финальная энергия Гиббса: {mp_result.G_final/1000:.2f} кДж/моль")
            print(f"   - Сегментов: {len(mp_result.segments)}")
            print(f"   - Фазовых переходов: {len(mp_result.phase_transitions)}")

        else:
            print("❌ Данные для H2O не найдены")

    except Exception as e:
        print(f"❌ Ошибка при поиске: {e}")


def main():
    """Основная функция."""
    print("Stage 07: Интеграция многофазных термодинамических расчётов")
    print("Стратегия: Big Bang (всегда многофазные расчёты)")
    print()

    # Запускаем демо
    try:
        asyncio.run(demo_basic_usage())
        asyncio.run(demo_yaml_cache())
        asyncio.run(demo_search_and_calculation())
    except KeyboardInterrupt:
        print("\n👋 Демонстрация прервана")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()