"""Compiler module for NOS.

Provides the end-to-end compilation pipeline that orchestrates
parsing, semantic analysis, and code generation.
"""

from .pipeline import CompilerPipeline, CompilationResult
from .main import main

__all__ = ['CompilerPipeline', 'CompilationResult', 'main']
