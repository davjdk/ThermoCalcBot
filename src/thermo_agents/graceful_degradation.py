"""
Модуль graceful degradation для обработки частичных отказов в системе.

Позволяет системе продолжать работать при неполных данных или временных
сбоях отдельных компонентов, предоставляя пользователю информацию о доступности.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from .agent_storage import AgentStorage


class DegradationLevel(Enum):
    """Уровни деградации системы."""
    FULL = "full"  # Полная функциональность
    PARTIAL = "partial"  # Частичная функциональность
    MINIMAL = "minimal"  # Минимальная функциональность
    FALLBACK = "fallback"  # Режим отката с базовыми ответами


class ComponentStatus(Enum):
    """Статусы компонентов системы."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    NO_DATA = "no_data"


@dataclass
class ComponentHealth:
    """Информация о здоровье компонента."""
    component_id: str
    status: ComponentStatus
    last_check: float
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class SystemDegradationReport:
    """Отчет о состоянии деградации системы."""
    degradation_level: DegradationLevel
    affected_components: List[ComponentHealth]
    available_data: Dict[str, Any]
    missing_data: Dict[str, Any]
    user_message: str
    technical_details: Dict[str, Any]
    recovery_suggestions: List[str]


class GracefulDegradationManager:
    """
    Менеджер graceful degradation для обработки отказов компонентов.

    Позволяет системе адаптироваться к проблемам и продолжать работу
    с неполными данными или временными сбоями.
    """

    def __init__(
        self,
        agent_id: str,
        storage: AgentStorage,
        logger: Optional[logging.Logger] = None
    ):
        """
        Инициализация менеджера деградации.

        Args:
            agent_id: ID агента для которого создается менеджер
            storage: Хранилище для сохранения состояния
            logger: Логгер для записи событий
        """
        self.agent_id = agent_id
        self.storage = storage
        self.logger = logger or logging.getLogger(__name__)

        # Отслеживание состояния компонентов
        self.component_health: Dict[str, ComponentHealth] = {}

        # История сбоев для анализа трендов
        self.failure_history: List[Dict[str, Any]] = []

        # Пороговые значения для деградации
        self.thresholds = {
            "max_failed_components": 2,
            "max_timeout_rate": 0.3,  # 30% таймаутов
            "max_no_data_rate": 0.5,  # 50% отсутствия данных
            "health_check_interval": 60,  # секунд
        }

        self.logger.info(f"GracefulDegradationManager initialized for agent {agent_id}")

    def register_component(
        self,
        component_id: str,
        status: ComponentStatus = ComponentStatus.HEALTHY,
        max_retries: int = 3
    ) -> None:
        """
        Регистрация компонента для мониторинга.

        Args:
            component_id: ID компонента
            status: Начальный статус
            max_retries: Максимальное количество повторных попыток
        """
        import time

        self.component_health[component_id] = ComponentHealth(
            component_id=component_id,
            status=status,
            last_check=time.time(),
            max_retries=max_retries
        )

        self.logger.info(f"Component {component_id} registered with status {status.value}")

    def update_component_status(
        self,
        component_id: str,
        status: ComponentStatus,
        error_message: Optional[str] = None
    ) -> None:
        """
        Обновление статуса компонента.

        Args:
            component_id: ID компонента
            status: Новый статус
            error_message: Сообщение об ошибке
        """
        import time

        if component_id not in self.component_health:
            self.register_component(component_id, status)

        component = self.component_health[component_id]
        old_status = component.status

        component.status = status
        component.last_check = time.time()
        component.error_message = error_message

        # Обновляем счетчик попыток при ошибках
        if status in [ComponentStatus.FAILED, ComponentStatus.TIMEOUT]:
            component.retry_count += 1
        elif status == ComponentStatus.HEALTHY:
            component.retry_count = 0

        # Логируем изменение статуса
        if old_status != status:
            self.logger.info(
                f"Component {component_id} status changed: {old_status.value} -> {status.value}"
            )
            if error_message:
                self.logger.warning(f"Component {component_id} error: {error_message}")

            # Сохраняем в историю сбоев
            if status in [ComponentStatus.FAILED, ComponentStatus.TIMEOUT, ComponentStatus.NO_DATA]:
                self.failure_history.append({
                    "component_id": component_id,
                    "status": status.value,
                    "error_message": error_message,
                    "timestamp": time.time(),
                    "retry_count": component.retry_count
                })

    def assess_system_degradation(
        self,
        available_data: Optional[Dict[str, Any]] = None,
        missing_data: Optional[Dict[str, Any]] = None
    ) -> SystemDegradationReport:
        """
        Оценка уровня деградации системы.

        Args:
            available_data: Доступные данные
            missing_data: Отсутствующие данные

        Returns:
            Отчет о деградации системы
        """
        if not available_data:
            available_data = {}
        if not missing_data:
            missing_data = {}

        # Анализируем состояние компонентов
        failed_components = [
            comp for comp in self.component_health.values()
            if comp.status in [ComponentStatus.FAILED, ComponentStatus.TIMEOUT]
        ]
        degraded_components = [
            comp for comp in self.component_health.values()
            if comp.status == ComponentStatus.DEGRADED
        ]
        no_data_components = [
            comp for comp in self.component_health.values()
            if comp.status == ComponentStatus.NO_DATA
        ]

        # Определяем уровень деградации
        total_components = len(self.component_health)
        failed_count = len(failed_components)
        no_data_count = len(no_data_components)

        if total_components == 0:
            degradation_level = DegradationLevel.FULL
        elif failed_count >= self.thresholds["max_failed_components"]:
            degradation_level = DegradationLevel.MINIMAL
        elif no_data_count / max(1, total_components) >= self.thresholds["max_no_data_rate"]:
            degradation_level = DegradationLevel.PARTIAL
        elif failed_components or degraded_components:
            degradation_level = DegradationLevel.PARTIAL
        else:
            degradation_level = DegradationLevel.FULL

        # Формируем сообщение пользователю
        user_message = self._generate_user_message(
            degradation_level, failed_components, no_data_components, missing_data
        )

        # Создаем технические детали
        technical_details = {
            "total_components": total_components,
            "failed_components": len(failed_components),
            "degraded_components": len(degraded_components),
            "no_data_components": len(no_data_components),
            "healthy_components": total_components - failed_count - len(degraded_components) - no_data_count,
            "recent_failures": len([
                f for f in self.failure_history
                if f["timestamp"] > (self.failure_history[-1]["timestamp"] if self.failure_history else 0) - 300  # за 5 минут
            ]) if self.failure_history else 0
        }

        # Генерируем предложения по восстановлению
        recovery_suggestions = self._generate_recovery_suggestions(
            degradation_level, failed_components, no_data_components
        )

        return SystemDegradationReport(
            degradation_level=degradation_level,
            affected_components=failed_components + degraded_components + no_data_components,
            available_data=available_data,
            missing_data=missing_data,
            user_message=user_message,
            technical_details=technical_details,
            recovery_suggestions=recovery_suggestions
        )

    def _generate_user_message(
        self,
        degradation_level: DegradationLevel,
        failed_components: List[ComponentHealth],
        no_data_components: List[ComponentHealth],
        missing_data: Dict[str, Any]
    ) -> str:
        """
        Генерация сообщения для пользователя о текущем состоянии системы.

        Args:
            degradation_level: Уровень деградации
            failed_components: Список отказавших компонентов
            no_data_components: Компоненты без данных
            missing_data: Отсутствующие данные

        Returns:
            Сообщение для пользователя
        """
        if degradation_level == DegradationLevel.FULL:
            return "✅ Все системы работают нормально. Запрос обработан полностью."

        elif degradation_level == DegradationLevel.PARTIAL:
            if no_data_components:
                missing_compounds = list(missing_data.get("compounds", []))
                if missing_compounds:
                    return f"⚠️ Система работает в режиме частичной доступности. " \
                           f"Отсутствуют данные для соединений: {', '.join(missing_compounds)}. " \
                           f"Результаты основаны на доступных данных."
                else:
                    return "⚠️ Система работает в режиме частичной доступности. " \
                           "Некоторые компоненты временно недоступны. Результаты могут быть неполными."

            elif failed_components:
                return "⚠️ Система работает в режиме частичной доступности. " \
                       "Некоторые компоненты временно недоступны. Повторите запрос позже."

            else:
                return "⚠️ Система работает в режиме частичной доступности."

        elif degradation_level == DegradationLevel.MINIMAL:
            return "🚨 Система работает в минимальном режиме. " \
                   "Большинство компонентов недоступны. Функциональность ограничена."

        elif degradation_level == DegradationLevel.FALLBACK:
            return "🔄 Система работает в режиме отката. " \
                   "Используются базовые ответы. Рекомендуется повторить запрос позже."

        return "ℹ️ Система работает с ограничениями."

    def _generate_recovery_suggestions(
        self,
        degradation_level: DegradationLevel,
        failed_components: List[ComponentHealth],
        no_data_components: List[ComponentHealth]
    ) -> List[str]:
        """
        Генерация предложений по восстановлению системы.

        Args:
            degradation_level: Уровень деградации
            failed_components: Отказавшие компоненты
            no_data_components: Компоненты без данных

        Returns:
            Список предложений по восстановлению
        """
        suggestions = []

        if degradation_level in [DegradationLevel.MINIMAL, DegradationLevel.FALLBACK]:
            suggestions.append("Подождите несколько минут и повторите запрос")
            suggestions.append("Проверьте подключение к интернету")
            suggestions.append("Попробуйте упростить запрос (указать fewer compounds)")

        if no_data_components:
            suggestions.append("Проверьте правильность написания химических формул")
            suggestions.append("Попробуйте использовать альтернативные названия соединений")
            suggestions.append("Укажите температурный диапазон, если это возможно")

        if failed_components:
            suggestions.append("Попробуйте повторить запрос через 1-2 минуты")
            suggestions.append("Если проблема повторяется, обратитесь к администратору системы")

        if degradation_level == DegradationLevel.PARTIAL:
            suggestions.append("Система работает с неполными данными, но результаты должны быть корректны")

        return suggestions

    def should_continue_processing(
        self,
        operation_type: str,
        available_data: Dict[str, Any],
        required_data: Dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """
        Определяет, следует ли продолжать обработку при текущем уровне деградации.

        Args:
            operation_type: Тип операции
            available_data: Доступные данные
            required_data: Обязательные данные

        Returns:
            Кортеж (продолжать ли, причина отказа)
        """
        # Оцениваем текущее состояние
        report = self.assess_system_degradation(available_data, required_data)

        # Определяем критические компоненты для разных типов операций
        critical_components = {
            "sql_generation": ["llm_api"],
            "database_query": ["database"],
            "results_filtering": ["llm_api", "database"],
            "thermodynamic_calculation": ["database", "filtering"],
        }

        # Проверяем наличие критических компонентов
        if operation_type in critical_components:
            for critical_comp in critical_components[operation_type]:
                if critical_comp in self.component_health:
                    comp = self.component_health[critical_comp]
                    if comp.status in [ComponentStatus.FAILED, ComponentStatus.TIMEOUT]:
                        if comp.retry_count >= comp.max_retries:
                            return False, f"Critical component {critical_comp} is unavailable after {comp.retry_count} retries"

        # Проверяем уровень деградации
        if report.degradation_level == DegradationLevel.MINIMAL:
            return False, "System is in minimal degradation mode - processing disabled"

        if report.degradation_level == DegradationLevel.FALLBACK:
            return False, "System is in fallback mode - processing disabled"

        return True, None

    def create_fallback_response(
        self,
        original_request: Dict[str, Any],
        degradation_report: SystemDegradationReport
    ) -> Dict[str, Any]:
        """
        Создание fallback ответа при деградации системы.

        Args:
            original_request: Оригинальный запрос
            degradation_report: Отчет о деградации

        Returns:
            Fallback ответ
        """
        fallback_response = {
            "status": "degraded",
            "degradation_level": degradation_report.degradation_level.value,
            "user_message": degradation_report.user_message,
            "recovery_suggestions": degradation_report.recovery_suggestions,
            "available_data": degradation_report.available_data,
            "missing_data": degradation_report.missing_data,
            "technical_details": degradation_report.technical_details,
        }

        # Добавляем специфичные данные в зависимости от типа запроса
        if "compounds" in original_request:
            fallback_response["requested_compounds"] = original_request["compounds"]

        if "temperature_k" in original_request:
            fallback_response["requested_temperature"] = original_request["temperature_k"]

        # Добавляем частичные результаты, если они есть
        if degradation_report.available_data:
            fallback_response["partial_results"] = True
            fallback_response["data_completeness"] = len(degradation_report.available_data) / max(1, len(original_request.get("compounds", [])))

        return fallback_response

    def cleanup_old_failure_history(self, max_age_hours: int = 24) -> None:
        """
        Очистка старой истории сбоев.

        Args:
            max_age_hours: Максимальный возраст записей в часах
        """
        import time

        cutoff_time = time.time() - (max_age_hours * 3600)
        self.failure_history = [
            failure for failure in self.failure_history
            if failure["timestamp"] > cutoff_time
        ]

        self.logger.debug(f"Cleaned up failure history, removed entries older than {max_age_hours} hours")

    def get_component_status(self, component_id: str) -> Optional[ComponentHealth]:
        """
        Получение статуса компонента.

        Args:
            component_id: ID компонента

        Returns:
            Статус компонента или None если не найден
        """
        return self.component_health.get(component_id)

    def reset_component_status(self, component_id: str) -> None:
        """
        Сброс статуса компонента в здоровое состояние.

        Args:
            component_id: ID компонента
        """
        if component_id in self.component_health:
            self.update_component_status(component_id, ComponentStatus.HEALTHY)
            self.logger.info(f"Reset status for component {component_id} to healthy")


def create_graceful_degradation_manager(
    agent_id: str,
    storage: AgentStorage,
    logger: Optional[logging.Logger] = None
) -> GracefulDegradationManager:
    """
    Создание менеджера graceful degradation.

    Args:
        agent_id: ID агента
        storage: Хранилище
        logger: Логгер

    Returns:
        Настроенный менеджер деградации
    """
    return GracefulDegradationManager(
        agent_id=agent_id,
        storage=storage,
        logger=logger
    )