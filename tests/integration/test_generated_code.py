"""Every fixture must compile to syntactically valid Python."""

from pathlib import Path

import pytest

from nos.compiler.pipeline import CompilerPipeline
from tests.helpers import assert_valid_python

FIXTURES = sorted((Path(__file__).parent.parent / "fixtures").glob("*.node"))


# Fixtures that still trip a known bug; remove the entry when the issue is fixed.
KNOWN_FAILURES = {
    "subscriber_service_action.node": "#19 hard-coded ROS package list",
}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_fixture_generates_valid_python(fixture):
    if fixture.name in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[fixture.name])
    result = CompilerPipeline().compile_file(str(fixture))
    assert result.success, result.errors
    assert_valid_python(result.files)


def test_fixtures_exist():
    assert FIXTURES


def test_generators_do_not_emit_the_same_path():
    """PythonGenerator and LaunchTranspiler must not overwrite each other (#11)."""
    from nos.codegen import PythonGenerator, LaunchTranspiler

    pipeline = CompilerPipeline()
    src = (FIXTURES[0].parent / "launch.node").read_text()
    result = pipeline.compile_string(src, "launch.node")
    node_files = set(PythonGenerator().generate(result.ast, None).files)
    launch_files = set(LaunchTranspiler().generate(result.ast, None).files)
    assert not node_files & launch_files
    assert "bringup_launch.py" in launch_files
