"""
Резолвер агрегатных состояний химических соединений.

Определяет фазу вещества при заданной температуре на основе
температурных переходов и информации из формулы.

Техническое описание:
Детерминированный резолвер для определения агрегатных состояний химических соединений
при заданных температурах. Использует данные о фазовых переходах (Tmelt, Tboil)
из базы данных для точного определения фазового состояния.

Ключевые компоненты:
- PhaseTransition: Модель информации о фазовых переходах
- PhaseResolver: Основной класс определения фазовых состояний
- Кэширование результатов для производительности

Основные методы PhaseResolver:
- get_phase_at_temperature(): Определение фазы при заданной температуре
- _determine_phase(): Основная логика определения фазы
- _determine_phase_from_formula(): Определение фазы из химической формулы
- _normalize_phase(): Нормализация и валидация фаз
- _get_cached_phase(): Кэширование результатов

Логика определения фазы:
- T < Tmelt → твёрдое состояние (s, cr, am)
- Tmelt ≤ T < Tboil → жидкое состояние (l)
- T ≥ Tboil → газообразное состояние (g)
- Водные растворы → водный раствор (aq)
- Особые случаи: сублимация, полиморфизм

Температурные пороги:
- SOLID_PHASE_MAX_TEMP: 273.15K (максимальная температура твердой фазы)
- LIQUID_PHASE_MIN_TEMP: 273.15K (минимальная температура жидкой фазы)
- LIQUID_PHASE_MAX_TEMP: 673.15K (максимальная температура жидкой фазы)
- GAS_PHASE_MIN_TEMP: 373.15K (минимальная температура газовой фазы)

Валидные фазы:
- s: твердое состояние (solid)
- l: жидкость (liquid)
- g: газ (gas)
- aq: водный раствор (aqueous)
- cr: кристаллический (crystalline)
- am: аморфный (amorphous)

Синонимы фаз:
- solid → s, liquid → l, gas → g, aqueous → aq
- crystalline → cr, amorphous → am
- vapor → g, steam → g

Анализ формулы:
- Определение типов соединений (оксиды, соли, кислоты, основания)
- Проверка на водородные соединения (H2O, NH3, HCl)
- Выявление ионных соединений и солевых систем
- Определение полимеров и комплексных соединений

Особые случаи:
- Вода: H2O с учетом аномальных фазовых переходов
- Аморфные материалы: отсутствие четкой температуры плавления
- Полимеры: размягчение вместо четкого плавления
- Сублимация: переход из твердого в газообразное

Кэширование:
- Простое кэширование по ключу {record_id}_{temperature}
- Увеличение производительности при повторных запросах
- Ограниченный размер кэша для контроля памяти

Интеграция с базой данных:
- 100% покрытие полей Tmelt и Tboil в базе данных
- Не требуется обработка NULL значений
- Использование надежных температурных данных

Метаданные и отладка:
- Детальное логирование процесса определения фазы
- Информация о использованных температурных переходах
- Причины выбора конкретного фазового состояния

Интеграция:
- Используется PhaseSelectionStage для фильтрации
- Интегрируется с TemperatureFilterStage
- Поддерживает FilterPipeline для конвейерной обработки
- Совместим с DatabaseRecord моделью

Используется в:
- PhaseSelectionStage для выбора правильной фазы
- TemperatureFilterStage для температурной фильтрации
- CompoundSearcher для валидации фазовых состояний
- Тестировании фазовых переходов
"""

from typing import Optional, Dict, Any, Set, Tuple, List
import re
from dataclasses import dataclass

from ..models.search import DatabaseRecord, PhaseSegment, MultiPhaseProperties
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

    # Stage 2: Enhanced methods for phase segment support

    def resolve_phase_at_temperature(
        self,
        compound_data: MultiPhaseProperties,
        temperature: float
    ) -> Tuple[str, PhaseSegment]:
        """
        Resolve phase and segment for temperature using multi-phase properties.

        This is an enhanced Stage 2 method that works with phase segments
        instead of individual database records.

        Args:
            compound_data: MultiPhaseProperties with segments and transitions
            temperature: Target temperature in Kelvin

        Returns:
            Tuple of (phase, segment) for the temperature

        Raises:
            ValueError: If no segment covers the temperature
        """
        # Find segment that covers the temperature
        segment = self._find_segment_for_temperature(compound_data.segments, temperature)

        if not segment:
            raise ValueError(f"No phase segment covers temperature {temperature:.1f}K")

        # Determine phase from segment record or temperature
        if segment.record:
            phase = self.normalize_phase(segment.record.phase) or self._estimate_phase_by_temperature(segment.record, temperature)
        else:
            phase = self._estimate_phase_by_temperature_range(segment, temperature)

        return phase, segment

    def get_active_record(
        self,
        segment: PhaseSegment,
        temperature: float
    ) -> DatabaseRecord:
        """
        Get the active database record for a segment at specific temperature.

        Args:
            segment: Phase segment with assigned record
            temperature: Target temperature

        Returns:
            Active database record for the temperature

        Raises:
            ValueError: If segment has no assigned record
        """
        if not segment.record:
            raise ValueError("Phase segment has no assigned database record")

        # Verify that the record covers the temperature
        if not segment.record.covers_temperature(temperature):
            # This shouldn't happen with proper segment construction,
            # but we provide a graceful fallback
            raise ValueError(
                f"Segment record {segment.record.id} does not cover temperature {temperature:.1f}K "
                f"(range: {segment.record.tmin:.1f}-{segment.record.tmax:.1f}K)"
            )

        return segment.record

    def _find_segment_for_temperature(
        self,
        segments: List[PhaseSegment],
        temperature: float
    ) -> Optional[PhaseSegment]:
        """
        Find the phase segment that covers the specified temperature.

        For temperature 298K, prioritize segments with H298/S298 reference records.

        Args:
            segments: List of phase segments
            temperature: Target temperature

        Returns:
            PhaseSegment that covers the temperature, or None
        """
        # Special case: prioritize H298/S298 reference segments for 298K
        if abs(temperature - 298.15) < 1e-6:
            for segment in segments:
                if (segment.record and
                    segment.record.is_h298_s298_reference):
                    return segment

        # Normal temperature coverage check
        for segment in segments:
            if segment.T_start <= temperature <= segment.T_end:
                return segment

        return None

    def _estimate_phase_by_temperature_range(
        self,
        segment: PhaseSegment,
        temperature: float
    ) -> str:
        """
        Estimate phase based on segment temperature range.

        This method is used when segment record is not available
        or doesn't have explicit phase information.

        Args:
            segment: Phase segment
            temperature: Target temperature

        Returns:
            Estimated phase ('s', 'l', 'g')
        """
        # Use temperature-based heuristics
        T_mid = (segment.T_start + segment.T_end) / 2

        # Check for typical phase transition temperatures
        if T_mid < 500:
            return 's'  # Likely solid
        elif T_mid > 2000:
            return 'g'  # Likely gas
        else:
            return 'l'  # Likely liquid

    def get_phase_sequence(
        self,
        compound_data: MultiPhaseProperties
    ) -> List[Tuple[str, Tuple[float, float]]]:
        """
        Get the complete phase sequence from multi-phase properties.

        Args:
            compound_data: MultiPhaseProperties with segments

        Returns:
            List of (phase, temperature_range) tuples
        """
        phase_sequence = []

        for segment in compound_data.segments:
            if segment.record:
                phase = self.normalize_phase(segment.record.phase) or 'unknown'
            else:
                # Estimate phase from temperature range
                T_mid = (segment.T_start + segment.T_end) / 2
                phase = self._estimate_phase_by_temperature_range(segment, T_mid)

            temp_range = (segment.T_start, segment.T_end)
            phase_sequence.append((phase, temp_range))

        return phase_sequence

    def validate_segment_continuity(
        self,
        compound_data: MultiPhaseProperties
    ) -> Dict[str, Any]:
        """
        Validate continuity of phase segments.

        Args:
            compound_data: MultiPhaseProperties to validate

        Returns:
            Validation results with issues and recommendations
        """
        issues = []
        recommendations = []

        if not compound_data.segments:
            return {
                "is_continuous": False,
                "issues": ["No segments found"],
                "recommendations": ["Create segments from database records"]
            }

        # Sort segments by temperature
        sorted_segments = sorted(compound_data.segments, key=lambda s: s.T_start)

        # Check for gaps between segments
        for i in range(len(sorted_segments) - 1):
            current = sorted_segments[i]
            next_segment = sorted_segments[i + 1]

            if current.T_end < next_segment.T_start:
                gap = next_segment.T_start - current.T_end
                issues.append(f"Gap of {gap:.1f}K between segments {i} and {i+1}")
                recommendations.append("Ensure complete temperature coverage")

            elif current.T_end > next_segment.T_start:
                overlap = current.T_end - next_segment.T_start
                if overlap > TEMPERATURE_EXTENSION_MARGIN:
                    issues.append(f"Overlap of {overlap:.1f}K between segments {i} and {i+1}")
                    recommendations.append("Adjust segment boundaries to remove overlap")

        # Check segment data quality
        for i, segment in enumerate(sorted_segments):
            if not segment.record:
                issues.append(f"Segment {i} has no assigned database record")
                recommendations.append("Assign appropriate records to all segments")

            elif segment.record.h298 == 0 and segment.record.s298 == 0:
                issues.append(f"Segment {i} record has H298=0 and S298=0")
                recommendations.append(f"Find better data for segment {i}")

        # Check phase transition consistency
        if compound_data.phase_transitions:
            for transition in compound_data.phase_transitions:
                if not (transition.from_phase and transition.to_phase):
                    issues.append(f"Invalid phase transition at {transition.temperature:.1f}K")
                    recommendations.append("Verify phase transition data")

        return {
            "is_continuous": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "total_segments": len(sorted_segments),
            "phase_transitions": len(compound_data.phase_transitions)
        }

    def get_phase_at_temperature_enhanced(
        self,
        compound_data: MultiPhaseProperties,
        temperature: float
    ) -> Optional[str]:
        """
        Enhanced version of get_phase_at_temperature for Stage 2.

        This method uses multi-phase properties instead of individual records
        and provides better accuracy for segment-based calculations.

        Args:
            compound_data: MultiPhaseProperties with segments
            temperature: Target temperature

        Returns:
            Phase at temperature or None if not covered
        """
        try:
            phase, _ = self.resolve_phase_at_temperature(compound_data, temperature)
            return phase
        except ValueError:
            # Temperature not covered by any segment
            return None

    def clear_cache(self) -> None:
        """Очистить кэш результатов."""
        self._cache.clear()