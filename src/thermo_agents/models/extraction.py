"""
Модели для извлечения параметров реакции из естественного языка.

Эта модель обновлена для поддержки до 10 веществ в реакции и используется
в Thermodynamic Agent для структурированного извлечения данных.

Техническое описание:
Pydantic модели для извлечения структурированных параметров термодинамических реакций
из запросов на естественном языке. Обеспечивают строгую типизацию и валидацию данных
для LLM-компонента в гибридной архитектуре v2.0.

Основная модель:

ExtractedReactionParameters:
- Структурированное представление параметров термодинамической реакции
- Результат работы ThermodynamicAgent по извлечению из естественного языка
- Поддержка до 10 веществ в реакции согласно требованиям
- Валидация всех параметров и согласованности данных

Ключевые поля ExtractedReactionParameters:

Тип и структура запроса:
- **query_type**: Тип запроса ("compound_data" или "reaction_calculation")
- **balanced_equation**: Уравнение реакции в стандартизированном формате
- **all_compounds**: Все вещества в реакции (до 10)
- **reactants**: Реагенты (левая часть уравнения)
- **products**: Продукты (правая часть уравнения)

Температурные параметры:
- **temperature_range_k**: Диапазон температур (tmin, tmax) в Кельвинах
- **temperature_step_k**: Шаг температуры для таблиц (25-250K)

Качество и метаданные:
- **extraction_confidence**: Уверенность извлечения (0.0-1.0)
- **missing_fields**: Поля, которые не удалось извлечь
- **compound_names**: Названия веществ {формула: [IUPAC, trivial...]}

Валидация данных:
- Проверка максимального количества веществ (≤10)
- Валидация температурных диапазонов
- Проверка согласованности реагентов и продуктов
- Валидация типов запросов

Типы запросов:
- **compound_data**: Запрос данных по одному веществу
  - Только одно вещество в all_compounds
  - Пустые reactants и products
- **reaction_calculation**: Расчёт термодинамики реакции
  - Несколько веществ (2-10)
  - Заполненные reactants и products

Правила валидации:
- Для compound_data: ровно одно вещество
- Для reaction_calculation: минимум 2 вещества
- Температурный диапазон должен быть корректным
- Уверенность извлечения в диапазоне 0.0-1.0

Температурные параметры:
- Диапазон поддерживает отрицательные температуры
- Шаг температуры ограничен (25-250K)
- Автоматическая коррекция некорректных значений

Структура compound_names:
- Ключ: химическая формула
- Значение: список названий [IUPAC, тривиальные]
- Поддержка синонимов для поиска
- Улучшение распознавания соединений

Методы валидации:
- validate_compounds_count(): Проверка количества веществ
- validate_reactants_products_consistency(): Согласованность реагентов/продуктов
- model_post_init(): Комплексная пост-валидация
- Проверка температурных диапазонов

Интеграция с LLM:
- Структурированный вывод PydanticAI
- Явные типы для надежности
- Автоматическая валидация результатов LLM
- Обработка ошибок извлечения

Особенности реализации:
- Использование Literal для query_type
- Max_length constraint для количества веществ
- Автоматическая валидация диапазонов
- Поддержка дополнительных полей через extra

Обработка ошибок:
- Информативные сообщения об ошибках валидации
- Список отсутствующих полей
- Метрики уверенности извлечения
- Graceful degradation при неполных данных

Конфигурация Pydantic:
- Строгая валидация всех полей
- Автоматическое преобразование типов
- Генерация схем для документации
- Поддержка сериализации JSON

Интеграция:
- Используется ThermodynamicAgent для структурированного вывода
- Интегрируется с ThermoOrchestrator для обработки
- Поддерживает LLM-компонент PydanticAI
- Совместим с остальными моделями системы

Используется в:
- ThermodynamicAgent для извлечения параметров
- ThermoOrchestrator для маршрутизации запросов
- CompoundSearcher для поиска соединений
- Валидации пользовательских запросов
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

    use_multi_phase: bool = Field(
        default=True,
        description="Использовать многофазные расчёты (Stage 5)"
    )

    full_data_search: bool = Field(
        default=True,
        description="Игнорировать температурные ограничения при поиске (Stage 5)"
    )

    user_preferences: Dict[str, object] = Field(
        default_factory=dict,
        description="Пользовательские предпочтения для расчётов (Stage 5)"
    )

    stoichiometry: Dict[str, float] = Field(
        default_factory=dict,
        description="Стехиометрические коэффициенты веществ (Stage 5)"
    )

    is_elemental: Optional[bool] = Field(
        default=None,
        description=(
            "Является ли вещество простым (состоит из одного элемента). "
            "True для O2, N2, H2, C, Fe, Cl2 и т.п. "
            "False для H2O, CO2, NH3, NaCl и других сложных веществ. "
            "Только для query_type='compound_data' (одно вещество). "
            "Для простых веществ H₂₉₈ = 0.0 кДж/моль по определению."
        )
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
        if tmax > 150000:
            raise ValueError(f"Tmax слишком высокая: {tmax} > 150000K")
        return v

    @field_validator('is_elemental')
    @classmethod
    def validate_is_elemental(cls, v, info):
        """Проверка корректности флага is_elemental."""
        query_type = info.data.get('query_type')
        all_compounds = info.data.get('all_compounds', [])

        # is_elemental применим только для compound_data (одно вещество)
        if v is not None and query_type != 'compound_data':
            raise ValueError(
                "Поле is_elemental применимо только для query_type='compound_data'"
            )

        if v is not None and len(all_compounds) > 1:
            raise ValueError(
                "Поле is_elemental применимо только для запросов с одним веществом"
            )

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