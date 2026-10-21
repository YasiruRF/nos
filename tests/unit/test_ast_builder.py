"""Unit tests for AST node classes and the AST builder."""

"""
Tests cover:
    - SourceLocation creation and string representation
    - AST node creation (PackageDecl, NodeDecl, ParameterDecl, etc.)
    - Node relationships and field access
    - Expression types (Literal, Identifier, Binary)

Run these tests:
    $ pytest tests/test_ast.py -v
"""

import pytest

from nos.ast.builder import ASTBuilder
from nos.ast.nodes import (
    ASTNode,
    BinaryExpression,
    Constraint,
    File,
    IdentifierExpression,
    LaunchDecl,
    LiteralExpression,
    NodeDecl,
    PackageDecl,
    ParameterDecl,
    PrimitiveType,
    PrimitiveTypeKind,
    PublicationDecl,
    QualifiedType,
    SourceLocation,
    SubscriptionDecl,
)


class TestSourceLocation:
    """Tests for SourceLocation class."""

    def test_location_creation(self):
        loc = SourceLocation(line=10, column=5, file="test.node")
        assert loc.line == 10
        assert loc.column == 5
        assert loc.file == "test.node"

    def test_location_string(self):
        loc = SourceLocation(line=10, column=5, file="test.node")
        assert str(loc) == "test.node:10:5"


class TestPackageDecl:
    """Tests for PackageDecl AST node."""

    def test_package_creation(self):
        loc = SourceLocation(1, 0, "test.node")
        package = PackageDecl(
            location=loc, name="robot_navigation", version="1.0.0", dependencies=["rclpy", "geometry_msgs"]
        )
        assert package.name == "robot_navigation"
        assert package.version == "1.0.0"
        assert package.dependencies == ["rclpy", "geometry_msgs"]

    def test_package_no_version(self):
        loc = SourceLocation(1, 0, "test.node")
        package = PackageDecl(location=loc, name="simple_pkg")
        assert package.name == "simple_pkg"
        assert package.version is None


class TestNodeDecl:
    """Tests for NodeDecl AST node."""

    def test_node_creation(self):
        loc = SourceLocation(1, 0, "test.node")
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
            callbacks=[],
        )
        assert node.name == "TestNode"
        assert len(node.parameters) == 0

    def test_node_with_parameters(self):
        loc = SourceLocation(1, 0, "test.node")
        param = ParameterDecl(
            location=loc,
            name="frame_id",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.STRING),
            default_value=LiteralExpression(location=loc, value="base_link", literal_type="string"),
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
            callbacks=[],
        )
        assert len(node.parameters) == 1
        assert node.parameters[0].name == "frame_id"


class TestParameterDecl:
    """Tests for ParameterDecl AST node."""

    def test_parameter_with_constraints(self):
        loc = SourceLocation(1, 0, "test.node")
        constraint = Constraint(
            location=loc,
            name="range",
            arguments=[
                LiteralExpression(location=loc, value=0.0, literal_type="float"),
                LiteralExpression(location=loc, value=100.0, literal_type="float"),
            ],
        )
        param = ParameterDecl(
            location=loc,
            name="speed",
            type=PrimitiveType(location=loc, kind=PrimitiveTypeKind.FLOAT),
            default_value=LiteralExpression(location=loc, value=10.0, literal_type="float"),
            constraints=[constraint],
        )
        assert param.name == "speed"
        assert len(param.constraints) == 1
        assert param.constraints[0].name == "range"


class TestSubscriptionDecl:
    """Tests for SubscriptionDecl AST node."""

    def test_subscription_creation(self):
        loc = SourceLocation(1, 0, "test.node")
        sub = SubscriptionDecl(
            location=loc,
            name="scan",
            message_type=QualifiedType(location=loc, package="sensor_msgs", name="LaserScan"),
            topic=LiteralExpression(location=loc, value="/scan", literal_type="string"),
            qos=None,
            constraints=[],
        )
        assert sub.name == "scan"
        assert sub.message_type.name == "LaserScan"
        assert sub.message_type.package == "sensor_msgs"


class TestASTBuilder:
    """Tests for ASTBuilder class."""

    def test_builder_creation(self):
        builder = ASTBuilder("test.node")
        assert builder.file_name == "test.node"

    def test_location_helper(self):
        builder = ASTBuilder("test.node")

        # Mock context object
        class MockCtx:
            class MockStart:
                line = 5
                column = 10

            start = MockStart()

        loc = builder._loc(MockCtx())
        assert loc.line == 5
        assert loc.column == 10
        assert loc.file == "test.node"


class TestExpressionNodes:
    """Tests for expression AST nodes."""

    def test_literal_expression(self):
        loc = SourceLocation(1, 0, "test.node")
        expr = LiteralExpression(location=loc, value=42, literal_type="int")
        assert expr.value == 42
        assert expr.literal_type == "int"

    def test_identifier_expression(self):
        loc = SourceLocation(1, 0, "test.node")
        expr = IdentifierExpression(location=loc, name="my_param")
        assert expr.name == "my_param"

    def test_binary_expression(self):
        loc = SourceLocation(1, 0, "test.node")
        left = LiteralExpression(location=loc, value=10, literal_type="int")
        right = LiteralExpression(location=loc, value=20, literal_type="int")
        expr = BinaryExpression(location=loc, operator="+", left=left, right=right)
        assert expr.operator == "+"
        assert expr.left.value == 10
        assert expr.right.value == 20


class TestFileNode:
    """Tests for File AST node (root)."""

    def test_empty_file(self):
        loc = SourceLocation(1, 0, "test.node")
        file_node = File(location=loc, package=None, imports=[], declarations=[])
        assert file_node.package is None
        assert len(file_node.declarations) == 0

    def test_file_with_package(self):
        loc = SourceLocation(1, 0, "test.node")
        package = PackageDecl(location=loc, name="test_pkg", version="1.0.0")
        file_node = File(location=loc, package=package, imports=[], declarations=[])
        assert file_node.package.name == "test_pkg"
