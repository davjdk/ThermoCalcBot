"""
Security and monitoring models for Telegram bot.

This module contains Pydantic models for security validation,
monitoring metrics, and error handling.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import time


@dataclass
class ValidationResult:
    """Result of input validation"""
    is_valid: bool
    message: str
    sanitized_query: Optional[str] = None


@dataclass
class SecurityContext:
    """Security context for request processing"""
    user_id: int
    username: Optional[str]
    chat_id: int
    request_count: int = 0
    last_request_time: float = 0.0
    is_blocked: bool = False
    block_reason: Optional[str] = None
    block_expires: Optional[float] = None


class ErrorCategory(Enum):
    """Categories of errors for handling"""
    USER_INPUT = "user_input"
    LLM_API = "llm_api"
    DATABASE = "database"
    TELEGRAM_API = "telegram_api"
    FILESYSTEM = "filesystem"
    SYSTEM = "system"


@dataclass
class SecurityMetrics:
    """Security-related metrics"""
    blocked_requests: int = 0
    validation_failures: int = 0
    rate_limit_hits: int = 0
    suspicious_patterns: int = 0
    last_security_event: Optional[datetime] = None


@dataclass
class BotPerformanceMetrics:
    """Performance metrics for the bot"""
    request_count: int = 0
    successful_requests: int = 0
    error_count: int = 0
    avg_response_time: float = 0.0
    active_sessions: int = 0
    start_time: float = 0.0

    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass
class AlertData:
    """Data for an alert notification"""
    alert_type: str
    severity: str  # "low", "medium", "high", "critical"
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    resolved: bool = False


@dataclass
class UserActivity:
    """User activity tracking"""
    user_id: int
    username: Optional[str]
    request_count: int = 0
    first_request: Optional[datetime] = None
    last_request: Optional[datetime] = None
    total_processing_time: float = 0.0
    errors: int = 0
    blocked: bool = False


@dataclass
class QueryStatistics:
    """Statistics for query analytics"""
    query: str
    count: int = 1
    avg_processing_time: float = 0.0
    success_rate: float = 1.0
    last_used: Optional[datetime] = None
    compounds_mentioned: List[str] = None
    is_reaction_query: bool = False

    def __post_init__(self):
        if self.compounds_mentioned is None:
            self.compounds_mentioned = []
        if self.last_used is None:
            self.last_used = datetime.now()


class SecurityConfig:
    """Configuration for security settings"""

    def __init__(
        self,
        max_query_length: int = 1000,
        max_requests_per_minute: int = 30,
        max_requests_per_hour: int = 200,
        block_duration_minutes: int = 60,
        enable_rate_limiting: bool = True,
        enable_input_validation: bool = True,
        admin_user_ids: List[int] = None,
        blocked_user_ids: List[int] = None,
        alert_thresholds: Dict[str, float] = None
    ):
        self.max_query_length = max_query_length
        self.max_requests_per_minute = max_requests_per_minute
        self.max_requests_per_hour = max_requests_per_hour
        self.block_duration_minutes = block_duration_minutes
        self.enable_rate_limiting = enable_rate_limiting
        self.enable_input_validation = enable_input_validation
        self.admin_user_ids = admin_user_ids or []
        self.blocked_user_ids = blocked_user_ids or []

        # Default alert thresholds
        self.alert_thresholds = alert_thresholds or {
            "error_rate_percent": 10.0,
            "memory_usage_percent": 80.0,
            "disk_space_gb": 1.0,
            "response_time_seconds": 30.0,
            "security_events_per_hour": 50
        }


class MonitoringConfig:
    """Configuration for monitoring settings"""

    def __init__(
        self,
        enable_metrics: bool = True,
        enable_health_checks: bool = True,
        enable_alerts: bool = True,
        enable_analytics: bool = True,
        metrics_retention_days: int = 30,
        health_check_interval_seconds: int = 300,  # 5 minutes
        alert_cooldown_seconds: int = 300,  # 5 minutes
        log_level: str = "INFO"
    ):
        self.enable_metrics = enable_metrics
        self.enable_health_checks = enable_health_checks
        self.enable_alerts = enable_alerts
        self.enable_analytics = enable_analytics
        self.metrics_retention_days = metrics_retention_days
        self.health_check_interval_seconds = health_check_interval_seconds
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.log_level = log_level