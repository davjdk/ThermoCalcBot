"""
Агент для выполнения запросов к базе данных.

Отвечает только за выполнение SQL запросов и возврат результатов.
Не генерирует SQL - получает готовые запросы от SQL агента.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .agent_storage import AgentStorage, get_storage
from .thermo_agents_logger import SessionLogger


@dataclass
class DatabaseAgentConfig:
    """Конфигурация агента базы данных."""

    agent_id: str = "database_agent"
    db_path: str = "data/thermo_data.db"
    storage: AgentStorage = field(default_factory=get_storage)
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__name__))
    session_logger: Optional[SessionLogger] = None
    poll_interval: float = 1.0
    timeout_seconds: int = 30


class DatabaseAgent:
    """
    Агент для выполнения SQL запросов к термодинамической базе данных.

    Обязанности:
    - Получает готовые SQL запросы от других агентов
    - Выполняет запросы к SQLite базе данных
    - Применяет фильтрацию результатов (например, по температуре)
    - Возвращает структурированные результаты
    """

    def __init__(self, config: DatabaseAgentConfig):
        """Инициализация агента базы данных."""
        self.config = config
        self.agent_id = config.agent_id
        self.storage = config.storage
        self.logger = config.logger
        self.running = False

        # Регистрация в хранилище
        self.storage.start_session(
            self.agent_id,
            {
                "status": "initialized",
                "capabilities": ["execute_sql", "filter_results", "query_database"],
                "database": config.db_path,
            },
        )

        self.logger.info(f"DatabaseAgent '{self.agent_id}' initialized")

    async def start(self):
        """Запустить агента в режиме прослушивания сообщений."""
        self.running = True
        self.storage.update_session(self.agent_id, {"status": "running"})
        self.logger.info(f"Agent '{self.agent_id}' started listening for messages")

        while self.running:
            try:
                # Получаем сообщения на выполнение SQL (оба типа)
                messages_standard = self.storage.receive_messages(
                    self.agent_id, message_type="execute_sql"
                )
                messages_individual = self.storage.receive_messages(
                    self.agent_id, message_type="execute_individual_sql"
                )

                # Объединяем сообщения
                all_messages = messages_standard + messages_individual

                # Обрабатываем каждое сообщение
                for message in all_messages:
                    await self._process_message(message)

                # Ждем перед следующей проверкой
                await asyncio.sleep(self.config.poll_interval)

            except Exception as e:
                self.logger.error(f"Error in database agent loop: {e}")
                await asyncio.sleep(self.config.poll_interval * 2)

    async def stop(self):
        """Остановить агента."""
        self.running = False
        self.storage.update_session(self.agent_id, {"status": "stopped"})
        self.logger.info(f"Agent '{self.agent_id}' stopped")

    async def _process_message(self, message):
        """Обработать входящее сообщение для выполнения SQL."""
        self.logger.info(
            f"Processing SQL execution request: {message.id} from {message.source_agent}, type: {message.message_type}"
        )

        try:
            # Извлекаем SQL запрос и параметры
            sql_query = message.payload.get("sql_query")

            # Определяем тип сообщения
            is_individual = message.message_type == "execute_individual_sql"

            if is_individual:
                # Индивидуальный запрос
                compound = message.payload.get("compound")
                common_params = message.payload.get("common_params", {})
                extracted_params = {
                    "compounds": [compound],
                    "temperature_k": common_params.get("temperature_k", 298.15),
                    "temperature_range_k": common_params.get("temperature_range_k", [298.15, 298.15]),
                    "phases": common_params.get("phases", []),
                    "properties": common_params.get("properties", ["basic"]),
                    "intent": "individual_lookup",
                }
                self.logger.info(f"Executing individual SQL query for compound {compound}: {sql_query}")
            else:
                # Стандартный запрос
                extracted_params = message.payload.get("extracted_params", {})
                self.logger.info(f"Executing standard SQL query: {sql_query}")

            if not sql_query:
                raise ValueError("No sql_query in message payload")

            if self.config.session_logger:
                self.config.session_logger.log_info(f"DATABASE EXECUTION START: {sql_query}")

            # Выполняем SQL запрос
            execution_result = await self._execute_query(sql_query, extracted_params)

            # Сохраняем результат в хранилище
            result_key = f"db_result_{message.id}"
            result_data = {
                "sql_query": sql_query,
                "execution_result": execution_result,
                "extracted_params": extracted_params,
            }

            self.storage.set(result_key, result_data, ttl_seconds=600)
            self.logger.info(f"Database result stored with key: {result_key}")

            # Отправляем результаты агенту фильтрации для интеллектуального отбора
            if execution_result.get("success") and execution_result.get("row_count", 0) > 0:
                self.logger.info("Sending results to filtering agent for analysis...")

                if is_individual:
                    # Индивидуальная фильтрация
                    filtering_message_id = self.storage.send_message(
                        source_agent=self.agent_id,
                        target_agent="results_filtering_agent",
                        message_type="filter_individual_results",
                        correlation_id=message.correlation_id,  # Используем correlation_id от SQL агента
                        payload={
                            "execution_result": execution_result,
                            "compound": compound,
                            "common_params": common_params,
                            "sql_query": sql_query,
                        },
                    )
                    self.logger.info(f"Individual results sent to filtering agent: {filtering_message_id}")
                else:
                    # Стандартная фильтрация
                    filtering_message_id = self.storage.send_message(
                        source_agent=self.agent_id,
                        target_agent="results_filtering_agent",
                        message_type="filter_results",
                        correlation_id=message.correlation_id,  # Используем исходный correlation_id от SQL агента
                        payload={
                            "execution_result": execution_result,
                            "extracted_params": extracted_params,
                            "sql_query": sql_query,
                        },
                    )
                    self.logger.info(f"Results sent to filtering agent: {filtering_message_id}")

            # Отправляем ответ SQL агенту
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="sql_executed",
                correlation_id=message.id,
                payload={
                    "status": "success",
                    "result_key": result_key,
                    "execution_result": execution_result,
                },
            )

            self.logger.info(f"Response sent to {message.source_agent}")

        except Exception as e:
            self.logger.error(f"Error processing database message {message.id}: {e}")

            # Отправляем сообщение об ошибке
            self.storage.send_message(
                source_agent=self.agent_id,
                target_agent=message.source_agent,
                message_type="sql_error",
                correlation_id=message.id,
                payload={"status": "error", "error": str(e)},
            )

            if self.config.session_logger:
                self.config.session_logger.log_error(f"DATABASE ERROR: {str(e)}")

    async def _execute_query(self, sql_query: str, extracted_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполнить SQL запрос к базе данных.

        Args:
            sql_query: SQL запрос для выполнения
            extracted_params: Параметры для фильтрации результатов

        Returns:
            Результаты выполнения запроса
        """
        try:
            # Очистка SQL запроса
            cleaned_query = self._clean_sql_query(sql_query)

            # Подключение к базе данных
            conn = sqlite3.connect(self.config.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Выполнение запроса
            cursor.execute(cleaned_query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            data_rows = [list(row) for row in rows] if rows else []

            conn.close()

            self.logger.info(f"SQL executed successfully: {len(data_rows)} rows found")

            # Применяем фильтрацию по температуре если есть температурный диапазон
            original_count = len(data_rows)
            target_temperature = extracted_params.get("temperature_k")
            temperature_range = extracted_params.get("temperature_range_k")

            if (temperature_range or target_temperature) and data_rows:
                # Используем диапазон если есть, иначе создаем узкий диапазон вокруг целевой температуры
                if temperature_range and len(temperature_range) >= 2:
                    filter_range = [float(temperature_range[0]), float(temperature_range[1])]
                    self.logger.info(f"Applying temperature range filtering: {filter_range[0]}-{filter_range[1]}K...")
                elif target_temperature:
                    # Если задана только точная температура, создаем узкий диапазон ±10K
                    filter_range = [target_temperature - 10, target_temperature + 10]
                    self.logger.info(f"Applying narrow temperature filtering around {target_temperature}K: {filter_range[0]}-{filter_range[1]}K...")
                else:
                    filter_range = None

                if filter_range:
                    data_rows = self._filter_by_temperature_range(data_rows, columns, filter_range)
                    filtered_count = len(data_rows)
                    self.logger.info(f"Temperature filtering: {filtered_count} of {original_count} rows remain")

                    if self.config.session_logger:
                        self.config.session_logger.log_info(
                            f"TEMPERATURE FILTER: Range={filter_range[0]}-{filter_range[1]}K, "
                            f"Matched={filtered_count}, Excluded={original_count - filtered_count}"
                        )

            # Логируем результаты через session_logger
            if self.config.session_logger:
                self.config.session_logger.log_query_results_table(
                    sql_query=sql_query, columns=columns, rows=data_rows
                )

            return {
                "success": True,
                "columns": columns,
                "rows": data_rows,
                "row_count": len(data_rows),
                "original_row_count": original_count,
                "temperature_filtered": bool(target_temperature),
                "target_temperature_k": target_temperature,
                "filter_temperature_range_k": filter_range if 'filter_range' in locals() else None,
            }

        except Exception as e:
            self.logger.error(f"Database query execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

    def _clean_sql_query(self, sql_query: str) -> str:
        """Очистка SQL запроса от HTML entities и множественных statements."""
        import html
        import re

        # Декодируем HTML entities
        cleaned = html.unescape(sql_query)

        # Удаляем лишние пробелы и переносы строк
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # Разделяем на statements по точке с запятой
        statements = [stmt.strip() for stmt in cleaned.split(';') if stmt.strip()]

        # Возвращаем только первый statement
        if statements:
            first_statement = statements[0]
            # Убеждаемся, что нет HTML entities в операторах сравнения
            first_statement = first_statement.replace('&lt;=', '<=').replace('&gt;=', '>=')
            first_statement = first_statement.replace('&lt;', '<').replace('&gt;', '>')
            first_statement = first_statement.replace('&amp;', '&')
            return first_statement

        return cleaned

    def _filter_by_temperature_range(self, data_rows, columns, filter_range_k: List[float]):
        """
        Фильтрация данных по температурному диапазону.

        Args:
            data_rows: Строки данных
            columns: Названия колонок
            filter_range_k: Диапазон температур [min, max] в Кельвинах

        Returns:
            Отфильтрованные строки, где диапазон соединения перекрывается с запрошенным диапазоном
        """
        # Найдем индексы колонок Tmin и Tmax
        tmin_idx = None
        tmax_idx = None

        for i, col in enumerate(columns):
            if col.lower() == 'tmin':
                tmin_idx = i
            elif col.lower() == 'tmax':
                tmax_idx = i

        if tmin_idx is None or tmax_idx is None:
            self.logger.warning("Temperature columns (Tmin/Tmax) not found, skipping temperature filtering")
            return data_rows

        filter_min, filter_max = filter_range_k

        # Фильтруем строки по пересечению температурных диапазонов
        filtered_rows = []
        for row in data_rows:
            try:
                tmin = float(row[tmin_idx]) if row[tmin_idx] is not None else 0
                tmax = float(row[tmax_idx]) if row[tmax_idx] is not None else 9999

                # Проверяем пересечение диапазонов:
                # диапазоны пересекаются если max(tmin, filter_min) <= min(tmax, filter_max)
                if max(tmin, filter_min) <= min(tmax, filter_max):
                    filtered_rows.append(row)

            except (ValueError, TypeError, IndexError):
                # Если не удается конвертировать температуры, оставляем строку
                filtered_rows.append(row)

        return filtered_rows

    def get_status(self) -> Dict:
        """Получить статус агента."""
        session = self.storage.get_session(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "running": self.running,
            "session": session,
            "database": self.config.db_path,
        }


# =============================================================================
# ФАБРИЧНЫЕ ФУНКЦИИ
# =============================================================================


def create_database_agent(
    db_path: str = "data/thermo_data.db",
    storage: Optional[AgentStorage] = None,
    logger: Optional[logging.Logger] = None,
    session_logger: Optional[SessionLogger] = None,
) -> DatabaseAgent:
    """
    Создать агента базы данных.

    Args:
        db_path: Путь к базе данных
        storage: Хранилище (или будет использовано глобальное)
        logger: Логгер
        session_logger: Сессионный логгер

    Returns:
        Настроенный агент базы данных
    """
    config = DatabaseAgentConfig(
        db_path=db_path,
        storage=storage or get_storage(),
        logger=logger or logging.getLogger(__name__),
        session_logger=session_logger,
    )

    return DatabaseAgent(config)


async def run_database_agent_standalone(config: DatabaseAgentConfig):
    """
    Запустить агента базы данных в standalone режиме для тестирования.

    Args:
        config: Конфигурация агента
    """
    agent = DatabaseAgent(config)

    try:
        await agent.start()
    except KeyboardInterrupt:
        await agent.stop()
        print("Database agent stopped")