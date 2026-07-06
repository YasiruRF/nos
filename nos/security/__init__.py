"""Security validation for embedded Python code in NOS.

This module provides security checks to prevent code injection
attacks through embedded Python code blocks.

All security validation is delegated to the sanitizer module for
consolidated security logic.
"""

# Import from sanitizer module to maintain backwards compatibility
from .sanitizer import (
    SecurityError,
    SecuritySeverity,
    SecurityViolation,
    SecurityValidationResult,
    PythonCodeSanitizer,
    validate_callback_code,
    sanitize_python_code,
    validate_and_raise,
)

# Re-export for backwards compatibility
__all__ = [
    'SecurityError',
    'SecuritySeverity',
    'SecurityViolation',
    'SecurityValidationResult',
    'PythonCodeSanitizer',
    'PythonCodeValidator',  # Alias for backwards compatibility
    'validate_callback_code',
    'sanitize_python_code',
    'validate_and_raise',
]


# Backwards compatibility: PythonCodeValidator is an alias for PythonCodeSanitizer
class PythonCodeValidator(PythonCodeSanitizer):
    """Backwards-compatible alias for PythonCodeSanitizer."""
    pass
