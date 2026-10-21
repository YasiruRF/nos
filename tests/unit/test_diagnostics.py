"""Compiler diagnostics (#15, #2, #4)."""

import logging

import pytest

from nos.ast.builder import ASTBuilder
from nos.compiler.pipeline import CompilerPipeline

VALID = 'package a\nnode N { publications { p: std_msgs::String @topic("/p") } }\n'


class TestSyntaxErrors:
    def test_syntax_error_has_file_line_column(self):
        result = CompilerPipeline().compile_string("package a\nnode N {", "foo.node")
        assert not result.success
        assert result.errors[0].startswith("foo.node:2:")
        assert "error:" in result.errors[0]

    def test_compile_file_reports_syntax_error_not_failed_to_parse(self, tmp_path):
        f = tmp_path / "bad.node"
        f.write_text("package a\nnode N { parameters { x: = 1 } }\n")
        result = CompilerPipeline().compile_file(str(f))
        assert not result.success
        assert all("Failed to parse" not in e for e in result.errors)
        assert str(f) + ":2:" in result.errors[0]

    def test_missing_file(self, tmp_path):
        result = CompilerPipeline().compile_file(str(tmp_path / "nope.node"))
        assert result.errors == [f"{tmp_path / 'nope.node'}: error: file not found"]

    def test_unreadable_encoding(self, tmp_path):
        f = tmp_path / "bin.node"
        f.write_bytes(b"\xff\xfe\x00bad")
        result = CompilerPipeline().compile_file(str(f))
        assert not result.success
        assert "cannot read file" in result.errors[0]


class TestInternalErrors:
    def test_builder_bug_is_reported_as_internal_error(self, monkeypatch):
        def boom(self, ctx):
            raise RuntimeError("kaboom")
        monkeypatch.setattr(ASTBuilder, "visit_NodeDecl", boom)
        result = CompilerPipeline().compile_string(VALID, "t.node")
        assert not result.success
        assert "internal compiler error" in result.errors[0]
        assert "kaboom" in result.errors[0]
        assert "Compilation error" not in result.errors[0]

    def test_traceback_only_when_verbose(self, monkeypatch):
        monkeypatch.setattr(ASTBuilder, "visit_NodeDecl",
                            lambda self, ctx: (_ for _ in ()).throw(RuntimeError("x")))
        quiet = CompilerPipeline().compile_string(VALID, "t.node")
        loud = CompilerPipeline({"verbose": True}).compile_string(VALID, "t.node")
        assert len(quiet.errors) == 1
        assert any("Traceback" in e for e in loud.errors)


class TestInputHandling:
    def test_bom_is_accepted_in_strings(self):
        assert CompilerPipeline().compile_string("﻿" + VALID, "t.node").success

    def test_bom_is_accepted_in_files(self, tmp_path):
        f = tmp_path / "bom.node"
        f.write_bytes(b"\xef\xbb\xbf" + VALID.encode())
        assert CompilerPipeline().compile_file(str(f)).success

    def test_empty_input_is_not_a_success(self):
        result = CompilerPipeline().compile_string("", "empty.node")
        assert not result.success
        assert "nothing to generate" in result.errors[0]

    def test_package_only_is_not_a_success(self):
        assert not CompilerPipeline().compile_string("package a", "t.node").success

    def test_file_and_string_agree(self, tmp_path):
        f = tmp_path / "t.node"
        f.write_text(VALID)
        from_file = CompilerPipeline().compile_file(str(f))
        from_string = CompilerPipeline().compile_string(VALID, str(f))
        assert from_file.files == from_string.files
        assert from_file.errors == from_string.errors


class TestQualifiedTypes:
    @pytest.mark.parametrize("src", [
        'package a\nnode N { publications { p: ::String @topic("/p") } }',
        'package a\nnode N { publications { p: std_msgs:: @topic("/p") } }',
    ])
    def test_malformed_separators_are_syntax_errors(self, src):
        result = CompilerPipeline().compile_string(src, "t.node")
        assert not result.success
        assert result.errors[0].startswith("t.node:2:")

    def test_three_part_with_kind_is_accepted(self):
        src = 'package a\nnode N { publications { p: std_msgs::msg::String @topic("/p") } }'
        result = CompilerPipeline().compile_string(src, "t.node")
        assert result.success, result.errors
        assert "from std_msgs.msg import String" in result.files["n_node.py"]

    def test_three_part_with_bad_kind_is_rejected(self):
        src = 'package a\nnode N { publications { p: std_msgs::foo::String @topic("/p") } }'
        result = CompilerPipeline().compile_string(src, "t.node")
        assert not result.success
        assert "invalid qualified type 'std_msgs::foo::String'" in result.errors[0]
        assert result.errors[0].startswith("t.node:2:")

    @pytest.mark.parametrize("text", ["::Type", "pkg::", "a::::b", ""])
    def test_split_reports_malformed_names(self, text):
        builder = ASTBuilder("t.node")
        builder.split_qualified_type(text)
        assert builder.errors

    def test_split_results(self):
        builder = ASTBuilder("t.node")
        assert builder.split_qualified_type("Twist") == ("", None, "Twist")
        assert builder.split_qualified_type("g::Twist") == ("g", None, "Twist")
        assert builder.split_qualified_type("g::msg::Twist") == ("g", "msg", "Twist")
        assert not builder.errors


class TestBuilderLogging:
    def test_fallbacks_are_silent_by_default_and_logged_at_debug(self, caplog):
        builder = ASTBuilder("t.node")
        with caplog.at_level(logging.WARNING, logger="nos.ast.builder"):
            builder.visit_default(object())
        assert not caplog.records
        with caplog.at_level(logging.DEBUG, logger="nos.ast.builder"):
            builder.visit_default(object())
        assert any("no AST handler" in r.getMessage() for r in caplog.records)
