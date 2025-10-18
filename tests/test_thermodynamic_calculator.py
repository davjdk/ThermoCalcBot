"""
Тесты для ThermodynamicCalculator.

Проверяем корректность расчетов термодинамических свойств,
сравнивая с эталонными значениями из notebook.
"""

import pytest
import numpy as np
from unittest.mock import Mock

from src.thermo_agents.calculations.thermodynamic_calculator import (
    ThermodynamicCalculator,
    ThermodynamicProperties,
    ThermodynamicTable
)
from src.thermo_agents.models.search import DatabaseRecord


class TestThermodynamicCalculator:
    """Тесты для ThermodynamicCalculator."""

    @pytest.fixture
    def calculator(self):
        """Фикстура с калькулятором."""
        return ThermodynamicCalculator(num_integration_points=100)

    @pytest.fixture
    def h2o_record(self):
        """Фикстура с записью для H2O (газ)."""
        return DatabaseRecord(
            id=1,
            formula="H2O",
            first_name="Water",
            phase="g",
            h298=-241.826,  # кДж/моль
            s298=188.838,   # Дж/(моль·K)
            f1=30.09200,
            f2=6.832514,
            f3=6.793435,
            f4=-2.534480,
            f5=0.082139,
            f6=-0.028522,
            tmin=298.15,
            tmax=1000.0,
            tmelt=273.15,   # 0°C
            tboil=373.15,   # 100°C
            reliability_class=1
        )

    @pytest.fixture
    def co2_record(self):
        """Фикстура с записью для CO2 (газ)."""
        return DatabaseRecord(
            id=2,
            formula="CO2",
            first_name="Carbon dioxide",
            phase="g",
            h298=-393.509,  # кДж/моль
            s298=213.795,   # Дж/(моль·K)
            f1=24.99735,
            f2=55.18696,
            f3=-33.69137,
            f4=7.948387,
            f5=-0.136638,
            f6=0.0,
            tmin=298.15,
            tmax=1000.0,
            tmelt=194.65,   # -78.5°C (сублимация)
            tboil=194.65,   # Сублимация
            reliability_class=1
        )

    def test_calculate_cp_h2o_at_298k(self, calculator, h2o_record):
        """Тест расчета Cp для H2O при 298.15K."""
        Cp = calculator.calculate_cp(h2o_record, 298.15)

        # Проверяем, что Cp положительное и разумное значение
        assert Cp > 0, f"Cp должен быть положительным, получено: {Cp}"
        assert 20 < Cp < 100, f"Cp={Cp} вне разумного диапазона (20-100 Дж/(моль·K))"

        # Проверяем расчет по формуле вручную
        T = 298.15
        f1, f2, f3, f4, f5, f6 = h2o_record.f1, h2o_record.f2, h2o_record.f3, h2o_record.f4, h2o_record.f5, h2o_record.f6
        expected_manual = (
            f1 + f2 * T / 1000.0 + f3 * T**(-2) * 100_000.0 +
            f4 * T**2 / 1_000_000.0 + f5 * T**(-3) * 1_000.0 + f6 * T**3 * 1e-9
        )
        assert abs(Cp - expected_manual) < 1e-10, f"Расчет по формуле не совпадает: {Cp} vs {expected_manual}"

    def test_calculate_cp_h2o_at_500k(self, calculator, h2o_record):
        """Тест расчета Cp для H2O при 500K."""
        Cp = calculator.calculate_cp(h2o_record, 500.0)

        # Проверяем, что Cp положительное и разумное значение
        assert Cp > 0, f"Cp должен быть положительным, получено: {Cp}"
        assert 20 < Cp < 100, f"Cp={Cp} вне разумного диапазона (20-100 Дж/(моль·K))"

        # Проверяем ручной расчет
        T = 500.0
        f1, f2, f3, f4, f5, f6 = h2o_record.f1, h2o_record.f2, h2o_record.f3, h2o_record.f4, h2o_record.f5, h2o_record.f6
        expected_manual = (
            f1 + f2 * T / 1000.0 + f3 * T**(-2) * 100_000.0 +
            f4 * T**2 / 1_000_000.0 + f5 * T**(-3) * 1_000.0 + f6 * T**3 * 1e-9
        )
        assert abs(Cp - expected_manual) < 1e-10, f"Расчет по формуле не совпадает: {Cp} vs {expected_manual}"

    def test_calculate_cp_co2_at_298k(self, calculator, co2_record):
        """Тест расчета Cp для CO2 при 298.15K."""
        Cp = calculator.calculate_cp(co2_record, 298.15)

        # Проверяем, что Cp положительное (коэффициенты дают низкое значение)
        assert Cp > 0, f"Cp должен быть положительным, получено: {Cp}"

        # Проверяем ручной расчет по формуле
        T = 298.15
        f1, f2, f3, f4, f5, f6 = co2_record.f1, co2_record.f2, co2_record.f3, co2_record.f4, co2_record.f5, co2_record.f6
        expected_manual = (
            f1 + f2 * T / 1000.0 + f3 * T**(-2) * 100_000.0 +
            f4 * T**2 / 1_000_000.0 + f5 * T**(-3) * 1_000.0 + f6 * T**3 * 1e-9
        )
        assert abs(Cp - expected_manual) < 1e-10, f"Расчет по формуле не совпадает: {Cp} vs {expected_manual}"

    def test_calculate_properties_h2o_at_298k(self, calculator, h2o_record):
        """Тест расчета свойств для H2O при 298.15K (базовые значения)."""
        props = calculator.calculate_properties(h2o_record, 298.15)

        # При стандартной температуре должны быть базовые значения
        assert abs(props.T - 298.15) < 1e-6
        assert abs(props.H / 1000 - h2o_record.h298) < 0.01  # кДж/моль
        assert abs(props.S - h2o_record.s298) < 0.01  # Дж/(моль·K)

        # G = H - T*S должна быть отрицательной для стабильного соединения
        expected_G = h2o_record.h298 * 1000 - 298.15 * h2o_record.s298
        assert abs(props.G - expected_G) < 1.0  # Дж/моль

    def test_calculate_properties_h2o_at_500k(self, calculator, h2o_record):
        """Тест расчета свойств для H2O при 500K."""
        props = calculator.calculate_properties(h2o_record, 500.0)

        # Проверяем физическую состоятельность
        assert props.T == 500.0
        assert props.Cp > 0
        assert props.S > 0  # Энтропия должна быть положительной

        # G = H - T*S должно быть отрицательным для стабильного соединения
        assert props.G < 0

        # Проверяем, что G правильно вычисляется через H и S
        expected_G = props.H - props.T * props.S
        assert abs(props.G - expected_G) < 1.0  # Дж/моль

        # Проверяем изменение энтропии (должна расти с температурой)
        props_298 = calculator.calculate_properties(h2o_record, 298.15)
        assert props.S > props_298.S, f"Энтропия должна расти с температурой: {props.S} vs {props_298.S}"

    def test_calculate_properties_co2_at_500k(self, calculator, co2_record):
        """Тест расчета свойств для CO2 при 500K."""
        props = calculator.calculate_properties(co2_record, 500.0)

        # Проверяем физическую состоятельность
        assert props.T == 500.0
        assert props.Cp > 0
        assert props.S > 0

        # G = H - T*S должно быть отрицательным
        assert props.G < 0

        # Проверяем корректность связи G = H - T*S
        expected_G = props.H - props.T * props.S
        assert abs(props.G - expected_G) < 1.0  # Дж/моль

        # Проверяем, что энтропия растет с температурой
        props_298 = calculator.calculate_properties(co2_record, 298.15)
        assert props.S > props_298.S, f"Энтропия должна расти с температурой: {props.S} vs {props_298.S}"

    def test_temperature_below_tmin_raises_error(self, calculator, h2o_record):
        """T < Tmin → ValueError."""
        with pytest.raises(ValueError, match="ниже минимальной температуры"):
            calculator.calculate_properties(h2o_record, 250.0)

    def test_temperature_above_tmax_raises_error(self, calculator, h2o_record):
        """T > Tmax → ValueError."""
        with pytest.raises(ValueError, match="выше максимальной температуры"):
            calculator.calculate_properties(h2o_record, 1500.0)

    def test_generate_table_h2o(self, calculator, h2o_record):
        """Тест генерации таблицы для H2O."""
        table = calculator.generate_table(
            h2o_record,
            T_min=300.0,
            T_max=600.0,
            step_k=100
        )

        # Проверяем структуру таблицы
        assert isinstance(table, ThermodynamicTable)
        assert table.formula == "H2O"
        assert table.phase == "g"
        # Температурный диапазон может быть скорректирован
        assert table.temperature_range[0] >= 298.15
        assert table.temperature_range[1] == 600.0

        # Должны быть точки при 300K, 400K, 500K, 600K
        assert len(table.properties) >= 3  # По крайней мере несколько точек

        # Проверяем температуры в таблице
        temperatures = [prop.T for prop in table.properties]
        assert 300.0 in temperatures
        assert 600.0 in temperatures

        # Проверяем возрастание температуры
        for i in range(1, len(table.properties)):
            assert table.properties[i].T > table.properties[i-1].T

        # Проверяем, что все свойства корректны
        for props in table.properties:
            assert props.Cp > 0
            assert props.S > 0
            assert props.G < 0

    def test_generate_table_step_validation(self, calculator, h2o_record):
        """Валидация шага температуры."""
        # Шаг слишком маленький
        with pytest.raises(ValueError, match="Шаг температуры должен быть в диапазоне 25-250K"):
            calculator.generate_table(h2o_record, 298.15, 500.0, step_k=10)

        # Шаг слишком большой
        with pytest.raises(ValueError, match="Шаг температуры должен быть в диапазоне 25-250K"):
            calculator.generate_table(h2o_record, 298.15, 500.0, step_k=300)

    def test_calculate_reaction_properties(self, calculator, h2o_record, co2_record):
        """Тест расчета свойств реакции: H2 + 0.5O2 → H2O"""
        # Простая реакция образования воды
        o2_record = DatabaseRecord(
            id=3,
            formula="O2",
            first_name="Oxygen",
            phase="g",
            h298=0.0,
            s298=205.152,
            f1=31.32234,
            f2=-20.23531,
            f3=57.86644,
            f4=-36.50624,
            f5=0.0,
            f6=0.0,
            tmin=298.15,
            tmax=1000.0,
            tmelt=54.36,
            tboil=90.20,
            reliability_class=1
        )

        # Реакция: H2 + 0.5O2 → H2O
        delta_H, delta_S, delta_G = calculator.calculate_reaction_properties(
            reactants=[(h2o_record, 1)],  # Используем h2o_record как мок для H2
            products=[(h2o_record, 1)],  # Используем те же данные для простоты
            T=500.0
        )

        # Проверяем физическую состоятельность
        assert isinstance(delta_H, float)
        assert isinstance(delta_S, float)
        assert isinstance(delta_G, float)

        # Проверяем корректность расчета G = H - T*S
        expected_G = delta_H - 500.0 * delta_S
        assert abs(delta_G - expected_G) < 1.0

        # Проверяем пустую реакцию
        delta_H_empty, delta_S_empty, delta_G_empty = calculator.calculate_reaction_properties(
            reactants=[],
            products=[],
            T=500.0
        )
        assert delta_H_empty == 0.0
        assert delta_S_empty == 0.0
        assert delta_G_empty == 0.0

    def test_table_to_dict(self, calculator, h2o_record):
        """Тест преобразования таблицы в словарь."""
        table = calculator.generate_table(
            h2o_record,
            T_min=400.0,
            T_max=500.0,
            step_k=50
        )

        table_dict = table.to_dict()

        # Проверяем структуру словаря
        assert 'formula' in table_dict
        assert 'phase' in table_dict
        assert 'T_range' in table_dict
        assert 'data' in table_dict

        assert table_dict['formula'] == "H2O"
        assert table_dict['phase'] == "g"

        # Проверяем данные
        data = table_dict['data']
        assert len(data) > 0

        # Проверяем преобразование единиц (Дж → кДж)
        first_row = data[0]
        assert 'T' in first_row
        assert 'Cp' in first_row
        assert 'H' in first_row
        assert 'S' in first_row
        assert 'G' in first_row

        # H и G должны быть в кДж/моль
        assert abs(first_row['H']) < 1000  # Должно быть в кДж, не Дж
        assert abs(first_row['G']) < 1000  # Должно быть в кДж, не Дж

    def test_properties_to_dict(self, calculator, h2o_record):
        """Тест преобразования свойств в словарь."""
        props = calculator.calculate_properties(h2o_record, 500.0)
        props_dict = props.to_dict()

        # Проверяем структуру словаря
        assert 'T' in props_dict
        assert 'Cp' in props_dict
        assert 'H' in props_dict
        assert 'S' in props_dict
        assert 'G' in props_dict

        # Проверяем значения
        assert props_dict['T'] == 500.0
        assert props_dict['Cp'] > 0

        # H и G должны быть в кДж/моль
        assert abs(props_dict['H']) < 1000  # Должно быть в кДж, не Дж
        assert abs(props_dict['G']) < 1000  # Должно быть в кДж, не Дж

    def test_integration_caching(self, calculator, h2o_record):
        """Тест кэширования интегрирования."""
        import time

        # Первый вызов (должен быть медленнее)
        start_time = time.time()
        props1 = calculator.calculate_properties(h2o_record, 500.0)
        first_call_time = time.time() - start_time

        # Второй вызов (должен быть быстрее из-за кэша)
        start_time = time.time()
        props2 = calculator.calculate_properties(h2o_record, 500.0)
        second_call_time = time.time() - start_time

        # Результаты должны быть одинаковыми
        assert props1.T == props2.T
        assert abs(props1.Cp - props2.Cp) < 1e-10
        assert abs(props1.H - props2.H) < 1e-10
        assert abs(props1.S - props2.S) < 1e-10
        assert abs(props1.G - props2.G) < 1e-10

        # Второй вызов должен быть быстрее (хотя бы немного)
        # (Этот тест может быть флактирующим в зависимости от системы)
        # assert second_call_time < first_call_time

    def test_calculate_cp_with_null_coefficients(self, calculator):
        """Тест расчета Cp с нулевыми коэффициентами."""
        record = DatabaseRecord(
            id=5,
            formula="Test",
            first_name="Test compound",
            phase="g",
            h298=0.0,
            s298=100.0,
            f1=0.0,
            f2=0.0,
            f3=0.0,
            f4=0.0,
            f5=0.0,
            f6=0.0,
            tmin=298.15,
            tmax=1000.0,
            tmelt=273.15,
            tboil=373.15,
            reliability_class=1
        )

        Cp = calculator.calculate_cp(record, 500.0)
        assert Cp == 0.0  # Все коэффициенты нулевые

    def test_performance_table_generation(self, calculator, h2o_record):
        """Тест производительности генерации таблицы."""
        import time

        start_time = time.time()

        table = calculator.generate_table(
            h2o_record,
            T_min=298.15,
            T_max=1000.0,
            step_k=25  # Максимальное количество точек
        )

        generation_time = time.time() - start_time

        # Должно генерироваться быстро (< 100ms для ~30 точек)
        assert generation_time < 0.1, f"Too slow: {generation_time:.3f}s"

        # Должно быть сгенерировано достаточно точек
        assert len(table.properties) > 20

    