"""
Optimal record selection module for thermodynamic data.

This module provides algorithms for optimizing the selection of database records
to cover temperature ranges with minimal record count while maintaining accuracy.
"""

from .optimal_record_selector import (
    OptimalRecordSelector,
    VirtualRecord,
    OptimizationConfig,
    RecordGroup,
    OptimizationScore
)

__all__ = [
    "OptimalRecordSelector",
    "VirtualRecord",
    "OptimizationConfig",
    "RecordGroup",
    "OptimizationScore"
]