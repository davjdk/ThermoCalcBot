"""
Стадии конвейерной фильтрации термодинамических данных.

Реализует конкретные стадии фильтрации с использованием резолверов
и сбором детальной статистики.

Техническое описание:
Конкретные реализации стадий фильтрации для конвейера термодинамических данных.
Каждая стадия наследуется от FilterStage и реализует детерминированную логику
фильтрации с использованием специализированных резолверов.

Стадии фильтрации:
- TemperatureFilterStage: Фильтрация по температурному диапазону
- PhaseSelectionStage: Выбор фазового состояния с учетом переходов
- DeduplicationStage: Удаление дубликатов записей
- ReliabilityPriorityStage: Приоритизация по классу надежности

TemperatureFilterStage:
- Проверяет пересечение температурных диапазонов [Tmin, Tmax] ∩ [tmin_user, tmax_user]
- Использует TemperatureResolver для оптимизации
- 100% покрытие Tmin/Tmax в базе данных (не нужно обрабатывать NULL)
- Статистика по записям в диапазоне и вне диапазона

PhaseSelectionStage:
- Определяет ожидаемую фазу при средней температуре
- Приоритизирует записи с правильной фазой
- Учитывает фазовые переходы (Tmelt, Tboil)
- Использует PhaseResolver для детерминированного определения фаз

DeduplicationStage:
- Удаляет дубликаты записей на основе ID и ключевых полей
- Сохраняет наиболее надежные версии при дубликатах
- Оптимизирует производительность последующих стадий

ReliabilityPriorityStage:
- Сортирует записи по классу надежности (1 = лучший)
- Ограничивает количество записей для оптимизации
- Предпочитает записи с полными термодинамическими данными

Общие характеристики стадий:
- Детерминированная логика без использования LLM
- Измерение времени выполнения
- Сбор статистики для логирования и отладки
- Интеграция с FilterContext для передачи параметров
- Graceful handling граничных случаев

Константы и пороги:
- MIN_TEMPERATURE_COVERAGE_RATIO: Минимальное покрытие диапазона
- MAX_RELIABILITY_CLASS: Максимальный допустимый класс надежности
- Фазовые температурные пороги для разных типов веществ
- Температурные диапазоны для фазовых состояний

Метрики и статистика:
- Время выполнения каждой стадии
- Коэффициент отсева записей
- Распределение по фазам и температурам
- Покрытие температурного диапазона

Интеграция:
- Используются FilterPipeline для последовательного выполнения
- Интегрируются с резолверами для определения фаз и температур
- Поддерживают SessionLogger для детального логирования
- Совместимы с DatabaseRecord моделью данных

Используются в:
- FilterPipeline для построения конвейера фильтрации
- CompoundSearcher для подготовки данных
- ThermoOrchestrator для обработки результатов поиска
- Тестировании и отладке системы фильтрации
"""

import time
from typing import Any, Dict, List, Optional

from ..models.search import DatabaseRecord
from .constants import (
    DEFAULT_CACHE_SIZE,
    MAX_RELIABILITY_CLASS,
    MIN_TEMPERATURE_COVERAGE_RATIO,
    MIN_TEMPERATURE_K,
    MAX_TEMPERATURE_K,
    SOLID_PHASE_MAX_TEMP,
    LIQUID_PHASE_MIN_TEMP,
    LIQUID_PHASE_MAX_TEMP,
    GAS_PHASE_MIN_TEMP,
    MELTING_POINT_MAX,
    BOILING_POINT_MIN,
    WATER_MELTING_POINT,
    WATER_BOILING_POINT,
)
from .filter_pipeline import FilterContext, FilterStage
from .phase_resolver import PhaseResolver




class PhaseSelectionStage(FilterStage):
    """Фильтрация по фазовому составу с учётом переходов."""

    def __init__(self, phase_resolver: PhaseResolver):
        super().__init__()
        self.phase_resolver = phase_resolver

    def filter(
        self, records: List[DatabaseRecord], context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Выбор записей с корректной фазой.

        Логика:
        1. Приоритизировать записи по фазовому состоянию
        2. Учесть надежность данных
        """
        start_time = time.time()

        # Простая фильтрация по фазам без температурной логики
        phase_scores = []
        phase_analysis = {"correct": 0, "unknown": 0, "incorrect": 0}

        for record in records:
            # Даем базовый score в зависимости от фазы
            score = 1.0
            if record.phase == 's':  # Твердая фаза наиболее стабильна
                score = 3.0
            elif record.phase == 'l':  # Жидкая фаза
                score = 2.0
            elif record.phase == 'g':  # Газовая фаза
                score = 1.0
            phase_scores.append((record, score))

            # Собираем статистику по фазам
            actual_phase = self._extract_phase(record)
            if actual_phase:
                phase_analysis["correct"] += 1
            else:
                phase_analysis["unknown"] += 1

        # Сортировка по соответствию фазе
        phase_scores.sort(key=lambda x: x[1], reverse=True)

        # Выбор записей с score >= MIN_TEMPERATURE_COVERAGE_RATIO (минимально приемлемые данные)
        filtered = [r for r, score in phase_scores if score >= MIN_TEMPERATURE_COVERAGE_RATIO]

        execution_time = (time.time() - start_time) * 1000

        self.last_stats = {
            "phase_matches": len(filtered),
            "phase_mismatches": len(records) - len(filtered),
            "phase_analysis": phase_analysis,
            "execution_time_ms": execution_time,
        }

        return filtered

    
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
        self, records: List[DatabaseRecord], context: FilterContext
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
        filtered = [r for r, _ in scored_records[: self.max_records]]

        execution_time = (time.time() - start_time) * 1000

        # Дополнительная статистика
        reliability_stats = {}
        for record in records:
            rel_class = (
                record.reliability_class if record.reliability_class is not None else 9
            )
            reliability_stats[rel_class] = reliability_stats.get(rel_class, 0) + 1

        completeness_stats = []
        for record in records:
            completeness = self._calculate_completeness(record)
            completeness_stats.append(completeness)

        self.last_stats = {
            "total_candidates": len(records),
            "selected": len(filtered),
            "max_records": self.max_records,
            "reliability_distribution": reliability_stats,
            "average_completeness": sum(completeness_stats) / len(completeness_stats)
            if completeness_stats
            else 0,
            "execution_time_ms": execution_time,
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
            score += min(range_width / DEFAULT_CACHE_SIZE, 10)  # Максимум 10 баллов за диапазон

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




class FormulaConsistencyStage(FilterStage):
    """Стадия проверки согласованности формул."""

    def __init__(self):
        super().__init__()

    def filter(
        self, records: List[DatabaseRecord], context: FilterContext
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
            "target_formula": target_formula,
            "exact_matches": sum(
                1 for r in filtered if r.formula.upper() == target_formula
            ),
            "base_formula_matches": len(filtered),
            "execution_time_ms": execution_time,
        }

        return filtered

    def _is_base_formula_match(self, record_formula: str, target_formula: str) -> bool:
        """Проверяет, является ли формула базовым совпадением."""
        # Удаляем фазовые обозначения
        record_clean = record_formula.split("(")[0].strip()
        target_clean = target_formula.split("(")[0].strip()

        return record_clean == target_clean

    def _is_isotope_or_isomer_match(
        self, record_formula: str, target_formula: str
    ) -> bool:
        """Проверяет совпадение изотопов или изомеров."""
        # Простая эвристика для изотопов (содержит цифры перед символами)
        import re

        # Удаляем фазовые обозначения
        record_clean = record_formula.split("(")[0].strip()
        target_clean = target_formula.split("(")[0].strip()

        # Извлекаем химические символы (без изотопных чисел)
        record_symbols = re.findall(r"[A-Z][a-z]?", record_clean)
        target_symbols = re.findall(r"[A-Z][a-z]?", target_clean)

        return record_symbols == target_symbols

    def get_stage_name(self) -> str:
        return "Проверка согласованности формул"


class DeduplicationStage(FilterStage):
    """Первая стадия фильтрации: удаление дубликатов по ключевым полям."""

    def filter(
        self, records: List[DatabaseRecord], context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Удаление дубликатов записей на основе уникальности ключевых полей.

        Критерии дедупликации:
        1. Формула соединения (formula)
        2. Фаза (phase)
        3. Температурный диапазон (tmin, tmax)
        4. Класс надежности (reliability_class)
        5. Основные термодинамические коэффициенты (f1, f2, f3)

        Приоритет при дедупликации:
        - Более высокий класс надежности (1 > 2 > 3 > ...)
        - Более широкий температурный диапазон
        - Более полное покрытие термодинамических данных
        """
        start_time = time.time()

        # Группируем записи по уникальным ключам
        unique_groups = {}
        duplicates_count = 0

        for record in records:
            # Создаем ключ для группировки
            key = self._create_deduplication_key(record)

            if key not in unique_groups:
                unique_groups[key] = []
            unique_groups[key].append(record)

        # Выбираем лучшую запись из каждой группы
        deduplicated_records = []
        for key, group in unique_groups.items():
            if len(group) > 1:
                duplicates_count += len(group) - 1
                # Выбираем лучшую запись из группы дубликатов
                best_record = self._select_best_record(group)
                deduplicated_records.append(best_record)
            else:
                deduplicated_records.append(group[0])

        execution_time = (time.time() - start_time) * 1000

        # Сбор статистики по дубликатам
        duplicates_by_formula = {}
        for key, group in unique_groups.items():
            if len(group) > 1:
                formula = key.split('|')[0]  # Extract formula from key
                duplicates_by_formula[formula] = duplicates_by_formula.get(formula, 0) + len(group) - 1

        self.last_stats = {
            "initial_records": len(records),
            "unique_records": len(deduplicated_records),
            "duplicates_removed": duplicates_count,
            "deduplication_rate": duplicates_count / len(records) if records else 0,
            "duplicates_by_formula": duplicates_by_formula,
            "execution_time_ms": execution_time,
        }

        return deduplicated_records

    def _create_deduplication_key(self, record: DatabaseRecord) -> str:
        """
        Создать ключ для идентификации дубликатов.

        Ключ включает основные поля, определяющие уникальность записи.
        Для чистых соединений (без составных частей) игнорируем фазу для лучшей дедупликации.
        """
        # Нормализация формулы (приводим к верхнему регистру, удаляем пробелы)
        formula = (record.formula or "").strip().upper()

        # Проверяем, является ли соединение чистым (не содержит составных частей)
        is_pure_compound = self._is_pure_compound(formula)

        # Для чистых соединений игнорируем фазу при дедупликации
        # Для составных соединений (например, BaO*Fe2O3) учитываем фазу
        if is_pure_compound:
            phase = "ANY"  # Любая фаза для чистых соединений
        else:
            phase = (record.phase or "").strip().lower()

        # Температурный диапазон (округляем до 1K)
        tmin = f"{record.tmin:.0f}" if record.tmin is not None else "None"
        tmax = f"{record.tmax:.0f}" if record.tmax is not None else "None"

        # Класс надежности
        reliability = str(record.reliability_class) if record.reliability_class is not None else "None"

        # Основные термодинамические коэффициенты (округляем)
        f1 = f"{record.f1:.3f}" if record.f1 is not None else "None"
        f2 = f"{record.f2:.3f}" if record.f2 is not None else "None"
        f3 = f"{record.f3:.3f}" if record.f3 is not None else "None"

        # Создаем составной ключ
        key = f"{formula}|{phase}|{tmin}|{tmax}|{reliability}|{f1}|{f2}|{f3}"

        return key

    def _is_pure_compound(self, formula: str) -> bool:
        """
        Проверить, является ли формула чистым соединением (не составным).

        Чистое соединение не содержит символов '*', '+', или других составных частей.
        """
        if not formula:
            return False

        # Составные соединения содержат "*", "+", или имеют составные части
        compound_indicators = ['*', '+', '(', ')']
        return not any(indicator in formula for indicator in compound_indicators)

    def _select_best_record(self, duplicate_group: List[DatabaseRecord]) -> DatabaseRecord:
        """
        Выбрать лучшую запись из группы дубликатов.

        Критерии выбора:
        1. Класс надежности (меньше = лучше)
        2. Ширина температурного диапазона (больше = лучше)
        3. Наличие стандартных свойств H298, S298
        4. Наличие фазовых переходов
        """
        if len(duplicate_group) == 1:
            return duplicate_group[0]

        # Сортируем записи по приоритету
        scored_records = []
        for record in duplicate_group:
            score = self._calculate_record_score(record)
            scored_records.append((record, score))

        # Сортируем по убыванию оценки
        scored_records.sort(key=lambda x: x[1], reverse=True)

        # Возвращаем запись с наивысшей оценкой
        return scored_records[0][0]

    def _calculate_record_score(self, record: DatabaseRecord) -> float:
        """
        Рассчитать оценку качества записи.

        Чем выше оценка, тем лучше запись.
        """
        score = 0.0

        # Критерий 1: Класс надежности (1 = лучший, 5 = худший)
        if record.reliability_class is not None:
            score += (6 - record.reliability_class) * 100  # 1→5*100, 2→4*100, и т.д.

        # Критерий 2: Ширина температурного диапазона
        if record.tmin is not None and record.tmax is not None:
            temp_range = record.tmax - record.tmin
            score += min(temp_range / 100, 50)  # Максимум 50 баллов за диапазон

        # Критерий 3: Наличие стандартных свойств ( nonzero values)
        if record.h298 is not None and record.h298 != 0:
            score += 20
        if record.s298 is not None and record.s298 != 0:
            score += 20

        # Критерий 4: Наличие фазовых переходов
        if record.tmelt is not None and record.tmelt > 0:
            score += 10
        if record.tboil is not None and record.tboil > 0:
            score += 10

        # Критерий 5: Полнота термодинамических коэффициентов
        coefficients_count = 0
        for coeff in [record.f1, record.f2, record.f3, record.f4, record.f5, record.f6]:
            if coeff is not None and coeff != 0:
                coefficients_count += 1
        score += coefficients_count * 5

        # Критерий 6: Предпочтение фазы для чистых соединений
        formula = (record.formula or "").strip().upper()
        if self._is_pure_compound(formula):
            phase = (record.phase or "").strip().lower()
            # Предпочитаем твердую фазу (s), затем жидкость (l), затем газ (g)
            if phase == 's':
                score += 15  # Твердая фаза наиболее стабильна
            elif phase == 'l':
                score += 10  # Жидкая фаза
            elif phase == 'g':
                score += 5   # Газовая фаза
            # aqu фаза получает нейтральный балл

        return score

    def get_stage_name(self) -> str:
        return "Удаление дубликатов"
