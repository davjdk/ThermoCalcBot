"""
Static data manager for YAML cache of frequently accessed compounds.

This module provides functionality to load, validate, and cache thermodynamic
data from YAML files for improved performance of frequently accessed compounds.
"""

import logging
import yaml
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict

from ..models.search import DatabaseRecord
from ..models.static_data import YAMLCompoundData, YAMLPhaseRecord

logger = logging.getLogger(__name__)


class StaticDataManager:
    """
    Manager for working with YAML cache of selected compounds.

    YAML files are stored in data/static_compounds/ and contain
    thermodynamic data for commonly used compounds.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize the static data manager.

        Args:
            data_dir: Path to directory with YAML files.
                     Default: data/static_compounds/
        """
        if data_dir is None:
            # Determine path relative to project root
            project_root = Path(__file__).parent.parent.parent.parent
            data_dir = project_root / "data" / "static_compounds"

        self.data_dir = Path(data_dir)
        self.cache: Dict[str, YAMLCompoundData] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Create directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"StaticDataManager initialized: {self.data_dir}")

    def is_available(self, formula: str) -> bool:
        """
        Check if YAML file exists for compound.

        Args:
            formula: Chemical formula (e.g., "H2O")

        Returns:
            True if file exists
        """
        yaml_path = self.data_dir / f"{formula}.yaml"
        return yaml_path.exists()

    def load_compound(self, formula: str) -> Optional[YAMLCompoundData]:
        """
        Load compound data from YAML.

        Args:
            formula: Chemical formula

        Returns:
            YAMLCompoundData or None if file not found
        """
        # Check cache first
        if formula in self.cache:
            self.logger.debug(f"Loading {formula} from cache")
            return self.cache[formula]

        yaml_path = self.data_dir / f"{formula}.yaml"

        if not yaml_path.exists():
            self.logger.debug(f"YAML file not found: {yaml_path}")
            return None

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # Validate through Pydantic
            compound_data = YAMLCompoundData(**data["compound"])

            # Check for outdated data
            self._check_data_age(formula, compound_data.metadata.extracted_date)

            # Save to cache
            self.cache[formula] = compound_data

            self.logger.info(
                f"✅ Loaded from YAML: {formula} ({len(compound_data.phases)} phases)"
            )
            return compound_data

        except Exception as e:
            self.logger.error(f"Error loading YAML for {formula}: {e}")
            return None

    def _check_data_age(self, formula: str, extracted_date: str) -> None:
        """
        Check if YAML data is outdated and warn if necessary.

        Args:
            formula: Chemical formula
            extracted_date: Date string from metadata
        """
        try:
            extracted = datetime.strptime(extracted_date, "%Y-%m-%d")
            age_days = (datetime.now() - extracted).days

            if age_days > 30:
                self.logger.warning(
                    f"YAML for {formula} is outdated ({age_days} days old)"
                )
        except ValueError:
            self.logger.warning(
                f"Invalid date format in YAML for {formula}: {extracted_date}"
            )

    def get_compound_phases(self, formula: str) -> List[DatabaseRecord]:
        """
        Get all phases of compound as DatabaseRecord objects.

        Args:
            formula: Chemical formula

        Returns:
            List of DatabaseRecord for all phases
        """
        compound_data = self.load_compound(formula)

        if compound_data is None:
            return []

        # Convert YAMLPhaseRecord → DatabaseRecord
        records = []
        for phase_data in compound_data.phases:
            record = DatabaseRecord(
                formula=compound_data.formula,
                name=compound_data.description,
                first_name=phase_data.first_name,
                phase=phase_data.phase,
                tmin=phase_data.tmin,
                tmax=phase_data.tmax,
                h298=phase_data.h298,
                s298=phase_data.s298,
                f1=phase_data.f1,
                f2=phase_data.f2,
                f3=phase_data.f3,
                f4=phase_data.f4,
                f5=phase_data.f5,
                f6=phase_data.f6,
                tmelt=phase_data.tmelt,
                tboil=phase_data.tboil,
                reliability_class=phase_data.reliability_class,
                molecular_weight=phase_data.molecular_weight,
                is_h298_s298_reference=False  # Default value
            )
            records.append(record)

        # Mark H298/S298 reference record if specified
        if compound_data.h298_s298_source:
            records = self._mark_h298_s298_reference(records, compound_data.h298_s298_source)

        return records

    def _mark_h298_s298_reference(
        self,
        records: List[DatabaseRecord],
        source_spec: "YamlH298S298Source"
    ) -> List[DatabaseRecord]:
        """
        Mark the record that should be used as H298/S298 reference.

        Args:
            records: List of DatabaseRecord objects
            source_spec: H298/S298 source specification from YAML

        Returns:
            Updated list with reference record marked
        """
        for record in records:
            if (record.phase == source_spec.phase and
                abs(record.tmin - source_spec.tmin_reference) < 1e-6):
                record.is_h298_s298_reference = True
                self.logger.info(
                    f"✅ Marked H298/S298 reference: {record.formula} "
                    f"{record.phase} phase at Tmin={record.tmin:.3f}K"
                )
                break
        else:
            self.logger.warning(
                f"⚠️ Could not find H298/S298 reference record for "
                f"{records[0].formula if records else 'unknown'} "
                f"(phase={source_spec.phase}, Tmin={source_spec.tmin_reference})"
            )

        return records

    def list_available_compounds(self) -> List[str]:
        """
        Get list of all available compounds in cache.

        Returns:
            List of compound formulas
        """
        yaml_files = self.data_dir.glob("*.yaml")
        formulas = [f.stem for f in yaml_files]
        return sorted(formulas)

    def reload(self) -> None:
        """Clear cache and reload data."""
        self.cache.clear()
        self.logger.info("Cache cleared")

    def get_cache_info(self) -> Dict[str, any]:
        """
        Get information about cache status.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "cache_size": len(self.cache),
            "data_dir": str(self.data_dir),
            "available_files": len(list(self.data_dir.glob("*.yaml"))),
            "cached_compounds": list(self.cache.keys())
        }