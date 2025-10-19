"""
Pydantic models for static YAML data storage.

This module contains data models for loading and validating thermodynamic
data from YAML files used as a cache for frequently accessed compounds.
"""

from typing import List, Optional, Dict

from pydantic import BaseModel, Field, field_validator


class YAMLPhaseRecord(BaseModel):
    """Single phase record in YAML format."""

    phase: str = Field(..., description="Phase (s/l/g/aq)")
    tmin: float = Field(..., description="Minimum temperature, K")
    tmax: float = Field(..., description="Maximum temperature, K")
    h298: float = Field(..., description="Enthalpy at 298K, J/mol")
    s298: float = Field(..., description="Entropy at 298K, J/(mol·K)")
    f1: float = Field(..., description="Heat capacity coefficient f1")
    f2: float = Field(..., description="Heat capacity coefficient f2")
    f3: float = Field(..., description="Heat capacity coefficient f3")
    f4: float = Field(..., description="Heat capacity coefficient f4")
    f5: float = Field(..., description="Heat capacity coefficient f5")
    f6: float = Field(..., description="Heat capacity coefficient f6")
    tmelt: float = Field(..., description="Melting temperature, K")
    tboil: float = Field(..., description="Boiling temperature, K")
    first_name: Optional[str] = Field(None, description="First name of compound")
    reliability_class: int = Field(1, description="Reliability class")
    molecular_weight: Optional[float] = Field(None, description="Molecular weight")

    @field_validator("tmax")
    @classmethod
    def validate_temperature_range(cls, v, info):
        """Validate that tmax > tmin."""
        if hasattr(info, 'data') and "tmin" in info.data and v <= info.data["tmin"]:
            raise ValueError("tmax must be greater than tmin")
        return v


class YAMLPhaseTransition(BaseModel):
    """Phase transition record in YAML format."""

    temperature: float = Field(..., description="Transition temperature, K")
    enthalpy: float = Field(..., description="Transition enthalpy, kJ/mol")
    entropy: float = Field(..., description="Transition entropy, J/(mol·K)")


class YAMLMetadata(BaseModel):
    """Metadata for YAML file."""

    source_database: str = Field(..., description="Source database")
    extracted_date: str = Field(..., description="Extraction date")
    version: str = Field(..., description="Data version")
    notes: Optional[str] = Field(None, description="Additional notes")


class YAMLCompoundData(BaseModel):
    """Complete structure of YAML compound file."""

    formula: str = Field(..., description="Chemical formula")
    common_names: List[str] = Field(default_factory=list, description="Common names")
    description: str = Field(..., description="Compound description")

    phases: List[YAMLPhaseRecord] = Field(..., description="All phases of compound")

    phase_transitions: Optional[Dict[str, YAMLPhaseTransition]] = Field(
        None,
        description="Phase transitions (melting, vaporization, sublimation)"
    )

    metadata: YAMLMetadata = Field(..., description="File metadata")

    @field_validator("phases")
    @classmethod
    def validate_phases_sorted(cls, v):
        """Validate that phases are sorted by Tmin."""
        if len(v) < 2:
            return v
        for i in range(len(v) - 1):
            if v[i].tmin > v[i + 1].tmin:
                raise ValueError("Phases must be sorted by Tmin")
        return v

    def to_dict(self) -> dict:
        """Serialize to dictionary for logging."""
        return {
            "formula": self.formula,
            "description": self.description,
            "phases_count": len(self.phases),
            "common_names": self.common_names,
            "source": self.metadata.source_database,
            "version": self.metadata.version,
            "extracted_date": self.metadata.extracted_date
        }