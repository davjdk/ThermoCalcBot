"""
Оптимизированный ReactionAggregator для агрегации результатов поиска.

Класс отвечает за объединение результатов поиска по отдельным веществам
в единую структуру данных по реакции с генерацией предупреждений
и рекомендаций. Использует прямые вызовы без message passing.
"""

from typing import Dict, List, Optional

from ..models.aggregation import (
    AggregatedReactionData,
    FilterStatistics,
)
from ..models.search import CompoundSearchResult, SearchStatistics


class ReactionAggregator:
    """Агрегация результатов поиска по всем веществам реакции."""

    def __init__(self, max_compounds: int = 10):
        """
        Инициализация агрегатора.

        Args:
            max_compounds: Максимальное количество веществ (по ТЗ: до 10)
        """
        self.max_compounds = max_compounds

    def aggregate_reaction_data(
        self, reaction_equation: str, compounds_results: List[CompoundSearchResult]
    ) -> AggregatedReactionData:
        """
        Агрегация данных по всем веществам реакции.

        Args:
            reaction_equation: Уравнение реакции "A + B → C + D"
            compounds_results: Результаты поиска для каждого вещества

        Returns:
            AggregatedReactionData с полной информацией

        Raises:
            ValueError: Если превышено максимальное количество веществ
        """
        # Валидация количества веществ
        if len(compounds_results) > self.max_compounds:
            raise ValueError(
                f"Превышено максимальное количество веществ: "
                f"{len(compounds_results)} > {self.max_compounds}"
            )

        # Разделение на найденные/ненайденные
        found_compounds = []
        missing_compounds = []
        filtered_out_compounds = []  # Новая категория: найдены, но отфильтрованы

        for result in compounds_results:
            # Проверяем, были ли найдены данные изначально
            # Используем stage_1_initial_matches из FilterStatistics
            has_initial_data = (
                result.filter_statistics and
                result.filter_statistics.stage_1_initial_matches > 0
            )

            # Проверяем, остались ли данные после фильтрации
            has_final_data = result.records_found and len(result.records_found) > 0

            if has_initial_data:
                if has_final_data:
                    found_compounds.append(result.compound_formula)
                else:
                    # Данные были найдены, но отклонены при фильтрации
                    filtered_out_compounds.append(result.compound_formula)
            else:
                missing_compounds.append(result.compound_formula)

        # Определение статуса полноты
        total_compounds = len(compounds_results)
        if len(found_compounds) == total_compounds:
            completeness_status = "complete"
        elif len(found_compounds) > 0 or len(filtered_out_compounds) > 0:
            completeness_status = "partial"
        else:
            completeness_status = "incomplete"

        # Сбор детальной статистики
        detailed_statistics = {
            result.compound_formula: result.filter_statistics
            for result in compounds_results
            if result.filter_statistics is not None
        }

        # Генерация предупреждений
        warnings = self._generate_warnings(compounds_results)

        # Генерация рекомендаций
        recommendations = self._generate_recommendations(
            missing_compounds, completeness_status, filtered_out_compounds
        )

        return AggregatedReactionData.model_construct(
            reaction_equation=reaction_equation,
            compounds_data=compounds_results,
            summary_table_formatted="",  # Заполняется TableFormatter
            completeness_status=completeness_status,
            missing_compounds=missing_compounds,
            found_compounds=found_compounds,
            filtered_out_compounds=filtered_out_compounds,  # Новое поле
            detailed_statistics=detailed_statistics,
            warnings=warnings,
            recommendations=recommendations,
        )

    def _generate_warnings(
        self, compounds_results: List[CompoundSearchResult]
    ) -> List[str]:
        """Генерация предупреждений на основе результатов."""
        warnings = []

        for result in compounds_results:
            # Проверяем, были ли данные отфильтрованы
            has_initial_data = (
                result.filter_statistics and
                result.filter_statistics.stage_1_initial_matches > 0
            )
            has_final_data = result.records_found and len(result.records_found) > 0

            if has_initial_data and not has_final_data:
                warnings.append(
                    f"Для {result.compound_formula} данные были найдены, "
                    f"но отклонены при фильтрации (возможно, несоответствие фазы)"
                )

            # Предупреждение о частичном покрытии
            if result.coverage_status == "partial":
                warnings.append(
                    f"Для {result.compound_formula} частичное покрытие "
                    f"температурного диапазона"
                )

            # Предупреждения из самого результата
            if result.warnings:
                warnings.extend(result.warnings)

            # Предупреждение о низком классе надёжности
            if result.records_found and len(result.records_found) > 0:
                top_record = result.records_found[0]
                if top_record.reliability_class and top_record.reliability_class > 2:
                    warnings.append(
                        f"Для {result.compound_formula} низкий класс надёжности данных "
                        f"(класс {top_record.reliability_class})"
                    )

        return warnings

    def _generate_recommendations(
        self, missing_compounds: List[str], completeness_status: str,
        filtered_out_compounds: List[str] = None
    ) -> List[str]:
        """Генерация рекомендаций пользователю."""
        recommendations = []

        if completeness_status == "incomplete":
            recommendations.append(
                "Попробуйте изменить температурный диапазон или "
                "уточните химические формулы веществ"
            )

        if missing_compounds:
            recommendations.append(
                f"Отсутствуют данные для: {', '.join(missing_compounds)}"
            )

        if completeness_status == "partial":
            recommendations.append(
                "Для некоторых веществ доступны только частичные данные. "
                "Рассмотрите возможность расширения температурного диапазона."
            )

        # Новая рекомендация для отфильтрованных веществ
        if filtered_out_compounds:
            recommendations.append(
                f"Для веществ {', '.join(filtered_out_compounds)} данные были найдены, "
                "но отклонены из-за несоответствия фазы. "
                "Попробуйте указать другую фазу в запросе или измените температурный диапазон."
            )

        # Рекомендация по проверке формул
        if missing_compounds and len(missing_compounds) > 1:
            recommendations.append(
                "Проверьте правильность написания химических формул. "
                "Используйте стандартные обозначения (H2O, CO2, NH3 и т.д.)"
            )

        return recommendations

    def _convert_search_statistics_to_filter_statistics(
        self, search_stats: Optional[SearchStatistics]
    ) -> Optional[FilterStatistics]:
        """
        Конвертация SearchStatistics в FilterStatistics для обратной совместимости.

        Args:
            search_stats: SearchStatistics из CompoundSearchResult

        Returns:
            FilterStatistics или None
        """
        if search_stats is None:
            return None

        # Создаем упрощенную FilterStatistics на основе SearchStatistics
        return FilterStatistics(
            stage_1_initial_matches=search_stats.total_records,
            stage_1_description="Поиск по формуле",
            stage_2_temperature_filtered=search_stats.total_records,  # Упрощенно
            stage_2_description="Температурная фильтрация",
            stage_3_phase_selected=len(search_stats.phase_distribution)
            if search_stats.phase_distribution
            else search_stats.total_records,
            stage_3_description="Выбор фазы",
            stage_4_final_selected=1,  # Упрощенно - одна лучшая запись
            stage_4_description="Приоритизация по надёжности",
            is_found=search_stats.total_records > 0,
        )

    def validate_compound_results(
        self, compounds_results: List[CompoundSearchResult]
    ) -> List[str]:
        """
        Валидация результатов поиска веществ.

        Args:
            compounds_results: Результаты поиска для валидации

        Returns:
            Список ошибок валидации
        """
        errors = []

        for i, result in enumerate(compounds_results):
            if not result.compound_formula:
                errors.append(f"Вещество {i + 1}: отсутствует формула")

            if result.filter_statistics is None:
                errors.append(
                    f"Вещество {result.compound_formula}: отсутствует статистика"
                )

        return errors
