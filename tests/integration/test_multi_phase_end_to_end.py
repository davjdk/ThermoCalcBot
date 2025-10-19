"""
End-to-end тесты многофазной термодинамической системы.

Проверяют полный цикл обработки запросов с использованием многофазных расчётов.
"""

import pytest
import tempfile
from pathlib import Path

from thermo_agents.orchestrator_multi_phase import MultiPhaseOrchestrator, MultiPhaseOrchestratorConfig


@pytest.fixture
def temp_cache_dir():
    """Временная директория для YAML кэша."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_orchestrator(temp_cache_dir):
    """Оркестратор с временным кэшем."""
    config = MultiPhaseOrchestratorConfig(
        db_path="tests/fixtures/test_thermo.db",
        static_cache_dir=str(temp_cache_dir / "static_compounds"),
        integration_points=100,  # Уменьшаем для скорости тестов
        # Без LLM агента для простоты
        llm_api_key=""
    )
    return MultiPhaseOrchestrator(config)


@pytest.fixture
def yaml_h2o_data():
    """Тестовые YAML данные для H2O."""
    return """
compound:
  formula: "H2O"
  common_names: ["Water", "Dihydrogen monoxide"]
  description: "Water test data"
  phases:
    - phase: "s"
      tmin: 0.0
      tmax: 273.15
      h298: -285830.0
      s298: 69.91
      f1: 16.62
      f2: 38.24
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1

    - phase: "l"
      tmin: 273.15
      tmax: 373.15
      h298: -285830.0
      s298: 69.91
      f1: 75.29
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1

    - phase: "g"
      tmin: 373.15
      tmax: 1000.0
      h298: -241826.0
      s298: 188.83
      f1: 30.00
      f2: 0.0
      f3: 0.0
      f4: 0.0
      f5: 0.0
      f6: 0.0
      tmelt: 273.15
      tboil: 373.15
      reliability_class: 1

  metadata:
    source_database: "test.db"
    extracted_date: "2025-10-19"
    version: "1.0"
"""


class TestMultiPhaseEndToEnd:
    """Класс end-to-end тестов многофазных расчётов."""

    @pytest.mark.asyncio
    async def test_h2o_full_pipeline_with_yaml_cache(self, test_orchestrator, temp_cache_dir, yaml_h2o_data):
        """End-to-end тест H2O через s→l→g фазы с YAML кэшем."""
        # Создаем YAML файл для H2O
        cache_dir = temp_cache_dir / "static_compounds"
        cache_dir.mkdir(parents=True, exist_ok=True)

        h2o_file = cache_dir / "H2O.yaml"
        h2o_file.write_text(yaml_h2o_data)

        # Выполняем запрос
        query = "Рассчитай свойства H2O от 200K до 500K"
        response = await test_orchestrator.process_query(query)

        # Проверки
        assert "H2O" in response or "Water" in response
        assert "273" in response or "Tmelt" in response  # Плавление
        assert "373" in response or "Tboil" in response  # Кипение
        assert "[Сегмент" in response  # Многофазный формат
        assert "Таблица" in response or "T(K)" in response  # Есть таблица

        # Проверка использования YAML кэша
        test_orchestrator.logger.info(f"Response preview: {response[:500]}...")

    @pytest.mark.asyncio
    async def test_simple_compound_data_multi_phase(self, test_orchestrator):
        """Тест простого запроса данных по веществу."""
        # Проверяем, что оркестратор работает без LLM агента
        response = await test_orchestrator.process_query("H2O свойства")

        # Должен быть fallback ответ
        assert "LLM агент недоступен" in response or "H2O" in response

    @pytest.mark.asyncio
    async def test_yaml_cache_priority(self, test_orchestrator, temp_cache_dir, yaml_h2o_data):
        """Тест приоритета YAML кэша над БД."""
        # Создаем YAML файл
        cache_dir = temp_cache_dir / "static_compounds"
        cache_dir.mkdir(parents=True, exist_ok=True)

        h2o_file = cache_dir / "H2O.yaml"
        h2o_file.write_text(yaml_h2o_data)

        # Проверяем, что YAML кэш доступен
        assert test_orchestrator.static_data_manager.is_available("H2O")

        # Выполняем поиск
        search_result = test_orchestrator.compound_searcher.search_all_phases(
            formula="H2O",
            max_temperature=500.0
        )

        # Проверки
        assert search_result.records is not None
        assert len(search_result.records) == 3  # s, l, g фазы
        assert search_result.phase_count == 3
        assert search_result.covers_298K
        assert search_result.tmelt == 273.15
        assert search_result.tboil == 373.15

    def test_multi_phase_config_validation(self):
        """Тест валидации конфигурации."""
        from thermo_agents.config.multi_phase_config import validate_config, MULTI_PHASE_CONFIG

        # Проверяем валидацию
        assert validate_config() is True

        # Проверяем значения
        assert MULTI_PHASE_CONFIG["integration_points"] == 400
        assert MULTI_PHASE_CONFIG["static_cache_dir"] == "data/static_compounds/"
        assert MULTI_PHASE_CONFIG["use_static_cache"] is True

    def test_orchestrator_initialization(self, temp_cache_dir):
        """Тест инициализации оркестратора."""
        config = MultiPhaseOrchestratorConfig(
            db_path="tests/fixtures/test_thermo.db",
            static_cache_dir=str(temp_cache_dir),
            integration_points=200
        )

        orchestrator = MultiPhaseOrchestrator(config)

        # Проверяем статус
        status = orchestrator.get_status()
        assert status["orchestrator_type"] == "multi_phase"
        assert status["status"] == "active"
        assert status["static_cache_enabled"] is True
        assert status["integration_points"] == 200

        # Проверяем компоненты
        assert "compound_searcher" in status["components"]
        assert "calculator" in status["components"]
        assert "static_data_manager" in status["components"]

    @pytest.mark.asyncio
    async def test_multi_phase_calculation_integration(self, test_orchestrator):
        """Интеграционный тест многофазного расчёта."""
        # Создаем тестовые данные
        from src.thermo_agents.models.search import DatabaseRecord

        # Прямой тест калькулятора
        records = [
            DatabaseRecord(
                id=1,
                formula="H2O",
                phase="s",
                tmin=0.0,
                tmax=273.15,
                h298=-285.83,
                s298=69.91,
                f1=16.62,
                f2=38.24,
                tmelt=273.15,
                reliability_class=1
            ),
            DatabaseRecord(
                id=2,
                formula="H2O",
                phase="l",
                tmin=273.15,
                tmax=373.15,
                h298=-285.83,
                s298=69.91,
                f1=75.29,
                tmelt=273.15,
                reliability_class=1
            )
        ]

        # Выполняем многофазный расчёт
        mp_result = test_orchestrator.calculator.calculate_multi_phase_properties(
            records=records,
            T_target=300.0
        )

        # Проверки
        assert mp_result.segments is not None
        assert len(mp_result.segments) == 2
        assert mp_result.Cp_final > 0
        assert mp_result.H_final < 0  # Энтальпия воды отрицательная
        assert mp_result.S_final > 0  # Энтропия положительная

    def test_static_data_manager_integration(self, temp_cache_dir):
        """Тест интеграции StaticDataManager."""
        from thermo_agents.storage.static_data_manager import StaticDataManager

        # Создаем тестовый YAML
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

        # Тестируем StaticDataManager
        manager = StaticDataManager(cache_dir)

        assert manager.is_available("CO2") is True
        assert manager.is_available("H2O") is False  # Не создан

        # Загрузка данных
        data = manager.load_compound("CO2")
        assert data is not None
        assert data.formula == "CO2"
        assert len(data.phases) == 1
        assert data.phases[0].phase == "g"


class TestMultiPhaseEdgeCases:
    """Тесты граничных случаев многофазных расчётов."""

    @pytest.mark.asyncio
    async def test_empty_query(self, test_orchestrator):
        """Тест пустого запроса."""
        response = await test_orchestrator.process_query("")
        assert len(response) > 0
        assert "❌" in response or "LLM агент недоступен" in response

    @pytest.mark.asyncio
    async def test_invalid_compound(self, test_orchestrator):
        """Тест несуществующего вещества."""
        # Без LLM агента будет fallback
        response = await test_orchestrator.process_query("InvalidCompound123 свойства")
        assert len(response) > 0

    def test_missing_database_file(self):
        """Тест отсутствующего файла БД."""
        config = MultiPhaseOrchestratorConfig(
            db_path="non_existent_file.db",
            static_cache_dir="temp"
        )

        # Оркестратор должен создаться, но будет ошибки при запросах
        orchestrator = MultiPhaseOrchestrator(config)
        status = orchestrator.get_status()
        assert status["orchestrator_type"] == "multi_phase"

    def test_invalid_cache_directory(self):
        """Тест некорректной директории кэша."""
        config = MultiPhaseOrchestratorConfig(
            db_path="tests/fixtures/test_thermo.db",
            static_cache_dir="/invalid/path/that/does/not/exist"
        )

        # Оркестратор должен создаться с предупреждением
        orchestrator = MultiPhaseOrchestrator(config)
        assert orchestrator.static_data_manager is not None