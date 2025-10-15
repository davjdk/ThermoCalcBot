# Этап 6: Рефакторинг Orchestrator

**Длительность:** 2-3 дня  
**Приоритет:** Средний  
**Статус:** Не начат  
**Зависимости:** Этап 5

---

## Описание

Упрощение и обновление оркестратора для работы с новыми модулями. Удаление зависимостей от упразднённых агентов и интеграция детерминированной логики.

---

## Основные задачи

### 1. Упростить логику координации

**Файл:** `src/thermo_agents/orchestrator.py`

**Старый поток (до рефакторинга):**
```
User Query → Thermodynamic Agent → SQL Generation Agent → 
Database Agent → Results Filtering Agent → Response Formatter
```

**Новый поток (после рефакторинга):**
```
User Query → Thermodynamic Agent → CompoundSearcher + FilterPipeline → 
ReactionAggregator + TableFormatter → Response
```

**Новая архитектура:**
```python
from src.thermo_agents.thermodynamic_agent import ThermodynamicAgent
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.filtering.filter_pipeline import FilterPipeline
from src.thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from src.thermo_agents.aggregation.table_formatter import TableFormatter
from src.thermo_agents.aggregation.statistics_formatter import StatisticsFormatter

class ThermoOrchestrator:
    """Упрощённый оркестратор термодинамической системы."""
    
    def __init__(
        self,
        thermodynamic_agent: ThermodynamicAgent,
        compound_searcher: CompoundSearcher,
        filter_pipeline: FilterPipeline,
        reaction_aggregator: ReactionAggregator,
        table_formatter: TableFormatter,
        statistics_formatter: StatisticsFormatter
    ):
        self.thermodynamic_agent = thermodynamic_agent
        self.compound_searcher = compound_searcher
        self.filter_pipeline = filter_pipeline
        self.reaction_aggregator = reaction_aggregator
        self.table_formatter = table_formatter
        self.statistics_formatter = statistics_formatter
    
    async def process_query(self, user_query: str) -> str:
        """
        Обработка запроса пользователя.
        
        Новый поток:
        1. Извлечение параметров (LLM)
        2. Поиск для каждого вещества (детерминированный)
        3. Фильтрация для каждого вещества (детерминированный)
        4. Агрегация результатов
        5. Форматирование ответа
        
        Args:
            user_query: Запрос на естественном языке
            
        Returns:
            Отформатированный текстовый ответ
        """
        try:
            # Шаг 1: Извлечение параметров
            params = await self.thermodynamic_agent.extract_parameters(user_query)
            
            # Шаг 2-3: Поиск и фильтрация для каждого вещества
            compound_results = []
            for compound in params.all_compounds:
                result = await self._search_and_filter_compound(
                    compound, params.temperature_range_k
                )
                compound_results.append(result)
            
            # Шаг 4: Агрегация
            aggregated_data = self.reaction_aggregator.aggregate_reaction_data(
                reaction_equation=params.balanced_equation,
                compounds_results=compound_results
            )
            
            # Форматирование таблицы
            aggregated_data.summary_table_formatted = \
                self.table_formatter.format_summary_table(compound_results)
            
            # Шаг 5: Форматирование ответа
            response = self._format_response(aggregated_data)
            
            return response
            
        except Exception as e:
            return self._format_error_response(str(e))
    
    async def _search_and_filter_compound(
        self, 
        compound: str, 
        temperature_range: Tuple[float, float]
    ) -> CompoundSearchResult:
        """Поиск и фильтрация для одного вещества."""
        # Поиск
        search_result = self.compound_searcher.search_compound(
            compound, temperature_range
        )
        
        # Фильтрация
        filter_context = FilterContext(
            temperature_range=temperature_range,
            compound_formula=compound
        )
        
        filter_result = self.filter_pipeline.execute(
            search_result.records_found,
            filter_context
        )
        
        # Обновление результата
        search_result.records_found = filter_result.filtered_records
        search_result.filter_statistics = self._build_filter_statistics(
            filter_result
        )
        
        return search_result
    
    def _build_filter_statistics(
        self, 
        filter_result: FilterResult
    ) -> FilterStatistics:
        """Преобразование FilterResult в FilterStatistics."""
        stats = filter_result.stage_statistics
        
        return FilterStatistics(
            stage_1_initial_matches=stats[0]['records_before'] if stats else 0,
            stage_1_description=stats[0]['stage_name'] if stats else "",
            
            stage_2_temperature_filtered=stats[1]['records_after'] if len(stats) > 1 else 0,
            stage_2_description=stats[1]['stage_name'] if len(stats) > 1 else "",
            
            stage_3_phase_selected=stats[2]['records_after'] if len(stats) > 2 else 0,
            stage_3_description=stats[2]['stage_name'] if len(stats) > 2 else "",
            
            stage_4_final_selected=stats[3]['records_after'] if len(stats) > 3 else 0,
            stage_4_description=stats[3]['stage_name'] if len(stats) > 3 else "",
            
            is_found=filter_result.is_found,
            failure_stage=filter_result.failure_stage,
            failure_reason=filter_result.failure_reason
        )
```

**Задачи:**
- [ ] Упростить архитектуру оркестратора
- [ ] Удалить все ссылки на упразднённые агенты
- [ ] Реализовать новый поток обработки
- [ ] Добавить обработку ошибок на каждом шаге

---

### 2. Убрать зависимости от упразднённых агентов

**Удалить:**
- `SQLGenerationAgent`
- `DatabaseAgent`
- `ResultsFilteringAgent`
- `IndividualSearchAgent` (если есть)

**Заменить на:**
- `CompoundSearcher` (из Этапа 2)
- `FilterPipeline` (из Этапа 3)
- `ReactionAggregator` (из Этапа 4)

**Задачи:**
- [ ] Удалить импорты упразднённых агентов
- [ ] Обновить конструктор `ThermoOrchestrator`
- [ ] Проверить отсутствие ссылок на старые агенты

---

### 3. Интегрировать новые модули поиска и агрегации

**Инициализация оркестратора:**
```python
# Инициализация компонентов
sql_builder = SQLBuilder()
db_connector = DatabaseConnector(db_path="data/thermo.db")
compound_searcher = CompoundSearcher(sql_builder, db_connector)

# Настройка конвейера фильтрации
filter_pipeline = FilterPipeline()
filter_pipeline.add_stage(TemperatureFilterStage())
filter_pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
filter_pipeline.add_stage(ReliabilityPriorityStage(max_records=1))

# Форматирование
table_formatter = TableFormatter()
statistics_formatter = StatisticsFormatter()
reaction_aggregator = ReactionAggregator(max_compounds=10)

# Оркестратор
orchestrator = ThermoOrchestrator(
    thermodynamic_agent=thermodynamic_agent,
    compound_searcher=compound_searcher,
    filter_pipeline=filter_pipeline,
    reaction_aggregator=reaction_aggregator,
    table_formatter=table_formatter,
    statistics_formatter=statistics_formatter
)
```

**Задачи:**
- [ ] Обновить инициализацию в `main.py`
- [ ] Добавить конфигурацию компонентов
- [ ] Использовать dependency injection

---

### 4. Обновить форматирование ответов с использованием `tabulate`

**Файл:** `src/thermo_agents/orchestrator.py`

**Метод форматирования:**
```python
def _format_response(self, data: AggregatedReactionData) -> str:
    """
    Форматирование финального ответа пользователю.
    
    Формат:
    ✅ Термодинамические данные для реакции:
       [equation] при [T_range]K
       
    📊 Найденные данные (tabulate):
    [таблица]
    
    📈 Детальная статистика фильтрации:
    [дерево статистики]
    
    ⚠️ Предупреждения:
    [список предупреждений]
    
    ❌ Ненайденные вещества:
    [список]
    """
    lines = []
    
    # Заголовок
    if data.completeness_status == "complete":
        lines.append("✅ Термодинамические данные для реакции:")
    elif data.completeness_status == "partial":
        lines.append("⚠️ Частичные термодинамические данные для реакции:")
    else:
        lines.append("❌ Термодинамические данные для реакции:")
    
    lines.append(f"   {data.reaction_equation}")
    lines.append("")
    
    # Таблица данных (только если есть найденные вещества)
    if data.found_compounds:
        lines.append("📊 Найденные данные:")
        lines.append(data.summary_table_formatted)
        lines.append("")
    
    # Детальная статистика
    lines.append(
        self.statistics_formatter.format_detailed_statistics(
            data.detailed_statistics
        )
    )
    
    # Предупреждения
    if data.warnings:
        lines.append("⚠️ Предупреждения:")
        for warning in data.warnings:
            lines.append(f"   - {warning}")
        lines.append("")
    
    # Ненайденные вещества
    if data.missing_compounds:
        lines.append("❌ Ненайденные вещества:")
        lines.append(f"   {', '.join(data.missing_compounds)}")
        lines.append("")
    
    # Рекомендации
    if data.recommendations:
        lines.append("💡 Рекомендация:")
        for rec in data.recommendations:
            lines.append(f"   {rec}")
        lines.append("")
    
    return "\n".join(lines)

def _format_error_response(self, error_message: str) -> str:
    """Форматирование ответа об ошибке."""
    return f"""
❌ Ошибка обработки запроса:
   {error_message}
   
💡 Попробуйте:
   - Уточнить формулы веществ
   - Указать температурный диапазон
   - Упростить запрос
"""
```

**Задачи:**
- [ ] Реализовать `_format_response()`
- [ ] Реализовать `_format_error_response()`
- [ ] Использовать эмодзи для наглядности
- [ ] Протестировать форматирование на примерах

---

### 5. Добавить вывод детальной статистики фильтрации

**Интеграция `StatisticsFormatter`:**

Уже реализовано в методе `_format_response()` через:
```python
self.statistics_formatter.format_detailed_statistics(
    data.detailed_statistics
)
```

**Задачи:**
- [ ] Убедиться, что статистика выводится для каждого вещества
- [ ] Добавить форматирование для случаев провала фильтрации
- [ ] Протестировать на реакциях с 2-10 веществами

---

## Артефакты этапа

### Файлы для обновления:
1. `src/thermo_agents/orchestrator.py` — полный рефакторинг
2. `main.py` — обновление инициализации
3. `tests/test_orchestrator.py` — обновление тестов

### Файлы для удаления (будут удалены на Этапе 8):
- `src/thermo_agents/sql_generation_agent.py`
- `src/thermo_agents/database_agent.py`
- `src/thermo_agents/results_filtering_agent.py`
- `src/thermo_agents/individual_search_agent.py`

---

## Критерии завершения этапа

✅ **Обязательные:**
1. Оркестратор работает с новой архитектурой
2. Все зависимости от упразднённых агентов удалены
3. Форматирование ответов использует `tabulate`
4. Детальная статистика выводится корректно
5. Все интеграционные тесты проходят

---

## Риски

| Риск                         | Вероятность | Влияние | Митигация                               |
| ---------------------------- | ----------- | ------- | --------------------------------------- |
| Регрессия функциональности   | Средняя     | Высокое | Интеграционные тесты, A/B тестирование  |
| Сложность интеграции модулей | Низкая      | Среднее | Dependency injection, чёткие интерфейсы |

---

## Следующий этап

➡️ **Этап 7:** Тестирование и документация
