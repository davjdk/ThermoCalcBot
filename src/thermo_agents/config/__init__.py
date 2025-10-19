"""
Конфигурация термодинамической системы.

Содержит настройки для различных компонентов системы.
"""

from .multi_phase_config import (
    MULTI_PHASE_CONFIG,
    DEFAULT_STATIC_CACHE_DIR,
    DEFAULT_INTEGRATION_POINTS,
    DEFAULT_MAX_TEMPERATURE,
    get_multi_phase_config,
    get_static_cache_dir,
    get_integration_points,
    is_multi_phase_enabled,
    should_use_static_cache,
    validate_config,
)

__all__ = [
    "MULTI_PHASE_CONFIG",
    "DEFAULT_STATIC_CACHE_DIR",
    "DEFAULT_INTEGRATION_POINTS",
    "DEFAULT_MAX_TEMPERATURE",
    "get_multi_phase_config",
    "get_static_cache_dir",
    "get_integration_points",
    "is_multi_phase_enabled",
    "should_use_static_cache",
    "validate_config",
]