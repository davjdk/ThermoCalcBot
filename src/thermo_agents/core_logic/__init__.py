"""
Core logic modules for thermodynamic calculations.

This package contains the core calculation logic ported from calc_example.ipynb:
- CompoundDataLoader: Three-stage database search with YAML cache priority
- PhaseTransitionDetector: Melting and boiling point detection
- RecordRangeBuilder: Three-level strategy for record selection
- ThermodynamicEngine: Cp, H, S, G calculations for single compounds
- ReactionEngine: ΔH, ΔS, ΔG, K calculations for reactions
"""

from .compound_data_loader import CompoundDataLoader
from .phase_transition_detector import PhaseTransitionDetector
from .record_range_builder import RecordRangeBuilder
from .thermodynamic_engine import ThermodynamicEngine
from .reaction_engine import ReactionEngine

__all__ = [
    'CompoundDataLoader',
    'PhaseTransitionDetector',
    'RecordRangeBuilder',
    'ThermodynamicEngine',
    'ReactionEngine'
]