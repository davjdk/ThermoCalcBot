"""
Unit тесты для компонентов Telegram бота ThermoSystem.

Тесты:
- Конфигурация и валидация
- Модели данных
- Управление сессиями
- Форматирование ответов
"""

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Добавление пути к исходникам
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from thermo_agents.telegram.config import TelegramBotConfig, BotLimits, FileConfig
from thermo_agents.telegram.models import (
    UserSession, BotResponse, FileResponse, MessageType, CommandStatus
)
from thermo_agents.telegram.session_manager import SessionManager, RateLimiter
from thermo_agents.telegram.thermo_adapter import ResponseFormatter, FileGenerator


class TestTelegramBotConfig:
    """Тесты конфигурации Telegram бота."""

    def test_default_config(self):
        """Тест конфигурации по умолчанию."""
        config = TelegramBotConfig(
            bot_token="test_token",
            openrouter_api_key="test_api_key"
        )

        assert config.bot_token == "test_token"
        assert config.bot_username == "ThermoCalcBot"
        assert config.mode == "polling"
        assert config.limits.max_concurrent_users == 20
        assert config.file_config.auto_file_threshold == 3000

    def test_config_from_env(self):
        """Тест загрузки конфигурации из переменных окружения."""
        import os

        # Устанавливаем тестовые переменные
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["OPENROUTER_API_KEY"] = "test_api_key"
        os.environ["MAX_CONCURRENT_USERS"] = "50"
        os.environ["AUTO_FILE_THRESHOLD"] = "5000"

        try:
            config = TelegramBotConfig.from_env()
            assert config.bot_token == "test_token"
            assert config.openrouter_api_key == "test_api_key"
            assert config.limits.max_concurrent_users == 50
            assert config.file_config.auto_file_threshold == 5000
        finally:
            # Очищаем переменные
            for key in ["TELEGRAM_BOT_TOKEN", "OPENROUTER_API_KEY", "MAX_CONCURRENT_USERS", "AUTO_FILE_THRESHOLD"]:
                if key in os.environ:
                    del os.environ[key]

    def test_config_validation(self):
        """Тест валидации конфигурации."""
        config = TelegramBotConfig(
            bot_token="",
            openrouter_api_key=""
        )

        errors = config.validate_config()
        assert len(errors) >= 2
        assert any("TELEGRAM_BOT_TOKEN" in error for error in errors)
        assert any("OPENROUTER_API_KEY" in error for error in errors)

    def test_invalid_mode_validation(self):
        """Тест валидации недопустимого режима."""
        config = TelegramBotConfig(
            bot_token="test_token",
            openrouter_api_key="test_api_key",
            mode="invalid_mode"
        )

        errors = config.validate_config()
        assert any("TELEGRAM_MODE" in error for error in errors)


class TestTelegramModels:
    """Тесты моделей данных Telegram бота."""

    def test_user_session_creation(self):
        """Тест создания сессии пользователя."""
        session = UserSession(
            user_id=12345,
            username="testuser",
            first_name="Test"
        )

        assert session.user_id == 12345
        assert session.username == "testuser"
        assert session.first_name == "Test"
        assert session.chat_id == 12345
        assert session.message_count == 0
        assert session.current_query is None

    def test_session_activity_tracking(self):
        """Тест отслеживания активности сессии."""
        import time

        session = UserSession(user_id=12345)
        time.sleep(0.001)  # Небольшая задержка для разницы во времени

        initial_count = session.message_count
        session.update_activity()

        assert session.message_count == initial_count + 1
        # Даем время на обновление
        assert session.last_activity >= session.created_at

    def test_session_processing_state(self):
        """Тест состояния обработки запроса."""
        session = UserSession(user_id=12345)

        session.start_processing("test query")
        assert session.current_query == "test query"
        assert session.processing_start is not None
        assert session.is_processing() is True

        session.finish_processing()
        assert session.current_query is None
        assert session.processing_start is None
        assert session.is_processing() is False

    def test_bot_response_creation(self):
        """Тест создания ответа бота."""
        response = BotResponse(
            text="Test response",
            user_id=12345,
            original_query="test query"
        )

        assert response.text == "Test response"
        assert response.message_type == MessageType.TEXT_QUERY
        assert response.status == CommandStatus.SUCCESS
        assert response.user_id == 12345
        assert response.original_query == "test query"
        assert response.use_markdown is True

    def test_bot_response_to_telegram_dict(self):
        """Тест конвертации ответа в словарь Telegram API."""
        response = BotResponse(
            text="Test response",
            use_markdown=False
        )

        telegram_dict = response.to_telegram_dict()
        assert telegram_dict["text"] == "Test response"
        assert telegram_dict["parse_mode"] is None
        assert telegram_dict["disable_web_page_preview"] is True


class TestSessionManager:
    """Тесты менеджера сессий."""

    @pytest.fixture
    def session_manager(self):
        """Фикстура для создания менеджера сессий."""
        return SessionManager(max_concurrent_users=5)

    @pytest.mark.asyncio
    async def test_session_creation(self, session_manager):
        """Тест создания сессии."""
        session = session_manager.get_or_create_session(
            user_id=12345,
            username="testuser",
            first_name="Test"
        )

        assert session.user_id == 12345
        assert session.username == "testuser"
        assert session_manager.get_total_session_count() == 1

    @pytest.mark.asyncio
    async def test_session_retrieval(self, session_manager):
        """Тест получения существующей сессии."""
        # Создаем сессию
        session1 = session_manager.get_or_create_session(user_id=12345)

        # Получаем ту же сессию
        session2 = session_manager.get_or_create_session(user_id=12345)

        assert session1 is session2
        assert session_manager.get_total_session_count() == 1

    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        """Тест rate limiter."""
        rate_limiter = RateLimiter(requests_per_minute=3)

        user_id = 12345

        # Первые 3 запроса должны пройти
        assert rate_limiter.can_make_request(user_id) is True
        rate_limiter.record_request(user_id)

        assert rate_limiter.can_make_request(user_id) is True
        rate_limiter.record_request(user_id)

        assert rate_limiter.can_make_request(user_id) is True
        rate_limiter.record_request(user_id)

        # 4-й запрос должен быть заблокирован
        assert rate_limiter.can_make_request(user_id) is False

    @pytest.mark.asyncio
    async def test_system_stats(self, session_manager):
        """Тест получения статистики системы."""
        # Создаем несколько сессий
        for i in range(3):
            session_manager.get_or_create_session(user_id=1000 + i)

        stats = session_manager.get_system_stats()

        assert stats["total_sessions"] == 3
        assert stats["active_sessions"] == 3  # Только что созданные
        assert stats["max_concurrent_users"] == 5
        assert stats["memory_usage_mb"] > 0


class TestResponseFormatter:
    """Тесты форматирования ответов."""

    @pytest.fixture
    def formatter(self):
        """Фикстура для создания форматтера."""
        return ResponseFormatter()

    @pytest.mark.asyncio
    async def test_format_response(self, formatter):
        """Тест форматирования ответа."""
        query = "2 H2 + O2 → 2 H2O"
        raw_response = "Results for the reaction"

        response = await formatter.format_response(query, raw_response, 12345)

        assert isinstance(response, BotResponse)
        assert response.user_id == 12345
        assert response.original_query == query
        assert "🔥" in response.text  # Эмодзи для реакции
        assert "ТЕРМОДИНАМИЧЕСКИЙ" in response.text

    @pytest.mark.asyncio
    async def test_unicode_enhancement(self, formatter):
        """Тест улучшения Unicode формул."""
        text_with_formulas = "Reaction: H2O + CO2 → H2CO3"
        enhanced = formatter._enhance_chemical_formulas(text_with_formulas)

        assert "H₂O" in enhanced
        assert "CO₂" in enhanced
        assert "→" in enhanced

    @pytest.mark.asyncio
    async def test_response_truncation(self, formatter):
        """Тест обрезки слишком длинных ответов."""
        # Создаем очень длинный ответ
        long_text = "x" * 5000

        truncated = formatter._truncate_response(long_text)

        assert len(truncated) <= formatter.max_message_length
        assert "..." in truncated
        assert "файле" in truncated


class TestFileGenerator:
    """Тесты генератора файлов."""

    @pytest.fixture
    def file_config(self):
        """Фикстура для создания файловой конфигурации."""
        from thermo_agents.telegram.config import FileConfig
        return FileConfig(
            auto_file_threshold=100,
            temp_file_dir=Path(tempfile.mkdtemp())
        )

    @pytest.fixture
    def file_generator(self, file_config):
        """Фикстура для создания генератора файлов."""
        return FileGenerator(file_config)

    def test_should_use_file_decision(self, file_generator):
        """Тест решения об использовании файла."""
        # Короткий текст - не нужен файл
        assert file_generator.should_use_file("short text") is False

        # Длинный текст - нужен файл
        long_text = "x" * 200
        assert file_generator.should_use_file(long_text) is True

        # Большая таблица - нужен файл
        table_text = "| T (K) | Value |\n" * 60
        assert file_generator.should_use_file(table_text) is True

    @pytest.mark.asyncio
    async def test_file_generation(self, file_generator):
        """Тест генерации файла."""
        query = "Test query"
        response = "Test response with enough content to trigger file generation. " * 20

        file_response = await file_generator.generate_file_response(query, response, 12345)

        assert isinstance(file_response, FileResponse)
        assert file_response.user_id == 12345
        assert file_response.original_query == query
        assert file_response.file_path.exists()
        assert file_response.get_file_size_mb() > 0
        assert len(file_response.caption) > 0

    def test_professional_report_creation(self, file_generator):
        """Тест создания профессионального отчёта."""
        query = "2 H2 + O2 → 2 H2O"
        raw_response = "Thermodynamic calculation results"

        report = file_generator._create_professional_report(query, raw_response)

        assert "ТЕРМОДИНАМИЧЕСКИЙ РАСЧЁТ" in report
        assert query in report
        assert "ЗАПРОС:" in report
        assert "РЕЗУЛЬТАТЫ РАСЧЁТА" in report
        assert "ThermoSystem Telegram Bot" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])