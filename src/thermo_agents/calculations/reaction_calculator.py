"""
Multi-Phase Reaction Calculator for Stage 3 Implementation.

This module implements reaction calculations with support for multiple records
per compound, handling seamless transitions between records while maintaining
thermodynamic continuity.

Техническое описание:
Многофазный калькулятор реакций для Этапа 3.
Реализует расчёты химических реакций с поддержкой множественных записей
для каждого соединения, обеспечивая бесшовные переходы между записями
и поддержание термодинамической непрерывности.

Основные функции:

1. Расчёт ΔH, ΔS, ΔG реакций с множественными записями
2. Автоматический выбор оптимальных записей для каждой температуры
3. Обработка переходов между записями для реагентов и продуктов
4. Построение таблиц термодинамических свойств реакций
5. Анализ влияния переходов на результаты расчётов

Ключевые алгоритмы:

- Выбор записей для каждого компонента реакции при заданной T
- Применение коррекций для обеспечения непрерывности
- Расчёт суммарных свойств реакции с учётом всех переходов
- Визуализация влияния переключения записей на свойства реакции

Интеграция:
- Использует MultiPhaseCompoundData для данных о соединениях
- Интегрируется с RecordTransitionManager для переходов
- Работает с ThermodynamicCalculator для базовых расчётов
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import logging

from ..models.search import MultiPhaseCompoundData, DatabaseRecord
from .thermodynamic_calculator import ThermodynamicCalculator, ThermodynamicProperties

logger = logging.getLogger(__name__)


@dataclass
class ReactionComponent:
    """Component of a chemical reaction with compound data and stoichiometry."""

    compound_data: MultiPhaseCompoundData
    stoichiometry: float  # Positive for products, negative for reactants
    is_reactant: bool

    @property
    def effective_stoichiometry(self) -> float:
        """Get effective stoichiometry (negative for reactants)."""
        return -abs(self.stoichiometry) if self.is_reactant else abs(self.stoichiometry)


@dataclass
class ReactionProperties:
    """Thermodynamic properties of a reaction at a specific temperature."""

    temperature: float
    delta_H: float  # J/mol
    delta_S: float  # J/(mol·K)
    delta_G: float  # J/mol

    # Component contributions
    component_contributions: Dict[str, Dict[str, float]]

    # Record transition information
    record_transitions: List[Dict[str, Any]]
    warnings: List[str]

    def to_dict(self) -> dict:
        """Convert to dictionary with kJ for energy values."""
        return {
            "T": self.temperature,
            "delta_H": self.delta_H / 1000,  # J → kJ
            "delta_S": self.delta_S,
            "delta_G": self.delta_G / 1000,  # J → kJ
            "component_contributions": self.component_contributions,
            "record_transitions": self.record_transitions,
            "warnings": self.warnings
        }


@dataclass
class ReactionTable:
    """Table of reaction thermodynamic properties over temperature range."""

    reaction_equation: str
    temperature_range: Tuple[float, float]
    properties: List[ReactionProperties]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "reaction": self.reaction_equation,
            "T_range": self.temperature_range,
            "data": [prop.to_dict() for prop in self.properties]
        }


class MultiPhaseReactionCalculator:
    """
    Calculator for multi-phase reactions with multiple records support (Stage 3).

    This class implements reaction calculations that can handle multiple database
    records for each compound, ensuring seamless transitions and thermodynamic
    continuity throughout the calculation.
    """

    def __init__(self):
        """Initialize the multi-phase reaction calculator."""
        self.thermo_calculator = ThermodynamicCalculator()
        logger.info("MultiPhaseReactionCalculator initialized for Stage 3")

    def calculate_reaction_properties(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature: float
    ) -> ReactionProperties:
        """
        Calculate reaction properties at a specific temperature (Stage 3).

        This method handles the core logic of calculating reaction thermodynamics
        when compounds have multiple database records, ensuring proper record
        selection and transition handling.

        Args:
            reactants_data: List of MultiPhaseCompoundData for reactants
            products_data: List of MultiPhaseCompoundData for products
            stoichiometry: Dictionary mapping compound formulas to stoichiometric coefficients
            temperature: Temperature in Kelvin

        Returns:
            ReactionProperties at the specified temperature

        Raises:
            ValueError: If temperature is outside any compound's range
        """
        logger.debug(f"Calculating reaction properties at T={temperature:.1f}K")

        # Build reaction components
        reactant_components = [
            ReactionComponent(
                compound_data=compound,
                stoichiometry=stoichiometry.get(compound.compound_formula, 0),
                is_reactant=True
            )
            for compound in reactants_data
        ]

        product_components = [
            ReactionComponent(
                compound_data=compound,
                stoichiometry=stoichiometry.get(compound.compound_formula, 0),
                is_reactant=False
            )
            for compound in products_data
        ]

        all_components = reactant_components + product_components

        # Calculate properties for each component
        total_delta_H = 0.0
        total_delta_S = 0.0
        component_contributions = {}
        record_transitions = []
        warnings = []

        for component in all_components:
            try:
                # Get properties for this component at temperature
                compound_props = self.thermo_calculator.calculate_properties_multi_record(
                    component.compound_data, temperature
                )

                # Calculate contribution to reaction
                contribution_H = component.effective_stoichiometry * compound_props.H
                contribution_S = component.effective_stoichiometry * compound_props.S

                total_delta_H += contribution_H
                total_delta_S += contribution_S

                # Store component contribution
                component_contributions[component.compound_data.compound_formula] = {
                    "H": compound_props.H / 1000,  # kJ/mol
                    "S": compound_props.S,
                    "stoichiometry": component.effective_stoichiometry,
                    "contribution_H": contribution_H / 1000,  # kJ/mol
                    "contribution_S": contribution_S
                }

                # Check for record transitions in this component
                if component.compound_data.has_multiple_records_per_segment:
                    transitions_info = self._analyze_component_transitions(
                        component, temperature
                    )
                    record_transitions.extend(transitions_info)

            except ValueError as e:
                warning_msg = (
                    f"Cannot calculate properties for {component.compound_data.compound_formula} "
                    f"at T={temperature:.1f}K: {e}"
                )
                warnings.append(warning_msg)
                logger.warning(warning_msg)

                # Use approximate values or skip
                continue

        # Calculate Gibbs energy
        delta_G = total_delta_H - temperature * total_delta_S

        # Build reaction equation for reference
        reactant_terms = [
            f"{abs(comp.stoichiometry):g} {comp.compound_data.compound_formula}"
            for comp in reactant_components if comp.stoichiometry != 0
        ]
        product_terms = [
            f"{comp.stoichiometry:g} {comp.compound_data.compound_formula}"
            for comp in product_components if comp.stoichiometry != 0
        ]

        reaction_equation = " + ".join(reactant_terms) + " → " + " + ".join(product_terms)

        return ReactionProperties(
            temperature=temperature,
            delta_H=total_delta_H,
            delta_S=total_delta_S,
            delta_G=delta_G,
            component_contributions=component_contributions,
            record_transitions=record_transitions,
            warnings=warnings
        )

    def calculate_reaction_table(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature_range: Tuple[float, float],
        num_points: int = 50
    ) -> ReactionTable:
        """
        Generate reaction thermodynamic table over temperature range.

        Args:
            reactants_data: List of MultiPhaseCompoundData for reactants
            products_data: List of MultiPhaseCompoundData for products
            stoichiometry: Stoichiometric coefficients
            temperature_range: Temperature range (Tmin, Tmax) in Kelvin
            num_points: Number of temperature points

        Returns:
            ReactionTable with properties across the range
        """
        import numpy as np

        T_min, T_max = temperature_range
        temperatures = np.linspace(T_min, T_max, num_points)

        properties = []

        for T in temperatures:
            try:
                props = self.calculate_reaction_properties(
                    reactants_data, products_data, stoichiometry, T
                )
                properties.append(props)
            except ValueError as e:
                logger.warning(f"Skipping T={T:.1f}K: {e}")
                continue

        # Build reaction equation
        reactant_terms = [
            f"{stoichiometry.get(comp.compound_formula, 0):g} {comp.compound_formula}"
            for comp in reactants_data if stoichiometry.get(comp.compound_formula, 0) != 0
        ]
        product_terms = [
            f"{stoichiometry.get(comp.compound_formula, 0):g} {comp.compound_formula}"
            for comp in products_data if stoichiometry.get(comp.compound_formula, 0) != 0
        ]

        reaction_equation = " + ".join(reactant_terms) + " → " + " + ".join(product_terms)

        return ReactionTable(
            reaction_equation=reaction_equation,
            temperature_range=temperature_range,
            properties=properties
        )

    def analyze_transition_impact(
        self,
        reactants_data: List[MultiPhaseCompoundData],
        products_data: List[MultiPhaseCompoundData],
        stoichiometry: Dict[str, float],
        temperature_range: Tuple[float, float]
    ) -> Dict[str, Any]:
        """
        Analyze the impact of record transitions on reaction properties.

        Args:
            reactants_data: List of MultiPhaseCompoundData for reactants
            products_data: List of MultiPhaseCompoundData for products
            stoichiometry: Stoichiometric coefficients
            temperature_range: Temperature range to analyze

        Returns:
            Dictionary with transition impact analysis
        """
        T_min, T_max = temperature_range

        # Find all transition temperatures in the range
        all_transitions = []

        for compound in reactants_data + products_data:
            if compound.has_multiple_records_per_segment:
                segments = compound.get_segments_in_range(T_min, T_max)

                for i in range(len(segments) - 1):
                    current = segments[i]
                    next_segment = segments[i + 1]

                    if current.record.id != next_segment.record.id:
                        transition_temp = (current.T_end + next_segment.T_start) / 2

                        # Calculate properties before and after transition
                        try:
                            props_before = self.calculate_reaction_properties(
                                reactants_data, products_data, stoichiometry,
                                transition_temp - 1
                            )
                            props_after = self.calculate_reaction_properties(
                                reactants_data, products_data, stoichiometry,
                                transition_temp + 1
                            )

                            # Calculate jumps
                            delta_H_jump = props_after.delta_H - props_before.delta_H
                            delta_S_jump = props_after.delta_S - props_before.delta_S
                            delta_G_jump = props_after.delta_G - props_before.delta_G

                            transition_info = {
                                "temperature": transition_temp,
                                "compound": compound.compound_formula,
                                "from_record": current.record.id,
                                "to_record": next_segment.record.id,
                                "delta_H_jump": delta_H_jump / 1000,  # kJ/mol
                                "delta_S_jump": delta_S_jump,
                                "delta_G_jump": delta_G_jump / 1000,  # kJ/mol
                                "significant_H": abs(delta_H_jump) > 100,  # > 100 J/mol
                                "significant_G": abs(delta_G_jump) > 100   # > 100 J/mol
                            }

                            all_transitions.append(transition_info)

                        except ValueError:
                            # Skip if calculation fails
                            continue

        # Analyze overall impact
        significant_transitions = [t for t in all_transitions if t["significant_G"]]

        return {
            "temperature_range": temperature_range,
            "total_transitions": len(all_transitions),
            "significant_transitions": len(significant_transitions),
            "transition_details": all_transitions,
            "max_H_jump": max((abs(t["delta_H_jump"]) for t in all_transitions), default=0),
            "max_G_jump": max((abs(t["delta_G_jump"]) for t in all_transitions), default=0),
            "compounds_with_transitions": list(set(t["compound"] for t in all_transitions)),
            "recommendation": self._generate_transition_recommendation(significant_transitions)
        }

    def _analyze_component_transitions(
        self,
        component: ReactionComponent,
        temperature: float
    ) -> List[Dict[str, Any]]:
        """
        Analyze record transitions for a component at given temperature.

        Args:
            component: Reaction component to analyze
            temperature: Temperature to check

        Returns:
            List of transition information
        """
        transitions = []

        # Get segments around the temperature
        nearby_segments = component.compound_data.get_segments_in_range(
            temperature - 10, temperature + 10
        )

        if len(nearby_segments) > 1:
            # Check if we're near a transition
            for i in range(len(nearby_segments) - 1):
                current = nearby_segments[i]
                next_segment = nearby_segments[i + 1]

                transition_temp = (current.T_end + next_segment.T_start) / 2

                if abs(temperature - transition_temp) < 5:  # Within 5K of transition
                    transition_info = {
                        "compound": component.compound_data.compound_formula,
                        "temperature": transition_temp,
                        "from_record": current.record.id,
                        "to_record": next_segment.record.id,
                        "distance_from_transition": abs(temperature - transition_temp)
                    }
                    transitions.append(transition_info)

        return transitions

    def _generate_transition_recommendation(
        self,
        significant_transitions: List[Dict[str, Any]]
    ) -> str:
        """
        Generate recommendation based on transition analysis.

        Args:
            significant_transitions: List of significant transitions

        Returns:
            Recommendation string
        """
        if not significant_transitions:
            return "Record transitions have minimal impact on reaction properties."

        if len(significant_transitions) == 1:
            return (
                "One significant record transition detected. "
                "Consider verifying data consistency around transition temperature."
            )

        if len(significant_transitions) > 3:
            return (
                "Multiple significant record transitions detected. "
                "High-resolution calculations recommended around transition points."
            )

        return (
            "Some record transitions may affect reaction properties. "
            "Review transition points for critical applications."
        )