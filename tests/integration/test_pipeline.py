"""Integration tests for the NOS compiler pipeline."""

import pytest
from nos.ast.nodes import (
    SourceLocation, File, PackageDecl, ImportDecl, NodeDecl, LaunchDecl,
    LiteralExpression
)
from nos.semantic import SemanticAnalyzer, SymbolTable
from nos.codegen import PythonGenerator, LaunchTranspiler
from nos.compiler.pipeline import CompilerPipeline, CompilationResult


class TestCompilerPipeline:
    """Tests for end-to-end compilation pipeline."""

    def test_pipeline_creation(self):
        pipeline = CompilerPipeline()
        assert pipeline.target == 'python'
        assert pipeline.verbose is False

    def test_pipeline_with_options(self):
        pipeline = CompilerPipeline({
            'target': 'cpp',
            'verbose': True
        })
        assert pipeline.target == 'cpp'
        assert pipeline.verbose is True

    def test_compile_empty_ast(self):
        """Test compilation with minimal AST."""
        pipeline = CompilerPipeline()
        loc = SourceLocation(1, 0, "test.node")

        # Create minimal AST
        file_node = File(
            location=loc,
            package=None,
            imports=[],
            declarations=[]
        )

        result = pipeline.compile_string("", "test.node")
        assert isinstance(result, CompilationResult)


class TestEndToEndFlow:
    """End-to-end flow tests."""

    def test_node_to_python_pipeline(self):
        """Full pipeline: Node AST -> Analysis -> Python Code."""
        from nos.ast.nodes import (
            ParameterDecl, PrimitiveType, PrimitiveTypeKind,
            LiteralExpression, CallbackDecl
        )

        # 1. Create AST
        loc = SourceLocation(1, 0, "test.node")
        param = ParameterDecl(
            location=loc,
            name="test_param",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="default", literal_type="string")
        )
        callback = CallbackDecl(
            location=loc,
            event="on_init",
            parameters=[],
            body="self.get_logger().info('Hello')"
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
            callbacks=[callback]
        )

        # 2. Analyze
        analyzer = SemanticAnalyzer()
        analysis = analyzer.analyze(node)
        assert analysis.is_valid

        # 3. Generate
        gen = PythonGenerator()
        output = gen.generate(node, analysis.symbol_table)

        # 4. Verify output
        assert "test_node_node.py" in output.files
        code = output.files["test_node_node.py"]
        assert "class TestNodeBase" in code
        assert "declare_parameter" in code
        assert "test_param" in code

    def test_launch_to_python_pipeline(self):
        """Full pipeline: Launch AST -> Analysis -> Python Code."""
        from nos.ast.nodes import ArgumentDecl, PrimitiveType, PrimitiveTypeKind

        # 1. Create AST
        loc = SourceLocation(1, 0, "test.node")
        arg = ArgumentDecl(
            location=loc,
            name="test_arg",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="value", literal_type="string")
        )
        launch = LaunchDecl(
            location=loc,
            name="TestLaunch",
            arguments=[arg],
            groups=[],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        # 2. Analyze
        analyzer = SemanticAnalyzer()
        analysis = analyzer.analyze(launch)

        # 3. Generate
        trans = LaunchTranspiler()
        output = trans.generate(launch, analysis.symbol_table)

        # 4. Verify output
        assert "test_launch_launch.py" in output.files
        code = output.files["test_launch_launch.py"]
        assert "LaunchDescription" in code
        assert "DeclareLaunchArgument" in code


class TestErrorHandling:
    """Tests for error handling in pipeline."""

    def test_undefined_reference_detection(self):
        """Test detection of undefined references."""
        from nos.semantic.analyzer import ReferenceResolver
        from nos.ast.nodes import IdentifierExpression

        loc = SourceLocation(10, 5, "test.node")
        symbol_table = SymbolTable()
        analyzer = SemanticAnalyzer()

        expr = IdentifierExpression(location=loc, name="undefined_var")

        resolver = ReferenceResolver(symbol_table, analyzer)
        resolver.visit(expr)

        # Should have recorded an error
        assert len(analyzer.diagnostics) > 0

    def test_compilation_result_errors(self):
        """Test CompilationResult error tracking."""
        result = CompilationResult()
        result.success = False
        result.errors.append("Syntax error at line 1")
        result.errors.append("Missing semicolon")

        assert not result.success
        assert len(result.errors) == 2


class TestMultiFileCompilation:
    """Tests for compiling multiple files."""

    def test_compile_multiple_nodes(self):
        """Test compiling multiple node definitions."""
        loc = SourceLocation(1, 0, "test.node")

        nodes = []
        for i in range(3):
            node = NodeDecl(
                location=loc,
                name=f"Node{i}",
                parameters=[],
                subscriptions=[],
                publications=[],
                services=[],
                actions=[],
                lifecycle=None,
                components=[],
                callbacks=[]
            )
            nodes.append(node)

        # Compile each
        gen = PythonGenerator()
        st = SymbolTable()

        for i, node in enumerate(nodes):
            output = gen.generate(node, st)
            assert f"node{i}_node.py" in output.files or f"Node{i}_node.py" in output.files


class TestRoundTrip:
    """Tests for source code round-tripping."""

    def test_node_structure_preservation(self):
        """Test that node structure is preserved through pipeline."""
        from nos.ast.nodes import SubscriptionDecl, QualifiedType

        loc = SourceLocation(1, 0, "test.node")

        sub = SubscriptionDecl(
            location=loc,
            name="input",
            message_type=QualifiedType(location=loc, package="std_msgs", name="String"),
            topic=LiteralExpression(location=loc, value="/input", literal_type="string"),
            qos=None,
            constraints=[]
        )
        node = NodeDecl(
            location=loc,
            name="RoundTripNode",
            parameters=[],
            subscriptions=[sub],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        # Verify structure before
        assert len(node.subscriptions) == 1
        assert node.subscriptions[0].name == "input"
        assert node.subscriptions[0].message_type.name == "String"

        # Go through pipeline
        analyzer = SemanticAnalyzer()
        analysis = analyzer.analyze(node)

        gen = PythonGenerator()
        output = gen.generate(node, analysis.symbol_table)

        # Verify output contains expected elements
        code = output.files["round_trip_node_node.py"]
        assert "input" in code
        assert "create_subscription" in code

    def test_pipeline_fails_on_syntax_error(self):
        """Test that compile_string fails on syntax errors in embedded Python."""
        pipeline = CompilerPipeline()
        source = """package test_pkg
version "0.1.0"

node SyntaxErrorNode {
    on_init -> {
        if True
            print("Missing colon")
    }
}
"""
        result = pipeline.compile_string(source, "test.node")
        assert result.success is False
        assert len(result.errors) > 0
        assert any("Syntax error" in err or "invalid syntax" in err for err in result.errors)
