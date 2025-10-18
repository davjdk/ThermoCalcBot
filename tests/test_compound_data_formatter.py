"""
Тесты для CompoundDataFormatter.

Проверяют корректность форматирования вывода для запросов данных по веществам.
"""

import pytest
from unittest.mock import Mock

from src.thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from src.thermo_agents.calculations.thermodynamic_calculator import (
    ThermodynamicCalculator,
    ThermodynamicTable,
    ThermodynamicProperties
)
from src.thermo_agents.models.search import DatabaseRecord, CompoundSearchResult


class TestCompoundDataFormatter:
    """Тесты для CompoundDataFormatter."""

    @pytest.fixture
    def calculator(self):
        """Фикстура с калькулятором."""
        return ThermodynamicCalculator(num_integration_points=100)

    @pytest.fixture
    def formatter(self, calculator):
        """Фикстура с форматтером."""
        return CompoundDataFormatter(calculator)

    @pytest.fixture
    def h2o_record(self):
        """Фикстура с записью для H2O."""
        return DatabaseRecord(
            id=1,
            formula="H2O",
            first_name="Water",
            second_name="Dihydrogen monoxide",
            phase="g",
            h298=-241.826,
            s298=188.838,
            f1=30.09200,
            f2=6.832514,
            f3=6.793435,
            f4=-2.534480,
            f5=0.082139,
            f6=-0.028522,
            tmin=298.15,
            tmax=1000.0,
            tmelt=273.15,
            tboil=373.15,
            reliability_class=1
        )

    @pytest.fixture
    def h2o_search_result(self, h2o_record):
        """Фикстура с результатом поиска для H2O."""
        return CompoundSearchResult(
            compound_formula="H2O",
            records_found=[h2o_record],
            coverage_status="full",
            execution_time_ms=0.01
        )

    def test_format_basic_properties(self, formatter, h2o_record):
        """Проверка форматирования базовых свойств."""
        output = formatter._format_basic_properties(h2o_record)

        # Проверяем наличие ключевых полей
        assert "Формула: H2O" in output
        assert "Название: Water" in output
        assert "Альтернативное название: Dihydrogen monoxide" in output
        assert "Фаза: g (gas (газ))" in output
        assert "Температурный диапазон: 298-1000 K" in output
        assert "H298 (энтальпия): -241.826 кДж/моль" in output
        assert "S298 (энтропия): 188.838 Дж/(моль·K)" in output

        # Проверяем коэффициенты Cp
        assert "f1=30.092000" in output
        assert "f6=-0.028522" in output

        # Проверяем фазовые переходы
        assert "Точка плавления: 273.1 K (0.0°C)" in output
        assert "Точка кипения: 373.1 K (100.0°C)" in output

        # Проверяем надежность данных
        assert "Надежность данных: Высокое (класс 1)" in output

    def test_format_basic_properties_minimal_record(self, formatter):
        """Тест с минимальной записью (без second_name)."""
        minimal_record = DatabaseRecord(
            id=2,
            formula="CH4",
            first_name="Methane",
            phase="g",
            h298=-74.873,
            s298=186.251,
            f1=19.251,
            f2=0.052213,
            f3=-1.597e-05,
            f4=2.154e-08,
            f5=-7.673e-12,
            f6=0.0,
            tmin=298.15,
            tmax=1000.0,
            tmelt=90.68,
            tboil=111.65,
            reliability_class=2
        )

        output = formatter._format_basic_properties(minimal_record)

        assert "Формула: CH4" in output
        assert "Название: Methane" in output
        assert "Альтернативное название:" not in output  # Не должно быть
        assert "Надежность данных: Среднее (класс 2)" in output

    def test_format_thermodynamic_table(self, formatter, h2o_record):
        """Проверка табличного вывода."""
        # Создаем тестовую таблицу
        props1 = ThermodynamicProperties(T=300.0, Cp=39.5, H=-241000.0, S=189.0, G=-297700.0)
        props2 = ThermodynamicProperties(T=400.0, Cp=36.7, H=-238000.0, S=200.0, G=-318000.0)

        table = ThermodynamicTable(
            formula="H2O",
            phase="g",
            temperature_range=(298.15, 400.0),
            properties=[props1, props2]
        )

        output = formatter._format_thermodynamic_table(table)

        # Проверяем наличие заголовков таблицы
        assert "T(K)" in output
        assert "Cp" in output
        assert "H" in output
        assert "S" in output
        assert "G" in output

        # Проверяем наличие данных
        assert "300" in output
        assert "400" in output
        assert "39.50" in output  # Cp значение
        assert "-241.00" in output  # H значение в кДж

        # Проверяем формат grid (наличие границ таблицы)
        assert "┌" in output or "+" in output  # Зависит от версии tabulate

        # Проверяем легенду
        assert "Легенда:" in output
        assert "T - температура" in output
        assert "Cp - изобарная теплоемкость" in output

    def test_format_not_found_response(self, formatter):
        """Проверка форматирования ответа для несуществующего вещества."""
        output = formatter._format_not_found_response("XYZ123")

        assert "❌ Вещество 'XYZ123' не найдено в базе данных" in output
        assert "Возможные причины:" in output
        assert "Попробуйте:" in output
        assert "Проверить правильность написания формулы" in output

    def test_format_response_success(self, formatter, h2o_search_result):
        """Проверка полного форматированного ответа."""
        output = formatter.format_response(h2o_search_result, 300.0, 600.0, 100)

        # Проверяем структуру ответа
        assert "📊 Термодинамические данные: H2O" in output
        assert "Базовые свойства:" in output
        assert "Термодинамические свойства по температуре:" in output
        assert "Примечания:" in output

        # Проверяем наличие ключевых элементов
        assert "Шаг по температуре: 100 K" in output
        assert "уравнений Шомейта" in output

    def test_format_response_no_records(self, formatter):
        """Проверка ответа когда записи не найдены."""
        empty_result = CompoundSearchResult(
            compound_formula="NonExistent",
            records_found=[],
            coverage_status="none",
            execution_time_ms=0.001
        )

        output = formatter.format_response(empty_result, 300.0, 600.0, 100)

        assert output.startswith("❌ Вещество 'NonExistent' не найдено")
        assert "Термодинамические данные:" not in output

    def test_format_simple_table(self, formatter, h2o_record):
        """Проверка форматирования простой таблицы."""
        output = formatter.format_simple_table(h2o_record, [300.0, 400.0, 500.0])

        assert "📊 Свойства вещества H2O" in output
        assert "300" in output
        assert "400" in output
        assert "500" in output

        # Проверяем заголовки
        assert "T(K)" in output
        assert "Cp(Дж/(моль·K))" in output
        assert "H(кДж/моль)" in output

    def test_format_simple_table_with_error(self, formatter, h2o_record):
        """Проверка форматирования таблицы с температурой вне диапазона."""
        output = formatter.format_simple_table(h2o_record, [200.0])  # Ниже Tmin

        assert "Ошибка:" in output

    def test_phase_mapping(self, formatter, h2o_record):
        """Проверка корректности отображения фаз."""
        # Проверяем газовую фазу
        output = formatter._format_basic_properties(h2o_record)
        assert "g (gas (газ))" in output

        # Создаем запись с другой фазой
        solid_record = DatabaseRecord(
            id=3,
            formula="Fe",
            first_name="Iron",
            phase="s",
            h298=0.0,
            s298=27.28,
            f1=23.998,
            f2=9.878e-04,
            f3=-3.673e-01,
            f4=1.546e-06,
            f5=0.0,
            f6=0.0,
            tmin=298.15,
            tmax=1800.0,
            tmelt=1811.0,
            tboil=3134.0,
            reliability_class=1
        )

        output = formatter._format_basic_properties(solid_record)
        assert "s (solid (твердое))" in output

    def test_reliability_class_mapping(self, formatter):
        """Проверка отображения классов надежности."""
        for reliability_class, expected_desc in [(1, "Высокое"), (2, "Среднее"), (3, "Низкое")]:
            record = DatabaseRecord(
                id=4,
                formula="Test",
                first_name="Test compound",
                phase="g",
                h298=0.0,
                s298=100.0,
                f1=30.0,
                f2=0.0,
                f3=0.0,
                f4=0.0,
                f5=0.0,
                f6=0.0,
                tmin=298.15,
                tmax=1000.0,
                tmelt=273.15,
                tboil=373.15,
                reliability_class=reliability_class
            )

            output = formatter._format_basic_properties(record)
            assert f"Надежность данных: {expected_desc} (класс {reliability_class})" in output

    def test_temperature_conversion(self, formatter, h2o_record):
        """Проверка корректности конвертации температур в °C."""
        output = formatter._format_basic_properties(h2o_record)

        assert "0.0°C" in output  # 273.15K - 273.15 = 0°C
        assert "100.0°C" in output  # 373.15K - 273.15 = 100°C

    def test_coefficient_precision(self, formatter, h2o_record):
        """Проверка точности вывода коэффициентов."""
        output = formatter._format_basic_properties(h2o_record)

        # Проверяем, что коэффициенты выводятся с 6 знаками после запятой
        assert "f1=30.092000" in output
        assert "f2=6.832514" in output
        assert "f6=-0.028522" in output

    def test_integration_with_calculator(self, formatter, h2o_search_result):
        """Интеграционный тест с калькулятором."""
        # Этот тест проверяет, что форматтер корректно вызывает калькулятор
        output = formatter.format_response(h2o_search_result, 300.0, 500.0, 100)

        # Должна быть сгенерирована таблица
        assert "Термодинамические свойства по температуре:" in output

        # Должны быть данные для разных температур
        assert "300" in output or "400" in output or "500" in output

        # Должны быть легенды
        assert "Легенда:" in output or "Примечания:" in output