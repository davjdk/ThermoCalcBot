"""
Тесты классификации типов запросов для ExtractedReactionParameters.

Проверяет корректность работы новых полей:
- query_type: "compound_data" vs "reaction_calculation"
- temperature_step_k: валидация диапазона 25-250K
"""

import pytest
import warnings
from src.thermo_agents.models.extraction import ExtractedReactionParameters


class TestQueryClassification:
    """Тесты классификации типов запросов."""

    def test_compound_data_single_substance(self):
        """Один вещество → compound_data."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["H2O"],
            reactants=[],
            products=[],
            temperature_range_k=[300, 600],
            extraction_confidence=1.0,
            compound_names={"H2O": ["Water", "вода"]},
            temperature_step_k=50
        )

        assert params.query_type == "compound_data"
        assert params.temperature_step_k == 50
        assert len(params.all_compounds) == 1
        assert params.reactants == []
        assert params.products == []

    def test_reaction_calculation_with_arrow(self):
        """Наличие → и 2+ вещества → reaction_calculation."""
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="2 W + 4 Cl2 + O2 → 2 WOCl4",
            all_compounds=["W", "Cl2", "O2", "WOCl4"],
            reactants=["W", "Cl2", "O2"],
            products=["WOCl4"],
            temperature_range_k=[600, 900],
            extraction_confidence=1.0,
            compound_names={
                "W": ["Tungsten"],
                "Cl2": ["Chlorine"],
                "O2": ["Oxygen"],
                "WOCl4": ["Tungsten oxychloride"]
            },
            temperature_step_k=25
        )

        assert params.query_type == "reaction_calculation"
        assert params.temperature_step_k == 25
        assert len(params.all_compounds) == 4
        assert len(params.reactants) == 3
        assert len(params.products) == 1

    def test_compound_data_empty_equation(self):
        """compound_data может иметь пустое уравнение."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["WCl6"],
            reactants=[],
            products=[],
            temperature_range_k=[298, 1000],
            extraction_confidence=0.9,
            compound_names={"WCl6": ["Tungsten hexachloride"]},
            temperature_step_k=100
        )

        assert params.query_type == "compound_data"
        assert params.balanced_equation == ""

    @pytest.mark.parametrize("step_k,expected_valid", [
        (25, True),   # Минимум
        (50, True),   # Валидный
        (100, True),  # По умолчанию
        (250, True),  # Максимум
        (10, False),  # Слишком маленький
        (300, False), # Слишком большой
        (37, True),   # Некратный 25 (warning, но валидный)
    ])
    def test_temperature_step_boundaries(self, step_k, expected_valid):
        """Проверка границ шага температуры."""
        if expected_valid:
            params = ExtractedReactionParameters(
                query_type="compound_data",
                temperature_step_k=step_k,
                balanced_equation="",
                all_compounds=["H2O"],
                reactants=[],
                products=[],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"]}
            )
            assert params.temperature_step_k == step_k
        else:
            with pytest.raises(ValueError):
                ExtractedReactionParameters(
                    query_type="compound_data",
                    temperature_step_k=step_k,
                    balanced_equation="",
                    all_compounds=["H2O"],
                    reactants=[],
                    products=[],
                    temperature_range_k=[298, 1000],
                    extraction_confidence=1.0,
                    compound_names={"H2O": ["Water"]}
                )

    def test_temperature_step_warning_for_non_multiple(self):
        """Некратный 25 шаг должен генерировать предупреждение."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            params = ExtractedReactionParameters(
                query_type="compound_data",
                temperature_step_k=37,  # Не кратно 25
                balanced_equation="",
                all_compounds=["H2O"],
                reactants=[],
                products=[],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"]}
            )

            # Проверяем, что было сгенерировано предупреждение
            assert len(w) == 1
            assert "Рекомендуется использовать шаг кратный 25K" in str(w[0].message)
            assert params.temperature_step_k == 37

    def test_consistency_validation_compound_data_multiple_substances(self):
        """compound_data с несколькими веществами → ошибка."""
        with pytest.raises(ValueError, match="compound_data должен содержать одно вещество"):
            ExtractedReactionParameters(
                query_type="compound_data",
                balanced_equation="",
                all_compounds=["H2O", "CO2"],  # Два вещества!
                reactants=[],
                products=[],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"], "CO2": ["Carbon dioxide"]}
            )

    def test_consistency_validation_compound_data_with_reactants(self):
        """compound_data с реагентами → ошибка."""
        with pytest.raises(ValueError, match="compound_data не должен содержать reactants/products"):
            ExtractedReactionParameters(
                query_type="compound_data",
                balanced_equation="",
                all_compounds=["H2O"],
                reactants=["H2O"],  # Не должно быть!
                products=[],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"]}
            )

    def test_consistency_validation_compound_data_with_products(self):
        """compound_data с продуктами → ошибка."""
        with pytest.raises(ValueError, match="compound_data не должен содержать reactants/products"):
            ExtractedReactionParameters(
                query_type="compound_data",
                balanced_equation="",
                all_compounds=["H2O"],
                reactants=[],
                products=["H2O"],  # Не должно быть!
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"]}
            )

    def test_consistency_validation_reaction_calculation_single_substance(self):
        """reaction_calculation с одним веществом → ошибка."""
        with pytest.raises(ValueError, match="reaction_calculation требует минимум 2 вещества"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="H2O → H2O",
                all_compounds=["H2O"],  # Только одно!
                reactants=["H2O"],
                products=["H2O"],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"]}
            )

    def test_consistency_validation_reaction_calculation_no_equation(self):
        """reaction_calculation без уравнения → ошибка."""
        with pytest.raises(ValueError, match="reaction_calculation требует balanced_equation"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="",  # Пустое!
                all_compounds=["H2O", "CO2"],
                reactants=["H2O"],
                products=["CO2"],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"], "CO2": ["Carbon dioxide"]}
            )

    def test_consistency_validation_reaction_calculation_na_equation(self):
        """reaction_calculation с уравнением "N/A" → ошибка."""
        with pytest.raises(ValueError, match="reaction_calculation требует balanced_equation"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="N/A",  # Недопустимо!
                all_compounds=["H2O", "CO2"],
                reactants=["H2O"],
                products=["CO2"],
                temperature_range_k=[298, 1000],
                extraction_confidence=1.0,
                compound_names={"H2O": ["Water"], "CO2": ["Carbon dioxide"]}
            )

    def test_reaction_calculation_valid_case(self):
        """Валидный reaction_calculation проходит проверку."""
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="Fe2O3 + 3H2 → 2Fe + 3H2O",
            all_compounds=["Fe2O3", "H2", "Fe", "H2O"],
            reactants=["Fe2O3", "H2"],
            products=["Fe", "H2O"],
            temperature_range_k=[500, 800],
            extraction_confidence=0.95,
            compound_names={
                "Fe2O3": ["Iron(III) oxide"],
                "H2": ["Hydrogen"],
                "Fe": ["Iron"],
                "H2O": ["Water"]
            },
            temperature_step_k=75
        )

        assert params.query_type == "reaction_calculation"
        assert len(params.all_compounds) == 4
        assert params.balanced_equation == "Fe2O3 + 3H2 → 2Fe + 3H2O"

    def test_default_temperature_step(self):
        """По умолчанию temperature_step_k = 100."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["H2O"],
            reactants=[],
            products=[],
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            compound_names={"H2O": ["Water"]}
            # temperature_step_k не указан
        )

        assert params.temperature_step_k == 100

    def test_compound_data_with_empty_reactants_products_allowed(self):
        """compound_data с пустыми списками реагентов/продуктов разрешен."""
        params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["NH3"],
            reactants=[],  # Пусто - это ок для compound_data
            products=[],   # Пусто - это ок для compound_data
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            compound_names={"NH3": ["Ammonia"]}
        )

        assert params.query_type == "compound_data"
        assert params.reactants == []
        assert params.products == []

    def test_edge_case_10_compounds_reaction(self):
        """Граничный случай: reaction с 10 соединениями (максимум)."""
        compounds = [f"C{i}H{i}" for i in range(1, 11)]  # 10 соединений
        reactants = compounds[:5]
        products = compounds[5:]

        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation=" + ".join(reactants) + " → " + " + ".join(products),
            all_compounds=compounds,
            reactants=reactants,
            products=products,
            temperature_range_k=[298, 1000],
            extraction_confidence=1.0,
            compound_names={comp: [f"Compound {i}"] for i, comp in enumerate(compounds, 1)}
        )

        assert len(params.all_compounds) == 10
        assert params.query_type == "reaction_calculation"