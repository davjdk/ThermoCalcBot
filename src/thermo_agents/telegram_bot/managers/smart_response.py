"""
Умная система ответов для Telegram бота.

Автоматически определяет оптимальный способ доставки ответа:
- Короткие ответы (<3000 символов) → сообщения
- Длинные ответы (≥3000 символов) → TXT файлы
- Очень большие таблицы → файлы с оптимизацией
- Сложные формулы → Unicode форматирование
"""

import asyncio
import time
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass

from telegram import Update, Message, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..config import TelegramBotConfig
from ..formatters.response_formatter import ResponseFormatter
from ..formatters.file_handler import FileHandler
from ..utils.session_manager import SessionManager


@dataclass
class ResponseMetadata:
    """Метаданные ответа для принятия решений."""
    content_length: int
    has_large_tables: bool
    has_complex_formulas: bool
    table_count: int
    line_count: int
    estimated_read_time_seconds: float
    complexity_score: float  # 0.0 - 1.0


@dataclass
class DeliveryPlan:
    """План доставки ответа."""
    method: str  # "message", "file", "split"
    format_type: str  # "standard", "compact", "detailed"
    should_compress: bool
    estimated_delivery_time_ms: float


class SmartResponseHandler:
    """Умный обработчик ответов с автоматической оптимизацией доставки."""

    def __init__(
        self,
        config: TelegramBotConfig,
        session_manager: SessionManager
    ):
        self.config = config
        self.session_manager = session_manager
        self.response_formatter = ResponseFormatter(config)
        self.file_handler = FileHandler(config)

        # Пороги для принятия решений
        self.MESSAGE_LENGTH_THRESHOLD = config.response_format_threshold
        self.LARGE_TABLE_THRESHOLD = 10  # строк в таблице
        self.COMPLEXITY_THRESHOLD = 0.7  # 0.0 - 1.0
        self.SEGMENT_THRESHOLD = config.max_message_length - 200  # запас для форматирования

    async def send_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        content: str,
        query_type: str = "calculation",
        user_query: str = ""
    ) -> Dict[str, Any]:
        """
        Основной метод отправки умного ответа.

        Args:
            update: Telegram Update объект
            context: Telegram контекст
            content: Контент ответа
            query_type: Тип запроса
            user_query: Оригинальный запрос пользователя

        Returns:
            Словарь с результатом отправки
        """
        start_time = time.time()

        try:
            # Анализ контента
            metadata = await self._analyze_content(content)

            # Определение плана доставки
            delivery_plan = self._create_delivery_plan(metadata, content)

            # Отправка согласно плану
            if delivery_plan.method == "message":
                result = await self._send_as_messages(
                    update, context, content, query_type, delivery_plan
                )
            elif delivery_plan.method == "file":
                result = await self._send_as_file(
                    update, context, content, query_type, user_query, delivery_plan
                )
            elif delivery_plan.method == "split":
                result = await self._send_split_messages(
                    update, context, content, query_type, delivery_plan
                )
            else:
                raise ValueError(f"Неизвестный метод доставки: {delivery_plan.method}")

            # Обновление статистики
            delivery_time = (time.time() - start_time) * 1000
            result["delivery_time_ms"] = delivery_time
            result["delivery_plan"] = delivery_plan.__dict__

            return result

        except Exception as e:
            # Fallback на простую отправку сообщения
            return await self._fallback_send(
                update, content, str(e), time.time() - start_time
            )

    async def _analyze_content(self, content: str) -> ResponseMetadata:
        """Анализ контента для определения метаданных."""
        lines = content.split('\n')
        line_count = len(lines)
        content_length = len(content)

        # Поиск таблиц
        table_count = 0
        large_tables = False
        for line in lines:
            if self._is_table_row(line):
                table_count += 1
                if table_count > self.LARGE_TABLE_THRESHOLD:
                    large_tables = True

        # Поиск сложных формул
        complex_formulas = self._has_complex_formulas(content)

        # Расчёт времени чтения (основано на средней скорости 200 слов/мин)
        word_count = len(content.split())
        estimated_read_time = (word_count / 200) * 60  # секунды

        # Расчёт сложности
        complexity_score = self._calculate_complexity_score(
            content_length, table_count, complex_formulas, line_count
        )

        return ResponseMetadata(
            content_length=content_length,
            has_large_tables=large_tables,
            has_complex_formulas=complex_formulas,
            table_count=table_count,
            line_count=line_count,
            estimated_read_time_seconds=estimated_read_time,
            complexity_score=complexity_score
        )

    def _create_delivery_plan(self, metadata: ResponseMetadata, content: str) -> DeliveryPlan:
        """Создание оптимального плана доставки."""
        content_length = metadata.content_length
        complexity = metadata.complexity_score

        # Основные решения о методе доставки
        if content_length >= self.MESSAGE_LENGTH_THRESHOLD:
            method = "file"
            format_type = "detailed" if complexity > 0.5 else "standard"
            should_compress = False
            estimated_time = 2000 + (content_length / 1000) * 50  # ms

        elif content_length > self.SEGMENT_THRESHOLD:
            method = "split"
            format_type = "standard"
            should_compress = True
            estimated_time = 1500 + (content_length / 500) * 100

        else:
            method = "message"
            format_type = "compact" if complexity < 0.3 else "standard"
            should_compress = complexity > 0.6
            estimated_time = 500 + (content_length / 1000) * 10

        return DeliveryPlan(
            method=method,
            format_type=format_type,
            should_compress=should_compress,
            estimated_delivery_time_ms=estimated_time
        )

    async def _send_as_messages(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        content: str,
        query_type: str,
        delivery_plan: DeliveryPlan
    ) -> Dict[str, Any]:
        """Отправка ответа как сообщения."""
        try:
            # Форматирование контента
            if delivery_plan.format_type == "compact":
                formatted_content = self._format_compact(content)
            else:
                formatted_content = content

            messages = self.response_formatter.format_thermo_response(
                formatted_content, query_type
            )

            # Отправка сообщений
            sent_messages = []
            for i, msg_text in enumerate(messages):
                if i > 0:
                    await asyncio.sleep(0.3)  # небольшая задержка

                message = await update.message.reply_text(
                    msg_text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                sent_messages.append(message.message_id)

            return {
                "success": True,
                "method": "message",
                "message_count": len(messages),
                "sent_message_ids": sent_messages,
                "total_characters": len(formatted_content)
            }

        except Exception as e:
            raise Exception(f"Ошибка отправки сообщений: {str(e)}")

    async def _send_as_file(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        content: str,
        query_type: str,
        user_query: str,
        delivery_plan: DeliveryPlan
    ) -> Dict[str, Any]:
        """Отправка ответа как файла."""
        try:
            # Извлечение соединений для имени файла
            compounds = self._extract_compounds_from_query(user_query) if user_query else []

            # Создание файла
            file_path, error = await self.file_handler.create_txt_file(
                content,
                query_type,
                compounds,
                title=f"ThermoSystem Report - {query_type.title()}"
            )

            if error or not file_path:
                raise Exception(f"Ошибка создания файла: {error}")

            # Создание InputFile
            input_file = await self.file_handler.create_input_file(file_path)
            if not input_file:
                raise Exception("Ошибка создания InputFile")

            # Создание краткого описания
            caption = self._create_file_caption(content, query_type, delivery_plan)

            # Отправка файла
            message = await update.message.reply_document(
                document=input_file,
                caption=caption,
                parse_mode="Markdown"
            )

            # Закрытие файла
            try:
                input_file.file_object.close()
            except:
                pass

            # Получение информации о файле
            file_info = await self.file_handler.get_file_info(file_path)

            return {
                "success": True,
                "method": "file",
                "file_path": str(file_path),
                "file_size_bytes": file_info.get("size_bytes", 0),
                "file_size_kb": file_info.get("size_kb", 0),
                "document_id": message.document.file_id,
                "caption_length": len(caption)
            }

        except Exception as e:
            raise Exception(f"Ошибка отправки файла: {str(e)}")

    async def _send_split_messages(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        content: str,
        query_type: str,
        delivery_plan: DeliveryPlan
    ) -> Dict[str, Any]:
        """Отправка ответа разделёнными сообщениями."""
        try:
            # Интеллектуальное разделение контента
            segments = await self._smart_split_content(content, query_type)

            # Отправка сегментов
            sent_messages = []
            for i, segment in enumerate(segments):
                # Заголовок сегмента
                if len(segments) > 1:
                    segment_header = f"📄 *Часть {i + 1}/{len(segments)}*\n\n"
                    segment_text = segment_header + segment
                else:
                    segment_text = segment

                # Добавление задержки между сообщениями
                if i > 0:
                    await asyncio.sleep(0.5)

                message = await update.message.reply_text(
                    segment_text,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                sent_messages.append(message.message_id)

            return {
                "success": True,
                "method": "split",
                "segment_count": len(segments),
                "sent_message_ids": sent_messages,
                "total_characters": sum(len(s) for s in segments)
            }

        except Exception as e:
            raise Exception(f"Ошибка отправки разделённых сообщений: {str(e)}")

    async def _fallback_send(
        self,
        update: Update,
        content: str,
        error: str,
        start_time: float
    ) -> Dict[str, Any]:
        """Fallback отправка при ошибках."""
        try:
            # Создание простого ответа
            fallback_content = f"""❌ *Произошла ошибка при обработке запроса*

Ошибка: {error}

📊 *Краткий результат:*
{content[:1000]}...

💡 *Попробуйте:*
• Упростить запрос
• Проверить формулы веществ
• Использовать /help для примеров"""

            await update.message.reply_text(
                fallback_content,
                parse_mode="Markdown"
            )

            return {
                "success": False,
                "method": "fallback",
                "error": error,
                "fallback_content_length": len(fallback_content),
                "delivery_time_ms": (time.time() - start_time) * 1000
            }

        except Exception as fallback_error:
            return {
                "success": False,
                "method": "failed",
                "error": f"Primary: {error}, Fallback: {str(fallback_error)}",
                "delivery_time_ms": (time.time() - start_time) * 1000
            }

    async def _smart_split_content(self, content: str, query_type: str) -> List[str]:
        """Интеллектуальное разделение контента на сегменты."""
        lines = content.split('\n')
        segments = []
        current_segment = ""
        segment_counter = 1

        # Логические разделители
        section_breaks = [
            "Результаты:", "Результат:", "Данные:", "Свойства:",
            "Вывод:", "Заключение:", "Интерпретация:",
            "Уравнение:", "Реакция:", "Температурный диапазон:"
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Проверка на разрыв секции
            is_section_break = any(break_marker in line for break_marker in section_breaks)

            # Проверка размера сегмента
            test_segment = current_segment + "\n" + line if current_segment else line

            if (len(test_segment) > self.SEGMENT_THRESHOLD) or (is_section_break and current_segment):
                # Сохраняем текущий сегмент
                if current_segment:
                    if segment_counter > 1:
                        current_segment = f"📄 *Часть {segment_counter}*\n\n{current_segment}"
                    segments.append(current_segment)
                    segment_counter += 1

                # Начинаем новый сегмент
                current_segment = line
            else:
                current_segment = test_segment

        # Добавляем последний сегмент
        if current_segment:
            if segment_counter > 1:
                current_segment = f"📄 *Часть {segment_counter}*\n\n{current_segment}"
            segments.append(current_segment)

        return segments if segments else [content]

    def _is_table_row(self, line: str) -> bool:
        """Определение, является ли строка частью таблицы."""
        import re
        # Паттерны для таблиц
        table_patterns = [
            r'\d+\.?\d*\s+\d+\.?\d*\s+\d+\.?\d*',  # три и более чисел
            r'\|\s*\d+\s*\|\s*\d+',  # формат |число|число|
            r'\d+\.\d+E[+-]\d+',  # научная нотация
            r'^\s*[|+-]+\s*$',  # разделители таблиц
        ]

        for pattern in table_patterns:
            if re.search(pattern, line):
                return True

        return False

    def _has_complex_formulas(self, content: str) -> bool:
        """Проверка на наличие сложных химических формул."""
        import re
        complex_patterns = [
            r'\b[A-Z][a-z]?\d*[A-Z][a-z]?\d*[A-Z][a-z]?\d*\b',  # трёхэлементные соединения
            r'\([^\)]+\)\d+',  # скобки с индексами
            r'\b[A-Z][a-z]?\d*_[0-9]+\b',  # изотопы
            r'→|←|↔|⇌|⇀',  # сложные стрелки
        ]

        for pattern in complex_patterns:
            if re.search(pattern, content):
                return True

        return False

    def _calculate_complexity_score(
        self,
        content_length: int,
        table_count: int,
        complex_formulas: bool,
        line_count: int
    ) -> float:
        """Расчёт оценки сложности контента (0.0 - 1.0)."""
        # Нормализация факторов
        length_factor = min(content_length / 10000, 1.0)  # до 10K символов
        table_factor = min(table_count / 20, 1.0)  # до 20 строк таблиц
        formula_factor = 0.3 if complex_formulas else 0.0
        line_factor = min(line_count / 100, 1.0)  # до 100 строк

        # Взвешенная сумма
        complexity = (
            length_factor * 0.3 +
            table_factor * 0.4 +
            formula_factor * 0.2 +
            line_factor * 0.1
        )

        return min(complexity, 1.0)

    def _format_compact(self, content: str) -> str:
        """Форматирование в компактном виде."""
        lines = content.split('\n')
        compact_lines = []

        # Сохраняем только ключевые строки
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Ключевые маркеры для сохранения
            if any(keyword in line.lower() for keyword in [
                "уравнение:", "реакция:", "результаты:", "δh", "δs", "δg",
                "вывод:", "температура", "давление", "константа"
            ]):
                compact_lines.append(line)
            elif line.startswith('|') or '→' in line or '->' in line:
                compact_lines.append(line)
            elif len(compact_lines) < 30:  # Ограничиваем количество строк
                compact_lines.append(line)

        return '\n'.join(compact_lines)

    def _extract_compounds_from_query(self, query: str) -> List[str]:
        """Извлечение соединений из запроса."""
        import re

        # Простые паттерны для химических формул
        patterns = [
            r'\b[A-Z][a-z]?\d*[a-z]?\d*\b',
            r'\b[A-Z]{2,}\d*\b',
        ]

        compounds = set()
        for pattern in patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                if len(match) > 1:  # отфильтровываем однобуквенные совпадения
                    compounds.add(match)

        return list(compounds)[:5]  # максимум 5 соединений

    def _create_file_caption(self, content: str, query_type: str, delivery_plan: DeliveryPlan) -> str:
        """Создание подписи к файлу."""
        # Извлечение ключевой информации
        lines = content.split('\n')
        equation = ""
        temp_range = ""

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in ["уравнение:", "реакция:"]):
                equation = line.strip()
            elif any(keyword in line_lower for keyword in ["температурный диапазон:", "диапазон:"]):
                temp_range = line.strip()

        type_names = {
            "reaction": "термодинамики реакции",
            "compound_data": "свойств вещества",
            "calculation": "термодинамического расчёта"
        }

        calc_type = type_names.get(query_type, "расчёта")

        caption = f"📄 *Детальный отчёт по {calc_type}*\n"

        if equation:
            caption += f"\n**{equation}**"

        if temp_range:
            caption += f"\n🌡️ {temp_range}"

        caption += f"""

📊 *Информация о файле:*
• Формат: optimised для анализа
• Сложность: {delivery_plan.format_type}
• Создан автоматически ThermoSystem

📎 *Файл содержит полный анализ с таблицами, формулами и интерпретацией результатов.*"""

        return caption

    def get_optimization_stats(self) -> Dict[str, Any]:
        """Получение статистики оптимизации."""
        return {
            "message_length_threshold": self.MESSAGE_LENGTH_THRESHOLD,
            "segment_threshold": self.SEGMENT_THRESHOLD,
            "complexity_threshold": self.COMPLEXITY_THRESHOLD,
            "large_table_threshold": self.LARGE_TABLE_THRESHOLD,
            "supported_methods": ["message", "file", "split"],
            "supported_formats": ["standard", "compact", "detailed"]
        }