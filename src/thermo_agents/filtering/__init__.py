"""
Модуль фильтрации термодинамических данных (Этап 1 рефакторинга).

Оставлены только базовые компоненты после удаления избыточной логики:
- PhaseResolver: определение фазовых состояний
- PhaseSegmentBuilder: построение фазовых сегментов
- constants: константы фильтрации
- precomputed_data: предвычисленные данные
"""

from .phase_resolver import PhaseResolver
from .phase_segment_builder import PhaseSegmentBuilder

__all__ = [
    'PhaseResolver',
    'PhaseSegmentBuilder',
]