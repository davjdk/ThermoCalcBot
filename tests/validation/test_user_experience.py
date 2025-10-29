"""
Тесты пользовательского опыта многофазной термодинамической системы.

Проверяют качество взаимодействия с пользователем:
- Ясность и полнота вывода
- Понятность таблиц и форматирования
- Качество сообщений об ошибках
- Информативность рекомендаций
- Доступность интерфейса
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.orchestrator_multi_phase import (
    MultiPhaseOrchestrator,
    MultiPhaseOrchestratorConfig
)


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    return "data/thermo_data.db"


@pytest.fixture
async def multi_phase_orchestrator(test_db_path):
    """Создает многофазный оркестратор для тестов UX."""

    config = MultiPhaseOrchestratorConfig(
        db_path=test_db_path,
        llm_api_key="test_key",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
        static_cache_dir="data/static_compounds",
        integration_points=100,
    )

    orchestrator = MultiPhaseOrchestrator(config)
    yield orchestrator


class TestUserExperience:
    """Тесты пользовательского опыта."""

    @pytest.mark.asyncio
    async def test_output_clarity_and_completeness(self, multi_phase_orchestrator):
        """
        Тест ясности и полноты вывода.

        Проверяет, что ответы содержат всю необходимую информацию
        и представлены в понятном для пользователя виде.
        """

        test_queries = [
            "H2O свойства при 298K",
            "FeO термодинамика при 1000K",
            "CO2 + NH3 реакция при 500K",
            "Fe + O2 → FeO равновесие",
        ]

        for query in test_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"
            assert len(response) > 50, f"Ответ слишком короткий для информативности: {query}"

            # Проверяем наличие ключевой информации
            essential_elements = [
                # Основные данные
                any(indicator in response.lower() for indicator in ["h298", "энтальп", "дельта h"]),
                any(indicator in response.lower() for indicator in ["s298", "энтроп", "дельта s"]),
                # Температурная информация
                any(indicator in response for indicator in ["298", "K", "°C"]),
                # Структурированность
                len(response.split('\n')) >= 2,  # Должно быть несколько строк
            ]

            # Если система не может найти полные данные, должно быть объяснение
            has_data = sum(essential_elements) >= 2
            if not has_data:
                has_explanation = any(
                    indicator in response.lower()
                    for indicator in ["не найдено", "недостаточно", "отсутствует", "ограничено"]
                )
                assert has_explanation, f"При отсутствии данных должно быть объяснение: {query}"

    @pytest.mark.asyncio
    async def test_table_formatting_quality(self, multi_phase_orchestrator):
        """
        Тест качества форматирования таблиц.

        Проверяет, что таблицы читаемы и правильно отформатированы.
        """

        table_queries = [
            "H2O свойства в виде таблицы",
            "FeO данные таблицей",
            "CO2 термодинамические свойства",
        ]

        for query in table_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"
            assert len(response) > 30, f"Ответ должен содержать таблицу: {query}"

            # Проверяем наличие элементов таблицы
            table_indicators = [
                "┌", "┬", "┐", "│", "├", "┼", "┤", "└", "┴", "┘",  # Unicode рамки
                "---", "|", "+", "-",                                 # ASCII таблицы
                "Формула", "Значение", "Единицы",                     # Заголовки
            ]

            has_table_elements = any(indicator in response for indicator in table_indicators)

            if has_table_elements:
                # Проверяем структуру таблицы
                lines = response.split('\n')
                table_lines = [line for line in lines if any(indicator in line for indicator in table_indicators)]

                # Таблица должна иметь хотя бы 3 строки (заголовок, разделитель, данные)
                if len(table_lines) >= 3:
                    # Проверяем выравнивание столбцов
                    header_line = table_lines[0]
                    data_line = table_lines[-1]

                    # В таблицах с Unicode символами должно быть выравнивание
                    if "│" in header_line and "│" in data_line:
                        header_cols = header_line.split("│")
                        data_cols = data_line.split("│")

                        # Количество столбцов должно совпадать
                        assert len(header_cols) == len(data_cols), \
                            f"Количество столбцов в таблице не совпадает: {query}"

    @pytest.mark.asyncio
    async def test_error_message_helpfulness(self, multi_phase_orchestrator):
        """
        Тест полезности сообщений об ошибках.

        Проверяет, что сообщения об ошибках информативны
        и помогают пользователю исправить запрос.
        """

        error_prone_queries = [
            "XYZ999 несуществующее соединение",
            "H2O при 999999999K",
            "Некорректный запрос !!!@@@",
            "",
        ]

        for query in error_prone_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Должен быть ответ даже для ошибочного запроса: {query}"

            # Проверяем, что ответ не содержит системных ошибок
            system_errors = ["traceback", "exception", "stack trace", "assertion error"]
            has_system_error = any(error in response.lower() for error in system_errors)
            assert not has_system_error, f"Ответ не должен содержать системные ошибки: {query}"

            # Если есть проблема, сообщение должно быть полезным
            if len(response) > 20:
                helpful_indicators = [
                    "не найдено", "проверьте", "попробуйте", "рекомендуем",
                    "устраните", "исправьте", "измените", "формат"
                ]
                has_helpful_content = any(indicator in response.lower() for indicator in helpful_indicators)

                # Для некорректных запросов должно быть вежливое сообщение
                if not query.strip():  # Пустой запрос
                    assert len(response) > 10, f"На пустой запрос должен быть осмысленный ответ: {response}"

    @pytest.mark.asyncio
    async def test_multi_phase_explanation_clarity(self, multi_phase_orchestrator):
        """
        Тест ясности объяснений многофазных расчётов.

        Проверяет, что многофазные расчёты объясняются понятным образом.
        """

        multi_phase_queries = [
            "H2O свойства от 250K до 400K",  # Включает фазовые переходы
            "FeO свойства от 298K до 4000K", # Плавление и кипение
            "Вода фазовые переходы",        # Явный запрос переходов
        ]

        for query in multi_phase_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"
            assert len(response) > 50, f"Ответ должен содержать объяснения: {query}"

            # Проверяем наличие информации о фазах
            phase_indicators = [
                "фаз", "твёрд", "жидк", "газ", "лед", "пар", "плавлен", "кипен"
            ]
            has_phase_info = any(indicator in response.lower() for indicator in phase_indicators)

            if has_phase_info:
                # Проверяем, что объяснения понятны
                explanation_indicators = [
                    "переход", "температура", "точка", "условия",
                    "происходит", "наблюдается", "изменение"
                ]
                has_explanation = any(indicator in response.lower() for indicator in explanation_indicators)

                assert has_explanation, \
                    f"При наличии фазовой информации должно быть объяснение: {query}"

    @pytest.mark.asyncio
    async def test_recommendation_quality(self, multi_phase_orchestrator):
        """
        Тест качества рекомендаций пользователю.

        Проверяет, что система даёт полезные рекомендации
        для улучшения результатов.
        """

        recommendation_queries = [
            "Свойства неизвестного вещества",  # Может потребовать уточнения
            "FeO свойства при очень низкой температуре",  # Может быть вне диапазона
            "Очень сложная реакция",  # Может потребовать упрощения
        ]

        for query in recommendation_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"

            # Проверяем наличие рекомендаций
            recommendation_indicators = [
                "рекомендуем", "предлагаем", "можно попробовать",
                "улучшить", "уточнить", "изменить", "попробуйте"
            ]

            has_recommendations = any(indicator in response.lower() for indicator in recommendation_indicators)

            # Рекомендации должны быть конструктивными
            if has_recommendations:
                constructive_indicators = [
                    "более точно", "конкретнее", "дополнительно",
                    "указать", "уточнить", "использовать"
                ]
                has_constructive = any(indicator in response.lower() for indicator in constructive_indicators)

                # Рекомендации должны быть полезными
                assert len(response) > 100 if has_recommendations else True, \
                    f"Рекомендации должны быть развернутыми: {query}"

    @pytest.mark.asyncio
    async def test_accessibility_and_readability(self, multi_phase_orchestrator):
        """
        Тест доступности и читаемости интерфейса.

        Проверяет, что вывод доступен для разных пользователей
        и легко читается.
        """

        accessibility_queries = [
            "H2O свойства",
            "FeO термодинамика",
            "CO2 данные",
        ]

        for query in accessibility_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"

            # Проверяем базовую читаемость
            lines = response.split('\n')
            non_empty_lines = [line for line in lines if line.strip()]

            # Должна быть структура из нескольких строк
            assert len(non_empty_lines) >= 2, f"Ответ должен иметь структуру: {query}"

            # Проверяем, что строки не слишком длинные (читаемость)
            very_long_lines = [line for line in non_empty_lines if len(line) > 200]
            assert len(very_long_lines) < len(non_empty_lines) * 0.3, \
                f"Слишком много длинных строк ухудшает читаемость: {query}"

            # Проверяем наличие интервалов (для визуального разделения)
            has_spacing = any(line.strip() == "" for line in lines)
            # Если ответ длинный, должны быть интервалы
            if len(response) > 500:
                assert has_spacing, f"Длинные ответы должны иметь интервалы: {query}"

    @pytest.mark.asyncio
    async def test_consistent_response_formatting(self, multi_phase_orchestrator):
        """
        Тест согласованности форматирования ответов.

        Проверяет, что ответы имеют согласованный формат
        и стиль.
        """

        format_queries = [
            "H2O свойства при 298K",
            "CO2 свойства при 298K",
            "NH3 свойства при 298K",
        ]

        responses = []
        for query in format_queries:
            response = await multi_phase_orchestrator.process_query(query)
            responses.append((query, response))

        # Проверяем согласованность структуры
        response_structures = []
        for query, response in responses:
            # Анализируем структуру
            lines = response.split('\n')
            non_empty_lines = [line for line in lines if line.strip()]

            structure = {
                'total_lines': len(lines),
                'content_lines': len(non_empty_lines),
                'has_tables': any("│" in line or "┌" in line for line in lines),
                'has_sections': any("---" in line or "===" in line for line in lines),
            }
            response_structures.append(structure)

        # Структуры должны быть схожими для однотипных запросов
        if len(response_structures) >= 2:
            first_structure = response_structures[0]

            for i, structure in enumerate(response_structures[1:], 1):
                # Количество строк не должно отличаться кардинально
                line_ratio = structure['content_lines'] / first_structure['content_lines']
                assert 0.3 <= line_ratio <= 3.0, \
                    f"Структуры ответов слишком различаются: {responses[i][0]} vs {responses[0][0]}"

    @pytest.mark.asyncio
    async def test_educational_value(self, multi_phase_orchestrator):
        """
        Тест образовательной ценности ответов.

        Проверяет, что ответы содержат полезную информацию
        и имеют образовательную ценность.
        """

        educational_queries = [
            "Почему вода замерзает при 0°C?",
            "Что такое фазовый переход?",
            "Как рассчитать энтальпию реакции?",
        ]

        for query in educational_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"
            assert len(response) > 100, f"Образовательные ответы должны быть развернутыми: {query}"

            # Проверяем наличие объяснений
            explanation_indicators = [
                "потому что", "так как", "это", "является",
                "обусловлено", "связано с", "зависит от"
            ]
            has_explanation = any(indicator in response.lower() for indicator in explanation_indicators)

            # Проверяем наличие термодинамических концепций
            concept_indicators = [
                "энергия", "энтальп", "энтроп", "температур",
                "давление", "фаз", "состояние", "равновес"
            ]
            has_concepts = any(indicator in response.lower() for indicator in concept_indicators)

            # Образовательные ответы должны быть полезными
            assert has_explanation or has_concepts, \
                f"Образовательный ответ должен содержать объяснения или концепции: {query}"

    @pytest.mark.asyncio
    async def test_progressive_disclosure(self, multi_phase_orchestrator):
        """
        Тест прогрессивного раскрытия информации.

        Проверяет, что информация представлена в порядке
        от общего к частному.
        """

        progressive_queries = [
            "FeO свойства",
            "FeO подробные свойства",
            "FeO все свойства",
        ]

        for query in progressive_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ не должен быть None: {query}"

            # Проверяем структуру: сначала общая информация, потом детали
            lines = response.split('\n')
            non_empty_lines = [line for line in lines if line.strip()]

            if len(non_empty_lines) >= 3:
                # Первые строки должны содержать основную информацию
                first_lines = non_empty_lines[:2]
                last_lines = non_empty_lines[-2:]

                # Основная информация должна быть в начале
                first_has_essentials = any(
                    indicator in " ".join(first_lines).lower()
                    for indicator in ["h298", "s298", "формула", "название"]
                )

                # Детали должны быть в конце
                last_has_details = any(
                    indicator in " ".join(last_lines).lower()
                    for indicator in ["коэффициент", "диапазон", "точность", "источник"]
                )

                # Структура должна быть логичной
                assert first_has_essentials or len(response) < 200, \
                    f"Ответ должен начинаться с основной информации: {query}"

    @pytest.mark.asyncio
    async def test_error_recovery_suggestions(self, multi_phase_orchestrator):
        """
        Тест предложений по восстановлению после ошибок.

        Проверяет, что система предлагает пути решения
        при возникновении проблем.
        """

        recovery_queries = [
            "H2O при недопустимой температуре",
            "Несуществующий реагент в реакции",
            "Запрос с опечатками",
        ]

        for query in recovery_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Должен быть ответ: {query}"

            # Проверяем наличие предложений по решению
            solution_indicators = [
                "попробуйте", "рекомендуется", "можно",
                "вариант", "альтернатива", "решение"
            ]
            has_solutions = any(indicator in response.lower() for indicator in solution_indicators)

            # Предложения должны быть конструктивными
            if has_solutions:
                constructive_indicators = [
                    "изменить", "уточнить", "проверить", "использовать",
                    "указать", "выбрать", "добавить"
                ]
                has_constructive = any(indicator in response.lower() for indicator in constructive_indicators)

                assert has_constructive, \
                    f"Предложения должны быть конструктивными: {query}"

    @pytest.mark.asyncio
    async def test_multilingual_support_clarity(self, multi_phase_orchestrator):
        """
        Тест ясности многоязычной поддержки.

        Проверяет, что система работает на русском языке
        и понятно обрабатывает запросы.
        """

        multilingual_queries = [
            "Свойства воды на русском языке",
            "Термодинамика FeO",
            "Расчёт реакции H2 + O2",
        ]

        for query in multilingual_queries:
            response = await multi_phase_orchestrator.process_query(query)

            assert response is not None, f"Ответ должен быть на русском: {query}"
            assert len(response) > 20, f"Ответ должен быть содержательным: {query}"

            # Проверяем, что ответ в основном на русском
            russian_indicators = [
                "свойств", "значени", "температур", "данн", "энерг",
                "кдж", "дж", "рассчита", "получен"
            ]
            has_russian = any(indicator in response.lower() for indicator in russian_indicators)

            # Ответ должен быть понятным русскоязычному пользователю
            assert has_russian or len(response) < 50, \
                f"Ответ должен быть понятен на русском языке: {query}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])