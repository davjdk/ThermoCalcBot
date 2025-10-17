"""
Unit тесты для ReactionValidator.

Тестируют:
1. Валидацию формул
2. Мягкую валидацию по названиям
3. Расчет confidence scores
4. Обработку краевых случаев
"""

import pytest
from unittest.mock import Mock
from typing import List

from thermo_agents.filtering.reaction_validator import (
    ReactionValidator,
    ValidationResult,
    CompoundValidationResult,
    validate_compound_names,
    create_reaction_validator
)
from thermo_agents.models.search import DatabaseRecord
from thermo_agents.models.extraction import ExtractedReactionParameters


class TestReactionValidator:
    """Тесты для класса ReactionValidator."""

    @pytest.fixture
    def validator(self):
        """Создает экземпляр ReactionValidator для тестов."""
        return ReactionValidator()

    @pytest.fixture
    def sample_db_records(self):
        """Создает примеры записей из БД для тестов."""
        return [
            DatabaseRecord(
                formula="Mg(g)",
                first_name="Magnesium",
                phase="g",
                tmin=298.15,
                tmax=2000.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="MgI(g)",
                first_name="Magnesium monoiodide",
                phase="g",
                tmin=298.15,
                tmax=1000.0,
                reliability_class=2
            ),
            DatabaseRecord(
                formula="Ti(s)",
                first_name="Titanium",
                phase="s",
                tmin=298.15,
                tmax=1941.0,
                reliability_class=1
            ),
            DatabaseRecord(
                formula="Ti(-g)",
                first_name="Titanium ion",
                phase="g",
                tmin=298.15,
                tmax=5000.0,
                reliability_class=3
            )
        ]

    @pytest.fixture
    def sample_reaction_params(self):
        """Создает пример параметров реакции."""
        return ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={
                "TiF4": ["Titanium(IV) fluoride", "Titanium tetrafluoride"],
                "Mg": ["Magnesium"],
                "Ti": ["Titanium"],
                "MgF2": ["Magnesium fluoride", "Sellaite"]
            }
        )

    def test_formula_match_score_exact_match(self, validator):
        """Тест точного совпадения формул."""
        # Точное совпадение
        score = validator._calculate_formula_match_score("Mg(g)", "Mg")
        assert score == 1.0

        # Совпадение с префиксом
        score = validator._calculate_formula_match_score("MgI(g)", "Mg")
        assert score == 1.0

        # Несовпадение
        score = validator._calculate_formula_match_score("Ti(s)", "Mg")
        assert score == 0.0

    def test_name_match_score_exact_match(self, validator):
        """Тест точного совпадения названий."""
        # Точное совпадение
        score = validator._calculate_name_match_score("Magnesium", ["Magnesium"])
        assert score == 1.0

        # Совпадение в разном регистре
        score = validator._calculate_name_match_score("magnesium", ["Magnesium"])
        assert score == 1.0

        # Нет совпадения
        score = validator._calculate_name_match_score("Titanium", ["Magnesium"])
        assert score == 0.0

    def test_name_match_score_partial_match(self, validator):
        """Тест частичного совпадения названий."""
        # Частичное совпадение (overlap)
        score = validator._calculate_name_match_score("Magnesium fluoride", ["Magnesium"])
        assert 0.3 <= score < 1.0

        # Совпадение после удаления спецсимволов
        score = validator._calculate_name_match_score("Titanium(IV) fluoride", ["Titanium IV fluoride"])
        assert score >= 0.9

        # Token overlap
        score = validator._calculate_name_match_score("Magnesium monoiodide", ["Magnesium", "Monoiodide"])
        assert score >= 0.7

    def test_validate_single_record_high_confidence(self, validator, sample_db_records):
        """Тест валидации записи с высоким confidence."""
        record = sample_db_records[0]  # Mg(g) с FirstName="Magnesium"
        target_formula = "Mg"
        target_role = "reactant"
        target_names = ["Magnesium"]

        result = validator._validate_single_record(
            record, target_formula, target_role, target_names
        )

        assert isinstance(result, ValidationResult)
        assert result.record == record
        assert result.formula_match_score == 1.0  # Точное совпадение формулы
        assert result.name_match_score == 1.0     # Точное совпадение названия
        assert result.total_confidence == 1.0     # Общий confidence = 1.0
        assert result.role_match == True
        assert "✅" in result.reasoning

    def test_validate_single_record_low_confidence(self, validator, sample_db_records):
        """Тест валидации записи с низким confidence."""
        record = sample_db_records[1]  # MgI(g) с FirstName="Magnesium monoiodide"
        target_formula = "Mg"
        target_role = "reactant"
        target_names = ["Magnesium"]

        result = validator._validate_single_record(
            record, target_formula, target_role, target_names
        )

        assert isinstance(result, ValidationResult)
        assert result.record == record
        assert result.formula_match_score == 1.0  # Префиксное совпадение
        assert 0.3 <= result.name_match_score < 1.0  # Частичное совпадение названия
        assert 0.7 <= result.total_confidence < 1.0  # Взвешенная сумма
        assert result.role_match == True

    def test_validate_single_compound_with_best_result(self, validator, sample_db_records):
        """Тест валидации соединения с лучшим результатом."""
        target_formula = "Mg"
        target_role = "reactant"
        target_names = ["Magnesium"]

        result = validator._validate_single_compound(
            target_formula, target_role, sample_db_records[:2], target_names
        )

        assert isinstance(result, CompoundValidationResult)
        assert result.target_formula == target_formula
        assert result.target_role == target_role
        assert len(result.all_results) == 2
        assert result.best_result is not None
        assert result.best_result.total_confidence >= result.all_results[1].total_confidence

    def test_validate_single_compound_no_records(self, validator):
        """Тест валидации соединения без записей."""
        target_formula = "Mg"
        target_role = "reactant"
        target_names = ["Magnesium"]

        result = validator._validate_single_compound(
            target_formula, target_role, [], target_names
        )

        assert isinstance(result, CompoundValidationResult)
        assert result.target_formula == target_formula
        assert len(result.all_results) == 0
        assert result.best_result is None
        assert "Нет записей" in result.validation_summary

    def test_validate_reaction_compounds_complete(self, validator, sample_db_records, sample_reaction_params):
        """Тест полной валидации реакции."""
        # Добавим еще записи для полноты теста
        all_records = sample_db_records + [
            DatabaseRecord(
                Formula="TiF4(g)",
                FirstName="Titanium tetrafluoride",
                Phase="g",
                Tmin=298.15,
                Tmax=1500.0,
                ReliabilityClass=1
            ),
            DatabaseRecord(
                Formula="MgF2(s)",
                FirstName="Magnesium fluoride",
                Phase="s",
                Tmin=298.15,
                Tmax=1500.0,
                ReliabilityClass=1
            )
        ]

        filtered_records, validation_results = validator.validate_reaction_compounds(
            all_records, sample_reaction_params
        )

        assert len(filtered_records) > 0
        assert len(validation_results) == len(sample_reaction_params.all_compounds)

        # Проверяем, что у каждого соединения есть результат валидации
        for compound in sample_reaction_params.all_compounds:
            assert compound in validation_results

    def test_normalize_name(self, validator):
        """Тест нормализации названий."""
        # Удаление диакритических знаков
        name1 = validator._normalize_name("Titanium")
        name2 = validator._normalize_name("titanium")
        assert name1 == name2

        # Нижний регистр и trim
        name = validator._normalize_name("  Magnesium  ")
        assert name == "magnesium"

    def test_remove_special_chars(self, validator):
        """Тест удаления специальных символов."""
        # Удаление скобок и цифр
        name = validator._remove_special_chars("Titanium(IV) fluoride")
        assert name == "titanium fluoride"

        # Удаление запятых и точек
        name = validator._remove_special_chars("Magnesium fluoride, Sellaite.")
        assert name == "magnesium fluoride sellaite"

    def test_find_best_formula_match(self, validator):
        """Тест поиска лучшего совпадения формулы."""
        target_formulas = ["Mg", "Ti", "Fe"]

        # Точное совпадение
        match = validator._find_best_formula_match("Mg(g)", target_formulas)
        assert match == "Mg"

        # Префиксное совпадение
        match = validator._find_best_formula_match("MgI(g)", target_formulas)
        assert match == "Mg"

        # Совпадение с модификаторами
        match = validator._find_best_formula_match("Ti(E)", target_formulas)
        assert match == "Ti"

        # Нет совпадения
        match = validator._find_best_formula_match("Fe2O3", target_formulas)
        assert match == "Fe"  # префиксное совпадение

    def test_determine_compound_role(self, validator, sample_reaction_params):
        """Тест определения роли соединения в реакции."""
        # Реагент
        role = validator._determine_compound_role("Mg", sample_reaction_params)
        assert role == "reactant"

        # Продукт
        role = validator._determine_compound_role("Ti", sample_reaction_params)
        assert role == "product"

        # Неизвестное соединение
        role = validator._determine_compound_role("Unknown", sample_reaction_params)
        assert role == "unknown"

    def test_edge_cases_empty_names(self, validator, sample_db_records):
        """Тест краевых случаев: пустые названия."""
        record = sample_db_records[0]  # Mg(g)
        target_formula = "Mg"
        target_role = "reactant"
        target_names = []  # Пустой список

        result = validator._validate_single_record(
            record, target_formula, target_role, target_names
        )

        # Should still work based on formula matching only
        assert result.formula_match_score == 1.0
        assert result.name_match_score == 0.0
        assert result.total_confidence == 0.7  # 70% weight on formula only

    def test_edge_cases_none_db_name(self, validator, sample_db_records):
        """Тест краевых случаев: отсутствующее имя в БД."""
        record = sample_db_records[0]
        # Удаляем FirstName для теста
        record.FirstName = None

        target_formula = "Mg"
        target_role = "reactant"
        target_names = ["Magnesium"]

        result = validator._validate_single_record(
            record, target_formula, target_role, target_names
        )

        assert result.name_match_score == 0.0
        assert result.total_confidence == 0.7  # Based on formula only


class TestReactionValidatorUtilities:
    """Тесты для утилитарных функций ReactionValidator."""

    def test_create_reaction_validator(self):
        """Тест создания валидатора через утилиту."""
        validator = create_reaction_validator()
        assert isinstance(validator, ReactionValidator)

    def test_validate_compound_names_utility(self):
        """Тест утилитарной функции валидации названий."""
        # Высокий score
        passed, score = validate_compound_names("Magnesium", ["Magnesium"], min_score=0.8)
        assert passed == True
        assert score == 1.0

        # Низкий score
        passed, score = validate_compound_names("Titanium", ["Magnesium"], min_score=0.8)
        assert passed == False
        assert score == 0.0

        # Частичное совпадение
        passed, score = validate_compound_names("Magnesium fluoride", ["Magnesium"], min_score=0.3)
        assert passed == True
        assert 0.3 <= score < 1.0

    def test_validate_compound_names_empty_input(self):
        """Тест утилиты с пустыми входными данными."""
        # Пустые названия от LLM
        passed, score = validate_compound_names("Magnesium", [], min_score=0.5)
        assert passed == False
        assert score == 0.0

        # Пустое название из БД
        passed, score = validate_compound_names("", ["Magnesium"], min_score=0.5)
        assert passed == False
        assert score == 0.0


class TestReactionValidatorIntegration:
    """Интеграционные тесты для ReactionValidator."""

    def test_real_world_validation_scenario(self):
        """Тест реального сценария валидации из ТЗ."""
        validator = ReactionValidator()

        # Создаем записи как в примере из ТЗ
        db_records = [
            DatabaseRecord(
                Formula="TiF4(g)",
                FirstName="Titanium tetrafluoride",
                Phase="g",
                Tmin=298.15,
                Tmax=1500.0,
                ReliabilityClass=1
            ),
            DatabaseRecord(
                Formula="MgI(g)",
                FirstName="Magnesium monoiodide",
                Phase="g",
                Tmin=298.15,
                Tmax=1000.0,
                ReliabilityClass=2
            ),
            DatabaseRecord(
                Formula="Ti(-g)",
                FirstName="Titanium ion",
                Phase="g",
                Tmin=298.15,
                Tmax=5000.0,
                ReliabilityClass=3
            ),
            DatabaseRecord(
                Formula="MgF2(s)",
                FirstName="Magnesium fluoride",
                Phase="s",
                Tmin=298.15,
                Tmax=1500.0,
                ReliabilityClass=1
            )
        ]

        reaction_params = ExtractedReactionParameters(
            balanced_equation="TiF4 + 2Mg → Ti + 2MgF2",
            all_compounds=["TiF4", "Mg", "Ti", "MgF2"],
            reactants=["TiF4", "Mg"],
            products=["Ti", "MgF2"],
            temperature_range_k=(900, 1500),
            extraction_confidence=0.95,
            missing_fields=[],
            compound_names={
                "TiF4": ["Titanium(IV) fluoride", "Titanium tetrafluoride"],
                "Mg": ["Magnesium"],
                "Ti": ["Titanium"],
                "MgF2": ["Magnesium fluoride", "Sellaite"]
            }
        )

        filtered_records, validation_results = validator.validate_reaction_compounds(
            db_records, reaction_params
        )

        # Проверяем результаты
        assert len(filtered_records) >= 2  # Должны быть отобраны как минимум TiF4 и MgF2

        # Проверяем, что MgI отфильтрован (низкий confidence для Mg)
        mg_records = [r for r in filtered_records if "Mg" in r.Formula]
        assert len(mg_records) == 0 or all(
            not "MgI" in record.Formula for record in mg_records
        )

        # Проверяем, что TiF4 и MgF2 прошли валидацию
        tif4_records = [r for r in filtered_records if "TiF4" in r.Formula]
        mgf2_records = [r for r in filtered_records if "MgF2" in r.Formula]

        assert len(tif4_records) > 0
        assert len(mgf2_records) > 0

    def test_confidence_calculation_accuracy(self):
        """Тест точности расчета confidence."""
        validator = ReactionValidator()

        # Тестовый случай: точное совпадение формулы и названия
        record = DatabaseRecord(
            Formula="Mg(g)",
            FirstName="Magnesium",
            Phase="g",
            Tmin=298.15,
            Tmax=2000.0,
            ReliabilityClass=1
        )

        result = validator._validate_single_record(
            record, "Mg", "reactant", ["Magnesium"]
        )

        # Проверяем веса: 70% формула + 30% название = 1.0
        expected_confidence = 0.7 * 1.0 + 0.3 * 1.0
        assert abs(result.total_confidence - expected_confidence) < 0.001

        # Тестовый случай: точная формула, но нет названия
        result = validator._validate_single_record(
            record, "Mg", "reactant", []
        )

        # Проверяем веса: 70% формула + 30% отсутствие названия = 0.7
        expected_confidence = 0.7 * 1.0 + 0.3 * 0.0
        assert abs(result.total_confidence - expected_confidence) < 0.001

    def test_error_handling_invalid_data(self):
        """Тест обработки некорректных данных."""
        validator = ReactionValidator()

        # Тест с None значениями
        with pytest.raises(AttributeError):
            validator._calculate_formula_match_score(None, "Mg")

        # Тест с пустыми строками
        score = validator._calculate_formula_match_score("", "Mg")
        assert score == 0.0

        # Тест валидации с некорректными параметрами реакции
        empty_params = ExtractedReactionParameters(
            balanced_equation="",
            all_compounds=[],
            reactants=[],
            products=[],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.0,
            missing_fields=["all"],
            compound_names={}
        )

        filtered_records, validation_results = validator.validate_reaction_compounds(
            [], empty_params
        )

        assert len(filtered_records) == 0
        assert len(validation_results) == 0