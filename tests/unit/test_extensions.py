"""Source extension policy: .node only, .nos rejected (#7)."""

import subprocess
import sys
from pathlib import Path

import pytest

from nos.compiler.main import main

PROGRAM = "package demo\nnode Talker { }\n"


@pytest.mark.parametrize("name", ["foo.nos", "FOO.NOS"])
def test_nos_extension_is_rejected_with_a_clear_message(tmp_path, capsys, name):
    f = tmp_path / name
    f.write_text(PROGRAM)
    assert main([str(f), "--dry-run"]) == 1
    err = capsys.readouterr().err
    assert "no longer supported" in err
    assert ".node" in err


def test_unknown_extension_rejected(tmp_path, capsys):
    f = tmp_path / "foo.txt"
    f.write_text(PROGRAM)
    assert main([str(f), "--dry-run"]) == 1
    assert "Invalid file type" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["foo.node", "Foo.NODE"])
def test_node_extension_accepted_case_insensitively(tmp_path, name):
    f = tmp_path / name
    f.write_text(PROGRAM)
    assert main([str(f), "--dry-run"]) == 0


def test_no_nos_extension_left_in_the_repo():
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "CHANGELOG.md",  # history
        "tests/unit/test_extensions.py",  # this test
        "nos/compiler/main.py",  # the deliberate rejection
        "README.md",  # documents the removal
        "ros2_dsl_architecture.md",  # hypothetical CMakeLists.txt.nos design sketch
    }
    allowed_prefixes = ("nos/extensions/vscode-nos/",)  # TextMate scope names (source.nos)
    out = subprocess.run(
        ["git", "grep", "-nI", r"\.nos\b", "--", ".", ":!nos/grammar"], cwd=root, capture_output=True, text=True
    ).stdout
    offenders = [
        line for line in out.splitlines() if line.split(":")[0] not in allowed and not line.startswith(allowed_prefixes)
    ]
    assert not offenders, "\n".join(offenders)
