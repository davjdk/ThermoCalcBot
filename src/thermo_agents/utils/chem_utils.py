"""Utilities for chemical formula parsing and manipulation."""

from typing import Dict, List
import re
import logging

logger = logging.getLogger(__name__)

# Regex for parsing chemical formulas (simplified version)
ELEMENT_RE = re.compile(r'([A-Z][a-z]?)(\d*)')
IONIC_RE = re.compile(r'[+\-]')

# Delimiters for composite formulas
COMPOSITE_DELIMITERS = ['*', '·', '.']


def parse_formula(formula: str) -> Dict[str, int]:
    """
    Parse a chemical formula into element counts.

    Simplified parser that handles basic formulas without parentheses.
    Examples:
        - "CO2" -> {"C": 1, "O": 2}
        - "Li2TiO3" -> {"Li": 2, "Ti": 1, "O": 3}
        - "NaCl" -> {"Na": 1, "Cl": 1}

    Args:
        formula: Chemical formula string

    Returns:
        Dictionary mapping element symbols to their counts
    """
    # Clean the formula - remove spaces and common delimiters
    clean_formula = formula.strip()
    for delim in COMPOSITE_DELIMITERS:
        clean_formula = clean_formula.replace(delim, ' ')

    # Split by spaces (for composite formulas) and parse each part
    parts = clean_formula.split()
    total_counts = {}

    for part in parts:
        if not part:
            continue

        # Extract element counts from this part
        for element, count_str in ELEMENT_RE.findall(part):
            count = int(count_str) if count_str else 1
            total_counts[element] = total_counts.get(element, 0) + count

    return total_counts


def sum_formulas(parts: List[str]) -> Dict[str, int]:
    """
    Sum multiple chemical formulas into total element counts.

    Args:
        parts: List of chemical formula parts

    Returns:
        Dictionary mapping element symbols to total counts
    """
    total = {}
    for part in parts:
        if not part.strip():
            continue
        parsed = parse_formula(part)
        for element, count in parsed.items():
            total[element] = total.get(element, 0) + count
    return total


def is_ionic_formula(formula: str) -> bool:
    """
    Check if a formula represents an ionic compound.

    Args:
        formula: Chemical formula string

    Returns:
        True if the formula appears to be ionic
    """
    # Check for charge indicators in the formula
    if IONIC_RE.search(formula):
        return True

    # Check for common ionic patterns
    ionic_patterns = [
        r'\(\+[0-9]*\)',   # (+g), (+2g), etc.
        r'\(-[0-9]*\)',   # (-g), (-2g), etc.
        r'[a-zA-Z]+\+[0-9]*',   # Na+, K2+, etc.
        r'[a-zA-Z]+-[0-9]*',    # Cl-, SO42-, etc.
    ]

    for pattern in ionic_patterns:
        if re.search(pattern, formula):
            return True

    return False


def is_ionic_name(name: str) -> bool:
    """
    Check if a compound name indicates it's ionic.

    Args:
        name: Compound name string

    Returns:
        True if the name suggests ionic nature
    """
    if not name:
        return False

    ionic_keywords = ['ion', 'cation', 'anion', 'ionic']
    name_lower = name.lower()

    return any(keyword in name_lower for keyword in ionic_keywords)


def query_contains_charge(query: str) -> bool:
    """
    Check if user query explicitly requests ionic forms.

    Args:
        query: User's search query

    Returns:
        True if query contains charge indicators
    """
    # Look for explicit charge indicators
    charge_patterns = [
        r'[+\-]',           # + or -
        r'\b(ion|cation|anion)\b',  # explicit ionic terms
    ]

    for pattern in charge_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return True

    return False


def normalize_composite_formula(formula: str) -> str:
    """
    Normalize a composite formula by removing spaces and standardizing delimiters.

    Args:
        formula: Chemical formula potentially containing composite parts

    Returns:
        Normalized formula string
    """
    normalized = formula.strip()

    # Replace various delimiters with standard '*'
    for delim in ['·', '.']:
        normalized = normalized.replace(delim, '*')

    # Remove extra spaces
    normalized = re.sub(r'\s+', '', normalized)

    return normalized


def expand_composite_candidates(query_formula: str, initial_records: List) -> List:
    """
    Find composite formula candidates that match the query formula by element composition.

    Args:
        query_formula: User's requested formula (e.g., "Li2TiO3")
        initial_records: List of database records to search within

    Returns:
        List of records whose composite formulas match the query composition
    """
    query_element_counts = parse_formula(query_formula)

    composite_candidates = []
    for record in initial_records:
        # Use both 'Formula' and 'formula' attribute names for compatibility
        formula = getattr(record, 'Formula', None) or getattr(record, 'formula', None)
        rowid = getattr(record, 'rowid', None) or getattr(record, 'id', None)

        if not formula:
            continue

        # Check if this is a composite formula
        if not any(delim in formula for delim in COMPOSITE_DELIMITERS):
            continue

        # Parse the composite formula
        composite_parts = []
        for delim in COMPOSITE_DELIMITERS:
            if delim in formula:
                composite_parts = formula.split(delim)
                break

        if len(composite_parts) < 2:
            continue

        # Calculate total element composition
        composite_elements = sum_formulas(composite_parts)

        # Check if compositions match
        if query_element_counts == composite_elements:
            composite_candidates.append(record)
            logger.debug(f"Composite match: {query_formula} = {formula} (record {rowid})")

    return composite_candidates