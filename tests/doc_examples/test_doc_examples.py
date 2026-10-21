"""Every ```node block in the README and docs/ must compile (#32).

Blocks that are intentional fragments use the ```node-fragment tag and are only
required to parse as part of a larger file, so they are skipped here.
"""

import re
from pathlib import Path

import pytest

from nos.compiler.pipeline import CompilerPipeline

ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *sorted((ROOT / "docs").glob("*.md"))]
BLOCK = re.compile(r"^```node\n(.*?)^```", re.S | re.M)


def collect():
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for match in BLOCK.finditer(text):
            line = text[: match.start()].count("\n") + 2
            yield pytest.param(match.group(1), id=f"{path.name}:{line}")


EXAMPLES = list(collect())


def test_there_are_examples_to_check():
    assert len(EXAMPLES) >= 3


@pytest.mark.parametrize("source", EXAMPLES)
def test_doc_example_compiles(source):
    result = CompilerPipeline().compile_string(source, "doc.node")
    assert result.success, result.errors


def test_no_untagged_node_samples():
    """A fenced block that looks like a NOS program must be tagged ```node."""
    offenders = []
    for path in DOCS:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^```(\w*)\n(.*?)^```", text, re.S | re.M):
            lang, body = match.groups()
            if lang == "nos" or (lang == "" and re.match(r"\s*package \w+", body)):
                offenders.append(f"{path.name}:{text[: match.start()].count(chr(10)) + 1}")
    assert not offenders, offenders
