"""Compiler module for NOS.

Provides the end-to-end compilation pipeline that orchestrates
parsing, semantic analysis, and code generation.
"""

from .main import main
from .pipeline import CompilationResult, CompilerPipeline

__all__ = ["CompilerPipeline", "CompilationResult", "main"]
