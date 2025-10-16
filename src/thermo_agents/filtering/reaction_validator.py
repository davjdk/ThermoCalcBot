"""
Модуль валидации химических соединений против уравнения реакции.

Этот модуль реализует мягкую валидацию найденных соединений с использованием:
1. Точного сопоставления формул (основной критерий)
2. Нечёткого сопоставления названий (дополнительный критерий)
3. Проверки ролей в реакции (реагент/продукт)
4. Приоритизации элементарных веществ

Реализует подход согласно ТЗ: названия НЕ отсекают результаты, а повышают confidence score.
"""

import logging
import re
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher
import unicodedata

from ..models.search import DatabaseRecord
from ..models.extraction import ExtractedReactionParameters

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Результат валидации одного соединения."""
    record: DatabaseRecord
    formula_match_score: float  # 0.0 или 1.0
    name_match_score: float     # 0.0 - 1.0
    total_confidence: float     # взвешенная сумма
    role_match: bool           # соответствует ли роль в реакции
    reasoning: str            # объяснение результата


@dataclass
class CompoundValidationResult:
    """Результат валидации для одного целевого соединения."""
    target_formula: str
    target_role: str  # 'reactant' или 'product'
    all_results: List[ValidationResult]
    best_result: Optional[ValidationResult]
    validation_summary: str


class ReactionValidator:
    """Валидатор соединений против уравнения реакции с мягкой валидацией по названиям."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def validate_reaction_compounds(
        self,
        db_records: List[DatabaseRecord],
        reaction_params: ExtractedReactionParameters
    ) -> Tuple[List[DatabaseRecord], Dict[str, CompoundValidationResult]]:
        """
        Валидация всех соединений реакции против найденных записей в БД.

        Args:
            db_records: Список записей из БД для всех соединений
            reaction_params: Параметры реакции с названиями веществ

        Returns:
            Tuple[List[DatabaseRecord], Dict[str, CompoundValidationResult]]:
            - Отфильтрованный список записей (с высоким confidence)
            - Детальная статистика валидации по каждому соединению
        """
        self.logger.info(
            f"Начало валидации реакции: {reaction_params.balanced_equation}"
        )

        # Группируем записи по целевым формулам
        records_by_formula = self._group_records_by_target_formula(
            db_records, reaction_params.all_compounds
        )

        validation_results = {}
        filtered_records = []

        # Валидируем каждое соединение
        for target_formula in reaction_params.all_compounds:
            target_records = records_by_formula.get(target_formula, [])
            target_role = self._determine_compound_role(
                target_formula, reaction_params
            )
            target_names = reaction_params.compound_names.get(target_formula, [])

            validation_result = self._validate_single_compound(
                target_formula, target_role, target_records, target_names
            )

            validation_results[target_formula] = validation_result

            # Добавляем лучшие результаты в отфильтрованный список
            if validation_result.best_result:
                filtered_records.append(validation_result.best_result.record)
                self.logger.info(
                    f"✅ {target_formula}: выбрана запись с confidence={validation_result.best_result.total_confidence:.3f}"
                )
            else:
                self.logger.warning(
                    f"❌ {target_formula}: не найдено подходящих записей"
                )

        self.logger.info(
            f"Валидация завершена. Отобрано {len(filtered_records)} из {len(db_records)} записей"
        )

        return filtered_records, validation_results

    def _group_records_by_target_formula(
        self,
        db_records: List[DatabaseRecord],
        target_formulas: List[str]
    ) -> Dict[str, List[DatabaseRecord]]:
        """Группирует записи БД по целевым формулам с гибким сопоставлением."""
        grouped = {formula: [] for formula in target_formulas}

        for record in db_records:
            best_match = self._find_best_formula_match(record.formula, target_formulas)
            if best_match:
                grouped[best_match].append(record)

        return grouped

    def _find_best_formula_match(
        self,
        db_formula: str,
        target_formulas: List[str]
    ) -> Optional[str]:
        """
        Находит лучшее сопоставление формулы из БД с целевыми формулами.
        Использует точное совпадение и префиксное сопоставление.
        """
        # Сначала проверяем точное совпадение (без фазовых модификаторов)
        clean_db_formula = self._clean_formula(db_formula)

        for target in target_formulas:
            if clean_db_formula == target:
                return target

            # Проверяем префиксное совпадение (например, Mg для Mg(g))
            if clean_db_formula.startswith(target):
                return target

            # Проверяем совпадение с модификаторами в скобках
            if db_formula.startswith(target + '('):
                return target

        return None

    def _clean_formula(self, formula: str) -> str:
        """Очищает формулу от фазовых обозначений и модификаторов."""
        # Удаляем фазовые обозначения в скобках
        formula = re.sub(r'\(.*?\)', '', formula)
        return formula.strip()

    def _determine_compound_role(
        self,
        formula: str,
        reaction_params: ExtractedReactionParameters
    ) -> str:
        """Определяет роль соединения в реакции (reactant/product)."""
        if formula in reaction_params.reactants:
            return 'reactant'
        elif formula in reaction_params.products:
            return 'product'
        else:
            return 'unknown'

    def _validate_single_compound(
        self,
        target_formula: str,
        target_role: str,
        db_records: List[DatabaseRecord],
        target_names: List[str]
    ) -> CompoundValidationResult:
        """
        Валидация одного соединения против найденных записей.
        """
        if not db_records:
            return CompoundValidationResult(
                target_formula=target_formula,
                target_role=target_role,
                all_results=[],
                best_result=None,
                validation_summary=f"Нет записей для {target_formula}"
            )

        validation_results = []

        for record in db_records:
            result = self._validate_single_record(
                record, target_formula, target_role, target_names
            )
            validation_results.append(result)

        # Сортируем по общему confidence
        validation_results.sort(key=lambda x: x.total_confidence, reverse=True)

        best_result = validation_results[0] if validation_results else None

        summary = (
            f"Для {target_formula} ({target_role}) найдено {len(db_records)} записей, "
            f"лучшая имеет confidence={best_result.total_confidence:.3f}"
            if best_result else f"Для {target_formula} нет подходящих записей"
        )

        return CompoundValidationResult(
            target_formula=target_formula,
            target_role=target_role,
            all_results=validation_results,
            best_result=best_result,
            validation_summary=summary
        )

    def _validate_single_record(
        self,
        record: DatabaseRecord,
        target_formula: str,
        target_role: str,
        target_names: List[str]
    ) -> ValidationResult:
        """
        Валидация одной записи БД.

        Args:
            record: Запись из БД
            target_formula: Целевая формула
            target_role: Целевая роль в реакции
            target_names: Названия веществ из LLM

        Returns:
            ValidationResult с рассчитанными score'ами
        """
        # 1. Проверка точности формулы (основной критерий - 70% веса)
        formula_match_score = self._calculate_formula_match_score(
            record.formula, target_formula
        )

        # 2. Проверка сопоставления названий (дополнительный критерий - 30% веса)
        name_match_score = self._calculate_name_match_score(
            getattr(record, 'first_name', ''), target_names
        )

        # 3. Общий confidence score
        total_confidence = 0.7 * formula_match_score + 0.3 * name_match_score

        # 4. Проверка роли (не влияет на confidence, только для логирования)
        role_match = self._check_role_match(record, target_role)

        # 5. Формирование объяснения
        reasoning = self._generate_reasoning(
            record, target_formula, formula_match_score, name_match_score, role_match
        )

        return ValidationResult(
            record=record,
            formula_match_score=formula_match_score,
            name_match_score=name_match_score,
            total_confidence=total_confidence,
            role_match=role_match,
            reasoning=reasoning
        )

    def _calculate_formula_match_score(self, db_formula: str, target_formula: str) -> float:
        """
        Рассчитывает score сопоставления формул.
        Возвращает 1.0 для точного совпадения, 0.0 для несовпадения.
        """
        clean_db_formula = self._clean_formula(db_formula)

        if clean_db_formula == target_formula:
            return 1.0

        # Проверяем префиксное совпадение (например, Mg для Mg(g))
        if clean_db_formula.startswith(target_formula):
            return 1.0

        # Проверяем совпадение с модификаторами
        if db_formula.startswith(target_formula + '('):
            return 1.0

        return 0.0

    def _calculate_name_match_score(self, db_name: str, target_names: List[str]) -> float:
        """
        Рассчитывает score сопоставления названий (мягкая валидация).

        Args:
            db_name: Название из БД (FirstName)
            target_names: Список названий от LLM

        Returns:
            Score от 0.0 до 1.0
        """
        if not target_names or not db_name:
            return 0.0

        max_score = 0.0

        for target_name in target_names:
            score = self._calculate_single_name_match_score(db_name, target_name)
            max_score = max(max_score, score)

        return max_score

    def _calculate_single_name_match_score(self, db_name: str, target_name: str) -> float:
        """
        Рассчитывает score сопоставления двух названий.
        """
        # 1. Точное совпадение (case-insensitive)
        if self._normalize_name(db_name) == self._normalize_name(target_name):
            return 1.0

        # 2. Совпадение после удаления специальных символов
        if self._remove_special_chars(db_name) == self._remove_special_chars(target_name):
            return 0.9

        # 3. Token overlap (проверка вхождения слов)
        db_tokens = set(self._normalize_name(db_name).split())
        target_tokens = set(self._normalize_name(target_name).split())

        if db_tokens and target_tokens:
            overlap = len(db_tokens & target_tokens) / len(db_tokens | target_tokens)
            if overlap >= 0.8:
                return 0.7 + overlap * 0.1

        # 4. Sequence similarity (Levenshtein-like)
        similarity = SequenceMatcher(None,
                                   self._normalize_name(db_name),
                                   self._normalize_name(target_name)).ratio()

        if similarity >= 0.8:
            return 0.5 + similarity * 0.2

        # 5. Частичное вхождение
        if self._normalize_name(target_name) in self._normalize_name(db_name):
            return 0.4

        if self._normalize_name(db_name) in self._normalize_name(target_name):
            return 0.3

        return 0.0

    def _normalize_name(self, name: str) -> str:
        """Нормализация названия для сравнения."""
        # Удаление диакритических знаков
        name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('ASCII')
        # Приведение к нижнему регистру и удаление лишних пробелов
        return name.lower().strip()

    def _remove_special_chars(self, name: str) -> str:
        """Удаление специальных символов из названия."""
        # Удаляем скобки, римские цифры, знаки препинания
        name = re.sub(r'[()0-9,\-\.]', ' ', name)
        # Удаляем лишние пробелы
        return ' '.join(name.split()).lower()

    def _check_role_match(self, record: DatabaseRecord, target_role: str) -> bool:
        """
        Проверяет, соответствует ли запись роли в реакции.
        В настоящее время всегда возвращает True, так как роль не хранится в БД.
        """
        # В будущем можно добавить логику определения роли по фазе и т.д.
        return True

    def _generate_reasoning(
        self,
        record: DatabaseRecord,
        target_formula: str,
        formula_score: float,
        name_score: float,
        role_match: bool
    ) -> str:
        """Генерирует объяснение результата валидации."""
        parts = []

        # Формула
        if formula_score == 1.0:
            parts.append(f"✅ Точное совпадение формулы: '{record.formula}' == '{target_formula}'")
        else:
            parts.append(f"❌ Несовпадение формулы: '{record.formula}' != '{target_formula}'")

        # Название
        if name_score >= 0.9:
            parts.append(f"✅ Отличное совпадение названия: {name_score:.2f}")
        elif name_score >= 0.7:
            parts.append(f"🟡 Хорошее совпадение названия: {name_score:.2f}")
        elif name_score > 0.0:
            parts.append(f"🟠 Частичное совпадение названия: {name_score:.2f}")
        elif name_score == 0.0 and hasattr(record, 'first_name'):
            parts.append(f"⚪ Нет совпадения названия с '{record.first_name}'")

        # Общий confidence
        total_confidence = 0.7 * formula_score + 0.3 * name_score
        parts.append(f"🎯 Общий confidence: {total_confidence:.3f}")

        return " | ".join(parts)


# Утилитарные функции для использования в других модулях
def create_reaction_validator() -> ReactionValidator:
    """Создаёт экземпляр ReactionValidator."""
    return ReactionValidator()


def validate_compound_names(
    db_name: str,
    llm_names: List[str],
    min_score: float = 0.5
) -> Tuple[bool, float]:
    """
    Утилитарная функция для быстрой валидации названий.

    Args:
        db_name: Название из БД
        llm_names: Названия от LLM
        min_score: Минимальный порог для считывания совпадением

    Returns:
        Tuple[bool, float]: (прошло ли валидацию, score)
    """
    validator = ReactionValidator()
    score = validator._calculate_name_match_score(db_name, llm_names)
    return score >= min_score, score