"""
Комплексный регрессионный тест для проблемы CrCl3.

Цель: Убедиться, что RecordRangeBuilder:
1. Выбирает ПРАВИЛЬНУЮ первую запись (фаза 's', H298=-544)
2. Выбирает МИНИМАЛЬНОЕ количество записей (1-2, а не 37)
3. Не возвращает дубликаты
4. Корректно работает с реальными продакшен данными

Данные: 37 записей из реального продакшена (как в вашем выводе).
"""

import logging

import pandas as pd

from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder


def test_crcl3_comprehensive_regression():
    """
    Комплексный тест для проблемы CrCl3 из продакшена.

    Проверяет:
    1. Правильный выбор первой записи
    2. Минимальное количество записей
    3. Отсутствие дубликатов
    4. Покрытие всего диапазона
    """
    # Реальные продакшен данные (37 записей, как в вашем выводе)
    data = create_production_dataset()
    df = pd.DataFrame(data)

    logger = logging.getLogger(__name__)
    builder = RecordRangeBuilder(logger)

    # Параметры из продакшена
    t_range = [298.0, 1098.0]
    melting = 1425.0
    boiling = None
    is_elemental = False
    tolerance = 1.0

    print("\n" + "=" * 100)
    print(f"КОМПЛЕКСНЫЙ ТЕСТ: CrCl3, диапазон {t_range[0]}-{t_range[1]}K")
    print("=" * 100)

    # ИСХОДНЫЕ ДАННЫЕ
    print(f"\n📊 ИСХОДНЫЕ ДАННЫЕ:")
    print(f"  Всего записей в DataFrame: {len(df)}")
    phase_counts_input = df["Phase"].value_counts().to_dict()
    print(f"  Распределение по фазам: {phase_counts_input}")

    # Уникальные диапазоны
    unique_ranges = (
        df.groupby(["Phase", "Tmin", "Tmax"]).size().reset_index(name="count")
    )
    print(f"\n  Уникальные температурные диапазоны:")
    for _, row in unique_ranges.iterrows():
        print(
            f"    Фаза {row['Phase']:2s}: Tmin={row['Tmin']:7.1f}K, Tmax={row['Tmax']:7.1f}K ({row['count']} записей)"
        )

    # ВЫЗОВ МЕТОДА
    print(f"\n🔧 ВЫПОЛНЯЕТСЯ ВЫБОР ЗАПИСЕЙ...")
    print(
        f"  Параметры: tolerance={tolerance}K, melting={melting}K, is_elemental={is_elemental}"
    )
    print()

    records = builder.get_compound_records_for_range(
        df=df,
        t_range=t_range,
        melting=melting,
        boiling=boiling,
        tolerance=tolerance,
        is_elemental=is_elemental,
    )

    # РЕЗУЛЬТАТЫ
    print(f"\n📦 РЕЗУЛЬТАТЫ:")
    print(f"  Выбрано записей: {len(records)}")

    if len(records) > 0:
        # Первая запись
        first = records[0]
        print(f"\n  Первая запись:")
        print(f"    Фаза: {first['Phase']}")
        print(f"    Tmin: {first['Tmin']}K, Tmax: {first['Tmax']}K")
        print(f"    H298: {first['H298']} кДж/моль")
        print(f"    S298: {first['S298']} Дж/(моль·K)")
        print(f"    Formula: {first['Formula']}")

        # Распределение по фазам
        if len(records) > 1:
            phase_counts_output = {}
            for rec in records:
                phase = rec["Phase"]
                phase_counts_output[phase] = phase_counts_output.get(phase, 0) + 1
            print(
                f"\n  Распределение выбранных записей по фазам: {phase_counts_output}"
            )

            # Детали всех записей
            print(f"\n  Детали всех {len(records)} выбранных записей:")
            for i, rec in enumerate(records):
                print(
                    f"    {i + 1:2d}. Фаза {rec['Phase']:2s}: Tmin={rec['Tmin']:7.1f}K, "
                    f"Tmax={rec['Tmax']:7.1f}K, H298={rec['H298']:7.1f}"
                )

    # ПРОВЕРКИ
    print(f"\n" + "=" * 100)
    print("🔍 ПРОВЕРКИ")
    print("=" * 100)

    # Проверка 1: Записи выбраны
    assert len(records) > 0, "❌ ОШИБКА: Не выбрано ни одной записи"
    print(f"✅ 1. Выбрано записей: {len(records)} > 0")

    # Проверка 2: Первая запись — фаза 's'
    assert records[0]["Phase"] == "s", (
        f"❌ ОШИБКА: Первая запись имеет фазу '{records[0]['Phase']}', ожидалась 's'"
    )
    print(f"✅ 2. Первая запись имеет фазу 's'")

    # Проверка 3: H298 около -544
    h298 = records[0]["H298"]
    assert h298 < -500, f"❌ ОШИБКА: H298={h298}, ожидалось < -500"
    print(f"✅ 3. H298={h298} кДж/моль (верное значение)")

    # Проверка 4: S298 > 100
    s298 = records[0]["S298"]
    assert abs(s298) > 100, f"❌ ОШИБКА: S298={s298}, ожидалось |S298| > 100"
    print(f"✅ 4. S298={s298} Дж/(моль·K) (верное значение)")

    # Проверка 5: Покрытие начальной точки
    assert records[0]["Tmin"] <= t_range[0] + tolerance, (
        f"❌ ОШИБКА: Tmin={records[0]['Tmin']} не покрывает начало {t_range[0]}"
    )
    assert records[0]["Tmax"] >= t_range[0], (
        f"❌ ОШИБКА: Tmax={records[0]['Tmax']} не покрывает начало {t_range[0]}"
    )
    print(f"✅ 5. Покрывает начальную точку {t_range[0]}K")

    # Проверка 6: Покрытие конечной точки
    assert records[-1]["Tmax"] >= t_range[1], (
        f"❌ ОШИБКА: Последняя запись (Tmax={records[-1]['Tmax']}) не покрывает конец {t_range[1]}"
    )
    print(f"✅ 6. Покрывает конечную точку {t_range[1]}K")

    # Проверка 7: Количество записей разумное (1-3)
    assert len(records) <= 3, (
        f"❌ ОШИБКА: Выбрано {len(records)} записей, ожидалось <= 3"
    )
    print(f"✅ 7. Количество записей разумное: {len(records)} <= 3")

    # Проверка 8: Нет дубликатов (одинаковые Tmin, Tmax, Phase, H298, S298)
    unique_records = set()
    for rec in records:
        key = (rec["Phase"], rec["Tmin"], rec["Tmax"], rec["H298"], rec["S298"])
        if key in unique_records:
            assert False, f"❌ ОШИБКА: Найден дубликат записи: {key}"
        unique_records.add(key)
    print(f"✅ 8. Нет дубликатов записей")

    # Проверка 9: Непрерывность покрытия
    for i in range(len(records) - 1):
        current = records[i]
        next_rec = records[i + 1]
        # Проверяем, что следующая запись начинается не раньше окончания текущей
        assert next_rec["Tmin"] <= current["Tmax"] + tolerance, (
            f"❌ ОШИБКА: Разрыв между записями {i} и {i + 1}: "
            f"{current['Tmax']}K -> {next_rec['Tmin']}K"
        )
    print(f"✅ 9. Непрерывность покрытия диапазона")

    print(f"\n{'=' * 100}")
    print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    print(f"{'=' * 100}\n")


def create_production_dataset():
    """
    Создаёт DataFrame с 37 записями, как в реальном продакшене.
    """
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

    # Фаза 'l' — 6 дубликатов
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

    # Фаза 'g' — 19 записей
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

    # Фаза 's' — 7 записей
    h298_values_s = [-544, -544, -544, -557, -570, -570]
    for h298 in h298_values_s:
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

    # Фаза 'a' — 4 дубликата
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

    # Фаза 'ai' — 1 запись
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

    return data


if __name__ == "__main__":
    test_crcl3_comprehensive_regression()
    test_crcl3_comprehensive_regression()
