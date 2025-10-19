# Stage 08: Скрипт экспорта веществ в YAML

## Цель
Создать скрипт для экспорта избранных веществ из БД в YAML формат.

## Статус
🔴 Не начато

## Входные данные
- Stage 04 завершён (StaticDataManager)
- Доступ к термодинамической БД

## Выходные данные
- Скрипт `scripts/export_to_static_data.py`
- CLI для экспорта конкретных веществ
- Валидация экспортированных YAML

## Изменяемые файлы
- Создать: `scripts/export_to_static_data.py`

## Зависимости
- Stage 04 (StaticDataManager и схема YAML)

## Алгоритм действий

### Шаг 1: Создание CLI интерфейса

**Параметры командной строки:**
```bash
python scripts/export_to_static_data.py [OPTIONS]

Опции:
  --formula TEXT         Формула вещества для экспорта (например, H2O)
  --all                  Экспортировать все распространённые вещества
  --list                 Показать список распространённых веществ
  --output-dir PATH      Директория для YAML файлов (по умолчанию: data/static_compounds/)
  --validate             Только валидация существующих YAML файлов
  --check-updates        Проверить обновления в БД для существующих YAML
  --overwrite           Перезаписать существующие файлы
  --help                Показать справку
```

### Шаг 2: Подключение к БД

1. Загрузить конфигурацию подключения к БД
2. Создать `DatabaseConnector` и `SQLBuilder`
3. Создать `CompoundSearcher` для поиска записей
4. Проверить доступность БД

### Шаг 3: Поиск и извлечение записей

Для каждого вещества:
1. Вызвать `CompoundSearcher.search_all_phases(formula, max_temperature=5000)`
2. Получить все записи для всех фаз
3. Отфильтровать по `ReliabilityClass == 1` (высокая надёжность)
4. Отфильтровать по `FirstName` (основное вещество, не варианты)
5. Отсортировать по Tmin

### Шаг 4: Формирование YAML структуры

Для каждой записи:
1. Преобразовать `DatabaseRecord` → `YAMLPhaseRecord`
2. Извлечь Tmelt и Tboil для phase_transitions
3. Добавить метаданные:
   - source_database: название БД
   - extracted_date: текущая дата
   - version: версия данных
4. Добавить описание и common_names из справочника

### Шаг 5: Валидация YAML

1. Проверить структуру через `YAMLCompoundData` (Pydantic)
2. Проверить сортировку фаз по Tmin
3. Проверить покрытие 298K
4. Проверить отсутствие пробелов и перекрытий
5. Генерировать предупреждения (warnings)

### Шаг 6: Сохранение в файл

1. Форматировать YAML с комментариями
2. Добавить заголовок с описанием
3. Сохранить в `{output_dir}/{formula}.yaml`
4. Логировать успешное сохранение

### Шаг 7: Проверка обновлений (--check-updates)

Для каждого существующего YAML:
1. Загрузить из файла
2. Найти соответствующие записи в БД
3. Сравнить значения (H298, S298, f1-f6, Tmelt, Tboil)
4. Если изменения > порога (0.1%) → вывести уведомление
5. Опционально: автоматическое обновление с --auto-update

## Критерии завершения
- [ ] CLI интерфейс реализован с argparse
- [ ] Скрипт корректно экспортирует вещества из БД в YAML
- [ ] Валидация YAML работает (проверка структуры и данных)
- [ ] Опции --formula, --all, --list, --validate работают
- [ ] Опция --check-updates сравнивает БД и YAML
- [ ] Генерируются комментарии в YAML для читаемости
- [ ] Метаданные (source, date, version) заполняются автоматически
- [ ] Логирование операций (что экспортировано, ошибки)
- [ ] Unit-тесты для функций экспорта
- [ ] Документация по использованию скрипта

## Тесты
- `tests/scripts/test_export_script.py` — unit-тесты функций
- `tests/scripts/test_yaml_export_h2o.py` — экспорт H2O и проверка
- `tests/scripts/test_yaml_validation.py` — валидация YAML структуры
- `tests/scripts/test_check_updates.py` — проверка обновлений

## Риски

### Средние риски
- **Несколько записей для одного вещества**: В БД может быть несколько вариантов (разные FirstName)
  - *Митигация*: Фильтровать по ReliabilityClass == 1 и основному FirstName
  - *Митигация*: Добавить опцию --variant для выбора конкретного варианта

- **Неполные данные**: Некоторые вещества могут не иметь всех фаз
  - *Митигация*: Генерировать warnings в YAML
  - *Митигация*: Валидация покажет пробелы

### Низкие риски
- **Изменения в структуре БД**: Поля могут измениться
  - *Митигация*: Использовать `DatabaseRecord` как промежуточную модель
  - *Митигация*: Тесты с mock данными

- **Кодировка символов**: Химические формулы с индексами
  - *Митигация*: UTF-8 кодировка для YAML файлов

## Примечания

### Список распространённых веществ для экспорта

По умолчанию (из ТЗ §5.1):
1. **H2O** — Вода (s, l, g)
2. **CO2** — Углекислый газ (s, l, g)
3. **O2** — Кислород (g)
4. **N2** — Азот (g)
5. **H2** — Водород (g)
6. **NH3** — Аммиак (g, l)
7. **HCl** — Хлороводород (g, aq)
8. **CH4** — Метан (g)
9. **H2O2** — Пероксид водорода (l, g)
10. **CO** — Угарный газ (g)
11. **Fe** — Железо (s, l)
12. **S** — Сера (s, l, g)

Дополнительно (из примеров):
13. **FeO** — Оксид железа(II) (s, l)
14. **SiO2** — Диоксид кремния (s)
15. **CaO** — Оксид кальция (s)
16. **Al** — Алюминий (s, l)
17. **C** (графит) — Углерод (s)

### Пример использования

**Экспорт одного вещества:**
```bash
uv run python scripts/export_to_static_data.py --formula H2O
```

**Экспорт всех распространённых:**
```bash
uv run python scripts/export_to_static_data.py --all
```

**Проверка обновлений:**
```bash
uv run python scripts/export_to_static_data.py --check-updates
```

**Валидация существующих:**
```bash
uv run python scripts/export_to_static_data.py --validate
```

**Список веществ:**
```bash
uv run python scripts/export_to_static_data.py --list
```

### Формат вывода скрипта

```
🔍 Экспорт вещества: H2O
📊 Найдено записей: 3 (s, l, g)
✅ Валидация пройдена
💾 Сохранено в: data/static_compounds/H2O.yaml
✨ Экспорт завершён успешно

Статистика:
- Записей: 3
- Фаз: 3 (solid, liquid, gas)
- Покрытие: 200.0K - 1700.0K
- Переходы: 2 (melting at 273.15K, boiling at 373.15K)
```

### Структура скрипта

```
scripts/export_to_static_data.py
├── main() — точка входа CLI
├── export_compound(formula, output_dir) — экспорт одного вещества
├── export_all_common(output_dir) — экспорт всех распространённых
├── validate_yaml(filepath) — валидация YAML файла
├── check_updates(yaml_path, db_connector) — проверка обновлений
├── format_yaml_with_comments(compound_data) — форматирование YAML
├── get_common_compounds_list() — список распространённых веществ
└── compare_records(yaml_record, db_record) — сравнение записей
```

### Связь с другими этапами
- Использует `YAMLCompoundData` из Stage 04
- Использует `CompoundSearcher.search_all_phases()` из Stage 03
- Создаёт YAML файлы для `StaticDataManager` из Stage 04
- Независим от Stage 05-07 (может быть реализован параллельно)

---

## Примеры кода

### Пример 1: Основной скрипт экспорта

```python
# scripts/export_to_static_data.py

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional
import yaml

# Добавить путь к src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.search.database_connector import DatabaseConnector
from src.thermo_agents.search.sql_builder import SQLBuilder
from src.thermo_agents.storage.static_data_manager import StaticDataManager
from src.thermo_agents.models.static_data import YAMLCompoundData, YAMLPhaseRecord, YAMLMetadata
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Список распространённых веществ
COMMON_COMPOUNDS = [
    "H2O", "CO2", "O2", "N2", "H2", "NH3", "HCl", "CH4",
    "H2O2", "CO", "Fe", "S", "FeO", "SiO2", "CaO", "Al", "C"
]

def main():
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="Экспорт термодинамических данных из БД в YAML"
    )
    parser.add_argument(
        "--formula",
        type=str,
        help="Формула вещества для экспорта (например, H2O)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Экспортировать все распространённые вещества"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Показать список распространённых веществ"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/static_compounds",
        help="Директория для YAML файлов"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Только валидация существующих YAML файлов"
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Проверить обновления в БД для существующих YAML"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Перезаписать существующие файлы"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/thermo_data.db",
        help="Путь к БД"
    )
    
    args = parser.parse_args()
    
    # Обработка команд
    if args.list:
        print("📋 Список распространённых веществ:")
        for i, formula in enumerate(COMMON_COMPOUNDS, 1):
            print(f"  {i:2d}. {formula}")
        return 0
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.validate:
        return validate_all_yaml(output_dir)
    
    if args.check_updates:
        return check_all_updates(output_dir, args.db_path)
    
    # Подключение к БД
    db_connector = DatabaseConnector(args.db_path)
    sql_builder = SQLBuilder()
    compound_searcher = CompoundSearcher(sql_builder, db_connector)
    
    # Экспорт
    if args.all:
        return export_all_common(compound_searcher, output_dir, args.overwrite)
    elif args.formula:
        return export_compound(
            compound_searcher,
            args.formula,
            output_dir,
            args.overwrite
        )
    else:
        parser.print_help()
        return 1

def export_compound(
    searcher: CompoundSearcher,
    formula: str,
    output_dir: Path,
    overwrite: bool = False
) -> int:
    """
    Экспорт одного вещества в YAML.
    
    Returns:
        0 если успешно, 1 если ошибка
    """
    logger.info(f"🔍 Экспорт вещества: {formula}")
    
    # Проверка существования файла
    yaml_path = output_dir / f"{formula}.yaml"
    if yaml_path.exists() and not overwrite:
        logger.warning(f"⚠️ Файл {yaml_path} уже существует. Используйте --overwrite")
        return 1
    
    try:
        # Поиск всех фаз
        search_result = searcher.search_all_phases(
            formula=formula,
            max_temperature=5000.0
        )
        
        if not search_result.records:
            logger.error(f"❌ Вещество {formula} не найдено в БД")
            return 1
        
        logger.info(f"📊 Найдено записей: {len(search_result.records)}")
        
        # Фильтрация по надёжности
        reliable_records = [
            rec for rec in search_result.records
            if rec.reliability_class == 1
        ]
        
        if not reliable_records:
            logger.warning("⚠️ Нет записей с высокой надёжностью (class=1)")
            reliable_records = search_result.records
        
        # Преобразование в YAML структуру
        compound_data = convert_to_yaml_structure(
            formula=formula,
            records=reliable_records,
            search_result=search_result
        )
        
        # Валидация
        yaml_data = YAMLCompoundData(**compound_data)
        logger.info("✅ Валидация пройдена")
        
        # Сохранение
        save_yaml_with_comments(yaml_data, yaml_path)
        logger.info(f"💾 Сохранено в: {yaml_path}")
        
        # Статистика
        print_export_statistics(yaml_data, search_result)
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Ошибка экспорта: {e}")
        import traceback
        traceback.print_exc()
        return 1

def convert_to_yaml_structure(
    formula: str,
    records: List["DatabaseRecord"],
    search_result: "MultiPhaseSearchResult"
) -> dict:
    """
    Преобразование DatabaseRecord в YAML структуру.
    
    Returns:
        Словарь для YAMLCompoundData
    """
    # Определить названия
    common_names = []
    description = formula
    
    if records and records[0].name:
        description = records[0].name
        common_names.append(records[0].name)
    
    if records and records[0].first_name:
        if records[0].first_name not in common_names:
            common_names.append(records[0].first_name)
    
    # Преобразовать фазы
    phases = []
    for record in records:
        phase_data = {
            "phase": record.phase or "unknown",
            "tmin": record.tmin,
            "tmax": record.tmax,
            "h298": record.h298,
            "s298": record.s298,
            "f1": record.f1,
            "f2": record.f2,
            "f3": record.f3,
            "f4": record.f4,
            "f5": record.f5,
            "f6": record.f6,
            "tmelt": record.tmelt,
            "tboil": record.tboil,
            "first_name": record.first_name,
            "reliability_class": record.reliability_class,
            "molecular_weight": record.molecular_weight,
        }
        phases.append(phase_data)
    
    # Фазовые переходы (из search_result)
    phase_transitions = {}
    if search_result.tmelt and search_result.tmelt > 0:
        phase_transitions["melting"] = {
            "temperature": search_result.tmelt,
            "enthalpy": 0.0,  # TODO: вычислить из данных
            "entropy": 0.0,
        }
    
    if search_result.tboil and search_result.tboil > 0:
        phase_transitions["vaporization"] = {
            "temperature": search_result.tboil,
            "enthalpy": 0.0,
            "entropy": 0.0,
        }
    
    # Метаданные
    metadata = {
        "source_database": "thermo_data.db",
        "extracted_date": datetime.now().strftime("%Y-%m-%d"),
        "version": "1.0",
        "notes": f"Экспортировано {len(records)} записей для {formula}"
    }
    
    return {
        "formula": formula,
        "common_names": common_names,
        "description": description,
        "phases": phases,
        "phase_transitions": phase_transitions if phase_transitions else None,
        "metadata": metadata
    }

def save_yaml_with_comments(
    compound_data: YAMLCompoundData,
    output_path: Path
):
    """Сохранение YAML с комментариями для читаемости."""
    data = {
        "compound": compound_data.dict(exclude_none=True)
    }
    
    # Сохранение
    with open(output_path, "w", encoding="utf-8") as f:
        # Заголовок
        f.write(f"# Термодинамические данные для {compound_data.formula}\n")
        f.write(f"# Экспортировано: {compound_data.metadata.extracted_date}\n")
        f.write(f"# Источник: {compound_data.metadata.source_database}\n")
        f.write("\n")
        
        # YAML
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

def print_export_statistics(
    yaml_data: YAMLCompoundData,
    search_result: "MultiPhaseSearchResult"
):
    """Вывод статистики экспорта."""
    print("\n✨ Экспорт завершён успешно")
    print("\nСтатистика:")
    print(f"- Записей: {len(yaml_data.phases)}")
    print(f"- Фаз: {search_result.phase_count} ({search_result.phase_sequence})")
    print(f"- Покрытие: {search_result.coverage_start:.1f}K - {search_result.coverage_end:.1f}K")
    
    if yaml_data.phase_transitions:
        transitions = []
        if "melting" in yaml_data.phase_transitions:
            transitions.append(f"melting at {yaml_data.phase_transitions['melting'].temperature}K")
        if "vaporization" in yaml_data.phase_transitions:
            transitions.append(f"boiling at {yaml_data.phase_transitions['vaporization'].temperature}K")
        print(f"- Переходы: {len(transitions)} ({', '.join(transitions)})")

def export_all_common(
    searcher: CompoundSearcher,
    output_dir: Path,
    overwrite: bool
) -> int:
    """Экспорт всех распространённых веществ."""
    logger.info(f"🚀 Экспорт всех распространённых веществ ({len(COMMON_COMPOUNDS)})")
    
    success_count = 0
    fail_count = 0
    
    for formula in COMMON_COMPOUNDS:
        result = export_compound(searcher, formula, output_dir, overwrite)
        if result == 0:
            success_count += 1
        else:
            fail_count += 1
        print()  # Разделитель
    
    logger.info(f"\n✅ Успешно: {success_count}")
    if fail_count > 0:
        logger.warning(f"❌ Ошибок: {fail_count}")
    
    return 0 if fail_count == 0 else 1

def validate_all_yaml(output_dir: Path) -> int:
    """Валидация всех YAML файлов."""
    logger.info(f"🔍 Валидация YAML файлов в {output_dir}")
    
    yaml_files = list(output_dir.glob("*.yaml"))
    
    if not yaml_files:
        logger.warning("⚠️ YAML файлы не найдены")
        return 1
    
    valid_count = 0
    invalid_count = 0
    
    for yaml_path in yaml_files:
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            # Валидация через Pydantic
            YAMLCompoundData(**data["compound"])
            
            logger.info(f"✅ {yaml_path.name}: OK")
            valid_count += 1
            
        except Exception as e:
            logger.error(f"❌ {yaml_path.name}: {e}")
            invalid_count += 1
    
    logger.info(f"\n✅ Валидных: {valid_count}")
    if invalid_count > 0:
        logger.error(f"❌ Невалидных: {invalid_count}")
    
    return 0 if invalid_count == 0 else 1

def check_all_updates(output_dir: Path, db_path: str) -> int:
    """Проверка обновлений в БД для существующих YAML."""
    logger.info(f"🔄 Проверка обновлений")
    
    # Подключение к БД
    db_connector = DatabaseConnector(db_path)
    sql_builder = SQLBuilder()
    searcher = CompoundSearcher(sql_builder, db_connector)
    
    yaml_files = list(output_dir.glob("*.yaml"))
    
    updates_found = 0
    
    for yaml_path in yaml_files:
        formula = yaml_path.stem
        
        try:
            # Загрузить YAML
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            yaml_data = YAMLCompoundData(**data["compound"])
            
            # Поиск в БД
            search_result = searcher.search_all_phases(formula, max_temperature=5000.0)
            
            if not search_result.records:
                logger.warning(f"⚠️ {formula}: не найдено в БД")
                continue
            
            # Сравнение
            has_updates = compare_yaml_with_db(yaml_data, search_result.records)
            
            if has_updates:
                logger.info(f"🆕 {formula}: обнаружены обновления")
                updates_found += 1
            else:
                logger.info(f"✅ {formula}: актуально")
                
        except Exception as e:
            logger.error(f"❌ {formula}: ошибка проверки: {e}")
    
    if updates_found > 0:
        logger.info(f"\n🆕 Обновлений найдено: {updates_found}")
        logger.info("Запустите с --overwrite для обновления")
    else:
        logger.info("\n✅ Все файлы актуальны")
    
    return 0

def compare_yaml_with_db(
    yaml_data: YAMLCompoundData,
    db_records: List["DatabaseRecord"]
) -> bool:
    """
    Сравнение YAML данных с записями БД.
    
    Returns:
        True если есть различия
    """
    # Упрощённое сравнение по количеству записей
    if len(yaml_data.phases) != len(db_records):
        return True
    
    # Сравнение по H298 и S298 первой записи
    if yaml_data.phases:
        yaml_phase = yaml_data.phases[0]
        db_record = db_records[0]
        
        h_diff = abs(yaml_phase.h298 - db_record.h298)
        s_diff = abs(yaml_phase.s298 - db_record.s298)
        
        # Порог 0.1%
        if h_diff > abs(db_record.h298) * 0.001:
            return True
        if s_diff > abs(db_record.s298) * 0.001:
            return True
    
    return False

if __name__ == "__main__":
    sys.exit(main())
```

### Пример 2: Unit-тесты для скрипта

```python
# tests/scripts/test_export_script.py

import pytest
from pathlib import Path
import yaml
from scripts.export_to_static_data import (
    export_compound,
    convert_to_yaml_structure,
    validate_all_yaml,
    COMMON_COMPOUNDS
)
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.models.static_data import YAMLCompoundData

def test_export_h2o(compound_searcher, tmp_path):
    """Тест экспорта H2O."""
    result = export_compound(
        searcher=compound_searcher,
        formula="H2O",
        output_dir=tmp_path,
        overwrite=True
    )
    
    assert result == 0, "Экспорт должен завершиться успешно"
    
    # Проверка файла
    yaml_path = tmp_path / "H2O.yaml"
    assert yaml_path.exists(), "YAML файл должен быть создан"
    
    # Проверка содержимого
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    assert "compound" in data
    assert data["compound"]["formula"] == "H2O"
    assert len(data["compound"]["phases"]) >= 1

def test_convert_to_yaml_structure(h2o_search_result, h2o_records):
    """Тест преобразования в YAML структуру."""
    yaml_dict = convert_to_yaml_structure(
        formula="H2O",
        records=h2o_records,
        search_result=h2o_search_result
    )
    
    assert yaml_dict["formula"] == "H2O"
    assert "phases" in yaml_dict
    assert len(yaml_dict["phases"]) == len(h2o_records)
    assert "metadata" in yaml_dict
    assert yaml_dict["metadata"]["source_database"] == "thermo_data.db"
    
    # Валидация через Pydantic
    YAMLCompoundData(**yaml_dict)

def test_validate_all_yaml(tmp_path):
    """Тест валидации YAML файлов."""
    # Создать валидный YAML
    valid_yaml = """
compound:
  formula: "TEST"
  common_names: ["Test"]
  description: "Test compound"
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -100.0
      s298: 50.0
      f1: 30.0
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 0.0
      tboil: 0.0
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
    (tmp_path / "TEST.yaml").write_text(valid_yaml)
    
    result = validate_all_yaml(tmp_path)
    assert result == 0, "Валидация должна пройти успешно"

def test_validate_invalid_yaml(tmp_path):
    """Тест валидации невалидного YAML."""
    invalid_yaml = """
compound:
  formula: "INVALID"
  # Отсутствуют обязательные поля
"""
    (tmp_path / "INVALID.yaml").write_text(invalid_yaml)
    
    result = validate_all_yaml(tmp_path)
    assert result == 1, "Валидация должна провалиться"

def test_common_compounds_list():
    """Тест списка распространённых веществ."""
    assert "H2O" in COMMON_COMPOUNDS
    assert "CO2" in COMMON_COMPOUNDS
    assert "O2" in COMMON_COMPOUNDS
    assert len(COMMON_COMPOUNDS) >= 12
```

### Пример 3: Интеграционный тест экспорта

```python
# tests/scripts/test_yaml_export_integration.py

import pytest
import subprocess
from pathlib import Path

def test_export_script_cli(tmp_path):
    """Интеграционный тест CLI скрипта."""
    # Запуск скрипта
    result = subprocess.run(
        [
            "uv", "run", "python", "scripts/export_to_static_data.py",
            "--formula", "H2O",
            "--output-dir", str(tmp_path),
            "--db-path", "tests/fixtures/test_thermo.db"
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0, f"Скрипт завершился с ошибкой: {result.stderr}"
    
    # Проверка вывода
    assert "Экспорт вещества: H2O" in result.stdout
    assert "Сохранено в:" in result.stdout
    
    # Проверка файла
    yaml_file = tmp_path / "H2O.yaml"
    assert yaml_file.exists()

def test_export_all_cli(tmp_path):
    """Тест экспорта всех веществ через CLI."""
    result = subprocess.run(
        [
            "uv", "run", "python", "scripts/export_to_static_data.py",
            "--all",
            "--output-dir", str(tmp_path),
            "--db-path", "tests/fixtures/test_thermo.db"
        ],
        capture_output=True,
        text=True,
        timeout=60  # 60 секунд на экспорт всех
    )
    
    assert result.returncode == 0
    
    # Проверка, что созданы файлы
    yaml_files = list(tmp_path.glob("*.yaml"))
    assert len(yaml_files) > 0

def test_list_compounds_cli():
    """Тест команды --list."""
    result = subprocess.run(
        ["uv", "run", "python", "scripts/export_to_static_data.py", "--list"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "H2O" in result.stdout
    assert "CO2" in result.stdout
```
