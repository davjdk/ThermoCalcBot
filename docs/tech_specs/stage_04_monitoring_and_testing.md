# Этап 4: Мониторинг и тестирование

## 9. Наблюдаемость и мониторинг

### 9.1 Pydantic Logfire интеграция

```python
import logfire
from pydantic_ai import Agent

# Глобальная конфигурация
logfire.configure(
    service_name="thermodynamic-agents",
    environment="development"
)

# Инструментация Pydantic AI
logfire.instrument_pydantic_ai()
logfire.instrument_sqlite3()  # Для логирования SQL запросов

# Создание агентов с автоматическим логированием
orchestrator = Agent(
    "openrouter:anthropic/claude-3.5-sonnet",
    deps_type=AppDeps,
    output_type=UserResponse
)
# Все вызовы автоматически трассируются в Logfire
```

### 9.2 Метрики производительности

**Отслеживаемые метрики:**
- **Usage по моделям**: токены, запросы, стоимость на провайдера
- **Время выполнения**: общее время + breakdown по агентам
- **Cache hit ratio**: эффективность кэширования БД
- **Errors & retries**: частота ошибок валидации, ретраев
- **Data quality**: процент успешного разрешения веществ

```python
@logfire.instrument("thermodynamic_analysis")
async def analyze_reaction(query: str, deps: AppDeps) -> UserResponse:
    """Анализ реакции с метриками"""
    
    start_time = time.time()
    
    try:
        result = await orchestrator.run(query, deps=deps)
        
        # Логирование успешного результата
        logfire.info("Analysis completed", 
                    duration=time.time() - start_time,
                    tokens_used=result.usage.total_tokens,
                    confidence=result.output.reaction_result.confidence if result.output.reaction_result else None)
        
        return result.output
        
    except Exception as e:
        logfire.error("Analysis failed", error=str(e), duration=time.time() - start_time)
        raise
```

### 9.3 Message History Management

**Стратегии управления историей:**
```python
from pydantic_ai.messages import ModelMessage

async def smart_history_processor(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Умная обрезка истории с сохранением контекста"""
    
    # Сохранить последние N сообщений
    recent_limit = 10
    
    # Обязательно сохранить пары tool call/return
    essential_pairs = []
    for i, msg in enumerate(messages):
        if msg.role == "assistant" and hasattr(msg, 'tool_calls'):
            # Найти соответствующий tool return
            for j in range(i+1, min(i+3, len(messages))):
                if messages[j].role == "tool":
                    essential_pairs.extend([msg, messages[j]])
                    break
    
    # Объединить recent + essential
    recent_messages = messages[-recent_limit:]
    return list(dict.fromkeys(essential_pairs + recent_messages))  # Дедупликация

# Применение к агенту
orchestrator = Agent(
    "openrouter:anthropic/claude-3.5-sonnet",
    history_processors=[smart_history_processor]
)
```

### 9.4 Сохранение и воспроизводимость

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter
import json
from datetime import datetime

async def save_analysis_session(result: RunResult[UserResponse], query: str) -> str:
    """Сохранение сессии для воспроизводимости"""
    
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "output": result.output.model_dump(),
        "usage": result.usage.model_dump(),
        "messages": ModelMessagesTypeAdapter.dump_python(result.all_messages())
    }
    
    session_id = f"session_{int(time.time())}"
    with open(f"logs/{session_id}.json", "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    
    return session_id

async def replay_analysis_session(session_id: str) -> UserResponse:
    """Воспроизведение анализа из сохранённой сессии"""
    
    with open(f"logs/{session_id}.json", "r", encoding="utf-8") as f:
        session_data = json.load(f)
    
    # Восстановление истории сообщений
    messages = ModelMessagesTypeAdapter.validate_python(session_data["messages"])
    
    # Повторный запуск с той же историей
    result = await orchestrator.run(
        session_data["query"],
        message_history=messages[:-1],  # Исключить последний ответ
        deps=app_deps
    )
    
    return result.output
```


## 10. Тестовые сценарии (E2E)

### 10.1 Сценарий 1: Хлорирование оксида циркония

**Запрос пользователя:**
> "Возможно ли хлорирование оксида циркония четыреххлористым углеродом? При какой температуре начнется реакция?"

**Ожидаемый процесс:**
1. **Парсинг запроса**: Orchestrator определяет тип задачи - анализ реакции
2. **Резолвинг веществ**: DB Resolver находит ZrO2(s), CCl4(g/l)
3. **Генерация гипотез**: Reactions Analyzer предлагает варианты:
   - `ZrO2(s) + CCl4(g) → ZrCl4(g) + CO2(g)`
   - `ZrO2(s) + 2CCl4(g) → ZrCl4(g) + 2COCl2(g)`
   - `ZrO2(s) + CCl4(g) → ZrCl4(g) + CO(g) + 1/2O2(g)`
4. **Термодинамический анализ**: Расчёт ΔG для каждой гипотезы
5. **Поиск T_eq**: Бисекция для лучшей реакции в диапазоне 400-1500K

**Ожидаемый результат:**
```json
{
  "query_type": "reaction_analysis",
  "reaction_result": {
    "balanced_equation": "ZrO2(s) + CCl4(g) → ZrCl4(g) + CO2(g)",
    "delta_H_kJ_per_mol": 125.3,
    "delta_S_J_per_molK": 89.7, 
    "delta_G_kJ_per_mol": -18.2,
    "feasible_at_T": true,
    "T_equilibrium": 1156.8,
    "confidence": 0.85,
    "diagnostics": {
      "alternative_reactions_considered": 3,
      "best_reaction_reason": "Минимальная энергия Гиббса",
      "species_data_quality": "good"
    }
  },
  "summary_ru": "Хлорирование диоксида циркония четырёххлористым углеродом термодинамически возможно при температурах выше 1157K (884°C). Реакция эндотермическая.",
  "recommendations": [
    "Проводить реакцию при температуре не ниже 900°C",
    "Обеспечить хорошую вентиляцию из-за токсичных продуктов"
  ]
}
```

### 10.2 Сценарий 2: Хлорирование оксида титана

**Запрос пользователя:**
> "Возможна ли реакция оксида титана с хлором при 700 градусах в присутствии метана?"

**Ожидаемый процесс:**
1. **Конвертация температуры**: 700°C = 973.15K
2. **Резолвинг веществ**: TiO2(s), Cl2(g), CH4(g) 
3. **Генерация гипотез**:
   - `TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO2(g) + 2H2(g)`
   - `TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO(g) + 2HCl(g)`
   - `TiO2(s) + 4HCl(g) → TiCl4(g) + 2H2O(g)` (если CH4 дает HCl)
4. **Анализ при T=973.15K**: Расчёт ΔG для каждой реакции
5. **Оценка осуществимости**: Проверка ΔG < 0

**Ожидаемый результат:**
```json
{
  "query_type": "reaction_analysis", 
  "reaction_result": {
    "balanced_equation": "TiO2(s) + 2Cl2(g) + CH4(g) → TiCl4(g) + CO2(g) + 2H2(g)",
    "delta_H_kJ_per_mol": -89.4,
    "delta_S_J_per_molK": 145.2,
    "delta_G_kJ_per_mol": -230.8,
    "feasible_at_T": true,
    "T_equilibrium": null,
    "confidence": 0.78,
    "diagnostics": {
      "evaluation_temperature": 973.15,
      "methane_role": "reducing_agent",
      "byproduct_uncertainty": "moderate"
    }
  },
  "summary_ru": "Реакция оксида титана с хлором в присутствии метана при 700°C термодинамически возможна (ΔG = -230.8 кДж/моль). Метан выступает как восстановитель.",
  "recommendations": [
    "Реакция сильно экзотермическая - контролировать температуру",
    "Возможно образование различных побочных продуктов (CO/CO2, H2/HCl)"
  ]
}
```

### 10.3 Критерии успешности тестов

**Обязательные требования:**
- [x] Корректное распознавание типа запроса
- [x] Успешное разрешение всех веществ из БД  
- [x] Физически разумные значения ΔH, ΔS, ΔG
- [x] Температура равновесия в диапазоне 200-3000K (если найдена)
- [x] Краткое резюме на русском языке
- [x] Структурированный JSON в соответствии с UserResponse схемой

**Дополнительные проверки:**
- Время выполнения < 30 секунд  
- Использование токенов < 10,000
- Количество вызовов инструментов < 15
- Confidence score > 0.7 для найденных реакций
- Диагностическая информация о качестве данных
