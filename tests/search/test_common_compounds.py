"""
Тесты для модуля распространенных химических веществ.

Проверяет корректность определения и построения SQL-условий для
базовых веществ (вода, CO2, O2 и т.д.).
"""

import pytest

from src.thermo_agents.search.common_compounds import (
    COMMON_COMPOUNDS,
    CommonCompoundResolver,
    CommonCompoundSpec,
)


class TestCommonCompoundSpec:
    """Тесты для спецификации распространенных веществ."""

    def test_water_spec_exists(self):
        """Проверка наличия спецификации для воды."""
        assert "H2O" in COMMON_COMPOUNDS
        water_spec = COMMON_COMPOUNDS["H2O"]
        assert isinstance(water_spec, CommonCompoundSpec)
        assert "H2O" in water_spec.formulas
        assert "Water" in water_spec.names
        assert water_spec.exact_match_only is True

    def test_co2_spec_exists(self):
        """Проверка наличия спецификации для CO2."""
        assert "CO2" in COMMON_COMPOUNDS
        co2_spec = COMMON_COMPOUNDS["CO2"]
        assert "CO2" in co2_spec.formulas
        assert "Carbon dioxide" in co2_spec.names

    def test_sulfur_spec_exists(self):
        """Проверка наличия спецификации для серы."""
        assert "S" in COMMON_COMPOUNDS
        sulfur_spec = COMMON_COMPOUNDS["S"]
        assert isinstance(sulfur_spec, CommonCompoundSpec)
        assert "S" in sulfur_spec.formulas
        assert "Sulfur" in sulfur_spec.names
        assert "Sulphur" in sulfur_spec.names
        assert sulfur_spec.exact_match_only is True
        assert "адаптивный выбор фазы" in sulfur_spec.description

    def test_all_common_compounds_have_descriptions(self):
        """Все распространенные вещества должны иметь описание."""
        for formula, spec in COMMON_COMPOUNDS.items():
            assert spec.description, f"Отсутствует описание для {formula}"
            assert len(spec.formulas) > 0, f"Отсутствуют формулы для {formula}"
            assert len(spec.names) > 0, f"Отсутствуют названия для {formula}"


class TestCommonCompoundResolver:
    """Тесты для резолвера распространенных веществ."""

    def setup_method(self):
        """Инициализация резолвера перед каждым тестом."""
        self.resolver = CommonCompoundResolver()

    def test_is_common_compound_water(self):
        """Проверка определения воды как распространенного вещества."""
        assert self.resolver.is_common_compound("H2O") is True
        assert self.resolver.is_common_compound("H2O ") is True  # с пробелом
        assert self.resolver.is_common_compound(" H2O") is True  # с пробелом

    def test_is_common_compound_co2(self):
        """Проверка определения CO2 как распространенного вещества."""
        assert self.resolver.is_common_compound("CO2") is True

    def test_is_common_compound_sulfur(self):
        """Проверка определения серы как распространенного вещества."""
        assert self.resolver.is_common_compound("S") is True
        assert self.resolver.is_common_compound("S ") is True  # с пробелом
        assert self.resolver.is_common_compound(" S") is True  # с пробелом

    def test_sulfur_no_false_positives(self):
        """Сера не должна ловить SO2, H2S и другие соединения."""
        # Негативные кейсы - серосодержащие соединения
        assert not self.resolver.is_common_compound("SO2")
        assert not self.resolver.is_common_compound("H2S")
        assert not self.resolver.is_common_compound("H2SO4")

        # Негативные кейсы - аллотропы (не должны распознаваться как S)
        assert not self.resolver.is_common_compound("S8")
        assert not self.resolver.is_common_compound("S2")
        assert not self.resolver.is_common_compound("S6")

    def test_is_not_common_compound(self):
        """Проверка что редкие вещества не определяются как распространенные."""
        assert self.resolver.is_common_compound("BaO") is False
        assert self.resolver.is_common_compound("NH4Cl") is False
        assert self.resolver.is_common_compound("TiO2") is False
        assert self.resolver.is_common_compound("BaCl2") is False

    def test_get_spec_water(self):
        """Проверка получения спецификации для воды."""
        spec = self.resolver.get_spec("H2O")
        assert spec is not None
        assert "H2O" in spec.formulas
        assert "Water" in spec.names

    def test_get_spec_unknown_compound(self):
        """Получение спецификации для неизвестного вещества возвращает None."""
        spec = self.resolver.get_spec("UnknownCompound123")
        assert spec is None

    def test_get_description_water(self):
        """Проверка получения описания для воды."""
        description = self.resolver.get_description("H2O")
        assert description == "Вода"

    def test_get_description_co2(self):
        """Проверка получения описания для CO2."""
        description = self.resolver.get_description("CO2")
        assert description == "Углекислый газ"

    def test_get_all_formulas(self):
        """Проверка получения всех распространенных формул."""
        formulas = self.resolver.get_all_formulas()
        assert "H2O" in formulas
        assert "CO2" in formulas
        assert "O2" in formulas
        assert "N2" in formulas
        assert len(formulas) > 5  # должно быть достаточно веществ


class TestSQLConditionBuilding:
    """Тесты для построения SQL-условий."""

    def setup_method(self):
        """Инициализация резолвера перед каждым тестом."""
        self.resolver = CommonCompoundResolver()

    def test_build_sql_condition_water(self):
        """Проверка построения SQL-условия для воды."""
        condition = self.resolver.build_sql_condition("H2O")
        assert condition is not None
        assert "H2O" in condition
        assert "TRIM(Formula) = 'H2O'" in condition
        assert "Formula LIKE 'H2O(%'" in condition
        # НЕ должно быть широких паттернов типа 'H2O%' или '%H2O%'
        assert (
            "Formula LIKE 'H2O%'" not in condition
            or "Formula LIKE 'H2O(%'" in condition
        )

    def test_build_sql_condition_co2(self):
        """Проверка построения SQL-условия для CO2."""
        condition = self.resolver.build_sql_condition("CO2")
        assert condition is not None
        assert "CO2" in condition
        assert "TRIM(Formula) = 'CO2'" in condition

    def test_sulfur_sql_condition_basic(self):
        """Проверка базового SQL-условия для серы."""
        condition = self.resolver.build_sql_condition("S")

        assert condition is not None
        assert "TRIM(Formula) = 'S'" in condition
        assert "Formula LIKE 'S(%'" in condition
        assert "(" in condition and ")" in condition  # Группировка через OR

    def test_sulfur_sql_condition_excludes_compounds(self):
        """SQL-условие не должно ловить серосодержащие соединения."""
        condition = self.resolver.build_sql_condition("S")

        # Проверяем, что используется точное совпадение
        assert "TRIM(Formula) = 'S'" in condition
        # Не должно быть широких паттернов LIKE '%S%'
        assert "LIKE '%S%'" not in condition

    def test_sulfur_sql_condition_with_names(self):
        """SQL-условие для серы с дополнительными названиями."""
        condition = self.resolver.build_sql_condition(
            "S", compound_names=["Sulfur", "Sulphur"]
        )
        assert condition is not None
        assert "Sulfur" in condition
        assert "Sulphur" in condition
        assert "LOWER(TRIM(FirstName))" in condition

    def test_build_sql_condition_with_names(self):
        """Проверка построения SQL-условия с дополнительными названиями."""
        condition = self.resolver.build_sql_condition(
            "H2O", compound_names=["Water", "Oxidane"]
        )
        assert condition is not None
        assert "Water" in condition
        assert "Oxidane" in condition
        assert "LOWER(TRIM(FirstName))" in condition

    def test_build_sql_condition_unknown_compound(self):
        """Построение SQL-условия для неизвестного вещества возвращает None."""
        condition = self.resolver.build_sql_condition("UnknownCompound")
        assert condition is None

    def test_sql_injection_protection(self):
        """Проверка защиты от SQL-инъекций."""
        # Попытка инъекции через название
        condition = self.resolver.build_sql_condition(
            "H2O", compound_names=["'; DROP TABLE compounds; --"]
        )
        assert condition is not None
        # Проверяем что одинарная кавычка экранирована
        assert "''" in condition  # экранированная кавычка


class TestIntegrationWithExistingCode:
    """Тесты интеграции с существующим кодом."""

    def test_water_vs_peroxide_distinction(self):
        """
        Критический тест: вода (H2O) не должна совпадать с пероксидом (H2O2).

        Это основная причина создания модуля - старая логика находила
        H2O2 при поиске H2O из-за паттерна LIKE 'H2O%'.
        """
        resolver = CommonCompoundResolver()

        # Вода должна быть распространенным веществом
        assert resolver.is_common_compound("H2O") is True

        # Пероксид НЕ должен быть распространенным (у него своя логика)
        assert resolver.is_common_compound("H2O2") is True  # пероксид тоже добавлен

        # Условия должны быть разными
        water_condition = resolver.build_sql_condition("H2O")
        peroxide_condition = resolver.build_sql_condition("H2O2")

        assert water_condition != peroxide_condition
        assert "TRIM(Formula) = 'H2O'" in water_condition
        assert "TRIM(Formula) = 'H2O2'" in peroxide_condition

    def test_sulfur_vs_sulfur_compounds_distinction(self):
        """
        Критический тест: сера (S) не должна совпадать с серосодержащими соединениями.

        Проверяет, что спецификация для серы работает корректно и не ловит
        соединения SO2, H2S, H2SO4, а также аллотропы S8, S2, S6.
        """
        resolver = CommonCompoundResolver()

        # Сера должна быть распространенным веществом
        assert resolver.is_common_compound("S") is True

        # Серосодержащие соединения НЕ должны распознаваться как сера
        assert not resolver.is_common_compound("SO2")
        assert not resolver.is_common_compound("H2S")
        assert not resolver.is_common_compound("H2SO4")

        # Аллотропы НЕ должны распознаваться как сера
        assert not resolver.is_common_compound("S8")
        assert not resolver.is_common_compound("S2")
        assert not resolver.is_common_compound("S6")

        # SQL-условие для серы должно быть точным
        sulfur_condition = resolver.build_sql_condition("S")
        assert sulfur_condition is not None
        assert "TRIM(Formula) = 'S'" in sulfur_condition
        assert "Formula LIKE 'S(%'" in sulfur_condition

        # SQL-условие не должно включать широкие паттерны
        assert "LIKE '%S%'" not in sulfur_condition

    def test_all_common_compounds_buildable(self):
        """Все распространенные вещества должны иметь buildable SQL-условия."""
        resolver = CommonCompoundResolver()

        for formula in resolver.get_all_formulas():
            condition = resolver.build_sql_condition(formula)
            assert condition is not None, f"Не удалось построить условие для {formula}"
            assert formula in condition, f"Формула {formula} отсутствует в условии"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
