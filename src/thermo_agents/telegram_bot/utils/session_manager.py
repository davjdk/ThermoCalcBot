"""
Управление сессиями пользователей Telegram бота.

Отслеживание активных пользователей, лимиты и статистика.
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Set, Optional
from dataclasses import dataclass, field

from ..config import TelegramBotConfig


@dataclass
class UserSession:
    """Информация о сессии пользователя."""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    start_time: float
    last_activity: float
    request_count: int = 0
    is_active: bool = True


@dataclass
class SessionStats:
    """Статистика сессий."""
    total_users_today: int = 0
    active_users: int = 0
    total_requests_today: int = 0
    average_session_time: float = 0.0
    peak_concurrent_users: int = 0


class SessionManager:
    """Менеджер сессий пользователей."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.sessions: Dict[int, UserSession] = {}
        self.active_users: Set[int] = set()
        self.stats = SessionStats()
        self._session_timeout = 3600  # 1 час таймаут сессии
        self._cleanup_task = None

    async def start_session(self, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> bool:
        """
        Начало сессии пользователя.

        Args:
            user_id: ID пользователя Telegram
            username: Username пользователя
            first_name: Имя пользователя

        Returns:
            True если сессия успешно создана
        """
        try:
            current_time = time.time()

            # Проверка лимита активных пользователей
            if len(self.active_users) >= self.config.max_concurrent_users:
                if user_id not in self.active_users:
                    return False

            # Создание или обновление сессии
            if user_id in self.sessions:
                session = self.sessions[user_id]
                session.last_activity = current_time
                session.is_active = True
            else:
                session = UserSession(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    start_time=current_time,
                    last_activity=current_time
                )
                self.sessions[user_id] = session
                self.stats.total_users_today += 1

            # Добавление в активные пользователи
            self.active_users.add(user_id)
            self.stats.active_users = len(self.active_users)
            self.stats.peak_concurrent_users = max(self.stats.peak_concurrent_users, self.stats.active_users)

            # Запуск задачи очистки если нужно
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions())

            return True

        except Exception as e:
            print(f"Ошибка создания сессии: {e}")
            return False

    async def end_session(self, user_id: int) -> None:
        """
        Завершение сессии пользователя.

        Args:
            user_id: ID пользователя
        """
        try:
            if user_id in self.sessions:
                session = self.sessions[user_id]
                session.is_active = False
                session.last_activity = time.time()

            self.active_users.discard(user_id)
            self.stats.active_users = len(self.active_users)

        except Exception as e:
            print(f"Ошибка завершения сессии: {e}")

    async def update_activity(self, user_id: int) -> None:
        """
        Обновление активности пользователя.

        Args:
            user_id: ID пользователя
        """
        try:
            current_time = time.time()

            if user_id in self.sessions:
                session = self.sessions[user_id]
                session.last_activity = current_time
                session.request_count += 1
                self.stats.total_requests_today += 1

                # Повторное добавление в активные если нужно
                self.active_users.add(user_id)
                self.stats.active_users = len(self.active_users)

        except Exception as e:
            print(f"Ошибка обновления активности: {e}")

    def is_user_active(self, user_id: int) -> bool:
        """Проверка, активен ли пользователь."""
        return user_id in self.active_users

    def get_session_info(self, user_id: int) -> Optional[UserSession]:
        """Получение информации о сессии пользователя."""
        return self.sessions.get(user_id)

    def get_active_users_count(self) -> int:
        """Получение количества активных пользователей."""
        return len(self.active_users)

    def can_accept_new_user(self) -> bool:
        """Проверка, может ли система принять нового пользователя."""
        return len(self.active_users) < self.config.max_concurrent_users

    def get_user_statistics(self) -> dict:
        """Получение статистики пользователей."""
        current_time = time.time()
        total_session_time = 0
        active_sessions = 0

        for session in self.sessions.values():
            if session.is_active:
                active_sessions += 1
                total_session_time += (current_time - session.start_time)

        avg_session_time = total_session_time / active_sessions if active_sessions > 0 else 0

        return {
            "total_users": len(self.sessions),
            "active_users": len(self.active_users),
            "total_requests_today": self.stats.total_requests_today,
            "average_session_time_minutes": avg_session_time / 60,
            "peak_concurrent_users": self.stats.peak_concurrent_users,
            "max_concurrent_users": self.config.max_concurrent_users,
            "utilization_percent": (len(self.active_users) / self.config.max_concurrent_users) * 100
        }

    def get_user_requests_today(self, user_id: int) -> int:
        """Получение количества запросов пользователя за сегодня."""
        session = self.sessions.get(user_id)
        return session.request_count if session else 0

    async def _cleanup_inactive_sessions(self) -> None:
        """Фоновая задача очистки неактивных сессий."""
        while True:
            try:
                await asyncio.sleep(300)  # Проверка каждые 5 минут
                await self._remove_inactive_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ошибка очистки сессий: {e}")

    async def _remove_inactive_sessions(self) -> None:
        """Удаление неактивных сессий."""
        try:
            current_time = time.time()
            inactive_users = []

            for user_id, session in self.sessions.items():
                if current_time - session.last_activity > self._session_timeout:
                    inactive_users.append(user_id)

            for user_id in inactive_users:
                await self.end_session(user_id)

            # Сброс ежедневной статистики в полночь
            now = datetime.now()
            if now.hour == 0 and now.minute < 5:  # Первые 5 минут часа
                self._reset_daily_stats()

        except Exception as e:
            print(f"Ошибка удаления неактивных сессий: {e}")

    def _reset_daily_stats(self) -> None:
        """Сброс ежедневной статистики."""
        self.stats.total_users_today = 0
        self.stats.total_requests_today = 0

    async def shutdown(self) -> None:
        """Корректное завершение работы менеджера сессий."""
        try:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            # Завершение всех активных сессий
            for user_id in list(self.active_users):
                await self.end_session(user_id)

        except Exception as e:
            print(f"Ошибка завершения работы SessionManager: {e}")

    def get_top_users(self, limit: int = 10) -> list[dict]:
        """Получение топ пользователей по количеству запросов."""
        users = []
        for session in self.sessions.values():
            users.append({
                "user_id": session.user_id,
                "username": session.username,
                "first_name": session.first_name,
                "request_count": session.request_count,
                "session_time_minutes": (time.time() - session.start_time) / 60,
                "is_active": session.is_active
            })

        # Сортировка по количеству запросов
        users.sort(key=lambda x: x["request_count"], reverse=True)
        return users[:limit]