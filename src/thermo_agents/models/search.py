"""
Pydantic models for search module results and data structures.

This module contains data models for search results, database records,
and filtering statistics used in the thermodynamic compounds search system.

Техническое описание:
Pydantic модели данных для модуля поиска термодинамических соединений.
Определяют структуру данных для результатов поиска, записей базы данных,
статистики фильтрации и метаданных в гибридной архитектуре v2.0.

Основные модели:

DatabaseRecord:
- Представляет запись из термодинамической базы данных
- Содержит все термодинамические свойства и метаданные
- Основана на анализе реальной структуры базы данных (316K записей)
- 100% покрытие полей Tmin, Tmax, H298, S298, f1-f6, MeltingPoint, BoilingPoint

Поля DatabaseRecord:
- id: Уникальный идентификатор записи
- formula: Химическая формула (может включать фазу в скобках)
- name/first_name/second_name: Наименования соединений
- phase: Фазовое состояние (s, l, g, a, ao, ai, aq)
- tmin/tmax: Температурный диапазон применимости
- h298/s298: Стандартные энтальпия и энтропия
- f1-f6: Коэффициенты теплоемкости (NASA полиномы)
- tmelt/tboil: Температуры фазовых переходов
- reliability_class: Класс надежности данных (1=высший)
- molecular_weight/cas_number: Дополнительные свойства

CompoundSearchResult:
- Результат поиска для одного химического соединения
- Содержит найденные записи и статистику фильтрации
- Включает метаданные поиска и предупреждения
- Поддерживает различные стратегии поиска

MultiPhaseSearchResult:
- Специализированный результат поиска всех фаз соединения
- Анализ температурного покрытия и фазовых переходов
- Определение покрытия стандартной температуры 298K
- Выявление пробелов и перекрытий в данных

SearchStatistics:
- Статистика результатов поиска соединения
- Распределение по фазам и температурам
- Метрики качества данных
- Информация о покрытии диапазонов

FilterStatistics:
- Детальная статистика по стадиям фильтрации
- Коэффициенты отсева на каждой стадии
- Время выполнения операций
- Причины отклонения записей

SearchPipeline:
- Трассинг операций поиска и фильтрации
- Последовательность примененных фильтров
- Статистика преобразования данных
- Метрики производительности

Вспомогательные модели:
- CoverageStatus: Статус покрытия (full/partial/none)
- Phase: Фазовые состояния (solid/liquid/gas/aqueous)
- TemperatureInterval: Температурные интервалы
- FilterOperation: Операции фильтрации
- SearchStrategy: Стратегии поиска

Валидация данных:
- Проверка диапазонов температур
- Валидация классов надежности
- Корректность химических формул
- Целостность термодинамических данных

Особенности реализации:
- Использование Pydantic для строгой типизации
- Автоматическая валидация данных
- Поддержка алиасов для совместимости с БД
- Сериализация/десериализация JSON
- Расширенные поля через extra="allow"

Константы и пороги:
- MIN_TEMPERATURE_K / MAX_TEMPERATURE_K: Диапазон температур
- HIGH_TEMP_THRESHOLD: Порог высоких температур
- MAX_RELIABILITY_CLASS: Максимальный класс надежности
- Температурные пороги для фазовых состояний

Методы моделей:
- covers_temperature(): Проверка покрытия температурного диапазона
- overlaps_with(): Проверка пересечения интервалов
- is_base_record(): Проверка базовой записи
- to_dict()/from_dict(): Сериализация

Интеграция:
- Используется CompoundSearcher для результатов поиска
- Интегрируется с FilterPipeline для статистики
- Поддерживает DatabaseConnector для данных из БД
- Совместим с остальными модулями системы

Используется в:
- CompoundSearcher для хранения результатов
- FilterPipeline для трейсинга операций
- ThermoOrchestrator для передачи данных
- ReactionAggregator для агрегации
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# Define constants locally to avoid circular import
MIN_TEMPERATURE_K = 0.0
MAX_TEMPERATURE_K = 150000.0
HIGH_TEMP_THRESHOLD = 50000.0
EXTREME_TEMP_THRESHOLD = 100000.0
MAX_RELIABILITY_CLASS = 3


class CoverageStatus(str, Enum):
    """Coverage status for compound search results."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class Phase(str, Enum):
    """Thermodynamic phases."""

    SOLID = "s"
    LIQUID = "l"
    GAS = "g"
    AQUEOUS = "aq"
    UNKNOWN = "unknown"


class DatabaseRecord(BaseModel):
    """
    Represents a single record from the thermodynamic database.

    This model maps to the compounds table structure with all
    thermodynamic properties and metadata based on actual database analysis.

    Note: Based on database analysis, Tmin, Tmax, H298, S298, f1-f6,
    MeltingPoint, and BoilingPoint are 100% populated in the database.
    """

    id: Optional[int] = Field(None, description="Database record ID")
    formula: str = Field(
        ..., description="Chemical formula (may include phase in parentheses)"
    )
    name: Optional[str] = Field(None, description="Compound name")
    first_name: Optional[str] = Field(None, description="First name from database (FirstName field)", alias="FirstName")
    second_name: Optional[str] = Field(None, description="Second name from database (SecondName field)", alias="SecondName")
    phase: Optional[str] = Field(
        None, description="Thermodynamic phase (s, l, g, a, ao, ai, aq)"
    )

    # Temperature ranges - always populated according to database analysis
    tmin: float = Field(..., description="Minimum temperature (K)", alias="Tmin")
    tmax: float = Field(..., description="Maximum temperature (K)", alias="Tmax")

    # Thermodynamic properties at standard conditions - always populated
    h298: float = Field(..., description="Enthalpy at 298K", alias="H298")
    s298: float = Field(..., description="Entropy at 298K", alias="S298")

    # Heat capacity coefficients (NASA polynomials) - always populated
    f1: float = Field(..., description="Heat capacity coefficient 1")
    f2: float = Field(..., description="Heat capacity coefficient 2")
    f3: float = Field(..., description="Heat capacity coefficient 3")
    f4: float = Field(..., description="Heat capacity coefficient 4")
    f5: float = Field(..., description="Heat capacity coefficient 5")
    f6: float = Field(..., description="Heat capacity coefficient 6")

    # Phase transition temperatures - always populated according to database analysis
    tmelt: float = Field(..., description="Melting point (K)", alias="MeltingPoint")
    tboil: float = Field(..., description="Boiling point (K)", alias="BoilingPoint")

    # Data quality indicators
    reliability_class: int = Field(
        ...,
        description="Reliability class (1=highest, 74.66% of data has class 1)",
        alias="ReliabilityClass",
    )

    # Additional properties that may exist in the database
    molecular_weight: Optional[float] = Field(None, description="Molecular weight")
    cas_number: Optional[str] = Field(None, description="CAS registry number")

    @field_validator("reliability_class")
    @classmethod
    def validate_reliability_class(cls, v):
        """Validate reliability class is in valid range."""
        if v is not None and (v < 0 or v > MAX_RELIABILITY_CLASS):
            raise ValueError(f"Reliability class must be between 0 and {MAX_RELIABILITY_CLASS}")
        return v

    @field_validator("tmin", "tmax")
    @classmethod
    def validate_temperatures(cls, v):
        """Validate temperatures are within valid range."""
        if v is not None and (v < MIN_TEMPERATURE_K or v > MAX_TEMPERATURE_K):
            raise ValueError(f"Temperatures must be between {MIN_TEMPERATURE_K} and {MAX_TEMPERATURE_K}K")
        return v

    class Config:
        """Pydantic configuration."""

        from_attributes = True  # Allow creation from ORM objects
        extra = "allow"  # Allow additional fields from database
        populate_by_name = True  # Allow population by both field name and alias

    # Backward compatibility properties for deprecated field names
    @property
    def MeltingPoint(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.tmelt

    @MeltingPoint.setter
    def MeltingPoint(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.tmelt = value

    @property
    def BoilingPoint(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.tboil

    @BoilingPoint.setter
    def BoilingPoint(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.tboil = value

    @property
    def Tmin(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.tmin

    @Tmin.setter
    def Tmin(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.tmin = value

    @property
    def Tmax(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.tmax

    @Tmax.setter
    def Tmax(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.tmax = value

    @property
    def H298(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.h298

    @H298.setter
    def H298(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.h298 = value

    @property
    def S298(self) -> Optional[float]:
        """Legacy property for backward compatibility."""
        return self.s298

    @S298.setter
    def S298(self, value: Optional[float]) -> None:
        """Legacy setter for backward compatibility."""
        self.s298 = value

    @property
    def ReliabilityClass(self) -> Optional[int]:
        """Legacy property for backward compatibility."""
        return self.reliability_class

    @ReliabilityClass.setter
    def ReliabilityClass(self, value: Optional[int]) -> None:
        """Legacy setter for backward compatibility."""
        self.reliability_class = value

    # Multi-phase calculation support methods (Stage 02)

    def is_base_record(self) -> bool:
        """
        Check if this record is a base record (contains H298≠0 or S298≠0).

        Base records have their own thermodynamic values at 298K.
        Records with H298=0 and S298=0 require accumulation from previous segments.

        Returns:
            True if H298≠0 or S298≠0
        """
        return abs(self.h298) > 1e-6 or abs(self.s298) > 1e-6

    def covers_temperature(self, T: float) -> bool:
        """
        Check if this record covers the specified temperature.

        Args:
            T: Temperature in Kelvin

        Returns:
            True if Tmin ≤ T ≤ Tmax
        """
        return self.tmin <= T <= self.tmax

    def has_phase_transition_at(self, T: float, tolerance: float = 1e-3) -> Optional[str]:
        """
        Check if there is a phase transition at the specified temperature.

        Args:
            T: Temperature in Kelvin
            tolerance: Tolerance for temperature comparison

        Returns:
            Transition type ("melting", "boiling") or None
        """
        if abs(T - self.tmelt) < tolerance and self.tmelt > 0:
            return "melting"
        if abs(T - self.tboil) < tolerance and self.tboil > 0:
            return "boiling"
        return None

    def get_transition_type(self, next_record: "DatabaseRecord") -> Optional[str]:
        """
        Determine the phase transition type between this record and the next one.

        Args:
            next_record: Next record by temperature

        Returns:
            Transition type ("s→l", "l→g", "s→g") or None
        """
        if self.phase == next_record.phase:
            return None  # No phase change

        # Check that records touch by temperature
        if abs(self.tmax - next_record.tmin) > 1e-3:
            return None  # No contact

        from_phase = (self.phase or "").lower()
        to_phase = (next_record.phase or "").lower()

        return f"{from_phase}→{to_phase}"

    def get_temperature_range(self) -> Tuple[float, float]:
        """
        Get the temperature range of this record.

        Returns:
            Tuple of (Tmin, Tmax)
        """
        return (self.tmin, self.tmax)

    def overlaps_with(self, other: "DatabaseRecord") -> bool:
        """
        Check if this record's temperature range overlaps with another record.

        Args:
            other: Another record to compare with

        Returns:
            True if temperature ranges overlap
        """
        return not (self.tmax < other.tmin or self.tmin > other.tmax)

    def has_extreme_temperatures(self) -> bool:
        """
        Check if this record has extreme temperature ranges.

        Returns:
            True if Tmax > EXTREME_TEMP_THRESHOLD
        """
        return self.tmax > EXTREME_TEMP_THRESHOLD

    def has_high_temperatures(self) -> bool:
        """
        Check if this record has high temperature ranges.

        Returns:
            True if Tmax > HIGH_TEMP_THRESHOLD
        """
        return self.tmax > HIGH_TEMP_THRESHOLD

    def get_temperature_warnings(self) -> List[str]:
        """
        Get warnings about temperature ranges for this record.

        Returns:
            List of warning messages about temperature ranges
        """
        warnings = []
        if self.has_extreme_temperatures():
            warnings.append(
                f"Экстремально высокая температура: {self.tmax:.0f}K "
                f"(>{EXTREME_TEMP_THRESHOLD:.0f}K). "
                "Данные могут быть теоретическими расчетами."
            )
        elif self.has_high_temperatures():
            warnings.append(
                f"Высокая температура: {self.tmax:.0f}K "
                f"(>{HIGH_TEMP_THRESHOLD:.0f}K). "
                "Обычно для газовой фазы при высоких температурах."
            )
        return warnings


class TemperatureRange(BaseModel):
    """Temperature range specification."""

    tmin: float = Field(..., description="Minimum temperature (K)")
    tmax: float = Field(..., description="Maximum temperature (K)")

    @field_validator("tmax")
    @classmethod
    def validate_range(cls, v, info):
        """Validate temperature range is valid."""
        if hasattr(info, 'data') and "tmin" in info.data and v <= info.data["tmin"]:
            raise ValueError("tmax must be greater than tmin")
        return v

    def contains(self, temperature: float) -> bool:
        """Check if temperature is within range."""
        return self.tmin <= temperature <= self.tmax

    def overlaps_with(self, other: "TemperatureRange") -> bool:
        """Check if this range overlaps with another."""
        return not (self.tmax < other.tmin or self.tmin > other.tmax)


class SearchStatistics(BaseModel):
    """Statistics for compound search results."""

    total_records: int = Field(0, description="Total records found")
    unique_phases: int = Field(0, description="Number of unique phases")
    temperature_coverage: Optional[float] = Field(
        None, description="Temperature coverage fraction"
    )
    avg_reliability: Optional[float] = Field(
        None, description="Average reliability class"
    )

    # Temperature statistics
    min_temperature: Optional[float] = Field(
        None, description="Minimum temperature in records"
    )
    max_temperature: Optional[float] = Field(
        None, description="Maximum temperature in records"
    )
    avg_temperature_range: Optional[float] = Field(
        None, description="Average temperature range"
    )

    # Phase distribution
    phase_distribution: Dict[str, int] = Field(
        default_factory=dict, description="Count of records per phase"
    )

    # Reliability distribution
    reliability_distribution: Dict[int, int] = Field(
        default_factory=dict, description="Count of records per reliability class"
    )


class CompoundSearchResult(BaseModel):
    """
    Result of searching for a single chemical compound.

    Contains the found records, search statistics, and metadata
    about the search operation.
    """

    compound_formula: str = Field(..., description="Requested compound formula")
    records_found: List[DatabaseRecord] = Field(
        default_factory=list, description="Database records matching the search"
    )
    search_parameters: Optional[Dict[str, Any]] = Field(
        None, description="Parameters used in search"
    )

    # Stage 1: Enhanced temperature range fields
    full_calculation_range: Optional[Tuple[float, float]] = Field(
        None, description="Full calculation temperature range (Stage 1)"
    )
    original_user_range: Optional[Tuple[float, float]] = Field(
        None, description="Original user-requested temperature range (Stage 1)"
    )
    stage1_mode: bool = Field(
        False, description="Whether Stage 1 enhanced search was used"
    )

    # Results analysis
    coverage_status: CoverageStatus = Field(
        CoverageStatus.UNKNOWN, description="Coverage status"
    )
    filter_statistics: Optional[SearchStatistics] = Field(
        None, description="Search statistics"
    )
    warnings: List[str] = Field(default_factory=list, description="Search warnings")

    # Metadata
    search_timestamp: datetime = Field(
        default_factory=datetime.now, description="When search was performed"
    )
    execution_time_ms: Optional[float] = Field(
        None, description="Search execution time in milliseconds"
    )

    @field_validator("coverage_status")
    @classmethod
    def validate_coverage_status(cls, v):
        """Validate coverage status is a valid enum value."""
        if v not in CoverageStatus:
            raise ValueError(f"Invalid coverage status: {v}")
        return v

    def add_warning(self, warning: str) -> None:
        """Add a warning to the search result."""
        self.warnings.append(warning)

    def collect_temperature_warnings(self) -> None:
        """
        Collect temperature warnings from all records in this search result.

        This method iterates through all found records and adds any
        temperature-related warnings to the warnings list.
        """
        temp_warnings_counts = {}

        for record in self.records_found:
            record_warnings = record.get_temperature_warnings()
            for warning in record_warnings:
                # Count duplicate warnings to avoid repetition
                if warning not in temp_warnings_counts:
                    temp_warnings_counts[warning] = 0
                temp_warnings_counts[warning] += 1

        # Add unique warnings with counts
        for warning, count in temp_warnings_counts.items():
            if count > 1:
                warning_with_count = f"{warning} ({count} записей)"
                self.add_warning(warning_with_count)
            else:
                self.add_warning(warning)

    def has_records(self) -> bool:
        """Check if any records were found."""
        return len(self.records_found) > 0

    def get_unique_phases(self) -> List[str]:
        """Get list of unique phases in found records."""
        phases = set()
        for record in self.records_found:
            if record.phase:
                phases.add(record.phase)
        return sorted(list(phases))

    def get_temperature_range(self) -> Optional[TemperatureRange]:
        """Get combined temperature range from all records."""
        if not self.records_found:
            return None

        valid_temps = [
            (r.tmin, r.tmax)
            for r in self.records_found
            if r.tmin is not None and r.tmax is not None
        ]

        if not valid_temps:
            return None

        min_temp = min(t[0] for t in valid_temps)
        max_temp = max(t[1] for t in valid_temps)

        return TemperatureRange(tmin=min_temp, tmax=max_temp)

    def get_best_record(self) -> Optional[DatabaseRecord]:
        """Get the best record based on reliability class."""
        if not self.records_found:
            return None

        # Sort by reliability class (1 is best), then by temperature range width
        sorted_records = sorted(
            self.records_found,
            key=lambda r: (
                r.reliability_class if r.reliability_class is not None else 999,
                -(r.tmax - r.tmin) if r.tmax and r.tmin else 0,
            ),
        )

        return sorted_records[0]

    # Stage 1: Enhanced temperature range methods

    def get_effective_temperature_range(self) -> Optional[Tuple[float, float]]:
        """
        Get the effective temperature range used for calculations.

        In Stage 1 mode, returns the full calculation range.
        Otherwise, returns the original temperature range from search parameters.

        Returns:
            Effective temperature range or None if not available
        """
        if self.stage1_mode and self.full_calculation_range:
            return self.full_calculation_range

        # Try to get from search parameters
        if self.search_parameters and "temperature_range" in self.search_parameters:
            return self.search_parameters["temperature_range"]

        return None

    def has_range_expansion(self) -> bool:
        """
        Check if Stage 1 expanded the temperature range beyond user request.

        Returns:
            True if calculation range is wider than original user range
        """
        if not self.stage1_mode:
            return False

        if not self.original_user_range or not self.full_calculation_range:
            return False

        return (
            self.full_calculation_range[0] < self.original_user_range[0] or
            self.full_calculation_range[1] > self.original_user_range[1]
        )

    def get_range_expansion_info(self) -> Dict[str, Any]:
        """
        Get information about temperature range expansion in Stage 1.

        Returns:
            Dictionary with expansion details
        """
        if not self.stage1_mode:
            return {"expanded": False, "reason": "Stage 1 mode not enabled"}

        if not self.original_user_range or not self.full_calculation_range:
            return {"expanded": False, "reason": "Missing range information"}

        original_width = self.original_user_range[1] - self.original_user_range[0]
        expanded_width = self.full_calculation_range[1] - self.full_calculation_range[0]

        return {
            "expanded": self.has_range_expansion(),
            "original_range": self.original_user_range,
            "full_range": self.full_calculation_range,
            "original_width": original_width,
            "expanded_width": expanded_width,
            "expansion_factor": expanded_width / original_width if original_width > 0 else 1.0,
            "records_in_original_range": self._count_records_in_range(self.original_user_range),
            "records_in_full_range": len(self.records_found)
        }

    def _count_records_in_range(self, temp_range: Tuple[float, float]) -> int:
        """Count records that overlap with the given temperature range."""
        if not temp_range:
            return 0

        return sum(
            1 for record in self.records_found
            if not (temp_range[1] < record.tmin or temp_range[0] > record.tmax)
        )

    def set_stage1_ranges(
        self,
        full_calculation_range: Tuple[float, float],
        original_user_range: Optional[Tuple[float, float]] = None
    ) -> None:
        """
        Set Stage 1 temperature ranges.

        Args:
            full_calculation_range: Full calculation temperature range
            original_user_range: Original user-requested temperature range
        """
        self.full_calculation_range = full_calculation_range
        self.original_user_range = original_user_range
        self.stage1_mode = True

    def get_stage1_summary(self) -> Dict[str, Any]:
        """
        Get a summary of Stage 1 enhancements.

        Returns:
            Dictionary with Stage 1 summary information
        """
        summary = {
            "stage1_enabled": self.stage1_mode,
            "records_found": len(self.records_found),
            "execution_time_ms": self.execution_time_ms
        }

        if self.stage1_mode:
            summary.update({
                "original_user_range": self.original_user_range,
                "full_calculation_range": self.full_calculation_range,
                "range_expansion": self.get_range_expansion_info()
            })

        return summary


class SearchStrategy(BaseModel):
    """Search strategy recommendations for compound lookup."""

    formula: str = Field(..., description="Target compound formula")
    search_strategies: List[str] = Field(
        default_factory=list, description="Recommended search strategies"
    )
    estimated_difficulty: str = Field(
        "medium", description="Estimated search difficulty"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Additional recommendations"
    )

    @field_validator("estimated_difficulty")
    @classmethod
    def validate_difficulty(cls, v):
        """Validate difficulty level."""
        if v not in ["easy", "medium", "hard"]:
            raise ValueError("Difficulty must be easy, medium, or hard")
        return v


class FilterOperation(BaseModel):
    """Represents a filter operation in the search pipeline."""

    operation_type: str = Field(..., description="Type of filter operation")
    input_count: int = Field(..., description="Number of records before filtering")
    output_count: int = Field(..., description="Number of records after filtering")
    filter_criteria: Optional[Dict[str, Any]] = Field(
        None, description="Filter criteria used"
    )
    execution_time_ms: Optional[float] = Field(
        None, description="Filter execution time"
    )

    @property
    def reduction_rate(self) -> float:
        """Calculate the reduction rate of this filter."""
        if self.input_count == 0:
            return 0.0
        return (self.input_count - self.output_count) / self.input_count


class SearchPipeline(BaseModel):
    """Complete search pipeline with all filter operations."""

    initial_query: str = Field(..., description="Initial search query")
    initial_results: int = Field(0, description="Number of initial results")
    final_results: int = Field(0, description="Number of final results")
    operations: List[FilterOperation] = Field(
        default_factory=list, description="Filter operations performed"
    )
    total_time_ms: Optional[float] = Field(
        None, description="Total pipeline execution time"
    )

    @property
    def total_reduction(self) -> float:
        """Calculate total reduction rate."""
        if self.initial_results == 0:
            return 0.0
        return (self.initial_results - self.final_results) / self.initial_results

    def add_operation(self, operation: FilterOperation) -> None:
        """Add a filter operation to the pipeline."""
        self.operations.append(operation)

    def get_operation_by_type(self, operation_type: str) -> Optional[FilterOperation]:
        """Get a specific filter operation by type."""
        for op in self.operations:
            if op.operation_type == operation_type:
                return op
        return None


class TransitionType(str, Enum):
    """Types of phase transitions."""

    MELTING = "melting"          # s → l
    BOILING = "boiling"          # l → g
    SUBLIMATION = "sublimation"  # s → g
    UNKNOWN = "unknown"


class PhaseSegment(BaseModel):
    """Calculation segment within a single database record."""

    record: DatabaseRecord = Field(..., description="Database record for this segment")
    T_start: float = Field(..., description="Start temperature of segment, K")
    T_end: float = Field(..., description="End temperature of segment, K")
    H_start: float = Field(..., description="Enthalpy at segment start, J/mol")
    S_start: float = Field(..., description="Entropy at segment start, J/(mol·K)")
    delta_H: float = Field(..., description="Enthalpy change in segment, J/mol")
    delta_S: float = Field(..., description="Entropy change in segment, J/(mol·K)")
    is_transition_boundary: bool = Field(
        False,
        description="Whether segment ends with a phase transition"
    )

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True

    @field_validator("T_end")
    @classmethod
    def validate_temperature_range(cls, v, info):
        """Validate that T_end is greater than T_start."""
        if hasattr(info, 'data') and "T_start" in info.data and v <= info.data["T_start"]:
            raise ValueError("T_end must be greater than T_start")
        return v

    @field_validator("T_start", "T_end")
    @classmethod
    def validate_temperatures_within_record(cls, v, info):
        """Validate temperatures are within record range."""
        if hasattr(info, 'data') and "record" in info.data and info.data["record"]:
            record = info.data["record"]
            if v < record.tmin or v > record.tmax:
                raise ValueError(f"Temperature {v}K is outside record range [{record.tmin}, {record.tmax}]K")
        return v

    @classmethod
    def from_database_record(cls, record: 'DatabaseRecord') -> 'PhaseSegment':
        """
        Create PhaseSegment from DatabaseRecord for multi-phase calculations.

        Args:
            record: DatabaseRecord with thermodynamic data

        Returns:
            PhaseSegment initialized from record
        """
        return cls(
            record=record,
            T_start=record.tmin or 298.15,
            T_end=record.tmax or 3000.0,
            H_start=record.h298,
            S_start=record.s298,
            delta_H=0.0,  # Will be calculated by integration
            delta_S=0.0,  # Will be calculated by integration
            is_transition_boundary=False
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "formula": self.record.formula,
            "phase": self.record.phase,
            "T_range": [self.T_start, self.T_end],
            "H_range": [self.H_start, self.H_start + self.delta_H],
            "S_range": [self.S_start, self.S_start + self.delta_S],
            "is_transition": self.is_transition_boundary,
        }


class PhaseTransition(BaseModel):
    """Information about a phase transition."""

    temperature: float = Field(..., description="Transition temperature, K")
    from_phase: str = Field(..., description="Source phase (s/l/g)")
    to_phase: str = Field(..., description="Target phase (s/l/g)")
    transition_type: TransitionType = Field(
        TransitionType.UNKNOWN,
        description="Transition type"
    )
    delta_H_transition: float = Field(0.0, description="Enthalpy of transition, kJ/mol")
    delta_S_transition: float = Field(0.0, description="Entropy of transition, J/(mol·K)")

    @model_validator(mode='before')
    @classmethod
    def determine_transition_type(cls, data):
        """Auto-determine transition type from phases."""
        # Handle dict input
        if isinstance(data, dict):
            from_p = data.get("from_phase", "").lower()
            to_p = data.get("to_phase", "").lower()
            transition_type = data.get("transition_type", TransitionType.UNKNOWN)

            # Auto-detect if not explicitly set or set to UNKNOWN
            if not transition_type or transition_type == TransitionType.UNKNOWN:
                if from_p == "s" and to_p == "l":
                    data["transition_type"] = TransitionType.MELTING
                elif from_p == "l" and to_p == "g":
                    data["transition_type"] = TransitionType.BOILING
                elif from_p == "s" and to_p == "g":
                    data["transition_type"] = TransitionType.SUBLIMATION
                else:
                    data["transition_type"] = TransitionType.UNKNOWN

        return data

    def to_dict(self) -> dict:
        """Serialize for logging."""
        return {
            "T": self.temperature,
            "transition": f"{self.from_phase}→{self.to_phase}",
            "type": self.transition_type.value,
            "ΔH": self.delta_H_transition,
            "ΔS": self.delta_S_transition,
        }


class MultiPhaseProperties(BaseModel):
    """Result of multi-phase thermodynamic calculation."""

    T_target: float = Field(..., description="Target calculation temperature, K")

    # Final thermodynamic properties
    H_final: float = Field(..., description="Enthalpy at T_target, J/mol")
    S_final: float = Field(..., description="Entropy at T_target, J/(mol·K)")
    G_final: float = Field(..., description="Gibbs energy at T_target, J/mol")
    Cp_final: float = Field(..., description="Heat capacity at T_target, J/(mol·K)")

    # Calculation metadata
    segments: List[PhaseSegment] = Field(
        default_factory=list,
        description="All calculation segments"
    )
    phase_transitions: List[PhaseTransition] = Field(
        default_factory=list,
        description="All phase transitions"
    )

    # Calculation trajectory (for graphs)
    temperature_path: List[float] = Field(
        default_factory=list,
        description="Temperature points of trajectory"
    )
    H_path: List[float] = Field(
        default_factory=list,
        description="Enthalpy along trajectory, J/mol"
    )
    S_path: List[float] = Field(
        default_factory=list,
        description="Entropy along trajectory, J/(mol·K)"
    )

    # Warnings
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about coverage gaps, overlaps, etc."
    )

    @field_validator("segments")
    @classmethod
    def validate_segments_sorted(cls, v):
        """Validate segments are sorted by temperature."""
        for i in range(len(v) - 1):
            if v[i].T_end > v[i+1].T_start:
                raise ValueError("Segments must be sorted by temperature")
        return v

    def to_dict(self) -> dict:
        """Serialize result."""
        return {
            "T_target": self.T_target,
            "thermodynamic_properties": {
                "H": self.H_final / 1000,  # kJ/mol
                "S": self.S_final,
                "G": self.G_final / 1000,  # kJ/mol
                "Cp": self.Cp_final,
            },
            "segments_count": len(self.segments),
            "transitions_count": len(self.phase_transitions),
            "warnings": self.warnings,
        }

    @property
    def has_phase_transitions(self) -> bool:
        """Check if phase transitions exist."""
        return len(self.phase_transitions) > 0

    @property
    def segment_count(self) -> int:
        """Get number of segments."""
        return len(self.segments)

    @property
    def phase_sequence(self) -> str:
        """Get phase sequence as string."""
        if not self.segments:
            return "unknown"

        phases = []
        for segment in self.segments:
            if segment.record.phase:
                phases.append(segment.record.phase)

        # Remove consecutive duplicates
        unique_phases = []
        for phase in phases:
            if not unique_phases or phase != unique_phases[-1]:
                unique_phases.append(phase)

        return " → ".join(unique_phases) if unique_phases else "unknown"


class MultiPhaseSearchResult(BaseModel):
    """Result of searching all phases of a compound with multi-phase coverage."""

    compound_formula: str = Field(..., description="Chemical formula of the compound")
    records: List[DatabaseRecord] = Field(
        default_factory=list,
        description="All found records, sorted by Tmin"
    )

    # Temperature boundaries
    coverage_start: float = Field(..., description="Start of coverage, K")
    coverage_end: float = Field(..., description="End of coverage, K")
    covers_298K: bool = Field(..., description="Whether range covers 298K")

    # Phase transitions
    tmelt: Optional[float] = Field(None, description="Melting temperature, K")
    tboil: Optional[float] = Field(None, description="Boiling temperature, K")

    # Metadata
    phase_count: int = Field(..., description="Number of different phases")
    has_gas_phase: bool = Field(False, description="Whether gas phase exists")

    # Warnings
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings about gaps, overlaps, etc."
    )

    @property
    def is_complete(self) -> bool:
        """Check if data is complete (no gaps, covers 298K)."""
        return self.covers_298K and len(self.warnings) == 0

    @property
    def phase_sequence(self) -> str:
        """Get phase sequence string (s→l→g)."""
        phases = [rec.phase for rec in self.records if rec.phase]
        return " → ".join(phases)

    def to_dict(self) -> dict:
        """Serialize result."""
        return {
            "formula": self.compound_formula,
            "coverage": [self.coverage_start, self.coverage_end],
            "covers_298K": self.covers_298K,
            "transitions": {
                "melting": self.tmelt,
                "boiling": self.tboil
            },
            "phases": self.phase_sequence,
            "records_count": len(self.records),
            "warnings": self.warnings
        }


class RecordTransition(BaseModel):
    """Information about transition between two database records."""

    from_record_id: int = Field(..., description="ID of source record")
    to_record_id: int = Field(..., description="ID of target record")
    transition_temperature: float = Field(..., description="Temperature of transition, K")

    # Corrections needed for continuity
    delta_H_correction: float = Field(0.0, description="Enthalpy correction for continuity, J/mol")
    delta_S_correction: float = Field(0.0, description="Entropy correction for continuity, J/(mol·K)")

    # Transition metadata
    is_continuous: bool = Field(True, description="Whether transition is naturally continuous")
    warning: Optional[str] = Field(None, description="Warning about transition quality")

    def to_dict(self) -> dict:
        """Serialize transition info."""
        return {
            "from_id": self.from_record_id,
            "to_id": self.to_record_id,
            "T": self.transition_temperature,
            "ΔH_correction": self.delta_H_correction,
            "ΔS_correction": self.delta_S_correction,
            "continuous": self.is_continuous,
            "warning": self.warning
        }


class MultiPhaseCompoundData(BaseModel):
    """
    Container for managing multiple database records of a single compound.

    This class serves as the central data structure for Stage 3, providing
    seamless access to multiple records within phase segments and managing
    transitions between them.
    """

    # Basic compound information
    compound_formula: str = Field(..., description="Chemical formula of the compound")

    # All records for this compound
    all_records: List[DatabaseRecord] = Field(
        default_factory=list,
        description="All database records for this compound"
    )

    # Phase segments (from Stage 2)
    phase_segments: List[PhaseSegment] = Field(
        default_factory=list,
        description="Phase segments for multi-phase calculations"
    )

    # Stage 3: Record transition management
    record_transitions: Dict[Tuple[int, int], RecordTransition] = Field(
        default_factory=dict,
        description="Precomputed transitions between records (from_id, to_id) → transition"
    )

    active_records_cache: Dict[float, DatabaseRecord] = Field(
        default_factory=dict,
        description="Cache of active records by temperature"
    )

    # Metadata
    total_temperature_range: Optional[Tuple[float, float]] = Field(
        None,
        description="Overall temperature coverage [Tmin, Tmax]"
    )
    has_multiple_records_per_segment: bool = Field(
        False,
        description="Whether any segment has multiple records"
    )

    class Config:
        """Pydantic configuration."""
        arbitrary_types_allowed = True

    def __post_init__(self) -> None:
        """Post-initialization setup."""
        if self.all_records and not self.total_temperature_range:
            self._calculate_total_range()

        # Check for multiple records per segment
        self.has_multiple_records_per_segment = self._check_multiple_records()

    def get_record_at_temperature(self, temperature: float) -> DatabaseRecord:
        """
        Get the appropriate database record for the specified temperature.

        This method implements the core Stage 3 logic for selecting records
        within phase segments based on temperature.

        Args:
            temperature: Temperature in Kelvin

        Returns:
            DatabaseRecord that covers the specified temperature

        Raises:
            ValueError: If no record covers the specified temperature
        """
        # Check cache first
        if temperature in self.active_records_cache:
            return self.active_records_cache[temperature]

        # Find appropriate phase segment
        target_segment = None
        for segment in self.phase_segments:
            if segment.T_start <= temperature <= segment.T_end:
                target_segment = segment
                break

        if not target_segment:
            raise ValueError(
                f"No phase segment covers temperature {temperature}K. "
                f"Available range: {self.get_available_range()}"
            )

        # Find record within segment
        # For now, segments contain one record each, but this prepares for multiple records
        selected_record = target_segment.record

        # Cache the result
        self.active_records_cache[temperature] = selected_record

        return selected_record

    def get_transition_between_records(self, from_id: int, to_id: int) -> Optional[RecordTransition]:
        """
        Get precomputed transition information between two records.

        Args:
            from_id: ID of source record
            to_id: ID of target record

        Returns:
            RecordTransition if available, None otherwise
        """
        return self.record_transitions.get((from_id, to_id))

    def precompute_transitions(self) -> None:
        """
        Precompute all possible transitions between records.

        This method analyzes records within each phase segment and computes
        the corrections needed to maintain thermodynamic continuity.
        """
        from ..calculations.record_transition_manager import RecordTransitionManager

        transition_manager = RecordTransitionManager()

        # Group records by phase segment
        segments_records = {}
        for segment in self.phase_segments:
            segment_key = f"{segment.record.phase}_{segment.T_start}_{segment.T_end}"
            if segment_key not in segments_records:
                segments_records[segment_key] = []
            segments_records[segment_key].append(segment.record)

        # Compute transitions within each segment
        for segment_key, records in segments_records.items():
            if len(records) < 2:
                continue  # No transitions needed for single record

            # Sort records by temperature
            sorted_records = sorted(records, key=lambda r: r.tmin)

            # Compute transitions between consecutive records
            for i in range(len(sorted_records) - 1):
                from_record = sorted_records[i]
                to_record = sorted_records[i + 1]

                # Find transition temperature (boundary between records)
                transition_temp = (from_record.tmax + to_record.tmin) / 2

                # Compute transition corrections
                correction = transition_manager.calculate_transition_corrections(
                    from_record, to_record, transition_temp
                )

                # Create and store transition
                transition = RecordTransition(
                    from_record_id=from_record.id or 0,
                    to_record_id=to_record.id or 0,
                    transition_temperature=transition_temp,
                    delta_H_correction=correction.get("delta_H", 0.0),
                    delta_S_correction=correction.get("delta_S", 0.0),
                    is_continuous=abs(correction.get("delta_H", 0.0)) < 1e-6,
                    warning=correction.get("warning")
                )

                self.record_transitions[(from_record.id or 0, to_record.id or 0)] = transition

    def get_available_range(self) -> Tuple[float, float]:
        """
        Get the total available temperature range.

        Returns:
            Tuple of (Tmin, Tmax) for complete coverage
        """
        if self.total_temperature_range:
            return self.total_temperature_range

        if not self.phase_segments:
            return (0.0, 0.0)

        t_min = min(seg.T_start for seg in self.phase_segments)
        t_max = max(seg.T_end for seg in self.phase_segments)

        return (t_min, t_max)

    def get_records_in_range(self, t_start: float, t_end: float) -> List[DatabaseRecord]:
        """
        Get all records that overlap with the specified temperature range.

        Args:
            t_start: Start temperature
            t_end: End temperature

        Returns:
            List of DatabaseRecord overlapping with the range
        """
        overlapping_records = []

        for record in self.all_records:
            if not (t_end < record.tmin or t_start > record.tmax):
                overlapping_records.append(record)

        return overlapping_records

    def get_segments_in_range(self, t_start: float, t_end: float) -> List[PhaseSegment]:
        """
        Get all phase segments that overlap with the specified temperature range.

        Args:
            t_start: Start temperature
            t_end: End temperature

        Returns:
            List of PhaseSegment overlapping with the range
        """
        overlapping_segments = []

        for segment in self.phase_segments:
            if not (t_end < segment.T_start or t_start > segment.T_end):
                overlapping_segments.append(segment)

        return overlapping_segments

    def _calculate_total_range(self) -> None:
        """Calculate the total temperature range from all records."""
        if not self.all_records:
            return

        t_min = min(record.tmin for record in self.all_records)
        t_max = max(record.tmax for record in self.all_records)

        self.total_temperature_range = (t_min, t_max)

    def _check_multiple_records(self) -> bool:
        """Check if any phase segment contains multiple records."""
        # Group by phase
        phase_groups = {}
        for record in self.all_records:
            phase = record.phase or "unknown"
            if phase not in phase_groups:
                phase_groups[phase] = []
            phase_groups[phase].append(record)

        # Check if any phase has multiple records
        for phase, records in phase_groups.items():
            if len(records) > 1:
                # Check if records have overlapping temperature ranges
                sorted_records = sorted(records, key=lambda r: r.tmin)
                for i in range(len(sorted_records) - 1):
                    current = sorted_records[i]
                    next_record = sorted_records[i + 1]

                    # If records touch or overlap, we have multiple records per segment
                    if next_record.tmin <= current.tmax + 1e-6:  # Small tolerance
                        return True

        return False

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "formula": self.compound_formula,
            "records_count": len(self.all_records),
            "segments_count": len(self.phase_segments),
            "temperature_range": self.get_available_range(),
            "has_multiple_records": self.has_multiple_records_per_segment,
            "transitions_count": len(self.record_transitions),
            "phase_sequence": self.phase_segments[0].record.phase if self.phase_segments else "unknown"
        }
