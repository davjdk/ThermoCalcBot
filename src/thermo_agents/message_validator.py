"""
Валидатор сообщений для Agent-to-Agent коммуникации.

Обеспечивает проверку целостности и корректности сообщений
между агентами в системе термодинамических агентов v2.0.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from .agent_storage import AgentMessage


class MessageType(Enum):
    """Типы сообщений в системе."""
    GENERATE_QUERY = "generate_query"
    GENERATE_INDIVIDUAL_QUERY = "generate_individual_query"
    EXECUTE_SQL = "execute_sql"
    EXECUTE_INDIVIDUAL_SQL = "execute_individual_sql"
    FILTER_RESULTS = "filter_results"
    FILTER_INDIVIDUAL_RESULTS = "filter_individual_results"
    SQL_EXECUTED = "sql_executed"
    RESULTS_FILTERED = "results_filtered"
    INDIVIDUAL_SQL_COMPLETE = "individual_sql_complete"
    INDIVIDUAL_FILTER_COMPLETE = "individual_filter_complete"
    ERROR = "error"
    RESPONSE = "response"


class ValidationResult(Enum):
    """Результаты валидации."""
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationError:
    """Описание ошибки валидации."""
    field: str
    message: str
    severity: ValidationResult


@dataclass
class ValidationReport:
    """Отчет о валидации сообщения."""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    message_type: str
    source_agent: str
    target_agent: str


class MessageValidator:
    """Валидатор сообщений между агентами."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Инициализация валидатора.

        Args:
            logger: Логгер для записи ошибок валидации
        """
        self.logger = logger or logging.getLogger(__name__)

        # Определяем обязательные поля для каждого типа сообщения
        self.required_fields = {
            MessageType.GENERATE_QUERY.value: {
                "sql_hint": str,
                "extracted_params": dict,
            },
            MessageType.GENERATE_INDIVIDUAL_QUERY.value: {
                "compound": str,
                "common_params": dict,
            },
            MessageType.EXECUTE_SQL.value: {
                "sql_query": str,
                "extracted_params": dict,
            },
            MessageType.EXECUTE_INDIVIDUAL_SQL.value: {
                "sql_query": str,
                "compound": str,
                "common_params": dict,
            },
            MessageType.FILTER_RESULTS.value: {
                "execution_result": dict,
                "extracted_params": dict,
            },
            MessageType.FILTER_INDIVIDUAL_RESULTS.value: {
                "execution_result": dict,
                "compound": str,
                "common_params": dict,
            },
            MessageType.SQL_EXECUTED.value: {
                "status": str,
                "result_key": str,
                "execution_result": dict,
            },
            MessageType.RESULTS_FILTERED.value: {
                "status": str,
                "result_key": str,
                "filtered_result": dict,
            },
            MessageType.INDIVIDUAL_SQL_COMPLETE.value: {
                "status": str,
                "result_key": str,
                "sql_result": dict,
            },
            MessageType.INDIVIDUAL_FILTER_COMPLETE.value: {
                "status": str,
                "result_key": str,
                "filtered_result": dict,
            },
            MessageType.ERROR.value: {
                "status": str,
                "error": str,
            },
            MessageType.RESPONSE.value: {
                "status": str,
                "result_key": str,
            },
        }

        # Определяем допустимые типы значений для полей
        self.field_types = {
            "sql_query": str,
            "sql_hint": str,
            "compound": str,
            "status": str,
            "result_key": str,
            "error": str,
            "extracted_params": dict,
            "common_params": dict,
            "execution_result": dict,
            "filtered_result": dict,
            "sql_result": dict,
        }

    def validate_message(self, message: AgentMessage) -> ValidationReport:
        """
        Валидация сообщения.

        Args:
            message: Сообщение для валидации

        Returns:
            Отчет о валидации
        """
        errors = []
        warnings = []

        # Базовая валидация структуры сообщения
        base_errors = self._validate_base_structure(message)
        errors.extend(base_errors)

        # Валидация типа сообщения
        if message.message_type not in self.required_fields:
            errors.append(ValidationError(
                field="message_type",
                message=f"Unknown message type: {message.message_type}",
                severity=ValidationResult.ERROR
            ))
        else:
            # Валидация обязательных полей для типа сообщения
            field_errors = self._validate_required_fields(message)
            errors.extend(field_errors)

            # Валидация типов полей
            type_errors = self._validate_field_types(message)
            errors.extend(type_errors)

            # Специализированная валидация для разных типов сообщений
            specialized_warnings = self._validate_specialized_rules(message)
            warnings.extend(specialized_warnings)

        # Валидация размеров данных
        size_warnings = self._validate_data_sizes(message)
        warnings.extend(size_warnings)

        is_valid = len(errors) == 0

        # Логируем результаты валидации
        if errors:
            self.logger.error(f"Message validation failed: {len(errors)} errors in message {message.id}")
            for error in errors:
                self.logger.error(f"  - {error.field}: {error.message}")

        if warnings:
            self.logger.warning(f"Message validation warnings: {len(warnings)} warnings in message {message.id}")
            for warning in warnings:
                self.logger.warning(f"  - {warning.field}: {warning.message}")

        return ValidationReport(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            message_type=message.message_type,
            source_agent=message.source_agent,
            target_agent=message.target_agent
        )

    def _validate_base_structure(self, message: AgentMessage) -> List[ValidationError]:
        """Валидация базовой структуры сообщения."""
        errors = []

        if not message.id:
            errors.append(ValidationError(
                field="id",
                message="Message ID is required",
                severity=ValidationResult.ERROR
            ))

        if not message.source_agent:
            errors.append(ValidationError(
                field="source_agent",
                message="Source agent is required",
                severity=ValidationResult.ERROR
            ))

        if not message.target_agent:
            errors.append(ValidationError(
                field="target_agent",
                message="Target agent is required",
                severity=ValidationResult.ERROR
            ))

        if not message.message_type:
            errors.append(ValidationError(
                field="message_type",
                message="Message type is required",
                severity=ValidationResult.ERROR
            ))

        if not isinstance(message.payload, dict):
            errors.append(ValidationError(
                field="payload",
                message="Payload must be a dictionary",
                severity=ValidationResult.ERROR
            ))

        return errors

    def _validate_required_fields(self, message: AgentMessage) -> List[ValidationError]:
        """Валидация обязательных полей для типа сообщения."""
        errors = []
        required = self.required_fields.get(message.message_type, {})

        for field_name, expected_type in required.items():
            if field_name not in message.payload:
                errors.append(ValidationError(
                    field=field_name,
                    message=f"Required field '{field_name}' is missing for message type '{message.message_type}'",
                    severity=ValidationResult.ERROR
                ))

        return errors

    def _validate_field_types(self, message: AgentMessage) -> List[ValidationError]:
        """Валидация типов полей."""
        errors = []

        for field_name, value in message.payload.items():
            if field_name in self.field_types:
                expected_type = self.field_types[field_name]
                if not isinstance(value, expected_type):
                    errors.append(ValidationError(
                        field=field_name,
                        message=f"Field '{field_name}' must be of type {expected_type.__name__}, got {type(value).__name__}",
                        severity=ValidationResult.ERROR
                    ))

        return errors

    def _validate_specialized_rules(self, message: AgentMessage) -> List[ValidationError]:
        """Специализированная валидация для разных типов сообщений."""
        warnings = []

        # Валидация SQL запросов
        if "sql_query" in message.payload:
            sql_query = message.payload["sql_query"]
            if isinstance(sql_query, str):
                if len(sql_query.strip()) == 0:
                    warnings.append(ValidationError(
                        field="sql_query",
                        message="SQL query is empty",
                        severity=ValidationResult.WARNING
                    ))
                elif len(sql_query.strip()) < 10:
                    warnings.append(ValidationError(
                        field="sql_query",
                        message="SQL query is very short",
                        severity=ValidationResult.WARNING
                    ))

        # Валидация статусов
        if "status" in message.payload:
            status = message.payload["status"]
            valid_statuses = ["success", "error", "no_results", "timeout", "abandoned"]
            if status not in valid_statuses:
                warnings.append(ValidationError(
                    field="status",
                    message=f"Unknown status '{status}', expected one of {valid_statuses}",
                    severity=ValidationResult.WARNING
                ))

        # Валидация execution_result
        if "execution_result" in message.payload:
            exec_result = message.payload["execution_result"]
            if isinstance(exec_result, dict):
                if "success" not in exec_result:
                    warnings.append(ValidationError(
                        field="execution_result",
                        message="execution_result missing 'success' field",
                        severity=ValidationResult.WARNING
                    ))

                if exec_result.get("success") and exec_result.get("row_count", 0) == 0:
                    warnings.append(ValidationError(
                        field="execution_result",
                        message="execution_result reports success but 0 rows",
                        severity=ValidationResult.WARNING
                    ))

        # Валидация extracted_params
        if "extracted_params" in message.payload:
            params = message.payload["extracted_params"]
            if isinstance(params, dict):
                if "compounds" not in params:
                    warnings.append(ValidationError(
                        field="extracted_params",
                        message="extracted_params missing 'compounds' field",
                        severity=ValidationResult.WARNING
                    ))
                elif not isinstance(params["compounds"], list):
                    warnings.append(ValidationError(
                        field="extracted_params.compounds",
                        message="compounds must be a list",
                        severity=ValidationResult.WARNING
                    ))
                elif len(params["compounds"]) == 0:
                    warnings.append(ValidationError(
                        field="extracted_params.compounds",
                        message="compounds list is empty",
                        severity=ValidationResult.WARNING
                    ))

        return warnings

    def _validate_data_sizes(self, message: AgentMessage) -> List[ValidationError]:
        """Валидация размеров данных для предотвращения проблем с производительностью."""
        warnings = []

        # Проверка размера payload
        payload_size = len(str(message.payload))
        if payload_size > 100000:  # 100KB
            warnings.append(ValidationError(
                field="payload",
                message=f"Large payload size: {payload_size} characters",
                severity=ValidationResult.WARNING
            ))

        # Проверка количества результатов
        if "execution_result" in message.payload:
            exec_result = message.payload["execution_result"]
            if isinstance(exec_result, dict) and "row_count" in exec_result:
                row_count = exec_result["row_count"]
                if row_count > 1000:
                    warnings.append(ValidationError(
                        field="execution_result.row_count",
                        message=f"Large result set: {row_count} rows",
                        severity=ValidationResult.WARNING
                    ))

        return warnings

    def validate_and_sanitize(self, message: AgentMessage) -> tuple[AgentMessage, ValidationReport]:
        """
        Валидация и очистка сообщения.

        Args:
            message: Исходное сообщение

        Returns:
            Кортеж (очищенное сообщение, отчет валидации)
        """
        # Выполняем валидацию
        report = self.validate_message(message)

        # Если есть ошибки, не модифицируем сообщение
        if not report.is_valid:
            return message, report

        # Создаем копию сообщения для очистки
        sanitized_message = AgentMessage(
            id=message.id,
            source_agent=message.source_agent,
            target_agent=message.target_agent,
            message_type=message.message_type,
            correlation_id=message.correlation_id,
            timestamp=message.timestamp,
            payload=self._sanitize_payload(message.payload)
        )

        return sanitized_message, report

    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Очистка payload от потенциально проблемных данных."""
        sanitized = {}

        for key, value in payload.items():
            # Очистка строковых полей
            if isinstance(value, str):
                # Удаляем лишние пробелы
                sanitized[key] = value.strip()
            # Ограничиваем размер списков
            elif isinstance(value, list) and len(value) > 1000:
                sanitized[key] = value[:1000]
                self.logger.warning(f"Truncated list '{key}' from {len(value)} to 1000 items")
            else:
                sanitized[key] = value

        return sanitized


def create_message_validator(logger: Optional[logging.Logger] = None) -> MessageValidator:
    """
    Создание валидатора сообщений.

    Args:
        logger: Логгер для записи ошибок

    Returns:
        Настроенный валидатор сообщений
    """
    return MessageValidator(logger=logger)