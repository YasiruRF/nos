"""Semantic analysis module for NOS.

Provides type checking, symbol resolution, and validation
of NOS AST nodes.
"""

from .analyzer import AnalysisResult, Diagnostic, DiagnosticSeverity, SemanticAnalyzer, SemanticError
from .symbol_table import Scope, Symbol, SymbolTable, SymbolType

__all__ = [
    "Symbol",
    "SymbolTable",
    "Scope",
    "SymbolType",
    "SemanticAnalyzer",
    "SemanticError",
    "Diagnostic",
    "DiagnosticSeverity",
    "AnalysisResult",
]
