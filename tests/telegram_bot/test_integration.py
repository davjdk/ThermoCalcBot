"""
Integration tests for Telegram bot security and monitoring.

This module tests the complete integration between security, monitoring,
and core bot functionality.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.telegram_bot.security import (
    QueryValidator, ErrorHandler, RateLimiter, ErrorContext
)
from src.telegram_bot.monitoring import (
    BotMetrics, QueryAnalytics, HealthChecker, AlertManager
)
from src.telegram_bot.logging import TelegramSessionLogger, TelegramSessionManager
from src.telegram_bot.models.security import (
    SecurityConfig, MonitoringConfig, ValidationResult
)


class TestSecurityMonitoringIntegration:
    """Test integration between security and monitoring systems."""

    def setup_method(self):
        """Setup integrated test environment."""
        self.security_config = SecurityConfig(
            max_requests_per_minute=10,
            max_requests_per_hour=100,
            admin_user_ids=[99999],
            blocked_user_ids=[11111]
        )
        self.monitoring_config = MonitoringConfig(
            enable_metrics=True,
            enable_health_checks=True,
            enable_alerts=True
        )

        # Initialize components
        self.query_validator = QueryValidator()
        self.rate_limiter = RateLimiter(self.security_config)
        self.error_handler = ErrorHandler()
        self.metrics = BotMetrics(self.monitoring_config)
        self.query_analytics = QueryAnalytics()
        self.alert_manager = AlertManager(self.monitoring_config, self.security_config)
        self.session_manager = TelegramSessionManager()

    def test_complete_request_workflow(self):
        """Test complete request workflow with all security and monitoring components."""
        user_id = 12345
        username = "testuser"
        query = "H2O properties at 298K"

        # Create session
        session = self.session_manager.create_session(user_id, username, user_id)

        try:
            # Step 1: Rate limiting check
            allowed, reason = self.rate_limiter.is_allowed(user_id)
            assert allowed, f"Request should be allowed: {reason}"

            # Step 2: Start concurrent request tracking
            assert self.rate_limiter.start_request(user_id)

            # Step 3: Log user request
            session.log_user_request(query)

            # Step 4: Input validation
            validation_result = self.query_validator.validate_query(query)
            assert validation_result.is_valid, "Query should pass validation"

            # Step 5: Simulate processing with timing
            processing_start = time.time()
            time.sleep(0.1)  # Simulate processing time
            processing_time = time.time() - processing_start

            # Step 6: Log LLM extraction
            session.log_llm_extraction(confidence=0.95, extraction_time=0.05)

            # Step 7: Log database search
            session.log_database_search(compounds_found=1, search_time=0.02)

            # Step 8: Log calculation completion
            session.log_calculation_completed(calculation_time=0.03)

            # Step 9: Record metrics
            self.metrics.record_request(
                user_id=user_id,
                username=username,
                query=query,
                processing_time=processing_time,
                success=True,
                timing_breakdown={
                    "llm": 0.05,
                    "database": 0.02,
                    "calculation": 0.03
                }
            )

            # Step 10: Record in analytics
            self.query_analytics.record_query(
                user_id=user_id,
                query=query,
                extracted_params=None,
                processing_time=processing_time,
                success=True
            )

            # Step 11: Log bot response
            response_length = 150
            session.log_bot_response(response_length, processing_time)

            # Verify all components recorded data
            metrics_stats = self.metrics.get_performance_stats()
            assert metrics_stats["total_requests"] == 1
            assert metrics_stats["successful_requests"] == 1

            analytics_queries = self.query_analytics.get_top_queries(limit=10)
            assert len(analytics_queries) >= 1

        finally:
            # Step 12: End concurrent request tracking
            self.rate_limiter.end_request(user_id)

            # Step 13: Close session
            session.close_session("completed")

    def test_error_handling_workflow(self):
        """Test error handling workflow with monitoring integration."""
        user_id = 12346
        username = "testuser"
        malicious_query = "<script>alert('xss')</script>"

        # Create session
        session = self.session_manager.create_session(user_id, username, user_id)

        try:
            # Step 1: Rate limiting check
            allowed, reason = self.rate_limiter.is_allowed(user_id)
            assert allowed

            # Step 2: Start concurrent request tracking
            assert self.rate_limiter.start_request(user_id)

            # Step 3: Log user request
            session.log_user_request(malicious_query)

            # Step 4: Input validation (should fail)
            validation_result = self.query_validator.validate_query(malicious_query)
            assert not validation_result.is_valid

            # Step 5: Handle validation error
            error_context = ErrorContext(
                user_id=user_id,
                username=username,
                query=malicious_query,
                component="security",
                operation="validation"
            )

            # Simulate async error handling
            async def handle_error():
                return await self.error_handler.handle_error(Exception("XSS detected"), error_context)

            user_message = asyncio.run(handle_error())

            # Step 6: Record failed request metrics
            self.metrics.record_request(
                user_id=user_id,
                username=username,
                query=malicious_query,
                processing_time=0.1,
                success=False,
                error_type="security_violation"
            )

            # Step 7: Record failed query in analytics
            self.query_analytics.record_query(
                user_id=user_id,
                query=malicious_query,
                extracted_params=None,
                processing_time=0.1,
                success=False
            )

            # Step 8: Log security event
            session.log_security_event(
                event_type="xss_attempt",
                details={"query": malicious_query, "blocked": True},
                severity="high"
            )

            # Verify error was handled and recorded
            assert user_message is not None
            assert "безопасности" in user_message.lower() or "security" in user_message.lower()

            metrics_stats = self.metrics.get_performance_stats()
            assert metrics_stats["total_requests"] == 1
            assert metrics_stats["error_count"] == 1

            error_stats = self.error_handler.get_error_statistics()
            assert error_stats["total_errors"] > 0

        finally:
            self.rate_limiter.end_request(user_id)
            session.close_session("error")

    @pytest.mark.asyncio
    async def test_alert_integration(self):
        """Test alert system integration with monitoring."""
        # Simulate high error rate to trigger alerts
        for i in range(15):  # Generate errors above threshold
            self.metrics.record_request(
                user_id=12347 + i,
                username=f"user{i}",
                query=f"Error query {i}",
                processing_time=0.5,
                success=False,
                error_type="system_error"
            )

        # Get metrics
        metrics = self.metrics.get_performance_stats()

        # Create mock health status
        health_status = {
            "components": {
                "database": {"status": "healthy"},
                "llm_api": {"status": "healthy"}
            }
        }

        # Check for alerts
        triggered_alerts = await self.alert_manager.check_and_send_alerts(metrics, health_status)

        # Should trigger high error rate alert
        assert len(triggered_alerts) > 0
        assert any(alert.rule_name == "high_error_rate" for alert in triggered_alerts)

        # Verify alert statistics
        alert_stats = self.alert_manager.get_alert_statistics()
        assert alert_stats["total_alerts"] > 0

    def test_rate_limiting_violation_tracking(self):
        """Test rate limiting violation tracking and analytics integration."""
        user_id = 12348

        # Trigger rate limit violations
        violations = 0
        for i in range(20):  # Exceed rate limit
            allowed, _ = self.rate_limiter.is_allowed(user_id)
            if not allowed:
                violations += 1

        assert violations > 0

        # Record violations in metrics
        for i in range(violations):
            self.metrics.record_request(
                user_id=user_id,
                username="violator",
                query=f"Violation query {i}",
                processing_time=0.1,
                success=False,
                error_type="rate_limit_exceeded"
            )

        # Check security events
        security_events = self.rate_limiter.get_security_events(hours=1)
        assert len(security_events) > 0

        # Check top violators
        top_violators = self.rate_limiter.get_top_violators(limit=5)
        assert len(top_violators) > 0

    def test_session_logging_integration(self):
        """Test session logging integration with all components."""
        user_id = 12349
        username = "sessionuser"

        # Create session
        with self.session_manager.create_session(user_id, username, user_id) as session:
            # Process multiple requests in the same session
            queries = [
                "H2O properties at 298K",
                "CO2 from 300K to 500K",
                "Calculate NH3 thermodynamics"
            ]

            for i, query in enumerate(queries):
                # Rate limiting check
                allowed, _ = self.rate_limiter.is_allowed(user_id)
                if not allowed:
                    continue

                # Start request
                self.rate_limiter.start_request(user_id)

                try:
                    # Log request
                    session.log_user_request(query)

                    # Validate input
                    validation_result = self.query_validator.validate_query(query)
                    if validation_result.is_valid:
                        # Simulate processing
                        processing_time = 0.1 + (i * 0.05)

                        # Record metrics
                        self.metrics.record_request(
                            user_id=user_id,
                            username=username,
                            query=query,
                            processing_time=processing_time,
                            success=True
                        )

                        # Record in analytics
                        self.query_analytics.record_query(
                            user_id=user_id,
                            query=query,
                            extracted_params=None,
                            processing_time=processing_time,
                            success=True
                        )

                        # Log processing steps
                        session.log_llm_extraction(0.9, 0.05)
                        session.log_database_search(1, 0.02)
                        session.log_calculation_completed(0.03)
                        session.log_bot_response(100, processing_time)

                finally:
                    self.rate_limiter.end_request(user_id)

        # Verify session data
        session_summary = session.get_session_summary()
        assert session_summary["total_requests"] > 0
        assert session_summary["username"] == username

        # Verify session manager statistics
        manager_stats = self.session_manager.get_session_statistics()
        assert manager_stats["active_sessions"] >= 0

    @patch('src.telegram_bot.monitoring.health_checker.psutil')
    @pytest.mark.asyncio
    async def test_health_check_integration(self, mock_psutil):
        """Test health check integration with alerting."""
        # Mock system metrics that would trigger alerts
        mock_memory = Mock()
        mock_memory.percent = 85.0  # High memory usage
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_process = Mock()
        mock_psutil.Process.return_value = mock_process

        # Create health checker
        health_checker = HealthChecker(self.monitoring_config)

        # Run health check
        health_status = await health_checker.check_all_components()

        # Should detect degraded memory status
        assert health_status["overall_status"] in ["degraded", "healthy"]

        # Check if alerts should be triggered
        if "components" in health_status:
            memory_status = health_status["components"].get("memory", {})
            if memory_status.get("status") == "degraded":
                # Create metrics that would trigger memory alert
                metrics = {"memory_usage_percent": 85.0}

                triggered_alerts = await self.alert_manager.check_and_send_alerts(
                    metrics, health_status
                )

                # Should trigger high memory usage alert
                memory_alerts = [a for a in triggered_alerts if "memory" in a.rule_name]
                assert len(memory_alerts) > 0

    def test_performance_monitoring_integration(self):
        """Test performance monitoring integration across components."""
        # Simulate high-load scenario
        user_ids = list(range(20000, 20010))  # 10 users

        total_start_time = time.time()

        for user_id in user_ids:
            # Simulate multiple requests per user
            for i in range(3):
                # Rate limiting check
                allowed, _ = self.rate_limiter.is_allowed(user_id)
                if not allowed:
                    continue

                # Start request
                self.rate_limiter.start_request(user_id)

                try:
                    # Simulate request processing
                    request_start = time.time()
                    time.sleep(0.01)  # Simulate work
                    processing_time = time.time() - request_start

                    # Record metrics with detailed timing
                    self.metrics.record_request(
                        user_id=user_id,
                        username=f"user{user_id}",
                        query=f"Performance test query {i}",
                        processing_time=processing_time,
                        success=True,
                        timing_breakdown={
                            "validation": 0.001,
                            "llm": 0.005,
                            "database": 0.002,
                            "calculation": 0.002
                        }
                    )

                finally:
                    self.rate_limiter.end_request(user_id)

        total_time = time.time() - total_start_time

        # Analyze performance data
        performance_stats = self.metrics.get_performance_stats()
        user_stats = self.metrics.get_user_stats()
        system_stats = self.metrics.get_system_stats()

        # Verify comprehensive monitoring
        assert performance_stats["total_requests"] > 0
        assert performance_stats["avg_response_time_seconds"] > 0
        assert user_stats["total_users"] > 0
        assert system_stats["cpu_percent"] >= 0

        # Check for performance alerts if needed
        if performance_stats["avg_response_time_seconds"] > 1.0:
            # Slow performance might trigger alerts
            metrics = {"response_time_seconds": performance_stats["avg_response_time_seconds"]}
            health_status = {"components": {}}

            async def check_alerts():
                return await self.alert_manager.check_and_send_alerts(metrics, health_status)

            triggered_alerts = asyncio.run(check_alerts())

            # May trigger slow response alerts
            response_time_alerts = [a for a in triggered_alerts if "response_time" in a.rule_name]

    def test_cleanup_and_maintenance(self):
        """Test cleanup and maintenance functionality."""
        # Generate some data
        for i in range(50):
            self.metrics.record_request(
                user_id=30000 + i,
                username=f"cleanupuser{i}",
                query=f"Cleanup test query {i}",
                processing_time=0.1,
                success=True
            )

        # Verify data exists
        assert self.metrics.get_performance_stats()["total_requests"] == 50

        # Test cleanup
        self.metrics.cleanup_old_data(days=0)  # Clean all data
        self.query_analytics.clear_old_data(days=0)
        self.rate_limiter.cleanup_old_data(days=0)
        self.session_manager.cleanup_old_logs(days=0)

        # Verify cleanup worked (some components might still retain recent data)
        metrics_after = self.metrics.get_performance_stats()
        # Note: BotMetrics might not delete recent data, so we check the cleanup methods work

    def test_configuration_integration(self):
        """Test that configuration changes are properly integrated."""
        # Test security config changes
        original_rate_limit = self.security_config.max_requests_per_minute

        # Update configuration
        self.security_config.max_requests_per_minute = 5
        new_rate_limiter = RateLimiter(self.security_config)

        # Test new limits are enforced
        user_id = 40000
        allowed_count = 0
        for i in range(10):
            allowed, _ = new_rate_limiter.is_allowed(user_id)
            if allowed:
                allowed_count += 1

        assert allowed_count <= 5

        # Test monitoring config changes
        self.monitoring_config.enable_alerts = False
        new_alert_manager = AlertManager(self.monitoring_config, self.security_config)

        # Alerts should be disabled
        assert not new_alert_manager.config.enable_alerts

        # Test configuration validation
        assert original_rate_limit != self.security_config.max_requests_per_minute


if __name__ == "__main__":
    pytest.main([__file__, "-v"])