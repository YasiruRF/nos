"""Main semantic analyzer for NOS.

Orchestrates semantic analysis passes including:
- Symbol table construction
- Type checking
- Constraint validation
- Reference resolution
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any
from enum import Enum

from ..ast import nodes
from ..ast.visitor import ASTVisitor
from .symbol_table import SymbolTable, Symbol, Scope, SymbolType


class DiagnosticSeverity(Enum):
    """Severity levels for diagnostics."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """A diagnostic message (error, warning, or info).

    Attributes:
        severity: The severity level
        message: Human-readable message
        location: Source location
        code: Optional error code for tooling
    """
    severity: DiagnosticSeverity
    message: str
    location: nodes.SourceLocation
    code: Optional[str] = None

    def __str__(self) -> str:
        prefix = self.severity.value.upper()
        return f"{self.location}: {prefix}: {self.message}"


class SemanticError(Exception):
    """Exception raised for semantic errors."""

    def __init__(self, message: str, location: Optional[nodes.SourceLocation] = None):
        self.message = message
        self.location = location
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        if self.location:
            return f"{self.location}: {self.message}"
        return self.message


@dataclass
class AnalysisResult:
    """Result of semantic analysis.

    Attributes:
        ast: The validated AST (may be modified)
        symbol_table: Complete symbol table
        diagnostics: All diagnostics from analysis
        is_valid: True if no errors were found
    """
    ast: nodes.ASTNode
    symbol_table: SymbolTable
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if analysis found no errors."""
        return not any(d.severity == DiagnosticSeverity.ERROR
                      for d in self.diagnostics)

    @property
    def errors(self) -> List[Diagnostic]:
        """Get all error diagnostics."""
        return [d for d in self.diagnostics
                if d.severity == DiagnosticSeverity.ERROR]

    @property
    def warnings(self) -> List[Diagnostic]:
        """Get all warning diagnostics."""
        return [d for d in self.diagnostics
                if d.severity == DiagnosticSeverity.WARNING]


class SemanticAnalyzer(ASTVisitor):
    """Main semantic analyzer for NOS.

    Performs multi-pass semantic analysis:
    1. Build symbol table (declarations)
    2. Resolve references
    3. Type checking
    4. Constraint validation

    Example:
        >>> from nos.ast.builder import ASTBuilder
        >>> from nos.semantic import SemanticAnalyzer
        >>> ast = builder.visit(parse_tree)
        >>> analyzer = SemanticAnalyzer()
        >>> result = analyzer.analyze(ast)
        >>> if result.is_valid:
        ...     print("Semantic analysis passed")
        ... else:
        ...     for error in result.errors:
        ...         print(error)
    """

    def __init__(self):
        self.symbol_table = SymbolTable()
        self.diagnostics: List[Diagnostic] = []
        self.current_node: Optional[str] = None

    def analyze(self, ast: nodes.ASTNode) -> AnalysisResult:
        """Analyze an AST and return results.

        Args:
            ast: The root AST node to analyze

        Returns:
            AnalysisResult containing validated AST and diagnostics
        """
        self.diagnostics.clear()

        self._reject_interface_declarations(ast)

        # Pass 1: Build symbol table
        self._build_symbols(ast)

        # Pass 2: Resolve references and type check
        self._resolve_and_check(ast)

        return AnalysisResult(
            ast=ast,
            symbol_table=self.symbol_table,
            diagnostics=self.diagnostics.copy()
        )

    def _reject_interface_declarations(self, ast: nodes.ASTNode):
        """Interface declarations parse but nothing generates .msg/.srv/.action yet."""
        if not isinstance(ast, nodes.File):
            return
        for decl in ast.declarations:
            if not isinstance(decl, nodes.InterfaceDecl):
                continue
            for item in decl.declarations:
                kind = {
                    nodes.MessageDecl: "message",
                    nodes.ServiceInterfaceDecl: "service",
                    nodes.ActionInterfaceDecl: "action",
                }.get(type(item), "interface")
                self._add_error(
                    f"{kind.capitalize()} interface declarations are not supported yet "
                    f"('{getattr(item, 'name', '')}'); define the {kind} in a ROS 2 "
                    f"interface package and reference it with package::Type",
                    item.location,
                    "E010"
                )

    def _add_error(self, message: str, location: nodes.SourceLocation, code: Optional[str] = None):
        """Add an error diagnostic."""
        self.diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            message=message,
            location=location,
            code=code
        ))

    def _add_warning(self, message: str, location: nodes.SourceLocation, code: Optional[str] = None):
        """Add a warning diagnostic."""
        self.diagnostics.append(Diagnostic(
            severity=DiagnosticSeverity.WARNING,
            message=message,
            location=location,
            code=code
        ))

    def _build_symbols(self, ast: nodes.ASTNode):
        """First pass: build symbol table from declarations."""
        builder = SymbolTableBuilder(self.symbol_table, self)
        builder.visit(ast)

    def _resolve_and_check(self, ast: nodes.ASTNode):
        """Second pass: resolve references and type check."""
        checker = ReferenceResolver(self.symbol_table, self)
        checker.visit(ast)


class SymbolTableBuilder(ASTVisitor):
    """Builds symbol table from AST declarations.

    First pass of semantic analysis - collects all symbols
    without validating references.
    """

    def __init__(self, symbol_table: SymbolTable, analyzer: SemanticAnalyzer):
        self.symbol_table = symbol_table
        self.analyzer = analyzer

    def visit_File(self, node: nodes.File) -> None:
        """Visit file and process declarations."""
        if node.package:
            self.visit(node.package)

        for imp in node.imports:
            self.visit(imp)

        for decl in node.declarations:
            self.visit(decl)

        if node.package:
            self.symbol_table.pop_scope()

    def visit_PackageDecl(self, node: nodes.PackageDecl) -> None:
        """Visit package declaration."""
        scope = self.symbol_table.push_scope(node.name, "package")

        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.PACKAGE,
            node=node,
            scope=scope,
            is_exported=True
        )
        self.symbol_table.define(symbol)

    def visit_ImportDecl(self, node: nodes.ImportDecl) -> None:
        """Visit import declaration."""
        # Use alias if provided, otherwise the last part of the qualified name
        name = node.alias if node.alias else node.qualified_name.split("::")[-1]

        symbol = Symbol(
            name=name,
            symbol_type=SymbolType.PACKAGE,
            node=node,
            scope=self.symbol_table.current_scope,
            is_exported=False
        )
        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate import or symbol: '{name}'",
                node.location,
                "W009"
            )

    def visit_NodeDecl(self, node: nodes.NodeDecl) -> None:
        """Visit node declaration."""
        # Define node symbol in current scope
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.NODE,
            node=node,
            scope=self.symbol_table.current_scope,
            is_exported=True
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_error(
                f"Duplicate node definition: '{node.name}'",
                node.location,
                "E001"
            )
            return

        # Create node scope
        node_scope = self.symbol_table.push_scope(node.name, "node")
        self.analyzer.current_node = node.name

        # Process parameters
        for param in node.parameters:
            self.visit(param)

        # Process subscriptions
        for sub in node.subscriptions:
            self.visit(sub)

        # Process publications
        for pub in node.publications:
            self.visit(pub)

        # Process services
        for svc in node.services:
            self.visit(svc)

        # Process actions
        for act in node.actions:
            self.visit(act)

        # Process components
        for comp in node.components:
            self.visit(comp)

        # Process callbacks
        for cb in node.callbacks:
            self.visit(cb)

        # Pop node scope
        self.symbol_table.pop_scope()
        self.analyzer.current_node = None

    def visit_ParameterDecl(self, node: nodes.ParameterDecl) -> None:
        """Visit parameter declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.PARAMETER,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_error(
                f"Duplicate parameter: '{node.name}'",
                node.location,
                "E002"
            )

    def visit_SubscriptionDecl(self, node: nodes.SubscriptionDecl) -> None:
        """Visit subscription declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.SUBSCRIPTION,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.message_type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate subscription name: '{node.name}'",
                node.location,
                "W001"
            )

    def visit_PublicationDecl(self, node: nodes.PublicationDecl) -> None:
        """Visit publication declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.PUBLICATION,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.message_type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate publication name: '{node.name}'",
                node.location,
                "W002"
            )

    def visit_ServiceDecl(self, node: nodes.ServiceDecl) -> None:
        """Visit service declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.SERVICE,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.service_type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate service name: '{node.name}'",
                node.location,
                "W003"
            )

    def visit_ActionDecl(self, node: nodes.ActionDecl) -> None:
        """Visit action declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.ACTION,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.action_type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate action name: '{node.name}'",
                node.location,
                "W004"
            )

    def visit_ComponentDecl(self, node: nodes.ComponentDecl) -> None:
        """Visit component declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.COMPONENT,
            node=node,
            scope=self.symbol_table.current_scope
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_warning(
                f"Duplicate component name: '{node.name}'",
                node.location,
                "W005"
            )

    def visit_CallbackDecl(self, node: nodes.CallbackDecl) -> None:
        """Visit callback declaration."""
        # Create callback scope
        callback_scope = self.symbol_table.push_scope(node.event, "callback")

        # Define callback symbol
        symbol = Symbol(
            name=node.event,
            symbol_type=SymbolType.CALLBACK,
            node=node,
            scope=self.symbol_table.current_scope
        )
        self.symbol_table.define(symbol)

        # Define parameters in callback scope
        for param in node.parameters:
            param_symbol = Symbol(
                name=param.name,
                symbol_type=SymbolType.VARIABLE,
                node=param,
                scope=callback_scope,
                type_info=param.type
            )
            self.symbol_table.define(param_symbol)

        # Pop callback scope
        self.symbol_table.pop_scope()

    def visit_LaunchDecl(self, node: nodes.LaunchDecl) -> None:
        """Visit launch declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.LAUNCH,
            node=node,
            scope=self.symbol_table.current_scope,
            is_exported=True
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_error(
                f"Duplicate launch definition: '{node.name}'",
                node.location,
                "E003"
            )
            return

        # Create launch scope
        launch_scope = self.symbol_table.push_scope(node.name, "launch")

        # Process arguments
        for arg in node.arguments:
            self.visit(arg)

        # Pop launch scope
        self.symbol_table.pop_scope()

    def visit_ArgumentDecl(self, node: nodes.ArgumentDecl) -> None:
        """Visit argument declaration."""
        symbol = Symbol(
            name=node.name,
            symbol_type=SymbolType.ARGUMENT,
            node=node,
            scope=self.symbol_table.current_scope,
            type_info=node.type
        )

        if not self.symbol_table.define(symbol):
            self.analyzer._add_error(
                f"Duplicate argument: '{node.name}'",
                node.location,
                "E004"
            )


class ReferenceResolver(ASTVisitor):
    """Resolves references and performs type checking.

    Second pass of semantic analysis - validates that all
    references point to valid symbols and types are compatible.
    """

    def __init__(self, symbol_table: SymbolTable, analyzer: SemanticAnalyzer):
        self.symbol_table = symbol_table
        self.analyzer = analyzer

    def visit_File(self, node: nodes.File) -> None:
        """Visit file and process declarations."""
        if node.package:
            self.symbol_table.push_scope(node.package.name, "package")

        for decl in node.declarations:
            self.visit(decl)

        if node.package:
            self.symbol_table.pop_scope()

    def visit_NodeDecl(self, node: nodes.NodeDecl) -> None:
        """Visit node declaration and manage scope."""
        self.symbol_table.push_scope(node.name, "node")
        
        # Visit children (parameters, subscriptions, etc.)
        self.visit_children(node)
        
        self.symbol_table.pop_scope()

    def visit_CallbackDecl(self, node: nodes.CallbackDecl) -> None:
        """Visit callback declaration and manage scope."""
        self.symbol_table.push_scope(node.event, "callback")
        self.visit_children(node)
        self.symbol_table.pop_scope()

    def visit_LaunchDecl(self, node: nodes.LaunchDecl) -> None:
        """Visit launch declaration and manage scope."""
        self.symbol_table.push_scope(node.name, "launch")
        self.visit_children(node)
        self.symbol_table.pop_scope()

    def visit_IdentifierExpression(self, node: nodes.IdentifierExpression) -> Optional[nodes.Type]:
        """Visit identifier and check if it exists."""
        symbol = self.symbol_table.lookup(node.name)
        if symbol is None:
            self.analyzer._add_error(
                f"Undefined reference: '{node.name}'",
                node.location,
                "E005"
            )
            return None
        return symbol.type_info

    def visit_MemberAccessExpression(self, node: nodes.MemberAccessExpression) -> Optional[nodes.Type]:
        """Visit member access expression."""
        # First visit the object and get its type
        obj_type = self.visit(node.object)

        if obj_type is None:
            return None

        # Validate member exists on object type
        if isinstance(obj_type, nodes.StructType):
            for field in obj_type.fields:
                if field.name == node.member:
                    return field.type
            
            self.analyzer._add_error(
                f"Member '{node.member}' not found on struct type",
                node.location,
                "E006"
            )
        elif isinstance(obj_type, nodes.QualifiedType):
            # For now, we assume qualified types (ROS2 msgs) have the member
            # In a full implementation, we would look up the message definition
            return None
        
        return None

    def visit_LiteralExpression(self, node: nodes.LiteralExpression) -> nodes.Type:
        """Visit literal expression and return its type."""
        kind_map = {
            'int': nodes.PrimitiveTypeKind.INT,
            'float': nodes.PrimitiveTypeKind.FLOAT,
            'string': nodes.PrimitiveTypeKind.STRING,
            'bool': nodes.PrimitiveTypeKind.BOOL,
            'duration': nodes.PrimitiveTypeKind.DURATION,
        }
        kind = kind_map.get(node.literal_type, nodes.PrimitiveTypeKind.STRING)
        return nodes.PrimitiveType(location=node.location, kind=kind)

    def visit_CallExpression(self, node: nodes.CallExpression) -> Optional[nodes.Type]:
        """Visit function call expression."""
        # Visit the callee
        callee_type = self.visit(node.callee)

        # Visit arguments
        for arg in node.arguments:
            self.visit(arg)
        
        return None  # Function return types not fully implemented yet

    def visit_QualifiedIdentifierExpression(self, node: nodes.QualifiedIdentifierExpression) -> Optional[nodes.Type]:
        """Visit qualified identifier: pkg::member"""
        if not node.parts:
            return None
        
        # Check if first part is a package/import
        package_name = node.parts[0]
        import_scope = self._find_import(package_name)
        
        if import_scope:
            # Look up subsequent parts in the scope
            current_scope = import_scope
            for part in node.parts[1:]:
                symbol = current_scope.lookup_local(part)
                if symbol is None:
                    self.analyzer._add_error(
                        f"Member '{part}' not found in '{current_scope.name}'",
                        node.location,
                        "E007"
                    )
                    return None
                if symbol.symbol_type == SymbolType.PACKAGE:
                    current_scope = symbol.scope
                else:
                    return symbol.type_info
        
        # If not an import, it might be a ROS2 message reference used as a value (unlikely in NOS but possible)
        return None

    def visit_QualifiedType(self, node: nodes.QualifiedType) -> nodes.Type:
        """Visit qualified type reference."""
        # Check if the package exists (imported or builtin)
        # Standard ROS2 message packages
        builtin_packages = {
            'std_msgs', 'geometry_msgs', 'sensor_msgs', 'nav_msgs',
            'diagnostic_msgs', 'action_msgs', 'builtin_interfaces',
            'rcl_interfaces', 'tf2_msgs', 'trajectory_msgs', 'visualization_msgs',
            'stereo_msgs', 'shape_msgs', 'std_srvs', 'turtlesim', 'turtlesim_msgs'
        }

        if node.package:
            if node.package not in builtin_packages:
                # Check if package was imported
                import_scope = self._find_import(node.package)
                if import_scope is None:
                    self.analyzer._add_error(
                        f"Unknown package or import: '{node.package}'",
                        node.location,
                        "E008"
                    )
                else:
                    # Check if the type exists in that package scope
                    symbol = import_scope.lookup_local(node.name)
                    if symbol is None:
                        self.analyzer._add_error(
                            f"Type '{node.name}' not found in package '{node.package}'",
                            node.location,
                            "E009"
                        )
        else:
            # Unqualified type - check if it's a builtin primitive handled elsewhere
            # or if it exists in the current scope chain
            symbol = self.symbol_table.lookup(node.name)
            if symbol is None:
                # Could be a builtin primitive like 'string', 'int' etc.
                pass

        return node

    def _find_import(self, package_name: str) -> Optional[Scope]:
        """Find an imported package scope."""
        # Look through imports in current scope chain
        current = self.symbol_table.current_scope
        while current:
            for symbol in current.get_all_symbols():
                if (symbol.symbol_type == SymbolType.PACKAGE and
                    symbol.name == package_name):
                    return symbol.scope
            current = current.parent
        return None

    def visit_Constraint(self, node: nodes.Constraint) -> None:
        """Visit constraint and validate."""
        valid_constraints = {
            'range', 'one_of', 'min', 'max', 'pattern',
            'description', 'dynamic', 'computed', 'validate',
            'topic', 'qos', 'service', 'when', 'delay'
        }

        if node.name not in valid_constraints:
            self.analyzer._add_warning(
                f"Unknown constraint: '@{node.name}'",
                node.location,
                "W020"
            )

        # Visit constraint arguments
        for arg in node.arguments:
            self.visit(arg)
