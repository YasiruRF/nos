"""Main semantic analyzer for NOS.

Orchestrates semantic analysis passes including:
- Symbol table construction
- Type checking
- Constraint validation
- Reference resolution
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum

from ..ast import nodes
from ..ast.visitor import ASTVisitor
from . import constraints as constraint_registry
from .symbol_table import SymbolTable, Symbol, Scope, SymbolType

# Interface packages that ship with every ROS 2 distribution
BUILTIN_PACKAGES = frozenset({
    'std_msgs', 'geometry_msgs', 'sensor_msgs', 'nav_msgs',
    'diagnostic_msgs', 'action_msgs', 'builtin_interfaces',
    'rcl_interfaces', 'tf2_msgs', 'trajectory_msgs', 'visualization_msgs',
    'stereo_msgs', 'shape_msgs', 'std_srvs', 'lifecycle_msgs',
})


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
        # Interface packages the source may use: builtin + `depends:` + imports
        self.known_packages: Set[str] = set(BUILTIN_PACKAGES)
        # `import pkg::Type [as Alias]` -> {local name: (pkg, Type)}
        self.imported_types: Dict[str, Tuple[str, str]] = {}

    def analyze(self, ast: nodes.ASTNode) -> AnalysisResult:
        """Analyze an AST and return results.

        Args:
            ast: The root AST node to analyze

        Returns:
            AnalysisResult containing validated AST and diagnostics
        """
        self.diagnostics.clear()
        self.symbol_table = SymbolTable()
        self.current_node = None
        self._collect_packages(ast)

        self._reject_interface_declarations(ast)
        self._warn_ungenerated_features(ast)

        # Pass 1: Build symbol table
        self._build_symbols(ast)

        # Pass 2: Resolve references and type check
        self._resolve_and_check(ast)

        return AnalysisResult(
            ast=ast,
            symbol_table=self.symbol_table,
            diagnostics=self.diagnostics.copy()
        )

    def _collect_packages(self, ast: nodes.ASTNode):
        """Work out which interface packages and types the source may refer to."""
        self.known_packages = set(BUILTIN_PACKAGES)
        self.imported_types = {}
        if not isinstance(ast, nodes.File):
            return

        if ast.package:
            self.known_packages.update(ast.package.dependencies)

        for imp in ast.imports:
            parts = imp.qualified_name.split("::")
            self.known_packages.add(parts[0])
            if len(parts) >= 2:
                self.imported_types[imp.alias or parts[-1]] = (parts[0], parts[-1])

    def _warn_ungenerated_features(self, ast: nodes.ASTNode):
        """Parsed constructs that no generator emits yet."""
        if not isinstance(ast, nodes.File):
            return
        for decl in ast.declarations:
            if isinstance(decl, nodes.NodeDecl):
                for comp in decl.components:
                    self._add_warning(
                        f"Component '{comp.name}' is parsed but not generated yet",
                        comp.location, "W025")
            elif isinstance(decl, nodes.LaunchDecl):
                for event in decl.events:
                    self._add_warning(
                        f"Launch event handler on \"{event.trigger}\" is parsed but not generated yet",
                        event.location, "W023")
                if decl.lifecycle_manager and decl.lifecycle_manager.transitions:
                    self._add_warning(
                        "Lifecycle manager transitions are not generated; "
                        "nav2_lifecycle_manager configures and activates the managed nodes itself",
                        decl.lifecycle_manager.location, "W024")

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
        self.symbol_table.push_scope(node.name, "node")
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
        # Define callback symbol (in the node scope, so duplicates collide)
        symbol = Symbol(
            name=node.event,
            symbol_type=SymbolType.CALLBACK,
            node=node,
            scope=self.symbol_table.current_scope
        )
        if not self.symbol_table.define(symbol):
            self.analyzer._add_error(
                f"Duplicate callback: '{node.event}'",
                node.location,
                "E011"
            )

        # Create callback scope
        callback_scope = self.symbol_table.push_scope(node.event, "callback")

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
        self.symbol_table.push_scope(node.name, "launch")

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
            for struct_field in obj_type.fields:
                if struct_field.name == node.member:
                    return struct_field.type
            
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
        self.visit(node.callee)

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
        """Visit qualified type reference.

        The package must be a builtin ROS package, listed in ``depends:`` or
        imported.  An unqualified name is resolved through
        ``import pkg::Type [as Alias]`` (the node is rewritten to the
        qualified form so code generation sees the real package).
        """
        analyzer = self.analyzer

        if not node.package:
            imported = analyzer.imported_types.get(node.name)
            if imported:
                node.package, node.name = imported
            elif node.name:
                analyzer._add_warning(
                    f"Unqualified type '{node.name}': write 'package::{node.name}' "
                    f"or import it with 'import package::{node.name}'",
                    node.location,
                    "W022"
                )
            return node

        if node.package not in analyzer.known_packages:
            analyzer._add_error(
                f"Unknown package or import: '{node.package}' "
                f"(add it to 'depends:' or import it)",
                node.location,
                "E008"
            )
            return node

        available = _installed_interfaces(node.package)
        if available is not None and node.name not in available:
            analyzer._add_warning(
                f"Type '{node.name}' was not found in the installed package '{node.package}'",
                node.location,
                "W021"
            )

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
        """Visit constraint: the name must be in the constraint registry."""
        if node.name not in constraint_registry.CONSTRAINTS:
            self.analyzer._add_warning(
                f"Unknown constraint: '@{node.name}'",
                node.location,
                "W020"
            )

        for arg in node.arguments:
            self.visit(arg)

    # ------------------------------------------------------------------
    # Declaration-level checks
    # ------------------------------------------------------------------

    def _check_constraints(self, constraints: List[nodes.Constraint], target: str) -> None:
        """Check each constraint against the registry for the declaration kind."""
        for constraint in constraints:
            spec = constraint_registry.CONSTRAINTS.get(constraint.name)
            if spec is None:
                continue  # reported as W020 by visit_Constraint

            if spec.targets is not None and target not in spec.targets:
                self.analyzer._add_error(
                    f"@{constraint.name} cannot be applied to a {target}",
                    constraint.location,
                    "E012"
                )
                continue

            count = len(constraint.arguments)
            if count < spec.min_args or (spec.max_args is not None and count > spec.max_args):
                expected = (str(spec.min_args) if spec.max_args == spec.min_args
                            else f"{spec.min_args}+" if spec.max_args is None
                            else f"{spec.min_args}-{spec.max_args}")
                self.analyzer._add_error(
                    f"@{constraint.name} takes {expected} argument(s), got {count}",
                    constraint.location,
                    "E012"
                )

            if constraint.name == "range":
                self._check_range(constraint)
            elif constraint.name == "qos":
                self._check_qos(constraint)

    def _check_range(self, constraint: nodes.Constraint) -> None:
        bounds = [a.value for a in constraint.arguments
                  if isinstance(a, nodes.LiteralExpression) and a.literal_type in ("int", "float")]
        if len(bounds) == 2 and bounds[0] > bounds[1]:
            self.analyzer._add_error(
                f"@range minimum ({bounds[0]}) is greater than maximum ({bounds[1]})",
                constraint.location,
                "E014"
            )

    def _check_qos(self, constraint: nodes.Constraint) -> None:
        for key, expr in constraint.named_arguments.items():
            if key not in constraint_registry.QOS_KEYS:
                self.analyzer._add_error(
                    f"Unknown @qos setting '{key}' "
                    f"(expected one of: {', '.join(sorted(constraint_registry.QOS_KEYS))})",
                    constraint.location,
                    "E013"
                )
                continue
            allowed = constraint_registry.QOS_VALUES.get(key)
            value = (expr.value if isinstance(expr, nodes.LiteralExpression)
                     else expr.name if isinstance(expr, nodes.IdentifierExpression) else None)
            if allowed is not None and value not in allowed:
                self.analyzer._add_error(
                    f"Invalid @qos {key} '{value}' (expected one of: {', '.join(sorted(allowed))})",
                    constraint.location,
                    "E013"
                )
            if key == "depth" and not (isinstance(value, int) and not isinstance(value, bool) and value > 0):
                self.analyzer._add_error(
                    "@qos depth must be a positive integer",
                    constraint.location,
                    "E013"
                )
        if len(constraint.named_arguments) != len(constraint.arguments):
            self.analyzer._add_error(
                "@qos arguments must be written as name=value",
                constraint.location,
                "E013"
            )

    def _check_default(self, decl) -> None:
        """A literal default must be compatible with the declared primitive type."""
        default, declared = decl.default_value, decl.type
        if not isinstance(default, nodes.LiteralExpression) \
                or not isinstance(declared, nodes.PrimitiveType):
            return

        K = nodes.PrimitiveTypeKind
        compatible = {
            K.BOOL: {"bool"},
            K.INT: {"int"},
            K.FLOAT: {"int", "float"},
            K.DOUBLE: {"int", "float"},
            K.STRING: {"string"},
            K.DURATION: {"duration"},
            K.TIME: {"duration"},
        }.get(declared.kind)
        if compatible is not None and default.literal_type not in compatible:
            self.analyzer._add_error(
                f"Default value of '{decl.name}' is a {default.literal_type}, "
                f"but its type is {declared.kind.value}",
                default.location,
                "E015"
            )

    def visit_ParameterDecl(self, node: nodes.ParameterDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.PARAMETER)
        self._check_default(node)
        self.visit_children(node)

    def visit_ArgumentDecl(self, node: nodes.ArgumentDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.ARGUMENT)
        self._check_default(node)
        self.visit_children(node)

    def visit_SubscriptionDecl(self, node: nodes.SubscriptionDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.SUBSCRIPTION)
        self.visit_children(node)

    def visit_PublicationDecl(self, node: nodes.PublicationDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.PUBLICATION)
        self.visit_children(node)

    def visit_ServiceDecl(self, node: nodes.ServiceDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.SERVICE)
        self.visit_children(node)

    def visit_ActionDecl(self, node: nodes.ActionDecl) -> None:
        self._check_constraints(node.constraints, constraint_registry.ACTION)
        self.visit_children(node)


def _installed_interfaces(package: str) -> Optional[Set[str]]:
    """Names of the message/service/action types of an installed ROS package.

    Returns None when ROS is not available, in which case types are not verified.
    """
    try:
        from rosidl_runtime_py import get_interface_packages, get_interfaces  # type: ignore
    except ImportError:
        return None
    try:
        if package not in get_interface_packages():
            return None
        return {
            name.split("/")[-1]
            for names in [get_interfaces().get(package, [])]
            for name in names
        }
    except Exception:  # a broken ROS install must not break compilation
        return None
