# Stage 03: Поиск всех фаз вещества (CompoundSearcher)

## Цель
Реализовать метод `search_all_phases()` для поиска всех записей вещества с покрытием многофазного диапазона.

## Статус
🟢 Завершено

## Входные данные
- Stage 01, 02 завершены (модели и расширения DatabaseRecord)
- Существующий `CompoundSearcher` (src/thermo_agents/search/compound_searcher.py)
- SQL Builder для генерации запросов

## Выходные данные
- Метод `CompoundSearcher.search_all_phases(formula, max_temperature, compound_names)`
- Класс `MultiPhaseSearchResult` с найденными записями и метаданными

## Изменяемые файлы
- `src/thermo_agents/search/compound_searcher.py` — добавление метода
- `src/thermo_agents/models/search.py` — добавление `MultiPhaseSearchResult`

## Зависимости
- Stage 01 (модели данных)
- Stage 02 (расширения DatabaseRecord)

## Алгоритм действий

### Шаг 1: Создание MultiPhaseSearchResult dataclass
1. Определить поля для метаданных поиска:
   - `compound_formula` — формула вещества
   - `records` — список найденных записей
   - `coverage_start`, `coverage_end` — температурные границы
   - `covers_298K` — флаг покрытия стандартной температуры
   - `tmelt`, `tboil` — температуры фазовых переходов
   - `phase_count`, `has_gas_phase` — метрики фаз
   - `warnings` — список предупреждений
2. Добавить property-методы:
   - `is_complete` — проверка полноты данных
   - `phase_sequence` — строка "s→l→g"
3. Реализовать `to_dict()` для сериализации

### Шаг 2: Реализация search_all_phases()
1. Проверка StaticDataManager (приоритет кэша):
   - Если вещество в YAML → загрузить из кэша
   - Иначе → поиск в БД
2. Генерация SQL запроса:
   - Поиск всех записей по формуле (без фильтра по фазе)
   - Limit=100 (достаточно для многофазных веществ)
3. Вызов `_build_result()` для обработки записей

### Шаг 3: Реализация _build_result()
1. Фильтрация записей по `max_temperature`
2. Сортировка по `tmin`
3. Определение покрытия (coverage_start, coverage_end)
4. Проверка покрытия 298K
5. Извлечение Tmelt/Tboil
6. Подсчёт фаз и определение газовой фазы
7. Генерация предупреждений

### Шаг 4: Реализация _extract_phase_transitions()
1. Сбор всех tmelt и tboil из записей
2. Определение наиболее частого значения (mode)
3. Возврат кортежа (Tmelt, Tboil)

### Шаг 5: Реализация _generate_warnings()
1. Проверка покрытия 298K
2. Проверка пробелов между записями (gap > 1K)
3. Проверка перекрытий (overlap > 1K)
4. Проверка базовой записи
5. Возврат списка предупреждений

### Шаг 6: Интеграция с StaticDataManager
1. Добавить параметр `static_data_manager` в конструктор
2. Проверка кэша перед запросом к БД
3. Логирование источника данных (YAML vs БД)

### Шаг 7: Тестирование
1. Unit-тесты для search_all_phases()
2. Тесты с моками для БД
3. Тесты генерации предупреждений
4. Интеграционные тесты с реальной БД
5. Тесты приоритета YAML кэша

## Детальный алгоритм

### search_all_phases(): Главный метод поиска

**Назначение:** Найти все записи вещества с покрытием до max_temperature.

**Алгоритм:**
```
FUNCTION search_all_phases(formula, max_temperature, compound_names):
    LOG "Поиск всех фаз для {formula}, T_max={max_temperature}K"
    
    # ШАГ 1: Проверка YAML кэша (приоритет)
    IF static_data_manager EXISTS AND static_data_manager.is_available(formula):
        LOG "⚡ Найдено в YAML кэше: {formula}"
        records = static_data_manager.get_compound_phases(formula)
        RETURN _build_result(formula, records, max_temperature)
    
    # ШАГ 2: Поиск в БД (fallback)
    LOG "Поиск в БД для {formula}"
    
    sql_query = sql_builder.build_compound_query(
        formula=formula,
        temperature_range=None,  # Все температуры
        phase=None,              # Все фазы
        limit=100,
        compound_names=compound_names
    )
    
    all_records = db_connector.execute_query(sql_query)
    
    IF all_records IS EMPTY:
        LOG WARNING "Не найдено записей для {formula}"
        RETURN MultiPhaseSearchResult(
            compound_formula=formula,
            records=[],
            coverage_start=0.0,
            coverage_end=0.0,
            covers_298K=False,
            phase_count=0,
            warnings=["Вещество не найдено в БД"]
        )
    
    RETURN _build_result(formula, all_records, max_temperature)
```

**Ключевые особенности:**
- **Приоритет кэша:** Проверка YAML перед БД для оптимизации
- **Fallback:** Если вещества нет в кэше → поиск в БД
- **Лог источника:** Явное указание источника данных (⚡ кэш или БД)

### _build_result(): Построение результата

**Назначение:** Обработать найденные записи и создать MultiPhaseSearchResult.

**Алгоритм:**
```
FUNCTION _build_result(formula, all_records, max_temperature):
    # ШАГ 1: Фильтрация по температуре
    relevant_records = FILTER all_records WHERE record.tmin <= max_temperature
    
    # Сортировка по Tmin
    SORT relevant_records BY tmin ASCENDING
    
    IF relevant_records IS EMPTY:
        RETURN MultiPhaseSearchResult(
            warnings=["Нет записей, покрывающих требуемый диапазон"]
        )
    
    # ШАГ 2: Определение покрытия
    coverage_start = relevant_records[0].tmin
    coverage_end = MIN(relevant_records[-1].tmax, max_temperature)
    
    covers_298K = ANY(record.covers_temperature(298.15) FOR record IN relevant_records)
    
    # ШАГ 3: Извлечение фазовых переходов
    tmelt, tboil = _extract_phase_transitions(relevant_records)
    
    # ШАГ 4: Подсчёт фаз
    phases = SET(record.phase FOR record IN relevant_records WHERE record.phase EXISTS)
    phase_count = LENGTH(phases)
    has_gas_phase = "g" IN phases
    
    # ШАГ 5: Генерация предупреждений
    warnings = _generate_warnings(relevant_records, covers_298K)
    
    RETURN MultiPhaseSearchResult(
        compound_formula=formula,
        records=relevant_records,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        covers_298K=covers_298K,
        tmelt=tmelt,
        tboil=tboil,
        phase_count=phase_count,
        has_gas_phase=has_gas_phase,
        warnings=warnings
    )
```

**Метрики качества:**
- `coverage_start/end` — границы доступных данных
- `covers_298K` — наличие стандартной температуры
- `phase_count` — количество агрегатных состояний
- `warnings` — проблемы покрытия

### _generate_warnings(): Генерация предупреждений

**Назначение:** Выявить проблемы в данных (пробелы, перекрытия, отсутствие 298K).

**Алгоритм:**
```
FUNCTION _generate_warnings(records, covers_298K):
    warnings = []
    
    # ПРЕДУПРЕЖДЕНИЕ 1: Нет покрытия 298K
    IF NOT covers_298K:
        ADD "⚠️ Отсутствует покрытие 298K (стандартная температура)" TO warnings
    
    # ПРЕДУПРЕЖДЕНИЕ 2: Пробелы между записями
    FOR i FROM 0 TO LENGTH(records) - 2:
        gap = records[i+1].tmin - records[i].tmax
        IF gap > 1.0:  # Пробел больше 1K
            ADD "⚠️ Пробел в покрытии: {records[i].tmax}K - {records[i+1].tmin}K" TO warnings
    
    # ПРЕДУПРЕЖДЕНИЕ 3: Перекрытия
    FOR i FROM 0 TO LENGTH(records) - 2:
        IF records[i].overlaps_with(records[i+1]):
            overlap_start = MAX(records[i].tmin, records[i+1].tmin)
            overlap_end = MIN(records[i].tmax, records[i+1].tmax)
            IF overlap_end - overlap_start > 1.0:
                ADD "⚠️ Перекрытие записей: {overlap_start}K - {overlap_end}K" TO warnings
    
    # ПРЕДУПРЕЖДЕНИЕ 4: Нет базовой записи
    IF records EXISTS AND NOT records[0].is_base_record():
        ADD "⚠️ Первая запись не является базовой (H298=0, S298=0)" TO warnings
    
    RETURN warnings
```

**Категории предупреждений:**
1. **Критичные:** Нет базовой записи, нет покрытия 298K
2. **Важные:** Пробелы > 10K
3. **Информационные:** Небольшие перекрытия

### _extract_phase_transitions(): Извлечение Tmelt/Tboil

**Назначение:** Определить консистентные значения температур фазовых переходов.

**Алгоритм:**
```
FUNCTION _extract_phase_transitions(records):
    # Сбор всех ненулевых tmelt
    tmelt_candidates = [record.tmelt FOR record IN records WHERE record.tmelt > 0]
    
    # Сбор всех ненулевых tboil
    tboil_candidates = [record.tboil FOR record IN records WHERE record.tboil > 0]
    
    # Определение наиболее частого значения (mode)
    tmelt = MODE(tmelt_candidates) IF tmelt_candidates NOT EMPTY ELSE None
    tboil = MODE(tboil_candidates) IF tboil_candidates NOT EMPTY ELSE None
    
    RETURN (tmelt, tboil)
```

**Обработка противоречий:**
- Если разные записи содержат разные Tmelt → взять наиболее частое
- Если все значения одинаковые → использовать это значение
- Если Tmelt отсутствует во всех записях → вернуть None

## Критерии завершения
- [ ] `search_all_phases()` реализован и возвращает все фазы
- [ ] Проверка покрытия 298K работает
- [ ] Генерируются предупреждения о пробелах и перекрытиях
- [ ] Интеграция с StaticDataManager (проверка YAML кэша)
- [ ] Unit-тесты покрывают все сценарии

## Тесты
- `tests/search/test_compound_searcher_multiphase.py`
- `tests/integration/test_search_all_phases.py`

## Риски

### Риск 1: SQL запрос возвращает слишком много записей (Средний)
**Описание:** Для некоторых веществ (например, Fe, C) в БД может быть >100 записей с разными состояниями (оксиды, карбиды).  
**Митигация:** 
- Увеличить limit до 100 (вместо дефолтных 10)
- Добавить строгую фильтрацию по формуле (без частичных совпадений)
- Если записей >100 → логировать WARNING  
**План действий:**
```python
if len(all_records) >= 100:
    logger.warning(f"Достигнут лимит записей (100) для {formula}")
```

### Риск 2: Противоречивые значения Tmelt/Tboil в разных записях (Средний)
**Описание:** Разные записи одного вещества могут содержать разные Tmelt (из-за ошибок данных или разных источников).  
**Митигация:** Использовать `mode` (наиболее частое значение) в `_extract_phase_transitions()`.  
**План действий:** Если найдено >2 разных значений Tmelt → добавить WARNING:
```python
if len(set(tmelt_candidates)) > 2:
    warnings.append(f"⚠️ Противоречивые Tmelt: {set(tmelt_candidates)}")
```

### Риск 3: Пробелы в покрытии приводят к некорректным расчётам (Высокий)
**Описание:** Если между 600K и 700K нет данных, расчёт для 650K невозможен.  
**Митигация:** 
- Генерировать WARNING для пробелов >1K
- В калькуляторе (Stage 05) проверять пробелы перед расчётом
- Предлагать интерполяцию для небольших пробелов  
**План действий:** 
```python
if gap > 10.0:  # Критичный пробел
    warnings.append(f"❌ КРИТИЧНО: Пробел {gap:.1f}K")
```

### Риск 4: YAML кэш содержит устаревшие данные (Низкий)
**Описание:** Если БД обновлена, а YAML кэш нет → приоритет кэша вернёт старые данные.  
**Митигация:** 
- Добавить metadata.version и metadata.extracted_date в YAML
- Реализовать команду `--check-updates` в скрипте экспорта (Stage 08)
- Добавить TTL для кэша (например, 30 дней)  
**План действий:** Если YAML старше 30 дней → логировать INFO о необходимости обновления.

### Риск 5: Производительность при поиске редких веществ (Низкий)
**Описание:** SQL запрос для редкого вещества может занимать >500ms.  
**Митигация:** 
- Использовать индексы БД на поле `formula`
- Кэшировать результаты поиска в памяти (LRU cache)
- Приоритет YAML кэша для распространённых веществ  
**Ожидаемая производительность:** 
- YAML кэш: <10ms
- БД без кэша: <100ms
- БД с индексом: <50ms  
**План действий:** Если performance тесты показывают >100ms → добавить `@lru_cache` на `search_all_phases()`.

## Примечания
Этот метод — ключевой для многофазных расчётов. Должен работать как с БД, так и с YAML кэшем.

---

## Примеры кода

### Пример 1: MultiPhaseSearchResult

```python
# src/thermo_agents/models/search.py

from typing import List, Optional, Tuple

@dataclass
class MultiPhaseSearchResult(BaseModel):
    """Результат поиска всех фаз вещества."""
    
    compound_formula: str = Field(..., description="Формула вещества")
    records: List[DatabaseRecord] = Field(
        default_factory=list,
        description="Все найденные записи, отсортированные по Tmin"
    )
    
    # Температурные границы
    coverage_start: float = Field(..., description="Начало покрытия, K")
    coverage_end: float = Field(..., description="Конец покрытия, K")
    covers_298K: bool = Field(..., description="Покрывает ли диапазон 298K")
    
    # Фазовые переходы
    tmelt: Optional[float] = Field(None, description="Температура плавления, K")
    tboil: Optional[float] = Field(None, description="Температура кипения, K")
    
    # Метаданные
    phase_count: int = Field(..., description="Количество различных фаз")
    has_gas_phase: bool = Field(False, description="Есть ли газовая фаза")
    
    # Предупреждения
    warnings: List[str] = Field(
        default_factory=list,
        description="Предупреждения о пробелах, перекрытиях и т.д."
    )
    
    @property
    def is_complete(self) -> bool:
        """Проверка полноты данных (нет пробелов, покрывает 298K)."""
        return self.covers_298K and len(self.warnings) == 0
    
    @property
    def phase_sequence(self) -> str:
        """Последовательность фаз (s→l→g)."""
        phases = [rec.phase for rec in self.records if rec.phase]
        return " → ".join(phases)
    
    def to_dict(self) -> dict:
        """Сериализация результата."""
        return {
            "formula": self.compound_formula,
            "coverage": [self.coverage_start, self.coverage_end],
            "covers_298K": self.covers_298K,
            "transitions": {
                "melting": self.tmelt,
                "boiling": self.tboil
            },
            "phases": self.phase_sequence,
            "records_count": len(self.records),
            "warnings": self.warnings
        }
```

### Пример 2: Реализация search_all_phases

```python
# src/thermo_agents/search/compound_searcher.py

from typing import List, Optional, Tuple
from ..models.search import MultiPhaseSearchResult

class CompoundSearcher:
    """Поисковик веществ в термодинамической БД."""
    
    def __init__(
        self,
        sql_builder: SQLBuilder,
        db_connector: DatabaseConnector,
        session_logger: Optional[Any] = None,
        static_data_manager: Optional[Any] = None  # Будет в Stage 04
    ):
        self.sql_builder = sql_builder
        self.db_connector = db_connector
        self.session_logger = session_logger
        self.static_data_manager = static_data_manager
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def search_all_phases(
        self,
        formula: str,
        max_temperature: float,
        compound_names: Optional[List[str]] = None
    ) -> MultiPhaseSearchResult:
        """
        Поиск всех фаз вещества с покрытием до max_temperature.
        
        Args:
            formula: Химическая формула (например, "H2O", "FeO")
            max_temperature: Максимальная температура расчёта, K
            compound_names: Список дополнительных имён для поиска
            
        Returns:
            MultiPhaseSearchResult с найденными записями и метаданными
        """
        self.logger.info(f"Поиск всех фаз для {formula}, T_max={max_temperature}K")
        
        # ШАГ 1: Проверка статического кэша (если доступен)
        if self.static_data_manager and self.static_data_manager.is_available(formula):
            self.logger.info(f"⚡ Найдено в статическом кэше: {formula}")
            records = self.static_data_manager.get_compound_phases(formula)
            return self._build_result(formula, records, max_temperature)
        
        # ШАГ 2: Поиск в БД
        self.logger.info(f"Поиск в БД для {formula}")
        
        # Генерация SQL запроса для поиска всех записей вещества
        sql_query = self.sql_builder.build_compound_query(
            formula=formula,
            temperature_range=None,  # Ищем все записи
            phase=None,  # Все фазы
            limit=100,  # Увеличиваем лимит
            compound_names=compound_names
        )
        
        # Выполнение запроса
        all_records = self.db_connector.execute_query(sql_query)
        
        if not all_records:
            self.logger.warning(f"Не найдено записей для {formula}")
            return MultiPhaseSearchResult(
                compound_formula=formula,
                records=[],
                coverage_start=0.0,
                coverage_end=0.0,
                covers_298K=False,
                phase_count=0,
                warnings=["Вещество не найдено в БД"]
            )
        
        return self._build_result(formula, all_records, max_temperature)
    
    def _build_result(
        self,
        formula: str,
        all_records: List[DatabaseRecord],
        max_temperature: float
    ) -> MultiPhaseSearchResult:
        """
        Построение MultiPhaseSearchResult из найденных записей.
        
        Args:
            formula: Формула вещества
            all_records: Все найденные записи
            max_temperature: Максимальная температура
            
        Returns:
            MultiPhaseSearchResult
        """
        # ШАГ 1: Фильтрация по температуре
        relevant_records = [
            rec for rec in all_records
            if rec.tmin <= max_temperature
        ]
        
        # Сортировка по Tmin
        relevant_records.sort(key=lambda r: r.tmin)
        
        if not relevant_records:
            return MultiPhaseSearchResult(
                compound_formula=formula,
                records=[],
                coverage_start=0.0,
                coverage_end=0.0,
                covers_298K=False,
                phase_count=0,
                warnings=["Нет записей, покрывающих требуемый температурный диапазон"]
            )
        
        # ШАГ 2: Определение покрытия
        coverage_start = relevant_records[0].tmin
        coverage_end = min(relevant_records[-1].tmax, max_temperature)
        covers_298K = any(rec.covers_temperature(298.15) for rec in relevant_records)
        
        # ШАГ 3: Определение фазовых переходов
        tmelt, tboil = self._extract_phase_transitions(relevant_records)
        
        # ШАГ 4: Подсчёт фаз
        phases = set(rec.phase for rec in relevant_records if rec.phase)
        phase_count = len(phases)
        has_gas_phase = "g" in phases
        
        # ШАГ 5: Генерация предупреждений
        warnings = self._generate_warnings(relevant_records, covers_298K)
        
        return MultiPhaseSearchResult(
            compound_formula=formula,
            records=relevant_records,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            covers_298K=covers_298K,
            tmelt=tmelt,
            tboil=tboil,
            phase_count=phase_count,
            has_gas_phase=has_gas_phase,
            warnings=warnings
        )
    
    def _extract_phase_transitions(
        self,
        records: List[DatabaseRecord]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Извлечение температур фазовых переходов из записей.
        
        Args:
            records: Список записей
            
        Returns:
            Кортеж (Tmelt, Tboil)
        """
        tmelt_candidates = [rec.tmelt for rec in records if rec.tmelt > 0]
        tboil_candidates = [rec.tboil for rec in records if rec.tboil > 0]
        
        # Берём наиболее частое значение (mode)
        from collections import Counter
        
        tmelt = None
        if tmelt_candidates:
            tmelt = Counter(tmelt_candidates).most_common(1)[0][0]
        
        tboil = None
        if tboil_candidates:
            tboil = Counter(tboil_candidates).most_common(1)[0][0]
        
        return tmelt, tboil
    
    def _generate_warnings(
        self,
        records: List[DatabaseRecord],
        covers_298K: bool
    ) -> List[str]:
        """
        Генерация предупреждений о проблемах покрытия.
        
        Args:
            records: Список записей
            covers_298K: Покрывает ли диапазон 298K
            
        Returns:
            Список строк с предупреждениями
        """
        warnings = []
        
        # Предупреждение 1: Нет покрытия 298K
        if not covers_298K:
            warnings.append(
                "⚠️ Отсутствует покрытие 298K (стандартная температура)"
            )
        
        # Предупреждение 2: Пробелы между записями
        for i in range(len(records) - 1):
            gap = records[i + 1].tmin - records[i].tmax
            if gap > 1.0:  # Пробел больше 1K
                warnings.append(
                    f"⚠️ Пробел в покрытии: {records[i].tmax}K - {records[i + 1].tmin}K"
                )
        
        # Предупреждение 3: Перекрытия
        for i in range(len(records) - 1):
            if records[i].overlaps_with(records[i + 1]):
                overlap_start = max(records[i].tmin, records[i + 1].tmin)
                overlap_end = min(records[i].tmax, records[i + 1].tmax)
                if overlap_end - overlap_start > 1.0:
                    warnings.append(
                        f"⚠️ Перекрытие записей: {overlap_start}K - {overlap_end}K"
                    )
        
        # Предупреждение 4: Нет базовой записи
        if records and not records[0].is_base_record():
            warnings.append(
                "⚠️ Первая запись не является базовой (H298=0, S298=0)"
            )
        
        return warnings
```

### Пример 3: Unit-тесты

```python
# tests/search/test_compound_searcher_multiphase.py

import pytest
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.models.search import DatabaseRecord

@pytest.fixture
def mock_searcher(mocker):
    """Мок CompoundSearcher с заглушками."""
    sql_builder = mocker.Mock()
    db_connector = mocker.Mock()
    return CompoundSearcher(sql_builder, db_connector)

def test_search_all_phases_feo(mock_searcher, mocker):
    """Тест поиска всех фаз FeO."""
    # Мокируем 5 записей FeO (4 твёрдых + 1 жидкая)
    mock_records = [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265.053, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=600.0, tmax=900.0,
            h298=0.0, s298=0.0,
            f1=30.849, f2=46.228, f3=11.694, f4=-19.278, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=900.0, tmax=1300.0,
            h298=0.0, s298=0.0,
            f1=90.408, f2=-38.021, f3=-83.811, f4=15.358, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="s", tmin=1300.0, tmax=1650.0,
            h298=0.0, s298=0.0,
            f1=153.698, f2=-82.062, f3=-374.815, f4=21.975, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24.058, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]
    
    mocker.patch.object(
        mock_searcher.db_connector,
        "execute_query",
        return_value=mock_records
    )
    
    # Поиск всех фаз для T_max=1700K
    result = mock_searcher.search_all_phases("FeO", max_temperature=1700.0)
    
    # Проверки
    assert result.compound_formula == "FeO"
    assert len(result.records) == 5
    assert result.covers_298K is True
    assert result.coverage_start == 298.0
    assert result.coverage_end == 1700.0
    assert result.tmelt == 1650.0
    assert result.tboil == 3687.0
    assert result.phase_count == 2  # s и l
    assert result.has_gas_phase is False
    assert len(result.warnings) == 0  # Нет предупреждений

def test_search_all_phases_gap_warning(mock_searcher, mocker):
    """Тест генерации предупреждения о пробеле."""
    mock_records = [
        DatabaseRecord(
            formula="X", phase="s", tmin=298.0, tmax=500.0,
            h298=-100.0, s298=50.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        ),
        DatabaseRecord(
            formula="X", phase="s", tmin=600.0, tmax=1000.0,  # Пробел 500-600K
            h298=0.0, s298=0.0,
            f1=30.0, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1000.0, tboil=2000.0, reliability_class=1
        ),
    ]
    
    mocker.patch.object(
        mock_searcher.db_connector,
        "execute_query",
        return_value=mock_records
    )
    
    result = mock_searcher.search_all_phases("X", max_temperature=1000.0)
    
    # Должно быть предупреждение о пробеле
    assert any("Пробел в покрытии" in w for w in result.warnings)
```

### Пример 4: Тест приоритета YAML кэша

```python
# tests/integration/test_yaml_cache_priority.py

import pytest
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.storage.static_data_manager import StaticDataManager
from src.thermo_agents.models.search import DatabaseRecord

def test_yaml_cache_priority(mocker, tmp_path):
    """
    Тест приоритета YAML кэша над БД.
    
    Сценарий:
    - H2O есть и в YAML кэше, и в БД
    - search_all_phases должен взять данные из YAML
    - БД не должна вызываться
    """
    # ШАГ 1: Создание YAML кэша с H2O
    yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water", "YAML Cache"]
  description: "Вода из YAML кэша"
  phases:
    - phase: "s"
      tmin: 200.0
      tmax: 273.15
      h298: -285830.0
      s298: 69.95
      f1: 30.092
      f2: 6.832
      f3: 6.793
      f4: -2.534
      f5: 0.082
      f6: -0.007
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
    - phase: "l"
      tmin: 273.15
      tmax: 373.15
      h298: -285830.0
      s298: 69.95
      f1: 75.327
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
  metadata:
    source_database: "yaml_cache"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir(parents=True)
    (yaml_dir / "H2O.yaml").write_text(yaml_content)
    
    # ШАГ 2: Создание StaticDataManager
    static_manager = StaticDataManager(data_dir=yaml_dir)
    
    # ШАГ 3: Создание CompoundSearcher с mock БД
    sql_builder = mocker.Mock()
    db_connector = mocker.Mock()
    
    searcher = CompoundSearcher(
        sql_builder=sql_builder,
        db_connector=db_connector,
        static_data_manager=static_manager
    )
    
    # ШАГ 4: Поиск H2O
    result = searcher.search_all_phases("H2O", max_temperature=400.0)
    
    # ПРОВЕРКИ
    # 1. Данные взяты из YAML (проверка по description)
    assert result.compound_formula == "H2O"
    assert len(result.records) == 2  # s + l
    assert result.records[0].name == "Вода из YAML кэша"
    
    # 2. БД НЕ вызывалась
    db_connector.execute_query.assert_not_called()
    
    # 3. Метаданные корректны
    assert result.covers_298K is True
    assert result.phase_count == 2
    assert result.tmelt == 273.15
    assert result.tboil == 373.15
    
    print("✅ YAML кэш имеет приоритет над БД")

def test_yaml_cache_fallback_to_db(mocker, tmp_path):
    """
    Тест fallback к БД если вещества нет в YAML кэше.
    
    Сценарий:
    - CO2 НЕТ в YAML кэше
    - search_all_phases должен обратиться к БД
    - БД возвращает записи
    """
    # ШАГ 1: Пустой YAML кэш
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir(parents=True)
    static_manager = StaticDataManager(data_dir=yaml_dir)
    
    # ШАГ 2: Mock БД с CO2
    mock_co2_records = [
        DatabaseRecord(
            formula="CO2", phase="g", tmin=298.0, tmax=1200.0,
            h298=-393.51, s298=213.79,
            f1=24.997, f2=55.186, f3=-33.691, f4=7.948, f5=-0.136, f6=-0.403,
            tmelt=216.58, tboil=194.68, reliability_class=1,
            name="Carbon dioxide from DB"
        ),
    ]
    
    sql_builder = mocker.Mock()
    db_connector = mocker.Mock()
    db_connector.execute_query.return_value = mock_co2_records
    
    searcher = CompoundSearcher(
        sql_builder=sql_builder,
        db_connector=db_connector,
        static_data_manager=static_manager
    )
    
    # ШАГ 3: Поиск CO2
    result = searcher.search_all_phases("CO2", max_temperature=1000.0)
    
    # ПРОВЕРКИ
    # 1. Данные взяты из БД
    assert result.compound_formula == "CO2"
    assert len(result.records) == 1
    assert result.records[0].name == "Carbon dioxide from DB"
    
    # 2. БД ВЫЗВАНА
    db_connector.execute_query.assert_called_once()
    
    print("✅ Fallback к БД работает корректно")
```

### Пример 5: Performance тест с кэшем

```python
# tests/performance/test_search_all_phases_performance.py

import pytest
import time
from pathlib import Path
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.storage.static_data_manager import StaticDataManager
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.search.sql_builder import SQLBuilder

def test_yaml_cache_performance(tmp_path):
    """
    Тест производительности поиска с YAML кэшем.
    
    Ожидание: <10ms для загрузки из YAML
    """
    # Подготовка: Создать YAML файл H2O
    yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water"]
  description: "Water"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1700.0
      h298: -241826.0
      s298: 188.83
      f1: 33.066
      f2: 2.563
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1
  metadata:
    source_database: "test"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    (yaml_dir / "H2O.yaml").write_text(yaml_content)
    
    # Создание searcher
    static_manager = StaticDataManager(data_dir=yaml_dir)
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")  # Реальная БД
    
    searcher = CompoundSearcher(
        sql_builder=sql_builder,
        db_connector=db_connector,
        static_data_manager=static_manager
    )
    
    # Прогрев кэша
    searcher.search_all_phases("H2O", max_temperature=1500.0)
    
    # Измерение производительности (10 вызовов)
    start = time.perf_counter()
    
    for _ in range(10):
        result = searcher.search_all_phases("H2O", max_temperature=1500.0)
    
    elapsed = time.perf_counter() - start
    avg_time = (elapsed / 10) * 1000  # мс
    
    # Требование: <10ms на вызов
    assert avg_time < 10.0, f"Слишком медленно: {avg_time:.2f}ms"
    
    print(f"✅ YAML cache: {avg_time:.2f}ms/вызов")

@pytest.mark.slow
def test_database_search_performance():
    """
    Тест производительности поиска в БД (без кэша).
    
    Ожидание: <100ms для поиска в БД
    """
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    
    # Searcher БЕЗ StaticDataManager
    searcher = CompoundSearcher(
        sql_builder=sql_builder,
        db_connector=db_connector,
        static_data_manager=None
    )
    
    start = time.perf_counter()
    
    # Поиск распространённого вещества
    result = searcher.search_all_phases("H2O", max_temperature=1500.0)
    
    elapsed = (time.perf_counter() - start) * 1000  # мс
    
    # Требование: <100ms
    assert elapsed < 100.0, f"Слишком медленно: {elapsed:.2f}ms"
    
    print(f"✅ DB search: {elapsed:.2f}ms")
    print(f"   Найдено записей: {len(result.records)}")
```

---

## План реализации

1. **День 1**: Создание `MultiPhaseSearchResult`
2. **День 2**: Реализация `search_all_phases()` и `_build_result()`
3. **День 3**: Реализация `_generate_warnings()`
4. **День 4**: Unit-тесты и интеграционные тесты
5. **День 5**: Документация и код-ревью

## Следующий этап
Stage 04: Создание StaticDataManager для YAML кэша избранных веществ
