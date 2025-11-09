"""
Unit тесты форматирования и обработки файлов
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from src.thermo_agents.telegram_bot.formatters.response_formatter import ResponseFormatter
from src.thermo_agents.telegram_bot.formatters.file_handler import FileHandler
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from tests.telegram_bot.fixtures.mock_updates import (
    create_mock_telegram_bot_config, create_mock_update, create_mock_context
)


class TestResponseFormatter:
    """Тесты форматера ответов"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.max_message_length = 4000
        return config

    @pytest.fixture
    def formatter(self, mock_config):
        """Создание форматера для тестов"""
        return ResponseFormatter(mock_config)

    def test_formatter_initialization(self, formatter, mock_config):
        """Тест инициализации форматера"""
        assert formatter.config == mock_config
        assert formatter.max_length == 4000

    def test_format_short_response(self, formatter):
        """Тест форматирования короткого ответа"""
        short_response = "Short thermodynamic response"
        result = formatter.format_thermo_response(short_response, "calculation")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == short_response

    def test_format_long_response_splitting(self, formatter):
        """Тест разделения длинного ответа"""
        # Создание длинного ответа (>4000 символов)
        long_response = "Thermodynamic data line with some information.\n" * 100
        result = formatter.format_thermo_response(long_response, "calculation")

        assert isinstance(result, list)
        assert len(result) >= 2

        # Проверка, что каждая часть не превышает лимит
        for part in result:
            assert len(part) <= formatter.max_length

    def test_enhance_content_reaction_type(self, formatter):
        """Тест улучшения контента для реакции"""
        content = "2 H2 + O2 → 2 H2O\nΔH = -571.66 kJ"
        result = formatter._enhance_content(content, "reaction")

        # Проверка добавления эмодзи для реакции
        assert "🔥" in result
        assert content in result

    def test_enhance_content_compound_type(self, formatter):
        """Тест улучшения контента для соединения"""
        content = "H2O properties\nT = 298.15 K"
        result = formatter._enhance_content(content, "compound")

        # Проверка добавления эмодзи для соединения
        assert "💧" in result or "🧪" in result
        assert content in result

    def test_enhance_content_default_type(self, formatter):
        """Тест улучшения контента для типа по умолчанию"""
        content = "Generic thermodynamic data"
        result = formatter._enhance_content(content, "unknown")

        # Проверка добавления эмодзи по умолчанию
        assert "📊" in result
        assert content in result

    def test_markdown_formatting_enhancement(self, formatter):
        """Тест улучшения Markdown форматирования"""
        content = "ΔH = -571.66 kJ/mol\nT = 298.15 K\nK = 2.1e+83"
        result = formatter._enhance_content(content, "calculation")

        # Проверка жирного форматирования для ключевых параметров
        assert "**ΔH = -571.66**" in result
        assert "**T = 298.15 K**" in result
        assert "**K = 2.1e+83**" in result

    def test_unicode_chemical_formulas_preservation(self, formatter):
        """Тест сохранения Unicode химических формул"""
        content = "H₂O + O₂ → H₂O₂"
        result = formatter.format_thermo_response(content, "calculation")

        assert isinstance(result, list)
        assert "H₂O" in result[0]
        assert "O₂" in result[0]
        assert "H₂O₂" in result[0]
        assert "→" in result[0]

    def test_smart_message_splitting_table_preservation(self, formatter):
        """Тест умного разделения с сохранением таблиц"""
        # Создание таблицы
        table_content = "Thermodynamic Data:\n"
        table_content += "| T (K) | ΔH (kJ) | ΔS (J/K) |\n"
        table_content += "|-------|----------|-----------|\n"
        for i in range(50):
            table_content += f"| {298 + i*10} | {-571.66 - i*0.1} | {-326.7 - i*0.05} |\n"

        result = formatter.format_thermo_response(table_content, "calculation")

        assert len(result) > 1

        # Проверка, что таблицы не разрываются
        for part in result:
            lines = part.split('\n')
            for line in lines:
                if '|' in line and line.strip():
                    # Строка таблицы должна быть полной
                    pipe_count = line.count('|')
                    assert pipe_count >= 2, f"Table line appears incomplete: {line}"

    def test_emoji_structure_addition(self, formatter):
        """Тест добавления эмодзи структуры"""
        content = "ΔH = -571.66 kJ/mol\nThis is a table:\nT (K) | Cp (J/mol·K)"
        result = formatter._enhance_content(content, "calculation")

        # Проверка наличия эмодзи
        assert "🔥" in result or "📊" in result
        lines = result.split('\n')
        assert any(line.startswith('🔥') for line in lines if 'ΔH' in line)

    def test_split_long_message_with_sections(self, formatter):
        """Тест разделения сообщения с секциями"""
        # Создание сообщения с секциями
        content = "Section 1: Basic Data\n" + "Some data here.\n" * 50
        content += "\nSection 2: Advanced Data\n" + "More data here.\n" * 50

        result = formatter._split_long_message(content, "calculation")

        assert len(result) > 1

        # Проверка, что разделение произошло на границах секций
        section_1_found = False
        section_2_found = False

        for part in result:
            if "Section 1" in part:
                section_1_found = True
            if "Section 2" in part:
                section_2_found = True

        assert section_1_found, "Section 1 not found in split parts"
        assert section_2_found, "Section 2 not found in split parts"

    def test_max_length_boundary(self, formatter):
        """Тест граничного значения максимальной длины"""
        # Создание сообщения точно на границе
        boundary_content = "A" * formatter.max_length
        result = formatter.format_thermo_response(boundary_content, "calculation")

        assert len(result) == 1
        assert len(result[0]) <= formatter.max_length

    def test_max_length_exceed_by_one(self, formatter):
        """Тест превышения максимальной длины на 1 символ"""
        # Создание сообщения, превышающее лимит на 1 символ
        over_boundary_content = "A" * (formatter.max_length + 1)
        result = formatter.format_thermo_response(over_boundary_content, "calculation")

        assert len(result) >= 2
        for part in result:
            assert len(part) <= formatter.max_length

    def test_empty_content_handling(self, formatter):
        """Тест обработки пустого контента"""
        result = formatter.format_thermo_response("", "calculation")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "" or "📊" in result[0]

    def test_content_with_special_characters(self, formatter):
        """Тест обработки контента со специальными символами"""
        content = "Special chars: *bold*, _italic_, `code`, [link](url)"
        result = formatter.format_thermo_response(content, "calculation")

        assert isinstance(result, list)
        assert content in result[0]


class TestFileHandler:
    """Тесты файлового хендлера"""

    @pytest.fixture
    def mock_config(self):
        """Mock конфигурации для тестов"""
        config = create_mock_telegram_bot_config()
        config.temp_file_dir = "temp/test_files"
        config.max_file_size_mb = 20
        config.file_cleanup_hours = 24
        return config

    @pytest.fixture
    def temp_dir(self):
        """Временная директория для тестов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def file_handler(self, mock_config, temp_dir):
        """Создание файлового хендлера для тестов"""
        mock_config.temp_file_dir = Path(temp_dir) / "test_files"
        return FileHandler(mock_config)

    def test_file_handler_initialization(self, file_handler, mock_config):
        """Тест инициализации файлового хендлера"""
        assert file_handler.config == mock_config
        assert file_handler.temp_file_dir == mock_config.temp_file_dir
        assert file_handler.max_file_size_bytes == 20 * 1024 * 1024
        assert file_handler.temp_file_dir.exists()

    def test_sanitize_filename_unicode(self, file_handler):
        """Тест очистки имён файлов с Unicode"""
        # Тест с подстрочными индексами и стрелками
        filename = "2H₂ + O₂ → 2H₂O"
        sanitized = file_handler._sanitize_filename(filename)

        # Unicode нормализация должна сохранить символы
        assert "H2" in sanitized or "H₂" in sanitized
        assert "O2" in sanitized or "O₂" in sanitized
        assert "to" in sanitized or "→" in sanitized

    def test_sanitize_filename_special_chars(self, file_handler):
        """Тест очистки имён файлов со специальными символами"""
        filename = "Reaction@#$%^&*()with special chars"
        sanitized = file_handler._sanitize_filename(filename)

        # Проверка отсутствия специальных символов
        assert all(c.isalnum() or c in '_ -' for c in sanitized)
        assert len(sanitized) <= 100

    def test_sanitize_filename_windows_incompatible(self, file_handler):
        """Тест очистки имён файлов с несовместимыми для Windows символами"""
        filename = 'Reaction:Name/With\\Windows:Incompatible*Chars?'
        sanitized = file_handler._sanitize_filename(filename)

        # Проверка замены несовместимых символов
        assert ":" not in sanitized
        assert "/" not in sanitized
        assert "\\" not in sanitized
        assert "*" not in sanitized
        assert "?" not in sanitized

    def test_sanitize_filename_length_limit(self, file_handler):
        """Тест ограничения длины имени файла"""
        long_filename = "A" * 200
        sanitized = file_handler._sanitize_filename(long_filename)

        assert len(sanitized) <= 100

    @pytest.mark.asyncio
    async def test_create_thermo_report_file(self, file_handler):
        """Тест создания файла с термодинамическим отчётом"""
        content = "Thermodynamic Report\nΔH = -571.66 kJ/mol\nT = 298.15 K"
        user_id = 12345
        reaction_info = "2 H2 + O2 → 2 H2O"

        file_path = await file_handler.create_thermo_report_file(
            content, user_id, reaction_info
        )

        # Проверки
        assert Path(file_path).exists()
        assert file_path.startswith(str(file_handler.temp_file_dir))

        # Проверка содержимого файла
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            assert content in file_content
            assert reaction_info in file_content

        # Проверка имени файла
        filename = Path(file_path).name
        assert str(user_id) in filename
        assert any(word in filename.lower() for word in ["h2", "o2", "reaction"])

    @pytest.mark.asyncio
    async def test_create_file_size_limit(self, file_handler):
        """Тест ограничения размера файла"""
        # Создание контента >20MB
        large_content = "A" * (21 * 1024 * 1024)  # 21MB
        user_id = 12345
        reaction_info = "Large reaction"

        with pytest.raises(ValueError, match="exceeds maximum size"):
            await file_handler.create_thermo_report_file(
                large_content, user_id, reaction_info
            )

    @pytest.mark.asyncio
    async def test_create_file_unicode_content(self, file_handler):
        """Тест создания файла с Unicode контентом"""
        content = "Термодинамические свойства H₂O и CO₂\nРеакция: 2 H₂ + O₂ → 2 H₂O"
        user_id = 12345
        reaction_info = "Unicode реакция"

        file_path = await file_handler.create_thermo_report_file(
            content, user_id, reaction_info
        )

        # Проверка сохранения Unicode
        with open(file_path, 'r', encoding='utf-8') as f:
            file_content = f.read()
            assert "H₂O" in file_content
            assert "CO₂" in file_content
            assert "→" in file_content
            assert "Термодинамические" in file_content

    @pytest.mark.asyncio
    async def test_send_file_success(self, file_handler):
        """Тест успешной отправки файла"""
        update = Mock()
        context = Mock()
        content = "Test report content"
        user_id = 12345
        reaction_info = "Test reaction"

        # Mock успешной отправки
        context.bot.send_document = AsyncMock()

        result = await file_handler.send_thermo_file(
            update, context, content, user_id, reaction_info
        )

        assert result is True
        context.bot.send_document.assert_called_once()

        # Проверка аргументов отправки
        call_args = context.bot.send_document.call_args
        assert call_args[1]["chat_id"] == update.effective_chat.id
        assert "caption" in call_args[1]

    @pytest.mark.asyncio
    async def test_send_file_creation_error(self, file_handler):
        """Тест ошибки при создании файла"""
        update = Mock()
        context = Mock()
        content = "Test content"
        user_id = 12345
        reaction_info = "Test reaction"

        # Mock ошибки создания файла
        with patch.object(file_handler, 'create_thermo_report_file',
                         side_effect=Exception("File creation error")):
            result = await file_handler.send_thermo_file(
                update, context, content, user_id, reaction_info
            )

            assert result is False

    @pytest.mark.asyncio
    async def test_send_file_telegram_error(self, file_handler):
        """Тест ошибки отправки в Telegram"""
        update = Mock()
        context = Mock()
        update.message = Mock()
        update.message.reply_text = AsyncMock()
        content = "Test content"
        user_id = 12345
        reaction_info = "Test reaction"

        # Mock ошибки отправки
        context.bot.send_document = AsyncMock(side_effect=Exception("Telegram error"))

        result = await file_handler.send_thermo_file(
            update, context, content, user_id, reaction_info
        )

        assert result is False
        update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_old_files(self, file_handler):
        """Тест очистки старых файлов"""
        # Создание тестовых файлов
        test_files = []
        for i in range(3):
            content = f"Test content {i}"
            user_id = 12345 + i
            reaction_info = f"Test reaction {i}"

            file_path = await file_handler.create_thermo_report_file(
                content, user_id, reaction_info
            )
            test_files.append(Path(file_path))

        # Изменение времени создания для имитации старых файлов
        import time
        old_time = time.time() - (25 * 3600)  # 25 часов назад
        for file_path in test_files[:2]:
            os.utime(file_path, (old_time, old_time))

        # Запуск очистки
        cleaned_count = await file_handler.cleanup_old_files()

        # Проверки
        assert cleaned_count == 2
        assert not test_files[0].exists()
        assert not test_files[1].exists()
        assert test_files[2].exists()

    @pytest.mark.asyncio
    async def test_cleanup_error_handling(self, file_handler):
        """Тест обработки ошибок при очистке"""
        # Mock ошибки при доступе к файлам
        with patch('pathlib.Path.iterdir', side_effect=PermissionError("Access denied")):
            cleaned_count = await file_handler.cleanup_old_files()

            # Должно вернуть 0 при ошибке
            assert cleaned_count == 0

    def test_generate_filename(self, file_handler):
        """Тест генерации имени файла"""
        user_id = 12345
        reaction_info = "2 H2 + O2 → 2 H2O"

        filename = file_handler._generate_filename(user_id, reaction_info)

        # Проверка формата имени файла
        assert str(user_id) in filename
        assert any(word in filename.lower() for word in ["h2", "o2", "reaction"])
        assert filename.endswith('.txt')

    def test_generate_filename_sanitization(self, file_handler):
        """Тест очистки имени файла при генерации"""
        user_id = 12345
        reaction_info = "Reaction@#$%^&*()with special chars"

        filename = file_handler._generate_filename(user_id, reaction_info)

        # Проверка отсутствия специальных символов
        assert all(c.isalnum() or c in '_ -' for c in filename.replace('.txt', ''))

    @pytest.mark.asyncio
    async def test_get_file_info(self, file_handler):
        """Тест получения информации о файле"""
        content = "Test content for file info"
        user_id = 12345
        reaction_info = "Test reaction"

        file_path = await file_handler.create_thermo_report_file(
            content, user_id, reaction_info
        )

        file_info = file_handler._get_file_info(file_path)

        assert file_info["exists"] is True
        assert file_info["size_bytes"] > 0
        assert file_info["size_mb"] < 1  # Должно быть меньше 1MB
        assert file_info["user_id"] == user_id
        assert reaction_info in file_info["filename"]

    def test_get_file_info_nonexistent(self, file_handler):
        """Тест получения информации о несуществующем файле"""
        file_info = file_handler._get_file_info("nonexistent_file.txt")

        assert file_info["exists"] is False
        assert file_info["size_bytes"] == 0
        assert file_info["size_mb"] == 0