"""Base code generator interface for NOS.

Defines the contract that all code generators must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List

from ..ast import nodes
from ..semantic import SymbolTable


@dataclass
class GenerationOutput:
    """Output from code generation.

    Attributes:
        files: Dictionary mapping file paths to file contents
        metadata: Build configuration and metadata
        security_errors: Security violations found during generation
    """
    files: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    security_errors: List[str] = field(default_factory=list)

    def add_file(self, path: str, content: str):
        """Add a generated file."""
        self.files[path] = content

    def get_file(self, path: str) -> str:
        """Get generated file content."""
        return self.files.get(path, "")


class CodeGenerator(ABC):
    """Abstract base class for code generators.

    Subclasses must implement generate() to produce target code.
    """

    def __init__(self, options: Dict[str, Any] = None):
        self.options = options or {}
        self.output = GenerationOutput()

    @abstractmethod
    def generate(self, ast: nodes.ASTNode, symbol_table: SymbolTable) -> GenerationOutput:
        """Generate code from AST.

        Args:
            ast: Validated AST
            symbol_table: Complete symbol table

        Returns:
            GenerationOutput with all generated files
        """
        pass

    def _indent(self, text: str, level: int = 1) -> str:
        """Indent text by level * 4 spaces."""
        indent = "    " * level
        return "\n".join(indent + line if line.strip() else line
                        for line in text.split("\n"))

    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def _reserved_keywords(self) -> set:
        """Get reserved keywords for the target language."""
        return set()

    def _escape_identifier(self, name: str) -> str:
        """Escape identifier if it's a reserved keyword."""
        if name in self._reserved_keywords():
            return f"{name}_"
        return name
