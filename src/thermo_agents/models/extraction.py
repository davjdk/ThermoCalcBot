"""
Модели для извлечения параметров реакции из естественного языка.

Эта модель обновлена для поддержки до 10 веществ в реакции и используется
в Thermodynamic Agent для структурированного извлечения данных.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Tuple, Optional, Dict, Literal


class ExtractedReactionParameters(BaseModel):
    """Параметры реакции, извлечённые из запроса пользователя."""

    query_type: Literal["compound_data", "reaction_calculation"] = Field(
        ...,
        description="Тип запроса: данные по веществу или расчёт реакции"
    )

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

    temperature_step_k: int = Field(
        default=100,
        ge=25,
        le=250,
        description="Шаг температуры для таблиц, K (25-250)"
    )

    @field_validator('all_compounds')
    @classmethod
    def validate_compounds_count(cls, v):
        """Проверка максимального количества веществ."""
        if len(v) > 10:
            raise ValueError(f"Превышено максимальное количество веществ: {len(v)} > 10")
        return v

    @field_validator('reactants', 'products')
    @classmethod
    def validate_reactants_products_consistency(cls, v, info):
        """Валидация согласованности реагентов и продуктов."""
        # Валидация будет перенесена в model_validator_mode='after'
        return v

    def model_post_init(self, __context):
        """Пост-инициализация для комплексной валидации."""
        # Валидация query_type согласованности
        if self.query_type == "compound_data":
            # Для compound_data должно быть одно вещество
            if len(self.all_compounds) > 1:
                raise ValueError(
                    f"compound_data должен содержать одно вещество, "
                    f"получено: {len(self.all_compounds)}"
                )
            # Реагенты и продукты должны быть пустыми
            if self.reactants or self.products:
                raise ValueError(
                    "compound_data не должен содержать reactants/products"
                )

        elif self.query_type == "reaction_calculation":
            # Для reaction_calculation должна быть реакция
            if len(self.all_compounds) < 2:
                raise ValueError(
                    f"reaction_calculation требует минимум 2 вещества, "
                    f"получено: {len(self.all_compounds)}"
                )
            # Должно быть уравнение реакции
            if not self.balanced_equation or self.balanced_equation == "N/A":
                raise ValueError(
                    "reaction_calculation требует balanced_equation"
                )

    @field_validator('temperature_step_k')
    @classmethod
    def validate_temperature_step(cls, v):
        """Проверка шага температуры."""
        if not (25 <= v <= 250):
            raise ValueError(
                f"temperature_step_k должен быть в диапазоне 25-250K, получено: {v}"
            )
        # Рекомендация: шаг должен быть кратен 25
        if v % 25 != 0:
            import warnings
            warnings.warn(
                f"Рекомендуется использовать шаг кратный 25K "
                f"(25, 50, 100, 150, 200, 250), получено: {v}K"
            )
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
        if self.query_type == "compound_data":
            # Для compound_data обязательны только all_compounds и temperature_range_k
            required_fields = ['all_compounds', 'temperature_range_k']
        else:  # reaction_calculation
            # Для reaction_calculation обязательны все поля реакции
            required_fields = [
                'balanced_equation',
                'reactants',
                'products',
                'all_compounds',
                'temperature_range_k'
            ]

        return len(self.missing_fields) == 0 and all(
            getattr(self, field) for field in required_fields
        )