"""
Отладочный тест для воспроизведения проблемы из продакшена.

Проблема: система выбирает 37 записей вместо 1-2 для диапазона 298-1098K.
Первая запись имеет фазу 'l' вместо 's'.
"""

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from thermo_agents.core_logic.phase_transition_detector import PhaseTransitionDetector
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder


def test_crcl3_from_real_database():
    """
    Тест с реальными данными из базы данных.
    """
    # Настройка логирования
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s %(name)s:%(filename)s:%(lineno)d %(message)s",
    )
    logger = logging.getLogger(__name__)

    # Параметры запроса
    formula = "CrCl3"

    # Подключение к базе данных
    db_path = Path(__file__).parent.parent.parent / "data" / "thermodynamic.db"
    if not db_path.exists():
        print(f"❌ База данных не найдена: {db_path}")
        return

    # Читаем данные напрямую через sqlite3
    conn = sqlite3.connect(str(db_path))
    query = f"""
        SELECT 
            Formula, FirstName, Phase, Tmin, Tmax, 
            H298, S298, Cp298, 
            f1, f2, f3, f4, f5, f6,
            MeltingPoint, BoilingPoint, Source
        FROM thermodynamic
        WHERE Formula = '{formula}'
        ORDER BY Phase, Tmin
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"\n{'=' * 80}")
    print(f"ДАННЫЕ ИЗ БАЗЫ ДЛЯ {formula}")
    print(f"{'=' * 80}")
    print(f"Всего записей в базе: {len(df)}")
    print()

    # Показываем сводку по фазам
    phase_counts = df["Phase"].value_counts()
    print("Распределение по фазам:")
    for phase, count in phase_counts.items():
        print(f"  {phase}: {count} записей")
    print()

    # Показываем уникальные диапазоны
    print("Уникальные температурные диапазоны:")
    unique_ranges = (
        df.groupby(["Phase", "Tmin", "Tmax"]).size().reset_index(name="count")
    )
    for _, row in unique_ranges.iterrows():
        print(
            f"  Фаза {row['Phase']:2s}: Tmin={row['Tmin']:7.1f}K, Tmax={row['Tmax']:7.1f}K ({row['count']} записей)"
        )
    print()

    # Определяем точки переходов
    phase_detector = PhaseTransitionDetector()
    melting, boiling = phase_detector.get_most_common_melting_boiling_points(df)
    print("Точки фазовых переходов:")
    print(f"  Плавление: {melting}K" if melting else "  Плавление: не определено")
    print(f"  Кипение: {boiling}K" if boiling else "  Кипение: не определено")
    print()

    # Параметры запроса
    t_range = [298.0, 1098.0]
    is_elemental = False  # Сложное вещество
    tolerance = 1.0

    print(f"{'=' * 80}")
    print(f"ЗАПРОС: {formula}, диапазон {t_range[0]}-{t_range[1]}K")
    print(f"{'=' * 80}")
    print(f"Tolerance: {tolerance}K")
    print(f"is_elemental: {is_elemental}")
    print()

    # Определяем ожидаемую фазу для 298K
    expected_phase_298 = phase_detector.get_phase_at_temperature(
        298.0, melting, boiling
    )
    print(f"Ожидаемая фаза для T=298K: '{expected_phase_298}'")
    print()

    # Показываем записи, которые МОГУТ покрывать 298K
    print("Записи, покрывающие T=298K (с tolerance=1.0):")
    covering_298 = df[(df["Tmin"] <= 298.0 + tolerance) & (df["Tmax"] >= 298.0)]
    print(f"Найдено {len(covering_298)} записей:")
    for _, rec in covering_298.iterrows():
        covers_exact = rec["Tmin"] <= 298.0 and rec["Tmax"] >= 298.0
        print(
            f"  Фаза {rec['Phase']:2s}: Tmin={rec['Tmin']:7.1f}K, Tmax={rec['Tmax']:7.1f}K, "
            f"H298={rec['H298']:7.1f}, S298={rec['S298']:7.2f}, "
            f"покрывает 298K: {covers_exact}"
        )
    print()

    # Вызов RecordRangeBuilder
    builder = RecordRangeBuilder(logger)

    print(f"{'=' * 80}")
    print("ВЫПОЛНЯЕТСЯ ВЫБОР ЗАПИСЕЙ...")
    print(f"{'=' * 80}")
    print()

    records = builder.get_compound_records_for_range(
        df=df,
        t_range=t_range,
        melting=melting,
        boiling=boiling,
        tolerance=tolerance,
        is_elemental=is_elemental,
    )

    print(f"\n{'=' * 80}")
    print("РЕЗУЛЬТАТ ВЫБОРА")
    print(f"{'=' * 80}")
    print(f"Всего выбрано записей: {len(records)}")
    print()

    if len(records) > 0:
        print("Первая запись:")
        first = records[0]
        print(f"  Фаза: {first['Phase']}")
        print(f"  Tmin: {first['Tmin']}K")
        print(f"  Tmax: {first['Tmax']}K")
        print(f"  H298: {first['H298']} кДж/моль")
        print(f"  S298: {first['S298']} Дж/(моль·K)")
        print()

        # Распределение выбранных записей по фазам
        if len(records) > 1:
            print(f"Все выбранные записи ({len(records)}):")
            phase_counts_selected = {}
            for i, rec in enumerate(records):
                phase = rec["Phase"]
                phase_counts_selected[phase] = phase_counts_selected.get(phase, 0) + 1
                if i < 10:  # Показываем первые 10
                    print(
                        f"  {i + 1:2d}. Фаза {rec['Phase']:2s}: Tmin={rec['Tmin']:7.1f}K, "
                        f"Tmax={rec['Tmax']:7.1f}K, H298={rec['H298']:7.1f}"
                    )

            if len(records) > 10:
                print(f"  ... (ещё {len(records) - 10} записей)")

            print()
            print("Распределение выбранных записей по фазам:")
            for phase, count in sorted(phase_counts_selected.items()):
                print(f"  {phase}: {count}")
    else:
        print("❌ Записи не выбраны!")

    print()

    # ПРОВЕРКИ
    print(f"{'=' * 80}")
    print("ПРОВЕРКИ")
    print(f"{'=' * 80}")

    if len(records) == 0:
        print("❌ ОШИБКА: Записи не выбраны!")
        assert False, "Записи не выбраны"

    # 1. Первая запись должна иметь фазу 's'
    first_phase = records[0]["Phase"]
    check1 = first_phase == expected_phase_298
    print(
        f"1. Фаза первой записи: {first_phase} (ожидалась '{expected_phase_298}') {'✅' if check1 else '❌'}"
    )

    # 2. Первая запись должна покрывать начальную точку
    first_tmin = records[0]["Tmin"]
    first_tmax = records[0]["Tmax"]
    covers_start = first_tmin <= t_range[0] + tolerance and first_tmax >= t_range[0]
    print(
        f"2. Покрывает T={t_range[0]}K: {first_tmin} <= {t_range[0]} + {tolerance} <= {first_tmax}: {covers_start} {'✅' if covers_start else '❌'}"
    )

    # 3. H298 должно быть ненулевым для сложного вещества
    first_h298 = records[0]["H298"]
    check3 = abs(first_h298) > 100
    print(f"3. H298={first_h298} (|H298| > 100): {check3} {'✅' if check3 else '❌'}")

    # 4. S298 должно быть ненулевым
    first_s298 = records[0]["S298"]
    check4 = abs(first_s298) > 10
    print(f"4. S298={first_s298} (|S298| > 10): {check4} {'✅' if check4 else '❌'}")

    # 5. Количество записей должно быть разумным (1-3 для диапазона без фазовых переходов)
    check5 = len(records) <= 3
    print(
        f"5. Количество записей <= 3: {len(records)} <= 3: {check5} {'✅' if check5 else '❌'}"
    )

    print()

    # Итоговая оценка
    all_checks = [check1, covers_start, check3, check4, check5]
    if all(all_checks):
        print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    else:
        print("❌ НЕКОТОРЫЕ ПРОВЕРКИ НЕ ПРОЙДЕНЫ!")
        failed_checks = [i + 1 for i, check in enumerate(all_checks) if not check]
        print(f"Проваленные проверки: {failed_checks}")
        assert False, f"Проверки не пройдены: {failed_checks}"


if __name__ == "__main__":
    test_crcl3_from_real_database()
    test_crcl3_from_real_database()
