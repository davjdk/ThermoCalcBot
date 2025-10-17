"""
Тесты для унифицированного логгера.

Проверяют функциональность UnifiedLogger, совместимость с SessionLogger
и правильность работы всех уровней логирования.
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from thermo_agents.logging.unified_logger import (
    UnifiedLogger,
    LogLevel,
    LogEntry,
    OperationContext,
    OperationTimer
)


class TestUnifiedLogger:
    """Тесты для UnifiedLogger."""

    def test_logger_initialization(self):
        """Тест инициализации логгера."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_session",
                logs_dir=temp_dir,
                enable_console_logging=False,
                enable_file_logging=True
            )

            assert logger.session_id == "test_session"
            assert logger.logs_dir == Path(temp_dir)
            assert logger.enable_file_logging is True
            assert logger.enable_console_logging is False

            # Проверяем создание файлов
            assert logger.log_file.exists()
            assert logger.structured_log_file.exists()

            logger.close()

    def test_basic_logging(self):
        """Тест базового логирования."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_basic",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            # Тестируем разные уровни логирования
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message", ValueError("Test error"))

            logger.close()

            # Проверяем структурированные логи
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                logs = [json.loads(line) for line in f]

            assert len(logs) == 4
            assert logs[0]["level"] == "DEBUG"
            assert logs[1]["level"] == "INFO"
            assert logs[2]["level"] == "WARNING"
            assert logs[3]["level"] == "ERROR"
            assert logs[3]["metadata"]["error"] == "Test error"

    def test_operation_tracking(self):
        """Тест отслеживания операций."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_ops",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            # Начинаем операцию
            operation_id = logger.start_operation(
                operation_type="test_operation",
                correlation_id="test_corr_id"
            )

            assert operation_id is not None
            assert len(logger.get_active_operations()) == 1

            # Завершаем операцию
            logger.end_operation(
                operation_id=operation_id,
                result={"status": "success"}
            )

            assert len(logger.get_active_operations()) == 0

            # Проверяем метрики
            metrics = logger.get_metrics()
            assert metrics["operations_started"] == 1
            assert metrics["operations_completed"] == 1
            assert metrics["operations_failed"] == 0

            logger.close()

    def test_operation_with_error(self):
        """Тест операции с ошибкой."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_error",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            operation_id = logger.start_operation(
                operation_type="failing_operation"
            )

            # Завершаем с ошибкой
            test_error = ValueError("Test operation error")
            logger.end_operation(
                operation_id=operation_id,
                error=test_error
            )

            metrics = logger.get_metrics()
            assert metrics["operations_failed"] == 1
            assert metrics["operations_completed"] == 0

            logger.close()

    def test_performance_logging(self):
        """Тест логирования производительности."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_perf",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            logger.performance(
                operation="test_query",
                duration_ms=150.5,
                records_processed=1000
            )

            logger.close()

            # Проверяем структурированный лог
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                log_entry = json.loads(f.readline())

            assert log_entry["level"] == "PERFORMANCE"
            assert log_entry["operation_type"] == "test_query"
            assert log_entry["duration_ms"] == 150.5
            assert log_entry["metadata"]["records_processed"] == 1000

    def test_llm_interaction_logging(self):
        """Тест логирования взаимодействия с LLM."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_llm",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            # Mock объекты для LLM
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"test": "data"}

            mock_params = MagicMock()
            mock_params.__class__.__name__ = "ExtractedParams"

            logger.log_llm_interaction(
                user_query="Test query",
                llm_response=mock_response,
                extracted_params=mock_params,
                extraction_time_ms=250.0
            )

            logger.close()

            # Проверяем структурированный лог
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                log_entry = json.loads(f.readline())

            assert log_entry["level"] == "INFO"
            assert log_entry["operation_type"] == "llm_extraction"
            assert log_entry["duration_ms"] == 250.0
            assert log_entry["metadata"]["user_query_length"] == len("Test query")

    def test_compound_data_logging(self):
        """Тест логирования данных соединений."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_compound",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            compounds = [
                {"compound": "H2O", "selected_records": [{"test": "data"}], "confidence": 0.95},
                {"compound": "CO2", "selected_records": [], "confidence": 0.0}
            ]

            logger.log_compound_data_table(compounds, "Test compounds")

            logger.close()

            # Проверяем структурированный лог
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                log_entry = json.loads(f.readline())

            assert log_entry["level"] == "INFO"
            assert log_entry["operation_type"] == "compound_data"
            assert log_entry["metadata"]["title"] == "Test compounds"
            assert log_entry["metadata"]["compounds_count"] == 2

    @patch('psutil.cpu_percent')
    @patch('psutil.Process')
    def test_system_metrics(self, mock_process, mock_cpu):
        """Тест сбора системных метрик."""
        # Mock psutil
        mock_cpu.return_value = 25.5
        mock_process_instance = MagicMock()
        mock_process_instance.memory_percent.return_value = 15.2
        mock_process.return_value = mock_process_instance

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_metrics",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            logger.info("Test message with metrics")

            logger.close()

            # Проверяем структурированный лог
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                log_entry = json.loads(f.readline())

            assert log_entry["cpu_usage"] == 25.5
            assert log_entry["memory_usage"] == 15.2

    def test_context_manager(self):
        """Тест работы как контекстный менеджер."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with UnifiedLogger(
                session_id="test_context",
                logs_dir=temp_dir,
                enable_console_logging=False
            ) as logger:

                logger.info("Inside context")
                operation_id = logger.start_operation("context_test")

            # После выхода из контекста логгер должен быть закрыт
            metrics = logger.get_metrics()
            assert metrics["operations_started"] == 1

    def test_operation_timer_context_manager(self):
        """Тест OperationTimer контекстного менеджера."""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_timer",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            operation_id = logger.start_operation("timed_operation")

            with OperationTimer(logger, operation_id) as timer:
                time.sleep(0.1)  # 100ms
                timer.result = {"status": "completed"}

            metrics = logger.get_metrics()
            assert metrics["operations_completed"] == 1
            assert metrics["total_duration_ms"] >= 90  # С небольшим допуском

            logger.close()

    def test_log_levels_filtering(self):
        """Тест фильтрации по уровням логирования."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Создаем логгер с уровнем WARNING
            logger = UnifiedLogger(
                session_id="test_levels",
                logs_dir=temp_dir,
                log_level=LogLevel.WARNING,
                enable_console_logging=False
            )

            logger.debug("Debug message")  # Не должно быть записано
            logger.info("Info message")     # Не должно быть записано
            logger.warning("Warning message")  # Должно быть записано
            logger.error("Error message")      # Должно быть записано

            logger.close()

            # Проверяем структурированные логи
            with open(logger.structured_log_file, 'r', encoding='utf-8') as f:
                logs = [json.loads(line) for line in f]

            # Должны быть только WARNING и ERROR
            assert len(logs) == 2
            assert all(log["level"] in ["WARNING", "ERROR"] for log in logs)

    def test_thread_safety(self):
        """Тест потоковой безопасности."""
        import threading

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = UnifiedLogger(
                session_id="test_thread",
                logs_dir=temp_dir,
                enable_console_logging=False
            )

            def worker():
                for i in range(10):
                    logger.info(f"Message {i} from thread {threading.current_thread().name}")
                    operation_id = logger.start_operation(f"operation_{i}")
                    time.sleep(0.001)  # Короткая пауза
                    logger.end_operation(operation_id, result={"thread": threading.current_thread().name})

            # Запускаем несколько потоков
            threads = []
            for i in range(5):
                thread = threading.Thread(target=worker, name=f"Worker-{i}")
                threads.append(thread)
                thread.start()

            # Ждем завершения всех потоков
            for thread in threads:
                thread.join()

            metrics = logger.get_metrics()
            assert metrics["operations_started"] == 50  # 10 операций * 5 потоков
            assert metrics["operations_completed"] == 50

            logger.close()


class TestSessionLoggerCompatibility:
    """Тесты обратной совместимости с SessionLogger."""

    def test_session_logger_initialization(self):
        """Тест инициализации SessionLogger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from thermo_agents.thermo_agents_logger import SessionLogger

            session_logger = SessionLogger(logs_dir=temp_dir)

            assert session_logger.session_id is not None
            assert session_logger._logger is not None
            assert session_logger.operation_logger is session_logger

            session_logger.close()

    def test_session_logger_basic_methods(self):
        """Тест базовых методов SessionLogger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from thermo_agents.thermo_agents_logger import SessionLogger

            session_logger = SessionLogger(logs_dir=temp_dir)

            # Тестируем базовые методы
            session_logger.log_info("Test info message")
            session_logger.log_error("Test error message")

            # Тестируем метаданные
            metadata = {"test_key": "test_value", "number": 42}
            session_logger.log_search_metadata(metadata, "Test metadata")

            session_logger.close()

            # Проверяем, что файлы созданы
            assert session_logger.log_file.exists()

    def test_session_logger_operation_context(self):
        """Тест создания контекста операции в SessionLogger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from thermo_agents.thermo_agents_logger import SessionLogger
            from thermo_agents.operations import OperationType

            session_logger = SessionLogger(logs_dir=temp_dir)

            with session_logger.create_operation_context(
                agent_name="test_agent",
                operation_type=OperationType.EXTRACT_PARAMETERS,
                correlation_id="test_corr"
            ) as operation:
                operation.set_result({"status": "success"})

            session_logger.close()

            # Проверяем метрики
            metrics = session_logger._logger.get_metrics()
            assert metrics["operations_completed"] == 1

    def test_session_logger_llm_interaction(self):
        """Тест логирования LLM взаимодействия в SessionLogger."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from thermo_agents.thermo_agents_logger import SessionLogger

            session_logger = SessionLogger(logs_dir=temp_dir)

            # Mock объекты
            mock_response = MagicMock()
            mock_response.model_dump.return_value = {"extracted": "data"}

            mock_params = MagicMock()
            mock_params.balanced_equation = "2H2 + O2 -> 2H2O"
            mock_params.all_compounds = ["H2", "O2", "H2O"]

            session_logger.log_llm_interaction(
                user_query="Test query",
                llm_response=mock_response,
                extracted_params=mock_params,
                extraction_time_ms=150.0
            )

            session_logger.close()

            # Проверяем, что логгер UnifiedLogger получил вызов
            metrics = session_logger._logger.get_metrics()
            # Успешная операция LLM должна быть засчитана
            assert metrics["log_entries_count"] > 0


if __name__ == "__main__":
    pytest.main([__file__])