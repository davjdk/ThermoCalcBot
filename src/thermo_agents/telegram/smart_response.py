"""
Smart Response Handler - Умная логика отправки ответов

Интеллектуально выбирает формат ответа (сообщение или файл)
в зависимости от размера и сложности контента.
"""

import re
import asyncio
from typing import List
import logging

logger = logging.getLogger(__name__)

class SmartResponseHandler:
    """Умная отправка ответов (сообщение или файл)"""

    def __init__(
        self,
        file_handler,
        message_threshold: int = 3000
    ):
        self.file_handler = file_handler
        self.message_threshold = message_threshold

    async def send_response(
        self,
        update,
        context,
        response: str,
        reaction_info: str = ""
    ) -> bool:
        """Умная отправка ответа (сообщение или файл)"""

        try:
            should_use_file = self._should_use_file(response)

            if should_use_file:
                logger.info(f"Using file delivery for response length: {len(response)}")
                success = await self.file_handler.send_file(
                    update, context, response, reaction_info
                )
            else:
                logger.info(f"Using message delivery for response length: {len(response)}")
                success = await self._send_as_messages(update, context, response)

            return success

        except Exception as e:
            logger.error(f"Error in smart response delivery: {e}")
            await self._send_error_message(update, str(e))
            return False

    def _should_use_file(self, response: str) -> bool:
        """Определение, нужно ли использовать файл"""

        # Основной критерий - длина ответа
        if len(response) >= self.message_threshold:
            return True

        # Дополнительные критерии для сложного контента
        if self._has_large_tables(response):
            return True

        if self._has_complex_formatting(response):
            return True

        if self._has_many_reactions(response):
            return True

        return False

    def _has_large_tables(self, response: str) -> bool:
        """Проверка на наличие больших таблиц"""
        lines = response.split('\n')
        table_rows = [line for line in lines if '|' in line and line.strip().startswith('|')]
        return len(table_rows) > 20  # Более 20 строк таблицы

    def _has_complex_formatting(self, response: str) -> bool:
        """Проверка на сложное форматирование"""
        return (
            response.count('┌') > 10 or  # Unicode таблицы
            response.count('─') > 50 or  # Линии таблиц
            response.count('\t') > 20 or # Табуляция
            response.count('║') > 10     # Вертикальные линии
        )

    def _has_many_reactions(self, response: str) -> bool:
        """Проверка на наличие множественных реакций"""
        # Подсчёт химических уравнений с реакциями
        reaction_patterns = [
            r'→', r'⇌', r'↔', r'<=>',  # Стрелки реакций
            r'ΔH', r'ΔS', r'ΔG',     # Термодинамические величины
            r'K\s*='                  # Константы равновесия
        ]

        reaction_count = sum(
            len(re.findall(pattern, response))
            for pattern in reaction_patterns
        )

        return reaction_count > 10  # Много реакций в одном ответе

    async def _send_as_messages(
        self,
        update,
        context,
        response: str
    ) -> bool:
        """Отправка ответа как сообщений (с разделением при необходимости)"""

        try:
            messages = self._split_message(response)

            for i, message in enumerate(messages):
                # Добавление нумерации частей для длинных ответов
                if len(messages) > 1:
                    message = f"📄 *Часть {i+1}/{len(messages)}*\n\n{message}"

                await update.message.reply_text(
                    message,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )

                # Небольшая задержка между частями для rate limiting
                if i < len(messages) - 1:
                    await asyncio.sleep(0.5)

            return True

        except Exception as e:
            logger.error(f"Error sending message(s): {e}")
            return False

    def _split_message(self, message: str, max_length: int = 4000) -> List[str]:
        """Разделение сообщения на части с учётом форматирования"""

        if len(message) <= max_length:
            return [message]

        parts = []
        current_part = ""
        lines = message.split('\n')

        for line in lines:
            # Если добавление строки превысит лимит
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line
                else:
                    # Строка сама по себе слишком длинная
                    sub_parts = self._split_line(line, max_length)
                    parts.extend(sub_parts[:-1])
                    current_part = sub_parts[-1]
            else:
                if current_part:
                    current_part += '\n' + line
                else:
                    current_part = line

        if current_part:
            parts.append(current_part.strip())

        return parts

    def _split_line(self, line: str, max_length: int) -> List[str]:
        """Разделение слишком длинной строки"""
        parts = []
        for i in range(0, len(line), max_length - 10):
            parts.append(line[i:i + max_length - 10])
        return parts

    async def _send_error_message(self, update, error_message: str):
        """Отправка сообщения об ошибке"""
        error_text = (
            "😔 *Ошибка при отправке ответа*\n\n"
            f"```{error_message}```\n\n"
            "Попробуйте повторить запрос или используйте /help"
        )

        await update.message.reply_text(error_text, parse_mode="Markdown")

    def get_delivery_stats(self) -> dict:
        """Статистика по доставке ответов"""
        return {
            'message_threshold': self.message_threshold,
            'file_handler_stats': self.file_handler.get_file_stats()
        }