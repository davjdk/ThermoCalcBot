"""
Простая демонстрация многофазных термодинамических расчётов (Stage 07).

Без Unicode для совместимости с Windows.
"""

import sys
from pathlib import Path

# Добавляем путь к исходникам
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig
from thermo_agents.config.multi_phase_config import MULTI_PHASE_CONFIG


def demo_basic_usage():
    """Демонстрация базового использования."""
    print("Stage 07: Multi-phase thermodynamic calculations demo")
    print("=" * 60)

    # Конфигурация
    config = MultiPhaseOrchestratorConfig(
        db_path="data/thermo_data.db",
        static_cache_dir="data/static_compounds/",
        integration_points=200,  # Уменьшено для скорости демо
        llm_api_key="",  # Без LLM для простоты
    )

    # Создание оркестратора
    print("Creating multi-phase orchestrator...")
    orchestrator = MultiPhaseOrchestrator(config)

    # Проверка статуса
    status = orchestrator.get_status()
    print(f"Orchestrator created successfully:")
    print(f"   - Type: {status['orchestrator_type']}")
    print(f"   - Status: {status['status']}")
    print(f"   - YAML cache: {'enabled' if status['static_cache_enabled'] else 'disabled'}")
    print(f"   - Integration points: {status['integration_points']}")
    print()

    # Конфигурация
    print("Multi-phase calculation configuration:")
    print(f"   - Use static cache: {MULTI_PHASE_CONFIG['use_static_cache']}")
    print(f"   - Cache directory: {MULTI_PHASE_CONFIG['static_cache_dir']}")
    print(f"   - Integration points: {MULTI_PHASE_CONFIG['integration_points']}")
    print(f"   - Max temperature: {MULTI_PHASE_CONFIG['max_temperature']}K")
    print()

    # Демонстрация компонентов
    print("Components initialized:")
    print(f"   - CompoundSearcher: {type(orchestrator.compound_searcher).__name__}")
    print(f"   - Calculator: {type(orchestrator.calculator).__name__}")
    print(f"   - StaticDataManager: {type(orchestrator.static_data_manager).__name__}")
    print(f"   - CompoundFormatter: {type(orchestrator.compound_formatter).__name__}")
    print()

    print("Demo completed successfully!")


def demo_yaml_cache():
    """Демонстрация работы YAML кэша."""
    print("\nYAML Cache Demo")
    print("=" * 20)

    from thermo_agents.storage.static_data_manager import StaticDataManager
    import tempfile

    # Создаем временный YAML файл
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

        print(f"Cache directory: {cache_dir}")
        print(f"YAML file exists: {yaml_file.exists()}")
        print(f"H2O available in cache: {manager.is_available('H2O')}")

        # Загрузка данных
        if manager.is_available("H2O"):
            data = manager.load_compound("H2O")
            if data:
                print(f"Loaded data for {data.formula}:")
                print(f"   - Names: {data.common_names}")
                print(f"   - Phases: {len(data.phases)}")
                print(f"   - Description: {data.description}")


def demo_search_and_calculation():
    """Демонстрация поиска и расчётов."""
    print("\nSearch and Calculation Demo")
    print("=" * 30)

    config = MultiPhaseOrchestratorConfig(
        db_path="data/thermo_data.db",
        static_cache_dir="data/static_compounds/",
        integration_points=100,
        llm_api_key="",
    )

    orchestrator = MultiPhaseOrchestrator(config)

    # Демонстрация поиска
    print("Searching multi-phase data for H2O...")
    try:
        search_result = orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        if search_result.records:
            print(f"Found {len(search_result.records)} records")
            print(f"Phases: {search_result.phase_count}")
            print(f"Coverage: {search_result.coverage_start:.0f}-{search_result.coverage_end:.0f}K")
            print(f"298K coverage: {'Yes' if search_result.covers_298K else 'No'}")

            if search_result.tmelt:
                print(f"Melting point: {search_result.tmelt:.0f}K")
            if search_result.tboil:
                print(f"Boiling point: {search_result.tboil:.0f}K")

            # Многофазный расчёт
            print("\nMulti-phase calculation at 400K...")
            mp_result = orchestrator.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                trajectory=[400.0]  # Используем правильный параметр
            )

            print(f"Calculation result:")
            print(f"   - Final Cp: {mp_result.Cp_final:.2f} J/(mol·K)")
            print(f"   - Final H: {mp_result.H_final/1000:.2f} kJ/mol")
            print(f"   - Final S: {mp_result.S_final:.2f} J/(mol·K)")
            print(f"   - Final G: {mp_result.G_final/1000:.2f} kJ/mol")
            print(f"   - Segments: {len(mp_result.segments)}")
            print(f"   - Phase transitions: {len(mp_result.phase_transitions)}")

        else:
            print("No data found for H2O")

    except Exception as e:
        print(f"Error during search: {e}")


def main():
    """Основная функция."""
    print("Stage 07: Multi-phase Thermodynamic Calculations Integration")
    print("Strategy: Big Bang (always multi-phase)")
    print()

    # Запускаем демо
    try:
        demo_basic_usage()
        demo_yaml_cache()
        demo_search_and_calculation()
        print("\nAll demos completed successfully!")
    except KeyboardInterrupt:
        print("\nDemo interrupted")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()