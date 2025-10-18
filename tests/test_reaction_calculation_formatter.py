"""
Тесты для ReactionCalculationFormatter.

Проверяют корректность форматирования вывода для расчетов термодинамики реакций.
"""

import pytest
import numpy as np
from unittest.mock import Mock

from src.thermo_agents.formatting.reaction_calculation_formatter import ReactionCalculationFormatter
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from src.thermo_agents.models.search import DatabaseRecord, CompoundSearchResult
from src.thermo_agents.models.extraction import ExtractedReactionParameters


class TestReactionCalculationFormatter:
    """Тесты для ReactionCalculationFormatter."""

    @pytest.fixture
    def calculator(self):
        """Фикстура с калькулятором."""
        return ThermodynamicCalculator(num_integration_points=100)

    @pytest.fixture
    def formatter(self, calculator):
        """Фикстура с форматтером."""
        return ReactionCalculationFormatter(calculator)

    @pytest.fixture
    def reaction_params(self):
        """Фикстура с параметрами реакции."""
        return ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="2 H2 + O2 -> 2 H2O",
            all_compounds=["H2", "O2", "H2O"],
            reactants=["H2", "O2"],
            products=["H2O"],
            temperature_range_k=(298.15, 800.0),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={
                "H2": ["Hydrogen"],
                "O2": ["Oxygen"],
                "H2O": ["Water"]
            },
            temperature_step_k=100
        )

    @pytest.fixture
    def h2_record(self):
        """Фикстура с записью для H2."""
        return DatabaseRecord(
            id=1,
            formula="H2",
            first_name="Hydrogen",
            phase="g",
            h298=0.0,
            s298=130.681,
            f1=33.066178,
            f2=-11.363417,
            f3=11.432816,
            f4=-2.772874,
            f5=-0.158558,
            f6=0.0,
            tmin=298.15,
            tmax=1000.0,
            tmelt=13.99,
            tboil=20.27,
            reliability_class=1
        )

    @pytest.fixture
    def o2_record(self):
        """Фикстура с записью для O2."""
        return DatabaseRecord(
            id=2,
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

    @pytest.fixture
    def h2o_record(self):
        """Фикстура с записью для H2O."""
        return DatabaseRecord(
            id=3,
            formula="H2O",
            first_name="Water",
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
    def reactants_results(self, h2_record, o2_record):
        """Фикстура с результатами поиска реагентов."""
        h2_result = CompoundSearchResult(
            compound_formula="H2",
            records_found=[h2_record],
            coverage_status="full",
            execution_time_ms=0.01
        )

        o2_result = CompoundSearchResult(
            compound_formula="O2",
            records_found=[o2_record],
            coverage_status="full",
            execution_time_ms=0.01
        )

        return [h2_result, o2_result]

    @pytest.fixture
    def products_results(self, h2o_record):
        """Фикстура с результатами поиска продуктов."""
        h2o_result = CompoundSearchResult(
            compound_formula="H2O",
            records_found=[h2o_record],
            coverage_status="full",
            execution_time_ms=0.01
        )

        return [h2o_result]

    def test_format_equation_simple(self, formatter):
        """Проверка форматирования простого уравнения."""
        output = formatter._format_equation("2 H2 + O2 -> 2 H2O")
        assert "→" in output
        assert "2 H₂" in output
        assert "O₂" in output
        assert "H₂O" in output

    def test_format_equation_with_numbers(self, formatter):
        """Проверка форматирования уравнения с числами."""
        output = formatter._format_equation("CH4 + 2 O2 -> CO2 + 2 H2O")
        assert "→" in output
        assert "CH₄" in output
        assert "2 O₂" in output
        assert "2 H₂O" in output

    def test_format_equation_reversible(self, formatter):
        """Проверка форматирования обратимой реакции."""
        output = formatter._format_equation("N2 + 3 H2 <=> 2 NH3")
        assert "⇄" in output
        assert "N₂" in output
        assert "3 H₂" in output
        assert "2 NH₃" in output

    def test_format_equation_no_numbers(self, formatter):
        """Проверка форматирования уравнения без чисел."""
        output = formatter._format_equation("C + O2 -> CO2")
        assert "→" in output
        assert "O₂" in output
        assert "CO₂" in output

    def test_format_calculation_method(self, formatter):
        """Проверка форматирования метода расчёта."""
        output = formatter._format_calculation_method()

        assert "ΔH°(T)" in output
        assert "ΔS°(T)" in output
        assert "ΔG°(T)" in output
        assert "∫" in output  # Интеграл
        assert "H°₂₉₈" in output  # Подстрочные индексы
        assert "S°₂₉₈" in output
        assert "T⁻²" in output  # Верхние индексы

    def test_format_substances_data(self, formatter, reactants_results, products_results):
        """Проверка форматирования данных веществ."""
        output = formatter._format_substances_data(reactants_results, products_results)

        # Проверяем наличие всех веществ
        assert "H2 — Hydrogen" in output
        assert "O2 — Oxygen" in output
        assert "H2O — Water" in output

        # Проверяем данные H2
        assert "Фаза: g" in output
        assert "T_применимости: 298-1000 K" in output
        assert "H₂₉₈: 0.000 кДж/моль" in output
        assert "S₂₉₈: 130.681 Дж/(моль·K)" in output

        # Проверяем коэффициенты Cp
        assert "f1=33.066178" in output
        assert "f6=0.000000" in output

    def test_format_substances_data_missing_records(self, formatter):
        """Проверка форматирования с отсутствующими записями."""
        missing_result = CompoundSearchResult(
            compound_formula="XYZ",
            records_found=[],
            coverage_status="none",
            execution_time_ms=0.001
        )

        output = formatter._format_substances_data([missing_result], [])

        assert "XYZ — ❌ НЕ НАЙДЕНО В БАЗЕ ДАННЫХ" in output

    def test_format_results(self, formatter, h2_record, o2_record, h2o_record):
        """Проверка форматирования результатов расчёта."""
        # Создаем тестовые данные
        reactant_data = [(h2_record, 2), (o2_record, 1)]
        product_data = [(h2o_record, 2)]

        T_values = np.array([298.15, 400.0, 500.0])
        output = formatter._format_results(reactant_data, product_data, T_values)

        # Проверяем структуру таблицы
        assert "T(K)" in output
        assert "ΔH°(кДж/моль)" in output
        assert "ΔS°(Дж/(К·моль))" in output
        assert "ΔG°(кДж/моль)" in output
        assert "Комментарий" in output

        # Проверяем наличие данных для температур
        assert "298" in output
        assert "400" in output
        assert "500" in output

        # Проверяем наличие комментариев
        assert "Экзергоническая" in output or "Эндергоническая" in output

    def test_format_results_with_calculation_error(self, formatter, h2_record):
        """Проверка форматирования результатов при ошибке расчёта."""
        # Используем температуру вне диапазона
        reactant_data = [(h2_record, 1)]
        product_data = [(h2_record, 1)]

        T_values = np.array([100.0])  # Ниже Tmin
        output = formatter._format_results(reactant_data, product_data, T_values)

        assert "Ошибка расчёта" in output

    def test_extract_stoichiometry_simple(self, formatter):
        """Проверка извлечения стехиометрии для простого случая."""
        stoich = formatter._extract_stoichiometry("H2", "H2")
        assert stoich == 1

        stoich = formatter._extract_stoichiometry("2 H2", "H2")
        assert stoich == 2

    def test_extract_stoichiometry_complex(self, formatter):
        """Проверка извлечения стехиометрии для сложного случая."""
        stoich = formatter._extract_stoichiometry("3 O2", "O2")
        assert stoich == 3

        # Случай, когда не удается извлечь коэффициент
        stoich = formatter._extract_stoichiometry("O2", "O2")
        assert stoich == 1

    def test_format_response_success(self, formatter, reaction_params, reactants_results, products_results):
        """Проверка полного форматированного ответа."""
        output = formatter.format_response(reaction_params, reactants_results, products_results, step_k=100)

        # Проверяем структуру ответа
        assert "⚗️ Термодинамический расчёт реакции" in output
        assert "Уравнение реакции:" in output
        assert "Метод расчёта:" in output
        assert "Данные веществ:" in output
        assert "Результаты расчёта:" in output

        # Проверяем Unicode форматирование
        assert "2 H₂ + O₂ → 2 H₂O" in output

        # Проверяем наличие ключевых элементов
        assert "Шаг по температуре: 100 K" in output
        assert "уравнений Шомейта" in output

    def test_format_response_no_data(self, formatter, reaction_params):
        """Проверка ответа при отсутствии данных."""
        empty_reactants = [CompoundSearchResult(
            formula="NonExistent1",
            records_found=[],
            total_records=0,
            search_time=0.001,
            coverage_status="none"
        )]

        empty_products = [CompoundSearchResult(
            formula="NonExistent2",
            records_found=[],
            total_records=0,
            search_time=0.001,
            coverage_status="none"
        )]

        output = formatter.format_response(reaction_params, empty_reactants, empty_products, step_k=100)

        # Должен быть заголовок и метод расчёта
        assert "⚗️ Термодинамический расчёт реакции" in output
        assert "Метод расчёта:" in output

        # Должны быть сообщения об отсутствии данных
        assert "НЕ НАЙДЕНО В БАЗЕ ДАННЫХ" in output

        # Результаты должны содержать ошибку
        assert "Не удалось рассчитать свойства реакции" in output

    def test_format_simple_results(self, formatter, reaction_params, h2_record, o2_record, h2o_record):
        """Проверка форматирования простых результатов."""
        reactant_data = [(h2_record, 2), (o2_record, 1)]
        product_data = [(h2o_record, 2)]
        temperatures = [298.15, 400.0, 500.0]

        output = formatter.format_simple_results(
            reaction_params,
            reactant_data,
            product_data,
            temperatures
        )

        # Проверяем структуру
        assert "📊 Результаты реакции: 2 H₂ + O₂ → 2 H₂O" in output
        assert "298K:" in output
        assert "400K:" in output
        assert "500K:" in output

        # Проверяем наличие ΔH, ΔS, ΔG
        assert "ΔH° =" in output
        assert "ΔS° =" in output
        assert "ΔG° =" in output

        # Проверяем наличие комментариев о термодинамической выгодности
        assert ("термодинамически выгодна" in output or
                "термодинамически невыгодна" in output or
                "равновесии" in output)

    def test_unicode_subscript_conversion(self, formatter):
        """Тест конвертации Unicode подстрочных индексов."""
        test_cases = [
            ("H2O", "H₂O"),
            ("CO2", "CO₂"),
            ("CH4", "CH₄"),
            ("C6H12O6", "C₆H₁₂O₆"),
            ("Fe2O3", "Fe₂O₃")
        ]

        for input_formula, expected_output in test_cases:
            output = formatter._format_equation(input_formula)
            assert expected_output in output

    def test_temperature_spacing_in_equation(self, formatter):
        """Проверка правильности расстановки пробелов в уравнении."""
        output = formatter._format_equation("A+B->C")
        assert "A + B → C" == output

        output = formatter._format_equation("2A+3B->C")
        assert "2 A + 3 B → C" == output

    def test_phase_inclusion_in_substances(self, formatter, h2_record):
        """Проверка включения информации о фазе."""
        result = CompoundSearchResult(
            formula="H2",
            records_found=[h2_record],
            total_records=1,
            search_time=0.01,
            coverage_status="full"
        )

        output = formatter._format_substances_data([result], [])
        assert "Фаза: g" in output
        assert "T_применимости: 298-1000 K" in output

    def test_coefficient_formatting(self, formatter, h2_record):
        """Проверка форматирования коэффициентов."""
        result = CompoundSearchResult(
            formula="H2",
            records_found=[h2_record],
            total_records=1,
            search_time=0.01,
            coverage_status="full"
        )

        output = formatter._format_substances_data([result], [])
        assert "f1=33.066178" in output
        assert "f2=-11.363417" in output
        assert "f6=0.000000" in output