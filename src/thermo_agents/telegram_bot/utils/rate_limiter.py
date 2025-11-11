"""
Управление лимитами запросов (Rate Limiting) для Telegram бота.

Защита от спама и превышения лимитов Telegram API.
"""

import time
import asyncio
from collections import defaultdict, deque
from typing import Dict, Optional
from dataclasses import dataclass

from ..config import TelegramBotConfig


@dataclass
class RateLimitInfo:
    """Информация о лимитах пользователя."""
    requests_count: int
    window_start: float
    last_request: float
    is_limited: bool


class RateLimiter:
    """Лимитер запросов для пользователей."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.messages_per_minute = config.rate_limit_messages_per_minute
        self.burst_limit = config.rate_limit_burst

        # Хранилище запросов по пользователям
        self.user_requests: Dict[int, deque] = defaultdict(deque)
        self.user_bursts: Dict[int, int] = defaultdict(int)
        self.last_cleanup = time.time()

        # Глобальные счётчики для API лимитов
        self.global_requests: deque = deque()
        self.global_requests_per_second = 30  # Telegram API limit

    async def check_rate_limit(self, user_id: int) -> tuple[bool, Optional[str]]:
        """
        Проверка лимитов запросов для пользователя.

        Args:
            user_id: ID пользователя Telegram

        Returns:
            Tuple[разрешено, сообщение_об_ошибке]
        """
        try:
            current_time = time.time()

            # Очистка старых записей
            await self._cleanup_old_records(current_time)

            # Проверка глобальных лимитов
            if not await self._check_global_limits(current_time):
                return False, "🚫 Слишком много запросов к системе. Пожалуйста, подождите несколько секунд."

            # Проверка минутных лимитов пользователя
            if not await self._check_minute_limits(user_id, current_time):
                return False, f"🚫 Лимит {self.messages_per_minute} запросов в минуту превышён. Пожалуйста, подождите."

            # Проверка burst лимитов
            if not await self._check_burst_limits(user_id, current_time):
                return False, "🚫 Слишком много запросов за короткое время. Пожалуйста, сделайте паузу."

            # Регистрация запроса
            await self._register_request(user_id, current_time)

            return True, None

        except Exception as e:
            print(f"Ошибка проверки rate limit: {e}")
            # При ошибке разрешаем запрос, но логируем
            return True, None

    async def _cleanup_old_records(self, current_time: float) -> None:
        """Очистка старых записей о запросах."""
        try:
            # Очистка раз в минуту
            if current_time - self.last_cleanup < 60:
                return

            # Очистка пользовательских записей (старше 1 минуты)
            cutoff_time = current_time - 60
            for user_id in list(self.user_requests.keys()):
                requests = self.user_requests[user_id]
                while requests and requests[0] < cutoff_time:
                    requests.popleft()

                if not requests:
                    del self.user_requests[user_id]

            # Очистка глобальных записей (старше 1 секунды)
            global_cutoff = current_time - 1
            while self.global_requests and self.global_requests[0] < global_cutoff:
                self.global_requests.popleft()

            self.last_cleanup = current_time

        except Exception as e:
            print(f"Ошибка очистки записей: {e}")

    async def _check_global_limits(self, current_time: float) -> bool:
        """Проверка глобальных лимитов API."""
        try:
            # Удаление старых глобальных запросов (старше 1 секунды)
            cutoff_time = current_time - 1
            while self.global_requests and self.global_requests[0] < cutoff_time:
                self.global_requests.popleft()

            # Проверка лимита запросов в секунду
            return len(self.global_requests) < self.global_requests_per_second

        except Exception as e:
            print(f"Ошибка проверки глобальных лимитов: {e}")
            return True

    async def _check_minute_limits(self, user_id: int, current_time: float) -> bool:
        """Проверка лимитов запросов в минуту."""
        try:
            requests = self.user_requests[user_id]

            # Удаление старых запросов (старше 1 минуты)
            cutoff_time = current_time - 60
            while requests and requests[0] < cutoff_time:
                requests.popleft()

            # Проверка лимита
            return len(requests) < self.messages_per_minute

        except Exception as e:
            print(f"Ошибка проверки минутных лимитов: {e}")
            return True

    async def _check_burst_limits(self, user_id: int, current_time: float) -> bool:
        """Проверка burst лимитов (быстрых запросов подряд)."""
        try:
            requests = self.user_requests[user_id]
            bursts = self.user_bursts

            # Проверка запросов за последние 10 секунд
            cutoff_time = current_time - 10
            recent_requests = sum(1 for req_time in requests if req_time > cutoff_time)

            if recent_requests >= self.burst_limit:
                return False

            # Сброс burst счётчика если прошло достаточно времени
            last_burst_time = max(requests) if requests else 0
            if current_time - last_burst_time > 10:
                bursts[user_id] = 0

            return True

        except Exception as e:
            print(f"Ошибка проверки burst лимитов: {e}")
            return True

    async def _register_request(self, user_id: int, current_time: float) -> None:
        """Регистрация нового запроса."""
        try:
            # Добавление в пользовательские запросы
            self.user_requests[user_id].append(current_time)

            # Добавление в глобальные запросы
            self.global_requests.append(current_time)

            # Обновление burst счётчика
            self.user_bursts[user_id] += 1

        except Exception as e:
            print(f"Ошибка регистрации запроса: {e}")

    def get_user_rate_info(self, user_id: int) -> RateLimitInfo:
        """Получение информации о лимитах пользователя."""
        try:
            current_time = time.time()
            requests = self.user_requests[user_id]

            if not requests:
                return RateLimitInfo(
                    requests_count=0,
                    window_start=current_time,
                    last_request=0,
                    is_limited=False
                )

            # Количество запросов последнюю минуту
            cutoff_time = current_time - 60
            recent_requests = sum(1 for req_time in requests if req_time > cutoff_time)

            # Время последнего запроса
            last_request = max(requests) if requests else 0

            # Проверка ограничений
            is_limited = (
                recent_requests >= self.messages_per_minute or
                len(self.global_requests) >= self.global_requests_per_second
            )

            return RateLimitInfo(
                requests_count=recent_requests,
                window_start=cutoff_time,
                last_request=last_request,
                is_limited=is_limited
            )

        except Exception as e:
            print(f"Ошибка получения информации о лимитах: {e}")
            return RateLimitInfo(
                requests_count=0,
                window_start=time.time(),
                last_request=0,
                is_limited=False
            )

    def get_global_rate_info(self) -> dict:
        """Получение глобальной информации о лимитах."""
        try:
            current_time = time.time()

            # Запросы последнюю секунду
            cutoff_time = current_time - 1
            global_rps = len(self.global_requests)

            # Запросы последнюю минуту
            minute_cutoff = current_time - 60
            total_minute_requests = sum(
                len(requests) for requests in self.user_requests.values()
                if any(req_time > minute_cutoff for req_time in requests)
            )

            return {
                "requests_per_second": global_rps,
                "requests_per_minute": total_minute_requests,
                "limit_per_second": self.global_requests_per_second,
                "active_users": len(self.user_requests),
                "current_time": current_time
            }

        except Exception as e:
            print(f"Ошибка получения глобальной информации: {e}")
            return {
                "requests_per_second": 0,
                "requests_per_minute": 0,
                "limit_per_second": self.global_requests_per_second,
                "active_users": 0,
                "current_time": time.time()
            }

    async def reset_user_limits(self, user_id: int) -> None:
        """Сброс лимитов для конкретного пользователя."""
        try:
            if user_id in self.user_requests:
                del self.user_requests[user_id]
            if user_id in self.user_bursts:
                del self.user_bursts[user_id]

        except Exception as e:
            print(f"Ошибка сброса лимитов пользователя: {e}")

    async def cleanup(self) -> None:
        """Очистка всех данных лимитера."""
        try:
            self.user_requests.clear()
            self.user_bursts.clear()
            self.global_requests.clear()

        except Exception as e:
            print(f"Ошибка очистки RateLimiter: {e}")