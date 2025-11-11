"""
Интеграционный тест для проверки исправления проблемы CrCl3.

Проверяет, что orchestrator._process_compound_data использует
RecordRangeBuilder для выбора записей (не весь DataFrame).
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from thermo_agents.models.extraction import ExtractedReactionParameters
from thermo_agents.orchestrator import ThermoOrchestrator, ThermoOrchestratorConfig


@pytest.mark.asyncio
async def test_orchestrator_crcl3_uses_record_range_builder():
    """
    Тест проверяет, что orchestrator выбирает записи через RecordRangeBuilder,
    а не использует весь DataFrame.

    Проблема: До исправления orchestrator передавал все 37 записей из DataFrame.
    Решение: Теперь вызывается RecordRangeBuilder.get_compound_records_for_range().
    """
    # Создаём конфигурацию
    config = ThermoOrchestratorConfig(
        db_path=Path("data/thermo_data.db"),
        llm_api_key="test_key",
    )

    # Создаём orchestrator
    orchestrator = ThermoOrchestrator(config)

    # Параметры запроса (как от пользователя)
    params = ExtractedReactionParameters(
        query_type="compound_data",
        balanced_equation="",  # Для compound_data не требуется
        all_compounds=["CrCl3"],
        reactants=[],  # Для compound_data не требуется
        products=[],  # Для compound_data не требуется
        compound_names={"CrCl3": ["Chromium(III) chloride"]},
        temperature_range_k=(298.0, 1098.0),
        temperature_step_k=50,
        extraction_confidence=1.0,
    )

    # Мокируем compound_loader, чтобы вернуть 37 записей (как в продакшене)
    mock_df = create_mock_crcl3_dataframe()

    with patch.object(
        orchestrator.compound_loader,
        "get_raw_compound_data_with_metadata",
        return_value=(mock_df, False, 1),  # (df, is_yaml_cache, search_stage)
    ):
        # Вызываем метод
        result = await orchestrator._process_compound_data(params)

    # ПРОВЕРКИ

    # 1. В результате НЕ должно быть "Использовано записей: 37"
    assert "Использовано записей: 37" not in result, (
        "Ошибка: используется весь DataFrame (37 записей) вместо выбранных!"
    )

    # 2. Должно быть "Использовано записей: 1" или "2" (не больше 3)
    assert (
        "Использовано записей: 1" in result
        or "Использовано записей: 2" in result
        or "Использовано записей: 3" in result
    ), f"Ожидалось 1-3 записи, но в результате: {result[:500]}"

    # 3. H298 должно быть около -544 (правильное значение для CrCl3)
    assert "-544" in result or "-557" in result or "-570" in result, (
        f"H298 должно быть около -544, но в результате: {result[:500]}"
    )

    # 4. H298 НЕ должно быть 0.060 (неправильное значение фазы 'l')
    assert "0.060" not in result and "60" not in result[:200], (
        "Ошибка: выбрана фаза 'l' (H298=60) вместо 's' (H298=-544)!"
    )

    print("✅ Тест пройден: orchestrator использует RecordRangeBuilder!")


def create_mock_crcl3_dataframe():
    """
    Создаёт mock DataFrame с 37 записями CrCl3 (как в продакшене).
    """
    import pandas as pd

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
        "MeltingPoint": [],
        "BoilingPoint": [],
        "Reference": [],
        "ReliabilityClass": [],
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
        data["MeltingPoint"].append(1425)
        data["BoilingPoint"].append(0)
        data["Reference"].append("Glushko 94")
        data["ReliabilityClass"].append(1)

    # Фаза 'g' — 19 записей (упрощаем до 6)
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
        data["MeltingPoint"].append(1425)
        data["BoilingPoint"].append(0)
        data["Reference"].append("Glushko 94")
        data["ReliabilityClass"].append(1)

    # Фаза 's' — 7 записей
    h298_values = [-544, -544, -544, -557, -570, -570, -556]
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
        data["MeltingPoint"].append(1425)
        data["BoilingPoint"].append(0)
        data["Reference"].append("Glushko 94")
        data["ReliabilityClass"].append(1)

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
        data["MeltingPoint"].append(1425)
        data["BoilingPoint"].append(0)
        data["Reference"].append("Glushko 94")
        data["ReliabilityClass"].append(1)

    return pd.DataFrame(data)


@pytest.mark.asyncio
async def test_is_elemental_method():
    """
    Тест для метода _is_elemental.
    """
    config = ThermoOrchestratorConfig(
        db_path=Path("data/thermo_data.db"),
        llm_api_key="test_key",
    )
    orchestrator = ThermoOrchestrator(config)

    # Простые вещества (элементы)
    assert orchestrator._is_elemental("O2") is True
    assert orchestrator._is_elemental("H2") is True
    assert orchestrator._is_elemental("C") is True
    assert orchestrator._is_elemental("Fe") is True
    assert orchestrator._is_elemental("Cl2") is True
    assert orchestrator._is_elemental("S") is True

    # Сложные вещества
    assert orchestrator._is_elemental("H2O") is False
    assert orchestrator._is_elemental("CO2") is False
    assert orchestrator._is_elemental("CrCl3") is False
    assert orchestrator._is_elemental("Fe2O3") is False
    assert orchestrator._is_elemental("NaCl") is False

    print("✅ Тест _is_elemental пройден!")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_orchestrator_crcl3_uses_record_range_builder())
    asyncio.run(test_is_elemental_method())
    asyncio.run(test_is_elemental_method())
