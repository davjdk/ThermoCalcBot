"""
Performance тесты файловых операций
"""

import pytest
import time
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from src.thermo_agents.telegram_bot.formatters.file_handler import FileHandler
from src.thermo_agents.telegram_bot.config import TelegramBotConfig
from tests.telegram_bot.fixtures.mock_updates import create_mock_telegram_bot_config


@pytest.mark.performance
class TestFileOperationsPerformance:
    """Performance тесты файловых операций"""

    @pytest.fixture
    def file_config(self):
        """Конфигурация для тестов файлов"""
        config = create_mock_telegram_bot_config()
        config.max_file_size_mb = 50
        config.temp_file_dir = "temp/performance_test_files"
        return config

    @pytest.fixture
    def temp_dir(self):
        """Временная директория для тестов"""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def file_handler(self, file_config, temp_dir):
        """Файловый хендлер для тестов"""
        file_config.temp_file_dir = Path(temp_dir) / "perf_files"
        return FileHandler(file_config)

    @pytest.mark.asyncio
    async def test_file_creation_performance(self, file_handler):
        """Тест производительности создания файлов"""
        file_count = 50
        content_size = 10000  # 10KB контент
        large_content = "A" * content_size

        creation_times = []
        file_paths = []

        start_time = time.time()
        for i in range(file_count):
            operation_start = time.time()

            file_path = await file_handler.create_thermo_report_file(
                large_content,
                12345 + i,
                f"Performance test reaction {i}"
            )

            creation_times.append(time.time() - operation_start)
            file_paths.append(file_path)

        total_time = time.time() - start_time
        avg_creation_time = sum(creation_times) / len(creation_times)
        max_creation_time = max(creation_times)

        # Проверки производительности
        assert avg_creation_time < 0.05, \
            f"Average file creation too slow: {avg_creation_time*1000:.2f}ms"
        assert max_creation_time < 0.2, \
            f"Max file creation too slow: {max_creation_time*1000:.2f}ms"
        assert total_time < 2.0, \
            f"Total file creation too slow: {total_time:.2f}s"

        # Проверка, что все файлы созданы
        assert all(Path(path).exists() for path in file_paths)
        assert len(file_paths) == file_count

        print(f"File creation performance:")
        print(f"  Files created: {file_count}")
        print(f"  Average time: {avg_creation_time*1000:.2f}ms")
        print(f"  Max time: {max_creation_time*1000:.2f}ms")
        print(f"  Total time: {total_time:.3f}s")
        print(f"  Files per second: {file_count/total_time:.2f}")

    @pytest.mark.asyncio
    async def test_large_file_handling_performance(self, file_handler):
        """Тест производительности обработки больших файлов"""
        large_content_sizes = [1, 5, 10, 20]  # MB

        for size_mb in large_content_sizes:
            content = "A" * (size_mb * 1024 * 1024)

            start_time = time.time()

            try:
                file_path = await file_handler.create_thermo_report_file(
                    content,
                    12345,
                    f"Large test {size_mb}MB"
                )

                creation_time = time.time() - start_time

                # Проверки производительности
                assert creation_time < 1.0, \
                    f"Large file ({size_mb}MB) creation too slow: {creation_time:.2f}s"

                # Проверка размера файла
                file_size = Path(file_path).stat().st_size / (1024 * 1024)  # MB
                assert abs(file_size - size_mb) < 0.1, \
                    f"File size mismatch: expected {size_mb}MB, got {file_size:.2f}MB"

                print(f"Large file ({size_mb}MB) creation: {creation_time:.3f}s")

            except ValueError as e:
                if "exceeds maximum size" in str(e) and size_mb > file_handler.config.max_file_size_mb:
                    print(f"File size {size_mb}MB correctly rejected (limit: {file_handler.config.max_file_size_mb}MB)")
                    continue
                else:
                    raise e

    @pytest.mark.asyncio
    async def test_concurrent_file_operations(self, file_handler):
        """Тест производительности конкурентных файловых операций"""
        concurrent_operations = 20
        content_size = 5000  # 5KB

        async def create_file_concurrently(operation_id: int):
            start_time = time.time()

            content = f"Concurrent operation {operation_id}\n" + "A" * content_size
            file_path = await file_handler.create_thermo_report_file(
                content,
                12345 + operation_id,
                f"Concurrent test {operation_id}"
            )

            return {
                "operation_id": operation_id,
                "file_path": file_path,
                "time": time.time() - start_time
            }

        # Запуск всех операций concurrently
        start_time = time.time()
        tasks = [create_file_concurrently(i) for i in range(concurrent_operations)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.time() - start_time

        # Анализ результатов
        successful_results = [r for r in results if isinstance(r, dict)]
        operation_times = [r["time"] for r in successful_results]

        avg_time = sum(operation_times) / len(operation_times)
        max_time = max(operation_times)

        # Проверки производительности
        assert len(successful_results) == concurrent_operations, \
            f"Not all operations completed: {len(successful_results)}/{concurrent_operations}"
        assert avg_time < 0.1, \
            f"Average concurrent operation too slow: {avg_time*1000:.2f}ms"
        assert total_time < max_time + 0.5, \
            f"Concurrent execution not efficient: {total_time:.2f}s vs max {max_time:.2f}s"

        print(f"Concurrent file operations performance:")
        print(f"  Operations: {concurrent_operations}")
        print(f"  Average time: {avg_time*1000:.2f}ms")
        print(f"  Max time: {max_time*1000:.2f}ms")
        print(f"  Total time: {total_time:.3f}s")

    @pytest.mark.asyncio
    async def test_file_cleanup_performance(self, file_handler):
        """Тест производительности очистки файлов"""
        # Создание тестовых файлов
        file_count = 100

        # Создание старых файлов (должны быть удалены)
        old_files = []
        for i in range(file_count // 2):
            content = f"Old file {i}\n" + "A" * 1000
            file_path = await file_handler.create_thermo_report_file(
                content,
                20000 + i,
                f"Old test {i}"
            )
            old_files.append(Path(file_path))

            # Имитация старого файла (изменение времени)
            old_time = time.time() - (25 * 3600)  # 25 часов назад
            import os
            os.utime(file_path, (old_time, old_time))

        # Создание новых файлов (не должны быть удалены)
        new_files = []
        for i in range(file_count // 2):
            content = f"New file {i}\n" + "A" * 1000
            file_path = await file_handler.create_thermo_report_file(
                content,
                30000 + i,
                f"New test {i}"
            )
            new_files.append(Path(file_path))

        # Тест производительности очистки
        start_time = time.time()
        cleaned_count = await file_handler.cleanup_old_files()
        cleanup_time = time.time() - start_time

        # Проверки
        assert cleaned_count == len(old_files), \
            f"Not all old files cleaned: {cleaned_count}/{len(old_files)}"
        assert cleanup_time < 2.0, \
            f"File cleanup too slow: {cleanup_time:.2f}s"
        assert all(not f.exists() for f in old_files), \
            "Some old files still exist"
        assert all(f.exists() for f in new_files), \
            "Some new files were deleted"

        print(f"File cleanup performance:")
        print(f"  Files created: {file_count}")
        print(f"  Files cleaned: {cleaned_count}")
        print(f"  Cleanup time: {cleanup_time:.3f}s")
        print(f"  Time per file: {cleanup_time/cleaned_count*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_filename_sanitization_performance(self, file_handler):
        """Тест производительности очистки имён файлов"""
        test_filenames = [
            "2H₂ + O₂ → 2H₂O",
            "Reaction@#$%^&*()with special chars",
            "Very long filename " * 20,  # >200 символов
            "File:With/Windows\\Incompatible*Chars?And|More<Terrible>",
            "Unicode_файл_с_русскими_буквами_и_специальными_символами",
            "Normal filename.txt"
        ] * 100  # 600 имён файлов

        sanitization_times = []

        for filename in test_filenames:
            start_time = time.time()
            sanitized = file_handler._sanitize_filename(filename)
            sanitization_times.append(time.time() - start_time)

        avg_time = sum(sanitization_times) / len(sanitization_times)
        max_time = max(sanitization_times)

        # Проверки производительности
        assert avg_time < 0.001, \
            f"Filename sanitization too slow: {avg_time*1000:.3f}ms"
        assert max_time < 0.01, \
            f"Max filename sanitization too slow: {max_time*1000:.2f}ms"

        print(f"Filename sanitization performance:")
        print(f"  Filenames processed: {len(test_filenames)}")
        print(f"  Average time: {avg_time*1000:.3f}ms")
        print(f"  Max time: {max_time*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_file_info_retrieval_performance(self, file_handler):
        """Тест производительности получения информации о файлах"""
        # Создание тестовых файлов
        file_count = 50
        file_paths = []

        for i in range(file_count):
            content = f"Test file {i}\n" + "A" * (i * 100)  # Разные размеры
            file_path = await file_handler.create_thermo_report_file(
                content,
                40000 + i,
                f"Info test {i}"
            )
            file_paths.append(file_path)

        # Тест производительности получения информации
        info_times = []

        for file_path in file_paths:
            start_time = time.time()
            info = file_handler._get_file_info(file_path)
            info_times.append(time.time() - start_time)

            # Проверка корректности информации
            assert info["exists"] is True
            assert info["size_bytes"] > 0
            assert info["user_id"] >= 40000

        avg_time = sum(info_times) / len(info_times)
        max_time = max(info_times)

        # Проверки производительности
        assert avg_time < 0.001, \
            f"File info retrieval too slow: {avg_time*1000:.3f}ms"
        assert max_time < 0.01, \
            f"Max file info retrieval too slow: {max_time*1000:.2f}ms"

        print(f"File info retrieval performance:")
        print(f"  Files checked: {file_count}")
        print(f"  Average time: {avg_time*1000:.3f}ms")
        print(f"  Max time: {max_time*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_unicode_file_content_performance(self, file_handler):
        """Тест производительности обработки Unicode контента"""
        unicode_content = """
        Термодинамические свойства:
        H₂O + O₂ → H₂O₂
        ΔH° = -285.83 кДж/моль
        S° = 69.91 Дж/(моль·К)

        Температурный диапазон: 273.15 - 373.15 K
        Точка плавления: 273.15 K
        Точка кипения: 373.15 K

        Таблица данных:
        | T (K) | ΔH (кДж) | ΔS (Дж/К) |
        |-------|----------|-----------|
        """ + "\n| 298   | -285.83  | 69.91    |\n" * 100

        creation_times = []

        for i in range(20):
            start_time = time.time()

            file_path = await file_handler.create_thermo_report_file(
                unicode_content,
                50000 + i,
                f"Unicode тест {i}"
            )

            creation_times.append(time.time() - start_time)

            # Проверка сохранения Unicode
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
                assert "H₂O" in file_content
                assert "Термодинамические" in file_content
                assert "→" in file_content

        avg_time = sum(creation_times) / len(creation_times)
        max_time = max(creation_times)

        # Проверки производительности
        assert avg_time < 0.1, \
            f"Unicode file creation too slow: {avg_time*1000:.2f}ms"
        assert max_time < 0.5, \
            f"Max Unicode file creation too slow: {max_time*1000:.2f}ms"

        print(f"Unicode file operations performance:")
        print(f"  Files created: {len(creation_times)}")
        print(f"  Average time: {avg_time*1000:.2f}ms")
        print(f"  Max time: {max_time*1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_memory_usage_during_file_operations(self, file_handler):
        """Тест использования памяти во время файловых операций"""
        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Создание множества файлов разного размера
        for i in range(30):
            content_size = 1000 + i * 1000  # От 1KB до 30KB
            content = "A" * content_size

            await file_handler.create_thermo_report_file(
                content,
                60000 + i,
                f"Memory test {i}"
            )

        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - initial_memory

        # Проверка использования памяти
        assert memory_increase < 50, \
            f"Memory usage too high during file operations: {memory_increase:.2f}MB"

        print(f"Memory usage during file operations:")
        print(f"  Initial memory: {initial_memory:.2f}MB")
        print(f"  Peak memory: {peak_memory:.2f}MB")
        print(f"  Memory increase: {memory_increase:.2f}MB")

    @pytest.mark.asyncio
    async def test_error_handling_performance(self, file_handler):
        """Тест производительности обработки ошибок файловых операций"""
        error_scenarios = [
            # Слишком большой файл
            ("A" * (55 * 1024 * 1024), 12345, "Too large file"),
            # Пустое имя реакции
            ("Some content", 12346, ""),
            # Специальные символы в имени
            ("Content", 12347, "File@#$%^&*()Name"),
            # Очень длинное имя
            ("Content", 12348, "A" * 200),
        ]

        error_times = []

        for content, user_id, reaction_info in error_scenarios:
            start_time = time.time()

            try:
                await file_handler.create_thermo_report_file(content, user_id, reaction_info)
            except (ValueError, OSError):
                # Ожидаем ошибки
                pass

            error_times.append(time.time() - start_time)

        avg_error_time = sum(error_times) / len(error_times)
        max_error_time = max(error_times)

        # Проверки производительности обработки ошибок
        assert avg_error_time < 0.1, \
            f"Error handling too slow: {avg_error_time*1000:.2f}ms"
        assert max_error_time < 0.5, \
            f"Max error handling too slow: {max_error_time*1000:.2f}ms"

        print(f"File error handling performance:")
        print(f"  Error scenarios: {len(error_scenarios)}")
        print(f"  Average time: {avg_error_time*1000:.2f}ms")
        print(f"  Max time: {max_error_time*1000:.2f}ms")