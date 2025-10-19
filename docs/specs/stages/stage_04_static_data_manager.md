# Stage 04: StaticDataManager для YAML кэша избранных веществ

## Цель
Создать систему для хранения и загрузки термодинамических данных избранных веществ из YAML файлов.

## Статус
🔴 Не начато

## Входные данные
- Структура YAML из ТЗ §5.3-5.4
- Stage 01-03 завершены (модели и поиск)

## Выходные данные
- `StaticDataManager` — класс для работы с YAML кэшем
- Структура директории `data/static_compounds/`
- Валидация и загрузка YAML файлов

## Изменяемые файлы
- Создать: `src/thermo_agents/storage/static_data_manager.py`
- Создать: `data/static_compounds/` (директория)
- Обновить: `src/thermo_agents/search/compound_searcher.py` (интеграция)

## Зависимости
- Stage 01 (модели данных)
- Stage 02 (расширения DatabaseRecord)

## Алгоритм действий

### Шаг 1: Создание Pydantic схем для YAML
1. Создать `YAMLPhaseRecord` — одна фаза вещества:
   - Поля: phase, tmin, tmax, h298, s298, f1-f6, tmelt, tboil, reliability_class
   - Валидатор: tmin < tmax
2. Создать `YAMLPhaseTransition` — фазовый переход:
   - Поля: temperature, enthalpy, entropy
3. Создать `YAMLMetadata` — метаданные файла:
   - Поля: source_database, extracted_date, version, notes
4. Создать `YAMLCompoundData` — корневая структура:
   - Поля: formula, common_names, description, phases, phase_transitions, metadata
   - Валидатор: фазы отсортированы по tmin

### Шаг 2: Реализация StaticDataManager
1. Конструктор `__init__(data_dir)`:
   - Определить путь к директории `data/static_compounds/`
   - Создать директорию если не существует
   - Инициализировать внутренний кэш `Dict[str, YAMLCompoundData]`
2. Метод `is_available(formula)`:
   - Проверить существование файла `{formula}.yaml`
3. Метод `load_compound(formula)`:
   - Проверить внутренний кэш
   - Загрузить YAML файл через `yaml.safe_load()`
   - Валидировать через Pydantic
   - Сохранить в кэш
4. Метод `get_compound_phases(formula)`:
   - Загрузить compound_data
   - Преобразовать YAMLPhaseRecord → DatabaseRecord
   - Вернуть список записей
5. Метод `list_available_compounds()`:
   - Сканировать директорию для *.yaml файлов
   - Вернуть отсортированный список формул

### Шаг 3: Интеграция с CompoundSearcher
1. Добавить параметр `static_data_manager` в конструктор
2. В `search_all_phases()`:
   - Проверить `static_data_manager.is_available(formula)`
   - Если TRUE → загрузить из YAML
   - Если FALSE → fallback к БД
3. Логировать источник данных (⚡ YAML или 🔍 БД)

### Шаг 4: Создание примеров YAML файлов
1. H2O.yaml — полный пример (3 фазы: s, l, g)
2. CO2.yaml — пример с сублимацией
3. FeO.yaml — пример многофазного твёрдого вещества

### Шаг 5: Тестирование
1. Unit-тесты для каждого метода StaticDataManager
2. Тесты валидации YAML схем
3. Тесты cache invalidation (reload)
4. Интеграционные тесты с CompoundSearcher
5. Performance тесты (<10ms для загрузки)

## Детальный алгоритм

### StaticDataManager.__init__(): Инициализация менеджера

**Назначение:** Создать менеджер для работы с YAML кэшем.

**Алгоритм:**
```
FUNCTION __init__(data_dir):
    IF data_dir IS None:
        # Определить путь относительно корня проекта
        project_root = Path(__file__).parent.parent.parent.parent
        data_dir = project_root / "data" / "static_compounds"
    
    self.data_dir = Path(data_dir)
    self.cache = {}  # Dict[str, YAMLCompoundData]
    
    # Создать директорию если не существует
    self.data_dir.mkdir(parents=True, exist_ok=True)
    
    LOG INFO "StaticDataManager инициализирован: {self.data_dir}"
```

**Структура директорий:**
```
data/
└── static_compounds/
    ├── H2O.yaml
    ├── CO2.yaml
    ├── O2.yaml
    ├── FeO.yaml
    └── ...
```

### is_available(): Проверка наличия YAML

**Назначение:** Быстрая проверка существования файла без загрузки.

**Алгоритм:**
```
FUNCTION is_available(formula):
    yaml_path = self.data_dir / f"{formula}.yaml"
    RETURN yaml_path.exists()
```

**Применение:**
```python
if static_manager.is_available("H2O"):
    # Загрузить из YAML
else:
    # Искать в БД
```

**Производительность:** O(1), <0.01ms

### load_compound(): Загрузка и валидация YAML

**Назначение:** Загрузить данные вещества из YAML с валидацией.

**Алгоритм:**
```
FUNCTION load_compound(formula):
    # ШАГ 1: Проверка кэша
    IF formula IN self.cache:
        LOG DEBUG "Загрузка {formula} из кэша"
        RETURN self.cache[formula]
    
    yaml_path = self.data_dir / f"{formula}.yaml"
    
    # ШАГ 2: Проверка существования
    IF NOT yaml_path.exists():
        LOG DEBUG "YAML файл не найден: {yaml_path}"
        RETURN None
    
    # ШАГ 3: Загрузка YAML
    TRY:
        WITH open(yaml_path, "r", encoding="utf-8") AS f:
            data = yaml.safe_load(f)
        
        # ШАГ 4: Валидация через Pydantic
        compound_data = YAMLCompoundData(**data["compound"])
        
        # ШАГ 5: Сохранение в кэш
        self.cache[formula] = compound_data
        
        LOG INFO "✅ Загружено из YAML: {formula} ({len(compound_data.phases)} фаз)"
        RETURN compound_data
    
    EXCEPT Exception AS e:
        LOG ERROR "Ошибка загрузки YAML для {formula}: {e}"
        RETURN None
```

**Обработка ошибок:**
- Невалидный YAML → вернуть None, логировать ошибку
- Отсутствующие обязательные поля → Pydantic ValidationError
- Неправильная сортировка фаз → ValidationError

### get_compound_phases(): Преобразование в DatabaseRecord

**Назначение:** Получить список DatabaseRecord для всех фаз вещества.

**Алгоритм:**
```
FUNCTION get_compound_phases(formula):
    # ШАГ 1: Загрузка данных
    compound_data = self.load_compound(formula)
    
    IF compound_data IS None:
        RETURN []
    
    # ШАГ 2: Преобразование YAMLPhaseRecord → DatabaseRecord
    records = []
    
    FOR phase_data IN compound_data.phases:
        record = DatabaseRecord(
            formula=compound_data.formula,
            name=compound_data.description,
            first_name=phase_data.first_name,
            phase=phase_data.phase,
            tmin=phase_data.tmin,
            tmax=phase_data.tmax,
            h298=phase_data.h298,
            s298=phase_data.s298,
            f1=phase_data.f1,
            f2=phase_data.f2,
            f3=phase_data.f3,
            f4=phase_data.f4,
            f5=phase_data.f5,
            f6=phase_data.f6,
            tmelt=phase_data.tmelt,
            tboil=phase_data.tboil,
            reliability_class=phase_data.reliability_class,
            molecular_weight=phase_data.molecular_weight
        )
        records.append(record)
    
    RETURN records
```

**Совместимость:** DatabaseRecord полностью совместим с данными из БД, поэтому остальной код (калькулятор, форматтер) работает без изменений.

### list_available_compounds(): Список кэшированных веществ

**Назначение:** Получить список всех доступных в кэше веществ.

**Алгоритм:**
```
FUNCTION list_available_compounds():
    yaml_files = self.data_dir.glob("*.yaml")
    formulas = [file.stem FOR file IN yaml_files]
    RETURN sorted(formulas)
```

**Применение:**
```python
available = static_manager.list_available_compounds()
# ["CO2", "FeO", "H2O", "O2", "S", ...]
```

## Критерии завершения
- [ ] `StaticDataManager` реализован
- [ ] YAML загружается и валидируется корректно
- [ ] Интеграция с `CompoundSearcher` работает
- [ ] Создан пример YAML для H2O
- [ ] Unit-тесты покрывают все методы

## Тесты
- `tests/storage/test_static_data_manager.py`
- `tests/integration/test_yaml_cache.py`

## Риски

### Риск 1: Некорректная схема YAML приводит к ошибкам парсинга (Средний)
**Описание:** Если YAML файл содержит опечатки, отсутствующие поля или неправильный формат, Pydantic выбросит ValidationError.  
**Митигация:** 
- Использовать строгие Pydantic схемы с валидаторами
- Добавить команду `--validate` в скрипт экспорта (Stage 08)
- Логировать детальные ошибки валидации  
**План действий:**
```python
try:
    compound_data = YAMLCompoundData(**data["compound"])
except ValidationError as e:
    logger.error(f"Ошибка валидации YAML для {formula}:")
    for error in e.errors():
        logger.error(f"  - {error['loc']}: {error['msg']}")
    return None
```

### Риск 2: YAML файлы содержат устаревшие данные (Высокий)
**Описание:** Если БД обновлена, а YAML кэш не обновлён, пользователи получат старые данные.  
**Митигация:** 
- Добавить `metadata.extracted_date` в каждый YAML
- Реализовать `--check-updates` в скрипте экспорта
- Добавить WARNING если YAML старше 30 дней
- Документировать процесс обновления кэша  
**План действий:**
```python
from datetime import datetime, timedelta

extracted = datetime.strptime(metadata.extracted_date, "%Y-%m-%d")
age_days = (datetime.now() - extracted).days

if age_days > 30:
    logger.warning(f"YAML для {formula} устарел ({age_days} дней)")
```

### Риск 3: Конфликт версий YAML схемы (Средний)
**Описание:** Если структура YAML изменится в будущем, старые файлы станут несовместимыми.  
**Митигация:** 
- Добавить `metadata.version` (текущая: "1.0")
- Поддерживать обратную совместимость (v1.0, v1.1, v2.0)
- При загрузке проверять версию и применять миграции  
**План действий:**
```python
if compound_data.metadata.version == "1.0":
    # Старая схема, совместима
    pass
elif compound_data.metadata.version == "2.0":
    # Новая схема, может требовать миграции
    compound_data = migrate_v1_to_v2(compound_data)
else:
    logger.warning(f"Неизвестная версия YAML: {compound_data.metadata.version}")
```

### Риск 4: Производительность при большом количестве YAML файлов (Низкий)
**Описание:** Если кэш содержит >100 веществ, `list_available_compounds()` может быть медленным.  
**Митигация:** 
- Использовать `Path.glob()` (быстрый встроенный метод)
- Кэшировать список доступных веществ
- Lazy loading: не загружать все YAML сразу  
**Ожидаемая производительность:**
- `is_available()`: <0.01ms
- `load_compound()` (первая загрузка): <5ms
- `load_compound()` (из кэша): <0.01ms
- `list_available_compounds()` для 100 файлов: <10ms  
**План действий:** Если performance тесты показывают деградацию, добавить кэширование списка файлов.

### Риск 5: Ошибки кодировки в YAML файлах (Низкий)
**Описание:** YAML может содержать кириллицу или специальные символы, что приведёт к UnicodeDecodeError.  
**Митигация:** 
- Всегда использовать `encoding="utf-8"` при открытии файлов
- Добавить `allow_unicode=True` в yaml.dump()
- Тестировать с разными языками  
**План действий:** Все операции с файлами используют UTF-8:
```python
with open(yaml_path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
```

### Риск 6: Race condition при параллельной загрузке (Низкий)
**Описание:** Если несколько потоков одновременно вызывают `load_compound()`, возможна двойная загрузка.  
**Митигация:** 
- StaticDataManager предназначен для single-threaded использования
- Если нужен multi-threading → использовать threading.Lock()
- Документировать ограничение  
**План действий:** Добавить примечание в docstring:
```python
"""
StaticDataManager — single-threaded менеджер YAML кэша.
Для multi-threaded использования добавьте threading.Lock().
"""
```

## Примечания
**ВАЖНО:** YAML файлы — это **кэш для избранных веществ**, а не замена БД. Пользователь вручную отбирает вещества для кэширования.

---

## Примеры кода

### Пример 1: Схема YAML (Pydantic модель)

```python
# src/thermo_agents/models/static_data.py

from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class YAMLPhaseRecord(BaseModel):
    """Одна фаза вещества в YAML."""
    phase: str = Field(..., description="Фаза (s/l/g/aq)")
    tmin: float = Field(..., description="Минимальная температура, K")
    tmax: float = Field(..., description="Максимальная температура, K")
    h298: float = Field(..., description="Энтальпия при 298K, Дж/моль")
    s298: float = Field(..., description="Энтропия при 298K, Дж/(моль·K)")
    f1: float = Field(..., description="Коэффициент Шомейта f1")
    f2: float = Field(..., description="Коэффициент Шомейта f2")
    f3: float = Field(..., description="Коэффициент Шомейта f3")
    f4: float = Field(..., description="Коэффициент Шомейта f4")
    f5: float = Field(..., description="Коэффициент Шомейта f5")
    f6: float = Field(..., description="Коэффициент Шомейта f6")
    tmelt: float = Field(..., description="Температура плавления, K")
    tboil: float = Field(..., description="Температура кипения, K")
    first_name: Optional[str] = Field(None, description="Первое имя вещества")
    reliability_class: int = Field(1, description="Класс надёжности")
    molecular_weight: Optional[float] = Field(None, description="Молекулярная масса")

class YAMLPhaseTransition(BaseModel):
    """Фазовый переход в YAML."""
    temperature: float = Field(..., description="Температура перехода, K")
    enthalpy: float = Field(..., description="Энтальпия перехода, кДж/моль")
    entropy: float = Field(..., description="Энтропия перехода, Дж/(моль·K)")

class YAMLMetadata(BaseModel):
    """Метаданные YAML файла."""
    source_database: str = Field(..., description="Источник данных")
    extracted_date: str = Field(..., description="Дата извлечения")
    version: str = Field(..., description="Версия данных")
    notes: Optional[str] = Field(None, description="Примечания")

class YAMLCompoundData(BaseModel):
    """Полная структура YAML файла вещества."""
    formula: str = Field(..., description="Химическая формула")
    common_names: List[str] = Field(default_factory=list, description="Распространённые названия")
    description: str = Field(..., description="Описание вещества")
    
    phases: List[YAMLPhaseRecord] = Field(..., description="Все фазы вещества")
    
    phase_transitions: Optional[Dict[str, YAMLPhaseTransition]] = Field(
        None,
        description="Фазовые переходы (melting, vaporization)"
    )
    
    metadata: YAMLMetadata = Field(..., description="Метаданные файла")
    
    @validator("phases")
    def validate_phases_sorted(cls, v):
        """Проверка сортировки фаз по Tmin."""
        if len(v) < 2:
            return v
        for i in range(len(v) - 1):
            if v[i].tmin > v[i + 1].tmin:
                raise ValueError("Фазы должны быть отсортированы по Tmin")
        return v
```

### Пример 2: StaticDataManager

```python
# src/thermo_agents/storage/static_data_manager.py

import os
import logging
from pathlib import Path
from typing import List, Optional, Dict
import yaml

from ..models.search import DatabaseRecord
from ..models.static_data import YAMLCompoundData, YAMLPhaseRecord

logger = logging.getLogger(__name__)


class StaticDataManager:
    """
    Менеджер для работы с YAML кэшем избранных веществ.
    
    YAML файлы хранятся в data/static_compounds/ и содержат
    термодинамические данные для распространённых веществ.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Инициализация менеджера.
        
        Args:
            data_dir: Путь к директории с YAML файлами.
                     По умолчанию: data/static_compounds/
        """
        if data_dir is None:
            # Определяем путь относительно корня проекта
            project_root = Path(__file__).parent.parent.parent.parent
            data_dir = project_root / "data" / "static_compounds"
        
        self.data_dir = Path(data_dir)
        self.cache: Dict[str, YAMLCompoundData] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Создать директорию если не существует
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"StaticDataManager инициализирован: {self.data_dir}")
    
    def is_available(self, formula: str) -> bool:
        """
        Проверка наличия YAML файла для вещества.
        
        Args:
            formula: Химическая формула (например, "H2O")
            
        Returns:
            True если файл существует
        """
        yaml_path = self.data_dir / f"{formula}.yaml"
        return yaml_path.exists()
    
    def load_compound(self, formula: str) -> Optional[YAMLCompoundData]:
        """
        Загрузка данных вещества из YAML.
        
        Args:
            formula: Химическая формула
            
        Returns:
            YAMLCompoundData или None если файл не найден
        """
        # Проверка кэша
        if formula in self.cache:
            self.logger.debug(f"Загрузка {formula} из кэша")
            return self.cache[formula]
        
        yaml_path = self.data_dir / f"{formula}.yaml"
        
        if not yaml_path.exists():
            self.logger.debug(f"YAML файл не найден: {yaml_path}")
            return None
        
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # Валидация через Pydantic
            compound_data = YAMLCompoundData(**data["compound"])
            
            # Сохранить в кэш
            self.cache[formula] = compound_data
            
            self.logger.info(f"✅ Загружено из YAML: {formula} ({len(compound_data.phases)} фаз)")
            return compound_data
            
        except Exception as e:
            self.logger.error(f"Ошибка загрузки YAML для {formula}: {e}")
            return None
    
    def get_compound_phases(self, formula: str) -> List[DatabaseRecord]:
        """
        Получение всех фаз вещества как DatabaseRecord.
        
        Args:
            formula: Химическая формула
            
        Returns:
            Список DatabaseRecord для всех фаз
        """
        compound_data = self.load_compound(formula)
        
        if compound_data is None:
            return []
        
        # Преобразование YAMLPhaseRecord → DatabaseRecord
        records = []
        for phase_data in compound_data.phases:
            record = DatabaseRecord(
                formula=compound_data.formula,
                name=compound_data.description,
                first_name=phase_data.first_name,
                phase=phase_data.phase,
                tmin=phase_data.tmin,
                tmax=phase_data.tmax,
                h298=phase_data.h298,
                s298=phase_data.s298,
                f1=phase_data.f1,
                f2=phase_data.f2,
                f3=phase_data.f3,
                f4=phase_data.f4,
                f5=phase_data.f5,
                f6=phase_data.f6,
                tmelt=phase_data.tmelt,
                tboil=phase_data.tboil,
                reliability_class=phase_data.reliability_class,
                molecular_weight=phase_data.molecular_weight
            )
            records.append(record)
        
        return records
    
    def list_available_compounds(self) -> List[str]:
        """
        Получение списка всех доступных веществ в кэше.
        
        Returns:
            Список формул веществ
        """
        yaml_files = self.data_dir.glob("*.yaml")
        formulas = [f.stem for f in yaml_files]
        return sorted(formulas)
    
    def reload(self) -> None:
        """Очистка кэша и перезагрузка данных."""
        self.cache.clear()
        self.logger.info("Кэш очищен")
```

### Пример 3: Пример YAML файла (H2O)

```yaml
# data/static_compounds/H2O.yaml

compound:
  formula: "H2O"
  common_names:
    - "Water"
    - "Вода"
  description: "Вода - наиболее распространенное химическое соединение"
  
  phases:
    # Твёрдая фаза (лёд)
    - phase: "s"
      tmin: 200.0
      tmax: 273.15
      h298: -285830.0  # Дж/моль
      s298: 69.95      # Дж/(моль·K)
      f1: 30.092
      f2: 6.832
      f3: 6.793
      f4: -2.534
      f5: 0.082
      f6: -0.007
      tmelt: 273.15
      tboil: 373.15
      first_name: "Ice"
      reliability_class: 1
      molecular_weight: 18.01528
    
    # Жидкая фаза
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
      first_name: "Water"
      reliability_class: 1
      molecular_weight: 18.01528
    
    # Газовая фаза (пар)
    - phase: "g"
      tmin: 298.15
      tmax: 1700.0
      h298: -241826.0  # Пар имеет другую энтальпию образования
      s298: 188.83
      f1: 33.066
      f2: 2.563
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      first_name: "Water vapor"
      reliability_class: 1
      molecular_weight: 18.01528
  
  phase_transitions:
    melting:
      temperature: 273.15
      enthalpy: 6.008    # кДж/моль
      entropy: 22.0      # Дж/(моль·K)
    
    vaporization:
      temperature: 373.15
      enthalpy: 40.66    # кДж/моль
      entropy: 108.95    # Дж/(моль·K)
  
  metadata:
    source_database: "thermo_data.db"
    extracted_date: "2025-10-19"
    version: "1.0"
    notes: |
      Полный набор данных для всех агрегатных состояний воды.
      Данные взяты из NIST-JANAF Thermochemical Tables.
```

### Пример 4: Интеграция с CompoundSearcher

```python
# src/thermo_agents/search/compound_searcher.py

class CompoundSearcher:
    """Поисковик веществ."""
    
    def __init__(
        self,
        sql_builder: SQLBuilder,
        db_connector: DatabaseConnector,
        session_logger: Optional[Any] = None,
        static_data_manager: Optional[StaticDataManager] = None
    ):
        self.sql_builder = sql_builder
        self.db_connector = db_connector
        self.session_logger = session_logger
        self.static_data_manager = static_data_manager  # НОВОЕ
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def search_all_phases(
        self,
        formula: str,
        max_temperature: float,
        compound_names: Optional[List[str]] = None
    ) -> MultiPhaseSearchResult:
        """
        Поиск всех фаз вещества.
        
        ПРИОРИТЕТ:
        1. YAML кэш (StaticDataManager)
        2. База данных (DatabaseConnector)
        """
        self.logger.info(f"Поиск всех фаз для {formula}")
        
        # ШАГ 1: Проверка YAML кэша
        if self.static_data_manager and self.static_data_manager.is_available(formula):
            self.logger.info(f"⚡ Найдено в YAML кэше: {formula}")
            if self.session_logger:
                self.session_logger.log_info(f"⚡ Использован YAML кэш для {formula}")
            
            records = self.static_data_manager.get_compound_phases(formula)
            return self._build_result(formula, records, max_temperature)
        
        # ШАГ 2: Поиск в БД (fallback)
        self.logger.info(f"Поиск в БД для {formula}")
        # ... (код из Stage 03)
```

### Пример 5: Unit-тесты

```python
# tests/storage/test_static_data_manager.py

import pytest
from pathlib import Path
from src.thermo_agents.storage.static_data_manager import StaticDataManager

@pytest.fixture
def temp_data_dir(tmp_path):
    """Временная директория для тестов."""
    return tmp_path / "static_compounds"

@pytest.fixture
def sample_yaml_h2o(temp_data_dir):
    """Создание примера YAML файла H2O."""
    temp_data_dir.mkdir(parents=True, exist_ok=True)
    yaml_content = """
compound:
  formula: "H2O"
  common_names: ["Water", "Вода"]
  description: "Вода"
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
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    yaml_path = temp_data_dir / "H2O.yaml"
    yaml_path.write_text(yaml_content)
    return yaml_path

def test_static_data_manager_is_available(temp_data_dir, sample_yaml_h2o):
    """Тест проверки наличия YAML файла."""
    manager = StaticDataManager(data_dir=temp_data_dir)
    
    assert manager.is_available("H2O") is True
    assert manager.is_available("CO2") is False

def test_static_data_manager_load_compound(temp_data_dir, sample_yaml_h2o):
    """Тест загрузки YAML файла."""
    manager = StaticDataManager(data_dir=temp_data_dir)
    
    compound_data = manager.load_compound("H2O")
    
    assert compound_data is not None
    assert compound_data.formula == "H2O"
    assert len(compound_data.phases) == 1
    assert compound_data.phases[0].phase == "s"
    assert compound_data.phases[0].tmin == 200.0

def test_static_data_manager_get_phases(temp_data_dir, sample_yaml_h2o):
    """Тест получения фаз как DatabaseRecord."""
    manager = StaticDataManager(data_dir=temp_data_dir)
    
    records = manager.get_compound_phases("H2O")
    
    assert len(records) == 1
    assert records[0].formula == "H2O"
    assert records[0].phase == "s"
    assert records[0].h298 == -285830.0

def test_static_data_manager_list_compounds(temp_data_dir, sample_yaml_h2o):
    """Тест получения списка доступных веществ."""
    manager = StaticDataManager(data_dir=temp_data_dir)
    
    compounds = manager.list_available_compounds()
    
    assert "H2O" in compounds
```

### Пример 6: Полный YAML файл для CO2 (сублимация)

```yaml
# data/static_compounds/CO2.yaml

compound:
  formula: "CO2"
  common_names:
    - "Carbon dioxide"
    - "Углекислый газ"
    - "Диоксид углерода"
  description: "Углекислый газ - газ без цвета и запаха"
  
  phases:
    # Твёрдая фаза (сухой лёд) - существует только при низких T
    - phase: "s"
      tmin: 150.0
      tmax: 194.68  # Температура сублимации
      h298: -393510.0  # Дж/моль
      s298: 213.79     # Дж/(моль·K)
      f1: 24.997
      f2: 55.186
      f3: -33.691
      f4: 7.948
      f5: -0.136
      f6: -0.403
      tmelt: 0.0    # CO2 не плавится при атм. давлении
      tboil: 194.68  # Сублимация
      first_name: "Dry ice"
      reliability_class: 1
      molecular_weight: 44.0095
    
    # Газовая фаза (обычное состояние при комнатной T)
    - phase: "g"
      tmin: 194.68
      tmax: 3000.0
      h298: -393510.0
      s298: 213.79
      f1: 24.997
      f2: 55.186
      f3: -33.691
      f4: 7.948
      f5: -0.136
      f6: -0.403
      tmelt: 0.0
      tboil: 194.68
      first_name: "Carbon dioxide"
      reliability_class: 1
      molecular_weight: 44.0095
  
  phase_transitions:
    sublimation:  # Прямой переход s → g
      temperature: 194.68
      enthalpy: 25.23    # кДж/моль
      entropy: 129.7     # Дж/(моль·K)
  
  metadata:
    source_database: "thermo_data.db"
    extracted_date: "2025-10-19"
    version: "1.0"
    notes: |
      CO2 сублимирует при атмосферном давлении.
      Жидкая фаза существует только при давлении >5.1 атм.
```

### Пример 7: Полный YAML файл для FeO (многофазное твёрдое)

```yaml
# data/static_compounds/FeO.yaml

compound:
  formula: "FeO"
  common_names:
    - "Iron(II) oxide"
    - "Wustite"
    - "Оксид железа(II)"
    - "Вюстит"
  description: "Оксид железа(II) - чёрный порошок"
  
  phases:
    # Твёрдая фаза: 5 сегментов с разными коэффициентами
    - phase: "s"
      tmin: 298.0
      tmax: 600.0
      h298: -265053.0  # Дж/моль (базовая запись)
      s298: 59.807     # Дж/(моль·K)
      f1: 50.278
      f2: 3.651
      f3: -1.941
      f4: 8.234
      f5: 0.0
      f6: 0.0
      tmelt: 1650.0
      tboil: 3687.0
      first_name: "Wustite"
      reliability_class: 1
      molecular_weight: 71.844
    
    - phase: "s"
      tmin: 600.0
      tmax: 900.0
      h298: 0.0  # Продолжающая запись
      s298: 0.0
      f1: 30.849
      f2: 46.228
      f3: 11.694
      f4: -19.278
      f5: 0.0
      f6: 0.0
      tmelt: 1650.0
      tboil: 3687.0
      first_name: "Wustite"
      reliability_class: 1
      molecular_weight: 71.844
    
    - phase: "s"
      tmin: 900.0
      tmax: 1300.0
      h298: 0.0
      s298: 0.0
      f1: 90.408
      f2: -38.021
      f3: -83.811
      f4: 15.358
      f5: 0.0
      f6: 0.0
      tmelt: 1650.0
      tboil: 3687.0
      first_name: "Wustite"
      reliability_class: 1
      molecular_weight: 71.844
    
    - phase: "s"
      tmin: 1300.0
      tmax: 1650.0
      h298: 0.0
      s298: 0.0
      f1: 153.698
      f2: -82.062
      f3: -374.815
      f4: 21.975
      f5: 0.0
      f6: 0.0
      tmelt: 1650.0
      tboil: 3687.0
      first_name: "Wustite"
      reliability_class: 1
      molecular_weight: 71.844
    
    # Жидкая фаза
    - phase: "l"
      tmin: 1650.0
      tmax: 5000.0
      h298: 24058.0   # Базовая запись для жидкости
      s298: 14.581
      f1: 68.199
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 1650.0
      tboil: 3687.0
      first_name: "Wustite (liquid)"
      reliability_class: 1
      molecular_weight: 71.844
  
  phase_transitions:
    melting:
      temperature: 1650.0
      enthalpy: 32.0     # кДж/моль
      entropy: 19.4      # Дж/(моль·K)
    
    vaporization:
      temperature: 3687.0
      enthalpy: 290.0    # кДж/моль (примерная)
      entropy: 78.6      # Дж/(моль·K)
  
  metadata:
    source_database: "thermo_data.db"
    extracted_date: "2025-10-19"
    version: "1.0"
    notes: |
      FeO из технического задания (§3.2).
      5 записей: 4 твёрдых сегмента + 1 жидкий.
      Используется для тестирования многофазных расчётов.
```

### Пример 8: Тесты cache invalidation и reload

```python
# tests/storage/test_static_data_cache.py

import pytest
from pathlib import Path
from src.thermo_agents.storage.static_data_manager import StaticDataManager

def test_cache_invalidation(tmp_path):
    """Тест инвалидации кэша при изменении YAML."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    # Версия 1: H2O с h298=-285830
    yaml_v1 = """
compound:
  formula: "H2O"
  common_names: ["Water v1"]
  description: "Version 1"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -241826.0
      s298: 188.83
      f1: 33.0
      f2: 2.5
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
    yaml_path = yaml_dir / "H2O.yaml"
    yaml_path.write_text(yaml_v1)
    
    # Загрузка версии 1
    manager = StaticDataManager(data_dir=yaml_dir)
    data_v1 = manager.load_compound("H2O")
    
    assert data_v1.common_names[0] == "Water v1"
    assert data_v1.description == "Version 1"
    
    # Изменение YAML (версия 2)
    yaml_v2 = yaml_v1.replace("Water v1", "Water v2").replace("Version 1", "Version 2")
    yaml_path.write_text(yaml_v2)
    
    # Попытка загрузить снова - должен вернуть кэш (v1)
    data_cached = manager.load_compound("H2O")
    assert data_cached.common_names[0] == "Water v1", "Кэш не инвалидирован"
    
    # Явная инвалидация
    manager.reload()
    
    # Теперь должна загрузиться версия 2
    data_v2 = manager.load_compound("H2O")
    assert data_v2.common_names[0] == "Water v2"
    assert data_v2.description == "Version 2"
    
    print("✅ Cache invalidation работает корректно")

def test_concurrent_load_same_compound(tmp_path):
    """Тест загрузки одного вещества несколько раз."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    yaml_content = """
compound:
  formula: "O2"
  common_names: ["Oxygen"]
  description: "Oxygen"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1500.0
      h298: 0.0
      s298: 205.15
      f1: 29.659
      f2: 6.137
      f3: -1.186
      f4: 0.095
      f5: -0.219
      f6: -0.008
      tmelt: 54.36
      tboil: 90.20
      reliability_class: 1
  metadata:
    source_database: "test"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    (yaml_dir / "O2.yaml").write_text(yaml_content)
    
    manager = StaticDataManager(data_dir=yaml_dir)
    
    # Загрузка 10 раз
    results = []
    for _ in range(10):
        data = manager.load_compound("O2")
        results.append(data)
    
    # Все результаты должны быть идентичными (один объект из кэша)
    for result in results[1:]:
        assert result is results[0], "Не используется кэш"
    
    print("✅ Кэширование работает при множественных загрузках")

def test_metadata_version_check(tmp_path):
    """Тест проверки версии метаданных."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    # YAML с версией 2.0
    yaml_v2 = """
compound:
  formula: "N2"
  common_names: ["Nitrogen"]
  description: "Nitrogen"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 2000.0
      h298: 0.0
      s298: 191.61
      f1: 28.883
      f2: 3.295
      f3: -0.853
      f4: 0.097
      f5: -0.226
      f6: -0.009
      tmelt: 63.15
      tboil: 77.36
      reliability_class: 1
  metadata:
    source_database: "test"
    extracted_date: "2025-10-19"
    version: "2.0"  # Новая версия!
    notes: "Future version"
"""
    (yaml_dir / "N2.yaml").write_text(yaml_v2)
    
    manager = StaticDataManager(data_dir=yaml_dir)
    data = manager.load_compound("N2")
    
    assert data is not None
    assert data.metadata.version == "2.0"
    
    # В будущем здесь может быть логика миграции
    print(f"✅ Версия {data.metadata.version} распознана")
```

### Пример 9: Performance тесты для StaticDataManager

```python
# tests/performance/test_static_data_performance.py

import pytest
import time
from pathlib import Path
from src.thermo_agents.storage.static_data_manager import StaticDataManager

def test_is_available_performance(tmp_path):
    """Тест производительности is_available()."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    # Создать 50 YAML файлов
    for i in range(50):
        yaml_path = yaml_dir / f"COMPOUND_{i}.yaml"
        yaml_path.write_text("compound:\n  formula: 'X'\n")
    
    manager = StaticDataManager(data_dir=yaml_dir)
    
    start = time.perf_counter()
    
    # 10,000 проверок
    for _ in range(10_000):
        _ = manager.is_available("COMPOUND_25")
    
    elapsed = time.perf_counter() - start
    per_call = (elapsed / 10_000) * 1_000_000  # микросекунды
    
    # Требование: <0.1 мкс/вызов
    assert per_call < 0.1, f"Слишком медленно: {per_call:.3f} мкс"
    print(f"✅ is_available(): {per_call:.3f} мкс/вызов")

def test_load_compound_first_time_performance(tmp_path):
    """Тест производительности первой загрузки YAML."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
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
    (yaml_dir / "H2O.yaml").write_text(yaml_content)
    
    manager = StaticDataManager(data_dir=yaml_dir)
    
    start = time.perf_counter()
    data = manager.load_compound("H2O")
    elapsed = (time.perf_counter() - start) * 1000  # мс
    
    # Требование: <5ms для первой загрузки
    assert elapsed < 5.0, f"Слишком медленно: {elapsed:.2f}ms"
    print(f"✅ load_compound() (первая загрузка): {elapsed:.2f}ms")

def test_load_compound_cached_performance(tmp_path):
    """Тест производительности загрузки из кэша."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    yaml_content = """
compound:
  formula: "O2"
  common_names: ["Oxygen"]
  description: "Oxygen"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1500.0
      h298: 0.0
      s298: 205.15
      f1: 29.659
      f2: 6.137
      f3: -1.186
      f4: 0.095
      f5: -0.219
      f6: -0.008
      tmelt: 54.36
      tboil: 90.20
      reliability_class: 1
  metadata:
    source_database: "test"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    (yaml_dir / "O2.yaml").write_text(yaml_content)
    
    manager = StaticDataManager(data_dir=yaml_dir)
    
    # Прогрев кэша
    manager.load_compound("O2")
    
    start = time.perf_counter()
    
    # 10,000 загрузок из кэша
    for _ in range(10_000):
        _ = manager.load_compound("O2")
    
    elapsed = time.perf_counter() - start
    per_call = (elapsed / 10_000) * 1_000_000  # микросекунды
    
    # Требование: <0.1 мкс/вызов из кэша
    assert per_call < 0.1, f"Слишком медленно: {per_call:.3f} мкс"
    print(f"✅ load_compound() (из кэша): {per_call:.3f} мкс/вызов")

def test_list_available_compounds_performance(tmp_path):
    """Тест производительности list_available_compounds()."""
    yaml_dir = tmp_path / "static_compounds"
    yaml_dir.mkdir()
    
    # Создать 100 YAML файлов
    for i in range(100):
        yaml_path = yaml_dir / f"COMPOUND_{i:03d}.yaml"
        yaml_path.write_text("compound:\n  formula: 'X'\n")
    
    manager = StaticDataManager(data_dir=yaml_dir)
    
    start = time.perf_counter()
    compounds = manager.list_available_compounds()
    elapsed = (time.perf_counter() - start) * 1000  # мс
    
    # Требование: <10ms для 100 файлов
    assert elapsed < 10.0, f"Слишком медленно: {elapsed:.2f}ms"
    assert len(compounds) == 100
    print(f"✅ list_available_compounds() (100 файлов): {elapsed:.2f}ms")
```

---

## План реализации

1. **День 1**: Создание Pydantic моделей для YAML схемы
2. **День 2**: Реализация `StaticDataManager` (загрузка, валидация)
3. **День 3**: Создание примера YAML для H2O
4. **День 4**: Интеграция с `CompoundSearcher`
5. **День 5**: Unit-тесты и документация

## Следующий этап
Stage 05: Реализация многофазного калькулятора (ThermodynamicCalculator.calculate_multi_phase)
