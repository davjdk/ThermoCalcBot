"""
Тест для воспроизведения бага поиска FeS → FeSiO3(G).

Этот тест воспроизводит конкретную проблему из лога сессии session_20251029_165401_15f01a.log,
где при поиске соединения FeS (сульфид железа(II) - Troilite) система неверно возвращает
FeSiO3(G) (метасиликат железа(II) - Garnet) вместо правильных записей FeS.

Проблема заключается в некорректной логике поиска по формуле, которая использует
containment search LIKE '%FeS%' и находит ложные совпадения с соединениями,
содержащими подстроку "FeS" но являющимися другими химическими соединениями.
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в путь для тестов
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline, FilterContext
from thermo_agents.filtering.filter_stages import (
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.complex_search_stage import ComplexFormulaSearchStage
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver


@pytest.fixture
def test_db_path():
    """Путь к тестовой базе данных."""
    # Find the database file
    db_paths = [
        Path("data/thermo_data.db"),
        Path("../data/thermo_data.db"),
        Path("../../data/thermo_data.db"),
    ]

    for path in db_paths:
        if path.exists():
            return path.resolve()

    pytest.skip("Thermodynamic database not found")


@pytest.fixture
def searcher(test_db_path):
    """Создает поисковик для тестов."""
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector(test_db_path)
    return CompoundSearcher(sql_builder, db_connector)


@pytest.fixture
def filter_pipeline():
    """Создает конвейер фильтрации для тестов."""
    pipeline = FilterPipeline()
    pipeline.add_stage(TemperatureFilterStage())

    temperature_resolver = TemperatureResolver()
    phase_resolver = PhaseResolver()

    pipeline.add_stage(PhaseSelectionStage(phase_resolver))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=1))
    pipeline.add_stage(TemperatureCoverageStage(temperature_resolver))

    return pipeline


class TestFeSSearchBug:
    """Тесты для воспроизведения и проверки исправления бага поиска FeS."""

    @pytest.mark.asyncio
    async def test_fes_search_bug_reproduction(self, searcher, filter_pipeline):
        """
        Воспроизводит баг из лога сессии.

        Запрос: FeS при температуре 773.0-973.0 K (500-700°C)
        Ожидаемый результат: FeS (Iron(II) sulfide - Troilite)
        Баговый результат: FeSiO3(G) (Iron(II) metasilicate - Garnet)
        """
        # Параметры из лога сессии
        formula = "FeS"
        temperature_range = (773.0, 973.0)  # 500-700°C в Кельвинах

        # Выполняем поиск
        result = searcher.search_compound(formula, temperature_range=temperature_range)

        # Базовые проверки результата
        assert result is not None
        assert result.compound_formula == formula
        assert len(result.records_found) > 0

        print(f"\n=== Результаты поиска для {formula} при {temperature_range} ===")
        print(f"Всего найдено записей: {len(result.records_found)}")

        # Анализ найденных записей
        fe_records = []
        fesio3_records = []
        other_records = []

        for record in result.records_found:
            if "FeS" in record.formula and "Si" not in record.formula:
                fe_records.append(record)
            elif "FeSiO3" in record.formula:
                fesio3_records.append(record)
            else:
                other_records.append(record)

        print(f"Записей с FeS (без Si): {len(fe_records)}")
        print(f"Записей с FeSiO3: {len(fesio3_records)}")
        print(f"Прочих записей: {len(other_records)}")

        # Показываем первые несколько записей каждого типа
        if fe_records:
            print("\n=== Записи FeS (ожидаемые результаты) ===")
            for i, record in enumerate(fe_records[:3]):
                print(f"{i+1}. {record.formula} (фаза: {record.phase}, t: {record.tmin}-{record.tmax})")

        if fesio3_records:
            print("\n=== Записи FeSiO3 (ошибочные результаты) ===")
            for i, record in enumerate(fesio3_records[:3]):
                print(f"{i+1}. {record.formula} (фаза: {record.phase}, t: {record.tmin}-{record.tmax})")

        # Проверяем наличие реальных записей FeS в базе данных
        with searcher.db_connector:
            direct_fes_query = """
                SELECT COUNT(*) as count
                FROM compounds
                WHERE TRIM(Formula) = 'FeS' OR Formula LIKE 'FeS(%'
            """
            direct_result = searcher.db_connector.execute_query(direct_fes_query)
            direct_fes_count = direct_result[0]['count'] if direct_result else 0

            direct_fesio3_query = """
                SELECT COUNT(*) as count
                FROM compounds
                WHERE TRIM(Formula) = 'FeSiO3' OR Formula LIKE 'FeSiO3(%'
            """
            direct_result2 = searcher.db_connector.execute_query(direct_fesio3_query)
            direct_fesio3_count = direct_result2[0]['count'] if direct_result2 else 0

        print(f"\n=== Прямая проверка в базе данных ===")
        print(f"Прямых записей FeS в БД: {direct_fes_count}")
        print(f"Прямых записей FeSiO3 в БД: {direct_fesio3_count}")

        # Воспроизводим фильтрацию из лога
        filter_context = FilterContext(
            temperature_range=temperature_range,
            compound_formula=formula
        )

        filter_result = filter_pipeline.execute(result.records_found, filter_context)

        print(f"\n=== Результаты фильтрации ===")
        if filter_result.filtered_records:
            final_record = filter_result.filtered_records[0]
            print(f"Финальная запись: {final_record.formula} (фаза: {final_record.phase})")

            # Это и есть баг - если финальная запись FeSiO3 вместо FeS
            if "Si" in final_record.formula:
                print("BUG REPRODUCED: Система выбрала FeSiO3 вместо FeS")
                # В реальном баге система выбирала FeSiO3(G)
                assert False, f"Баг воспроизведен: вместо FeS выбрано {final_record.formula}"
            else:
                print("BUG FIXED: Система выбрала корректную запись FeS")
        else:
            print("⚠️  Фильтрация не вернула результатов")

    def test_fes_database_availability(self, searcher):
        """
        Проверяет доступность записей FeS в базе данных.

        Этот тест подтверждает, что в базе данных существуют записи FeS,
        которые должны быть найдены при поиске.
        """
        with searcher.db_connector:
            # Ищем все варианты записей FeS
            fes_variants_query = """
                SELECT Formula, Phase, COUNT(*) as count
                FROM compounds
                WHERE Formula LIKE 'FeS%'
                   OR TRIM(Formula) = 'FeS'
                   OR Formula LIKE 'FeS(%'
                GROUP BY Formula, Phase
                ORDER BY count DESC
            """
            fes_records = searcher.db_connector.execute_query(fes_variants_query)

            print(f"\n=== Варианты записей FeS в базе данных ===")
            total_fes = 0
            for record in fes_records:
                print(f"{record['Formula']} (фаза: {record['Phase']}): {record['count']} записей")
                total_fes += record['count']

            print(f"Всего записей FeS: {total_fes}")

            # Должны быть записи FeS в базе данных
            assert total_fes > 0, "В базе данных отсутствуют записи FeS"

            # Проверяем температурные диапазоны для FeS
            temp_range_query = """
                SELECT Tmin, Tmax, Phase, COUNT(*) as count
                FROM compounds
                WHERE (TRIM(Formula) = 'FeS' OR Formula LIKE 'FeS(%')
                  AND Tmin IS NOT NULL AND Tmax IS NOT NULL
                GROUP BY Tmin, Tmax, Phase
                ORDER BY Tmin
            """
            temp_records = searcher.db_connector.execute_query(temp_range_query)

            print(f"\n=== Температурные диапазоны для FeS ===")
            for record in temp_records[:5]:  # Первые 5 диапазонов
                print(f"Фаза {record['Phase']}: {record['Tmin']}-{record['Tmax']} K ({record['count']} записей)")

            # Проверяем, есть ли записи перекрывающие наш диапазон 773-973K
            overlapping = [
                r for r in temp_records
                if r['Tmin'] <= 973.0 and r['Tmax'] >= 773.0
            ]

            print(f"Записей FeS в диапазоне 773-973K: {sum(r['count'] for r in overlapping)}")
            assert len(overlapping) > 0, "Нет записей FeS в нужном температурном диапазоне"

    def test_fesio3_false_positive_detection(self, searcher):
        """
        Проверяет, что поиск FeS неверно находит FeSiO3 как ложноположительное совпадение.

        Этот тест демонстрирует проблему в логике поиска, где containment search
        LIKE '%FeS%' находит FeSiO3, которое содержит подстроку "FeS" но является
        совершенно другим химическим соединением.
        """
        with searcher.db_connector:
            # Проверяем SQL запрос, который генерирует поиск FeS
            sql_query, params = searcher.sql_builder.build_compound_search_query(
                formula='FeS',
                temperature_range=(773.0, 973.0),
                limit=100
            )

            print(f"\n=== SQL запрос для поиска FeS ===")
            print(f"Query: {sql_query}")
            print(f"Params: {params}")

            # Выполняем запрос и анализируем результаты
            results = searcher.db_connector.execute_query(sql_query, params)

            fe_matches = 0
            fesio3_matches = 0
            false_positives = 0

            print(f"\n=== Анализ результатов SQL запроса ===")
            for record in results[:10]:  # Первые 10 результатов
                formula = record.get('Formula', '')
                if 'FeS' in formula and 'Si' not in formula:
                    fe_matches += 1
                    print(f"CORRECT: {formula}")
                elif 'FeSiO3' in formula:
                    fesio3_matches += 1
                    false_positives += 1
                    print(f"FALSE POSITIVE: {formula} (содержит 'FeS' но это FeSiO3)")
                else:
                    print(f"UNCERTAIN: {formula}")

            print(f"\n=== Статистика совпадений ===")
            print(f"Корректных совпадений FeS: {fe_matches}")
            print(f"Ложноположительных совпадений: {false_positives}")
            print(f"Всего проанализировано: {min(10, len(results))} из {len(results)}")

            # Если есть ложноположительные совпадения, это подтверждает баг
            if false_positives > 0:
                print("BUG CONFIRMED: SQL запрос находит ложноположительные совпадения")
                # Это и есть корень проблемы - containment search находит не те соединения
            else:
                print("NO FALSE POSITIVES: Ложноположительных совпадений не обнаружено")

    def test_formula_classification_logic(self, searcher):
        """
        Проверяет логику классификации формул в SQL Builder.

        FeS должна классифицироваться как простая формула для точного поиска,
        а не как сложная формула, требующая containment search.
        """
        # Тестируем различные формулы
        test_formulas = [
            ('FeS', True),    # Должна быть простой (бинарное соединение)
            ('FeO', True),    # Простая
            ('H2O', True),    # Простая
            ('CO2', True),    # Простая
            ('FeSiO3', False), # Сложная (соединение трех элементов)
            ('H2SO4', False),  # Сложная
        ]

        print(f"\n=== Тест классификации формул ===")

        for formula, should_be_simple in test_formulas:
            # Проверяем, как система классифицирует эти формулы
            sql_query, _ = searcher.sql_builder.build_compound_search_query(
                formula=formula,
                limit=10
            )

            # Анализируем тип поиска по SQL запросу
            uses_exact_match = "TRIM(Formula) = ?" in sql_query
            uses_prefix_search = "Formula LIKE ? || '(%'" in sql_query
            uses_containment = "LIKE '%" in sql_query and not uses_prefix_search

            is_simple = uses_exact_match or uses_prefix_search
            is_complex = uses_containment

            print(f"{formula}:")
            print(f"  Ожидается: {'простая' if should_be_simple else 'сложная'}")
            print(f"  Определено как: {'простая' if is_simple else 'сложная'}")
            print(f"  Использует точный поиск: {uses_exact_match}")
            print(f"  Использует префиксный поиск: {uses_prefix_search}")
            print(f"  Использует containment search: {uses_containment}")

            if should_be_simple and is_complex:
                print(f"  ERROR: {formula} должна быть простой")
            elif not should_be_simple and is_simple:
                print(f"  WARNING: {formula} может быть сложной")
            else:
                print(f"  OK: Классификация корректна")

            print()

    def test_multi_level_search_strategy(self, searcher):
        """
        Тестирует многоуровневую стратегию поиска для FeS.

        Согласно отчету об анализе базы данных, должна использоваться стратегия:
        1. Точный поиск TRIM(Formula) = 'FeS'
        2. Префиксный поиск Formula LIKE 'FeS(%'
        3. Containment поиск только как последняя мера
        """
        print(f"\n=== Тест многоуровневой стратегии поиска для FeS ===")

        # Уровень 1: Точный поиск
        with searcher.db_connector:
            exact_query = "SELECT COUNT(*) as count FROM compounds WHERE TRIM(Formula) = 'FeS'"
            exact_result = searcher.db_connector.execute_query(exact_query)
            exact_count = exact_result[0]['count'] if exact_result else 0

            print(f"Уровень 1 - Точный поиск: {exact_count} записей")

            # Уровень 2: Префиксный поиск (с фазами в скобках)
            prefix_query = "SELECT COUNT(*) as count FROM compounds WHERE Formula LIKE 'FeS(%'"
            prefix_result = searcher.db_connector.execute_query(prefix_query)
            prefix_count = prefix_result[0]['count'] if prefix_result else 0

            print(f"Уровень 2 - Префиксный поиск: {prefix_count} записей")

            # Уровень 3: Containment поиск (проблемный)
            containment_query = "SELECT COUNT(*) as count FROM compounds WHERE Formula LIKE '%FeS%'"
            containment_result = searcher.db_connector.execute_query(containment_query)
            containment_count = containment_result[0]['count'] if containment_result else 0

            print(f"Уровень 3 - Containment поиск: {containment_count} записей")

            # Проверяем, сколько из containment поиска являются ложными срабатываниями
            false_positive_query = """
                SELECT COUNT(*) as count
                FROM compounds
                WHERE Formula LIKE '%FeS%'
                  AND Formula NOT LIKE 'FeS%'
                  AND Formula NOT LIKE '%(FeS%'
                  AND TRIM(Formula) != 'FeS'
            """
            false_positive_result = searcher.db_connector.execute_query(false_positive_query)
            false_positive_count = false_positive_result[0]['count'] if false_positive_result else 0

            print(f"Ложноположительных срабатываний: {false_positive_count}")

            # Анализ результатов
            total_direct = exact_count + prefix_count
            print(f"\n=== Анализ стратегии ===")
            print(f"Прямых совпадений (точный + префиксный): {total_direct}")
            print(f"Containment совпадений: {containment_count}")
            print(f"Ложных срабатываний в containment: {false_positive_count}")

            if false_positive_count > 0:
                print("PROBLEM: Containment поиск создает ложные срабатывания")
                print("SOLUTION: Не использовать containment поиск для простых формул типа FeS")

            if total_direct > 0:
                print("OK: Есть достаточное количество прямых совпадений")
                print("SOLUTION: Использовать только точный и префиксный поиск для FeS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])