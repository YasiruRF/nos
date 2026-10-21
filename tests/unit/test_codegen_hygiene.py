"""Regression tests for lifecycle codegen, imports and identifier handling (#12, #16, #17, #18)."""

import ast
import subprocess
import sys

from nos.compiler.pipeline import CompilerPipeline
from tests.helpers import assert_valid_python


def compile_ok(source: str):
    result = CompilerPipeline().compile_string(source, "t.node")
    assert result.success, result.errors
    assert_valid_python(result.files)
    return result


def node_source(result) -> str:
    (name,) = [n for n in result.files if n.endswith("_node.py")]
    return result.files[name]


def pyflakes(code: str) -> str:
    proc = subprocess.run([sys.executable, "-m", "pyflakes"], input=code, capture_output=True, text=True)
    return proc.stdout + proc.stderr


class TestLifecycle:
    SRC = """package a
node N {
  publications { p: std_msgs::String @topic("/p") }
  lifecycle: managed
  on_shutdown -> { self.get_logger().info("bye") }
}
"""

    def methods(self, code):
        tree = ast.parse(code)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        return [f.name for f in cls.body if isinstance(f, ast.FunctionDef)]

    def test_no_duplicate_method_definitions(self):
        names = self.methods(node_source(compile_ok(self.SRC)))
        assert len(names) == len(set(names)), names

    def test_user_shutdown_does_not_replace_transition_hook(self):
        code = node_source(compile_ok(self.SRC))
        assert "def on_nos_shutdown(self)" in code
        assert "def on_shutdown" not in code
        assert "self.on_shutdown()" not in code

    def test_communications_created_once_in_configure(self):
        code = node_source(compile_ok(self.SRC))
        init = code[code.index("def __init__") : code.index("def _declare_nos_parameters")]
        assert "_setup_communications" not in init
        assert "def on_configure" in code
        assert "def on_cleanup" in code
        assert "self.destroy_publisher(self.p)" in code

    def test_lifecycle_publisher_is_used(self):
        assert "create_lifecycle_publisher" in node_source(compile_ok(self.SRC))

    def test_unmanaged_node_is_a_plain_node(self):
        code = node_source(compile_ok(self.SRC.replace("managed", "unmanaged")))
        assert "(NOSNode)" in code
        assert "NOSLifecycleNode" not in code

    def test_plain_node_calls_shutdown_hook_from_main(self):
        code = node_source(compile_ok("package a\nnode N { on_shutdown -> { pass } }"))
        assert "node.on_shutdown()" in code
        assert "def on_shutdown(self)" in code


class TestImports:
    def test_pyflakes_clean_for_complex_node(self):
        src = """package a
node N {
  parameters {
    d: duration = 5s
    r: float = 1.0 @range(0.0, 2.0)
    n: int = 1 @range(0, 5)
  }
  subscriptions { s: sensor_msgs::LaserScan @topic("/s") @reentrant }
  publications { p: geometry_msgs::Twist @topic("/p") }
  services { c: std_srvs::Trigger @service("/t") @client }
  on go(y: geometry_msgs::Point) -> { pass }
}
"""
        code = node_source(compile_ok(src))
        assert pyflakes(code) == ""

    def test_no_wildcard_imports(self):
        code = node_source(compile_ok('package a\nnode N { publications { p: std_msgs::String @topic("/p") } }'))
        assert "import *" not in code
        assert "from std_msgs.msg import String" in code

    def test_unused_helpers_not_imported(self):
        code = node_source(compile_ok("package a\nnode N { }"))
        for name in ("QoSProfile", "ParameterDescriptor", "Duration", "List", "Any"):
            assert name not in code

    def test_duration_default_is_importable_expression(self):
        code = node_source(compile_ok("package a\nnode N { parameters { d: duration = 5s } }"))
        assert "Duration(seconds=5)" in code
        assert "from rclpy.duration import Duration" in code

    def test_reentrant_uses_multithreaded_executor(self):
        code = node_source(
            compile_ok('package a\nnode N { subscriptions { s: std_msgs::String @topic("/s") @reentrant } }')
        )
        assert "MultiThreadedExecutor()" in code
        assert "from rclpy.executors import MultiThreadedExecutor" in code


class TestIdentifiers:
    def test_keyword_parameter_name(self):
        src = "package a\nnode N { parameters { class: int = 1  lambda: int = 2 } }"
        code = node_source(compile_ok(src))
        assert "def class_(self)" in code
        assert "get_parameter('class')" in code

    def test_range_bounds_are_expressions_not_source_strings(self):
        src = "package a\nnode N { parameters { n: int = 1 @range(0, 5) } }"
        code = node_source(compile_ok(src))
        assert "IntegerRange(from_value=int(0), to_value=int(5))" in code

    def test_string_literal_with_quotes_stays_valid(self):
        src = r"package a" + "\n" + r'node N { parameters { s: string = "a\"b\\c" } }'
        compile_ok(src)


class TestSecurityErrors:
    def test_errors_from_every_node_are_reported(self):
        src = """package a
node A { on_init -> { import os } }
node B { on_init -> { import sys } }
"""
        result = CompilerPipeline().compile_string(src, "t.node")
        assert not result.success
        text = "\n".join(result.errors)
        assert "'os'" in text and "'sys'" in text
