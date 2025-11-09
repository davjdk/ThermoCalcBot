"""
Health Checker для Telegram бота.

Мониторинг состояния компонентов системы:
- ThermoOrchestrator и база данных
- LLM API доступность
- Системные ресурсы
- Файловая система
- Производительность
"""

import asyncio
import time
import psutil
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..config import TelegramBotConfig
from ..utils.thermo_integration import ThermoIntegration


@dataclass
class HealthStatus:
    """Статус здоровья компонента."""
    component: str
    status: str  # "healthy", "degraded", "unhealthy"
    response_time_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None
    last_check: float = 0.0


@dataclass
class SystemMetrics:
    """Системные метрики."""
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_percent: float
    disk_free_gb: float
    active_processes: int
    uptime_seconds: float


class HealthChecker:
    """Комплексная проверка здоровья системы."""

    def __init__(self, config: TelegramBotConfig, thermo_integration: ThermoIntegration):
        self.config = config
        self.thermo_integration = thermo_integration
        self.start_time = time.time()

        # Кэш результатов проверки
        self.health_cache: Dict[str, HealthStatus] = {}
        self.cache_ttl = 60  # секунды

        # Пороги для здоровья
        self.CPU_WARNING_THRESHOLD = 80.0  # %
        self.MEMORY_WARNING_THRESHOLD = 80.0  # %
        self.DISK_WARNING_THRESHOLD = 90.0  # %
        self.RESPONSE_TIME_WARNING = 5000  # ms
        self.RESPONSE_TIME_CRITICAL = 10000  # ms

    async def check_all_components(self) -> Dict[str, Any]:
        """
        Комплексная проверка всех компонентов.

        Returns:
            Словарь с результатами проверки здоровья
        """
        current_time = time.time()
        overall_status = "healthy"
        warnings = []
        errors = []

        # Проверка компонентов
        component_results = {}

        # 1. ThermoOrchestrator
        orchestrator_status = await self._check_thermo_orchestrator(current_time)
        component_results["orchestrator"] = orchestrator_status
        if orchestrator_status.status != "healthy":
            errors.append(f"ThermoOrchestrator: {orchestrator_status.error}")
            overall_status = "unhealthy"

        # 2. База данных
        db_status = await self._check_database(current_time)
        component_results["database"] = db_status
        if db_status.status == "unhealthy":
            errors.append(f"Database: {db_status.error}")
            overall_status = "unhealthy"

        # 3. LLM API
        llm_status = await self._check_llm_api(current_time)
        component_results["llm_api"] = llm_status
        if llm_status.status == "unhealthy":
            errors.append(f"LLM API: {llm_status.error}")
            overall_status = "unhealthy"
        elif llm_status.status == "degraded":
            warnings.append(f"LLM API: {llm_status.error}")

        # 4. Файловая система
        fs_status = await self._check_filesystem(current_time)
        component_results["filesystem"] = fs_status
        if fs_status.status == "unhealthy":
            errors.append(f"Filesystem: {fs_status.error}")
            overall_status = "unhealthy"
        elif fs_status.status == "degraded":
            warnings.append(f"Filesystem: {fs_status.error}")

        # 5. Системные ресурсы
        system_status = await self._check_system_resources(current_time)
        component_results["system"] = system_status
        if system_status.status == "unhealthy":
            errors.append(f"System resources: {system_status.error}")
            overall_status = "unhealthy"
        elif system_status.status == "degraded":
            warnings.append(f"System resources: {system_status.error}")

        # Расчёт общего процента здоровья
        health_score = self._calculate_health_score(component_results)

        # Определение итогового статуса
        if overall_status == "healthy" and warnings:
            overall_status = "degraded"

        return {
            "overall_status": overall_status,
            "health_score": health_score,
            "components": component_results,
            "warnings": warnings,
            "errors": errors,
            "uptime_seconds": time.time() - self.start_time,
            "check_timestamp": current_time
        }

    async def _check_thermo_orchestrator(self, current_time: float) -> HealthStatus:
        """Проверка здоровья ThermoOrchestrator."""
        cache_key = "orchestrator"

        # Проверка кэша
        if self._is_cache_valid(cache_key, current_time):
            return self.health_cache[cache_key]

        start_time = time.time()

        try:
            # Базовая проверка интеграции
            health_result = await self.thermo_integration.health_check()
            response_time = (time.time() - start_time) * 1000

            if health_result["status"] == "healthy":
                status = "healthy"
                error = None
            else:
                status = "unhealthy"
                error = health_result.get("error", "Unknown error")

            details = {
                "subcomponents": health_result.get("components", {}),
                "performance": health_result.get("performance", {}),
                "db_path": str(self.config.thermo_db_path)
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            status = "unhealthy"
            error = str(e)
            details = {}

        health_status = HealthStatus(
            component="ThermoOrchestrator",
            status=status,
            response_time_ms=response_time,
            details=details,
            error=error,
            last_check=current_time
        )

        self.health_cache[cache_key] = health_status
        return health_status

    async def _check_database(self, current_time: float) -> HealthStatus:
        """Проверка здоровья базы данных."""
        cache_key = "database"

        if self._is_cache_valid(cache_key, current_time):
            return self.health_cache[cache_key]

        start_time = time.time()

        try:
            db_path = self.config.thermo_db_path

            # Проверка существования файла
            if not db_path.exists():
                raise FileNotFoundError(f"Database file not found: {db_path}")

            # Проверка размера файла
            file_size = db_path.stat().st_size
            if file_size < 1000000:  # меньше 1MB
                raise ValueError(f"Database file too small: {file_size} bytes")

            # Проверка доступности для чтения
            try:
                with open(db_path, 'rb') as f:
                    header = f.read(100)  # читаем заголовок
            except Exception as e:
                raise PermissionError(f"Cannot read database file: {str(e)}")

            response_time = (time.time() - start_time) * 1000
            status = "healthy"
            error = None
            details = {
                "path": str(db_path),
                "size_bytes": file_size,
                "size_mb": round(file_size / 1024 / 1024, 2),
                "readable": True
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            status = "unhealthy"
            error = str(e)
            details = {}

        health_status = HealthStatus(
            component="Database",
            status=status,
            response_time_ms=response_time,
            details=details,
            error=error,
            last_check=current_time
        )

        self.health_cache[cache_key] = health_status
        return health_status

    async def _check_llm_api(self, current_time: float) -> HealthStatus:
        """Проверка здоровья LLM API."""
        cache_key = "llm_api"

        if self._is_cache_valid(cache_key, current_time):
            return self.health_cache[cache_key]

        start_time = time.time()

        try:
            # Простой тестовый запрос
            if not self.thermo_integration.orchestrator:
                raise RuntimeError("ThermoOrchestrator not initialized")

            # Быстрая проверка через базовый запрос
            test_query = "H2O"
            result = await self.thermo_integration.process_query(test_query, 0)

            response_time = (time.time() - start_time) * 1000

            if result.success:
                if response_time > self.RESPONSE_TIME_CRITICAL:
                    status = "unhealthy"
                    error = f"Response time too slow: {response_time:.0f}ms"
                elif response_time > self.RESPONSE_TIME_WARNING:
                    status = "degraded"
                    error = f"Response time slow: {response_time:.0f}ms"
                else:
                    status = "healthy"
                    error = None
            else:
                status = "unhealthy"
                error = f"Query failed: {result.error}"

            details = {
                "test_query": test_query,
                "result_length": len(result.content) if result.content else 0,
                "api_url": self.config.llm_base_url,
                "model": self.config.llm_model
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            status = "unhealthy"
            error = str(e)
            details = {}

        health_status = HealthStatus(
            component="LLM_API",
            status=status,
            response_time_ms=response_time,
            details=details,
            error=error,
            last_check=current_time
        )

        self.health_cache[cache_key] = health_status
        return health_status

    async def _check_filesystem(self, current_time: float) -> HealthStatus:
        """Проверка здоровья файловой системы."""
        cache_key = "filesystem"

        if self._is_cache_valid(cache_key, current_time):
            return self.health_cache[cache_key]

        start_time = time.time()

        try:
            # Проверка директории временных файлов
            temp_dir = self.config.temp_file_dir
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Проверка доступности записи
            test_file = temp_dir / f"health_check_{int(time.time())}.tmp"
            try:
                test_file.write_text("health check")
                test_file.unlink()  # удаление тестового файла
                writeable = True
            except Exception as e:
                writeable = False
                raise PermissionError(f"Cannot write to temp directory: {str(e)}")

            # Проверка дискового пространства
            disk_usage = psutil.disk_usage(str(temp_dir.parent))
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            disk_free_gb = disk_usage.free / (1024**3)

            if disk_percent > self.DISK_WARNING_THRESHOLD:
                status = "degraded"
                error = f"Low disk space: {disk_percent:.1f}% used"
            else:
                status = "healthy"
                error = None

            response_time = (time.time() - start_time) * 1000

            details = {
                "temp_dir": str(temp_dir),
                "writeable": writeable,
                "disk_percent": disk_percent,
                "disk_free_gb": disk_free_gb,
                "disk_total_gb": disk_usage.total / (1024**3)
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            status = "unhealthy"
            error = str(e)
            details = {}

        health_status = HealthStatus(
            component="Filesystem",
            status=status,
            response_time_ms=response_time,
            details=details,
            error=error,
            last_check=current_time
        )

        self.health_cache[cache_key] = health_status
        return health_status

    async def _check_system_resources(self, current_time: float) -> HealthStatus:
        """Проверка системных ресурсов."""
        cache_key = "system"

        if self._is_cache_valid(cache_key, current_time):
            return self.health_cache[cache_key]

        start_time = time.time()

        try:
            # Получение системных метрик
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Количество процессов
            process_count = len(psutil.pids())

            # Анализ ресурсов
            issues = []

            if cpu_percent > self.CPU_WARNING_THRESHOLD:
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")

            if memory.percent > self.MEMORY_WARNING_THRESHOLD:
                issues.append(f"High memory usage: {memory.percent:.1f}%")

            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > self.DISK_WARNING_THRESHOLD:
                issues.append(f"High disk usage: {disk_percent:.1f}%")

            if issues:
                status = "degraded"
                error = "; ".join(issues)
            else:
                status = "healthy"
                error = None

            response_time = (time.time() - start_time) * 1000

            details = {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_mb": memory.used / (1024**2),
                "disk_percent": disk_percent,
                "disk_free_gb": disk.free / (1024**3),
                "process_count": process_count,
                "uptime_hours": (time.time() - self.start_time) / 3600
            }

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            status = "unhealthy"
            error = str(e)
            details = {}

        health_status = HealthStatus(
            component="System",
            status=status,
            response_time_ms=response_time,
            details=details,
            error=error,
            last_check=current_time
        )

        self.health_cache[cache_key] = health_status
        return health_status

    def _is_cache_valid(self, cache_key: str, current_time: float) -> bool:
        """Проверка валидности кэша."""
        if cache_key not in self.health_cache:
            return False

        cached = self.health_cache[cache_key]
        return (current_time - cached.last_check) < self.cache_ttl

    def _calculate_health_score(self, component_results: Dict[str, HealthStatus]) -> float:
        """
        Расчёт общего процента здоровья.

        Returns:
            Значение от 0.0 до 100.0
        """
        if not component_results:
            return 0.0

        total_score = 0.0
        component_count = len(component_results)

        for component, health_status in component_results.items():
            if health_status.status == "healthy":
                score = 100.0
            elif health_status.status == "degraded":
                score = 50.0
            else:  # unhealthy
                score = 0.0

            # Учёт времени ответа
            if health_status.response_time_ms > self.RESPONSE_TIME_CRITICAL:
                score *= 0.5
            elif health_status.response_time_ms > self.RESPONSE_TIME_WARNING:
                score *= 0.8

            total_score += score

        return total_score / component_count

    async def get_system_metrics(self) -> SystemMetrics:
        """Получение текущих системных метрик."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            return SystemMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_mb=memory.used / (1024**2),
                disk_percent=(disk.used / disk.total) * 100,
                disk_free_gb=disk.free / (1024**3),
                active_processes=len(psutil.pids()),
                uptime_seconds=time.time() - self.start_time
            )
        except Exception:
            # Возвращаем значения по умолчанию при ошибке
            return SystemMetrics(
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_mb=0.0,
                disk_percent=0.0,
                disk_free_gb=0.0,
                active_processes=0,
                uptime_seconds=time.time() - self.start_time
            )

    def clear_cache(self) -> None:
        """Очистка кэша проверки здоровья."""
        self.health_cache.clear()

    def get_cached_status(self, component: str) -> Optional[HealthStatus]:
        """Получение закэшированного статуса компонента."""
        return self.health_cache.get(component)

    async def run_background_monitoring(self, interval_seconds: int = 300) -> None:
        """
        Фоновый мониторинг здоровья системы.

        Args:
            interval_seconds: Интервал проверки в секундах
        """
        while True:
            try:
                await self.check_all_components()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Health monitoring error: {e}")
                await asyncio.sleep(interval_seconds)