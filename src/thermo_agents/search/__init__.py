"""
Search module for thermodynamic compounds.

This module provides deterministic SQL generation and database search
functionality for thermodynamic compounds, replacing the LLM-based
SQL Generation Agent.
"""

from .sql_builder import SQLBuilder

__all__ = ["SQLBuilder"]