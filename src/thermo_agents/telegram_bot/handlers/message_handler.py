"""
Обработчик текстовых сообщений для Telegram бота.

Интеграция с ThermoOrchestrator для обработки термодинамических запросов.
"""

import time
import asyncio
from typing import Optional, Tuple

from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..config import TelegramBotConfig, BotStatus
from ..formatters.response_formatter import ResponseFormatter
from ..formatters.file_handler import FileHandler
from ..utils.thermo_integration import ThermoIntegration


class MessageHandler:
    """Обработчик текстовых сообщений Telegram бота."""

    def __init__(
        self,
        config: TelegramBotConfig,
        status: BotStatus,
        thermo_integration: ThermoIntegration
    ):
        self.config = config
        self.status = status
        self.thermo_integration = thermo_integration
        self.response_formatter = ResponseFormatter(config)
        self.file_handler = FileHandler(config)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработка текстового сообщения."""
        if not update.message or not update.message.text:
            return

        message = update.message
        user_id = update.effective_user.id
        query_text = message.text.strip()

        # Обновление статистики
        self.status.total_requests += 1
        self.status.active_users += 1

        start_time = time.time()

        try:
            # Отправка индикатора обработки
            processing_message = await message.reply_text(
                "🔄 *Обрабатываю запрос...*",
                parse_mode="Markdown"
            )

            # Обработка запроса через ThermoSystem
            response_data = await self._process_thermo_query(query_text, user_id)

            # Удаление индикатора обработки
            await processing_message.delete()

            # Отправка результата
            if response_data["success"]:
                await self._send_successful_response(message, response_data)
                self.status.successful_requests += 1
            else:
                await self._send_error_response(message, response_data["error"])
                self.status.failed_requests += 1

        except Exception as e:
            # Удаление индикатора обработки если существует
            try:
                await processing_message.delete()
            except:
                pass

            error_msg = f"Внутренняя ошибка: {str(e)}"
            await self._send_error_response(message, error_msg)
            self.status.failed_requests += 1

        finally:
            # Обновление статистики
            self.status.active_users -= 1
            response_time = (time.time() - start_time) * 1000
            self.status.average_response_time_ms = (
                (self.status.average_response_time_ms * (self.status.total_requests - 1) + response_time) /
                self.status.total_requests
            )

    async def _process_thermo_query(self, query: str, user_id: int) -> dict:
        """Обработка термодинамического запроса."""
        try:
            # Вызов ThermoOrchestrator через интеграцию
            result = await self.thermo_integration.process_query(query, user_id)

            return {
                "success": True,
                "content": result.content,
                "query_type": result.query_type,
                "compounds": result.compounds,
                "processing_time_ms": result.processing_time_ms,
                "has_large_tables": result.has_large_tables,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _send_successful_response(self, message: Message, response_data: dict) -> None:
        """Отправка успешного ответа."""
        content = response_data["content"]
        query_type = response_data["query_type"]
        compounds = response_data["compounds"]

        # Определение способа отправки
        should_send_file = self.file_handler.should_send_as_file(
            content,
            response_data.get("has_large_tables", False)
        )

        if should_send_file:
            await self._send_file_response(message, content, query_type, compounds)
        else:
            await self._send_text_response(message, content, query_type)

    async def _send_text_response(self, message: Message, content: str, query_type: str) -> None:
        """Отправка текстового ответа."""
        try:
            # Форматирование контента
            formatted_messages = self.response_formatter.format_thermo_response(content, query_type)

            # Отправка сообщений
            for i, msg_text in enumerate(formatted_messages):
                if i > 0:
                    # Небольшая задержка между сообщениями
                    await asyncio.sleep(0.5)

                await message.reply_text(
                    msg_text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )

        except Exception as e:
            # Fallback если форматирование не удалось
            fallback_text = f"📊 *Результаты расчёта:*\n\n{content[:3000]}..."
            if len(content) > 3000:
                fallback_text += f"\n\n_(Обрезано для Telegram. Полный результат был слишком большим)_"

            await message.reply_text(
                fallback_text,
                parse_mode="Markdown"
            )

    async def _send_file_response(
        self,
        message: Message,
        content: str,
        query_type: str,
        compounds: list[str]
    ) -> None:
        """Отправка ответа в виде файла."""
        try:
            # Создание TXT файла
            file_path, error = await self.file_handler.create_txt_file(
                content,
                query_type,
                compounds,
                title="Термодинамический отчет"
            )

            if error or not file_path:
                # Если файл не создан, отправляем как текст
                await self._send_text_response(message, content, query_type)
                return

            # Создание InputFile
            input_file = await self.file_handler.create_input_file(file_path)
            if not input_file:
                await self._send_text_response(message, content, query_type)
                return

            # Форматирование краткого сообщения
            brief_content = self._create_brief_summary(content, query_type, file_path)

            # Отправка файла с кратким описанием
            await message.reply_document(
                document=input_file,
                caption=brief_content,
                parse_mode="Markdown"
            )

        except Exception as e:
            # Fallback при ошибке отправки файла
            print(f"Ошибка отправки файла: {e}")
            await self._send_text_response(message, content, query_type)

    def _create_brief_summary(self, content: str, query_type: str, file_path) -> str:
        """Создание краткого резюме для файла."""
        # Получение информации о файле
        file_info = asyncio.run(self.file_handler.get_file_info(file_path))

        # Определение типа расчёта
        type_map = {
            "reaction": "расчёта термодинамики реакции",
            "compound_data": "термодинамических свойств вещества",
            "calculation": "термодинамического расчёта"
        }

        calc_type = type_map.get(query_type, "термодинамического расчёта")

        # Извлечение ключевой информации из контента
        lines = content.split('\n')
        equation = ""
        temp_range = ""

        for line in lines:
            if "уравнение:" in line.lower() or "реакция:" in line.lower():
                equation = line.strip()
            elif "температурный диапазон:" in line.lower() or "диапазон:" in line.lower():
                temp_range = line.strip()

        summary = f"""📄 *Детальный отчёт по {calc_type}*"""

        if equation:
            summary += f"\n\n**{equation}**"

        if temp_range:
            summary += f"\n\n🌡️ {temp_range}"

        summary += f"""
📊 *Информация о файле:*
• Размер: {file_info.get('size_kb', 0)} KB
• Создан: {file_info.get('created', 'N/A')}

📎 *Файл содержит полный термодинамический анализ с таблицами и интерпретацией результатов.*"""

        return summary

    async def _send_error_response(self, message: Message, error_text: str) -> None:
        """Отправка сообщения об ошибке."""
        error_message = self.response_formatter.format_error_message(error_text)

        await message.reply_text(
            error_message,
            parse_mode="Markdown"
        )