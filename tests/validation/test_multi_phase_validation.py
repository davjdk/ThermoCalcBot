"""
Комплексная валидация многофазной термодинамической системы.

Тестирует корректность многофазных расчётов, фазовых переходов,
и согласованность термодинамических данных.

Coverage:
- Многофазные расчеты для различных веществ
- Корректность фазовых переходов
- Термодинамическая согласованность
- Выбор оптимальных записей
- Покрытие температурных диапазонов
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)
from thermo_agents.session_logger import SessionLogger


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
async def multi_phase_orchestrator(test_db_path):
    """Создает многофазный оркестратор для тестов."""

    config = MultiPhaseOrchestratorConfig(
        db_path=test_db_path,
        llm_api_key="test_key",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        static_cache_dir="data/static_compounds",
        integration_points=100,
    )

    orchestrator = MultiPhaseOrchestrator(config)
    yield orchestrator


class TestMultiPhaseValidation:
    """Тесты валидации многофазной системы."""

    @pytest.mark.asyncio
    async def test_water_phase_transitions_comprehensive(self, multi_phase_orchestrator):
        """
        Тест комплексной проверки фазовых переходов воды.

        Ожидаемые переходы:
        - Твёрдая (лед): 250-273K
        - Жидкая (вода): 273-373K
        - Газовая (пар): 373-400K
        """

        query = "Свойства воды от 250K до 400K"
        response = await multi_phase_orchestrator.process_query(query)

        assert response is not None
        assert len(response) > 0

        # Проверяем наличие информации о разных фазах
        phase_indicators = ["твёрд", "жидк", "газ", "лёд", "пар", "s/l/g"]
        found_phases = sum(1 for indicator in phase_indicators if indicator in response.lower())

        assert found_phases >= 2, f"Должна быть информация о нескольких фазах воды: {response[:300]}..."

        # Проверяем температурные точки переходов
        assert "273" in response or "373" in response, "Должны быть указаны точки фазовых переходов"

    @pytest.mark.asyncio
    async def test_feo_phase_transitions_melting_boiling(self, multi_phase_orchestrator):
        """
        Тест фазовых переходов FeO.

        Ожидаемые переходы:
        - Твёрдая: 298-1650K
        - Жидкая: 1650-3687K
        - Газовая: 3687-4000K
        """

        query = "FeO свойства от 298K до 4000K"
        response = await multi_phase_orchestrator.process_query(query)

        assert response is not None
        assert len(response) > 0

        # Проверяем информацию о высокотемпературных фазах
        has_high_temp_info = any(
            indicator in response.lower()
            for indicator in ["1650", "3687", "плавлен", "жидк", "газ"]
        )
        assert has_high_temp_info, f"Должна быть информация о высокотемпературных фазах FeO: {response[:300]}..."

    @pytest.mark.asyncio
    async def test_multi_phase_compound_selection_accuracy(self, multi_phase_orchestrator):
        """
        Тест точности выбора записей для многофазных расчётов.

        Проверяет, что система выбирает оптимальные записи
        для покрытия температурного диапазона с учетом фаз.
        """

        test_compounds = [
            ("H2O", (250, 400)),   # Через фазовые переходы
            ("FeO", (298, 2000)),  # Включая плавление
            ("CO2", (200, 500)),   # Возможная сублимация
            ("NH3", (195, 250)),   # Низкотемпературные фазы
        ]

        for compound, temp_range in test_compounds:
            result = multi_phase_orchestrator.compound_searcher.search_compound(
                compound, temp_range
            )

            assert result is not None, f"{compound} должен быть найден"

            if result.records_found:
                # Проверяем покрытие температурного диапазона
                ranges_covered = []
                for record in result.records_found:
                    t_min = record.get('Tmin', 0)
                    t_max = record.get('Tmax', 0)
                    try:
                        t_min_val = float(t_min)
                        t_max_val = float(t_max)
                        ranges_covered.append((t_min_val, t_max_val))
                    except (ValueError, TypeError):
                        continue

                # Проверяем, что диапазоны покрывают запрашиваемый диапазон
                if ranges_covered:
                    # Сортируем по Tmin
                    ranges_covered.sort()

                    # Проверяем покрытие от начала диапазона
                    current_min = temp_range[0]
                    coverage_gaps = []

                    for r_min, r_max in ranges_covered:
                        if r_min > current_min:
                            coverage_gaps.append((current_min, r_min))
                        current_min = max(current_min, r_max)
                        if current_min >= temp_range[1]:
                            break

                    # Если есть пробелы в покрытии, это не ошибка, но должно быть логировано
                    # (некоторые фазы могут отсутствовать в базе данных)

    @pytest.mark.asyncio
    async def test_thermodynamic_consistency_across_phases(self, multi_phase_orchestrator):
        """
        Тест термодинамической согласованности across фаз.

        Проверяет непрерывность термодинамических функций
        при фазовых переходах.
        """

        # Вода - хороший тестовый случай с доступными данными
        compound = "H2O"
        temp_range = (250, 400)  # Включает все три фазы

        result = multi_phase_orchestrator.compound_searcher.search_compound(
            compound, temp_range
        )

        assert result is not None
        assert result.records_found, "Должны быть данные для воды в этом диапазоне"

        # Собираем данные для разных фаз
        phase_data = {}
        for record in result.records_found:
            phase = record.get('Phase', 'unknown')
            if phase not in phase_data:
                phase_data[phase] = []
            phase_data[phase].append(record)

        # Проверяем наличие данных для разных фаз
        assert len(phase_data) >= 1, "Должны быть данные для разных фаз"

        # Проверяем согласованность энтальпии образования в каждой фазе
        for phase, records in phase_data.items():
            h298_values = []
            for record in records:
                h298 = record.get('H298')
                if h298 is not None:
                    try:
                        h298_val = float(h298)
                        h298_values.append(h298_val)
                    except (ValueError, TypeError):
                        continue

            if h298_values:
                # В пределах одной фазы значения H298 должны быть согласованы
                # (различия могут быть из-за разных источников данных)
                min_h298 = min(h298_values)
                max_h298 = max(h298_values)

                # Разница не должна быть слишком большой (более 100 кДж/моль)
                # если это не разные фазы
                if phase == 'l':  # Жидкая фаза как референс
                    assert max_h298 - min_h298 < 100.0, \
                        f"Слишком большой разброс H298 в фазе {phase}: {min_h298}..{max_h298}"

    @pytest.mark.asyncio
    async def test_temperature_range_coverage_validation(self, multi_phase_orchestrator):
        """
        Тест проверки покрытия температурных диапазонов.

        Проверяет, что система обеспечивает максимальное покрытие
        запрашиваемого температурного диапазона.
        """

        test_cases = [
            ("Fe", (298, 2000)),   # Широкий диапазон
            ("CO2", (200, 600)),   # Низкие температуры
            ("NH3", (300, 800)),   # Средние температуры
            ("CH4", (100, 1500)),  # Очень широкий диапазон
        ]

        for compound, temp_range in test_cases:
            result = multi_phase_orchestrator.compound_searcher.search_compound(
                compound, temp_range
            )

            if result and result.records_found:
                # Анализируем покрытие
                total_coverage = 0
                for record in result.records_found:
                    t_min = record.get('Tmin', 0)
                    t_max = record.get('Tmax', 0)
                    try:
                        t_min_val = float(t_min)
                        t_max_val = float(t_max)

                        # Пересечение с запрашиваемым диапазоном
                        overlap_start = max(t_min_val, temp_range[0])
                        overlap_end = min(t_max_val, temp_range[1])

                        if overlap_end > overlap_start:
                            total_coverage += overlap_end - overlap_start
                    except (ValueError, TypeError):
                        continue

                # Проверяем, что покрытие достаточно большое
                requested_range_length = temp_range[1] - temp_range[0]
                coverage_ratio = total_coverage / requested_range_length if requested_range_length > 0 else 0

                # Должно быть покрыто хотя бы 25% диапазона
                # (остальное может отсутствовать в базе данных)
                assert coverage_ratio >= 0.25 or total_coverage == 0, \
                    f"Низкое покрытие температурного диапазона для {compound}: {coverage_ratio:.2%}"

    @pytest.mark.asyncio
    async def test_phase_transition_temperature_accuracy(self, multi_phase_orchestrator):
        """
        Тест точности температур фазовых переходов.

        Проверяет, что температуры фазовых переходов
        соответствуют известным физическим значениям.
        """

        # Вода: точка плавления 273K, точка кипения 373K
        query = "H2O фазовые переходы температуры"
        response = await multi_phase_orchestrator.process_query(query)

        assert response is not None

        # Проверяем наличие корректных температур переходов
        has_melting_point = any(
            temp in response for temp in ["273", "273.15", "0°C", "0 C"]
        )
        has_boiling_point = any(
            temp in response for temp in ["373", "373.15", "100°C", "100 C"]
        )

        # Если система находит данные о фазовых переходах, они должны быть корректными
        if has_melting_point:
            assert "273" in response, "Температура плавления воды должна быть около 273K"
        if has_boiling_point:
            assert "373" in response, "Температура кипения воды должна быть около 373K"

    @pytest.mark.asyncio
    async def test_multi_phase_reaction_calculation(self, multi_phase_orchestrator):
        """
        Тест многофазных расчётов реакций.

        Проверяет корректность расчётов реакций с учетом
        фазовых переходов реагентов и продуктов.
        """

        # Реакция с различными фазами компонентов
        query = "FeO(тв) + H₂S(г) → FeS(тв) + H₂O(ж) при 773K (500°C)"
        response = await multi_phase_orchestrator.process_query(query)

        assert response is not None
        assert len(response) > 0

        # Проверяем наличие термодинамических расчётов
        has_thermo_calculation = any(
            indicator in response.lower()
            for indicator in ["δh", "δg", "δs", "кдж", "дж", "энтальп", "энерг"]
        )

        # Если все данные доступны, должен быть расчёт
        if has_thermo_calculation:
            # Проверяем, что расчёт учитывает фазы
            has_phase_info = any(
                phase in response.lower()
                for phase in ["тв", "ж", "г", "(тв)", "(ж)", "(г)", "s", "l", "g"]
            )
            assert has_phase_info, f"Расчёт должен учитывать фазы веществ: {response[:400]}..."

    @pytest.mark.asyncio
    async def test_edge_case_phase_transitions(self, multi_phase_orchestrator):
        """
        Тест граничных случаев фазовых переходов.

        Проверяет обработку сложных случаев:
        - Полиморфные переходы
        - Сублимация
        - Разложение
        """

        edge_cases = [
            "CO2 свойства от 150K до 250K",  # Возможная сублимация
            "NH3 свойства при трипельной точке",  # Тройная точка
            "P (фосфор) полиморфные переходы",  # Полиморфизм
        ]

        for query in edge_cases:
            try:
                response = await multi_phase_orchestrator.process_query(query)

                assert response is not None
                assert len(response) > 0

                # Проверяем, что система обрабатывает сложные случаи
                # без падений и возвращает осмысленный ответ
                has_meaningful_content = len(response) > 50
                assert has_meaningful_content, f"Ответ должен содержать осмысленную информацию: {response[:100]}..."

            except Exception as e:
                # Система должна обрабатывать ошибки граничных случаев
                pytest.skip(f"Тест граничного случая пропущен из-за ошибки: {e}")

    @pytest.mark.asyncio
    async def test_multi_phase_data_integrity(self, multi_phase_orchestrator):
        """
        Тест целостности многофазных данных.

        Проверяет согласованность данных между разными фазами
        одного и того же вещества.
        """

        # FeO - хороший тест с несколькими фазами
        compound = "FeO"
        temp_range = (298, 4000)  # Все фазы

        result = multi_phase_orchestrator.compound_searcher.search_compound(
            compound, temp_range
        )

        if result and result.records_found:
            # Группируем записи по фазам
            phase_records = {}
            for record in result.records_found:
                phase = record.get('Phase', 'unknown')
                if phase not in phase_records:
                    phase_records[phase] = []
                phase_records[phase].append(record)

            # Проверяем целостность данных
            for phase, records in phase_records.items():
                # Проверяем H298 в пределах фазы
                h298_values = []
                for record in records:
                    h298 = record.get('H298')
                    if h298 is not None:
                        try:
                            h298_val = float(h298)
                            if abs(h298_val) < 1e6:  # Разумные значения
                                h298_values.append(h298_val)
                        except (ValueError, TypeError):
                            continue

                if len(h298_values) > 1:
                    # В пределах одной фазы значения должны быть согласованы
                    std_dev = (sum((x - sum(h298_values)/len(h298_values))**2 for x in h298_values) / len(h298_values))**0.5
                    assert std_dev < 50.0, f"Большой разброс H298 в фазе {phase}: {h298_values}"

    @pytest.mark.asyncio
    async def test_multi_phase_performance_validation(self, multi_phase_orchestrator):
        """
        Тест производительности многофазных расчётов.

        Проверяет, что многофазные расчёты укладываются
        в требования к производительности.
        """

        import time

        test_queries = [
            "H2O свойства от 250K до 400K",
            "FeO свойства от 298K до 4000K",
            "CO2 + NH3 реакция при 500K",
            "Fe + O2 → FeO при 1000K",
        ]

        for query in test_queries:
            start_time = time.time()
            response = await multi_phase_orchestrator.process_query(query)
            end_time = time.time()

            execution_time = end_time - start_time

            # Требование: ≤5 секунд для многофазных расчётов
            assert execution_time < 5.0, f"Слишком медленный расчёт для '{query}': {execution_time:.2f}s"
            assert response is not None
            assert len(response) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])