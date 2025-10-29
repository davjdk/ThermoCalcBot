"""
Transition Data Manager - Этап 4 реализации

Управление данными фазовых переходов из базы данных.

КРИТИЧЕСКИ ВАЖНО: В БД НЕТ полей h_fusion и h_vaporization!
Энтальпии переходов рассчитываются из разницы H298 разных фаз.

Реальная структура БД:
- Таблица: compounds
- Поля: MeltingPoint, BoilingPoint, H298, S298, f1-f6
- Все поля в PascalCase
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum

from ..models.search import (
    DatabaseRecord,
    PhaseTransition,
    TransitionType
)
from .thermodynamic_calculator import ThermodynamicCalculator

logger = logging.getLogger(__name__)


class CompoundType(Enum):
    """Типы химических соединений для эвристических оценок."""
    METAL = "metal"
    SALT = "salt"
    OXIDE = "oxide"
    MOLECULAR = "molecular"
    UNKNOWN = "unknown"


class TransitionDataError(Exception):
    """Ошибка при обработке данных фазовых переходов."""
    pass


@dataclass
class TransitionDataManager:
    """
    Управление данными фазовых переходов.

    Основные задачи:
    1. Извлечение температур переходов из БД (MeltingPoint, BoilingPoint)
    2. Расчёт энтальпий переходов из разницы H298 разных фаз
    3. Эвристические оценки при отсутствии/некорректности данных
    4. Валидация термодинамической согласованности
    5. Кэширование результатов для быстрого доступа

    ВАЖНО: H298 в БД — это энтальпии ОБРАЗОВАНИЯ, а не абсолютные!
    Расчёт ΔH_transition — это ПРИБЛИЖЕНИЕ!
    """

    thermodynamic_calculator: ThermodynamicCalculator
    _transition_cache: Dict[str, List[PhaseTransition]] = None

    def __post_init__(self):
        """Инициализация менеджера данных."""
        self.thermodynamic_calculator = ThermodynamicCalculator()
        self._transition_cache = {}

    def extract_transition_data(
        self,
        records: List[DatabaseRecord]
    ) -> List[PhaseTransition]:
        """
        Извлечь данные о фазовых переходах из записей БД.

        Алгоритм:
        1. Извлечь MeltingPoint и BoilingPoint из записей
        2. Найти записи для разных фаз при температурах переходов
        3. Рассчитать ΔH_transition из разницы энтальпий образования
        4. Применить эвристики при необходимости
        5. Валидировать физическую корректность

        Args:
            records: Записи БД для одного соединения

        Returns:
            List[PhaseTransition]: Список фазовых переходов
        """

        if not records:
            logger.warning("Нет записей для извлечения данных переходов")
            return []

        formula = records[0].formula
        logger.info(f"Извлечение данных переходов для {formula} из {len(records)} записей")

        # Проверяем кэш
        cache_key = f"{formula}_{len(records)}"
        if cache_key in self._transition_cache:
            logger.debug(f"Используем кэшированные переходы для {formula}")
            return self._transition_cache[cache_key]

        transitions = []

        # Группируем записи по фазам
        records_by_phase = self._group_records_by_phase(records)

        # 1. Плавление (s → l)
        melting_transition = self._extract_melting_transition(records_by_phase, formula)
        if melting_transition:
            transitions.append(melting_transition)

        # 2. Кипение (l → g) или сублимация (s → g)
        boiling_transition = self._extract_boiling_transition(records_by_phase, formula)
        if boiling_transition:
            transitions.append(boiling_transition)

        # Кэшируем результат
        self._transition_cache[cache_key] = transitions

        logger.info(f"Извлечено {len(transitions)} переходов для {formula}")
        for transition in transitions:
            logger.debug(f"  {transition.to_dict()}")

        return transitions

    def _group_records_by_phase(
        self,
        records: List[DatabaseRecord]
    ) -> Dict[str, List[DatabaseRecord]]:
        """Сгруппировать записи по фазам."""
        phase_groups = {}
        for record in records:
            phase = record.phase.lower()
            if phase not in phase_groups:
                phase_groups[phase] = []
            phase_groups[phase].append(record)
        return phase_groups

    def _extract_melting_transition(
        self,
        records_by_phase: Dict[str, List[DatabaseRecord]],
        formula: str
    ) -> Optional[PhaseTransition]:
        """Извлечь данные о плавлении."""

        if 's' not in records_by_phase or 'l' not in records_by_phase:
            logger.debug(f"Нет данных для плавления {formula} (требуются s и l фазы)")
            return None

        solid_records = records_by_phase['s']
        liquid_records = records_by_phase['l']

        # Извлекаем температуру плавления
        melting_point = self._extract_melting_point(solid_records + liquid_records)
        if melting_point is None:
            logger.debug(f"Нет MeltingPoint для {formula}")
            return None

        # Выбираем подходящие записи для расчёта
        solid_record = self._select_record_for_temperature(solid_records, melting_point)
        liquid_record = self._select_record_for_temperature(liquid_records, melting_point)

        if solid_record is None or liquid_record is None:
            logger.warning(f"Не найдены подходящие записи для расчёта плавления {formula}")
            return None

        # Рассчитываем энтальпию перехода
        delta_h, method = self.calculate_transition_enthalpy(
            solid_record, liquid_record, melting_point
        )

        # Рассчитываем энтропию перехода
        delta_s = (delta_h * 1000) / melting_point  # кДж → Дж

        # Создаём объект перехода
        try:
            transition = PhaseTransition(
                temperature=melting_point,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=delta_h,
                delta_S_transition=delta_s,
                reliability=0.8 if method == 'calculated' else 0.5,
                calculation_method=method,
                warning=None
            )

            logger.info(
                f"Плавление {formula}: T={melting_point:.1f}K, "
                f"ΔH={delta_h:.3f} кДж/моль, метод={method}"
            )

            return transition

        except ValueError as e:
            logger.warning(f"Ошибка валидации перехода плавления {formula}: {e}")
            # Пробуем эвристику
            return self._create_heuristic_melting_transition(melting_point, formula)

    def _extract_boiling_transition(
        self,
        records_by_phase: Dict[str, List[DatabaseRecord]],
        formula: str
    ) -> Optional[PhaseTransition]:
        """Извлечь данные о кипении или сублимации."""

        # Извлекаем температуру кипения
        all_records = []
        for phase_records in records_by_phase.values():
            all_records.extend(phase_records)

        boiling_point = self._extract_boiling_point(all_records)
        if boiling_point is None:
            logger.debug(f"Нет BoilingPoint для {formula}")
            return None

        # Определяем тип перехода: кипение (l→g) или сублимация (s→g)
        if 'l' in records_by_phase and 'g' in records_by_phase:
            # Кипение
            liquid_records = records_by_phase['l']
            gas_records = records_by_phase['g']

            liquid_record = self._select_record_for_temperature(liquid_records, boiling_point)
            gas_record = self._select_record_for_temperature(gas_records, boiling_point)

            if liquid_record and gas_record:
                delta_h, method = self.calculate_transition_enthalpy(
                    liquid_record, gas_record, boiling_point
                )
                delta_s = (delta_h * 1000) / boiling_point

                try:
                    transition = PhaseTransition(
                        temperature=boiling_point,
                        from_phase='l',
                        to_phase='g',
                        transition_type=TransitionType.BOILING,
                        delta_H_transition=delta_h,
                        delta_S_transition=delta_s,
                        reliability=0.8 if method == 'calculated' else 0.5,
                        calculation_method=method,
                        warning=None
                    )

                    logger.info(
                        f"Кипение {formula}: T={boiling_point:.1f}K, "
                        f"ΔH={delta_h:.3f} кДж/моль, метод={method}"
                    )

                    return transition

                except ValueError as e:
                    logger.warning(f"Ошибка валидации перехода кипения {formula}: {e}")

        elif 's' in records_by_phase and 'g' in records_by_phase:
            # Сублимация
            solid_records = records_by_phase['s']
            gas_records = records_by_phase['g']

            solid_record = self._select_record_for_temperature(solid_records, boiling_point)
            gas_record = self._select_record_for_temperature(gas_records, boiling_point)

            if solid_record and gas_record:
                delta_h, method = self.calculate_transition_enthalpy(
                    solid_record, gas_record, boiling_point
                )
                delta_s = (delta_h * 1000) / boiling_point

                try:
                    transition = PhaseTransition(
                        temperature=boiling_point,
                        from_phase='s',
                        to_phase='g',
                        transition_type=TransitionType.SUBLIMATION,
                        delta_H_transition=delta_h,
                        delta_S_transition=delta_s,
                        reliability=0.7 if method == 'calculated' else 0.4,
                        calculation_method=method,
                        warning=None
                    )

                    logger.info(
                        f"Сублимация {formula}: T={boiling_point:.1f}K, "
                        f"ΔH={delta_h:.3f} кДж/моль, метод={method}"
                    )

                    return transition

                except ValueError as e:
                    logger.warning(f"Ошибка валидации перехода сублимации {formula}: {e}")

        # Если расчёт не удался, используем эвристику
        if 'l' in records_by_phase or 's' in records_by_phase:
            return self._create_heuristic_boiling_transition(boiling_point, formula)

        return None

    def _extract_melting_point(self, records: List[DatabaseRecord]) -> Optional[float]:
        """Извлечь температуру плавления из записей."""
        for record in records:
            if hasattr(record, 'MeltingPoint') and record.MeltingPoint > 0:
                return float(record.MeltingPoint)
        return None

    def _extract_boiling_point(self, records: List[DatabaseRecord]) -> Optional[float]:
        """Извлечь температуру кипения из записей."""
        for record in records:
            if hasattr(record, 'BoilingPoint') and record.BoilingPoint > 0:
                return float(record.BoilingPoint)
        return None

    def _select_record_for_temperature(
        self,
        records: List[DatabaseRecord],
        temperature: float
    ) -> Optional[DatabaseRecord]:
        """Выбрать запись с подходящим температурным диапазоном."""

        # Ищем запись, где температура попадает в диапазон
        for record in records:
            if (hasattr(record, 'Tmin') and hasattr(record, 'Tmax') and
                record.Tmin <= temperature <= record.Tmax):
                return record

        # Если нет точного попадания, выбираем ближайшую по Tmin
        if records:
            return min(records, key=lambda r: abs(r.Tmin - temperature) if hasattr(r, 'Tmin') else float('inf'))

        return None

    def calculate_transition_enthalpy(
        self,
        from_record: DatabaseRecord,
        to_record: DatabaseRecord,
        transition_temp: float
    ) -> Tuple[float, str]:
        """
        Рассчитать энтальпию перехода между фазами.

        КРИТИЧНО: Этот расчёт — ПРИБЛИЖЕНИЕ!
        H298 в БД — это энтальпии ОБРАЗОВАНИЯ, не абсолютные.

        Алгоритм:
        1. Рассчитать H(transition_temp) для обеих фаз
        2. ΔH_transition = H(to_phase) - H(from_phase)
        3. Валидировать физическую корректность
        4. При отрицательном значении → использовать эвристику

        Args:
            from_record: Запись БД для исходной фазы
            to_record: Запись БД для целевой фазы
            transition_temp: Температура перехода

        Returns:
            Tuple[float, str]: (ΔH в кДж/моль, метод расчёта)
        """

        logger.debug(
            f"Расчёт энтальпии перехода {from_record.formula} "
            f"{from_record.phase}→{to_record.phase} при T={transition_temp:.1f}K"
        )

        try:
            # Рассчитываем энтальпии на температуре перехода
            h_from = self.thermodynamic_calculator.calculate_properties(
                from_record, transition_temp
            ).enthalpy

            h_to = self.thermodynamic_calculator.calculate_properties(
                to_record, transition_temp
            ).enthalpy

            # Разница даёт приближённую энтальпию перехода
            delta_h = (h_to - h_from) / 1000  # Дж → кДж

            logger.debug(
                f"H({transition_temp:.1f}K, {from_record.phase}) = {h_from:.0f} Дж/моль, "
                f"H({transition_temp:.1f}K, {to_record.phase}) = {h_to:.0f} Дж/моль"
            )
            logger.debug(f"Расчётная ΔH_transition = {delta_h:.3f} кДж/моль")

            # Валидация физической корректности
            if delta_h > 0:
                logger.debug("Расчётная энтальпия перехода положительна - корректно")
                return delta_h, 'calculated'
            else:
                logger.warning(
                    f"Расчётная энтальпия перехода отрицательна: ΔH={delta_h:.3f} кДж/моль. "
                    f"Используем эвристическую оценку."
                )
                # Используем эвристику
                compound_type = self._classify_compound(from_record.formula)
                heuristic_delta_h = self.apply_heuristic_estimation(
                    'melting' if from_record.phase == 's' else 'boiling',
                    transition_temp,
                    compound_type
                )
                return heuristic_delta_h, 'heuristic'

        except Exception as e:
            logger.error(f"Ошибка при расчёте энтальпии перехода: {e}")
            # Используем эвристику при ошибке
            compound_type = self._classify_compound(from_record.formula)
            transition_type = 'melting' if from_record.phase == 's' else 'boiling'
            heuristic_delta_h = self.apply_heuristic_estimation(
                transition_type, transition_temp, compound_type
            )
            return heuristic_delta_h, 'heuristic'

    def apply_heuristic_estimation(
        self,
        transition_type: str,
        transition_temp: float,
        compound_type: str = "unknown"
    ) -> float:
        """
        Эвристическая оценка энтальпии перехода.

        Используется когда:
        - Нет данных для обеих фаз
        - Расчёт даёт нефизичный результат (отрицательный)

        Args:
            transition_type: Тип перехода ('melting', 'boiling', 'sublimation')
            transition_temp: Температура перехода (K)
            compound_type: Тип соединения

        Returns:
            float: Эвристическая оценка ΔH в кДж/моль
        """

        if transition_type == 'boiling':
            # Правило Трутона для кипения: ΔS_vap ≈ 85-88 Дж/(моль·K)
            delta_s_heuristic = 87.0  # Среднее значение
            delta_h = transition_temp * delta_s_heuristic / 1000  # → кДж/моль

            logger.debug(
                f"Эвристика кипения: ΔS ≈ {delta_s_heuristic} Дж/(моль·K), "
                f"ΔH ≈ {delta_h:.2f} кДж/моль"
            )

        elif transition_type == 'melting':
            # Правило Ричардса для плавления: ΔH_fusion ≈ T_melt × ΔS_fusion
            # ΔS_fusion зависит от типа вещества
            delta_s_estimates = {
                'metal': 10.0,      # Металлы
                'salt': 25.0,       # Соли
                'molecular': 15.0,  # Молекулярные
                'oxide': 20.0,      # Оксиды
                'unknown': 15.0     # По умолчанию
            }

            delta_s_heuristic = delta_s_estimates.get(compound_type, 15.0)
            delta_h = transition_temp * delta_s_heuristic / 1000  # → кДж/моль

            logger.debug(
                f"Эвристика плавления ({compound_type}): ΔS ≈ {delta_s_heuristic} Дж/(моль·K), "
                f"ΔH ≈ {delta_h:.2f} кДж/моль"
            )

        elif transition_type == 'sublimation':
            # Сублимация ≈ плавление + кипение
            melting_estimate = self.apply_heuristic_estimation('melting', transition_temp, compound_type)
            boiling_estimate = self.apply_heuristic_estimation('boiling', transition_temp, compound_type)
            delta_h = melting_estimate + boiling_estimate

            logger.debug(
                f"Эвристика сублимации: ΔH ≈ {delta_h:.2f} кДж/моль "
                f"(плавление: {melting_estimate:.2f} + кипение: {boiling_estimate:.2f})"
            )

        else:
            logger.warning(f"Неизвестный тип перехода: {transition_type}")
            delta_h = 10.0  # Значение по умолчанию

        return delta_h

    def _classify_compound(self, formula: str) -> str:
        """Классифицировать тип соединения по формуле."""

        # Простые эвристики для классификации
        formula_lower = formula.lower()

        # Металлы (простые вещества)
        if re.match(r'^[a-z]{1,2}$', formula_lower):
            return 'metal'

        # Оксиды
        if 'o' in formula_lower and not any(x in formula_lower for x in ['h', 'c', 'n', 's', 'p', 'cl', 'f', 'br', 'i']):
            return 'oxide'

        # Соли (содержат металлы и неметаллы)
        if re.search(r'[a-z]{1,2}[0-9]*', formula_lower):
            # Сложное определение соли
            elements = re.findall(r'[a-z]{1,2}', formula_lower)
            if len(elements) >= 2:
                return 'salt'

        # По умолчанию - молекулярное соединение
        return 'molecular'

    def _create_heuristic_melting_transition(
        self,
        melting_point: float,
        formula: str
    ) -> Optional[PhaseTransition]:
        """Создать переход плавления на основе эвристики."""

        compound_type = self._classify_compound(formula)
        delta_h = self.apply_heuristic_estimation('melting', melting_point, compound_type)
        delta_s = (delta_h * 1000) / melting_point

        try:
            transition = PhaseTransition(
                temperature=melting_point,
                from_phase='s',
                to_phase='l',
                transition_type=TransitionType.MELTING,
                delta_H_transition=delta_h,
                delta_S_transition=delta_s,
                reliability=0.4,  # Низкая надёжность для эвристики
                calculation_method='heuristic',
                warning=f"Эвристическая оценка энтальпии плавления для {compound_type}"
            )

            logger.warning(
                f"Используется эвристическая оценка плавления {formula}: "
                f"ΔH={delta_h:.2f} кДж/моль (надёжность: {transition.reliability:.1f})"
            )

            return transition

        except ValueError as e:
            logger.error(f"Ошибка создания эвристического перехода плавления {formula}: {e}")
            return None

    def _create_heuristic_boiling_transition(
        self,
        boiling_point: float,
        formula: str
    ) -> Optional[PhaseTransition]:
        """Создать переход кипения на основе эвристики."""

        delta_h = self.apply_heuristic_estimation('boiling', boiling_point)
        delta_s = (delta_h * 1000) / boiling_point

        try:
            transition = PhaseTransition(
                temperature=boiling_point,
                from_phase='l',  # По умолчанию предполагаем кипение
                to_phase='g',
                transition_type=TransitionType.BOILING,
                delta_H_transition=delta_h,
                delta_S_transition=delta_s,
                reliability=0.5,  # Средняя надёжность для правила Трутона
                calculation_method='heuristic',
                warning="Эвристическая оценка по правилу Трутона"
            )

            logger.warning(
                f"Используется эвристическая оценка кипения {formula}: "
                f"ΔH={delta_h:.2f} кДж/моль (надёжность: {transition.reliability:.1f})"
            )

            return transition

        except ValueError as e:
            logger.error(f"Ошибка создания эвристического перехода кипения {formula}: {e}")
            return None

    def validate_transition_consistency(
        self,
        transitions: List[PhaseTransition]
    ) -> List[str]:
        """
        Валидация термодинамической согласованности переходов.

        Проверки:
        1. ΔH > 0 (эндотермический процесс)
        2. ΔS > 0 (увеличение энтропии)
        3. Правило Трутона для кипения: 75 < ΔS_vap < 95 Дж/(моль·K)
        4. Разумные значения для плавления: 8 < ΔS_fusion < 35 Дж/(моль·K)

        Args:
            transitions: Список переходов для валидации

        Returns:
            List[str]: Список предупреждений о проблемах
        """

        warnings = []

        for transition in transitions:
            # Проверка знаков
            if transition.delta_H_transition <= 0:
                warnings.append(
                    f"Отрицательная энтальпия перехода {transition.transition_type.value}: "
                    f"ΔH={transition.delta_H_transition:.3f} кДж/моль"
                )

            if transition.delta_S_transition <= 0:
                warnings.append(
                    f"Отрицательная энтропия перехода {transition.transition_type.value}: "
                    f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K)"
                )

            # Правило Трутона для кипения
            if transition.transition_type == TransitionType.BOILING:
                if not (75 < transition.delta_S_transition < 95):
                    warnings.append(
                        f"Энтропия кипения выходит за пределы правила Трутона: "
                        f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K) (ожидается 75-95)"
                    )

            # Проверка для плавления
            if transition.transition_type == TransitionType.MELTING:
                if not (8 < transition.delta_S_transition < 35):
                    warnings.append(
                        f"Энтропия плавления выходит за типичные пределы: "
                        f"ΔS={transition.delta_S_transition:.1f} Дж/(моль·K) (ожидается 8-35)"
                    )

        return warnings

    def cache_transition_data(
        self,
        formula: str,
        transitions: List[PhaseTransition]
    ) -> None:
        """Кэширование рассчитанных данных переходов."""
        cache_key = f"{formula}_{len(transitions)}"
        self._transition_cache[cache_key] = transitions
        logger.debug(f"Закэшированы переходы для {formula}: {len(transitions)} переходов")

    def get_cached_transitions(self, formula: str, record_count: int = 0) -> Optional[List[PhaseTransition]]:
        """Получить закэшированные переходы."""
        cache_key = f"{formula}_{record_count}"
        return self._transition_cache.get(cache_key)

    def clear_cache(self) -> None:
        """Очистить кэш переходов."""
        self._transition_cache.clear()
        logger.info("Кэш переходов очищен")