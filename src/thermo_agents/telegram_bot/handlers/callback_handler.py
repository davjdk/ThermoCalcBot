"""
Обработчик callback запросов для inline кнопок Telegram бота.

Поддерживает интерактивные элементы:
- Переключение между форматами вывода
- Управление температурными диапазонами
- Повторные расчёты с изменёнными параметрами
- Получение детальной информации
"""

import asyncio
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..config import TelegramBotConfig, BotStatus
from ..formatters.response_formatter import ResponseFormatter
from ..utils.thermo_integration import ThermoIntegration


class CallbackHandler:
    """Обработчик callback запросов от inline кнопок."""

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

        # История запросов для callback обработки
        self.user_query_history: Dict[int, Dict[str, Any]] = {}

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Основной обработчик callback запросов."""
        if not update.callback_query:
            return

        callback_query = update.callback_query
        user_id = update.effective_user.id

        try:
            # Ответ на callback для остановки индикатора загрузки
            await callback_query.answer()

            # Парсинг callback данных
            callback_data = callback_query.data
            if not callback_data:
                return

            # Обработка разных типов callback
            if callback_data.startswith("calc_"):
                await self._handle_calculation_callback(callback_query, user_id)
            elif callback_data.startswith("format_"):
                await self._handle_format_callback(callback_query, user_id)
            elif callback_data.startswith("range_"):
                await self._handle_range_callback(callback_query, user_id)
            elif callback_data.startswith("info_"):
                await self._handle_info_callback(callback_query, user_id)
            elif callback_data.startswith("repeat_"):
                await self._handle_repeat_callback(callback_query, user_id)
            else:
                await self._handle_unknown_callback(callback_query)

        except Exception as e:
            print(f"Ошибка обработки callback: {e}")
            await self._send_callback_error(callback_query)

    async def _handle_calculation_callback(self, callback_query, user_id: int) -> None:
        """Обработка callback для быстрых расчётов."""
        data = callback_query.data

        # Извлечение типа расчёта
        calc_type = data.replace("calc_", "")

        quick_queries = {
            "water": "H2O свойства при 298-600K",
            "combustion": "2 H2 + O2 → 2 H2O при 298-1000K",
            "carbon": "C + O2 → CO2 при 298-800K",
            "ammonia": "N2 + 3 H2 → 2 NH3 при 400-700K"
        }

        if calc_type not in quick_queries:
            await self._send_callback_error(callback_query, "Неизвестный тип расчёта")
            return

        # Отправка сообщения о обработке
        processing_msg = await callback_query.message.reply_text(
            "🔄 *Выполняю быстрый расчёт...*",
            parse_mode="Markdown"
        )

        try:
            # Выполнение расчёта
            query = quick_queries[calc_type]
            result = await self.thermo_integration.process_query(query, user_id)

            # Удаление сообщения об обработке
            await processing_msg.delete()

            if result.success:
                # Сохранение в историю
                self._save_query_to_history(user_id, query, result.content, result.query_type)

                # Форматирование и отправка результата
                await self._send_calculation_result(
                    callback_query.message,
                    result.content,
                    result.query_type
                )
            else:
                await callback_query.message.reply_text(
                    f"❌ *Ошибка расчёта:* {result.error}",
                    parse_mode="Markdown"
                )

        except Exception as e:
            await processing_msg.delete()
            await callback_query.message.reply_text(
                f"❌ *Ошибка:* {str(e)}",
                parse_mode="Markdown"
            )

    async def _handle_format_callback(self, callback_query, user_id: int) -> None:
        """Обработка callback для изменения формата вывода."""
        data = callback_query.data
        format_type = data.replace("format_", "")

        # Получение последнего запроса из истории
        last_query = self.user_query_history.get(user_id)
        if not last_query:
            await callback_query.message.reply_text(
                "❌ Нет предыдущих запросов для изменения формата",
                parse_mode="Markdown"
            )
            return

        # Изменение формата и повторная отправка
        original_content = last_query["content"]
        query_type = last_query["query_type"]

        if format_type == "compact":
            # Компактный формат
            formatted_content = self._format_compact(original_content, query_type)
        elif format_type == "detailed":
            # Детальный формат
            formatted_content = self._format_detailed(original_content, query_type)
        else:
            await self._send_callback_error(callback_query, "Неизвестный формат")
            return

        # Отправка в новом формате
        await callback_query.message.reply_text(
            f"📄 *Результат в формате {format_type}:*\n\n{formatted_content}",
            parse_mode="Markdown"
        )

    async def _handle_range_callback(self, callback_query, user_id: int) -> None:
        """Обработка callback для изменения температурного диапазона."""
        data = callback_query.data
        range_type = data.replace("range_", "")

        # Получение последнего запроса
        last_query = self.user_query_history.get(user_id)
        if not last_query:
            await callback_query.message.reply_text(
                "❌ Нет предыдущих запросов для изменения диапазона",
                parse_mode="Markdown"
            )
            return

        # Изменение температурного диапазона
        original_query = last_query["query"]

        range_modifications = {
            "expand": " расширить диапазон до 2000K",
            "shrink": " сузить диапазон до ±100K",
            "low": " для низких температур 100-400K",
            "high": " для высоких температур 1000-2000K"
        }

        if range_type not in range_modifications:
            await self._send_callback_error(callback_query, "Неизвестный диапазон")
            return

        # Модификация запроса
        modified_query = original_query + range_modifications[range_type]

        # Отправка сообщения об обработке
        processing_msg = await callback_query.message.reply_text(
            "🔄 *Пересчитываю с новым диапазоном...*",
            parse_mode="Markdown"
        )

        try:
            # Выполнение нового расчёта
            result = await self.thermo_integration.process_query(modified_query, user_id)

            await processing_msg.delete()

            if result.success:
                # Обновление истории
                self._save_query_to_history(user_id, modified_query, result.content, result.query_type)

                # Отправка нового результата
                await self._send_calculation_result(
                    callback_query.message,
                    result.content,
                    result.query_type
                )
            else:
                await callback_query.message.reply_text(
                    f"❌ *Ошибка пересчёта:* {result.error}",
                    parse_mode="Markdown"
                )

        except Exception as e:
            await processing_msg.delete()
            await callback_query.message.reply_text(
                f"❌ *Ошибка:* {str(e)}",
                parse_mode="Markdown"
            )

    async def _handle_info_callback(self, callback_query, user_id: int) -> None:
        """Обработка callback для получения дополнительной информации."""
        data = callback_query.data
        info_type = data.replace("info_", "")

        info_messages = {
            "thermo": """🔬 *Информация о ThermoSystem*

• База данных: 316K термодинамических записей
• Поддерживаемые вещества: Простые и сложные химические соединения
• Точность: Основана на экспериментальных данных
• Расчёты: ΔH, ΔS, ΔG, константа равновесия K

📊 *Форматы результатов:*
• Таблицы: T, Cp, H, S, G свойства
• Реакции: термодинамический анализ
• Файлы: детальные отчёты в TXT формате""",

            "usage": """📝 *Советы по использованию:*

✅ *Правильные формулы:*
H2O, CO2, NH3, Fe2O3, Al2O3

✅ *Температурные диапазоны:*
298-1000K, 25-500°C

✅ *Реакции:*
2 H2 + O2 → 2 H2O

❌ *Избегать:*
Сокращений, опечаток в формулах
Слишком широких диапазонов
Сложных органических молекул"""
        }

        if info_type not in info_messages:
            await self._send_callback_error(callback_query, "Неизвестный тип информации")
            return

        await callback_query.message.reply_text(
            info_messages[info_type],
            parse_mode="Markdown"
        )

    async def _handle_repeat_callback(self, callback_query, user_id: int) -> None:
        """Обработка callback для повторения последнего запроса."""
        last_query = self.user_query_history.get(user_id)
        if not last_query:
            await callback_query.message.reply_text(
                "❌ Нет предыдущих запросов для повтора",
                parse_mode="Markdown"
            )
            return

        # Отправка сообщения о повторении
        processing_msg = await callback_query.message.reply_text(
            "🔄 *Повторяю последний запрос...*",
            parse_mode="Markdown"
        )

        try:
            # Повторное выполнение запроса
            original_query = last_query["query"]
            result = await self.thermo_integration.process_query(original_query, user_id)

            await processing_msg.delete()

            if result.success:
                await self._send_calculation_result(
                    callback_query.message,
                    result.content,
                    result.query_type
                )
            else:
                await callback_query.message.reply_text(
                    f"❌ *Ошибка повтора:* {result.error}",
                    parse_mode="Markdown"
                )

        except Exception as e:
            await processing_msg.delete()
            await callback_query.message.reply_text(
                f"❌ *Ошибка:* {str(e)}",
                parse_mode="Markdown"
            )

    async def _handle_unknown_callback(self, callback_query) -> None:
        """Обработка неизвестных callback запросов."""
        await callback_query.message.reply_text(
            "❌ Неизвестная команда. Пожалуйста, используйте /help",
            parse_mode="Markdown"
        )

    async def _send_callback_error(self, callback_query, error_message: str = None) -> None:
        """Отправка ошибки при обработке callback."""
        try:
            error_text = error_message or "Произошла ошибка при обработке запроса"
            await callback_query.message.reply_text(
                f"❌ *Ошибка:* {error_text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass  # Игнорируем ошибки при отправке сообщения об ошибке

    def _save_query_to_history(self, user_id: int, query: str, content: str, query_type: str) -> None:
        """Сохранение запроса в историю пользователя."""
        self.user_query_history[user_id] = {
            "query": query,
            "content": content,
            "query_type": query_type,
            "timestamp": asyncio.get_event_loop().time()
        }

        # Ограничение размера истории
        if len(self.user_query_history) > 100:
            oldest_user = min(self.user_query_history.keys(),
                            key=lambda uid: self.user_query_history[uid]["timestamp"])
            del self.user_query_history[oldest_user]

    async def _send_calculation_result(self, message, content: str, query_type: str) -> None:
        """Отправка результата расчёта с интерактивными кнопками."""
        # Форматирование контента
        formatted_messages = self.response_formatter.format_thermo_response(content, query_type)

        # Создание inline кнопок
        keyboard = self._create_interaction_keyboard(query_type)
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        # Отправка сообщений
        for i, msg_text in enumerate(formatted_messages):
            if i > 0:
                await asyncio.sleep(0.5)

            # Кнопки только для последнего сообщения
            current_markup = reply_markup if i == len(formatted_messages) - 1 else None

            await message.reply_text(
                msg_text,
                parse_mode="Markdown",
                reply_markup=current_markup,
                disable_web_page_preview=True
            )

    def _create_interaction_keyboard(self, query_type: str) -> list:
        """Создание inline клавиатуры для взаимодействия."""
        keyboard = []

        # Кнопки быстрого доступа
        quick_calc_row = [
            InlineKeyboardButton("💧 H₂O", callback_data="calc_water"),
            InlineKeyboardButton("🔥 Сгорание", callback_data="calc_combustion"),
            InlineKeyboardButton("💨 CO₂", callback_data="calc_carbon")
        ]
        keyboard.append(quick_calc_row)

        # Кнопки форматирования
        format_row = [
            InlineKeyboardButton("📄 Компактно", callback_data="format_compact"),
            InlineKeyboardButton("📊 Детально", callback_data="format_detailed")
        ]
        keyboard.append(format_row)

        # Кнопки диапазонов
        if query_type in ["reaction", "compound_data"]:
            range_row = [
                InlineKeyboardButton("🌡️ Расширить", callback_data="range_expand"),
                InlineKeyboardButton("🔄 Повторить", callback_data="repeat_last")
            ]
            keyboard.append(range_row)

        # Кнопки информации
        info_row = [
            InlineKeyboardButton("ℹ️ ThermoSystem", callback_data="info_thermo"),
            InlineKeyboardButton("📝 Справка", callback_data="info_usage")
        ]
        keyboard.append(info_row)

        return keyboard

    def _format_compact(self, content: str, query_type: str) -> str:
        """Форматирование в компактном виде."""
        lines = content.split('\n')
        compact_lines = []

        # Сохраняем только ключевые строки
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Ключевые маркеры
            if any(keyword in line.lower() for keyword in [
                "уравнение:", "реакция:", "результаты:", "δh", "δs", "δg",
                "вывод:", "температура"
            ]):
                compact_lines.append(line)
            elif line.startswith('|') or '→' in line or '->' in line:
                compact_lines.append(line)

        return '\n'.join(compact_lines[:20])  # Максимум 20 строк

    def _format_detailed(self, content: str, query_type: str) -> str:
        """Форматирование в детальном виде."""
        # Добавляем дополнительную информацию
        detailed_content = f"""
📊 *Детальный формат результатов*

{content}

---
📈 *Дополнительная информация:*
• Расчёты выполнены с использованием формул Шомейта
• Точность зависит от качества исходных данных
• Все свойства приведены для стандартного состояния
• Для анализа фазовых переходов используйте расширенные диапазоны температур
        """

        return detailed_content.strip()

    def get_user_history(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение истории запросов пользователя."""
        return self.user_query_history.get(user_id)

    def clear_user_history(self, user_id: int) -> bool:
        """Очистка истории пользователя."""
        if user_id in self.user_query_history:
            del self.user_query_history[user_id]
            return True
        return False