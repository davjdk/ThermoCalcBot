"""
Performance тесты многофазных термодинамических расчётов.

Проверяют соответствие целевым метрикам производительности.
"""

import pytest
import time
import tempfile
from pathlib import Path

from src.thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig


@pytest.fixture
def temp_cache_dir():
    """Временная директория для YAML кэша."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def performance_orchestrator(temp_cache_dir):
    """Оркестратор для performance тестов."""
    config = MultiPhaseOrchestratorConfig(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(temp_cache_dir / "static_compounds"),
        integration_points=200,  # Уменьшаем для скорости
        llm_api_key=""
    )
    return MultiPhaseOrchestrator(config)


class TestMultiPhasePerformance:
    """Performance тесты многофазных расчётов."""

    @pytest.mark.asyncio
    async def test_single_compound_search_performance(self, performance_orchestrator):
        """Тест производительности поиска одного вещества."""
        formula = "H2O"
        max_temp = 500.0

        start_time = time.time()
        search_result = performance_orchestrator.compound_searcher.search_all_phases(
            formula=formula,
            max_temperature=max_temp
        )
        elapsed_time = (time.time() - start_time) * 1000  # мс

        # Целевые метрики: < 100мс для поиска
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
        from src.thermo_agents.storage.static_data_manager import StaticDataManager

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
            from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator
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
        from src.thermo_agents.calculations.thermodynamic_calculator import ThermodynamicCalculator

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