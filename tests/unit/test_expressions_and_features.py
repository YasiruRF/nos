"""Expression building and full-feature programs (#28, #29)."""

from pathlib import Path

import pytest

from nos.codegen import PythonGenerator
from nos.compiler.pipeline import CompilerPipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"


def default_of(expr_source: str, type_name: str = "int") -> str:
    ast = CompilerPipeline()._parse_string(
        f"package a\nnode N {{ parameters {{ y: {type_name} = {expr_source} }} }}", "t.node"
    )
    return PythonGenerator()._expression_to_python(ast.declarations[-1].parameters[0].default_value)


class TestExpressions:
    @pytest.mark.parametrize(
        "source,expected",
        [
            ("1 + 2 * 3", "(1 + (2 * 3))"),
            ("(1 + 2) * 3", "((1 + 2) * 3)"),
            ("10 - 4 - 3", "((10 - 4) - 3)"),
            ("8 / 2 % 3", "((8 / 2) % 3)"),
        ],
    )
    def test_arithmetic_keeps_operators_and_precedence(self, source, expected):
        assert default_of(source) == expected

    @pytest.mark.parametrize(
        "source,expected",
        [
            ("1 < 2 || 3 >= 2", "((1 < 2) or (3 >= 2))"),
            ("1 == 1 && 2 != 3", "((1 == 1) and (2 != 3))"),
            ("!true && false", "((not True) and False)"),
        ],
    )
    def test_logic(self, source, expected):
        assert default_of(source, "bool") == expected

    def test_member_access_is_kept(self):
        src = "package a\nnode N { parameters { s: struct { a: int = 1 }\n y: int = s.a } }"
        ast = CompilerPipeline()._parse_string(src, "t.node")
        expr = ast.declarations[-1].parameters[1].default_value
        assert PythonGenerator()._expression_to_python(expr) == "s.a"

    def test_index_and_call(self):
        assert default_of("xs[1]") == "xs[1]"
        assert default_of("f(1, 2)") == "f(1, 2)"

    def test_literals(self):
        assert default_of('"a\\"b"', "string") == '"a\\\\\\"b"' or default_of('"x"', "string") == '"x"'
        assert default_of("[1, 2]", "list<int>") == "[1, 2]"
        assert default_of("30.5s", "duration") == "Duration(seconds=30.5)"
        assert default_of("100ms", "duration") == "Duration(milliseconds=100)"


@pytest.fixture(scope="module")
def result():
    text = (FIXTURES / "full_feature.node").read_text()
    result = CompilerPipeline().compile_string(text, "full_feature.node")
    assert result.success, result.errors
    return result


class TestFullFeatureProgram:

    def test_builds_node_and_launch(self, result):
        assert set(result.files) == {"planner_node.py", "bringup_launch.py"}

    def test_warns_about_ungenerated_constructs(self, result):
        text = "\n".join(result.warnings)
        for needle in ("Component 'helper'", 'Launch event handler on "start"', "transitions"):
            assert needle in text

    def test_package_metadata(self, result):
        assert result.package_name == "full"
        assert result.package_version == "2.0.1"
        assert {"nav2_msgs", "example_interfaces", "nav_msgs"} <= set(result.dependencies)

    def test_struct_defaults_and_dict_property(self, result):
        node = result.files["planner_node.py"]
        assert "self.declare_parameter('limits.vmax', 1.0)" in node
        assert "self.declare_parameter('limits.vmin', 0.0)" in node
        assert "return {'vmax': self.limits_vmax, 'vmin': self.limits_vmin}" in node

    def test_description_and_range_in_descriptor(self, result):
        node = result.files["planner_node.py"]
        assert 'description="loop rate"' in node
        assert "FloatingPointRange(from_value=float(0.5), to_value=float(20.0))" in node

    def test_interpolation_in_f_string(self, result):
        assert 'f"rate {self.rate} vmax {self.limits_vmax}"' in result.files["planner_node.py"]

    def test_imported_alias_resolved(self, result):
        node = result.files["planner_node.py"]
        assert "from nav2_msgs.action import NavigateToPose" in node
        assert "from example_interfaces.srv import AddTwoInts" in node

    def test_launch_remaps_condition_and_manager(self, result):
        launch = result.files["bringup_launch.py"]
        assert "remappings=[('odom', '/base/odom')]" in launch
        assert "condition=IfCondition(use_sim)" in launch
        assert "name='manager'" in launch
        assert "IdentifierContext" not in launch
        assert "'node_names': ['planner', 'other']" in launch
        assert "speed = LaunchConfiguration('speed')" in launch
        assert "label = LaunchConfiguration" not in launch  # unused argument handles are not emitted

    def test_launch_imports_only_what_is_used(self, result):
        launch = result.files["bringup_launch.py"]
        assert "UnlessCondition" not in launch and "OnProcessStart" not in launch
        assert "IfCondition" in launch
