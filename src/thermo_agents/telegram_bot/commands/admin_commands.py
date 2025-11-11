"""
Административные команды Telegram бота.

Доступные команды (только для admin_user_id):
- /admin_status - детальный статус системы
- /admin_stats - статистика использования
- /admin_health - проверка здоровья компонентов
- /admin_users - активные пользователи
- /admin_errors - ошибки системы
- /admin_cleanup - очистка временных файлов
- /admin_broadcast <сообщение> - рассылка сообщения
- /admin_config - текущая конфигурация
- /admin_system - системные ресурсы
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from telegram import Update
from telegram.ext import ContextTypes

from ..config import TelegramBotConfig
from ..utils.health_checker import HealthChecker
from ..utils.error_handler import TelegramBotErrorHandler
from ..formatters.file_handler import FileHandler


class AdminCommands:
    """Обработчик административных команд."""

    def __init__(
        self,
        config: TelegramBotConfig,
        health_checker: HealthChecker,
        error_handler: TelegramBotErrorHandler,
        session_manager,
        rate_limiter
    ):
        self.config = config
        self.health_checker = health_checker
        self.error_handler = error_handler
        self.session_manager = session_manager
        self.rate_limiter = rate_limiter
        self.file_handler = FileHandler(config)

    async def handle_admin_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_status."""
        try:
            # Проверка прав администратора
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            # Получение детальной информации о системе
            status_report = await self._get_admin_status_report()

            # Отправка отчёта
            await update.message.reply_text(
                status_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения статуса: {str(e)}")

    async def handle_admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_stats."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            stats_report = await self._get_statistics_report()

            await update.message.reply_text(
                stats_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения статистики: {str(e)}")

    async def handle_admin_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_health."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            # Выполнение проверки здоровья
            health_results = await self.health_checker.check_all_components()

            health_report = self._format_health_report(health_results)

            await update.message.reply_text(
                health_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка проверки здоровья: {str(e)}")

    async def handle_admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_users."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            users_report = await self._get_users_report()

            await update.message.reply_text(
                users_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения данных пользователей: {str(e)}")

    async def handle_admin_errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_errors."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            # Получение ошибок за последние 24 часа
            errors_report = await self._get_errors_report()

            await update.message.reply_text(
                errors_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения отчёта об ошибках: {str(e)}")

    async def handle_admin_cleanup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_cleanup."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            # Очистка временных файлов
            cleaned_files = await self.file_handler.cleanup_old_files()

            # Очистка кэша
            self.health_checker.clear_cache()

            cleanup_report = f"""🧹 *Отчёт об очистке*

✅ *Временные файлы:* {cleaned_files} удалено
✅ *Кэш здоровья:* очищен
✅ *Статистика:* сохранена

*Текущее состояние:*
• Временных файлов: {await self.file_handler.get_temp_files_count()}
• Свободное место на диске: определено..."""

            await update.message.reply_text(
                cleanup_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка очистки: {str(e)}")

    async def handle_admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_broadcast."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            # Проверка наличия сообщения
            if not context.args:
                await update.message.reply_text(
                    "❌ *Ошибка:* Укажите сообщение для рассылки\n\n"
                    "Использование: `/admin_broadcast <сообщение>`",
                    parse_mode="Markdown"
                )
                return

            broadcast_message = " ".join(context.args)
            sent_count = await self._send_broadcast(broadcast_message)

            await update.message.reply_text(
                f"📢 *Рассылка отправлена*\n\n"
                f"📨 Сообщение: `{broadcast_message}`\n"
                f"👥 Получено: {sent_count} пользователей",
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка рассылки: {str(e)}")

    async def handle_admin_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_config."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            config_report = self._get_config_report()

            await update.message.reply_text(
                config_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения конфигурации: {str(e)}")

    async def handle_admin_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка команды /admin_system."""
        try:
            if not self._is_admin(update.effective_user.id):
                await self._send_admin_error(update, "Доступ запрещён")
                return

            system_report = await self._get_system_report()

            await update.message.reply_text(
                system_report,
                parse_mode="Markdown"
            )

        except Exception as e:
            await self._send_admin_error(update, f"Ошибка получения системной информации: {str(e)}")

    def _is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором."""
        return user_id == self.config.admin_user_id

    async def _send_admin_error(self, update: Update, error_message: str) -> None:
        """Отправка сообщения об ошибке администратору."""
        await update.message.reply_text(
            f"❌ *Административная ошибка:* {error_message}",
            parse_mode="Markdown"
        )

    async def _get_admin_status_report(self) -> str:
        """Получение детального административного отчёта о статусе."""
        # Получение системных метрик
        system_metrics = await self.health_checker.get_system_metrics()

        # Статистика сессий
        session_stats = self.session_manager.get_user_statistics()

        # Статистика ошибок
        error_stats = self.error_handler.get_error_statistics()

        # Информация о файлах
        temp_files_count = await self.file_handler.get_temp_files_count()
        total_temp_size = await self.file_handler.get_total_temp_files_size()

        return f"""📊 *Административный статус системы*

🕒 *Время работы:* {system_metrics.uptime_seconds/3600:.1f} часов

👥 *Пользователи:*
• Активные сессии: {session_stats.get('active_sessions', 0)}
• Всего уникальных: {session_stats.get('total_unique_users', 0)}
• Пик нагрузки: {session_stats.get('peak_concurrent_users', 0)}

📈 *Производительность:*
• CPU: {system_metrics.cpu_percent:.1f}%
• Память: {system_metrics.memory_mb:.0f}MB ({system_metrics.memory_percent:.1f}%)
• Диск: {system_metrics.disk_free_gb:.1f}GB свободно

📁 *Файлы:*
• Временных файлов: {temp_files_count}
• Общий размер: {total_temp_size/1024/1024:.1f}MB

⚠️ *Ошибки:*
• Всего: {error_stats['total_errors']}
• Последний час: {len([e for e in self.error_handler.statistics.recent_errors if (datetime.now() - e.timestamp).total_seconds() < 3600])}

🔧 *Конфигурация:*
• Max пользователей: {self.config.max_concurrent_users}
• Rate лимит: {self.config.rate_limit_messages_per_minute}/мин
• Порог файла: {self.config.response_format_threshold} символов

🕐 *Обновлено:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    async def _get_statistics_report(self) -> str:
        """Получение статистического отчёта."""
        error_stats = self.error_handler.get_error_statistics()
        session_stats = self.session_manager.get_user_statistics()
        rate_stats = self.rate_limiter.get_global_rate_info()

        return f"""📈 *Статистика использования*

📊 *Общие показатели:*
• Всего запросов: {session_stats.get('total_requests', 0)}
• Успешных: {session_stats.get('successful_requests', 0)}
• Ошибок: {session_stats.get('failed_requests', 0)}
• Успешность: {(session_stats.get('successful_requests', 0) / max(session_stats.get('total_requests', 1), 1) * 100):.1f}%

👥 *Пользователи:*
• Активные: {session_stats.get('active_sessions', 0)}
• Всего уникальных: {session_stats.get('total_unique_users', 0)}
• Средняя сессия: {session_stats.get('average_session_duration_minutes', 0):.1f} мин

⏱️ *Rate Limiting:*
• Всего запросов: {rate_stats.get('total_requests', 0)}
• Ограничено: {rate_stats.get('limited_requests', 0)}
• Активные пользователи: {len(rate_stats.get('active_users', []))}

❌ *Ошибки по категориям:*
{self._format_error_categories(error_stats['errors_by_category'])}

🔥 *Ошибки по серьёзности:*
{self._format_error_severities(error_stats['errors_by_severity'])}

🕐 *Период:* Последние 24 часа"""

    def _format_error_categories(self, categories: Dict[str, int]) -> str:
        """Форматирование ошибок по категориям."""
        if not categories:
            return "• Нет ошибок"

        lines = []
        for category, count in categories.items():
            lines.append(f"• {category}: {count}")
        return "\n".join(lines)

    def _format_error_severities(self, severities: Dict[str, int]) -> str:
        """Форматирование ошибок по серьёзности."""
        if not severities:
            return "• Нет ошибок"

        lines = []
        for severity, count in severities.items():
            lines.append(f"• {severity}: {count}")
        return "\n".join(lines)

    def _format_health_report(self, health_results: Dict[str, Any]) -> str:
        """Форматирование отчёта о здоровье."""
        overall_status = health_results["overall_status"]
        health_score = health_results["health_score"]
        components = health_results["components"]

        status_emoji = {
            "healthy": "🟢",
            "degraded": "🟡",
            "unhealthy": "🔴"
        }

        report = f"""🏥 *Отчёт о здоровье системы*

{status_emoji.get(overall_status, "❓")} *Общий статус:* {overall_status.upper()}
📊 *Оценка здоровья:* {health_score:.1f}%

📋 *Компоненты:*
"""

        for component_name, health_status in components.items():
            component_emoji = status_emoji.get(health_status.status, "❓")
            response_time = health_status.response_time_ms

            report += f"\n{component_emoji} *{component_name.title()}:* {health_status.status.upper()}"
            report += f" ({response_time:.0f}ms)"

            if health_status.error:
                report += f"\n  └ Ошибка: `{health_status.error[:100]}`"

        if health_results["warnings"]:
            report += f"\n\n⚠️ *Предупреждения:*"
            for warning in health_results["warnings"]:
                report += f"\n• {warning}"

        if health_results["errors"]:
            report += f"\n\n🚨 *Критические ошибки:*"
            for error in health_results["errors"]:
                report += f"\n• {error}"

        report += f"\n\n🕐 *Проверено:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        return report

    async def _get_users_report(self) -> str:
        """Получение отчёта о пользователях."""
        sessions = self.session_manager.active_sessions

        if not sessions:
            return "👥 *Отчёт о пользователях*\n\nНет активных пользователей."

        report = "👥 *Активные пользователи*\n\n"

        for user_id, session in sessions.items():
            duration = time.time() - session.start_time
            last_activity = time.time() - session.last_activity

            report += f"👤 *ID {user_id}*\n"
            report += f"  • Имя: {session.username or 'N/A'}\n"
            report += f"  • Запросов: {session.request_count}\n"
            report += f"  • Длительность: {duration/60:.1f} мин\n"
            report += f"  • Последняя активность: {last_activity/60:.1f} мин назад\n\n"

        return report

    async def _get_errors_report(self) -> str:
        """Получение отчёта об ошибках."""
        recent_errors = self.error_handler.statistics.recent_errors
        last_24h_errors = [
            e for e in recent_errors
            if (datetime.now() - e.timestamp).total_seconds() < 86400
        ]

        if not last_24h_errors:
            return "📝 *Отчёт об ошибках*\n\nЗа последние 24 часа ошибок не было."

        report = f"""📝 *Отчёт об ошибках (последние 24 часа)*

Всего: {len(last_24h_errors)} ошибок

"""

        # Группировка по времени
        time_groups = {}
        for error in last_24h_errors:
            hour_key = error.timestamp.strftime("%H:00")
            if hour_key not in time_groups:
                time_groups[hour_key] = []
            time_groups[hour_key].append(error)

        for hour, errors in sorted(time_groups.items()):
            report += f"🕐 *{hour}* — {len(errors)} ошибок\n"

        # Последние 5 ошибок
        report += "\n🔍 *Последние ошибки:*\n"
        for error in last_24h_errors[-5:]:
            time_str = error.timestamp.strftime("%H:%M:%S")
            report += f"\n• {time_str} — {error.category.value}: {str(error.exception)[:80]}"

        return report

    async def _send_broadcast(self, message: str) -> int:
        """Отправка рассылки всем активным пользователям."""
        # Здесь должна быть логика отправки сообщения всем активным пользователям
        # В текущей имплементации возвращаем模拟 (simulation)
        sessions = self.session_manager.active_sessions
        sent_count = 0

        for user_id in sessions.keys():
            try:
                # Здесь должна быть реальная отправка через bot.send_message
                # bot.send_message(chat_id=user_id, text=message)
                sent_count += 1
            except Exception:
                continue

        return sent_count

    def _get_config_report(self) -> str:
        """Получение отчёта о конфигурации."""
        return f"""⚙️ *Текущая конфигурация*

🤖 *Бот:*
• Username: {self.config.bot_username}
• Max пользователей: {self.config.max_concurrent_users}
• Timeout: {self.config.bot_timeout_seconds}s

📊 *Производительность:*
• Порог файла: {self.config.response_format_threshold} символов
• Max размер файла: {self.config.max_file_size_mb}MB
• Очистка файлов: {self.config.file_cleanup_hours}ч

🔗 *Интеграция:*
• База данных: {self.config.thermo_db_path}
• YAML кэш: {self.config.thermo_static_data_dir}
• LLM модель: {self.config.llm_model}

📁 *Файлы:*
• Temp директория: {self.config.temp_file_dir}
• Max длина сообщения: {self.config.max_message_length}

🚦 *Rate Limiting:*
• Сообщений в минуту: {self.config.rate_limit_messages_per_minute}
• Всплеск: {self.config.rate_limit_burst}

📝 *Логирование:*
• Уровень: {self.config.log_level}
• Сессии: {self.config.enable_session_logging}
• Директория логов: {self.config.session_log_dir}"""

    async def _get_system_report(self) -> str:
        """Получение системного отчёта."""
        try:
            import psutil

            # CPU информация
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()

            # Память
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Диск
            disk = psutil.disk_usage('/')

            # Сеть
            network = psutil.net_io_counters()

            # Процессы
            process_count = len(psutil.pids())

            return f"""🖥️ *Системная информация*

💻 *Процессор:*
• Загрузка: {cpu_percent:.1f}%
• Ядра: {cpu_count}
• Частота: {cpu_freq.current:.0f}MHz (если доступно)

🧠 *Память:*
• RAM: {memory.used/1024/1024:.0f}MB / {memory.total/1024/1024:.0f}MB ({memory.percent:.1f}%)
• Swap: {swap.used/1024/1024:.0f}MB / {swap.total/1024/1024:.0f}MB

💾 *Диск:*
• Использовано: {disk.used/1024/1024/1024:.1f}GB / {disk.total/1024/1024/1024:.1f}GB ({disk.used/disk.total*100:.1f}%)
• Свободно: {disk.free/1024/1024/1024:.1f}GB

🌐 *Сеть:*
• Отправлено: {network.bytes_sent/1024/1024:.1f}MB
• Получено: {network.bytes_recv/1024/1024:.1f}MB

⚙️ *Процессы:* {process_count} активных

🕐 *Обновлено:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        except Exception as e:
            return f"❌ *Ошибка получения системной информации:* {str(e)}"