"""
Bot metrics collection and performance monitoring.

This module provides comprehensive metrics collection for the Telegram bot
including performance statistics, user activity tracking, and system health.
"""

import time
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field
import psutil
import asyncio
from pathlib import Path

from ..models.security import (
    BotPerformanceMetrics,
    SecurityMetrics,
    UserActivity,
    QueryStatistics,
    MonitoringConfig
)
from ...thermo_agents.session_logger import SessionLogger


@dataclass
class RequestMetrics:
    """Metrics for a single request"""
    user_id: int
    query_length: int
    processing_time: float
    success: bool
    error_type: Optional[str] = None
    llm_time: Optional[float] = None
    db_time: Optional[float] = None
    calculation_time: Optional[float] = None
    formatting_time: Optional[float] = None


class BotMetrics:
    """
    Comprehensive metrics collection for Telegram bot performance and usage.

    Tracks:
    - Request statistics and success rates
    - Response times and performance
    - User activity and patterns
    - System resource usage
    - Error rates and types
    """

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.performance_metrics = BotPerformanceMetrics()
        self.security_metrics = SecurityMetrics()

        # Request tracking
        self.recent_requests = deque(maxlen=1000)  # Last 1000 requests
        self.hourly_stats = defaultdict(lambda: {"requests": 0, "errors": 0})

        # User activity tracking
        self.user_activities: Dict[int, UserActivity] = {}
        self.active_users = set()

        # Query analytics
        self.query_stats: Dict[str, QueryStatistics] = {}
        self.compound_frequency = defaultdict(int)
        self.reaction_frequency = defaultdict(int)

        # Performance tracking
        self.response_times = deque(maxlen=1000)
        self.error_counts = defaultdict(int)

        # System monitoring
        self.system_stats = {}
        self.last_system_check = 0

        # Thread safety
        self._lock = threading.Lock()

        # Background tasks
        if config.enable_health_checks:
            self._start_background_monitoring()

    def record_request(
        self,
        user_id: int,
        username: Optional[str],
        query: str,
        processing_time: float,
        success: bool,
        error_type: Optional[str] = None,
        timing_breakdown: Optional[Dict[str, float]] = None
    ) -> None:
        """
        Record metrics for a completed request.

        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            query: The processed query
            processing_time: Total processing time in seconds
            success: Whether the request was successful
            error_type: Type of error if unsuccessful
            timing_breakdown: Detailed timing for different stages
        """
        with self._lock:
            # Update performance metrics
            self.performance_metrics.request_count += 1
            if success:
                self.performance_metrics.successful_requests += 1
            else:
                self.performance_metrics.error_count += 1
                self.error_counts[error_type or "unknown"] += 1

            # Update average response time
            self._update_average_response_time(processing_time)
            self.response_times.append(processing_time)

            # Create request metrics
            request_metrics = RequestMetrics(
                user_id=user_id,
                query_length=len(query),
                processing_time=processing_time,
                success=success,
                error_type=error_type,
                llm_time=timing_breakdown.get("llm") if timing_breakdown else None,
                db_time=timing_breakdown.get("database") if timing_breakdown else None,
                calculation_time=timing_breakdown.get("calculation") if timing_breakdown else None,
                formatting_time=timing_breakdown.get("formatting") if timing_breakdown else None
            )

            self.recent_requests.append(request_metrics)

            # Update user activity
            self._update_user_activity(user_id, username, processing_time, success)

            # Update query analytics
            if self.config.enable_analytics:
                self._update_query_analytics(query, success, processing_time)

            # Update hourly statistics
            current_hour = datetime.now().strftime("%Y-%m-%d %H:00")
            self.hourly_stats[current_hour]["requests"] += 1
            if not success:
                self.hourly_stats[current_hour]["errors"] += 1

    def _update_average_response_time(self, processing_time: float) -> None:
        """Update the running average response time."""
        total_requests = self.performance_metrics.request_count
        current_avg = self.performance_metrics.avg_response_time

        # Running average calculation
        self.performance_metrics.avg_response_time = (
            (current_avg * (total_requests - 1) + processing_time) / total_requests
        )

    def _update_user_activity(
        self,
        user_id: int,
        username: Optional[str],
        processing_time: float,
        success: bool
    ) -> None:
        """Update user activity statistics."""
        now = datetime.now()

        if user_id not in self.user_activities:
            self.user_activities[user_id] = UserActivity(
                user_id=user_id,
                username=username,
                first_request=now
            )

        activity = self.user_activities[user_id]
        activity.request_count += 1
        activity.last_request = now
        activity.total_processing_time += processing_time

        if not success:
            activity.errors += 1

        # Update active users
        self.active_users.add(user_id)

        # Clean up inactive users (no activity in last hour)
        self._cleanup_inactive_users()

    def _update_query_analytics(
        self,
        query: str,
        success: bool,
        processing_time: float
    ) -> None:
        """Update query statistics and analytics."""
        # Normalize query for analytics
        normalized_query = self._normalize_query(query)

        if normalized_query not in self.query_stats:
            self.query_stats[normalized_query] = QueryStatistics(
                query=normalized_query,
                count=1,
                avg_processing_time=processing_time,
                success_rate=1.0 if success else 0.0
            )
        else:
            stats = self.query_stats[normalized_query]
            stats.count += 1
            stats.last_used = datetime.now()

            # Update average processing time
            stats.avg_processing_time = (
                (stats.avg_processing_time * (stats.count - 1) + processing_time) / stats.count
            )

            # Update success rate
            if success:
                stats.success_rate = (stats.success_rate * (stats.count - 1) + 1.0) / stats.count
            else:
                stats.success_rate = (stats.success_rate * (stats.count - 1)) / stats.count

    def _normalize_query(self, query: str) -> str:
        """Normalize query for analytics comparison."""
        # Remove extra whitespace and convert to lowercase
        normalized = " ".join(query.lower().split())

        # Replace temperature variations with standard format
        normalized = normalized.replace("k", "K")
        normalized = normalized.replace("°c", "C")
        normalized = normalized.replace("°f", "F")

        return normalized

    def _cleanup_inactive_users(self) -> None:
        """Remove users who haven't been active in the last hour."""
        cutoff_time = datetime.now() - timedelta(hours=1)

        inactive_users = [
            user_id for user_id, activity in self.user_activities.items()
            if activity.last_request and activity.last_request < cutoff_time
        ]

        for user_id in inactive_users:
            del self.user_activities[user_id]
            self.active_users.discard(user_id)

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        with self._lock:
            uptime = time.time() - self.performance_metrics.start_time
            error_rate = (
                (self.performance_metrics.error_count / self.performance_metrics.request_count * 100)
                if self.performance_metrics.request_count > 0 else 0
            )

            # Calculate requests per minute
            requests_per_minute = 0
            if uptime > 0:
                requests_per_minute = self.performance_metrics.request_count / (uptime / 60)

            # Calculate percentiles for response times
            response_times_list = list(self.response_times)
            response_stats = {}
            if response_times_list:
                response_times_list.sort()
                n = len(response_times_list)
                response_stats = {
                    "min": min(response_times_list),
                    "max": max(response_times_list),
                    "p50": response_times_list[n // 2],
                    "p95": response_times_list[int(n * 0.95)] if n > 20 else response_times_list[-1],
                    "p99": response_times_list[int(n * 0.99)] if n > 100 else response_times_list[-1]
                }

            return {
                "uptime_seconds": uptime,
                "total_requests": self.performance_metrics.request_count,
                "successful_requests": self.performance_metrics.successful_requests,
                "error_count": self.performance_metrics.error_count,
                "error_rate_percent": error_rate,
                "success_rate_percent": 100 - error_rate,
                "avg_response_time_seconds": self.performance_metrics.avg_response_time,
                "requests_per_minute": requests_per_minute,
                "active_users": len(self.active_users),
                "total_unique_users": len(self.user_activities),
                "response_time_stats": response_stats
            }

    def get_user_stats(self) -> Dict[str, Any]:
        """Get user activity statistics."""
        with self._lock:
            if not self.user_activities:
                return {
                    "total_users": 0,
                    "active_users": 0,
                    "avg_requests_per_user": 0,
                    "top_users": []
                }

            # Calculate statistics
            total_requests = sum(activity.request_count for activity in self.user_activities.values())
            avg_requests = total_requests / len(self.user_activities)

            # Get top users by request count
            top_users = sorted(
                self.user_activities.values(),
                key=lambda x: x.request_count,
                reverse=True
            )[:10]

            return {
                "total_users": len(self.user_activities),
                "active_users": len(self.active_users),
                "total_requests": total_requests,
                "avg_requests_per_user": avg_requests,
                "top_users": [
                    {
                        "user_id": activity.user_id,
                        "username": activity.username,
                        "requests": activity.request_count,
                        "errors": activity.errors,
                        "success_rate": 1.0 - (activity.errors / activity.request_count) if activity.request_count > 0 else 1.0,
                        "avg_processing_time": activity.total_processing_time / activity.request_count if activity.request_count > 0 else 0,
                        "last_request": activity.last_request.isoformat() if activity.last_request else None
                    }
                    for activity in top_users
                ]
            }

    def get_query_analytics(self, limit: int = 10) -> Dict[str, Any]:
        """Get query analytics and popular queries."""
        with self._lock:
            # Get top queries by frequency
            top_queries = sorted(
                self.query_stats.values(),
                key=lambda x: x.count,
                reverse=True
            )[:limit]

            # Get queries with highest error rates
            problematic_queries = [
                stats for stats in self.query_stats.values()
                if stats.success_rate < 0.8 and stats.count >= 3
            ]
            problematic_queries.sort(key=lambda x: x.success_rate)

            return {
                "top_queries": [
                    {
                        "query": stats.query,
                        "count": stats.count,
                        "avg_processing_time": stats.avg_processing_time,
                        "success_rate": stats.success_rate,
                        "last_used": stats.last_used.isoformat()
                    }
                    for stats in top_queries
                ],
                "problematic_queries": [
                    {
                        "query": stats.query,
                        "count": stats.count,
                        "success_rate": stats.success_rate,
                        "avg_processing_time": stats.avg_processing_time
                    }
                    for stats in problematic_queries[:5]
                ],
                "total_unique_queries": len(self.query_stats),
                "compound_frequency": dict(self.compound_frequency),
                "reaction_frequency": dict(self.reaction_frequency)
            }

    def get_system_stats(self) -> Dict[str, Any]:
        """Get system resource statistics."""
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Get process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()

            return {
                "cpu_percent": cpu_percent,
                "memory": {
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "used_gb": memory.used / (1024**3),
                    "percent": memory.percent
                },
                "disk": {
                    "total_gb": disk.total / (1024**3),
                    "free_gb": disk.free / (1024**3),
                    "used_gb": disk.used / (1024**3),
                    "percent": (disk.used / disk.total) * 100
                },
                "process": {
                    "memory_rss_mb": process_memory.rss / (1024**2),
                    "memory_vms_mb": process_memory.vms / (1024**2),
                    "cpu_percent": process.cpu_percent(),
                    "num_threads": process.num_threads(),
                    "open_files": len(process.open_files())
                }
            }
        except Exception as e:
            return {"error": f"Failed to get system stats: {str(e)}"}

    def get_hourly_stats(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly statistics for the last N hours."""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            hourly_data = []
            for hour_str, stats in self.hourly_stats.items():
                hour_dt = datetime.strptime(hour_str, "%Y-%m-%d %H:00")
                if hour_dt >= cutoff_time:
                    error_rate = (
                        (stats["errors"] / stats["requests"] * 100)
                        if stats["requests"] > 0 else 0
                    )

                    hourly_data.append({
                        "hour": hour_str,
                        "requests": stats["requests"],
                        "errors": stats["errors"],
                        "error_rate_percent": error_rate,
                        "success_rate_percent": 100 - error_rate
                    })

            return sorted(hourly_data, key=lambda x: x["hour"])

    def _start_background_monitoring(self) -> None:
        """Start background system monitoring."""
        def monitor_system():
            while True:
                try:
                    if self.config.enable_metrics:
                        self.system_stats = self.get_system_stats()
                        self.last_system_check = time.time()

                    # Sleep for configured interval
                    time.sleep(self.config.health_check_interval_seconds)
                except Exception as e:
                    # Log error but continue monitoring
                    print(f"System monitoring error: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying

        monitor_thread = threading.Thread(target=monitor_system, daemon=True)
        monitor_thread.start()

    def reset_metrics(self) -> None:
        """Reset all metrics (use with caution)."""
        with self._lock:
            self.performance_metrics = BotPerformanceMetrics()
            self.security_metrics = SecurityMetrics()
            self.recent_requests.clear()
            self.user_activities.clear()
            self.active_users.clear()
            self.query_stats.clear()
            self.response_times.clear()
            self.error_counts.clear()
            self.hourly_stats.clear()
            self.compound_frequency.clear()
            self.reaction_frequency.clear()