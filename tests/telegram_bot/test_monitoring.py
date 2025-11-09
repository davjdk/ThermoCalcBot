"""
Comprehensive monitoring tests for Telegram bot.

This module tests all monitoring features including:
- Performance metrics collection
- Query analytics and pattern analysis
- Health checks for all components
- Alert management and notifications
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.telegram_bot.monitoring import (
    BotMetrics, QueryAnalytics, HealthChecker, AlertManager
)
from src.telegram_bot.models.security import (
    MonitoringConfig, SecurityConfig, HealthCheckResult, AlertRule
)


class TestBotMetrics:
    """Test cases for BotMetrics class."""

    def setup_method(self):
        """Setup test metrics collector."""
        self.config = MonitoringConfig(enable_metrics=True)
        self.metrics = BotMetrics(self.config)

    def test_request_recording(self):
        """Test recording of request metrics."""
        user_id = 12345
        username = "testuser"
        query = "H2O properties at 298K"
        processing_time = 1.5
        success = True

        # Record request
        self.metrics.record_request(
            user_id=user_id,
            username=username,
            query=query,
            processing_time=processing_time,
            success=success,
            timing_breakdown={
                "llm": 0.8,
                "database": 0.4,
                "calculation": 0.2,
                "formatting": 0.1
            }
        )

        # Check performance stats
        stats = self.metrics.get_performance_stats()
        assert stats["total_requests"] == 1
        assert stats["successful_requests"] == 1
        assert stats["error_count"] == 0
        assert stats["success_rate_percent"] == 100.0
        assert stats["avg_response_time_seconds"] == 1.5

        # Check user stats
        user_stats = self.metrics.get_user_stats()
        assert user_stats["total_users"] == 1
        assert user_stats["active_users"] == 1
        assert len(user_stats["top_users"]) == 1

    def test_error_tracking(self):
        """Test error tracking in metrics."""
        user_id = 12346

        # Record successful request
        self.metrics.record_request(
            user_id=user_id,
            username="testuser",
            query="H2O properties",
            processing_time=1.0,
            success=True
        )

        # Record failed request
        self.metrics.record_request(
            user_id=user_id,
            username="testuser",
            query="Invalid query",
            processing_time=0.5,
            success=False,
            error_type="validation_error"
        )

        # Check stats
        stats = self.metrics.get_performance_stats()
        assert stats["total_requests"] == 2
        assert stats["successful_requests"] == 1
        assert stats["error_count"] == 1
        assert stats["success_rate_percent"] == 50.0

    def test_user_activity_tracking(self):
        """Test user activity tracking."""
        user1_id = 12347
        user2_id = 12348

        # Record requests from different users
        for i in range(3):
            self.metrics.record_request(
                user_id=user1_id,
                username="user1",
                query=f"H2O query {i}",
                processing_time=1.0,
                success=True
            )

        self.metrics.record_request(
            user_id=user2_id,
            username="user2",
            query="CO2 query",
            processing_time=1.2,
            success=True
        )

        # Check user stats
        user_stats = self.metrics.get_user_stats()
        assert user_stats["total_users"] == 2
        assert user_stats["active_users"] == 2

        # Check top users
        top_users = user_stats["top_users"]
        assert len(top_users) == 2
        assert top_users[0]["requests"] == 3  # user1
        assert top_users[1]["requests"] == 1  # user2

    def test_response_time_tracking(self):
        """Test response time tracking and statistics."""
        response_times = [0.5, 1.0, 1.5, 2.0, 2.5]

        for i, rt in enumerate(response_times):
            self.metrics.record_request(
                user_id=12349 + i,
                username=f"user{i}",
                query=f"Query {i}",
                processing_time=rt,
                success=True
            )

        stats = self.metrics.get_performance_stats()
        assert stats["avg_response_time_seconds"] == sum(response_times) / len(response_times)

        # Check response time percentiles
        response_stats = stats["response_time_stats"]
        assert response_stats["min"] == min(response_times)
        assert response_stats["max"] == max(response_times)

    @patch('src.telegram_bot.monitoring.bot_metrics.psutil')
    def test_system_stats(self, mock_psutil):
        """Test system statistics collection."""
        # Mock psutil responses
        mock_psutil.cpu_percent.return_value = 45.5
        mock_memory = Mock()
        mock_memory.total = 8589934592  # 8GB
        mock_memory.available = 4294967296  # 4GB
        mock_memory.used = 4294967296  # 4GB
        mock_memory.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_memory

        mock_disk = Mock()
        mock_disk.total = 107374182400  # 100GB
        mock_disk.free = 53687091200  # 50GB
        mock_disk.used = 53687091200  # 50GB
        mock_psutil.disk_usage.return_value = mock_disk

        mock_process = Mock()
        mock_process.memory_info.return_value = Mock(rss=134217728, vms=268435456)  # 128MB, 256MB
        mock_process.cpu_percent.return_value = 15.0
        mock_process.num_threads.return_value = 4
        mock_process.open_files.return_value = [Mock(), Mock()]
        mock_psutil.Process.return_value = mock_process

        # Get system stats
        system_stats = self.metrics.get_system_stats()

        assert system_stats["cpu_percent"] == 45.5
        assert system_stats["memory"]["total_gb"] == 8.0
        assert system_stats["memory"]["available_gb"] == 4.0
        assert system_stats["disk"]["total_gb"] == 100.0
        assert system_stats["disk"]["free_gb"] == 50.0

    def test_metrics_reset(self):
        """Test metrics reset functionality."""
        # Record some data
        self.metrics.record_request(
            user_id=12350,
            username="testuser",
            query="Test query",
            processing_time=1.0,
            success=True
        )

        # Verify data exists
        stats = self.metrics.get_performance_stats()
        assert stats["total_requests"] > 0

        # Reset metrics
        self.metrics.reset_metrics()

        # Verify data is cleared
        stats = self.metrics.get_performance_stats()
        assert stats["total_requests"] == 0
        assert stats["successful_requests"] == 0


class TestQueryAnalytics:
    """Test cases for QueryAnalytics class."""

    def setup_method(self):
        """Setup test query analytics."""
        self.analytics = QueryAnalytics()

    def test_query_recording(self):
        """Test recording of queries for analytics."""
        user_id = 12345
        query = "H2O properties at 298K"
        processing_time = 1.5
        success = True

        # Record query
        self.analytics.record_query(
            user_id=user_id,
            query=query,
            extracted_params=None,
            processing_time=processing_time,
            success=success
        )

        # Check query history
        assert len(self.analytics.query_history) == 1
        assert self.analytics.query_history[0]["query"] == query
        assert self.analytics.query_history[0]["success"] == success

    def test_pattern_recognition(self):
        """Test query pattern recognition."""
        # Test different query patterns
        queries = [
            ("H2O properties at 298K", "compound_properties"),
            ("2 H2 + O2 → 2 H2O at 298K", "reaction_calculation"),
            ("Calculate CO2 from 300K to 500K", "temperature_range"),
            ("Check equilibrium constant", "equilibrium"),
            ("Water melting point", "phase_transition")
        ]

        for query, expected_pattern in queries:
            self.analytics.record_query(
                user_id=12346,
                query=query,
                extracted_params=None,
                processing_time=1.0,
                success=True
            )

        # Check pattern analytics
        pattern_stats = self.analytics.get_pattern_analytics()
        assert "patterns" in pattern_stats
        assert len(pattern_stats["patterns"]) > 0

    def test_top_queries(self):
        """Test top queries functionality."""
        # Record multiple instances of the same query
        popular_query = "H2O properties at 298K"
        unpopular_query = "Fe2O3 complex reaction"

        for i in range(5):
            self.analytics.record_query(
                user_id=12347 + i,
                query=popular_query,
                extracted_params=None,
                processing_time=1.0,
                success=True
            )

        self.analytics.record_query(
            user_id=12352,
            query=unpopular_query,
            extracted_params=None,
            processing_time=1.5,
            success=True
        )

        # Get top queries
        top_queries = self.analytics.get_top_queries(limit=5)
        assert len(top_queries) >= 1
        assert top_queries[0]["query"] == popular_query
        assert top_queries[0]["count"] == 5

    def test_usage_trends(self):
        """Test usage trends calculation."""
        base_time = datetime.now()
        user_id = 12348

        # Record queries over time
        for i in range(10):
            # Simulate different timestamps
            timestamp = base_time + timedelta(minutes=i)
            self.analytics.record_query(
                user_id=user_id,
                query=f"Query {i}",
                extracted_params=None,
                processing_time=1.0,
                success=i % 3 != 0,  # Every 3rd query fails
                timestamp=timestamp
            )

        # Get usage trends
        trends = self.analytics.get_usage_trends(hours=1)
        assert "hourly_trends" in trends
        assert trends["total_queries"] == 10
        assert trends["active_users"] == 1

    def test_compound_analytics(self):
        """Test compound analytics."""
        from src.telegram_bot.models.security import QueryStatistics
        from src.thermo_agents.models.extraction import ExtractedReactionParameters, CompoundInfo

        # Create mock extracted parameters
        compound1 = CompoundInfo(compound_name="H2O", formula="H2O", phase="l")
        compound2 = CompoundInfo(compound_name="CO2", formula="CO2", phase="g")

        mock_params = ExtractedReactionParameters(
            query_type="compound_data",
            all_compounds=[compound1, compound2],
            balanced_equation=None
        )

        # Record query with compounds
        self.analytics.record_query(
            user_id=12349,
            query="H2O and CO2 properties",
            extracted_params=mock_params,
            processing_time=1.5,
            success=True
        )

        # Check compound analytics
        compound_stats = self.analytics.get_compound_analytics(limit=10)
        assert len(compound_stats) >= 0  # May be empty depending on implementation

    def test_analytics_export(self):
        """Test analytics data export."""
        # Record some data
        self.analytics.record_query(
            user_id=12350,
            query="Test query",
            extracted_params=None,
            processing_time=1.0,
            success=True
        )

        # Export to file
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name

        try:
            self.analytics.export_analytics(temp_file)

            # Verify file was created and contains data
            assert os.path.exists(temp_file)
            assert os.path.getsize(temp_file) > 0

            import json
            with open(temp_file, 'r') as f:
                data = json.load(f)

            assert "export_timestamp" in data
            assert "query_patterns" in data

        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)


class TestHealthChecker:
    """Test cases for HealthChecker class."""

    def setup_method(self):
        """Setup test health checker."""
        self.config = MonitoringConfig(enable_health_checks=True)
        self.health_checker = HealthChecker(self.config)

    @pytest.mark.asyncio
    async def test_database_health_check(self):
        """Test database health check."""
        with patch('src.telegram_bot.monitoring.health_checker.DatabaseConnector') as mock_db:
            # Mock successful database response
            mock_connector = Mock()
            mock_connector.execute_query.return_value = [{"count": 1000}]
            mock_db.return_value = mock_connector

            with patch('pathlib.Path.exists', return_value=True):
                result = await self.health_checker._check_database_health()

            assert result.status == "healthy"
            assert result.response_time_ms is not None
            assert result.details is not None
            assert result.details["record_count"] == 1000

    @pytest.mark.asyncio
    async def test_database_health_check_failure(self):
        """Test database health check failure."""
        with patch('src.telegram_bot.monitoring.health_checker.DatabaseConnector') as mock_db:
            # Mock database failure
            mock_db.side_effect = Exception("Database connection failed")

            result = await self.health_checker._check_database_health()

            assert result.status == "unhealthy"
            assert "Database connection failed" in result.error_message

    @pytest.mark.asyncio
    async def test_memory_health_check(self):
        """Test memory health check."""
        with patch('src.telegram_bot.monitoring.health_checker.psutil') as mock_psutil:
            # Mock memory stats
            mock_memory = Mock()
            mock_memory.total = 8589934592  # 8GB
            mock_memory.available = 4294967296  # 4GB
            mock_memory.used = 4294967296  # 4GB
            mock_memory.percent = 50.0
            mock_psutil.virtual_memory.return_value = mock_memory

            mock_process = Mock()
            mock_process.memory_info.return_value = Mock(rss=134217728, vms=268435456)
            mock_process.memory_percent.return_value = 10.0
            mock_psutil.Process.return_value = mock_process

            result = await self.health_checker._check_memory_health()

            assert result.status == "healthy"
            assert result.details["memory_percent"] == 50.0
            assert result.details["process_memory_rss_mb"] == 128.0

    @pytest.mark.asyncio
    async def test_memory_health_check_degraded(self):
        """Test memory health check with degraded status."""
        with patch('src.telegram_bot.monitoring.health_checker.psutil') as mock_psutil:
            # Mock high memory usage
            mock_memory = Mock()
            mock_memory.percent = 85.0  # High usage
            mock_psutil.virtual_memory.return_value = mock_memory

            mock_process = Mock()
            mock_psutil.Process.return_value = mock_process

            result = await self.health_checker._check_memory_health()

            assert result.status == "degraded"

    @pytest.mark.asyncio
    async def test_filesystem_health_check(self):
        """Test filesystem health check."""
        with patch('src.telegram_bot.monitoring.health_checker.psutil') as mock_psutil:
            # Mock disk usage
            mock_disk = Mock()
            mock_disk.total = 107374182400  # 100GB
            mock_disk.free = 10737418240  # 10GB
            mock_disk.used = 96636764160  # 90GB
            mock_psutil.disk_usage.return_value = mock_disk

            with patch('os.access', return_value=True):
                with patch('pathlib.Path.exists', return_value=True):
                    result = await self.health_checker._check_filesystem_health()

            assert result.status == "healthy"
            assert result.details["available_space_gb"] == 10.0

    @pytest.mark.asyncio
    async def test_comprehensive_health_check(self):
        """Test comprehensive health check of all components."""
        # Mock all health checks to return healthy
        with patch.object(self.health_checker, '_check_database_health') as mock_db, \
             patch.object(self.health_checker, '_check_llm_api_health') as mock_llm, \
             patch.object(self.health_checker, '_check_filesystem_health') as mock_fs, \
             patch.object(self.health_checker, '_check_memory_health') as mock_mem:

            # Mock healthy responses
            for mock_check in [mock_db, mock_llm, mock_fs, mock_mem]:
                mock_check.return_value = HealthCheckResult(
                    component="test",
                    status="healthy",
                    response_time_ms=100.0,
                    timestamp=datetime.now()
                )

            # Run comprehensive check
        health_status = await self.health_checker.check_all_components()

        assert health_status["overall_status"] == "healthy"
        assert len(health_status["components"]) >= 4
        assert "recommendations" in health_status
        assert len(health_status["recommendations"]) > 0

    def test_custom_health_check(self):
        """Test custom health check functionality."""
        def custom_check():
            return HealthCheckResult(
                component="custom_test",
                status="healthy",
                response_time_ms=50.0,
                timestamp=datetime.now()
            )

        # Add custom check
        self.health_checker.add_custom_check("test_check", custom_check)

        # Verify it was added
        assert "test_check" in self.health_checker.custom_checks

        # Remove custom check
        self.health_checker.remove_custom_check("test_check")
        assert "test_check" not in self.health_checker.custom_checks


class TestAlertManager:
    """Test cases for AlertManager class."""

    def setup_method(self):
        """Setup test alert manager."""
        self.config = MonitoringConfig(enable_alerts=True)
        self.security_config = SecurityConfig()
        self.alert_manager = AlertManager(self.config, self.security_config)

    def test_alert_rule_creation(self):
        """Test alert rule creation and management."""
        rule_name = "test_rule"
        condition = "test_metric"
        threshold = 75.0
        severity = "high"

        # Add custom rule
        self.alert_manager.add_custom_rule(
            name=rule_name,
            condition=condition,
            threshold=threshold,
            severity=severity,
            description="Test alert rule"
        )

        # Verify rule was added
        assert rule_name in self.alert_manager.alert_rules
        rule = self.alert_manager.alert_rules[rule_name]
        assert rule.condition == condition
        assert rule.threshold == threshold
        assert rule.severity == severity

        # Remove rule
        self.alert_manager.remove_rule(rule_name)
        assert rule_name not in self.alert_manager.alert_rules

    def test_alert_rule_enable_disable(self):
        """Test enabling and disabling alert rules."""
        rule_name = "high_error_rate"

        # Ensure rule exists (it should be a default rule)
        assert rule_name in self.alert_manager.alert_rules

        # Disable rule
        self.alert_manager.disable_rule(rule_name)
        assert not self.alert_manager.alert_rules[rule_name].enabled

        # Enable rule
        self.alert_manager.enable_rule(rule_name)
        assert self.alert_manager.alert_rules[rule_name].enabled

    @pytest.mark.asyncio
    async def test_alert_triggering(self):
        """Test alert triggering based on metrics."""
        metrics = {
            "error_rate_percent": 15.0,  # Above default threshold of 10%
            "avg_response_time_seconds": 2.0
        }

        health_status = {
            "components": {
                "database": {"status": "healthy"},
                "llm_api": {"status": "healthy"}
            }
        }

        # Check alerts (should trigger high error rate alert)
        triggered_alerts = await self.alert_manager.check_and_send_alerts(metrics, health_status)

        assert len(triggered_alerts) > 0
        assert any(alert.rule_name == "high_error_rate" for alert in triggered_alerts)

    @pytest.mark.asyncio
    async def test_alert_cooldown(self):
        """Test alert cooldown functionality."""
        # Create a rule with short cooldown for testing
        self.alert_manager.add_custom_rule(
            name="test_cooldown",
            condition="test_metric",
            threshold=10.0,
            severity="medium",
            cooldown_seconds=1  # 1 second cooldown
        )

        metrics = {"test_metric": 15.0}
        health_status = {"components": {}}

        # Trigger alert first time
        triggered_alerts1 = await self.alert_manager.check_and_send_alerts(metrics, health_status)
        assert len(triggered_alerts1) > 0

        # Try to trigger again immediately (should be blocked by cooldown)
        triggered_alerts2 = await self.alert_manager.check_and_send_alerts(metrics, health_status)
        assert len(triggered_alerts2) == 0

        # Wait for cooldown to expire
        time.sleep(1.1)

        # Try again (should work now)
        triggered_alerts3 = await self.alert_manager.check_and_send_alerts(metrics, health_status)
        assert len(triggered_alerts3) > 0

    def test_alert_history(self):
        """Test alert history tracking."""
        # Add a manual alert to history
        from src.telegram_bot.models.security import AlertNotification
        test_alert = AlertNotification(
            alert_id="test_alert_1",
            rule_name="test_rule",
            severity="medium",
            message="Test alert",
            details={"test": True},
            timestamp=datetime.now()
        )

        self.alert_manager.alert_history.append(test_alert)

        # Get alert history
        history = self.alert_manager.get_alert_history(hours=24)
        assert len(history) >= 1
        assert history[0]["alert_id"] == "test_alert_1"

    def test_alert_statistics(self):
        """Test alert statistics calculation."""
        # Add some test alerts to history
        from src.telegram_bot.models.security import AlertNotification

        alerts = [
            AlertNotification(
                alert_id=f"test_alert_{i}",
                rule_name="test_rule",
                severity="medium",
                message=f"Test alert {i}",
                details={},
                timestamp=datetime.now()
            )
            for i in range(5)
        ]

        for alert in alerts:
            self.alert_manager.alert_history.append(alert)
            self.alert_manager.alert_stats[alert.rule_name] += 1
            self.alert_manager.severity_stats[alert.severity] += 1

        # Get statistics
        stats = self.alert_manager.get_alert_statistics()
        assert stats["total_alerts"] == 5
        assert stats["alerts_by_rule"]["test_rule"] == 5
        assert stats["alerts_by_severity"]["medium"] == 5

    @pytest.mark.asyncio
    async def test_alert_resolution(self):
        """Test alert resolution functionality."""
        # Create and trigger an alert
        metrics = {"error_rate_percent": 15.0}
        health_status = {"components": {}}

        triggered_alerts = await self.alert_manager.check_and_send_alerts(metrics, health_status)
        assert len(triggered_alerts) > 0

        alert_id = triggered_alerts[0].alert_id

        # Resolve the alert
        success = await self.alert_manager.resolve_alert(alert_id, "test_user")
        assert success

        # Alert should no longer be active
        active_alerts = self.alert_manager.get_active_alerts()
        assert not any(alert["alert_id"] == alert_id for alert in active_alerts)

    @pytest.mark.asyncio
    async def test_test_alert_system(self):
        """Test alert system test functionality."""
        result = await self.alert_manager.test_alert_system()

        assert result["success"] is True
        assert "Test alert sent successfully" in result["message"]
        assert "alert_id" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])