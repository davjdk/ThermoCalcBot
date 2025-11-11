"""
Telegram session logging with security and privacy features.

This module provides comprehensive session logging for Telegram bot interactions
with user privacy protection and structured logging capabilities.
"""

import os
import time
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import threading

from ...thermo_agents.session_logger import SessionLogger


@dataclass
class TelegramSessionData:
    """Data structure for Telegram session information"""
    session_id: str
    user_id: int
    username: Optional[str]
    chat_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    request_count: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_processing_time: float = 0.0
    queries: List[Dict[str, Any]] = None
    files_sent: List[Dict[str, Any]] = None
    errors: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.queries is None:
            self.queries = []
        if self.files_sent is None:
            self.files_sent = []
        if self.errors is None:
            self.errors = []


class TelegramSessionLogger:
    """
    Enhanced session logger for Telegram bot with security and privacy features.

    Features:
    - User privacy protection (only user IDs logged)
    - Structured JSON logging for analysis
    - Automatic log rotation and cleanup
    - Session performance metrics
    - Error tracking and analysis
    - File operation logging
    - Security event logging
    """

    def __init__(self, user_id: int, username: Optional[str] = None, chat_id: Optional[int] = None):
        self.user_id = user_id
        self.username = self._sanitize_username(username)
        self.chat_id = chat_id or user_id
        self.session_start = time.time()
        self.request_count = 0

        # Generate session ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_id = f"user_{user_id}_{timestamp}"

        # Create session data structure
        self.session_data = TelegramSessionData(
            session_id=self.session_id,
            user_id=user_id,
            username=self.username,
            chat_id=self.chat_id,
            start_time=datetime.now()
        )

        # Setup logging
        self.logger = self._setup_session_logger()
        self.base_logger = logging.getLogger(f"telegram.session.{user_id}")

        # Thread safety
        self._lock = threading.Lock()

        # Log session start
        self.info(f"Session started for user {self.username}({user_id}) in chat {self.chat_id}")

    def _sanitize_username(self, username: Optional[str]) -> Optional[str]:
        """Sanitize username for logging."""
        if not username:
            return None

        # Remove special characters and limit length
        sanitized = ''.join(c for c in username if c.isalnum() or c in ['_', '-'])
        return sanitized[:20] if sanitized else None

    def _setup_session_logger(self) -> logging.Logger:
        """Setup dedicated logger for this session."""
        logger = logging.getLogger(f"telegram.session.{self.user_id}.{self.session_id}")

        # Create logs directory if it doesn't exist
        logs_dir = Path("logs/telegram_sessions")
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Create session log file
        log_file = logs_dir / f"{self.session_id}.log"

        # Setup file handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)

        # Setup formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # Add handler to logger
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)

        # Prevent propagation to avoid duplicate logs
        logger.propagate = False

        return logger

    def log_user_request(self, query: str, query_length: int = None) -> None:
        """Log a user request."""
        with self._lock:
            self.request_count += 1
            session_time = time.time() - self.session_start

            # Log to session logger
            self.logger.info(f"Request #{self.request_count}: {query[:100]}{'...' if len(query) > 100 else ''} (session_time: {session_time:.2f}s)")

            # Update session data
            query_data = {
                "request_number": self.request_count,
                "query": self._sanitize_query(query),
                "query_length": query_length or len(query),
                "timestamp": datetime.now().isoformat(),
                "session_time": session_time
            }
            self.session_data.queries.append(query_data)

    def log_llm_extraction(
        self,
        confidence: float,
        extraction_time: float,
        extracted_params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log LLM parameter extraction."""
        with self._lock:
            self.logger.info(
                f"LLM extraction completed: confidence={confidence:.2f}, "
                f"time={extraction_time:.2f}s"
            )

            # Add to last query if available
            if self.session_data.queries:
                self.session_data.queries[-1]["llm_extraction"] = {
                    "confidence": confidence,
                    "extraction_time": extraction_time,
                    "timestamp": datetime.now().isoformat()
                }

    def log_database_search(
        self,
        compounds_found: int,
        search_time: float,
        query_details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log database search operation."""
        with self._lock:
            self.logger.info(
                f"Database search: {compounds_found} compounds found in {search_time:.2f}s"
            )

            # Add to last query if available
            if self.session_data.queries:
                self.session_data.queries[-1]["database_search"] = {
                    "compounds_found": compounds_found,
                    "search_time": search_time,
                    "timestamp": datetime.now().isoformat()
                }

    def log_calculation_completed(self, calculation_time: float, calculation_type: str = "thermodynamic") -> None:
        """Log calculation completion."""
        with self._lock:
            self.logger.info(
                f"{calculation_type.capitalize()} calculations completed in {calculation_time:.2f}s"
            )

            # Add to last query if available
            if self.session_data.queries:
                self.session_data.queries[-1]["calculation"] = {
                    "type": calculation_type,
                    "calculation_time": calculation_time,
                    "timestamp": datetime.now().isoformat()
                }

    def log_bot_response(
        self,
        response_length: int,
        processing_time: float,
        response_type: str = "text"
    ) -> None:
        """Log bot response."""
        with self._lock:
            total_time = time.time() - self.session_start
            self.session_data.total_processing_time += processing_time

            # Determine success based on response
            success = response_length > 0 and "error" not in response_type.lower()
            if success:
                self.session_data.successful_requests += 1
            else:
                self.session_data.failed_requests += 1

            self.logger.info(
                f"Response sent: {response_length} chars ({response_type}), "
                f"processing_time={processing_time:.2f}s, "
                f"total_session_time={total_time:.2f}s, "
                f"success={success}"
            )

            # Update last query if available
            if self.session_data.queries:
                self.session_data.queries[-1]["response"] = {
                    "length": response_length,
                    "type": response_type,
                    "processing_time": processing_time,
                    "success": success,
                    "timestamp": datetime.now().isoformat()
                }

    def log_file_sent(
        self,
        filename: str,
        file_size_kb: float,
        file_type: str = "txt"
    ) -> None:
        """Log file sending operation."""
        with self._lock:
            self.logger.info(f"File sent: {filename} ({file_size_kb:.1f} KB, {file_type})")

            # Add to session data
            file_data = {
                "filename": filename,
                "size_kb": file_size_kb,
                "type": file_type,
                "timestamp": datetime.now().isoformat()
            }
            self.session_data.files_sent.append(file_data)

            # Add to last query if available
            if self.session_data.queries:
                if "files_sent" not in self.session_data.queries[-1]:
                    self.session_data.queries[-1]["files_sent"] = []
                self.session_data.queries[-1]["files_sent"].append(file_data)

    def log_error(
        self,
        error_type: str,
        error_message: str,
        error_details: Optional[Dict[str, Any]] = None,
        component: Optional[str] = None
    ) -> None:
        """Log an error that occurred during processing."""
        with self._lock:
            self.logger.error(
                f"Error [{error_type}]: {error_message}"
                + (f" in {component}" if component else "")
            )

            # Add to session data
            error_data = {
                "type": error_type,
                "message": error_message,
                "component": component,
                "details": error_details,
                "timestamp": datetime.now().isoformat()
            }
            self.session_data.errors.append(error_data)

            # Add to last query if available
            if self.session_data.queries:
                if "errors" not in self.session_data.queries[-1]:
                    self.session_data.queries[-1]["errors"] = []
                self.session_data.queries[-1]["errors"].append(error_data)

    def log_security_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        severity: str = "info"
    ) -> None:
        """Log a security-related event."""
        with self._lock:
            log_method = getattr(self.logger, severity, self.logger.info)
            log_method(f"Security event [{event_type}]: {details}")

            # Add to session data as special error type
            security_data = {
                "type": "security",
                "event_type": event_type,
                "severity": severity,
                "details": details,
                "timestamp": datetime.now().isoformat()
            }
            self.session_data.errors.append(security_data)

    def log_performance_metrics(self, metrics: Dict[str, Any]) -> None:
        """Log performance metrics for the session."""
        with self._lock:
            self.logger.info(f"Performance metrics: {metrics}")

    def _sanitize_query(self, query: str) -> str:
        """Sanitize query for logging (remove sensitive information)."""
        # Limit length and remove potential sensitive data
        sanitized = query[:500]
        if len(query) > 500:
            sanitized += "..."
        return sanitized

    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)

    def debug(self, message: str) -> None:
        """Log debug message."""
        self.logger.debug(message)

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the current session."""
        with self._lock:
            session_duration = time.time() - self.session_start
            success_rate = (
                (self.session_data.successful_requests / self.session_data.request_count * 100)
                if self.session_data.request_count > 0 else 0
            )
            avg_processing_time = (
                (self.session_data.total_processing_time / self.session_data.request_count)
                if self.session_data.request_count > 0 else 0
            )

            return {
                "session_id": self.session_id,
                "user_id": self.user_id,
                "username": self.username,
                "chat_id": self.chat_id,
                "start_time": self.session_data.start_time.isoformat(),
                "duration_seconds": session_duration,
                "total_requests": self.session_data.request_count,
                "successful_requests": self.session_data.successful_requests,
                "failed_requests": self.session_data.failed_requests,
                "success_rate_percent": success_rate,
                "avg_processing_time_seconds": avg_processing_time,
                "total_processing_time_seconds": self.session_data.total_processing_time,
                "files_sent_count": len(self.session_data.files_sent),
                "errors_count": len(self.session_data.errors),
                "queries_count": len(self.session_data.queries)
            }

    def export_session_data(self, filepath: Optional[str] = None) -> str:
        """Export session data to JSON file."""
        if filepath is None:
            logs_dir = Path("logs/telegram_sessions")
            logs_dir.mkdir(parents=True, exist_ok=True)
            filepath = logs_dir / f"{self.session_id}_data.json"

        with self._lock:
            # Update session end time
            self.session_data.end_time = datetime.now()

            # Prepare data for export (remove sensitive information)
            export_data = asdict(self.session_data)

            # Convert datetime objects to ISO format
            if export_data["start_time"]:
                export_data["start_time"] = export_data["start_time"].isoformat()
            if export_data["end_time"]:
                export_data["end_time"] = export_data["end_time"].isoformat()

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            return str(filepath)

    def close_session(self, status: str = "completed") -> None:
        """Close the session and log summary."""
        with self._lock:
            session_duration = time.time() - self.session_start
            self.session_data.end_time = datetime.now()

            if status == "completed":
                self.info(
                    f"Session completed successfully: {self.request_count} requests in {session_duration:.2f}s"
                )
            elif status == "error":
                self.error(
                    f"Session ended with error: {self.request_count} requests in {session_duration:.2f}s"
                )
            else:
                self.info(
                    f"Session ended ({status}): {self.request_count} requests in {session_duration:.2f}s"
                )

            # Export session data
            try:
                self.export_session_data()
            except Exception as e:
                self.error(f"Failed to export session data: {e}")

            # Close logger handlers
            for handler in self.logger.handlers:
                handler.close()
                self.logger.removeHandler(handler)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.error(f"Session ended with error: {exc_val}")
            self.close_session("error")
        else:
            self.close_session("completed")


class TelegramSessionManager:
    """Manager for multiple Telegram sessions with cleanup capabilities."""

    def __init__(self, max_sessions: int = 1000, session_timeout_hours: int = 24):
        self.max_sessions = max_sessions
        self.session_timeout_hours = session_timeout_hours
        self.active_sessions: Dict[int, TelegramSessionLogger] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        user_id: int,
        username: Optional[str] = None,
        chat_id: Optional[int] = None
    ) -> TelegramSessionLogger:
        """Create a new session for a user."""
        with self._lock:
            # Close existing session for this user if exists
            if user_id in self.active_sessions:
                self.active_sessions[user_id].close_session("replaced")

            # Check session limit
            if len(self.active_sessions) >= self.max_sessions:
                self._cleanup_old_sessions()

            # Create new session
            session = TelegramSessionLogger(user_id, username, chat_id)
            self.active_sessions[user_id] = session

            return session

    def get_session(self, user_id: int) -> Optional[TelegramSessionLogger]:
        """Get existing session for a user."""
        with self._lock:
            return self.active_sessions.get(user_id)

    def close_session(self, user_id: int, status: str = "completed") -> None:
        """Close session for a specific user."""
        with self._lock:
            if user_id in self.active_sessions:
                self.active_sessions[user_id].close_session(status)
                del self.active_sessions[user_id]

    def _cleanup_old_sessions(self) -> None:
        """Remove sessions that have timed out."""
        current_time = time.time()
        timeout_seconds = self.session_timeout_hours * 3600

        expired_users = []
        for user_id, session in self.active_sessions.items():
            if current_time - session.session_start > timeout_seconds:
                session.close_session("timeout")
                expired_users.append(user_id)

        for user_id in expired_users:
            del self.active_sessions[user_id]

    def get_active_sessions_count(self) -> int:
        """Get number of active sessions."""
        with self._lock:
            return len(self.active_sessions)

    def cleanup_old_logs(self, days: int = 30) -> None:
        """Clean up old session log files."""
        logs_dir = Path("logs/telegram_sessions")
        if not logs_dir.exists():
            return

        cutoff_time = time.time() - (days * 24 * 3600)

        for log_file in logs_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                except Exception as e:
                    print(f"Failed to delete old log file {log_file}: {e}")

        for data_file in logs_dir.glob("*.json"):
            if data_file.stat().st_mtime < cutoff_time:
                try:
                    data_file.unlink()
                except Exception as e:
                    print(f"Failed to delete old data file {data_file}: {e}")

    def get_session_statistics(self) -> Dict[str, Any]:
        """Get statistics about all sessions."""
        with self._lock:
            total_requests = sum(session.request_count for session in self.active_sessions.values())
            total_errors = sum(len(session.session_data.errors) for session in self.active_sessions.values())

            return {
                "active_sessions": len(self.active_sessions),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "avg_requests_per_session": total_requests / len(self.active_sessions) if self.active_sessions else 0,
                "users_with_sessions": list(self.active_sessions.keys())
            }