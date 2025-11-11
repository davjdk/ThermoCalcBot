"""
Менеджер сессий и rate limiting для Telegram бота.

Основные классы:
- SessionManager: Управление сессиями пользователей
- RateLimiter: Ограничение частоты запросов
- UserActivityTracker: Отслеживание активности
"""

import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set

from .models import UserSession


class RateLimiter:
    """Rate limiter для ограничения частоты запросов."""

    def __init__(self, requests_per_minute: int = 30):
        self.requests_per_minute = requests_per_minute
        self.user_requests: Dict[int, deque] = defaultdict(lambda: deque())
        self.cleanup_task: Optional[asyncio.Task] = None

    async def start_cleanup_task(self):
        """Запустить фоновую задачу очистки старых запросов."""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_old_requests())

    async def stop_cleanup_task(self):
        """Остановить фоновую задачу."""
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            self.cleanup_task = None

    async def _cleanup_old_requests(self):
        """Фоновая очистка старых запросов."""
        while True:
            try:
                await asyncio.sleep(60)  # Очистка каждую минуту
                current_time = time.time()
                cutoff_time = current_time - 60  # 1 минута назад

                for user_id, requests in list(self.user_requests.items()):
                    # Удаляем старые запросы
                    while requests and requests[0] < cutoff_time:
                        requests.popleft()

                    # Удаляем пустые слоты
                    if not requests:
                        del self.user_requests[user_id]

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ошибка в cleanup task: {e}")

    def can_make_request(self, user_id: int) -> bool:
        """Проверить, может ли пользователь сделать запрос."""
        current_time = time.time()
        cutoff_time = current_time - 60  # 1 минута назад

        # Удаляем старые запросы
        while (self.user_requests[user_id] and
               self.user_requests[user_id][0] < cutoff_time):
            self.user_requests[user_id].popleft()

        # Проверяем лимит
        return len(self.user_requests[user_id]) < self.requests_per_minute

    def record_request(self, user_id: int):
        """Зарегистрировать запрос пользователя."""
        self.user_requests[user_id].append(time.time())

    def get_remaining_requests(self, user_id: int) -> int:
        """Получить количество оставшихся запросов."""
        current_time = time.time()
        cutoff_time = current_time - 60

        # Удаляем старые запросы
        while (self.user_requests[user_id] and
               self.user_requests[user_id][0] < cutoff_time):
            self.user_requests[user_id].popleft()

        return max(0, self.requests_per_minute - len(self.user_requests[user_id]))

    def get_reset_time(self, user_id: int) -> Optional[datetime]:
        """Получить время сброса лимита."""
        if not self.user_requests[user_id]:
            return None

        oldest_request = self.user_requests[user_id][0]
        reset_timestamp = oldest_request + 60
        return datetime.fromtimestamp(reset_timestamp)


class SessionManager:
    """Менеджер сессий пользователей."""

    def __init__(self, max_concurrent_users: int = 20):
        self.max_concurrent_users = max_concurrent_users
        self.sessions: Dict[int, UserSession] = {}
        self.rate_limiter = RateLimiter()
        self.cleanup_task: Optional[asyncio.Task] = None

    async def start(self):
        """Запустить менеджер сессий."""
        await self.rate_limiter.start_cleanup_task()
        self.cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions())

    async def stop(self):
        """Остановить менеджер сессий."""
        await self.rate_limiter.stop_cleanup_task()
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        # Очистка временных файлов
        await self._cleanup_temp_files()

    async def _cleanup_inactive_sessions(self):
        """Фоновая очистка неактивных сессий."""
        while True:
            try:
                await asyncio.sleep(300)  # Проверка каждые 5 минут
                current_time = datetime.now()
                inactive_threshold = timedelta(hours=24)  # 24 часа

                inactive_users = []
                for user_id, session in self.sessions.items():
                    if current_time - session.last_activity > inactive_threshold:
                        inactive_users.append(user_id)

                for user_id in inactive_users:
                    await self.remove_session(user_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ошибка в cleanup inactive sessions: {e}")

    async def _cleanup_temp_files(self):
        """Очистка временных файлов всех сессий."""
        for session in self.sessions.values():
            for file_path in session.temp_files:
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception as e:
                    print(f"Ошибка удаления временного файла {file_path}: {e}")

    def get_or_create_session(self, user_id: int, username: Optional[str] = None,
                            first_name: Optional[str] = None,
                            last_name: Optional[str] = None) -> UserSession:
        """Получить или создать сессию пользователя."""
        if user_id not in self.sessions:
            if len(self.sessions) >= self.max_concurrent_users:
                # Удаляем самую старую неактивную сессию
                oldest_user = min(
                    self.sessions.items(),
                    key=lambda x: x[1].last_activity
                )[0]
                self.sessions.pop(oldest_user)

            self.sessions[user_id] = UserSession(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )

        session = self.sessions[user_id]
        session.update_activity()
        return session

    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Получить сессию пользователя."""
        return self.sessions.get(user_id)

    async def remove_session(self, user_id: int):
        """Удалить сессию пользователя."""
        if user_id in self.sessions:
            session = self.sessions[user_id]

            # Очистка временных файлов
            for file_path in session.temp_files:
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception as e:
                    print(f"Ошибка удаления временного файла {file_path}: {e}")

            del self.sessions[user_id]

    def get_active_session_count(self) -> int:
        """Получить количество активных сессий."""
        current_time = datetime.now()
        active_threshold = timedelta(minutes=30)

        return sum(
            1 for session in self.sessions.values()
            if current_time - session.last_activity < active_threshold
        )

    def get_total_session_count(self) -> int:
        """Получить общее количество сессий."""
        return len(self.sessions)

    def get_processing_users(self) -> Set[int]:
        """Получить множество пользователей, выполняющих запросы."""
        return {
            user_id for user_id, session in self.sessions.items()
            if session.current_query is not None
        }

    def get_system_stats(self) -> Dict[str, any]:
        """Получить статистику системы."""
        current_time = datetime.now()
        active_threshold = timedelta(minutes=30)

        active_sessions = [
            session for session in self.sessions.values()
            if current_time - session.last_activity < active_threshold
        ]

        processing_sessions = [
            session for session in self.sessions.values()
            if session.current_query is not None
        ]

        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "processing_sessions": len(processing_sessions),
            "max_concurrent_users": self.max_concurrent_users,
            "rate_limit_per_minute": self.rate_limiter.requests_per_minute,
            "memory_usage_mb": self._estimate_memory_usage()
        }

    def _estimate_memory_usage(self) -> float:
        """Оценить использование памяти в МБ."""
        # Приблизительная оценка использования памяти
        base_memory = 50  # Базовое использование памяти
        session_memory = len(self.sessions) * 0.5  # ~0.5 МБ на сессию
        return base_memory + session_memory

    def is_user_processing(self, user_id: int) -> bool:
        """Проверить, обрабатывается ли запрос пользователя."""
        session = self.get_session(user_id)
        return session is not None and session.current_query is not None

    def can_user_make_request(self, user_id: int) -> tuple[bool, str]:
        """Проверить, может ли пользователь сделать запрос."""
        # Проверка rate limiting
        if not self.rate_limiter.can_make_request(user_id):
            reset_time = self.rate_limiter.get_reset_time(user_id)
            remaining_requests = self.rate_limiter.get_remaining_requests(user_id)

            if reset_time:
                time_until_reset = reset_time.strftime("%H:%M:%S")
                message = (
                    f"⏳ *Лимит запросов исчерпан*\n\n"
                    f"Осталось запросов: {remaining_requests}/{self.rate_limiter.requests_per_minute}\n"
                    f"Сброс через: {time_until_reset}"
                )
            else:
                message = "⏳ *Лимит запросов исчерпан*\n\nПопробуйте через минуту."

            return False, message

        # Проверка, не обрабатывается ли уже запрос
        if self.is_user_processing(user_id):
            return False, "⏳ *Ваш предыдущий запрос ещё обрабатывается*\n\nПодождите завершения."

        # Проверка максимального количества одновременных пользователей
        if user_id not in self.sessions and len(self.sessions) >= self.max_concurrent_users:
            return (
                False,
                f"🚫 *Система перегружена*\n\n"
                f"Максимум одновременных пользователей: {self.max_concurrent_users}\n"
                f"Попробуйте позже."
            )

        return True, ""