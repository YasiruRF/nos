"""Analyzer: package resolution, constraints registry, new checks (#19, #20, #21, #5)."""

import pytest

from nos.compiler.pipeline import CompilerPipeline
from nos.semantic import SemanticAnalyzer


def analyze(source: str):
    pipeline = CompilerPipeline()
    ast = pipeline._parse_string(source, "t.node")
    return SemanticAnalyzer().analyze(ast)


def codes(result):
    return sorted(d.code for d in result.diagnostics)


class TestPackageResolution:
    def test_depends_makes_package_known(self):
        src = """package a
depends: ["example_interfaces"]
node A { services { s: example_interfaces::AddTwoInts @service("/add") } }
"""
        assert analyze(src).is_valid

    def test_unknown_package_names_the_remedy(self):
        src = 'package a\nnode A { services { s: example_interfaces::AddTwoInts @service("/add") } }'
        result = analyze(src)
        assert codes(result) == ["E008"]
        assert "depends" in result.errors[0].message

    def test_plain_import_makes_package_known(self):
        src = """package a
import example_interfaces
node A { services { s: example_interfaces::AddTwoInts @service("/add") } }
"""
        assert analyze(src).is_valid

    def test_import_binds_type_and_rewrites_it_to_qualified(self):
        src = """package a
import example_interfaces::AddTwoInts
node A { services { s: AddTwoInts @service("/add") } }
"""
        result = analyze(src)
        assert result.is_valid
        node = result.ast.declarations[-1]
        assert node.services[0].service_type.package == "example_interfaces"

    def test_import_alias(self):
        src = """package a
import std_srvs::Trigger as Trig
node A { services { s: Trig @service("/t") } }
"""
        result = analyze(src)
        assert result.is_valid
        t = result.ast.declarations[-1].services[0].service_type
        assert (t.package, t.name) == ("std_srvs", "Trigger")

    def test_generated_imports_follow_the_resolved_package(self):
        src = """package a
import example_interfaces::AddTwoInts
node A { services { s: AddTwoInts @service("/add") } }
"""
        result = CompilerPipeline().compile_string(src, "t.node")
        assert result.success, result.errors
        assert "from example_interfaces.srv import AddTwoInts" in result.files["a_node.py"]

    def test_unqualified_type_warns(self):
        result = analyze('package a\nnode A { publications { p: Twist @topic("/x") } }')
        assert result.is_valid
        assert codes(result) == ["W022"]

    def test_turtlesim_needs_depends(self):
        src = 'package a\nnode A { publications { p: turtlesim_msgs::Pose @topic("/x") } }'
        assert codes(analyze(src)) == ["E008"]
        assert analyze(src.replace("package a", 'package a\ndepends: ["turtlesim_msgs"]')).is_valid

    def test_same_type_name_from_two_packages_does_not_collide(self):
        src = """package a
depends: ["x_msgs", "y_msgs"]
node A {
  publications {
    p: x_msgs::Thing @topic("/p")
    q: y_msgs::Thing @topic("/q")
  }
}
"""
        result = CompilerPipeline().compile_string(src, "t.node")
        assert result.success, result.errors
        code = result.files["a_node.py"]
        assert "from x_msgs.msg import Thing as x_msgs_Thing" in code
        assert "from y_msgs.msg import Thing as y_msgs_Thing" in code


class TestAnalyzerReuse:
    def test_analyze_twice_has_no_spurious_duplicates(self):
        pipeline = CompilerPipeline()
        ast = pipeline._parse_string("package a\nnode A { }", "t.node")
        analyzer = SemanticAnalyzer()
        assert analyzer.analyze(ast).is_valid
        assert analyzer.analyze(ast).is_valid


class TestConstraintRegistry:
    def test_reentrant_and_client_are_known(self):
        src = """package a
node N {
  subscriptions { s: std_msgs::String @topic("/x") @reentrant }
  services { c: std_srvs::Trigger @service("/t") @client }
}
"""
        result = analyze(src)
        assert result.is_valid
        assert not result.warnings

    def test_unknown_constraint_still_warns(self):
        src = "package a\nnode N { parameters { x: int = 1 @bogus } }"
        assert codes(analyze(src)) == ["W020"]

    def test_client_on_subscription_is_rejected(self):
        src = 'package a\nnode N { subscriptions { s: std_msgs::String @topic("/x") @client } }'
        result = analyze(src)
        assert codes(result) == ["E012"]
        assert "cannot be applied to a subscription" in result.errors[0].message

    def test_range_on_wrong_arity(self):
        assert codes(analyze("package a\nnode N { parameters { x: int = 1 @range(1) } }")) == ["E012"]

    def test_range_min_greater_than_max(self):
        assert codes(analyze("package a\nnode N { parameters { x: int = 1 @range(5, 1) } }")) == ["E014"]

    def test_range_on_publication_rejected(self):
        src = 'package a\nnode N { publications { p: std_msgs::String @topic("/x") @range(0, 1) } }'
        assert codes(analyze(src)) == ["E012"]


class TestQos:
    SRC = 'package a\nnode N {{ subscriptions {{ s: std_msgs::String @topic("/x") @qos({qos}) }} }}'

    @pytest.mark.parametrize(
        "qos",
        [
            'reliability="reliable"',
            'reliability="best_effort", depth=5',
            'durability="transient_local"',
            'history="keep_all"',
        ],
    )
    def test_valid(self, qos):
        assert analyze(self.SRC.format(qos=qos)).is_valid

    @pytest.mark.parametrize(
        "qos",
        [
            'reliability="relieable"',
            'history="keep_everything"',
            "depth=0",
            "speed=3",
            'durability="forever"',
            "5",
        ],
    )
    def test_invalid(self, qos):
        assert "E013" in codes(analyze(self.SRC.format(qos=qos)))

    def test_qos_reaches_generated_code(self):
        result = CompilerPipeline().compile_string(self.SRC.format(qos='reliability="best_effort", depth=5'), "t.node")
        assert "create_qos_profile(reliability='best_effort', depth=5)" in result.files["n_node.py"]


class TestOtherChecks:
    def test_duplicate_callbacks(self):
        src = "package a\nnode N { on_init -> { pass }\n on_init -> { pass } }"
        assert codes(analyze(src)) == ["E011"]

    def test_default_type_mismatch(self):
        assert codes(analyze('package a\nnode N { parameters { x: int = "s" } }')) == ["E015"]
        assert codes(analyze("package a\nnode N { parameters { x: string = 1 } }")) == ["E015"]
        assert analyze("package a\nnode N { parameters { x: float = 1 } }").is_valid
        assert analyze("package a\nnode N { parameters { d: duration = 5s } }").is_valid
