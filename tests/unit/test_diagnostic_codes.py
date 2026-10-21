"""Every diagnostic code has a negative test (#28)."""

import pytest

from nos.compiler.pipeline import CompilerPipeline
from nos.semantic import SemanticAnalyzer


def diagnostics(source: str):
    ast = CompilerPipeline()._parse_string(source, "t.node")
    return SemanticAnalyzer().analyze(ast).diagnostics


def codes(source: str):
    return sorted(d.code for d in diagnostics(source))


CASES = {
    "E001": "package a\nnode N { }\nnode N { }",
    "E002": "package a\nnode N { parameters { x: int = 1\n x: int = 2 } }",
    "E003": "package a\nlaunch L { }\nlaunch L { }",
    "E004": "package a\nlaunch L { arguments { x: int = 1\n x: int = 2 } }",
    "E005": "package a\nnode N { parameters { x: int = missing } }",
    "E006": "package a\nnode N { parameters { s: struct { a: int = 1 }\n y: int = s.zz } }",
    "E008": 'package a\nnode N { publications { p: nope_msgs::T @topic("/x") } }',
    "E010": "package a\nmessage M @id(1) { x: int }",
    "E011": "package a\nnode N { on_init -> { pass }\n on_init -> { pass } }",
    "E012": "package a\nnode N { parameters { x: int = 1 @client } }",
    "E013": 'package a\nnode N { subscriptions { s: std_msgs::String @topic("/x") @qos(depth=0) } }',
    "E014": "package a\nnode N { parameters { x: int = 1 @range(3, 2) } }",
    "E015": 'package a\nnode N { parameters { x: int = "text" } }',
    "W001": 'package a\nnode N { subscriptions { s: std_msgs::String @topic("/x")\n s: std_msgs::String @topic("/y") } }',
    "W002": 'package a\nnode N { publications { p: std_msgs::String @topic("/x")\n p: std_msgs::String @topic("/y") } }',
    "W003": 'package a\nnode N { services { s: std_srvs::Trigger @service("/x")\n s: std_srvs::Trigger @service("/y") } }',
    "W004": "package a\nnode N { actions { s: nav2_msgs::NavigateToPose\n s: nav2_msgs::NavigateToPose } }".replace(
        "package a", 'package a depends: ["nav2_msgs"]'
    ),
    "W005": "package a\nnode N { components { c: X { }\n c: Y { } } }",
    "W009": "package a\nimport std_msgs::String\nimport std_msgs::String",
    "W020": "package a\nnode N { parameters { x: int = 1 @bogus } }",
    "W022": 'package a\nnode N { publications { p: Twist @topic("/x") } }',
    "W023": 'package a\nlaunch L { on "ev" { n.enabled = true } }',
    "W024": "package a\nlaunch L { lifecycle m manager { manages: [x]\n transitions: { { from: a, to: b } } } }",
    "W025": "package a\nnode N { components { c: X { } } }",
}


@pytest.mark.parametrize("code,source", sorted(CASES.items()))
def test_code_is_reported(code, source):
    assert code in codes(source), diagnostics(source)


@pytest.mark.parametrize("code", sorted(c for c in CASES if c.startswith("E")))
def test_error_codes_make_the_program_invalid(code):
    result = CompilerPipeline().compile_string(CASES[code], "t.node")
    assert not result.success


@pytest.mark.parametrize("code", sorted(c for c in CASES if c.startswith("W")))
def test_warnings_do_not_block_analysis(code):
    ast = CompilerPipeline()._parse_string(CASES[code], "t.node")
    result = SemanticAnalyzer().analyze(ast)
    assert result.is_valid, result.errors


def test_diagnostics_have_locations_and_format():
    (diag,) = [d for d in diagnostics(CASES["E001"]) if d.code == "E001"]
    assert str(diag).startswith("t.node:3:0: ERROR: Duplicate node definition")
