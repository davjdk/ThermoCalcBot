"""
Стадия валидации соединений против уравнения реакции.

Это Stage 0 в конвейере фильтрации - выполняется перед температурной фильтрацией
и другими стадиями. Использует ReactionValidator для мягкой валидации по названиям.
"""

from typing import List, Dict, Any, Optional
import logging

from .filter_pipeline import FilterStage, FilterContext
from .reaction_validator import ReactionValidator, CompoundValidationResult
from ..models.search import DatabaseRecord
from ..models.extraction import ExtractedReactionParameters

logger = logging.getLogger(__name__)


class ReactionValidationStage(FilterStage):
    """
    Стадия валидации соединений против уравнения реакции.

    Выполняет:
    1. Валидацию формул против уравнения реакции
    2. Мягкую валидацию по названиям веществ
    3. Приоритизацию точных совпадений
    4. Фильтрацию на основе confidence score
    """

    def __init__(
        self,
        min_confidence_threshold: float = 0.5,
        max_records_per_compound: int = 3,
        enable_name_validation: bool = True
    ):
        """
        Args:
            min_confidence_threshold: Минимальный confidence score для сохранения записи
            max_records_per_compound: Максимальное количество записей на соединение
            enable_name_validation: Включить ли валидацию по названиям
        """
        super().__init__()
        self.min_confidence_threshold = min_confidence_threshold
        self.max_records_per_compound = max_records_per_compound
        self.enable_name_validation = enable_name_validation
        self.validator = ReactionValidator()
        self._last_validation_results: Dict[str, CompoundValidationResult] = {}

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Применяет валидацию реакции к записям.

        Args:
            records: Список записей из БД
            context: Контекст с параметрами реакции

        Returns:
            Отфильтрованный список записей
        """
        if not context.reaction_params:
            logger.warning("Отсутствуют параметры реакции в контексте")
            self.last_stats = {
                'validation_applied': False,
                'reason': 'No reaction parameters in context',
                'records_before': len(records),
                'records_after': len(records)
            }
            return records

        logger.info(
            f"Stage 0 - Валидация реакции для {context.compound_formula}, "
            f"уравнение: {context.reaction_params.balanced_equation}"
        )

        # Валидация соединений
        filtered_records, validation_results = self.validator.validate_reaction_compounds(
            records, context.reaction_params
        )

        # Сохраняем результаты для последующего анализа
        self._last_validation_results = validation_results

        # Фильтруем по порогу confidence
        final_records = []
        for record in filtered_records:
            # Находим соответствующий результат валидации
            validation_result = self._find_validation_result(record, validation_results)
            if validation_result and validation_result.total_confidence >= self.min_confidence_threshold:
                final_records.append(record)

        # Ограничиваем количество записей на соединение
        if len(final_records) > self.max_records_per_compound:
            final_records = self._limit_records_per_compound(final_records, context)

        # Формируем статистику
        target_compound = context.compound_formula
        target_result = validation_results.get(target_compound)

        stats = {
            'validation_applied': True,
            'reaction_equation': context.reaction_params.balanced_equation,
            'target_compound': target_compound,
            'target_role': self._get_compound_role(target_compound, context.reaction_params),
            'records_before': len(records),
            'records_after_validation': len(filtered_records),
            'records_after_threshold': len(final_records),
            'confidence_threshold': self.min_confidence_threshold,
            'name_validation_enabled': self.enable_name_validation,
            'validation_summary': target_result.validation_summary if target_result else 'No validation result',
            'best_confidence': target_result.best_result.total_confidence if target_result and target_result.best_result else 0.0,
            'best_record_reasoning': target_result.best_result.reasoning if target_result and target_result.best_result else 'No best result'
        }

        self.last_stats = stats

        logger.info(
            f"Валидация завершена: {len(records)} → {len(final_records)} записей. "
            f"Лучший confidence: {stats['best_confidence']:.3f}"
        )

        return final_records

    def _find_validation_result(
        self,
        record: DatabaseRecord,
        validation_results: Dict[str, CompoundValidationResult]
    ) -> Optional[Any]:
        """Находит результат валидации для конкретной записи."""
        for compound_result in validation_results.values():
            for validation_result in compound_result.all_results:
                if validation_result.record == record:
                    return validation_result
        return None

    def _limit_records_per_compound(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """Ограничивает количество записей для одного соединения."""
        # Если записей меньше лимита, возвращаем как есть
        if len(records) <= self.max_records_per_compound:
            return records

        # Сортируем по confidence (используем результаты валидации)
        records_with_confidence = []
        for record in records:
            validation_result = self._find_validation_result(record, self._last_validation_results)
            confidence = validation_result.total_confidence if validation_result else 0.0
            records_with_confidence.append((record, confidence))

        # Сортируем по confidence (убывание)
        records_with_confidence.sort(key=lambda x: x[1], reverse=True)

        # Берем лучшие записи
        limited_records = [record for record, _ in records_with_confidence[:self.max_records_per_compound]]

        logger.info(
            f"Ограничено количество записей для {context.compound_formula}: "
            f"{len(records)} → {len(limited_records)}"
        )

        return limited_records

    def _get_compound_role(
        self,
        compound: str,
        reaction_params: Optional[ExtractedReactionParameters]
    ) -> str:
        """Определяет роль соединения в реакции."""
        if not reaction_params:
            return 'unknown'

        if compound in reaction_params.reactants:
            return 'reactant'
        elif compound in reaction_params.products:
            return 'product'
        else:
            return 'unknown'

    def get_stage_name(self) -> str:
        """Название стадии для отчётности."""
        return "Reaction Validation Stage"

    def get_validation_results(self) -> Dict[str, CompoundValidationResult]:
        """Получить детальные результаты валидации."""
        return self._last_validation_results.copy()

    def get_validation_summary(self) -> Dict[str, Any]:
        """Получить сводную информацию о валидации."""
        if not self._last_validation_results:
            return {'validation_applied': False}

        summary = {
            'validation_applied': True,
            'total_compounds': len(self._last_validation_results),
            'compounds_with_results': sum(1 for result in self._last_validation_results.values() if result.best_result),
            'compounds_without_results': sum(1 for result in self._last_validation_results.values() if not result.best_result),
            'average_confidence': self._calculate_average_confidence(),
            'compounds_detail': {}
        }

        for compound, result in self._last_validation_results.items():
            summary['compounds_detail'][compound] = {
                'role': result.target_role,
                'records_found': len(result.all_results),
                'has_best_result': bool(result.best_result),
                'best_confidence': result.best_result.total_confidence if result.best_result else 0.0,
                'summary': result.validation_summary
            }

        return summary

    def _calculate_average_confidence(self) -> float:
        """Рассчитывает средний confidence score по всем соединениям."""
        confidences = []
        for result in self._last_validation_results.values():
            if result.best_result:
                confidences.append(result.best_result.total_confidence)

        return sum(confidences) / len(confidences) if confidences else 0.0