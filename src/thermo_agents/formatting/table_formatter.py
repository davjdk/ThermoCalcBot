"""
Форматирование таблиц результатов расчета с использованием rich.

Создает красивые таблицы с результатами термодинамических расчетов,
включая отметки фазовых переходов и интерпретацию спонтанности.
"""

import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
from rich.console import Console
from rich.table import Table
from rich.style import Style
from rich.text import Text


class TableFormatter:
    """
    Форматирование таблиц с результатами.
    """

    def __init__(self):
        self.console = Console()

    @staticmethod
    def determine_spontaneity(delta_g: float) -> str:
        """
        Определяет спонтанность реакции по ΔG.

        Args:
            delta_g: Энергия Гиббса в Дж/моль

        Returns:
            "Экзергоническая (⇑ спонтанная)" | "Эндергоническая (⇓ несп.)" | "Равновесие"
        """
        if abs(delta_g) < 1000:  # |ΔG| < 1 кДж/моль
            return "Равновесие"
        elif delta_g < 0:
            return "Экзергоническая (⇑ спонтанная)"
        else:
            return "Эндергоническая (⇓ несп.)"

    @staticmethod
    def format_phase_transition_comment(
        temperature: float,
        phase_transitions: Dict[str, List[Tuple[float, str, str]]]
    ) -> str:
        """
        Форматирует комментарий о фазовых переходах для температуры.

        Args:
            temperature: Текущая температура
            phase_transitions: Словарь фазовых переходов {formula: [(T, phase_from, phase_to)]}

        Returns:
            Отформатированный комментарий или пустая строка
        """
        comments = []

        for formula, transitions in phase_transitions.items():
            for T, phase_from, phase_to in transitions:
                # Если температура совпадает с температурой перехода (допуск ±10K)
                if abs(temperature - T) <= 10:
                    transition_names = {
                        ("s", "l"): "плавление",
                        ("l", "g"): "кипение",
                        ("s", "g"): "сублимация"
                    }
                    transition_key = (phase_from, phase_to)
                    transition_name = transition_names.get(transition_key, "переход")

                    comments.append(f"⚠ {formula}: {transition_name} ({phase_from} → {phase_to}) при {T:.0f}K")

        return "; ".join(comments)

    def format_reaction_table(
        self,
        df_result: pd.DataFrame,
        phase_transitions: Optional[Dict[str, List[Tuple[float, str, str]]]] = None
    ) -> str:
        """
        Форматирует таблицу результатов расчета реакции.

        Колонки:
        - T (K): Температура
        - ΔH° (кДж/моль): Энтальпия реакции
        - ΔS° (Дж/(К·моль)): Энтропия реакции
        - ΔG° (кДж/моль): Энергия Гиббса
        - Комментарий: Интерпретация (спонтанность, фазовые переходы)

        Фазовые переходы:
        - Отмечаются в строках, где T попадает в диапазон перехода
        - Формат: "⚠ {formula}: {transition_type} ({phase_from} → {phase_to}) при {T}K"

        Интерпретация ΔG:
        - ΔG < 0: "Экзергоническая (⇑ спонтанная)"
        - ΔG > 0: "Эндергоническая (⇓ несп.)"
        - ΔG ≈ 0 (|ΔG| < 1): "Равновесие"

        Args:
            df_result: DataFrame с колонками [T, delta_H, delta_S, delta_G, ln_K, K]
            phase_transitions: Словарь фазовых переходов для каждого вещества

        Returns:
            Отформатированная таблица
        """
        from tabulate import tabulate

        if phase_transitions is None:
            phase_transitions = {}

        # Подготавливаем данные для таблицы
        table_data = []
        headers = ["T(K)", "ΔH° (кДж/моль)", "ΔS° (Дж/(К·моль))", "ΔG° (кДж/моль)", "Комментарий"]

        for _, row in df_result.iterrows():
            T = row['T']
            delta_H = row['delta_H'] / 1000  # Конвертируем в кДж/моль
            delta_S = row['delta_S']
            delta_G = row['delta_G'] / 1000  # Конвертируем в кДж/моль

            # Определяем спонтанность
            spontaneity = self.determine_spontaneity(row['delta_G'])

            # Форматируем комментарий о фазовых переходах
            phase_comment = self.format_phase_transition_comment(T, phase_transitions)

            # Объединяем комментарии
            if phase_comment:
                comment = f"{spontaneity} | {phase_comment}"
            else:
                comment = spontaneity

            table_data.append([
                f"{T:.0f}",
                f"{delta_H:+.2f}",
                f"{delta_S:+.2f}",
                f"{delta_G:+.2f}",
                comment
            ])

        # Форматируем таблицу с tabulate
        formatted_table = tabulate(
            table_data,
            headers=headers,
            tablefmt="grid",
            stralign="center",
            numalign="decimal"
        )

        # Добавляем информацию о количестве точек
        num_points = len(df_result)
        result = formatted_table + f"\n\n{num_points} точек рассчитано"

        return result

    def format_simple_table(
        self,
        df_result: pd.DataFrame
    ) -> str:
        """
        Форматирует простую таблицу результатов без фазовых переходов.

        Args:
            df_result: DataFrame с результатами

        Returns:
            Отформатированная таблица
        """
        return self.format_reaction_table(df_result, {})

    def format_csv_export(
        self,
        df_result: pd.DataFrame
    ) -> str:
        """
        Форматирует данные для экспорта в CSV.

        Args:
            df_result: DataFrame с результатами

        Returns:
            CSV-отформатированная строка
        """
        # Копируем и преобразуем данные
        df_export = df_result.copy()
        df_export['ΔH° (кДж/моль)'] = df_export['delta_H'] / 1000
        df_export['ΔS° (Дж/(К·моль))'] = df_result['delta_S']
        df_export['ΔG° (кДж/моль)'] = df_result['delta_G'] / 1000

        # Выбираем нужные колонки для экспорта
        export_columns = ['T', 'ΔH° (кДж/моль)', 'ΔS° (Дж/(К·моль))', 'ΔG° (кДж/моль)', 'ln_K', 'K']
        df_export = df_export[export_columns]

        return df_export.to_csv(index=False, float_format='%.6f')

    def create_comparison_table(
        self,
        df_original: pd.DataFrame,
        df_reference: pd.DataFrame,
        tolerance: float = 1e-3
    ) -> str:
        """
        Создает таблицу сравнения с референсными данными.

        Args:
            df_original: Рассчитанные данные
            df_reference: Референсные данные
            tolerance: Допустимое относительное отклонение

        Returns:
            Таблица сравнения
        """
        table = Table(
            title="Сравнение с референсными данными",
            show_header=True,
            header_style="bold cyan",
            border_style="blue"
        )

        table.add_column("T(K)", justify="right", style="white", width=6)
        table.add_column("ΔG° (расч.)", justify="right", style="green", width=12)
        table.add_column("ΔG° (реф.)", justify="right", style="blue", width=12)
        table.add_column("Отклонение", justify="right", style="yellow", width=12)
        table.add_column("Статус", justify="center", width=10)

        # Сравниваем данные
        for _, row in df_original.iterrows():
            T = row['T']
            delta_G_calc = row['delta_G'] / 1000

            # Ищем соответствующую референсную точку
            ref_row = df_reference[df_reference['T'] == T]
            if not ref_row.empty:
                delta_G_ref = ref_row.iloc[0]['delta_G'] / 1000
                rel_error = abs(delta_G_calc - delta_G_ref) / abs(delta_G_ref) if delta_G_ref != 0 else 0

                if rel_error <= tolerance:
                    status = "✅ OK"
                    status_style = "green"
                elif rel_error <= tolerance * 10:
                    status = "⚠️ ПОХОЖЕ"
                    status_style = "yellow"
                else:
                    status = "❌ РАЗЛИЧИЕ"
                    status_style = "red"

                error_text = f"{rel_error:.2%}"

                table.add_row(
                    f"{T:.0f}",
                    f"{delta_G_calc:+.4f}",
                    f"{delta_G_ref:+.4f}",
                    error_text,
                    Text(status, style=status_style)
                )
            else:
                table.add_row(
                    f"{T:.0f}",
                    f"{delta_G_calc:+.4f}",
                    "—",
                    "—",
                    Text("❓ НЕТ ДАННЫХ", style="dim")
                )

        with self.console.capture() as capture:
            self.console.print(table)

        return capture.get()