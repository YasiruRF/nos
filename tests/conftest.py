"""Pytest configuration and fixtures for NOS tests.

This module provides shared fixtures for the NOS test suite.
Fixtures include default source locations, mock parser outputs,
and other test utilities.

Example:
    def test_my_feature(source_location):
        # Use the source_location fixture
        node = SomeNode(location=source_location, ...)
"""

import pytest

from nos.ast.nodes import SourceLocation


@pytest.fixture
def source_location():
    """Create a default source location for testing."""
    return SourceLocation(line=1, column=0, file="test.node")


@pytest.fixture
def test_file_location():
    """Create a source location pointing to a test file."""
    return SourceLocation(line=1, column=0, file="/tmp/test.node")


@pytest.fixture
def mock_parser_output():
    """Mock parse tree output for testing AST builder."""

    class MockToken:
        def __init__(self, text, line=1, column=0):
            self.text = text
            self.line = line
            self.column = column

    class MockCtx:
        def __init__(self):
            self.start = MockToken("")
            self.stop = MockToken("")

    return MockCtx()


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
