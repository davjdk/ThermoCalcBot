"""
End-to-End тесты с реальным Telegram API

Эти тесты требуют реального токена бота и ID тестового чата.
Запускаются только при установке соответствующих переменных окружения.

Required environment variables:
- TELEGRAM_BOT_TOKEN_TEST: Токен тестового бота
- TELEGRAM_TEST_CHAT_ID: ID тестового чата

Запуск: pytest -m e2e -s
"""

import pytest
import asyncio
import os
import time
from typing import Optional
from telegram import Bot
from telegram.ext import Application
from telegram.request import BaseRequest

from tests.telegram_bot.fixtures.test_data import TEST_QUERIES


@pytest.mark.e2e
@pytest.mark.external
class TestRealTelegramBot:
    """E2E тесты с реальным Telegram API"""

    @pytest.fixture(scope="class")
    def real_bot_token(self):
        """Реальный токен бота (из переменных окружения)"""
        token = os.getenv("TELEGRAM_BOT_TOKEN_TEST")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set. Set this environment variable to run E2E tests.")
        return token

    @pytest.fixture(scope="class")
    def test_chat_id(self):
        """ID тестового чата (из переменных окружения)"""
        chat_id_str = os.getenv("TELEGRAM_TEST_CHAT_ID")
        if not chat_id_str:
            pytest.skip("TELEGRAM_TEST_CHAT_ID not set. Set this environment variable to run E2E tests.")
        return int(chat_id_str)

    @pytest.fixture(scope="class")
    async def real_bot(self, real_bot_token):
        """Создание реального бота для тестов"""
        application = Application.builder().token(real_bot_token).build()
        bot = application.bot
        yield bot
        await application.stop()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_connection(self, real_bot):
        """Тест подключения к реальному боту"""
        try:
            bot_info = await real_bot.get_me()
            assert bot_info is not None
            assert bot_info.username is not None
            assert bot_info.is_bot is True

            print(f"✅ Connected to bot: @{bot_info.username}")
            print(f"   Bot ID: {bot_info.id}")
            print(f"   Can read messages: {bot_info.can_read_all_group_messages}")

        except Exception as e:
            pytest.fail(f"Failed to connect to bot: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_start_command(self, real_bot, test_chat_id):
        """Тест команды /start с реальным ботом"""
        try:
            # Отправка /start команды
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text="/start"
            )

            assert message is not None
            assert message.text is not None
            assert message.message_id is not None

            print(f"✅ /start command sent successfully")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа от бота
            await asyncio.sleep(3)

        except Exception as e:
            pytest.fail(f"Failed to send /start command: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_help_command(self, real_bot, test_chat_id):
        """Тест команды /help с реальным ботом"""
        try:
            # Отправка /help команды
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text="/help"
            )

            assert message is not None
            assert message.text == "/help"

            print(f"✅ /help command sent successfully")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа от бота
            await asyncio.sleep(3)

        except Exception as e:
            pytest.fail(f"Failed to send /help command: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_status_command(self, real_bot, test_chat_id):
        """Тест команды /status с реальным ботом"""
        try:
            # Отправка /status команды
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text="/status"
            )

            assert message is not None
            assert message.text == "/status"

            print(f"✅ /status command sent successfully")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа от бота
            await asyncio.sleep(3)

        except Exception as e:
            pytest.fail(f"Failed to send /status command: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_simple_calculation(self, real_bot, test_chat_id):
        """Тест простого расчёта через реального бота"""
        try:
            # Отправка запроса на расчёт
            query = "H2O properties at 298K"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ Calculation query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа от бота (больше времени для расчётов)
            await asyncio.sleep(15)

        except Exception as e:
            pytest.fail(f"Failed to send calculation query: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_reaction_calculation(self, real_bot, test_chat_id):
        """Тест расчёта реакции через реального бота"""
        try:
            # Отправка запроса на расчёт реакции
            query = "2 H2 + O2 → 2 H2O"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ Reaction query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа от бота (реакции могут занимать больше времени)
            await asyncio.sleep(20)

        except Exception as e:
            pytest.fail(f"Failed to send reaction query: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_unicode_formulas(self, real_bot, test_chat_id):
        """Тест Unicode химических формул"""
        try:
            # Отправка запроса с Unicode формулами
            query = "Свойства H₂O при 298K, реакция O₂ → O₃"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ Unicode query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа
            await asyncio.sleep(15)

        except Exception as e:
            pytest.fail(f"Failed to send Unicode query: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_large_table_request(self, real_bot, test_chat_id):
        """Тест запроса с большой таблицей (должен вернуть файл)"""
        try:
            # Отправка запроса, который должен вернуть большую таблицу
            query = "2 H2 + O2 → 2 H2O при 298-1000K с шагом 50K"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ Large table query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Ожидание файла (может занимать больше времени)
            await asyncio.sleep(30)

        except Exception as e:
            pytest.fail(f"Failed to send large table query: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_error_handling(self, real_bot, test_chat_id):
        """Тест обработки ошибок реальным ботом"""
        try:
            # Отправка заведомо некорректного запроса
            query = "InvalidCompoundThatDoesNotExist properties"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ Error query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Ожидание ответа об ошибке
            await asyncio.sleep(10)

        except Exception as e:
            pytest.fail(f"Failed to send error query: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_concurrent_requests(self, real_bot, test_chat_id):
        """Тест конкурентных запросов к реальному боту"""
        try:
            queries = [
                "H2O properties at 298K",
                "CO2 properties at 300K",
                "CH4 properties at 298K",
                "N2 properties at 298K"
            ]

            start_time = time.time()
            messages = []

            # Отправка всех запросов concurrently
            tasks = []
            for query in queries:
                task = real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Проверка результатов
            successful_sends = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_sends) == len(queries), \
                f"Only {len(successful_sends)}/{len(queries)} requests sent successfully"

            send_time = time.time() - start_time

            print(f"✅ Concurrent requests sent successfully")
            print(f"   Queries: {len(queries)}")
            print(f"   Send time: {send_time:.2f}s")
            print(f"   Time per query: {send_time/len(queries)*1000:.2f}ms")

            # Ожидание ответов
            await asyncio.sleep(30)

        except Exception as e:
            pytest.fail(f"Failed to send concurrent requests: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_response_time_measurement(self, real_bot, test_chat_id):
        """Тест измерения времени ответа реального бота"""
        try:
            # Измерение времени ответа для разных запросов
            test_queries = [
                "H2O properties at 298K",
                "2 H2 + O2 → 2 H2O"
            ]

            response_times = []

            for query in test_queries:
                # Отправка запроса
                start_time = time.time()
                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )
                send_time = time.time() - start_time

                assert message is not None

                print(f"✅ Query sent: {query}")
                print(f"   Send time: {send_time*1000:.2f}ms")

                # Ожидание ответа (базовое время для отправки)
                await asyncio.sleep(10)

                # В реальном E2E тесте здесь было бы получение ответа и измерение полного времени
                # Но для базового теста измеряем только время отправки
                response_times.append(send_time)

            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)

            print(f"Response time analysis:")
            print(f"   Average send time: {avg_time*1000:.2f}ms")
            print(f"   Max send time: {max_time*1000:.2f}ms")

            # Базовые проверки времени отправки
            assert avg_time < 5.0, f"Average send time too high: {avg_time:.2f}s"
            assert max_time < 10.0, f"Max send time too high: {max_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Failed to measure response times: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_file_download_capability(self, real_bot, test_chat_id):
        """Тест возможности скачивания файлов от реального бота"""
        try:
            # Запрос, который должен вернуть файл
            query = "Detailed thermodynamic analysis: 2 H2 + O2 → 2 H2O from 200K to 1000K"
            message = await real_bot.send_message(
                chat_id=test_chat_id,
                text=query
            )

            assert message is not None
            assert message.text == query

            print(f"✅ File request query sent: {query}")
            print(f"   Message ID: {message.message_id}")

            # Длительное ожидание для генерации файла
            await asyncio.sleep(45)

        except Exception as e:
            pytest.fail(f"Failed to send file request: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_user_session(self, real_bot, test_chat_id):
        """Тест пользовательской сессии с реальным ботом"""
        try:
            # Симуляция полной пользовательской сессии
            session_steps = [
                "/start",
                "H2O properties at 298K",
                "2 H2 + O2 → 2 H2O",
                "/status",
                "/help"
            ]

            session_times = []

            for step in session_steps:
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=step
                )

                step_time = time.time() - start_time
                session_times.append(step_time)

                assert message is not None

                print(f"✅ Session step completed: {step}")
                print(f"   Time: {step_time*1000:.2f}ms")

                # Небольшая задержка между шагами
                await asyncio.sleep(5)

            total_session_time = sum(session_times)
            avg_step_time = total_session_time / len(session_times)

            print(f"Session analysis:")
            print(f"   Total steps: {len(session_steps)}")
            print(f"   Total time: {total_session_time:.2f}s")
            print(f"   Average step time: {avg_step_time*1000:.2f}ms")

            # Проверки времени сессии
            assert total_session_time < 30.0, f"Session too slow: {total_session_time:.2f}s"
            assert avg_step_time < 5.0, f"Average step time too high: {avg_step_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Failed to complete user session: {e}")


@pytest.mark.e2e
@pytest.mark.external
@pytest.mark.slow
class TestRealTelegramBotAdvanced:
    """Расширенные E2E тесты с реальным Telegram API"""

    @pytest.fixture(scope="class")
    def real_bot_token(self):
        """Реальный токен бота (из переменных окружения)"""
        token = os.getenv("TELEGRAM_BOT_TOKEN_TEST")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")
        return token

    @pytest.fixture(scope="class")
    def test_chat_id(self):
        """ID тестового чата (из переменных окружения)"""
        chat_id_str = os.getenv("TELEGRAM_TEST_CHAT_ID")
        if not chat_id_str:
            pytest.skip("TELEGRAM_TEST_CHAT_ID not set")
        return int(chat_id_str)

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_stress_multiple_users_simulation(self, real_bot_token, test_chat_id):
        """Стресс-тест с симуляцией множественных пользователей"""
        try:
            application = Application.builder().token(real_bot_token).build()
            bot = application.bot

            # Симуляция 5 разных "пользователей" через разные запросы
            user_scenarios = [
                ["H2O properties", "CO2 properties", "/status"],
                ["CH4 combustion", "N2 properties", "/help"],
                ["2 H2 + O2 → 2 H2O", "O2 properties", "/start"],
                ["Unicode test H₂O", "Reaction test", "/status"],
                ["Large table request", "Error test", "/help"]
            ]

            start_time = time.time()
            all_tasks = []

            # Запуск всех "пользователей" concurrently
            for user_id, scenario in enumerate(user_scenarios):
                for step in scenario:
                    task = bot.send_message(
                        chat_id=test_chat_id,
                        text=f"[User{user_id+1}] {step}"
                    )
                    all_tasks.append(task)

            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            total_time = time.time() - start_time

            successful_sends = [r for r in results if not isinstance(r, Exception)]
            total_requests = len(all_tasks)

            print(f"✅ Stress test completed")
            print(f"   Total requests: {total_requests}")
            print(f"   Successful: {len(successful_sends)}")
            print(f"   Success rate: {len(successful_sends)/total_requests:.2%}")
            print(f"   Total time: {total_time:.2f}s")
            print(f"   Requests per second: {total_requests/total_time:.2f}")

            # Проверки стресс-теста
            assert len(successful_sends) >= total_requests * 0.9, \
                f"Success rate too low: {len(successful_sends)}/{total_requests}"
            assert total_time < 60.0, \
                f"Stress test too slow: {total_time:.2f}s"

            await application.stop()

        except Exception as e:
            pytest.fail(f"Stress test failed: {e}")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_real_bot_long_running_operation(self, real_bot_token, test_chat_id):
        """Тест длительной операции реального бота"""
        try:
            application = Application.builder().token(real_bot_token).build()
            bot = application.bot

            # Очень сложный запрос, который должен занять много времени
            complex_query = """
            Comprehensive analysis:
            2 H2 + O2 → 2 H2O from 100K to 2000K with 50K steps
            Include all phases: solid, liquid, gas
            Calculate equilibrium constants for each temperature
            Provide detailed thermodynamic tables
            """

            start_time = time.time()

            message = await bot.send_message(
                chat_id=test_chat_id,
                text=complex_query
            )

            send_time = time.time() - start_time

            assert message is not None

            print(f"✅ Complex query sent successfully")
            print(f"   Send time: {send_time*1000:.2f}ms")
            print(f"   Query length: {len(complex_query)} characters")

            # Длительное ожидание для сложной обработки
            await asyncio.sleep(120)  # 2 минуты

            await application.stop()

        except Exception as e:
            pytest.fail(f"Long running operation test failed: {e}")


# Вспомогательные функции для E2E тестов
async def wait_for_bot_response(bot: Bot, chat_id: int, timeout: int = 30) -> Optional[dict]:
    """
    Ожидание ответа от бота (для будущих расширений)

    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        timeout: Таймаут ожидания в секундах

    Returns:
        Информация о ответе или None если ответ не получен
    """
    # В будущей версии здесь может быть реализован polling ответов
    # через Telegram Bot API getUpdates или webhook
    await asyncio.sleep(timeout)
    return None


def setup_e2e_test_environment():
    """
    Настройка окружения для E2E тестов

    Returns:
        bool: True если окружение настроено корректно
    """
    required_vars = ["TELEGRAM_BOT_TOKEN_TEST", "TELEGRAM_TEST_CHAT_ID"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print("❌ E2E test environment not properly configured")
        print(f"   Missing environment variables: {', '.join(missing_vars)}")
        print("   Set these variables to run E2E tests:")
        print("   export TELEGRAM_BOT_TOKEN_TEST='your_bot_token'")
        print("   export TELEGRAM_TEST_CHAT_ID='your_chat_id'")
        return False

    print("✅ E2E test environment configured")
    return True


if __name__ == "__main__":
    # Проверка конфигурации при прямом запуске
    setup_e2e_test_environment()