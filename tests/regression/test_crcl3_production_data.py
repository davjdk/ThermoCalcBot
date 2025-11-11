"""
Тест с реальными продакшен данными для CrCl3.

Проблема: запись с фазой 's' имеет Tmin=298.1K, что не покрывает 298.0K
без учёта tolerance.
"""

import logging
import pandas as pd
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder


def test_crcl3_production_real_data():
    """
    Тест с реальными данными из продакшена для CrCl3.

    Продакшен данные показывают:
    - Фаза 's': Tmin=298.1K (НЕ покрывает 298.0K без tolerance)
    - Фаза 'l': Tmin=1100K (покрывает диапазон, но неверная фаза)

    С tolerance=1.0K: 298.1K ≤ 298.0K + 1.0K = 299.0K ✅
    """
    # Реальные данные из продакшена
    data = {
        "Formula": ["CrCl3", "CrCl3", "CrCl3(g)", "CrCl3(a)"],
        "FirstName": [
            "Chromium(III) chloride",
            "Chromium(III) chloride",
            "Chromium(III) chloride",
            "Chromium(III) chloride"
        ],
        "Phase": ["s", "l", "g", "a"],
        "Tmin": [298.1, 1100, 298.1, 298.1],
        "Tmax": [1100, 2500, 900, 300],
        "H298": [-544, 60, -333, -737],
        "S298": [122.9, 54.54, 346.97, -45.9],
        "Cp298": [91.8, 130, 76.17, 0],
        "f1": [84.9102, 130, 79.1251, 0],
        "f2": [32.0871, 0, 4.65746, 0],
        "f3": [-2.37869, 0, -4.10801, 0],
        "f4": [-0.0087, 0, 3.07807, 0],
        "f5": [0, 0, 0, 0],
        "f6": [0, 0, 0, 0],
    }
    df = pd.DataFrame(data)

    logger = logging.getLogger(__name__)
    builder = RecordRangeBuilder(logger)

    # Параметры запроса
    t_range = [298.0, 1098.0]  # 298K = 25°C
    melting = 1425.0  # K (плавление CrCl3)
    boiling = None
    is_elemental = False  # Сложное вещество
    tolerance = 1.0  # Стандартный tolerance

    print("=== ТЕСТ С РЕАЛЬНЫМИ ДАННЫМИ ===")
    print(f"Запрос: CrCl3, диапазон {t_range[0]}-{t_range[1]}K")
    print(f"Температура плавления: {melting}K")
    print(f"Tolerance: {tolerance}K")
    print()

    print("=== ДОСТУПНЫЕ ЗАПИСИ ===")
    for _, rec in df.iterrows():
        covers_298 = rec["Tmin"] <= 298.0 + tolerance and rec["Tmax"] >= 298.0
        print(f"{rec['Phase']:4s}: Tmin={rec['Tmin']:6.1f}, Tmax={rec['Tmax']:6.1f}, "
              f"H298={rec['H298']:6.0f}, покрывает 298K: {covers_298}")

    print()

    # Вызов метода
    records = builder.get_compound_records_for_range(
        df=df,
        t_range=t_range,
        melting=melting,
        boiling=boiling,
        tolerance=tolerance,
        is_elemental=is_elemental
    )

    print("=== ВЫБРАННЫЕ ЗАПИСИ ===")
    for i, rec in enumerate(records):
        print(f"Запись {i+1}: фаза={rec['Phase']}, Tmin={rec['Tmin']}, Tmax={rec['Tmax']}, "
              f"H298={rec['H298']}, S298={rec['S298']}")

    # Проверки
    print("\n=== ПРОВЕРКИ ===")

    # 1. Выбрана запись с фазой 's'?
    first_phase = records[0]["Phase"]
    print(f"1. Фаза первой записи: {first_phase} {'✅' if first_phase == 's' else '❌'}")
    assert first_phase == "s", f"Фаза первой записи '{first_phase}' ≠ 's'"

    # 2. Покрывает ли начальную точку?
    first_tmin = records[0]["Tmin"]
    covers_start = first_tmin <= t_range[0] + tolerance
    print(f"2. Tmin={first_tmin} ≤ {t_range[0]} + {tolerance} = {t_range[0] + tolerance}: {covers_start} {'✅' if covers_start else '❌'}")
    assert covers_start, f"Tmin={first_tmin} не покрывает начало диапазона с tolerance={tolerance}"

    # 3. Правильная фаза для температуры?
    expected_phase = "s"  # При 298K и Tmelt=1425K
    correct_phase = records[0]["Phase"] == expected_phase
    print(f"3. Ожидаемая фаза: {expected_phase}, фактическая: {records[0]['Phase']}: {correct_phase} {'✅' if correct_phase else '❌'}")
    assert records[0]["Phase"] == expected_phase, f"Неверная фаза: {records[0]['Phase']} ≠ {expected_phase}"

    # 4. Не нулевые H298 и S298 для сложного вещества?
    nonzero_h298 = abs(records[0]["H298"]) > 100
    nonzero_s298 = abs(records[0]["S298"]) > 100
    print(f"4. H298={records[0]['H298']} (|H298|>100): {nonzero_h298} {'✅' if nonzero_h298 else '❌'}")
    print(f"5. S298={records[0]['S298']} (|S298|>100): {nonzero_s298} {'✅' if nonzero_s298 else '❌'}")
    assert nonzero_h298, f"H298={records[0]['H298']} близко к нулю для сложного вещества"
    assert nonzero_s298, f"S298={records[0]['S298']} близко к нулю для сложного вещества"

    print("\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")


def test_tolerance_edge_cases():
    """
    Тест граничных случаев с tolerance.
    """
    data = {
        "Formula": ["CrCl3", "CrCl3"],
        "FirstName": ["Chromium(III) chloride", "Chromium(III) chloride"],
        "Phase": ["s", "l"],
        "Tmin": [298.1, 1100],
        "Tmax": [1100, 2500],
        "H298": [-544, 60],
        "S298": [122.9, 54.54],
        "f1": [84.9102, 130],
        "f2": [32.0871, 0],
        "f3": [-2.37869, 0],
        "f4": [-0.0087, 0],
        "f5": [0, 0],
        "f6": [0, 0],
    }
    df = pd.DataFrame(data)

    logger = logging.getLogger(__name__)
    builder = RecordRangeBuilder(logger)

    print("\n=== ТЕСТ НА tolerance ===")

    # Test 1: tolerance=0.0 (должно выбрать 'l')
    print("Test 1: tolerance=0.0")
    records_0 = builder.get_compound_records_for_range(
        df=df, t_range=[298.0, 1098.0], melting=1425.0,
        boiling=None, tolerance=0.0, is_elemental=False
    )
    print(f"  Выбрана фаза: {records_0[0]['Phase']}")

    # Test 2: tolerance=0.1 (должно выбрать 'l', т.к. 298.1 > 298.0 + 0.1 = 298.1)
    print("Test 2: tolerance=0.1")
    records_01 = builder.get_compound_records_for_range(
        df=df, t_range=[298.0, 1098.0], melting=1425.0,
        boiling=None, tolerance=0.1, is_elemental=False
    )
    print(f"  Выбрана фаза: {records_01[0]['Phase']}")

    # Test 3: tolerance=1.0 (должно выбрать 's')
    print("Test 3: tolerance=1.0")
    records_10 = builder.get_compound_records_for_range(
        df=df, t_range=[298.0, 1098.0], melting=1425.0,
        boiling=None, tolerance=1.0, is_elemental=False
    )
    print(f"  Выбрана фаза: {records_10[0]['Phase']}")

    assert records_10[0]["Phase"] == "s", f"С tolerance=1.0 должна выбираться фаза 's', выбрана '{records_10[0]['Phase']}'"
    print("✅ Проверка tolerance пройдена!")


if __name__ == "__main__":
    test_crcl3_production_real_data()
    test_tolerance_edge_cases()
    print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")