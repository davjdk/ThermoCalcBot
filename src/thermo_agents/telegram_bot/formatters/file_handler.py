"""
Обработка файлов для детальных термодинамических отчетов.

Поддерживает:
- Генерацию TXT файлов с отчетами
- Управление временными файлами
- Автоматическую очистку
- Unicode нормализацию для Windows
"""

import os
import re
import time
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import unicodedata

from telegram import InputFile
from telegram.constants import ParseMode

from ..config import TelegramBotConfig


class FileHandler:
    """Управление TXT файлами для Telegram бота."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.temp_file_dir = config.temp_file_dir
        self.max_file_size_bytes = config.max_file_size_mb * 1024 * 1024

        # Создание директории для временных файлов
        self.temp_file_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """Очистка имени файла для безопасного хранения."""
        # Unicode нормализация для Windows
        normalized = unicodedata.normalize('NFKD', filename)

        # Удаление недопустимых символов
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', normalized)

        # Удаление пробелов в начале и конце
        sanitized = sanitized.strip()

        # Ограничение длины
        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized

    def _generate_filename(self, query_type: str, compounds: list[str]) -> str:
        """Генерация имени файла на основе запроса."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Создание короткого имени из соединений
        if compounds:
            compound_str = "_".join(compounds[:3])  # Максимум 3 соединения
            if len(compound_str) > 30:
                compound_str = compound_str[:30]
        else:
            compound_str = "calculation"

        query_suffix = {
            "reaction": "reaction",
            "compound_data": "properties",
            "unknown": "calculation"
        }.get(query_type, "calculation")

        filename = f"thermo_{query_suffix}_{compound_str}_{timestamp}.txt"
        return self._sanitize_filename(filename)

    async def create_txt_file(
        self,
        content: str,
        query_type: str,
        compounds: list[str],
        title: str = "Термодинамический отчет"
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        Создание TXT файла с термодинамическим отчетом.

        Args:
            content: Содержимое отчета
            query_type: Тип запроса (reaction, compound_data)
            compounds: Список соединений
            title: Заголовок отчета

        Returns:
            Tuple[Path к файлу, ошибка]
        """
        try:
            # Проверка размера контента
            content_size = len(content.encode('utf-8'))
            if content_size > self.max_file_size_bytes:
                return None, f"Размер отчета ({content_size / 1024 / 1024:.1f}MB) превышает лимит ({self.config.max_file_size_mb}MB)"

            # Генерация имени файла
            filename = self._generate_filename(query_type, compounds)
            file_path = self.temp_file_dir / filename

            # Форматирование контента с заголовком
            formatted_content = self._format_report_content(content, title, query_type)

            # Сохранение файла
            file = await asyncio.to_thread(open, file_path, 'w', encoding='utf-8')
            try:
                await asyncio.to_thread(file.write, formatted_content)
            finally:
                await asyncio.to_thread(file.close)

            return file_path, None

        except Exception as e:
            return None, f"Ошибка создания файла: {str(e)}"

    def _format_report_content(self, content: str, title: str, query_type: str) -> str:
        """Форматирование контента для TXT файла."""
        separator = "=" * 60
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        formatted = f"""
{separator}
{title}
{separator}

Сгенерировано: {timestamp}
Тип расчета: {query_type}
Источник: ThermoSystem v2.2

{separator}

{content}

{separator}
© 2025 ThermoSystem Telegram Bot (@ThermoCalcBot)
Отчет сгенерирован автоматически. Для проверки и исследований.
"""

        return formatted.strip()

    async def cleanup_old_files(self) -> int:
        """Очистка старых временных файлов."""
        try:
            cleaned_count = 0
            cutoff_time = datetime.now() - timedelta(hours=self.config.file_cleanup_hours)

            for file_path in self.temp_file_dir.glob("thermo_*.txt"):
                if file_path.is_file():
                    file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_time < cutoff_time:
                        await asyncio.to_thread(os.remove, file_path)
                        cleaned_count += 1

            return cleaned_count

        except Exception as e:
            print(f"Ошибка очистки файлов: {e}")
            return 0

    async def get_file_info(self, file_path: Path) -> dict:
        """Получение информации о файле."""
        try:
            stat = file_path.stat()
            return {
                "name": file_path.name,
                "size_bytes": stat.st_size,
                "size_kb": round(stat.st_size / 1024, 2),
                "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "exists": True
            }
        except Exception:
            return {"exists": False}

    def should_send_as_file(self, content: str, has_large_tables: bool = False) -> bool:
        """
        Определение, нужно ли отправлять контент как файл.

        Args:
            content: Содержимое ответа
            has_large_tables: Есть ли большие таблицы

        Returns:
            True если нужно отправлять как файл
        """
        content_length = len(content)

        # Основной критерий - длина контента
        if content_length >= self.config.response_format_threshold:
            return True

        # Дополнительные критерии
        if has_large_tables or "температурный диапазон" in content.lower():
            if content_length > 2000:  # Более низкий порог для таблиц
                return True

        return False

    async def create_input_file(self, file_path: Path) -> Optional[InputFile]:
        """Создание InputFile для отправки через Telegram Bot API."""
        try:
            # Проверка существования файла
            if not file_path.exists():
                return None

            # Создание InputFile
            file_handle = await asyncio.to_thread(open, file_path, 'rb')
            try:
                input_file = InputFile(
                    file_handle,
                    filename=file_path.name
                )
                return input_file
            except Exception as e:
                await asyncio.to_thread(file_handle.close)
                print(f"Ошибка создания InputFile: {e}")
                return None

        except Exception as e:
            print(f"Ошибка создания InputFile: {e}")
            return None

    async def get_temp_files_count(self) -> int:
        """Получение количества временных файлов."""
        try:
            return len(list(self.temp_file_dir.glob("thermo_*.txt")))
        except Exception:
            return 0

    async def get_total_temp_files_size(self) -> int:
        """Получение общего размера временных файлов в байтах."""
        try:
            total_size = 0
            for file_path in self.temp_file_dir.glob("thermo_*.txt"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        except Exception:
            return 0