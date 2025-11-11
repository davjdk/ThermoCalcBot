"""
Rate limiting and access control for Telegram bot.

This module provides comprehensive rate limiting, user access control,
and security monitoring to prevent abuse and ensure fair usage.
"""

import time
import threading
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict, deque

from ..models.security import SecurityConfig, SecurityContext


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_minute: int = 30
    requests_per_hour: int = 200
    requests_per_day: int = 1000
    burst_limit: int = 5  # Maximum requests in 10 seconds
    block_duration_minutes: int = 60
    max_concurrent_requests: int = 3


@dataclass
class UserRateLimit:
    """Rate limiting data for a user"""
    user_id: int
    minute_requests: deque = field(default_factory=lambda: deque(maxlen=100))
    hour_requests: deque = field(default_factory=lambda: deque(maxlen=500))
    day_requests: deque = field(default_factory=lambda: deque(maxlen=2000))
    burst_requests: deque = field(default_factory=lambda: deque(maxlen=20))
    concurrent_requests: int = 0
    last_request_time: float = 0.0
    blocked_until: float = 0.0
    violation_count: int = 0
    total_requests: int = 0


@dataclass
class SecurityEvent:
    """Security event tracking"""
    user_id: int
    event_type: str
    timestamp: datetime
    details: Dict[str, Any]
    severity: str = "medium"  # "low", "medium", "high", "critical"


class RateLimiter:
    """
    Comprehensive rate limiting and access control system.

    Features:
    - Multiple time window rate limiting (minute/hour/day)
    - Burst protection
    - Concurrent request limiting
    - User blocking with automatic expiry
    - Security event tracking
    - Whitelist and blacklist support
    """

    def __init__(self, config: SecurityConfig):
        self.config = config

        # Rate limiting configuration
        self.rate_config = RateLimitConfig(
            requests_per_minute=config.max_requests_per_minute,
            requests_per_hour=config.max_requests_per_hour,
            block_duration_minutes=config.block_duration_minutes
        )

        # User rate limit tracking
        self.user_limits: Dict[int, UserRateLimit] = {}
        self._lock = threading.Lock()

        # Security event tracking
        self.security_events: List[SecurityEvent] = []
        self.violation_stats = defaultdict(int)

        # Access control lists
        self.whitelist_users: Set[int] = set(config.admin_user_ids)
        self.blacklist_users: Set[int] = set(config.blocked_user_ids)

        # Statistics
        self.total_requests = 0
        self.blocked_requests = 0
        self.total_violations = 0

    def is_allowed(
        self,
        user_id: int,
        username: Optional[str] = None,
        check_concurrent: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if a request from a user is allowed.

        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            check_concurrent: Whether to check concurrent request limit

        Returns:
            Tuple of (is_allowed, reason_if_denied)
        """
        with self._lock:
            current_time = time.time()
            self.total_requests += 1

            # Check if user is permanently blocked
            if user_id in self.blacklist_users:
                self._log_security_event(
                    user_id,
                    "blacklisted_user_access_attempt",
                    {"username": username},
                    "high"
                )
                self.blocked_requests += 1
                return False, "User is permanently blocked"

            # Check if user is whitelisted (admin)
            if user_id in self.whitelist_users:
                return True, None

            # Get or create user rate limit data
            if user_id not in self.user_limits:
                self.user_limits[user_id] = UserRateLimit(user_id=user_id)

            user_limit = self.user_limits[user_id]

            # Check if user is temporarily blocked
            if current_time < user_limit.blocked_until:
                remaining_time = int(user_limit.blocked_until - current_time)
                return False, f"User is blocked for {remaining_time} more seconds"

            # Clean old requests from deques
            self._cleanup_old_requests(user_limit, current_time)

            # Check rate limits
            checks = [
                ("minute", len(user_limit.minute_requests), self.rate_config.requests_per_minute),
                ("hour", len(user_limit.hour_requests), self.rate_config.requests_per_hour),
                ("day", len(user_limit.day_requests), self.rate_config.requests_per_day),
                ("burst", len(user_limit.burst_requests), self.rate_config.burst_limit)
            ]

            for period, current_count, limit in checks:
                if current_count >= limit:
                    return self._handle_rate_limit_violation(user_id, username, period, limit, current_time)

            # Check concurrent request limit
            if check_concurrent and user_limit.concurrent_requests >= self.rate_config.max_concurrent_requests:
                return False, f"Too many concurrent requests (max: {self.rate_config.max_concurrent_requests})"

            # Record this request
            self._record_request(user_limit, current_time)

            return True, None

    def _cleanup_old_requests(self, user_limit: UserRateLimit, current_time: float) -> None:
        """Remove old requests from the tracking deques."""
        # Remove requests older than 1 minute
        minute_cutoff = current_time - 60
        while user_limit.minute_requests and user_limit.minute_requests[0] < minute_cutoff:
            user_limit.minute_requests.popleft()

        # Remove requests older than 1 hour
        hour_cutoff = current_time - 3600
        while user_limit.hour_requests and user_limit.hour_requests[0] < hour_cutoff:
            user_limit.hour_requests.popleft()

        # Remove requests older than 1 day
        day_cutoff = current_time - 86400
        while user_limit.day_requests and user_limit.day_requests[0] < day_cutoff:
            user_limit.day_requests.popleft()

        # Remove requests older than 10 seconds (burst)
        burst_cutoff = current_time - 10
        while user_limit.burst_requests and user_limit.burst_requests[0] < burst_cutoff:
            user_limit.burst_requests.popleft()

    def _record_request(self, user_limit: UserRateLimit, current_time: float) -> None:
        """Record a new request for the user."""
        user_limit.minute_requests.append(current_time)
        user_limit.hour_requests.append(current_time)
        user_limit.day_requests.append(current_time)
        user_limit.burst_requests.append(current_time)
        user_limit.last_request_time = current_time
        user_limit.total_requests += 1

    def _handle_rate_limit_violation(
        self,
        user_id: int,
        username: Optional[str],
        period: str,
        limit: int,
        current_time: float
    ) -> Tuple[bool, str]:
        """Handle a rate limit violation."""
        user_limit = self.user_limits[user_id]
        user_limit.violation_count += 1
        self.total_violations += 1

        # Log security event
        self._log_security_event(
            user_id,
            "rate_limit_violation",
            {
                "username": username,
                "period": period,
                "limit": limit,
                "current_count": len(getattr(user_limit, f"{period}_requests")),
                "violation_count": user_limit.violation_count
            },
            "medium" if period == "burst" else "high"
        )

        # Determine block duration based on violation history
        if user_limit.violation_count >= 5:  # Multiple violations
            block_duration = self.rate_config.block_duration_minutes * 2  # Double block time
            severity = "critical"
        elif user_limit.violation_count >= 3:
            block_duration = self.rate_config.block_duration_minutes
            severity = "high"
        else:
            block_duration = self.rate_config.block_duration_minutes // 2  # Half block time
            severity = "medium"

        # Apply block
        user_limit.blocked_until = current_time + (block_duration * 60)
        self.blocked_requests += 1

        # Log block event
        self._log_security_event(
            user_id,
            "user_blocked",
            {
                "username": username,
                "duration_minutes": block_duration,
                "reason": f"Rate limit violation ({period})",
                "violation_count": user_limit.violation_count
            },
            severity
        )

        return False, f"Rate limit exceeded. Blocked for {block_duration} minutes."

    def start_request(self, user_id: int) -> bool:
        """Mark the start of a request processing."""
        with self._lock:
            if user_id not in self.user_limits:
                self.user_limits[user_id] = UserRateLimit(user_id=user_id)

            user_limit = self.user_limits[user_id]

            if user_limit.concurrent_requests >= self.rate_config.max_concurrent_requests:
                return False

            user_limit.concurrent_requests += 1
            return True

    def end_request(self, user_id: int) -> None:
        """Mark the end of a request processing."""
        with self._lock:
            if user_id in self.user_limits:
                self.user_limits[user_id].concurrent_requests = max(
                    0, self.user_limits[user_id].concurrent_requests - 1
                )

    def add_to_whitelist(self, user_id: int) -> None:
        """Add a user to the whitelist."""
        with self._lock:
            self.whitelist_users.add(user_id)
            # Remove from blacklist if present
            self.blacklist_users.discard(user_id)

    def remove_from_whitelist(self, user_id: int) -> None:
        """Remove a user from the whitelist."""
        with self._lock:
            self.whitelist_users.discard(user_id)

    def add_to_blacklist(self, user_id: int, reason: Optional[str] = None) -> None:
        """Add a user to the blacklist."""
        with self._lock:
            self.blacklist_users.add(user_id)
            # Remove from whitelist if present
            self.whitelist_users.discard(user_id)

            # Log event
            self._log_security_event(
                user_id,
                "user_blacklisted",
                {"reason": reason},
                "high"
            )

    def remove_from_blacklist(self, user_id: int) -> None:
        """Remove a user from the blacklist."""
        with self._lock:
            self.blacklist_users.discard(user_id)

    def unblock_user(self, user_id: int) -> bool:
        """Manually unblock a user."""
        with self._lock:
            if user_id in self.user_limits:
                self.user_limits[user_id].blocked_until = time.time()
                self._log_security_event(
                    user_id,
                    "user_unblocked",
                    {"manual": True},
                    "low"
                )
                return True
            return False

    def _log_security_event(
        self,
        user_id: int,
        event_type: str,
        details: Dict[str, Any],
        severity: str = "medium"
    ) -> None:
        """Log a security event."""
        event = SecurityEvent(
            user_id=user_id,
            event_type=event_type,
            timestamp=datetime.now(),
            details=details,
            severity=severity
        )
        self.security_events.append(event)

        # Keep only recent events (last 1000)
        if len(self.security_events) > 1000:
            self.security_events = self.security_events[-1000:]

        self.violation_stats[event_type] += 1

    def get_user_status(self, user_id: int) -> Optional[SecurityContext]:
        """Get the security status of a user."""
        with self._lock:
            if user_id not in self.user_limits:
                return None

            user_limit = self.user_limits[user_id]
            current_time = time.time()

            is_blocked = current_time < user_limit.blocked_until
            block_reason = None
            if is_blocked:
                remaining_time = int(user_limit.blocked_until - current_time)
                block_reason = f"Rate limit violation. Blocked for {remaining_time} more seconds."

            return SecurityContext(
                user_id=user_id,
                username=None,  # Would need to be passed separately
                chat_id=user_id,  # Simplified
                request_count=user_limit.total_requests,
                last_request_time=user_limit.last_request_time,
                is_blocked=is_blocked,
                block_reason=block_reason,
                block_expires=user_limit.blocked_until if is_blocked else None
            )

    def get_statistics(self) -> Dict[str, Any]:
        """Get rate limiting statistics."""
        with self._lock:
            current_time = time.time()

            # Count currently blocked users
            blocked_users = sum(
                1 for user_limit in self.user_limits.values()
                if current_time < user_limit.blocked_until
            )

            # Count active users (requests in last hour)
            active_users = sum(
                1 for user_limit in self.user_limits.values()
                if current_time - user_limit.last_request_time < 3600
            )

            # Calculate violation rate
            violation_rate = (
                (self.total_violations / self.total_requests * 100)
                if self.total_requests > 0 else 0
            )

            return {
                "total_requests": self.total_requests,
                "blocked_requests": self.blocked_requests,
                "total_violations": self.total_violations,
                "violation_rate_percent": violation_rate,
                "active_users": active_users,
                "blocked_users": blocked_users,
                "whitelisted_users": len(self.whitelist_users),
                "blacklisted_users": len(self.blacklist_users),
                "tracked_users": len(self.user_limits),
                "rate_limits": {
                    "requests_per_minute": self.rate_config.requests_per_minute,
                    "requests_per_hour": self.rate_config.requests_per_hour,
                    "requests_per_day": self.rate_config.requests_per_day,
                    "burst_limit": self.rate_config.burst_limit,
                    "max_concurrent": self.rate_config.max_concurrent_requests
                }
            }

    def get_security_events(
        self,
        hours: int = 24,
        severity: Optional[str] = None,
        event_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent security events."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        filtered_events = []
        for event in self.security_events:
            if event.timestamp >= cutoff_time:
                if severity is None or event.severity == severity:
                    if event_type is None or event.event_type == event_type:
                        filtered_events.append({
                            "user_id": event.user_id,
                            "event_type": event.event_type,
                            "severity": event.severity,
                            "timestamp": event.timestamp.isoformat(),
                            "details": event.details
                        })

        return sorted(filtered_events, key=lambda x: x["timestamp"], reverse=True)

    def get_top_violators(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get users with the most violations."""
        user_violations = defaultdict(int)
        for event in self.security_events:
            if event.event_type in ["rate_limit_violation", "user_blocked"]:
                user_violations[event.user_id] += 1

        top_violators = sorted(
            user_violations.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        return [
            {
                "user_id": user_id,
                "violation_count": count,
                "user_status": self.get_user_status(user_id)
            }
            for user_id, count in top_violators
        ]

    def cleanup_old_data(self, days: int = 30) -> None:
        """Clean up old rate limiting data."""
        with self._lock:
            cutoff_time = time.time() - (days * 24 * 3600)

            # Remove inactive users
            inactive_users = [
                user_id for user_id, user_limit in self.user_limits.items()
                if user_limit.last_request_time < cutoff_time
            ]

            for user_id in inactive_users:
                del self.user_limits[user_id]

            # Clean old security events
            cutoff_datetime = datetime.now() - timedelta(days=days)
            self.security_events = [
                event for event in self.security_events
                if event.timestamp >= cutoff_datetime
            ]

    def reset_user_limits(self, user_id: int) -> bool:
        """Reset rate limits for a specific user."""
        with self._lock:
            if user_id in self.user_limits:
                self.user_limits[user_id] = UserRateLimit(user_id=user_id)
                return True
            return False

    def get_rate_limit_status(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get current rate limit status for a user."""
        with self._lock:
            if user_id not in self.user_limits:
                return None

            user_limit = self.user_limits[user_id]
            current_time = time.time()

            self._cleanup_old_requests(user_limit, current_time)

            return {
                "user_id": user_id,
                "minute_requests": len(user_limit.minute_requests),
                "minute_limit": self.rate_config.requests_per_minute,
                "hour_requests": len(user_limit.hour_requests),
                "hour_limit": self.rate_config.requests_per_hour,
                "day_requests": len(user_limit.day_requests),
                "day_limit": self.rate_config.requests_per_day,
                "burst_requests": len(user_limit.burst_requests),
                "burst_limit": self.rate_config.burst_limit,
                "concurrent_requests": user_limit.concurrent_requests,
                "concurrent_limit": self.rate_config.max_concurrent_requests,
                "total_requests": user_limit.total_requests,
                "violation_count": user_limit.violation_count,
                "is_blocked": current_time < user_limit.blocked_until,
                "blocked_until": user_limit.blocked_until if current_time < user_limit.blocked_until else None
            }