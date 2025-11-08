"""
Record range builder with three-level selection strategy.

This module implements the record selection logic from calc_example.ipynb
with three-level strategy and phase transition handling.
"""

import logging
from typing import List, Optional, Tuple

import pandas as pd

from .phase_transition_detector import PhaseTransitionDetector


class RecordRangeBuilder:
    """
    Строит список записей для покрытия температурного диапазона.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.phase_detector = PhaseTransitionDetector()

    def get_compound_records_for_range(
        self,
        df: pd.DataFrame,
        t_range: List[float],  # [T_start, T_end]
        melting: Optional[float],
        boiling: Optional[float],
        tolerance: float = 1.0,
        is_elemental: Optional[bool] = None,
    ) -> List[pd.Series]:
        """
        Возвращает список записей, покрывающих весь температурный диапазон.

        Трехуровневая стратегия поиска:

        СТРАТЕГИЯ 1 (приоритет):
        - Ищем запись для ожидаемой фазы с Tmin ≈ current_T (±tolerance)
        - ДЛЯ СЛОЖНЫХ ВЕЩЕСТВ (is_elemental=False): приоритет записям с H298≠0, S298≠0
          если Tmin-Tmax покрывает 298±1K

        СТРАТЕГИЯ 2 (fallback):
        - Ищем любую запись с Tmin ≈ current_T
        - Проверяем, что >50% диапазона в правильной фазе
        - ДЛЯ СЛОЖНЫХ ВЕЩЕСТВ: приоритет записям с H298≠0, S298≠0

        СТРАТЕГИЯ 3 (последний шанс):
        - Ищем запись, которая ПОКРЫВАЕТ current_T (Tmin < current_T < Tmax)
        - Проверяем, что >50% ОСТАВШЕГОСЯ диапазона в правильной фазе
        - ДЛЯ СЛОЖНЫХ ВЕЩЕСТВ: приоритет записям с H298≠0, S298≠0

        Учёт фазовых переходов:
        - При достижении melting/boiling переключается на соответствующую фазу
        - Продолжает поиск с температуры перехода
        - При смене фазы первая запись новой фазы не должна иметь H298=S298=0 (для сложных веществ)

        Args:
            df: DataFrame с записями вещества
            t_range: [T_start, T_end]
            melting: Температура плавления (K)
            boiling: Температура кипения (K)
            tolerance: Допустимое отклонение для Tmin (K)
            is_elemental: True = простое вещество (H298=0 допустимо),
                         False = сложное (приоритет H298≠0, S298≠0),
                         None = не учитывать фильтрацию

        Returns:
            Список записей (pd.Series), покрывающих весь диапазон

        Логирование:
            - [Стратегия 1] Использована запись фазы '{phase}' при T={T}K
            - [Стратегия 2] Использована запись фазы '{phase}' (доминирует {dom_phase}) при T={T}K
            - [Стратегия 3] Использована покрывающая запись фазы '{phase}' (Tmin={Tmin}, покрывает T={T}K)
            - Фазовый переход при T={transition_T}K внутри записи {phase}
            - ⚠ Не найдена подходящая запись для T={T}K (ожидаемая фаза: {phase})
            - ⚠ Отфильтрована запись с H298=0, S298=0 (сложное вещество) при T={T}K
        """
        records = []
        current_T = t_range[0]
        target_T = t_range[1]
        last_phase = None

        while current_T < target_T:
            # Определяем текущую ожидаемую фазу на основе температуры
            expected_phase = self.phase_detector.get_phase_at_temperature(
                current_T, melting, boiling
            )

            # СТРАТЕГИЯ 1: Ищем запись для ожидаемой фазы, начинающуюся с current_T
            matching_records = df[
                (df["Phase"] == expected_phase)
                & (df["Tmin"] <= current_T + tolerance)
                & (df["Tmin"] >= current_T - tolerance)
            ]

            # Фильтрация для сложных веществ: приоритет H298≠0, S298≠0
            if not matching_records.empty and is_elemental is False:
                matching_records = self._prioritize_nonzero_h298_s298(
                    matching_records, current_T, last_phase, expected_phase
                )

            if not matching_records.empty:
                # Нашли запись для ожидаемой фазы
                record = matching_records.iloc[0]
                records.append(record)
                last_phase = expected_phase
                self.logger.debug(
                    f"[Стратегия 1] Использована запись фазы '{expected_phase}' при T={current_T}K"
                )
            else:
                # СТРАТЕГИЯ 2: Не найдена запись для ожидаемой фазы
                candidates = self._find_candidates_starting_at_T(
                    df, current_T, tolerance
                )

                valid_candidates = []

                if not candidates.empty:
                    # Фильтруем кандидатов по критериям
                    for idx, candidate in candidates.iterrows():
                        if not self._is_valid_phase_transition(
                            last_phase, candidate["Phase"]
                        ):
                            continue

                        # Проверка: >50% диапазона в корректной фазе
                        dominant_phase = self._get_dominant_phase(
                            candidate, melting, boiling
                        )
                        if dominant_phase == candidate["Phase"]:
                            valid_candidates.append((idx, candidate, dominant_phase, 2))

                # СТРАТЕГИЯ 3: Ищем запись, которая ПОКРЫВАЕТ current_T
                if not valid_candidates:
                    covering_candidates = df[
                        (df["Tmin"] < current_T) & (df["Tmax"] > current_T)
                    ]

                    for idx, candidate in covering_candidates.iterrows():
                        if not self._is_valid_phase_transition(
                            last_phase, candidate["Phase"]
                        ):
                            continue

                        # Проверка: >50% ОСТАВШЕГОСЯ диапазона в правильной фазе
                        phase_fraction = self._get_phase_fraction_from_T(
                            candidate, current_T, melting, boiling
                        )

                        if phase_fraction > 0.5:
                            valid_candidates.append(
                                (idx, candidate, candidate["Phase"], 3)
                            )

                if not valid_candidates:
                    self.logger.warning(
                        f"⚠ Не найдена подходящая запись для T={current_T}K "
                        f"(ожидаемая фаза: {expected_phase})"
                    )
                    break

                # Сортируем кандидатов по приоритету (меньше = лучше)
                valid_candidates.sort(key=lambda x: x[3])

                # Берём лучшего кандидата
                idx, record, phase_info, strategy = valid_candidates[0]
                records.append(record)
                last_phase = record["Phase"]

                if strategy == 2:
                    self.logger.debug(
                        f"[Стратегия 2] Использована запись фазы '{record['Phase']}' "
                        f"(доминирует {phase_info}) при T={current_T}K"
                    )
                elif strategy == 3:
                    self.logger.debug(
                        f"[Стратегия 3] Использована покрывающая запись фазы '{record['Phase']}' "
                        f"(Tmin={record['Tmin']}, покрывает T={current_T}K)"
                    )

            # Определяем следующую температуру
            record_tmax = record["Tmax"]

            # Проверяем, достигли ли мы точки фазового перехода внутри текущей записи
            next_transition = None
            if melting and current_T < melting <= record_tmax:
                next_transition = melting
            elif boiling and current_T < boiling <= record_tmax:
                next_transition = boiling

            if next_transition:
                # Фазовый переход внутри текущей записи
                self.logger.debug(
                    f"Фазовый переход при T={next_transition}K внутри записи {last_phase}"
                )
                current_T = record_tmax

                # Если достигли или превысили целевую температуру, завершаем
                if current_T >= target_T:
                    break
            else:
                # Переход к следующей записи
                current_T = record_tmax

                # Если достигли или превысили целевую температуру, завершаем
                if current_T >= target_T:
                    break

        return records

    def _find_candidates_starting_at_T(
        self, df: pd.DataFrame, T: float, tolerance: float
    ) -> pd.DataFrame:
        """Ищет записи, начинающиеся с температуры T (с допуском)."""
        return df[(df["Tmin"] <= T + tolerance) & (df["Tmin"] >= T - tolerance)]

    def _is_valid_phase_transition(
        self, old_phase: Optional[str], new_phase: str
    ) -> bool:
        """Проверяет корректность перехода между фазами."""
        if old_phase is None:
            return True

        return self.phase_detector.validate_phase_sequence(old_phase, new_phase)

    def _get_dominant_phase(
        self, record: pd.Series, melting: Optional[float], boiling: Optional[float]
    ) -> str:
        """
        Определяет доминирующую фазу для записи на основе температурного диапазона.
        Возвращает фазу, в которой запись находится >50% времени.
        """
        tmin = record["Tmin"]
        tmax = record["Tmax"]
        total_range = tmax - tmin

        # Разбиваем диапазон по фазовым переходам
        phase_ranges = {"s": 0, "l": 0, "g": 0}

        current_t = tmin
        while current_t < tmax:
            # Определяем фазу при current_t
            phase = self.phase_detector.get_phase_at_temperature(
                current_t, melting, boiling
            )

            # Определяем конец текущего фазового сегмента
            if phase == "s" and melting and melting < tmax:
                segment_end = min(melting, tmax)
            elif phase == "l" and boiling and boiling < tmax:
                segment_end = min(boiling, tmax)
            else:
                segment_end = tmax

            # Добавляем длительность сегмента
            phase_ranges[phase] += segment_end - current_t
            current_t = segment_end

        # Находим доминирующую фазу (>50%)
        for phase, duration in phase_ranges.items():
            if duration > total_range / 2:
                return phase

        # Если нет явного доминирования (50/50), возвращаем фазу начала диапазона
        return self.phase_detector.get_phase_at_temperature(tmin, melting, boiling)

    def _get_phase_fraction_from_T(
        self,
        record: pd.Series,
        start_T: float,
        melting: Optional[float],
        boiling: Optional[float],
    ) -> float:
        """
        Вычисляет, какая доля диапазона записи [start_T, Tmax] находится в фазе записи.
        Используется для СТРАТЕГИИ 3, когда запись начинается раньше current_T.
        """
        tmin = max(start_T, record["Tmin"])  # Начинаем с start_T или Tmin записи
        tmax = record["Tmax"]
        record_phase = record["Phase"]

        if tmin >= tmax:
            return 0.0

        total_range = tmax - tmin
        phase_duration = 0.0

        current_t = tmin
        while current_t < tmax:
            phase_at_t = self.phase_detector.get_phase_at_temperature(
                current_t, melting, boiling
            )

            # Определяем конец текущего фазового сегмента
            if phase_at_t == "s" and melting and melting < tmax:
                segment_end = min(melting, tmax)
            elif phase_at_t == "l" and boiling and boiling < tmax:
                segment_end = min(boiling, tmax)
            else:
                segment_end = tmax

            # Если фаза совпадает с фазой записи, добавляем длительность
            if phase_at_t == record_phase:
                phase_duration += segment_end - current_t

            current_t = segment_end

        return phase_duration / total_range if total_range > 0 else 0.0

    def _prioritize_nonzero_h298_s298(
        self,
        records: pd.DataFrame,
        current_T: float,
        last_phase: Optional[str],
        expected_phase: str,
    ) -> pd.DataFrame:
        """
        Приоритизация записей с H298≠0 и S298≠0 для сложных веществ.

        Логика:
        1. Если Tmin-Tmax покрывает 298±1K: отдать приоритет записям с H298≠0, S298≠0
        2. При смене фазы (last_phase ≠ expected_phase): первая запись новой фазы
           не должна иметь H298=0, S298=0

        Args:
            records: DataFrame с кандидатами
            current_T: Текущая температура
            last_phase: Предыдущая фаза (None если это первая запись)
            expected_phase: Ожидаемая фаза на текущей температуре

        Returns:
            Отфильтрованный DataFrame
        """
        if records.empty:
            return records

        # Проверка смены фазы
        is_phase_transition = (last_phase is not None) and (
            last_phase != expected_phase
        )

        # Фильтруем записи с H298=0 и S298=0
        nonzero_records = records[
            (records["H298"].abs() > 0.001) | (records["S298"].abs() > 0.001)
        ]

        # Записи, покрывающие 298±1K
        covering_298 = records[(records["Tmin"] <= 299.0) & (records["Tmax"] >= 297.0)]

        # ПРИОРИТЕТ 1: Смена фазы - ОБЯЗАТЕЛЬНО H298≠0 или S298≠0
        if is_phase_transition:
            if not nonzero_records.empty:
                self.logger.debug(
                    f"[Фазовый переход {last_phase}->{expected_phase}] "
                    f"Использованы записи с H298≠0 или S298≠0 (найдено {len(nonzero_records)})"
                )
                return nonzero_records
            else:
                # Если нет записей с ненулевыми значениями, логируем предупреждение
                self.logger.warning(
                    f"⚠ Фазовый переход {last_phase}->{expected_phase}: "
                    f"нет записей с H298≠0, S298≠0. Используются записи с нулевыми значениями."
                )
                return records

        # ПРИОРИТЕТ 2: Записи, покрывающие 298±1K с H298≠0, S298≠0
        if not covering_298.empty:
            nonzero_covering_298 = covering_298[
                (covering_298["H298"].abs() > 0.001)
                | (covering_298["S298"].abs() > 0.001)
            ]
            if not nonzero_covering_298.empty:
                self.logger.debug(
                    f"[Приоритет H298≠0] Найдено {len(nonzero_covering_298)} записей, "
                    f"покрывающих 298K с ненулевыми H298/S298"
                )
                return nonzero_covering_298

        # ПРИОРИТЕТ 3: Любые записи с H298≠0, S298≠0
        if not nonzero_records.empty:
            self.logger.debug(
                f"[Приоритет H298≠0] Использованы записи с ненулевыми H298/S298 "
                f"(найдено {len(nonzero_records)})"
            )
            return nonzero_records

        # FALLBACK: Если все записи имеют H298=S298=0, возвращаем их
        # (может быть для некоторых модификаций веществ)
        self.logger.debug(
            f"⚠ Все записи имеют H298≈0, S298≈0 (сложное вещество). "
            f"Используются как есть ({len(records)} записей)."
        )
        return records
