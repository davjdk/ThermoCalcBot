"""
Стадия комплексного поиска химических формул.

Основываясь на анализе базы данных, реализует многоуровневый алгоритм поиска:
1. Точный поиск TRIM(Formula) = 'H2O'
2. Расширенный поиск Formula LIKE 'H2O(%'
3. Префиксный поиск Formula LIKE 'HCl%' (для сложных соединений)
4. Общий поиск Formula LIKE '%H2O%'
"""

from typing import List, Dict, Any, Optional
import time
import re

from .filter_pipeline import FilterStage, FilterContext
from ..models.search import DatabaseRecord


class ComplexFormulaSearchStage(FilterStage):
    """
    Стадия комплексного поиска химических формул.

    Note: According to database analysis, many compounds like HCl, CO2, NH3, CH4
    require extended search beyond exact TRIM(Formula) matching.
    """

    def __init__(self, search_strategy: str = "comprehensive"):
        super().__init__()
        self.search_strategy = search_strategy

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Фильтрация записей с использованием комплексного поиска формул.

        Args:
            records: Предварительно отфильтрованные записи
            context: Контекст с целевой формулой

        Returns:
            Отфильтрованные записи, соответствующие комплексному поиску
        """
        start_time = time.time()
        target_formula = context.compound_formula.upper().strip()

        # Анализируем, какой тип поиска нужен для этой формулы
        search_method = self._determine_search_method(target_formula)

        filtered = []
        search_stats = {
            'exact_matches': 0,
            'phase_matches': 0,
            'prefix_matches': 0,
            'contains_matches': 0
        }

        for record in records:
            record_formula = record.formula.upper().strip()
            match_type = self._check_formula_match(record_formula, target_formula)

            if match_type:
                filtered.append(record)
                search_stats[match_type] += 1

        execution_time = (time.time() - start_time) * 1000

        self.last_stats = {
            'target_formula': target_formula,
            'search_method': search_method,
            'total_records_before': len(records),
            'total_records_after': len(filtered),
            'search_statistics': search_stats,
            'execution_time_ms': execution_time,
            'reduction_rate': (len(records) - len(filtered)) / len(records) if records else 0
        }

        return filtered

    def _determine_search_method(self, formula: str) -> str:
        """
        Определяет необходимый метод поиска на основе анализа формулы.

        Note: Based on database analysis, certain compounds require extended search:
        - HCl: needs LIKE 'HCl%' (0 exact matches, 153 with prefix)
        - CO2: needs LIKE 'CO2%' (0 exact matches, 1428 with prefix)
        - NH3: needs LIKE 'NH3%' (1 exact match, 1710 with prefix)
        - CH4: needs LIKE 'CH4%' (0 exact matches, 1352 with prefix)
        """
        # Простые молекулы, которые требуют расширенного поиска
        simple_molecules = {'HCL', 'CO2', 'NH3', 'CH4', 'HF', 'HBR', 'HI', 'NO', 'NO2', 'SO2', 'SO3'}

        if formula in simple_molecules:
            return "prefix_required"

        # Формулы с возможными изотопами
        if re.match(r'^[A-Z][a-z]?[0-9]+', formula):
            return "isotope_possible"

        # Сложные формулы с возможными модификаторами
        if '(' in formula or ')' in formula:
            return "phase_aware"

        # Ионные формы
        if '+' in formula or '-' in formula:
            return "ionic"

        return "standard"

    def _check_formula_match(self, record_formula: str, target_formula: str) -> Optional[str]:
        """
        Проверяет соответствие формулы записи целевой формуле.

        Returns:
            'exact' - точное совпадение после TRIM
            'phase' - совпадение с фазовыми модификаторами
            'prefix' - префиксное совпадение
            'contains' - содержится в формуле
            None - нет соответствия
        """
        # 1. Точное совпадение (TRIM)
        record_base = record_formula.split('(')[0].strip()
        if record_base == target_formula:
            return 'exact'

        # 2. Совпадение с фазовыми модификаторами
        if record_formula.startswith(target_formula + '('):
            return 'phase'

        # 3. Префиксное совпадение (для сложных соединений)
        if record_formula.startswith(target_formula):
            return 'prefix'

        # 4. Проверка на изотопы и изомеры
        if self._is_isotope_or_isomer_match(record_base, target_formula):
            return 'contains'

        return None

    def _is_isotope_or_isomer_match(self, record_formula: str, target_formula: str) -> bool:
        """
        Проверяет совпадение изотопов или изомеров.

        Например: 2H2O (тяжёлая вода) соответствует H2O
        """
        # Извлекаем химические символы (без изотопных чисел)
        def extract_symbols(formula: str) -> List[str]:
            # Удаляем все цифры и получаем символы
            clean = re.sub(r'[0-9]', '', formula)
            # Находим все химические символы (заглавная + необязательная строчная)
            return re.findall(r'[A-Z][a-z]?', clean)

        record_symbols = extract_symbols(record_formula)
        target_symbols = extract_symbols(target_formula)

        if not record_symbols or not target_symbols:
            return False

        # Проверяем совпадение множества символов
        return set(record_symbols) == set(target_symbols)

    def get_search_recommendations(self, formula: str) -> List[str]:
        """
        Получить рекомендации по поиску для конкретной формулы.

        Args:
            formula: Химическая формула

        Returns:
            Список рекомендуемых SQL запросов
        """
        formula_upper = formula.upper().strip()
        recommendations = []

        search_method = self._determine_search_method(formula_upper)

        if search_method == "prefix_required":
            recommendations.extend([
                f"Formula LIKE '{formula_upper}%'",  # Основной поиск
                f"TRIM(Formula) = '{formula_upper}'",  # Точный поиск
                f"Formula LIKE '%{formula_upper}%'"  # Общий поиск
            ])
        elif search_method == "ionic":
            recommendations.extend([
                f"Formula LIKE '{formula_upper}%'",  # Основной поиск
                f"Formula LIKE '%{formula_upper}%'"  # Общий поиск
            ])
        else:
            recommendations.extend([
                f"TRIM(Formula) = '{formula_upper}'",  # Точный поиск
                f"Formula LIKE '{formula_upper}(%'",  # С фазами
                f"Formula LIKE '{formula_upper}%'"   # Префиксный
            ])

        return recommendations

    def get_stage_name(self) -> str:
        return "Комплексный поиск формул"


class FormulaConsistencyStage(FilterStage):
    """
    Стадия проверки согласованности формул и удаления дубликатов.

    Note: According to database analysis, 89.64% of records are duplicates
    with different parameters (average 9.6 records per unique formula).
    """

    def __init__(self, max_records_per_formula: int = 10):
        super().__init__()
        self.max_records_per_formula = max_records_per_formula

    def filter(
        self,
        records: List[DatabaseRecord],
        context: FilterContext
    ) -> List[DatabaseRecord]:
        """
        Фильтрация записей с удалением дубликатов и сохранением лучших.

        Args:
            records: Список записей для обработки
            context: Контекст фильтрации

        Returns:
            Отфильтрованные записи без дубликатов
        """
        start_time = time.time()

        # Группируем записи по базовой формуле
        formula_groups = {}
        for record in records:
            base_formula = record.formula.split('(')[0].strip().upper()
            if base_formula not in formula_groups:
                formula_groups[base_formula] = []
            formula_groups[base_formula].append(record)

        # Сортируем каждую группу по надёжности и выбираем лучшие записи
        filtered = []
        duplication_stats = {
            'total_formulas': len(formula_groups),
            'total_records_before': len(records),
            'total_records_after': 0,
            'max_group_size': 0,
            'avg_group_size': 0
        }

        for base_formula, group in formula_groups.items():
            # Сортируем по надёжности (1=лучший), затем по температурному диапазону
            group.sort(key=lambda r: (
                r.reliability_class,
                -(r.tmax - r.tmin) if r.tmax and r.tmin else 0
            ))

            # Выбираем топ-N записей
            selected = group[:self.max_records_per_formula]
            filtered.extend(selected)

            # Обновляем статистику
            duplication_stats['max_group_size'] = max(
                duplication_stats['max_group_size'], len(group)
            )

        duplication_stats['total_records_after'] = len(filtered)
        duplication_stats['avg_group_size'] = len(records) / len(formula_groups) if formula_groups else 0

        execution_time = (time.time() - start_time) * 1000

        self.last_stats = {
            'duplication_statistics': duplication_stats,
            'deduplication_rate': (len(records) - len(filtered)) / len(records) if records else 0,
            'execution_time_ms': execution_time,
            'max_records_per_formula': self.max_records_per_formula
        }

        return filtered

    def get_stage_name(self) -> str:
        return "Удаление дубликатов"