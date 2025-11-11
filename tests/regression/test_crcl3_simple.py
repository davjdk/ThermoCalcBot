"""
Простой тест для проверки исправления с продакшен данными CrCl3.
"""

import logging
import pandas as pd
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder


def test_crcl3_simple():
    """
    Простой тест с реальными данными.
    """
    # Реальные данные из продакшена
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

    # Тест с tolerance=1.0 (стандартный)
    records = builder.get_compound_records_for_range(
        df=df,
        t_range=[298.0, 1098.0],
        melting=1425.0,
        boiling=None,
        tolerance=1.0,
        is_elemental=False
    )

    print(f"Выбрано записей: {len(records)}")
    for i, rec in enumerate(records):
        print(f"Запись {i+1}: фаза={rec['Phase']}, Tmin={rec['Tmin']}, H298={rec['H298']}")

    # Проверки
    assert len(records) > 0, "Не выбрано ни одной записи"
    assert records[0]["Phase"] == "s", f"Фаза первой записи '{records[0]['Phase']}' != 's'"
    assert records[0]["Tmin"] <= 298.0 + 1.0, f"Tmin={records[0]['Tmin']} не покрывает 298K с tolerance=1.0"
    assert abs(records[0]["H298"]) > 500, f"H298={records[0]['H298']} близко к нулю"

    print("SUCCESS: All checks passed!")


if __name__ == "__main__":
    test_crcl3_simple()