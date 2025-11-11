"""
Адаптер для интеграции Telegram бота с ThermoOrchestrator.

Основные классы:
- ThermoAdapter: Основной адаптер для работы с ThermoSystem
- ResponseFormatter: Форматирование ответов для Telegram
- FileGenerator: Генерация TXT файлов для больших отчетов
"""

import asyncio
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Union

from ..orchestrator import ThermoOrchestrator, ThermoOrchestratorConfig
from ..session_logger import SessionLogger
from .config import TelegramBotConfig
from .models import BotResponse, CommandStatus, FileResponse, MessageType

logger = logging.getLogger(__name__)


class ThermoAdapter:
    """Адаптер для интеграции с ThermoOrchestrator."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.orchestrator: Optional[ThermoOrchestrator] = None
        self.response_formatter = ResponseFormatter()
        self.file_generator = FileGenerator(config.file_config)

    async def initialize(self):
        """Инициализация адаптера."""
        try:
            # Создание конфигурации ThermoOrchestrator
            thermo_config = ThermoOrchestratorConfig(
                llm_api_key=self.config.openrouter_api_key,
                llm_base_url=self.config.llm_base_url,
                llm_model=self.config.llm_model,
                db_path=self.config.thermo_db_path,
                max_retries=2,
                timeout_seconds=self.config.limits.request_timeout_seconds,
            )

            # Создание оркестратора
            self.orchestrator = ThermoOrchestrator(thermo_config)
            logger.info("ThermoOrchestrator успешно инициализирован")

        except Exception as e:
            logger.error(f"Ошибка инициализации ThermoOrchestrator: {e}")
            raise

    async def process_query(
        self, query: str, user_id: int
    ) -> Tuple[Union[BotResponse, FileResponse], bool]:
        """
        Обработать запрос через ThermoOrchestrator.

        Args:
            query: Запрос пользователя
            user_id: ID пользователя

        Returns:
            Кортеж (ответ, needs_file)
        """
        if not self.orchestrator:
            raise RuntimeError("ThermoAdapter не инициализирован")

        try:
            # Создаем логгер сессии для трассировки
            with SessionLogger() as session_logger:
                session_logger.info(f"Processing query from user {user_id}: {query}")

                # Выполняем запрос через ThermoOrchestrator
                raw_response = await self.orchestrator.process_query(query)
                session_logger.info("Query processed successfully")

                # Определяем, нужно ли отправлять как файл
                needs_file = self.file_generator.should_use_file(raw_response)

                if needs_file:
                    # Генерируем файл
                    file_response = await self.file_generator.generate_file_response(
                        query, raw_response, user_id
                    )
                    session_logger.info("File response generated")
                    return file_response, True
                else:
                    # Форматируем текстовый ответ
                    bot_response = await self.response_formatter.format_response(
                        query, raw_response, user_id
                    )
                    session_logger.info("Text response formatted")
                    return bot_response, False

        except asyncio.TimeoutError:
            logger.error(f"Timeout processing query for user {user_id}: {query}")
            return BotResponse(
                text="⏰ *Таймаут запроса*\n\nЗапрос слишком сложный. Попробуйте упростить его или уменьшить температурный диапазон.",
                message_type=MessageType.ERROR,
                status=CommandStatus.TIMEOUT,
                user_id=user_id,
                original_query=query,
            ), False

        except Exception as e:
            logger.error(f"Error processing query for user {user_id}: {e}")
            return BotResponse(
                text="❌ *Ошибка обработки запроса*\n\n"
                f"Произошла ошибка при обработке вашего запроса. "
                f"Попробуйте переформулировать вопрос или обратитесь к /help.",
                message_type=MessageType.ERROR,
                status=CommandStatus.ERROR,
                user_id=user_id,
                original_query=query,
            ), False

    async def get_system_status(self) -> dict:
        """Получить статус системы ThermoOrchestrator."""
        if not self.orchestrator:
            return {"status": "Не инициализирован"}

        try:
            # Базовая проверка работоспособности
            test_query = "H2O"
            await asyncio.wait_for(
                self.orchestrator.process_query(test_query), timeout=10.0
            )
            return {"status": "Работает", "last_check": datetime.now().isoformat()}
        except Exception as e:
            return {
                "status": f"Ошибка: {str(e)}",
                "last_check": datetime.now().isoformat(),
            }

    async def shutdown(self):
        """Завершение работы адаптера."""
        logger.info("ThermoAdapter shutting down")


class ResponseFormatter:
    """Форматирование ответов для Telegram."""

    def __init__(self):
        self.max_message_length = 4000  # Telegram limit

    async def format_response(
        self, query: str, raw_response: str, user_id: int
    ) -> BotResponse:
        """Отформатировать ответ для Telegram."""
        # Обрезаем слишком длинные ответы
        if len(raw_response) > self.max_message_length:
            raw_response = self._truncate_response(raw_response)

        # Форматируем с эмодзи и Markdown
        formatted_response = self._apply_telegram_formatting(raw_response, query)

        return BotResponse(
            text=formatted_response,
            message_type=MessageType.TEXT_QUERY,
            status=CommandStatus.SUCCESS,
            user_id=user_id,
            original_query=query,
            use_markdown=False,  # Отключаем Markdown для избежания ошибок парсинга
            parse_mode=None,
        )

    def _truncate_response(self, response: str) -> str:
        """Обрезать ответ с сохранением важной информации."""
        if len(response) <= self.max_message_length:
            return response

        # Ищем таблицы и сохраняем начало и конец
        lines = response.split("\n")
        truncated_lines = []
        current_length = 0

        for line in lines:
            if (
                current_length + len(line) + 1 > self.max_message_length - 200
            ):  # Оставляем место для завершения
                break
            truncated_lines.append(line)
            current_length += len(line) + 1

        truncated_lines.append("\n\n...")
        truncated_lines.append("📄 *Полный отчет доступен в файле*")

        return "\n".join(truncated_lines)

    def _apply_telegram_formatting(self, response: str, query: str) -> str:
        """Применить форматирование для Telegram."""
        # Добавляем заголовок
        lines = response.split("\n")

        # Ищем тип контента для эмодзи
        if any(keyword in query.lower() for keyword in ["реакц", "→", "react"]):
            emoji = "🔥"
            title = "ТЕРМОДИНАМИЧЕСКИЙ РАСЧЁТ РЕАКЦИИ"
        elif any(
            keyword in query.lower() for keyword in ["таблиц", "свойств", "данные"]
        ):
            emoji = "📊"
            title = "СВОЙСТВА ВЕЩЕСТВА"
        else:
            emoji = "⚗️"
            title = "ТЕРМОДИНАМИЧЕСКИЙ АНАЛИЗ"

        # Формируем заголовок
        header = f"{emoji} *{title}*\n\n"

        # Добавляем Unicode обработку для химических формул
        formatted_lines = []
        for line in lines:
            # Заменяем простые формулы на Unicode
            line = self._enhance_chemical_formulas(line)
            formatted_lines.append(line)

        formatted_response = header + "\n".join(formatted_lines)

        # Добавляем футер
        footer = f"\n\n_Сгенерировано ThermoSystem Telegram Bot_"
        formatted_response += footer

        return formatted_response

    def _enhance_chemical_formulas(self, text: str) -> str:
        """Улучшить химические формулы с Unicode."""
        # Простые замены для распространенных формул
        replacements = {
            "H2O": "H₂O",
            "CO2": "CO₂",
            "H2": "H₂",
            "O2": "O₂",
            "N2": "N₂",
            "CH4": "CH₄",
            "NH3": "NH₃",
            "CO": "CO",
            "SO2": "SO₂",
            "NO2": "NO₂",
            "HCl": "HCl",
            "NaCl": "NaCl",
            "Fe2O3": "Fe₂O₃",
            "CaCO3": "CaCO₃",
            "MgO": "MgO",
            "Al2O3": "Al₂O₃",
            "SiO2": "SiO₂",
            "KCl": "KCl",
            "->": "→",
            "<-": "←",
            "<->": "↔",
            "=>": "⇒",
            "<=": "⇐",
        }

        result = text
        for old, new in replacements.items():
            # Заменяем только полные вхождения формул
            import re

            pattern = r"\b" + re.escape(old) + r"\b"
            result = re.sub(pattern, new, result)

        return result


class FileGenerator:
    """Генерация TXT файлов для больших отчетов."""

    def __init__(self, file_config):
        self.file_config = file_config

    def should_use_file(self, response: str) -> bool:
        """Определить, нужно ли использовать файл."""
        # Критерии для отправки файла
        return (
            len(response) >= self.file_config.auto_file_threshold
            or response.count("\n") >= 100  # Много строк
            or "| T (K)" in response
            and response.count("|") >= 50  # Большая таблица
        )

    async def generate_file_response(
        self, query: str, raw_response: str, user_id: int
    ) -> FileResponse:
        """Сгенерировать файловый ответ."""
        try:
            # Создаем временную директорию
            temp_dir = Path(self.file_config.temp_file_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Генерируем имя файла
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"thermo_calculation_{user_id}_{timestamp}.txt"
            file_path = temp_dir / filename

            # Создаем профессиональный отчет
            file_content = self._create_professional_report(query, raw_response)

            # Записываем файл
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(file_content)

            # Создаем подпись
            caption = self._create_file_caption(query, len(file_content))

            return FileResponse(
                file_path=file_path,
                caption=caption,
                user_id=user_id,
                original_query=query,
            )

        except Exception as e:
            logger.error(f"Error generating file: {e}")
            # В случае ошибки, возвращаем текстовый ответ
            raise RuntimeError(f"Не удалось создать файл: {str(e)}")

    def _create_professional_report(self, query: str, raw_response: str) -> str:
        """Создать профессиональный отчет в TXT формате."""
        # Заголовок отчета
        header = "=" * 80 + "\n"
        header += "                ТЕРМОДИНАМИЧЕСКИЙ РАСЧЁТ\n"
        header += "=" * 80 + "\n\n"

        # Информация о запросе
        query_info = f"ЗАПРОС: {query}\n"
        query_info += (
            f"ДАТА ВЫПОЛНЕНИЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

        # Разделитель
        separator = "=" * 80 + "\n"
        separator += "                        РЕЗУЛЬТАТЫ РАСЧЁТА\n"
        separator += "=" * 80 + "\n\n"

        # Основной контент
        content = raw_response

        # Футер
        footer = "\n" + "=" * 80 + "\n"
        footer += "Сгенерировано ThermoSystem Telegram Bot\n"
        footer += f"URL: https://github.com/your-repo/thermo-system\n"
        footer += f"Время генерации: {datetime.now().isoformat()}\n"
        footer += "=" * 80

        return header + query_info + separator + content + footer

    def _create_file_caption(self, query: str, content_length: int) -> str:
        """Создать подпись к файлу."""
        # Определяем тип запроса
        if any(keyword in query.lower() for keyword in ["реакц", "→", "react"]):
            file_type = "Расчёт реакции"
        elif any(keyword in query.lower() for keyword in ["таблиц", "свойств"]):
            file_type = "Свойства вещества"
        else:
            file_type = "Термодинамический анализ"

        # Формируем подпись
        caption = f"📄 *{file_type}*\n\n"
        caption += f"Размер файла: {content_length:,} символов\n"
        caption += f"Создан: {datetime.now().strftime('%H:%M:%S')}\n\n"
        caption += "_Отчет содержит детальные результаты расчёта_"

        return caption

    async def cleanup_old_files(self):
        """Очистка старых временных файлов."""
        try:
            temp_dir = Path(self.file_config.temp_file_dir)
            if not temp_dir.exists():
                return

            current_time = datetime.now()
            cutoff_time = current_time - timedelta(
                hours=self.file_config.file_cleanup_hours
            )

            for file_path in temp_dir.glob("thermo_calculation_*.txt"):
                if file_path.stat().st_mtime < cutoff_time.timestamp():
                    file_path.unlink()
                    logger.info(f"Удален старый файл: {file_path}")

        except Exception as e:
            logger.error(f"Ошибка очистки старых файлов: {e}")
