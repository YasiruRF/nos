"""Regression tests for AST builder crashes (#13, #14)."""

import pytest

from nos.ast import nodes
from nos.compiler.pipeline import CompilerPipeline


def parse(source: str) -> nodes.File:
    pipeline = CompilerPipeline()
    ast = pipeline._parse_string(source, "t.node")
    assert ast is not None
    return ast


def only_node(ast: nodes.File) -> nodes.NodeDecl:
    return next(d for d in ast.declarations if isinstance(d, nodes.NodeDecl))


class TestListTypes:
    def test_parameter_list_of_int(self):
        node = only_node(parse("package a\nnode N { parameters { xs: list<int> = [1, 2] } }"))
        t = node.parameters[0].type
        assert isinstance(t, nodes.ListType)
        assert t.element_type.kind == nodes.PrimitiveTypeKind.INT

    def test_nested_list(self):
        node = only_node(parse("package a\nnode N { parameters { xs: list<list<float>> = [] } }"))
        t = node.parameters[0].type
        assert isinstance(t.element_type, nodes.ListType)
        assert t.element_type.element_type.kind == nodes.PrimitiveTypeKind.FLOAT

    def test_list_of_qualified_type(self):
        node = only_node(parse("package a\nnode N { parameters { ps: list<geometry_msgs::Point> = [] } }"))
        elem = node.parameters[0].type.element_type
        assert isinstance(elem, nodes.QualifiedType)
        assert (elem.package, elem.name) == ("geometry_msgs", "Point")

    def test_callback_parameter_list(self):
        node = only_node(parse("package a\nnode N { on foo(x: list<float>) -> { pass } }"))
        assert isinstance(node.callbacks[0].parameters[0].type, nodes.ListType)

    def test_struct_field_list(self):
        node = only_node(parse("package a\nnode N { parameters { s: struct { xs: list<int> } } }"))
        assert isinstance(node.parameters[0].type.fields[0].type, nodes.ListType)

    def test_list_codegen_is_valid_python(self):
        result = CompilerPipeline().compile_string("package a\nnode N { on foo(x: list<float>) -> { pass } }", "t.node")
        assert result.success, result.errors
        code = result.files["n_node.py"]
        assert "x: List[float]" in code
        assert "from typing import List" in code


class TestInterfaceDeclarations:
    SRC = """package a
message M @id(1) { x: int }
service S @id(2) { request { a: int } response { b: int } }
action A @id(3) { goal { a: int } feedback { b: int } result { c: int } }
"""

    def interfaces(self):
        ast = parse(self.SRC)
        return [i for d in ast.declarations if isinstance(d, nodes.InterfaceDecl) for i in d.declarations]

    def test_parses_all_three_kinds(self):
        msg, srv, act = self.interfaces()
        assert (msg.name, msg.id) == ("M", 1)
        assert [f.name for f in msg.fields] == ["x"]
        assert (srv.name, srv.id) == ("S", 2)
        assert [f.name for f in srv.request_fields] == ["a"]
        assert [f.name for f in srv.response_fields] == ["b"]
        assert (act.name, act.id) == ("A", 3)
        assert [f.name for f in act.goal_fields] == ["a"]
        assert [f.name for f in act.feedback_fields] == ["b"]
        assert [f.name for f in act.result_fields] == ["c"]

    def test_compiler_reports_not_supported(self):
        result = CompilerPipeline().compile_string(self.SRC, "t.node")
        assert not result.success
        assert len([e for e in result.errors if "not supported yet" in e]) == 3
