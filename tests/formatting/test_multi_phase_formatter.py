"""
Unit-тесты для многофазного форматтера.
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from thermo_agents.formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from thermo_agents.models.search import (
    DatabaseRecord, PhaseSegment, PhaseTransition, MultiPhaseProperties
)
from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator


@pytest.fixture
def calculator():
    """Создать экземпляр калькулятора для тестов."""
    return ThermodynamicCalculator()


@pytest.fixture
def compound_formatter(calculator):
    """Создать форматтер веществ."""
    return CompoundDataFormatter(calculator)


@pytest.fixture
def reaction_formatter(calculator):
    """Создать форматтер реакций."""
    return ReactionCalculationFormatter(calculator)


@pytest.fixture
def feo_multi_phase_result():
    """Результат многофазного расчёта для FeO."""
    # Создание сегментов
    segment1 = PhaseSegment(
        record=DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265053.0, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1,
            first_name="Iron(II) oxide"
        ),
        T_start=298.0, T_end=600.0,
        H_start=-265053.0, S_start=59.807,
        delta_H=15420.0, delta_S=36.85,
        is_transition_boundary=False
    )

    segment2 = PhaseSegment(
        record=DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=1650.0,
            h298=0.0, s298=0.0,  # Продолжающаяся запись
            f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1,
            first_name="Iron(II) oxide"
        ),
        T_start=600.0, T_end=1650.0,
        H_start=-249630.0, S_start=96.66,
        delta_H=104120.0, delta_S=89.42,
        is_transition_boundary=True  # Сделаем этот сегмент граничным
    )

    segment5 = PhaseSegment(
        record=DatabaseRecord(
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24058.0, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1,
            first_name="Iron(II) oxide"
        ),
        T_start=1650.0, T_end=1700.0,
        H_start=-145510.0, S_start=186.08,
        delta_H=3410.0, delta_S=2.05,
        is_transition_boundary=False
    )

    # Фазовый переход (только плавление)
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    return MultiPhaseProperties(
        T_target=1700.0,
        H_final=-142100.0,
        S_final=188.13,
        G_final=-461920.0,
        Cp_final=68.199,
        segments=[segment1, segment2, segment5],
        phase_transitions=[transition],
        temperature_path=[298.0, 600.0, 1650.0, 1700.0],
        H_path=[-265053.0, -249630.0, -145510.0, -142100.0],
        S_path=[59.807, 96.66, 186.08, 188.13],
        warnings=[]
    )


def test_format_compound_data_multi_phase(compound_formatter, feo_multi_phase_result):
    """Тест форматирования раздела 'Данные веществ'."""
    result = compound_formatter.format_compound_data_multi_phase(
        formula="FeO",
        compound_name="Iron(II) oxide",
        multi_phase_result=feo_multi_phase_result
    )

    # Проверки содержимого
    assert "FeO — Iron(II) oxide" in result
    assert "[Сегмент 1]" in result
    assert "[Сегмент 2]" in result
    assert "[Сегмент 3]" in result
    assert "298-600 K" in result
    assert "600-1650 K" in result
    assert "1650-1700 K" in result
    assert "-265.053 кДж/моль" in result
    assert "(накопленное)" in result
    assert "ФАЗОВЫЙ ПЕРЕХОД при 1650K" in result
    assert "s → l" in result
    assert "melting" in result or "плавление" in result


def test_format_comment_column_with_transition(reaction_formatter, feo_multi_phase_result):
    """Тест форматирования колонки 'Комментарий' с переходом."""
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    mp_result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[transition],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )

    comment = reaction_formatter.format_comment_column(
        T=1650.0,
        compounds_multi_phase={"FeO": mp_result}
    )

    assert "FeO" in comment
    assert "s→l" in comment
    assert "плавление" in comment or "melting" in comment
    assert "ΔH=" in comment


def test_format_comment_column_no_transition(reaction_formatter):
    """Тест форматирования колонки 'Комментарий' без переходов."""
    mp_result = MultiPhaseProperties(
        T_target=500.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )

    comment = reaction_formatter.format_comment_column(
        T=500.0,
        compounds_multi_phase={"H2O": mp_result}
    )

    assert comment == "", "Комментарий должен быть пустым без переходов"


def test_format_metadata(reaction_formatter, feo_multi_phase_result):
    """Тест форматирования метаданных."""
    # Создадим второй результат для теста
    sio2_mp = MultiPhaseProperties(
        T_target=1000.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )

    metadata = reaction_formatter.format_metadata(
        compounds_multi_phase={"FeO": feo_multi_phase_result, "SiO2": sio2_mp}
    )

    assert "Использовано сегментов расчёта:" in metadata
    assert "FeO" in metadata
    assert "SiO2" in metadata
    assert "Фазовых переходов обнаружено:" in metadata
    assert "Шаг по температуре:" in metadata


def test_format_results_table_with_transitions(reaction_formatter):
    """Тест форматирования таблицы результатов с переходами."""
    temperatures = [298, 600, 1650, 1700]
    delta_H = [-82.61, -86.15, -91.45, -109.87]
    delta_S = [-11.83, -10.92, -8.76, -6.78]
    delta_G = [-79.08, -80.44, -76.79, -98.32]

    # Создадим простой результат с переходом
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    mp_result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[transition],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )

    table = reaction_formatter.format_results_table_with_transitions(
        temperatures=temperatures,
        delta_H=delta_H,
        delta_S=delta_S,
        delta_G=delta_G,
        compounds_multi_phase={"FeO": mp_result}
    )

    # Проверки заголовков таблицы
    assert "T(K)" in table
    assert "ΔH°(кДж/моль)" in table
    assert "ΔS°(Дж/(К·моль))" in table
    assert "ΔG°(кДж/моль)" in table
    assert "Комментарий" in table

    # Проверка наличия комментария для температуры перехода
    assert "1650" in table
    assert "плавление" in table or "melting" in table


def test_format_transition_comment_melting(reaction_formatter):
    """Тест форматирования комментария для плавления."""
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    comment = reaction_formatter._format_transition_comment("FeO", transition)

    assert "FeO: s→l" in comment
    assert "плавление" in comment
    assert "ΔH=+32.0 кДж/моль" in comment


def test_format_transition_comment_boiling(reaction_formatter):
    """Тест форматирования комментария для кипения."""
    transition = PhaseTransition(
        temperature=373.0,
        from_phase="l",
        to_phase="g",
        transition_type="boiling",
        delta_H_transition=40.7,
        delta_S_transition=109.1
    )

    comment = reaction_formatter._format_transition_comment("H2O", transition)

    assert "H2O: l→g" in comment
    assert "кипение" in comment
    assert "ΔH=+40.7 кДж/моль" in comment


def test_describe_phases_solid_only(reaction_formatter):
    """Тест описания фаз для только твёрдой фазы."""
    description = reaction_formatter._describe_phases(["s"])
    assert description == "твёрдых"


def test_describe_phases_multiple(reaction_formatter):
    """Тест описания фаз для нескольких фаз."""
    description = reaction_formatter._describe_phases(["s", "l"])
    assert "твёрдых" in description
    assert "жидких" in description
    assert " + " in description


def test_format_transition_comment_unknown_type(reaction_formatter):
    """Тест форматирования комментария для неизвестного типа перехода."""
    transition = PhaseTransition(
        temperature=1000.0,
        from_phase="s1",
        to_phase="s2",
        transition_type="unknown",
        delta_H_transition=5.0,
        delta_S_transition=5.0
    )

    comment = reaction_formatter._format_transition_comment("C", transition)

    assert "C: s1→s2" in comment
    assert "unknown" in comment
    assert "ΔH=+5.0 кДж/моль" in comment