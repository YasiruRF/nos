"""Regression tests for launch file generation (#8, #9, #10)."""

import ast

import pytest

from nos.compiler.pipeline import CompilerPipeline
from tests.helpers import assert_valid_python


def compile_launch(source: str) -> str:
    result = CompilerPipeline().compile_string(source, "t.node")
    assert result.success, result.errors
    assert_valid_python(result.files)
    (name,) = [n for n in result.files if n.endswith("_launch.py")]
    return result.files[name]


def returned_actions_include(code: str, call_name: str) -> bool:
    """True if a ``name = Call(...)`` assignment is appended to ``actions``."""
    tree = ast.parse(code)
    assigned = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Name) and func.id == call_name:
                assigned[node.targets[0].id] = True
    appended = {
        n.value.args[0].id
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "append"
        and isinstance(n.value.args[0], ast.Name)
    }
    return bool(assigned) and all(name in appended for name in assigned)


INCLUDE_ARGS = '''package a
launch L {
  include "other.launch.py" { args: { speed: 2 } }
}
'''

INCLUDE_PLAIN = '''package a
launch L {
  include "other.launch.py" { }
}
'''


class TestInclude:
    def test_include_with_args_is_valid_python(self):
        code = compile_launch(INCLUDE_ARGS)
        assert "launch_arguments={'speed': \"2\"}.items()" in code

    def test_include_without_args_is_valid_python(self):
        compile_launch(INCLUDE_PLAIN)

    def test_include_uses_real_package_not_empty_string(self):
        code = compile_launch(INCLUDE_ARGS)
        assert "FindPackageShare('a')" in code
        assert "FindPackageShare('')" not in code


class TestArguments:
    SRC = '''package a
launch L {
  arguments { speed: float = 1.5  name: string = "x" }
}
'''

    def test_arguments_are_returned_in_launch_description(self):
        code = compile_launch(self.SRC)
        assert returned_actions_include(code, "DeclareLaunchArgument")
        assert "actions.append(declare_speed)" in code
        assert "actions.append(declare_name)" in code

    def test_defaults_are_strings(self):
        code = compile_launch(self.SRC)
        assert 'default_value="1.5"' in code
        assert 'default_value="x"' in code


class TestPackageAndExecutableNames:
    SRC = '''package my_pkg
launch L {
  group g @namespace("ns") {
    x1: LidarDriver { parameters: { rate: 10 } }
  }
}
'''

    def test_uses_generated_package_and_entry_point(self):
        code = compile_launch(self.SRC)
        assert "package='my_pkg'" in code
        assert "executable='lidar_driver_node'" in code
        assert "package='lidar_driver'" not in code

    def test_namespace_pushed_into_group(self):
        code = compile_launch(self.SRC)
        assert 'PushRosNamespace("ns")' in code

    def test_imported_node_uses_its_package(self):
        src = '''package my_pkg
import other_pkg::Planner
launch L {
  group g @namespace("ns") { p: Planner { } }
}
'''
        code = compile_launch(src)
        assert "package='other_pkg'" in code
        assert "executable='planner_node'" in code

    def test_lifecycle_manager_uses_real_package(self):
        src = '''package a
launch L {
  lifecycle mgr manager { manages: [x] }
}
'''
        code = compile_launch(src)
        assert "package='nav2_lifecycle_manager'" in code
        assert "package='lifecycle_manager'" not in code
