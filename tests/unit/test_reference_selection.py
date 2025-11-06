"""
Тесты для новой функциональности: динамическая смена референсных значений H298/S298
и определение простых веществ.

Эти тесты проверяют:
1. Выбор референсной записи для многофазных систем
2. Применение правила H298=0 для простых веществ
3. Валидацию поля is_elemental в ExtractedReactionParameters
"""

import pytest
from typing import List, Optional
from src.thermo_agents.models.search import DatabaseRecord
from src.thermo_agents.models.extraction import ExtractedReactionParameters
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator, ThermodynamicProperties


@pytest.fixture
def thermodynamic_calculator():
    """Fixture для создания ThermodynamicCalculator."""
    return ThermodynamicCalculator()


def create_mock_record(
    formula: str = "H2O",
    phase: str = "l",
    h298: float = -241.8,
    s298: float = 188.8,
    tmin: float = 298.15,
    tmax: float = 1000.0,
    **kwargs
) -> DatabaseRecord:
    """Создаёт тестовую запись базы данных."""
    return DatabaseRecord(
        id=kwargs.get('id', 1),  # integer ID
        formula=formula,
        phase=phase,
        h298=h298,
        s298=s298,
        f1=kwargs.get('f1', 32.2),
        f2=kwargs.get('f2', 0.192),
        f3=kwargs.get('f3', 1.06e4),
        f4=kwargs.get('f4', -3.6e-6),
        f5=kwargs.get('f5', 0.0),
        f6=kwargs.get('f6', 0.0),
        tmin=tmin,
        tmax=tmax,
        tmelt=kwargs.get('tmelt', 273.15),
        tboil=kwargs.get('tboil', 373.15),
        reliability_class=kwargs.get('reliability_class', 1),  # обязательное поле
        is_h298_s298_reference=kwargs.get('is_h298_s298_reference', False)
    )


class TestSelectReferenceRecord:
    """Тесты для метода _select_reference_record()."""

    def test_first_record_uses_itself(self, thermodynamic_calculator):
        """Первая запись использует саму себя как референс."""
        records = [create_mock_record(h298=-100, s298=50)]
        ref = thermodynamic_calculator._select_reference_record(records, 0)
        assert ref == records[0]

    def test_same_phase_uses_first_record(self, thermodynamic_calculator):
        """Одна фаза, несколько записей → используется первая запись фазы."""
        records = [
            create_mock_record(id=1, phase='s', h298=-100, s298=50, tmin=298, tmax=500),
            create_mock_record(id=2, phase='s', h298=-90, s298=55, tmin=500, tmax=800)
        ]
        ref = thermodynamic_calculator._select_reference_record(records, 1)
        assert ref == records[0]  # Должна вернуться первая запись

    def test_phase_change_with_valid_values(self, thermodynamic_calculator):
        """Смена фазы с валидными h298/s298 использует новую запись."""
        records = [
            create_mock_record(id=1, phase='s', h298=-100, s298=50),
            create_mock_record(id=2, phase='l', h298=-80, s298=60)  # Валидные значения
        ]
        ref = thermodynamic_calculator._select_reference_record(records, 1)
        assert ref == records[1]  # Должна вернуться вторая запись

    def test_phase_change_with_zero_values(self, thermodynamic_calculator):
        """Смена фазы с нулевыми h298/s298 сохраняет предыдущую референсную запись."""
        records = [
            create_mock_record(phase='s', h298=-100, s298=50),
            create_mock_record(phase='l', h298=0.0, s298=0.0)  # Нулевые значения
        ]
        ref = thermodynamic_calculator._select_reference_record(records, 1)
        assert ref == records[0]  # Должна вернуться первая запись

    def test_complex_phase_sequence(self, thermodynamic_calculator):
        """Сложная последовательность фазовых переходов."""
        records = [
            create_mock_record(phase='s', h298=-100, s298=50, tmin=298, tmax=500),
            create_mock_record(phase='s', h298=-90, s298=55, tmin=500, tmax=800),
            create_mock_record(phase='l', h298=0.0, s298=0.0, tmin=800, tmax=1200),
            create_mock_record(phase='l', h298=-70, s298=65, tmin=1200, tmax=1500)
        ]

        # Запись 0: использует себя
        assert thermodynamic_calculator._select_reference_record(records, 0) == records[0]

        # Запись 1: та же фаза → первая запись фазы
        assert thermodynamic_calculator._select_reference_record(records, 1) == records[0]

        # Запись 2: смена фазы с нулями → предыдущая фаза
        assert thermodynamic_calculator._select_reference_record(records, 2) == records[0]

        # Запись 3: та же фаза → первая запись жидкой фазы (с нулями)
        assert thermodynamic_calculator._select_reference_record(records, 3) == records[2]


class TestElementalCompounds:
    """Тесты для простых веществ и правила H298=0."""

    def test_elemental_compound_has_zero_h298(self, thermodynamic_calculator):
        """Простое вещество имеет H298=0.0."""
        record = create_mock_record(formula="O2", h298=-100, s298=50)  # В базе может быть ненулевое значение
        props = thermodynamic_calculator.calculate_properties(
            record,
            298.15,
            is_elemental=True  # Флаг простого вещества
        )
        # H298 должна быть принудительно установлена в 0
        assert abs(props.H) < 1e-6  # H(298K) ≈ 0 Дж/моль
        assert props.S != 0.0  # S298 может быть ненулевой

    def test_complex_compound_uses_database_h298(self, thermodynamic_calculator):
        """Сложное вещество использует H298 из базы данных."""
        record = create_mock_record(formula="H2O", h298=-241.8, s298=188.8)  # H2O
        props = thermodynamic_calculator.calculate_properties(
            record,
            298.15,
            is_elemental=False  # Флаг сложного вещества
        )
        # H298 должна быть из базы данных
        assert abs(props.H / 1000 - (-241.8)) < 1e-6  # H(298K) = -241.8 кДж/моль

    def test_no_elemental_flag_uses_database_value(self, thermodynamic_calculator):
        """Без флага is_elemental используется значение из базы данных."""
        record = create_mock_record(formula="Fe", h298=-50, s298=27)
        props = thermodynamic_calculator.calculate_properties(record, 298.15)
        # Должно использоваться значение из базы данных
        assert abs(props.H / 1000 - (-50)) < 1e-6  # H(298K) = -50 кДж/моль

    def test_reference_record_overrides_database(self, thermodynamic_calculator):
        """Референсная запись имеет приоритет над текущей."""
        current_record = create_mock_record(formula="NH3", h298=0.0, s298=0.0)
        reference_record = create_mock_record(formula="NH3", h298=-45.9, s298=192.8)

        props = thermodynamic_calculator.calculate_properties(
            current_record,
            298.15,
            reference_record=reference_record
        )

        # Должны использоваться значения из референсной записи
        assert abs(props.H / 1000 - (-45.9)) < 1e-6  # H(298K) = -45.9 кДж/моль
        assert abs(props.S - 192.8) < 1e-6  # S(298K) = 192.8 Дж/(моль·K)

    def test_elemental_flag_overrides_reference_record(self, thermodynamic_calculator):
        """Флаг простого вещества имеет приоритет над референсной записью."""
        current_record = create_mock_record(formula="O2", h298=0.0, s298=0.0)
        reference_record = create_mock_record(formula="O2", h298=-100, s298=50)

        props = thermodynamic_calculator.calculate_properties(
            current_record,
            298.15,
            reference_record=reference_record,
            is_elemental=True  # Простое вещество
        )

        # H298 должна быть 0 несмотря на референсную запись
        assert abs(props.H) < 1e-6  # H(298K) ≈ 0 Дж/моль


class TestExtractionModelValidation:
    """Тесты валидации поля is_elemental в ExtractedReactionParameters."""

    def test_elemental_with_compound_data_valid(self):
        """is_elemental=True допустим для compound_data с одним веществом."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["O2"],
            reactants=[],
            products=[],
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            missing_fields=[],
            compound_names={"O2": ["Oxygen"]},
            is_elemental=True
        )
        assert params.is_elemental is True

    def test_elemental_false_with_compound_data_valid(self):
        """is_elemental=False допустим для compound_data с одним веществом."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["H2O"],
            reactants=[],
            products=[],
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            missing_fields=[],
            compound_names={"H2O": ["Water"]},
            is_elemental=False
        )
        assert params.is_elemental is False

    def test_elemental_with_reaction_calculation_raises_error(self):
        """is_elemental не допускается для reaction_calculation."""
        with pytest.raises(ValueError, match="применимо только для query_type='compound_data'"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="2H2 + O2 → 2H2O",
                all_compounds=["H2", "O2", "H2O"],
                reactants=["H2", "O2"],
                products=["H2O"],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                missing_fields=[],
                compound_names={"H2": ["Hydrogen"], "O2": ["Oxygen"], "H2O": ["Water"]},
                is_elemental=True  # ← Ошибка: реакция, а не одно вещество
            )

    def test_elemental_with_multiple_compounds_raises_error(self):
        """is_elemental не допускается для нескольких веществ."""
        with pytest.raises(ValueError, match="применимо только для запросов с одним веществом"):
            ExtractedReactionParameters(
                query_type="compound_data",
                balanced_equation="",
                all_compounds=["H2O", "CO2"],  # ← Два вещества
                reactants=[],
                products=[],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                missing_fields=[],
                compound_names={"H2O": ["Water"], "CO2": ["Carbon dioxide"]},
                is_elemental=True
            )

    def test_elemental_none_with_compound_data_valid(self):
        """is_elemental=None допустим для compound_data."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["CH4"],
            reactants=[],
            products=[],
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            missing_fields=[],
            compound_names={"CH4": ["Methane"]},
            is_elemental=None
        )
        assert params.is_elemental is None


class TestIntegration:
    """Интеграционные тесты для полной функциональности."""

    def test_elemental_compound_calculation_flow(self, thermodynamic_calculator):
        """Полный цикл расчёта для простого вещества."""
        # Создаём запись для O2 (простое вещество)
        o2_record = create_mock_record(
            formula="O2",
            phase="g",
            h298=-100,  # В базе может быть любое значение
            s298=205,
            tmin=298.15,
            tmax=2000.0
        )

        # Расчёт с флагом простого вещества
        props = thermodynamic_calculator.calculate_properties(
            o2_record,
            500.0,
            is_elemental=True
        )

        # Проверяем результат
        assert props.T == 500.0
        assert abs(props.H) < 1e-6  # H должно быть близко к 0
        assert props.S > 0  # Энтропия должна быть положительной
        assert props.Cp > 0  # Теплоёмкость должна быть положительной

    def test_multiphase_with_elemental_flag(self, thermodynamic_calculator):
        """Многофазная система с флагом простого вещества."""
        # Создадим двухфазную систему для простого вещества (например, Fe)
        fe_solid = create_mock_record(
            formula="Fe",
            phase="s",
            h298=-50,
            s298=27,
            tmin=298.15,
            tmax=1811.0
        )
        fe_liquid = create_mock_record(
            formula="Fe",
            phase="l",
            h298=0.0,  # Нулевые значения в жидкой фазе
            s298=0.0,
            tmin=1811.0,
            tmax=3134.0
        )

        # Создадим MultiPhaseCompoundData (упрощённая версия для теста)
        from src.thermo_agents.models.search import MultiPhaseCompoundData
        compound_data = MultiPhaseCompoundData(
            formula="Fe",
            records=[fe_solid, fe_liquid],
            melting_point=1811.0,
            boiling_point=3134.0
        )

        # Расчёт в твёрдой фазе
        props_solid = thermodynamic_calculator.calculate_properties_multi_record(
            compound_data, 500.0
        )

        # Расчёт в жидкой фазе (проверим, что не падает)
        props_liquid = thermodynamic_calculator.calculate_properties_multi_record(
            compound_data, 2000.0
        )

        # Базовые проверки
        assert props_solid.T == 500.0
        assert props_liquid.T == 2000.0
        assert props_solid.Cp > 0
        assert props_liquid.Cp > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])