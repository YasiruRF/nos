"""Unit tests for code generation and launch transpilation."""

import pytest
from nos.ast.nodes import (
    SourceLocation, NodeDecl, ParameterDecl, PrimitiveType, PrimitiveTypeKind,
    LiteralExpression, QualifiedType, SubscriptionDecl, PublicationDecl,
    LaunchDecl, GroupDecl, NodeInstance, ContainerDecl, ComponentInstance,
    IdentifierExpression, BinaryExpression
)
from nos.semantic import SymbolTable, SemanticAnalyzer
from nos.codegen import PythonGenerator, LaunchTranspiler, GenerationOutput


class TestPythonGenerator:
    """Tests for PythonGenerator class."""

    def test_generator_creation(self):
        gen = PythonGenerator()
        assert gen.target == 'python'

    def test_generate_simple_node(self):
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="TestNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        assert isinstance(output, GenerationOutput)
        assert "test_node_node.py" in output.files

    def test_generate_node_with_params(self):
        loc = SourceLocation(1, 0, "test.nos")
        param = ParameterDecl(
            location=loc,
            name="frame_id",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="base", literal_type="string")
        )
        node = NodeDecl(
            location=loc,
            name="ParamNode",
            parameters=[param],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["param_node_node.py"]
        assert "frame_id" in code
        assert "declare_parameter" in code

    def test_generate_subscription(self):
        loc = SourceLocation(1, 0, "test.nos")
        sub = SubscriptionDecl(
            location=loc,
            name="scan",
            message_type=QualifiedType(location=loc, package="sensor_msgs", name="LaserScan"),
            topic=LiteralExpression(location=loc, value="/scan", literal_type="string"),
            qos=None,
            constraints=[]
        )
        node = NodeDecl(
            location=loc,
            name="SubNode",
            parameters=[],
            subscriptions=[sub],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["sub_node_node.py"]
        assert "create_subscription" in code
        assert "LaserScan" in code

    def test_camel_to_snake(self):
        gen = PythonGenerator()
        assert gen._camel_to_snake("TestNode") == "test_node"
        assert gen._camel_to_snake("LidarProcessor") == "lidar_processor"
        assert gen._camel_to_snake("URLParser") == "url_parser"

    def test_indent(self):
        gen = PythonGenerator()
        text = "line1\nline2"
        indented = gen._indent(text, 1)
        assert "    line1" in indented
        assert "    line2" in indented


class TestLaunchTranspiler:
    """Tests for LaunchTranspiler class."""

    def test_transpiler_creation(self):
        trans = LaunchTranspiler()
        assert trans.launch_counter == 0

    def test_generate_launch(self):
        loc = SourceLocation(1, 0, "test.nos")
        launch = LaunchDecl(
            location=loc,
            name="TestLaunch",
            arguments=[],
            groups=[],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        assert isinstance(output, GenerationOutput)
        assert "test_launch_launch.py" in output.files

    def test_generate_launch_with_group(self):
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeInstance(
            location=loc,
            name="lidar",
            node_type="LidarDriver",
            parameters={}
        )
        group = GroupDecl(
            location=loc,
            name="sensors",
            namespace=LiteralExpression(location=loc, value="sensors", literal_type="string"),
            nodes=[node]
        )
        launch = LaunchDecl(
            location=loc,
            name="GroupLaunch",
            arguments=[],
            groups=[group],
            containers=[],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        code = output.files["group_launch_launch.py"]
        assert "GroupAction" in code
        assert "lidar" in code

    def test_generate_container(self):
        loc = SourceLocation(1, 0, "test.nos")
        comp = ComponentInstance(
            location=loc,
            name="processor",
            component_type="ImageProcessor",
            parameters={}
        )
        container = ContainerDecl(
            location=loc,
            name="PerceptionContainer",
            container_name=LiteralExpression(location=loc, value="perception_container", literal_type="string"),
            components=[comp]
        )
        launch = LaunchDecl(
            location=loc,
            name="ContainerLaunch",
            arguments=[],
            groups=[],
            containers=[container],
            includes=[],
            lifecycle_manager=None,
            events=[]
        )

        trans = LaunchTranspiler()
        st = SymbolTable()
        output = trans.generate(launch, st)

        code = output.files["container_launch_launch.py"]
        assert "ComposableNodeContainer" in code
        assert "ComposableNode" in code


class TestGenerationOutput:
    """Tests for GenerationOutput class."""

    def test_output_creation(self):
        out = GenerationOutput()
        assert len(out.files) == 0

    def test_add_file(self):
        out = GenerationOutput()
        out.add_file("test.py", "print('hello')")
        assert "test.py" in out.files
        assert out.files["test.py"] == "print('hello')"

    def test_get_file(self):
        out = GenerationOutput()
        out.add_file("test.py", "content")
        assert out.get_file("test.py") == "content"
        assert out.get_file("missing.py") == ""


class TestCodeGenerationEdgeCases:
    """Tests for edge cases in code generation."""

    def test_reserved_keyword_escape(self):
        """Test that reserved keywords are escaped."""
        gen = PythonGenerator()
        reserved = gen._reserved_keywords()
        assert "class" in reserved
        assert "def" in reserved

    def test_expression_to_python_literal(self):
        """Test expression conversion to Python."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        # Integer literal
        int_lit = LiteralExpression(location=loc, value=42, literal_type="int")
        assert gen._expression_to_python(int_lit) == "42"

        # String literal
        str_lit = LiteralExpression(location=loc, value="hello", literal_type="string")
        assert gen._expression_to_python(str_lit) == '"hello"'

        # Boolean literal
        bool_lit = LiteralExpression(location=loc, value=True, literal_type="bool")
        assert gen._expression_to_python(bool_lit) == "True"

    def test_expression_to_python_identifier(self):
        """Test identifier expression conversion."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        ident = IdentifierExpression(location=loc, name="my_var")
        assert gen._expression_to_python(ident) == "my_var"

    def test_python_type_conversion(self):
        """Test NOS type to Python type conversion."""
        gen = PythonGenerator()
        loc = SourceLocation(1, 0, "test.nos")

        # Primitive types
        int_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.INT)
        assert gen._get_python_type(int_type) == "int"

        float_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.FLOAT)
        assert gen._get_python_type(float_type) == "float"

        string_type = PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING)
        assert gen._get_python_type(string_type) == "str"

    def test_empty_node_generation(self):
        """Test generation of empty node."""
        loc = SourceLocation(1, 0, "test.nos")
        node = NodeDecl(
            location=loc,
            name="EmptyNode",
            parameters=[],
            subscriptions=[],
            publications=[],
            services=[],
            actions=[],
            lifecycle=None,
            components=[],
            callbacks=[]
        )

        gen = PythonGenerator()
        st = SymbolTable()
        output = gen.generate(node, st)

        code = output.files["empty_node_node.py"]
        # Should still have valid Python structure
        assert "class" in code
        assert "def __init__" in code
