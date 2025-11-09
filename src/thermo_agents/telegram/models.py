"""
Модели данных для Telegram бота ThermoSystem.

Основные классы:
- UserSession: Сессия пользователя
- BotCommand: Команда бота
- BotResponse: Ответ бота
- FileResponse: Ответ с файлом
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List


class CommandStatus(Enum):
    """Статус выполнения команды."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class MessageType(Enum):
    """Тип сообщения."""
    COMMAND = "command"
    TEXT_QUERY = "text_query"
    FILE_RESPONSE = "file_response"
    PROGRESS = "progress"
    ERROR = "error"


@dataclass
class UserSession:
    """Сессия пользователя в Telegram боте."""

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    chat_id: int = field(init=False)

    # Метаданные сессии
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    message_count: int = 0

    # Контекст выполнения
    current_command: Optional[str] = None
    current_query: Optional[str] = None
    processing_start: Optional[datetime] = None

    # Временное хранилище для файлов
    temp_files: List[Path] = field(default_factory=list)

    def __post_init__(self):
        """Инициализация post-поля."""
        self.chat_id = self.user_id  # В простом случае chat_id == user_id

    def update_activity(self):
        """Обновить время последней активности."""
        self.last_activity = datetime.now()
        self.message_count += 1

    def start_processing(self, query: str, command: Optional[str] = None):
        """Начать обработку запроса."""
        self.current_query = query
        self.current_command = command
        self.processing_start = datetime.now()
        self.update_activity()

    def finish_processing(self):
        """Завершить обработку запроса."""
        self.current_query = None
        self.current_command = None
        self.processing_start = None
        self.update_activity()

    def add_temp_file(self, file_path: Path):
        """Добавить временный файл в сессию."""
        self.temp_files.append(file_path)

    def get_processing_duration(self) -> Optional[float]:
        """Получить длительность обработки в секундах."""
        if self.processing_start:
            return (datetime.now() - self.processing_start).total_seconds()
        return None

    def is_timeout(self, timeout_seconds: int = 60) -> bool:
        """Проверить, не превышен ли таймаут обработки."""
        if self.processing_start:
            return self.get_processing_duration() > timeout_seconds
        return False

    def is_processing(self) -> bool:
        """Проверить, обрабатывается ли запрос в данный момент."""
        return self.current_query is not None and self.processing_start is not None


@dataclass
class BotCommand:
    """Команда бота."""

    command: str
    description: str
    is_admin_only: bool = False
    examples: List[str] = field(default_factory=list)

    # Метаданные
    usage_count: int = 0
    last_used: Optional[datetime] = None

    def increment_usage(self):
        """Увеличить счетчик использования."""
        self.usage_count += 1
        self.last_used = datetime.now()


@dataclass
class BotResponse:
    """Ответ бота."""

    text: str
    message_type: MessageType = MessageType.TEXT_QUERY
    status: CommandStatus = CommandStatus.SUCCESS

    # Опциональные поля
    user_id: Optional[int] = None
    command: Optional[str] = None
    original_query: Optional[str] = None
    processing_time: Optional[float] = None

    # Форматирование
    use_markdown: bool = True
    parse_mode: str = "Markdown"  # Markdown или HTML

    # Метаданные
    created_at: datetime = field(default_factory=datetime.now)

    def to_telegram_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь для Telegram API."""
        return {
            "text": self.text,
            "parse_mode": self.parse_mode if self.use_markdown else None,
            "disable_web_page_preview": True
        }


@dataclass
class FileResponse:
    """Ответ с файлом."""

    file_path: Path
    caption: str
    file_type: str = "text/plain"  # MIME тип

    # Метаданные
    file_size_bytes: int = field(init=False)
    user_id: Optional[int] = None
    command: Optional[str] = None
    original_query: Optional[str] = None
    processing_time: Optional[float] = None

    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Инициализация полей."""
        if self.file_path.exists():
            self.file_size_bytes = self.file_path.stat().st_size
        else:
            self.file_size_bytes = 0

    def get_file_size_mb(self) -> float:
        """Получить размер файла в МБ."""
        return self.file_size_bytes / (1024 * 1024)

    def to_telegram_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь для Telegram API."""
        return {
            "document": open(self.file_path, "rb"),
            "caption": self.caption,
            "parse_mode": "Markdown"
        }


@dataclass
class ProgressMessage:
    """Сообщение о прогрессе выполнения."""

    stage: str
    progress_percent: float = 0.0
    message: str = ""

    # Дополнительная информация
    estimated_time_remaining: Optional[float] = None
    current_step: Optional[str] = None

    def to_emoji_status(self) -> str:
        """Получить эмодзи статуса."""
        if self.progress_percent < 25:
            return "🔍"
        elif self.progress_percent < 50:
            return "⚗️"
        elif self.progress_percent < 75:
            return "📊"
        elif self.progress_percent < 100:
            return "📈"
        else:
            return "✅"

    def to_text(self) -> str:
        """Сформировать текстовое сообщение."""
        emoji = self.to_emoji_status()
        progress_bar = "█" * int(self.progress_percent / 10) + "░" * (10 - int(self.progress_percent / 10))

        text = f"{emoji} *{self.stage}*\n"
        text += f"`{progress_bar}` {self.progress_percent:.1f}%\n"

        if self.message:
            text += f"\n{self.message}"

        if self.current_step:
            text += f"\n\nТекущий шаг: {self.current_step}"

        if self.estimated_time_remaining:
            text += f"\nОсталось ~{self.estimated_time_remaining:.0f} сек."

        return text


# Предопределенные команды бота
BOT_COMMANDS = {
    "start": BotCommand(
        command="/start",
        description="Приветствие и краткая справка",
        examples=["/start"]
    ),
    "help": BotCommand(
        command="/help",
        description="Подробная справка по использованию",
        examples=["/help", "/help расчеты"]
    ),
    "calculate": BotCommand(
        command="/calculate",
        description="Выполнить термодинамический расчёт",
        examples=[
            "/calculate 2 H2 + O2 → 2 H2O",
            "/calculate свойства H2O при 300-600K"
        ]
    ),
    "status": BotCommand(
        command="/status",
        description="Статус бота и текущая нагрузка",
        examples=["/status"]
    ),
    "examples": BotCommand(
        command="/examples",
        description="Примеры запросов",
        examples=["/examples"]
    ),
    "about": BotCommand(
        command="/about",
        description="Информация о системе",
        examples=["/about"]
    )
}