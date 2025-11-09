"""
Форматирование ответов для Telegram Bot.

Адаптирует вывод ThermoSystem под ограничения Telegram API:
- Разделение длинных сообщений (>4096 символов)
- Markdown форматирование
- Unicode символы для химических формул
- Эмодзи для визуальной структуры
"""

import re
from typing import List, Tuple
from telegram.constants import ParseMode

from ..config import TelegramBotConfig


class ResponseFormatter:
    """Форматирование ответов для Telegram."""

    def __init__(self, config: TelegramBotConfig):
        self.config = config
        self.max_length = config.max_message_length

    def format_thermo_response(self, content: str, query_type: str = "calculation") -> List[str]:
        """
        Форматирование ответа от ThermoSystem для Telegram.

        Args:
            content: Оригинальный контент от ThermoSystem
            query_type: Тип запроса (reaction, compound_data)

        Returns:
            Список отформатированных сообщений для отправки
        """
        # Базовая обработка
        formatted = self._enhance_content(content, query_type)

        # Проверка длины и разделение
        if len(formatted) <= self.max_length:
            return [formatted]

        # Разделение на части
        return self._split_long_message(formatted, query_type)

    def _enhance_content(self, content: str, query_type: str) -> str:
        """Улучшение контента для Telegram."""
        # Добавление эмодзи в зависимости от типа запроса
        emoji_map = {
            "reaction": "🔥",
            "compound_data": "📊",
            "calculation": "⚗️"
        }

        emoji = emoji_map.get(query_type, "🔬")

        # Форматирование заголовка
        if query_type == "reaction":
            title = f"{emoji} *Термодинамический расчёт реакции*"
        elif query_type == "compound_data":
            title = f"{emoji} *Термодинамические свойства вещества*"
        else:
            title = f"{emoji} *Термодинамический расчёт*"

        # Разделение контента на строки
        lines = content.strip().split('\n')

        # Поиск и форматирование ключевых секций
        enhanced_lines = [title]

        current_section = None
        for line in lines:
            line = line.strip()

            if not line:
                continue

            # Форматирование ключевых терминов
            line = self._format_key_terms(line)

            # Определение секций
            if any(keyword in line.lower() for keyword in [
                "уравнение:", "реакция:", "уравнение реакции"
            ]):
                enhanced_lines.append(f"\n**{line}**")
                current_section = "equation"

            elif any(keyword in line.lower() for keyword in [
                "температурный диапазон:", "диапазон:", "температуры:"
            ]):
                enhanced_lines.append(f"\n🌡️ **{line}**")
                current_section = "temperature"

            elif any(keyword in line.lower() for keyword in [
                "результаты:", "результат:", "данные:", "свойства:"
            ]):
                enhanced_lines.append(f"\n📈 **{line}**")
                current_section = "results"

            elif any(keyword in line.lower() for keyword in [
                "вывод:", "заключение:", "интерпретация:"
            ]):
                enhanced_lines.append(f"\n📝 **{line}**")
                current_section = "conclusion"

            else:
                # Обработка таблиц
                if self._is_table_line(line):
                    line = self._format_table_line(line, current_section)

                # Обработка формул
                line = self._format_chemical_formulas(line)

                enhanced_lines.append(line)

        # Добавление завершающего элемента
        enhanced_lines.append("\n" + "─" * 30)

        return '\n'.join(enhanced_lines)

    def _format_key_terms(self, line: str) -> str:
        """Форматирование ключевых терминов."""
        # Δ символы
        line = re.sub(r'\bDelta H\b', 'ΔH', line)
        line = re.sub(r'\bDelta S\b', 'ΔS', line)
        line = re.sub(r'\bDelta G\b', 'ΔG', line)

        # Температура
        line = re.sub(r'\b(\d+)K\b', r'\1K', line)
        line = re.sub(r'\b(\d+)°C\b', r'\1°C', line)

        return line

    def _is_table_line(self, line: str) -> bool:
        """Определение, является ли строка таблицей."""
        # Проверка на наличие нескольких цифр и разделителей
        return bool(re.search(r'\d+.*\d+.*\d+', line) and ('|' in line or '\t' in line))

    def _format_table_line(self, line: str, section: str = None) -> str:
        """Форматирование строки таблицы."""
        # Замена табуляции на разделители
        line = line.replace('\t', ' | ')

        # Добавление форматирования для таблиц
        if section == "results":
            return f"`{line}`"
        else:
            return line

    def _format_chemical_formulas(self, line: str) -> str:
        """Форматирование химических формул с Unicode."""
        # Замена простых формул на Unicode варианты
        formula_replacements = {
            r'\bH2O\b': 'H₂O',
            r'\bCO2\b': 'CO₂',
            r'\bCO\b': 'CO',
            r'\bO2\b': 'O₂',
            r'\bH2\b': 'H₂',
            r'\bN2\b': 'N₂',
            r'\bNH3\b': 'NH₃',
            r'\bCH4\b': 'CH₄',
            r'\bHCl\b': 'HCl',
            r'\bSO2\b': 'SO₂',
            r'\bNO2\b': 'NO₂',
        }

        for pattern, replacement in formula_replacements.items():
            line = re.sub(pattern, replacement, line)

        # Форматирование стрелок реакций
        line = re.sub(r'\s*->\s*', ' → ', line)
        line = re.sub(r'\s*=>\s*', ' ⇒ ', line)

        return line

    def _split_long_message(self, content: str, query_type: str) -> List[str]:
        """Разделение длинного сообщения на части."""
        messages = []
        current_message = ""

        lines = content.split('\n')

        # Заголовок для каждой части
        part_emoji = "🔥" if query_type == "reaction" else "📊"
        part_counter = 1

        for line in lines:
            # Проверка, добавление строки не превысит лимит
            test_message = current_message + '\n' + line if current_message else line

            if len(test_message) <= self.max_length - 100:  # Оставляем запас
                current_message = test_message
            else:
                # Сохраняем текущее сообщение
                if current_message:
                    if part_counter > 1:
                        current_message = f"{part_emoji} *Часть {part_counter}*\n\n{current_message}"
                    messages.append(current_message)
                    part_counter += 1

                # Начинаем новое сообщение
                current_message = line

        # Добавляем последнее сообщение
        if current_message:
            if part_counter > 1:
                current_message = f"{part_emoji} *Часть {part_counter}*\n\n{current_message}"
            messages.append(current_message)

        return messages

    def format_error_message(self, error_text: str) -> str:
        """Форматирование сообщения об ошибке."""
        return f"""❌ *Ошибка выполнения запроса*

{error_text}

Пожалуйста, проверьте:
• Правильность написания химических формул
• Указан ли температурный диапазон
• Корректность синтаксиса化学反应

Для справки используйте /help"""

    def format_help_message(self) -> str:
        """Форматирование справочного сообщения."""
        return """🔬 *ThermoSystem Telegram Bot*

📋 *Основные команды:*
/start - Приветствие и краткая справка
/help - Подробная справка по использованию
/calculate <запрос> - Выполнить термодинамический расчёт
/status - Статус бота и текущая нагрузка
/examples - Примеры запросов
/about - Информация о системе

📝 *Примеры запросов:*

**Табличные данные:**
• "Дай таблицу для H2O при 300-600K с шагом 50 градусов"
• "Свойства CO2 от 298 до 1000K"
• "Термодинамические данные для Fe2O3 при 400-800K"

**Расчёты реакций:**
• "2 H2 + O2 → 2 H2O при 298-1000K"
• "Fe2O3 + 3 C → 2 Fe + 3 CO при 800-1200K"
• "Реагирует ли сероводород с оксидом железа(II) при 500-700°C?"

📄 *Формат результатов:*
• Короткие результаты (>3000 символов) отправляются как сообщения
• Детальные отчёты (>3000 символов) отправляются как TXT файлы
• Все файлы сохраняют Unicode химические формулы

⚙️ *Поддерживаемые формулы:*
• Химические формулы: H2O, CO2, NH3, CH4, Fe2O3
• Реакции: A + B → C + D (до 10 веществ)
• Температуры: 298K, 25°C, диапазоны 298-1000K
• Шаги: 25K, 50K, 100K, 250K

🔍 *Советы:*
• Используйте правильные химические формулы
• Указывайте температурный диапазон для таблиц
• Для больших отчётов проверьте загруженные TXT файлы

_Поддерживается Unicode форматирование: H₂O, CO₂, →, ΔH, ΔG_"""

    def format_status_message(self, status: dict) -> str:
        """Форматирование сообщения о статусе бота."""
        return f"""📊 *Статус ThermoSystem Bot*

🟢 *Состояние:* {'Запущен' if status.get('is_running') else 'Остановлен'}
⏱️ *Время работы:* {status.get('uptime_seconds', 0):.0f} сек
👥 *Активные пользователи:* {status.get('active_users', 0)}
📈 *Всего запросов:* {status.get('total_requests', 0)}
✅ *Успешных:* {status.get('successful_requests', 0)}
❌ *Ошибок:* {status.get('failed_requests', 0)}
⚡ *Среднее время ответа:* {status.get('average_response_time_ms', 0):.0f} мс
💾 *Временных файлов:* {status.get('temp_files_count', 0)}

🗄️ *Система:*
• База данных: {status.get('db_records', 'N/A')} записей
• LLM модель: {status.get('llm_model', 'N/A')}
• Макс. пользователей: {status.get('max_concurrent_users', 'N/A')}

🔧 *Производительность:*
• CPU: {status.get('cpu_percent', 0):.1f}%
• Память: {status.get('memory_mb', 0):.0f} MB"""