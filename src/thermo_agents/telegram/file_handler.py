"""
Telegram File Handler - Управление временными файлами для Telegram бота

Обеспечивает создание, отправку и очистку временных файлов для
доставки больших термодинамических отчётов через Telegram Bot API.
"""

import os
import tempfile
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
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

        # Запуск фоновой очистки (только если есть event loop)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._periodic_cleanup())
        except RuntimeError:
            # Нет event loop - очистка будет запускаться вручную
            logger.info("No event loop available - periodic cleanup will be manual")

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
        update,
        context,
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
        update,
        context,
        file_path: str,
        filename: str,
        content: str
    ) -> bool:
        """Отправка документа через Telegram API"""
        try:
            # Импорт telegram здесь для избежания circular imports
            from telegram import InputFile

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

    async def _send_size_error(self, update, file_size_mb: float):
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

    async def _send_file_summary(self, update, summary: str):
        """Отправка краткого summary после отправки файла"""
        summary_text = (
            f"✅ *Отчёт готов!*\n\n"
            f"{summary}\n\n"
            f"💾 *Полный отчёт в прикреплённом файле*"
        )

        await update.message.reply_text(summary_text, parse_mode="Markdown")

    async def _send_error_message(self, update, error_message: str):
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