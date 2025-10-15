#!/usr/bin/env python3
"""
Stage 0: Filtering Strategy Prototype
This script implements the prototype filtering stages based on database analysis results.
"""

import sqlite3
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import json

@dataclass
class FilterStats:
    """Statistics for filtering stages."""
    stage_name: str
    input_count: int
    output_count: int
    filtered_count: int
    execution_time: float
    details: Dict[str, Any]

@dataclass
class CompoundRecord:
    """Represents a compound record from the database."""
    formula: str
    phase: Optional[str]
    tmin: float
    tmax: float
    melting_point: float
    boiling_point: float
    reliability_class: int
    h298: float
    s298: float
    f1: float
    f2: float
    f3: float
    f4: float
    f5: float
    f6: float
    first_name: Optional[str]
    second_name: Optional[str]

class DatabaseConnector:
    """Database connection and query execution."""

    def __init__(self, db_path: str = "data/thermo_data.db"):
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        return self.conn

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def execute_query(self, query: str, params: tuple = None) -> List[CompoundRecord]:
        """Execute query and return compound records."""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        rows = cursor.fetchall()
        return [CompoundRecord(*row) for row in rows]

class FormulaMatchStage:
    """Stage 1: Formula matching with phase handling."""

    def __init__(self, db_connector: DatabaseConnector):
        self.db = db_connector
        self.stats = None

    def filter(self, formula: str, target_phase: Optional[str] = None) -> Tuple[List[CompoundRecord], FilterStats]:
        """Filter compounds by formula with phase matching."""
        import time
        start_time = time.time()

        # Build query based on formula matching strategy
        if target_phase:
            query = """
            SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint,
                   ReliabilityClass, H298, S298, f1, f2, f3, f4, f5, f6,
                   FirstName, SecondName
            FROM compounds
            WHERE (TRIM(Formula) = ? OR Formula LIKE ?)
              AND Phase = ?
            ORDER BY ReliabilityClass ASC
            """
            params = (formula.strip(), f"{formula.strip()}(%", target_phase)
        else:
            query = """
            SELECT Formula, Phase, Tmin, Tmax, MeltingPoint, BoilingPoint,
                   ReliabilityClass, H298, S298, f1, f2, f3, f4, f5, f6,
                   FirstName, SecondName
            FROM compounds
            WHERE TRIM(Formula) = ? OR Formula LIKE ?
            ORDER BY ReliabilityClass ASC
            """
            params = (formula.strip(), f"{formula.strip()}(%")

        results = self.db.execute_query(query, params)

        execution_time = time.time() - start_time
        self.stats = FilterStats(
            stage_name="FormulaMatchStage",
            input_count=0,  # We don't track total DB size
            output_count=len(results),
            filtered_count=0,
            execution_time=execution_time,
            details={
                "formula": formula,
                "target_phase": target_phase,
                "query": query,
                "unique_formulas": len(set(r.formula for r in results))
            }
        )

        return results, self.stats

class TemperatureFilterStage:
    """Stage 2: Temperature range filtering."""

    def __init__(self):
        self.stats = None

    def filter(self, compounds: List[CompoundRecord], temperature: float) -> Tuple[List[CompoundRecord], FilterStats]:
        """Filter compounds by temperature range."""
        import time
        start_time = time.time()

        filtered = []
        for compound in compounds:
            if compound.tmin <= temperature <= compound.tmax:
                filtered.append(compound)

        execution_time = time.time() - start_time
        self.stats = FilterStats(
            stage_name="TemperatureFilterStage",
            input_count=len(compounds),
            output_count=len(filtered),
            filtered_count=len(compounds) - len(filtered),
            execution_time=execution_time,
            details={
                "temperature": temperature,
                "temp_coverage_ratio": len(filtered) / len(compounds) if compounds else 0
            }
        )

        return filtered, self.stats

class PhaseSelectionStage:
    """Stage 3: Intelligent phase selection based on temperature."""

    def __init__(self):
        self.stats = None

    def filter(self, compounds: List[CompoundRecord], temperature: float,
               target_phase: Optional[str] = None) -> Tuple[List[CompoundRecord], FilterStats]:
        """Select appropriate phase based on temperature and user preference."""
        import time
        start_time = time.time()

        if not compounds:
            empty_stats = FilterStats(
                stage_name="PhaseSelectionStage",
                input_count=0,
                output_count=0,
                filtered_count=0,
                execution_time=time.time() - start_time,
                details={"temperature": temperature, "target_phase": target_phase}
            )
            return [], empty_stats

        # If target phase is specified, prioritize it
        if target_phase:
            target_compounds = [c for c in compounds if c.phase == target_phase]
            if target_compounds:
                selected = target_compounds
            else:
                # Fall back to temperature-based selection
                selected = self._select_by_temperature(compounds, temperature)
        else:
            # Use temperature-based phase selection
            selected = self._select_by_temperature(compounds, temperature)

        execution_time = time.time() - start_time
        self.stats = FilterStats(
            stage_name="PhaseSelectionStage",
            input_count=len(compounds),
            output_count=len(selected),
            filtered_count=len(compounds) - len(selected),
            execution_time=execution_time,
            details={
                "temperature": temperature,
                "target_phase": target_phase,
                "selected_phases": list(set(c.phase for c in selected)),
                "selection_strategy": "target_phase_priority" if target_phase else "temperature_based"
            }
        )

        return selected, self.stats

    def _select_by_temperature(self, compounds: List[CompoundRecord], temperature: float) -> List[CompoundRecord]:
        """Select phase based on temperature and phase transition data."""
        selected = []

        for compound in compounds:
            if compound.melting_point and compound.boiling_point:
                # Use melting/boiling points for phase determination
                if temperature < compound.melting_point:
                    # Solid phase expected
                    if compound.phase in ['s', 'a']:
                        selected.append(compound)
                elif temperature < compound.boiling_point:
                    # Liquid phase expected
                    if compound.phase in ['l']:
                        selected.append(compound)
                else:
                    # Gas phase expected
                    if compound.phase in ['g']:
                        selected.append(compound)
            else:
                # Fallback to current phase
                selected.append(compound)

        # If no temperature-based selection, return all compounds
        if not selected:
            selected = compounds

        return selected

class ReliabilityPriorityStage:
    """Stage 4: Priority sorting by reliability class."""

    def __init__(self):
        self.stats = None

    def filter(self, compounds: List[CompoundRecord]) -> Tuple[List[CompoundRecord], FilterStats]:
        """Sort compounds by reliability class and remove duplicates."""
        import time
        start_time = time.time()

        # Sort by reliability class (lower is better)
        sorted_compounds = sorted(compounds, key=lambda x: x.reliability_class)

        # Remove duplicates (same formula and phase) keeping the most reliable
        seen = set()
        deduplicated = []
        for compound in sorted_compounds:
            key = (compound.formula, compound.phase)
            if key not in seen:
                seen.add(key)
                deduplicated.append(compound)

        execution_time = time.time() - start_time
        self.stats = FilterStats(
            stage_name="ReliabilityPriorityStage",
            input_count=len(compounds),
            output_count=len(deduplicated),
            filtered_count=len(compounds) - len(deduplicated),
            execution_time=execution_time,
            details={
                "duplicates_removed": len(compounds) - len(deduplicated),
                "reliability_classes": list(set(c.reliability_class for c in deduplicated)),
                "best_reliability": min(c.reliability_class for c in deduplicated) if deduplicated else None
            }
        )

        return deduplicated, self.stats

class FilterPipeline:
    """Complete filtering pipeline with statistics collection."""

    def __init__(self, db_path: str = "data/thermo_data.db"):
        self.db = DatabaseConnector(db_path)
        self.stage1 = FormulaMatchStage(self.db)
        self.stage2 = TemperatureFilterStage()
        self.stage3 = PhaseSelectionStage()
        self.stage4 = ReliabilityPriorityStage()
        self.pipeline_stats = []

    def search(self, formula: str, temperature: float = 298.15,
               target_phase: Optional[str] = None) -> Tuple[List[CompoundRecord], Dict[str, Any]]:
        """Execute complete filtering pipeline."""
        self.pipeline_stats = []

        try:
            self.db.connect()

            # Stage 1: Formula matching
            results, stats1 = self.stage1.filter(formula, target_phase)
            self.pipeline_stats.append(stats1)

            # Stage 2: Temperature filtering
            results, stats2 = self.stage2.filter(results, temperature)
            self.pipeline_stats.append(stats2)

            # Stage 3: Phase selection
            results, stats3 = self.stage3.filter(results, temperature, target_phase)
            self.pipeline_stats.append(stats3)

            # Stage 4: Reliability priority
            results, stats4 = self.stage4.filter(results)
            self.pipeline_stats.append(stats4)

            pipeline_summary = {
                "input_formula": formula,
                "temperature": temperature,
                "target_phase": target_phase,
                "final_results_count": len(results),
                "pipeline_efficiency": len(results) / max(1, stats1.output_count),
                "total_execution_time": sum(s.execution_time for s in self.pipeline_stats),
                "stage_statistics": [
                    {
                        "stage": s.stage_name,
                        "input_count": s.input_count,
                        "output_count": s.output_count,
                        "filtered_count": s.filtered_count,
                        "efficiency": s.output_count / max(1, s.input_count) if s.input_count > 0 else 1.0,
                        "details": s.details
                    }
                    for s in self.pipeline_stats
                ]
            }

            return results, pipeline_summary

        finally:
            self.db.close()

def test_pipeline_scenarios():
    """Test the filtering pipeline with various scenarios."""
    pipeline = FilterPipeline()

    test_scenarios = [
        {
            "name": "H2O at 298K (room temperature)",
            "formula": "H2O",
            "temperature": 298.15,
            "target_phase": None
        },
        {
            "name": "H2O at 273K (freezing point)",
            "formula": "H2O",
            "temperature": 273.15,
            "target_phase": None
        },
        {
            "name": "H2O at 673K (high temperature, gas)",
            "formula": "H2O",
            "temperature": 673.15,
            "target_phase": "g"
        },
        {
            "name": "Fe at 1500K (below melting)",
            "formula": "Fe",
            "temperature": 1500.0,
            "target_phase": None
        },
        {
            "name": "Fe at 2000K (above melting)",
            "formula": "Fe",
            "temperature": 2000.0,
            "target_phase": None
        },
        {
            "name": "NaCl at 298K (solid)",
            "formula": "NaCl",
            "temperature": 298.15,
            "target_phase": "s"
        },
        {
            "name": "NaCl at 1200K (above melting)",
            "formula": "NaCl",
            "temperature": 1200.0,
            "target_phase": None
        }
    ]

    results = {}

    for scenario in test_scenarios:
        print(f"Testing: {scenario['name']}")

        try:
            compounds, summary = pipeline.search(
                formula=scenario['formula'],
                temperature=scenario['temperature'],
                target_phase=scenario['target_phase']
            )

            results[scenario['name']] = {
                "success": True,
                "compounds_found": len(compounds),
                "pipeline_summary": summary,
                "top_compounds": [
                    {
                        "formula": c.formula,
                        "phase": c.phase,
                        "reliability": c.reliability_class,
                        "temp_range": f"{c.tmin}-{c.tmax}K"
                    }
                    for c in compounds[:3]  # Top 3 results
                ]
            }

            print(f"  [OK] Found {len(compounds)} compounds")

        except Exception as e:
            results[scenario['name']] = {
                "success": False,
                "error": str(e)
            }
            print(f"  [ERROR] {e}")

    return results

def main():
    """Main function to run the filtering strategy prototype."""
    print("=== Filtering Strategy Prototype ===")
    print("Testing 4-stage filtering pipeline...")

    # Test scenarios
    test_results = test_pipeline_scenarios()

    # Save results
    with open('docs/filtering_strategy_results.json', 'w', encoding='utf-8') as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)

    print("\n=== PROTOTYPE RESULTS ===")

    successful_tests = sum(1 for r in test_results.values() if r.get('success', False))
    total_tests = len(test_results)

    print(f"Successful tests: {successful_tests}/{total_tests}")

    for scenario_name, result in test_results.items():
        if result.get('success', False):
            summary = result['pipeline_summary']
            print(f"\n{scenario_name}:")
            print(f"  Compounds found: {result['compounds_found']}")
            print(f"  Pipeline efficiency: {summary['pipeline_efficiency']:.2%}")
            print(f"  Execution time: {summary['total_execution_time']:.4f}s")

            if result['top_compounds']:
                print(f"  Top result: {result['top_compounds'][0]['formula']} "
                      f"({result['top_compounds'][0]['phase']}) "
                      f"Reliability: {result['top_compounds'][0]['reliability']}")
        else:
            print(f"\n{scenario_name}: FAILED - {result.get('error', 'Unknown error')}")

    print("\n[SUCCESS] Filtering strategy prototype complete!")
    print("Results saved to docs/filtering_strategy_results.json")

if __name__ == "__main__":
    main()