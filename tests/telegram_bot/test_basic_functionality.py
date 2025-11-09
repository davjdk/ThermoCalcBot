"""
Базовые тесты функциональности Telegram бота.

Тестирование основных компонентов без запуска самого бота.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from thermo_agents.telegram_bot.config import TelegramBotConfig, BotStatus
from thermo_agents.telegram_bot.formatters.file_handler import FileHandler
from thermo_agents.telegram_bot.formatters.response_formatter import ResponseFormatter
from thermo_agents.telegram_bot.utils.session_manager import SessionManager
from thermo_agents.telegram_bot.utils.rate_limiter import RateLimiter


class TestTelegramBotBasics:
    """Тесты базовой функциональности Telegram бота."""

    @pytest.fixture
    def config(self):
        """Тестовая конфигурация."""
        return TelegramBotConfig(
            bot_token="test_token",
            llm_api_key="test_key",
            thermo_db_path=Path("data/thermo_data.db"),
            temp_file_dir=Path("temp/test_files"),
            max_concurrent_users=5
        )

    @pytest.fixture
    def status(self):
        """Тестовый статус."""
        return BotStatus()

    @pytest.fixture
    def file_handler(self, config):
        """FileHandler для тестов."""
        handler = FileHandler(config)
        # Создание тестовой директории
        handler.temp_file_dir.mkdir(parents=True, exist_ok=True)
        return handler

    @pytest.fixture
    def response_formatter(self, config):
        """ResponseFormatter для тестов."""
        return ResponseFormatter(config)

    @pytest.fixture
    def session_manager(self, config):
        """SessionManager для тестов."""
        return SessionManager(config)

    @pytest.fixture
    def rate_limiter(self, config):
        """RateLimiter для тестов."""
        return RateLimiter(config)

    def test_config_validation(self, config):
        """Тест валидации конфигурации."""
        # Проверка валидной конфигурации
        errors = config.validate_config()
        # Ошибки могут быть из-за отсутствия реальных файлов, но токены должны быть в порядке
        assert "TELEGRAM_BOT_TOKEN" not in str(errors)
        assert "OPENROUTER_API_KEY" not in str(errors)

    def test_file_handler_filename_generation(self, file_handler):
        """Тест генерации имен файлов."""
        filename = file_handler._generate_filename("reaction", ["H2", "O2"])
        assert filename.startswith("thermo_reaction_")
        assert filename.endswith(".txt")

        # Проверка очистки имени
        clean_name = file_handler._sanitize_filename("H2O:Test/File")
        assert ":" not in clean_name
        assert "/" not in clean_name

    @pytest.mark.asyncio
    async def test_file_handler_create_txt_file(self, file_handler):
        """Тест создания TXT файла."""
        content = "Тестовый термодинамический отчет"
        file_path, error = await file_handler.create_txt_file(
            content,
            "reaction",
            ["H2O"],
            "Тестовый отчет"
        )

        assert file_path is not None
        assert error is None
        assert file_path.exists()

        # Проверка содержимого
        async with asyncio.to_thread(open, file_path, 'r', encoding='utf-8') as f:
            file_content = asyncio.to_thread(f.read)
            content = await file_content
            assert "Тестовый термодинамический отчет" in content
            assert "Тестовый отчет" in content

        # Очистка
        await asyncio.to_thread(file_path.unlink)

    def test_response_formatter_basic(self, response_formatter):
        """Тест базового форматирования ответов."""
        content = "ΔH = -285.8 kJ/mol\nΔS = -69.9 J/(mol·K)"
        formatted = response_formatter.format_thermo_response(content, "reaction")

        assert isinstance(formatted, list)
        assert len(formatted) >= 1
        assert "ΔH" in formatted[0]
        assert "ΔS" in formatted[0]

    def test_response_formatter_help(self, response_formatter):
        """Тест форматирования справки."""
        help_text = response_formatter.format_help_message()
        assert "ThermoSystem" in help_text
        assert "команд" in help_text.lower()

    def test_response_formatter_error(self, response_formatter):
        """Тест форматирования ошибок."""
        error_text = response_formatter.format_error_message("Тестовая ошибка")
        assert "Тестовая ошибка" in error_text
        assert "❌" in error_text

    @pytest.mark.asyncio
    async def test_session_manager_basic(self, session_manager):
        """Тест базовой функциональности менеджера сессий."""
        user_id = 12345

        # Начало сессии
        started = await session_manager.start_session(
            user_id,
            "testuser",
            "Test User"
        )
        assert started is True
        assert session_manager.is_user_active(user_id) is True

        # Обновление активности
        await session_manager.update_activity(user_id)

        # Получение информации
        info = session_manager.get_session_info(user_id)
        assert info is not None
        assert info.user_id == user_id
        assert info.username == "testuser"

        # Завершение сессии
        await session_manager.end_session(user_id)
        assert session_manager.is_user_active(user_id) is False

    def test_session_manager_limits(self, session_manager):
        """Тест лимитов менеджера сессий."""
        # Изначально должно быть место для новых пользователей
        assert session_manager.can_accept_new_user() is True

        # Статистика должна быть пустой
        stats = session_manager.get_user_statistics()
        assert stats["total_users"] == 0
        assert stats["active_users"] == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_basic(self, rate_limiter):
        """Тест базовой функциональности RateLimiter."""
        user_id = 12345

        # Первые несколько запросов должны проходить
        for i in range(3):
            can_proceed, message = await rate_limiter.check_rate_limit(user_id)
            assert can_proceed is True
            assert message is None

        # Проверка информации о лимитах
        info = rate_limiter.get_user_rate_info(user_id)
        assert info.requests_count == 3
        assert info.is_limited is False

    def test_rate_limiter_stats(self, rate_limiter):
        """Тест статистики RateLimiter."""
        stats = rate_limiter.get_global_rate_info()
        assert "requests_per_second" in stats
        assert "requests_per_minute" in stats
        assert "active_users" in stats
        assert stats["active_users"] == 0

    @pytest.mark.asyncio
    async def test_file_handler_should_send_as_file(self, file_handler):
        """Тест логики определения формата отправки."""
        # Короткий контент - как сообщение
        short_content = "Короткий ответ"
        assert file_handler.should_send_as_file(short_content) is False

        # Длинный контент - как файл
        long_content = "A" * 3500  # Больше порога в 3000
        assert file_handler.should_send_as_file(long_content) is True

        # Контент с большими таблицами
        table_content = "Температура\tCp\tH\tS\tG\n" + "300\t50\t100\t200\t50\n" * 10
        if len(table_content) > 2000:
            assert file_handler.should_send_as_file(table_content, True) is True

    @pytest.mark.asyncio
    async def test_cleanup_teardown(self, session_manager, rate_limiter):
        """Тест корректной очистки ресурсов."""
        # Завершение работы компонентов
        await session_manager.shutdown()
        await rate_limiter.cleanup()

    def test_status_model(self, status):
        """Тест модели статуса."""
        assert status.is_running is False
        assert status.active_users == 0
        assert status.total_requests == 0

        # Обновление статуса
        status.is_running = True
        status.active_users = 5
        status.total_requests = 10

        assert status.is_running is True
        assert status.active_users == 5
        assert status.total_requests == 10