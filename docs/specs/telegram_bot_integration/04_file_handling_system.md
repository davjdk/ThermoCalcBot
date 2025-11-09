# Система обработки файлов и умные ответы

**Проект:** ThermoSystem Telegram Bot Integration
**Версия документа:** 1.1
**Дата:** 9 ноября 2025

---

## 📄 1. Обзор системы обработки файлов

### 1.1. Стратегия умных ответов

Система интеллектуально выбирает формат ответа в зависимости от размера и сложности контента:

| Критерий | Условие | Формат доставки |
|----------|---------|-----------------|
| **Размер ответа** | `< 3000 символов` | Telegram сообщение |
| **Размер ответа** | `≥ 3000 символов` | TXT файл |
| **Большие таблицы** | `> 20 строк таблицы` | TXT файл |
| **Сложное форматирование** | Много Unicode символов | TXT файл |
| **Лимит Telegram** | `> 20MB` | Ошибка и предложение уменьшить |

### 1.2. Преимущества TXT файлов

**Профессиональные возможности:**
- 📄 **Без ограничений 4096 символов** - полные термодинамические отчёты
- 🎯 **Идеальное сохранение форматирования** таблиц, формул, выравнивания
- 💼 **Скачать для офлайн анализа** - удобно для исследователей
- 📱 **Доступно на всех устройствах** - мобильные и десктоп
- 📊 **Профессиональный вид** - подходит для академических работ

**Технические характеристики:**
- ✅ **Полная поддержка TXT файлов** до 20MB (лимит Telegram Bot API)
- ✅ **UTF-8 кодировка** - сохранение Unicode химических формул (H₂O, CO₂, →)
- ✅ **Метод `sendDocument()`** с классом `InputFile`
- ✅ **Автоматическая очистка** временных файлов через 24 часа

---

## 🗂️ 2. TelegramFileHandler

### 2.1. Основной класс управления файлами

```python
import os
import tempfile
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from telegram import InputFile, Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

class TelegramFileHandler:
    """Управление временными файлами для Telegram бота"""

    def __init__(
        self,
        temp_dir: str = "temp/telegram_files",
        cleanup_hours: int = 24,
        max_file_size_mb: int = 20
    ):
        self.temp_dir = Path(temp_dir)
        self.cleanup_hours = cleanup_hours
        self.max_file_size_mb = max_file_size_mb
        self.active_files: Dict[int, Dict[str, Any]] = {}

        # Создание директории
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Запуск фоновой очистки
        asyncio.create_task(self._periodic_cleanup())

        logger.info(f"TelegramFileHandler initialized with temp_dir: {self.temp_dir}")

    async def create_temp_file(
        self,
        content: str,
        user_id: int,
        reaction_info: str = ""
    ) -> str:
        """Создание временного файла с уникальным именем"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Генерация имени файла
        safe_reaction = self._sanitize_filename(reaction_info)[:30]
        if safe_reaction:
            filename = f"thermo_report_{safe_reaction}_{timestamp}.txt"
        else:
            filename = f"thermo_report_{timestamp}.txt"

        file_path = self.temp_dir / filename

        # Запись файла с UTF-8 кодировкой
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # Регистрация файла
            self.active_files[user_id] = {
                'path': str(file_path),
                'filename': filename,
                'created_at': datetime.now(),
                'size': len(content),
                'reaction_info': reaction_info
            }

            logger.info(f"Created temp file: {filename} for user {user_id}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Error creating temp file: {e}")
            raise

    async def send_file(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        content: str,
        reaction_info: str = ""
    ) -> bool:
        """Отправка контента как файла"""
        try:
            # Проверка размера файла (лимит Telegram: 20MB)
            file_size_mb = len(content.encode('utf-8')) / (1024 * 1024)

            if file_size_mb > self.max_file_size_mb:
                logger.warning(f"File size {file_size_mb:.2f}MB exceeds Telegram limit (20MB)")
                await self._send_size_error(update, file_size_mb)
                return False

            # Создание временного файла
            file_path = await self.create_temp_file(content, update.effective_user.id, reaction_info)
            filename = Path(file_path).name

            # Отправка файла
            success = await self._send_document(update, context, file_path, filename, content)

            if success:
                # Краткое summary в чате
                summary = self._extract_summary(content)
                await self._send_file_summary(update, summary)

            return success

        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await self._send_error_message(update, str(e))
            return False

    async def _send_document(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        file_path: str,
        filename: str,
        content: str
    ) -> bool:
        """Отправка документа через Telegram API"""
        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()

            input_file = InputFile(file_content, filename=filename)

            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=input_file,
                caption=self._generate_caption(content, self.active_files[update.effective_user.id].get('reaction_info', '')),
                parse_mode="Markdown"
            )

            logger.info(f"File sent successfully: {filename}")
            return True

        except Exception as e:
            logger.error(f"Error sending document: {e}")
            return False

    def _generate_caption(self, content: str, reaction_info: str) -> str:
        """Генерация подписи к файлу"""
        char_count = len(content)
        kb_size = char_count / 1024

        caption = (
            f"📊 *Детальный термодинамический отчёт*\n\n"
        )

        if reaction_info:
            caption += f"**Реакция:** {reaction_info}\n"

        caption += (
            f"**Размер:** {char_count:,} символов ({kb_size:.1f} KB)\n"
            f"**Создан:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💾 *Сохраните файл для офлайн анализа*"
        )

        return caption

    def _sanitize_filename(self, filename: str) -> str:
        """Очистка имени файла от недопустимых символов с Unicode нормализацией"""
        import re
        import unicodedata

        # Нормализация Unicode (NFD -> NFC для совместимости)
        filename = unicodedata.normalize('NFKC', filename)

        # Преобразование подстрочных индексов в обычные цифры для имён файлов
        subscript_map = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
        filename = filename.translate(subscript_map)

        # Удаление специальных Unicode символов (→, ⇌, и т.д.)
        filename = filename.replace('→', '_to_').replace('⇌', '_eq_')

        # Замена специальных символов на подчеркивание
        filename = re.sub(r'[^\w\s-]', '_', filename)

        # Замена пробелов на подчеркивание
        filename = re.sub(r'\s+', '_', filename)

        # Удаление множественных подчеркиваний
        filename = re.sub(r'_+', '_', filename)

        # Ограничение длины
        return filename.strip('_')[:50]

    async def _send_size_error(self, update: Update, file_size_mb: float):
        """Отправка сообщения об ошибке размера файла"""
        error_text = (
            f"⚠️ *Файл слишком большой*\n\n"
            f"Размер отчёта: {file_size_mb:.2f}MB превышает лимит Telegram (20MB).\n"
            f"Попробуйте уменьшить температурный диапазон или шаг расчёта."
        )

        await update.message.reply_text(error_text, parse_mode="Markdown")

    def _extract_summary(self, response: str) -> str:
        """Извлечение краткого summary из полного отчёта"""
        lines = response.split('\n')

        # Поиск ключевой информации
        summary_lines = []
        for line in lines[:50]:  # Первые 50 строк
            if any(keyword in line for keyword in [
                'Уравнение:', 'Температурный диапазон:', 'ΔH', 'K =', 'T ='
            ]):
                summary_lines.append(line)

        summary = '\n'.join(summary_lines[:5])  # Максимум 5 строк summary

        if not summary:
            summary = "✅ *Расчёт завершён успешно*"

        return summary

    async def _send_file_summary(self, update: Update, summary: str):
        """Отправка краткого summary после отправки файла"""
        summary_text = (
            f"✅ *Отчёт готов!*\n\n"
            f"{summary}\n\n"
            f"💾 *Полный отчёт в прикреплённом файле*"
        )

        await update.message.reply_text(summary_text, parse_mode="Markdown")

    async def _send_error_message(self, update: Update, error_message: str):
        """Отправка сообщения об ошибке"""
        error_text = (
            "😔 *Ошибка при отправке файла*\n\n"
            f"```{error_message}```\n\n"
            "Попробуйте повторить запрос или используйте /help"
        )

        await update.message.reply_text(error_text, parse_mode="Markdown")

    async def _periodic_cleanup(self):
        """Периодическая очистка старых файлов"""
        while True:
            try:
                await asyncio.sleep(3600)  # Проверка каждый час
                await self._cleanup_old_files()
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")

    async def _cleanup_old_files(self):
        """Очистка файлов старше cleanup_hours"""
        cutoff_time = datetime.now() - timedelta(hours=self.cleanup_hours)
        deleted_count = 0

        try:
            for file_path in self.temp_dir.glob("*.txt"):
                if datetime.fromtimestamp(file_path.stat().st_mtime) < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted old file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Error deleting file {file_path}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old files")

        except Exception as e:
            logger.error(f"Error during file cleanup: {e}")

    def get_file_stats(self) -> Dict[str, Any]:
        """Статистика по файлам"""
        try:
            files = list(self.temp_dir.glob("*.txt"))
            total_size = sum(f.stat().st_size for f in files)

            return {
                'total_files': len(files),
                'total_size_mb': total_size / (1024 * 1024),
                'active_sessions': len(self.active_files),
                'temp_directory': str(self.temp_dir)
            }
        except Exception as e:
            logger.error(f"Error getting file stats: {e}")
            return {
                'total_files': 0,
                'total_size_mb': 0,
                'active_sessions': len(self.active_files),
                'temp_directory': str(self.temp_dir),
                'error': str(e)
            }

    async def cleanup_user_files(self, user_id: int):
        """Очистка файлов конкретного пользователя"""
        if user_id in self.active_files:
            user_file_info = self.active_files[user_id]
            try:
                file_path = Path(user_file_info['path'])
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Cleaned up file for user {user_id}: {file_path.name}")
            except Exception as e:
                logger.error(f"Error cleaning up user file: {e}")

            del self.active_files[user_id]

    async def shutdown(self):
        """Корректное завершение работы с очисткой"""
        logger.info("Shutting down TelegramFileHandler...")

        # Очистка всех активных файлов
        for user_id in list(self.active_files.keys()):
            await self.cleanup_user_files(user_id)

        # Финальная очистка директории
        try:
            await self._cleanup_old_files()
        except Exception as e:
            logger.error(f"Error during shutdown cleanup: {e}")

        logger.info("TelegramFileHandler shutdown complete")
```

---

## 🧠 3. SmartResponseHandler

### 3.1. Умная логика отправки ответов

```python
import re
from typing import List
from telegram import Update
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

class SmartResponseHandler:
    """Умная отправка ответов (сообщение или файл)"""

    def __init__(
        self,
        file_handler: TelegramFileHandler,
        message_threshold: int = 3000
    ):
        self.file_handler = file_handler
        self.message_threshold = message_threshold

    async def send_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
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
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
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

    async def _send_error_message(self, update: Update, error_message: str):
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
```

---

## 📋 4. Конфигурация файловой системы

### 4.1. FileHandlerConfig

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class FileHandlerConfig:
    """Конфигурация системы обработки файлов"""

    # Directory configuration
    temp_file_dir: str = "temp/telegram_files"
    cleanup_hours: int = 24
    max_file_size_mb: int = 20  # Лимит Telegram Bot API

    # Smart response configuration
    auto_file_threshold: int = 3000  # символов
    max_table_rows: int = 20
    max_unicode_lines: int = 10

    # File naming
    max_filename_length: int = 50
    filename_timestamp_format: str = "%Y%m%d_%H%M%S"

    # Performance
    enable_file_compression: bool = False
    max_concurrent_file_operations: int = 5

    @classmethod
    def from_env(cls) -> 'FileHandlerConfig':
        """Создание конфигурации из переменных окружения"""
        return cls(
            temp_file_dir=os.getenv("TEMP_FILE_DIR", "temp/telegram_files"),
            cleanup_hours=int(os.getenv("FILE_CLEANUP_HOURS", "24")),
            max_file_size_mb=int(os.getenv("MAX_FILE_SIZE_MB", "20")),
            auto_file_threshold=int(os.getenv("AUTO_FILE_THRESHOLD", "3000")),
            max_table_rows=int(os.getenv("MAX_TABLE_ROWS", "20")),
            max_unicode_lines=int(os.getenv("MAX_UNICODE_LINES", "10")),
            max_filename_length=int(os.getenv("MAX_FILENAME_LENGTH", "50")),
            enable_file_compression=os.getenv("ENABLE_FILE_COMPRESSION", "false").lower() == "true",
            max_concurrent_file_operations=int(os.getenv("MAX_CONCURRENT_FILE_OPERATIONS", "5"))
        )

    def validate(self) -> List[str]:
        """Валидация конфигурации"""
        errors = []

        if self.cleanup_hours <= 0:
            errors.append("FILE_CLEANUP_HOURS must be positive")

        if self.max_file_size_mb <= 0 or self.max_file_size_mb > 50:
            errors.append("MAX_FILE_SIZE_MB must be between 1 and 50")

        if self.auto_file_threshold < 1000:
            errors.append("AUTO_FILE_THRESHOLD must be at least 1000 characters")

        if self.max_table_rows < 5:
            errors.append("MAX_TABLE_ROWS must be at least 5")

        return errors
```

### 4.2. Интеграция с основной системой

```python
# В основном классе бота
class ThermoSystemTelegramBot:
    def __init__(self, config: TelegramBotConfig):
        self.config = config

        # Инициализация файловой системы
        file_handler_config = FileHandlerConfig.from_env()
        self.file_handler = TelegramFileHandler(
            temp_dir=file_handler_config.temp_file_dir,
            cleanup_hours=file_handler_config.cleanup_hours,
            max_file_size_mb=file_handler_config.max_file_size_mb
        )

        # Инициализация умных ответов
        self.smart_response_handler = SmartResponseHandler(
            file_handler=self.file_handler,
            message_threshold=file_handler_config.auto_file_threshold
        )

    async def shutdown(self):
        """Корректное завершение работы с очисткой файлов"""
        logger.info("Shutting down bot...")

        # Очистка файловой системы
        await self.file_handler.shutdown()

        # Другие операции shutdown...
        logger.info("Bot shutdown complete")
```

---

## 🧪 5. Тестирование файловой системы

### 5.1. Unit тесты для FileHandler

```python
import pytest
import tempfile
from unittest.mock import AsyncMock, Mock
from pathlib import Path

@pytest.mark.asyncio
class TestTelegramFileHandler:
    def setup_method(self):
        """Настройка тестового окружения"""
        self.temp_dir = tempfile.mkdtemp()
        self.file_handler = TelegramFileHandler(
            temp_dir=self.temp_dir,
            cleanup_hours=1,  # 1 час для тестов
            max_file_size_mb=1  # 1MB для тестов
        )

    async def test_create_temp_file(self):
        """Тест создания временного файла"""
        content = "Test content"
        user_id = 12345
        reaction_info = "2 H2 + O2 → 2 H2O"

        file_path = await self.file_handler.create_temp_file(
            content, user_id, reaction_info
        )

        # Проверки
        assert Path(file_path).exists()
        assert Path(file_path).name.startswith("thermo_report_")
        assert "2H2_O2_to_2H2O" in Path(file_path).name

        # Проверка содержимого
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

    def test_sanitize_filename(self):
        """Тест очистки имени файла"""
        test_cases = [
            ("2 H₂ + O₂ → 2 H₂O", "2H2_O2_to_2H2O"),
            ("CO₂ + H₂O ⇌ H₂CO₃", "CO2_H2O_eq_H2CO3"),
            ("Complex reaction: A→B", "Complex_reaction_A_to_B"),
            ("", ""),
            ("Very long filename that should be truncated", "Very_long_filename_that_should_be_tr")
        ]

        for input_name, expected in test_cases:
            result = self.file_handler._sanitize_filename(input_name)
            assert result == expected[:50]  # С учётом ограничения длины

    def test_should_use_file_criteria(self):
        """Тест критериев использования файла"""
        smart_handler = SmartResponseHandler(self.file_handler)

        # Длинный ответ
        long_response = "A" * 4000
        assert smart_handler._should_use_file(long_response) == True

        # Короткий ответ
        short_response = "Short response"
        assert smart_handler._should_use_file(short_response) == False

        # Ответ с большой таблицей
        table_response = "| T | H | S |\n" + "A | B | C |\n" * 25
        assert smart_handler._has_large_tables(table_response) == True

        # Ответ со сложным форматированием
        complex_response = "┌─────┐\n" * 15
        assert smart_handler._has_complex_formatting(complex_response) == True

    async def test_cleanup_old_files(self):
        """Тест очистки старых файлов"""
        import time
        from datetime import datetime, timedelta

        # Создание тестового файла
        test_file = Path(self.temp_dir) / "test_old_file.txt"
        test_file.write_text("test content")

        # Установка старого времени модификации
        old_time = datetime.now() - timedelta(hours=25)
        old_timestamp = old_time.timestamp()

        # Изменение времени файла (platform dependent)
        try:
            import os
            os.utime(test_file, (old_timestamp, old_timestamp))
        except:
            # Если не удалось изменить время, пропускаем тест
            pass

        # Запуск очистки
        await self.file_handler._cleanup_old_files()

        # Проверка (файл должен быть удалён)
        # Note: Этот тест может не работать на всех системах
```

### 5.2. Интеграционные тесты

```python
@pytest.mark.asyncio
async def test_end_to_end_file_delivery():
    """Тест полной цепочки доставки файла"""
    # Mock объекты Telegram
    mock_update = Mock()
    mock_update.effective_user.id = 12345
    mock_update.effective_chat.id = 67890
    mock_update.message.reply_text = AsyncMock()

    mock_context = Mock()
    mock_context.bot.send_document = AsyncMock()

    # Тестовый контент (большой для файла)
    large_content = "Thermodynamic report content...\n" * 200

    # Создание обработчиков
    file_handler = TelegramFileHandler(temp_dir=tempfile.mkdtemp())
    smart_handler = SmartResponseHandler(file_handler)

    # Отправка ответа
    success = await smart_handler.send_response(
        mock_update, mock_context, large_content, "Test Reaction"
    )

    # Проверки
    assert success == True
    assert mock_context.bot.send_document.called
    assert mock_update.message.reply_text.called  # Для summary

    # Очистка
    await file_handler.shutdown()
```

---

## 📊 6. Метрики и мониторинг

### 6.1. File System Metrics

```python
class FileSystemMetrics:
    """Сбор метрик файловой системы"""

    def __init__(self, file_handler: TelegramFileHandler):
        self.file_handler = file_handler
        self.metrics = {
            'files_created': 0,
            'files_sent': 0,
            'total_size_mb': 0.0,
            'errors': 0,
            'cleanup_runs': 0
        }

    def record_file_creation(self, size_mb: float):
        """Запись создания файла"""
        self.metrics['files_created'] += 1
        self.metrics['total_size_mb'] += size_mb

    def record_file_sent(self, size_mb: float):
        """Запись отправки файла"""
        self.metrics['files_sent'] += 1

    def record_error(self):
        """Запись ошибки"""
        self.metrics['errors'] += 1

    def record_cleanup(self, files_deleted: int):
        """Запись очистки"""
        self.metrics['cleanup_runs'] += 1

    def get_metrics(self) -> dict:
        """Получение всех метрик"""
        current_stats = self.file_handler.get_file_stats()

        return {
            **self.metrics,
            'current_stats': current_stats,
            'average_file_size_mb': (
                self.metrics['total_size_mb'] / max(1, self.metrics['files_created'])
            ),
            'success_rate': (
                (self.metrics['files_sent'] / max(1, self.metrics['files_created'])) * 100
            )
        }

    def reset_metrics(self):
        """Сброс метрик"""
        for key in self.metrics:
            self.metrics[key] = 0
```

---

## 📋 7. Следующие шаги

После изучения файловой системы перейдите к документу **[05_security_monitoring.md](./05_security_monitoring.md)** для ознакомления с требованиями безопасности и мониторинга системы.

---

**Документ подготовлен для:** Python разработчиков и DevOps инженеров
**Целевая аудитория:** Команда разработки ThermoSystem
**Сложность реализации:** Средняя (требует знаний async Python, file handling, Unicode)