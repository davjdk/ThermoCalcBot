# Stage 06: Обновление форматтера для многофазных данных

## Цель
Обновить `CompoundDataFormatter` для вывода информации о всех использованных сегментах и фазовых переходах.

## Статус
🔴 Не начато

## Входные данные
- Stage 01-05 завершены
- Существующий `CompoundDataFormatter`
- `MultiPhaseProperties` с результатами расчёта

## Выходные данные
- Обновлённый формат вывода "Данные веществ"
- Новый формат колонки "Комментарий" (только фазовые переходы)

## Изменяемые файлы
- `src/thermo_agents/formatting/compound_data_formatter.py`
- `src/thermo_agents/formatting/reaction_calculation_formatter.py`

## Зависимости
- Stage 01 (модели данных)
- Stage 05 (многофазный калькулятор)

## Алгоритм действий

### Шаг 1: Обновление раздела "Данные веществ"

**Текущий формат (один сегмент):**
```
Данные веществ:
FeO — Iron(II) oxide
  Фаза: s | T_применимости: 298-600 K
  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)
```

**Новый формат (все сегменты):**
```
Данные веществ:
FeO — Iron(II) oxide
  [Сегмент 1] Фаза: s | T_применимости: 298-600 K
  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)
  Cp коэффициенты: [50.278, 3.651, -1.941, 8.234, 0.000, 0.000]
  
  [Сегмент 2] Фаза: s | T_применимости: 600-900 K
  H₂₉₈: 0.000 кДж/моль (накопленное) | S₂₉₈: 0.000 Дж/(моль·K) (накопленное)
  Cp коэффициенты: [30.849, 46.228, 11.694, -19.278, 0.000, 0.000]
  
  [ФАЗОВЫЙ ПЕРЕХОД при 1650K: s → l (плавление)]
  ΔH_плавления: 32.0 кДж/моль | ΔS_плавления: 19.4 Дж/(моль·K)
  
  [Сегмент 3] Фаза: l | T_применимости: 1650-5000 K
  H₂₉₈: 24.058 кДж/моль | S₂₉₈: 14.581 Дж/(моль·K)
```

**Изменения:**
1. Нумерация сегментов: `[Сегмент 1]`, `[Сегмент 2]`, ...
2. Для H₂₉₈=0 добавить `(накопленное)` — значит используется накопленное из предыдущих сегментов
3. Выделение фазовых переходов между сегментами с типом и энергетикой
4. Все записи в хронологическом порядке по температуре

### Шаг 2: Обновление колонки "Комментарий"

**Старый формат:**
```
T(K)  | ΔH°(кДж/моль) | ΔS°(Дж/(К·моль)) | ΔG°(кДж/моль) | Комментарий
-----------------------------------------------------------------------
1473  |     -992.17   |         52.78    |     -1069.91  | Экзергоническая
```

**Новый формат:**
```
T(K)  | ΔH°(кДж/моль) | ΔS°(Дж/(К·моль)) | ΔG°(кДж/моль) | Комментарий
-----------------------------------------------------------------------
 298  |     -82.61    |        -11.83    |      -79.08   | 
 523  |     -86.15    |        -10.92    |      -80.44   | SiO2: s→s (α-кварц → кристобалит)
1473  |     -92.17    |         -9.22    |      -78.59   | 
1650  |     -91.45    |         -8.76    |      -76.79   | FeO: s→l (плавление)
```

**Правила:**
1. **Убрать** информацию о спонтанности ("Экзергоническая", "Эндергоническая")
2. **Добавить** информацию о фазовых переходах: `{Вещество}: {from}→{to} ({тип})`
3. Если смена записи без изменения фазы: `{Вещество}: {phase}→{phase} (смена записи)`
4. Если несколько веществ имеют переходы: разделять через `; `
5. Если нет переходов: колонка остается пустой

### Шаг 3: Добавление метаданных в конце вывода

**Новые строки:**
```
Использовано сегментов расчёта: CaO(1), SiO2(2), CaSiO3(1)
Фазовых переходов обнаружено: 2 (SiO2)
Шаг по температуре: 100 K (плюс точки фазовых переходов)
```

### Шаг 4: Интеграция с MultiPhaseProperties

1. Метод форматтера должен принимать `MultiPhaseProperties` вместо `ThermodynamicProperties`
2. Извлекать информацию из `segments` и `phase_transitions`
3. Генерировать вывод для каждого сегмента
4. Интерполировать фазовые переходы в таблицу результатов

## Критерии завершения
- [ ] Форматтер выводит все использованные сегменты с нумерацией
- [ ] Для H₂₉₈=0 выводится "(накопленное)"
- [ ] Фазовые переходы отображаются между сегментами с ΔH и ΔS
- [ ] Колонка "Комментарий" содержит только фазовые переходы
- [ ] Информация о спонтанности удалена из колонки "Комментарий"
- [ ] Cp коэффициенты форматируются как массив
- [ ] Метаданные (количество сегментов, переходов) выводятся в конце
- [ ] Unit-тесты для форматирования всех типов вывода
- [ ] Обратная совместимость: старый формат работает для одиночных записей

## Тесты
- `tests/formatting/test_multi_phase_formatter.py` — unit-тесты форматтера
- `tests/formatting/test_compound_data_formatter_multiphase.py` — тест раздела "Данные веществ"
- `tests/formatting/test_reaction_formatter_transitions.py` — тест колонки "Комментарий"

## Риски

### Средние риски
- **Обратная совместимость**: Старый код может ожидать определённый формат вывода
  - *Митигация*: Добавить флаг `use_multi_phase_format=True/False`
  - *Митигация*: Тесты для обоих форматов

- **Длинный вывод**: Для веществ с 10+ сегментами вывод может быть очень большим
  - *Митигация*: Опция сворачивания промежуточных сегментов
  - *Митигация*: Показывать только ключевые сегменты (первый, последний, переходы)

### Низкие риски
- **Форматирование чисел**: Разные единицы (кДж/моль vs Дж/моль) могут запутать
  - *Митигация*: Чётко указывать единицы в каждом поле

## Примечания

### Примеры вывода из ТЗ (§6.3)

**Пример 1: FeO с плавлением**
```
Данные веществ:

FeO — Iron(II) oxide (Вюстит)
  [Сегмент 1] Фаза: s | T_применимости: 298-600 K
  H₂₉₈: -265.053 кДж/моль | S₂₉₈: 59.807 Дж/(моль·K)
  Cp коэффициенты: [50.278, 3.651, -1.941, 8.234, 0.000, 0.000]
  
  [Сегмент 2] Фаза: s | T_применимости: 600-900 K
  H₂₉₈: 0.000 кДж/моль (накопленное) | S₂₉₈: 0.000 Дж/(моль·K) (накопленное)
  Cp коэффициенты: [30.849, 46.228, 11.694, -19.278, 0.000, 0.000]
  
  [ФАЗОВЫЙ ПЕРЕХОД при 1650K: s → l (плавление)]
  ΔH_плавления: ~32 кДж/моль | ΔS_плавления: ~19 Дж/(моль·K)
  
  [Сегмент 5] Фаза: l | T_применимости: 1650-5000 K
  H₂₉₈: 24.058 кДж/моль | S₂₉₈: 14.581 Дж/(моль·K)
  Cp коэффициенты: [68.199, 0.000, 0.000, 0.000, 0.000, 0.000]
  Примечание: Константная теплоёмкость для жидкой фазы

Результаты расчёта:
T(K)  | ΔH°(кДж/моль) | ΔS°(Дж/(К·моль)) | ΔG°(кДж/моль) | Комментарий
-----------------------------------------------------------------------
 298  |     -142.10   |        188.13    |     -198.19   | 
 600  |     -135.82   |        195.45    |     -253.09   | FeO: s→s (смена записи)
 900  |     -128.42   |        203.88    |     -311.91   | FeO: s→s (смена записи)
1300  |     -118.56   |        215.72    |     -398.99   | FeO: s→s (смена записи)
1650  |     -110.34   |        225.18    |     -481.63   | FeO: s→l (плавление, ΔH=+32 кДж/моль)
1700  |     -109.87   |        226.05    |     -493.96   | 

Использовано сегментов: 5 (4 твёрдых + 1 жидкая)
Фазовых переходов: 1 (плавление при 1650K)
```

**Пример 2: Реакция с несколькими переходами**
```
Данные веществ:

CaO — Calcium oxide
  [Сегмент 1] Фаза: s | T_применимости: 298-3200 K
  H₂₉₈: -635.089 кДж/моль | S₂₉₈: 38.074 Дж/(моль·K)

SiO2 — Silicon dioxide
  [Сегмент 1] Фаза: s (α-кварц) | T_применимости: 298-847 K
  H₂₉₈: -910.700 кДж/моль | S₂₉₈: 41.460 Дж/(моль·K)
  
  [Сегмент 2] Фаза: s (кристобалит) | T_применимости: 523-4000 K
  H₂₉₈: 0.000 кДж/моль (накопленное) | S₂₉₈: 0.000 Дж/(моль·K) (накопленное)
  Примечание: Базовые значения накоплены из предыдущего сегмента (α-кварц)

CaSiO3(P) — Calcium silicate (псевдоволластонит)
  [Сегмент 1] Фаза: s | T_применимости: 298-1817 K
  H₂₉₈: -1628.398 кДж/моль | S₂₉₈: 87.362 Дж/(моль·K)

Результаты расчёта:
T(K)  | ΔH°(кДж/моль) | ΔS°(Дж/(К·моль)) | ΔG°(кДж/моль) | Комментарий
-----------------------------------------------------------------------
 298  |     -82.61    |        -11.83    |      -79.08   | 
 523  |     -86.15    |        -10.92    |      -80.44   | SiO2: s→s (α-кварц → кристобалит)
 847  |     -88.94    |        -10.15    |      -80.34   | SiO2: s→s (переход β-кварц)
1473  |     -92.17    |         -9.22    |      -78.59   | 
1773  |     -90.95    |         -8.47    |      -75.94   | 

Использовано сегментов расчёта: CaO(1), SiO2(2), CaSiO3(1)
Фазовых переходов обнаружено: 2 (SiO2)
```

### Связь с другими этапами
- Использует `MultiPhaseProperties` из Stage 01
- Получает данные расчёта от Stage 05
- Результаты используются в Stage 07 (интеграция с оркестратором)

---

## Примеры кода

### Пример 1: Форматирование раздела "Данные веществ"

```python
# src/thermo_agents/formatting/compound_data_formatter.py

from typing import List
from ..models.search import DatabaseRecord, MultiPhaseProperties

class CompoundDataFormatter:
    """Форматтер для вывода данных веществ."""
    
    def format_compound_data_multi_phase(
        self,
        formula: str,
        compound_name: str,
        multi_phase_result: MultiPhaseProperties
    ) -> str:
        """
        Форматирование раздела "Данные веществ" для многофазного расчёта.
        
        Args:
            formula: Химическая формула
            compound_name: Название вещества
            multi_phase_result: Результат многофазного расчёта
            
        Returns:
            Отформатированная строка
        """
        lines = []
        lines.append(f"{formula} — {compound_name}")
        
        segment_num = 1
        for i, segment in enumerate(multi_phase_result.segments):
            # Заголовок сегмента
            phase_name = self._get_phase_name(segment.record.phase)
            lines.append(
                f"  [Сегмент {segment_num}] Фаза: {segment.record.phase} | "
                f"T_применимости: {segment.T_start:.0f}-{segment.T_end:.0f} K"
            )
            
            # H298 и S298
            if segment.record.is_base_record():
                lines.append(
                    f"  H₂₉₈: {segment.record.h298 / 1000:.3f} кДж/моль | "
                    f"S₂₉₈: {segment.record.s298:.3f} Дж/(моль·K)"
                )
            else:
                lines.append(
                    f"  H₂₉₈: 0.000 кДж/моль (накопленное) | "
                    f"S₂₉₈: 0.000 Дж/(моль·K) (накопленное)"
                )
            
            # Cp коэффициенты
            cp_coeffs = [
                segment.record.f1, segment.record.f2, segment.record.f3,
                segment.record.f4, segment.record.f5, segment.record.f6
            ]
            cp_str = ", ".join(f"{c:.3f}" for c in cp_coeffs)
            lines.append(f"  Cp коэффициенты: [{cp_str}]")
            
            # Дополнительная информация
            if segment.record.first_name:
                lines.append(f"  Источник: {segment.record.first_name}")
            if segment.record.reliability_class:
                lines.append(f"  Надёжность: {segment.record.reliability_class} (высокая)")
            
            # Фазовый переход после сегмента
            if segment.is_transition_boundary and i < len(multi_phase_result.phase_transitions):
                transition = multi_phase_result.phase_transitions[i]
                lines.append("")
                lines.append(
                    f"  [ФАЗОВЫЙ ПЕРЕХОД при {transition.temperature:.0f}K: "
                    f"{transition.from_phase} → {transition.to_phase} ({transition.transition_type})]"
                )
                if abs(transition.delta_H_transition) > 0.01:
                    lines.append(
                        f"  ΔH_{transition.transition_type}: {transition.delta_H_transition:.2f} кДж/моль | "
                        f"ΔS_{transition.transition_type}: {transition.delta_S_transition:.2f} Дж/(моль·K)"
                    )
            
            lines.append("")
            segment_num += 1
        
        return "\n".join(lines)
    
    def _get_phase_name(self, phase: str) -> str:
        """Получение читаемого названия фазы."""
        phase_names = {
            "s": "твёрдая",
            "l": "жидкая",
            "g": "газовая",
            "aq": "водный раствор"
        }
        return phase_names.get(phase, phase)
```

### Пример 2: Форматирование колонки "Комментарий"

```python
# src/thermo_agents/formatting/reaction_calculation_formatter.py

from typing import Dict, List
from ..models.search import MultiPhaseProperties

class ReactionCalculationFormatter:
    """Форматтер для вывода результатов расчёта реакций."""
    
    def format_comment_column(
        self,
        T: float,
        compounds_multi_phase: Dict[str, MultiPhaseProperties]
    ) -> str:
        """
        Форматирование колонки "Комментарий" с фазовыми переходами.
        
        Args:
            T: Текущая температура
            compounds_multi_phase: Словарь {формула: MultiPhaseProperties}
            
        Returns:
            Строка комментария (пустая если нет переходов)
        """
        comments = []
        
        for formula, mp_result in compounds_multi_phase.items():
            # Проверить, есть ли фазовый переход при температуре T
            for transition in mp_result.phase_transitions:
                if abs(transition.temperature - T) < 1.0:  # Допуск 1K
                    comment = self._format_transition_comment(
                        formula, transition
                    )
                    comments.append(comment)
            
            # Проверить смену записи без изменения фазы
            for segment in mp_result.segments:
                if abs(segment.T_end - T) < 1.0:
                    if segment.is_transition_boundary:
                        continue  # Уже добавлено как переход
                    
                    # Смена записи в той же фазе
                    phase = segment.record.phase
                    comments.append(f"{formula}: {phase}→{phase} (смена записи)")
        
        return "; ".join(comments) if comments else ""
    
    def _format_transition_comment(
        self,
        formula: str,
        transition: "PhaseTransition"
    ) -> str:
        """
        Форматирование комментария для фазового перехода.
        
        Returns:
            Строка вида "FeO: s→l (плавление, ΔH=+32 кДж/моль)"
        """
        transition_names = {
            "melting": "плавление",
            "boiling": "кипение",
            "sublimation": "сублимация"
        }
        
        transition_name = transition_names.get(
            transition.transition_type,
            transition.transition_type
        )
        
        comment = (
            f"{formula}: {transition.from_phase}→{transition.to_phase} "
            f"({transition_name}"
        )
        
        if abs(transition.delta_H_transition) > 0.01:
            comment += f", ΔH={transition.delta_H_transition:+.1f} кДж/моль"
        
        comment += ")"
        
        return comment
    
    def format_results_table_with_transitions(
        self,
        temperatures: List[float],
        delta_H: List[float],
        delta_S: List[float],
        delta_G: List[float],
        compounds_multi_phase: Dict[str, MultiPhaseProperties]
    ) -> str:
        """
        Форматирование таблицы результатов с колонкой "Комментарий".
        
        Returns:
            Отформатированная таблица
        """
        from tabulate import tabulate
        
        # Подготовка данных
        table_data = []
        for i, T in enumerate(temperatures):
            comment = self.format_comment_column(T, compounds_multi_phase)
            
            row = [
                f"{T:.0f}",
                f"{delta_H[i]:.2f}",
                f"{delta_S[i]:.2f}",
                f"{delta_G[i]:.2f}",
                comment
            ]
            table_data.append(row)
        
        # Заголовки
        headers = [
            "T(K)",
            "ΔH°(кДж/моль)",
            "ΔS°(Дж/(К·моль))",
            "ΔG°(кДж/моль)",
            "Комментарий"
        ]
        
        # Форматирование
        table = tabulate(
            table_data,
            headers=headers,
            tablefmt="simple",
            stralign="right"
        )
        
        return table
```

### Пример 3: Добавление метаданных

```python
# src/thermo_agents/formatting/reaction_calculation_formatter.py

def format_metadata(
    self,
    compounds_multi_phase: Dict[str, MultiPhaseProperties]
) -> str:
    """
    Форматирование метаданных о сегментах и переходах.
    
    Args:
        compounds_multi_phase: Словарь {формула: MultiPhaseProperties}
        
    Returns:
        Строка с метаданными
    """
    lines = []
    
    # Подсчёт сегментов
    segments_info = []
    total_segments = 0
    for formula, mp_result in compounds_multi_phase.items():
        count = len(mp_result.segments)
        total_segments += count
        
        # Определить типы фаз
        phases = list(set(seg.record.phase for seg in mp_result.segments))
        phase_desc = self._describe_phases(phases)
        
        segments_info.append(f"{formula}({count} {phase_desc})")
    
    lines.append(f"Использовано сегментов расчёта: {', '.join(segments_info)}")
    
    # Подсчёт фазовых переходов
    total_transitions = sum(
        len(mp.phase_transitions) for mp in compounds_multi_phase.values()
    )
    
    if total_transitions > 0:
        # Детали переходов
        transition_details = []
        for formula, mp_result in compounds_multi_phase.items():
            if mp_result.phase_transitions:
                transition_details.append(f"{formula}")
        
        lines.append(
            f"Фазовых переходов обнаружено: {total_transitions} "
            f"({', '.join(transition_details)})"
        )
    else:
        lines.append("Фазовых переходов не обнаружено")
    
    # Шаг по температуре
    lines.append("Шаг по температуре: 100 K (плюс точки фазовых переходов)")
    
    return "\n".join(lines)

def _describe_phases(self, phases: List[str]) -> str:
    """Описание фаз (твёрдых, жидких и т.д.)."""
    phase_counts = {
        "s": "твёрдых",
        "l": "жидких",
        "g": "газовых"
    }
    
    descriptions = []
    for phase in phases:
        if phase in phase_counts:
            descriptions.append(phase_counts[phase])
    
    return " + ".join(descriptions) if descriptions else "фаз"
```

### Пример 4: Unit-тест форматтера

```python
# tests/formatting/test_multi_phase_formatter.py

import pytest
from src.thermo_agents.formatting.compound_data_formatter import CompoundDataFormatter
from src.thermo_agents.models.search import (
    DatabaseRecord, PhaseSegment, PhaseTransition, MultiPhaseProperties
)

@pytest.fixture
def feo_multi_phase_result():
    """Результат многофазного расчёта для FeO."""
    # Создание сегментов
    segment1 = PhaseSegment(
        record=DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265053.0, s298=59.807,
            f1=50.278, f2=3.651, f3=-1.941, f4=8.234, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1,
            first_name="Iron(II) oxide"
        ),
        T_start=298.0, T_end=600.0,
        H_start=-265053.0, S_start=59.807,
        delta_H=15420.0, delta_S=36.85,
        is_transition_boundary=False
    )
    
    segment5 = PhaseSegment(
        record=DatabaseRecord(
            formula="FeO", phase="l", tmin=1650.0, tmax=5000.0,
            h298=24058.0, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1,
            first_name="Iron(II) oxide"
        ),
        T_start=1650.0, T_end=1700.0,
        H_start=-145510.0, S_start=186.08,
        delta_H=3410.0, delta_S=2.05,
        is_transition_boundary=True
    )
    
    # Фазовый переход
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )
    
    return MultiPhaseProperties(
        T_target=1700.0,
        H_final=-142100.0,
        S_final=188.13,
        G_final=-461920.0,
        Cp_final=68.199,
        segments=[segment1, segment5],
        phase_transitions=[transition],
        temperature_path=[298.0, 600.0, 1650.0, 1700.0],
        H_path=[-265053.0, -249630.0, -145510.0, -142100.0],
        S_path=[59.807, 96.66, 186.08, 188.13],
        warnings=[]
    )

def test_format_compound_data_multi_phase(feo_multi_phase_result):
    """Тест форматирования раздела "Данные веществ"."""
    formatter = CompoundDataFormatter()
    
    result = formatter.format_compound_data_multi_phase(
        formula="FeO",
        compound_name="Iron(II) oxide",
        multi_phase_result=feo_multi_phase_result
    )
    
    # Проверки содержимого
    assert "FeO — Iron(II) oxide" in result
    assert "[Сегмент 1]" in result
    assert "[Сегмент 2]" in result
    assert "298-600 K" in result
    assert "1650-1700 K" in result
    assert "-265.053 кДж/моль" in result
    assert "(накопленное)" not in result  # Только для H298=0
    assert "ФАЗОВЫЙ ПЕРЕХОД при 1650K" in result
    assert "s → l" in result
    assert "melting" in result or "плавление" in result

def test_format_comment_column_with_transition():
    """Тест форматирования колонки "Комментарий" с переходом."""
    formatter = ReactionCalculationFormatter()
    
    transition = PhaseTransition(
        temperature=1650.0,
        from_phase="s",
        to_phase="l",
        transition_type="melting",
        delta_H_transition=32.0,
        delta_S_transition=19.4
    )
    
    mp_result = MultiPhaseProperties(
        T_target=1700.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[transition],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )
    
    comment = formatter.format_comment_column(
        T=1650.0,
        compounds_multi_phase={"FeO": mp_result}
    )
    
    assert "FeO" in comment
    assert "s→l" in comment
    assert "плавление" in comment or "melting" in comment
    assert "ΔH=" in comment

def test_format_comment_column_no_transition():
    """Тест форматирования колонки "Комментарий" без переходов."""
    formatter = ReactionCalculationFormatter()
    
    mp_result = MultiPhaseProperties(
        T_target=500.0,
        H_final=0.0, S_final=0.0, G_final=0.0, Cp_final=0.0,
        segments=[], phase_transitions=[],
        temperature_path=[], H_path=[], S_path=[], warnings=[]
    )
    
    comment = formatter.format_comment_column(
        T=500.0,
        compounds_multi_phase={"H2O": mp_result}
    )
    
    assert comment == "", "Комментарий должен быть пустым без переходов"

def test_format_metadata():
    """Тест форматирования метаданных."""
    formatter = ReactionCalculationFormatter()
    
    # ... (создание mp_result с сегментами и переходами)
    
    metadata = formatter.format_metadata(
        compounds_multi_phase={"FeO": mp_result, "SiO2": mp_result2}
    )
    
    assert "Использовано сегментов расчёта:" in metadata
    assert "FeO" in metadata
    assert "SiO2" in metadata
    assert "Фазовых переходов обнаружено:" in metadata
    assert "Шаг по температуре:" in metadata
```

### Пример 5: Интеграционный тест полного вывода

```python
# tests/integration/test_formatter_full_output.py

def test_full_reaction_output_with_transitions(compound_searcher, calculator, formatter):
    """Тест полного вывода реакции с фазовыми переходами."""
    # Поиск веществ
    cao_result = compound_searcher.search_all_phases("CaO", max_temperature=1800.0)
    sio2_result = compound_searcher.search_all_phases("SiO2", max_temperature=1800.0)
    casio3_result = compound_searcher.search_all_phases("CaSiO3", max_temperature=1800.0)
    
    # Расчёты для каждого вещества
    cao_mp = calculator.calculate_multi_phase_properties(cao_result.records, 1773.0)
    sio2_mp = calculator.calculate_multi_phase_properties(sio2_result.records, 1773.0)
    casio3_mp = calculator.calculate_multi_phase_properties(casio3_result.records, 1773.0)
    
    # Форматирование
    output = formatter.format_full_reaction_output(
        reaction="CaO + SiO2 → CaSiO3",
        temperatures=[298, 523, 847, 1473, 1773],
        compounds_multi_phase={
            "CaO": cao_mp,
            "SiO2": sio2_mp,
            "CaSiO3": casio3_mp
        }
    )
    
    # Проверки
    assert "Данные веществ:" in output
    assert "[Сегмент" in output
    assert "SiO2: s→s (α-кварц → кристобалит)" in output
    assert "Использовано сегментов расчёта:" in output
    assert "CaO(1)" in output
    assert "SiO2(2)" in output
```
