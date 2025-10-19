"""
Unit-тесты для ReactionCalculationFormatter с фазовыми переходами.
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

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
def formatter(calculator):
    """Создать форматтер реакций."""
    return ReactionCalculationFormatter(calculator)


@pytest.fixture
def cao_multi_phase():
    """Результат многофазного расчёта для CaO."""
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="CaO", phase="s", tmin=298.0, tmax=3200.0,
            h298=-635089.0, s298=38.074,
            f1=50.0, f2=2.0, f3=-0.5, f4=0.1, f5=0.0, f6=0.0,
            tmelt=3172.0, tboil=4000.0, reliability_class=1,
            first_name="Calcium oxide"
        ),
        T_start=298.0, T_end=1800.0,
        H_start=-635089.0, S_start=38.074,
        delta_H=60000.0, delta_S=35.0,
        is_transition_boundary=False
    )

    return MultiPhaseProperties(
        T_target=1800.0,
        H_final=-575089.0,
        S_final=73.074,
        Cp_final=53.5,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 1800.0],
        H_path=[-635089.0, -575089.0],
        S_path=[38.074, 73.074],
        warnings=[]
    )


@pytest.fixture
def sio2_with_transitions():
    """Результат многофазного расчёта для SiO2 с переходами."""
    segment1 = PhaseSegment(
        record=DatabaseRecord(
            formula="SiO2", phase="s", tmin=298.0, tmax=523.0,
            h298=-910700.0, s298=41.460,
            f1=46.018, f2=11.860, f3=-1.505, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1996.0, tboil=3680.0, reliability_class=1,
            first_name="Silicon dioxide (α-quartz)"
        ),
        T_start=298.0, T_end=523.0,
        H_start=-910700.0, S_start=41.460,
        delta_H=8000.0, delta_S=15.0,
        is_transition_boundary=False
    )

    segment2 = PhaseSegment(
        record=DatabaseRecord(
            formula="SiO2", phase="s", tmin=523.0, tmax=847.0,
            h298=0.0, s298=0.0,  # Продолжающаяся запись
            f1=55.980, f2=15.420, f3=-2.650, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1996.0, tboil=3680.0, reliability_class=1,
            first_name="Silicon dioxide (cristobalite)"
        ),
        T_start=523.0, T_end=847.0,
        H_start=-902700.0, S_start=56.460,
        delta_H=12000.0, delta_S=20.0,
        is_transition_boundary=False
    )

    # Фазовый переход при 523K
    transition1 = PhaseTransition(
        temperature=523.0,
        from_phase="s",
        to_phase="s",
        transition_type="unknown",
        delta_H_transition=2.5,
        delta_S_transition=4.8
    )

    return MultiPhaseProperties(
        T_target=847.0,
        H_final=-890700.0,
        S_final=76.460,
        Cp_final=61.2,
        segments=[segment1, segment2],
        phase_transitions=[transition1],
        temperature_path=[298.0, 523.0, 847.0],
        H_path=[-910700.0, -902700.0, -890700.0],
        S_path=[41.460, 56.460, 76.460],
        warnings=[]
    )


@pytest.fixture
def casio3_multi_phase():
    """Результат многофазного расчёта для CaSiO3."""
    segment = PhaseSegment(
        record=DatabaseRecord(
            formula="CaSiO3", phase="s", tmin=298.0, tmax=1817.0,
            h298=-1628398.0, s298=87.362,
            f1=100.0, f2=8.0, f3=-2.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1817.0, tboil=3000.0, reliability_class=1,
            first_name="Calcium silicate (pseudowollastonite)"
        ),
        T_start=298.0, T_end=1800.0,
        H_start=-1628398.0, S_start=87.362,
        delta_H=100000.0, delta_S=60.0,
        is_transition_boundary=False
    )

    return MultiPhaseProperties(
        T_target=1800.0,
        H_final=-1528398.0,
        S_final=147.362,
        Cp_final=114.5,
        segments=[segment],
        phase_transitions=[],
        temperature_path=[298.0, 1800.0],
        H_path=[-1628398.0, -1528398.0],
        S_path=[87.362, 147.362],
        warnings=[]
    )


def test_format_comment_column_polymorphic_transition(formatter, sio2_with_transitions):
    """Тест форматирования комментария для полиморфного перехода."""
    comment = formatter.format_comment_column(
        T=523.0,
        compounds_multi_phase={"SiO2": sio2_with_transitions}
    )

    assert "SiO2: s→s" in comment
    assert "unknown" in comment
    assert "ΔH=+2.5 кДж/моль" in comment


def test_format_comment_column_no_transition_at_temperature(formatter, cao_multi_phase):
    """Тест форматирования комментария при отсутствии перехода."""
    comment = formatter.format_comment_column(
        T=1000.0,
        compounds_multi_phase={"CaO": cao_multi_phase}
    )

    assert comment == ""


def test_format_comment_column_multiple_compounds(formatter, cao_multi_phase, sio2_with_transitions):
    """Тест форматирования комментария для нескольких соединений."""
    compounds = {
        "CaO": cao_multi_phase,
        "SiO2": sio2_with_transitions
    }

    comment = formatter.format_comment_column(
        T=523.0,
        compounds_multi_phase=compounds
    )

    assert "SiO2: s→s" in comment
    assert "polymorphic" in comment


def test_format_comment_column_record_change(formatter):
    """Тест форматирования комментария для смены записи."""
    # Создадим сегмент с границей смены записи
    segment1 = PhaseSegment(
        record=DatabaseRecord(
            formula="Fe2O3", phase="s", tmin=298.0, tmax=950.0,
            h298=-822200.0, s298=87.4,
            f1=100.0, f2=20.0, f3=-5.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1839.0, tboil=3000.0, reliability_class=1,
            first_name="Iron(III) oxide"
        ),
        T_start=298.0, T_end=950.0,
        H_start=-822200.0, S_start=87.4,
        delta_H=40000.0, delta_S=30.0,
        is_transition_boundary=True  # Граница смены записи
    )

    segment2 = PhaseSegment(
        record=DatabaseRecord(
            formula="Fe2O3", phase="s", tmin=950.0, tmax=1839.0,
            h298=0.0, s298=0.0,  # Продолжающаяся запись
            f1=120.0, f2=25.0, f3=-6.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1839.0, tboil=3000.0, reliability_class=1,
            first_name="Iron(III) oxide"
        ),
        T_start=950.0, T_end=1500.0,
        H_start=-782200.0, S_start=117.4,
        delta_H=50000.0, delta_S=35.0,
        is_transition_boundary=False
    )

    mp_result = MultiPhaseProperties(
        T_target=1500.0,
        H_final=-732200.0,
        S_final=152.4,
        Cp_final=130.0,
        segments=[segment1, segment2],
        phase_transitions=[],
        temperature_path=[298.0, 950.0, 1500.0],
        H_path=[-822200.0, -782200.0, -732200.0],
        S_path=[87.4, 117.4, 152.4],
        warnings=[]
    )

    comment = formatter.format_comment_column(
        T=950.0,
        compounds_multi_phase={"Fe2O3": mp_result}
    )

    assert "Fe2O3: s→s (смена записи)" in comment


def test_format_results_table_with_multiple_transitions(formatter):
    """Тест форматирования таблицы с несколькими переходами."""
    temperatures = [298, 523, 600, 847]
    delta_H = [-82.61, -86.15, -88.50, -92.17]
    delta_S = [-11.83, -10.92, -10.50, -9.22]
    delta_G = [-79.08, -80.44, -82.23, -78.59]

    # Создадим результат с переходом
    transition = PhaseTransition(
        temperature=523.0,
        from_phase="s",
        to_phase="s",
        transition_type="unknown",
        delta_H_transition=2.5,
        delta_S_transition=4.8
    )

    mp_result = MultiPhaseProperties(
        T_target=847.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[transition],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )

    table = formatter.format_results_table_with_transitions(
        temperatures=temperatures,
        delta_H=delta_H,
        delta_S=delta_S,
        delta_G=delta_G,
        compounds_multi_phase={"SiO2": mp_result}
    )

    # Проверяем, что таблица содержит комментарий для температуры перехода
    lines = table.split('\n')
    transition_line = None
    for line in lines:
        if '523' in line:
            transition_line = line
            break

    assert transition_line is not None
    assert "polymorphic" in transition_line


def test_format_metadata_multiple_compounds(formatter, cao_multi_phase, sio2_with_transitions, casio3_multi_phase):
    """Тест форматирования метаданных для нескольких соединений."""
    compounds = {
        "CaO": cao_multi_phase,
        "SiO2": sio2_with_transitions,
        "CaSiO3": casio3_multi_phase
    }

    metadata = formatter.format_metadata(compounds)

    # Проверки сегментов
    assert "Использовано сегментов расчёта:" in metadata
    assert "CaO(1 твёрдых)" in metadata
    assert "SiO2(2 твёрдых)" in metadata
    assert "CaSiO3(1 твёрдых)" in metadata

    # Проверки переходов
    assert "Фазовых переходов обнаружено: 1" in metadata
    assert "(SiO2)" in metadata

    # Проверка шага температуры
    assert "Шаг по температуре: 100 K" in metadata


def test_format_metadata_no_transitions(formatter, cao_multi_phase, casio3_multi_phase):
    """Тест форматирования метаданных без переходов."""
    compounds = {
        "CaO": cao_multi_phase,
        "CaSiO3": casio3_multi_phase
    }

    metadata = formatter.format_metadata(compounds)

    assert "Фазовых переходов не обнаружено" in metadata


def test_describe_phases_mixed(formatter):
    """Тест описания смешанных фаз."""
    phases = ["s", "l", "g"]
    description = formatter._describe_phases(phases)

    assert "твёрдых" in description
    assert "жидких" in description
    assert "газовых" in description
    assert " + " in description


def test_format_transition_comment_small_delta_h(formatter):
    """Тест форматирования комментария с малым ΔH."""
    transition = PhaseTransition(
        temperature=500.0,
        from_phase="s1",
        to_phase="s2",
        transition_type="unknown",
        delta_H_transition=0.005,  # Очень малое значение
        delta_S_transition=0.01
    )

    comment = formatter._format_transition_comment("C", transition)

    # ΔH не должен включаться, так как оно слишком мало
    assert "ΔH=" not in comment
    assert "C: s1→s2 (unknown)" in comment