"""
Performance тесты для конкурентных пользователей
"""

import pytest
import asyncio
import time
import psutil
import os
from unittest.mock import Mock, AsyncMock
from typing import List, Dict, Any

from src.thermo_agents.telegram_bot.bot import ThermoSystemTelegramBot
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_update, create_mock_context, create_mock_telegram_bot_config
)
from tests.telegram_bot.fixtures.test_data import (
    PERFORMANCE_TEST_PARAMS, SAMPLE_THERMO_RESPONSES
)


@pytest.mark.performance
class TestConcurrentUsers:
    """Performance тесты для конкурентных пользователей"""

    @pytest.fixture
    def performance_config(self):
        """Конфигурация для performance тестов"""
        config = create_mock_telegram_bot_config()
        config.max_concurrent_users = 50
        config.request_timeout_seconds = 30
        config.rate_limit_per_minute = 60
        return config

    @pytest.fixture
    async def performance_bot(self, performance_config):
        """Бот для performance тестов"""
        with patch('src.thermo_agents.telegram_bot.bot.Application') as mock_application, \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager') as mock_session_manager, \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter') as mock_rate_limiter, \
             patch('src.thermo_agents.telegram_bot.bot.ThermoIntegration') as mock_thermo_integration, \
             patch('src.thermo_agents.telegram_bot.bot.HealthChecker') as mock_health_checker, \
             patch('src.thermo_agents.telegram_bot.bot.TelegramBotErrorHandler') as mock_error_handler, \
             patch('src.thermo_agents.telegram_bot.bot.SmartResponseHandler') as mock_smart_response, \
             patch('src.thermo_agents.telegram_bot.bot.CommandHandler') as mock_command_handler, \
             patch('src.thermo_agents.telegram_bot.bot.AdminCommands') as mock_admin_commands, \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler') as mock_message_handler, \
             patch('src.thermo_agents.telegram_bot.bot.CallbackHandler') as mock_callback_handler:

            # Mock ThermoIntegration с реалистичной задержкой
            mock_thermo_instance = Mock()
            mock_thermo_instance.process_thermodynamic_query = AsyncMock(
                side_effect=self._mock_thermo_processing
            )
            mock_thermo_instance.health_check = AsyncMock(return_value={
                "status": "healthy",
                "components": {"database": True, "llm": True}
            })
            mock_thermo_integration.return_value = mock_thermo_instance

            # Mock session manager
            mock_session_instance = Mock()
            mock_session_instance.start_session = AsyncMock(return_value=True)
            mock_session_instance.is_user_active = Mock(return_value=True)
            mock_session_instance.update_activity = AsyncMock()
            mock_session_manager.return_value = mock_session_instance

            # Mock rate limiter
            mock_rate_instance = Mock()
            mock_rate_instance.check_rate_limit = AsyncMock(return_value=(True, None))
            mock_rate_limiter.return_value = mock_rate_instance

            bot = ThermoSystemTelegramBot(performance_config)
            bot.thermo_integration = mock_thermo_instance
            bot.session_manager = mock_session_instance
            bot.rate_limiter = mock_rate_instance

            yield bot

    async def _mock_thermo_processing(self, query: str) -> str:
        """Mock обработки термодинамического запроса с реалистичной задержкой"""
        # Симуляция времени обработки (0.5-2 секунды)
        processing_time = 0.5 + (hash(query) % 1500) / 1000
        await asyncio.sleep(processing_time)

        # Возвращаем соответствующий ответ
        if "H2O" in query:
            return SAMPLE_THERMO_RESPONSES["h2o_properties"]
        elif "reaction" in query or "+" in query:
            return SAMPLE_THERMO_RESPONSES["reaction_h2_o2"]
        else:
            return f"Thermodynamic response for {query}"

    @pytest.mark.asyncio
    async def test_concurrent_users_performance(self, performance_bot):
        """Тест производительности при конкурентных пользователях"""
        user_count = PERFORMANCE_TEST_PARAMS["concurrent_users"]
        requests_per_user = PERFORMANCE_TEST_PARAMS["requests_per_user"]

        async def simulate_user_request(user_id: int, request_id: int):
            """Симуляция запроса пользователя"""
            start_time = time.time()

            update = create_mock_update(f"H2O properties request {request_id}", user_id=user_id)
            context = create_mock_context()

            try:
                # Mock message handler
                performance_bot.message_handler.handle_message = AsyncMock()

                await performance_bot._handle_message(update, context)

                processing_time = time.time() - start_time
                return {
                    "user_id": user_id,
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "success": True
                }
            except Exception as e:
                processing_time = time.time() - start_time
                return {
                    "user_id": user_id,
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "success": False,
                    "error": str(e)
                }

        # Создание всех задач
        tasks = []
        for user_id in range(user_count):
            for request_id in range(requests_per_user):
                task = simulate_user_request(user_id, request_id)
                tasks.append(task)

        # Запуск всех задач concurrently
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Анализ результатов
        successful_results = [r for r in results if isinstance(r, dict) and r.get("success")]
        processing_times = [r["processing_time"] for r in successful_results]

        # Вычисление метрик
        success_rate = len(successful_results) / len(results)
        avg_processing_time = sum(processing_times) / len(processing_times)
        max_processing_time = max(processing_times)
        min_processing_time = min(processing_times)

        # Проверки производительности
        assert success_rate >= 0.95, f"Success rate too low: {success_rate}"
        assert max_processing_time < PERFORMANCE_TEST_PARAMS["max_response_time"], \
            f"Max response time too high: {max_processing_time}s"
        assert avg_processing_time < PERFORMANCE_TEST_PARAMS["avg_response_time"], \
            f"Average response time too high: {avg_processing_time}s"

        # Проверка общего времени выполнения
        expected_total_time = max(processing_times)  # Должно быть близко к максимальному времени
        assert total_time < expected_total_time + 5, \
            f"Total execution time too high: {total_time}s vs expected {expected_total_time}s"

        print(f"Performance Results:")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Average processing time: {avg_processing_time:.2f}s")
        print(f"  Max processing time: {max_processing_time:.2f}s")
        print(f"  Min processing time: {min_processing_time:.2f}s")
        print(f"  Total execution time: {total_time:.2f}s")

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, performance_bot):
        """Тест стабильности использования памяти"""
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Выполнение множества запросов
        for i in range(100):
            update = create_mock_update(f"Test query {i}", user_id=12345 + i % 10)
            context = create_mock_context()

            performance_bot.message_handler.handle_message = AsyncMock()
            await performance_bot._handle_message(update, context)

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Проверка, что память не выросла более чем на 100MB
        assert memory_increase < PERFORMANCE_TEST_PARAMS["memory_limit_mb"], \
            f"Memory increased by {memory_increase:.2f}MB, limit {PERFORMANCE_TEST_PARAMS['memory_limit_mb']}MB"

        print(f"Memory usage:")
        print(f"  Initial: {initial_memory:.2f}MB")
        print(f"  Final: {final_memory:.2f}MB")
        print(f"  Increase: {memory_increase:.2f}MB")

    @pytest.mark.asyncio
    async def test_response_time_regression(self, performance_bot):
        """Тест регрессии времени ответа"""
        response_times = []

        for i in range(50):
            start_time = time.time()

            update = create_mock_update("H2O properties at 298K", user_id=12345)
            context = create_mock_context()

            performance_bot.message_handler.handle_message = AsyncMock()
            await performance_bot._handle_message(update, context)

            response_time = time.time() - start_time
            response_times.append(response_time)

        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]

        # Проверки
        assert avg_response_time < PERFORMANCE_TEST_PARAMS["avg_response_time"], \
            f"Average response time regression: {avg_response_time:.2f}s"
        assert max_response_time < PERFORMANCE_TEST_PARAMS["max_response_time"], \
            f"Max response time regression: {max_response_time:.2f}s"
        assert p95_response_time < PERFORMANCE_TEST_PARAMS["max_response_time"] * 0.8, \
            f"95th percentile regression: {p95_response_time:.2f}s"

        print(f"Response time analysis:")
        print(f"  Average: {avg_response_time:.2f}s")
        print(f"  Maximum: {max_response_time:.2f}s")
        print(f"  95th percentile: {p95_response_time:.2f}s")

    @pytest.mark.asyncio
    async def test_load_balancing_efficiency(self, performance_bot):
        """Тест эффективности балансировки нагрузки"""
        user_scenarios = {}
        for user_id in range(20):
            user_scenarios[user_id] = [
                f"H2O properties at {298 + i*10}K" for i in range(5)
            ]

        async def simulate_user_session(user_id: int, queries: List[str]):
            """Симуляция пользовательской сессии"""
            session_times = []
            for query in queries:
                start_time = time.time()

                update = create_mock_update(query, user_id=user_id)
                context = create_mock_context()

                performance_bot.message_handler.handle_message = AsyncMock()
                await performance_bot._handle_message(update, context)

                session_times.append(time.time() - start_time)

            return {
                "user_id": user_id,
                "avg_time": sum(session_times) / len(session_times),
                "max_time": max(session_times),
                "min_time": min(session_times)
            }

        # Запуск всех пользовательских сессий
        tasks = [
            simulate_user_session(user_id, queries)
            for user_id, queries in user_scenarios.items()
        ]

        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Анализ балансировки
        avg_times = [r["avg_time"] for r in results if isinstance(r, dict)]
        max_avg_time = max(avg_times)
        min_avg_time = min(avg_times)
        balance_ratio = max_avg_time / min_avg_time

        # Проверка эффективной балансировки
        assert balance_ratio < 2.0, \
            f"Load balancing inefficient: ratio {balance_ratio:.2f}"

        # Проверка общего времени
        expected_parallel_time = max_avg_time
        assert total_time < expected_parallel_time + 3, \
            f"Parallel execution inefficient: {total_time:.2f}s vs expected {expected_parallel_time:.2f}s"

        print(f"Load balancing results:")
        print(f"  Balance ratio (max/min): {balance_ratio:.2f}")
        print(f"  Total parallel time: {total_time:.2f}s")
        print(f"  Expected time: {expected_parallel_time:.2f}s")

    @pytest.mark.asyncio
    async def test_rate_limiting_performance(self, performance_bot):
        """Тест производительности rate limiting"""
        user_id = 12345
        request_count = 30  # Количество запросов для теста

        # Mock rate limiter с реальными ограничениями
        from src.thermo_agents.telegram_bot.utils.rate_limiter import RateLimiter
        rate_limiter = RateLimiter(performance_bot.config)
        performance_bot.rate_limiter = rate_limiter

        start_time = time.time()
        allowed_requests = 0
        blocked_requests = 0

        for i in range(request_count):
            can_proceed, message = await rate_limiter.check_rate_limit(user_id)
            if can_proceed:
                allowed_requests += 1
                # Сброс счетчика rate limiter
                await rate_limiter.record_request(user_id)
            else:
                blocked_requests += 1

        total_time = time.time() - start_time

        # Проверки
        assert allowed_requests > 0, "No requests were allowed"
        assert blocked_requests >= 0, "Negative blocked requests"

        # Проверка производительности rate limiting
        rate_limiting_overhead = total_time / request_count
        assert rate_limiting_overhead < 0.01, \
            f"Rate limiting too slow: {rate_limiting_overhead*1000:.2f}ms per request"

        print(f"Rate limiting performance:")
        print(f"  Allowed requests: {allowed_requests}")
        print(f"  Blocked requests: {blocked_requests}")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Overhead per request: {rate_limiting_overhead*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_session_management_performance(self, performance_bot):
        """Тест производительности управления сессиями"""
        user_count = 50
        session_operations = []

        # Тест создания сессий
        start_time = time.time()
        for user_id in range(user_count):
            operation_start = time.time()
            await performance_bot.session_manager.start_session(
                user_id, f"user{user_id}", f"User{user_id}"
            )
            session_operations.append(time.time() - operation_start)

        creation_time = time.time() - start_time
        avg_creation_time = sum(session_operations) / len(session_operations)

        # Тест обновления активности
        update_operations = []
        for i in range(200):  # 200 обновлений активности
            operation_start = time.time()
            await performance_bot.session_manager.update_activity(i % user_count)
            update_operations.append(time.time() - operation_start)

        # Проверки производительности
        assert avg_creation_time < 0.01, \
            f"Session creation too slow: {avg_creation_time*1000:.2f}ms"
        assert creation_time < 1.0, \
            f"Batch session creation too slow: {creation_time:.2f}s"

        avg_update_time = sum(update_operations) / len(update_operations)
        assert avg_update_time < 0.001, \
            f"Activity update too slow: {avg_update_time*1000:.3f}ms"

        print(f"Session management performance:")
        print(f"  Avg session creation: {avg_creation_time*1000:.2f}ms")
        print(f"  Total creation time: {creation_time:.3f}s")
        print(f"  Avg activity update: {avg_update_time*1000:.3f}ms")

    @pytest.mark.asyncio
    async def test_error_handling_performance(self, performance_bot):
        """Тест производительности обработки ошибок"""
        error_count = 50
        error_times = []

        # Mock ошибок в ThermoIntegration
        performance_bot.thermo_integration.process_thermodynamic_query = AsyncMock(
            side_effect=Exception("Simulated error")
        )

        for i in range(error_count):
            start_time = time.time()

            update = create_mock_update(f"Error query {i}", user_id=12345)
            context = create_mock_context()
            update.message.reply_text = AsyncMock()

            try:
                await performance_bot._handle_message(update, context)
            except Exception:
                pass  # Ожидаем ошибки

            error_times.append(time.time() - start_time)

        avg_error_time = sum(error_times) / len(error_times)
        max_error_time = max(error_times)

        # Проверки производительности обработки ошибок
        assert avg_error_time < 0.1, \
            f"Error handling too slow: {avg_error_time*1000:.2f}ms"
        assert max_error_time < 0.5, \
            f"Max error handling time too high: {max_error_time*1000:.2f}ms"

        print(f"Error handling performance:")
        print(f"  Average error time: {avg_error_time*1000:.2f}ms")
        print(f"  Max error time: {max_error_time*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_resource_cleanup_performance(self, performance_bot):
        """Тест производительности очистки ресурсов"""
        # Создание множества временных файлов
        from src.thermo_agents.telegram_bot.formatters.file_handler import FileHandler
        file_handler = FileHandler(performance_bot.config)

        file_creation_times = []
        file_cleanup_times = []

        # Тест создания файлов
        for i in range(20):
            start_time = time.time()
            content = f"Test content {i}\n" * 100
            await file_handler.create_thermo_report_file(content, 12345 + i, f"Test {i}")
            file_creation_times.append(time.time() - start_time)

        # Тест очистки файлов
        start_time = time.time()
        cleaned_count = await file_handler.cleanup_old_files()
        cleanup_time = time.time() - start_time

        # Проверки производительности
        avg_creation_time = sum(file_creation_times) / len(file_creation_times)
        assert avg_creation_time < 0.1, \
            f"File creation too slow: {avg_creation_time*1000:.2f}ms"
        assert cleanup_time < 2.0, \
            f"File cleanup too slow: {cleanup_time:.2f}s"

        print(f"File operations performance:")
        print(f"  Avg file creation: {avg_creation_time*1000:.2f}ms")
        print(f"  Cleanup time: {cleanup_time:.3f}s")
        print(f"  Files cleaned: {cleaned_count}")


@pytest.mark.performance
@pytest.mark.slow
class TestStressTests:
    """Стресс-тесты для экстремальных нагрузок"""

    @pytest.fixture
    def stress_config(self):
        """Конфигурация для стресс-тестов"""
        config = create_mock_telegram_bot_config()
        config.max_concurrent_users = 200
        config.request_timeout_seconds = 60
        return config

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self, stress_config):
        """Стресс-тест с высокой конкурентностью"""
        user_count = 100
        requests_per_user = 10
        max_concurrent = 50

        with patch('src.thermo_agents.telegram_bot.bot.Application'), \
             patch('src.thermo_agents.telegram_bot.bot.SessionManager') as mock_session_manager, \
             patch('src.thermo_agents.telegram_bot.bot.RateLimiter') as mock_rate_limiter, \
             patch('src.thermo_agents.telegram_bot.bot.ThermoIntegration') as mock_thermo_integration, \
             patch('src.thermo_agents.telegram_bot.bot.MessageHandler') as mock_message_handler:

            # Mock компонентов
            mock_thermo_instance = Mock()
            mock_thermo_instance.process_thermodynamic_query = AsyncMock(
                side_effect=lambda q: f"Response for {q}"
            )
            mock_thermo_integration.return_value = mock_thermo_instance

            mock_session_instance = Mock()
            mock_session_instance.start_session = AsyncMock(return_value=True)
            mock_session_instance.is_user_active = Mock(return_value=True)
            mock_session_instance.update_activity = AsyncMock()
            mock_session_manager.return_value = mock_session_instance

            mock_rate_instance = Mock()
            mock_rate_instance.check_rate_limit = AsyncMock(return_value=(True, None))
            mock_rate_limiter.return_value = mock_rate_instance

            bot = ThermoSystemTelegramBot(stress_config)
            bot.thermo_integration = mock_thermo_instance
            bot.session_manager = mock_session_instance
            bot.rate_limiter = mock_rate_instance

            # Стресс-тест
            semaphore = asyncio.Semaphore(max_concurrent)

            async def stress_request(user_id: int, request_id: int):
                async with semaphore:
                    start_time = time.time()
                    try:
                        update = create_mock_update(f"Stress test {request_id}", user_id=user_id)
                        context = create_mock_context()
                        bot.message_handler.handle_message = AsyncMock()
                        await bot._handle_message(update, context)
                        return {"success": True, "time": time.time() - start_time}
                    except Exception:
                        return {"success": False, "time": time.time() - start_time}

            # Запуск стресс-теста
            tasks = []
            for user_id in range(user_count):
                for request_id in range(requests_per_user):
                    task = stress_request(user_id, request_id)
                    tasks.append(task)

            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            total_time = time.time() - start_time

            # Анализ результатов
            successful = [r for r in results if isinstance(r, dict) and r.get("success")]
            success_rate = len(successful) / len(results)

            # Проверки стресс-теста
            assert success_rate >= 0.90, f"Stress test failed: success rate {success_rate}"
            assert total_time < 60, f"Stress test too slow: {total_time}s"

            print(f"Stress test results:")
            print(f"  Total requests: {len(results)}")
            print(f"  Successful: {len(successful)}")
            print(f"  Success rate: {success_rate:.2%}")
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Requests per second: {len(results)/total_time:.2f}")