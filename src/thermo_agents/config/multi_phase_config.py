"""
Конфигурация многофазных термодинамических расчётов.

Содержит параметры для интеграции многофазной логики в систему.
"""

from pathlib import Path
from typing import Dict, Any, Optional

# Конфигурация многофазных расчётов
MULTI_PHASE_CONFIG: Dict[str, Any] = {
    # Использование YAML кэша
    "use_static_cache": True,
    "static_cache_dir": "data/static_compounds/",

    # Настройки интегрирования
    "min_segments_for_warning": 5,  # Предупреждать если > 5 сегментов
    "integration_points": 400,  # Точек для численного интегрирования
    "max_temperature": 6000.0,  # Максимальная температура расчёта (K)

    # Пороги для предупреждений
    "gap_threshold": 1.0,  # Пробел в покрытии > 1K вызывает предупреждение
    "overlap_threshold": 1.0,  # Перекрытие > 1K вызывает предупреждение

    # Форматирование вывода
    "show_phase_transitions": True,  # Показывать фазовые переходы
    "show_segment_info": True,  # Показывать информацию о сегментах
    "show_metadata": True,  # Показывать метаданные расчёта

    # Качество данных
    "max_reliability_class": 3,  # Максимальный класс надёжности (1=высший, 3=низший)
    "require_298K_coverage": True,  # Требовать покрытие 298K
}

# Значения по умолчанию для инициализации
DEFAULT_STATIC_CACHE_DIR: str = MULTI_PHASE_CONFIG["static_cache_dir"]
DEFAULT_INTEGRATION_POINTS: int = MULTI_PHASE_CONFIG["integration_points"]
DEFAULT_MAX_TEMPERATURE: float = MULTI_PHASE_CONFIG["max_temperature"]

def get_multi_phase_config() -> Dict[str, Any]:
    """Получить копию конфигурации многофазных расчётов."""
    return MULTI_PHASE_CONFIG.copy()

def get_static_cache_dir(base_dir: Optional[Path] = None) -> Path:
    """
    Получить директорию для YAML кэша.

    Args:
        base_dir: Базовая директория проекта. Если None, используется текущая.

    Returns:
        Path к директории статического кэша
    """
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent.parent

    cache_dir = base_dir / MULTI_PHASE_CONFIG["static_cache_dir"]
    return cache_dir

def get_integration_points(override: Optional[int] = None) -> int:
    """
    Получить количество точек интегрирования.

    Args:
        override: Переопределение значения

    Returns:
        Количество точек интегрирования
    """
    if override is not None:
        return override
    return MULTI_PHASE_CONFIG["integration_points"]

def is_multi_phase_enabled() -> bool:
    """Проверить, включены ли многофазные расчёты."""
    return MULTI_PHASE_CONFIG["use_static_cache"]

def should_use_static_cache(formula: str) -> bool:
    """
    Проверить, следует ли использовать статический кэш для вещества.

    Args:
        formula: Химическая формула

    Returns:
        True если следует использовать кэш
    """
    if not is_multi_phase_enabled():
        return False

    # Список веществ, для которых предпочтительно использовать кэш
    cache_favored_compounds = {
        "H2O", "CO2", "O2", "N2", "H2", "CO", "NO", "NO2",
        "SO2", "SO3", "CH4", "C2H6", "C3H8", "NH3", "HCl", "HF"
    }

    return formula in cache_favored_compounds

def validate_config() -> bool:
    """
    Валидировать конфигурацию многофазных расчётов.

    Returns:
        True если конфигурация корректна
    """
    errors = []

    # Проверка типов
    if not isinstance(MULTI_PHASE_CONFIG["use_static_cache"], bool):
        errors.append("use_static_cache должен быть bool")

    if not isinstance(MULTI_PHASE_CONFIG["static_cache_dir"], str):
        errors.append("static_cache_dir должен быть str")

    if not isinstance(MULTI_PHASE_CONFIG["integration_points"], int):
        errors.append("integration_points должен быть int")

    if not isinstance(MULTI_PHASE_CONFIG["max_temperature"], (int, float)):
        errors.append("max_temperature должен быть числом")

    # Проверка диапазонов
    if MULTI_PHASE_CONFIG["integration_points"] < 50:
        errors.append("integration_points должен быть >= 50")

    if MULTI_PHASE_CONFIG["max_temperature"] <= 0:
        errors.append("max_temperature должен быть > 0")

    if errors:
        print("❌ Ошибки в конфигурации MULTI_PHASE_CONFIG:")
        for error in errors:
            print(f"  - {error}")
        return False

    return True

# Валидация конфигурации при импорте
if not validate_config():
    raise ValueError("Некорректная конфигурация многофазных расчётов")