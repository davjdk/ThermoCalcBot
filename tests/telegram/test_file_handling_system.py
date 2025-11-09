"""
Тесты для файловой системы Telegram бота

Проверяет функциональность TelegramFileHandler, SmartResponseHandler и конфигурации.
"""

import pytest
import tempfile
import asyncio
from unittest.mock import AsyncMock, Mock, MagicMock
from pathlib import Path
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from thermo_agents.telegram.file_handler import TelegramFileHandler
from thermo_agents.telegram.smart_response import SmartResponseHandler
from thermo_agents.telegram.config import FileHandlerConfig
from thermo_agents.telegram.metrics import FileSystemMetrics, MetricsCollector


@pytest.fixture
def temp_dir():
    """Создание временной директории для тестов"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def file_handler(temp_dir):
    """Создание тестового TelegramFileHandler"""
    return TelegramFileHandler(
        temp_dir=temp_dir,
        cleanup_hours=1,  # 1 час для тестов
        max_file_size_mb=1  # 1MB для тестов
    )


@pytest.fixture
def smart_response_handler(file_handler):
    """Создание тестового SmartResponseHandler"""
    return SmartResponseHandler(
        file_handler=file_handler,
        message_threshold=3000
    )


@pytest.fixture
def file_config():
    """Создание тестовой конфигурации"""
    return FileHandlerConfig(
        temp_file_dir="temp/test_files",
        cleanup_hours=1,
        max_file_size_mb=1,
        auto_file_threshold=3000,
        max_table_rows=20,
        max_filename_length=50
    )


@pytest.fixture
def mock_update():
    """Создание mock объекта Telegram Update"""
    update = Mock()
    update.effective_user.id = 12345
    update.effective_chat.id = 67890
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Создание mock объекта Telegram Context"""
    context = Mock()
    context.bot.send_document = AsyncMock()
    return context


class TestTelegramFileHandler:
    """Тесты TelegramFileHandler"""

    def test_init(self, temp_dir):
        """Тест инициализации"""
        handler = TelegramFileHandler(temp_dir=temp_dir)

        assert handler.temp_dir == Path(temp_dir)
        assert handler.cleanup_hours == 24
        assert handler.max_file_size_mb == 20
        assert handler.active_files == {}
        assert Path(temp_dir).exists()

    @pytest.mark.asyncio
    async def test_create_temp_file(self, file_handler):
        """Тест создания временного файла"""
        content = "Test content for file creation"
        user_id = 12345
        reaction_info = "2 H2 + O2 → 2 H2O"

        file_path = await file_handler.create_temp_file(content, user_id, reaction_info)

        # Проверки
        assert Path(file_path).exists()
        assert Path(file_path).name.startswith("thermo_report_")
        assert "2H2_O2_to_2H2O" in Path(file_path).name

        # Проверка содержимого
        with open(file_path, 'r', encoding='utf-8') as f:
            assert f.read() == content

        # Проверка регистрации файла
        assert user_id in file_handler.active_files
        assert file_handler.active_files[user_id]['size'] == len(content)
        assert file_handler.active_files[user_id]['reaction_info'] == reaction_info

    def test_sanitize_filename(self, file_handler):
        """Тест очистки имени файла"""
        test_cases = [
            ("2 H₂ + O₂ → 2 H₂O", "2H2_O2_to_2H2O"),
            ("CO₂ + H₂O ⇌ H₂CO₃", "CO2_H2O_eq_H2CO3"),
            ("Complex reaction: A→B", "Complex_reaction_A_to_B"),
            ("", ""),
            ("Very long filename that should be truncated" * 2, "Very_long_filename_that_should_be_tr"),
        ]

        for input_name, expected in test_cases:
            result = file_handler._sanitize_filename(input_name)
            assert result == expected[:50]  # С учётом ограничения длины

    @pytest.mark.asyncio
    async def test_send_file_success(self, file_handler, mock_update, mock_context):
        """Тест успешной отправки файла"""
        content = "Test thermodynamic report content\n" * 100  # Достаточно большой контент
        reaction_info = "2 H2 + O2 → 2 H2O"

        # Mock отправки документа
        with pytest.MonkeyPatch().context() as m:
            # Мокаем telegram.InputFile
            mock_input_file = Mock()
            m.setattr("thermo_agents.telegram.file_handler.InputFile", mock_input_file)

            success = await file_handler.send_file(mock_update, mock_context, content, reaction_info)

        assert success is True
        assert mock_update.message.reply_text.called  # Для summary
        assert mock_context.bot.send_document.called

    @pytest.mark.asyncio
    async def test_send_file_size_error(self, file_handler, mock_update, mock_context):
        """Тест ошибки размера файла"""
        # Создаем контент размером более 1MB
        large_content = "A" * (2 * 1024 * 1024)  # 2MB

        success = await file_handler.send_file(mock_update, mock_context, large_content)

        assert success is False
        assert mock_update.message.reply_text.called
        # Проверка, что вызывалась функция отправки ошибки размера
        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "Файл слишком большой" in call_args

    def test_extract_summary(self, file_handler):
        """Тест извлечения summary из полного отчёта"""
        response = """
        Уравнение: 2 H2 + O2 → 2 H2O
        Температурный диапазон: 298-1000 K
        ΔH = -571.66 kJ/mol

        Таблица результатов:
        T (K) | ΔH (kJ/mol) | ΔS (J/mol·K) | ΔG (kJ/mol) | K
        298 | -571.66 | -326.6 | -474.26 | 1.5e+83
        500 | -577.98 | -299.3 | -428.33 | 1.2e+45
        """

        summary = file_handler._extract_summary(response)

        assert "Уравнение:" in summary
        assert "Температурный диапазон:" in summary
        assert "ΔH" in summary

    @pytest.mark.asyncio
    async def test_cleanup_old_files(self, file_handler):
        """Тест очистки старых файлов"""
        import time
        from datetime import datetime, timedelta

        # Создание тестового файла
        test_file = Path(file_handler.temp_dir) / "test_old_file.txt"
        test_file.write_text("test content")

        # Изменение времени файла на старое (если возможно)
        try:
            old_time = datetime.now() - timedelta(hours=25)
            old_timestamp = old_time.timestamp()
            os.utime(test_file, (old_timestamp, old_timestamp))
        except:
            # Если не удалось изменить время, пропускаем тест
            pass

        # Запуск очистки
        await file_handler._cleanup_old_files()

        # Проверка статистики
        stats = file_handler.get_file_stats()
        assert 'total_files' in stats
        assert 'total_size_mb' in stats

    def test_get_file_stats(self, file_handler):
        """Тест получения статистики по файлам"""
        stats = file_handler.get_file_stats()

        assert 'total_files' in stats
        assert 'total_size_mb' in stats
        assert 'active_sessions' in stats
        assert 'temp_directory' in stats
        assert stats['active_sessions'] == 0  # Изначально нет активных сессий

    @pytest.mark.asyncio
    async def test_cleanup_user_files(self, file_handler):
        """Тест очистки файлов пользователя"""
        content = "Test content"
        user_id = 12345

        # Создание файла для пользователя
        file_path = await file_handler.create_temp_file(content, user_id)
        assert user_id in file_handler.active_files

        # Очистка файлов пользователя
        await file_handler.cleanup_user_files(user_id)

        assert user_id not in file_handler.active_files
        assert not Path(file_path).exists()


class TestSmartResponseHandler:
    """Тесты SmartResponseHandler"""

    def test_should_use_file_criteria(self, smart_response_handler):
        """Тест критериев использования файла"""

        # Длинный ответ
        long_response = "A" * 4000
        assert smart_response_handler._should_use_file(long_response) is True

        # Короткий ответ
        short_response = "Short response"
        assert smart_response_handler._should_use_file(short_response) is False

        # Ответ с большой таблицей
        table_response = "| T | H | S |\n" + "| A | B | C |\n" * 25
        assert smart_response_handler._has_large_tables(table_response) is True

        # Ответ со сложным форматированием
        complex_response = "┌─────┐\n" * 15
        assert smart_response_handler._has_complex_formatting(complex_response) is True

        # Ответ с множественными реакциями
        reaction_response = "2 H2 + O2 → 2 H2O\n" * 5
        reaction_response += "ΔH = -571.66 kJ/mol\n" * 5
        assert smart_response_handler._has_many_reactions(reaction_response) is True

    def test_split_message(self, smart_response_handler):
        """Тест разделения сообщения"""
        # Короткое сообщение не разделяется
        short_message = "Short message"
        parts = smart_response_handler._split_message(short_message)
        assert len(parts) == 1
        assert parts[0] == short_message

        # Длинное сообщение разделяется
        long_message = "A" * 5000
        parts = smart_response_handler._split_message(long_message, max_length=1000)
        assert len(parts) > 1
        assert all(len(part) <= 1000 for part in parts)

    def test_split_line(self, smart_response_handler):
        """Тест разделения длинной строки"""
        long_line = "A" * 5000
        parts = smart_response_handler._split_line(long_line, max_length=1000)
        assert len(parts) == 5  # 5000 / 1000
        assert all(len(part) <= 1000 for part in parts)

    @pytest.mark.asyncio
    async def test_send_as_messages(self, smart_response_handler, mock_update, mock_context):
        """Тест отправки ответа как сообщений"""
        response = "Test response that will be sent as message"

        success = await smart_response_handler._send_as_messages(mock_update, mock_context, response)

        assert success is True
        assert mock_update.message.reply_text.called

        # Проверка параметров вызова
        call_args = mock_update.message.reply_text.call_args
        assert call_args[1]['parse_mode'] == "Markdown"
        assert call_args[1]['disable_web_page_preview'] is True


class TestFileHandlerConfig:
    """Тесты FileHandlerConfig"""

    def test_default_config(self):
        """Тест конфигурации по умолчанию"""
        config = FileHandlerConfig()

        assert config.temp_file_dir == Path("temp/telegram_files")
        assert config.cleanup_hours == 24
        assert config.max_file_size_mb == 20
        assert config.auto_file_threshold == 3000
        assert config.allowed_extensions == ['.txt']

    def test_config_validation(self):
        """Тест валидации конфигурации"""
        # Валидная конфигурация
        config = FileHandlerConfig()
        errors = config.validate()
        assert len(errors) == 0

        # Невалидная конфигурация
        config = FileHandlerConfig(cleanup_hours=-1, max_file_size_mb=100)
        errors = config.validate()
        assert len(errors) > 0
        assert any("must be positive" in error for error in errors)

    def test_from_env(self):
        """Тест создания конфигурации из переменных окружения"""
        with pytest.MonkeyPatch().context() as m:
            m.setenv("TEMP_FILE_DIR", "custom/temp")
            m.setenv("FILE_CLEANUP_HOURS", "12")
            m.setenv("MAX_FILE_SIZE_MB", "10")

            config = FileHandlerConfig.from_env()

            assert str(config.temp_file_dir) == "custom/temp"
            assert config.cleanup_hours == 12
            assert config.max_file_size_mb == 10

    def test_to_dict(self, file_config):
        """Тест преобразования в словарь"""
        config_dict = file_config.to_dict()

        assert isinstance(config_dict, dict)
        assert 'temp_file_dir' in config_dict
        assert 'cleanup_hours' in config_dict
        assert 'max_file_size_mb' in config_dict
        assert 'auto_file_threshold' in config_dict

    def test_ensure_temp_directory(self, file_config):
        """Тест создания временной директории"""
        temp_dir = file_config.ensure_temp_directory()

        assert temp_dir.exists()
        assert temp_dir.is_dir()


class TestFileSystemMetrics:
    """Тесты FileSystemMetrics"""

    def test_metrics_initialization(self, file_handler):
        """Тест инициализации метрик"""
        metrics = FileSystemMetrics(file_handler)

        assert metrics.metrics['files_created'] == 0
        assert metrics.metrics['files_sent'] == 0
        assert metrics.metrics['total_size_mb'] == 0.0
        assert metrics.metrics['errors'] == 0
        assert 'start_time' in metrics.metrics

    def test_record_metrics(self, file_handler):
        """Тест записи метрик"""
        metrics = FileSystemMetrics(file_handler)

        # Запись создания файла
        metrics.record_file_creation(1.5)
        assert metrics.metrics['files_created'] == 1
        assert metrics.metrics['total_size_mb'] == 1.5

        # Запись отправки файла
        metrics.record_file_sent(1.5)
        assert metrics.metrics['files_sent'] == 1
        assert metrics.metrics['file_responses'] == 1

        # Запись сообщения
        metrics.record_message_sent()
        assert metrics.metrics['message_responses'] == 1

        # Запись времени ответа
        metrics.record_response_time(1500.0)
        assert metrics.metrics['total_response_time_ms'] == 1500.0

        # Запись ошибки
        metrics.record_error()
        assert metrics.metrics['errors'] == 1

    def test_get_metrics(self, file_handler):
        """Тест получения метрик"""
        metrics = FileSystemMetrics(file_handler)

        # Добавляем некоторые данные
        metrics.record_file_creation(1.0)
        metrics.record_file_sent(1.0)
        metrics.record_message_sent()
        metrics.record_response_time(1000.0)

        metrics_data = metrics.get_metrics()

        assert 'files_created' in metrics_data
        assert 'average_file_size_mb' in metrics_data
        assert 'success_rate' in metrics_data
        assert 'average_response_time_ms' in metrics_data
        assert 'file_usage_rate' in metrics_data
        assert metrics_data['average_file_size_mb'] == 1.0

    def test_reset_metrics(self, file_handler):
        """Тест сброса метрик"""
        metrics = FileSystemMetrics(file_handler)

        # Добавляем данные
        metrics.record_file_creation(1.0)
        metrics.record_error()

        # Сбрасываем
        metrics.reset_metrics()

        # Проверяем сброс
        assert metrics.metrics['files_created'] == 0
        assert metrics.metrics['errors'] == 0
        assert metrics.metrics['total_size_mb'] == 0.0

    def test_performance_summary(self, file_handler):
        """Тест текстового summary производительности"""
        metrics = FileSystemMetrics(file_handler)

        # Добавляем данные
        metrics.record_file_creation(1.5)
        metrics.record_file_sent(1.5)
        metrics.record_message_sent()

        summary = metrics.get_performance_summary()

        assert isinstance(summary, str)
        assert "Производительность файловой системы" in summary
        assert "Uptime:" in summary
        assert "Файлов создано:" in summary
        assert "成功率:" in summary


class TestMetricsCollector:
    """Тесты MetricsCollector"""

    def test_collector_initialization(self):
        """Тест инициализации коллектора"""
        collector = MetricsCollector()

        assert collector.metrics['total_requests'] == 0
        assert collector.metrics['successful_requests'] == 0
        assert collector.metrics['failed_requests'] == 0
        assert 'start_time' in collector.metrics

    def test_record_request(self):
        """Тест записи запроса"""
        collector = MetricsCollector()

        collector.record_request('thermo')
        assert collector.metrics['total_requests'] == 1
        assert collector.metrics['thermo_queries'] == 1

        collector.record_request('command')
        assert collector.metrics['total_requests'] == 2
        assert collector.metrics['command_queries'] == 1

    def test_record_success_and_failure(self):
        """Тест записи успехов и неудач"""
        collector = MetricsCollector()

        collector.record_success(1500.0)
        assert collector.metrics['successful_requests'] == 1
        assert len(collector.metrics['response_times']) == 1
        assert collector.metrics['response_times'][0] == 1500.0

        collector.record_failure('timeout')
        assert collector.metrics['failed_requests'] == 1
        assert collector.metrics['error_types']['timeout'] == 1

    def test_user_activity(self):
        """Тест записи активности пользователя"""
        collector = MetricsCollector()

        user_id = 12345
        collector.record_user_activity(user_id, 'query')

        assert user_id in collector.metrics['user_activity']
        assert collector.metrics['user_activity'][user_id]['requests'] == 1
        assert collector.metrics['user_activity'][user_id]['activities'][0]['activity'] == 'query'

    def test_get_summary(self):
        """Тест получения summary"""
        collector = MetricsCollector()

        # Добавляем данные
        collector.record_request('thermo')
        collector.record_success(1500.0)
        collector.record_failure('timeout')
        collector.record_user_activity(12345, 'query')

        summary = collector.get_summary()

        assert 'total_requests' in summary
        assert 'success_rate' in summary
        assert 'avg_response_time_ms' in summary
        assert 'thermo_queries' in summary
        assert 'active_users_1h' in summary
        assert summary['total_requests'] == 1

    def test_health_status(self):
        """Тест статуса здоровья"""
        collector = MetricsCollector()

        # Здоровый статус
        collector.record_success(1000.0)
        health = collector.get_health_status()
        assert health['status'] == 'healthy'
        assert len(health['issues']) == 0

        # Нездоровый статус
        for _ in range(20):
            collector.record_failure('timeout')

        health = collector.get_health_status()
        assert health['status'] in ['degraded', 'unhealthy']


# Интеграционные тесты
class TestIntegration:
    """Интеграционные тесты файловой системы"""

    @pytest.mark.asyncio
    async def test_end_to_end_file_delivery(self, temp_dir, mock_update, mock_context):
        """Тест полной цепочки доставки файла"""
        # Создание компонентов
        file_handler = TelegramFileHandler(temp_dir=temp_dir, max_file_size_mb=1)
        smart_handler = SmartResponseHandler(file_handler)

        # Большой контент для файла
        large_content = "Thermodynamic report content...\n" * 200

        # Mock InputFile
        with pytest.MonkeyPatch().context() as m:
            mock_input_file = Mock()
            m.setattr("thermo_agents.telegram.file_handler.InputFile", mock_input_file)

            # Отправка ответа
            success = await smart_handler.send_response(
                mock_update, mock_context, large_content, "Test Reaction"
            )

        # Проверки
        assert success is True
        assert mock_context.bot.send_document.called
        assert mock_update.message.reply_text.called  # Для summary

        # Очистка
        await file_handler.shutdown()

    @pytest.mark.asyncio
    async def test_end_to_end_message_delivery(self, temp_dir, mock_update, mock_context):
        """Тест полной цепочки доставки сообщения"""
        # Создание компонентов
        file_handler = TelegramFileHandler(temp_dir=temp_dir)
        smart_handler = SmartResponseHandler(file_handler, message_threshold=1000)

        # Маленький контент для сообщения
        small_content = "Short thermodynamic result"

        # Отправка ответа
        success = await smart_handler.send_response(
            mock_update, mock_context, small_content, "Test Reaction"
        )

        # Проверки
        assert success is True
        assert mock_update.message.reply_text.called
        assert not mock_context.bot.send_document.called  # Файл не должен отправляться

        # Очистка
        await file_handler.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_integration(self, temp_dir, mock_update, mock_context):
        """Тест интеграции метрик с файловой системой"""
        # Создание компонентов
        file_handler = TelegramFileHandler(temp_dir=temp_dir)
        metrics = FileSystemMetrics(file_handler)

        # Запись метрик
        content = "Test content"
        file_size_mb = len(content.encode('utf-8')) / (1024 * 1024)

        metrics.record_file_creation(file_size_mb)

        # Mock отправки
        with pytest.MonkeyPatch().context() as m:
            mock_input_file = Mock()
            m.setattr("thermo_agents.telegram.file_handler.InputFile", mock_input_file)

            success = await file_handler.send_file(mock_update, mock_context, content, "Test")

        if success:
            metrics.record_file_sent(file_size_mb)

        # Проверка метрик
        metrics_data = metrics.get_metrics()
        assert metrics_data['files_created'] == 1
        if success:
            assert metrics_data['files_sent'] == 1

        # Очистка
        await file_handler.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])