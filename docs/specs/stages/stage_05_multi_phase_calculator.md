# Stage 05: Многофазный термодинамический калькулятор

## Цель
Реализовать метод `calculate_multi_phase_properties()` для расчёта через несколько температурных сегментов и фаз.

## Статус
🔴 Не начато

## Входные данные
- Stage 01-04 завершены
- Существующий `ThermodynamicCalculator`
- Список `DatabaseRecord` для всех фаз вещества

## Выходные данные
- Метод `calculate_multi_phase_properties()`
- `MultiPhaseProperties` с результатами расчёта

## Изменяемые файлы
- `src/thermo_agents/calculations/thermodynamic_calculator.py`

## Зависимости
- Stage 01 (модели данных)
- Stage 02 (расширения DatabaseRecord)
- Stage 03 (поиск всех фаз)

## Алгоритм действий

### Шаг 1: Валидация входных данных
1. Проверить, что список `records` не пустой
2. Отсортировать записи по `Tmin` (если ещё не отсортированы)
3. Проверить, что `T_target` находится в пределах покрытия записей
4. Проверить наличие базовой записи (первая должна иметь H298≠0)

### Шаг 2: Определение начальной температуры
1. Если записи покрывают 298K → начать с 298K
2. Иначе начать с `records[0].Tmin`
3. Установить базовые значения H и S из первой записи

### Шаг 3: Построение температурной траектории
Для каждой записи в списке:
1. Определить `T_start` и `T_end` для сегмента:
   - `T_start` = max(current_T, record.Tmin)
   - `T_end` = min(T_target, record.Tmax)
2. Если `T_end <= T_start` → пропустить запись
3. Создать `PhaseSegment` с начальными H и S

### Шаг 4: Интегрирование в каждом сегменте
Для каждого сегмента:
1. Вычислить `ΔH = ∫[T_start→T_end] Cp(T) dT`
2. Вычислить `ΔS = ∫[T_start→T_end] Cp(T)/T dT`
3. Обновить накопленные значения:
   - `H_accumulated += ΔH`
   - `S_accumulated += ΔS`
4. Сохранить сегмент в список

### Шаг 5: Обработка фазовых переходов
На границе между сегментами:
1. Проверить, совпадают ли `record[i].Tmax` и `record[i+1].Tmin`
2. Проверить изменение фазы (`record[i].phase != record[i+1].phase`)
3. Если фазовый переход:
   - Определить тип перехода (melting/boiling/sublimation)
   - Если `record[i+1].H298 ≠ 0`: использовать его как новую базу
   - Иначе: продолжить накопление
   - Создать `PhaseTransition` и добавить в список
4. Логировать переход

### Шаг 6: Финальный расчёт
1. Вычислить `Cp_final` при `T_target` для последней записи
2. Вычислить `G_final = H_final - T_target * S_final`
3. Построить траектории (temperature_path, H_path, S_path)
4. Собрать предупреждения (если были пробелы, перекрытия)

### Шаг 7: Возврат результата
Создать и вернуть `MultiPhaseProperties` со всеми данными.

## Критерии завершения
- [ ] Метод `calculate_multi_phase_properties()` реализован
- [ ] Корректное накопление H и S через сегменты (проверено на примере FeO)
- [ ] Обработка фазовых переходов s→l, l→g, s→g
- [ ] Интегрирование работает с переменным шагом (адаптивное)
- [ ] Построение температурных траекторий (для графиков)
- [ ] Генерация предупреждений о проблемах покрытия
- [ ] Unit-тесты покрывают все сценарии (≥90%)
- [ ] Интеграционные тесты с реальными данными (H2O, FeO, SiO2)
- [ ] Производительность: расчёт 5 сегментов < 100ms

## Тесты
- `tests/calculations/test_multi_phase_calculator.py` — unit-тесты
- `tests/integration/test_feo_multi_phase.py` — тест примера из ТЗ (FeO при 1700K)
- `tests/integration/test_h2o_phase_transitions.py` — тест переходов воды

## Риски

### Высокие риски
- **Накопление ошибок интегрирования**: При последовательном интегрировании через 5+ сегментов ошибки могут накапливаться
  - *Митигация*: Использовать scipy.integrate.quad для высокой точности
  - *Митигация*: Добавить валидацию по контрольным точкам

### Средние риски
- **Обработка нестандартных фазовых переходов**: Некоторые вещества имеют несколько твёрдых фаз (полиморфы)
  - *Митигация*: Поддерживать переходы s→s с разными названиями фаз
  
- **Отсутствие данных для фазовых переходов**: ΔH_melting и ΔS_melting могут быть неизвестны
  - *Митигация*: Использовать приближение через разницу базовых значений H298 и S298

### Низкие риски
- **Производительность**: Интегрирование может быть медленным для большого количества сегментов
  - *Митигация*: Кэшировать результаты интегрирования для типовых диапазонов

## Примечания

### Математические формулы
Используются формулы из ТЗ §4.3-4.5:

**Энтальпия:**
$$
H(T) = H_{base} + \int_{T_{start}}^{T} C_p(T) dT
$$

**Энтропия:**
$$
S(T) = S_{base} + \int_{T_{start}}^{T} \frac{C_p(T)}{T} dT
$$

**Энергия Гиббса:**
$$
G(T) = H(T) - T \cdot S(T)
$$

### Ключевые особенности реализации
1. **Начало с 298K**: Если первая запись покрывает 298K, используем её H298 и S298 как базу
2. **Накопление через сегменты**: Для записей с H298=0 используем накопленные значения
3. **Фазовые переходы**: Если следующая запись имеет H298≠0, это новая база (скачок энтальпии)
4. **Траектории**: Сохраняем промежуточные значения для построения графиков

### Связь с другими этапами
- Использует `PhaseSegment`, `PhaseTransition`, `MultiPhaseProperties` из Stage 01
- Использует методы `DatabaseRecord` из Stage 02
- Получает список записей от `CompoundSearcher.search_all_phases()` из Stage 03
- Результаты форматируются в Stage 06

---

## Примеры кода

### Пример 1: Основной метод calculate_multi_phase_properties

```python
# src/thermo_agents/calculations/thermodynamic_calculator.py

from typing import List, Optional
import numpy as np
from scipy.integrate import quad

from ..models.search import DatabaseRecord, PhaseSegment, PhaseTransition, MultiPhaseProperties

class ThermodynamicCalculator:
    """Термодинамический калькулятор."""
    
    def __init__(self, num_integration_points: int = 400):
        self.T_REF = 298.15
        self.num_integration_points = num_integration_points
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def calculate_multi_phase_properties(
        self,
        records: List[DatabaseRecord],
        T_target: float,
        T_start: Optional[float] = None
    ) -> MultiPhaseProperties:
        """
        Расчёт термодинамических свойств через несколько фаз и температурных сегментов.
        
        Args:
            records: Список записей БД, отсортированных по Tmin
            T_target: Целевая температура расчёта, K
            T_start: Начальная температура (по умолчанию 298.15K или records[0].Tmin)
            
        Returns:
            MultiPhaseProperties с результатами расчёта
            
        Raises:
            ValueError: Если records пустой или T_target вне покрытия
        """
        # Шаг 1: Валидация входных данных
        if not records:
            raise ValueError("Список records пустой")
        
        if len(records) > 1 and records[0].tmin > records[-1].tmin:
            self.logger.warning("Записи не отсортированы по Tmin, выполняю сортировку")
            records = sorted(records, key=lambda r: r.tmin)
        
        if T_target > records[-1].tmax:
            raise ValueError(
                f"T_target={T_target}K выходит за пределы покрытия "
                f"(max={records[-1].tmax}K)"
            )
        
        # Шаг 2: Определение начальной температуры и базовых значений
        if T_start is None:
            # Если первая запись покрывает 298K, начинаем с 298K
            if records[0].tmin <= self.T_REF <= records[0].tmax:
                T_start = self.T_REF
            else:
                T_start = records[0].tmin
        
        # Проверка базовой записи
        if not records[0].is_base_record():
            self.logger.warning(
                f"Первая запись {records[0].formula} не является базовой (H298=0, S298=0)"
            )
        
        H_base = records[0].h298  # Дж/моль
        S_base = records[0].s298  # Дж/(моль·K)
        
        # Шаг 3-6: Построение траектории и интегрирование
        segments = []
        phase_transitions = []
        temperature_path = [T_start]
        H_path = [H_base]
        S_path = [S_base]
        warnings = []
        
        H_accumulated = H_base
        S_accumulated = S_base
        current_T = T_start
        
        for i, record in enumerate(records):
            # Определить границы сегмента
            segment_T_start = max(current_T, record.tmin)
            segment_T_end = min(T_target, record.tmax)
            
            if segment_T_end <= segment_T_start:
                continue  # Сегмент не используется
            
            # Интегрирование в сегменте
            delta_H = self._integrate_enthalpy(record, segment_T_start, segment_T_end)
            delta_S = self._integrate_entropy(record, segment_T_start, segment_T_end)
            
            # Создать сегмент
            segment = PhaseSegment(
                record=record,
                T_start=segment_T_start,
                T_end=segment_T_end,
                H_start=H_accumulated,
                S_start=S_accumulated,
                delta_H=delta_H,
                delta_S=delta_S,
                is_transition_boundary=False
            )
            
            # Обновить накопленные значения
            H_accumulated += delta_H
            S_accumulated += delta_S
            
            # Сохранить траекторию
            temperature_path.append(segment_T_end)
            H_path.append(H_accumulated)
            S_path.append(S_accumulated)
            
            segments.append(segment)
            
            # Шаг 5: Проверка фазового перехода
            if i < len(records) - 1:
                next_record = records[i + 1]
                transition = self._check_phase_transition(
                    record, next_record, segment_T_end, H_accumulated, S_accumulated
                )
                
                if transition:
                    phase_transitions.append(transition)
                    segment.is_transition_boundary = True
                    
                    # Если следующая запись имеет свою базу, обновляем
                    if next_record.is_base_record():
                        # Вычисляем скачок энтальпии и энтропии
                        H_next_base = self._calculate_H_at_T(
                            next_record, segment_T_end, next_record.h298
                        )
                        S_next_base = self._calculate_S_at_T(
                            next_record, segment_T_end, next_record.s298
                        )
                        
                        transition.delta_H_transition = (H_next_base - H_accumulated) / 1000  # кДж/моль
                        transition.delta_S_transition = S_next_base - S_accumulated
                        
                        H_accumulated = H_next_base
                        S_accumulated = S_next_base
            
            current_T = segment_T_end
            
            # Если достигли целевой температуры, выходим
            if current_T >= T_target:
                break
        
        # Шаг 7: Финальный расчёт
        Cp_final = self.calculate_cp(segments[-1].record, T_target)
        G_final = H_accumulated - T_target * S_accumulated
        
        return MultiPhaseProperties(
            T_target=T_target,
            H_final=H_accumulated,
            S_final=S_accumulated,
            G_final=G_final,
            Cp_final=Cp_final,
            segments=segments,
            phase_transitions=phase_transitions,
            temperature_path=temperature_path,
            H_path=H_path,
            S_path=S_path,
            warnings=warnings
        )
    
    def _integrate_enthalpy(
        self,
        record: DatabaseRecord,
        T_start: float,
        T_end: float
    ) -> float:
        """
        Интегрирование энтальпии: ΔH = ∫[T_start→T_end] Cp(T) dT
        
        Returns:
            ΔH в Дж/моль
        """
        def integrand(T):
            return self.calculate_cp(record, T)
        
        result, error = quad(integrand, T_start, T_end)
        return result
    
    def _integrate_entropy(
        self,
        record: DatabaseRecord,
        T_start: float,
        T_end: float
    ) -> float:
        """
        Интегрирование энтропии: ΔS = ∫[T_start→T_end] Cp(T)/T dT
        
        Returns:
            ΔS в Дж/(моль·K)
        """
        def integrand(T):
            return self.calculate_cp(record, T) / T
        
        result, error = quad(integrand, T_start, T_end)
        return result
    
    def _check_phase_transition(
        self,
        current_record: DatabaseRecord,
        next_record: DatabaseRecord,
        T_boundary: float,
        H_current: float,
        S_current: float
    ) -> Optional[PhaseTransition]:
        """
        Проверка наличия фазового перехода между записями.
        
        Returns:
            PhaseTransition или None
        """
        # Проверка соприкосновения температурных диапазонов
        if abs(current_record.tmax - next_record.tmin) > 1e-3:
            return None
        
        # Проверка изменения фазы
        if current_record.phase == next_record.phase:
            return None  # Нет изменения фазы
        
        # Определить тип перехода
        transition_type_str = current_record.get_transition_type(next_record)
        
        if not transition_type_str:
            return None
        
        # Создать объект перехода
        return PhaseTransition(
            temperature=T_boundary,
            from_phase=current_record.phase or "unknown",
            to_phase=next_record.phase or "unknown",
            transition_type=transition_type_str,
            delta_H_transition=0.0,  # Будет вычислено позже
            delta_S_transition=0.0
        )
    
    def _calculate_H_at_T(
        self,
        record: DatabaseRecord,
        T: float,
        H_base: float
    ) -> float:
        """Вычисление H(T) от базовой температуры."""
        if record.tmin <= self.T_REF <= record.tmax:
            T_base = self.T_REF
        else:
            T_base = record.tmin
        
        delta_H = self._integrate_enthalpy(record, T_base, T)
        return H_base + delta_H
    
    def _calculate_S_at_T(
        self,
        record: DatabaseRecord,
        T: float,
        S_base: float
    ) -> float:
        """Вычисление S(T) от базовой температуры."""
        if record.tmin <= self.T_REF <= record.tmax:
            T_base = self.T_REF
        else:
            T_base = record.tmin
        
        delta_S = self._integrate_entropy(record, T_base, T)
        return S_base + delta_S
```

### Пример 2: Unit-тест для FeO (пример из ТЗ)

```python
# tests/calculations/test_multi_phase_calculator.py

import pytest
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
from src.thermo_agents.models.search import DatabaseRecord

@pytest.fixture
def feo_records():
    """5 записей FeO из примера ТЗ §4.5."""
    return [
        DatabaseRecord(
            formula="FeO", phase="s", tmin=298.0, tmax=600.0,
            h298=-265053.0, s298=59.807,
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
            h298=24058.0, s298=14.581,
            f1=68.199, f2=0.0, f3=0.0, f4=0.0, f5=0.0, f6=0.0,
            tmelt=1650.0, tboil=3687.0, reliability_class=1
        ),
    ]

def test_multi_phase_feo_1700k(feo_records):
    """Тест расчёта FeO при 1700K (пример из ТЗ §4.5)."""
    calculator = ThermodynamicCalculator()
    
    result = calculator.calculate_multi_phase_properties(
        records=feo_records,
        T_target=1700.0
    )
    
    # Проверки из ТЗ
    assert result.T_target == 1700.0
    assert len(result.segments) == 5, "Должно быть 5 сегментов"
    assert len(result.phase_transitions) == 1, "Должен быть 1 фазовый переход (s→l)"
    
    # Проверка фазового перехода
    transition = result.phase_transitions[0]
    assert transition.temperature == 1650.0
    assert transition.from_phase == "s"
    assert transition.to_phase == "l"
    assert transition.transition_type == "s→l"
    
    # Проверка финальных значений (с допуском ±1%)
    # Из ТЗ: H_1700 ≈ -142.10 кДж/моль
    assert abs(result.H_final / 1000 - (-142.10)) < 1.5, "H_final отклоняется от ожидаемого"
    
    # Из ТЗ: S_1700 ≈ 188.13 Дж/(моль·K)
    assert abs(result.S_final - 188.13) < 2.0, "S_final отклоняется от ожидаемого"
    
    # Из ТЗ: G_1700 ≈ -461.92 кДж/моль
    assert abs(result.G_final / 1000 - (-461.92)) < 5.0, "G_final отклоняется от ожидаемого"
    
    # Проверка Cp для жидкой фазы (константа)
    assert abs(result.Cp_final - 68.199) < 0.1

def test_multi_phase_segments_accumulation(feo_records):
    """Тест накопления H и S через сегменты."""
    calculator = ThermodynamicCalculator()
    
    result = calculator.calculate_multi_phase_properties(
        records=feo_records,
        T_target=900.0  # До плавления
    )
    
    # Первый сегмент должен иметь базовые значения
    assert result.segments[0].H_start == -265053.0
    assert result.segments[0].S_start == 59.807
    
    # Второй сегмент должен начинаться с накопленных значений первого
    H_after_seg1 = result.segments[0].H_start + result.segments[0].delta_H
    assert abs(result.segments[1].H_start - H_after_seg1) < 1e-3
    
    # Проверка, что значения накапливаются
    assert result.H_final > result.segments[0].H_start, "H должна увеличиваться"
    assert result.S_final > result.segments[0].S_start, "S должна увеличиваться"

def test_multi_phase_validation_errors(feo_records):
    """Тест валидации входных данных."""
    calculator = ThermodynamicCalculator()
    
    # Пустой список
    with pytest.raises(ValueError, match="пустой"):
        calculator.calculate_multi_phase_properties([], T_target=1000.0)
    
    # T_target вне покрытия
    with pytest.raises(ValueError, match="выходит за пределы"):
        calculator.calculate_multi_phase_properties(
            feo_records,
            T_target=6000.0  # Выше максимума (5000K)
        )
```

### Пример 3: Интеграционный тест с H2O

```python
# tests/integration/test_h2o_multi_phase.py

import pytest
from src.thermo_agents.search.compound_searcher import CompoundSearcher
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator

def test_h2o_phase_transitions(compound_searcher, calculator):
    """Тест расчёта H2O через s→l→g фазовые переходы."""
    # Поиск всех фаз H2O
    search_result = compound_searcher.search_all_phases(
        formula="H2O",
        max_temperature=1500.0
    )
    
    assert search_result.covers_298K is True
    assert search_result.phase_count >= 2, "Должно быть минимум 2 фазы"
    
    # Многофазный расчёт
    result = calculator.calculate_multi_phase_properties(
        records=search_result.records,
        T_target=500.0  # Газовая фаза
    )
    
    # Проверка наличия переходов
    assert result.has_phase_transitions is True
    
    # Проверка переходов
    transitions = {t.transition_type: t for t in result.phase_transitions}
    
    # Должен быть переход плавления около 273K
    melting_temps = [t.temperature for t in result.phase_transitions if "s" in t.from_phase and "l" in t.to_phase]
    assert len(melting_temps) > 0
    assert any(270 < T < 275 for T in melting_temps), "Tmelt ≈ 273K"
    
    # Должен быть переход кипения около 373K
    boiling_temps = [t.temperature for t in result.phase_transitions if "l" in t.from_phase and "g" in t.to_phase]
    if boiling_temps:  # Если есть жидкая фаза
        assert any(370 < T < 380 for T in boiling_temps), "Tboil ≈ 373K"

def test_h2o_enthalpy_increases_with_phase_transitions():
    """Тест, что энтальпия увеличивается при фазовых переходах."""
    # ... (аналогично предыдущему тесту)
    
    # Энтальпия должна скачком увеличиваться при плавлении
    for transition in result.phase_transitions:
        if transition.transition_type == "melting":
            assert transition.delta_H_transition > 0, "ΔH_melting должна быть > 0"
```

### Пример 4: Performance-тест

```python
# tests/performance/test_multi_phase_speed.py

import pytest
import time
from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator

def test_multi_phase_performance(feo_records):
    """Тест производительности многофазного расчёта."""
    calculator = ThermodynamicCalculator()
    
    start = time.time()
    result = calculator.calculate_multi_phase_properties(
        records=feo_records,
        T_target=1700.0
    )
    elapsed = time.time() - start
    
    # Расчёт 5 сегментов должен занять < 100ms
    assert elapsed < 0.1, f"Расчёт занял {elapsed*1000:.1f}ms (ожидалось < 100ms)"
    
    # Проверка, что результат корректен
    assert result.T_target == 1700.0
    assert len(result.segments) == 5

@pytest.mark.parametrize("num_segments", [1, 3, 5, 10])
def test_scaling_with_segments(num_segments):
    """Тест масштабирования времени расчёта с количеством сегментов."""
    # ... (генерация записей с num_segments)
    
    # Время должно расти линейно с числом сегментов
    # ...
```
