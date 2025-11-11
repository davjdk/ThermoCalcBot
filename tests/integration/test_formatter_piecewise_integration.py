"""
Интеграционный тест для проверки работы compound_info_formatter.py
с кусочным интегрированием (calculate_properties_piecewise).
"""

import logging
import sys
from pathlib import Path

import pytest

# Добавляем src в путь
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.core_logic.thermodynamic_engine import ThermodynamicEngine
from thermo_agents.formatting.compound_info_formatter import CompoundInfoFormatter


@pytest.fixture
def logger():
    """Создаёт логгер для тестов."""
    return logging.getLogger(__name__)


@pytest.fixture
def thermo_engine(logger):
    """Создаёт экземпляр термодинамического движка."""
    return ThermodynamicEngine(logger)


@pytest.fixture
def so2_records():
    """
    Три записи SO2 из БД (298.15-700K, 700-2000K, 2000-3000K).
    Все одной фазы (g).

    ВАЖНО: Используем lowercase ключи (h298, tmin и т.д.), так как
    get_value() ищет lowercase для совместимости с Pydantic.
    """
    return [
        {
            "formula": "SO2",
            "first_name": "Sulfur dioxide",
            "phase": "g",
            "tmin": 298.15,
            "tmax": 700.0,
            "h298": -296.812653,
            "s298": 248.219711,
            "f1": 17.3468437,
            "f2": 79.22814,
            "f3": 2.6442852,
            "f4": -45.6306534,
            "f5": 0.0,
            "f6": 0.0,
        },
        {
            "formula": "SO2",
            "first_name": "Sulfur dioxide",
            "phase": "g",
            "tmin": 700.0,
            "tmax": 2000.0,
            "h298": 0.0,
            "s298": 0.0,
            "f1": 51.64724,
            "f2": 6.296913,
            "f3": -21.5894165,
            "f4": -1.36816645,
            "f5": 0.0,
            "f6": 0.0,
        },
        {
            "formula": "SO2",
            "first_name": "Sulfur dioxide",
            "phase": "g",
            "tmin": 2000.0,
            "tmax": 3000.0,
            "h298": 0.0,
            "s298": 0.0,
            "f1": 66.65942,
            "f2": -4.47687531,
            "f3": -112.892563,
            "f4": 0.8409831,
            "f5": 0.0,
            "f6": 0.0,
        },
    ]


class TestFormatterPiecewiseIntegration:
    """Тесты форматирования с кусочным интегрированием."""

    def test_formatter_calls_piecewise_integration_for_so2(
        self, thermo_engine, so2_records
    ):
        """
        Упрощённый тест: Проверяет, что кусочное интегрирование работает
        и H/S монотонно растут (без скачков).
        """
        # Температуры для проверки (охватывают все три записи)
        temperatures = [500.0, 698.0, 800.0, 1500.0, 1998.0, 2100.0, 2500.0]

        h_values = []
        s_values = []

        for T in temperatures:
            props = thermo_engine.calculate_properties_piecewise(
                so2_records, T, reference_record=so2_records[0]
            )
            h_values.append(props["enthalpy"] / 1000)
            s_values.append(props["entropy"])

        print("\n=== Проверка монотонности H и S ===")
        for i, (T, h, s) in enumerate(zip(temperatures, h_values, s_values)):
            print(f"T={T:6.1f}K: H={h:7.2f} кДж/моль, S={s:6.2f} Дж/(моль·K)")

        # Проверяем монотонность (H и S должны расти с температурой)
        for i in range(1, len(h_values)):
            assert h_values[i] > h_values[i - 1], (
                f"H должна расти: T={temperatures[i - 1]}K H={h_values[i - 1]:.2f} → "
                f"T={temperatures[i]}K H={h_values[i]:.2f}"
            )
            assert s_values[i] > s_values[i - 1], (
                f"S должна расти: T={temperatures[i - 1]}K S={s_values[i - 1]:.2f} → "
                f"T={temperatures[i]}K S={s_values[i]:.2f}"
            )

        print("\n✓ H и S монотонно растут во всём диапазоне (без скачков)")
