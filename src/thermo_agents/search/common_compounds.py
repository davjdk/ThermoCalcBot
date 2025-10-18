"""
Справочник и логика поиска для распространенных химических веществ.

Модуль содержит жестко закодированные правила поиска для наиболее
распространенных веществ в базе данных, где требуется безошибочное
определение (вода, углекислый газ, кислород, азот и т.д.).

Мотивация:
- Паттерны LIKE 'H2O%' ловят H2O2 (пероксид) вместо воды
- Для базовых веществ нужна 100% точность определения
- Ускорение поиска через точные условия вместо широких паттернов
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommonCompoundSpec:
    """
    Спецификация для однозначного определения распространенного вещества.

    Attributes:
        formulas: Список точных формул в базе данных (без паттернов LIKE)
        names: Стандартные названия для валидации
        description: Описание вещества для логирования
        exact_match_only: Если True, используется только точное совпадение формулы
    """

    formulas: List[str]
    names: List[str]
    description: str
    exact_match_only: bool = True


# Справочник распространенных веществ
COMMON_COMPOUNDS: Dict[str, CommonCompoundSpec] = {
    # Вода
    "H2O": CommonCompoundSpec(
        formulas=["H2O"],
        names=["Water", "Oxidane"],
        description="Вода",
        exact_match_only=True,
    ),
    # Углекислый газ
    "CO2": CommonCompoundSpec(
        formulas=["CO2"],
        names=["Carbon dioxide", "Carbonic anhydride"],
        description="Углекислый газ",
        exact_match_only=True,
    ),
    # Кислород
    "O2": CommonCompoundSpec(
        formulas=["O2"],
        names=["Oxygen", "Dioxygen"],
        description="Кислород",
        exact_match_only=True,
    ),
    # Азот
    "N2": CommonCompoundSpec(
        formulas=["N2"],
        names=["Nitrogen", "Dinitrogen"],
        description="Азот",
        exact_match_only=True,
    ),
    # Водород
    "H2": CommonCompoundSpec(
        formulas=["H2"],
        names=["Hydrogen", "Dihydrogen"],
        description="Водород",
        exact_match_only=True,
    ),
    # Аммиак
    "NH3": CommonCompoundSpec(
        formulas=["NH3"],
        names=["Ammonia", "Azane"],
        description="Аммиак",
        exact_match_only=True,
    ),
    # Хлороводород
    "HCl": CommonCompoundSpec(
        formulas=["HCl"],
        names=["Hydrogen chloride", "Hydrochloric acid"],
        description="Хлороводород",
        exact_match_only=True,
    ),
    # Метан
    "CH4": CommonCompoundSpec(
        formulas=["CH4"],
        names=["Methane"],
        description="Метан",
        exact_match_only=True,
    ),
    # Пероксид водорода
    "H2O2": CommonCompoundSpec(
        formulas=["H2O2"],
        names=["Hydrogen peroxide"],
        description="Пероксид водорода",
        exact_match_only=True,
    ),
    # Оксид углерода (угарный газ)
    "CO": CommonCompoundSpec(
        formulas=["CO"],
        names=["Carbon monoxide"],
        description="Угарный газ",
        exact_match_only=True,
    ),
    # Сера (элементарная)
    "S": CommonCompoundSpec(
        formulas=["S"],
        names=["Sulfur", "Sulphur"],
        description="Сера (элементарная, адаптивный выбор фазы по температуре)",
        exact_match_only=True,
    ),
}


class CommonCompoundResolver:
    """
    Резолвер для определения распространенных химических веществ.

    Предоставляет специализированную логику поиска для базовых веществ,
    которые должны определяться без ошибок.
    """

    def __init__(self):
        """Инициализация резолвера."""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._compound_map = COMMON_COMPOUNDS

    def is_common_compound(self, formula: str) -> bool:
        """
        Проверить, является ли формула распространенным веществом.

        Args:
            formula: Химическая формула для проверки

        Returns:
            True если вещество в справочнике распространенных
        """
        clean_formula = formula.strip()
        return clean_formula in self._compound_map

    def get_spec(self, formula: str) -> Optional[CommonCompoundSpec]:
        """
        Получить спецификацию распространенного вещества.

        Args:
            formula: Химическая формула

        Returns:
            Спецификация или None если вещество не в справочнике
        """
        clean_formula = formula.strip()
        return self._compound_map.get(clean_formula)

    def build_sql_condition(
        self, formula: str, compound_names: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Построить SQL-условие для точного поиска распространенного вещества.

        Args:
            formula: Химическая формула
            compound_names: Опциональные названия веществ

        Returns:
            SQL-условие для WHERE или None если вещество не распространенное
        """
        spec = self.get_spec(formula)
        if not spec:
            return None

        self.logger.debug(
            f"Построение точного условия для распространенного вещества: {spec.description}"
        )

        # Для точного совпадения используем жесткие условия
        conditions = []

        # Точное совпадение формулы (с учетом фаз в скобках)
        for exact_formula in spec.formulas:
            conditions.append(f"TRIM(Formula) = '{self._escape_sql(exact_formula)}'")
            # Разрешаем формулу с указанием фазы в скобках: H2O(g), H2O(l), H2O(s)
            conditions.append(f"Formula LIKE '{self._escape_sql(exact_formula)}(%'")

        # Опционально: поиск по названиям
        if compound_names:
            for name in compound_names:
                if name and name.strip():
                    escaped_name = self._escape_sql(name.strip())
                    conditions.append(
                        f"LOWER(TRIM(FirstName)) = LOWER('{escaped_name}')"
                    )

        # Объединяем условия через OR
        return "(" + " OR ".join(conditions) + ")"

    def _escape_sql(self, value: str) -> str:
        """
        Экранировать SQL-значение.

        Args:
            value: Строка для экранирования

        Returns:
            Безопасная для SQL строка
        """
        return value.replace("'", "''")

    def get_all_formulas(self) -> List[str]:
        """
        Получить список всех распространенных формул в справочнике.

        Returns:
            Список формул
        """
        return list(self._compound_map.keys())

    def get_description(self, formula: str) -> Optional[str]:
        """
        Получить описание распространенного вещества.

        Args:
            formula: Химическая формула

        Returns:
            Описание или None
        """
        spec = self.get_spec(formula)
        return spec.description if spec else None
