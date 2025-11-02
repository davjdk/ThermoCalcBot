"""
Phase transition detector for melting and boiling points.

This module implements the phase transition detection logic from calc_example.ipynb.
"""

import logging
import pandas as pd
from typing import Tuple, Optional


class PhaseTransitionDetector:
    """
    Определяет температуры фазовых переходов (плавление, кипение).
    """

    @staticmethod
    def get_most_common_melting_boiling_points(df: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
        """
        Находит самые частые ненулевые значения MeltingPoint и BoilingPoint.

        Фильтрация:
        - Игнорируются нулевые значения
        - BoilingPoint должен быть > MeltingPoint

        Args:
            df: DataFrame с данными вещества (колонки: MeltingPoint, BoilingPoint)

        Returns:
            (melting_point, boiling_point) или (None, None)

        Логирование:
            - ✓ Определены точки переходов: melting={value}K, boiling={value}K
            - ⚠ Точки переходов не определены для {formula}
        """
        if df.empty:
            return None, None

        # Находим самое частое ненулевое значение MeltingPoint
        melting_mask = df['MeltingPoint'] != 0
        if melting_mask.any():
            melting_point = df.loc[melting_mask, 'MeltingPoint'].value_counts().idxmax()
        else:
            melting_point = None

        # Для boiling_point фильтруем только те значения, которые больше melting_point
        if melting_point is not None:
            boiling_candidates = df[
                (df['BoilingPoint'] != 0) &
                (df['BoilingPoint'] > melting_point)
            ]['BoilingPoint']
        else:
            boiling_candidates = df[df['BoilingPoint'] != 0]['BoilingPoint']

        if len(boiling_candidates) > 0:
            boiling_point = boiling_candidates.value_counts().idxmax()
        else:
            boiling_point = None

        return melting_point, boiling_point

    @staticmethod
    def get_phase_at_temperature(T: float, melting: Optional[float], boiling: Optional[float]) -> str:
        """
        Определяет ожидаемую фазу при температуре T.

        Args:
            T: Температура в K
            melting: Температура плавления в K (может быть None)
            boiling: Температура кипения в K (может быть None)

        Returns:
            's' (solid), 'l' (liquid), или 'g' (gas)
        """
        if boiling and T >= boiling:
            return 'g'
        elif melting and T >= melting:
            return 'l'
        else:
            return 's'

    @staticmethod
    def validate_phase_sequence(old_phase: str, new_phase: str) -> bool:
        """
        Проверяет корректность последовательности фазовых переходов.
        Запрещает пропуск фаз (например, s → g без l).

        Args:
            old_phase: Предыдущая фаза
            new_phase: Новая фаза

        Returns:
            True если переход корректен, False если нет
        """
        phase_order = {'s': 0, 'l': 1, 'g': 2}

        if old_phase not in phase_order or new_phase not in phase_order:
            return True  # Неизвестные фазы разрешаем

        old_order = phase_order[old_phase]
        new_order = phase_order[new_phase]

        # Разрешаем только переход на следующую фазу или ту же
        return new_order <= old_order + 1