"""
Регрессионный тест для проверки исправления выбора записи для Zn при 298K.

Баг: При T=298K выбиралась запись 4 (g, 100-3000K) вместо записи 1 (s, 298.1-692.7K),
потому что Стратегия 3 в RecordRangeBuilder находила запись с наибольшим покрытием
диапазона, не проверяя соответствие фазы ожидаемой для данной температуры.

Исправление: В RecordRangeBuilder.get_compound_records_for_range() добавлена
проверка соответствия фазы в Стратегии 3. Если фаза кандидата не совпадает
с ожидаемой фазой при current_T, приоритет снижается с 3 до 4.

Данные из логов:
- Zn имеет 4 записи:
  1. s: 298.1-692.7K (H298=0, S298=41.63) - ПРАВИЛЬНАЯ для T=298K
  2. l: 692.7-1180K (H298=7, S298=10.57)
  3. g: 298.1-2000K (H298=130, S298=160.98)
  4. g: 100-3000K (H298=130, S298=160.99) - ОШИБОЧНО выбиралась
- Фазовые переходы: Tплавления=693K, Tкипения=1180K
- При T=298K должна быть твёрдая фаза (s), так как T < Tплавления
"""

import logging
import sys
from pathlib import Path

import pandas as pd
import pytest

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.core_logic.phase_transition_detector import PhaseTransitionDetector
from thermo_agents.core_logic.record_range_builder import RecordRangeBuilder
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.sql_builder import SQLBuilder


@pytest.fixture
def test_db_path():
    """Путь к базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
def logger():
    """Создаёт логгер для тестов."""
    return logging.getLogger(__name__)


@pytest.fixture
def record_range_builder(logger):
    """Создаёт экземпляр RecordRangeBuilder."""
    return RecordRangeBuilder(logger)


@pytest.fixture
def phase_detector():
    """Создаёт экземпляр PhaseTransitionDetector."""
    return PhaseTransitionDetector()


@pytest.fixture
def compound_searcher(test_db_path):
    """Создаёт поисковик соединений."""
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(test_db_path)
    return CompoundSearcher(sql_builder, db_connector)


@pytest.fixture
def zn_records(compound_searcher):
    """
    Загружает записи Zn из базы данных.

    Ожидается 4 записи:
    - Запись 1: s, 298.1-692.7K, H298=0, S298=41.63
    - Запись 2: l, 692.7-1180K, H298=7, S298=10.57
    - Запись 3: g, 298.1-2000K, H298=130, S298=160.98
    - Запись 4: g, 100-3000K, H298=130, S298=160.99
    """
    result = compound_searcher.search_compound(formula="Zn", compound_names=["Zinc"])

    records = result.records_found
    assert len(records) >= 4, (
        f"Ожидалось минимум 4 записи для Zn, найдено {len(records)}"
    )

    return records


@pytest.fixture
def zn_dataframe(zn_records):
    """Преобразует записи Zn в DataFrame для RecordRangeBuilder."""
    data = []
    for rec in zn_records:
        data.append(
            {
                "Formula": rec.formula,
                "FirstName": rec.first_name,
                "Phase": rec.phase,
                "Tmin": rec.tmin,
                "Tmax": rec.tmax,
                "H298": rec.h298,
                "S298": rec.s298,
                "f1": rec.f1,
                "f2": rec.f2,
                "f3": rec.f3,
                "f4": rec.f4,
                "f5": rec.f5,
                "f6": rec.f6,
            }
        )
    return pd.DataFrame(data)


class TestZnPhaseSelectionFix:
    """Тесты для проверки правильного выбора фазы для Zn при 298K."""

    def test_zn_has_expected_records(self, zn_records):
        """Проверяет, что Zn имеет ожидаемые записи из логов."""
        # Сортируем записи по фазе и Tmin для упрощения проверки
        sorted_records = sorted(zn_records, key=lambda x: (x.phase, x.tmin))

        # Проверяем наличие записи твёрдой фазы
        solid_records = [r for r in sorted_records if r.phase == "s"]
        assert len(solid_records) >= 1, "Должна быть минимум одна запись твёрдой фазы"

        solid_record = solid_records[0]
        assert abs(solid_record.tmin - 298.1) < 1.0
        assert abs(solid_record.tmax - 692.7) < 1.0

        # Проверяем наличие записи жидкой фазы
        liquid_records = [r for r in sorted_records if r.phase == "l"]
        assert len(liquid_records) >= 1, "Должна быть минимум одна запись жидкой фазы"

        # Проверяем наличие газовых записей
        gas_records = [r for r in sorted_records if r.phase == "g"]
        assert len(gas_records) >= 2, "Должно быть минимум две записи газовой фазы"

        # Проверяем широкую газовую запись (100-3000K)
        wide_gas = [r for r in gas_records if r.tmin < 200]
        assert len(wide_gas) >= 1, "Должна быть газовая запись с Tmin < 200K"

    def test_zn_phase_at_298k(self, phase_detector):
        """Проверяет, что при T=298K ожидается твёрдая фаза."""
        melting = 693.0  # K
        boiling = 1180.0  # K

        expected_phase = phase_detector.get_phase_at_temperature(
            298.0, melting, boiling
        )
        assert expected_phase == "s", (
            f"При T=298K (< Tплавления={melting}K) должна быть фаза 's', получено '{expected_phase}'"
        )

    def test_zn_record_selection_at_298k(self, record_range_builder, zn_dataframe):
        """
        ОСНОВНОЙ ТЕСТ: Проверяет, что при T=298K выбирается запись твёрдой фазы (s),
        а не широкая газовая запись (g, 100-3000K).
        """
        melting = 693.0  # K
        boiling = 1180.0  # K

        # Запрашиваем записи для диапазона 298-400K
        # (небольшой диапазон, чтобы точно попасть в твёрдую фазу)
        t_range = [298.0, 400.0]

        selected_records = record_range_builder.get_compound_records_for_range(
            df=zn_dataframe,
            t_range=t_range,
            melting=melting,
            boiling=boiling,
            tolerance=1.0,
            is_elemental=True,  # Zn - простое вещество
        )

        assert len(selected_records) > 0, "Должна быть выбрана хотя бы одна запись"

        # Первая запись должна быть твёрдой фазы
        first_record = selected_records[0]

        print(f"\n=== Выбранная запись для T=298K ===")
        print(f"Фаза: {first_record['Phase']}")
        print(f"Диапазон: {first_record['Tmin']:.1f}-{first_record['Tmax']:.1f} K")
        print(f"H298: {first_record['H298']:.2f} кДж/моль")
        print(f"S298: {first_record['S298']:.2f} Дж/(моль·K)")

        assert first_record["Phase"] == "s", (
            f"При T=298K должна быть выбрана фаза 's', выбрана '{first_record['Phase']}'"
        )

        # Проверяем температурный диапазон
        assert abs(first_record["Tmin"] - 298.1) < 2.0, (
            f"Tmin должен быть ≈298.1K, получено {first_record['Tmin']:.1f}K"
        )
        assert abs(first_record["Tmax"] - 692.7) < 2.0, (
            f"Tmax должен быть ≈692.7K, получено {first_record['Tmax']:.1f}K"
        )

    def test_zn_record_selection_across_phases(
        self, record_range_builder, zn_dataframe
    ):
        """
        Проверяет правильный выбор записей во всём температурном диапазоне
        с переходами между фазами (s → l → g).
        """
        melting = 693.0  # K
        boiling = 1180.0  # K

        # Запрашиваем записи для широкого диапазона 298-2000K
        # (охватывает все три фазы)
        t_range = [298.0, 2000.0]

        selected_records = record_range_builder.get_compound_records_for_range(
            df=zn_dataframe,
            t_range=t_range,
            melting=melting,
            boiling=boiling,
            tolerance=1.0,
            is_elemental=True,
        )

        assert len(selected_records) >= 3, (
            f"Должно быть минимум 3 записи (s, l, g), получено {len(selected_records)}"
        )

        print(f"\n=== Выбранные записи для диапазона 298-2000K ===")
        for i, rec in enumerate(selected_records):
            print(
                f"Запись {i + 1}: {rec['Phase']}, {rec['Tmin']:.1f}-{rec['Tmax']:.1f} K"
            )

        # Проверяем последовательность фаз
        phases = [rec["Phase"] for rec in selected_records]

        # Первая запись должна быть твёрдой
        assert phases[0] == "s", f"Первая фаза должна быть 's', получено '{phases[0]}'"

        # Должна быть хотя бы одна жидкая фаза
        assert "l" in phases, "Должна быть запись жидкой фазы 'l'"

        # Должна быть хотя бы одна газовая фаза
        assert "g" in phases, "Должна быть запись газовой фазы 'g'"

        # Проверяем, что фазы идут в правильном порядке (s → l → g)
        s_indices = [i for i, p in enumerate(phases) if p == "s"]
        l_indices = [i for i, p in enumerate(phases) if p == "l"]
        g_indices = [i for i, p in enumerate(phases) if p == "g"]

        if s_indices and l_indices:
            assert max(s_indices) < min(l_indices), (
                "Твёрдая фаза должна идти раньше жидкой"
            )

        if l_indices and g_indices:
            assert max(l_indices) < min(g_indices), (
                "Жидкая фаза должна идти раньше газовой"
            )

    def test_zn_no_wide_gas_record_at_low_temp(
        self, record_range_builder, zn_dataframe
    ):
        """
        Проверяет, что широкая газовая запись (100-3000K) НЕ выбирается
        при низких температурах, где ожидается твёрдая фаза.
        """
        melting = 693.0  # K
        boiling = 1180.0  # K

        # Запрашиваем записи для диапазона 250-500K (до плавления)
        t_range = [250.0, 500.0]

        selected_records = record_range_builder.get_compound_records_for_range(
            df=zn_dataframe,
            t_range=t_range,
            melting=melting,
            boiling=boiling,
            tolerance=1.0,
            is_elemental=True,
        )

        # Проверяем, что НЕ выбрана широкая газовая запись
        for rec in selected_records:
            if rec["Phase"] == "g":
                # Если выбрана газовая запись, она не должна быть широкой (100-3000K)
                assert rec["Tmin"] > 200, (
                    f"Не должна быть выбрана широкая газовая запись (Tmin={rec['Tmin']:.1f}K < 200K) при T=250-500K"
                )

        # Все записи должны быть твёрдой фазы (диапазон до плавления)
        phases = [rec["Phase"] for rec in selected_records]
        assert all(p == "s" for p in phases), (
            f"Все записи должны быть фазы 's' для T=250-500K, получено {set(phases)}"
        )

    def test_zn_strategy_3_priority_with_matching_phase(
        self, record_range_builder, zn_dataframe
    ):
        """
        Проверяет, что в Стратегии 3 запись с правильной фазой имеет приоритет
        над записью с неправильной фазой (даже если покрывает больший диапазон).
        """
        melting = 693.0  # K
        boiling = 1180.0  # K

        # Запрашиваем записи с температуры 298K
        # Обе записи покрывают эту температуру:
        # - s: 298.1-692.7K (правильная фаза)
        # - g: 100-3000K (неправильная фаза, но шире)
        t_range = [298.0, 350.0]

        selected_records = record_range_builder.get_compound_records_for_range(
            df=zn_dataframe,
            t_range=t_range,
            melting=melting,
            boiling=boiling,
            tolerance=1.0,
            is_elemental=True,
        )

        # Должна быть выбрана запись с фазой 's', а не 'g'
        assert len(selected_records) > 0
        first_record = selected_records[0]

        assert first_record["Phase"] == "s", (
            f"Должна быть выбрана фаза 's' (приоритет 3), а не '{first_record['Phase']}' (приоритет 4)"
        )

        print(f"\n=== Проверка приоритета Стратегии 3 ===")
        print(
            f"Выбрана запись: {first_record['Phase']}, {first_record['Tmin']:.1f}-{first_record['Tmax']:.1f} K"
        )
        print("Запись с правильной фазой имеет приоритет ✓")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
