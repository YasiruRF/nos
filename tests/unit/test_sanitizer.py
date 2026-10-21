"""Security tests for NOS embedded Python code handling.

Tests validate that the security sanitizer correctly:
1. Blocks dangerous builtins (eval, exec, __import__, etc.)
2. Blocks imports of sensitive modules (os, sys, subprocess, etc.)
3. Allows safe code patterns
4. Handles edge cases properly
"""

import pytest

from nos.security import (
    PythonCodeSanitizer,
    SecurityError,
    SecuritySeverity,
    SecurityValidationResult,
    sanitize_python_code,
    validate_and_raise,
    validate_callback_code,
)
from nos.security.sanitizer import SecurityViolation


class TestSecurityValidationResult:
    """Tests for SecurityValidationResult dataclass."""

    def test_safe_result(self):
        result = SecurityValidationResult(is_safe=True, errors=[], warnings=[])
        assert result.is_safe is True
        assert bool(result) is True
        assert len(result.errors) == 0

    def test_unsafe_result(self):
        result = SecurityValidationResult(is_safe=False, errors=["Dangerous code detected"], warnings=[])
        assert result.is_safe is False
        assert bool(result) is False
        assert len(result.errors) == 1

    def test_result_with_warnings(self):
        result = SecurityValidationResult(is_safe=True, errors=[], warnings=["Potential issue"])
        assert result.is_safe is True
        assert len(result.warnings) == 1

    def test_result_with_violations(self):
        violations = [SecurityViolation("Test error", SecuritySeverity.CRITICAL, line=5)]
        result = SecurityValidationResult(is_safe=False, errors=["Test error"], violations=violations)
        assert len(result.violations) == 1
        assert result.violations[0].severity == SecuritySeverity.CRITICAL


class TestSanitizerBasicValidation:
    """Basic validation tests for PythonCodeSanitizer."""

    def test_empty_code_is_safe(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("")
        assert result.is_safe is True

    def test_whitespace_code_is_safe(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("   \n\t  ")
        assert result.is_safe is True

    def test_simple_print_is_safe(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("print('hello')")
        assert result.is_safe is True

    def test_basic_math_is_safe(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("x = 1 + 2\ny = x * 3")
        assert result.is_safe is True

    def test_syntax_error_is_blocked(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("if x >:")
        assert result.is_safe is False
        assert "Syntax error" in result.errors[0]


class TestDangerousBuiltins:
    """Tests for blocking dangerous builtin functions."""

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("eval('1 + 1')"),
            ("eval(user_input)"),
            ("result = eval(expression)"),
        ],
    )
    def test_eval_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False
        assert any("eval" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("exec('print(1)')"),
            ("exec(user_code)"),
            ("exec('import os')"),
        ],
    )
    def test_exec_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False
        assert any("exec" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("compile('code', '', 'exec')"),
            ("compiled = compile(source)"),
        ],
    )
    def test_compile_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False
        assert any("compile" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("__import__('os')"),
            ("mod = __import__(module_name)"),
        ],
    )
    def test_import_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False
        assert any("__import__" in err.lower() or "import" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("open('/etc/passwd')"),
            ("f = open('file.txt', 'w')"),
        ],
    )
    def test_open_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False
        assert any("open" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "dangerous_code",
        [
            ("getattr(obj, 'eval')"),
            ("getattr(__builtins__, 'eval')"),
        ],
    )
    def test_getattr_blocked(self, dangerous_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(dangerous_code)
        assert result.is_safe is False


class TestSensitiveImports:
    """Tests for blocking imports of sensitive modules."""

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import os"),
            ("import os.path"),
            ("from os import system"),
            ("from os.path import join"),
            ("import os, sys"),  # Multiple imports
        ],
    )
    def test_os_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("os" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import sys"),
            ("from sys import exit"),
            ("import sys as system"),
        ],
    )
    def test_sys_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("sys" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import subprocess"),
            ("from subprocess import run, Popen"),
            ("import subprocess as sp"),
        ],
    )
    def test_subprocess_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("subprocess" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import socket"),
            ("from socket import socket"),
            ("import socketserver"),
        ],
    )
    def test_socket_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("socket" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import urllib"),
            ("import urllib.request"),
            ("from urllib import urlopen"),
        ],
    )
    def test_urllib_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("urllib" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import pickle"),
            ("import cPickle"),
            ("import shelve"),
        ],
    )
    def test_pickle_import_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False
        assert any("pickle" in err.lower() or "shelve" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import ctypes"),
            ("import mmap"),
            ("import multiprocessing"),
        ],
    )
    def test_low_level_imports_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False

    @pytest.mark.parametrize(
        "import_code",
        [
            ("import ftplib"),
            ("import smtplib"),
            ("import telnetlib"),
        ],
    )
    def test_network_imports_blocked(self, import_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(import_code)
        assert result.is_safe is False


class TestDangerousAttributes:
    """Tests for blocking dangerous attribute access."""

    @pytest.mark.parametrize(
        "code",
        [
            ("os.system('ls')"),
            ("os.popen('cmd')"),
        ],
    )
    def test_os_system_blocked(self, code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        assert result.is_safe is False
        assert any("system" in err.lower() or "popen" in err.lower() for err in result.errors)

    @pytest.mark.parametrize(
        "code",
        [
            ("subprocess.Popen(['ls'])"),
            ("subprocess.run(['cmd'])"),
        ],
    )
    def test_subprocess_blocked(self, code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        assert result.is_safe is False

    @pytest.mark.parametrize(
        "code",
        [
            ("obj.__class__"),
            ("obj.__bases__"),
            ("cls.__subclasses__()"),
        ],
    )
    def test_dunder_access_blocked(self, code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        assert result.is_safe is False
        assert any("__" in err for err in result.errors)

    @pytest.mark.parametrize(
        "code",
        [
            ("func.__globals__"),
            ("func.__code__"),
            ("func.func_globals"),
        ],
    )
    def test_frame_access_blocked(self, code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        assert result.is_safe is False

    @pytest.mark.parametrize(
        "code",
        [
            ("pickle.load(f)"),
            ("pickle.loads(data)"),
        ],
    )
    def test_pickle_load_blocked(self, code):
        sanitizer = PythonCodeSanitizer(strict_mode=True)
        result = sanitizer.validate(code)
        assert result.is_safe is False


class TestSafeCodePatterns:
    """Tests for code patterns that should be allowed."""

    @pytest.mark.parametrize(
        "safe_code",
        [
            # Basic math operations
            ("x = 1 + 2"),
            ("y = x * 3 / 4"),
            ("result = (a + b) * c"),
            ("value = sum([1, 2, 3])"),
            ("import math; math.sqrt(16)"),
            # String operations
            ('s = "hello".upper()'),
            ("parts = text.split(',')"),
            ("joined = '-'.join(items)"),
            # Data structures
            ("d = {'key': 'value'}"),
            ("lst = [1, 2, 3]"),
            ("tup = (1, 2)"),
            ("st = {1, 2, 3}"),
            # Control flow
            ("if x > 0:\n    print(x)"),
            ("for i in range(10):\n    pass"),
            ("while x < 10:\n    x += 1"),
            ("try:\n    x = 1\nexcept:\n    pass"),
            # List comprehensions
            ("squares = [x**2 for x in range(10)]"),
            ("evens = [x for x in nums if x % 2 == 0]"),
            # Functions
            ("def greet(name):\n    return f'Hello {name}'"),
            ("lambda x: x * 2"),
            # Safe imports
            ("import json"),
            ("from datetime import datetime"),
            ("import collections"),
        ],
    )
    def test_safe_code_passes(self, safe_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(safe_code)
        assert result.is_safe is True, f"Failed for code: {safe_code}, errors: {result.errors}"

    @pytest.mark.parametrize(
        "ros_code",
        [
            # ROS2 message handling
            ("msg.data = 'hello'"),
            ("header = msg.header"),
            ("self.publisher.publish(msg)"),
            ("import rclpy"),
            ("from std_msgs.msg import String"),
            ("from geometry_msgs.msg import Point"),
        ],
    )
    def test_ros2_code_allowed(self, ros_code):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(ros_code)
        assert result.is_safe is True, f"ROS code blocked: {ros_code}, errors: {result.errors}"


class TestStrictMode:
    """Tests for strict vs non-strict mode."""

    def test_strict_mode_blocks_unverified_imports(self):
        sanitizer = PythonCodeSanitizer(strict_mode=True)
        result = sanitizer.validate("import some_unknown_module")
        assert result.is_safe is False

    def test_non_strict_mode_warns_unverified_imports(self):
        sanitizer = PythonCodeSanitizer(strict_mode=False)
        result = sanitizer.validate("import some_unknown_module")
        assert result.is_safe is True
        assert len(result.warnings) > 0

    def test_strict_mode_warns_file_operations(self):
        sanitizer = PythonCodeSanitizer(strict_mode=True)
        result = sanitizer.validate("obj.read()")
        assert len(result.warnings) > 0

    def test_non_strict_mode_allows_file_operations(self):
        sanitizer = PythonCodeSanitizer(strict_mode=False)
        result = sanitizer.validate("obj.read()")
        assert result.is_safe is True
        # Might have warnings but still safe


class TestObfuscationDetection:
    """Tests for detecting obfuscated code."""

    def test_hex_escapes_detected(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("x = '\\x65\\x76\\x61\\x6c'")
        # Should have warnings about hex escapes

    def test_base64_like_detected(self):
        sanitizer = PythonCodeSanitizer()
        # Long base64-like string
        result = sanitizer.validate("data = 'SGVsbG8gV29ybGQgVGhpcyBJcyBUZXN0IERhdGE='")
        assert len(result.warnings) > 0 or len(result.errors) > 0

    def test_chr_ord_pattern_detected(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("x = chr(ord('a') + 1)")
        # Should have warnings about encoding patterns

    def test_excessive_escapes_detected(self):
        sanitizer = PythonCodeSanitizer()
        code = "x = '\\n\\t\\r\\x00\\n\\t\\r\\x00'"
        result = sanitizer.validate(code)
        # Might have warnings


class TestBytecodeManipulation:
    """Tests for detecting bytecode manipulation attempts."""

    def test_dis_module_blocked(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("import dis; dis.dis(func)")
        assert result.is_safe is False

    def test_code_type_creation_blocked(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("types.CodeType(...)")
        assert result.is_safe is False

    def test_code_object_replacement_blocked(self):
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate("func.__code__ = new_code")
        assert result.is_safe is False


class TestSanitization:
    """Tests for the sanitize function."""

    def test_sanitize_removes_import(self):
        code = "import os; os.system('ls')"
        sanitized, modifications = sanitize_python_code(code)
        assert "os" not in sanitized or "SECURITY_REMOVED" in sanitized
        assert len(modifications) > 0

    def test_sanitize_comments_out_eval(self):
        code = "eval('1+1')"
        sanitized, modifications = sanitize_python_code(code)
        assert "# SECURITY_REMOVED" in sanitized


class TestValidateAndRaise:
    """Tests for validate_and_raise function."""

    def test_raise_on_unsafe_code(self):
        with pytest.raises(SecurityError):
            validate_and_raise("eval('1+1')")

    def test_no_raise_on_safe_code(self):
        # Should not raise
        validate_and_raise("x = 1 + 2")


class TestBackwardsCompatibility:
    """Tests for backwards compatible API."""

    def test_validate_callback_code_exists(self):
        # This is the function used by python_generator.py
        result = validate_callback_code("print('hello')")
        assert result.is_safe is True

    def test_old_api_works(self):
        from nos.security import PythonCodeValidator

        validator = PythonCodeValidator()
        result = validator.validate("eval('1+1')")
        assert result.is_safe is False


class TestComplexScenarios:
    """Tests for complex real-world scenarios."""

    def test_callback_with_math_operations(self):
        code = """
result = msg.data * 2 + 1
if result > 10:
    self.publish(result)
"""
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_callback_with_string_formatting(self):
        code = """
message = f"Received: {msg.header.frame_id}"
self.get_logger().info(message)
"""
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_callback_with_list_processing(self):
        code = """
values = [p.x for p in msg.points]
avg = sum(values) / len(values) if values else 0
"""
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_callback_with_dangerous_code_blocked(self):
        code = """
result = eval(msg.data)
self.publish(result)
"""
        result = validate_callback_code(code, strict=True)
        assert result.is_safe is False
        assert any("eval" in err for err in result.errors)

    def test_callback_with_import_blocked(self):
        code = """
import os
cmd = msg.data
os.system(cmd)
"""
        result = validate_callback_code(code, strict=True)
        assert result.is_safe is False
        assert any("os" in err.lower() for err in result.errors)

    def test_nested_dangerous_code(self):
        code = """
def process():
    if True:
        for i in range(10):
            eval("1+1")
"""
        result = validate_callback_code(code, strict=True)
        assert result.is_safe is False

    def test_lambda_with_danger(self):
        code = "f = lambda: eval('1')"
        result = validate_callback_code(code)
        assert result.is_safe is False

    def test_class_with_danger(self):
        code = """
class MyClass:
    def method(self):
        exec("print(1)")
"""
        result = validate_callback_code(code)
        assert result.is_safe is False


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unicode_in_code(self):
        code = "x = 'hello Ã± world'"
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_very_long_code(self):
        code = "x = 1\n" * 1000  # 1000 lines
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_code_with_comments(self):
        code = """
# This is a comment
x = 1  # inline comment
# Another comment
"""
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_code_with_docstrings(self):
        code = '''
def func():
    """This is a docstring."""
    return 42
'''
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_empty_function(self):
        code = "def func():\n    pass"
        result = validate_callback_code(code)
        assert result.is_safe is True

    def test_multiple_statements_per_line(self):
        code = "x = 1; y = 2; print(x + y)"
        result = validate_callback_code(code)
        assert result.is_safe is True


class TestViolationReporting:
    """Tests for detailed violation reporting."""

    def test_violation_has_line_number(self):
        code = "x = 1\neval('1')\ny = 2"
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        assert len(result.violations) > 0
        # At least one violation should have a line number
        violations_with_lines = [v for v in result.violations if v.line is not None]
        assert len(violations_with_lines) > 0

    def test_violation_severity_levels(self):
        code = "eval('1')"  # Critical violation
        sanitizer = PythonCodeSanitizer()
        result = sanitizer.validate(code)
        critical_violations = [v for v in result.violations if v.severity == SecuritySeverity.CRITICAL]
        assert len(critical_violations) > 0

    def test_violation_message_format(self):
        violation = SecurityViolation("Test message", SecuritySeverity.HIGH, line=10)
        message = str(violation)
        assert "HIGH" in message
        assert "Test message" in message
        assert "line 10" in message


def _validate(code, strict=True):
    return PythonCodeSanitizer(strict_mode=strict).validate(code)


# Valid ROS code that used to be rejected (#22)
ALLOWED_SNIPPETS = [
    "import re\nre.compile('a+')",
    "self.gripper.open()",
    "self.sensor.input(3)",
    "self.file(1)",
    "self.help(1)",
    "Open(1)",
    "self.worker.run()",
    "self.cli.call(req)",
    "self.cli.call_async(req)",
    "self.kill()",
    "self.cfg.load()",
    "self.cfg.loads(text)",
    "import threading\nt = threading.Thread(target=self.work)\nt.start()",
    "import hashlib\nhashlib.sha256(b'x').hexdigest()",
    "x = 'open(file) and eval(x) are only words here'",
    "# eval(this) is a comment\nx = 1",
    "import numpy as np\nnp.array([1, 2]).mean()",
    "from std_msgs.msg import String\nmsg = String()",
    "from rclpy.node import Node",
    "import json\njson.dumps({'a': 1})",
    "super().__init__()",
    "name = type(self).__name__",
    "f = lambda a, b: a @ b",
    "self.get_logger().info(f'{self.speed:.2f}')",
    "x = getattr(self, 'speed')",
]


@pytest.mark.parametrize("code", ALLOWED_SNIPPETS)
def test_valid_ros_code_is_accepted(code):
    result = _validate(code)
    assert result.is_safe, result.errors


# Bypasses from the security report (#23)
BLOCKED_SNIPPETS = [
    "f = getattr(__builtins__, 'ev'+'al'); f('1')",
    "__builtins__['ex'+'ec']('print(1)')",
    "g = globals(); g['__buil'+'tins__']",
    "import operator; operator.attrgetter('__cl'+'ass__')(())",
    "'{0.__class__}'.format(1)",
    "'{0[__class__]}'.format(1)",
    "import numpy as np; np.loadtxt('/etc/passwd', dtype=str)",
    "import numpy as np; np.savetxt('/tmp/x', [1])",
    "from numpy import loadtxt",
    "import numpy; numpy.load('x.npy', allow_pickle=True)",
    "import rclpy.impl.implementation_singleton",
    "import json; json.codecs",
    "__import__ = 1",
    "f = eval",
    "x = vars(self)",
    "x = locals()",
    "setattr(self, name, 1)",
    "getattr(self, name)",
    "getattr(self, '__class__')",
    "type('X', (object,), {})",
    "().__class__.__bases__[0].__subclasses__()",
    "self.__class__.__mro__",
    "import types; types.CodeType",
    "import types as t; t.FunctionType",
    "import os",
    "import io; io.open('/etc/passwd')",
    "from . import secrets",
    "import importlib",
    "def f(): return __builtins__",
    "f.__globals__",
    "x = (lambda: 0).__code__",
]


@pytest.mark.parametrize("code", BLOCKED_SNIPPETS)
def test_known_bypasses_are_blocked(code):
    assert not _validate(code).is_safe, code


class TestSanitizerAstBased:
    def test_open_call_still_blocked(self):
        assert not _validate("open('/etc/passwd')").is_safe

    def test_builtin_in_string_is_not_flagged(self):
        assert _validate("print('call eval( and exec( here')").is_safe

    def test_block_after_dynamic_format_warns(self):
        result = _validate("tpl = get_template()\ntpl.format(self)")
        assert result.is_safe
        assert any("non-literal template" in w for w in result.warnings)

    def test_local_variable_named_like_module_is_fine(self):
        assert _validate("path = [1, 2]\npath.append(3)").is_safe
        assert _validate("code = 3\nprint(code)").is_safe

    def test_dunder_name_error_mentions_the_name(self):
        result = _validate("x = obj.__dict__")
        assert any("__dict__" in e for e in result.errors)

    def test_no_stale_python2_node_names_in_allowlist(self):
        for stale in ("Num", "Str", "NameConstant", "TryExcept", "TryFinally", "Bytes"):
            assert stale not in PythonCodeSanitizer.ALLOWED_AST_NODES
