#!/usr/bin/env python3
"""
Тестовый скрипт для проверки улучшенной системы логирования сессий v1.1
"""

import asyncio
import sys
from pathlib import Path

# Добавляем src в путь
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from thermo_agents.session_logger import SessionLogger


async def test_session_logging_v11():
    """Тестирование логирования сессии с улучшениями v1.1."""
    print("=== Тестирование SessionLogger v1.1 ===")

    # Создаем логгер сессии
    with SessionLogger() as logger:
        print(f"Создан логгер сессии: {logger.session_id}")
        print(f"Файл лога: {logger.log_file}")

        # Тест логирования LLM запроса
        logger.log_llm_request("расчет реакции 3H2S + Fe2O3 -> 3H2O + 2FeS при 773-973K с шагом 100K")

        # Тест логирования LLM ответа
        response = {
            "query_type": "REACTION_CALCULATION",
            "reaction_equation": "3H2S + Fe2O3 -> 3H2O + 2FeS",
            "temperature_start": 773,
            "temperature_end": 973,
            "temperature_step": 100,
            "pressure": None,
            "phases": None
        }
        logger.log_llm_response(response, duration=2.333, model="gpt-4-turbo", temperature=0.0, max_tokens=1000)

        # Тест улучшенного логирования поиска в БД
        sql_query = """
            SELECT
                c.compound_id,
                c.formula,
                c.name,
                c.phase,
                c.t_min,
                c.t_max,
                c.h298,
                c.s298,
                c.cp_a, c.cp_b, c.cp_c, c.cp_d, c.cp_e, c.cp_f
            FROM compounds c
            WHERE c.formula IN (?, ?, ?, ?)
                AND c.t_min <= ?
                AND c.t_max >= ?
            ORDER BY c.formula, c.phase
        """
        parameters = {
            "formulas": ["H2S", "Fe2O3", "H2O", "FeS"],
            "temp_min": 773,
            "temp_max": 973
        }
        results = [
            {
                "compound_id": 12345,
                "formula": "H2S",
                "name": "Hydrogen sulfide",
                "phase": "g",
                "t_min": 298,
                "t_max": 2000,
                "h298": -20.630,
                "s298": 205.81
            },
            {
                "compound_id": 12346,
                "formula": "Fe2O3",
                "name": "Iron(III) oxide",
                "phase": "s",
                "t_min": 298,
                "t_max": 950,
                "h298": -824.200,
                "s298": 87.400
            },
            {
                "compound_id": 12347,
                "formula": "Fe2O3",
                "name": "gamma-Iron(III) oxide",
                "phase": "s",
                "t_min": 273,
                "t_max": 760,  # Below target range - should show warning
                "h298": 0.000,   # Missing data - should show error
                "s298": 0.000    # Missing data - should show error
            },
            {
                "compound_id": 12348,
                "formula": "H2O",
                "name": "Hydrogen oxide",
                "phase": "g",
                "t_min": 298,
                "t_max": 6000,
                "h298": -241.826,
                "s298": 188.84
            },
            {
                "compound_id": 12349,
                "formula": "H2O",
                "name": "Hydrogen oxide",
                "phase": "l",
                "t_min": 273,
                "t_max": 647,   # Below target range - should show warning
                "h298": -285.830,
                "s298": 69.950
            },
            {
                "compound_id": 12350,
                "formula": "FeS",
                "name": "Iron(II) sulfide",
                "phase": "l",
                "t_min": 298,
                "t_max": 3000,
                "h298": -64.630,
                "s298": 91.206
            }
        ]

        logger.log_database_search(
            sql_query=sql_query,
            parameters=parameters,
            results=results,
            execution_time=0.152,
            context="Looking for compounds in reaction equation"
        )

        # Тест улучшенного логирования фильтрации
        logger.log_filtering_pipeline_start(
            input_count=len(results),
            target_temp_range=(773, 973),
            required_compounds=["H2S", "Fe2O3", "H2O", "FeS"]
        )

        # Этап 1: Температурная фильтрация с улучшенным логированием
        input_records = results.copy()
        output_records = [r for r in results if r["t_min"] <= 773 and r["t_max"] >= 973]
        removed_records = [r for r in results if r not in output_records]

        removal_reasons = {
            "t_max < 773 K": [
                "Fe2O3 (gamma-Iron(III) oxide, s, 273-760K) - insufficient coverage",
                "H2O (l, 273-647K) - maximum temperature too low"
            ],
            "Phase mismatch": [
                "H2O (l) - gas phase preferred at high temperature"
            ]
        }

        logger.log_filtering_stage(
            stage_name="Temperature Range Filter",
            stage_number=1,
            criteria={
                "t_min": "Record t_min <= 773 K (target start)",
                "t_max": "Record t_max >= 973 K (target end)",
                "range": "Accept partial overlap with [773, 973] range"
            },
            input_count=len(input_records),
            output_count=len(output_records),
            input_records=input_records,
            output_records=output_records,
            removal_reasons=removal_reasons
        )

        # Этап 2: Выбор фазы
        phase_output_records = output_records.copy()  # Assume no changes for simplicity

        logger.log_filtering_stage(
            stage_name="Phase State Filter",
            stage_number=2,
            criteria={
                "temperature": "Prefer phases stable at avg temperature (873 K)",
                "stoichiometry": "For reaction: detect expected phases from stoichiometry"
            },
            input_count=len(output_records),
            output_count=len(phase_output_records),
            input_records=output_records,
            output_records=phase_output_records,
            removal_reasons={}
        )

        # Тест валидации
        validation_results = {
            "all_compounds_present": True,
            "temperature_coverage": False,
            "phase_consistency": True,
            "data_quality": False
        }

        issues = [
            {
                "severity": "MEDIUM",
                "description": "Fe2O3: t_max=760K < required 973K (diff: 213K)",
                "impact": "Extrapolation required for 213K",
                "risk": "MEDIUM",
                "recommendations": [
                    "Search for alternative Fe2O3 records with higher t_max"
                ]
            },
            {
                "severity": "HIGH",
                "description": "Fe2O3: H298=0, S298=0",
                "impact": "May affect reaction enthalpy/entropy calculations",
                "risk": "HIGH",
                "recommendations": [
                    "Consider manual review for Fe2O3",
                    "Search for alternative data sources"
                ]
            }
        ]

        logger.log_validation_check(
            validation_results=validation_results,
            issues=issues
        )

        # Завершение фильтрации с улучшенными предупреждениями
        final_records = output_records
        warnings = [
            "Fe2O3: t_max (760K) below target range start (773K) - extrapolation needed",
            "Fe2O3: Missing critical thermodynamic data (H298, S298)",
            "H2O: t_max (647K) below target range start (773K) - extrapolation needed"
        ]

        logger.log_filtering_complete(
            final_count=len(final_records),
            initial_count=len(results),
            duration=0.658,
            warnings=warnings,
            final_records=final_records
        )

        print("OK: Логирование v1.1 завершено успешно!")

    print(f"\nFILE: Лог-файл создан: {logger.log_file}")
    print("\nНовые возможности v1.1:")
    print("  + Легенда символов в начале лога")
    print("  + Вывод SQL-запроса с параметрами")
    print("  + Phase distribution до/после каждого этапа")
    print("  + Top-3 причины отсева с примерами")
    print("  + Валидация с рекомендациями")
    print("  + Temperature warnings в таблицах")
    print("  + Critical data issues (H298=0, S298=0)")


if __name__ == "__main__":
    asyncio.run(test_session_logging_v11())