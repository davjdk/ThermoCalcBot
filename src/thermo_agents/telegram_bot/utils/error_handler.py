"""
Централизованный обработчик ошибок для Telegram бота.

Классификация ошибок:
- User Input Errors - ошибки ввода пользователя
- System Errors - системные ошибки
- External API Errors - ошибки внешних API
- Critical Errors - критические ошибки

Обеспечивает:
- Graceful degradation
- User-friendly сообщения
- Логирование и мониторинг
- Автоматическое восстановление
"""

import asyncio
import logging
import traceback
from enum import Enum
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

from telegram import Update, Message
from telegram.ext import ContextTypes


class ErrorSeverity(Enum):
    """Уровень серьёзности ошибки."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Категория ошибки."""
    USER_INPUT = "user_input"
    SYSTEM = "system"
    EXTERNAL_API = "external_api"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ErrorInfo:
    """Информация об ошибке."""
    exception: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    user_id: Optional[int]
    context: Dict[str, Any]
    timestamp: datetime
    recovery_suggestions: List[str]
    should_retry: bool
    max_retries: int = 3


@dataclass
class ErrorStatistics:
    """Статистика ошибок."""
    total_errors: int = 0
    errors_by_category: Dict[str, int] = None
    errors_by_severity: Dict[str, int] = None
    recent_errors: List[ErrorInfo] = None

    def __post_init__(self):
        if self.errors_by_category is None:
            self.errors_by_category = {}
        if self.errors_by_severity is None:
            self.errors_by_severity = {}
        if self.recent_errors is None:
            self.recent_errors = []


class TelegramBotErrorHandler:
    """Централизованный обработчик ошибок для Telegram бота."""

    def __init__(self, config, admin_user_id: Optional[int] = None):
        self.config = config
        self.admin_user_id = admin_user_id
        self.logger = logging.getLogger(__name__)

        # Статистика ошибок
        self.statistics = ErrorStatistics()

        # История ошибок для пользователя
        self.user_error_history: Dict[int, List[ErrorInfo]] = {}

        # Пороги для уведомлений администратора
        self.ADMIN_NOTIFICATION_THRESHOLD = 5  # ошибок в час
        self.CRITICAL_ERROR_IMMEDIATE = True

    async def handle_error(
        self,
        error: Exception,
        update: Optional[Update] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool]:
        """
        Основной метод обработки ошибок.

        Args:
            error: Исключение
            update: Telegram Update объект
            context: Telegram контекст
            additional_context: Дополнительный контекст

        Returns:
            Tuple[сообщение для пользователя, нужно ли повторить попытку]
        """
        # Классификация ошибки
        error_info = self._classify_error(error, update, additional_context)

        # Обновление статистики
        self._update_statistics(error_info)

        # Логирование
        await self._log_error(error_info)

        # Проверка на необходимость уведомления администратора
        await self._check_admin_notification(error_info)

        # Создание пользовательского сообщения
        user_message = self._create_user_message(error_info)

        # Определение необходимости повтора
        should_retry = self._should_retry(error_info)

        return user_message, should_retry

    def _classify_error(
        self,
        error: Exception,
        update: Optional[Update] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> ErrorInfo:
        """Классификация ошибки."""
        error_type = type(error).__name__
        error_message = str(error)

        # Определение категории и серьёзности
        category, severity, suggestions, should_retry = self._analyze_error(error)

        # Сбор контекста
        context = {
            "error_type": error_type,
            "error_message": error_message,
            "traceback": traceback.format_exc(),
        }

        if update:
            context.update({
                "user_id": update.effective_user.id if update.effective_user else None,
                "username": update.effective_user.username if update.effective_user else None,
                "message_text": update.message.text if update.message else None,
                "chat_id": update.effective_chat.id if update.effective_chat else None,
            })

        if additional_context:
            context.update(additional_context)

        return ErrorInfo(
            exception=error,
            category=category,
            severity=severity,
            user_id=update.effective_user.id if update and update.effective_user else None,
            context=context,
            timestamp=datetime.now(),
            recovery_suggestions=suggestions,
            should_retry=should_retry
        )

    def _analyze_error(self, error: Exception) -> Tuple[ErrorCategory, ErrorSeverity, List[str], bool]:
        """Анализ ошибки для определения категории и серьёзности."""
        error_message = str(error).lower()
        error_type = type(error).__name__

        # Timeout ошибки
        if "timeout" in error_message or error_type in ["TimeoutError", "asyncio.TimeoutError"]:
            return (
                ErrorCategory.TIMEOUT,
                ErrorSeverity.MEDIUM,
                [
                    "Попробуйте упростить запрос",
                    "Уменьшите температурный диапазон",
                    "Проверьте соединение с интернетом"
                ],
                True
            )

        # Network ошибки
        if any(keyword in error_message for keyword in [
            "connection", "network", "unreachable", "dns", "ssl"
        ]) or error_type in ["ConnectionError", "RequestException"]:
            return (
                ErrorCategory.NETWORK,
                ErrorSeverity.HIGH,
                [
                    "Проверьте подключение к интернету",
                    "Попробуйте повторить запрос позже",
                    "Если проблема сохраняется, свяжитесь с поддержкой"
                ],
                True
            )

        # Rate limiting ошибки
        if "rate limit" in error_message or "too many requests" in error_message:
            return (
                ErrorCategory.RATE_LIMIT,
                ErrorSeverity.MEDIUM,
                [
                    "Подождите некоторое время перед следующим запросом",
                    "Попробуйте более простой запрос",
                    "Лимит запросов: 30 в минуту"
                ],
                False
            )

        # Аутентификация ошибки
        if "unauthorized" in error_message or "auth" in error_message or error_type == "Unauthorized":
            return (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.CRITICAL,
                [
                    "Ошибка аутентификации бота",
                    "Свяжитесь с администратором"
                ],
                False
            )

        # Ошибки API ключей
        if "api key" in error_message or "token" in error_message:
            return (
                ErrorCategory.AUTHENTICATION,
                ErrorSeverity.CRITICAL,
                [
                    "Ошибка конфигурации API",
                    "Свяжитесь с администратором"
                ],
                False
            )

        # Database ошибки
        if "database" in error_message or "sqlite" in error_message or error_type in ["DatabaseError", "OperationalError"]:
            return (
                ErrorCategory.SYSTEM,
                ErrorSeverity.HIGH,
                [
                    "Ошибка доступа к базе данных",
                    "Попробуйте повторить запрос позже",
                    "Если проблема сохраняется, сообщите администратору"
                ],
                True
            )

        # Memory ошибки
        if "memory" in error_message or error_type == "MemoryError":
            return (
                ErrorCategory.SYSTEM,
                ErrorSeverity.HIGH,
                [
                    "Система перегружена",
                    "Попробуйте более простой запрос",
                    "Повторите попытку позже"
                ],
                True
            )

        # LLM API ошибки
        if any(keyword in error_message for keyword in [
            "openrouter", "llm", "model", "api"
        ]) or "openai" in error_message:
            return (
                ErrorCategory.EXTERNAL_API,
                ErrorSeverity.MEDIUM,
                [
                    "Ошибка внешнего сервиса",
                    "Попробуйте повторить запрос позже",
                    "Попробуйте упростить формулировку"
                ],
                True
            )

        # Ошибки парсинга/валидации (пользовательский ввод)
        if any(keyword in error_message for keyword in [
            "invalid", "parse", "format", "validation", "not found"
        ]) or error_type in ["ValueError", "ValidationError"]:
            return (
                ErrorCategory.USER_INPUT,
                ErrorSeverity.LOW,
                [
                    "Проверьте правильность написания формул",
                    "Убедитесь в корректности запроса",
                    "Используйте /help для примеров"
                ],
                False
            )

        # File system ошибки
        if "file" in error_message or "directory" in error_message or error_type in ["FileNotFoundError", "PermissionError"]:
            return (
                ErrorCategory.SYSTEM,
                ErrorSeverity.MEDIUM,
                [
                    "Ошибка файловой системы",
                    "Попробуйте другой запрос",
                    "Сообщите об ошибке если повторяется"
                ],
                True
            )

        # Unknown ошибки
        return (
            ErrorCategory.UNKNOWN,
            ErrorSeverity.HIGH,
            [
                "Произошла неизвестная ошибка",
                "Попробуйте повторить запрос",
                "Сообщите администратору если проблема сохраняется"
            ],
            True
        )

    def _create_user_message(self, error_info: ErrorInfo) -> str:
        """Создание дружелюбного сообщения для пользователя."""
        category_templates = {
            ErrorCategory.USER_INPUT: """❌ *Ошибка в запросе*

{error_message}

💡 *Рекомендации:*
{recovery_suggestions}

📝 *Полезные советы:*
• Используйте правильные химические формулы (H2O, CO2, NH3)
• Указывайте температурный диапазон в формате 298-1000K
• Для реакций используйте формат: A + B → C + D

Используйте /help для примеров запросов.""",

            ErrorCategory.TIMEOUT: """⏱️ *Превышено время ожидания*

{error_message}

🔄 *Попробуйте:*
{recovery_suggestions}

⚡ *Совет:* Сложные запросы требуют больше времени. Попробуйте упростить запрос.""",

            ErrorCategory.NETWORK: """🌐 *Ошибка сети*

{error_message}

{recovery_suggestions}

📡 *Проверьте:* Подключение к интернету и работу VPN если используется.""",

            ErrorCategory.RATE_LIMIT: """⏳ *Слишком много запросов*

{error_message}

{recovery_suggestions}

⚖️ *Лимиты:* 30 запросов в минуту для обеспечения стабильной работы всех пользователей.""",

            ErrorCategory.SYSTEM: """⚙️ *Системная ошибка*

{error_message}

{recovery_suggestions}

🔧 *Информация:* Мы работаем над устранением проблемы. Попробуйте позже.""",

            ErrorCategory.EXTERNAL_API: """🔗 *Ошибка внешнего сервиса*

{error_message}

{recovery_suggestions}

🌐 *Информация:* Проблема со стороны внешних сервисов. Обычно решается быстро.""",

            ErrorCategory.AUTHENTICATION: """🔐 *Ошибка аутентификации*

{error_message}

{recovery_suggestions}

👨‍💼 *Действие:* Сообщите администратору о проблеме.""",

            ErrorCategory.UNKNOWN: """❓ *Неизвестная ошибка*

{error_message}

{recovery_suggestions}

🔍 *Действие:* Попробуйте другой запрос или сообщите администратору."""
        }

        template = category_templates.get(
            error_info.category,
            category_templates[ErrorCategory.UNKNOWN]
        )

        # Форматирование рекомендаций
        suggestions_text = "\n".join(f"• {suggestion}" for suggestion in error_info.recovery_suggestions)

        return template.format(
            error_message=self._sanitize_error_message(str(error_info.exception)),
            recovery_suggestions=suggestions_text
        )

    def _sanitize_error_message(self, message: str) -> str:
        """Очистка сообщения об ошибке для отображения пользователю."""
        # Удаление технических деталей
        sanitized = message

        # Удаление путей файлов
        import re
        sanitized = re.sub(r'[A-Za-z]:\\[^\\s]*', '[путь]', sanitized)
        sanitized = re.sub(r'/[^\\s]*', '[путь]', sanitized)

        # Удаление токенов и ключей
        sanitized = re.sub(r'[a-zA-Z0-9_-]{20,}', '[ключ]', sanitized)

        # Ограничение длины
        if len(sanitized) > 200:
            sanitized = sanitized[:200] + "..."

        return sanitized

    def _should_retry(self, error_info: ErrorInfo) -> bool:
        """Определение, нужно ли повторять попытку."""
        return error_info.should_retry

    def _update_statistics(self, error_info: ErrorInfo) -> None:
        """Обновление статистики ошибок."""
        # Общая статистика
        self.statistics.total_errors += 1

        # По категориям
        category_name = error_info.category.value
        self.statistics.errors_by_category[category_name] = (
            self.statistics.errors_by_category.get(category_name, 0) + 1
        )

        # По серьёзности
        severity_name = error_info.severity.value
        self.statistics.errors_by_severity[severity_name] = (
            self.statistics.errors_by_severity.get(severity_name, 0) + 1
        )

        # История ошибок
        self.statistics.recent_errors.append(error_info)
        if len(self.statistics.recent_errors) > 100:  # храним последние 100 ошибок
            self.statistics.recent_errors.pop(0)

        # История по пользователям
        if error_info.user_id:
            if error_info.user_id not in self.user_error_history:
                self.user_error_history[error_info.user_id] = []

            self.user_error_history[error_info.user_id].append(error_info)
            if len(self.user_error_history[error_info.user_id]) > 10:  # последние 10 ошибок пользователя
                self.user_error_history[error_info.user_id].pop(0)

    async def _log_error(self, error_info: ErrorInfo) -> None:
        """Логирование ошибки."""
        log_level = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
        }.get(error_info.severity, logging.ERROR)

        self.logger.log(
            log_level,
            f"Error [{error_info.category.value}/{error_info.severity.value}]: "
            f"{str(error_info.exception)} (User: {error_info.user_id})"
        )

        # Детальное логирование для отладки
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.logger.debug(f"Error context: {error_info.context}")

    async def _check_admin_notification(self, error_info: ErrorInfo) -> None:
        """Проверка необходимости уведомления администратора."""
        if not self.admin_user_id:
            return

        # Немедленное уведомление для критических ошибок
        if error_info.severity == ErrorSeverity.CRITICAL and self.CRITICAL_ERROR_IMMEDIATE:
            await self._send_admin_notification(error_info, urgent=True)
            return

        # Проверка порога ошибок
        recent_errors = [
            e for e in self.statistics.recent_errors
            if (datetime.now() - e.timestamp).total_seconds() < 3600  # за последний час
        ]

        if len(recent_errors) >= self.ADMIN_NOTIFICATION_THRESHOLD:
            await self._send_admin_notification(error_info, urgent=False)

    async def _send_admin_notification(self, error_info: ErrorInfo, urgent: bool = False) -> None:
        """Отправка уведомления администратору."""
        # Здесь должна быть логика отправки сообщения администратору
        # Например, через Telegram API или другой канал
        pass

    async def send_user_friendly_error(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        error: Exception,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Отправка дружелюбного сообщения об ошибке пользователю."""
        try:
            user_message, should_retry = await self.handle_error(
                error, update, context, additional_context
            )

            if update.message:
                await update.message.reply_text(
                    user_message,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )

        except Exception as e:
            # Fallback при ошибке отправки сообщения об ошибке
            self.logger.critical(f"Failed to send error message: {str(e)}")

    def get_error_statistics(self) -> Dict[str, Any]:
        """Получение статистики ошибок."""
        return {
            "total_errors": self.statistics.total_errors,
            "errors_by_category": dict(self.statistics.errors_by_category),
            "errors_by_severity": dict(self.statistics.errors_by_severity),
            "recent_error_count": len(self.statistics.recent_errors),
            "unique_users_with_errors": len(self.user_error_history),
        }

    def get_user_error_history(self, user_id: int) -> List[ErrorInfo]:
        """Получение истории ошибок пользователя."""
        return self.user_error_history.get(user_id, [])

    def clear_user_history(self, user_id: int) -> bool:
        """Очистка истории ошибок пользователя."""
        if user_id in self.user_error_history:
            del self.user_error_history[user_id]
            return True
        return False

    async def handle_application_error(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE,
        error: Exception
    ) -> None:
        """
        Обработчик ошибок приложения для telegram.ext.

        Этот метод можно зарегистрировать как error_handler для Application.
        """
        try:
            # Определение типа Update
            telegram_update = None
            if hasattr(update, 'effective_user'):
                telegram_update = update

            # Дополнительный контекст
            additional_context = {
                "error_handler": "application_error_handler",
                "context_data": str(context) if context else "No context"
            }

            # Обработка ошибки
            await self.handle_error(
                error,
                telegram_update,
                context,
                additional_context
            )

            # Отправка сообщения пользователю если возможно
            if telegram_update and hasattr(telegram_update, 'message'):
                await self.send_user_friendly_error(
                    telegram_update, context, error, additional_context
                )

        except Exception as e:
            # Критическая ошибка в обработчике ошибок
            self.logger.critical(f"Error handler failed: {str(e)}")
            self.logger.critical(f"Original error: {str(error)}")