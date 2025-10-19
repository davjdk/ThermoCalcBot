"""
Unit tests for PhaseTransition model.
"""

import pytest
from thermo_agents.models.search import PhaseTransition, TransitionType


def test_phase_transition_melting():
    """Test melting transition creation."""
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=6.008,
        delta_S_transition=22.0
    )

    assert transition.temperature == 273.15
    assert transition.transition_type == TransitionType.MELTING
    assert transition.delta_H_transition == 6.008
    assert transition.delta_S_transition == 22.0


def test_phase_transition_auto_type_detection():
    """Test automatic transition type detection."""
    # s → l = melting
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.MELTING

    # l → g = boiling
    transition = PhaseTransition(
        temperature=373.15,
        from_phase="l",
        to_phase="g",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.BOILING

    # s → g = sublimation
    transition = PhaseTransition(
        temperature=195.4,
        from_phase="s",
        to_phase="g",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.SUBLIMATION

    # Unknown transition
    transition = PhaseTransition(
        temperature=1000.0,
        from_phase="s",
        to_phase="s",  # Same phase
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.UNKNOWN


def test_phase_transition_explicit_type():
    """Test explicitly setting transition type."""
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.BOILING,  # Explicit but wrong for phases
        delta_H_transition=6.008
    )

    # Should keep the explicit type, not auto-detect
    assert transition.transition_type == TransitionType.BOILING


def test_phase_transition_case_insensitive():
    """Test case insensitive phase detection."""
    # Upper case phases
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="S",
        to_phase="L",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.MELTING

    # Mixed case phases
    transition = PhaseTransition(
        temperature=373.15,
        from_phase="L",
        to_phase="G",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.BOILING


def test_phase_transition_to_dict():
    """Test transition serialization."""
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type=TransitionType.MELTING,
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )

    result = transition.to_dict()

    assert result["T"] == 1650.0
    assert result["transition"] == "s→l"
    assert result["type"] == "melting"
    assert result["ΔH"] == 32.0
    assert result["ΔS"] == 19.4


def test_phase_transition_default_values():
    """Test PhaseTransition with default values."""
    transition = PhaseTransition(
        temperature=1000.0,
        from_phase="l",
        to_phase="g"
    )

    # Should auto-detect as boiling
    assert transition.transition_type == TransitionType.BOILING

    # Default values for thermodynamic properties
    assert transition.delta_H_transition == 0.0
    assert transition.delta_S_transition == 0.0


def test_phase_transition_validation():
    """Test PhaseTransition validation."""
    # Valid transition
    transition = PhaseTransition(
        temperature=273.15,
        from_phase="s",
        to_phase="l"
    )
    assert transition.transition_type == TransitionType.MELTING

    # Empty phases should result in UNKNOWN
    transition = PhaseTransition(
        temperature=100.0,
        from_phase="",
        to_phase="",
        transition_type=TransitionType.UNKNOWN
    )
    assert transition.transition_type == TransitionType.UNKNOWN