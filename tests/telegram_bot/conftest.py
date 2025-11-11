"""
Общие фикстуры и конфигурация для всех тестов Telegram бота
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_user, create_mock_chat, create_mock_message,
    create_mock_update, create_mock_command_update, create_mock_context,
    create_mock_callback_query, create_mock_orchestrator,
    create_mock_session_manager, create_mock_telegram_bot_config,
    SAMPLE_THERMO_RESPONSES, MOCK_UPDATES
)
from tests.telegram_bot.fixtures.test_data import (
    TEST_COMPOUNDS, TEST_REACTIONS, TEST_QUERIES,
    EXPECTED_RESPONSES, PERFORMANCE_TEST_PARAMS,
    TEMPERATURE_RANGES, PHASES, UNITS
)
from tests.telegram_bot.utils import (
    assert_telegram_message_sent, assert_telegram_file_sent,
    assert_telegram_chat_action_sent, create_temp_file,
    run_async_test_with_timeout, measure_async_execution_time,
    create_mock_memory_usage, assert_response_within_time_limit,
    assert_memory_usage_within_limit, extract_table_from_response,
    extract_thermodynamic_values, simulate_concurrent_requests,
    cleanup_temp_files, assert_file_content_matches,
    assert_chemical_formulas_preserved, AsyncMockContext,
    create_large_response, assert_message_split_correctly,
    TelegramBotTestClient, ConcurrentTestRunner
)


# Общие фикстуры для всех тестов
@pytest.fixture(scope="session")
def event_loop():
    """Создание event loop для всех тестов"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def temp_dir():
    """Временная директория для всех тестов"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture(autouse=True)
async def cleanup_after_test():
    """Автоматическая очистка после каждого теста"""
    yield
    # Здесь можно добавить общую логику очистки
    await asyncio.sleep(0.01)  # Небольшая задержка для cleanup


# Фикстуры для моков
@pytest.fixture
def mock_update():
    """Базовый mock обновления"""
    return create_mock_update("test message")


@pytest.fixture
def mock_context():
    """Базовый mock контекста"""
    return create_mock_context()


@pytest.fixture
def mock_config():
    """Базовая mock конфигурация"""
    return create_mock_telegram_bot_config()


@pytest.fixture
def mock_orchestrator():
    """Базовый mock оркестратора"""
    return create_mock_orchestrator()


@pytest.fixture
def mock_session_manager():
    """Базовый mock менеджера сессий"""
    return create_mock_session_manager()


# Параметры для тестов
@pytest.fixture
def performance_params():
    """Параметры для performance тестов"""
    return PERFORMANCE_TEST_PARAMS


@pytest.fixture
def test_queries():
    """Тестовые запросы"""
    return TEST_QUERIES


@pytest.fixture
def sample_responses():
    """Примеры ответов"""
    return SAMPLE_THERMO_RESPONSES


@pytest.fixture
def test_compounds():
    """Тестовые соединения"""
    return TEST_COMPOUNDS


@pytest.fixture
def test_reactions():
    """Тестовые реакции"""
    return TEST_REACTIONS


# Конфигурация pytest
def pytest_configure(config):
    """Дополнительная конфигурация pytest"""
    config.addinivalue_line(
        "markers", "unit: Unit тесты"
    )
    config.addinivalue_line(
        "markers", "integration: Интеграционные тесты"
    )
    config.addinivalue_line(
        "markers", "performance: Performance тесты"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end тесты"
    )
    config.addinivalue_line(
        "markers", "slow: Медленные тесты"
    )
    config.addinivalue_line(
        "markers", "external: Тесты требующие внешних сервисов"
    )


@pytest.fixture(autouse=True)
def skip_external_tests(request):
    """Автоматический пропуск external тестов если нет переменных окружения"""
    if "external" in request.node.keywords:
        if not os.getenv("TELEGRAM_BOT_TOKEN_TEST"):
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")


# Хелперы для тестов
@pytest.fixture
def telegram_test_client():
    """Test клиент для бота"""
    from tests.telegram_bot.utils.bot_test_client import TelegramBotTestClient
    return TelegramBotTestClient


@pytest.fixture
def test_helpers():
    """Тестовые хелперы"""
    import tests.telegram_bot.utils.test_helpers as helpers
    return helpers


# Database фикстуры для интеграционных тестов
@pytest.fixture
async def test_database(temp_dir):
    """Создание тестовой базы данных"""
    db_path = temp_dir / "test_thermo_data.db"

    # Копирование реальной базы данных если она существует
    real_db = Path("data/thermo_data.db")
    if real_db.exists():
        import shutil
        shutil.copy2(real_db, db_path)
    else:
        # Создание пустой базы данных для тестов
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.close()

    yield db_path

    # Очистка
    if db_path.exists():
        db_path.unlink()


# Logging фикстуры
@pytest.fixture
def capture_logs():
    """Перехват логов для тестов"""
    import logging
    from io import StringIO

    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger("src.thermo_agents.telegram_bot")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield log_capture

    logger.removeHandler(handler)


# Mock фикстуры для внешних зависимостей
@pytest.fixture
def mock_telegram_application():
    """Mock Telegram Application"""
    app = Mock()
    app.add_handler = Mock()
    app.run_polling = AsyncMock()
    app.stop = AsyncMock()
    app.shutdown = AsyncMock()
    app.bot = Mock()
    return app


@pytest.fixture
def mock_telegram_bot():
    """Mock Telegram Bot"""
    bot = Mock()
    bot.send_message = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_chat_action = AsyncMock()
    bot.get_me = AsyncMock()
    return bot


# Performance фикстуры
@pytest.fixture
def performance_monitor():
    """Мониторинг производительности для тестов"""
    import psutil
    import time

    class PerformanceMonitor:
        def __init__(self):
            self.process = psutil.Process()
            self.start_time = None
            self.start_memory = None

        def start(self):
            self.start_time = time.time()
            self.start_memory = self.process.memory_info().rss / 1024 / 1024

        def stop(self):
            end_time = time.time()
            end_memory = self.process.memory_info().rss / 1024 / 1024

            return {
                "execution_time": end_time - self.start_time,
                "memory_used": end_memory - self.start_memory,
                "peak_memory": end_memory
            }

    return PerformanceMonitor()


# Error handling фикстуры
@pytest.fixture
def error_collector():
    """Сборщик ошибок для тестов"""
    class ErrorCollector:
        def __init__(self):
            self.errors = []

        def add_error(self, error):
            self.errors.append(error)

        def get_errors(self):
            return self.errors

        def clear(self):
            self.errors.clear()

        def has_errors(self):
            return len(self.errors) > 0

    return ErrorCollector()


# Асинхронные фикстуры
@pytest.fixture
async def async_test_context():
    """Контекст для асинхронных тестов"""
    class AsyncTestContext:
        def __init__(self):
            self.tasks = []

        def add_task(self, coro):
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task

        async def wait_all(self):
            if self.tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        async def cleanup(self):
            for task in self.tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            self.tasks.clear()

    context = AsyncTestContext()
    yield context
    await context.cleanup()


# File system фикстуры
@pytest.fixture
def temp_file_factory(temp_dir):
    """Фабрика временных файлов"""
    def create_temp_file(content="test content", suffix=".txt", prefix="test_"):
        import tempfile
        fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=str(temp_dir))
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return Path(path)

    return create_temp_file


# Time fixtures
@pytest.fixture
def mock_time():
    """Mock времени для тестов"""
    from unittest.mock import patch

    with patch('time.time') as mock_time_func:
        mock_time_func.return_value = 1234567890.0
        yield mock_time_func


# Network fixtures
@pytest.fixture
def mock_network():
    """Mock сетевых запросов"""
    import aiohttp

    async def mock_session(*args, **kwargs):
        session = Mock()
        session.get = AsyncMock()
        session.post = AsyncMock()
        session.close = AsyncMock()
        return session

    with patch('aiohttp.ClientSession', side_effect=mock_session):
        yield mock_session