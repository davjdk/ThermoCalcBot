"""
Pydantic модели для агрегации результатов термодинамического поиска.

Содержит модели для статистики фильтрации и агрегированных данных по реакции.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ..models.search import CompoundSearchResult


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
