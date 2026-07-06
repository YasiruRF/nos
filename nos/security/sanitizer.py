"""Security sanitizer for embedded Python code in NOS.

This module provides comprehensive security validation to prevent code injection
attacks through embedded Python code blocks in NOS callbacks.
"""

import ast
import re
import logging
from typing import List, Set, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum

# Configure audit logging
logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when security validation fails for embedded Python code.

    This exception indicates that the code contains dangerous patterns
    that could lead to arbitrary code execution or system compromise.
    """
    pass


class SecuritySeverity(Enum):
    """Severity levels for security violations."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityViolation:
    """A single security violation found in code."""
    message: str
    severity: SecuritySeverity
    line: Optional[int] = None
    column: Optional[int] = None

    def __str__(self) -> str:
        loc = f" at line {self.line}" if self.line else ""
        return f"[{self.severity.value.upper()}] {self.message}{loc}"


@dataclass
class SecurityValidationResult:
    """Result of security validation.

    Attributes:
        is_safe: True if code passes all security checks
        errors: Critical violations that must be fixed
        warnings: Non-critical concerns that should be reviewed
        sanitized_code: Code with dangerous patterns removed (if sanitization enabled)
    """
    is_safe: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sanitized_code: Optional[str] = None
    violations: List[SecurityViolation] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Return True if code is safe."""
        return self.is_safe


class PythonCodeSanitizer:
    """Validates and sanitizes embedded Python code for security risks.

    This sanitizer uses a defense-in-depth approach:
    1. Allowlist-based AST validation
    2. Pattern-based detection of dangerous constructs
    3. Import restriction to safe modules only
    4. Built-in function filtering

    Security Rules:
    - BLOCKED: eval, exec, compile, __import__, open, file
    - BLOCKED: os.*, sys.*, subprocess.*, socket.*, urllib.*, ftplib, smtplib
    - BLOCKED: builtins module access, importlib
    - ALLOWED: Basic math, string operations, ROS2 message handling
    - ALLOWED: Standard data structures (list, dict, set, tuple)
    - ALLOWED: Safe modules: math, json, datetime, typing, collections

    Usage:
        sanitizer = PythonCodeSanitizer(strict_mode=True)
        result = sanitizer.validate(python_code)
        if not result.is_safe:
            raise SecurityError(result.errors[0])
    """

    # Dangerous builtins that allow arbitrary code execution
    DANGEROUS_BUILTINS: Set[str] = frozenset({
        'eval', 'exec', 'compile', '__import__', '__build_class__',
        'open', 'file', 'input', 'raw_input', 'breakpoint',
        'help', 'license', 'credits', 'copyright',
    })

    # Sensitive modules that provide system access
    SENSITIVE_MODULES: Set[str] = frozenset({
        # System and process control
        'os', 'sys', 'platform', 'subprocess', 'multiprocessing',
        'threading', '_thread', 'dummy_threading',
        # Network operations
        'socket', 'socketserver', 'urllib', 'urllib2', 'urllib3',
        'http', 'http.client', 'http.server', 'ftplib', 'smtplib',
        'poplib', 'imaplib', 'telnetlib', 'xmlrpc', 'xmlrpc.client',
        'xmlrpc.server',
        # File system operations beyond basic open
        'shutil', 'pathlib', 'path', 'commands', 'popen2',
        'posix', 'nt', 'macpath',
        # Dynamic code execution
        'ctypes', 'mmap', 'gc', 'inspect', 'importlib', 'imp',
        'pkgutil', 'modulefinder', 'runpy', 'code', 'codeop',
        # Cryptographic that might be dangerous
        'hashlib', 'hmac', 'secrets',
        # Internal modules
        'builtins', '__builtin__', '__main__', '__future__',
        # Pickle and serialization (code execution vectors)
        'pickle', 'cPickle', 'shelve', 'marshal', 'dill', 'cloudpickle',
        # Database access
        'sqlite3', 'dbm', 'dbm.sqlite3',
        # SSL/TLS context manipulation
        'ssl', '_ssl',
    })

    # File operation patterns that indicate dangerous access
    FILE_OPERATIONS: Set[str] = frozenset({
        'open', 'file', 'read', 'write', 'append', 'truncate',
        'mkdir', 'rmdir', 'remove', 'unlink', 'rename', 'replace',
        'chmod', 'chown', 'link', 'symlink',
    })

    # Network operation patterns
    NETWORK_OPERATIONS: Set[str] = frozenset({
        'socket', 'connect', 'bind', 'listen', 'accept',
        'recv', 'send', 'recvfrom', 'sendto',
        'urlopen', 'urlretrieve', 'request', 'requests',
    })

    # Dangerous attributes that allow code execution
    DANGEROUS_ATTRIBUTES: Set[str] = frozenset({
        'system', 'popen', 'Popen', 'run', 'spawn', 'spawnv', 'spawnve',
        'call', 'check_call', 'check_output', 'getoutput', 'getstatusoutput',
        'execl', 'execle', 'execlp', 'execlpe',
        'execv', 'execve', 'execvp', 'execvpe', 'fork', 'forkpty',
        'kill', 'killpg', 'nice', 'plock', 'startfile',
        '__subclasses__', '__bases__', '__base__', '__class__',
        '__mro__', '__dict__', '__globals__', '__code__',
        'func_globals', 'gi_frame', 'tb_frame', 'f_locals', 'f_globals',
        'load', 'loads',  # pickle methods
    })

    # Safe module allowlist
    SAFE_MODULES: Set[str] = frozenset({
        # Math and numeric
        'math', 'cmath', 'decimal', 'fractions', 'numbers', 'random',
        'statistics', 'numpy', 'np',
        # Data structures
        'collections', 'collections.abc', 'heapq', 'bisect', 'copy',
        'itertools', 'functools', 'operator', 'enum', 'typing',
        'types', 'dataclasses', 'attrs',
        # String handling
        'string', 're', 'regex', 'textwrap', 'unicodedata',
        'stringprep', 'chardet',
        # Time
        'time', 'datetime', 'calendar', 'zoneinfo',
        # Data formats
        'json', 'json5', 'yaml', 'toml', 'configparser', 'csv',
        # ROS2 specific
        'rclpy', 'rclpy.node', 'rclpy.qos', 'rclpy.parameter',
        'std_msgs', 'geometry_msgs', 'sensor_msgs', 'nav_msgs',
        'builtin_interfaces', 'rosidl_runtime_py',
        # Safe utilities
        'base64', 'binascii', 'struct', 'array', 'uuid',
        'contextlib', 'warnings', 'traceback', 'inspect'  # inspect allowed but filtered
    })

    # Allowed AST node types for allowlist-based validation
    ALLOWED_AST_NODES: Set[str] = frozenset({
        # Module structure
        'Module', 'Expression', 'Interactive',
        # Literals
        'Constant', 'Num', 'Str', 'Bytes', 'FormattedValue',
        'JoinedStr', 'List', 'Tuple', 'Set', 'Dict',
        # Variables
        'Name', 'Load', 'Store', 'Del', 'Starred',
        # Expressions
        'Expr', 'UnaryOp', 'UAdd', 'USub', 'Not', 'Invert',
        'BinOp', 'Add', 'Sub', 'Mult', 'Div', 'FloorDiv', 'Mod', 'Pow',
        'LShift', 'RShift', 'BitOr', 'BitXor', 'BitAnd',
        'BoolOp', 'And', 'Or',
        'Compare', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'Is', 'IsNot',
        'In', 'NotIn',
        'Call', 'keyword', 'arg', 'arguments', 'Subscript', 'Slice',
        'Attribute', 'Index',
        'IfExp', 'NamedExpr', 'Await',
        # Control flow
        'If', 'For', 'While', 'Break', 'Continue', 'Return', 'Yield', 'YieldFrom',
        'Try', 'ExceptHandler', 'Raise', 'Assert', 'Pass',
        'With', 'withitem', 'TryStar', 'TryExcept', 'TryFinally',
        'Match', 'match_case', 'MatchValue', 'MatchSingleton', 'MatchSequence',
        'MatchMapping', 'MatchClass', 'MatchStar', 'MatchAs', 'MatchOr',
        # Functions and classes
        'FunctionDef', 'AsyncFunctionDef', 'Lambda', 'Return', 'Return',
        'ClassDef', 'Global', 'Nonlocal',
        # Comprehensions
        'ListComp', 'SetComp', 'GeneratorExp', 'DictComp', 'comprehension',
        # Assignments
        'Assign', 'AugAssign', 'AnnAssign',
        # Imports (we'll validate these separately)
        'Import', 'ImportFrom', 'alias',
        # Async
        'AsyncFor', 'AsyncWith', 'Await',
        # Other
        'Delete', 'Tuple', 'List', 'Dict', 'Set', 'NameConstant',
        # Python 3.10+ nodes
        'Match', 'match_case', 'MatchValue', 'MatchSingleton', 'MatchSequence',
        'MatchMapping', 'MatchClass', 'MatchStar', 'MatchAs', 'MatchOr',
    })

    def __init__(self, strict_mode: bool = True, allow_imports: bool = True):
        """Initialize sanitizer.

        Args:
            strict_mode: If True, warns on potentially risky patterns
            allow_imports: If False, blocks all import statements
        """
        self.strict_mode = strict_mode
        self.allow_imports = allow_imports
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.violations: List[SecurityViolation] = []

    def validate(self, code: str, context: str = "callback") -> SecurityValidationResult:
        """Validate Python code for security risks.

        Performs comprehensive security analysis:
        1. Parse code with AST
        2. Check for dangerous builtins
        3. Validate imports against allowlist
        4. Check for dangerous attribute access
        5. Check for obfuscation attempts

        Args:
            code: Python code to validate
            context: Context description for error messages

        Returns:
            SecurityValidationResult with safety status and issues

        Raises:
            SecurityError: If code cannot be parsed or contains critical violations
        """
        self.errors = []
        self.warnings = []
        self.violations = []

        if not code or not code.strip():
            return SecurityValidationResult(is_safe=True, errors=[], warnings=[])

        # Log audit event
        logger.info(f"Validating {context} code security")

        # Parse code with AST - this is our first line of defense
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            error_msg = f"Syntax error in embedded Python: {e}"
            logger.error(f"Security validation failed - {error_msg}")
            self.errors.append(error_msg)
            self.violations.append(
                SecurityViolation(error_msg, SecuritySeverity.CRITICAL)
            )
            return SecurityValidationResult(
                is_safe=False,
                errors=self.errors.copy(),
                warnings=self.warnings.copy(),
                violations=self.violations.copy()
            )
        except Exception as e:
            error_msg = f"Could not parse embedded Python for security analysis: {e}"
            logger.error(f"Security validation failed - {error_msg}")
            self.errors.append(error_msg)
            return SecurityValidationResult(
                is_safe=False,
                errors=self.errors.copy(),
                warnings=self.warnings.copy()
            )

        # Run all security checks
        self._validate_ast_nodes(tree, code)
        self._check_dangerous_builtins(code)
        self._check_imports(tree)
        self._check_dangerous_attributes(tree)
        self._check_file_operations(tree)
        self._check_network_operations(tree)
        self._check_obfuscation(code)
        self._check_bytecode_manipulation(code)

        is_safe = len(self.errors) == 0

        if not is_safe:
            logger.warning(
                f"Security validation failed for {context}: {len(self.errors)} errors"
            )
            for error in self.errors:
                logger.warning(f"  - {error}")

        return SecurityValidationResult(
            is_safe=is_safe,
            errors=self.errors.copy(),
            warnings=self.warnings.copy(),
            violations=self.violations.copy()
        )

    def _validate_ast_nodes(self, tree: ast.AST, code: str) -> None:
        """Validate that only allowed AST node types are present.

        This is a defense-in-depth measure that catches unexpected node types
        that might be used for code injection.
        """
        for node in ast.walk(tree):
            node_type = type(node).__name__
            if node_type not in self.ALLOWED_AST_NODES:
                # Get line number for better error reporting
                line = getattr(node, 'lineno', None)
                error_msg = (
                    f"Security Error: Disallowed AST node type '{node_type}' detected. "
                    f"This node type is not in the allowlist and may be unsafe."
                )
                self.errors.append(error_msg)
                self.violations.append(
                    SecurityViolation(error_msg, SecuritySeverity.CRITICAL, line)
                )

    def _check_dangerous_builtins(self, code: str) -> None:
        """Check for dangerous builtin function calls using regex.

        These are fast pattern checks that catch obvious attempts before
        deeper AST analysis.
        """
        for builtin in self.DANGEROUS_BUILTINS:
            # Match builtin calls: eval(...), exec(...), etc.
            pattern = rf'\b{builtin}\s*\('
            for match in re.finditer(pattern, code, re.IGNORECASE):
                line = code[:match.start()].count('\n') + 1
                error_msg = (
                    f"Security Error: Dangerous builtin '{builtin}' detected at line {line}. "
                    f"This function can execute arbitrary code."
                )
                self.errors.append(error_msg)
                self.violations.append(
                    SecurityViolation(error_msg, SecuritySeverity.CRITICAL, line)
                )

        # Check for getattr with dangerous builtins
        getattr_pattern = r'getattr\s*\([^)]*,\s*["\'](eval|exec|compile|__import__)["\']'
        for match in re.finditer(getattr_pattern, code, re.IGNORECASE):
            line = code[:match.start()].count('\n') + 1
            error_msg = (
                f"Security Error: getattr used to access dangerous builtin at line {line}. "
                f"This is a code injection attempt."
            )
            self.errors.append(error_msg)
            self.violations.append(
                SecurityViolation(error_msg, SecuritySeverity.CRITICAL, line)
            )

    def _check_imports(self, tree: ast.AST) -> None:
        """Check import statements against safe module allowlist.

        Only modules in SAFE_MODULES are permitted. All others are blocked.
        """
        if not self.allow_imports:
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    error_msg = "Security Error: Import statements are disabled."
                    self.errors.append(error_msg)
                    self.violations.append(
                        SecurityViolation(error_msg, SecuritySeverity.CRITICAL, node.lineno)
                    )
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split('.')[0]
                    if module in self.SENSITIVE_MODULES:
                        error_msg = (
                            f"Security Error: Import of sensitive module '{module}' detected. "
                            f"This module is in the blocklist."
                        )
                        self.errors.append(error_msg)
                        self.violations.append(
                            SecurityViolation(error_msg, SecuritySeverity.CRITICAL, node.lineno)
                        )
                    elif module not in self.SAFE_MODULES:
                        # Not in safe modules - block by default (deny by default policy)
                        if self.strict_mode:
                            error_msg = (
                                f"Security Error: Import of unverified module '{module}' detected. "
                                f"Only pre-approved modules are allowed."
                            )
                            self.errors.append(error_msg)
                            self.violations.append(
                                SecurityViolation(error_msg, SecuritySeverity.HIGH, node.lineno)
                            )
                        else:
                            warning_msg = (
                                f"Security Warning: Import of unverified module '{module}' detected. "
                                f"Please verify this is safe."
                            )
                            self.warnings.append(warning_msg)
                            self.violations.append(
                                SecurityViolation(warning_msg, SecuritySeverity.MEDIUM, node.lineno)
                            )

            elif isinstance(node, ast.ImportFrom):
                module = node.module.split('.')[0] if node.module else ''
                if module in self.SENSITIVE_MODULES:
                    error_msg = (
                        f"Security Error: Import from sensitive module '{module}' detected. "
                        f"This module is in the blocklist."
                    )
                    self.errors.append(error_msg)
                    self.violations.append(
                        SecurityViolation(error_msg, SecuritySeverity.CRITICAL, node.lineno)
                    )
                elif module and module not in self.SAFE_MODULES:
                    if self.strict_mode:
                        error_msg = (
                            f"Security Error: Import from unverified module '{module}' detected. "
                            f"Only pre-approved modules are allowed."
                        )
                        self.errors.append(error_msg)
                        self.violations.append(
                            SecurityViolation(error_msg, SecuritySeverity.HIGH, node.lineno)
                        )
                    else:
                        warning_msg = (
                            f"Security Warning: Import from unverified module '{module}' detected. "
                            f"Please verify this is safe."
                        )
                        self.warnings.append(warning_msg)
                        self.violations.append(
                            SecurityViolation(warning_msg, SecuritySeverity.MEDIUM, node.lineno)
                        )

    def _check_dangerous_attributes(self, tree: ast.AST) -> None:
        """Check for dangerous attribute access using AST.

        Catches attempts like os.system, subprocess.Popen, obj.__class__.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in self.DANGEROUS_ATTRIBUTES:
                    line = getattr(node, 'lineno', None)
                    error_msg = (
                        f"Security Error: Dangerous attribute access '.{node.attr}' detected. "
                        f"This could allow arbitrary code execution or system access."
                    )
                    self.errors.append(error_msg)
                    self.violations.append(
                        SecurityViolation(error_msg, SecuritySeverity.CRITICAL, line)
                    )

            # Check for __import__ calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id == '__import__':
                        line = getattr(node, 'lineno', None)
                        error_msg = (
                            "Security Error: Use of __import__ detected. "
                            "This could allow dynamic imports of dangerous modules."
                        )
                        self.errors.append(error_msg)
                        self.violations.append(
                            SecurityViolation(error_msg, SecuritySeverity.CRITICAL, line)
                        )

    def _check_file_operations(self, tree: ast.AST) -> None:
        """Check for file operation patterns."""
        if not self.strict_mode:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in self.FILE_OPERATIONS:
                line = getattr(node, 'lineno', None)
                warning_msg = (
                    f"Security Warning: File operation '{node.attr}' detected at line {line}. "
                    f"Ensure this is intended and safe."
                )
                self.warnings.append(warning_msg)
                self.violations.append(
                    SecurityViolation(warning_msg, SecuritySeverity.MEDIUM, line)
                )

    def _check_network_operations(self, tree: ast.AST) -> None:
        """Check for network operation patterns."""
        if not self.strict_mode:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in self.NETWORK_OPERATIONS:
                line = getattr(node, 'lineno', None)
                warning_msg = (
                    f"Security Warning: Network operation '{node.attr}' detected at line {line}. "
                    f"Ensure this is intended and safe."
                )
                self.warnings.append(warning_msg)
                self.violations.append(
                    SecurityViolation(warning_msg, SecuritySeverity.MEDIUM, line)
                )

    def _check_obfuscation(self, code: str) -> None:
        """Check for code obfuscation attempts.

        Detects various obfuscation techniques used to hide malicious code.
        """
        # Check for excessive backslash escapes
        backslash_count = code.count('\\')
        if backslash_count > len(code) * 0.1:  # More than 10% backslashes
            warning_msg = (
                "Security Warning: High density of escape sequences detected. "
                "Possible obfuscation attempt."
            )
            self.warnings.append(warning_msg)
            self.violations.append(
                SecurityViolation(warning_msg, SecuritySeverity.LOW)
            )

        # Check for hex-encoded strings
        hex_pattern = r'\\x[0-9a-fA-F]{2}'
        if re.search(hex_pattern, code):
            matches = list(re.finditer(hex_pattern, code))
            if len(matches) > 5:  # More than 5 hex escapes
                warning_msg = (
                    "Security Warning: Multiple hex escape sequences detected. "
                    "Possible obfuscation attempt."
                )
                self.warnings.append(warning_msg)
                self.violations.append(
                    SecurityViolation(warning_msg, SecuritySeverity.LOW)
                )

        # Check for base64-like encoded strings
        b64_pattern = r'[A-Za-z0-9+/]{32,}={0,2}'
        if re.search(b64_pattern, code):
            warning_msg = (
                "Security Warning: Potentially base64-encoded content detected. "
                "Possible obfuscation attempt."
            )
            self.warnings.append(warning_msg)
            self.violations.append(
                SecurityViolation(warning_msg, SecuritySeverity.LOW)
            )

        # Check for multiple encoding layers (e.g., chr(ord(...)))
        encoding_pattern = r'chr\s*\(\s*ord\s*\(|chr\s*\(\s*\d+\s*\)'
        if re.search(encoding_pattern, code, re.IGNORECASE):
            warning_msg = (
                "Security Warning: Character encoding/decoding patterns detected. "
                "Possible obfuscation attempt."
            )
            self.warnings.append(warning_msg)
            self.violations.append(
                SecurityViolation(warning_msg, SecuritySeverity.MEDIUM)
            )

        # Check for dynamic code creation patterns
        dynamic_patterns = [
            r'\bchr\s*\(\s*\d+\s*\)\s*\+',  # chr() concatenation
            r'["\']\s*\+\s*["\']',  # String concatenation for splitting
            r'join\s*\(\s*\[.*\]\s*\)',  # join with list
            r'eval\s*\(\s*chr\s*\(',  # eval with chr
        ]
        for pattern in dynamic_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                warning_msg = (
                    "Security Warning: Dynamic code construction pattern detected. "
                    "Possible obfuscation attempt."
                )
                self.warnings.append(warning_msg)
                self.violations.append(
                    SecurityViolation(warning_msg, SecuritySeverity.MEDIUM)
                )
                break

    def _check_bytecode_manipulation(self, code: str) -> None:
        """Check for attempts to manipulate Python bytecode.

        This catches attempts to use dis, marshal, or direct bytecode manipulation.
        """
        bytecode_patterns = [
            r'\bdis\.',  # dis module (bytecode inspection)
            r'\bmarshal\.',  # marshal module
            r'\btypes\.CodeType\b',  # Direct code object creation
            r'__code__\s*=',  # Code object replacement
            r'func_code\s*=',  # Python 2 style
            r'\.func_globals\b',  # Function globals access
        ]
        for pattern in bytecode_patterns:
            if re.search(pattern, code):
                error_msg = (
                    "Security Error: Bytecode manipulation pattern detected. "
                    "This could allow arbitrary code execution."
                )
                self.errors.append(error_msg)
                self.violations.append(
                    SecurityViolation(error_msg, SecuritySeverity.CRITICAL)
                )
                break

    def sanitize(self, code: str) -> Tuple[str, List[str]]:
        """Attempt to sanitize Python code by removing dangerous patterns.

        WARNING: This is a best-effort sanitization. It should NOT be relied upon
        for security-critical applications. Always validate first and reject
        unsafe code when possible.

        Args:
            code: Python code to sanitize

        Returns:
            Tuple of (sanitized_code, list_of_modifications)
        """
        modifications = []
        sanitized = code

        # Replace __import__ calls with None
        if '__import__' in sanitized:
            sanitized = re.sub(r'__import__\s*\([^)]+\)', 'None', sanitized)
            modifications.append("Removed __import__ call")

        # Comment out eval/exec calls
        for builtin in ['eval', 'exec']:
            pattern = rf'(\b{builtin}\s*\([^)]*\))'
            if re.search(pattern, sanitized):
                sanitized = re.sub(pattern, rf'# SECURITY_REMOVED: \1', sanitized)
                modifications.append(f"Commented out {builtin}() call")

        # Remove dangerous imports
        for module in self.SENSITIVE_MODULES:
            import_pattern = rf'^\s*import\s+{module}\b.*$'
            sanitized = re.sub(import_pattern, '# SECURITY_REMOVED: import blocked', sanitized, flags=re.MULTILINE)
            from_pattern = rf'^\s*from\s+{module}\b.*$'
            sanitized = re.sub(from_pattern, '# SECURITY_REMOVED: from import blocked', sanitized, flags=re.MULTILINE)
            if re.search(rf'\b{module}\b', code):
                modifications.append(f"Removed references to sensitive module '{module}'")

        return sanitized, modifications


def validate_and_raise(code: str, context: str = "callback") -> None:
    """Validate code and raise SecurityError if unsafe.

    Convenience function for code that needs to fail fast on security violations.

    Args:
        code: Python code to validate
        context: Context description for error messages

    Raises:
        SecurityError: If code contains security violations
    """
    sanitizer = PythonCodeSanitizer(strict_mode=True)
    result = sanitizer.validate(code, context)
    if not result.is_safe:
        raise SecurityError(f"Security validation failed: {result.errors[0]}")


# Backwards-compatible API
def validate_callback_code(code: str, strict: bool = True) -> SecurityValidationResult:
    """Validate callback Python code (backwards compatible API).

    Args:
        code: Python code to validate
        strict: Use strict validation mode

    Returns:
        SecurityValidationResult
    """
    sanitizer = PythonCodeSanitizer(strict_mode=strict)
    return sanitizer.validate(code, context="callback")


def sanitize_python_code(code: str) -> Tuple[str, List[str]]:
    """Sanitize Python code (backwards compatible API).

    Args:
        code: Python code to sanitize

    Returns:
        Tuple of (sanitized_code, list_of_modifications)
    """
    sanitizer = PythonCodeSanitizer()
    return sanitizer.sanitize(code)
