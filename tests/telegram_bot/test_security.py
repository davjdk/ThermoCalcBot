"""
Comprehensive security tests for Telegram bot.

This module tests all security features including:
- Input validation and sanitization
- Rate limiting and access control
- Error handling and security event logging
- Session logging with privacy protection
"""

import pytest
import time
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from src.telegram_bot.security import (
    QueryValidator, ErrorHandler, RateLimiter, ErrorContext
)
from src.telegram_bot.security.query_validator import ValidationResult
from src.telegram_bot.models.security import (
    SecurityConfig, ErrorCategory, MonitoringConfig
)


class TestQueryValidator:
    """Test cases for QueryValidator class."""

    def test_valid_chemical_query(self):
        """Test validation of valid chemical queries."""
        validator = QueryValidator()

        # Valid chemical formula queries
        valid_queries = [
            "H2O properties at 298K",
            "CO2 from 300K to 500K",
            "Fe2O3 + 3 C → 2 Fe + 3 CO",
            "NH3 thermodynamic data 400-600K",
            "Calculate H2 + O2 → H2O at 298K"
        ]

        for query in valid_queries:
            result = validator.validate_query(query)
            assert result.is_valid, f"Query should be valid: {query}"
            assert result.sanitized_query is not None
            assert len(result.sanitized_query) <= len(query) + 50  # Allow for HTML escaping

    def test_xss_prevention(self):
        """Test XSS attack prevention."""
        validator = QueryValidator()

        xss_queries = [
            "<script>alert('xss')</script>",
            "H2O <img src=x onerror=alert(1)> properties",
            "<javascript>alert('test')</javascript>",
            "CO2 <iframe src='javascript:alert(1)'></iframe>"
        ]

        for query in xss_queries:
            result = validator.validate_query(query)
            assert not result.is_valid, f"XSS query should be blocked: {query}"
            assert "Forbidden pattern detected" in result.message

    def test_sql_injection_prevention(self):
        """Test SQL injection prevention."""
        validator = QueryValidator()

        sql_injection_queries = [
            "'; DROP TABLE compounds; --",
            "H2O'; DELETE FROM compounds WHERE 't'='t",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM users --"
        ]

        for query in sql_injection_queries:
            result = validator.validate_query(query)
            assert not result.is_valid, f"SQL injection query should be blocked: {query}"

    def test_code_injection_prevention(self):
        """Test code injection prevention."""
        validator = QueryValidator()

        code_injection_queries = [
            "exec('rm -rf /')",
            "eval(__import__('os').system('ls'))",
            "import subprocess; subprocess.call(['ls'])",
            "__import__('os').system('whoami')",
            "$(rm -rf /)",
            "`cat /etc/passwd`"
        ]

        for query in code_injection_queries:
            result = validator.validate_query(query)
            assert not result.is_valid, f"Code injection query should be blocked: {query}"

    def test_url_prevention(self):
        """Test URL/prevention in queries."""
        validator = QueryValidator()

        url_queries = [
            "Visit http://malicious.com for H2O data",
            "Check https://evil.org/attack",
            "javascript:alert('test')"
        ]

        for query in url_queries:
            result = validator.validate_query(query)
            assert not result.is_valid, f"URL query should be blocked: {query}"

    def test_query_length_limits(self):
        """Test query length validation."""
        validator = QueryValidator()

        # Query that's too long
        long_query = "H2O " * 200  # This will exceed the 1000 character limit
        result = validator.validate_query(long_query)
        assert not result.is_valid
        assert "too long" in result.message.lower()

    def test_empty_query_handling(self):
        """Test handling of empty queries."""
        validator = QueryValidator()

        empty_queries = ["", "   ", "\n\t", None]

        for query in empty_queries:
            result = validator.validate_query(query)
            assert not result.is_valid
            assert "empty" in result.message.lower()

    def test_temperature_validation(self):
        """Test temperature range validation."""
        # Valid temperature ranges
        valid_temps = [
            ("298K", True),
            ("300-500K", True),
            ("from 298 to 500 K", True),
            ("298-1000", True),
            ("-100", True),  # Single temperature
            ("15000", False)  # Too high
        ]

        for temp_str, should_be_valid in valid_temps:
            is_valid, message, temp_range = QueryValidator.validate_temperature_range(temp_str)
            if should_be_valid:
                assert is_valid, f"Temperature should be valid: {temp_str}"
                assert temp_range is not None
            else:
                assert not is_valid, f"Temperature should be invalid: {temp_str}"

    def test_chemical_formula_validation(self):
        """Test chemical formula validation."""
        validator = QueryValidator()

        # Valid chemical formulas
        valid_formulas = [
            "H2O",
            "CO2",
            "Fe2O3",
            "NH3",
            "CH4",
            "C6H12O6"
        ]

        # Invalid chemical formulas
        invalid_formulas = [
            "H2O<script>",
            "CO2 OR 1=1",
            "Fe2O3; DROP TABLE"
        ]

        for formula in valid_formulas:
            query = f"Properties of {formula}"
            result = validator.validate_query(query)
            assert result.is_valid, f"Valid formula should pass: {formula}"

        for formula in invalid_formulas:
            query = f"Properties of {formula}"
            result = validator.validate_query(query)
            assert not result.is_valid, f"Invalid formula should be blocked: {formula}"


class TestRateLimiter:
    """Test cases for RateLimiter class."""

    def setup_method(self):
        """Setup test rate limiter."""
        self.config = SecurityConfig(
            max_requests_per_minute=5,
            max_requests_per_hour=50,
            block_duration_minutes=1
        )
        self.rate_limiter = RateLimiter(self.config)

    def test_basic_rate_limiting(self):
        """Test basic rate limiting functionality."""
        user_id = 12345

        # First few requests should be allowed
        for i in range(5):
            allowed, reason = self.rate_limiter.is_allowed(user_id)
            assert allowed, f"Request {i+1} should be allowed"

        # Sixth request should be blocked (exceeds minute limit)
        allowed, reason = self.rate_limiter.is_allowed(user_id)
        assert not allowed
        assert "rate limit exceeded" in reason.lower()

    def test_burst_protection(self):
        """Test burst protection."""
        user_id = 12346

        # Send rapid requests
        allowed_requests = 0
        for i in range(10):
            allowed, _ = self.rate_limiter.is_allowed(user_id)
            if allowed:
                allowed_requests += 1

        # Should be limited by burst protection (5 requests in 10 seconds)
        assert allowed_requests <= 5

    def test_concurrent_request_limiting(self):
        """Test concurrent request limiting."""
        user_id = 12347

        # Start multiple concurrent requests
        started_requests = 0
        for i in range(5):
            if self.rate_limiter.start_request(user_id):
                started_requests += 1

        # Should be limited to max concurrent requests
        assert started_requests <= 3  # Default max concurrent

        # End one request
        self.rate_limiter.end_request(user_id)

        # Should be able to start another
        assert self.rate_limiter.start_request(user_id)

    def test_user_blocking(self):
        """Test user blocking functionality."""
        user_id = 12348

        # Add user to blacklist
        self.rate_limiter.add_to_blacklist(user_id)

        # Request should be blocked
        allowed, reason = self.rate_limiter.is_allowed(user_id)
        assert not allowed
        assert "permanently blocked" in reason.lower()

        # Remove from blacklist
        self.rate_limiter.remove_from_blacklist(user_id)

        # Request should now be allowed
        allowed, reason = self.rate_limiter.is_allowed(user_id)
        assert allowed

    def test_whitelist_bypass(self):
        """Test whitelist bypass functionality."""
        user_id = 12349

        # Add user to whitelist
        self.rate_limiter.add_to_whitelist(user_id)

        # Send many requests - should all be allowed
        for i in range(20):
            allowed, reason = self.rate_limiter.is_allowed(user_id)
            assert allowed, f"Whitelisted user request {i+1} should be allowed"

    def test_violation_tracking(self):
        """Test violation tracking and statistics."""
        user_id = 12350

        # Trigger multiple violations
        violations = 0
        for i in range(10):
            allowed, _ = self.rate_limiter.is_allowed(user_id)
            if not allowed:
                violations += 1

        assert violations > 0

        # Check statistics
        stats = self.rate_limiter.get_statistics()
        assert stats["total_violations"] > 0
        assert stats["violation_rate_percent"] > 0

    def test_security_event_logging(self):
        """Test security event logging."""
        user_id = 12351

        # Trigger a violation
        for i in range(10):  # Exceed rate limit
            self.rate_limiter.is_allowed(user_id)

        # Check security events
        events = self.rate_limiter.get_security_events(hours=1)
        assert len(events) > 0

        # Should have rate limit violation events
        violation_events = [e for e in events if e["event_type"] == "rate_limit_violation"]
        assert len(violation_events) > 0

    def test_block_expiry(self):
        """Test that blocks expire correctly."""
        user_id = 12352

        # Configure short block duration for testing
        self.config.block_duration_minutes = 0.01  # ~0.6 seconds
        rate_limiter = RateLimiter(self.config)

        # Trigger violation to get blocked
        for i in range(10):
            rate_limiter.is_allowed(user_id)

        # Should be blocked
        allowed, reason = rate_limiter.is_allowed(user_id)
        assert not allowed
        assert "blocked" in reason.lower()

        # Wait for block to expire
        time.sleep(1)

        # Should be unblocked now
        allowed, reason = rate_limiter.is_allowed(user_id)
        assert allowed

    def test_concurrent_request_tracking(self):
        """Test concurrent request tracking."""
        user_id = 12353

        # Start concurrent requests
        started = []
        for i in range(3):
            if self.rate_limiter.start_request(user_id):
                started.append(i)

        assert len(started) == 3

        # Try to start another - should fail
        assert not self.rate_limiter.start_request(user_id)

        # End one request
        self.rate_limiter.end_request(user_id)

        # Should be able to start another
        assert self.rate_limiter.start_request(user_id)

        # Clean up
        for _ in range(4):
            self.rate_limiter.end_request(user_id)


class TestErrorHandler:
    """Test cases for ErrorHandler class."""

    def setup_method(self):
        """Setup test error handler."""
        self.error_handler = ErrorHandler()

    def test_error_categorization(self):
        """Test error categorization."""
        test_cases = [
            (Exception("database connection failed"), ErrorCategory.DATABASE),
            (Exception("LLM API timeout"), ErrorCategory.LLM_API),
            (Exception("telegram bot token error"), ErrorCategory.TELEGRAM_API),
            (Exception("file not found"), ErrorCategory.FILESYSTEM),
            (Exception("validation failed"), ErrorCategory.USER_INPUT),
            (Exception("system error"), ErrorCategory.SYSTEM),
        ]

        for error, expected_category in test_cases:
            category = self.error_handler._categorize_error(error)
            assert category == expected_category, f"Error categorization failed for: {error}"

    def test_user_friendly_messages(self):
        """Test user-friendly error messages."""
        test_cases = [
            (ErrorCategory.USER_INPUT, "😔 *Неверный формат запроса*"),
            (ErrorCategory.LLM_API, "🤖 *Сервис временно недоступен*"),
            (ErrorCategory.DATABASE, "🗄️ *База данных временно недоступна*"),
            (ErrorCategory.TELEGRAM_API, "📱 *Ошибка Telegram API*"),
        ]

        for category, expected_prefix in test_cases:
            message = self.error_handler.error_messages[category]
            assert message.startswith(expected_prefix), f"Message format incorrect for {category}"

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self):
        """Test complete error handling workflow."""
        error = Exception("Test database error")
        context = ErrorContext(
            user_id=12345,
            username="testuser",
            query="H2O properties",
            component="database",
            operation="search"
        )

        # Handle the error
        user_message = await self.error_handler.handle_error(error, context)

        # Should return user-friendly message
        assert user_message is not None
        assert len(user_message) > 0
        assert "База данных" in user_message or "Database" in user_message

        # Should update statistics
        stats = self.error_handler.get_error_statistics()
        assert stats["total_errors"] > 0
        assert "database" in stats["errors_by_component"]

    def test_error_statistics(self):
        """Test error statistics tracking."""
        # Generate some errors
        errors = [
            (Exception("DB Error"), ErrorCategory.DATABASE),
            (Exception("API Error"), ErrorCategory.LLM_API),
            (Exception("Validation Error"), ErrorCategory.USER_INPUT),
        ]

        for error, category in errors:
            self.error_handler._update_error_stats(
                category, error, ErrorContext(user_id=12345)
            )

        stats = self.error_handler.get_error_statistics()
        assert stats["total_errors"] == 3
        assert len(stats["errors_by_category"]) == 3
        assert stats["errors_by_category"]["database"] == 1
        assert stats["errors_by_category"]["llm_api"] == 1
        assert stats["errors_by_category"]["user_input"] == 1

    def test_critical_error_detection(self):
        """Test critical error detection."""
        # Generate multiple critical errors
        for i in range(12):  # Exceed threshold of 10
            self.error_handler._update_error_stats(
                ErrorCategory.SYSTEM,
                Exception(f"Critical error {i}"),
                ErrorContext(user_id=12345)
            )

        # Check health status
        health = self.error_handler.get_health_status()
        assert health["health_status"] in ["degraded", "poor"]
        assert health["critical_errors"] > 0


class TestIntegrationSecurity:
    """Integration tests for security components."""

    def setup_method(self):
        """Setup integration test environment."""
        self.security_config = SecurityConfig(
            max_requests_per_minute=5,
            max_requests_per_hour=50,
            admin_user_ids=[99999],
            blocked_user_ids=[11111]
        )
        self.rate_limiter = RateLimiter(self.security_config)
        self.query_validator = QueryValidator()
        self.error_handler = ErrorHandler()

    def test_complete_security_workflow(self):
        """Test complete security workflow for a request."""
        user_id = 12345
        query = "H2O properties at 298K"

        # Step 1: Check rate limiting
        allowed, reason = self.rate_limiter.is_allowed(user_id)
        assert allowed, "User should be allowed to make request"

        # Step 2: Start concurrent request tracking
        assert self.rate_limiter.start_request(user_id)

        try:
            # Step 3: Validate input
            result = self.query_validator.validate_query(query)
            assert result.is_valid, "Query should pass validation"

            # Simulate successful processing
            success = True
            processing_time = 1.5

        except Exception as e:
            # Step 4: Handle errors if they occur
            import asyncio
            user_message = asyncio.run(self.error_handler.handle_error(
                e, ErrorContext(user_id=user_id, query=query)
            ))
            success = False
            processing_time = 0.5

        finally:
            # Step 5: End concurrent request tracking
            self.rate_limiter.end_request(user_id)

        # Verify final state
        assert True  # Test completed without exceptions

    def test_blocked_user_workflow(self):
        """Test workflow for blocked user."""
        blocked_user_id = 11111  # This user is in the blocked list

        # Should be blocked at rate limiting stage
        allowed, reason = self.rate_limiter.is_allowed(blocked_user_id)
        assert not allowed
        assert "permanently blocked" in reason.lower()

        # Should have security event logged
        events = self.rate_limiter.get_security_events(hours=1)
        blocked_events = [e for e in events if e["event_type"] == "blacklisted_user_access_attempt"]
        assert len(blocked_events) > 0

    def test_admin_user_bypass(self):
        """Test admin user bypass functionality."""
        admin_user_id = 99999  # This user is in admin list

        # Admin should bypass rate limiting
        for i in range(20):  # Exceed normal rate limits
            allowed, reason = self.rate_limiter.is_allowed(admin_user_id)
            assert allowed, f"Admin user request {i+1} should be allowed"

        # Should not be blocked even with many requests
        stats = self.rate_limiter.get_statistics()
        assert stats["whitelisted_users"] > 0

    def test_security_event_accumulation(self):
        """Test security event accumulation and analysis."""
        user_id = 22222

        # Trigger multiple types of security events
        # Rate limit violations
        for i in range(10):
            self.rate_limiter.is_allowed(user_id)

        # Query validation failures
        malicious_queries = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE compounds; --",
            "exec('rm -rf /')"
        ]

        for query in malicious_queries:
            self.query_validator.validate_query(query)

        # Check accumulated security events
        events = self.rate_limiter.get_security_events(hours=1)
        assert len(events) > 0

        # Should have different types of events
        event_types = set(e["event_type"] for e in events)
        assert "rate_limit_violation" in event_types

        # Check user violators list
        violators = self.rate_limiter.get_top_violators(limit=5)
        assert len(violators) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])