"""
Регрессионный тест на основе реальных продакшен данных CrCl3.

Проблема: система выбирает 37 записей вместо 1-2 для диапазона 298-1098K.
Первая запись имеет фазу 'l' (H298=60) вместо 's' (H298=-544).

Данные взяты из вывода продакшена.
"""

import logging

import pandas as pd

from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder


def test_crcl3_production_issue_37_records():
    """
    Тест воспроизводит проблему из продакшена:
    - Выбрано 37 записей вместо 1-2
    - Первая запись имеет фазу 'l' (H298=60) вместо 's' (H298=-544)

    Ожидаемое поведение после исправления:
    - Выбрано 1 запись (фаза 's', покрывает весь диапазон 298-1098K)
    - H298 ≈ -544 кДж/моль
    """
    # Реальные данные из продакшена (37 записей)
    # Упрощаем до ключевых записей
    data = {
        "Formula": [],
        "FirstName": [],
        "Phase": [],
        "Tmin": [],
        "Tmax": [],
        "H298": [],
        "S298": [],
        "Cp298": [],
        "f1": [],
        "f2": [],
        "f3": [],
        "f4": [],
        "f5": [],
        "f6": [],
    }

    # Фаза 'l' - 6 дубликатов
    for _ in range(6):
        data["Formula"].append("CrCl3")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("l")
        data["Tmin"].append(1100)
        data["Tmax"].append(2500)
        data["H298"].append(60)
        data["S298"].append(54.54)
        data["Cp298"].append(130)
        data["f1"].append(130)
        data["f2"].append(0)
        data["f3"].append(0)
        data["f4"].append(0)
        data["f5"].append(0)
        data["f6"].append(0)

    # Фаза 'g' - 19 записей (разные диапазоны)
    # 900-2300K (6 дубликатов)
    for _ in range(6):
        data["Formula"].append("CrCl3(g)")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("g")
        data["Tmin"].append(900)
        data["Tmax"].append(2300)
        data["H298"].append(0)
        data["S298"].append(0)
        data["Cp298"].append(36.56)
        data["f1"].append(89.2042)
        data["f2"].append(3.60615)
        data["f3"].append(-47.6325)
        data["f4"].append(-1.56323)
        data["f5"].append(0)
        data["f6"].append(0)

    # 298.1-2000K (1 запись)
    data["Formula"].append("CrCl3(g)")
    data["FirstName"].append("Chromium(III) chloride")
    data["Phase"].append("g")
    data["Tmin"].append(298.1)
    data["Tmax"].append(2000)
    data["H298"].append(-325)
    data["S298"].append(317.64)
    data["Cp298"].append(76.01)
    data["f1"].append(83.3452)
    data["f2"].append(3.15474)
    data["f3"].append(-7.35965)
    data["f4"].append(0)
    data["f5"].append(0)
    data["f6"].append(0)

    # 2300-6000K (6 дубликатов)
    for _ in range(6):
        data["Formula"].append("CrCl3(g)")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("g")
        data["Tmin"].append(2300)
        data["Tmax"].append(6000)
        data["H298"].append(0)
        data["S298"].append(0)
        data["Cp298"].append(210.05)
        data["f1"].append(88.3339)
        data["f2"].append(-1.12422)
        data["f3"].append(108.484)
        data["f4"].append(0.100247)
        data["f5"].append(0)
        data["f6"].append(0)

    # 298.1-900K (6 дубликатов)
    for _ in range(6):
        data["Formula"].append("CrCl3(g)")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("g")
        data["Tmin"].append(298.1)
        data["Tmax"].append(900)
        data["H298"].append(-333)
        data["S298"].append(346.97)
        data["Cp298"].append(76.17)
        data["f1"].append(79.1251)
        data["f2"].append(4.65746)
        data["f3"].append(-4.10801)
        data["f4"].append(3.07807)
        data["f5"].append(0)
        data["f6"].append(0)

    # Фаза 's' - 7 записей
    # 298.1-1100K (6 дубликатов с небольшими различиями в H298)
    h298_values = [-544, -544, -544, -557, -570, -570]
    for h298 in h298_values:
        data["Formula"].append("CrCl3")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("s")
        data["Tmin"].append(298.1)
        data["Tmax"].append(1100)
        data["H298"].append(h298)
        data["S298"].append(122.9)
        data["Cp298"].append(91.8)
        data["f1"].append(84.9102)
        data["f2"].append(32.0871)
        data["f3"].append(-2.37869)
        data["f4"].append(-0.0087)
        data["f5"].append(0)
        data["f6"].append(0)

    # 298.1-1200K (1 запись)
    data["Formula"].append("CrCl3")
    data["FirstName"].append("Chromium(III) chloride")
    data["Phase"].append("s")
    data["Tmin"].append(298.1)
    data["Tmax"].append(1200)
    data["H298"].append(-556)
    data["S298"].append(123.01)
    data["Cp298"].append(91.8)
    data["f1"].append(98.8302)
    data["f2"].append(13.9578)
    data["f3"].append(-9.94954)
    data["f4"].append(0)
    data["f5"].append(0)
    data["f6"].append(0)

    # Фаза 'a' - 4 дубликата
    for _ in range(4):
        data["Formula"].append("CrCl3(a)")
        data["FirstName"].append("Chromium(III) chloride")
        data["Phase"].append("a")
        data["Tmin"].append(298.1)
        data["Tmax"].append(300)
        data["H298"].append(-737)
        data["S298"].append(-45.9)
        data["Cp298"].append(0)
        data["f1"].append(0)
        data["f2"].append(0)
        data["f3"].append(0)
        data["f4"].append(0)
        data["f5"].append(0)
        data["f6"].append(0)

    # Фаза 'ai' - 1 запись
    data["Formula"].append("CrCl3(ia)")
    data["FirstName"].append("Chromium(III) chloride")
    data["Phase"].append("ai")
    data["Tmin"].append(298.1)
    data["Tmax"].append(300)
    data["H298"].append(-737)
    data["S298"].append(-45.9)
    data["Cp298"].append(0)
    data["f1"].append(0)
    data["f2"].append(0)
    data["f3"].append(0)
    data["f4"].append(0)
    data["f5"].append(0)
    data["f6"].append(0)

    df = pd.DataFrame(data)

    # Инициализация RecordRangeBuilder
    logger = logging.getLogger(__name__)
    builder = RecordRangeBuilder(logger)  # Параметры запроса (из продакшена)
    t_range = [298.0, 1098.0]
    melting = 1425.0  # K
    boiling = None
    is_elemental = False
    tolerance = 1.0

    print("\n" + "=" * 80)
    print(f"ТЕСТ: CrCl3, диапазон {t_range[0]}-{t_range[1]}K")
    print("=" * 80)
    print(f"Всего записей в данных: {len(df)}")
    print(f"Распределение по фазам: {dict(df['Phase'].value_counts())}")
    print()

    # Вызов метода
    records = builder.get_compound_records_for_range(
        df=df,
        t_range=t_range,
        melting=melting,
        boiling=boiling,
        tolerance=tolerance,
        is_elemental=is_elemental,
    )

    print(f"Выбрано записей: {len(records)}")
    if len(records) > 0:
        print("\nПервая запись:")
        print(f"  Фаза: {records[0]['Phase']}")
        print(f"  Tmin: {records[0]['Tmin']}K")
        print(f"  Tmax: {records[0]['Tmax']}K")
        print(f"  H298: {records[0]['H298']} кДж/моль")
        print(f"  S298: {records[0]['S298']} Дж/(моль·K)")

        if len(records) > 1:
            phase_counts = {}
            for rec in records:
                phase = rec["Phase"]
                phase_counts[phase] = phase_counts.get(phase, 0) + 1
            print(f"\nРаспределение выбранных записей: {phase_counts}")
    print()

    # ПРОВЕРКИ
    print("=" * 80)
    print("ПРОВЕРКИ")
    print("=" * 80)

    # 1. Первая запись должна иметь фазу 's'
    assert len(records) > 0, "Не выбрано ни одной записи"
    assert records[0]["Phase"] == "s", (
        f"Первая запись имеет фазу '{records[0]['Phase']}', ожидалась 's'"
    )
    print("✅ 1. Фаза первой записи: 's'")

    # 2. H298 должно быть около -544 (или -557, -570)
    h298 = records[0]["H298"]
    assert h298 < -500, f"H298={h298}, ожидалось значение < -500 (около -544)"
    print(f"✅ 2. H298={h298} кДж/моль (верное значение)")

    # 3. S298 должно быть около 122.9
    s298 = records[0]["S298"]
    assert abs(s298) > 100, f"S298={s298}, ожидалось |S298| > 100"
    print(f"✅ 3. S298={s298} Дж/(моль·K) (верное значение)")

    # 4. Покрывает начальную точку
    assert records[0]["Tmin"] <= t_range[0] + tolerance, (
        f"Tmin={records[0]['Tmin']} не покрывает начало диапазона {t_range[0]}"
    )
    assert records[0]["Tmax"] >= t_range[0], (
        f"Tmax={records[0]['Tmax']} не покрывает начало диапазона {t_range[0]}"
    )
    print(f"✅ 4. Покрывает начальную точку {t_range[0]}K")

    # 5. Количество записей должно быть разумным (1-3)
    assert len(records) <= 3, f"Выбрано {len(records)} записей, ожидалось <= 3"
    print(f"✅ 5. Количество записей: {len(records)} (разумное)")

    print("\n🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")


if __name__ == "__main__":
    test_crcl3_production_issue_37_records()
    test_crcl3_production_issue_37_records()
    test_crcl3_production_issue_37_records()
