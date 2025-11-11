"""
Health check system for Telegram bot components.

This module provides comprehensive health monitoring for all system components
including database, LLM API, filesystem, memory, and custom health checks.
"""

import asyncio
import time
import sqlite3
import psutil
from typing import Dict, Any, List, Optional, Callable, Union
from datetime import datetime
from pathlib import Path
import aiohttp
import logging

from ..models.security import HealthCheckResult, MonitoringConfig
from ...thermo_agents.orchestrator import ThermoOrchestrator, ThermoOrchestratorConfig
from ...thermo_agents.search.database_connector import DatabaseConnector


logger = logging.getLogger(__name__)


class HealthChecker:
    """
    Comprehensive health checking system for Telegram bot components.

    Monitors:
    - Database connectivity and performance
    - LLM API availability and response times
    - Filesystem space and accessibility
    - Memory usage and availability
    - Custom component health checks
    """

    def __init__(self, config: MonitoringConfig, orchestrator: Optional[ThermoOrchestrator] = None):
        self.config = config
        self.orchestrator = orchestrator
        self.custom_checks: Dict[str, Callable] = {}
        self.last_check_time = 0.0
        self.check_history: List[HealthCheckResult] = []

    async def check_all_components(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check of all components.

        Returns:
            Dictionary with overall status and individual component results
        """
        start_time = time.time()
        health_status = {
            "overall_status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "check_duration_ms": 0,
            "components": {},
            "alerts": [],
            "recommendations": []
        }

        # Check all standard components
        component_checks = [
            ("database", self._check_database_health),
            ("llm_api", self._check_llm_api_health),
            ("filesystem", self._check_filesystem_health),
            ("memory", self._check_memory_health),
            ("cpu", self._check_cpu_health),
            ("network", self._check_network_health)
        ]

        # Run all checks concurrently
        tasks = []
        for component_name, check_func in component_checks:
            task = asyncio.create_task(self._run_component_check(component_name, check_func))
            tasks.append(task)

        # Run custom checks
        for check_name, check_func in self.custom_checks.items():
            task = asyncio.create_task(self._run_component_check(f"custom_{check_name}", check_func))
            tasks.append(task)

        # Wait for all checks to complete
        component_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        unhealthy_components = []
        degraded_components = []

        for i, result in enumerate(component_results):
            if isinstance(result, Exception):
                component_name = list(component_checks)[i][0] if i < len(component_checks) else f"custom_{i}"
                health_result = HealthCheckResult(
                    component=component_name,
                    status="unhealthy",
                    error_message=str(result),
                    timestamp=datetime.now()
                )
            else:
                health_result = result

            health_status["components"][health_result.component] = {
                "status": health_result.status,
                "response_time_ms": health_result.response_time_ms,
                "details": health_result.details,
                "error_message": health_result.error_message,
                "timestamp": health_result.timestamp.isoformat() if health_result.timestamp else None
            }

            # Track problematic components
            if health_result.status == "unhealthy":
                unhealthy_components.append(health_result.component)
            elif health_result.status == "degraded":
                degraded_components.append(health_result.component)

            # Store in history
            self.check_history.append(health_result)

        # Determine overall status
        if unhealthy_components:
            health_status["overall_status"] = "unhealthy"
            health_status["alerts"].append(f"Unhealthy components: {', '.join(unhealthy_components)}")
        elif degraded_components:
            health_status["overall_status"] = "degraded"
            health_status["alerts"].append(f"Degraded components: {', '.join(degraded_components)}")

        # Add recommendations based on results
        health_status["recommendations"] = self._generate_recommendations(health_status["components"])

        # Calculate total check duration
        health_status["check_duration_ms"] = (time.time() - start_time) * 1000
        self.last_check_time = time.time()

        # Limit history size
        if len(self.check_history) > 1000:
            self.check_history = self.check_history[-1000:]

        return health_status

    async def _run_component_check(
        self,
        component_name: str,
        check_func: Callable
    ) -> HealthCheckResult:
        """Run a single component health check with error handling."""
        try:
            return await check_func()
        except Exception as e:
            logger.error(f"Health check failed for {component_name}: {e}")
            return HealthCheckResult(
                component=component_name,
                status="unhealthy",
                error_message=str(e),
                timestamp=datetime.now()
            )

    async def _check_database_health(self) -> HealthCheckResult:
        """Check database connectivity and performance."""
        start_time = time.time()

        try:
            # Test database connection
            db_path = Path("data/thermo_data.db")
            if not db_path.exists():
                return HealthCheckResult(
                    component="database",
                    status="unhealthy",
                    error_message="Database file not found",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now()
                )

            # Test connection and query
            db_connector = DatabaseConnector(str(db_path))

            # Simple test query
            result = db_connector.execute_query("SELECT COUNT(*) as count FROM compounds LIMIT 1")
            response_time = (time.time() - start_time) * 1000

            if not result:
                return HealthCheckResult(
                    component="database",
                    status="unhealthy",
                    error_message="Database query returned no results",
                    response_time_ms=response_time,
                    timestamp=datetime.now()
                )

            # Get database stats
            stats_query = """
                SELECT
                    COUNT(*) as total_records,
                    COUNT(DISTINCT formula) as unique_formulas
                FROM compounds
            """
            stats_result = db_connector.execute_query(stats_query)

            details = {
                "record_count": stats_result[0]["total_records"] if stats_result else 0,
                "unique_formulas": stats_result[0]["unique_formulas"] if stats_result else 0,
                "file_size_mb": db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
            }

            # Determine status based on response time
            status = "healthy"
            if response_time > 5000:  # 5 seconds
                status = "degraded"
            if response_time > 10000:  # 10 seconds
                status = "unhealthy"

            return HealthCheckResult(
                component="database",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="database",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    async def _check_llm_api_health(self) -> HealthCheckResult:
        """Check LLM API availability and performance."""
        start_time = time.time()

        if not self.orchestrator:
            return HealthCheckResult(
                component="llm_api",
                status="degraded",
                error_message="Orchestrator not available",
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

        try:
            # Test LLM with a simple query
            test_result = await self.orchestrator.process_query(
                "H2O properties at 298K",
                test_mode=True
            )
            response_time = (time.time() - start_time) * 1000

            if not test_result:
                return HealthCheckResult(
                    component="llm_api",
                    status="unhealthy",
                    error_message="LLM API returned empty response",
                    response_time_ms=response_time,
                    timestamp=datetime.now()
                )

            details = {
                "test_successful": True,
                "response_length": len(test_result) if isinstance(test_result, str) else 0,
                "model": getattr(self.orchestrator, 'model_name', 'unknown')
            }

            # Determine status based on response time
            status = "healthy"
            if response_time > 15000:  # 15 seconds
                status = "degraded"
            if response_time > 30000:  # 30 seconds
                status = "unhealthy"

            return HealthCheckResult(
                component="llm_api",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="llm_api",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    async def _check_filesystem_health(self) -> HealthCheckResult:
        """Check filesystem space and accessibility."""
        start_time = time.time()

        try:
            # Check current directory
            current_dir = Path(".")
            if not current_dir.exists():
                return HealthCheckResult(
                    component="filesystem",
                    status="unhealthy",
                    error_message="Current directory not accessible",
                    response_time_ms=(time.time() - start_time) * 1000,
                    timestamp=datetime.now()
                )

            # Check disk space
            disk_usage = psutil.disk_usage('.')
            available_gb = disk_usage.free / (1024**3)
            total_gb = disk_usage.total / (1024**3)
            used_percent = (disk_usage.used / disk_usage.total) * 100

            # Check critical directories
            critical_dirs = ["data", "logs", "src"]
            accessible_dirs = []
            inaccessible_dirs = []

            for dir_name in critical_dirs:
                dir_path = Path(dir_name)
                if dir_path.exists() and dir_path.is_dir():
                    if dir_path.exists() and os.access(dir_path, os.R_OK | os.W_OK):
                        accessible_dirs.append(dir_name)
                    else:
                        inaccessible_dirs.append(dir_name)
                else:
                    # Try to create directory if it doesn't exist
                    try:
                        dir_path.mkdir(parents=True, exist_ok=True)
                        accessible_dirs.append(dir_name)
                    except Exception:
                        inaccessible_dirs.append(dir_name)

            details = {
                "available_space_gb": available_gb,
                "total_space_gb": total_gb,
                "used_percent": used_percent,
                "accessible_directories": accessible_dirs,
                "inaccessible_directories": inaccessible_dirs
            }

            # Determine status
            status = "healthy"
            if available_gb < 1.0:  # Less than 1GB
                status = "unhealthy"
            elif available_gb < 5.0:  # Less than 5GB
                status = "degraded"
            elif inaccessible_dirs:
                status = "degraded"

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                component="filesystem",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="filesystem",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    async def _check_memory_health(self) -> HealthCheckResult:
        """Check memory usage and availability."""
        start_time = time.time()

        try:
            memory = psutil.virtual_memory()
            process = psutil.Process()

            process_memory = process.memory_info()

            details = {
                "total_memory_gb": memory.total / (1024**3),
                "available_memory_gb": memory.available / (1024**3),
                "used_memory_gb": memory.used / (1024**3),
                "memory_percent": memory.percent,
                "process_memory_rss_mb": process_memory.rss / (1024**2),
                "process_memory_vms_mb": process_memory.vms / (1024**2),
                "process_memory_percent": process.memory_percent()
            }

            # Determine status
            status = "healthy"
            if memory.percent > 90:
                status = "unhealthy"
            elif memory.percent > 80:
                status = "degraded"

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                component="memory",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="memory",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    async def _check_cpu_health(self) -> HealthCheckResult:
        """Check CPU usage and load."""
        start_time = time.time()

        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None

            process = psutil.Process()
            process_cpu = process.cpu_percent()

            details = {
                "cpu_percent": cpu_percent,
                "cpu_count": cpu_count,
                "process_cpu_percent": process_cpu,
                "load_average": load_avg
            }

            # Determine status
            status = "healthy"
            if cpu_percent > 90:
                status = "unhealthy"
            elif cpu_percent > 75:
                status = "degraded"

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                component="cpu",
                status=status,
                response_time_ms=response_time,
                details=details,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="cpu",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    async def _check_network_health(self) -> HealthCheckResult:
        """Check network connectivity."""
        start_time = time.time()

        try:
            # Test basic internet connectivity
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get("https://httpbin.org/get") as response:
                    if response.status == 200:
                        network_status = "healthy"
                        error_message = None
                    else:
                        network_status = "degraded"
                        error_message = f"HTTP {response.status}"

            # Test specific endpoints if available
            endpoints_to_test = []
            if self.orchestrator and hasattr(self.orchestrator, 'config'):
                llm_base_url = getattr(self.orchestrator.config, 'llm_base_url', None)
                if llm_base_url:
                    endpoints_to_test.append(("LLM API", llm_base_url))

            endpoint_results = {}
            for name, url in endpoints_to_test:
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        async with session.get(url) as response:
                            endpoint_results[name] = {
                                "status": response.status,
                                "response_time_ms": (time.time() - start_time) * 1000
                            }
                except Exception as e:
                    endpoint_results[name] = {
                        "error": str(e)
                    }

            details = {
                "basic_connectivity": network_status,
                "tested_endpoints": endpoint_results
            }

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                component="network",
                status=network_status,
                response_time_ms=response_time,
                details=details,
                error_message=error_message,
                timestamp=datetime.now()
            )

        except Exception as e:
            return HealthCheckResult(
                component="network",
                status="unhealthy",
                error_message=str(e),
                response_time_ms=(time.time() - start_time) * 1000,
                timestamp=datetime.now()
            )

    def add_custom_check(self, name: str, check_func: Callable[[], HealthCheckResult]) -> None:
        """Add a custom health check."""
        self.custom_checks[name] = check_func

    def remove_custom_check(self, name: str) -> None:
        """Remove a custom health check."""
        self.custom_checks.pop(name, None)

    def _generate_recommendations(self, components: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on component health."""
        recommendations = []

        for component_name, component_data in components.items():
            status = component_data.get("status", "unknown")
            details = component_data.get("details", {})

            if component_name == "memory" and status in ["degraded", "unhealthy"]:
                used_percent = details.get("memory_percent", 0)
                if used_percent > 80:
                    recommendations.append(
                        f"High memory usage ({used_percent:.1f}%). Consider restarting the bot or upgrading memory."
                    )

            elif component_name == "filesystem" and status in ["degraded", "unhealthy"]:
                available_gb = details.get("available_space_gb", 0)
                if available_gb < 5:
                    recommendations.append(
                        f"Low disk space ({available_gb:.1f}GB available). Clean up old logs and temporary files."
                    )

            elif component_name == "database" and status == "unhealthy":
                recommendations.append(
                    "Database health check failed. Check database file integrity and permissions."
                )

            elif component_name == "llm_api" and status == "unhealthy":
                recommendations.append(
                    "LLM API is not responding. Check API key, network connectivity, and service status."
                )

            elif component_name == "cpu" and status in ["degraded", "unhealthy"]:
                cpu_percent = details.get("cpu_percent", 0)
                if cpu_percent > 75:
                    recommendations.append(
                        f"High CPU usage ({cpu_percent:.1f}%). Check for excessive load or optimize processing."
                    )

        if not recommendations:
            recommendations.append("All components are operating normally.")

        return recommendations

    def get_health_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get health check history for the specified time period."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        filtered_history = []
        for result in self.check_history:
            if result.timestamp and result.timestamp >= cutoff_time:
                filtered_history.append({
                    "component": result.component,
                    "status": result.status,
                    "response_time_ms": result.response_time_ms,
                    "error_message": result.error_message,
                    "timestamp": result.timestamp.isoformat()
                })

        return filtered_history

    def get_component_status_summary(self) -> Dict[str, str]:
        """Get current status summary for all components."""
        if not self.check_history:
            return {}

        # Get the most recent result for each component
        latest_results = {}
        for result in reversed(self.check_history):
            if result.component not in latest_results:
                latest_results[result.component] = result.status

        return latest_results