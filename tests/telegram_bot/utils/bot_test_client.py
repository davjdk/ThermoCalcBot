"""
Test клиент для Telegram бота
"""

import asyncio
from typing import Optional, List, Dict, Any, Callable
from unittest.mock import Mock, AsyncMock

from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_update, create_mock_command_update, create_mock_context
)
from tests.telegram_bot.utils.test_helpers import (
    assert_telegram_message_sent, assert_telegram_file_sent
)


class TelegramBotTestClient:
    """Test клиент для взаимодействия с Telegram ботом"""

    def __init__(self, bot_instance, mock_orchestrator=None, mock_session_manager=None):
        """
        Инициализация тестового клиента

        Args:
            bot_instance: Экземпляр тестируемого бота
            mock_orchestrator: Mock оркестратора (опционально)
            mock_session_manager: Mock менеджера сессий (опционально)
        """
        self.bot = bot_instance
        self.mock_orchestrator = mock_orchestrator
        self.mock_session_manager = mock_session_manager
        self.sent_messages = []
        self.sent_files = []
        self.chat_actions = []

    async def send_command(self, command: str, user_id: int = 12345, chat_id: int = 12345) -> Dict[str, Any]:
        """
        Отправка команды боту

        Args:
            command: Текст команды (например, "/start", "/help")
            user_id: ID пользователя
            chat_id: ID чата

        Returns:
            Словарь с результатом выполнения команды
        """
        update = create_mock_command_update(command, user_id, chat_id)
        context = create_mock_context()

        # Сохраняем mock объекты для проверки
        mock_message = update.message
        mock_bot = context.bot

        try:
            # Определяем обработчик команды
            if command.startswith("/start"):
                await self.bot._command_handlers.start(update, context)
            elif command.startswith("/help"):
                await self.bot._command_handlers.help(update, context)
            elif command.startswith("/calculate"):
                await self.bot._command_handlers.calculate(update, context)
            elif command.startswith("/status"):
                await self.bot._command_handlers.status(update, context)
            else:
                raise ValueError(f"Unknown command: {command}")

            # Сохраняем информацию об отправленных сообщениях
            if mock_message.reply_text.called:
                call_args = mock_message.reply_text.call_args
                self.sent_messages.append({
                    "text": call_args[0][0] if call_args[0] else "",
                    "parse_mode": call_args[1].get("parse_mode"),
                    "command": command,
                    "user_id": user_id
                })

            return {
                "success": True,
                "message_sent": mock_message.reply_text.called,
                "chat_action_sent": mock_bot.send_chat_action.called,
                "message_count": len(self.sent_messages)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message_count": len(self.sent_messages)
            }

    async def send_message(self, text: str, user_id: int = 12345, chat_id: int = 12345) -> Dict[str, Any]:
        """
        Отправка текстового сообщения боту

        Args:
            text: Текст сообщения
            user_id: ID пользователя
            chat_id: ID чата

        Returns:
            Словарь с результатом обработки сообщения
        """
        update = create_mock_update(text, user_id, chat_id)
        context = create_mock_context()

        mock_message = update.message
        mock_bot = context.bot

        try:
            # Обработка текстового сообщения
            await self.bot._message_handler.handle_text(update, context)

            # Сохраняем информацию об отправленных сообщениях и файлах
            if mock_message.reply_text.called:
                call_args = mock_message.reply_text.call_args
                self.sent_messages.append({
                    "text": call_args[0][0] if call_args[0] else "",
                    "parse_mode": call_args[1].get("parse_mode"),
                    "user_message": text,
                    "user_id": user_id
                })

            if mock_bot.send_document.called:
                call_args = mock_bot.send_document.call_args
                self.sent_files.append({
                    "filename": call_args[1].get("filename", "report.txt"),
                    "user_message": text,
                    "user_id": user_id
                })

            if mock_bot.send_chat_action.called:
                call_args = mock_bot.send_chat_action.call_args
                self.chat_actions.append({
                    "action": call_args[1].get("action", "typing"),
                    "user_message": text,
                    "user_id": user_id
                })

            return {
                "success": True,
                "message_sent": mock_message.reply_text.called,
                "file_sent": mock_bot.send_document.called,
                "chat_action_sent": mock_bot.send_chat_action.called,
                "message_count": len(self.sent_messages),
                "file_count": len(self.sent_files)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message_count": len(self.sent_messages),
                "file_count": len(self.sent_files)
            }

    async def send_multiple_commands(self, commands: List[str], user_id: int = 12345) -> List[Dict[str, Any]]:
        """
        Отправка нескольких команд последовательно

        Args:
            commands: Список команд
            user_id: ID пользователя

        Returns:
            Список результатов выполнения команд
        """
        results = []
        for command in commands:
            result = await self.send_command(command, user_id)
            results.append(result)
            # Небольшая задержка между командами
            await asyncio.sleep(0.1)

        return results

    async def send_multiple_messages(self, messages: List[str], user_id: int = 12345) -> List[Dict[str, Any]]:
        """
        Отправка нескольких сообщений последовательно

        Args:
            messages: Список сообщений
            user_id: ID пользователя

        Returns:
            Список результатов обработки сообщений
        """
        results = []
        for message in messages:
            result = await self.send_message(message, user_id)
            results.append(result)
            # Небольшая задержка между сообщениями
            await asyncio.sleep(0.1)

        return results

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Получить последнее отправленное сообщение"""
        return self.sent_messages[-1] if self.sent_messages else None

    def get_last_file(self) -> Optional[Dict[str, Any]]:
        """Получить последний отправленный файл"""
        return self.sent_files[-1] if self.sent_files else None

    def get_messages_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить сообщения от определенного пользователя"""
        return [msg for msg in self.sent_messages if msg.get("user_id") == user_id]

    def get_files_by_user(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить файлы от определенного пользователя"""
        return [file for file in self.sent_files if file.get("user_id") == user_id]

    def clear_history(self):
        """Очистить историю отправленных сообщений и файлов"""
        self.sent_messages.clear()
        self.sent_files.clear()
        self.chat_actions.clear()

    def assert_message_sent(self, expected_text: str = None, parse_mode: str = None):
        """Проверить, что было отправлено сообщение"""
        assert len(self.sent_messages) > 0, "No messages were sent"

        if expected_text:
            last_message = self.get_last_message()
            assert expected_text in last_message["text"], f"Expected '{expected_text}' in last message"

        if parse_mode:
            last_message = self.get_last_message()
            assert last_message.get("parse_mode") == parse_mode, f"Expected parse_mode '{parse_mode}'"

    def assert_file_sent(self, expected_filename: str = None):
        """Проверить, что был отправлен файл"""
        assert len(self.sent_files) > 0, "No files were sent"

        if expected_filename:
            last_file = self.get_last_file()
            assert expected_filename in last_file["filename"], f"Expected '{expected_filename}' in filename"

    def assert_chat_action_sent(self, expected_action: str = "typing"):
        """Проверить, что была отправлена chat action"""
        assert len(self.chat_actions) > 0, "No chat actions were sent"

        if expected_action:
            last_action = self.chat_actions[-1]
            assert last_action.get("action") == expected_action, f"Expected action '{expected_action}'"

    async def simulate_user_session(self, user_id: int, session_commands: List[str]) -> Dict[str, Any]:
        """
        Симуляция пользовательской сессии

        Args:
            user_id: ID пользователя
            session_commands: Команды сессии

        Returns:
            Статистика сессии
        """
        start_time = asyncio.get_event_loop().time()

        # Отправляем команду /start в начале сессии
        await self.send_command("/start", user_id)

        # Обрабатываем команды сессии
        results = []
        for command in session_commands:
            if command.startswith("/"):
                result = await self.send_command(command, user_id)
            else:
                result = await self.send_message(command, user_id)
            results.append(result)

        session_time = asyncio.get_event_loop().time() - start_time
        successful_requests = sum(1 for r in results if r.get("success", False))

        return {
            "user_id": user_id,
            "session_time": session_time,
            "total_requests": len(results),
            "successful_requests": successful_requests,
            "success_rate": successful_requests / len(results) if results else 0,
            "messages_sent": len(self.get_messages_by_user(user_id)),
            "files_sent": len(self.get_files_by_user(user_id))
        }


class ConcurrentTestRunner:
    """Запускertest для конкурентного тестирования"""

    def __init__(self, bot_client_factory: Callable):
        """
        Инициализация

        Args:
            bot_client_factory: Фабрика для создания клиентов бота
        """
        self.bot_client_factory = bot_client_factory

    async def run_concurrent_users(self, user_scenarios: Dict[int, List[str]], max_concurrent: int = 10) -> Dict[str, Any]:
        """
        Запуск теста с конкурентными пользователями

        Args:
            user_scenarios: Сценарии для каждого пользователя {user_id: [commands/messages]}
            max_concurrent: Максимальное количество одновременных пользователей

        Returns:
            Статистика теста
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_user_scenario(user_id: int, scenario: List[str]):
            async with semaphore:
                bot_client = self.bot_client_factory()
                return await bot_client.simulate_user_session(user_id, scenario)

        tasks = [
            run_user_scenario(user_id, scenario)
            for user_id, scenario in user_scenarios.items()
        ]

        session_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Обработка результатов
        successful_sessions = [r for r in session_results if isinstance(r, dict)]
        failed_sessions = [r for r in session_results if isinstance(r, Exception)]

        total_requests = sum(s["total_requests"] for s in successful_sessions)
        successful_requests = sum(s["successful_requests"] for s in successful_sessions)

        return {
            "total_users": len(user_scenarios),
            "successful_sessions": len(successful_sessions),
            "failed_sessions": len(failed_sessions),
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "overall_success_rate": successful_requests / total_requests if total_requests > 0 else 0,
            "average_session_time": sum(s["session_time"] for s in successful_sessions) / len(successful_sessions) if successful_sessions else 0,
            "errors": [str(e) for e in failed_sessions]
        }