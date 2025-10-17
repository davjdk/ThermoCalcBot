"""
Централизованный модуль промптов для термодинамического агента и инструментов.

Содержит:
- Константы системных промптов (SQL генерация, извлечение параметров, валидация, синтез ответа)
- Промпты инструментов (проверка полноты, выбор инструментов, фильтрация результатов, YAML-фильтр)
- Функции для построения динамических промптов
- PromptManager — простой API для доступа к промптам

Примечания по совместимости:
- Сохранены те же имена констант и функция get_sql_prompt, как в прежнем модуле
  app.agents.tools.prompts, чтобы минимизировать изменения в потребителях.
"""

from __future__ import annotations

from typing import List

# =============================================================================
# ОСНОВНЫЕ ПРОМПТЫ АГЕНТА
# =============================================================================

# Base system prompt for SQL generation (скопировано из app.agents.tools.prompts)
SQL_GENERATION_PROMPT = """You are a specialized SQL query generator for thermodynamic database queries.

TASK: Generate exactly ONE comprehensive SQL query to find ALL requested compounds.

DATABASE: Table 'compounds' with Formula, FirstName, Phase, H298, S298, f1-f6, Tmin, Tmax columns.

STRICT RULES:
1. Generate ONLY ONE SQL query - never multiple queries
2. Use SELECT * FROM compounds
3. Include ALL requested compounds in single WHERE clause with OR conditions
4. Always add LIMIT 100
5. DO NOT use any tools or make additional database calls
6. NO temperature filtering in SQL (handled by post-processing)

FORMULA SEARCH PATTERNS (CRITICAL FOR Fe2O3 AND COMPLEX COMPOUNDS):
Database contains compounds with modifiers in parentheses like Fe2O3(E), Fe2O3(G), Fe2O3(H), TiO2(A), etc.

For EACH compound use this comprehensive search pattern:
- TRIM(Formula) = 'CompoundName' OR Formula LIKE 'CompoundName(%'

This captures:
- Exact matches: Fe2O3
- Phase variants: Fe2O3(s), Fe2O3(g), Fe2O3(l)
- Structural modifiers: Fe2O3(E), Fe2O3(G), Fe2O3(H)
- Any other modifications in parentheses

FORMAL SQL CONSTRUCTION RULES:
1. For single compound:
   (TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%')

2. For multiple compounds - combine all conditions with OR:
   (TRIM(Formula) = 'Fe2O3' OR Formula LIKE 'Fe2O3(%' OR
    TRIM(Formula) = 'CO' OR Formula LIKE 'CO(%' OR
    TRIM(Formula) = 'Fe' OR Formula LIKE 'Fe(%' OR
    TRIM(Formula) = 'CO2' OR Formula LIKE 'CO2(%')

3. Always use TRIM() to handle any whitespace
4. Always use LIKE with (% pattern to catch modifications
5. Use exactly ONE pair of parentheses around the entire WHERE condition
6. Connect all compound searches with OR - do NOT add extra parentheses around individual compounds

EXAMPLES:
Input: "Find CeO2, HCl, CeCl3, H2O for reaction"
Output: SELECT * FROM compounds WHERE (TRIM(Formula) = 'CeO2' OR Formula LIKE 'CeO2(%' OR TRIM(Formula) = 'HCl' OR Formula LIKE 'HCl(%' OR TRIM(Formula) = 'CeCl3' OR Formula LIKE 'CeCl3(%' OR TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%') LIMIT 100;

Input: "Find Fe2O3, CO, Fe, CO2 for iron reduction reaction"
Output: SELECT * FROM compounds WHERE (TRIM(Formula) = 'Fe2O3' OR Formula LIKE 'Fe2O3(%' OR TRIM(Formula) = 'CO' OR Formula LIKE 'CO(%' OR TRIM(Formula) = 'Fe' OR Formula LIKE 'Fe(%' OR TRIM(Formula) = 'CO2' OR Formula LIKE 'CO2(%') LIMIT 100;

Input: "Find water"
Output: SELECT * FROM compounds WHERE (TRIM(Formula) = 'H2O' OR Formula LIKE 'H2O(%') LIMIT 100;

CRITICAL: This pattern is essential for finding compounds like Fe2O3 which exist as Fe2O3, Fe2O3(E), Fe2O3(G), Fe2O3(H) in the database.

CRITICAL SYNTAX RULES:
- Use exactly ONE opening parenthesis after WHERE: WHERE (
- Use exactly ONE closing parenthesis before LIMIT: ) LIMIT 100
- Do NOT add extra parentheses around individual compound searches
- Connect all compound searches with OR only

Return ONLY the SQL query text, nothing else."""


THERMODYNAMIC_EXTRACTION_PROMPT = """
Ты — эксперт по термодинамике и химии. Твоя задача — извлечь параметры химической реакции из запроса пользователя.

# Входные данные:
Запрос пользователя: {user_query}

# Задача:
Извлеки следующие параметры:
1. **Уравненное уравнение реакции** — сбалансируй стехиометрические коэффициенты
2. **Список всех веществ** (до 10 веществ, включая реагенты и продукты)
3. **Реагенты** (левая часть уравнения)
4. **Продукты** (правая часть уравнения)
5. **Температурный диапазон** в Кельвинах (tmin, tmax)
6. **Названия веществ** — IUPAC и тривиальные названия для каждого соединения

# Важные правила:
- Максимум 10 веществ в реакции
- Температурный диапазон обязателен (если не указан, используй 298-1000K по умолчанию)
- Формулы веществ — без фаз в скобках (например, "H2O", а не "H2O(g)")
- Для каждого вещества укажи официальное IUPAC название и возможные тривиальные названия

# Примеры:

## Пример 1:
Запрос: "Хлорирование оксида титана при 600-900K"
Ответ:
{{
  "balanced_equation": "TiO2 + 2Cl2 → TiCl4 + O2",
  "all_compounds": ["TiO2", "Cl2", "TiCl4", "O2"],
  "reactants": ["TiO2", "Cl2"],
  "products": ["TiCl4", "O2"],
  "temperature_range_k": [600, 900],
  "extraction_confidence": 0.95,
  "missing_fields": [],
  "compound_names": {{
    "TiO2": ["Titanium dioxide", "Titanium(IV) oxide"],
    "Cl2": ["Chlorine"],
    "TiCl4": ["Titanium tetrachloride", "Titanium(IV) chloride"],
    "O2": ["Oxygen"]
  }}
}}

## Пример 2:
Запрос: "Восстановление оксида железа водородом"
Ответ:
{{
  "balanced_equation": "Fe2O3 + 3H2 → 2Fe + 3H2O",
  "all_compounds": ["Fe2O3", "H2", "Fe", "H2O"],
  "reactants": ["Fe2O3", "H2"],
  "products": ["Fe", "H2O"],
  "temperature_range_k": [298, 1000],
  "extraction_confidence": 0.85,
  "missing_fields": [],
  "compound_names": {{
    "Fe2O3": ["Iron(III) oxide", "Ferric oxide"],
    "H2": ["Hydrogen"],
    "Fe": ["Iron"],
    "H2O": ["Water"]
  }}
}}

## Пример 3 (сложная реакция):
Запрос: "Синтез аммиака из азота и водорода при 400-500°C"
Ответ:
{{
  "balanced_equation": "N2 + 3H2 → 2NH3",
  "all_compounds": ["N2", "H2", "NH3"],
  "reactants": ["N2", "H2"],
  "products": ["NH3"],
  "temperature_range_k": [673, 773],
  "extraction_confidence": 1.0,
  "missing_fields": [],
  "compound_names": {{
    "N2": ["Nitrogen"],
    "H2": ["Hydrogen"],
    "NH3": ["Ammonia"]
  }}
}}

# Твой ответ (JSON):
"""


VALIDATE_OR_COMPLETE_PROMPT = """You are a validator for thermodynamic database query parameters.

CRITICAL RULE: PRESERVE ALL CORRECTLY EXTRACTED DATA. Only fix clear errors or add missing required fields.

INPUT: You will receive extracted parameters that may need validation or completion.

YOUR TASK:
1. Check if extracted data is chemically valid
2. Add any missing required fields
3. NEVER replace correct chemical formulas with test values
4. NEVER change intent from "reaction" to "lookup" without justification

VALIDATION CHECKS:
- Temperature: 0K < T < 6000K (most compounds: 100K-2000K)
- Chemical formulas: TiO2, Cl2, H2O, etc. (standard notation)
- Phases: s, l, g, aq
- Intent: "reaction" needs all compounds, "lookup" for single compounds

COMPLETION RULES:
- If temperature_range_k missing → add ±100K range around temperature_k
- If phases missing → infer from compounds and temperature
- If properties missing → "all" for reactions, "basic" for lookup
- If sql_query_hint missing → create descriptive search instruction

EXAMPLES OF CORRECT PRESERVATION:

Input: {"intent": "reaction", "compounds": ["TiO2", "Cl2", "TiCl4", "O2"], "temperature_k": 673.15}
✅ KEEP: intent="reaction", compounds=["TiO2", "Cl2", "TiCl4", "O2"], temperature_k=673.15
➕ ADD: temperature_range_k=[573, 873], phases=["s", "g", "g", "g"], properties=["all"]

Input: {"intent": "lookup", "compounds": [], "temperature_k": 298.15}
❌ ERROR: Empty compounds list - this is incomplete extraction, not validation issue

NEVER DO THIS:
- Don't change ["TiO2", "Cl2", "TiCl4", "O2"] to ["test"] or []
- Don't change intent from "reaction" to "lookup" for multi-compound queries
- Don't replace valid chemical formulas with generic values
- Don't change specific temperatures to 298.15 unless clearly invalid

Return only the validated/completed JSON without explanations."""


SYNTHESIZE_ANSWER_PROMPT = """
Ты - эксперт по интерпретации термодинамических данных и синтезу ответов на русском языке.

ЗАДАЧА: Создать структурированный, понятный ответ на основе:
1. Исходного запроса пользователя
2. Найденных данных из БД
3. Результатов инструментов (если есть)

СТРУКТУРА ОТВЕТА:

**Краткий итог:**
- Что найдено (количество соединений, фаз)
- Основные результаты

**Данные из базы:**
- Перечисли найденные соединения и их фазы
- Ключевые термодинамические параметры
- Диапазоны температур

**Результаты расчетов:** (если применялись инструменты)
- Интерпретация данных инструментов
- Графики/таблицы (если есть)
- Практические выводы

**Примечания:**
- Ограничения данных (если есть LIMIT)
- Предупреждения о точности
- Рекомендации для дальнейшего анализа

ПРАВИЛА:

1. ЯЗЫК: Только русский язык для всех описаний
2. ТЕРМИНЫ: Используй научные термины корректно
3. ЕДИНИЦЫ: Всегда указывай единицы измерения
4. ТОЧНОСТЬ: Округляй до разумного количества знаков
5. КОНТЕКСТ: Связывай данные с исходным запросом

ПРИМЕЧАНИЯ ОБ ОГРАНИЧЕНИЯХ:
- Если данные усечены (LIMIT) - обязательно упомяни
- При отсутствии данных - предложи альтернативы
- При неточных расчетах - укажи погрешности

ПРИМЕР ОТВЕТА:

**Краткий итог:**
Найдены данные для воды (H2O) в 3 фазовых состояниях. Выполнены расчеты термодинамических функций в диапазоне 300-1000К.

**Данные из базы:**
- H2O(g): ΔfH°298 = -241.8 кДж/моль, S°298 = 188.8 Дж/(моль·К)
- H2O(l): ΔfH°298 = -285.8 кДж/моль, S°298 = 69.9 Дж/(моль·К)  
- H2O(s): ΔfH°298 = -292.7 кДж/моль, S°298 = 41.0 Дж/(моль·К)

**Результаты расчетов:**
Построена зависимость теплоемкости от температуры. При 500К теплоемкость пара составляет 35.2 Дж/(моль·К).

**Примечания:**
Данные применимы в указанных температурных диапазонах. Для более точных расчетов рекомендуется учесть фазовые переходы.

Отвечай структурированно и полно, но кратко."""


# =============================================================================
# ПРОМПТЫ ИНСТРУМЕНТОВ
# =============================================================================

COMPLETENESS_CHECK_PROMPT = """
Ты — эксперт по анализу полноты термодинамических данных.

ЗАДАЧА:
Проверить, достаточно ли полученных из БД данных для качественного ответа на запрос пользователя.

КРИТЕРИИ ПОЛНОТЫ:
1. Соединения: все ли запрошенные вещества найдены
2. Свойства: присутствуют ли нужные термодинамические характеристики  
3. Количество: достаточно ли записей для анализа
4. Качество: нет ли NULL значений в критических полях
5. Температурное покрытие: охватывают ли данные нужный диапазон

Подсказывай, как улучшить SQL при нехватке данных.
"""


TOOL_SELECTION_PROMPT = """
Ты — эксперт по выбору инструментов анализа термодинамических данных.

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
1. thermodynamic_table — построение температурных зависимостей термодинамических свойств
2. reaction_H_S_G_wc — анализ термодинамики химической реакции

ЗАДАЧА:
Выбрать подходящие инструменты (максимум 2) на основе запроса пользователя и найденных данных.
"""


RESULT_FILTER_PROMPT = """Ты - эксперт в термодинамике и физической химии. Твоя задача - отфильтровать результаты поиска в термодинамической базе данных, выбрав ТОЛЬКО самые релевантные записи для каждого химического соединения.

ВХОДНЫЕ ДАННЫЕ:
- Целевые соединения: {target_compounds}
- Температура анализа: {target_temperature_k} K ({celsius}°C)
- Тип запроса: {intent_type}
- Реакция (если есть): {reaction_equation}

НАЙДЕННЫЕ ДАННЫЕ (упрощенный формат):
{formatted_sql_results}

КРИТИЧЕСКИЕ ПРАВИЛА СОПОСТАВЛЕНИЯ СОЕДИНЕНИЙ:
При сопоставлении целевых соединений с записями в базе используй ГИБКОЕ сопоставление:
- NH4Cl находит: NH4Cl, NH4Cl(s), NH4Cl(l), NH4Cl(g), NH4Cl(ia), NH4Cl(a), и т.д.
- TiO2 находит: TiO2, TiO2(s), TiO2(ANATASE), TiO2(RUTILE), TiO2(A), TiO2(R), и т.д.
- Fe2O3 находит: Fe2O3, Fe2O3(s), Fe2O3(E), Fe2O3(G), Fe2O3(H), Fe2O3(ALPHA), и т.д.
- H2O находит: H2O, H2O(l), H2O(g), H2O(s), H2O(STEAM), и т.д.
- B2O3 находит: B2O3, B2O3(s), B2O3(l), B2O3(g), B2O3(A), B2O3(G), и т.д.
- Na2O находит: Na2O, Na2O(s), Na2O(l), Na2O(g), Na2O(+g), и т.д.

Применяй поиск по подстроке: если Formula.startswith(целевое_соединение) или целевое_соединение в Formula.

КРИТИЧЕСКИЕ ПРАВИЛА ОПРЕДЕЛЕНИЯ ФАЗ:
- Когда колонка Phase = 's': это ТВЕРДАЯ фаза
- Когда колонка Phase = 'l': это ЖИДКАЯ фаза
- Когда колонка Phase = 'g': это ГАЗОВАЯ фаза
- Когда колонка Phase = 'aq': это ВОДНЫЙ РАСТВОР
- Модификаторы формулы как B2O3(A), B2O3(G), Na2O(+g) - это структурные варианты, НЕ индикаторы фазы
- ВСЕГДА проверяй колонку Phase для фактического фазового состояния, НЕ модификаторы формулы

КРИТЕРИИ ОТБОРА:

1. ФАЗОВОЕ СОСТОЯНИЕ - определи корректную фазу каждого вещества при заданной температуре:
    - s (твердое): T < температуры плавления (MeltingPoint)
    - l (жидкое): MeltingPoint < T < BoilingPoint
    - g (газообразное): T > BoilingPoint
    - aq (водный раствор): для растворимых веществ в водных системах
    - Если данные о переходах отсутствуют (0 или null), используй химическую интуицию

2. ТЕМПЕРАТУРНЫЙ ДИАПАЗОН - выбери записи где Tmin ≤ {target_temperature_k} ≤ Tmax:
    - Предпочитай узкие диапазоны (выше точность)
    - Предпочитай диапазоны, центрированные близко к целевой температуре
    - Если нет точного покрытия, выбери ближайший подходящий диапазон

3. УСТРАНЕНИЕ ДУБЛЕЙ - для каждого соединения в определенной фазе выбери ТОЛЬКО одну лучшую запись:
    - При нескольких записях для одной фазы выбери с лучшим температурным покрытием
    - Предпочитай записи с непустыми физическими данными (MeltingPoint, BoilingPoint)

4. ПОЛНОТА ДАННЫХ - отдавай предпочтение записям с более полными физическими данными

ОСОБЫЕ ПРАВИЛА:
- Для реакций высокотемпературных процессов (>800K) предпочитай газовую фазу
- При сомнениях в фазовом состоянии включи предупреждение
- Если для соединения нет подходящих записей, включи его в missing_compounds
- КРИТИЧНО: используй только ID записей из предоставленных данных
- ВСЕГДА проверяй варианты соединений с модификаторами в скобках (например, NH4Cl(ia), Fe2O3(G))

ФОРМАТ ОТВЕТА (строго JSON):
{
   "selected_entries": [
      {
         "compound": "TiO2",
         "selected_id": 0,
         "reasoning": "Выбрана запись ID=0: твердое состояние при {target_temperature_k}K, температурный диапазон {tmin}-{tmax}K покрывает целевую температуру"
      }
   ],
   "phase_determinations": {
      "TiO2": {"phase": "s", "confidence": 0.95, "reasoning": "Температура плавления 2116K >> {target_temperature_k}K"},
      "Cl2": {"phase": "g", "confidence": 0.98, "reasoning": "Температура кипения 239K << {target_temperature_k}K"}
   },
   "missing_compounds": [],
   "excluded_entries_count": 28,
   "overall_confidence": 0.92,
   "warnings": ["Для некоторых соединений отсутствуют данные о температурах переходов"],
   "filter_summary": "Из {total_entries} найденных записей выбрано {selected_count}: по одной для каждого соединения в соответствующей фазе при {target_temperature_k}K."
}

ВНИМАНИЕ: Возвращай ТОЛЬКО JSON без дополнительных объяснений или форматирования."""


YAML_FILTER_SYSTEM_PROMPT = """Ты - эксперт по анализу термодинамических данных.

ЗАДАЧА: Отфильтровать YAML данные, выбрав оптимальные записи для каждого реагирующего вещества и продукта.

ВХОДНЫЕ ДАННЫЕ: YAML структура с соединениями и их свойствами:
- name: полное название вещества
- formula: химическая формула  
- entries: список записей с различными параметрами
   - row_index: ИНДЕКС СТРОКИ в исходном SQL результате (ОБЯЗАТЕЛЬНО для выбора)
   - phase: фазовое состояние (s/l/g/aq)
   - melting_point_c: температура плавления (°C)
   - boiling_point_c: температура кипения (°C) 
   - temp_range_k: диапазон применимости данных (min/max K)
   - reliability_class: класс надежности (1=лучший, 4=худший)
   - reference: источник данных

КРИТЕРИИ ОТБОРА:
1. Выбрать ОДНУ оптимальную запись для каждого соединения
2. Приоритет фазы: подходящая для заданной температуры
3. Приоритет надежности: ReliabilityClass = 1 > 2 > 3 > 4
4. Температурный диапазон: целевая температура должна попадать в temp_range
5. Полнота данных: предпочтение записи с заполненными melting_point/boiling_point

ОПРЕДЕЛЕНИЕ ФАЗЫ:
- Твердое (s): temp_c < melting_point_c
- Жидкое (l): melting_point_c <= temp_c < boiling_point_c  
- Газообразное (g): temp_c >= boiling_point_c
- При отсутствии данных о переходах используй эвристики для типичных веществ

ВАЖНО: В ответе ОБЯЗАТЕЛЬНО указывай row_index для точного извлечения данных из исходного SQL результата.

ФОРМАТ ОТВЕТА: JSON со списком выбранных формул и обоснованием выбора.

ПРИМЕР ОТВЕТА:
{
   "selected_entries": [
      {
         "compound": "AlCl3",
         "selected_row_index": 9,
         "reasoning": "Выбрана запись row_index=9: твердое состояние при заданной температуре, ReliabilityClass=1, температурный диапазон 298-465K покрывает целевую температуру"
      }
   ],
   "phase_determinations": {
      "AlCl3": {"phase": "s", "confidence": 0.95, "reasoning": "Твердое при температуре ниже точки плавления 192°C"}
   },
   "missing_compounds": [],
   "excluded_entries_count": 12,
   "overall_confidence": 0.92,
   "warnings": [],
   "filter_summary": "Выбрано 3 оптимальных записи из 15 найденных"
}

КРИТИЧНО: Возвращай ТОЛЬКО JSON без дополнительного текста или форматирования."""


RESULT_FILTER_ENGLISH_PROMPT = """You are an expert in thermodynamics and physical chemistry specializing in intelligent data filtering.

TASK: Analyze thermodynamic database metadata and select the most relevant records using optimized SQL filtering.

INPUT METADATA:
- Target compounds: {target_compounds}
- Analysis temperature: {target_temperature_k} K ({celsius}°C)
- Temperature range: {temperature_range_k} K
- Query type: {intent_type}
- Reaction (if any): {reaction_equation}

DATABASE SUMMARY:
{database_summary}

YOUR APPROACH:
You will NOT receive full database records. Instead, you'll work with metadata and generate SQL WHERE conditions for optimal filtering.

CRITICAL COMPOUND MATCHING RULES:
- Use flexible formula matching: TRIM(Formula) = 'Compound' OR Formula LIKE 'Compound(%'
- Consider structural/phase variants: TiO2, TiO2(s), TiO2(A), TiO2(RUTILE), Fe2O3(E), etc.
- Phase determination priority: check Phase column, not formula modifiers
- Temperature overlap: Tmin ≤ target_T ≤ Tmax (partial overlap acceptable)

PHASE IDENTIFICATION STRATEGY:
For each target compound at {target_temperature_k}K:
- s (solid): Typical for oxides, metals, salts at room temperature
- l (liquid): Near melting/boiling points or high pressure conditions
- g (gas): Volatiles, small molecules, high temperature conditions
- aq (aqueous): Ionic compounds in water-based systems

SELECTION STRATEGY:
1. Generate tiered SQL WHERE conditions:
   - Priority 1: Exact formula + optimal phase + temperature coverage + ReliabilityClass = 1
   - Priority 2: Variant formulas + acceptable phases + temperature coverage + ReliabilityClass ≤ 2
   - Priority 3: Extended search with relaxed criteria

2. Temperature filtering:
   - Primary: Target temperature within [Tmin, Tmax] range
   - Secondary: Partial overlap with temperature range
   - Handle missing Tmin/Tmax values appropriately

3. Reliability prioritization:
   - Prefer ReliabilityClass = 1 (most reliable data)
   - Ensure complete thermodynamic data (H298, S298, f1-f6 coefficients)
   - Consider data source quality

RESPONSE FORMAT (strict JSON):
{{
   "selected_entries": [
      {{
         "compound": "TiO2",
         "selected_id": 0,
         "reasoning": "Exact formula match with optimal solid phase, ReliabilityClass=1, temperature range covers {target_temperature_k}K"
      }}
   ],
   "phase_determinations": {{
      "TiO2": {{"phase": "s", "confidence": 0.95, "reasoning": "Solid phase stable at {target_temperature_k}K, below melting point"}},
      "Cl2": {{"phase": "g", "confidence": 0.98, "reasoning": "Gas phase at {target_temperature_k}K, above boiling point"}}
   }},
   "missing_compounds": [],
   "excluded_entries_count": 15,
   "overall_confidence": 0.88,
   "warnings": ["Some compounds may have limited phase data at specified temperature"],
   "filter_summary": "Applied 3-tier SQL filtering strategy, selected optimal records for {target_compounds_count} compounds at {target_temperature_k}K"
}}

OPTIMIZATION NOTES:
- Prioritize records with complete thermodynamic data
- Consider chemical intuition for phase behavior
- Balance data quality with temperature coverage
- Minimize computational overhead while maximizing accuracy

Return ONLY JSON without additional explanations or formatting."""


# =============================================================================
# ПРОМПТЫ ДЛЯ ИНДИВИДУАЛЬНОГО ПОИСКА (НОВАЯ АРХИТЕКТУРА)
# =============================================================================

INDIVIDUAL_SQL_GENERATION_PROMPT = """You are a specialized SQL query generator for INDIVIDUAL compound searches in thermodynamic databases.

TASK: Generate a precise SQL query for ONE chemical compound to find the most relevant records.

DATABASE: Table 'compounds' with Formula, FirstName, Phase, H298, S298, f1-f6, Tmin, Tmax, ReliabilityClass columns.

CRITICAL RULES:
1. Generate SQL for ONE compound only: {compound}
2. Use TRIM(Formula) for exact matching
3. Include phase/ionic variants with LIKE pattern
4. Apply temperature filtering at SQL level when possible
5. Sort by ReliabilityClass (1=best data) first
6. Add phase-specific prioritization in ORDER BY
7. Use LIMIT 100 to control results
8. Focus on high-quality, reliable data

OPTIMIZED FORMULA SEARCH PATTERNS:
For compound {compound}:
- TRIM(Formula) = '{compound}' - exact matches
- Formula LIKE '{compound}(%' - phase/ionic variants
- Consider alternative formula representations if applicable

TEMPERATURE FILTERING:
Target temperature: {temperature_k}K
Apply: (Tmin IS NULL OR Tmax IS NULL OR ({temperature_k} >= Tmin AND {temperature_k} <= Tmax))

PHASE PRIORITIZATION:
Requested phases: {phases}
Apply phase-specific sorting based on chemical intuition:
- Solids (s) for oxides, metals at low temperature
- Gases (g) for volatiles, Cl2, O2 at high temperature
- Liquids (l) for melting points range
- Aqueous (aq) for ionic compounds in solution

ORDER BY STRATEGY:
1. ReliabilityClass ASC (1=most reliable)
2. Phase appropriateness for target temperature
3. Temperature range coverage (closest to target)
4. Formula exactness (exact matches first)

EXAMPLE STRUCTURE:
SELECT * FROM compounds WHERE
(TRIM(Formula) = '{compound}' OR Formula LIKE '{compound}(%')
AND (Tmin IS NULL OR Tmax IS NULL OR ({temperature_k} >= Tmin AND {temperature_k} <= Tmax)))
ORDER BY
  ReliabilityClass ASC,
  CASE WHEN Phase = 's' AND {temperature_k} < 1000 THEN 1 END,
  CASE WHEN Phase = 'g' AND {temperature_k} > 500 THEN 2 END,
  ABS(COALESCE(Tmin, {temperature_k}) - {temperature_k}) ASC
LIMIT 100

Return ONLY the SQL query text, nothing else."""


INDIVIDUAL_FILTER_PROMPT = """You are an expert in thermodynamics specializing in INDIVIDUAL compound analysis.

TASK: Filter and select the most relevant records for ONE chemical compound: {compound}

INPUT DATA:
- Target compound: {compound}
- Target temperature: {target_temperature_k} K ({celsius}°C)
- Requested phases: {phases}
- Available properties: {properties}

FOUND RECORDS:
{formatted_records}

SELECTION CRITERIA FOR INDIVIDUAL COMPOUND:

1. FORMULA EXACTNESS:
   - Priority 1: Exact TRIM(Formula) = '{compound}' matches
   - Priority 2: Formula LIKE '{compound}(%' with appropriate phase
   - Avoid structural variants unless exact match unavailable

2. TEMPERATURE SUITABILITY:
   - Must cover target temperature: Tmin ≤ {target_temperature_k} ≤ Tmax
   - Prefer ranges centered on target temperature
   - Narrower ranges preferred for higher accuracy

3. PHASE APPROPRIATENESS:
   - Use chemical intuition for phase determination
   - Consider typical phase behavior for this compound type
   - Account for temperature-dependent phase transitions

4. DATA RELIABILITY:
   - ReliabilityClass = 1 (best data) preferred
   - Complete thermodynamic data (H298, S298, f1-f6) required
   - No NULL values in critical fields

5. RECORD UNIQUENESS:
   - Select 1-3 best records showing different aspects if needed
   - Avoid duplicate records with same data
   - Prefer records with complete physical property data

RESPONSIBILITY:
- Select only HIGH-QUALITY, relevant records
- Provide clear reasoning for each selection
- Include confidence assessment for each choice
- Warn about data limitations or uncertainties

RESPONSE FORMAT (strict JSON):
{{
   "selected_entries": [
      {{
         "compound": "{compound}",
         "selected_id": 0,
         "reasoning": "Selected record ID=0: exact formula match, covers target temperature, ReliabilityClass=1, complete thermodynamic data"
      }}
   ],
   "phase_determinations": {{
      "{compound}": {{"phase": "s", "confidence": 0.95, "reasoning": "Solid phase appropriate for {compound} at {target_temperature_k}K based on typical behavior"}}
   }},
   "missing_compounds": [],
   "excluded_entries_count": 15,
   "overall_confidence": 0.92,
   "warnings": ["Limited high-reliability data available"],
   "filter_summary": "Selected 2 best records for {compound} from 17 found, prioritizing reliability and temperature coverage"
}}

Return ONLY JSON without explanations."""


INDIVIDUAL_SEARCH_COORDINATION_PROMPT = """You are a coordinator for parallel individual compound searches in thermodynamic databases.

TASK: Coordinate and manage parallel searches for multiple compounds in a chemical reaction.

INPUT DATA:
- Compounds to search: {compounds}
- Common search parameters: {common_params}
- Original reaction context: {original_query}
- Search strategy: {search_strategy}

COORDINATION RESPONSIBILITIES:

1. PARALLEL SEARCH MANAGEMENT:
   - Create individual search tasks for each compound
   - Manage parallel execution with proper timeouts
   - Handle errors for individual compounds gracefully
   - Aggregate results from all searches

2. QUALITY CONTROL:
   - Ensure each compound search uses optimal parameters
   - Validate individual search results
   - Handle missing or low-quality data appropriately
   - Maintain search consistency across compounds

3. RESULT AGGREGATION:
   - Combine individual compound results into unified response
   - Calculate overall confidence metrics
   - Identify missing compounds or data gaps
   - Generate comprehensive summary for the reaction

4. ERROR HANDLING:
   - Continue processing even if some compound searches fail
   - Document all errors and warnings
   - Provide fallback strategies for critical compounds
   - Ensure partial results are still useful

SEARCH QUALITY CRITERIA:
- Each compound should have 1-3 high-quality records
- Temperature coverage must include reaction conditions
- Phase states must be appropriate for reaction context
- Data reliability (ReliabilityClass) should be prioritized
- Complete thermodynamic data required for reaction analysis

EXPECTED OUTPUT:
- Individual results for each compound
- Aggregated summary table with all selected records
- Overall confidence assessment
- Missing compounds and warnings
- Recommendations for data improvement

Focus on finding the BEST POSSIBLE data for each individual compound while maintaining efficient parallel processing."""


# =============================================================================
# ПРОМПТЫ ДЛЯ ОПТИМИЗИРОВАННОЙ ФИЛЬТРАЦИИ (SQL WHERE ГЕНЕРАЦИЯ)
# =============================================================================

SQL_FILTER_GENERATION_PROMPT = """You are an expert in thermodynamics and SQL query optimization.

TASK: Generate optimized SQL WHERE conditions to filter thermodynamic database records for compound analysis.

INPUT DATA:
- Target compound: {compound}
- Target temperature: {target_temperature_k} K ({celsius}°C)
- Temperature range: {temperature_range_k} K
- Preferred phases: {phases}
- Available formulas in database: {available_formulas}
- Total records found: {total_records_count}

DATABASE TABLE STRUCTURE:
- Formula: chemical formula (TEXT) - may have modifiers like TiO2(A), Fe2O3(E)
- Phase: phase state (TEXT) - s= solid, l=liquid, g=gas, aq=aqueous
- Tmin/Tmax: temperature validity range (REAL)
- ReliabilityClass: data reliability (INTEGER, 1=best, 4=worst)
- MeltingPoint/BoilingPoint: phase transition temperatures (REAL)
- H298/S298/f1-f6: thermodynamic data (REAL)

FILTERING REQUIREMENTS:
1. FORMULA MATCHING:
   - Exact match: TRIM(Formula) = '{compound}'
   - Variant match: Formula LIKE '{compound}(%'
   - Include structural/phase variants in parentheses

2. TEMPERATURE OVERLAP:
   - Check partial overlap: (Tmin <= {temp_max} AND Tmax >= {temp_min})
   - Handle missing Tmin/Tmax (NULL values)
   - Prefer records covering target temperature

3. PHASE PRIORITIZATION:
   - For target compound {compound} at {target_temperature_k}K
   - Consider typical phase behavior for this compound type
   - Account for melting/boiling points if available

4. RELIABILITY CLASS:
   - Prioritize ReliabilityClass = 1 (best data)
   - Include complete thermodynamic data preference

GENERATION STRATEGY:
Create multiple WHERE conditions with different priorities:
- Priority 1: Exact formula + optimal phase + temperature coverage + best reliability
- Priority 2: Variant formulas + acceptable phases + temperature coverage
- Priority 3: Extended search with relaxed criteria

OUTPUT FORMAT (strict JSON):
{{
    "sql_where_conditions": [
        "TRIM(Formula) = '{compound}' AND Phase = 's' AND ({target_temperature_k} >= Tmin AND {target_temperature_k} <= Tmax) AND ReliabilityClass = 1",
        "Formula LIKE '{compound}(%' AND ({target_temperature_k} >= Tmin AND {target_temperature_k} <= Tmax) AND ReliabilityClass <= 2"
    ],
    "order_by_clauses": [
        "ReliabilityClass ASC, ABS({target_temperature_k} - Tmin) ASC",
        "ReliabilityClass ASC, ABS({target_temperature_k} - (Tmin + Tmax)/2) ASC"
    ],
    "limit_values": [5, 10, 20],
    "reasoning": "Generated 3-tier filtering strategy prioritizing exact matches with optimal phase and reliability class",
    "phase_analysis": {{
        "recommended_phase": "s",
        "confidence": 0.95,
        "reasoning": "Solid phase typical for {compound} at {target_temperature_k}K based on chemical intuition"
    }},
    "expected_results": {{
        "min_records": 1,
        "max_records": 20,
        "optimal_records": 3
    }}
}}

Focus on creating precise, efficient SQL conditions that will return the most relevant records while minimizing data processing overhead."""


# SQL validation and refinement prompts removed - no longer needed


# =============================================================================
# ФУНКЦИИ ДЛЯ ДИНАМИЧЕСКИХ ПРОМПТОВ
# =============================================================================


def build_contextual_analysis_prompt(params) -> str:
    """Построение контекстного промпта для анализа данных (используется для YAML-фильтрации)."""
    return f"""
АНАЛИЗ ТЕРМОДИНАМИЧЕСКИХ ДАННЫХ

КОНТЕКСТ ЗАДАЧИ:
- Целевая температура: {params.target_temperature_k} K ({params.target_temperature_k - 273.15:.1f}°C)
- Реагирующие вещества: {", ".join(params.target_compounds)}
- Тип анализа: {params.intent_type.value}

ДАННЫЕ ДЛЯ АНАЛИЗА (YAML формат):
```yaml
{params.yaml_data}
```
"""


# =============================================================================
# МЕНЕДЖЕР ПРОМПТОВ
# =============================================================================


class PromptManager:
    """Менеджер всех промптов термодинамического агента и его инструментов."""

    def __init__(self, version: str = "v1.0"):
        self.version = version
        self._prompts = {
            # Основные промпты агента
            "sql_generation": SQL_GENERATION_PROMPT,
            "extract_inputs": EXTRACT_INPUTS_PROMPT,
            "validate": VALIDATE_OR_COMPLETE_PROMPT,
            "synthesize": SYNTHESIZE_ANSWER_PROMPT,
            # Промпты инструментов
            "completeness_check": COMPLETENESS_CHECK_PROMPT,
            "tool_selection": TOOL_SELECTION_PROMPT,
            "result_filter": RESULT_FILTER_PROMPT,
            "result_filter_english": RESULT_FILTER_ENGLISH_PROMPT,
            "yaml_filter": YAML_FILTER_SYSTEM_PROMPT,
            # Промпты для индивидуального поиска (новая архитектура)
            "individual_sql_generation": INDIVIDUAL_SQL_GENERATION_PROMPT,
            "individual_filter": INDIVIDUAL_FILTER_PROMPT,
            "individual_search_coordination": INDIVIDUAL_SEARCH_COORDINATION_PROMPT,
            # Промпты для оптимизированной фильтрации
            "sql_filter_generation": SQL_FILTER_GENERATION_PROMPT,
        }

    def get_prompt(self, prompt_name: str) -> str:
        """Получить промпт по имени."""
        if prompt_name not in self._prompts:
            raise ValueError(f"Неизвестный промпт: {prompt_name}")
        return self._prompts[prompt_name]

    def list_available_prompts(self) -> List[str]:
        """Список доступных промптов."""
        return list(self._prompts.keys())

    # Функции для динамических промптов
    @staticmethod
    def build_contextual_analysis_prompt(params) -> str:
        """Построение контекстного промпта для анализа данных."""
        return build_contextual_analysis_prompt(params)
