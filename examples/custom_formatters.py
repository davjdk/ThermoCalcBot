"""
Пример создания кастомных форматтеров для термодинамических данных.

Демонстрирует различные способы форматирования результатов:
таблицы, CSV, JSON, HTML отчеты и т.д.
"""

import asyncio
import json
import csv
import sys
from pathlib import Path
from io import StringIO
from typing import List, Dict, Any

# Добавляем src в путь
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.search.sql_builder import SQLBuilder
from thermo_agents.search.database_connector import DatabaseConnector
from thermo_agents.search.compound_searcher import CompoundSearcher
from thermo_agents.filtering.filter_pipeline import FilterPipeline, FilterContext
from thermo_agents.filtering.filter_stages import (
    ComplexFormulaSearchStage,
    TemperatureFilterStage,
    PhaseSelectionStage,
    ReliabilityPriorityStage,
    TemperatureCoverageStage
)
from thermo_agents.filtering.temperature_resolver import TemperatureResolver
from thermo_agents.filtering.phase_resolver import PhaseResolver
from thermo_agents.aggregation.reaction_aggregator import ReactionAggregator
from thermo_agents.models.search import CompoundSearchResult, DatabaseRecord
from tabulate import tabulate


class CSVFormatter:
    """Кастомный форматтер для экспорта в CSV."""

    def format_compounds_to_csv(self, results: List[CompoundSearchResult]) -> str:
        """Форматирует результаты поиска в CSV."""
        output = StringIO()
        writer = csv.writer(output)

        # Заголовки
        headers = [
            'Compound', 'Formula', 'Phase', 'Tmin_K', 'Tmax_K',
            'H298_kJ/mol', 'S298_J/mol*K', 'Reliability', 'Source'
        ]
        writer.writerow(headers)

        # Данные
        for result in results:
            if result.records_found:
                for record in result.records_found:
                    row = [
                        result.compound,
                        record.get('Formula', ''),
                        record.get('Phase', ''),
                        record.get('Tmin', ''),
                        record.get('Tmax', ''),
                        record.get('H298', ''),
                        record.get('S298', ''),
                        record.get('ReliabilityClass', ''),
                        record.get('Source', '')
                    ]
                    writer.writerow(row)

        return output.getvalue()


class JSONFormatter:
    """Кастомный форматтер для экспорта в JSON."""

    def format_compounds_to_json(self, results: List[CompoundSearchResult]) -> str:
        """Форматирует результаты поиска в JSON."""
        data = {
            'compounds': [],
            'summary': {
                'total_compounds': len(results),
                'total_records': sum(len(r.records_found) for r in results),
                'export_timestamp': str(Path(__file__).stat().st_mtime)
            }
        }

        for result in results:
            compound_data = {
                'compound': result.compound,
                'is_found': result.is_found,
                'search_statistics': result.search_statistics.__dict__ if result.search_statistics else None,
                'records': []
            }

            for record in result.records_found:
                record_data = {
                    'formula': record.get('Formula'),
                    'phase': record.get('Phase'),
                    'temperature_range': {
                        'min': record.get('Tmin'),
                        'max': record.get('Tmax')
                    },
                    'thermodynamic_properties': {
                        'H298': record.get('H298'),
                        'S298': record.get('S298'),
                        'f1': record.get('f1'),
                        'f2': record.get('f2'),
                        'f3': record.get('f3'),
                        'f4': record.get('f4'),
                        'f5': record.get('f5'),
                        'f6': record.get('f6')
                    },
                    'phase_data': {
                        'melting_point': record.get('MeltingPoint'),
                        'boiling_point': record.get('BoilingPoint')
                    },
                    'metadata': {
                        'reliability_class': record.get('ReliabilityClass'),
                        'source': record.get('Source'),
                        'first_name': record.get('FirstName')
                    }
                }
                compound_data['records'].append(record_data)

            data['compounds'].append(compound_data)

        return json.dumps(data, indent=2, ensure_ascii=False)


class HTMLFormatter:
    """Кастомный форматтер для создания HTML отчетов."""

    def format_compounds_to_html(self, results: List[CompoundSearchResult],
                                 title: str = "Thermodynamic Data Report") -> str:
        """Форматирует результаты поиска в HTML."""

        def format_table(records: List[Dict]) -> str:
            """Создает HTML таблицу."""
            if not records:
                return "<p>No data available</p>"

            headers = [
                'Formula', 'Phase', 'Tmin (K)', 'Tmax (K)',
                'H298 (kJ/mol)', 'S298 (J/mol·K)', 'Reliability'
            ]

            rows = []
            for record in records:
                row = [
                    record.get('Formula', ''),
                    record.get('Phase', ''),
                    record.get('Tmin', ''),
                    record.get('Tmax', ''),
                    record.get('H298', ''),
                    record.get('S298', ''),
                    record.get('ReliabilityClass', '')
                ]
                rows.append(row)

            return tabulate(rows, headers=headers, tablefmt='html')

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background-color: #f4f4f4; padding: 20px; border-radius: 5px; }}
        .compound-section {{ margin: 20px 0; border: 1px solid #ddd; border-radius: 5px; }}
        .compound-header {{ background-color: #e9ecef; padding: 15px; font-weight: bold; }}
        .compound-content {{ padding: 15px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .summary {{ background-color: #d4edda; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .error {{ color: #721c24; background-color: #f8d7da; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{title}</h1>
        <p>Generated on {Path(__file__).stat().st_mtime}</p>
    </div>

    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total Compounds:</strong> {len(results)}</p>
        <p><strong>Total Records:</strong> {sum(len(r.records_found) for r in results)}</p>
    </div>
"""

        for result in results:
            html += f"""
    <div class="compound-section">
        <div class="compound-header">
            📊 Compound: {result.compound}
            {' ✅ Found' if result.is_found else ' ❌ Not Found'}
        </div>
        <div class="compound-content">
            {format_table(result.records_found) if result.records_found else '<p class="error">No records found</p>'}
        </div>
    </div>
"""

        html += """
</body>
</html>
"""
        return html


class MarkdownFormatter:
    """Кастомный форматтер для Markdown отчетов."""

    def format_compounds_to_markdown(self, results: List[CompoundSearchResult],
                                    title: str = "Thermodynamic Data Report") -> str:
        """Форматирует результаты поиска в Markdown."""

        markdown = f"# {title}\n\n"
        markdown += f"**Total Compounds:** {len(results)}\n"
        markdown += f"**Total Records:** {sum(len(r.records_found) for r in results)}\n\n"

        for result in results:
            status = "✅ Found" if result.is_found else "❌ Not Found"
            markdown += f"## 📊 Compound: {result.compound} {status}\n\n"

            if result.records_found:
                # Создаем таблицу
                headers = [
                    'Formula', 'Phase', 'Tmin (K)', 'Tmax (K)',
                    'H298 (kJ/mol)', 'S298 (J/mol·K)', 'Reliability'
                ]

                rows = []
                for record in result.records_found[:10]:  # Ограничиваем до 10 записей
                    row = [
                        record.get('Formula', ''),
                        record.get('Phase', ''),
                        record.get('Tmin', ''),
                        record.get('Tmax', ''),
                        record.get('H298', ''),
                        record.get('S298', ''),
                        record.get('ReliabilityClass', '')
                    ]
                    rows.append(row)

                table = tabulate(rows, headers=headers, tablefmt='github')
                markdown += f"{table}\n\n"

                if len(result.records_found) > 10:
                    markdown += f"*... and {len(result.records_found) - 10} more records*\n\n"
            else:
                markdown += "> No records found\n\n"

        return markdown


class BriefTextFormatter:
    """Краткий текстовый форматтер для консольного вывода."""

    def format_compounds_brief(self, results: List[CompoundSearchResult]) -> str:
        """Форматирует результаты в кратком текстовом виде."""
        lines = []

        for result in results:
            if result.is_found and result.records_found:
                lines.append(f"📊 {result.compound}: ✅ {len(result.records_found)} records")

                # Показываем лучшую запись
                best_record = result.records_found[0]
                lines.append(f"   🎯 Best: {best_record.get('Formula', 'N/A')} "
                           f"({best_record.get('Phase', 'N/A')}) "
                           f"{best_record.get('Tmin', 'N/A')}-{best_record.get('Tmax', 'N/A')}K")
            else:
                lines.append(f"📊 {result.compound}: ❌ Not found")

        return "\n".join(lines)


async def get_sample_data():
    """Получает примеры данных для демонстрации."""
    # Инициализация
    sql_builder = SQLBuilder()
    db_connector = DatabaseConnector("data/thermo_data.db")
    compound_searcher = CompoundSearcher(sql_builder, db_connector)

    # Конвейер фильтрации
    pipeline = FilterPipeline()
    pipeline.add_stage(ComplexFormulaSearchStage(db_connector, sql_builder))
    pipeline.add_stage(TemperatureFilterStage())
    pipeline.add_stage(PhaseSelectionStage(PhaseResolver()))
    pipeline.add_stage(ReliabilityPriorityStage(max_records=3))

    compounds = ["H2O", "CO2", "Fe"]
    temp_range = (298, 500)

    results = []

    for compound in compounds:
        try:
            search_result = compound_searcher.search_compound(compound, temp_range)

            if search_result:
                # Фильтрация
                filter_context = FilterContext(
                    temperature_range=temp_range,
                    compound_formula=compound
                )
                filter_result = pipeline.execute(search_result.records_found, filter_context)

                if filter_result and filter_result.filtered_records:
                    search_result.records_found = filter_result.filtered_records

            results.append(search_result)

        except Exception as e:
            print(f"Error processing {compound}: {e}")

    return results


async def demo_csv_formatting(results):
    """Демонстрация CSV форматирования."""
    print("📄 Демонстрация CSV форматирования")
    print("=" * 60)

    formatter = CSVFormatter()
    csv_output = formatter.format_compounds_to_csv(results)

    print("Первые строки CSV:")
    print("-" * 30)
    lines = csv_output.split('\n')[:10]
    for line in lines:
        print(line)

    # Сохранение в файл
    output_file = Path("examples/thermodynamic_data.csv")
    output_file.write_text(csv_output, encoding='utf-8')
    print(f"\n💾 Сохранено в: {output_file}")
    print()


async def demo_json_formatting(results):
    """Демонстрация JSON форматирования."""
    print("📋 Демонстрация JSON форматирования")
    print("=" * 60)

    formatter = JSONFormatter()
    json_output = formatter.format_compounds_to_json(results)

    # Показываем начало JSON
    lines = json_output.split('\n')[:20]
    for line in lines:
        print(line)
    if len(json_output.split('\n')) > 20:
        print("... (продолжение)")

    # Сохранение в файл
    output_file = Path("examples/thermodynamic_data.json")
    output_file.write_text(json_output, encoding='utf-8')
    print(f"\n💾 Сохранено в: {output_file}")
    print()


async def demo_html_formatting(results):
    """Демонстрация HTML форматирования."""
    print("🌐 Демонстрация HTML форматирования")
    print("=" * 60)

    formatter = HTMLFormatter()
    html_output = formatter.format_compounds_to_html(results,
                                                      "Thermodynamic Data Demo")

    # Сохранение в файл
    output_file = Path("examples/thermodynamic_data.html")
    output_file.write_text(html_output, encoding='utf-8')
    print(f"💾 Сохранено в: {output_file}")
    print("🌐 Откройте файл в браузере для просмотра")
    print()


async def demo_markdown_formatting(results):
    """Демонстрация Markdown форматирования."""
    print("📝 Демонстрация Markdown форматирования")
    print("=" * 60)

    formatter = MarkdownFormatter()
    markdown_output = formatter.format_compounds_to_markdown(results,
                                                             "Thermodynamic Data Demo")

    # Показываем начало Markdown
    lines = markdown_output.split('\n')[:30]
    for line in lines:
        print(line)
    if len(markdown_output.split('\n')) > 30:
        print("... (продолжение)")

    # Сохранение в файл
    output_file = Path("examples/thermodynamic_data.md")
    output_file.write_text(markdown_output, encoding='utf-8')
    print(f"\n💾 Сохранено в: {output_file}")
    print()


async def demo_brief_formatting(results):
    """Демонстрация краткого форматирования."""
    print("📋 Демонстрация краткого форматирования")
    print("=" * 60)

    formatter = BriefTextFormatter()
    brief_output = formatter.format_compounds_brief(results)

    print(brief_output)
    print()


async def main():
    """Главная функция демонстрации кастомных форматтеров."""
    print("🚀 Термодинамическая система v2.0 - Кастомные форматтеры")
    print("=" * 60)
    print()

    # Получаем данные
    print("📊 Получение примеров данных...")
    results = await get_sample_data()

    if not results:
        print("❌ Не удалось получить данные для демонстрации")
        return

    print(f"✅ Получено данных для {len(results)} соединений")
    print()

    # Демонстрации
    await demo_brief_formatting(results)
    await demo_csv_formatting(results)
    await demo_json_formatting(results)
    await demo_markdown_formatting(results)
    await demo_html_formatting(results)

    print("=" * 60)
    print("✅ Демонстрация кастомных форматтеров завершена")
    print("💾 Все форматы сохранены в папке examples/")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())