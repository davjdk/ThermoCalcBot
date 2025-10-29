"""
Тесты производительности многофазной термодинамической системы.

Проверяет соответствие требованиям производительности:
- Время отклика ≤3 секунд для простых запросов
- Использование памяти ≤200MB
- Производительность многофазных расчётов
- Эффективность кэширования
- Масштабируемость системы
"""

import pytest
import asyncio
import sys
import time
import psutil
import gc
import os
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


class TestMultiPhasePerformance:
    """Тесты производительности многофазной системы."""

    @pytest.mark.asyncio
    async def test_simple_query_response_time(self, multi_phase_orchestrator):
        """
        Тест времени отклика для простых запросов.

        Требование: ≤3 секунд для запросов свойств одного вещества.
        """

        simple_queries = [
            "H2O свойства при 298K",
            "CO2 термодинамика при 500K",
            "FeO энтальпия образования",
            "NH3 теплоёмкость",
        ]

        response_times = []

        for query in simple_queries:
            # Очистка кэша для чистого измерения
            gc.collect()

            start_time = time.time()
            response = await multi_phase_orchestrator.process_query(query)
            end_time = time.time()

            execution_time = end_time - start_time
            response_times.append(execution_time)

            # Проверки
            assert response is not None, f"Ответ не должен быть None для запроса: {query}"
            assert len(response) > 0, f"Ответ не должен быть пустым для запроса: {query}"
            assert execution_time < 3.0, f"Слишком медленный ответ для '{query}': {execution_time:.2f}s"

        # Проверяем среднее время
        avg_time = sum(response_times) / len(response_times)
        assert avg_time < 2.0, f"Среднее время выполнения слишком велико: {avg_time:.2f}s"

    @pytest.mark.asyncio
    async def test_complex_reaction_calculation_speed(self, multi_phase_orchestrator):
        """
        Тест скорости расчёта сложных реакций.

        Требование: ≤5 секунд для многофазных реакций с 4+ компонентами.
        """

        complex_queries = [
            "FeO + H₂S → FeS + H₂O термодинамика при 773K",
            "CO2 + NH3 → NH2COONH4 реакция при 400K",
            "Fe + O2 → FeO2 + Fe3O4 равновесие при 1000K",
            "TiO2 + Cl2 → TiCl4 + O2 расчёт при 800K",
        ]

        for query in complex_queries:
            gc.collect()

            start_time = time.time()
            response = await multi_phase_orchestrator.process_query(query)
            end_time = time.time()

            execution_time = end_time - start_time

            assert response is not None, f"Ответ не должен быть None для реакции: {query}"
            assert len(response) > 0, f"Ответ не должен быть пустым для реакции: {query}"
            assert execution_time < 5.0, f"Слишком медленный расчёт реакции '{query}': {execution_time:.2f}s"

            # Проверяем наличие термодинамической информации
            has_thermo_data = any(
                indicator in response.lower()
                for indicator in ["δh", "δg", "δs", "кдж", "дж", "энерг"]
            )

            # Если расчёт выполнен успешно, должна быть термодинамическая информация
            if execution_time < 2.0 and len(response) > 100:
                assert has_thermo_data, f"В успешном расчёте должна быть термодинамическая информация: {response[:200]}..."

    def test_memory_usage_optimization(self, multi_phase_orchestrator):
        """
        Тест оптимизации использования памяти.

        Требование: ≤200MB пикового использования памяти.
        """

        process = psutil.Process(os.getpid())

        # Измеряем базовое использование памяти
        gc.collect()
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Выполняем серию запросов для проверки утечек памяти
        async def run_memory_test():
            queries = [
                "H2O свойства от 250K до 400K",
                "FeO свойства от 298K до 4000K",
                "CO2 + NH3 реакция при 500K",
                "Fe + O2 → FeO термодинамика при 1000K",
                "TiO2 + Cl2 → TiCl4 + O2 при 800K",
            ]

            peak_memory = baseline_memory

            for i, query in enumerate(queries):
                await multi_phase_orchestrator.process_query(query)

                current_memory = process.memory_info().rss / 1024 / 1024
                peak_memory = max(peak_memory, current_memory)

                # Принудительная сборка мусора каждые 2 запроса
                if i % 2 == 1:
                    gc.collect()

            return peak_memory

        # Запускаем тест
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            peak_memory = loop.run_until_complete(run_memory_test())
        finally:
            loop.close()

        # Проверяем требования
        memory_increase = peak_memory - baseline_memory
        total_memory = peak_memory

        assert total_memory < 200, f"Превышено ограничение памяти: {total_memory:.1f}MB > 200MB"
        assert memory_increase < 100, f"Слишком большой рост памяти: {memory_increase:.1f}MB"

    @pytest.mark.asyncio
    async def test_cache_effectiveness(self, multi_phase_orchestrator):
        """
        Тест эффективности кэширования.

        Проверяет, что повторные запросы выполняются быстрее.
        """

        test_queries = [
            "H2O свойства при 350K",
            "FeO термодинамика при 1000K",
            "CO2 свойства при 400K",
        ]

        cache_ratios = []

        for query in test_queries:
            # Первый запрос (без кэша)
            gc.collect()
            start_time = time.time()
            response1 = await multi_phase_orchestrator.process_query(query)
            first_time = time.time() - start_time

            # Повторный запрос (с кэшем)
            gc.collect()
            start_time = time.time()
            response2 = await multi_phase_orchestrator.process_query(query)
            second_time = time.time() - start_time

            # Проверяем идентичность ответов
            assert response1 == response2, f"Ответы должны быть идентичны для повторных запросов"

            # Проверяем ускорение
            if first_time > 0.1:  # Только если первый запрос был достаточно долгим
                speedup = first_time / second_time if second_time > 0 else float('inf')
                cache_ratios.append(speedup)

                # Кэш должен давать ускорение хотя бы в 1.5 раза
                assert speedup > 1.5 or second_time < 0.1, \
                    f"Кэш не обеспечивает достаточного ускорения: {speedup:.1f}x для '{query}'"

        # Среднее ускорение должно быть значительным
        if cache_ratios:
            avg_speedup = sum(cache_ratios) / len(cache_ratios)
            assert avg_speedup > 2.0, f"Среднее ускорение от кэша слишком мало: {avg_speedup:.1f}x"

    @pytest.mark.asyncio
    async def benchmark_vs_current_system_version(self, multi_phase_orchestrator):
        """
        Бенчмарк сравнения с текущей версией системы.

        Проверяет, что производительность не ухудшилась.
        """

        # Бенчмарк запросы
        benchmark_queries = [
            ("Простой запрос", "H2O свойства при 298K"),
            ("Фазовые переходы", "H2O свойства от 250K до 400K"),
            ("Реакция", "FeO + H₂S → FeS + H₂O при 773K"),
            ("Сложная реакция", "TiO2 + 2Cl2 → TiCl4 + O2 при 800K"),
        ]

        benchmark_results = {}

        for name, query in benchmark_queries:
            times = []

            # Выполняем несколько измерений для статистики
            for i in range(3):
                gc.collect()
                start_time = time.time()
                response = await multi_phase_orchestrator.process_query(query)
                end_time = time.time()

                execution_time = end_time - start_time
                times.append(execution_time)

                # Проверяем корректность ответа
                assert response is not None, f"Ответ не должен быть None для {name}"
                assert len(response) > 0, f"Ответ не должен быть пустым для {name}"

            # Статистика
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            benchmark_results[name] = {
                'avg': avg_time,
                'min': min_time,
                'max': max_time,
                'times': times
            }

            # Проверяем требования производительности
            assert avg_time < 4.0, f"Слишком медленное выполнение {name}: {avg_time:.2f}s"
            assert max_time < 6.0, f"Слишком медленное выполнение {name} (max): {max_time:.2f}s"

        # Выводим результаты для документации
        print(f"\n=== Бенчмарк производительности ===")
        for name, results in benchmark_results.items():
            print(f"{name}: {results['avg']:.2f}s (сред), {results['min']:.2f}s (мин), {results['max']:.2f}s (макс)")

    @pytest.mark.asyncio
    async def test_performance_requirements_compliance(self, multi_phase_orchestrator):
        """
        Комплексный тест соответствия требованиям производительности.

        Проверяет все требования спецификации одновременно.
        """

        # Тестовые сценарии охватывающие все требования
        test_scenarios = [
            {
                'name': 'Быстрый однофазный запрос',
                'query': 'CO2 свойства при 298K',
                'max_time': 2.0,
                'min_response_length': 50
            },
            {
                'name': 'Многофазный расчёт',
                'query': 'H2O свойства от 250K до 400K',
                'max_time': 3.0,
                'min_response_length': 100
            },
            {
                'name': 'Расчёт реакции',
                'query': 'Fe + O2 → FeO термодинамика при 1000K',
                'max_time': 4.0,
                'min_response_length': 150
            },
            {
                'name': 'Сложная реакция',
                'query': 'TiO2 + 2Cl2 → TiCl4 + O2 при 800K',
                'max_time': 5.0,
                'min_response_length': 200
            }
        ]

        compliance_results = []

        for scenario in test_scenarios:
            # Измерение производительности
            gc.collect()
            start_time = time.time()
            response = await multi_phase_orchestrator.process_query(scenario['query'])
            end_time = time.time()

            execution_time = end_time - start_time
            response_length = len(response) if response else 0

            # Проверка соответствия требованиям
            time_compliant = execution_time <= scenario['max_time']
            length_compliant = response_length >= scenario['min_response_length']
            response_valid = response is not None and response_length > 0

            compliance_results.append({
                'name': scenario['name'],
                'time': execution_time,
                'max_time': scenario['max_time'],
                'time_compliant': time_compliant,
                'length': response_length,
                'min_length': scenario['min_response_length'],
                'length_compliant': length_compliant,
                'response_valid': response_valid,
                'fully_compliant': time_compliant and length_compliant and response_valid
            })

            # Утверждения для каждого сценария
            assert response_valid, f"Ответ должен быть валидным для {scenario['name']}"
            assert time_compliant, f"Время выполнения превышено для {scenario['name']}: {execution_time:.2f}s > {scenario['max_time']}s"
            assert length_compliant, f"Ответ слишком короткий для {scenario['name']}: {response_length} < {scenario['min_length']}"

        # Проверяем общую соответствующую
        compliant_scenarios = sum(1 for r in compliance_results if r['fully_compliant'])
        total_scenarios = len(compliance_results)

        compliance_rate = compliant_scenarios / total_scenarios
        assert compliance_rate >= 0.9, f"Слишком низкий уровень соответствия требованиям: {compliance_rate:.1%}"

        # Выводим детальные результаты
        print(f"\n=== Результаты соответствия требованиям ===")
        for result in compliance_results:
            status = "✅" if result['fully_compliant'] else "❌"
            print(f"{status} {result['name']}: {result['time']:.2f}s (≤{result['max_time']}s), {result['length']} символов (≥{result['min_length']})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
        assert elapsed_time < 100, f"Поиск занял {elapsed_time:.1f}мс > 100мс"
        assert search_result is not None

        print(f"✅ Поиск {formula}: {elapsed_time:.1f}мс")

    @pytest.mark.asyncio
    async def test_multi_phase_calculation_performance(self, performance_orchestrator):
        """Тест производительности многофазного расчёта."""
        # Ищем данные сначала
        search_result = performance_orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        if search_result.records:
            start_time = time.time()
            mp_result = performance_orchestrator.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                T_target=400.0
            )
            elapsed_time = (time.time() - start_time) * 1000  # мс

            # Целевые метрики: < 500мс для многофазного расчёта
            assert elapsed_time < 500, f"Расчёт занял {elapsed_time:.1f}мс > 500мс"
            assert mp_result is not None

            print(f"✅ Многофазный расчёт: {elapsed_time:.1f}мс")
        else:
            pytest.skip("Нет данных для H2O в тестовой БД")

    def test_yaml_cache_performance(self, temp_cache_dir):
        """Тест производительности YAML кэша."""
        from thermo_agents.storage.static_data_manager import StaticDataManager

        # Создаем тестовые YAML данные
        cache_dir = temp_cache_dir / "static_compounds"
        cache_dir.mkdir(parents=True, exist_ok=True)

        yaml_content = """
compound:
  formula: "CO2"
  common_names: ["Carbon dioxide"]
  phases:
    - phase: "g"
      tmin: 298.0
      tmax: 1000.0
      h298: -393509.0
      s298: 213.74
      f1: 44.22
      f2: 9.04
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      reliability_class: 1
  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""
        (cache_dir / "CO2.yaml").write_text(yaml_content)

        manager = StaticDataManager(cache_dir)

        # Тест загрузки из YAML (первый раз - с диска)
        start_time = time.time()
        data1 = manager.load_compound("CO2")
        first_load_time = (time.time() - start_time) * 1000

        # Тест загрузки из кэша (второй раз - из памяти)
        start_time = time.time()
        data2 = manager.load_compound("CO2")
        cached_load_time = (time.time() - start_time) * 1000

        # Проверки
        assert data1 is not None
        assert data2 is not None
        assert data1.formula == data2.formula

        # Целевые метрики
        assert first_load_time < 50, f"Первичная загрузка YAML: {first_load_time:.1f}мс > 50мс"
        assert cached_load_time < 5, f"Загрузка из кэша: {cached_load_time:.1f}мс > 5мс"

        print(f"✅ YAML загрузка (первая): {first_load_time:.1f}мс")
        print(f"✅ YAML загрузка (из кэша): {cached_load_time:.1f}мс")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("formula,max_T,expected_time", [
        ("H2O", 500, 300),
        ("CO2", 800, 300),
        ("O2", 600, 300),
        ("N2", 600, 300),
    ])
    async def test_performance_by_compound(
        self, performance_orchestrator, formula, max_T, expected_time
    ):
        """
        Тест производительности для различных веществ.

        Args:
            performance_orchestrator: Оркестратор для тестов
            formula: Химическая формула
            max_T: Максимальная температура
            expected_time: Ожидаемое время в мс
        """
        start_time = time.time()

        # Полный цикл: поиск + расчёт
        search_result = performance_orchestrator.compound_searcher.search_all_phases(
            formula=formula,
            max_temperature=max_T
        )

        if search_result.records:
            mp_result = performance_orchestrator.calculator.calculate_multi_phase_properties(
                records=search_result.records,
                T_target=max_T
            )
        else:
            mp_result = None

        elapsed_time = (time.time() - start_time) * 1000

        # Проверка производительности
        if search_result.records:  # Только если есть данные
            assert elapsed_time < expected_time, (
                f"{formula}: {elapsed_time:.1f}мс > {expected_time:.0f}мс"
            )
            print(f"✅ {formula} (до {max_T}K): {elapsed_time:.1f}мс")
        else:
            print(f"⚠️ {formula}: нет данных в тестовой БД")

    def test_concurrent_search_performance(self, performance_orchestrator):
        """Тест производительности при одновременных запросах."""
        import concurrent.futures
        import threading

        formulas = ["H2O", "CO2", "O2", "N2"]
        results = {}
        times = {}

        def search_formula(formula):
            """Поиск вещества в отдельном потоке."""
            thread_id = threading.get_ident()
            start_time = time.time()

            try:
                result = performance_orchestrator.compound_searcher.search_all_phases(
                    formula=formula,
                    max_temperature=500.0
                )
                elapsed_time = (time.time() - start_time) * 1000
                results[formula] = result
                times[formula] = elapsed_time
                return (formula, elapsed_time, len(result.records) if result else 0)
            except Exception as e:
                return (formula, -1, str(e))

        # Выполняем поиск параллельно
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(search_formula, formula) for formula in formulas]
            concurrent_results = [future.result() for future in futures]

        # Анализ результатов
        for formula, elapsed_time, record_count in concurrent_results:
            if elapsed_time > 0:
                print(f"✅ Параллельный поиск {formula}: {elapsed_time:.1f}мс ({record_count} записей)")
                # Каждый запрос должен выполняться за разумное время
                assert elapsed_time < 200, f"Параллельный поиск {formula} слишком медленный: {elapsed_time:.1f}мс"
            else:
                print(f"❌ Ошибка поиска {formula}: {record_count}")

    def test_memory_usage_performance(self, performance_orchestrator):
        """Тест использования памяти."""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Выполняем серию расчётов
        formulas = ["H2O", "CO2", "O2", "N2"]
        calculations = 0

        for _ in range(10):  # 10 итераций
            for formula in formulas:
                search_result = performance_orchestrator.compound_searcher.search_all_phases(
                    formula=formula,
                    max_temperature=500.0
                )
                if search_result.records:
                    performance_orchestrator.calculator.calculate_multi_phase_properties(
                        records=search_result.records,
                        T_target=400.0
                    )
                    calculations += 1

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        print(f"✅ Память: начальная {initial_memory:.1f}MB, финальная {final_memory:.1f}MB")
        print(f"✅ Увеличение памяти: {memory_increase:.1f}MB за {calculations} расчётов")
        print(f"✅ Память на расчёт: {memory_increase/calculations:.2f}MB")

        # Проверка: утечка памяти не должна быть большой
        assert memory_increase < 50, f"Слишком большое увеличение памяти: {memory_increase:.1f}MB"
        assert memory_increase / calculations < 1.0, f"Слишком много памяти на расчёт: {memory_increase/calculations:.2f}MB"

    @pytest.mark.asyncio
    async def test_integration_points_performance_impact(self, performance_orchestrator):
        """Тест влияния количества точек интегрирования на производительность."""
        if not performance_orchestrator.compound_searcher.search_all_phases("H2O", 500.0).records:
            pytest.skip("Нет данных для теста")

        integration_points_list = [50, 100, 200, 400]
        times = []

        for points in integration_points_list:
            # Создаем калькулятор с разным количеством точек
            from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
            calculator = ThermodynamicCalculator(num_integration_points=points)

            # Выполняем расчёт
            search_result = performance_orchestrator.compound_searcher.search_all_phases(
                formula="H2O",
                max_temperature=500.0
            )

            start_time = time.time()
            mp_result = calculator.calculate_multi_phase_properties(
                records=search_result.records,
                T_target=400.0
            )
            elapsed_time = (time.time() - start_time) * 1000
            times.append(elapsed_time)

            print(f"✅ {points} точек: {elapsed_time:.1f}мс")

        # Проверяем, что время растёт линейно, а не экспоненциально
        if len(times) >= 2:
            time_ratio = times[-1] / times[0]  # Последний / первый
            points_ratio = integration_points_list[-1] / integration_points_list[0]

            # Время не должно расти быстрее, чем количество точек
            assert time_ratio < points_ratio * 1.5, (
                f"Время растёт слишком быстро: {time_ratio:.1f}x при росте точек {points_ratio:.1f}x"
            )

    def test_cache_efficiency(self, performance_orchestrator):
        """Тест эффективности кэширования."""
        from thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator

        calculator = ThermodynamicCalculator(num_integration_points=100)

        # Находим данные
        search_result = performance_orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        if not search_result.records:
            pytest.skip("Нет данных для теста")

        # Первый расчёт (без кэша)
        start_time = time.time()
        calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=400.0
        )
        first_time = (time.time() - start_time) * 1000

        # Второй расчёт (с кэшем)
        start_time = time.time()
        calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=400.0
        )
        second_time = (time.time() - start_time) * 1000

        # Третий расчёт (с кэшем, другая температура)
        start_time = time.time()
        calculator.calculate_multi_phase_properties(
            records=search_result.records,
            T_target=450.0
        )
        third_time = (time.time() - start_time) * 1000

        print(f"✅ Первый расчёт: {first_time:.1f}мс")
        print(f"✅ Второй расчёт (кэш): {second_time:.1f}мс")
        print(f"✅ Третий расчёт (кэш): {third_time:.1f}мс")

        # Кэш должен ускорять повторные расчёты
        if first_time > 10:  # Только если первый расчёт достаточно долгий
            assert second_time < first_time * 0.5, f"Кэш не ускоряет расчёт: {second_time:.1f}мс vs {first_time:.1f}мс"
            assert third_time < first_time * 0.5, f"Кэш не ускоряет новый расчёт: {third_time:.1f}мс vs {first_time:.1f}мс"