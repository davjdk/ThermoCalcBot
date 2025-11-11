"""
Интеграция Telegram бота с ThermoOrchestrator.

Адаптирует интерфейс ThermoSystem для использования в Telegram боте.
"""

import time
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from ...orchestrator import ThermoOrchestrator, ThermoOrchestratorConfig
from ...session_logger import SessionLogger
from ...models.extraction import ExtractedReactionParameters


@dataclass
class ThermoResponse:
    """Результат обработки запроса ThermoSystem."""
    content: str
    query_type: str
    compounds: list[str]
    processing_time_ms: float
    has_large_tables: bool
    success: bool = True
    error: Optional[str] = None


class ThermoIntegration:
    """Интеграция с ThermoOrchestrator для Telegram бота."""

    def __init__(self, config):
        self.config = config
        self.orchestrator: Optional[ThermoOrchestrator] = None
        self._init_orchestrator()

    def _init_orchestrator(self) -> None:
        """Инициализация ThermoOrchestrator."""
        try:
            # Создание конфигурации ThermoOrchestrator
            thermo_config = ThermoOrchestratorConfig(
                llm_api_key=self.config.llm_api_key,
                llm_base_url=self.config.llm_base_url,
                llm_model=self.config.llm_model,
                db_path=self.config.thermo_db_path,
                static_data_dir=self.config.thermo_static_data_dir,
                max_retries=2,
                timeout_seconds=self.config.request_timeout_seconds
            )

            # Создание сессионного логгера
            session_logger = SessionLogger()

            # Инициализация оркестратора
            self.orchestrator = ThermoOrchestrator(thermo_config, session_logger=session_logger)

        except Exception as e:
            print(f"Ошибка инициализации ThermoOrchestrator: {e}")
            self.orchestrator = None

    async def process_query(self, query: str, user_id: int) -> ThermoResponse:
        """
        Обработка термодинамического запроса.

        Args:
            query: Текст запроса пользователя
            user_id: ID пользователя Telegram

        Returns:
            ThermoResponse с результатом обработки
        """
        if not self.orchestrator:
            return ThermoResponse(
                content="",
                query_type="error",
                compounds=[],
                processing_time_ms=0,
                has_large_tables=False,
                success=False,
                error="ThermoOrchestrator не инициализирован"
            )

        start_time = time.time()

        try:
            # Обработка запроса через ThermoOrchestrator
            result = await self.orchestrator.process_query(query)

            # Извлечение информации о запросе
            query_info = await self._extract_query_info(query, user_id)

            # Определение наличия больших таблиц
            has_large_tables = self._detect_large_tables(result)

            processing_time = (time.time() - start_time) * 1000

            return ThermoResponse(
                content=result,
                query_type=query_info["query_type"],
                compounds=query_info["compounds"],
                processing_time_ms=processing_time,
                has_large_tables=has_large_tables,
                success=True
            )

        except asyncio.TimeoutError:
            return ThermoResponse(
                content="",
                query_type="error",
                compounds=[],
                processing_time_ms=(time.time() - start_time) * 1000,
                has_large_tables=False,
                success=False,
                error="Превышен таймаут обработки запроса"
            )

        except Exception as e:
            return ThermoResponse(
                content="",
                query_type="error",
                compounds=[],
                processing_time_ms=(time.time() - start_time) * 1000,
                has_large_tables=False,
                success=False,
                error=f"Ошибка обработки запроса: {str(e)}"
            )

    async def _extract_query_info(self, query: str, user_id: int) -> dict:
        """
        Извлечение информации о запросе для логирования и статистики.

        Args:
            query: Текст запроса
            user_id: ID пользователя

        Returns:
            Словарь с информацией о запросе
        """
        try:
            # Базовая классификация запроса
            query_lower = query.lower()

            # Определение типа запроса
            if any(keyword in query_lower for keyword in [
                "дай таблицу", "свойства", "свойств", "данные", "табличные данные",
                "table", "properties", "data"
            ]):
                query_type = "compound_data"
            elif any(keyword in query_lower for keyword in [
                "реакция", "реагирует", "->", "→", "реагирует ли", "прореагирует",
                "reaction", "react"
            ]):
                query_type = "reaction"
            else:
                query_type = "calculation"

            # Извлечение соединений (простой парсинг)
            compounds = self._extract_compounds(query)

            return {
                "query_type": query_type,
                "compounds": compounds,
                "user_id": user_id,
                "query_length": len(query)
            }

        except Exception as e:
            print(f"Ошибка извлечения информации о запросе: {e}")
            return {
                "query_type": "unknown",
                "compounds": [],
                "user_id": user_id,
                "query_length": len(query)
            }

    def _extract_compounds(self, query: str) -> list[str]:
        """
        Простое извлечение химических формул из запроса.

        Args:
            query: Текст запроса

        Returns:
            Список найденных соединений
        """
        import re

        # Базовые паттерны для химических формул
        compound_patterns = [
            r'\b[A-Z][a-z]?\d*[a-z]?\d*\b',  # Простые формулы (H2O, CO2)
            r'\b[A-Z]{2,}\d*\b',  # Соединения из нескольких заглавных букв (Fe, NaCl)
            r'\b[A-Z][a-z]?\d*[A-Z][a-z]?\d*\b',  # Двуэлементные соединения
        ]

        compounds = set()

        for pattern in compound_patterns:
            matches = re.findall(pattern, query)
            for match in matches:
                # Фильтрация общих слов
                if match.lower() not in ['at', 'to', 'from', 'and', 'or', 'in', 'on', 'for']:
                    compounds.add(match)

        # Дополнительная фильтрация для химических соединений
        chemical_compounds = []
        for compound in compounds:
            if self._is_likely_compound(compound):
                chemical_compounds.append(compound)

        return list(chemical_compounds)[:10]  # Максимум 10 соединений

    def _is_likely_compound(self, text: str) -> bool:
        """
        Определение, является ли текст вероятным химическим соединением.

        Args:
            text: Текст для проверки

        Returns:
            True если это вероятно химическое соединение
        """
        # Список известных химических элементов
        elements = {
            'H', 'He', 'Li', 'Be', 'B', 'C', 'N', 'O', 'F', 'Ne',
            'Na', 'Mg', 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', 'K', 'Ca',
            'Fe', 'Cu', 'Zn', 'Ag', 'Au', 'Hg', 'Pb', 'Sn', 'Ni', 'Co'
        }

        text_upper = text.upper()

        # Проверка на известные соединения
        known_compounds = {
            'H2O', 'CO2', 'CO', 'O2', 'H2', 'N2', 'NH3', 'CH4', 'HCl',
            'SO2', 'NO2', 'H2SO4', 'NaCl', 'Fe2O3', 'FeO', 'CaO',
            'SiO2', 'Al2O3', 'MgO', 'K2O', 'Na2O', 'P2O5'
        }

        if text in known_compounds:
            return True

        # Проверка на паттерны с элементами
        has_element = any(element in text_upper for element in elements)
        has_digit = any(char.isdigit() for char in text)

        # Если есть цифры, это скорее всего химическая формула
        if has_digit and has_element:
            return True

        # Если начинается с заглавной буквы и содержит другие заглавные
        if len(text) >= 2 and text[0].isupper() and any(c.isupper() for c in text[1:]):
            return True

        return False

    def _detect_large_tables(self, content: str) -> bool:
        """
        Определение наличия больших таблиц в контенте.

        Args:
            content: Контент для анализа

        Returns:
            True если есть большие таблицы
        """
        lines = content.split('\n')
        table_lines = 0

        for line in lines:
            # Поиск строк, похожих на таблицы
            if self._is_table_line(line):
                table_lines += 1

        # Если есть более 5 строк таблицы, считаем это большой таблицей
        return table_lines > 5

    def _is_table_line(self, line: str) -> bool:
        """Определение, является ли строка частью таблицы."""
        # Проверка на наличие нескольких чисел в строке
        import re

        # Паттерны для таблиц с числами
        number_patterns = [
            r'\d+\.?\d*\s+[\d\.]+\s+[\d\.]+',  # Три и более числа
            r'\|\s*\d+\s*\|\s*\d+',  # Формат |число|число|
            r'\d+\.\d+E[+-]\d+',  # Научная нотация
        ]

        for pattern in number_patterns:
            if re.search(pattern, line):
                return True

        return False

    async def health_check(self) -> dict:
        """Проверка здоровья интеграции."""
        try:
            if not self.orchestrator:
                return {
                    "status": "unhealthy",
                    "error": "ThermoOrchestrator не инициализирован"
                }

            # Проверка базы данных
            db_path = self.config.thermo_db_path
            if not db_path.exists():
                return {
                    "status": "unhealthy",
                    "error": f"База данных не найдена: {db_path}"
                }

            # Проверка LLM API (простой тестовый запрос)
            test_start = time.time()
            try:
                test_result = await self.orchestrator.process_query("H2O свойства")
                llm_time = (time.time() - test_start) * 1000
                llm_status = "healthy"
            except Exception as e:
                llm_time = 0
                llm_status = f"unhealthy: {str(e)}"

            return {
                "status": "healthy",
                "components": {
                    "orchestrator": "healthy",
                    "database": "healthy",
                    "llm_api": llm_status
                },
                "performance": {
                    "llm_response_time_ms": llm_time
                }
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Ошибка health check: {str(e)}"
            }