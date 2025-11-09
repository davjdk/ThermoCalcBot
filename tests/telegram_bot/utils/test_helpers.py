"""
Вспомогательные функции для тестирования Telegram бота
"""

import asyncio
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, AsyncMock


def assert_telegram_message_sent(mock_message: Mock, expected_text: str = None, parse_mode: str = None):
    """Проверка отправки сообщения в Telegram"""
    assert mock_message.reply_text.called, "Message reply was not called"

    if expected_text:
        call_args = mock_message.reply_text.call_args
        actual_text = call_args[0][0] if call_args[0] else ""
        assert expected_text in actual_text, f"Expected '{expected_text}' in message '{actual_text}'"

    if parse_mode:
        call_kwargs = mock_message.reply_text.call_args[1]
        assert call_kwargs.get("parse_mode") == parse_mode, f"Expected parse_mode '{parse_mode}'"


def assert_telegram_file_sent(mock_bot: Mock, filename: str = None):
    """Проверка отправки файла в Telegram"""
    assert mock_bot.send_document.called, "Document was not sent"

    if filename:
        call_args = mock_bot.send_document.call_args
        actual_filename = call_args[1].get("filename", "")
        assert filename in actual_filename, f"Expected '{filename}' in filename '{actual_filename}'"


def assert_telegram_chat_action_sent(mock_bot: Mock, action: str = "typing"):
    """Проверка отправки chat action"""
    assert mock_bot.send_chat_action.called, "Chat action was not sent"

    call_args = mock_bot.send_chat_action.call_args
    actual_action = call_args[1].get("action", "")
    assert actual_action == action, f"Expected action '{action}', got '{actual_action}'"


def create_temp_file(content: str, filename: str = None) -> Path:
    """Создание временного файла для тестов"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = Path(f.name)

    if filename:
        # Создать директорию и переместить файл
        temp_dir = temp_path.parent / "test_files"
        temp_dir.mkdir(exist_ok=True)
        new_path = temp_dir / filename
        temp_path.rename(new_path)
        return new_path

    return temp_path


async def run_async_test_with_timeout(coro, timeout: float = 30.0):
    """Запуск асинхронного теста с таймаутом"""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        raise AssertionError(f"Test timed out after {timeout} seconds")


def measure_async_execution_time(coro):
    """Измерение времени выполнения асинхронной корутины"""
    async def wrapper():
        start_time = time.time()
        try:
            result = await coro
            execution_time = time.time() - start_time
            return result, execution_time
        except Exception as e:
            execution_time = time.time() - start_time
            raise e
    return wrapper()


def create_mock_memory_usage(initial_mb: float = 50.0):
    """Создание mock для мониторинга использования памяти"""
    mock_process = Mock()
    mock_process.memory_info.return_value.rss = initial_mb * 1024 * 1024  # Convert to bytes
    return mock_process


def assert_response_within_time_limit(execution_time: float, max_time: float):
    """Проверка времени ответа"""
    assert execution_time <= max_time, f"Response time {execution_time:.2f}s exceeds limit {max_time}s"


def assert_memory_usage_within_limit(initial_memory: float, final_memory: float, max_increase: float):
    """Проверка увеличения использования памяти"""
    memory_increase = final_memory - initial_memory
    assert memory_increase <= max_increase, f"Memory increased by {memory_increase:.2f}MB, limit {max_increase}MB"


def extract_table_from_response(response: str) -> List[str]:
    """Извлечение таблицы из ответа"""
    lines = response.split('\n')
    table_lines = []
    in_table = False

    for line in lines:
        if '|' in line and ('T' in line or 'K' in line):
            in_table = True
            table_lines.append(line)
        elif in_table and '|' in line:
            table_lines.append(line)
        elif in_table and '|' not in line:
            break

    return table_lines


def extract_thermodynamic_values(response: str) -> Dict[str, float]:
    """Извлечение термодинамических значений из ответа"""
    values = {}
    lines = response.split('\n')

    for line in lines:
        if 'ΔH' in line or 'DH' in line:
            # Извлечение энтальпии
            import re
            match = re.search(r'([+-]?\d+\.?\d*)\s*кДж', line)
            if match:
                values['enthalpy'] = float(match.group(1))

        if 'S°' in line or 'S=' in line:
            # Извлечение энтропии
            import re
            match = re.search(r'(\d+\.?\d*)\s*Дж', line)
            if match:
                values['entropy'] = float(match.group(1))

        if 'K =' in line or 'K=' in line:
            # Извлечение константы равновесия
            import re
            match = re.search(r'K\s*=\s*([+-]?\d+\.?\d*[eE]?[+-]?\d*)', line)
            if match:
                values['equilibrium_constant'] = float(match.group(1))

    return values


def simulate_concurrent_requests(handler_func, requests_data: List[Dict], max_concurrent: int = 5):
    """Симуляция конкурентных запросов"""
    async def simulate_request(request_data):
        start_time = time.time()
        try:
            result = await handler_func(request_data)
            execution_time = time.time() - start_time
            return {
                "success": True,
                "result": result,
                "execution_time": execution_time,
                "user_id": request_data.get("user_id")
            }
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "success": False,
                "error": str(e),
                "execution_time": execution_time,
                "user_id": request_data.get("user_id")
            }

    async def run_with_semaphore(semaphore, request_data):
        async with semaphore:
            return await simulate_request(request_data)

    async def run_all_requests():
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = [run_with_semaphore(semaphore, req) for req in requests_data]
        return await asyncio.gather(*tasks, return_exceptions=True)

    return run_all_requests()


def cleanup_temp_files(temp_dir: Path):
    """Очистка временных файлов"""
    if temp_dir.exists():
        for file_path in temp_dir.rglob("*"):
            if file_path.is_file():
                file_path.unlink()
        temp_dir.rmdir()


def assert_file_content_matches(file_path: Path, expected_content: str):
    """Проверка содержимого файла"""
    assert file_path.exists(), f"File {file_path} does not exist"

    with open(file_path, 'r', encoding='utf-8') as f:
        actual_content = f.read()

    assert actual_content == expected_content, f"File content does not match expected content"


def assert_chemical_formulas_preserved(text: str, expected_formulas: List[str]):
    """Проверка сохранения химических формул с Unicode"""
    for formula in expected_formulas:
        assert formula in text, f"Chemical formula '{formula}' not preserved in text"


class AsyncMockContext:
    """Контекстный менеджер для асинхронных моков"""

    def __init__(self, mock_obj: Mock, method_name: str):
        self.mock_obj = mock_obj
        self.method_name = method_name
        self.original_method = getattr(mock_obj, method_name)

    async def __aenter__(self):
        async_mock = AsyncMock()
        setattr(self.mock_obj, self.method_name, async_mock)
        return async_mock

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        setattr(self.mock_obj, self.method_name, self.original_method)


def create_large_response(size_kb: int = 10) -> str:
    """Создание большого ответа для тестирования разделения сообщений"""
    base_text = "Thermodynamic calculation result line with some data: {value}\n"
    lines_needed = size_kb * 1024 // len(base_text)

    return "".join(base_text.format(value=i) for i in range(lines_needed))


def assert_message_split_correctly(messages: List[str], max_length: int = 4096):
    """Проверка корректности разделения длинных сообщений"""
    assert len(messages) > 1, "Long message was not split"

    for i, message in enumerate(messages):
        assert len(message) <= max_length, f"Message {i} exceeds max length: {len(message)} > {max_length}"

        # Проверка, что таблицы не разрываются
        if '|' in message:
            lines = message.split('\n')
            for line in lines:
                if '|' in line and line.strip():
                    # Строка таблицы должна быть полной
                    pipe_count = line.count('|')
                    assert pipe_count >= 2, f"Table line appears incomplete: {line}"