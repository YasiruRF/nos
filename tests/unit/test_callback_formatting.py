"""Callback bodies keep their formatting (#3)."""

import ast

from nos.compiler.pipeline import CompilerPipeline
from tests.helpers import assert_valid_python

NESTED = '''package a
node N {
  on_init -> {
    x = {"a": 1}
    for i in range(3):
        if i % 2:
            odd = i

        else:
            y = [i,
                 i + 1]
    self.get_logger().info(f"v {x}")
  }
}
'''


def generated(source):
    result = CompilerPipeline().compile_string(source, "t.node")
    assert result.success, result.errors
    assert_valid_python(result.files)
    return result.files["n_node.py"]


def method_source(code, name):
    tree = ast.parse(code)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    fn = next(f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == name)
    return fn


def test_nested_control_flow_and_blank_lines_survive():
    code = generated(NESTED)
    assert "                    odd = i\n\n                else:" in code
    assert "y = [i,\n                         i + 1]" in code


def test_nested_structure_is_semantically_unchanged():
    fn = method_source(generated(NESTED), "on_init")
    try_node = fn.body[1] if isinstance(fn.body[0], ast.Expr) else fn.body[0]
    body = try_node.body
    assert isinstance(body[1], ast.For)
    assert isinstance(body[1].body[0], ast.If)
    assert body[1].body[0].orelse


def test_multiline_string_content_is_not_indented():
    src = 'package a\nnode N {\n  on_init -> {\n    msg = """line1\nline2\n    line3"""\n  }\n}\n'
    code = generated(src)
    fn = method_source(code, "on_init")
    string = next(n.value for n in ast.walk(fn)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and n.value.startswith("line1"))
    assert string == "line1\nline2\n    line3"


def test_tabs_are_accepted():
    src = "package a\nnode N {\n  on_init -> {\n\tfor i in range(2):\n\t\tx = i\n  }\n}\n"
    generated(src)


def test_callback_with_parameters_keeps_formatting():
    src = '''package a
node N {
  on tick(n: int) -> {
    while n > 0:
        n -= 1

        if n == 2:
            break
  }
}
'''
    code = generated(src)
    assert "            while n > 0:\n                n -= 1\n\n                if n == 2:" in code
