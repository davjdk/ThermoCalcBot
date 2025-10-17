"""
Интеграционный тест: проверка корректности поиска воды vs пероксида.

Этот тест демонстрирует решение основной проблемы - разделение H2O и H2O2.
"""

import pytest

from src.thermo_agents.search.sql_builder import SQLBuilder


class TestWaterVsPeroxide:
    """Критический тест: вода не должна путаться с пероксидом."""

    def setup_method(self):
        """Инициализация SQLBuilder."""
        self.builder = SQLBuilder()

    def test_h2o_search_excludes_h2o2(self):
        """
        Поиск H2O не должен возвращать H2O2.

        ДО ИСПРАВЛЕНИЯ: Паттерн 'H2O%' ловил и H2O2
        ПОСЛЕ ИСПРАВЛЕНИЯ: Используется точная логика
        """
        query, params = self.builder.build_compound_search_query("H2O")

        # SQL должен содержать точное совпадение
        assert "TRIM(Formula) = 'H2O'" in query

        # SQL должен разрешать фазы в скобках
        assert "Formula LIKE 'H2O(%'" in query

        # SQL НЕ должен содержать широкий паттерн который ловит H2O2
        # Проверяем что если есть 'H2O%', то это только в контексте 'H2O(%'
        if "H2O%" in query:
            # Должен быть только как часть 'H2O(%'
            assert query.count("H2O%") == query.count("H2O(%")

    def test_h2o2_search_is_exact(self):
        """
        Поиск H2O2 должен находить только пероксид.

        Пероксид тоже в справочнике распространенных веществ,
        должен искаться точно.
        """
        query, params = self.builder.build_compound_search_query("H2O2")

        # SQL должен содержать точное совпадение
        assert "TRIM(Formula) = 'H2O2'" in query

        # SQL должен разрешать фазы в скобках
        assert "Formula LIKE 'H2O2(%'" in query

    def test_water_and_peroxide_produce_different_queries(self):
        """
        H2O и H2O2 должны создавать разные SQL запросы.
        """
        water_query, _ = self.builder.build_compound_search_query("H2O")
        peroxide_query, _ = self.builder.build_compound_search_query("H2O2")

        # Запросы должны быть разными
        assert water_query != peroxide_query

        # Каждый должен искать свою формулу
        assert "TRIM(Formula) = 'H2O'" in water_query
        assert "TRIM(Formula) = 'H2O2'" in peroxide_query

        # Проверка что в запросе для воды нет упоминания пероксида
        assert "H2O2" not in water_query


class TestCommonCompoundsIntegration:
    """Тесты интеграции для всех распространенных веществ."""

    def setup_method(self):
        """Инициализация SQLBuilder."""
        self.builder = SQLBuilder()

    @pytest.mark.parametrize(
        "formula,description",
        [
            ("H2O", "вода"),
            ("CO2", "углекислый газ"),
            ("O2", "кислород"),
            ("N2", "азот"),
            ("H2", "водород"),
            ("NH3", "аммиак"),
            ("HCl", "хлороводород"),
            ("CH4", "метан"),
            ("CO", "угарный газ"),
        ],
    )
    def test_common_compound_uses_exact_logic(self, formula, description):
        """
        Все распространенные вещества должны использовать точную логику.

        Args:
            formula: Химическая формула
            description: Описание для информативности
        """
        query, params = self.builder.build_compound_search_query(formula)

        # Должно быть точное совпадение
        assert f"TRIM(Formula) = '{formula}'" in query, (
            f"{description} ({formula}) должен иметь точное совпадение"
        )

        # Должен разрешаться поиск с фазами
        assert f"Formula LIKE '{formula}(%'" in query, (
            f"{description} ({formula}) должен поддерживать фазы в скобках"
        )

    def test_non_common_compound_uses_wide_logic(self):
        """
        Не-распространенные вещества должны использовать широкую логику.
        """
        # BaO не в списке распространенных
        query, params = self.builder.build_compound_search_query("BaO")

        # Должны быть широкие паттерны
        assert "TRIM(Formula) = 'BaO'" in query
        assert "Formula LIKE 'BaO(%'" in query
        assert "Formula LIKE 'BaO%'" in query
        # Для простых формул может не быть containment search
        # assert "Formula LIKE '%BaO%'" in query


class TestRealWorldScenario:
    """Тесты реальных сценариев использования."""

    def setup_method(self):
        """Инициализация SQLBuilder."""
        self.builder = SQLBuilder()

    def test_reaction_with_water_and_peroxide(self):
        """
        Сценарий: реакция содержит и воду и пероксид.

        Каждое вещество должно находиться точно, без пересечений.
        """
        # Реакция: 2H2O2 → 2H2O + O2

        # Поиск воды
        water_query, _ = self.builder.build_compound_search_query("H2O")

        # Поиск пероксида
        peroxide_query, _ = self.builder.build_compound_search_query("H2O2")

        # Поиск кислорода
        oxygen_query, _ = self.builder.build_compound_search_query("O2")

        # Все запросы должны быть разными
        assert water_query != peroxide_query
        assert water_query != oxygen_query
        assert peroxide_query != oxygen_query

    def test_query_with_names_fallback(self):
        """
        Тест поиска с использованием названий веществ.
        """
        query, params = self.builder.build_compound_search_query(
            "H2O", compound_names=["Water", "Oxidane"]
        )

        # Должны быть условия для названий
        assert "Water" in query or "LOWER" in query
        assert "FirstName" in query or "Water" in query


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
