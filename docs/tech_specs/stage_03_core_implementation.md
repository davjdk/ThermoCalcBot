# Этап 3: Основная реализация

## 7. Алгоритмы и бизнес-логика

### 7.1 Выбор фазы и температурного диапазона

**Приоритеты выбора записи:**
1. Точное совпадение фазы + температура в диапазоне [Tmin, Tmax]
2. Любая фаза + температура в диапазоне  
3. Указанная фаза + ближайший диапазон
4. Стабильная фаза при заданной температуре (по термодинамическим данным)
5. Запись с наиболее широким температурным покрытием

**Алгоритм разрешения неоднозначности:**
```python
def select_best_record(records: list[SpeciesRecord], target_T: float, phase_hint: str) -> SpeciesRecord:
    # 1. Фильтр по фазе (если указана)
    if phase_hint:
        phase_filtered = [r for r in records if r.phase == phase_hint]
        if phase_filtered:
            records = phase_filtered
    
    # 2. Фильтр по температурному диапазону
    in_range = [r for r in records if r.tmin <= target_T <= r.tmax]
    if in_range:
        # Выбрать наиболее узкий диапазон
        return min(in_range, key=lambda r: r.tmax - r.tmin)
    
    # 3. Ближайший диапазон 
    return min(records, key=lambda r: min(abs(target_T - r.tmin), abs(target_T - r.tmax)))
```

### 7.2 Термодинамические расчёты

**Формула теплоёмкости** (из пользовательской БД):
```python
def calculate_cp(T: float, f1: float, f2: float, f3: float, f4: float, f5: float, f6: float) -> float:
    """Cp в Дж/(моль·К)"""
    return (f1 + f2*T/1000 + f3*T**(-2) * 100_000 + 
            f4*T**2 / 1_000_000 + f5*T**(-3) * 1_000 + 
            f6*T**3 * 10**(-9))
```

**Численное интегрирование:**
```python
from scipy.integrate import quad

def calculate_enthalpy_change(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """ΔH(T) = H298 + ∫[T_ref→T] Cp dT"""
    def cp_func(temp):
        return calculate_cp(temp, species.f1, species.f2, species.f3, 
                          species.f4, species.f5, species.f6)
    
    integral, _ = quad(cp_func, T_ref, T)
    return species.H298_kJ_per_mol * 1000 + integral  # кДж→Дж

def calculate_entropy_change(species: SpeciesRecord, T: float, T_ref: float = 298.15) -> float:
    """ΔS(T) = S298 + ∫[T_ref→T] (Cp/T) dT"""
    def cp_over_t_func(temp):
        return calculate_cp(temp, species.f1, species.f2, species.f3,
                          species.f4, species.f5, species.f6) / temp
    
    integral, _ = quad(cp_over_t_func, T_ref, T)
    return species.S298_J_per_molK + integral
```

### 7.3 Балансировка химических реакций

**Линейная система для элементов:**
```python
import numpy as np
from typing import Dict, List

def balance_reaction(reactants: List[str], products: List[str]) -> Dict[str, float]:
    """Балансировка по элементному составу"""
    # 1. Парсинг формул → элементный состав
    elements = get_all_elements(reactants + products)
    
    # 2. Составление матрицы A·x = 0
    # где x = [коэф_реагентов, коэф_продуктов]
    matrix = build_element_matrix(reactants, products, elements)
    
    # 3. Решение системы (метод наименьших квадратов)
    coefficients = solve_linear_system(matrix)
    
    # 4. Нормализация к целым числам
    return normalize_coefficients(coefficients, reactants, products)

def generate_byproduct_hypotheses(main_products: List[str], available_elements: set) -> List[List[str]]:
    """Генерация гипотез с учётом частых побочных продуктов"""
    common_byproducts = ["CO(g)", "CO2(g)", "H2O(g)", "HCl(g)", "Cl2(g)"]
    
    # Фильтр по доступным элементам
    valid_byproducts = [bp for bp in common_byproducts 
                       if get_elements(bp).issubset(available_elements)]
    
    # Генерация комбинаций
    return generate_combinations(main_products, valid_byproducts)
```

### 7.4 Поиск температуры равновесия  

**Метод бисекции для T_eq:**
```python
def find_equilibrium_temperature(
    participants: List[ReactionParticipant], 
    T_bounds: Tuple[float, float] = (298, 2273),
    tolerance: float = 100.0  # Дж/моль
) -> Optional[float]:
    """Поиск T где ΔG_reaction ≈ 0"""
    
    def delta_g_reaction(T: float) -> float:
        total_dg = 0.0
        for participant in participants:
            species_data = resolve_species(participant.formula, participant.phase, T)
            thermo_point = calculate_properties(species_data, T)
            
            if participant.role == 'product':
                total_dg += participant.coefficient * thermo_point.G
            else:  # reactant
                total_dg -= participant.coefficient * thermo_point.G
        return total_dg
    
    # Проверка смены знака в границах
    dg_low = delta_g_reaction(T_bounds[0])
    dg_high = delta_g_reaction(T_bounds[1])
    
    if dg_low * dg_high > 0:
        return None  # Нет пересечения с осью T
    
    # Бисекция
    T_low, T_high = T_bounds
    while T_high - T_low > 1.0:  # точность 1K
        T_mid = (T_low + T_high) / 2
        dg_mid = delta_g_reaction(T_mid)
        
        if abs(dg_mid) < tolerance:
            return T_mid
            
        if dg_mid * dg_low < 0:
            T_high = T_mid
        else:
            T_low = T_mid
            dg_low = dg_mid
    
    return (T_low + T_high) / 2
```


## 8. Структурированный вывод и валидация

### 8.1 Pydantic AI Output Configuration

**Режим Tool Output** (рекомендуется):
```python
from pydantic_ai import Agent, ToolOutput, ModelSettings

# Агент с типизированным выводом
orchestrator = Agent(
    model="openrouter:anthropic/claude-3.5-sonnet",
    output_type=ToolOutput(UserResponse, name="thermodynamic_analysis"),
    model_settings=ModelSettings(
        temperature=0.1,  # Низкая температура для научных расчётов
        max_tokens=4000,
        timeout=60.0
    )
)

# Output validator для дополнительной проверки
@orchestrator.output_validator
async def validate_thermo_response(ctx: RunContext[AppDeps], output: UserResponse) -> UserResponse:
    """Валидация физической корректности результатов"""
    
    if output.reaction_result:
        # Проверка энергии Гиббса
        if abs(output.reaction_result.delta_G_kJ_per_mol) > 1000:  # >1000 кДж/моль
            raise ModelRetry("Энергия Гиббса физически некорректна")
        
        # Проверка температуры равновесия
        if output.reaction_result.T_equilibrium:
            if not (200 <= output.reaction_result.T_equilibrium <= 3000):
                raise ModelRetry("Температура равновесия вне физически разумных пределов")
    
    return output
```

### 8.2 Форматирование ответа пользователю

**Структура финального ответа:**
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
      "species_found": ["ZrO2(s)", "CCl4(g)", "ZrCl4(g)", "CO2(g)"],
      "temperature_ranges": {
        "ZrO2(s)": "298-2000K",
        "CCl4(g)": "298-1500K"
      },
      "extrapolation_warnings": []
    }
  },
  "summary_ru": "Хлорирование диоксида циркония четырёххлористым углеродом термодинамически возможно при температурах выше 1157K (884°C). Реакция эндотермическая с ΔH = 125.3 кДж/моль.",
  "recommendations": [
    "Проводить реакцию при температуре не ниже 900°C",
    "Учесть образование токсичного угарного газа", 
    "Рекомендуется избыток CCl4 для смещения равновесия"
  ],
  "data_quality": {
    "all_species_found": true,
    "temperature_coverage": "good",
    "confidence_level": "high"
  }
}
```

### 8.3 Обработка ошибок и ретраи

**Автоматические ретраи при:**
- Ошибках валидации Pydantic моделей
- Физически некорректных значениях
- Отсутствии ключевых данных

**Usage Limits для контроля затрат:**
```python
from pydantic_ai import UsageLimits

usage_limits = UsageLimits(
    tool_calls_limit=15,  # Максимум 15 вызовов инструментов
    request_token_limit=8000,  # Лимит токенов на запрос
    response_token_limit=2000   # Лимит токенов в ответе
)

result = orchestrator.run_sync(
    user_query,
    deps=app_deps,
    usage_limits=usage_limits
)
```

### 8.4 Стриминг (опционально)

```python
async def stream_analysis(query: str) -> None:
    """Потоковый анализ с промежуточными результатами"""
    async with orchestrator.run_stream(query, deps=app_deps) as result:
        print("🔍 Анализирую запрос...")
        
        async for text in result.stream_text():
            # Промежуточные результаты для UX
            print(f"📊 {text}")
        
        # Финальный структурированный результат
        final_output = await result.output()
        return final_output
```
