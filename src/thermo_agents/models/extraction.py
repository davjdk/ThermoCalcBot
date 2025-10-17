"""
Модели для извлечения параметров реакции из естественного языка.

Эта модель обновлена для поддержки до 10 веществ в реакции и используется
в Thermodynamic Agent для структурированного извлечения данных.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Tuple, Optional, Dict


class ExtractedReactionParameters(BaseModel):
    """Параметры реакции, извлечённые из запроса пользователя."""

    balanced_equation: str = Field(
        ...,
        description="Уравненное уравнение реакции, например: 'TiO2 + 2HCl → TiCl4 + H2O'"
    )

    all_compounds: List[str] = Field(
        ...,
        max_length=10,
        description="Все вещества в реакции (до 10 веществ)"
    )

    reactants: List[str] = Field(
        ...,
        description="Список реагентов (левая часть уравнения)"
    )

    products: List[str] = Field(
        ...,
        description="Список продуктов (правая часть уравнения)"
    )

    temperature_range_k: Tuple[float, float] = Field(
        ...,
        description="Температурный диапазон в Кельвинах (tmin, tmax)"
    )

    extraction_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность извлечения (0.0-1.0)"
    )

    missing_fields: List[str] = Field(
        default_factory=list,
        description="Список полей, которые не удалось извлечь"
    )

    compound_names: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Названия веществ: {формула: [IUPAC name, trivial names...]}"
    )

    @field_validator('all_compounds')
    @classmethod
    def validate_compounds_count(cls, v):
        """Проверка максимального количества веществ."""
        if len(v) > 10:
            raise ValueError(f"Превышено максимальное количество веществ: {len(v)} > 10")
        return v

    @field_validator('temperature_range_k')
    @classmethod
    def validate_temperature_range(cls, v):
        """Проверка корректности температурного диапазона."""
        tmin, tmax = v
        if tmin < 0:
            raise ValueError(f"Tmin не может быть отрицательной: {tmin}")
        if tmax <= tmin:
            raise ValueError(f"Tmax должен быть больше Tmin: {tmax} <= {tmin}")
        if tmax > 10000:
            raise ValueError(f"Tmax слишком высокая: {tmax} > 10000K")
        return v

    def is_complete(self) -> bool:
        """Проверка полноты извлечённых данных."""
        required_fields = [
            'balanced_equation',
            'reactants',
            'products',
            'temperature_range_k'
        ]
        return len(self.missing_fields) == 0 and all(
            getattr(self, field) for field in required_fields
        )