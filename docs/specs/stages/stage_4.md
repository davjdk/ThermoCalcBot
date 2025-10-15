# Этап 4: Агрегация и форматирование

**Длительность:** 2-3 дня  
**Приоритет:** Средний  
**Статус:** Не начат  
**Зависимости:** Этап 3

---

## Описание

Создание модуля агрегации данных по всем веществам реакции и форматирования результатов для вывода пользователю.

---

## Основные задачи

### 1. Создать структуру модуля `aggregation/`

**Структура каталога:**
```
src/thermo_agents/aggregation/
├── __init__.py                 # Экспорты
├── reaction_aggregator.py      # Агрегация по реакции
└── table_formatter.py          # Форматирование таблиц
```

**Задачи:**
- [ ] Создать каталог `src/thermo_agents/aggregation/`
- [ ] Создать файл `__init__.py` с экспортами

---

### 2. Реализовать `ReactionAggregator`

**Файл:** `src/thermo_agents/aggregation/reaction_aggregator.py`

**Класс:**
```python
from typing import List, Dict
from src.thermo_agents.models.search import CompoundSearchResult
from src.thermo_agents.models.aggregation import AggregatedReactionData, FilterStatistics

class ReactionAggregator:
    """Агрегация результатов поиска по всем веществам реакции."""
    
    def __init__(self, max_compounds: int = 10):
        """
        Args:
            max_compounds: Максимальное количество веществ (по ТЗ: до 10)
        """
        self.max_compounds = max_compounds
    
    def aggregate_reaction_data(
        self,
        reaction_equation: str,
        compounds_results: List[CompoundSearchResult]
    ) -> AggregatedReactionData:
        """
        Агрегация данных по всем веществам реакции.
        
        Args:
            reaction_equation: Уравнение реакции "A + B → C + D"
            compounds_results: Результаты поиска для каждого вещества
            
        Returns:
            AggregatedReactionData с полной информацией
        """
        # Валидация количества веществ
        if len(compounds_results) > self.max_compounds:
            raise ValueError(
                f"Превышено максимальное количество веществ: "
                f"{len(compounds_results)} > {self.max_compounds}"
            )
        
        # Разделение на найденные/ненайденные
        found_compounds = []
        missing_compounds = []
        
        for result in compounds_results:
            if result.filter_statistics and result.filter_statistics.is_found:
                found_compounds.append(result.compound_formula)
            else:
                missing_compounds.append(result.compound_formula)
        
        # Определение статуса полноты
        if len(missing_compounds) == 0:
            completeness_status = "complete"
        elif len(found_compounds) > 0:
            completeness_status = "partial"
        else:
            completeness_status = "incomplete"
        
        # Сбор детальной статистики
        detailed_statistics = {
            result.compound_formula: result.filter_statistics
            for result in compounds_results
        }
        
        # Генерация предупреждений
        warnings = self._generate_warnings(compounds_results)
        
        # Генерация рекомендаций
        recommendations = self._generate_recommendations(
            missing_compounds, completeness_status
        )
        
        return AggregatedReactionData(
            reaction_equation=reaction_equation,
            compounds_data=compounds_results,
            summary_table_formatted="",  # Заполняется TableFormatter
            completeness_status=completeness_status,
            missing_compounds=missing_compounds,
            found_compounds=found_compounds,
            detailed_statistics=detailed_statistics,
            warnings=warnings,
            recommendations=recommendations
        )
    
    def _generate_warnings(
        self, 
        compounds_results: List[CompoundSearchResult]
    ) -> List[str]:
        """Генерация предупреждений на основе результатов."""
        warnings = []
        
        for result in compounds_results:
            # Предупреждение о частичном покрытии
            if result.coverage_status == "partial":
                warnings.append(
                    f"Для {result.compound_formula} частичное покрытие "
                    f"температурного диапазона"
                )
            
            # Предупреждения из самого результата
            warnings.extend(result.warnings)
        
        return warnings
    
    def _generate_recommendations(
        self, 
        missing_compounds: List[str],
        completeness_status: str
    ) -> List[str]:
        """Генерация рекомендаций пользователю."""
        recommendations = []
        
        if completeness_status == "incomplete":
            recommendations.append(
                "Попробуйте изменить температурный диапазон или "
                "уточните химические формулы веществ"
            )
        
        if missing_compounds:
            recommendations.append(
                f"Отсутствуют данные для: {', '.join(missing_compounds)}"
            )
        
        return recommendations
```

**Задачи:**
- [ ] Реализовать класс `ReactionAggregator`
- [ ] Добавить валидацию максимального количества веществ (10)
- [ ] Реализовать генерацию предупреждений
- [ ] Реализовать генерацию рекомендаций

---

### 3. Реализовать `TableFormatter` с `tabulate`

**Файл:** `src/thermo_agents/aggregation/table_formatter.py`

**Класс:**
```python
from tabulate import tabulate
from typing import List
from src.thermo_agents.models.search import CompoundSearchResult, DatabaseRecord

class TableFormatter:
    """Форматирование результатов в таблицы через tabulate."""
    
    def format_summary_table(
        self, 
        compounds_results: List[CompoundSearchResult]
    ) -> str:
        """
        Форматирование сводной таблицы термодинамических свойств.
        
        Колонки (порядок строго соблюдается):
        1. Формула
        2. Фаза
        3. T_диапазон (K)
        4. H298 (кДж/моль)
        5. S298 (Дж/моль·K)
        6. Cp_коэффициенты (f1-f6)
        7. Надёжность (класс)
        
        Returns:
            Отформатированная таблица в формате 'grid'
        """
        headers = [
            "Формула",
            "Фаза",
            "T_диапазон (K)",
            "H298 (кДж/моль)",
            "S298 (Дж/моль·K)",
            "Cp_коэффициенты (f1-f6)",
            "Надёжность (класс)"
        ]
        
        table_data = []
        
        for result in compounds_results:
            if not result.records_found:
                continue
            
            # Взять первую (приоритетную) запись
            record = result.records_found[0]
            
            row = [
                self._format_formula(record),
                self._format_phase(record),
                self._format_temperature_range(record),
                self._format_h298(record),
                self._format_s298(record),
                self._format_cp_coefficients(record),
                self._format_reliability(record)
            ]
            
            table_data.append(row)
        
        return tabulate(table_data, headers=headers, tablefmt="grid")
    
    def _format_formula(self, record: DatabaseRecord) -> str:
        """Форматирование формулы (убрать фазу в скобках, если есть)."""
        formula = record.formula
        if '(' in formula:
            return formula[:formula.index('(')]
        return formula
    
    def _format_phase(self, record: DatabaseRecord) -> str:
        """Извлечение фазы."""
        if record.phase:
            return record.phase
        
        # Извлечь из формулы
        if '(' in record.formula and ')' in record.formula:
            start = record.formula.index('(') + 1
            end = record.formula.index(')')
            return record.formula[start:end]
        
        return "?"
    
    def _format_temperature_range(self, record: DatabaseRecord) -> str:
        """Форматирование температурного диапазона."""
        tmin = int(record.tmin) if record.tmin else 0
        tmax = int(record.tmax) if record.tmax else "∞"
        return f"{tmin}-{tmax}"
    
    def _format_h298(self, record: DatabaseRecord) -> str:
        """Форматирование энтальпии."""
        if record.h298 is None:
            return "—"
        return f"{record.h298:.1f}"
    
    def _format_s298(self, record: DatabaseRecord) -> str:
        """Форматирование энтропии."""
        if record.s298 is None:
            return "—"
        return f"{record.s298:.1f}"
    
    def _format_cp_coefficients(self, record: DatabaseRecord) -> str:
        """Форматирование коэффициентов теплоёмкости."""
        coeffs = [record.f1, record.f2, record.f3, record.f4, record.f5, record.f6]
        
        # Если все NULL
        if all(c is None for c in coeffs):
            return "—"
        
        # Форматирование с сокращением
        formatted = []
        for c in coeffs[:3]:  # Первые 3 коэффициента
            if c is not None:
                formatted.append(f"{c:.2e}" if abs(c) < 0.01 else f"{c:.3f}")
            else:
                formatted.append("—")
        
        return ", ".join(formatted) + ", ..."
    
    def _format_reliability(self, record: DatabaseRecord) -> str:
        """Форматирование класса надёжности."""
        if record.reliability_class is None:
            return "?"
        return str(record.reliability_class)
```

**Задачи:**
- [ ] Реализовать класс `TableFormatter`
- [ ] Добавить все методы форматирования (`_format_*`)
- [ ] Обеспечить строгий порядок колонок
- [ ] Протестировать с `tabulate` на примерах

---

### 4. Добавить генерацию детальной статистики фильтрации

**Формат вывода:**
```
📈 Детальная статистика фильтрации:

TiO2:
  ├─ Стадия 1 (Поиск по формуле): найдено 15 записей
  ├─ Стадия 2 (Температурный диапазон 298-673K): осталось 8 записей
  ├─ Стадия 3 (Фазовый состав - твёрдое при T<2130K): осталось 3 записи
  └─ Стадия 4 (Приоритизация по надёжности): выбрана 1 запись
```

**Реализация:**
```python
class StatisticsFormatter:
    """Форматирование детальной статистики фильтрации."""
    
    def format_detailed_statistics(
        self, 
        detailed_statistics: Dict[str, FilterStatistics]
    ) -> str:
        """
        Форматирование дерева статистики для каждого вещества.
        
        Args:
            detailed_statistics: Словарь {формула: FilterStatistics}
            
        Returns:
            Отформатированная строка с деревом статистики
        """
        lines = ["📈 Детальная статистика фильтрации:", ""]
        
        for formula, stats in detailed_statistics.items():
            lines.append(f"{formula}:")
            
            # Стадия 1
            lines.append(
                f"  ├─ Стадия 1 ({stats.stage_1_description}): "
                f"найдено {stats.stage_1_initial_matches} записей"
            )
            
            # Стадия 2
            if stats.stage_2_temperature_filtered > 0:
                lines.append(
                    f"  ├─ Стадия 2 ({stats.stage_2_description}): "
                    f"осталось {stats.stage_2_temperature_filtered} записей"
                )
            else:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason}"
                )
                lines.append("")
                continue
            
            # Стадия 3
            if stats.stage_3_phase_selected > 0:
                lines.append(
                    f"  ├─ Стадия 3 ({stats.stage_3_description}): "
                    f"осталось {stats.stage_3_phase_selected} записей"
                )
            else:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason}"
                )
                lines.append("")
                continue
            
            # Стадия 4
            lines.append(
                f"  └─ Стадия 4 ({stats.stage_4_description}): "
                f"выбрана {stats.stage_4_final_selected} запись"
            )
            lines.append("")
        
        return "\n".join(lines)
```

**Задачи:**
- [ ] Реализовать `StatisticsFormatter`
- [ ] Добавить форматирование дерева с символами ├─ и └─
- [ ] Обработать случай провала на любой стадии

---

### 5. Обновить Pydantic модели

**Файл:** `src/thermo_agents/models/aggregation.py`

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from src.thermo_agents.models.search import CompoundSearchResult

class FilterStatistics(BaseModel):
    """Статистика фильтрации для одного вещества."""
    stage_1_initial_matches: int
    stage_1_description: str = "Поиск по формуле"
    
    stage_2_temperature_filtered: int
    stage_2_description: str
    
    stage_3_phase_selected: int
    stage_3_description: str
    
    stage_4_final_selected: int
    stage_4_description: str = "Приоритизация по надёжности"
    
    is_found: bool
    failure_stage: Optional[int] = None
    failure_reason: Optional[str] = None

class AggregatedReactionData(BaseModel):
    """Агрегированные данные по реакции."""
    reaction_equation: str
    compounds_data: List[CompoundSearchResult]
    summary_table_formatted: str
    completeness_status: str = Field(
        ..., 
        description="'complete', 'partial', 'incomplete'"
    )
    missing_compounds: List[str] = Field(default_factory=list)
    found_compounds: List[str] = Field(default_factory=list)
    detailed_statistics: Dict[str, FilterStatistics]
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
```

**Задачи:**
- [ ] Создать `src/thermo_agents/models/aggregation.py`
- [ ] Реализовать `FilterStatistics`
- [ ] Реализовать `AggregatedReactionData`

---

## Артефакты этапа

### Файлы для создания:
1. `src/thermo_agents/aggregation/reaction_aggregator.py`
2. `src/thermo_agents/aggregation/table_formatter.py`
3. `src/thermo_agents/aggregation/statistics_formatter.py`
4. `src/thermo_agents/models/aggregation.py`
5. `tests/test_reaction_aggregator.py`
6. `tests/test_table_formatter.py`

### Зависимости:
- Добавить `tabulate` в `pyproject.toml`

---

## Критерии завершения этапа

✅ **Обязательные:**
1. `ReactionAggregator` корректно агрегирует данные по всем веществам
2. `TableFormatter` форматирует таблицы через `tabulate` в формате `grid`
3. `StatisticsFormatter` форматирует дерево статистики
4. Поддержка до 10 веществ в реакции
5. Все unit-тесты проходят

---

## Риски

| Риск                          | Вероятность | Влияние | Митигация                            |
| ----------------------------- | ----------- | ------- | ------------------------------------ |
| Сложное форматирование дерева | Низкая      | Низкое  | Использовать готовые символы Unicode |
| Проблемы с `tabulate`         | Низкая      | Среднее | Тестировать на разных версиях        |

---

## Следующий этап

➡️ **Этап 5:** Обновление Thermodynamic Agent
