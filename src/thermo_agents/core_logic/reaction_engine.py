"""
Reaction engine for thermodynamic calculations of chemical reactions.

This module implements the reaction thermodynamics calculations from calc_example.ipynb
including parsing reaction equations and calculating ΔH, ΔS, ΔG, K.
"""

import logging
import numpy as np
import pandas as pd
import re
from typing import Dict, List, Optional, Tuple

from .compound_data_loader import CompoundDataLoader
from .phase_transition_detector import PhaseTransitionDetector
from .record_range_builder import RecordRangeBuilder
from .thermodynamic_engine import ThermodynamicEngine
from ..models.extraction import ExtractedReactionParameters


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
        logger: logging.Logger
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
        temperature_range: List[float]  # [T_start, T_end, step]
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
            compound_names = params.compound_names.get(formula) if hasattr(params, 'compound_names') and params.compound_names else None

            # Загружаем данные из БД
            df = self.compound_loader.get_raw_compound_data(formula, compound_names)

            if df.empty:
                self.logger.error(f"⚠ {formula}: нет данных в БД")
                raise ValueError(f"Не найдены данные для вещества {formula}")

            # Определяем точки фазовых переходов
            melting, boiling = self.phase_detector.get_most_common_melting_boiling_points(df)

            # Получаем записи для полного диапазона
            t_range_full = [temperature_range[0], temperature_range[1]]
            records = self.range_builder.get_compound_records_for_range(
                df, t_range_full, melting, boiling
            )

            if not records:
                self.logger.error(f"⚠ {formula}: не удалось получить записи для диапазона")
                raise ValueError(f"Не удалось получить записи для вещества {formula}")

            compound_data[formula] = {
                'records': records,
                'melting': melting,
                'boiling': boiling,
                'coeff': reaction_coeffs.get(formula, 0)
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
                coeff = data['coeff']
                records = data['records']

                # Находим подходящую запись для текущей температуры
                suitable_record = None
                for record in records:
                    if record['Tmin'] <= T <= record['Tmax']:
                        suitable_record = record
                        break

                # Временное решение для этапа 2: если нет точного совпадения,
                # используем первую запись (даже если T вне диапазона)
                if suitable_record is None and records:
                    suitable_record = records[0]
                    self.logger.debug(f"⚠ T={T}K: использована первая запись для {formula} (Tmin={records[0]['Tmin']}K)")

                if suitable_record is None:
                    self.logger.warning(f"⚠ T={T}K: нет подходящей записи для {formula}")
                    continue

                # Рассчитываем термодинамические свойства
                properties = self.thermo_engine.calculate_properties(suitable_record, T)

                # Добавляем вклад в реакцию (с учетом стехиометрии)
                delta_H += coeff * properties['enthalpy']
                delta_S += coeff * properties['entropy']

            # Вычисляем ΔG и константу равновесия
            delta_G = delta_H - T * delta_S

            # ln(K) = -ΔG / (R * T)
            ln_K = -delta_G / (self.R * T) if T > 0 else 0
            K = np.exp(ln_K) if abs(ln_K) < 700 else (np.inf if ln_K > 0 else 0)  # Избегаем overflow

            results.append({
                'T': T,
                'delta_H': delta_H,
                'delta_S': delta_S,
                'delta_G': delta_G,
                'ln_K': ln_K,
                'K': K
            })

        df_result = pd.DataFrame(results)
        self.logger.info(f"✓ Расчет завершен: {len(df_result)} температурных точек")

        return df_result

    def parse_reaction_equation(
        self,
        equation: str,
        all_compounds: List[str]
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
        if '=' in equation:
            left, right = equation.split('=')
        elif '→' in equation:
            left, right = equation.split('→')
        elif '->' in equation:
            left, right = equation.split('->')
        else:
            raise ValueError(f"Уравнение должно содержать '=', '→' или '->': {equation}")

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
                pattern = r'(\d*\.?\d*)\s*' + escaped_compound + r'(?:\s|$|\+)'

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