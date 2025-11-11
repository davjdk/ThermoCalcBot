"""
Query validation and sanitization for Telegram bot security.

This module provides comprehensive input validation to prevent security issues
including XSS, SQL injection, and code injection attacks.
"""

import re
import html
from typing import Optional, Tuple
from dataclasses import dataclass
from ..models.security import ValidationResult


@dataclass
class ValidationResult:
    """Result of query validation"""
    is_valid: bool
    message: str
    sanitized_query: Optional[str] = None


class QueryValidator:
    """
    Comprehensive input validation and sanitization for Telegram bot queries.

    Provides protection against:
    - XSS attacks through HTML tag filtering
    - SQL injection through pattern detection
    - Code injection through exec/eval filtering
    - Query length limits
    - Chemical formula validation
    """

    MAX_QUERY_LENGTH = 1000

    # Forbidden patterns for security
    FORBIDDEN_PATTERNS = [
        r'<[^>]*>',                    # HTML tags
        r'javascript:',                # JavaScript URL
        r'http[s]?://',                # HTTP links
        r'exec\s*\(',                  # Code execution
        r'eval\s*\(',                  # Eval functions
        r'import\s+',                  # Import statements
        r'__import__',                 # Import magic method
        r'subprocess\.',               # Subprocess calls
        r'os\.',                       # OS module calls
        r'sys\.',                      # System module calls
        r'\$\{.*\}',                   # Template injection
        r'{{.*}}',                     # Template injection (Jinja style)
        r'%{.*}%',                     # Template injection (Python style)
        r'`.*`',                       # Backtick execution
        r'\$\(',                       # Command substitution
    ]

    # Chemical formula patterns
    CHEMICAL_FORMULA_PATTERN = r'^[A-Za-z0-9\(\)\[\]\+\-\s]*$'

    # Allowed characters for chemical queries (more permissive)
    ALLOWED_CHARS_PATTERN = r'^[A-Za-z0-9\s\.\,\:\;\(\)\[\]\{\}\+\-\=\>\<\°\℃\℉\→\←\↔\∆\Δ\×\÷\±\∞\α\β\γ\δ\ε\ζ\η\θ\ι\κ\λ\μ\ν\ξ\ο\π\ρ\σ\τ\υ\φ\χ\ψ\ω\Α\Β\Γ\Δ\Ε\Ζ\Η\Θ\Ι\Κ\Λ\Μ\Ν\Ξ\Ο\Π\Ρ\Σ\Τ\Υ\Φ\Χ\Ψ\Ω\₀\₁\₂\₃\₄\₅\₆\₇\₈\₉\⁺\⁻\⁽\⁾\₍\₎]*$'

    @classmethod
    def validate_query(cls, query: str) -> ValidationResult:
        """
        Validate and sanitize a user query for security.

        Args:
            query: Raw user query string

        Returns:
            ValidationResult with validation status and sanitized query
        """
        if not query or not query.strip():
            return ValidationResult(
                is_valid=False,
                message="Query cannot be empty"
            )

        original_query = query.strip()

        # 1. Check length
        if len(original_query) > cls.MAX_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                message=f"Query too long (max {cls.MAX_QUERY_LENGTH} characters)"
            )

        # 2. Check for forbidden patterns
        for pattern in cls.FORBIDDEN_PATTERNS:
            if re.search(pattern, original_query, re.IGNORECASE):
                pattern_name = cls._get_pattern_description(pattern)
                return ValidationResult(
                    is_valid=False,
                    message=f"Forbidden pattern detected: {pattern_name}"
                )

        # 3. Basic character validation
        if not re.match(cls.ALLOWED_CHARS_PATTERN, original_query):
            return ValidationResult(
                is_valid=False,
                message="Query contains invalid characters"
            )

        # 4. Sanitize HTML entities
        sanitized = html.escape(original_query)

        # 5. Additional security sanitization
        sanitized = cls._security_sanitize(sanitized)

        # 6. Validate chemical formulas if present
        if not cls._validate_chemical_formulas(sanitized):
            return ValidationResult(
                is_valid=False,
                message="Invalid chemical formulas detected"
            )

        return ValidationResult(
            is_valid=True,
            message="Valid",
            sanitized_query=sanitized
        )

    @classmethod
    def _get_pattern_description(cls, pattern: str) -> str:
        """Get human-readable description of a forbidden pattern."""
        descriptions = {
            r'<[^>]*>': "HTML tags",
            r'javascript:': "JavaScript URLs",
            r'http[s]?://': "HTTP/HTTPS links",
            r'exec\s*\(': "Code execution functions",
            r'eval\s*\(": "Eval functions",
            r'import\s+': "Import statements",
            r'__import__': "Import magic methods",
            r'subprocess\.': "Subprocess module calls",
            r'os\.': "OS module calls",
            r'sys\.': "System module calls",
            r'\$\{.*\}': "Template injection (${...})",
            r'{{.*}}': "Template injection ({{...}})",
            r'%{.*}%': "Template injection (%{...}%)",
            r'`.*`': "Backtick execution",
            r'\$\(': "Command substitution",
        }
        return descriptions.get(pattern, "Suspicious pattern")

    @classmethod
    def _security_sanitize(cls, query: str) -> str:
        """
        Apply additional security sanitization.

        Args:
            query: Partially sanitized query

        Returns:
            Further sanitized query
        """
        # Remove multiple consecutive spaces
        query = re.sub(r'\s+', ' ', query)

        # Remove suspicious Unicode characters that might be used for attacks
        # Keep only safe Unicode characters for chemistry
        query = ''.join(char for char in query if ord(char) < 0x10000 or char in '→←↔∆Δ×÷±∞₀₁₂₃₄₅₆₇₈₉⁺⁻⁽⁾₍₎')

        # Trim whitespace
        query = query.strip()

        return query

    @classmethod
    def _validate_chemical_formulas(cls, query: str) -> bool:
        """
        Validate that chemical formulas in the query are properly formatted.

        Args:
            query: Sanitized query string

        Returns:
            True if chemical formulas appear valid, False otherwise
        """
        # Extract potential chemical formulas (simplified pattern)
        # This is a basic check - more sophisticated validation would be done by LLM
        formula_pattern = r'\b[A-Z][a-z]?(?:[A-Z][a-z]?\d*)*(?:\([A-Za-z0-9]+\)\d*)*\b'

        potential_formulas = re.findall(formula_pattern, query)

        for formula in potential_formulas:
            # Skip common words that might match the pattern
            if formula.lower() in ['for', 'and', 'the', 'with', 'from', 'that', 'this', 'will', 'can', 'not']:
                continue

            # Basic chemical formula validation
            if not re.match(r'^[A-Z][a-z]?(?:[A-Z][a-z]?\d*)*(?:\([A-Za-z0-9]+\)\d*)*$', formula):
                continue  # Skip if doesn't look like a chemical formula

            # Check for balanced parentheses
            if formula.count('(') != formula.count(')'):
                return False

        return True

    @classmethod
    def validate_temperature_range(cls, temp_str: str) -> Tuple[bool, str, Optional[Tuple[float, float]]]:
        """
        Validate and parse temperature range specifications.

        Args:
            temp_str: Temperature range string (e.g., "300-500K", "298 to 1000 K")

        Returns:
            Tuple of (is_valid, message, temperature_range or None)
        """
        if not temp_str:
            return True, "", None

        # Extract numbers from the temperature string
        numbers = re.findall(r'\d+\.?\d*', temp_str)

        if len(numbers) == 0:
            return False, "No temperature values found", None

        if len(numbers) == 1:
            # Single temperature value
            try:
                temp = float(numbers[0])
                if temp < 0 or temp > 10000:  # Reasonable temperature limits
                    return False, "Temperature out of reasonable range (0-10000K)", None
                return True, "", (temp, temp)
            except ValueError:
                return False, "Invalid temperature format", None

        elif len(numbers) == 2:
            # Temperature range
            try:
                temp_min = float(numbers[0])
                temp_max = float(numbers[1])

                if temp_min < 0 or temp_max > 10000:
                    return False, "Temperature out of reasonable range (0-10000K)", None

                if temp_min >= temp_max:
                    return False, "Minimum temperature must be less than maximum", None

                return True, "", (temp_min, temp_max)
            except ValueError:
                return False, "Invalid temperature format", None

        else:
            return False, "Too many temperature values (expected 1 or 2)", None

    @classmethod
    def sanitize_user_message(cls, message: str) -> str:
        """
        Quick sanitization for user messages that aren't chemical queries.

        Args:
            message: Raw user message

        Returns:
            Sanitized message safe for display
        """
        if not message:
            return ""

        # Basic HTML escaping
        sanitized = html.escape(message)

        # Remove excessive whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Limit length
        if len(sanitized) > 500:  # Shorter limit for non-query messages
            sanitized = sanitized[:500] + "..."

        return sanitized.strip()


def validate_telegram_input(text: str) -> Tuple[bool, str, Optional[str]]:
    """
    Convenience function for validating Telegram bot input.

    Args:
        text: Input text from Telegram user

    Returns:
        Tuple of (is_valid, error_message, sanitized_text)
    """
    result = QueryValidator.validate_query(text)

    if result.is_valid:
        return True, "", result.sanitized_query
    else:
        return False, result.message, None