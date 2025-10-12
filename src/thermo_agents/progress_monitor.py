"""
Прогресс-мониторинг для долгих операций в термодинамических агентах.

Обеспечивает визуализацию прогресса, детальную трассировку
и метрики производительности в реальном времени.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
import threading
from datetime import datetime, timedelta

from .thermo_agents_logger import SessionLogger


class ProgressStatus(Enum):
    """Статусы прогресса операции."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressStep:
    """Шаг операции с прогрессом."""
    name: str
    description: str
    estimated_duration: float = 0.0
    weight: float = 1.0  # Вес шага для общего прогресса


@dataclass
class ProgressMetrics:
    """Метрики прогресса операции."""
    operation_id: str
    operation_type: str
    total_steps: int
    current_step: int = 0
    overall_progress: float = 0.0
    step_progress: float = 0.0
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    step_start_time: Optional[datetime] = None
    status: ProgressStatus = ProgressStatus.PENDING


class ProgressMonitor:
    """
    Монитор прогресса для долгих операций.

    Основные возможности:
    - Визуализация прогресса операций
    - Детальная трассировка шагов
    - Расчет оставшегося времени
    - Интеграция с SessionLogger
    """

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        session_logger: Optional[SessionLogger] = None,
        update_interval: float = 0.5
    ):
        """
        Инициализация монитора прогресса.

        Args:
            logger: Логгер для вывода информации
            session_logger: Сессионный логгер
            update_interval: Интервал обновления прогресса
        """
        self.logger = logger or logging.getLogger(__name__)
        self.session_logger = session_logger
        self.update_interval = update_interval

        # Активные операции
        self.active_operations: Dict[str, ProgressMetrics] = {}
        self.operation_steps: Dict[str, List[ProgressStep]] = {}

        # История операций
        self.completed_operations: Dict[str, ProgressMetrics] = {}

        # Callback функции для обновления UI
        self.progress_callbacks: List[Callable[[ProgressMetrics], None]] = []

        # Бэкграунд задача для обновления прогресса
        self._update_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger.info("ProgressMonitor initialized")

    async def start_operation(
        self,
        operation_id: str,
        operation_type: str,
        steps: List[ProgressStep]
    ) -> ProgressMetrics:
        """
        Начать мониторинг новой операции.

        Args:
            operation_id: Уникальный ID операции
            operation_type: Тип операции
            steps: Список шагов операции

        Returns:
            Метрики прогресса операции
        """
        # Рассчитываем общий вес шагов
        total_weight = sum(step.weight for step in steps)

        # Нормализуем веса шагов
        for step in steps:
            step.weight = step.weight / total_weight

        # Создаем метрики
        metrics = ProgressMetrics(
            operation_id=operation_id,
            operation_type=operation_type,
            total_steps=len(steps)
        )

        self.active_operations[operation_id] = metrics
        self.operation_steps[operation_id] = steps

        self.logger.info(
            f"Started monitoring operation {operation_id} ({operation_type}) with {len(steps)} steps"
        )

        if self.session_logger:
            self.session_logger.log_info(
                f"PROGRESS START: {operation_id} ({operation_type}), {len(steps)} steps"
            )

        # Запускаем бэкграунд обновление если нужно
        if not self._running:
            await self._start_background_updates()

        return metrics

    async def update_step_progress(
        self,
        operation_id: str,
        step_name: str,
        progress: float,
        message: Optional[str] = None
    ) -> bool:
        """
        Обновить прогресс текущего шага.

        Args:
            operation_id: ID операции
            step_name: Название шага
            progress: Прогресс шага (0.0 - 1.0)
            message: Дополнительное сообщение

        Returns:
            True если обновление успешно
        """
        if operation_id not in self.active_operations:
            self.logger.warning(f"Operation {operation_id} not found for progress update")
            return False

        metrics = self.active_operations[operation_id]
        steps = self.operation_steps[operation_id]

        # Находим текущий шаг
        current_step_name = steps[metrics.current_step].name if metrics.current_step < len(steps) else ""

        if step_name != current_step_name:
            # Пытаемся найти шаг и переключиться на него
            for i, step in enumerate(steps):
                if step.name == step_name:
                    metrics.current_step = i
                    metrics.step_start_time = datetime.now()
                    metrics.step_progress = 0.0
                    break
            else:
                self.logger.warning(f"Step {step_name} not found in operation {operation_id}")
                return False

        # Обновляем прогресс шага
        old_progress = metrics.step_progress
        metrics.step_progress = max(0.0, min(1.0, progress))
        metrics.status = ProgressStatus.IN_PROGRESS

        # Рассчитываем общий прогресс
        overall_progress = 0.0
        for i, step in enumerate(steps):
            if i < metrics.current_step:
                overall_progress += step.weight  # Завершенные шаги
            elif i == metrics.current_step:
                overall_progress += step.weight * metrics.step_progress  # Текущий шаг
            # Последующие шаги не учитываются

        metrics.overall_progress = overall_progress

        # Обновляем время
        now = datetime.now()
        metrics.elapsed_time = (now - metrics.start_time).total_seconds()

        # Рассчитываем предполагаемое оставшееся время
        if metrics.overall_progress > 0.01:  # Избегаем деления на ноль
            estimated_total = metrics.elapsed_time / metrics.overall_progress
            metrics.estimated_remaining = estimated_total - metrics.elapsed_time
        else:
            # Базируемся на оценках шагов
            total_estimated = sum(
                step.estimated_duration for step in steps[metrics.current_step:]
            )
            metrics.estimated_remaining = total_estimated

        # Логируем обновление
        if abs(metrics.overall_progress - old_progress) > 0.05 or message:
            self.logger.info(
                f"Progress {operation_id}: {metrics.overall_progress:.1%} "
                f"(step {metrics.current_step + 1}/{len(steps)}: {step_name} {metrics.step_progress:.1%})"
            )

            if self.session_logger:
                log_msg = f"PROGRESS UPDATE: {operation_id}, {metrics.overall_progress:.1%}, "
                log_msg += f"step {step_name} {metrics.step_progress:.1%}"
                if message:
                    log_msg += f" - {message}"
                self.session_logger.log_info(log_msg)

        # Вызываем callback функции
        for callback in self.progress_callbacks:
            try:
                callback(metrics)
            except Exception as e:
                self.logger.error(f"Error in progress callback: {e}")

        return True

    async def complete_step(self, operation_id: str, step_name: str) -> bool:
        """
        Завершить текущий шаг.

        Args:
            operation_id: ID операции
            step_name: Название шага

        Returns:
            True если шаг завершен успешно
        """
        if operation_id not in self.active_operations:
            return False

        metrics = self.active_operations[operation_id]
        steps = self.operation_steps[operation_id]

        # Устанавливаем прогресс шага в 100%
        await self.update_step_progress(operation_id, step_name, 1.0)

        # Перемещаемся к следующему шагу
        if metrics.current_step < len(steps) - 1:
            metrics.current_step += 1
            metrics.step_start_time = datetime.now()
            metrics.step_progress = 0.0

            next_step = steps[metrics.current_step]
            self.logger.info(
                f"Operation {operation_id}: moved to step {metrics.current_step + 1}/{len(steps)}: {next_step.name}"
            )

            if self.session_logger:
                self.session_logger.log_info(
                    f"STEP COMPLETE: {operation_id}, {step_name} → {next_step.name}"
                )
        else:
            # Все шаги завершены
            await self.complete_operation(operation_id, success=True)

        return True

    async def complete_operation(self, operation_id: str, success: bool = True, error: Optional[str] = None) -> bool:
        """
        Завершить операцию.

        Args:
            operation_id: ID операции
            success: Успешность завершения
            error: Ошибка при неуспешном завершении

        Returns:
            True если операция завершена
        """
        if operation_id not in self.active_operations:
            self.logger.warning(f"Operation {operation_id} not found for completion")
            return False

        metrics = self.active_operations[operation_id]
        metrics.status = ProgressStatus.COMPLETED if success else ProgressStatus.FAILED

        # Финальное обновление времени
        now = datetime.now()
        metrics.elapsed_time = (now - metrics.start_time).total_seconds()
        metrics.estimated_remaining = 0.0

        if success:
            metrics.overall_progress = 1.0
            metrics.step_progress = 1.0

            self.logger.info(
                f"Operation {operation_id} completed successfully in {metrics.elapsed_time:.1f}s"
            )

            if self.session_logger:
                self.session_logger.log_info(
                    f"PROGRESS COMPLETE: {operation_id}, {metrics.elapsed_time:.1f}s total"
                )
        else:
            self.logger.error(
                f"Operation {operation_id} failed after {metrics.elapsed_time:.1f}s: {error}"
            )

            if self.session_logger:
                self.session_logger.log_error(
                    f"PROGRESS FAILED: {operation_id}, {metrics.elapsed_time:.1f}s, error: {error}"
                )

        # Перемещаем в завершенные операции
        self.completed_operations[operation_id] = metrics
        del self.active_operations[operation_id]

        # Вызываем callback функции
        for callback in self.progress_callbacks:
            try:
                callback(metrics)
            except Exception as e:
                self.logger.error(f"Error in progress callback: {e}")

        return True

    def get_progress(self, operation_id: str) -> Optional[ProgressMetrics]:
        """
        Получить текущий прогресс операции.

        Args:
            operation_id: ID операции

        Returns:
            Метрики прогресса или None
        """
        return self.active_operations.get(operation_id)

    def get_all_progress(self) -> Dict[str, ProgressMetrics]:
        """Получить прогресс всех активных операций."""
        return self.active_operations.copy()

    def add_progress_callback(self, callback: Callable[[ProgressMetrics], None]):
        """
        Добавить callback функцию для обновления прогресса.

        Args:
            callback: Функция, принимающая ProgressMetrics
        """
        self.progress_callbacks.append(callback)

    def remove_progress_callback(self, callback: Callable[[ProgressMetrics], None]):
        """Удалить callback функцию."""
        if callback in self.progress_callbacks:
            self.progress_callbacks.remove(callback)

    def format_progress_bar(self, metrics: ProgressMetrics, width: int = 40) -> str:
        """
        Сформатировать текстовый прогресс-бар.

        Args:
            metrics: Метрики прогресса
            width: Ширина прогресс-бара

        Returns:
            Строка с прогресс-баром
        """
        filled = int(metrics.overall_progress * width)
        bar = "█" * filled + "░" * (width - filled)

        status_emoji = {
            ProgressStatus.PENDING: "⏳",
            ProgressStatus.IN_PROGRESS: "🔄",
            ProgressStatus.COMPLETED: "✅",
            ProgressStatus.FAILED: "❌",
            ProgressStatus.CANCELLED: "⏹️"
        }

        emoji = status_emoji.get(metrics.status, "❓")

        time_info = ""
        if metrics.elapsed_time > 0:
            time_info = f" ({metrics.elapsed_time:.1f}s"
            if metrics.estimated_remaining > 0:
                time_info += f", ~{metrics.estimated_remaining:.0f}s remaining"
            time_info += ")"

        step_info = ""
        if metrics.current_step < metrics.total_steps:
            steps = self.operation_steps.get(metrics.operation_id, [])
            if steps:
                current_step_name = steps[metrics.current_step].name
                step_info = f" - {current_step_name} ({metrics.step_progress:.1%})"

        return f"{emoji} [{bar}] {metrics.overall_progress:.1%}{time_info}{step_info}"

    def get_detailed_report(self, operation_id: str) -> Optional[str]:
        """
        Получить детальный отчет об операции.

        Args:
            operation_id: ID операции

        Returns:
            Детальный текстовый отчет
        """
        metrics = self.active_operations.get(operation_id) or self.completed_operations.get(operation_id)
        if not metrics:
            return None

        steps = self.operation_steps.get(operation_id, [])

        report = f"""
Operation Report: {metrics.operation_id}
Type: {metrics.operation_type}
Status: {metrics.status.value}
Progress: {metrics.overall_progress:.1%}
Current Step: {metrics.current_step + 1}/{metrics.total_steps}
Elapsed Time: {metrics.elapsed_time:.1f}s
"""

        if metrics.status == ProgressStatus.IN_PROGRESS:
            report += f"Estimated Remaining: {metrics.estimated_remaining:.1f}s\n"

        if steps:
            report += "\nSteps:\n"
            for i, step in enumerate(steps):
                status = "✅" if i < metrics.current_step else "🔄" if i == metrics.current_step else "⏳"
                step_progress = "100%" if i < metrics.current_step else f"{metrics.step_progress:.1%}" if i == metrics.current_step else "0%"
                report += f"  {i+1}. {status} {step.name} - {step.description} ({step_progress})\n"

        return report

    async def _start_background_updates(self):
        """Запустить бэкграунд задачу для обновления прогресса."""
        if self._running:
            return

        self._running = True
        self._update_task = asyncio.create_task(self._background_update_loop())

    async def _background_update_loop(self):
        """Бэкграунд цикл для обновления метрик."""
        while self._running and self.active_operations:
            try:
                # Обновляем метрики для всех активных операций
                for operation_id, metrics in list(self.active_operations.items()):
                    now = datetime.now()
                    metrics.elapsed_time = (now - metrics.start_time).total_seconds()

                    # Обновляем оценку оставшегося времени
                    if metrics.overall_progress > 0.01:
                        estimated_total = metrics.elapsed_time / metrics.overall_progress
                        metrics.estimated_remaining = estimated_total - metrics.elapsed_time

                await asyncio.sleep(self.update_interval)

            except Exception as e:
                self.logger.error(f"Error in progress update loop: {e}")
                await asyncio.sleep(self.update_interval * 2)

        self._running = False

    async def shutdown(self):
        """Завершить работу монитора прогресса."""
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

        self.logger.info("ProgressMonitor shutdown")


# =============================================================================
# КОНТЕКСТНЫЙ МЕНЕДЖЕР ДЛЯ ПРОСТОГО ИСПОЛЬЗОВАНИЯ
# =============================================================================

class ProgressContext:
    """
    Контекстный менеджер для автоматического мониторинга операций.
    """

    def __init__(
        self,
        monitor: ProgressMonitor,
        operation_id: str,
        operation_type: str,
        steps: List[ProgressStep]
    ):
        self.monitor = monitor
        self.operation_id = operation_id
        self.operation_type = operation_type
        self.steps = steps
        self.metrics: Optional[ProgressMetrics] = None

    async def __aenter__(self) -> ProgressMetrics:
        """Начать мониторинг операции."""
        self.metrics = await self.monitor.start_operation(
            self.operation_id,
            self.operation_type,
            self.steps
        )
        return self.metrics

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Завершить мониторинг операции."""
        if self.metrics:
            success = exc_type is None
            error = str(exc_val) if exc_val else None
            await self.monitor.complete_operation(self.operation_id, success, error)


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================

def create_progress_monitor(
    logger: Optional[logging.Logger] = None,
    session_logger: Optional[SessionLogger] = None,
    update_interval: float = 0.5
) -> ProgressMonitor:
    """
    Создать новый монитор прогресса.

    Args:
        logger: Логгер
        session_logger: Сессионный логгер
        update_interval: Интервал обновления

    Returns:
        Новый экземпляр ProgressMonitor
    """
    return ProgressMonitor(
        logger=logger,
        session_logger=session_logger,
        update_interval=update_interval
    )


def create_standard_thermo_steps() -> List[ProgressStep]:
    """
    Создать стандартные шаги для термодинамической операции.

    Returns:
        Список стандартных шагов
    """
    return [
        ProgressStep(
            name="parameter_extraction",
            description="Извлечение параметров из запроса",
            estimated_duration=5.0,
            weight=1.0
        ),
        ProgressStep(
            name="sql_generation",
            description="Генерация SQL запросов",
            estimated_duration=15.0,
            weight=2.0
        ),
        ProgressStep(
            name="database_execution",
            description="Выполнение запросов к базе данных",
            estimated_duration=10.0,
            weight=1.5
        ),
        ProgressStep(
            name="results_filtering",
            description="Фильтрация и анализ результатов",
            estimated_duration=20.0,
            weight=2.5
        ),
        ProgressStep(
            name="final_aggregation",
            description="Агрегация финальных результатов",
            estimated_duration=5.0,
            weight=1.0
        ),
    ]


def create_compound_search_steps(compounds_count: int) -> List[ProgressStep]:
    """
    Создать шаги для поиска соединений.

    Args:
        compounds_count: Количество соединений для поиска

    Returns:
        Список шагов операции
    """
    base_steps = [
        ProgressStep(
            name="parameter_extraction",
            description="Извлечение параметров из запроса",
            estimated_duration=5.0,
            weight=1.0
        ),
    ]

    # Шаги для каждого соединения
    for i in range(compounds_count):
        base_steps.append(ProgressStep(
            name=f"compound_search_{i+1}",
            description=f"Поиск соединения {i+1}/{compounds_count}",
            estimated_duration=30.0,
            weight=2.0
        ))

    base_steps.extend([
        ProgressStep(
            name="results_aggregation",
            description="Агрегация результатов поиска",
            estimated_duration=10.0,
            weight=1.5
        ),
        ProgressStep(
            name="final_analysis",
            description="Финальный анализ и подготовка ответа",
            estimated_duration=5.0,
            weight=1.0
        ),
    ])

    return base_steps