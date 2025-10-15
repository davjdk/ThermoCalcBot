"""
Pydantic models for search module results and data structures.

This module contains data models for search results, database records,
and filtering statistics used in the thermodynamic compounds search system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, validator


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

    @validator("reliability_class")
    def validate_reliability_class(cls, v):
        """Validate reliability class is in valid range."""
        if v is not None and (v < 0 or v > 9):
            raise ValueError("Reliability class must be between 0 and 9")
        return v

    @validator("tmin", "tmax")
    def validate_temperatures(cls, v):
        """Validate temperatures are positive."""
        if v is not None and v <= 0:
            raise ValueError("Temperatures must be positive")
        return v

    class Config:
        """Pydantic configuration."""

        from_attributes = True  # Allow creation from ORM objects
        extra = "allow"  # Allow additional fields from database
        populate_by_name = True  # Allow population by both field name and alias


class TemperatureRange(BaseModel):
    """Temperature range specification."""

    tmin: float = Field(..., description="Minimum temperature (K)")
    tmax: float = Field(..., description="Maximum temperature (K)")

    @validator("tmax")
    def validate_range(cls, v, values):
        """Validate temperature range is valid."""
        if "tmin" in values and v <= values["tmin"]:
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

    @validator("coverage_status")
    def validate_coverage_status(cls, v):
        """Validate coverage status is a valid enum value."""
        if v not in CoverageStatus:
            raise ValueError(f"Invalid coverage status: {v}")
        return v

    def add_warning(self, warning: str) -> None:
        """Add a warning to the search result."""
        self.warnings.append(warning)

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

    @validator("estimated_difficulty")
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
