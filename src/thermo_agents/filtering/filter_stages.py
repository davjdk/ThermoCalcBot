"""
Стадии конвейерной фильтрации термодинамических данных.

Реализует конкретные стадии фильтрации с использованием резолверов
и сбором детальной статистики.
"""

from typing import List, Dict, Any, Optional
import time

from .filter_pipeline import FilterStage, FilterContext
from .temperature_resolver import TemperatureResolver
from .phase_resolver import PhaseResolver
from ..models.search import DatabaseRecord


class TemperatureFilterStage(FilterStage):
    """Фильтрация по температурному диапазону."""

    def __init__(self, temperature_resolver: Optional[TemperatureResolver] = None):
        super().__init__()
        self.temperature_resolver = temperature_resolver or TemperatureResolver()

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Фильтрация записей по температурному диапазону.

        Note: According to database analysis, Tmin and Tmax are 100% populated,
        so we don't need to handle NULL values.

        Логика:
        - Проверка пересечения [Tmin, Tmax] с [tmin_user, tmax_user]
        """
        start_time = time.time()
        tmin_user, tmax_user = context.temperature_range
        filtered = []

        for record in records:
            # В базе данных Tmin и Tmax всегда заполнены (100% покрытие)
            # Проверка пересечения интервалов
            if record.tmin <= tmax_user and record.tmax >= tmin_user:
                filtered.append(record)

        execution_time = (time.time() - start_time) * 1000

        self.last_stats = {
            'temperature_range': context.temperature_range,
            'records_in_range': len(filtered),
            'records_out_of_range': len(records) - len(filtered),
            'execution_time_ms': execution_time,
            'coverage_percentage': (len(filtered) / len(records) * 100) if records else 0,
            'note': 'All records have Tmin/Tmax populated according to database analysis'
        }

        return filtered

    def get_stage_name(self) -> str:
        return "Температурная фильтрация"


class PhaseSelectionStage(FilterStage):
    """Фильтрация по фазовому составу с учётом переходов."""

    def __init__(self, phase_resolver: PhaseResolver):
        super().__init__()
        self.phase_resolver = phase_resolver

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Выбор записей с корректной фазой для температурного диапазона.

        Логика:
        1. Определить ожидаемую фазу при заданной температуре
        2. Приоритизировать записи с правильной фазой
        3. Учесть фазовые переходы (Tmelt, Tboil)
        """
        start_time = time.time()
        tmin, tmax = context.temperature_range
        t_mid = (tmin + tmax) / 2  # Средняя температура

        phase_scores = []
        phase_analysis = {'correct': 0, 'unknown': 0, 'incorrect': 0}

        for record in records:
            expected_phase = self.phase_resolver.get_phase_at_temperature(record, t_mid)
            score = self._calculate_phase_score(record, expected_phase)
            phase_scores.append((record, score))

            # Собираем статистику по фазам
            actual_phase = self._extract_phase(record)
            if actual_phase == expected_phase:
                phase_analysis['correct'] += 1
            elif actual_phase is None or expected_phase is None:
                phase_analysis['unknown'] += 1
            else:
                phase_analysis['incorrect'] += 1

        # Сортировка по соответствию фазе
        phase_scores.sort(key=lambda x: x[1], reverse=True)

        # Выбор записей с score >= 0.3 (минимально приемлемые данные)
        filtered = [r for r, score in phase_scores if score >= 0.3]

        execution_time = (time.time() - start_time) * 1000

        self.last_stats = {
            'phase_matches': len(filtered),
            'phase_mismatches': len(records) - len(filtered),
            'phase_analysis': phase_analysis,
            'mid_temperature': t_mid,
            'execution_time_ms': execution_time,
            'average_score': sum(score for _, score in phase_scores) / len(phase_scores) if phase_scores else 0
        }

        return filtered

    def _calculate_phase_score(
        self,
        record: DatabaseRecord,
        expected_phase: Optional[str]
    ) -> float:
        """Расчёт соответствия фазы (0-1)."""
        if expected_phase is None:
            return 0.8  # Неизвестная ожидаемая фаза - высокий приоритет

        record_phase = self._extract_phase(record)

        if record_phase == expected_phase:
            return 1.0
        elif record_phase is None:
            return 0.8  # Неизвестная фаза - высокий приоритет
        else:
            # Неправильная фаза, но даём шанс если есть термодинамические данные
            # и температурный диапазон подходит
            if self._has_adequate_thermodynamic_data(record):
                return 0.6  # Неправильная фаза, но хорошие данные
            else:
                return 0.3  # Неправильная фаза и плохие данные

    def _has_adequate_thermodynamic_data(self, record: DatabaseRecord) -> bool:
        """Проверяет, имеет ли запись адекватные термодинамические данные."""
        # Проверяем наличие ключевых термодинамических свойств
        has_basic_data = (
            record.h298 is not None and
            record.s298 is not None and
            record.f1 is not None and
            record.f2 is not None and
            record.f3 is not None
        )

        # Проверяем надежность данных
        good_reliability = record.reliability_class is not None and record.reliability_class <= 3

        # Проверяем наличие фазовых переходов
        has_phase_transitions = record.tmelt is not None and record.tboil is not None

        return has_basic_data and (good_reliability or has_phase_transitions)

    def _extract_phase(self, record: DatabaseRecord) -> Optional[str]:
        """Извлечь фазу из записи."""
        # Проверить поле phase
        if record.phase:
            return self.phase_resolver.normalize_phase(record.phase)

        # Извлечь из формулы: H2O(g) → 'g'
        return self.phase_resolver._extract_phase_from_formula(record.formula)

    def get_stage_name(self) -> str:
        return "Фазовая фильтрация"


class ReliabilityPriorityStage(FilterStage):
    """Приоритизация по надёжности и полноте данных."""

    def __init__(self, max_records: int = 1):
        super().__init__()
        self.max_records = max_records

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Выбор топ-N записей по критериям:
        1. ReliabilityClass (1 > 2 > 3 > 4)
        2. Полнота термодинамических данных
        3. Наличие фазовых переходов
        """
        start_time = time.time()
        scored_records = []

        for record in records:
            score = self._calculate_priority_score(record)
            scored_records.append((record, score))

        # Сортировка по убыванию score
        scored_records.sort(key=lambda x: x[1], reverse=True)

        # Выбор топ-N
        filtered = [r for r, _ in scored_records[:self.max_records]]

        execution_time = (time.time() - start_time) * 1000

        # Дополнительная статистика
        reliability_stats = {}
        for record in records:
            rel_class = record.reliability_class if record.reliability_class is not None else 9
            reliability_stats[rel_class] = reliability_stats.get(rel_class, 0) + 1

        completeness_stats = []
        for record in records:
            completeness = self._calculate_completeness(record)
            completeness_stats.append(completeness)

        self.last_stats = {
            'total_candidates': len(records),
            'selected': len(filtered),
            'max_records': self.max_records,
            'reliability_distribution': reliability_stats,
            'average_completeness': sum(completeness_stats) / len(completeness_stats) if completeness_stats else 0,
            'average_score': sum(score for _, score in scored_records) / len(scored_records) if scored_records else 0,
            'execution_time_ms': execution_time
        }

        return filtered

    def _calculate_priority_score(self, record: DatabaseRecord) -> float:
        """Расчёт приоритета записи."""
        score = 0.0

        # Критерий 1: ReliabilityClass (инвертируем: 1=лучший)
        if record.reliability_class is not None:
            score += (10 - record.reliability_class) * 100
        else:
            score += 10  # Базовый балл для неизвестной надёжности

        # Критерий 2: Полнота термодинамических данных
        completeness = self._calculate_completeness(record)
        score += completeness * 50

        # Критерий 3: Наличие фазовых переходов
        if record.tmelt is not None:
            score += 20
        if record.tboil is not None:
            score += 20

        # Критерий 4: Ширина температурного диапазона
        if record.tmin is not None and record.tmax is not None:
            range_width = record.tmax - record.tmin
            score += min(range_width / 100, 10)  # Максимум 10 баллов за диапазон

        # Критерий 5: Наличие стандартных свойств
        if record.h298 is not None:
            score += 10
        if record.s298 is not None:
            score += 10

        return score

    def _calculate_completeness(self, record: DatabaseRecord) -> float:
        """
        Расчёт полноты термодинамических данных (0-1).

        Note: According to database analysis, H298, S298, and f1-f6 are
        100% populated, so completeness will always be 1.0.
        This method is kept for consistency with the original design.
        """
        # В базе данных все термодинамические свойства 100% заполнены
        # Поэтому полнота всегда равна 1.0
        return 1.0

    def get_stage_name(self) -> str:
        return "Приоритизация по надёжности"


class TemperatureCoverageStage(FilterStage):
    """Дополнительная стадия для проверки температурного покрытия."""

    def __init__(self, temperature_resolver: Optional[TemperatureResolver] = None):
        super().__init__()
        self.temperature_resolver = temperature_resolver or TemperatureResolver()

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Фильтрация записей по температурному покрытию.
        Оставляет только записи, которые обеспечивают покрытие
        заданного температурного диапазона.
        """
        start_time = time.time()
        coverage_status = self.temperature_resolver.check_coverage(records, context.temperature_range)

        # Если полное покрытие - оставляем все записи
        if coverage_status == 'full':
            filtered = records
        # Если частичное покрытие - оставляем записи, которые покрывают диапазон
        elif coverage_status == 'partial':
            filtered = self._filter_by_coverage(records, context.temperature_range)
        else:
            # Нет покрытия - пустой результат
            filtered = []

        execution_time = (time.time() - start_time) * 1000
        coverage_percentage = self.temperature_resolver.calculate_coverage_percentage(
            records, context.temperature_range
        )

        self.last_stats = {
            'coverage_status': coverage_status,
            'coverage_percentage': coverage_percentage * 100,
            'records_with_coverage': len(filtered),
            'execution_time_ms': execution_time,
            'temperature_range': context.temperature_range
        }

        return filtered

    def _filter_by_coverage(
        self,
        records: List[DatabaseRecord],
        temperature_range: tuple
    ) -> List[DatabaseRecord]:
        """Оставить только записи, покрывающие диапазон."""
        tmin, tmax = temperature_range
        filtered = []

        for record in records:
            tmin_rec = record.tmin if record.tmin is not None else 0.0
            tmax_rec = record.tmax if record.tmax is not None else float('inf')

            # Проверяем, пересекается ли запись с диапазоном
            if tmin_rec <= tmax and tmax_rec >= tmin:
                filtered.append(record)

        return filtered

    def get_stage_name(self) -> str:
        return "Проверка температурного покрытия"


class FormulaConsistencyStage(FilterStage):
        """Стадия проверки согласованности формул."""

        def __init__(self):
            super().__init__()

        def filter(
            self,
            records: List[DatabaseRecord],
            context: FilterContext
        ) -> List[DatabaseRecord]:
            """Фильтрация записей по согласованности формул."""
            start_time = time.time()
            target_formula = context.compound_formula.upper()
            filtered = []

            for record in records:
                record_formula = record.formula.upper()

                # Прямое совпадение
                if record_formula == target_formula:
                    filtered.append(record)
                    continue

                # Проверяем, является ли формула базовой частью
                if self._is_base_formula_match(record_formula, target_formula):
                    filtered.append(record)
                    continue

                # Проверяем изотопы и изомеры
                if self._is_isotope_or_isomer_match(record_formula, target_formula):
                    filtered.append(record)

            execution_time = (time.time() - start_time) * 1000

            self.last_stats = {
                'target_formula': target_formula,
                'exact_matches': sum(1 for r in filtered if r.formula.upper() == target_formula),
                'base_formula_matches': len(filtered),
                'execution_time_ms': execution_time
            }

            return filtered

        def _is_base_formula_match(self, record_formula: str, target_formula: str) -> bool:
            """Проверяет, является ли формула базовым совпадением."""
            # Удаляем фазовые обозначения
            record_clean = record_formula.split('(')[0].strip()
            target_clean = target_formula.split('(')[0].strip()

            return record_clean == target_clean

        def _is_isotope_or_isomer_match(self, record_formula: str, target_formula: str) -> bool:
            """Проверяет совпадение изотопов или изомеров."""
            # Простая эвристика для изотопов (содержит цифры перед символами)
            import re

            # Удаляем фазовые обозначения
            record_clean = record_formula.split('(')[0].strip()
            target_clean = target_formula.split('(')[0].strip()

            # Извлекаем химические символы (без изотопных чисел)
            record_symbols = re.findall(r'[A-Z][a-z]?', record_clean)
            target_symbols = re.findall(r'[A-Z][a-z]?', target_clean)

            return record_symbols == target_symbols

        def get_stage_name(self) -> str:
            return "Проверка согласованности формул"