"""Base code generator interface for NOS.

Defines the contract that all code generators must implement.
"""

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

    def __init__(self, options: Optional[Dict[str, Any]] = None):
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
        return "\n".join(indent + line if line.strip() else line for line in text.split("\n"))

    def _camel_to_snake(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def _reserved_keywords(self) -> set:
        """Get reserved keywords for the target language."""
        return set()

    def _escape_identifier(self, name: str) -> str:
        """Escape identifier if it's a reserved keyword."""
        if name in self._reserved_keywords():
            return f"{name}_"
        return name

    _DURATION_UNITS = {"s": "seconds", "ms": "milliseconds", "us": "microseconds", "ns": "nanoseconds"}
    _OPERATOR_MAP = {"&&": "and", "||": "or"}

    def _expression_to_python(self, expr: Optional[nodes.Expression]) -> str:
        """Convert an expression AST node to Python source."""
        if expr is None:
            return "None"

        if isinstance(expr, nodes.LiteralExpression):
            if expr.literal_type == "string":
                return json.dumps(expr.value)
            if expr.literal_type == "duration":
                match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(s|ms|us|ns)", str(expr.value))
                if match:
                    unit = self._DURATION_UNITS[match.group(2)]
                    return f"Duration({unit}={match.group(1)})"
            return str(expr.value)

        if isinstance(expr, nodes.IdentifierExpression):
            return self._escape_identifier(expr.name)

        if isinstance(expr, nodes.QualifiedIdentifierExpression):
            return ".".join(expr.parts)

        if isinstance(expr, nodes.BinaryExpression):
            left = self._expression_to_python(expr.left)
            right = self._expression_to_python(expr.right)
            op = self._OPERATOR_MAP.get(expr.operator, expr.operator)
            return f"({left} {op} {right})"

        if isinstance(expr, nodes.UnaryExpression):
            operand = self._expression_to_python(expr.operand)
            if expr.operator == "!":
                return f"(not {operand})"
            return f"({expr.operator}{operand})"

        if isinstance(expr, nodes.MemberAccessExpression):
            return f"{self._expression_to_python(expr.object)}.{expr.member}"

        if isinstance(expr, nodes.IndexExpression):
            array = self._expression_to_python(expr.array)
            return f"{array}[{self._expression_to_python(expr.index)}]"

        if isinstance(expr, nodes.CallExpression):
            callee = self._expression_to_python(expr.callee)
            args = [self._expression_to_python(arg) for arg in expr.arguments]
            return f"{callee}({', '.join(args)})"

        if isinstance(expr, nodes.InterpolatedExpression):
            return self._expression_to_python(expr.inner)

        if isinstance(expr, nodes.ArrayExpression):
            return "[" + ", ".join(self._expression_to_python(e) for e in expr.elements) + "]"

        if isinstance(expr, nodes.StructInitializerExpression):
            items = ", ".join(f"{json.dumps(k)}: {self._expression_to_python(v)}" for k, v in expr.fields.items())
            return "{" + items + "}"

        return str(expr)
