"""
Alert management and notification system for Telegram bot.

This module provides comprehensive alerting capabilities for monitoring
system health, performance issues, and security events.
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import threading

from ..models.security import AlertData, SecurityConfig, MonitoringConfig

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Definition of an alert rule"""
    name: str
    condition: str  # Expression to evaluate
    threshold: float
    severity: str  # "low", "medium", "high", "critical"
    enabled: bool = True
    cooldown_seconds: int = 300  # 5 minutes default
    description: str = ""
    last_triggered: Optional[float] = None
    trigger_count: int = 0


@dataclass
class AlertNotification:
    """Alert notification data"""
    alert_id: str
    rule_name: str
    severity: str
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    notification_sent: bool = False


class AlertManager:
    """
    Comprehensive alert management system for Telegram bot monitoring.

    Features:
    - Configurable alert rules and thresholds
    - Cooldown periods to prevent alert spam
    - Multiple severity levels
    - Alert history and tracking
    - Integration with Telegram notifications
    - Performance and security alerts
    """

    def __init__(
        self,
        config: MonitoringConfig,
        security_config: SecurityConfig,
        telegram_bot=None
    ):
        self.config = config
        self.security_config = security_config
        self.telegram_bot = telegram_bot

        # Alert storage
        self.active_alerts: Dict[str, AlertNotification] = {}
        self.alert_history: List[AlertNotification] = []
        self.alert_rules: Dict[str, AlertRule] = {}

        # Alert cooldown tracking
        self.alert_cooldowns: Dict[str, float] = {}

        # Alert statistics
        self.alert_stats = defaultdict(int)
        self.severity_stats = defaultdict(int)

        # Thread safety
        self._lock = threading.Lock()

        # Initialize default alert rules
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default alert rules based on configuration."""
        default_rules = [
            AlertRule(
                name="high_error_rate",
                condition="error_rate_percent",
                threshold=self.security_config.alert_thresholds.get("error_rate_percent", 10.0),
                severity="high",
                cooldown_seconds=600,  # 10 minutes
                description="High error rate detected"
            ),
            AlertRule(
                name="high_memory_usage",
                condition="memory_usage_percent",
                threshold=self.security_config.alert_thresholds.get("memory_usage_percent", 80.0),
                severity="medium",
                cooldown_seconds=300,  # 5 minutes
                description="High memory usage detected"
            ),
            AlertRule(
                name="low_disk_space",
                condition="disk_space_gb",
                threshold=self.security_config.alert_thresholds.get("disk_space_gb", 1.0),
                severity="critical",
                cooldown_seconds=1800,  # 30 minutes
                description="Low disk space detected"
            ),
            AlertRule(
                name="slow_response_time",
                condition="response_time_seconds",
                threshold=self.security_config.alert_thresholds.get("response_time_seconds", 30.0),
                severity="medium",
                cooldown_seconds=300,  # 5 minutes
                description="Slow response time detected"
            ),
            AlertRule(
                name="high_security_events",
                condition="security_events_per_hour",
                threshold=self.security_config.alert_thresholds.get("security_events_per_hour", 50.0),
                severity="high",
                cooldown_seconds=900,  # 15 minutes
                description="High number of security events detected"
            ),
            AlertRule(
                name="database_unhealthy",
                condition="database_status",
                threshold=0.5,  # 0=healthy, 0.5=degraded, 1=unhealthy
                severity="critical",
                cooldown_seconds=300,  # 5 minutes
                description="Database health check failed"
            ),
            AlertRule(
                name="llm_api_unhealthy",
                condition="llm_api_status",
                threshold=0.5,
                severity="high",
                cooldown_seconds=600,  # 10 minutes
                description="LLM API health check failed"
            )
        ]

        for rule in default_rules:
            self.alert_rules[rule.name] = rule

    async def check_and_send_alerts(
        self,
        metrics: Dict[str, Any],
        health_status: Dict[str, Any]
    ) -> List[AlertNotification]:
        """
        Check all alert rules and send notifications if needed.

        Args:
            metrics: Performance metrics
            health_status: Health check results

        Returns:
            List of triggered alerts
        """
        triggered_alerts = []

        for rule_name, rule in self.alert_rules.items():
            if not rule.enabled:
                continue

            try:
                alert = await self._check_rule(rule, metrics, health_status)
                if alert:
                    triggered_alerts.append(alert)
                    await self._handle_alert(alert)

            except Exception as e:
                logger.error(f"Error checking alert rule {rule_name}: {e}")

        return triggered_alerts

    async def _check_rule(
        self,
        rule: AlertRule,
        metrics: Dict[str, Any],
        health_status: Dict[str, Any]
    ) -> Optional[AlertNotification]:
        """Check a single alert rule."""
        # Check cooldown
        if self._is_in_cooldown(rule.name, rule.cooldown_seconds):
            return None

        # Get current value for the condition
        current_value = self._get_metric_value(rule.condition, metrics, health_status)
        if current_value is None:
            return None

        # Check if threshold is exceeded
        threshold_exceeded = False
        if rule.condition in ["error_rate_percent", "memory_usage_percent", "response_time_seconds"]:
            threshold_exceeded = current_value > rule.threshold
        elif rule.condition == "disk_space_gb":
            threshold_exceeded = current_value < rule.threshold
        elif rule.condition in ["database_status", "llm_api_status"]:
            # Convert status string to numeric value
            status_value = self._status_to_numeric(health_status.get("components", {}).get(rule.condition.replace("_status", ""), {}).get("status", "healthy"))
            threshold_exceeded = status_value >= rule.threshold
        else:
            threshold_exceeded = current_value > rule.threshold

        if not threshold_exceeded:
            return None

        # Create alert
        alert_id = f"{rule.name}_{int(time.time())}"
        message = self._generate_alert_message(rule, current_value)
        details = {
            "rule_name": rule.name,
            "current_value": current_value,
            "threshold": rule.threshold,
            "condition": rule.condition,
            "severity": rule.severity,
            "metrics": metrics,
            "health_status": health_status
        }

        alert = AlertNotification(
            alert_id=alert_id,
            rule_name=rule.name,
            severity=rule.severity,
            message=message,
            details=details,
            timestamp=datetime.now()
        )

        # Update rule tracking
        rule.last_triggered = time.time()
        rule.trigger_count += 1

        # Update cooldown
        self.alert_cooldowns[rule.name] = time.time()

        return alert

    def _is_in_cooldown(self, rule_name: str, cooldown_seconds: int) -> bool:
        """Check if an alert rule is in cooldown period."""
        if rule_name not in self.alert_cooldowns:
            return False

        time_since_last = time.time() - self.alert_cooldowns[rule_name]
        return time_since_last < cooldown_seconds

    def _get_metric_value(
        self,
        condition: str,
        metrics: Dict[str, Any],
        health_status: Dict[str, Any]
    ) -> Optional[float]:
        """Extract metric value based on condition."""
        # Performance metrics
        if condition == "error_rate_percent":
            return metrics.get("error_rate_percent", 0)
        elif condition == "response_time_seconds":
            return metrics.get("avg_response_time_seconds", 0)
        elif condition == "security_events_per_hour":
            # This would need to be calculated from security metrics
            return 0  # Placeholder

        # Health status metrics
        elif condition == "memory_usage_percent":
            memory_stats = health_status.get("components", {}).get("memory", {}).get("details", {})
            return memory_stats.get("memory_percent", 0)
        elif condition == "disk_space_gb":
            filesystem_stats = health_status.get("components", {}).get("filesystem", {}).get("details", {})
            return filesystem_stats.get("available_space_gb", 0)

        return None

    def _status_to_numeric(self, status: str) -> float:
        """Convert status string to numeric value."""
        status_map = {
            "healthy": 0.0,
            "degraded": 0.5,
            "unhealthy": 1.0
        }
        return status_map.get(status, 0.0)

    def _generate_alert_message(self, rule: AlertRule, current_value: float) -> str:
        """Generate alert message based on rule and current value."""
        severity_emojis = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴"
        }

        emoji = severity_emojis.get(rule.severity, "⚠️")

        if rule.condition == "error_rate_percent":
            message = f"{emoji} High error rate: {current_value:.1f}% (threshold: {rule.threshold:.1f}%)"
        elif rule.condition == "memory_usage_percent":
            message = f"{emoji} High memory usage: {current_value:.1f}% (threshold: {rule.threshold:.1f}%)"
        elif rule.condition == "disk_space_gb":
            message = f"{emoji} Low disk space: {current_value:.1f}GB available (threshold: {rule.threshold:.1f}GB)"
        elif rule.condition == "response_time_seconds":
            message = f"{emoji} Slow response time: {current_value:.1f}s (threshold: {rule.threshold:.1f}s)"
        elif rule.condition in ["database_status", "llm_api_status"]:
            message = f"{emoji} {rule.description.replace('_', ' ').title()}"
        else:
            message = f"{emoji} {rule.description}: {current_value:.2f} (threshold: {rule.threshold:.2f})"

        return message

    async def _handle_alert(self, alert: AlertNotification) -> None:
        """Handle an alert notification."""
        with self._lock:
            # Store alert
            self.active_alerts[alert.alert_id] = alert
            self.alert_history.append(alert)

            # Update statistics
            self.alert_stats[alert.rule_name] += 1
            self.severity_stats[alert.severity] += 1

        # Send notification
        if self.config.enable_alerts:
            await self._send_notification(alert)

        # Log alert
        logger.warning(
            f"Alert triggered: {alert.rule_name} ({alert.severity}) - {alert.message}"
        )

    async def _send_notification(self, alert: AlertNotification) -> None:
        """Send alert notification via Telegram."""
        if not self.telegram_bot:
            return

        try:
            # Format message for Telegram
            message = f"🚨 *ThermoCalcBot Alert*\n\n"
            message += f"**Severity:** {alert.severity.upper()}\n"
            message += f"**Rule:** {alert.rule_name}\n"
            message += f"**Message:** {alert.message}\n"
            message += f"**Time:** {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"

            # Add details for high and critical alerts
            if alert.severity in ["high", "critical"]:
                details = alert.details
                if "current_value" in details and "threshold" in details:
                    message += f"**Current:** {details['current_value']}\n"
                    message += f"**Threshold:** {details['threshold']}\n"

            # Send to admin users
            admin_users = self.security_config.admin_user_ids
            if admin_users:
                for user_id in admin_users:
                    try:
                        await self.telegram_bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode="Markdown"
                        )
                        alert.notification_sent = True
                    except Exception as e:
                        logger.error(f"Failed to send alert to user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to send alert notification: {e}")

    def add_custom_rule(
        self,
        name: str,
        condition: str,
        threshold: float,
        severity: str,
        description: str = "",
        cooldown_seconds: int = 300
    ) -> None:
        """Add a custom alert rule."""
        rule = AlertRule(
            name=name,
            condition=condition,
            threshold=threshold,
            severity=severity,
            description=description,
            cooldown_seconds=cooldown_seconds
        )
        self.alert_rules[name] = rule

    def remove_rule(self, name: str) -> None:
        """Remove an alert rule."""
        if name in self.alert_rules:
            del self.alert_rules[name]

    def enable_rule(self, name: str) -> None:
        """Enable an alert rule."""
        if name in self.alert_rules:
            self.alert_rules[name].enabled = True

    def disable_rule(self, name: str) -> None:
        """Disable an alert rule."""
        if name in self.alert_rules:
            self.alert_rules[name].enabled = False

    async def resolve_alert(self, alert_id: str, resolved_by: str = "system") -> bool:
        """
        Mark an alert as resolved.

        Args:
            alert_id: ID of the alert to resolve
            resolved_by: Who resolved the alert (user ID or "system")

        Returns:
            True if alert was resolved, False if not found
        """
        with self._lock:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                alert.resolved_at = datetime.now()

                # Move to history and remove from active
                del self.active_alerts[alert_id]

                logger.info(f"Alert {alert_id} resolved by {resolved_by}")
                return True

        return False

    def get_active_alerts(self, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get currently active alerts."""
        with self._lock:
            alerts = []
            for alert in self.active_alerts.values():
                if severity is None or alert.severity == severity:
                    alerts.append({
                        "alert_id": alert.alert_id,
                        "rule_name": alert.rule_name,
                        "severity": alert.severity,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat(),
                        "notification_sent": alert.notification_sent,
                        "details": alert.details
                    })

            return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)

    def get_alert_history(
        self,
        hours: int = 24,
        severity: Optional[str] = None,
        rule_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get alert history for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        with self._lock:
            filtered_alerts = []
            for alert in self.alert_history:
                if alert.timestamp >= cutoff_time:
                    if severity is None or alert.severity == severity:
                        if rule_name is None or alert.rule_name == rule_name:
                            filtered_alerts.append({
                                "alert_id": alert.alert_id,
                                "rule_name": alert.rule_name,
                                "severity": alert.severity,
                                "message": alert.message,
                                "timestamp": alert.timestamp.isoformat(),
                                "resolved": alert.resolved,
                                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                                "notification_sent": alert.notification_sent
                            })

            return sorted(filtered_alerts, key=lambda x: x["timestamp"], reverse=True)

    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        with self._lock:
            total_alerts = len(self.alert_history)
            active_alerts = len(self.active_alerts)
            resolved_alerts = sum(1 for alert in self.alert_history if alert.resolved)

            # Recent alerts (last 24 hours)
            cutoff_time = datetime.now() - timedelta(hours=24)
            recent_alerts = sum(1 for alert in self.alert_history if alert.timestamp >= cutoff_time)

            return {
                "total_alerts": total_alerts,
                "active_alerts": active_alerts,
                "resolved_alerts": resolved_alerts,
                "recent_alerts_24h": recent_alerts,
                "alerts_by_rule": dict(self.alert_stats),
                "alerts_by_severity": dict(self.severity_stats),
                "total_rules": len(self.alert_rules),
                "enabled_rules": sum(1 for rule in self.alert_rules.values() if rule.enabled)
            }

    def get_rule_status(self) -> List[Dict[str, Any]]:
        """Get status of all alert rules."""
        with self._lock:
            rules_status = []
            for rule_name, rule in self.alert_rules.items():
                rules_status.append({
                    "name": rule_name,
                    "enabled": rule.enabled,
                    "severity": rule.severity,
                    "threshold": rule.threshold,
                    "condition": rule.condition,
                    "description": rule.description,
                    "cooldown_seconds": rule.cooldown_seconds,
                    "trigger_count": rule.trigger_count,
                    "last_triggered": rule.last_triggered,
                    "last_triggered_iso": datetime.fromtimestamp(rule.last_triggered).isoformat() if rule.last_triggered else None
                })

            return sorted(rules_status, key=lambda x: x["name"])

    def clear_old_alerts(self, days: int = 30) -> None:
        """Clear old alerts from history."""
        cutoff_time = datetime.now() - timedelta(days=days)

        with self._lock:
            self.alert_history = [
                alert for alert in self.alert_history
                if alert.timestamp >= cutoff_time
            ]

    async def test_alert_system(self) -> Dict[str, Any]:
        """Test the alert system by triggering a test alert."""
        test_alert = AlertNotification(
            alert_id="test_alert",
            rule_name="test_rule",
            severity="low",
            message="🧪 Test alert - Alert system is working correctly",
            details={"test": True},
            timestamp=datetime.now()
        )

        try:
            await self._handle_alert(test_alert)
            return {
                "success": True,
                "message": "Test alert sent successfully",
                "alert_id": test_alert.alert_id
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Test alert failed: {str(e)}"
            }
        finally:
            # Clean up test alert
            await self.resolve_alert(test_alert.alert_id, "test_system")