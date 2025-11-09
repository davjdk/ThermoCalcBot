"""
Centralized error handling for Telegram bot.

This module provides comprehensive error categorization, graceful degradation,
and user-friendly error messages for all types of system failures.
"""

import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass
import asyncio

from ..models.security import ErrorCategory, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class ErrorContext:
    """Context information for error handling"""
    user_id: Optional[int] = None
    username: Optional[str] = None
    query: Optional[str] = None
    component: Optional[str] = None
    operation: Optional[str] = None
    is_debug_mode: bool = False
    additional_data: Optional[Dict[str, Any]] = None


@dataclass
class ErrorStatistics:
    """Statistics for error tracking"""
    total_errors: int = 0
    errors_by_category: Dict[str, int] = None
    errors_by_component: Dict[str, int] = None
    recent_errors: List[Dict[str, Any]] = None
    first_error_time: Optional[datetime] = None
    last_error_time: Optional[datetime] = None

    def __post_init__(self):
        if self.errors_by_category is None:
            self.errors_by_category = {}
        if self.errors_by_component is None:
            self.errors_by_component = {}
        if self.recent_errors is None:
            self.recent_errors = []


class ErrorHandler:
    """
    Centralized error handling system for Telegram bot.

    Features:
    - Error categorization and routing
    - Graceful degradation strategies
    - User-friendly error messages
    - Error statistics and tracking
    - Debug information for developers
    - Recovery suggestions
    """

    def __init__(self):
        self.error_stats = ErrorStatistics()
        self.error_messages = self._init_error_messages()
        self.recovery_strategies = self._init_recovery_strategies()
        self.critical_error_threshold = 10  # Errors per minute
        self.error_time_window = 60  # seconds

    def _init_error_messages(self) -> Dict[ErrorCategory, str]:
        """Initialize user-friendly error messages."""
        return {
            ErrorCategory.USER_INPUT: "😔 *Неверный формат запроса*\n\nПопробуйте переформулировать запрос или используйте /help для справки.",
            ErrorCategory.LLM_API: "🤖 *Сервис временно недоступен*\n\nПопробуйте повторить запрос через минуту. Если проблема persists, используйте /examples.",
            ErrorCategory.DATABASE: "🗄️ *База данных временно недоступна*\n\nПопробуйте позже или используйте /examples для просмотра примеров.",
            ErrorCategory.TELEGRAM_API: "📱 *Ошибка Telegram API*\n\nПопробуйте повторить запрос. Если ошибка продолжается, обратитесь к администратору.",
            ErrorCategory.FILESYSTEM: "📁 *Ошибка файловой системы*\n\nНе удалось обработать файлы. Попробуйте отправить запрос заново.",
            ErrorCategory.SYSTEM: "⚙️ *Внутренняя ошибка системы*\n\nМы уже работаем над исправлением. Попробуйте позже.",
            ErrorCategory.SECURITY: "🔒 *Ошибка безопасности*\n\nВаш запрос был заблокирован по соображениям безопасности. Проверьте формат запроса.",
            ErrorCategory.RATE_LIMIT: "⏱️ *Слишком много запросов*\n\nПожалуйста, подождите некоторое время перед следующим запросом.",
            ErrorCategory.TIMEOUT: "⏰ *Превышено время ожидания*\n\nЗапрос занял слишком много времени. Попробуйте упростить запрос.",
            ErrorCategory.VALIDATION: "✋ *Ошибка валидации*\n\nПроверьте правильность введённых данных и попробуйте снова."
        }

    def _init_recovery_strategies(self) -> Dict[ErrorCategory, List[str]]:
        """Initialize recovery strategies for different error types."""
        return {
            ErrorCategory.USER_INPUT: [
                "• Используйте правильный формат химических формул (H2O, CO2)",
                "• Укажите температуру в Кельвинах (K) или Цельсиях (°C)",
                "• Для реакций используйте формат: '2 H2 + O2 → 2 H2O'",
                "• Попробуйте /examples для просмотра примеров"
            ],
            ErrorCategory.LLM_API: [
                "• Подождите 1-2 минуты и повторите запрос",
                "• Упростите запрос (меньше соединений, простой температурный диапазон)",
                "• Используйте более простые химические формулы",
                "• Проверьте подключение к интернету"
            ],
            ErrorCategory.DATABASE: [
                "• Подождите несколько минут и повторите запрос",
                "• Используйте распространённые соединения (H2O, CO2, NH3)",
                "• Попробуйте указать температуру 298K (25°C)",
                "• Используйте /examples для готовых примеров"
            ],
            ErrorCategory.TELEGRAM_API: [
                "• Проверьте интернет-соединение",
                "• Попробуйте перезапустить Telegram",
                "• Обратитесь к администратору @username",
                "• Попробуйте отправить запрос через несколько минут"
            ],
            ErrorCategory.FILESYSTEM: [
                "• Проверьте, что файл не повреждён",
                "• Убедитесь, что файл имеет правильный формат",
                "• Попробуйте отправить запрос текстом",
                "• Обратитесь к администратору если проблема persists"
            ],
            ErrorCategory.SYSTEM: [
                "• Подождите 5-10 минут",
                "• Попробуйте более простой запрос",
                "• Используйте /help для получения справки",
                "• Сообщите о проблеме администратору"
            ],
            ErrorCategory.SECURITY: [
                "• Уберите из запроса HTML теги и JavaScript",
                "• Не используйте ссылки и URL",
                "• Проверьте правильность химических формул",
                "• Используйте только символы для химических формул"
            ],
            ErrorCategory.RATE_LIMIT: [
                "• Подождите 1-2 минуты",
                "• Используйте более точные запросы",
                "• Сгруппируйте несколько вопросов в один запрос",
                "• Проверьте /status для информации о лимитах"
            ],
            ErrorCategory.TIMEOUT: [
                "• Упростите запрос (меньше соединений)",
                "• Используйте более узкий температурный диапазон",
                "• Уменьшите шаг температуры",
                "• Разделите сложный запрос на несколько простых"
            ],
            ErrorCategory.VALIDATION: [
                "• Проверьте правильность химических формул",
                "• Убедитесь, что температура в допустимом диапазоне (0-10000K)",
                "• Проверьте балансировку химических реакций",
                "• Используйте правильные символы и формат"
            ]
        }

    async def handle_error(
        self,
        error: Exception,
        context: ErrorContext
    ) -> str:
        """
        Handle an error and return user-friendly message.

        Args:
            error: The exception that occurred
            context: Error context information

        Returns:
            User-friendly error message
        """
        # Categorize the error
        category = self._categorize_error(error)

        # Update error statistics
        self._update_error_stats(category, error, context)

        # Log the error
        self._log_error(error, category, context)

        # Get user message
        user_message = self.error_messages.get(category, self.error_messages[ErrorCategory.SYSTEM])

        # Add recovery suggestions
        recovery_suggestions = self.recovery_strategies.get(category, [])
        if recovery_suggestions:
            user_message += "\n\n*Что можно попробовать:*\n" + "\n".join(recovery_suggestions[:3])

        # Add debug information if in debug mode
        if context.is_debug_mode:
            user_message += f"\n\n`Debug info: {type(error).__name__}: {str(error)}`"

        # Check for critical error conditions
        await self._check_critical_conditions(category)

        return user_message

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type and message."""
        error_message = str(error).lower()
        error_type = type(error).__name__

        # Security and validation errors
        if any(keyword in error_message for keyword in ["forbidden", "validation", "sanitization", "security"]):
            return ErrorCategory.SECURITY
        elif "validation" in error_message or "extract" in error_message:
            return ErrorCategory.VALIDATION
        elif "rate limit" in error_message or "too many requests" in error_message:
            return ErrorCategory.RATE_LIMIT
        elif "timeout" in error_message or "timed out" in error_message:
            return ErrorCategory.TIMEOUT

        # LLM API errors
        elif any(keyword in error_message for keyword in ["openrouter", "llm", "anthropic", "openai", "api"]):
            return ErrorCategory.LLM_API

        # Database errors
        elif any(keyword in error_message for keyword in ["database", "sqlite", "sql", "db"]):
            return ErrorCategory.DATABASE

        # Telegram API errors
        elif any(keyword in error_message for keyword in ["telegram", "bot", "chat", "message"]):
            return ErrorCategory.TELEGRAM_API

        # Filesystem errors
        elif any(keyword in error_message for keyword in ["file", "path", "directory", "permission", "disk"]):
            return ErrorCategory.FILESYSTEM

        # User input errors
        elif any(keyword in error_message for keyword in ["input", "parse", "format", "syntax"]):
            return ErrorCategory.USER_INPUT

        # System errors
        else:
            return ErrorCategory.SYSTEM

    def _update_error_stats(
        self,
        category: ErrorCategory,
        error: Exception,
        context: ErrorContext
    ) -> None:
        """Update error statistics."""
        self.error_stats.total_errors += 1

        # Update category statistics
        category_name = category.value
        self.error_stats.errors_by_category[category_name] = self.error_stats.errors_by_category.get(category_name, 0) + 1

        # Update component statistics
        if context.component:
            self.error_stats.errors_by_component[context.component] = self.error_stats.errors_by_component.get(context.component, 0) + 1

        # Update timestamps
        now = datetime.now()
        if self.error_stats.first_error_time is None:
            self.error_stats.first_error_time = now
        self.error_stats.last_error_time = now

        # Add to recent errors
        error_data = {
            "timestamp": now,
            "category": category_name,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_id": context.user_id,
            "component": context.component,
            "query": context.query
        }
        self.error_stats.recent_errors.append(error_data)

        # Keep only last 100 recent errors
        if len(self.error_stats.recent_errors) > 100:
            self.error_stats.recent_errors = self.error_stats.recent_errors[-100:]

    def _log_error(
        self,
        error: Exception,
        category: ErrorCategory,
        context: ErrorContext
    ) -> None:
        """Log the error with context information."""
        log_data = {
            "category": category.value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "user_id": context.user_id,
            "username": context.username,
            "query": context.query,
            "component": context.component,
            "operation": context.operation,
            "traceback": traceback.format_exc() if context.is_debug_mode else None
        }

        # Log with appropriate level
        if category in [ErrorCategory.SECURITY, ErrorCategory.SYSTEM]:
            logger.error(f"Error [{category.value}]: {log_data}")
        elif category in [ErrorCategory.LLM_API, ErrorCategory.DATABASE]:
            logger.warning(f"Error [{category.value}]: {log_data}")
        else:
            logger.info(f"Error [{category.value}]: {log_data}")

    async def _check_critical_conditions(self, category: ErrorCategory) -> None:
        """Check for critical error conditions."""
        if category in [ErrorCategory.SYSTEM, ErrorCategory.DATABASE]:
            # Check if we're getting too many errors in a short time
            recent_critical_errors = [
                error for error in self.error_stats.recent_errors
                if (error["category"] in [ErrorCategory.SYSTEM.value, ErrorCategory.DATABASE.value] and
                    (datetime.now() - error["timestamp"]).total_seconds() < self.error_time_window)
            ]

            if len(recent_critical_errors) >= self.critical_error_threshold:
                logger.critical(f"CRITICAL: {len(recent_critical_errors)} critical errors in {self.error_time_window}s")
                # Here you could implement additional emergency measures
                # like switching to maintenance mode or notifying administrators

    def get_error_statistics(self) -> Dict[str, Any]:
        """Get comprehensive error statistics."""
        return {
            "total_errors": self.error_stats.total_errors,
            "errors_by_category": self.error_stats.errors_by_category.copy(),
            "errors_by_component": self.error_stats.errors_by_component.copy(),
            "first_error_time": self.error_stats.first_error_time.isoformat() if self.error_stats.first_error_time else None,
            "last_error_time": self.error_stats.last_error_time.isoformat() if self.error_stats.last_error_time else None,
            "recent_errors_count": len(self.error_stats.recent_errors),
            "error_rate_per_minute": self._calculate_error_rate()
        }

    def _calculate_error_rate(self) -> float:
        """Calculate current error rate per minute."""
        if not self.error_stats.recent_errors:
            return 0.0

        now = datetime.now()
        recent_errors = [
            error for error in self.error_stats.recent_errors
            if (now - error["timestamp"]).total_seconds() < 60  # Last minute
        ]

        return len(recent_errors) / 1.0  # Per minute

    def get_recent_errors(
        self,
        limit: int = 20,
        category: Optional[str] = None,
        component: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent errors with optional filtering."""
        errors = self.error_stats.recent_errors.copy()

        # Filter by category
        if category:
            errors = [e for e in errors if e["category"] == category]

        # Filter by component
        if component:
            errors = [e for e in errors if e["component"] == component]

        # Sort by timestamp (newest first) and limit
        errors.sort(key=lambda x: x["timestamp"], reverse=True)
        return errors[:limit]

    def clear_error_history(self, older_than_hours: int = 24) -> None:
        """Clear error history older than specified hours."""
        cutoff_time = datetime.now() - timedelta(hours=older_than_hours)

        self.error_stats.recent_errors = [
            error for error in self.error_stats.recent_errors
            if error["timestamp"] >= cutoff_time
        ]

    def reset_statistics(self) -> None:
        """Reset all error statistics."""
        self.error_stats = ErrorStatistics()

    def get_health_status(self) -> Dict[str, Any]:
        """Get system health status based on errors."""
        total_errors = self.error_stats.total_errors
        error_rate = self._calculate_error_rate()

        # Determine health status
        if error_rate == 0:
            health_status = "excellent"
        elif error_rate < 1:
            health_status = "good"
        elif error_rate < 5:
            health_status = "degraded"
        else:
            health_status = "poor"

        # Check for critical error patterns
        critical_categories = [ErrorCategory.SYSTEM.value, ErrorCategory.DATABASE.value]
        critical_errors = sum(
            count for category, count in self.error_stats.errors_by_category.items()
            if category in critical_categories
        )

        return {
            "health_status": health_status,
            "total_errors": total_errors,
            "error_rate_per_minute": error_rate,
            "critical_errors": critical_errors,
            "most_common_category": max(self.error_stats.errors_by_category.items(), key=lambda x: x[1])[0] if self.error_stats.errors_by_category else None,
            "most_problematic_component": max(self.error_stats.errors_by_component.items(), key=lambda x: x[1])[0] if self.error_stats.errors_by_component else None
        }


class GracefulDegradationHandler:
    """Handler for graceful degradation when components fail."""

    def __init__(self):
        self.degradation_strategies = {
            "llm_unavailable": self._handle_llm_unavailable,
            "database_unavailable": self._handle_database_unavailable,
            "filesystem_unavailable": self._handle_filesystem_unavailable,
            "high_load": self._handle_high_load
        }

    async def handle_degradation(
        self,
        issue_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle system degradation."""
        if issue_type in self.degradation_strategies:
            return await self.degradation_strategies[issue_type](context)
        else:
            return {"success": False, "message": f"Unknown degradation type: {issue_type}"}

    async def _handle_llm_unavailable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LLM service unavailability."""
        # Fallback to template-based responses
        fallback_responses = {
            "H2O": "Данные по воде доступны в базе данных. Используйте формат 'H2O свойства 298K'.",
            "CO2": "Данные по CO2 доступны. Попробуйте 'CO2 таблица 300-500K'.",
            "default": "LLM сервис временно недоступен. Используйте простые формулы типа 'H2O свойства 298K'."
        }

        query = context.get("query", "").upper()
        for compound in fallback_responses:
            if compound in query:
                return {
                    "success": True,
                    "response": fallback_responses[compound],
                    "fallback_mode": True
                }

        return {
            "success": True,
            "response": fallback_responses["default"],
            "fallback_mode": True
        }

    async def _handle_database_unavailable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle database unavailability."""
        return {
            "success": True,
            "response": "🗄️ База данных временно недоступна. Попробуйте позже или используйте /examples.",
            "fallback_mode": True
        }

    async def _handle_filesystem_unavailable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle filesystem issues."""
        return {
            "success": True,
            "response": "📁 Проблемы с файловой системой. Ответы будут предоставлены в текстовом формате.",
            "fallback_mode": True
        }

    async def _handle_high_load(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle high system load."""
        return {
            "success": True,
            "response": "⚡ Система под высокой нагрузкой. Запрос будет обработан с задержкой.",
            "fallback_mode": True,
            "delay_suggested": 5
        }