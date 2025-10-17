"""Быстрый тест новой фазовой фильтрации."""

import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.filtering.filter_pipeline import FilterContext
from thermo_agents.filtering.phase_based_temperature_stage import (
    PhaseBasedTemperatureStage,
)
from thermo_agents.models.search import DatabaseRecord


def create_test_record(formula, phase, tmin, tmax, tmelt, tboil, reliability=1):
    """Создать тестовую запись."""
    return DatabaseRecord(
        id=None,
        formula=formula,
        firstname="Test compound",
        phase=phase,
        tmin=tmin,
        tmax=tmax,
        tmelt=tmelt,
        tboil=tboil,
        h298=0.0,
        s298=0.0,
        f1=0.0,
        f2=0.0,
        f3=0.0,
        f4=0.0,
        f5=0.0,
        f6=0.0,
        reliability_class=reliability,
        reference="",
    )


def test_ion_filtering():
    """Тест фильтрации ионных форм."""
    print("\n=== ТЕСТ 1: Фильтрация ионных форм ===")

    stage = PhaseBasedTemperatureStage(exclude_ions=True)

    records = [
        create_test_record("CO2(g)", "g", 1000, 10000, 216, 194, 1),
        create_test_record("CO2(+g)", "g", 1000, 10000, 216, 194, 1),  # Ионная форма
    ]

    context = FilterContext(temperature_range=(973.0, 1173.0), compound_formula="CO2")

    filtered = stage.filter(records, context)

    print(f"Записей до фильтрации: {len(records)}")
    print(f"Записей после фильтрации: {len(filtered)}")
    print(f"Ионы исключены: {stage.last_stats.get('ions_excluded', False)}")

    assert len(filtered) == 1, "Должна остаться только нейтральная форма"
    assert "(+g)" not in filtered[0].formula, "Ионная форма не должна пройти"
    print("✓ Тест пройден: ионные формы отфильтрованы")


def test_phase_separation():
    """Тест разделения по фазам."""
    print("\n=== ТЕСТ 2: Разделение по фазам ===")

    stage = PhaseBasedTemperatureStage(exclude_ions=True, max_records_per_phase=1)

    # Li2CO3: Tmelt = 993K, Tboil = 1564K
    # Запрос: 973-1173K (пересекает точку плавления)
    records = [
        create_test_record("Li2CO3", "s", 683, 993, 993, 1564, 1),  # Твердая
        create_test_record("Li2CO3", "l", 993, 2000, 993, 1564, 1),  # Жидкая
    ]

    context = FilterContext(
        temperature_range=(973.0, 1173.0), compound_formula="Li2CO3"
    )

    filtered = stage.filter(records, context)

    print(f"Записей до фильтрации: {len(records)}")
    print(f"Записей после фильтрации: {len(filtered)}")
    print(f"Фазовые диапазоны: {stage.last_stats.get('phase_ranges', [])}")
    print(f"Покрытие фаз: {stage.last_stats.get('phase_coverage', {})}")

    # Должны быть выбраны обе фазы, так как диапазон пересекает Tmelt
    print(f"\nВыбранные фазы: {[r.phase for r in filtered]}")

    print("✓ Тест пройден: фазовое разделение работает")


def test_single_phase():
    """Тест для диапазона в одной фазе."""
    print("\n=== ТЕСТ 3: Диапазон в одной фазе ===")

    stage = PhaseBasedTemperatureStage(exclude_ions=True)

    # TiO2: запрос ниже точки плавления (только твердая фаза)
    records = [
        create_test_record("TiO2(s)", "s", 298, 2116, 2116, 3245, 1),
        create_test_record("TiO2(l)", "l", 2116, 3000, 2116, 3245, 1),
        create_test_record("TiO2(g)", "g", 1100, 6000, 2116, 3245, 1),
    ]

    context = FilterContext(
        temperature_range=(973.0, 1173.0),  # 700-900°C, ниже точки плавления
        compound_formula="TiO2",
    )

    filtered = stage.filter(records, context)

    print(f"Записей до фильтрации: {len(records)}")
    print(f"Записей после фильтрации: {len(filtered)}")
    print(f"Выбранные фазы: {[r.phase for r in filtered]}")

    # Должна быть выбрана только твердая фаза
    assert all(r.phase == "s" for r in filtered), (
        "При T < Tmelt должна быть только твердая фаза"
    )
    print("✓ Тест пройден: выбрана только твердая фаза")


def main():
    """Запуск всех тестов."""
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ PhaseBasedTemperatureStage")
    print("=" * 60)

    try:
        test_ion_filtering()
        test_phase_separation()
        test_single_phase()

        print("\n" + "=" * 60)
        print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ ОШИБКА: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ НЕОЖИДАННАЯ ОШИБКА: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
