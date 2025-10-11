"""
Система операций для структурированного логирования действий агентов.

Предоставляет единый формат логирования операций агентов с разделением
на успешные операции (краткий лог) и ошибки (полное детальное логирование).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OperationStatus(str, Enum):
    """Статусы операции."""

    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class OperationType(str, Enum):
    """Типы операций агентов."""

    # Thermodynamic Agent
    EXTRACT_PARAMETERS = "EXTRACT_PARAMETERS"

    # SQL Generation Agent
    GENERATE_QUERY = "GENERATE_QUERY"
    VALIDATE_QUERY = "VALIDATE_QUERY"

    # Database Agent
    EXECUTE_QUERY = "EXECUTE_QUERY"
    TEMPERATURE_FILTER = "TEMPERATURE_FILTER"

    # Results Filtering Agent
    FILTER_RESULTS = "FILTER_RESULTS"
    INDIVIDUAL_FILTER = "INDIVIDUAL_FILTER"

    # Individual Search Agent
    INDIVIDUAL_SEARCH = "INDIVIDUAL_SEARCH"
    PARALLEL_SEARCH = "PARALLEL_SEARCH"

    # Orchestrator
    PROCESS_REQUEST = "PROCESS_REQUEST"
    COORDINATE_AGENTS = "COORDINATE_AGENTS"


class OperationData(BaseModel):
    """Данные операции."""

    input_data: Dict[str, Any] = Field(default_factory=dict, description="Входные данные операции")
    output_data: Dict[str, Any] = Field(default_factory=dict, description="Результат операции")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Метаданные операции")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Детали ошибки")
    execution_time_ms: Optional[float] = Field(None, description="Время выполнения в миллисекундах")


class Operation(BaseModel):
    """Операция агента."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: str = Field(description="Имя агента-исполнителя")
    operation_type: OperationType = Field(description="Тип операции")
    status: OperationStatus = Field(default_factory=lambda: OperationStatus.STARTED)

    # Маршрут данных
    source_agent: Optional[str] = Field(None, description="Агент-источник данных")
    target_agent: Optional[str] = Field(None, description="Агент-получатель результата")

    # Данные операции
    data: OperationData = Field(default_factory=OperationData)

    # Контекстные данные
    correlation_id: Optional[str] = Field(None, description="ID для связи операций")
    session_id: Optional[str] = Field(None, description="ID сессии")

    def set_success(self, output_data: Dict[str, Any], execution_time_ms: Optional[float] = None) -> None:
        """Отметить операцию как успешную."""
        self.status = OperationStatus.SUCCESS
        self.data.output_data = output_data
        if execution_time_ms is not None:
            self.data.execution_time_ms = execution_time_ms

    def set_error(self, error_details: Dict[str, Any], execution_time_ms: Optional[float] = None) -> None:
        """Отметить операцию как завершившуюся с ошибкой."""
        self.status = OperationStatus.ERROR
        self.data.error_details = error_details
        if execution_time_ms is not None:
            self.data.execution_time_ms = execution_time_ms

    def set_timeout(self, timeout_seconds: float) -> None:
        """Отметить операцию как завершившуюся по таймауту."""
        self.status = OperationStatus.TIMEOUT
        self.data.error_details = {"timeout_seconds": timeout_seconds, "reason": "Operation timed out"}

    def set_input_data(self, input_data: Dict[str, Any]) -> None:
        """Установить входные данные операции."""
        self.data.input_data = input_data

    def set_route(self, source: Optional[str] = None, target: Optional[str] = None) -> None:
        """Установить маршрут операции."""
        if source:
            self.source_agent = source
        if target:
            self.target_agent = target

    def add_metadata(self, key: str, value: Any) -> None:
        """Добавить метаданные операции."""
        self.data.metadata[key] = value

    def get_summary(self) -> str:
        """Получить краткое описание операции."""
        route_info = ""
        if self.source_agent and self.target_agent:
            route_info = f" [{self.source_agent} -> {self.target_agent}]"
        elif self.source_agent:
            route_info = f" [from {self.source_agent}]"
        elif self.target_agent:
            route_info = f" [to {self.target_agent}]"

        return f"ОПЕРАЦИЯ: [{self.agent_name}] -> {self.operation_type.value}{route_info}"


class OperationLogger:
    """Логгер операций с форматированием для удобного чтения."""

    def __init__(self, logger: logging.Logger, session_id: Optional[str] = None):
        """
        Инициализация логгера операций.

        Args:
            logger: Базовый логгер
            session_id: ID сессии для группировки операций
        """
        self.logger = logger
        self.session_id = session_id
        self._active_operations: Dict[str, Operation] = {}

    def start_operation(
        self,
        agent_name: str,
        operation_type: OperationType,
        input_data: Optional[Dict[str, Any]] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Operation:
        """
        Начать новую операцию.

        Args:
            agent_name: Имя агента
            operation_type: Тип операции
            input_data: Входные данные
            source_agent: Агент-источник
            target_agent: Агент-получатель
            correlation_id: ID корреляции

        Returns:
            Созданная операция
        """
        operation = Operation(
            agent_name=agent_name,
            operation_type=operation_type,
            source_agent=source_agent,
            target_agent=target_agent,
            correlation_id=correlation_id,
            session_id=self.session_id,
        )

        if input_data:
            operation.set_input_data(input_data)

        self._active_operations[operation.id] = operation

        # Логируем начало операции
        self.logger.info(operation.get_summary())

        # Логируем входные данные
        if input_data:
            input_summary = self._format_data_summary(input_data, "ВХОДНЫЕ ДАННЫЕ")
            self.logger.info(input_summary)

        return operation

    def complete_operation(
        self,
        operation: Operation,
        output_data: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
        execution_time_ms: Optional[float] = None,
        storage_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Завершить операцию.

        Args:
            operation: Операция для завершения
            output_data: Результат операции
            error_details: Детали ошибки
            execution_time_ms: Время выполнения
            storage_snapshot: Снимок состояния хранилища
        """
        if operation.id not in self._active_operations:
            self.logger.warning(f"Attempting to complete unknown operation: {operation.id}")
            return

        # Обновляем статус операции
        if error_details:
            operation.set_error(error_details, execution_time_ms)
            self._log_operation_error(operation, storage_snapshot)
        else:
            operation.set_success(output_data or {}, execution_time_ms)
            self._log_operation_success(operation, storage_snapshot)

        # Удаляем из активных операций
        del self._active_operations[operation.id]

    def _log_operation_success(self, operation: Operation, storage_snapshot: Optional[Dict[str, Any]] = None) -> None:
        """Логировать успешную операцию."""
        # Логируем результат
        if operation.data.output_data:
            result_summary = self._format_data_summary(operation.data.output_data, "РЕЗУЛЬТАТ")
            self.logger.info(result_summary)

        # Логируем время выполнения
        if operation.data.execution_time_ms is not None:
            self.logger.info(f"ВРЕМЯ ВЫПОЛНЕНИЯ: {operation.data.execution_time_ms:.2f}ms")

        # Логируем маршрут если есть
        self._log_operation_route(operation)

        # Логируем состояние хранилища если есть
        if storage_snapshot:
            self._log_storage_snapshot(storage_snapshot)

    def _log_operation_error(self, operation: Operation, storage_snapshot: Optional[Dict[str, Any]] = None) -> None:
        """Логировать операцию с ошибкой (полное логирование)."""
        self.logger.error(f"ОПЕРАЦИЯ ЗАВЕРШИЛАСЬ С ОШИБКОЙ: {operation.get_summary()}")

        # Полное логирование входных данных
        if operation.data.input_data:
            self.logger.error("ПОЛНЫЕ ВХОДНЫЕ ДАННЫЕ:")
            self.logger.error(json.dumps(operation.data.input_data, ensure_ascii=False, indent=2))

        # Детали ошибки
        if operation.data.error_details:
            self.logger.error("ДЕТАЛИ ОШИБКИ:")
            self.logger.error(json.dumps(operation.data.error_details, ensure_ascii=False, indent=2))

        # Метаданные
        if operation.data.metadata:
            self.logger.error("МЕТАДАННЫЕ ОПЕРАЦИИ:")
            self.logger.error(json.dumps(operation.data.metadata, ensure_ascii=False, indent=2))

        # Время выполнения
        if operation.data.execution_time_ms is not None:
            self.logger.error(f"ВРЕМЯ ВЫПОЛНЕНИЯ ДО ОШИБКИ: {operation.data.execution_time_ms:.2f}ms")

        # Маршрут
        self._log_operation_route(operation)

        # Полное состояние хранилища при ошибке
        if storage_snapshot:
            self.logger.error("ПОЛНОЕ СОСТОЯНИЕ ХРАНИЛИЩА НА МОМЕНТ ОШИБКИ:")
            self.logger.error(json.dumps(storage_snapshot, ensure_ascii=False, indent=2))

    def _log_operation_route(self, operation: Operation) -> None:
        """Логировать маршрут операции."""
        route_parts = []
        if operation.source_agent:
            route_parts.append(f"FROM: {operation.source_agent}")
        if operation.target_agent:
            route_parts.append(f"TO: {operation.target_agent}")

        if route_parts:
            self.logger.info("МАРШРУТ: " + " | ".join(route_parts))

        if operation.correlation_id:
            self.logger.info(f"CORRELATION ID: {operation.correlation_id}")

    def _log_storage_snapshot(self, storage_snapshot: Dict[str, Any]) -> None:
        """Логировать снимок состояния хранилища."""
        stats = storage_snapshot.get("stats", {})
        if stats:
            self.logger.info(
                f"AGENT STORAGE: {stats.get('storage_entries', 0)} entries, "
                f"{stats.get('message_queue_size', 0)} pending messages, "
                f"{stats.get('active_sessions', 0)} active sessions"
            )

            # Активные агенты
            agents = stats.get("agents", [])
            if agents:
                self.logger.info(f"ACTIVE AGENTS: {', '.join(agents)}")

    def _format_data_summary(self, data: Dict[str, Any], prefix: str) -> str:
        """
        Отформатировать краткое описание данных.

        Args:
            data: Данные для форматирования
            prefix: Префикс строки

        Returns:
            Отформатированная строка
        """
        if not data:
            return f"{prefix}: {{}}"

        # Создаем краткое описание
        summary_parts = []

        # Извлекаем ключевые поля
        for key, value in list(data.items())[:5]:  # Максимум 5 полей
            if isinstance(value, str):
                # Обрезаем длинные строки
                if len(value) > 100:
                    summary_parts.append(f'"{key}": "{value[:100]}..."')
                else:
                    summary_parts.append(f'"{key}": "{value}"')
            elif isinstance(value, (list, dict)):
                # Для коллекций показываем размер
                summary_parts.append(f'"{key}": {len(value)} items')
            else:
                # Для простых типов показываем значение
                summary_parts.append(f'"{key}": {str(value)[:50]}')

        summary = "{ " + ", ".join(summary_parts)
        if len(data) > 5:
            summary += ", ..."
        summary += " }"

        return f"{prefix}: {summary}"

    def get_active_operations(self) -> List[Operation]:
        """Получить список активных операций."""
        return list(self._active_operations.values())

    def cancel_all_operations(self, reason: str = "Session ended") -> None:
        """Отменить все активные операции."""
        for operation_id in list(self._active_operations.keys()):
            operation = self._active_operations[operation_id]
            operation.set_error({"reason": reason})
            self.logger.warning(f"Operation cancelled: {operation.get_summary()}")

        self._active_operations.clear()


class OperationContext:
    """Контекстный менеджер для автоматического управления операциями."""

    def __init__(
        self,
        operation_logger: OperationLogger,
        agent_name: str,
        operation_type: OperationType,
        input_data: Optional[Dict[str, Any]] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        self.operation_logger = operation_logger
        self.agent_name = agent_name
        self.operation_type = operation_type
        self.input_data = input_data
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.correlation_id = correlation_id

        self.operation: Optional[Operation] = None
        self.start_time: Optional[float] = None
        self.storage_snapshot_provider: Optional[callable] = None

    def set_storage_snapshot_provider(self, provider: callable) -> None:
        """Установить провайдер снимков состояния хранилища."""
        self.storage_snapshot_provider = provider

    def __enter__(self) -> Operation:
        """Начать операцию при входе в контекст."""
        import time
        self.start_time = time.time()

        self.operation = self.operation_logger.start_operation(
            agent_name=self.agent_name,
            operation_type=self.operation_type,
            input_data=self.input_data,
            source_agent=self.source_agent,
            target_agent=self.target_agent,
            correlation_id=self.correlation_id,
        )

        return self.operation

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Завершить операцию при выходе из контекста."""
        import time
        execution_time = None
        if self.start_time:
            execution_time = (time.time() - self.start_time) * 1000  # в миллисекундах

        storage_snapshot = None
        if self.storage_snapshot_provider:
            try:
                storage_snapshot = self.storage_snapshot_provider()
            except Exception as e:
                self.operation_logger.logger.warning(f"Failed to get storage snapshot: {e}")

        if exc_type is not None:
            # Было исключение - логируем как ошибку
            error_details = {
                "exception_type": exc_type.__name__ if exc_type else "Unknown",
                "exception_message": str(exc_val) if exc_val else "Unknown error",
            }

            # Добавляем traceback для отладки
            if exc_tb:
                import traceback
                error_details["traceback"] = traceback.format_exception(exc_type, exc_val, exc_tb)

            self.operation_logger.complete_operation(
                operation=self.operation,
                error_details=error_details,
                execution_time_ms=execution_time,
                storage_snapshot=storage_snapshot,
            )
        else:
            # Исключений не было - успешное завершение
            output_data = {}
            if hasattr(self, '_result_data'):
                output_data = self._result_data

            self.operation_logger.complete_operation(
                operation=self.operation,
                output_data=output_data,
                execution_time_ms=execution_time,
                storage_snapshot=storage_snapshot,
            )

    def set_result(self, result_data: Dict[str, Any]) -> None:
        """Установить результат операции."""
        if self.operation:
            self._result_data = result_data