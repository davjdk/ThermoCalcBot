"""
Unit-тесты для StatisticsFormatter.
"""

import pytest
from thermo_agents.aggregation.statistics_formatter import StatisticsFormatter
from thermo_agents.models.aggregation import FilterStatistics


@pytest.fixture
def successful_filter_stats():
    """Mock успешной статистики фильтрации."""
    return FilterStatistics(
        stage_1_initial_matches=15,
        stage_1_description="Поиск по формуле",
        stage_2_temperature_filtered=8,
        stage_2_description="Температурная фильтрация (298-673K)",
        stage_3_phase_selected=3,
        stage_3_description="Выбор твёрдой фазы (T<2130K)",
        stage_4_final_selected=1,
        stage_4_description="Приоритизация по надёжности",
        is_found=True
    )


@pytest.fixture
def failed_filter_stats_stage1():
    """Mock статистики с провалом на стадии 1."""
    return FilterStatistics(
        stage_1_initial_matches=0,
        stage_1_description="Поиск по формуле",
        stage_2_temperature_filtered=0,
        stage_2_description="Температурная фильтрация",
        stage_3_phase_selected=0,
        stage_3_description="Выбор фазы",
        stage_4_final_selected=0,
        is_found=False,
        failure_stage=1,
        failure_reason="Вещество не найдено в базе данных"
    )


@pytest.fixture
def failed_filter_stats_stage2():
    """Mock статистики с провалом на стадии 2."""
    return FilterStatistics(
        stage_1_initial_matches=5,
        stage_1_description="Поиск по формуле",
        stage_2_temperature_filtered=0,
        stage_2_description="Температурная фильтрация (298-673K)",
        stage_3_phase_selected=0,
        stage_3_description="Выбор фазы",
        stage_4_final_selected=0,
        is_found=False,
        failure_stage=2,
        failure_reason="Нет данных в указанном температурном диапазоне"
    )


@pytest.fixture
def partial_filter_stats():
    """Mock частичной статистики фильтрации."""
    return FilterStatistics(
        stage_1_initial_matches=3,
        stage_1_description="Поиск по формуле",
        stage_2_temperature_filtered=2,
        stage_2_description="Температурная фильтрация (298-500K)",
        stage_3_phase_selected=1,
        stage_3_description="Выбор фазы",
        stage_4_final_selected=1,
        stage_4_description="Приоритизация по надёжности",
        is_found=True
    )


@pytest.fixture
def statistics_formatter():
    """Экземпляр StatisticsFormatter для тестов."""
    return StatisticsFormatter()


class TestStatisticsFormatter:
    """Тесты для StatisticsFormatter."""

    def test_format_detailed_statistics_success(
        self,
        statistics_formatter,
        successful_filter_stats
    ):
        """Тест форматирования детальной статистики для успешного поиска."""
        detailed_stats = {"TiO2": successful_filter_stats}
        result = statistics_formatter.format_detailed_statistics(detailed_stats)

        assert "📈 Детальная статистика фильтрации:" in result
        assert "TiO2:" in result
        assert "Стадия 1 (Поиск по формуле): найдено 15 записей" in result
        assert "Стадия 2 (Температурная фильтрация (298-673K)): осталось 8 записей" in result
        assert "Стадия 3 (Выбор твёрдой фазы (T<2130K)): осталось 3 записей" in result
        assert "Стадия 4 (Приоритизация по надёжности): выбрана 1 запись" in result
        assert "✅ ВЕЩЕСТВО УСПЕШНО НАЙДЕНО" in result

    def test_format_detailed_statistics_failure_stage1(
        self,
        statistics_formatter,
        failed_filter_stats_stage1
    ):
        """Тест форматирования статистики с провалом на стадии 1."""
        detailed_stats = {"UnknownCompound": failed_filter_stats_stage1}
        result = statistics_formatter.format_detailed_statistics(detailed_stats)

        assert "UnknownCompound:" in result
        assert "Стадия 1 (Поиск по формуле): найдено 0 записей" in result
        assert "❌ ВЕЩЕСТВО НЕ НАЙДЕНО: Вещество не найдено в базе данных" in result

    def test_format_detailed_statistics_failure_stage2(
        self,
        statistics_formatter,
        failed_filter_stats_stage2
    ):
        """Тест форматирования статистики с провалом на стадии 2."""
        detailed_stats = {"PartialCompound": failed_filter_stats_stage2}
        result = statistics_formatter.format_detailed_statistics(detailed_stats)

        assert "PartialCompound:" in result
        assert "Стадия 1 (Поиск по формуле): найдено 5 записей" in result
        assert "Стадия 2 (Температурная фильтрация (298-673K)): осталось 0 записей" in result
        assert "❌ ВЕЩЕСТВО НЕ НАЙДЕНО: Нет данных в указанном температурном диапазоне" in result

    def test_format_detailed_statistics_multiple_compounds(
        self,
        statistics_formatter,
        successful_filter_stats,
        failed_filter_stats_stage1,
        partial_filter_stats
    ):
        """Тест форматирования статистики для нескольких веществ."""
        detailed_stats = {
            "TiO2": successful_filter_stats,
            "UnknownCompound": failed_filter_stats_stage1,
            "PartialCompound": partial_filter_stats
        }
        result = statistics_formatter.format_detailed_statistics(detailed_stats)

        assert "TiO2:" in result
        assert "UnknownCompound:" in result
        assert "PartialCompound:" in result
        assert "✅ ВЕЩЕСТВО УСПЕШНО НАЙДЕНО" in result
        assert "❌ ВЕЩЕСТВО НЕ НАЙДЕНО" in result

    def test_format_detailed_statistics_empty(self, statistics_formatter):
        """Тест форматирования пустой статистики."""
        result = statistics_formatter.format_detailed_statistics({})
        assert result == "📈 Нет статистики для отображения"

    def test_format_summary_statistics_complete(
        self,
        statistics_formatter,
        successful_filter_stats,
        partial_filter_stats
    ):
        """Тест форматирования сводной статистики."""
        detailed_stats = {
            "TiO2": successful_filter_stats,
            "FeO": partial_filter_stats
        }
        result = statistics_formatter.format_summary_statistics(detailed_stats)

        assert "📊 Сводная статистика обработки:" in result
        assert "Всего веществ: 2" in result
        assert "Найдено: 2 (100.0%)" in result
        assert "Отсутствует: 0 (0.0%)" in result
        assert "Всего найденных записей: 18" in result  # 15 + 3
        assert "Выбранных записей: 2" in result
        assert "Коэффициент отбора: 11.1%" in result

    def test_format_summary_statistics_partial(
        self,
        statistics_formatter,
        successful_filter_stats,
        failed_filter_stats_stage1
    ):
        """Тест форматирования сводной статистики с частичным успехом."""
        detailed_stats = {
            "TiO2": successful_filter_stats,
            "UnknownCompound": failed_filter_stats_stage1
        }
        result = statistics_formatter.format_summary_statistics(detailed_stats)

        assert "Всего веществ: 2" in result
        assert "Найдено: 1 (50.0%)" in result
        assert "Отсутствует: 1 (50.0%)" in result

    def test_format_summary_statistics_empty(self, statistics_formatter):
        """Тест форматирования пустой сводной статистики."""
        result = statistics_formatter.format_summary_statistics({})
        assert result == "📊 Нет статистики для отображения"

    def test_format_filtering_efficiency_complete(
        self,
        statistics_formatter,
        successful_filter_stats,
        partial_filter_stats
    ):
        """Тест форматирования эффективности фильтрации."""
        detailed_stats = {
            "TiO2": successful_filter_stats,
            "FeO": partial_filter_stats
        }
        result = statistics_formatter.format_filtering_efficiency(detailed_stats)

        assert "⚡ Эффективность стадий фильтрации:" in result
        assert "Поиск → Температурная фильтрация:" in result
        assert "Температурная → Фазовая фильтрация:" in result
        assert "Фазовая → Приоритезация:" in result

        # Проверить расчётные значения
        # TiO2: 8/15 = 53.3%, 3/8 = 37.5%, 1/3 = 33.3%
        # FeO: 2/3 = 66.7%, 1/2 = 50.0%, 1/1 = 100.0%
        # Средние: (53.3+66.7)/2 = 60.0%, (37.5+50.0)/2 = 43.8%, (33.3+100.0)/2 = 66.7%
        assert "60.0%" in result
        assert "43.8%" in result
        assert "66.7%" in result

    def test_format_filtering_efficiency_empty(self, statistics_formatter):
        """Тест форматирования эффективности с пустыми данными."""
        result = statistics_formatter.format_filtering_efficiency({})
        assert result == "⚡ Нет данных для анализа эффективности"

    def test_format_filtering_efficiency_no_stage_data(self, statistics_formatter):
        """Тест форматирования эффективности без данных на некоторых стадиях."""
        # Создать статистику с нулевыми значениями на всех стадиях
        empty_stats = FilterStatistics(
            stage_1_initial_matches=0,
            stage_1_description="Поиск по формуле",
            stage_2_temperature_filtered=0,
            stage_2_description="Температурная фильтрация",
            stage_3_phase_selected=0,
            stage_3_description="Выбор фазы",
            stage_4_final_selected=0,
            is_found=False
        )

        detailed_stats = {"EmptyCompound": empty_stats}
        result = statistics_formatter.format_filtering_efficiency(detailed_stats)

        assert "Поиск → Температурная фильтрация: нет данных" in result
        assert "Температурная → Фазовая фильтрация: нет данных" in result
        assert "Фазовая → Приоритезация: нет данных" in result

    def test_pluralization_in_statistics(self, statistics_formatter, successful_filter_stats):
        """Тест правильного склонения существительных в статистике."""
        # Проверить разные значения для правильного склонения "запись"
        test_cases = [
            (1, "запись"),
            (2, "записи"),
            (4, "записи"),
            (5, "записей")
        ]

        for final_selected, expected_word in test_cases:
            stats = FilterStatistics(
                stage_1_initial_matches=10,
                stage_1_description="Поиск по формуле",
                stage_2_temperature_filtered=5,
                stage_2_description="Температурная фильтрация",
                stage_3_phase_selected=2,
                stage_3_description="Выбор фазы",
                stage_4_final_selected=final_selected,
                stage_4_description="Приоритизация по надёжности",
                is_found=True
            )

            detailed_stats = {"TestCompound": stats}
            result = statistics_formatter.format_detailed_statistics(detailed_stats)
            assert f"выбрана {final_selected} {expected_word}" in result