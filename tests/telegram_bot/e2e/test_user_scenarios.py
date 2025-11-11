"""
E2E тесты реальных пользовательских сценариев

Эти тесты симулируют реальные сценарии использования бота
и проверяют полный пользовательский опыт.
"""

import pytest
import asyncio
import os
import time
from typing import List, Dict, Any
from telegram import Bot
from telegram.ext import Application

from tests.telegram_bot.fixtures.test_data import (
    TEST_COMPOUNDS, TEST_REACTIONS, TEST_QUERIES
)


@pytest.mark.e2e
@pytest.mark.external
class TestUserScenarios:
    """Тесты реальных пользовательских сценариев"""

    @pytest.fixture(scope="class")
    def real_bot_token(self):
        """Реальный токен бота"""
        token = os.getenv("TELEGRAM_BOT_TOKEN_TEST")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")
        return token

    @pytest.fixture(scope="class")
    def test_chat_id(self):
        """ID тестового чата"""
        chat_id_str = os.getenv("TELEGRAM_TEST_CHAT_ID")
        if not chat_id_str:
            pytest.skip("TELEGRAM_TEST_CHAT_ID not set")
        return int(chat_id_str)

    @pytest.fixture(scope="class")
    async def real_bot(self, real_bot_token):
        """Создание реального бота"""
        application = Application.builder().token(real_bot_token).build()
        bot = application.bot
        yield bot
        await application.stop()

    @pytest.mark.asyncio
    async def test_researcher_basic_workflow(self, real_bot, test_chat_id):
        """Сценарий: Исследователь выполняет базовые расчёты"""
        try:
            print("🔬 Starting researcher basic workflow scenario...")

            workflow_steps = [
                ("/start", "Welcome and introduction", 5),
                ("H2O properties at 298.15 K", "Water properties calculation", 20),
                ("CO2 properties at 298 K", "Carbon dioxide properties", 20),
                ("2 H2 + O2 → 2 H2O", "Combustion reaction calculation", 30),
                ("/status", "Check system status", 10),
                ("/help", "Get help information", 5)
            ]

            session_results = []

            for step, description, wait_time in workflow_steps:
                print(f"   Executing: {description}")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=step
                )

                step_time = time.time() - start_time

                assert message is not None, f"Failed to send: {step}"

                session_results.append({
                    "step": step,
                    "description": description,
                    "time": step_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Completed in {step_time*1000:.2f}ms")
                await asyncio.sleep(wait_time)

            # Анализ сессии
            total_time = sum(r["time"] for r in session_results)
            avg_step_time = total_time / len(session_results)

            print(f"📊 Researcher workflow completed:")
            print(f"   Total steps: {len(session_results)}")
            print(f"   Total time: {total_time:.2f}s")
            print(f"   Average step time: {avg_step_time*1000:.2f}ms")

            # Проверки
            assert len(session_results) == len(workflow_steps), "Not all steps completed"
            assert total_time < 120, f"Workflow too slow: {total_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Researcher workflow failed: {e}")

    @pytest.mark.asyncio
    async def test_student_homework_scenario(self, real_bot, test_chat_id):
        """Сценарий: Студент выполняет домашнее задание по термодинамике"""
        try:
            print("📚 Starting student homework scenario...")

            homework_queries = [
                "What is the enthalpy of formation of water at 298K?",
                "Calculate ΔG for reaction: CH4 + 2 O2 → CO2 + 2 H2O at 298K",
                "Properties of methane gas from 200K to 400K",
                "Equilibrium constant for N2 + 3 H2 ⇌ 2 NH3 at different temperatures",
                "/examples",
                "Help with chemical thermodynamics calculations"
            ]

            homework_results = []

            for i, query in enumerate(homework_queries, 1):
                print(f"   Question {i}: {query[:50]}...")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )

                query_time = time.time() - start_time

                assert message is not None, f"Failed to send homework query {i}"

                homework_results.append({
                    "question_id": i,
                    "query": query,
                    "time": query_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Sent in {query_time*1000:.2f}ms")
                await asyncio.sleep(15)  # Время на обработку сложных запросов

            # Анализ выполнения домашнего задания
            total_time = sum(r["time"] for r in homework_results)
            avg_query_time = total_time / len(homework_results)

            print(f"📓 Student homework scenario completed:")
            print(f"   Questions answered: {len(homework_results)}")
            print(f"   Total query time: {total_time:.2f}s")
            print(f"   Average query time: {avg_query_time*1000:.2f}ms")

            # Проверки
            assert len(homework_results) == len(homework_queries), "Not all questions answered"
            assert avg_query_time < 3.0, f"Query processing too slow: {avg_query_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Student homework scenario failed: {e}")

    @pytest.mark.asyncio
    async def test_engineer_optimization_scenario(self, real_bot, test_chat_id):
        """Сценарий: Инженер оптимизирует процесс"""
        try:
            print("⚙️ Starting engineer optimization scenario...")

            optimization_queries = [
                # Базовые свойства реагентов
                "H2 properties from 298K to 800K",
                "O2 properties from 298K to 800K",
                "H2O properties from 298K to 800K (liquid and gas phases)",

                # Реакция при разных условиях
                "2 H2 + O2 → 2 H2O at 298K, 500K, 700K",

                # Детальный анализ с таблицей
                "Detailed thermodynamic analysis: 2 H2 + O2 → 2 H2O from 300K to 1000K step 50K",

                # Статус системы
                "/status"
            ]

            optimization_results = []
            calculation_start_time = time.time()

            for i, query in enumerate(optimization_queries, 1):
                print(f"   Step {i}: {query[:60]}...")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )

                step_time = time.time() - start_time

                assert message is not None, f"Failed to send optimization query {i}"

                optimization_results.append({
                    "step_id": i,
                    "query": query,
                    "time": step_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Sent in {step_time*1000:.2f}ms")

                # Разное время ожидания для разных типов запросов
                if "detailed" in query.lower() or "analysis" in query.lower():
                    await asyncio.sleep(60)  # Детальные расчёты требуют больше времени
                else:
                    await asyncio.sleep(20)

            total_optimization_time = time.time() - calculation_start_time

            print(f"🔧 Engineer optimization scenario completed:")
            print(f"   Optimization steps: {len(optimization_results)}")
            print(f"   Total optimization time: {total_optimization_time:.2f}s")
            print(f"   Communication time: {sum(r['time'] for r in optimization_results):.2f}s")

            # Проверки
            assert len(optimization_results) == len(optimization_queries)
            assert total_optimization_time < 300, f"Optimization process too slow: {total_optimization_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Engineer optimization scenario failed: {e}")

    @pytest.mark.asyncio
    async def test_teacher_lecture_preparation(self, real_bot, test_chat_id):
        """Сценарий: Преподаватель готовит материалы для лекции"""
        try:
            print("👨‍🏫 Starting teacher lecture preparation scenario...")

            lecture_topics = [
                # Основные концепции
                "Water thermodynamic properties for teaching demonstration",
                "Carbon dioxide phase transitions with temperature table",

                # Химические реакции для демонстрации
                "Combustion reactions: H2 + 1/2 O2 → H2O, CH4 + 2 O2 → CO2 + 2 H2O",

                # Сравнительный анализ
                "Compare H2O and CO2 properties across different temperatures",

                # Большая таблица для раздаточных материалов
                "Comprehensive thermodynamic data table: H2, O2, N2, CO2, CH4 from 200K to 1000K"
            ]

            lecture_results = []
            preparation_start_time = time.time()

            for i, topic in enumerate(lecture_topics, 1):
                print(f"   Lecture material {i}: {topic[:50]}...")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=topic
                )

                material_time = time.time() - start_time

                assert message is not None, f"Failed to prepare lecture material {i}"

                lecture_results.append({
                    "material_id": i,
                    "topic": topic,
                    "time": material_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Prepared in {material_time*1000:.2f}ms")

                # Большое время ожидания для комплексных таблиц
                if "comprehensive" in topic.lower() or "table" in topic.lower():
                    await asyncio.sleep(90)
                else:
                    await asyncio.sleep(25)

            total_preparation_time = time.time() - preparation_start_time

            print(f"📝 Teacher lecture preparation completed:")
            print(f"   Lecture materials: {len(lecture_results)}")
            print(f"   Total preparation time: {total_preparation_time:.2f}s")
            print(f"   Average material time: {total_preparation_time/len(lecture_results):.2f}s")

            # Проверки
            assert len(lecture_results) == len(lecture_topics)
            assert total_preparation_time < 400, f"Lecture preparation too slow: {total_preparation_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Teacher lecture preparation failed: {e}")

    @pytest.mark.asyncio
    async def test_explorer_discovery_scenario(self, real_bot, test_chat_id):
        """Сценарий: Исследователь изучает новые соединения"""
        try:
            print("🔍 Starting explorer discovery scenario...")

            discovery_queries = [
                # Начало исследования
                "/start",
                "What compounds can you analyze?",

                # Известные соединения
                "Ammonia NH3 properties at standard conditions",
                "Properties of sulfur hexafluoride SF6",

                # Менее известные соединения
                "Properties of nitrous oxide N2O",
                "Xenon hexafluoroplatinate K2[PtF6] properties",

                # Сложные реакции
                "Catalytic reaction: N2 + 3 H2 ⇌ 2 NH3 with temperature effects",

                # Обратная связь
                "/status"
            ]

            discovery_results = []
            discovery_start_time = time.time()

            for i, query in enumerate(discovery_queries, 1):
                print(f"   Discovery step {i}: {query[:45]}...")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )

                discovery_time = time.time() - start_time

                assert message is not None, f"Failed to send discovery query {i}"

                discovery_results.append({
                    "step_id": i,
                    "query": query,
                    "time": discovery_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Explored in {discovery_time*1000:.2f}ms")

                # Время ожидания зависит от сложности запроса
                if "xenon" in query.lower() or "complex" in query.lower():
                    await asyncio.sleep(40)
                else:
                    await asyncio.sleep(15)

            total_discovery_time = time.time() - discovery_start_time

            print(f"🧪 Explorer discovery scenario completed:")
            print(f"   Discovery steps: {len(discovery_results)}")
            print(f"   Total discovery time: {total_discovery_time:.2f}s")
            print(f"   Average step time: {total_discovery_time/len(discovery_results):.2f}s")

            # Проверки
            assert len(discovery_results) == len(discovery_queries)
            assert total_discovery_time < 250, f"Discovery process too slow: {total_discovery_time:.2f}s"

        except Exception as e:
            pytest.fail(f"Explorer discovery scenario failed: {e}")

    @pytest.mark.asyncio
    async def test_error_recovery_scenario(self, real_bot, test_chat_id):
        """Сценарий: Восстановление после ошибок"""
        try:
            print("🛠️ Starting error recovery scenario...")

            error_scenarios = [
                # Корректные запросы
                ("H2O properties", "Correct query", 15),
                # Некорректные запросы
                ("InvalidCompoundThatDoesNotExist123", "Invalid compound", 10),
                ("", "Empty query", 5),
                ("A" * 5000, "Very long query", 10),
                # Восстановление с корректным запросом
                ("CO2 properties at 298K", "Recovery query", 15),
                # Команды
                ("/help", "Help command", 5),
                ("/status", "Status command", 10)
            ]

            recovery_results = []

            for query, description, wait_time in error_scenarios:
                print(f"   Testing: {description}")
                start_time = time.time()

                try:
                    message = await real_bot.send_message(
                        chat_id=test_chat_id,
                        text=query
                    )

                    step_time = time.time() - start_time

                    recovery_results.append({
                        "query": query,
                        "description": description,
                        "time": step_time,
                        "success": True,
                        "error": None
                    })

                    print(f"      ✅ Success in {step_time*1000:.2f}ms")

                except Exception as e:
                    step_time = time.time() - start_time

                    recovery_results.append({
                        "query": query,
                        "description": description,
                        "time": step_time,
                        "success": False,
                        "error": str(e)
                    })

                    print(f"      ❌ Failed: {e}")

                await asyncio.sleep(wait_time)

            # Анализ восстановления
            successful_queries = [r for r in recovery_results if r["success"]]
            failed_queries = [r for r in recovery_results if not r["success"]]

            print(f"🔧 Error recovery scenario completed:")
            print(f"   Total queries: {len(recovery_results)}")
            print(f"   Successful: {len(successful_queries)}")
            print(f"   Failed: {len(failed_queries)}")
            print(f"   Success rate: {len(successful_queries)/len(recovery_results):.2%}")

            # Проверки
            assert len(successful_queries) >= len(recovery_results) * 0.7, \
                f"Success rate too low: {len(successful_queries)}/{len(recovery_results)}"

        except Exception as e:
            pytest.fail(f"Error recovery scenario failed: {e}")

    @pytest.mark.asyncio
    async def test_multilingual_support_scenario(self, real_bot, test_chat_id):
        """Сценарий: Проверка многоязычной поддержки"""
        try:
            print("🌍 Starting multilingual support scenario...")

            multilingual_queries = [
                # Английские запросы
                ("Water properties at 298K", "English query", 15),
                ("Calculate Gibbs free energy for CH4 combustion", "English complex query", 25),

                # Русские запросы
                ("Свойства воды при 298К", "Russian query", 15),
                ("Рассчитать энергию Гиббса для горения метана", "Russian complex query", 25),

                # Смешанные запросы
                ("H2O свойства at 298K", "Mixed language query", 20),
                ("Calculate ΔH для реакции: CO2 + H2O → H2CO3", "Mixed complex query", 30),

                # Unicode формулы
                ("Свойства H₂O и CO₂ при 298K", "Unicode formulas", 20)
            ]

            multilingual_results = []

            for query, description, wait_time in multilingual_queries:
                print(f"   Testing: {description}")
                start_time = time.time()

                message = await real_bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )

                query_time = time.time() - start_time

                assert message is not None, f"Failed to send multilingual query: {description}"

                multilingual_results.append({
                    "query": query,
                    "description": description,
                    "time": query_time,
                    "message_id": message.message_id
                })

                print(f"      ✅ Processed in {query_time*1000:.2f}ms")
                await asyncio.sleep(wait_time)

            print(f"🌐 Multilingual support scenario completed:")
            print(f"   Languages tested: English, Russian, Mixed")
            print(f"   Total queries: {len(multilingual_results)}")
            print(f"   Average processing time: {sum(r['time'] for r in multilingual_results)/len(multilingual_results)*1000:.2f}ms")

            # Проверки
            assert len(multilingual_results) == len(multilingual_queries)
            assert all(r["time"] < 5.0 for r in multilingual_results), "Some queries too slow"

        except Exception as e:
            pytest.fail(f"Multilingual support scenario failed: {e}")


@pytest.mark.e2e
@pytest.mark.external
@pytest.mark.slow
class TestPerformanceScenarios:
    """Сценарии тестирования производительности в реальных условиях"""

    @pytest.fixture(scope="class")
    def real_bot_token(self):
        """Реальный токен бота"""
        token = os.getenv("TELEGRAM_BOT_TOKEN_TEST")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN_TEST not set")
        return token

    @pytest.fixture(scope="class")
    def test_chat_id(self):
        """ID тестового чата"""
        chat_id_str = os.getenv("TELEGRAM_TEST_CHAT_ID")
        if not chat_id_str:
            pytest.skip("TELEGRAM_TEST_CHAT_ID not set")
        return int(chat_id_str)

    @pytest.mark.asyncio
    async def test_rapid_succession_requests(self, real_bot_token, test_chat_id):
        """Тест быстрых последовательных запросов"""
        try:
            application = Application.builder().token(real_bot_token).build()
            bot = application.bot

            rapid_queries = [
                "H2O properties",
                "CO2 properties",
                "CH4 properties",
                "N2 properties",
                "O2 properties"
            ]

            print("⚡ Starting rapid succession test...")
            start_time = time.time()

            # Быстрая отправка запросов
            results = []
            for query in rapid_queries:
                query_start = time.time()
                message = await bot.send_message(
                    chat_id=test_chat_id,
                    text=query
                )
                query_time = time.time() - query_start

                results.append({
                    "query": query,
                    "time": query_time,
                    "success": message is not None
                })

            total_send_time = time.time() - start_time

            print(f"🚀 Rapid succession test completed:")
            print(f"   Queries sent: {len(results)}")
            print(f"   Total send time: {total_send_time:.3f}s")
            print(f"   Average send time: {total_send_time/len(results)*1000:.2f}ms")
            print(f"   Queries per second: {len(results)/total_send_time:.2f}")

            # Проверки
            assert all(r["success"] for r in results), "Some queries failed"
            assert total_send_time < 10.0, f"Rapid succession too slow: {total_send_time:.2f}s"

            await application.stop()

        except Exception as e:
            pytest.fail(f"Rapid succession test failed: {e}")

    @pytest.mark.asyncio
    async def test_endurance_session(self, real_bot_token, test_chat_id):
        """Тест выносливости - длительная сессия"""
        try:
            application = Application.builder().token(real_bot_token).build()
            bot = application.bot

            endurance_queries = [
                "Basic calculation",
                "H2O properties",
                "Reaction calculation",
                "2 H2 + O2 → 2 H2O",
                "Status check",
                "/status",
                "Help request",
                "/help",
                "Another calculation",
                "CO2 properties"
            ]

            print("🏃 Starting endurance session test...")
            session_start = time.time()

            session_results = []
            for i, query in enumerate(endurance_queries):
                query_start = time.time()

                message = await bot.send_message(
                    chat_id=test_chat_id,
                    text=f"[Session {i+1}/10] {query}"
                )

                query_time = time.time() - query_start
                session_results.append({
                    "step": i+1,
                    "query": query,
                    "time": query_time,
                    "success": message is not None
                })

                print(f"   Step {i+1}/10 completed in {query_time*1000:.2f}ms")

                # Небольшая задержка между шагами
                await asyncio.sleep(3)

            total_session_time = time.time() - session_start

            print(f"💪 Endurance session completed:")
            print(f"   Session steps: {len(session_results)}")
            print(f"   Total session time: {total_session_time:.2f}s")
            print(f"   Average step time: {total_session_time/len(session_results):.2f}s")

            # Проверки
            assert all(r["success"] for r in session_results), "Session had failures"
            assert total_session_time < 120, f"Endurance session too slow: {total_session_time:.2f}s"

            await application.stop()

        except Exception as e:
            pytest.fail(f"Endurance session test failed: {e}")