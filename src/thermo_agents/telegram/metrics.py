"""
File System Metrics - Сбор метрик файловой системы

Отслеживает статистику использования файлов, доставку ответов и производительность.
"""

import time
import logging
from typing import Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class FileSystemMetrics:
    """Сбор метрик файловой системы"""

    def __init__(self, file_handler):
        self.file_handler = file_handler
        self.metrics = {
            'files_created': 0,
            'files_sent': 0,
            'total_size_mb': 0.0,
            'errors': 0,
            'cleanup_runs': 0,
            'message_responses': 0,
            'file_responses': 0,
            'total_response_time_ms': 0.0,
            'start_time': time.time()
        }

    def record_file_creation(self, size_mb: float):
        """Запись создания файла"""
        self.metrics['files_created'] += 1
        self.metrics['total_size_mb'] += size_mb

    def record_file_sent(self, size_mb: float):
        """Запись отправки файла"""
        self.metrics['files_sent'] += 1
        self.metrics['file_responses'] += 1

    def record_message_sent(self):
        """Запись отправки сообщения"""
        self.metrics['message_responses'] += 1

    def record_response_time(self, response_time_ms: float):
        """Запись времени ответа"""
        self.metrics['total_response_time_ms'] += response_time_ms

    def record_error(self):
        """Запись ошибки"""
        self.metrics['errors'] += 1

    def record_cleanup(self, files_deleted: int):
        """Запись очистки"""
        self.metrics['cleanup_runs'] += 1
        logger.info(f"Cleanup completed: {files_deleted} files deleted")

    def get_metrics(self) -> dict:
        """Получение всех метрик"""
        current_stats = self.file_handler.get_file_stats()
        uptime_seconds = time.time() - self.metrics['start_time']
        total_responses = self.metrics['message_responses'] + self.metrics['file_responses']

        return {
            **self.metrics,
            'current_stats': current_stats,
            'uptime_seconds': uptime_seconds,
            'total_responses': total_responses,
            'average_file_size_mb': (
                self.metrics['total_size_mb'] / max(1, self.metrics['files_created'])
            ),
            'success_rate': (
                (total_responses / max(1, total_responses + self.metrics['errors'])) * 100
            ),
            'average_response_time_ms': (
                self.metrics['total_response_time_ms'] / max(1, total_responses)
            ),
            'file_usage_rate': (
                (self.metrics['file_responses'] / max(1, total_responses)) * 100
            ),
            'files_per_hour': (
                self.metrics['files_created'] / max(1, uptime_seconds / 3600)
            )
        }

    def reset_metrics(self):
        """Сброс метрик"""
        for key in self.metrics:
            if key != 'start_time':
                self.metrics[key] = 0
        self.metrics['start_time'] = time.time()
        logger.info("Metrics reset")

    def get_performance_summary(self) -> str:
        """Получение текстового summary производительности"""
        metrics = self.get_metrics()
        uptime_hours = metrics['uptime_seconds'] / 3600

        summary = f"""
📊 **Производительность файловой системы**

🕒 **Uptime:** {uptime_hours:.1f} часов
📁 **Файлов создано:** {metrics['files_created']}
📤 **Файлов отправлено:** {metrics['files_sent']}
💬 **Ответов сообщениями:** {metrics['message_responses']}
📄 **Ответов файлами:** {metrics['file_responses']}

📈 **Метрики:**
•成功率: {metrics['success_rate']:.1f}%
•Средний размер файла: {metrics['average_file_size_mb']:.2f} MB
•Среднее время ответа: {metrics['average_response_time_ms']:.0f} ms
•Использование файлов: {metrics['file_usage_rate']:.1f}%
•Файлов в час: {metrics['files_per_hour']:.1f}

🗂️ **Текущее состояние:**
•Активных файлов: {metrics['current_stats']['total_files']}
•Общий размер: {metrics['current_stats']['total_size_mb']:.2f} MB
•Активных сессий: {metrics['current_stats']['active_sessions']}
        """.strip()

        return summary

class MetricsCollector:
    """Коллектор метрик для всего бота"""

    def __init__(self):
        self.metrics = {
            'start_time': time.time(),
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'thermo_queries': 0,
            'command_queries': 0,
            'response_times': [],
            'error_types': {},
            'user_activity': {}
        }

    def record_request(self, request_type: str = 'unknown'):
        """Запись запроса"""
        self.metrics['total_requests'] += 1

        if request_type == 'thermo':
            self.metrics['thermo_queries'] += 1
        elif request_type == 'command':
            self.metrics['command_queries'] += 1

    def record_success(self, response_time_ms: float):
        """Запись успешного запроса"""
        self.metrics['successful_requests'] += 1
        self.metrics['response_times'].append(response_time_ms)

    def record_failure(self, error_type: str = 'unknown'):
        """Запись неудачного запроса"""
        self.metrics['failed_requests'] += 1

        if error_type not in self.metrics['error_types']:
            self.metrics['error_types'][error_type] = 0
        self.metrics['error_types'][error_type] += 1

    def record_user_activity(self, user_id: int, activity: str):
        """Запись активности пользователя"""
        if user_id not in self.metrics['user_activity']:
            self.metrics['user_activity'][user_id] = {
                'requests': 0,
                'last_activity': time.time(),
                'activities': []
            }

        self.metrics['user_activity'][user_id]['requests'] += 1
        self.metrics['user_activity'][user_id]['last_activity'] = time.time()
        self.metrics['user_activity'][user_id]['activities'].append({
            'activity': activity,
            'timestamp': time.time()
        })

    def get_summary(self) -> dict:
        """Получение summary метрик"""
        uptime_seconds = time.time() - self.metrics['start_time']
        total_requests = self.metrics['total_requests']
        success_rate = (self.metrics['successful_requests'] / max(1, total_requests)) * 100

        # Расчет среднего времени ответа
        avg_response_time = 0
        if self.metrics['response_times']:
            avg_response_time = sum(self.metrics['response_times']) / len(self.metrics['response_times'])

        # Расчет запросов в час
        requests_per_hour = total_requests / max(1, uptime_seconds / 3600)

        # Активные пользователи (за последний час)
        active_users = 0
        one_hour_ago = time.time() - 3600
        for user_id, activity in self.metrics['user_activity'].items():
            if activity['last_activity'] > one_hour_ago:
                active_users += 1

        return {
            'uptime_seconds': uptime_seconds,
            'total_requests': total_requests,
            'successful_requests': self.metrics['successful_requests'],
            'failed_requests': self.metrics['failed_requests'],
            'success_rate': success_rate,
            'avg_response_time_ms': avg_response_time,
            'requests_per_hour': requests_per_hour,
            'thermo_queries': self.metrics['thermo_queries'],
            'command_queries': self.metrics['command_queries'],
            'active_users_1h': active_users,
            'total_unique_users': len(self.metrics['user_activity']),
            'error_types': self.metrics['error_types'],
            'most_common_error': max(self.metrics['error_types'].items(),
                                    key=lambda x: x[1])[0] if self.metrics['error_types'] else None
        }

    def get_health_status(self) -> dict:
        """Получение статуса здоровья системы"""
        summary = self.get_summary()

        # Определение статуса здоровья
        health_status = "healthy"
        issues = []

        if summary['success_rate'] < 90:
            health_status = "degraded"
            issues.append(f"Low success rate: {summary['success_rate']:.1f}%")

        if summary['avg_response_time_ms'] > 10000:  # 10 секунд
            health_status = "degraded"
            issues.append(f"High response time: {summary['avg_response_time_ms']:.0f}ms")

        if summary['success_rate'] < 70:
            health_status = "unhealthy"
            issues.append(f"Very low success rate: {summary['success_rate']:.1f}%")

        if summary['failed_requests'] > 10 and summary['total_requests'] < 20:
            health_status = "unhealthy"
            issues.append("High failure rate with low total requests")

        return {
            'status': health_status,
            'issues': issues,
            'uptime_seconds': summary['uptime_seconds'],
            'last_check': time.time()
        }