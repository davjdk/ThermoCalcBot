# Telegram Bot Security and Monitoring Guide

This guide provides comprehensive documentation for the security and monitoring system implemented for the ThermoSystem Telegram bot integration.

## Overview

The security and monitoring system consists of several integrated components that work together to provide:

- **Input Validation & Sanitization** - Prevents XSS, SQL injection, and code injection attacks
- **Rate Limiting & Access Control** - Prevents abuse and ensures fair usage
- **Error Handling & Graceful Degradation** - Provides robust error management
- **Performance Monitoring** - Tracks system performance and usage patterns
- **Health Checks** - Monitors component health and system status
- **Alert Management** - Provides real-time notifications for critical issues
- **Session Logging** - Comprehensive logging with privacy protection

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Security Layer                              │
├─────────────────────────────────────────────────────────────────┤
│  QueryValidator  │  RateLimiter  │  ErrorHandler │  SessionLogger │
└─────────────────┬─────────────────┬─────────────────┬─────────────┘
                  │                 │                 │
┌─────────────────▼─────────────────▼─────────────────▼─────────────┐
│                   Monitoring Layer                              │
├─────────────────────────────────────────────────────────────────┤
│  BotMetrics  │  QueryAnalytics  │  HealthChecker  │  AlertManager │
└─────────────────────────────────────────────────────────────────┘
                                  │
┌─────────────────────────────────▼─────────────────────────────────┐
│                      ThermoSystem Core                          │
└─────────────────────────────────────────────────────────────────┘
```

## Security Components

### QueryValidator

The `QueryValidator` class provides comprehensive input validation and sanitization:

```python
from src.telegram_bot.security import QueryValidator

validator = QueryValidator()

# Validate user input
result = validator.validate_query("H2O properties at 298K")
if result.is_valid:
    safe_query = result.sanitized_query
    # Process the safe query
else:
    # Handle validation error
    print(f"Invalid query: {result.message}")
```

**Key Features:**
- XSS prevention (HTML tag filtering)
- SQL injection prevention
- Code injection prevention
- Query length limits
- Chemical formula validation
- HTML entity escaping

### RateLimiter

The `RateLimiter` class manages user access and prevents abuse:

```python
from src.telegram_bot.security import RateLimiter
from src.telegram_bot.models.security import SecurityConfig

config = SecurityConfig(
    max_requests_per_minute=30,
    max_requests_per_hour=200,
    admin_user_ids=[12345],  # Admin users bypass limits
    blocked_user_ids=[67890]  # Blocked users
)

rate_limiter = RateLimiter(config)

# Check if request is allowed
allowed, reason = rate_limiter.is_allowed(user_id=12345)
if allowed:
    # Process request
    rate_limiter.start_request(user_id)
    try:
        # ... process request ...
        pass
    finally:
        rate_limiter.end_request(user_id)
else:
    # Handle rate limit exceeded
    print(f"Request blocked: {reason}")
```

**Key Features:**
- Multiple time window limits (minute/hour/day)
- Burst protection
- Concurrent request limiting
- User blocking with automatic expiry
- Whitelist/blacklist support
- Security event tracking

### ErrorHandler

The `ErrorHandler` class provides centralized error handling:

```python
from src.telegram_bot.security import ErrorHandler, ErrorContext

error_handler = ErrorHandler()

async def handle_request_error(error: Exception, user_id: int, query: str):
    context = ErrorContext(
        user_id=user_id,
        query=query,
        component="database",
        operation="search"
    )

    user_message = await error_handler.handle_error(error, context)
    return user_message
```

**Key Features:**
- Error categorization (user input, LLM API, database, etc.)
- User-friendly error messages
- Recovery suggestions
- Error statistics and tracking
- Debug information for developers

## Monitoring Components

### BotMetrics

The `BotMetrics` class collects performance and usage metrics:

```python
from src.telegram_bot.monitoring import BotMetrics
from src.telegram_bot.models.security import MonitoringConfig

config = MonitoringConfig(enable_metrics=True)
metrics = BotMetrics(config)

# Record a request
metrics.record_request(
    user_id=12345,
    username="testuser",
    query="H2O properties at 298K",
    processing_time=1.5,
    success=True,
    timing_breakdown={
        "llm": 0.8,
        "database": 0.4,
        "calculation": 0.2,
        "formatting": 0.1
    }
)

# Get performance statistics
stats = metrics.get_performance_stats()
print(f"Total requests: {stats['total_requests']}")
print(f"Success rate: {stats['success_rate_percent']:.1f}%")
print(f"Average response time: {stats['avg_response_time_seconds']:.2f}s")
```

**Key Features:**
- Request statistics and success rates
- Response time tracking
- User activity monitoring
- System resource monitoring
- Performance analytics

### QueryAnalytics

The `QueryAnalytics` class analyzes query patterns and usage:

```python
from src.telegram_bot.monitoring import QueryAnalytics

analytics = QueryAnalytics()

# Record a query
analytics.record_query(
    user_id=12345,
    query="H2O properties at 298K",
    extracted_params=extracted_params,
    processing_time=1.5,
    success=True
)

# Get top queries
top_queries = analytics.get_top_queries(limit=10)
for query_data in top_queries:
    print(f"Query: {query_data['query']}")
    print(f"Count: {query_data['count']}")
    print(f"Success rate: {query_data['success_rate']:.1%}")
```

**Key Features:**
- Query pattern recognition
- Popular query tracking
- Compound usage analytics
- Reaction analysis
- Usage trend analysis

### HealthChecker

The `HealthChecker` class monitors system component health:

```python
from src.telegram_bot.monitoring import HealthChecker
from src.telegram_bot.models.security import MonitoringConfig

config = MonitoringConfig(enable_health_checks=True)
health_checker = HealthChecker(config)

# Run comprehensive health check
health_status = await health_checker.check_all_components()

print(f"Overall status: {health_status['overall_status']}")
print(f"Check duration: {health_status['check_duration_ms']:.1f}ms")

for component, status in health_status['components'].items():
    print(f"{component}: {status['status']} ({status['response_time_ms']:.1f}ms)")
```

**Key Features:**
- Database connectivity monitoring
- LLM API availability checks
- Filesystem monitoring
- Memory and CPU tracking
- Custom health checks
- Automated recommendations

### AlertManager

The `AlertManager` class handles alert notifications:

```python
from src.telegram_bot.monitoring import AlertManager
from src.telegram_bot.models.security import SecurityConfig, MonitoringConfig

monitoring_config = MonitoringConfig(enable_alerts=True)
security_config = SecurityConfig(alert_thresholds={
    "error_rate_percent": 10.0,
    "memory_usage_percent": 80.0,
    "response_time_seconds": 30.0
})

alert_manager = AlertManager(monitoring_config, security_config)

# Check for alerts based on current metrics
metrics = {"error_rate_percent": 15.0, "memory_usage_percent": 85.0}
health_status = {"components": {"database": {"status": "degraded"}}}

triggered_alerts = await alert_manager.check_and_send_alerts(metrics, health_status)
for alert in triggered_alerts:
    print(f"Alert: {alert.rule_name} - {alert.message}")
```

**Key Features:**
- Configurable alert rules
- Multiple severity levels
- Cooldown periods to prevent spam
- Alert history and tracking
- Telegram notification integration
- Custom alert rules

## Session Logging

The `TelegramSessionLogger` provides comprehensive session logging with privacy protection:

```python
from src.telegram_bot.logging import TelegramSessionLogger, TelegramSessionManager

# Create session manager
session_manager = TelegramSessionManager()

# Create session for user
session = session_manager.create_session(user_id=12345, username="testuser")

try:
    # Log user request
    session.log_user_query("H2O properties at 298K")

    # Log processing steps
    session.log_llm_extraction(confidence=0.95, extraction_time=0.5)
    session.log_database_search(compounds_found=1, search_time=0.2)
    session.log_calculation_completed(calculation_time=0.3)

    # Log response
    session.log_bot_response(response_length=150, processing_time=1.0)

finally:
    # Close session
    session.close_session("completed")
```

**Key Features:**
- Privacy-focused logging (only user IDs, not personal data)
- Structured JSON logging
- Session performance metrics
- Automatic log rotation
- Error and security event logging

## Configuration

### Security Configuration

```python
from src.telegram_bot.models.security import SecurityConfig

security_config = SecurityConfig(
    # Rate limiting
    max_requests_per_minute=30,
    max_requests_per_hour=200,
    block_duration_minutes=60,

    # User access control
    admin_user_ids=[12345, 67890],  # Admin users bypass limits
    blocked_user_ids=[11111, 22222],  # Permanently blocked users

    # Alert thresholds
    alert_thresholds={
        "error_rate_percent": 10.0,
        "memory_usage_percent": 80.0,
        "disk_space_gb": 1.0,
        "response_time_seconds": 30.0,
        "security_events_per_hour": 50
    },

    # Feature toggles
    enable_rate_limiting=True,
    enable_input_validation=True
)
```

### Monitoring Configuration

```python
from src.telegram_bot.models.security import MonitoringConfig

monitoring_config = MonitoringConfig(
    # Feature toggles
    enable_metrics=True,
    enable_health_checks=True,
    enable_alerts=True,
    enable_analytics=True,

    # Retention settings
    metrics_retention_days=30,
    health_check_interval_seconds=300,  # 5 minutes
    alert_cooldown_seconds=300,  # 5 minutes

    # Logging level
    log_level="INFO"
)
```

## Integration Example

Here's a complete example of integrating all components:

```python
import asyncio
from src.telegram_bot.security import QueryValidator, RateLimiter, ErrorHandler, ErrorContext
from src.telegram_bot.monitoring import BotMetrics, QueryAnalytics, HealthChecker, AlertManager
from src.telegram_bot.logging import TelegramSessionManager
from src.telegram_bot.models.security import SecurityConfig, MonitoringConfig

class TelegramBotSecurity:
    def __init__(self):
        # Configuration
        self.security_config = SecurityConfig(
            max_requests_per_minute=30,
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
        self.analytics = QueryAnalytics()
        self.health_checker = HealthChecker(self.monitoring_config)
        self.alert_manager = AlertManager(self.monitoring_config, self.security_config)
        self.session_manager = TelegramSessionManager()

    async def process_user_request(self, user_id: int, username: str, query: str):
        """Process a user request with full security and monitoring."""
        # Create session
        session = self.session_manager.create_session(user_id, username, user_id)

        try:
            # 1. Rate limiting check
            allowed, reason = self.rate_limiter.is_allowed(user_id)
            if not allowed:
                session.log_security_event("rate_limit_block", {"reason": reason}, "medium")
                return f"⏱️ {reason}"

            # 2. Start concurrent request tracking
            if not self.rate_limiter.start_request(user_id):
                return "⚠️ Too many concurrent requests"

            # 3. Log user request
            session.log_user_request(query)

            # 4. Input validation
            validation_result = self.query_validator.validate_query(query)
            if not validation_result.is_valid:
                session.log_security_event("validation_failure", {
                    "query": query[:100],
                    "reason": validation_result.message
                }, "high")

                # Record failed request
                self.metrics.record_request(
                    user_id=user_id,
                    username=username,
                    query=query,
                    processing_time=0.1,
                    success=False,
                    error_type="validation_failed"
                )

                return f"❌ {validation_result.message}"

            # 5. Process the request (simulate)
            processing_start = time.time()

            try:
                # Simulate processing steps
                await asyncio.sleep(0.1)  # Simulate work

                # Log processing steps
                session.log_llm_extraction(confidence=0.95, extraction_time=0.05)
                session.log_database_search(compounds_found=1, search_time=0.02)
                session.log_calculation_completed(calculation_time=0.03)

                # Generate response
                response = f"✅ Processed: {validation_result.sanitized_query}"
                processing_time = time.time() - processing_start

                # Log successful processing
                session.log_bot_response(len(response), processing_time)

                # Record metrics
                self.metrics.record_request(
                    user_id=user_id,
                    username=username,
                    query=query,
                    processing_time=processing_time,
                    success=True,
                    timing_breakdown={
                        "validation": 0.01,
                        "llm": 0.05,
                        "database": 0.02,
                        "calculation": 0.03
                    }
                )

                # Record in analytics
                self.analytics.record_query(
                    user_id=user_id,
                    query=query,
                    extracted_params=None,
                    processing_time=processing_time,
                    success=True
                )

                return response

            except Exception as e:
                # Handle processing error
                error_context = ErrorContext(
                    user_id=user_id,
                    username=username,
                    query=query,
                    component="processing",
                    operation="calculation"
                )

                user_message = await self.error_handler.handle_error(e, error_context)
                session.log_error("processing_error", str(e), {"component": "processing"})

                # Record failed request
                self.metrics.record_request(
                    user_id=user_id,
                    username=username,
                    query=query,
                    processing_time=time.time() - processing_start,
                    success=False,
                    error_type="processing_error"
                )

                return user_message

        finally:
            # 6. End concurrent request tracking
            self.rate_limiter.end_request(user_id)

            # 7. Close session
            session.close_session("completed")

    async def run_health_checks(self):
        """Run periodic health checks."""
        health_status = await self.health_checker.check_all_components()

        # Check for alerts
        metrics = self.metrics.get_performance_stats()
        triggered_alerts = await self.alert_manager.check_and_send_alerts(
            metrics, health_status
        )

        return health_status, triggered_alerts

    def get_system_statistics(self):
        """Get comprehensive system statistics."""
        return {
            "performance": self.metrics.get_performance_stats(),
            "users": self.metrics.get_user_stats(),
            "analytics": self.analytics.get_usage_trends(),
            "security": self.rate_limiter.get_statistics(),
            "alerts": self.alert_manager.get_alert_statistics(),
            "health": self.health_checker.get_component_status_summary()
        }

# Usage example
async def main():
    bot = TelegramBotSecurity()

    # Process some requests
    responses = []
    for i in range(5):
        response = await bot.process_user_request(
            user_id=12345 + i,
            username=f"user{i}",
            query=f"H2O properties at {298 + i * 10}K"
        )
        responses.append(response)

    # Run health checks
    health_status, alerts = await bot.run_health_checks()

    # Get system statistics
    stats = bot.get_system_statistics()

    print("Responses:", responses)
    print("Health Status:", health_status["overall_status"])
    print("System Stats:", stats)

if __name__ == "__main__":
    asyncio.run(main())
```

## Best Practices

### Security
1. **Always validate input** before processing
2. **Use rate limiting** to prevent abuse
3. **Log security events** for monitoring
4. **Regularly update** security rules and patterns
5. **Monitor for anomalies** in user behavior

### Monitoring
1. **Track key metrics** consistently
2. **Set appropriate alert thresholds**
3. **Regular health checks** for early detection
4. **Analyze usage patterns** for optimization
5. **Maintain logs** for troubleshooting and compliance

### Performance
1. **Optimize query processing** time
2. **Use efficient data structures** for tracking
3. **Implement cleanup** for old data
4. **Monitor resource usage** continuously
5. **Scale components** independently as needed

## Troubleshooting

### Common Issues

**Rate Limiting Issues:**
- Check if user is on whitelist/blacklist
- Verify time window configurations
- Monitor concurrent request limits
- Review security event logs

**Performance Issues:**
- Check system resource usage
- Analyze query processing times
- Review health check results
- Monitor alert patterns

**Security Issues:**
- Review validation logs
- Check for new attack patterns
- Update forbidden patterns
- Monitor user behavior analytics

### Debug Information

Enable debug mode for detailed logging:

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Create error context with debug mode
error_context = ErrorContext(
    user_id=user_id,
    query=query,
    is_debug_mode=True
)
```

## Maintenance

### Regular Tasks
1. **Review and update** security patterns monthly
2. **Clean up old logs** and metrics data
3. **Update alert thresholds** based on usage patterns
4. **Monitor system performance** trends
5. **Backup configuration** and important data

### Scaling Considerations
1. **Distribute metrics collection** across multiple instances
2. **Use external storage** for long-term analytics
3. **Implement centralized alerting** for multiple bots
4. **Cache frequent queries** to improve performance
5. **Load balance** health checks across systems

## Security Checklist

- [ ] Input validation is enabled for all user inputs
- [ ] Rate limiting is configured with appropriate limits
- [ ] Error handling provides user-friendly messages
- [ ] Security events are logged and monitored
- [ ] Alert thresholds are set for critical metrics
- [ ] Health checks cover all system components
- [ ] Session logging protects user privacy
- [ ] Admin access is properly controlled
- [ ] System monitoring is comprehensive
- [ ] Backup and recovery procedures are in place

This security and monitoring system provides a robust foundation for the Telegram bot integration, ensuring safe operation, excellent performance, and comprehensive observability.