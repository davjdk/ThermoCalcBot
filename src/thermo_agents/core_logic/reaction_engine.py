"""
Reaction engine for thermodynamic calculations of chemical reactions.

This module implements the reaction thermodynamics calculations from calc_example.ipynb
including parsing reaction equations and calculating ΔH, ΔS, ΔG, K.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from ..models.extraction import ExtractedReactionParameters
from .compound_data_loader import CompoundDataLoader
from .phase_transition_detector import PhaseTransitionDetector
from .record_range_builder import RecordRangeBuilder
from .thermodynamic_engine import ThermodynamicEngine


class ReactionEngine:
    """
    Расчет ΔH, ΔS, ΔG, K для химической реакции.
    """

    def __init__(
        self,
        compound_loader: CompoundDataLoader,
        phase_detector: PhaseTransitionDetector,
        range_builder: RecordRangeBuilder,
        thermo_engine: ThermodynamicEngine,
        logger: logging.Logger,
    ):
        self.compound_loader = compound_loader
        self.phase_detector = phase_detector
        self.range_builder = range_builder
        self.thermo_engine = thermo_engine
        self.logger = logger
        self.R = 8.314  # Дж/(моль·K)

    def calculate_reaction(
        self,
        params: ExtractedReactionParameters,
        temperature_range: List[float],  # [T_start, T_end, step]
    ) -> pd.DataFrame:
        """
        Рассчитывает термодинамику реакции для диапазона температур.

        Алгоритм:

        1. Для каждого вещества:
           - Загрузить данные из БД (двухстадийный поиск)
           - Определить MeltingPoint, BoilingPoint
           - Получить записи для диапазона [T_start, T_end]

        2. Для каждой температуры T:
           - Для каждого вещества:
             * Найти подходящую запись (Tmin ≤ T ≤ Tmax)
             * Рассчитать H(T), S(T)
             * Умножить на стехиометрический коэффициент
           - Суммировать вклады:
             ΔH(T) = Σ [coeff · H(T)]
             ΔS(T) = Σ [coeff · S(T)]
           - Вычислить ΔG(T) = ΔH(T) - T·ΔS(T)
           - Вычислить ln(K) = -ΔG(T) / (R·T)
           - Вычислить K = exp(ln(K))

        3. Вернуть DataFrame с колонками:
           T (K), ΔH (Дж/моль), ΔS (Дж/(моль·K)), ΔG (Дж/моль), ln(K), K

        Args:
            params: Параметры из LLM (формулы, стехиометрия, уравнение)
            temperature_range: [T_start, T_end, step] в K

        Returns:
            DataFrame с результатами расчета

        Raises:
            ValueError: Если не найдены данные для одного из веществ

        Логирование:
            - ═══ РАСЧЕТ РЕАКЦИИ: {equation}
            - Стехиометрия: {stoichiometry}
            - ✓ {formula}: подготовлено {N} записей, coeff={coeff}
            - ⚠ T={T}K: нет подходящей записи для {formula}
            - ✓ Расчет завершен: {N} температурных точек
        """
        # Парсим уравнение реакции
        equation = params.balanced_equation
        all_compounds = params.all_compounds

        try:
            reaction_coeffs = self.parse_reaction_equation(equation, all_compounds)
        except Exception as e:
            self.logger.error(f"Ошибка парсинга уравнения '{equation}': {e}")
            raise ValueError(f"Ошибка парсинга уравнения: {e}")

        self.logger.info(f"═══ РАСЧЕТ РЕАКЦИИ: {equation}")
        self.logger.info(f"Стехиометрия: {reaction_coeffs}")

        # Подготовка данных для каждого вещества
        compound_data = {}

        for formula in all_compounds:
            # Получаем имена из compound_names если есть
            compound_names = (
                params.compound_names.get(formula)
                if hasattr(params, "compound_names") and params.compound_names
                else None
            )

            # Загружаем данные из БД
            df = self.compound_loader.get_raw_compound_data(formula, compound_names)

            if df.empty:
                self.logger.error(f"⚠ {formula}: нет данных в БД")
                raise ValueError(f"Не найдены данные для вещества {formula}")

            # Определяем точки фазовых переходов
            melting, boiling = (
                self.phase_detector.get_most_common_melting_boiling_points(df)
            )

            # Получаем записи для полного диапазона
            t_range_full = [temperature_range[0], temperature_range[1]]

            # Определяем is_elemental для текущего вещества (метод calculate_reaction)
            is_elemental = (
                params.compound_types.get(formula) if params.compound_types else None
            )

            records = self.range_builder.get_compound_records_for_range(
                df, t_range_full, melting, boiling, is_elemental=is_elemental
            )

            if not records:
                self.logger.error(
                    f"⚠ {formula}: не удалось получить записи для диапазона"
                )
                raise ValueError(f"Не удалось получить записи для вещества {formula}")

            compound_data[formula] = {
                "records": records,
                "melting": melting,
                "boiling": boiling,
                "coeff": reaction_coeffs.get(formula, 0),
            }

            self.logger.info(
                f"✓ {formula}: подготовлено {len(records)} записей, coeff={reaction_coeffs.get(formula, 0)}"
            )

        # Расчет для каждой температуры
        results = []
        T_start, T_end, T_step = temperature_range
        temperatures = np.arange(T_start, T_end + T_step, T_step)

        for T in temperatures:
            delta_H = 0.0
            delta_S = 0.0

            for formula, data in compound_data.items():
                coeff = data["coeff"]
                records = data["records"]

                # Находим подходящую запись для текущей температуры
                suitable_record = None
                for record in records:
                    if record["Tmin"] <= T <= record["Tmax"]:
                        suitable_record = record
                        break

                # Если не найдена запись в диапазоне, используем экстраполяцию
                if suitable_record is None and records:
                    # Находим запись с максимальным Tmax
                    max_record = max(records, key=lambda r: r.get("Tmax", 0))
                    T_max_available = max_record.get("Tmax", 0)

                    if T > T_max_available:
                        # Экстраполяция с постоянной теплоёмкостью
                        suitable_record = max_record
                        self.logger.debug(
                            f"🔼 T={T}K: экстраполяция для {formula} "
                            f"(T_max={T_max_available}K, используем Cp(T_max))"
                        )

                        # Рассчитываем свойства с экстраполяцией
                        properties = (
                            self.thermo_engine.calculate_properties_with_extrapolation(
                                suitable_record, T, T_max_available
                            )
                        )
                    else:
                        # Температура ниже минимума - используем первую запись
                        suitable_record = records[0]
                        self.logger.debug(
                            f"⚠ T={T}K: использована первая запись для {formula} "
                            f"(Tmin={records[0]['Tmin']}K)"
                        )
                        properties = self.thermo_engine.calculate_properties(
                            suitable_record, T
                        )
                else:
                    # Обычный расчёт в пределах диапазона
                    if suitable_record is None:
                        self.logger.warning(
                            f"⚠ T={T}K: нет подходящей записи для {formula}"
                        )
                        continue
                    properties = self.thermo_engine.calculate_properties(
                        suitable_record, T
                    )

                # Добавляем вклад в реакцию (с учетом стехиометрии)
                delta_H += coeff * properties["enthalpy"]
                delta_S += coeff * properties["entropy"]

            # Вычисляем ΔG и константу равновесия
            delta_G = delta_H - T * delta_S

            # ln(K) = -ΔG / (R * T)
            ln_K = -delta_G / (self.R * T) if T > 0 else 0
            K = (
                np.exp(ln_K) if abs(ln_K) < 700 else (np.inf if ln_K > 0 else 0)
            )  # Избегаем overflow

            results.append(
                {
                    "T": T,
                    "delta_H": delta_H,
                    "delta_S": delta_S,
                    "delta_G": delta_G,
                    "ln_K": ln_K,
                    "K": K,
                }
            )

        df_result = pd.DataFrame(results)
        self.logger.info(f"✓ Расчет завершен: {len(df_result)} температурных точек")

        return df_result

    def parse_reaction_equation(
        self, equation: str, all_compounds: List[str]
    ) -> Dict[str, float]:
        """
        Парсит уравнение реакции и извлекает стехиометрические коэффициенты.

        Поддерживаемые форматы:
        - "A + 2B = C"
        - "A + 2B → C"
        - "A + 2B -> C"

        Args:
            equation: Сбалансированное уравнение
            all_compounds: Список формул веществ

        Returns:
            {formula: coefficient}
            Реагенты (левая сторона): отрицательные коэффициенты
            Продукты (правая сторона): положительные коэффициенты

        Пример:
            "2H2 + O2 → 2H2O"
            → {'H2': -2.0, 'O2': -1.0, 'H2O': 2.0}
        """
        # Разделяем на левую и правую части
        if "=" in equation:
            left, right = equation.split("=")
        elif "→" in equation:
            left, right = equation.split("→")
        elif "->" in equation:
            left, right = equation.split("->")
        else:
            raise ValueError(
                f"Уравнение должно содержать '=', '→' или '->': {equation}"
            )

        def parse_side(side_str: str, all_compounds: List[str]) -> Dict[str, float]:
            """Парсит одну сторону уравнения."""
            coeffs = {}
            side_str = side_str.strip()

            # Создаем regex паттерн для поиска всех соединений
            # Сортируем по длине (сначала длинные), чтобы избежать ложных совпадений
            sorted_compounds = sorted(all_compounds, key=len, reverse=True)

            for compound in sorted_compounds:
                # Экранируем спецсимволы в формуле
                escaped_compound = re.escape(compound)
                # Паттерн: опциональный коэффициент + формула + граница слова
                pattern = r"(\d*\.?\d*)\s*" + escaped_compound + r"(?:\s|$|\+)"

                matches = re.finditer(pattern, side_str)

                for match in matches:
                    coeff_str = match.group(1).strip()
                    coeff = float(coeff_str) if coeff_str else 1.0

                    if compound in coeffs:
                        coeffs[compound] += coeff
                    else:
                        coeffs[compound] = coeff

            return coeffs

        # Парсим обе стороны
        left_coeffs = parse_side(left, all_compounds)
        right_coeffs = parse_side(right, all_compounds)

        # Объединяем: реактанты (левая сторона) - отрицательные, продукты (правая) - положительные
        reaction_coeffs = {}

        for compound, coeff in left_coeffs.items():
            reaction_coeffs[compound] = -coeff

        for compound, coeff in right_coeffs.items():
            if compound in reaction_coeffs:
                reaction_coeffs[compound] += coeff
            else:
                reaction_coeffs[compound] = coeff

        return reaction_coeffs

    def calculate_reaction_with_metadata(
        self, params: ExtractedReactionParameters, temperature_range: List[float]
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Расчет реакции с возвратом метаданных об отобранных записях.

        Returns:
            (df_result, compounds_metadata)

            compounds_metadata = {
                formula: {
                    'records_used': [список pd.Series],
                    'melting_point': float,
                    'boiling_point': float,
                    'phase_transitions': [(T, phase_from, phase_to), ...],
                    'is_yaml_cache': bool,
                    'search_stage': int
                }
            }
        """
        # Парсим уравнение реакции
        equation = params.balanced_equation
        all_compounds = params.all_compounds

        try:
            reaction_coeffs = self.parse_reaction_equation(equation, all_compounds)
        except Exception as e:
            self.logger.error(f"Ошибка парсинга уравнения '{equation}': {e}")
            raise ValueError(f"Ошибка парсинга уравнения: {e}")

        self.logger.info(f"═══ РАСЧЕТ РЕАКЦИИ: {equation}")
        self.logger.info(f"Стехиометрия: {reaction_coeffs}")

        # Подготовка данных для каждого вещества и сбор метаданных
        compound_data = {}
        compounds_metadata = {}

        for formula in all_compounds:
            # Получаем имена из compound_names если есть
            compound_names = (
                params.compound_names.get(formula)
                if hasattr(params, "compound_names") and params.compound_names
                else None
            )

            # Загружаем данные из БД
            df, is_yaml_cache, search_stage = (
                self.compound_loader.get_raw_compound_data_with_metadata(
                    formula, compound_names
                )
            )

            if df.empty:
                self.logger.error(f"⚠ {formula}: нет данных в БД")
                raise ValueError(f"Не найдены данные для вещества {formula}")

            # Определяем точки фазовых переходов
            melting, boiling = (
                self.phase_detector.get_most_common_melting_boiling_points(df)
            )

            # Получаем записи для полного диапазона
            t_range_full = [temperature_range[0], temperature_range[1]]

            # Определяем is_elemental для текущего вещества (метод calculate_reaction_with_metadata)
            is_elemental = (
                params.compound_types.get(formula) if params.compound_types else None
            )

            records = self.range_builder.get_compound_records_for_range(
                df, t_range_full, melting, boiling, is_elemental=is_elemental
            )

            if not records:
                self.logger.error(
                    f"⚠ {formula}: не удалось получить записи для диапазона"
                )
                raise ValueError(f"Не удалось получить записи для вещества {formula}")

            # Собираем информацию о фазовых переходах на основе данных Tmin/Tmax
            phase_transitions = []

            # Сортируем записи по Tmin для определения последовательности фаз
            sorted_records = sorted(records, key=lambda r: r.get("Tmin", float("inf")))

            for i, record in enumerate(sorted_records):
                current_phase = record.get("Phase", "unknown")
                current_Tmin = record.get("Tmin")
                current_Tmax = record.get("Tmax")

                # Пропускаем записи без температурных данных
                if current_Tmin is None or current_Tmax is None:
                    continue

                # Ищем следующую запись с другой фазой
                for next_record in sorted_records[i + 1 :]:
                    next_phase = next_record.get("Phase", "unknown")
                    next_Tmin = next_record.get("Tmin")

                    # Если фаза изменилась, фиксируем переход
                    if next_phase != current_phase and next_Tmin is not None:
                        # Переход происходит в начале следующей записи
                        transition_T = next_Tmin
                        phase_transitions.append(
                            (transition_T, current_phase, next_phase)
                        )
                        break

            # Сохраняем метаданные
            compounds_metadata[formula] = {
                "records_used": records,
                "melting_point": melting,
                "boiling_point": boiling,
                "phase_transitions": phase_transitions,
                "is_yaml_cache": is_yaml_cache,
                "search_stage": search_stage,
            }

            compound_data[formula] = {
                "records": records,
                "melting": melting,
                "boiling": boiling,
                "coeff": reaction_coeffs.get(formula, 0),
            }

            source_info = "YAML-кэш" if is_yaml_cache else f"БД (стадия {search_stage})"
            self.logger.info(
                f"✓ {formula}: подготовлено {len(records)} записей, coeff={reaction_coeffs.get(formula, 0)} ({source_info})"
            )

        # Расчет для каждой температуры (остальная логика без изменений)
        results = []
        T_start, T_end, T_step = temperature_range
        temperatures = np.arange(T_start, T_end + T_step, T_step)

        for T in temperatures:
            delta_H = 0.0
            delta_S = 0.0

            for formula, data in compound_data.items():
                coeff = data["coeff"]
                records = data["records"]

                # Находим подходящую запись для текущей температуры
                suitable_record = None
                for record in records:
                    if record["Tmin"] <= T <= record["Tmax"]:
                        suitable_record = record
                        break

                # Если не найдена запись в диапазоне, используем экстраполяцию
                if suitable_record is None and records:
                    # Находим запись с максимальным Tmax
                    max_record = max(records, key=lambda r: r.get("Tmax", 0))
                    T_max_available = max_record.get("Tmax", 0)

                    if T > T_max_available:
                        # Экстраполяция с постоянной теплоёмкостью
                        suitable_record = max_record
                        self.logger.debug(
                            f"🔼 T={T}K: экстраполяция для {formula} "
                            f"(T_max={T_max_available}K, используем Cp(T_max))"
                        )

                        # Рассчитываем свойства с экстраполяцией
                        properties = (
                            self.thermo_engine.calculate_properties_with_extrapolation(
                                suitable_record, T, T_max_available
                            )
                        )
                    else:
                        # Температура ниже минимума - используем первую запись
                        suitable_record = records[0]
                        self.logger.debug(
                            f"⚠ T={T}K: использована первая запись для {formula} "
                            f"(Tmin={records[0]['Tmin']}K)"
                        )
                        properties = self.thermo_engine.calculate_properties(
                            suitable_record, T
                        )
                else:
                    # Обычный расчёт в пределах диапазона
                    if suitable_record is None:
                        self.logger.warning(
                            f"⚠ T={T}K: нет подходящей записи для {formula}"
                        )
                        continue
                    properties = self.thermo_engine.calculate_properties(
                        suitable_record, T
                    )

                # Добавляем вклад в реакцию (с учетом стехиометрии)
                delta_H += coeff * properties["enthalpy"]
                delta_S += coeff * properties["entropy"]

            # Вычисляем ΔG и константу равновесия
            delta_G = delta_H - T * delta_S

            # ln(K) = -ΔG / (R * T)
            ln_K = -delta_G / (self.R * T) if T > 0 else 0
            K = (
                np.exp(ln_K) if abs(ln_K) < 700 else (np.inf if ln_K > 0 else 0)
            )  # Избегаем overflow

            results.append(
                {
                    "T": T,
                    "delta_H": delta_H,
                    "delta_S": delta_S,
                    "delta_G": delta_G,
                    "ln_K": ln_K,
                    "K": K,
                }
            )

        df_result = pd.DataFrame(results)
        self.logger.info(f"✓ Расчет завершен: {len(df_result)} температурных точек")

        return df_result, compounds_metadata
