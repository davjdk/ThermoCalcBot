"""
StatisticsFormatter - форматирование детальной статистики фильтрации.

Класс отвечает за представление статистики обработки результатов
в виде удобного для чтения дерева с информацией о каждой стадии.
"""

from typing import Dict
from ..models.aggregation import FilterStatistics


class StatisticsFormatter:
    """Форматирование детальной статистики фильтрации."""

    def format_detailed_statistics(
        self,
        detailed_statistics: Dict[str, FilterStatistics]
    ) -> str:
        """
        Форматирование дерева статистики для каждого вещества.

        Args:
            detailed_statistics: Словарь {формула: FilterStatistics}

        Returns:
            Отформатированная строка с деревом статистики
        """
        if not detailed_statistics:
            return "📈 Нет статистики для отображения"

        lines = ["📈 Детальная статистика фильтрации:", ""]

        for formula, stats in detailed_statistics.items():
            lines.append(f"{formula}:")

            # Стадия 1: Поиск по формуле
            lines.append(
                f"  ├─ Стадия 1 ({stats.stage_1_description}): "
                f"найдено {stats.stage_1_initial_matches} записей"
            )

            # Проверка провала на стадии 1
            if not stats.is_found and stats.failure_stage == 1:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason or 'Неизвестная ошибка'}"
                )
                lines.append("")
                continue

            # Стадия 2: Температурная фильтрация
            if stats.stage_2_temperature_filtered > 0:
                lines.append(
                    f"  ├─ Стадия 2 ({stats.stage_2_description}): "
                    f"осталось {stats.stage_2_temperature_filtered} записей"
                )
            else:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason or 'Отфильтровано по температуре'}"
                )
                lines.append("")
                continue

            # Проверка провала на стадии 2
            if not stats.is_found and stats.failure_stage == 2:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason or 'Ошибка на стадии 2'}"
                )
                lines.append("")
                continue

            # Стадия 3: Выбор фазы
            if stats.stage_3_phase_selected > 0:
                lines.append(
                    f"  ├─ Стадия 3 ({stats.stage_3_description}): "
                    f"осталось {stats.stage_3_phase_selected} записей"
                )
            else:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason or 'Нет подходящей фазы'}"
                )
                lines.append("")
                continue

            # Проверка провала на стадии 3
            if not stats.is_found and stats.failure_stage == 3:
                lines.append(
                    f"  └─ ❌ ВЕЩЕСТВО НЕ НАЙДЕНО: {stats.failure_reason or 'Ошибка на стадии 3'}"
                )
                lines.append("")
                continue

            # Стадия 4: Приоритезация
            lines.append(
                f"  └─ Стадия 4 ({stats.stage_4_description}): "
                f"выбрана {stats.stage_4_final_selected} {'запись' if stats.stage_4_final_selected == 1 else 'записи' if stats.stage_4_final_selected < 5 else 'записей'}"
            )

            # Добавить статус успеха
            if stats.is_found:
                lines.append("  ✅ ВЕЩЕСТВО УСПЕШНО НАЙДЕНО")

            lines.append("")

        # Удалить последний пустой символ
        if lines and lines[-1] == "":
            lines.pop()

        return "\n".join(lines)

    def format_summary_statistics(
        self,
        detailed_statistics: Dict[str, FilterStatistics]
    ) -> str:
        """
        Форматирование сводной статистики по всем веществам.

        Args:
            detailed_statistics: Словарь {формула: FilterStatistics}

        Returns:
            Отформатированная сводная статистика
        """
        if not detailed_statistics:
            return "📊 Нет статистики для отображения"

        total_compounds = len(detailed_statistics)
        found_compounds = sum(1 for stats in detailed_statistics.values() if stats.is_found)
        missing_compounds = total_compounds - found_compounds

        total_initial_matches = sum(stats.stage_1_initial_matches for stats in detailed_statistics.values())
        total_final_selected = sum(stats.stage_4_final_selected for stats in detailed_statistics.values())

        lines = [
            "📊 Сводная статистика обработки:",
            "",
            f"  Всего веществ: {total_compounds}",
            f"  Найдено: {found_compounds} ({(found_compounds/total_compounds*100):.1f}%)",
            f"  Отсутствует: {missing_compounds} ({(missing_compounds/total_compounds*100):.1f}%)",
            "",
            f"  Всего найденных записей: {total_initial_matches}",
            f"  Выбранных записей: {total_final_selected}",
            f"  Коэффициент отбора: {(total_final_selected/total_initial_matches*100):.1f}%" if total_initial_matches > 0 else "  Коэффициент отбора: 0%"
        ]

        return "\n".join(lines)

    def format_filtering_efficiency(
        self,
        detailed_statistics: Dict[str, FilterStatistics]
    ) -> str:
        """
        Форматирование статистики эффективности фильтрации.

        Args:
            detailed_statistics: Словарь {формула: FilterStatistics}

        Returns:
            Отформатированная статистика эффективности
        """
        if not detailed_statistics:
            return "⚡ Нет данных для анализа эффективности"

        stage_efficiency = {
            "stage_1_to_2": [],
            "stage_2_to_3": [],
            "stage_3_to_4": []
        }

        for stats in detailed_statistics.values():
            if stats.stage_1_initial_matches > 0:
                efficiency = (stats.stage_2_temperature_filtered / stats.stage_1_initial_matches) * 100
                stage_efficiency["stage_1_to_2"].append(efficiency)

            if stats.stage_2_temperature_filtered > 0:
                efficiency = (stats.stage_3_phase_selected / stats.stage_2_temperature_filtered) * 100
                stage_efficiency["stage_2_to_3"].append(efficiency)

            if stats.stage_3_phase_selected > 0:
                efficiency = (stats.stage_4_final_selected / stats.stage_3_phase_selected) * 100
                stage_efficiency["stage_3_to_4"].append(efficiency)

        lines = [
            "⚡ Эффективность стадий фильтрации:",
            ""
        ]

        stages = [
            ("Поиск → Температурная фильтрация", "stage_1_to_2"),
            ("Температурная → Фазовая фильтрация", "stage_2_to_3"),
            ("Фазовая → Приоритезация", "stage_3_to_4")
        ]

        for stage_name, stage_key in stages:
            efficiencies = stage_efficiency[stage_key]
            if efficiencies:
                avg_efficiency = sum(efficiencies) / len(efficiencies)
                lines.append(f"  {stage_name}: {avg_efficiency:.1f}% (в среднем)")
            else:
                lines.append(f"  {stage_name}: нет данных")

        return "\n".join(lines)