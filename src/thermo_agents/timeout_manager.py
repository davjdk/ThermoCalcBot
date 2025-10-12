"""
Адаптивный менеджер таймаутов для термодинамических агентов.

Обеспечивает динамическое управление таймаутами с механизмами
ранней диагностики и retry стратегиями.
"""

from __future__ import annotations

import asyncio
import logging
import time
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import aiohttp
from pydantic import BaseModel

from .thermo_agents_logger import SessionLogger


class OperationType(Enum):
    """Типы операций для управления таймаутами."""
    LLM_REQUEST = "llm_request"
    SQL_GENERATION = "sql_generation"
    TEMPERATURE_FILTER = "temperature_filter"
    LLM_FILTERING = "llm_filtering"
    COMPOUND_SEARCH = "compound_search"
    TOTAL_REQUEST = "total_request"
    HEARTBEAT = "heartbeat"


@dataclass
class TimeoutConfig:
    """Конфигурация таймаута для операции."""
    base_timeout: float
    max_timeout: float
    retry_multiplier: float = 1.5
    max_retries: int = 1
    backoff_base: float = 2.0
    jitter: bool = True


class RetryableError(BaseModel):
    """Описание ошибки, для которой возможен retry."""
    error_type: str
    retryable: bool
    message_pattern: str


class TimeoutManager:
    """
    Адаптивный менеджер таймаутов с механизмом retry.

    Основные возможности:
    - Динамическая настройка таймаутов
    - Heartbeat мониторинг LLM доступности
    - Умный retry механизм с exponential backoff
    - Ранняя диагностика проблем
    """

    # Базовые конфигурации таймаутов (оптимизированные для сложных запросов)
    DEFAULT_TIMEOUTS = {
        OperationType.LLM_REQUEST: TimeoutConfig(
            base_timeout=45.0,  # Увеличено с 30.0
            max_timeout=120.0,  # Увеличено с 60.0
            retry_multiplier=1.5,
            max_retries=2  # Увеличено с 1
        ),
        OperationType.SQL_GENERATION: TimeoutConfig(
            base_timeout=90.0,  # Увеличено с 45.0
            max_timeout=180.0,  # Увеличено с 90.0
            retry_multiplier=1.5,
            max_retries=2  # Увеличено с 1
        ),
        OperationType.TEMPERATURE_FILTER: TimeoutConfig(
            base_timeout=15.0,  # Увеличено с 10.0
            max_timeout=30.0,  # Увеличено с 20.0
            retry_multiplier=1.5,
            max_retries=1
        ),
        OperationType.LLM_FILTERING: TimeoutConfig(
            base_timeout=120.0,  # Увеличено с 60.0
            max_timeout=300.0,  # Увеличено с 120.0
            retry_multiplier=1.5,
            max_retries=2  # Увеличено с 1
        ),
        OperationType.COMPOUND_SEARCH: TimeoutConfig(
            base_timeout=180.0,  # Увеличено с 90.0
            max_timeout=600.0,  # Увеличено с 180.0
            retry_multiplier=1.5,
            max_retries=2  # Увеличено с 1
        ),
        OperationType.TOTAL_REQUEST: TimeoutConfig(
            base_timeout=300.0,  # Увеличено с 120.0
            max_timeout=900.0,  # Увеличено с 240.0
            retry_multiplier=1.5,
            max_retries=1
        ),
        OperationType.HEARTBEAT: TimeoutConfig(
            base_timeout=15.0,
            max_timeout=30.0,
            retry_multiplier=1.5,
            max_retries=1
        ),
    }

    # Ошибки, для которых возможен retry
    RETRYABLE_ERRORS = [
        RetryableError(
            error_type="timeout",
            retryable=True,
            message_pattern="timeout|timed out|TimeoutError"
        ),
        RetryableError(
            error_type="network",
            retryable=True,
            message_pattern="connection|network|unreachable|ConnectionError"
        ),
        RetryableError(
            error_type="http_error",
            retryable=True,
            message_pattern="502|503|504|500|HTTP error"
        ),
        RetryableError(
            error_type="rate_limit",
            retryable=True,
            message_pattern="rate limit|too many requests|429"
        ),
        RetryableError(
            error_type="llm_unavailable",
            retryable=True,
            message_pattern="unavailable|overloaded|capacity"
        ),
        # Не retryable ошибки
        RetryableError(
            error_type="syntax",
            retryable=False,
            message_pattern="syntax|invalid syntax|SQL error"
        ),
        RetryableError(
            error_type="validation",
            retryable=False,
            message_pattern="validation|invalid data|TypeError"
        ),
        RetryableError(
            error_type="auth",
            retryable=False,
            message_pattern="authentication|authorization|401|403"
        ),
    ]

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        session_logger: Optional[SessionLogger] = None,
        llm_base_url: Optional[str] = None,
        adaptive_adjustment: bool = True
    ):
        """
        Инициализация менеджера таймаутов.

        Args:
            logger: Логгер для вывода информации
            session_logger: Сессионный логгер
            llm_base_url: URL для проверки доступности LLM
            adaptive_adjustment: Включить адаптивную настройку таймаутов
        """
        self.logger = logger or logging.getLogger(__name__)
        self.session_logger = session_logger
        self.llm_base_url = llm_base_url
        self.adaptive_adjustment = adaptive_adjustment

        # История производительности для адаптивной настройки
        self.performance_history: Dict[OperationType, List[float]] = {
            op_type: [] for op_type in OperationType
        }

        # Текущие адаптированные таймауты
        self.adaptive_timeouts = self.DEFAULT_TIMEOUTS.copy()

        # Circuit breaker состояние для каждого типа операции
        self.circuit_breaker_state: Dict[OperationType, Dict] = {
            op_type: {
                "failures": 0,
                "last_failure_time": None,
                "state": "closed",  # closed, open, half_open
                "success_count": 0
            }
            for op_type in OperationType
        }

        # Circuit breaker настройки
        self.circuit_breaker_config = {
            "failure_threshold": 3,  # Количество отказов для открытия circuit
            "recovery_timeout": 60,  # Секунды до попытки восстановления
            "success_threshold": 2,  # Количество успехов для закрытия circuit
        }

        # Статистика
        self.stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "retries_performed": 0,
            "timeouts_avoided": 0,
            "circuit_breaker_activations": 0,
        }

        self.logger.info("TimeoutManager initialized with adaptive timeouts and circuit breaker")

    def get_timeout(self, operation_type: OperationType, retry_count: int = 0) -> float:
        """
        Получить адаптивный таймаут для операции.

        Args:
            operation_type: Тип операции
            retry_count: Номер попытки (0 - первая)

        Returns:
            Таймаут в секундах
        """
        config = self.adaptive_timeouts.get(operation_type)
        if not config:
            self.logger.warning(f"No timeout config for {operation_type}, using default 30s")
            return 30.0

        # Базовый таймаут с адаптивной настройкой
        base_timeout = config.base_timeout

        # Увеличиваем таймаут для retry попыток
        if retry_count > 0:
            base_timeout *= (config.retry_multiplier ** retry_count)

        # Ограничиваем максимальным таймаутом
        timeout = min(base_timeout, config.max_timeout)

        self.logger.debug(
            f"Timeout for {operation_type.value} (retry {retry_count}): {timeout:.1f}s"
        )

        return timeout

    def is_retryable_error(self, error: Exception) -> bool:
        """
        Определить, является ли ошибка retryable.

        Args:
            error: Исключение для анализа

        Returns:
            True если ошибка retryable
        """
        error_message = str(error).lower()
        error_type = type(error).__name__.lower()

        # Немедленно не retryable критические ошибки
        critical_errors = [
            "attributeerror", "typeerror", "valueerror", "keyerror",
            "syntaxerror", "importerror", "memoryerror"
        ]

        if any(critical_error in error_type for critical_error in critical_errors):
            self.logger.debug(f"Critical non-retryable error: {error_type}")
            return False

        # Проверяем по списку retryable ошибок
        for retryable_error in self.RETRYABLE_ERRORS:
            if (retryable_error.message_pattern.lower() in error_message or
                retryable_error.error_type.lower() in error_type):
                return retryable_error.retryable

        # Дополнительные non-retryable паттерны
        non_retryable_patterns = [
            "total_duration", "attribute", "type", "syntax", "validation",
            "authentication", "authorization", "forbidden", "not found"
        ]

        if any(pattern in error_message for pattern in non_retryable_patterns):
            self.logger.debug(f"Non-retryable error pattern: {error_message[:50]}...")
            return False

        # Retryable сетевые ошибки
        retryable_keywords = ["timeout", "connection", "network", "unreachable", "rate limit"]
        if any(keyword in error_message for keyword in retryable_keywords):
            self.logger.debug(f"Retryable network error: {error_message[:50]}...")
            return True

        # По умолчанию для неизвестных ошибок - не retryable для безопасности
        self.logger.debug(f"Unknown error type, treating as non-retryable: {error_type}")
        return False

    def _check_circuit_breaker(self, operation_type: OperationType) -> bool:
        """
        Проверить состояние circuit breaker для операции.

        Args:
            operation_type: Тип операции

        Returns:
            True если операция разрешена (circuit closed или half_open)
        """
        circuit_state = self.circuit_breaker_state[operation_type]
        config = self.circuit_breaker_config

        if circuit_state["state"] == "closed":
            return True
        elif circuit_state["state"] == "open":
            # Проверяем, прошло ли достаточно времени для попытки восстановления
            if (circuit_state["last_failure_time"] and
                time.time() - circuit_state["last_failure_time"] > config["recovery_timeout"]):
                circuit_state["state"] = "half_open"
                self.logger.info(f"Circuit breaker for {operation_type.value} transitioning to half-open")
                return True
            return False
        elif circuit_state["state"] == "half_open":
            return True

        return False

    def _record_circuit_breaker_success(self, operation_type: OperationType):
        """
        Записать успешное выполнение для circuit breaker.

        Args:
            operation_type: Тип операции
        """
        circuit_state = self.circuit_breaker_state[operation_type]
        config = self.circuit_breaker_config

        if circuit_state["state"] == "half_open":
            circuit_state["success_count"] += 1
            if circuit_state["success_count"] >= config["success_threshold"]:
                circuit_state["state"] = "closed"
                circuit_state["failures"] = 0
                circuit_state["success_count"] = 0
                self.logger.info(f"Circuit breaker for {operation_type.value} closed after successful recovery")

    def _record_circuit_breaker_failure(self, operation_type: OperationType):
        """
        Записать отказ для circuit breaker.

        Args:
            operation_type: Тип операции
        """
        circuit_state = self.circuit_breaker_state[operation_type]
        config = self.circuit_breaker_config

        circuit_state["failures"] += 1
        circuit_state["last_failure_time"] = time.time()

        if (circuit_state["state"] == "half_open" or
            circuit_state["failures"] >= config["failure_threshold"]):
            circuit_state["state"] = "open"
            circuit_state["success_count"] = 0
            self.stats["circuit_breaker_activations"] += 1
            self.logger.warning(f"Circuit breaker for {operation_type.value} opened after {circuit_state['failures']} failures")

    async def execute_with_retry(
        self,
        operation: Callable,
        operation_type: OperationType,
        *args,
        **kwargs
    ) -> Any:
        """
        Выполнить операцию с retry механизмом и circuit breaker.

        Args:
            operation: Асинхронная функция для выполнения
            operation_type: Тип операции
            *args, **kwargs: Аргументы операции

        Returns:
            Результат операции

        Raises:
            Последняя ошибка если все попытки неудачны
            CircuitBreakerOpenError если circuit breaker открыт
        """
        config = self.adaptive_timeouts.get(operation_type)
        if not config:
            config = TimeoutConfig(base_timeout=30.0, max_timeout=60.0, max_retries=1)

        # Проверяем circuit breaker
        if not self._check_circuit_breaker(operation_type):
            circuit_state = self.circuit_breaker_state[operation_type]
            raise Exception(f"Circuit breaker open for {operation_type.value}. Last failure: {circuit_state['last_failure_time']}")

        last_error = None
        start_time = time.time()

        for attempt in range(config.max_retries + 1):
            timeout = self.get_timeout(operation_type, attempt)
            attempt_start = time.time()

            try:
                self.logger.info(
                    f"Executing {operation_type.value} (attempt {attempt + 1}/{config.max_retries + 1}, timeout: {timeout:.1f}s)"
                )

                if self.session_logger:
                    self.session_logger.log_info(
                        f"OPERATION START: {operation_type.value}, attempt {attempt + 1}, timeout {timeout:.1f}s"
                    )

                # Выполняем операцию с таймаутом
                result = await asyncio.wait_for(operation(*args, **kwargs), timeout=timeout)

                # Успешное выполнение
                elapsed = time.time() - attempt_start
                self._record_success(operation_type, elapsed)
                self._record_circuit_breaker_success(operation_type)

                self.logger.info(
                    f"{operation_type.value} completed successfully in {elapsed:.1f}s (attempt {attempt + 1})"
                )

                if self.session_logger:
                    self.session_logger.log_info(
                        f"OPERATION SUCCESS: {operation_type.value}, completed in {elapsed:.1f}s, attempt {attempt + 1}"
                    )

                return result

            except Exception as e:
                last_error = e
                elapsed = time.time() - attempt_start

                self.logger.warning(
                    f"{operation_type.value} failed on attempt {attempt + 1} after {elapsed:.1f}s: {str(e)[:100]}"
                )

                if self.session_logger:
                    self.session_logger.log_error(
                        f"OPERATION FAILED: {operation_type.value}, attempt {attempt + 1}, error: {str(e)[:100]}"
                    )

                # Записываем отказ в circuit breaker
                self._record_circuit_breaker_failure(operation_type)

                # Если circuit breaker открыт, прекращаем попытки
                if self.circuit_breaker_state[operation_type]["state"] == "open":
                    self.logger.error(f"Circuit breaker opened for {operation_type.value}, aborting retries")
                    break

                # Проверяем, можно ли retry
                if attempt < config.max_retries and self.is_retryable_error(e):
                    # Вычисляем задержку с exponential backoff и jitter
                    delay = self._calculate_retry_delay(config, attempt)

                    self.logger.info(
                        f"Retrying {operation_type.value} in {delay:.1f}s (attempt {attempt + 2})"
                    )

                    if self.session_logger:
                        self.session_logger.log_info(
                            f"RETRY SCHEDULED: {operation_type.value}, delay {delay:.1f}s, next attempt {attempt + 2}"
                        )

                    await asyncio.sleep(delay)
                    self.stats["retries_performed"] += 1
                    continue
                else:
                    # Нельзя retry или это последняя попытка
                    break

        # Все попытки неудачны
        total_elapsed = time.time() - start_time
        self._record_failure(operation_type, total_elapsed)

        self.logger.error(
            f"{operation_type.value} failed after {config.max_retries + 1} attempts in {total_elapsed:.1f}s"
        )

        if self.session_logger:
            self.session_logger.log_error(
                f"OPERATION FINAL FAILURE: {operation_type.value}, {config.max_retries + 1} attempts, {total_elapsed:.1f}s total"
            )

        raise last_error

    def _calculate_retry_delay(self, config: TimeoutConfig, attempt: int) -> float:
        """
        Рассчитать задержку перед retry с улучшенным exponential backoff и jitter.

        Args:
            config: Конфигурация таймаута
            attempt: Номер текущей попытки (0-based)

        Returns:
            Задержка в секундах
        """
        # Улучшенный exponential backoff с учетом контекста операции
        base_delay = config.backoff_base ** attempt

        # Добавляем небольшой linear компонент для первых попыток
        if attempt == 0:
            base_delay = 0.5  # Минимальная задержка для первой retry
        elif attempt == 1:
            base_delay = max(base_delay, 1.0)  # Минимальная задержка для второй retry

        # Умный jitter - меньше для быстрых операций, больше для долгих
        if config.jitter:
            if config.base_timeout < 30:
                jitter = random.uniform(0.9, 1.1)  # Меньший jitter для быстрых операций
            else:
                jitter = random.uniform(0.7, 1.3)  # Больший jitter для долгих операций
            delay = base_delay * jitter
        else:
            delay = base_delay

        # Адаптивное ограничение максимальной задержки
        max_delay = min(
            60.0,  # Абсолютный максимум
            config.base_timeout * 0.3,  # Не более 30% от базового таймаута
            max(10.0, config.base_timeout * 0.1)  # Минимум 10 секунд или 10% от таймаута
        )

        delay = min(delay, max_delay)

        self.logger.debug(f"Calculated retry delay: {delay:.2f}s (attempt {attempt}, base_timeout: {config.base_timeout}s)")
        return delay

    def _record_success(self, operation_type: OperationType, elapsed: float):
        """Записать успешное выполнение для адаптивной настройки."""
        self.stats["total_operations"] += 1
        self.stats["successful_operations"] += 1

        if self.adaptive_adjustment:
            history = self.performance_history[operation_type]
            history.append(elapsed)

            # Оставляем только последние 10 выполнений
            if len(history) > 10:
                history.pop(0)

            # Адаптивная настройка таймаута
            self._adjust_timeout_adaptive(operation_type)

    def _record_failure(self, operation_type: OperationType, elapsed: float):
        """Записать неудачное выполнение."""
        self.stats["total_operations"] += 1

    def _adjust_timeout_adaptive(self, operation_type: OperationType):
        """
        Адтивно настроить таймаут на основе истории выполнения.

        Args:
            operation_type: Тип операции для настройки
        """
        history = self.performance_history[operation_type]
        if len(history) < 3:  # Нужно минимум 3 выполнений для настройки
            return

        config = self.adaptive_timeouts[operation_type]

        # Вычисляем среднее время и стандартное отклонение
        avg_time = sum(history) / len(history)
        variance = sum((x - avg_time) ** 2 for x in history) / len(history)
        std_dev = variance ** 0.5

        # Новое предложение таймаута: среднее + 2 стандартных отклонения
        suggested_timeout = avg_time + (2 * std_dev)

        # Ограничиваем в разумных пределах
        min_timeout = config.base_timeout * 0.5
        max_timeout = config.max_timeout

        suggested_timeout = max(min_timeout, min(suggested_timeout, max_timeout))

        # Применяем настройку если разница существенна (>10%)
        current_timeout = config.base_timeout
        if abs(suggested_timeout - current_timeout) / current_timeout > 0.1:
            config.base_timeout = suggested_timeout

            self.logger.info(
                f"Adapted timeout for {operation_type.value}: {current_timeout:.1f}s → {suggested_timeout:.1f}s "
                f"(avg: {avg_time:.1f}s, std: {std_dev:.1f}s)"
            )

            if self.session_logger:
                self.session_logger.log_info(
                    f"TIMEOUT ADAPTED: {operation_type.value}, {current_timeout:.1f}s → {suggested_timeout:.1f}s"
                )

    async def check_llm_heartbeat(self) -> bool:
        """
        Проверить доступность LLM API.

        Returns:
            True если LLM доступен
        """
        if not self.llm_base_url:
            self.logger.warning("No LLM base URL configured for heartbeat check")
            return True

        try:
            timeout = self.get_timeout(OperationType.HEARTBEAT)

            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
                # Простая проверка доступности API
                async with session.get(f"{self.llm_base_url}/models") as response:
                    if response.status == 200:
                        self.logger.debug("LLM heartbeat check successful")
                        return True
                    else:
                        self.logger.warning(f"LLM heartbeat failed: HTTP {response.status}")
                        return False

        except Exception as e:
            self.logger.warning(f"LLM heartbeat check failed: {str(e)}")
            return False

    async def wait_for_early_diagnosis(
        self,
        operation_task: asyncio.Task,
        operation_type: OperationType,
        check_interval: float = 2.0
    ) -> Any:
        """
        Ожидать выполнения операции с ранней диагностикой проблем.

        Args:
            operation_task: Задача для выполнения
            operation_type: Тип операции
            check_interval: Интервал проверки

        Returns:
            Результат операции
        """
        timeout = self.get_timeout(operation_type)
        start_time = time.time()

        while not operation_task.done():
            await asyncio.sleep(check_interval)
            elapsed = time.time() - start_time

            # Ранняя диагностика: если прошло 70% таймаута
            if elapsed > timeout * 0.7:
                self.logger.warning(
                    f"Early diagnosis: {operation_type.value} taking longer than expected "
                    f"({elapsed:.1f}s / {timeout:.1f}s)"
                )

                if self.session_logger:
                    self.session_logger.log_warning(
                        f"EARLY DIAGNOSIS: {operation_type.value}, {elapsed:.1f}s elapsed, {timeout:.1f}s timeout"
                    )

            # Проверяем heartbeat для LLM операций
            if operation_type in [OperationType.LLM_REQUEST, OperationType.LLM_FILTERING]:
                if elapsed > timeout * 0.5:
                    heartbeat_ok = await self.check_llm_heartbeat()
                    if not heartbeat_ok:
                        self.logger.error("LLM heartbeat failed during operation")
                        # Не прерываем операцию, но логируем проблему

        # Возвращаем результат (или исключение)
        return operation_task.result()

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику работы менеджера."""
        return {
            **self.stats,
            "success_rate": (
                self.stats["successful_operations"] / max(1, self.stats["total_operations"])
            ),
            "adaptive_timeouts": {
                op_type.value: config.base_timeout
                for op_type, config in self.adaptive_timeouts.items()
            },
            "performance_summary": {
                op_type.value: {
                    "count": len(history),
                    "avg_time": sum(history) / len(history) if history else 0,
                    "min_time": min(history) if history else 0,
                    "max_time": max(history) if history else 0,
                }
                for op_type, history in self.performance_history.items()
            }
        }


# =============================================================================
# ГЛОБАЛЬНЫЙ ЭКЗЕМПЛЯР И ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================

_global_timeout_manager: Optional[TimeoutManager] = None


def get_timeout_manager(
    logger: Optional[logging.Logger] = None,
    session_logger: Optional[SessionLogger] = None,
    llm_base_url: Optional[str] = None
) -> TimeoutManager:
    """
    Получить глобальный экземпляр менеджера таймаутов.

    Args:
        logger: Логгер
        session_logger: Сессионный логгер
        llm_base_url: URL LLM API

    Returns:
        Экземпляр TimeoutManager
    """
    global _global_timeout_manager

    if _global_timeout_manager is None:
        _global_timeout_manager = TimeoutManager(
            logger=logger,
            session_logger=session_logger,
            llm_base_url=llm_base_url
        )

    return _global_timeout_manager


def create_timeout_manager(
    logger: Optional[logging.Logger] = None,
    session_logger: Optional[SessionLogger] = None,
    llm_base_url: Optional[str] = None,
    adaptive_adjustment: bool = True
) -> TimeoutManager:
    """
    Создать новый экземпляр менеджера таймаутов.

    Args:
        logger: Логгер
        session_logger: Сессионный логгер
        llm_base_url: URL LLM API
        adaptive_adjustment: Включить адаптивную настройку

    Returns:
        Новый экземпляр TimeoutManager
    """
    return TimeoutManager(
        logger=logger,
        session_logger=session_logger,
        llm_base_url=llm_base_url,
        adaptive_adjustment=adaptive_adjustment
    )