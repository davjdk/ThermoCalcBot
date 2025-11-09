"""
Тестовые фикстуры и моки для Telegram Bot
"""

from unittest.mock import Mock, AsyncMock
from typing import Optional, Dict, Any


def create_mock_user(user_id: int = 12345, username: str = "testuser") -> Mock:
    """Создание mock пользователя Telegram"""
    user = Mock()
    user.id = user_id
    user.username = username
    user.first_name = "Test"
    user.last_name = "User"
    user.is_bot = False
    return user


def create_mock_chat(chat_id: int = 12345, chat_type: str = "private") -> Mock:
    """Создание mock чата Telegram"""
    chat = Mock()
    chat.id = chat_id
    chat.type = chat_type
    chat.title = "Test Chat" if chat_type != "private" else None
    return chat


def create_mock_message(
    text: str,
    user_id: int = 12345,
    chat_id: int = 12345,
    message_id: int = 1
) -> Mock:
    """Создание mock сообщения Telegram"""
    message = Mock()
    message.message_id = message_id
    message.text = text
    message.from_user = create_mock_user(user_id)
    message.chat = create_mock_chat(chat_id)
    message.reply_text = AsyncMock()
    message.reply_photo = AsyncMock()
    message.reply_document = AsyncMock()
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    return message


def create_mock_update(message_text: str, user_id: int = 12345, chat_id: int = 12345) -> Mock:
    """Создание mock обновления Telegram"""
    update = Mock()
    update.update_id = 1
    update.message = create_mock_message(message_text, user_id, chat_id)
    update.effective_user = update.message.from_user
    update.effective_chat = update.message.chat
    update.effective_message = update.message
    return update


def create_mock_command_update(command: str, user_id: int = 12345, chat_id: int = 12345) -> Mock:
    """Создание mock обновления с командой"""
    entities = [
        Mock(type="bot_command", offset=0, length=len(command))
    ]
    update = create_mock_update(command, user_id, chat_id)
    update.message.entities = entities
    return update


def create_mock_context() -> Mock:
    """Создание mock контекста Telegram"""
    context = Mock()
    context.bot = Mock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.send_document = AsyncMock()
    context.bot.send_photo = AsyncMock()
    context.bot.get_chat = AsyncMock()
    context.args = []
    context.job = None
    return context


def create_mock_callback_query(
    data: str,
    user_id: int = 12345,
    chat_id: int = 12345
) -> Mock:
    """Создание mock callback query"""
    callback_query = Mock()
    callback_query.id = "test_callback_123"
    callback_query.data = data
    callback_query.from_user = create_mock_user(user_id)
    callback_query.message = create_mock_message("callback", user_id, chat_id)
    callback_query.answer = AsyncMock()
    callback_query.edit_message_text = AsyncMock()

    update = Mock()
    update.update_id = 1
    update.callback_query = callback_query
    update.effective_user = callback_query.from_user
    update.effective_chat = callback_query.message.chat

    return update


def create_mock_orchestrator(response_text: str = "Test thermodynamic response") -> Mock:
    """Создание mock оркестратора ThermoSystem"""
    orchestrator = Mock()
    orchestrator.process_query = AsyncMock(return_value=response_text)
    orchestrator.thermodynamic_agent = Mock()
    orchestrator.thermodynamic_agent.test_connection = AsyncMock(return_value=True)
    return orchestrator


def create_mock_session_manager() -> Mock:
    """Создание mock менеджера сессий"""
    session_manager = Mock()
    session_manager.get_or_create_session = Mock(return_value=Mock())
    session_manager.get_active_session_count = Mock(return_value=5)
    session_manager.get_session_stats = Mock(return_value={
        "total_requests": 100,
        "avg_session_duration": 45.2
    })
    session_manager.close_all_sessions = AsyncMock()
    session_manager.cleanup_expired_sessions = AsyncMock()
    return session_manager


def create_mock_telegram_bot_config() -> Mock:
    """Создание mock конфигурации Telegram бота"""
    config = Mock()
    config.bot_token = "test_token_12345"
    config.bot_username = "TestBot"
    config.mode = "polling"
    config.max_concurrent_users = 10
    config.request_timeout_seconds = 60
    config.enable_file_downloads = True
    config.enable_monitoring = True
    config.log_level = "INFO"
    return config


# Тестовые данные для термодинамических расчётов
SAMPLE_THERMO_RESPONSES = {
    "h2o_properties": """Термодинамические свойства H2O (вода):

Температура: 298.15 K (25°C)
Фаза: жидкая

**ΔH° = -285.83 кДж/моль**
**S° = 69.91 Дж/(моль·К)**
**Cp = 75.29 Дж/(моль·К)**

Температурный диапазон: 273.15 - 373.15 K
Точка плавления: 273.15 K
Точка кипения: 373.15 K
""",

    "co2_properties": """Термодинамические свойства CO2 (углекислый газ):

Температура: 298.15 K (25°C)
Фаза: газ

**ΔH° = -393.51 кДж/моль**
**S° = 213.74 Дж/(моль·К)**
**Cp = 44.01 Дж/(моль·К)**

Температурный диапазон: 194.65 - 304.13 K
Критическая точка: 304.13 K
""",

    "reaction_h2_o2": """Реакция: 2 H2 + O2 → 2 H2O

**Термодинамические параметры при 298.15 K:**
ΔH° = -571.66 кДж
ΔS° = -326.7 Дж/К
ΔG° = -474.24 кДж

**Константа равновесия:**
K = 2.1e+83

**Таблица температур:**

| T (K) | ΔH (кДж) | ΔS (Дж/К) | ΔG (кДж) | K |
|-------|----------|-----------|----------|---|
| 298   | -571.66  | -326.7    | -474.24  | 2.1e+83 |
| 400   | -575.43  | -311.2    | -450.95  | 4.3e+58 |
| 600   | -583.02  | -289.1    | -410.56  | 2.1e+35 |
| 800   | -590.61  | -272.1    | -372.93  | 3.7e+19 |
| 1000  | -598.20  | -258.1    | -340.10  | 1.2e+17 |

Экзотермическая реакция (выделяет тепло)
"""
}


# Примеры обновлений для разных сценариев
MOCK_UPDATES = {
    "start": create_mock_command_update("/start"),
    "help": create_mock_command_update("/help"),
    "calculate": create_mock_command_update("/calculate H2O properties 300K"),
    "status": create_mock_command_update("/status"),
    "text_h2o": create_mock_update("H2O properties at 300K"),
    "text_reaction": create_mock_update("2 H2 + O2 → 2 H2O"),
    "text_invalid": create_mock_update("InvalidCompoundThatDoesNotExist properties"),
    "callback_help": create_mock_callback_query("help"),
    "callback_settings": create_mock_callback_query("settings"),
}