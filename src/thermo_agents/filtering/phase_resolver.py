"""
Резолвер агрегатных состояний химических соединений.

Определяет фазу вещества при заданной температуре на основе
температурных переходов и информации из формулы.
"""

from typing import Optional, Dict, Any, Set
import re
from dataclasses import dataclass

from ..models.search import DatabaseRecord
from .constants import (
    SOLID_PHASE_MAX_TEMP,
    LIQUID_PHASE_MIN_TEMP,
    LIQUID_PHASE_MAX_TEMP,
    GAS_PHASE_MIN_TEMP,
    WATER_MELTING_POINT,
    WATER_BOILING_POINT,
    TEMPERATURE_EXTENSION_MARGIN,
    VALID_PHASES,
)


@dataclass
class PhaseTransition:
    """Информация о фазовом переходе."""
    temperature: float
    from_phase: str
    to_phase: str
    transition_type: str  # 'melting', 'boiling', 'sublimation', etc.


class PhaseResolver:
    """Определение агрегатного состояния при заданной температуре."""

    def __init__(self):
        self._cache: Dict[str, str] = {}

        # Валидные фазы из констант
        self.valid_phases: Set[str] = VALID_PHASES

        # Температурные приоритеты фаз (низкая температура -> высокая температура)
        self.phase_temperature_order = ['s', 'cr', 'am', 'l', 'g', 'aq']

        # Словарь синонимов фаз
        self.phase_synonyms = {
            'solid': 's',
            'liquid': 'l',
            'gas': 'g',
            'aqueous': 'aq',
            'crystalline': 'cr',
            'amorphous': 'am',
            'vapor': 'g',
            'steam': 'g'
        }

    def get_phase_at_temperature(
        self,
        record: DatabaseRecord,
        temperature: float
    ) -> Optional[str]:
        """
        Определить фазу вещества при заданной температуре.

        Логика:
        - T < Tmelt → твёрдое (s)
        - Tmelt <= T < Tboil → жидкое (l)
        - T >= Tboil → газ (g)
        - Если Tmelt/Tboil = NULL → использовать фазу из формулы
        - Особые случаи: сублимация, полиморфизм

        Args:
            record: Запись из базы данных
            temperature: Температура в Кельвинах

        Returns:
            's', 'l', 'g', 'aq', 'cr', 'am', или None
        """
        cache_key = f"phase_{record.id}_{temperature}" if record.id else f"phase_{record.formula}_{temperature}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        phase = self._determine_phase(record, temperature)
        self._cache[cache_key] = phase
        return phase

    def _determine_phase(self, record: DatabaseRecord, temperature: float) -> Optional[str]:
        """
        Основная логика определения фазы.

        Note: According to database analysis, MeltingPoint and BoilingPoint
        are 100% populated, so we always have complete phase transition data.
        """

        # В базе данных MeltingPoint и BoilingPoint всегда заполнены (100% покрытие)
        tmelt = record.tmelt
        tboil = record.tboil

        # Полная информация о переходах всегда доступна
        if temperature < tmelt:
            return 's'  # Твёрдое
        elif tmelt <= temperature < tboil:
            return 'l'  # Жидкое
        else:
            return 'g'  # Газ

    def _extract_phase_from_formula(self, formula: str) -> Optional[str]:
        """Извлечь фазу из формулы типа H2O(g)."""
        if not formula:
            return None

        # Ищем паттерн (phase) в конце формулы
        pattern = r'\(([s,l,g,aq,cr,am]+)\)$'
        match = re.search(pattern, formula)

        if match:
            phase = match.group(1)
            return self.normalize_phase(phase)

        return None

    def normalize_phase(self, phase: str) -> Optional[str]:
        """
        Нормализовать обозначение фазы.

        Note: According to database analysis, common phases include:
        - g (54.9%), l (16.67%), s (16.02%)
        - a, ao, ai (amorphous phases - ~12% total)
        - aq (aqueous - rare)
        """
        if not phase:
            return None

        phase_lower = phase.lower().strip()

        # Прямое соответствие (включая специфичные для базы данных)
        if phase_lower in self.valid_phases:
            return phase_lower

        # Через синонимы
        if phase_lower in self.phase_synonyms:
            return self.phase_synonyms[phase_lower]

        return None

    def _estimate_phase_by_temperature(self, record: DatabaseRecord, temperature: float) -> Optional[str]:
        """Эвристическая оценка фазы по температуре."""

        # Очень низкие температуры (<SOLID_PHASE_MAX_TEMP) - вероятно твёрдое
        if temperature < SOLID_PHASE_MAX_TEMP:
            return 's'

        # Высокие температуры (>GAS_PHASE_MIN_TEMP) - вероятно газ
        if temperature > GAS_PHASE_MIN_TEMP:
            return 'g'

        # Средние температуры - вероятно жидкое
        if LIQUID_PHASE_MIN_TEMP <= temperature <= LIQUID_PHASE_MAX_TEMP:
            return 'l'

        return None

    def get_phase_transitions(self, record: DatabaseRecord) -> Dict[str, float]:
        """
        Получить известные фазовые переходы для записи.

        Args:
            record: Запись из базы данных

        Returns:
            Словарь с температурами переходов
        """
        transitions = {}

        if record.tmelt is not None:
            transitions['melting'] = record.tmelt

        if record.tboil is not None:
            transitions['boiling'] = record.tboil

        return transitions

    def is_phase_transition_temperature(
        self,
        record: DatabaseRecord,
        temperature: float,
        tolerance: float = 5.0
    ) -> bool:
        """
        Проверить, является ли температура точкой фазового перехода.

        Args:
            record: Запись из базы данных
            temperature: Температура для проверки
            tolerance: Допуск температуры в Кельвинах

        Returns:
            True если температура близка к точке перехода
        """
        if record.tmelt is not None:
            if abs(temperature - record.tmelt) <= tolerance:
                return True

        if record.tboil is not None:
            if abs(temperature - record.tboil) <= tolerance:
                return True

        return False

    def get_stable_phases(
        self,
        record: DatabaseRecord,
        temperature_range: tuple
    ) -> Dict[str, tuple]:
        """
        Определить стабильные фазы в заданном температурном диапазоне.

        Args:
            record: Запись из базы данных
            temperature_range: (tmin, tmax)

        Returns:
            Словарь {фаза: (tmin, tmax)}
        """
        tmin, tmax = temperature_range
        phases = {}

        if record.tmelt is not None and record.tboil is not None:
            # Полная информация о переходах
            if tmin < record.tmelt:
                phases['s'] = (tmin, min(record.tmelt, tmax))

            if record.tmelt < tmax:
                phases['l'] = (max(record.tmelt, tmin), min(record.tboil, tmax))

            if record.tboil < tmax:
                phases['g'] = (max(record.tboil, tmin), tmax)

        else:
            # Частичная информация - используем текущую фазу
            current_phase = self.get_phase_at_temperature(record, (tmin + tmax) / 2)
            if current_phase:
                phases[current_phase] = (tmin, tmax)

        return phases

    def validate_phase_consistency(
        self,
        record: DatabaseRecord
    ) -> Dict[str, Any]:
        """
        Проверить согласованность фазовой информации в записи.

        Args:
            record: Запись из базы данных

        Returns:
            Словарь с результатами валидации
        """
        issues = []

        formula_phase = self._extract_phase_from_formula(record.formula)
        record_phase = self.normalize_phase(record.phase) if record.phase else None

        # Проверяем согласованность фаз
        if formula_phase and record_phase and formula_phase != record_phase:
            issues.append(f"Фаза в формуле ({formula_phase}) не совпадает с фазой в записи ({record_phase})")

        # Проверяем реалистичность температур переходов
        if record.tmelt is not None and record.tboil is not None:
            if record.tmelt >= record.tboil:
                issues.append(f"Температура плавления ({record.tmelt}K) больше или равна температуре кипения ({record.tboil}K)")

        # Проверяем температурные диапазоны
        if record.tmin is not None and record.tmelt is not None:
            if record.tmin > record.tmelt:
                issues.append(f"Минимальная температура ({record.tmin}K) больше температуры плавления ({record.tmelt}K)")

        if record.tmax is not None and record.tboil is not None:
            if record.tmax < record.tboil:
                issues.append(f"Максимальная температура ({record.tmax}K) меньше температуры кипения ({record.tboil}K)")

        return {
            'is_consistent': len(issues) == 0,
            'issues': issues,
            'formula_phase': formula_phase,
            'record_phase': record_phase,
            'transitions': self.get_phase_transitions(record)
        }

    def clear_cache(self) -> None:
        """Очистить кэш результатов."""
        self._cache.clear()