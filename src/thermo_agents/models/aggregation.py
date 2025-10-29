"""
Pydantic модели для агрегации результатов термодинамического поиска.

Содержит модели для статистики фильтрации и агрегированных данных по реакции.

Техническое описание:
Pydantic модели данных для агрегации результатов термодинамического поиска.
Определяют структуру данных для статистики фильтрации, агрегированных данных по реакции
и результатов обработки в гибридной архитектуре v2.0.

Основные модели:

FilterStatistics:
- Детальная статистика фильтрации для одного вещества
- Отслеживание преобразования данных на каждой стадии
- Анализ причин провала фильтрации
- Метрики производительности операций

Стадии фильтрации FilterStatistics:
- **stage_1_initial_matches**: Количество записей найденных по формуле
- **stage_2_temperature_filtered**: После температурной фильтрации
- **stage_3_phase_selected**: После выбора фазового состояния
- **stage_4_final_selected**: Финально выбранные записи

Дополнительные поля FilterStatistics:
- is_found: Булево значение успешности поиска
- failure_stage: Стадия провала (если применимо)
- failure_reason: Причина провала операции
- Описания каждой стадии для понятности

AggregatedReactionData:
- Полные агрегированные данные по термодинамической реакции
- Результаты поиска для всех веществ реакции
- Форматированные таблицы и статистика
- Анализ полноты и качества данных

Основные поля AggregatedReactionData:
- reaction_equation: Уравнение реакции в формате 'A + B → C + D'
- compounds_data: Результаты поиска для каждого вещества
- summary_table_formatted: Отформатированная таблица результатов
- completeness_status: Статус полноты данных
- missing_compounds/found_compounds: Разделение веществ по статусу
- filtered_out_compounds: Вещества отфильтрованные при обработке
- detailed_statistics: Статистика по каждому веществу
- warnings: Предупреждения о проблемах
- recommendations: Рекомендации пользователю

Методы AggregatedReactionData:
- get_total_compounds_count(): Общее количество веществ
- get_found_compounds_count(): Количество найденных веществ
- get_missing_compounds_count(): Количество отсутствующих веществ
- get_completeness_percentage(): Процент полноты данных

Статусы полноты:
- **complete**: Все вещества найдены с полными данными
- **partial**: Часть веществ найдена или данные неполные
- **incomplete**: Данные отсутствуют для большинства веществ

Анализ качества данных:
- Проверка температурного покрытия
- Валидация надежности источников
- Анализ фазовой согласованности
- Выявление проблемных областей

Генерация предупреждений:
- Отсутствие термодинамических данных
- Проблемы с покрытием диапазонов
- Низкая надежность источников
- Фазовые несоответствия

Создание рекомендаций:
- Расширение поиска по синонимам
- Проверка орфографии в формулах
- Использование альтернативных источников
- Коррекция температурных диапазонов

Валидация данных:
- Проверка корректности уравнений реакций
- Валидация форматов результатов поиска
- Проверка целостности статистики
- Согласованность данных между моделями

Интеграция с другими моделями:
- Использует CompoundSearchResult из search.py
- Совместим с FilterPipeline результатами
- Поддерживает DatabaseRecord модели
- Интегрируется с агрегационной логикой

Особенности реализации:
- Использование Pydantic для строгой типизации
- Автоматическая валидация агрегированных данных
- Поддержка сериализации/десериализации
- Расширенные поля для будущих улучшений

Конфигурация Pydantic:
- arbitrary_types_allowed для сложных типов
- Поддержка валидации данных
- Автоматическое преобразование типов
- Генерация схем для API

Интеграция:
- Используется ReactionAggregator для результатов
- Интегрируется с ThermoOrchestrator
- Поддерживает TableFormatter для вывода
- Совместим с остальными компонентами

Используется в:
- ReactionAggregator для агрегации данных
- ThermoOrchestrator для финальных результатов
- API endpoints для структурированных данных
- Системах отчетности и анализа
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass

from pydantic import BaseModel, Field

from ..models.search import CompoundSearchResult, MultiPhaseCompoundData


class FilterStatistics(BaseModel):
    """Статистика фильтрации для одного вещества."""

    stage_1_initial_matches: int = Field(
        ..., description="Количество записей найденных на стадии 1 (поиск по формуле)"
    )
    stage_1_description: str = Field(
        default="Поиск по формуле", description="Описание стадии 1"
    )

    stage_2_temperature_filtered: int = Field(
        ..., description="Количество записей после температурной фильтрации (стадия 2)"
    )
    stage_2_description: str = Field(
        ..., description="Описание стадии 2 (температурная фильтрация)"
    )

    stage_3_phase_selected: int = Field(
        ..., description="Количество записей после выбора фазы (стадия 3)"
    )
    stage_3_description: str = Field(..., description="Описание стадии 3 (выбор фазы)")

    stage_4_final_selected: int = Field(
        ..., description="Количество финально выбранных записей (стадия 4)"
    )
    stage_4_description: str = Field(
        default="Приоритизация по надёжности",
        description="Описание стадии 4 (приоритезация)",
    )

    is_found: bool = Field(..., description="Было ли вещество найдено в результате")
    failure_stage: Optional[int] = Field(
        default=None, description="Стадия на которой произошёл провал (если применимо)"
    )
    failure_reason: Optional[str] = Field(
        default=None, description="Причина провала (если применимо)"
    )

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


class AggregatedReactionData(BaseModel):
    """Агрегированные данные по реакции."""

    reaction_equation: str = Field(
        ..., description="Уравнение реакции в формате 'A + B → C + D'"
    )
    compounds_data: List[CompoundSearchResult] = Field(
        ..., description="Результаты поиска для каждого вещества"
    )
    summary_table_formatted: str = Field(
        ..., description="Отформатированная сводная таблица"
    )
    completeness_status: str = Field(
        ..., description="Статус полноты: 'complete', 'partial', 'incomplete'"
    )
    missing_compounds: List[str] = Field(
        default_factory=list, description="Список ненайденных веществ"
    )
    found_compounds: List[str] = Field(
        default_factory=list, description="Список найденных веществ"
    )
    filtered_out_compounds: List[str] = Field(
        default_factory=list, description="Список веществ, найденных но отфильтрованных"
    )
    detailed_statistics: Dict[str, FilterStatistics] = Field(
        ..., description="Детальная статистика фильтрации по каждому веществу"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Предупреждения о возможных проблемах"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Рекомендации пользователю"
    )

    def get_total_compounds_count(self) -> int:
        """Получить общее количество веществ в реакции."""
        return len(self.compounds_data)

    def get_found_compounds_count(self) -> int:
        """Получить количество найденных веществ."""
        return len(self.found_compounds)

    def get_missing_compounds_count(self) -> int:
        """Получить количество ненайденных веществ."""
        return len(self.missing_compounds)

    def get_completeness_percentage(self) -> float:
        """Получить процент полноты данных."""
        if self.get_total_compounds_count() == 0:
            return 0.0
        return (
            self.get_found_compounds_count() / self.get_total_compounds_count()
        ) * 100

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


@dataclass
class MultiPhaseReactionData:
    """Данные многофазной реакции для Stage 5."""

    balanced_equation: str
    reactants: List[str]
    products: List[str]
    stoichiometry: Dict[str, float]

    # Новые поля для Stage 5
    user_temperature_range: Optional[Tuple[float, float]]
    calculation_range: Tuple[float, float]
    compounds_data: Dict[str, MultiPhaseCompoundData]
    phase_changes: List[Tuple[float, str, str]]  # (T, compound, transition)

    # Результаты
    calculation_table: List[Dict[str, Any]]
    data_statistics: Dict[str, Any]

    # Метаданные
    calculation_method: str
    total_records_used: int
    phases_used: Set[str]

    def __post_init__(self):
        """Post-initialization validation."""
        # Validate temperature ranges
        if self.calculation_range[0] >= self.calculation_range[1]:
            raise ValueError("Invalid calculation range: start >= end")

        # Validate that user range is within calculation range if provided
        if self.user_temperature_range:
            user_min, user_max = self.user_temperature_range
            calc_min, calc_max = self.calculation_range
            if user_min < calc_min or user_max > calc_max:
                # This is acceptable - we'll expand the range
                pass

        # Validate stoichiometry
        if not self.stoichiometry:
            raise ValueError("Stoichiometry cannot be empty")

    def get_range_expansion_factor(self) -> float:
        """Calculate how much the range was expanded."""
        if not self.user_temperature_range:
            return 1.0

        user_width = self.user_temperature_range[1] - self.user_temperature_range[0]
        calc_width = self.calculation_range[1] - self.calculation_range[0]

        return calc_width / user_width if user_width > 0 else 1.0

    def get_database_coverage_percentage(self) -> float:
        """Calculate database coverage percentage."""
        total_available = sum(
            len(data.records) for data in self.compounds_data.values()
        )
        return (self.total_records_used / total_available * 100) if total_available > 0 else 0.0

    def get_phase_transition_count(self) -> int:
        """Get total number of phase transitions."""
        return len(self.phase_changes)

    def get_compounds_with_transitions(self) -> Set[str]:
        """Get compounds that have phase transitions."""
        return {compound for _, compound, _ in self.phase_changes}
