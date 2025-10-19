"""
Unit-тесты для CompoundDataFormatter с многофазными данными.
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from thermo_agents.models.search import (
    DatabaseRecord, PhaseSegment, PhaseTransition, MultiPhaseProperties
)
from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator


@pytest.fixture
def calculator():
    """Создать экземпляр калькулятора для тестов."""
    return ThermodynamicCalculator()


@pytest.fixture
def formatter(calculator):
    """Создать форматтер веществ."""
    return CompoundDataFormatter(calculator)


@pytest.fixture
def sio2_multi_phase_result():
    """Результат многофазного расчёта для SiO2 с несколькими фазами."""
    # Первый сегмент - α-кварц
    segment1 = PhaseSegment(
        record=DatabaseRecord(
            formula="SiO2", phase="s", tmin=298.0, tmax=847.0,
            h298=-910700.0, s298=41.460,
            f1=46.018, f2=11.860, f3=-1.505, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1996.0, tboil=3680.0, reliability_class=1,
            first_name="Silicon dioxide (α-quartz)"
        ),
        T_start=298.0, T_end=847.0,
        H_start=-910700.0, S_start=41.460,
        delta_H=12000.0, delta_S=18.5,
        is_transition_boundary=False
    )

    # Второй сегмент - продолжение α-кварца
    segment2 = PhaseSegment(
        record=DatabaseRecord(
            formula="SiO2", phase="s", tmin=847.0, tmax=1996.0,
            h298=0.0, s298=0.0,  # Продолжающаяся запись
            f1=55.980, f2=15.420, f3=-2.650, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1996.0, tboil=3680.0, reliability_class=1,
            first_name="Silicon dioxide"
        ),
        T_start=847.0, T_end=1996.0,
        H_start=-898700.0, S_start=59.96,
        delta_H=45000.0, delta_S=35.2,
        is_transition_boundary=False
    )

    # Третий сегмент - жидкая фаза
    segment3 = PhaseSegment(
        record=DatabaseRecord(
            formula="SiO2", phase="l", tmin=1996.0, tmax=4000.0,
            h298=-744000.0, s298=95.0,
            f1=80.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1996.0, tboil=3680.0, reliability_class=1,
            first_name="Silicon dioxide (liquid)"
        ),
        T_start=1996.0, T_end=2500.0,
        H_start=-853700.0, S_start=95.16,
        delta_H=40000.0, delta_S=20.0,
        is_transition_boundary=True
    )

    # Фазовый переход плавления
    transition = PhaseTransition(
        temperature=1996.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=50.0,
        delta_S_transition=25.1
    )

    return MultiPhaseProperties(
        T_target=2500.0,
        H_final=-813700.0,
        S_final=115.16,
        G_final=-1_102_650.0,
        Cp_final=80.0,
        segments=[segment1, segment2, segment3],
        phase_transitions=[transition],
        temperature_path=[298.0, 847.0, 1996.0, 2500.0],
        H_path=[-910700.0, -898700.0, -853700.0, -813700.0],
        S_path=[41.460, 59.96, 95.16, 115.16],
        warnings=[]
    )


def test_format_sio2_compound_data_multi_phase(formatter, sio2_multi_phase_result):
    """Тест форматирования данных для SiO2 с несколькими сегментами."""
    result = formatter.format_compound_data_multi_phase(
        formula="SiO2",
        compound_name="Silicon dioxide",
        multi_phase_result=sio2_multi_phase_result
    )

    # Проверки содержимого
    assert "SiO2 — Silicon dioxide" in result
    assert "[Сегмент 1]" in result
    assert "[Сегмент 2]" in result
    assert "[Сегмент 3]" in result

    # Проверки диапазонов температур
    assert "298-847 K" in result
    assert "847-1996 K" in result
    assert "1996-2500 K" in result

    # Проверки фаз
    assert "Фаза: s" in result
    assert "Фаза: l" in result

    # Проверки H298
    assert "-910.700 кДж/моль" in result  # Первый сегмент
    assert "(накопленное)" in result  # Второй сегмент

    # Проверки Cp коэффициентов
    assert "46.018, 11.860" in result  # Первый сегмент

    # Проверки фазового перехода
    assert "ФАЗОВЫЙ ПЕРЕХОД при 1996K" in result
    assert "s → l" in result
    assert "melting" in result or "плавление" in result

    # Проверки ΔH перехода
    assert "ΔH_melting: 50.00 кДж/моль" in result or "ΔH_плавление" in result


def test_format_compound_data_with_no_transitions(formatter):
    """Тест форматирования данных без фазовых переходов."""
    # Создаём простой сегмент без переходов
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="Al2O3", phase="s", tmin=298.0, tmax=2000.0,
            h298=-1675700.0, s298=50.92,
            f1=120.5, f2=12.8, f3=-3.2, f4=0.0, f5=0.0, f6=0.0,
            tmelt=2345.0, tboil=3800.0, reliability_class=1,
            first_name="Aluminum oxide"
        ),
        T_start=298.0, T_end=1500.0,
        H_start=-1675700.0, S_start=50.92,
        delta_H=80000.0, delta_S=40.5,
        is_transition_boundary=False
    )

    mp_result = MultiPhaseProperties(
        T_target=1500.0,
        H_final=-1595700.0,
        S_final=91.42,
        Cp_final=145.2,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 1500.0],
        H_path=[-1675700.0, -1595700.0],
        S_path=[50.92, 91.42],
        warnings=[]
    )

    result = formatter.format_compound_data_multi_phase(
        formula="Al2O3",
        compound_name="Aluminum oxide",
        multi_phase_result=mp_result
    )

    assert "Al2O3 — Aluminum oxide" in result
    assert "[Сегмент 1]" in result
    assert "298-1500 K" in result
    assert "-1675.700 кДж/моль" in result
    assert "ФАЗОВЫЙ ПЕРЕХОД" not in result


def test_format_compound_data_with_reliability_class(formatter):
    """Тест форматирования данных с разным классом надёжности."""
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="Fe", phase="s", tmin=298.0, tmax=1811.0,
            h298=0.0, s298=27.28,
            f1=20.0, f2=12.0, f3=-2.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1811.0, tboil=3134.0, reliability_class=2,  # Средняя надёжность
            first_name="Iron"
        ),
        T_start=298.0, T_end=1000.0,
        H_start=0.0, S_start=27.28,
        delta_H=15000.0, delta_S=12.5,
        is_transition_boundary=False
    )

    mp_result = MultiPhaseProperties(
        T_target=1000.0,
        H_final=15000.0,
        S_final=39.78,
        Cp_final=30.0,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 1000.0],
        H_path=[0.0, 15000.0],
        S_path=[27.28, 39.78],
        warnings=[]
    )

    result = formatter.format_compound_data_multi_phase(
        formula="Fe",
        compound_name="Iron",
        multi_phase_result=mp_result
    )

    assert "Надёжность: 2 (средняя)" in result


def test_format_compound_data_cp_coefficients_formatting(formatter):
    """Тест форматирования Cp коэффициентов."""
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="CaO", phase="s", tmin=298.0, tmax=3200.0,
            h298=-635089.0, s298=38.074,
            f1=50.0, f2=2.0, f3=-0.5, f4=0.1, f5=0.0, f6=0.0,
            tmelt=3172.0, tboil=4000.0, reliability_class=1,
            first_name="Calcium oxide"
        ),
        T_start=298.0, T_end=1000.0,
        H_start=-635089.0, S_start=38.074,
        delta_H=25000.0, delta_S=20.0,
        is_transition_boundary=False
    )

    mp_result = MultiPhaseProperties(
        T_target=1000.0,
        H_final=-610089.0,
        S_final=58.074,
        Cp_final=52.0,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 1000.0],
        H_path=[-635089.0, -610089.0],
        S_path=[38.074, 58.074],
        warnings=[]
    )

    result = formatter.format_compound_data_multi_phase(
        formula="CaO",
        compound_name="Calcium oxide",
        multi_phase_result=mp_result
    )

    # Проверяем форматирование Cp коэффициентов
    assert "Cp коэффициенты: [50.000, 2.000, -0.500, 0.100, 0.000, 0.000]" in result


def test_format_compound_data_source_information(formatter):
    """Тест форматирования информации об источнике данных."""
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="MgO", phase="s", tmin=298.0, tmax=3098.0,
            h298=-601601.0, s298=26.95,
            f1=42.0, f2=5.0, f3=-1.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=3250.0, tboil=4000.0, reliability_class=1,
            first_name="Magnesium oxide (NIST data)"
        ),
        T_start=298.0, T_end=800.0,
        H_start=-601601.0, S_start=26.95,
        delta_H=18000.0, delta_S=15.0,
        is_transition_boundary=False
    )

    mp_result = MultiPhaseProperties(
        T_target=800.0,
        H_final=-583601.0,
        S_final=41.95,
        Cp_final=46.5,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 800.0],
        H_path=[-601601.0, -583601.0],
        S_path=[26.95, 41.95],
        warnings=[]
    )

    result = formatter.format_compound_data_multi_phase(
        formula="MgO",
        compound_name="Magnesium oxide",
        multi_phase_result=mp_result
    )

    assert "Источник: Magnesium oxide (NIST data)" in result