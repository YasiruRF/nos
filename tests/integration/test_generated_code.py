"""Every fixture must compile to syntactically valid Python."""

from pathlib import Path

import pytest

from nos.compiler.pipeline import CompilerPipeline
from tests.helpers import assert_valid_python

FIXTURES = sorted((Path(__file__).parent.parent / "fixtures").glob("*.node"))


# Fixtures that still trip a known bug; remove the entry when the issue is fixed.
KNOWN_FAILURES = {
    "launch.node": "#8 include with args emits a double comma",
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
