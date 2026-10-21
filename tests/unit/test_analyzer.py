"""Unit tests for the semantic analyzer and symbol table."""

import pytest
from nos.ast.nodes import (
    SourceLocation, NodeDecl, ParameterDecl, PrimitiveType, PrimitiveTypeKind,
    PackageDecl, LiteralExpression, IdentifierExpression, LaunchDecl
)
from nos.semantic import (
    SymbolTable, Scope, Symbol, SymbolType,
    SemanticAnalyzer, Diagnostic, DiagnosticSeverity
)


class TestScope:
    """Tests for Scope class."""

    def test_scope_creation(self):
        scope = Scope("test", None, "block")
        assert scope.name == "test"
        assert scope.parent is None
        assert len(scope.symbols) == 0

    def test_scope_lookup(self):
        parent = Scope("global", None, "global")
        child = Scope("child", parent, "block")

        symbol = Symbol("x", SymbolType.VARIABLE, None, parent)
        parent.define(symbol)

        # Should find in parent
        found = child.lookup("x")
        assert found is not None
        assert found.name == "x"

    def test_scope_lookup_local(self):
        parent = Scope("global", None, "global")
        child = Scope("child", parent, "block")

        symbol = Symbol("x", SymbolType.VARIABLE, None, parent)
        parent.define(symbol)

        # Should not find in child scope locally
        found = child.lookup_local("x")
        assert found is None

        # Should find in parent scope locally
        found = parent.lookup_local("x")
        assert found is not None

    def test_scope_define_duplicate(self):
        scope = Scope("test", None, "block")
        symbol1 = Symbol("x", SymbolType.VARIABLE, None, scope)
        symbol2 = Symbol("x", SymbolType.VARIABLE, None, scope)

        assert scope.define(symbol1) is True
        assert scope.define(symbol2) is False  # Duplicate


class TestSymbolTable:
    """Tests for SymbolTable class."""

    def test_symbol_table_creation(self):
        st = SymbolTable()
        assert st.global_scope is not None
        assert st.current_scope == st.global_scope

    def test_push_pop_scope(self):
        st = SymbolTable()
        new_scope = st.push_scope("test", "block")
        assert st.current_scope == new_scope
        assert new_scope.parent == st.global_scope

        st.pop_scope()
        assert st.current_scope == st.global_scope

    def test_define_and_lookup(self):
        st = SymbolTable()
        loc = SourceLocation(1, 0, "test.node")
        symbol = Symbol(
            name="my_param",
            symbol_type=SymbolType.PARAMETER,
            node=None,
            scope=st.current_scope
        )
        st.define(symbol)

        found = st.lookup("my_param")
        assert found is not None
        assert found.name == "my_param"

    def test_find_by_type(self):
        st = SymbolTable()
        loc = SourceLocation(1, 0, "test.node")

        node_symbol = Symbol("Node1", SymbolType.NODE, None, st.current_scope)
        param_symbol = Symbol("param1", SymbolType.PARAMETER, None, st.current_scope)

        st.define(node_symbol)
        st.define(param_symbol)

        nodes = st.find_by_type(SymbolType.NODE)
        assert len(nodes) == 1
        assert nodes[0].name == "Node1"

    def test_find_parameters(self):
        st = SymbolTable()
        loc = SourceLocation(1, 0, "test.node")

        node_scope = st.push_scope("MyNode", "node")
        param = Symbol("speed", SymbolType.PARAMETER, None, node_scope)
        node_scope.define(param)

        params = st.find_parameters("MyNode")
        assert len(params) == 1
        assert params[0].name == "speed"


class TestSemanticAnalyzer:
    """Tests for SemanticAnalyzer class."""

    def test_analyzer_creation(self):
        analyzer = SemanticAnalyzer()
        assert analyzer.symbol_table is not None
        assert len(analyzer.diagnostics) == 0

    def test_analyze_empty_file(self):
        analyzer = SemanticAnalyzer()
        loc = SourceLocation(1, 0, "test.node")
        file_node = PackageDecl(
            location=loc,
            name="test_pkg"
        )

        result = analyzer.analyze(file_node)
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_analyze_node_with_params(self):
        analyzer = SemanticAnalyzer()
        loc = SourceLocation(1, 0, "test.node")

        param = ParameterDecl(
            location=loc,
            name="frame_id",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="base", literal_type="string")
        )
        node = NodeDecl(
            location=loc,
            name="TestNode",
            parameters=[param],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        result = analyzer.analyze(node)
        # Should have parameter symbol defined
        params = result.symbol_table.find_parameters("TestNode")
        assert len(params) == 1

    def test_duplicate_parameter_error(self):
        analyzer = SemanticAnalyzer()
        loc = SourceLocation(1, 0, "test.node")

        param1 = ParameterDecl(
            location=loc,
            name="speed",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.FLOAT)
        )
        param2 = ParameterDecl(
            location=loc,
            name="speed",  # Duplicate
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.FLOAT)
        )
        node = NodeDecl(
            location=loc,
            name="TestNode",
            parameters=[param1, param2],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        result = analyzer.analyze(node)
        assert len(result.errors) == 1  # Duplicate parameter error


class TestDiagnostics:
    """Tests for Diagnostic class."""

    def test_error_diagnostic(self):
        loc = SourceLocation(10, 5, "test.node")
        diag = Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            message="Undefined variable",
            location=loc,
            code="E001"
        )
        assert diag.severity == DiagnosticSeverity.ERROR
        assert str(diag) == "test.node:10:5: ERROR: Undefined variable"

    def test_warning_diagnostic(self):
        loc = SourceLocation(5, 0, "test.node")
        diag = Diagnostic(
            severity=DiagnosticSeverity.WARNING,
            message="Unused variable",
            location=loc
        )
        assert diag.severity == DiagnosticSeverity.WARNING


class TestSymbolTypes:
    """Tests for SymbolType enum."""

    def test_symbol_types(self):
        assert SymbolType.PACKAGE.name == "PACKAGE"
        assert SymbolType.NODE.name == "NODE"
        assert SymbolType.PARAMETER.name == "PARAMETER"
        assert SymbolType.SUBSCRIPTION.name == "SUBSCRIPTION"
        assert SymbolType.PUBLICATION.name == "PUBLICATION"

    def test_symbol_equality(self):
        scope = Scope("test", None, "block")
        s1 = Symbol("x", SymbolType.VARIABLE, None, scope)
        s2 = Symbol("x", SymbolType.VARIABLE, None, scope)
        assert s1 == s2
