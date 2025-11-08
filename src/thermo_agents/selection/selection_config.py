"""
Configuration module for optimal record selection.

Contains optimization parameters and scoring function weights.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class OptimizationConfig:
    """Configuration for optimal record selection algorithm."""

    # Scoring function weights (sum to 1.0)
    w1_record_count: float = 0.5  # Weight for minimizing number of records
    w2_data_quality: float = 0.3  # Weight for data quality (reliability class)
    w3_transition_coverage: float = 0.2  # Weight for phase transition coverage

    # Tolerance parameters
    gap_tolerance_k: float = 50.0  # Maximum allowed gap between records (K)
    transition_tolerance_k: float = (
        10.0  # Temperature tolerance for phase transitions (K)
    )
    coeffs_comparison_tolerance: float = (
        1e-6  # Tolerance for comparing Shomate coefficients
    )

    # Performance limits
    max_optimization_time_ms: float = 50.0  # Maximum time for optimization (ms)
    max_virtual_records: int = 100  # Maximum virtual records to cache

    # Validation thresholds
    min_score_improvement: float = (
        0.01  # Minimum score improvement to accept optimization
    )
    max_records_per_phase: int = 10  # Maximum records to consider per phase

    def __post_init__(self):
        """Validate configuration parameters."""
        # Check weight sum
        weight_sum = (
            self.w1_record_count + self.w2_data_quality + self.w3_transition_coverage
        )
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum}")

        # Check positive values
        if any(
            w <= 0
            for w in [
                self.w1_record_count,
                self.w2_data_quality,
                self.w3_transition_coverage,
            ]
        ):
            raise ValueError("All weights must be positive")

        # Check tolerances
        if self.gap_tolerance_k < 0:
            raise ValueError("Gap tolerance must be non-negative")

        if self.transition_tolerance_k <= 0:
            raise ValueError("Transition tolerance must be positive")

        if self.coeffs_comparison_tolerance <= 0:
            raise ValueError("Coefficients comparison tolerance must be positive")

    def get_score_weights(self) -> Tuple[float, float, float]:
        """Get scoring function weights as tuple."""
        return (self.w1_record_count, self.w2_data_quality, self.w3_transition_coverage)


@dataclass
class RecordGroup:
    """Group of contiguous records of the same phase."""

    phase: str
    tmin: float
    tmax: float
    records: list
    is_first_in_phase: bool = False

    @property
    def temperature_span(self) -> float:
        """Get temperature span of this group."""
        return self.tmax - self.tmin

    @property
    def record_count(self) -> int:
        """Get number of records in this group."""
        return len(self.records)

    @property
    def avg_reliability(self) -> float:
        """Get average reliability class of records in this group."""
        if not self.records:
            return 3.0  # Worst class

        reliability_values = []
        for record in self.records:
            # Handle both pandas Series and dict-like objects
            if hasattr(record, "ReliabilityClass"):
                reliability_values.append(record.ReliabilityClass)
            elif hasattr(record, "reliability_class"):
                reliability_values.append(record.reliability_class)
            elif "ReliabilityClass" in record:
                reliability_values.append(record["ReliabilityClass"])
            elif "reliability_class" in record:
                reliability_values.append(record["reliability_class"])

        return (
            sum(reliability_values) / len(reliability_values)
            if reliability_values
            else 3.0
        )


@dataclass
class OptimizationScore:
    """Score for evaluating record selection quality."""

    total_score: float
    record_count_score: float
    data_quality_score: float
    transition_coverage_score: float

    @classmethod
    def calculate(
        cls,
        n_records: int,
        avg_reliability: float,
        transition_coverage: float,
        config: OptimizationConfig,
    ) -> "OptimizationScore":
        """
        Calculate optimization score using the formula:
        Score = w1 * (1/N_records) + w2 * (Avg_reliability / 3) + w3 * Transition_coverage
        """
        w1, w2, w3 = config.get_score_weights()

        # Component scores
        record_count_score = 1.0 / max(n_records, 1)  # Avoid division by zero
        data_quality_score = (
            3.0 - avg_reliability
        ) / 3.0  # Lower reliability class is better
        transition_coverage_score = transition_coverage

        # Weighted sum
        total_score = (
            w1 * record_count_score
            + w2 * data_quality_score
            + w3 * transition_coverage_score
        )

        return cls(
            total_score=total_score,
            record_count_score=record_count_score,
            data_quality_score=data_quality_score,
            transition_coverage_score=transition_coverage_score,
        )

    def is_better_than(
        self, other: "OptimizationScore", min_improvement: float = 0.01
    ) -> bool:
        """Check if this score is significantly better than another."""
        improvement = (self.total_score - other.total_score) / other.total_score
        return improvement >= min_improvement
