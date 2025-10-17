"""
Унифицированный логгер для термодинамических агентов.

Объединяет функциональность SessionLogger и OperationLogger в единый компонент
с поддержкой структурированного логирования, метрик производительности и
операционного отслеживания.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TextIO, Union
from dataclasses import dataclass, field
from pathlib import Path
import uuid


class LogLevel(Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    PERFORMANCE = "PERFORMANCE"


@dataclass
class LogEntry:
    """Запись в логе с метаданными."""
    timestamp: datetime
    level: LogLevel
    session_id: str
    operation_type: Optional[str]
    message: str
    metadata: Dict[str, Any]
    correlation_id: Optional[str] = None
    duration_ms: Optional[float] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Преобразовать в словарь для сериализации."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "session_id": self.session_id,
            "operation_type": self.operation_type,
            "message": self.message,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "duration_ms": self.duration_ms,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
        }

    def to_json(self) -> str:
        """Преобразовать в JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class OperationContext:
    """Контекст операции для отслеживания."""
    operation_id: str
    operation_type: str
    session_id: str
    correlation_id: Optional[str]
    start_time: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    input_data: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None

    def get_duration_ms(self) -> float:
        """Получить длительность операции в миллисекундах."""
        return (time.time() - self.start_time) * 1000


class UnifiedLogger:
    """
    Унифицированный логгер для всех операций системы.

    Объединяет функциональность SessionLogger и OperationLogger с поддержкой:
    - Структурированного логирования
    - Метрик производительности
    - Операционного отслеживания
    - Форматирования вывода
    - Thread-safety
    """

    def __init__(
        self,
        session_id: str,
        log_level: LogLevel = LogLevel.INFO,
        enable_file_logging: bool = True,
        enable_console_logging: bool = True,
        logs_dir: str = "logs/sessions",
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5
    ):
        """
        Инициализация унифицированного логгера.

        Args:
            session_id: ID сессии
            log_level: Уровень логирования
            enable_file_logging: Включить логирование в файл
            enable_console_logging: Включить логирование в консоль
            logs_dir: Директория для логов
            max_file_size: Максимальный размер файла лога
            backup_count: Количество backup файлов
        """
        self.session_id = session_id
        self.log_level = log_level
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging
        self.logs_dir = Path(logs_dir)
        self.max_file_size = max_file_size
        self.backup_count = backup_count

        # Thread safety
        self._lock = threading.RLock()
        self._active_operations: Dict[str, OperationContext] = {}

        # Initialize logging infrastructure
        self._setup_logging()

        # Performance metrics
        self._metrics = {
            "operations_started": 0,
            "operations_completed": 0,
            "operations_failed": 0,
            "total_duration_ms": 0.0,
            "log_entries_count": 0
        }

    def _setup_logging(self):
        """Настроить инфраструктуру логирования."""
        # Создаем logger
        self.logger = logging.getLogger(f"unified_logger_{self.session_id}")
        self.logger.setLevel(self.log_level.value)

        # Очищаем существующие handlers
        self.logger.handlers.clear()

        # Форматирование
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Console handler
        if self.enable_console_logging:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(self.log_level.value)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

        # File handler
        if self.enable_file_logging:
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.logs_dir / f"session_{self.session_id}.log"

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self.log_level.value)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # Структурированный файл логов
        if self.enable_file_logging:
            self.structured_log_file = self.logs_dir / f"structured_{self.session_id}.jsonl"
        else:
            self.structured_log_file = None

    def start_operation(
        self,
        operation_type: str,
        correlation_id: Optional[str] = None,
        **metadata
    ) -> str:
        """
        Начать операцию с таймером.

        Args:
            operation_type: Тип операции
            correlation_id: ID корреляции
            **metadata: Дополнительные метаданные

        Returns:
            ID операции
        """
        operation_id = str(uuid.uuid4())
        operation = OperationContext(
            operation_id=operation_id,
            operation_type=operation_type,
            session_id=self.session_id,
            correlation_id=correlation_id,
            start_time=time.time(),
            metadata=metadata
        )

        with self._lock:
            self._active_operations[operation_id] = operation
            self._metrics["operations_started"] += 1

        self.log(
            LogLevel.INFO,
            f"Started operation: {operation_type}",
            operation_id=operation_id,
            operation_type=operation_type,
            correlation_id=correlation_id,
            **metadata
        )

        return operation_id

    def end_operation(
        self,
        operation_id: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        **metadata
    ):
        """
        Завершить операцию и записать метрики.

        Args:
            operation_id: ID операции
            result: Результат операции
            error: Ошибка операции
            **metadata: Дополнительные метаданные
        """
        with self._lock:
            operation = self._active_operations.pop(operation_id, None)

        if operation is None:
            self.log(LogLevel.WARNING, f"Operation not found: {operation_id}")
            return

        # Обновляем метаданные
        operation.result = result
        operation.error = error
        operation.metadata.update(metadata)
        duration_ms = operation.get_duration_ms()

        # Обновляем метрики
        with self._lock:
            if error:
                self._metrics["operations_failed"] += 1
            else:
                self._metrics["operations_completed"] += 1
            self._metrics["total_duration_ms"] += duration_ms

        # Логируем завершение
        if error:
            self.log(
                LogLevel.ERROR,
                f"Failed operation: {operation.operation_type}",
                operation_id=operation_id,
                operation_type=operation.operation_type,
                correlation_id=operation.correlation_id,
                duration_ms=duration_ms,
                error=str(error),
                error_type=type(error).__name__,
                **metadata
            )
        else:
            self.log(
                LogLevel.INFO,
                f"Completed operation: {operation.operation_type}",
                operation_id=operation_id,
                operation_type=operation.operation_type,
                correlation_id=operation.correlation_id,
                duration_ms=duration_ms,
                **metadata
            )

    def log(
        self,
        level: LogLevel,
        message: str,
        operation_id: Optional[str] = None,
        operation_type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error: Optional[Exception] = None,
        **metadata
    ):
        """
        Записать сообщение с метаданными.

        Args:
            level: Уровень логирования
            message: Сообщение
            operation_id: ID операции
            operation_type: Тип операции
            correlation_id: ID корреляции
            duration_ms: Длительность операции
            error: Ошибка
            **metadata: Дополнительные метаданные
        """
        # Проверяем уровень логирования
        if not self._should_log(level):
            return

        # Создаем запись
        log_entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            session_id=self.session_id,
            operation_type=operation_type,
            message=message,
            metadata=metadata,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            cpu_usage=self._get_cpu_usage(),
            memory_usage=self._get_memory_usage()
        )

        # Добавляем информацию об ошибке
        if error:
            log_entry.metadata["error"] = str(error)
            log_entry.metadata["error_type"] = type(error).__name__

        # Стандартное логирование
        log_message = self._format_log_message(log_entry)
        getattr(self.logger, level.value.lower())(log_message)

        # Структурированное логирование
        if self.structured_log_file:
            self._write_structured_log(log_entry)

        # Обновляем метрики
        with self._lock:
            self._metrics["log_entries_count"] += 1

    def debug(self, message: str, **metadata):
        """DEBUG уровень логирования."""
        self.log(LogLevel.DEBUG, message, **metadata)

    def info(self, message: str, **metadata):
        """INFO уровень логирования."""
        self.log(LogLevel.INFO, message, **metadata)

    def warning(self, message: str, **metadata):
        """WARNING уровень логирования."""
        self.log(LogLevel.WARNING, message, **metadata)

    def error(self, message: str, error: Optional[Exception] = None, **metadata):
        """ERROR уровень логирования."""
        self.log(LogLevel.ERROR, message, error=error, **metadata)

    def performance(
        self,
        operation: str,
        duration_ms: float,
        **metadata
    ):
        """PERFORMANCE уровень логирования."""
        self.log(
            LogLevel.PERFORMANCE,
            f"Performance: {operation}",
            operation_type=operation,
            duration_ms=duration_ms,
            **metadata
        )

    def log_llm_interaction(
        self,
        user_query: str,
        llm_response: Any,
        extracted_params: Any,
        extraction_time_ms: float,
        **metadata
    ):
        """
        Логировать взаимодействие с LLM.

        Args:
            user_query: Запрос пользователя
            llm_response: Ответ LLM
            extracted_params: Извлеченные параметры
            extraction_time_ms: Время извлечения
            **metadata: Дополнительные метаданные
        """
        self.log(
            LogLevel.INFO,
            "LLM interaction completed",
            operation_type="llm_extraction",
            duration_ms=extraction_time_ms,
            user_query_length=len(user_query),
            response_model=type(llm_response).__name__,
            params_model=type(extracted_params).__name__,
            **metadata
        )

    def log_compound_data_table(self, compounds: List[Dict], title: str, **metadata):
        """
        Логировать таблицу данных соединений.

        Args:
            compounds: Список соединений
            title: Заголовок таблицы
            **metadata: Дополнительные метаданные
        """
        self.log(
            LogLevel.INFO,
            f"Compound data table: {title}",
            operation_type="compound_data",
            compounds_count=len(compounds),
            title=title,
            compounds=compounds,  # Может быть большим, но важно для отладки
            **metadata
        )

    def log_search_metadata(self, metadata: Dict, title: str, **additional_metadata):
        """
        Логировать метаданные поиска.

        Args:
            metadata: Метаданные поиска
            title: Заголовок
            **additional_metadata: Дополнительные метаданные
        """
        self.log(
            LogLevel.INFO,
            f"Search metadata: {title}",
            operation_type="search_metadata",
            title=title,
            **metadata,
            **additional_metadata
        )

    def _should_log(self, level: LogLevel) -> bool:
        """Проверить, следует ли логировать сообщение."""
        levels_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.PERFORMANCE: 1,  # INFO level
        }
        return levels_order[level] >= levels_order[self.log_level]

    def _format_log_message(self, entry: LogEntry) -> str:
        """Отформатировать сообщение для стандартного лога."""
        parts = [entry.message]

        if entry.operation_type:
            parts.append(f"[{entry.operation_type}]")

        if entry.correlation_id:
            parts.append(f"(corr: {entry.correlation_id[:8]})")

        if entry.duration_ms is not None:
            parts.append(f"({entry.duration_ms:.1f}ms)")

        return " ".join(parts)

    def _write_structured_log(self, entry: LogEntry):
        """Записать структурированный лог."""
        try:
            with open(self.structured_log_file, 'a', encoding='utf-8') as f:
                f.write(entry.to_json() + '\n')
        except Exception as e:
            # Не должно падать логирование из-за ошибок записи
            self.logger.error(f"Failed to write structured log: {e}")

    def _get_cpu_usage(self) -> Optional[float]:
        """Получить использование CPU."""
        try:
            import psutil
            return psutil.cpu_percent(interval=None)
        except ImportError:
            return None
        except Exception:
            return None

    def _get_memory_usage(self) -> Optional[float]:
        """Получить использование памяти."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_percent()
        except ImportError:
            return None
        except Exception:
            return None

    def get_metrics(self) -> Dict[str, Any]:
        """Получить метрики логгера."""
        with self._lock:
            metrics = self._metrics.copy()
            metrics["active_operations"] = len(self._active_operations)
            metrics["average_duration_ms"] = (
                metrics["total_duration_ms"] / max(1, metrics["operations_completed"])
            )
            return metrics

    def get_active_operations(self) -> List[OperationContext]:
        """Получить список активных операций."""
        with self._lock:
            return list(self._active_operations.values())

    def clear_metrics(self):
        """Очистить метрики."""
        with self._lock:
            self._metrics = {
                "operations_started": 0,
                "operations_completed": 0,
                "operations_failed": 0,
                "total_duration_ms": 0.0,
                "log_entries_count": 0
            }

    def close(self):
        """Закрыть логгер и очистить ресурсы."""
        with self._lock:
            # Завершаем все активные операции
            for operation_id in list(self._active_operations.keys()):
                self.end_operation(
                    operation_id,
                    error=RuntimeError("Logger closed with active operations")
                )

        # Закрываем handlers
        for handler in self.logger.handlers:
            handler.close()
        self.logger.handlers.clear()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Context manager для операций
@dataclass
class OperationTimer:
    """Контекст менеджер для измерения времени операций."""
    logger: UnifiedLogger
    operation_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Exception] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.error = exc_val
        self.logger.end_operation(
            self.operation_id,
            result=self.result,
            error=self.error
        )
        return False  # Не подавлять исключения