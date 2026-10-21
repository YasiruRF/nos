"""Golden-file snapshots and pyflakes cleanliness of generated code (#29).

Regenerate the snapshots after an intentional change with::

    NOS_UPDATE_GOLDEN=1 pytest tests/integration/test_golden.py
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from nos.compiler.pipeline import CompilerPipeline

FIXTURES = Path(__file__).parent.parent / "fixtures"
GOLDEN = Path(__file__).parent.parent / "golden"
PROGRAMS = sorted(p.stem for p in FIXTURES.glob("*.node"))


def compile_fixture(stem: str):
    # a fixed file name keeps the "# Source:" header machine independent
    result = CompilerPipeline().compile_string((FIXTURES / f"{stem}.node").read_text(), f"{stem}.node")
    assert result.success, result.errors
    return result


def pyflakes(code: str) -> str:
    proc = subprocess.run([sys.executable, "-m", "pyflakes"], input=code, capture_output=True, text=True)
    return proc.stdout + proc.stderr


@pytest.mark.parametrize("stem", PROGRAMS)
def test_generated_code_is_pyflakes_clean(stem):
    for name, content in compile_fixture(stem).files.items():
        assert pyflakes(content) == "", f"{stem}: {name}"


@pytest.mark.parametrize("stem", PROGRAMS)
def test_matches_golden_files(stem):
    files = compile_fixture(stem).files
    target = GOLDEN / stem

    if os.environ.get("NOS_UPDATE_GOLDEN"):
        target.mkdir(parents=True, exist_ok=True)
        for old in target.glob("*"):
            old.unlink()
        for name, content in files.items():
            (target / f"{name}.golden").write_text(content)

    expected = {p.name[: -len(".golden")]: p.read_text() for p in target.glob("*.golden")}
    assert set(files) == set(expected), "generated file set changed"
    for name, content in files.items():
        assert content == expected[name], f"{stem}/{name} differs from its golden file"
