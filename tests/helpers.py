"""Shared helpers for generator tests."""

import ast
from typing import Dict


def assert_valid_python(files: Dict[str, str]) -> None:
    """Assert that every generated ``.py`` file is syntactically valid Python."""
    assert files, "no files were generated"
    for name, content in files.items():
        if not name.endswith(".py"):
            continue
        try:
            compile(content, name, "exec")
            ast.parse(content, name)
        except SyntaxError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"{name} is not valid Python: {exc}\n--- source ---\n{content}") from exc
