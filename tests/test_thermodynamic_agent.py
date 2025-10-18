"""
Unit-тесты для ThermodynamicAgent с использованием новой модели ExtractedReactionParameters.

Тесты проверяют корректность извлечения параметров реакции, валидацию данных,
обработку ошибок и поддержку до 10 веществ в реакции.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

from thermo_agents.thermodynamic_agent import ThermodynamicAgent, ThermoAgentConfig
from thermo_agents.models.extraction import ExtractedReactionParameters


class TestExtractedReactionParameters:
    """Тесты для модели ExtractedReactionParameters."""

    def test_valid_simple_reaction(self):
        """Тест валидной простой реакции."""
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="2H2 + O2 → 2H2O",
            all_compounds=["H2", "O2", "H2O"],
            reactants=["H2", "O2"],
            products=["H2O"],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.95,
            missing_fields=[]
        )

        assert params.balanced_equation == "2H2 + O2 → 2H2O"
        assert len(params.all_compounds) == 3
        assert params.is_complete() is True
        assert params.temperature_range_k == (298, 1000)

    def test_valid_complex_reaction(self):
        """Тест валидной сложной реакции с 10 веществами."""
        compounds = [f"C{i}H{j}" for i, j in [(1, 4), (2, 6), (3, 8), (4, 10), (5, 12)]]
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="C1H4 + C2H6 + C3H8 + C4H10 + C5H12 → Products",
            all_compounds=compounds,
            reactants=compounds[:3],
            products=compounds[3:],
            temperature_range_k=(500, 1500),
            extraction_confidence=0.85,
            missing_fields=[]
        )

        assert len(params.all_compounds) == 5
        assert params.is_complete() is True

    def test_invalid_too_many_compounds(self):
        """Тест реакции с превышением максимального количества веществ."""
        with pytest.raises(ValidationError):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="Complex reaction",
                all_compounds=[f"C{i}" for i in range(11)],  # 11 веществ > 10
                reactants=["C1", "C2"],
                products=["C3", "C4"],
                temperature_range_k=(298, 1000),
                extraction_confidence=0.9,
                missing_fields=[]
            )

    def test_invalid_temperature_range(self):
        """Тест невалидного температурного диапазона."""
        # Tmin >= Tmax
        with pytest.raises(ValidationError, match="Tmax должен быть больше Tmin"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(500, 300),  # Tmin > Tmax
                extraction_confidence=0.9,
                missing_fields=[]
            )

        # Отрицательная температура
        with pytest.raises(ValidationError, match="Tmin не может быть отрицательной"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(-100, 300),  # Отрицательная Tmin
                extraction_confidence=0.9,
                missing_fields=[]
            )

        # Слишком высокая температура
        with pytest.raises(ValidationError, match="Tmax слишком высокая"):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(298, 15000),  # Tmax > 10000K
                extraction_confidence=0.9,
                missing_fields=[]
            )

    def test_invalid_confidence_range(self):
        """Тест невалидного значения уверенности."""
        with pytest.raises(ValidationError):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(298, 1000),
                extraction_confidence=1.5,  # > 1.0
                missing_fields=[]
            )

        with pytest.raises(ValidationError):
            ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(298, 1000),
                extraction_confidence=-0.1,  # < 0.0
                missing_fields=[]
            )

    def test_incomplete_parameters(self):
        """Тест неполных параметров с missing_fields."""
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="A + B → C",
            all_compounds=["A", "B", "C"],
            reactants=["A", "B"],
            products=["C"],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.7,
            missing_fields=["temperature_range"]  # Указываем, что поле отсутствует
        )

        # Явно устанавливаем missing_fields, так как is_complete() их проверяет
        params.missing_fields = ["temperature_range"]
        assert params.is_complete() is False

    def test_is_complete_method(self):
        """Тест метода is_complete()."""
        # Полные параметры
        complete_params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="A + B → C",
            all_compounds=["A", "B", "C"],
            reactants=["A", "B"],
            products=["C"],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.9,
            missing_fields=[]
        )
        assert complete_params.is_complete() is True

        # Неполные параметры (compound_data, т.к. пустой balanced_equation не пройдет валидацию для reaction_calculation)
        incomplete_params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["A"],  # Только одно вещество для compound_data
            reactants=[],
            products=[],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.8,
            missing_fields=["temperature_range"]  # Указываем, что отсутствует температурный диапазон
        )
        assert incomplete_params.is_complete() is False

        # Полные параметры для compound_data
        compound_data_params = ExtractedReactionParameters(
            query_type="compound_data",
            balanced_equation="",
            all_compounds=["H2O"],
            reactants=[],
            products=[],
            temperature_range_k=(298, 1000),
            extraction_confidence=1.0,
            missing_fields=[]
        )
        assert compound_data_params.is_complete() is True


class TestThermodynamicAgent:
    """Тесты для ThermodynamicAgent."""

    @pytest.fixture
    def mock_config(self):
        """Фикстура с мок-конфигурацией агента."""
        config = MagicMock(spec=ThermoAgentConfig)
        config.agent_id = "test_agent"
        config.llm_api_key = "test_key"
        config.llm_base_url = "https://test.url"
        config.llm_model = "test:model"
        config.max_retries = 3
        config.poll_interval = 0.1
        config.storage = MagicMock()
        config.logger = MagicMock()
        config.session_logger = MagicMock()
        return config

    @pytest.fixture
    def mock_agent(self, mock_config):
        """Фикстура с мок-агентом."""
        with patch('thermo_agents.thermodynamic_agent.OpenAIProvider'), \
             patch('thermo_agents.thermodynamic_agent.OpenAIChatModel'):
            agent = ThermodynamicAgent(mock_config)
            # Мокаем PydanticAI агент
            agent.agent = AsyncMock()
            return agent

    @pytest.mark.asyncio
    async def test_extract_parameters_success(self, mock_agent):
        """Тест успешного извлечения параметров."""
        # Моковые данные
        mock_params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="TiO2 + 2Cl2 → TiCl4 + O2",
            all_compounds=["TiO2", "Cl2", "TiCl4", "O2"],
            reactants=["TiO2", "Cl2"],
            products=["TiCl4", "O2"],
            temperature_range_k=(600, 900),
            extraction_confidence=0.95,
            missing_fields=[]
        )

        # Мокаем результат от PydanticAI
        mock_result = MagicMock()
        mock_result.output = mock_params
        mock_agent.agent.run.return_value = mock_result

        # Выполняем метод
        result = await mock_agent.extract_parameters("Хлорирование оксида титана при 600-900K")

        # Проверяем результат
        assert isinstance(result, ExtractedReactionParameters)
        assert result.balanced_equation == "TiO2 + 2Cl2 → TiCl4 + O2"
        assert len(result.all_compounds) == 4
        assert result.temperature_range_k == (600, 900)
        assert result.is_complete() is True

        # Проверяем, что агент был вызван с правильным промптом
        mock_agent.agent.run.assert_called_once()
        call_args = mock_agent.agent.run.call_args[0]
        assert "Хлорирование оксида титана при 600-900K" in call_args[0]

    @pytest.mark.asyncio
    async def test_extract_parameters_incomplete_data(self, mock_agent):
        """Тест извлечения с неполными данными."""
        # Моковые данные с отсутствующими полями
        mock_params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="Fe2O3 + 3H2 → 2Fe + 3H2O",
            all_compounds=["Fe2O3", "H2", "Fe", "H2O"],
            reactants=["Fe2O3", "H2"],
            products=["Fe", "H2O"],
            temperature_range_k=(298, 1000),
            extraction_confidence=0.85,
            missing_fields=["temperature_range"]  # Отсутствует температурный диапазон
        )

        mock_result = MagicMock()
        mock_result.output = mock_params
        mock_agent.agent.run.return_value = mock_result

        # Должно вызвать ошибку из-за неполных данных
        with pytest.raises(ValueError, match="Не удалось извлечь обязательные поля"):
            await mock_agent.extract_parameters("Восстановление оксида железа")

    @pytest.mark.asyncio
    async def test_extract_parameters_timeout_error(self, mock_agent):
        """Тест обработки таймаута."""
        import asyncio
        mock_agent.agent.run.side_effect = asyncio.TimeoutError()

        with pytest.raises(ValueError, match="превышено время ожидания"):
            await mock_agent.extract_parameters("Тестовый запрос")

    @pytest.mark.asyncio
    async def test_extract_parameters_auth_error(self, mock_agent):
        """Тест обработки ошибки аутентификации."""
        mock_agent.agent.run.side_effect = Exception("status_code: 401")

        with pytest.raises(ValueError, match="Ошибка аутентификации"):
            await mock_agent.extract_parameters("Тестовый запрос")

    @pytest.mark.asyncio
    async def test_extract_parameters_rate_limit_error(self, mock_agent):
        """Тест обработки ошибки rate limit."""
        mock_agent.agent.run.side_effect = Exception("status_code: 429")

        with pytest.raises(ValueError, match="Превышен лимит запросов"):
            await mock_agent.extract_parameters("Тестовый запрос")

    @pytest.mark.asyncio
    async def test_extract_parameters_network_error(self, mock_agent):
        """Тест обработки сетевой ошибки."""
        mock_agent.agent.run.side_effect = Exception("network connection failed")

        with pytest.raises(ValueError, match="Сетевая ошибка"):
            await mock_agent.extract_parameters("Тестовый запрос")

    @pytest.mark.asyncio
    async def test_extract_parameters_generic_error(self, mock_agent):
        """Тест обработки общей ошибки."""
        mock_agent.agent.run.side_effect = Exception("Unknown error occurred")

        with pytest.raises(ValueError, match="Не удалось извлечь параметры"):
            await mock_agent.extract_parameters("Тестовый запрос")

    @pytest.mark.asyncio
    async def test_extract_parameters_retry_mechanism(self, mock_agent):
        """Тест механизма повторных попыток."""
        # Первая попытка - ошибка, вторая - успех
        mock_params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="N2 + 3H2 → 2NH3",
            all_compounds=["N2", "H2", "NH3"],
            reactants=["N2", "H2"],
            products=["NH3"],
            temperature_range_k=(673, 773),
            extraction_confidence=1.0,
            missing_fields=[]
        )

        mock_result = MagicMock()
        mock_result.output = mock_params

        # Сначала ошибка, потом успех
        mock_agent.agent.run.side_effect = [
            Exception("Temporary failure"),
            mock_result
        ]

        result = await mock_agent.extract_parameters("Синтез аммиака")

        # Проверяем, что было 2 попытки
        assert mock_agent.agent.run.call_count == 2
        assert result.balanced_equation == "N2 + 3H2 → 2NH3"

    @pytest.mark.asyncio
    async def test_extract_parameters_max_retries_exceeded(self, mock_agent):
        """Тест превышения максимального количества попыток."""
        mock_agent.agent.run.side_effect = Exception("Persistent error")

        with pytest.raises(ValueError, match="после 3 попыток"):
            await mock_agent.extract_parameters("Тестовый запрос")

        # Проверяем, что было сделано максимальное количество попыток
        assert mock_agent.agent.run.call_count == 3

    def test_process_single_query_compatibility(self, mock_agent):
        """Тест совместимости метода process_single_query."""
        # Этот метод должен вызывать extract_parameters
        with patch.object(mock_agent, 'extract_parameters', new_callable=AsyncMock) as mock_extract:
            mock_params = ExtractedReactionParameters(
                query_type="reaction_calculation",
                balanced_equation="A + B → C",
                all_compounds=["A", "B", "C"],
                reactants=["A", "B"],
                products=["C"],
                temperature_range_k=(298, 1000),
                extraction_confidence=0.9,
                missing_fields=[]
            )
            mock_extract.return_value = mock_params

            # Вызываем process_single_query
            result = asyncio.run(mock_agent.process_single_query("Тест"))

            # Проверяем, что был вызван extract_parameters
            mock_extract.assert_called_once_with("Тест")
            assert result == mock_params


class TestIntegrationWithNewArchitecture:
    """Интеграционные тесты с новой архитектурой."""

    @pytest.mark.asyncio
    async def test_stoichiometric_coefficients_independence(self):
        """Тест независимости от стехиометрических коэффициентов."""
        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation="2H2 + O2 → 2H2O",  # Коэффициенты: 2, 1, 2
            all_compounds=["H2", "O2", "H2O"],     # Без коэффициентов
            reactants=["H2", "O2"],
            products=["H2O"],
            temperature_range_k=(500, 800),
            extraction_confidence=0.95,
            missing_fields=[]
        )

        # Проверяем, что в all_compounds нет коэффициентов
        assert "2H2" not in params.all_compounds
        assert "2H2O" not in params.all_compounds
        assert "H2" in params.all_compounds
        assert "O2" in params.all_compounds
        assert "H2O" in params.all_compounds

        # Коэффициенты остаются только в balanced_equation
        assert "2H2" in params.balanced_equation
        assert "2H2O" in params.balanced_equation

    def test_maximum_compounds_support(self):
        """Тест поддержки максимального количества веществ (10)."""
        max_compounds = [f"C{i}" for i in range(1, 11)]  # C1, C2, ..., C10

        params = ExtractedReactionParameters(
            query_type="reaction_calculation",
            balanced_equation=" + ".join(max_compounds[:5]) + " → " + " + ".join(max_compounds[5:]),
            all_compounds=max_compounds,
            reactants=max_compounds[:5],
            products=max_compounds[5:],
            temperature_range_k=(298, 2000),
            extraction_confidence=0.8,
            missing_fields=[]
        )

        assert len(params.all_compounds) == 10
        assert params.is_complete() is True

    def test_prompt_formatting(self):
        """Тест форматирования промпта."""
        from thermo_agents.prompts import THERMODYNAMIC_EXTRACTION_PROMPT

        user_query = "Хлорирование оксида титана при 600-900K"
        formatted_prompt = THERMODYNAMIC_EXTRACTION_PROMPT.format(user_query=user_query)

        assert user_query in formatted_prompt
        assert "до 10 веществ" in formatted_prompt
        assert "Стехиометрические коэффициенты НЕ используются" in formatted_prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])