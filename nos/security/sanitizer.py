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
    """Validates embedded Python code for risky constructs.

    This is a *guard rail*, not a sandbox.  Callback code runs inside the
    node process with the node's privileges; the sanitizer exists to catch
    accidents and the obvious ways of reaching the filesystem, the shell or
    the interpreter internals from a ``.node`` file.  Static filtering of
    Python cannot contain a determined attacker, so untrusted ``.node`` files
    must be compiled and run in an OS-level sandbox (container, separate user).
    See ``docs/security.md`` for the threat model.

    All checks work on the parsed AST, so text inside strings and comments is
    never mistaken for code, and ``obj.open()`` is not confused with ``open()``.

    Rules (errors unless noted):
    - builtins that execute or load code or reach interpreter internals
      (``eval``, ``exec``, ``compile``, ``__import__``, ``open``, ``globals``,
      ``locals``, ``vars``, ``__builtins__``, ...) are blocked as bare names,
      whether called, assigned or passed around
    - ``getattr``/``setattr``/``delattr`` need a literal, non-dunder attribute name
    - ``type(...)`` with three arguments (dynamic class creation) is blocked
    - dunder attributes (``__class__``, ``__globals__``, ...) are blocked
    - ``str.format`` templates that traverse dunder attributes are blocked
    - imports are limited to an allow-list of exact module names; sensitive
      modules (``os``, ``sys``, ``subprocess``, ``socket``, ...) are blocked
    - attributes of allowed modules that reach the filesystem or build code
      objects (``numpy.loadtxt``, ``json.codecs``, ``types.CodeType``, ...) are blocked
    - warnings: file/network-looking method names, obfuscation heuristics

    Usage:
        sanitizer = PythonCodeSanitizer(strict_mode=True)
        result = sanitizer.validate(python_code)
        if not result.is_safe:
            raise SecurityError(result.errors[0])
    """

    # Builtins that execute code, load code, or read files.  Blocked as bare
    # names in any position (call, assignment, argument).
    DANGEROUS_BUILTINS: Set[str] = frozenset({
        'eval', 'exec', 'compile', '__import__', '__build_class__',
        'open', 'file', 'breakpoint', 'execfile', 'reload',
    })

    # Blocked as a bare *call* only (a variable called `input` is harmless).
    DANGEROUS_CALLS: Set[str] = frozenset({'input', 'raw_input', 'help'})

    # Names that expose interpreter internals; blocked in any position.
    INTROSPECTION_NAMES: Set[str] = frozenset({
        'globals', 'locals', 'vars', '__builtins__', '__builtin__',
        '__loader__', '__spec__', '__dict__',
    })

    # Dunder names that are routinely needed and harmless.
    ALLOWED_DUNDERS: Set[str] = frozenset({
        '__init__', '__name__', '__doc__', '__str__', '__repr__', '__len__',
        '__iter__', '__next__', '__enter__', '__exit__', '__eq__', '__hash__',
        '__version__', '__all__', '__file__',
    })

    # Sensitive modules that provide system access
    SENSITIVE_MODULES: Set[str] = frozenset({
        # System and process control
        'os', 'sys', 'platform', 'subprocess', 'multiprocessing', '_thread',
        'signal', 'resource', 'pty', 'tty', 'fcntl',
        # Network operations
        'socket', 'socketserver', 'urllib', 'urllib2', 'urllib3',
        'http', 'http.client', 'http.server', 'ftplib', 'smtplib',
        'poplib', 'imaplib', 'telnetlib', 'xmlrpc', 'xmlrpc.client',
        'xmlrpc.server', 'requests', 'asyncio.subprocess',
        # File system operations
        'shutil', 'pathlib', 'path', 'commands', 'popen2', 'tempfile', 'glob',
        'posix', 'nt', 'macpath', 'fileinput',
        # Dynamic code execution / interpreter internals
        'ctypes', 'mmap', 'gc', 'inspect', 'importlib', 'imp',
        'pkgutil', 'modulefinder', 'runpy', 'code', 'codeop', 'dis',
        'builtins', '__builtin__', '__main__', '__future__', 'sysconfig',
        # Pickle and serialization (code execution vectors)
        'pickle', 'cPickle', 'shelve', 'marshal', 'dill', 'cloudpickle',
        # Database access
        'sqlite3', 'dbm', 'dbm.sqlite3',
        # SSL/TLS context manipulation
        'ssl', '_ssl',
    })

    # File operation patterns that indicate dangerous access (warnings)
    FILE_OPERATIONS: Set[str] = frozenset({
        'open', 'file', 'read', 'write', 'append', 'truncate',
        'mkdir', 'rmdir', 'remove', 'unlink', 'rename',
        'chmod', 'chown', 'symlink',
    })

    # Network operation patterns (warnings)
    NETWORK_OPERATIONS: Set[str] = frozenset({
        'socket', 'connect', 'bind', 'listen', 'accept',
        'recv', 'send', 'recvfrom', 'sendto',
        'urlopen', 'urlretrieve',
    })

    # Attribute names that start a process or replace the process image,
    # whatever object they are read from.  Generic names such as ``run``,
    # ``call``, ``kill`` or ``load`` are *not* listed: they are ordinary
    # methods on user objects, and the modules that make them dangerous
    # (subprocess, os, pickle) cannot be imported anyway.
    DANGEROUS_ATTRIBUTES: Set[str] = frozenset({
        'system', 'popen', 'Popen', 'spawn', 'spawnv', 'spawnve',
        'check_call', 'check_output', 'getoutput', 'getstatusoutput',
        'execl', 'execle', 'execlp', 'execlpe',
        'execv', 'execve', 'execvp', 'execvpe', 'fork', 'forkpty',
        'killpg', 'startfile',
        'func_globals', 'gi_frame', 'tb_frame', 'f_locals', 'f_globals',
        'f_back', 'f_builtins', 'gi_code', 'cr_frame', 'co_code',
    })

    # Modules that may be imported (exact names; submodules are not implied)
    SAFE_MODULES: Set[str] = frozenset({
        # Math and numeric
        'math', 'cmath', 'decimal', 'fractions', 'numbers', 'random',
        'statistics', 'numpy',
        # Data structures
        'collections', 'collections.abc', 'heapq', 'bisect', 'copy',
        'itertools', 'functools', 'operator', 'enum', 'typing',
        'types', 'dataclasses', 'attrs', 'queue',
        # String handling
        'string', 're', 'regex', 'textwrap', 'unicodedata',
        'stringprep', 'chardet',
        # Time
        'time', 'datetime', 'calendar', 'zoneinfo',
        # Data formats
        'json', 'json5', 'yaml', 'toml', 'configparser', 'csv',
        # ROS2 specific
        'rclpy', 'rclpy.node', 'rclpy.qos', 'rclpy.parameter', 'rclpy.duration',
        'rclpy.time', 'rclpy.executors', 'rclpy.callback_groups', 'rclpy.action',
        'rclpy.clock', 'rclpy.logging', 'rclpy.lifecycle', 'rosidl_runtime_py',
        'tf2_ros', 'cv_bridge',
        # Safe utilities
        'base64', 'binascii', 'struct', 'array', 'uuid',
        'contextlib', 'warnings', 'traceback', 'logging', 'io',
        # Concurrency primitives and hashing are routine in ROS nodes
        'threading', 'hashlib', 'hmac', 'secrets',
    })

    # ROS interface packages: any of their msg/srv/action modules may be imported
    INTERFACE_PACKAGES: Set[str] = frozenset({
        'std_msgs', 'geometry_msgs', 'sensor_msgs', 'nav_msgs',
        'diagnostic_msgs', 'action_msgs', 'builtin_interfaces',
        'rcl_interfaces', 'tf2_msgs', 'trajectory_msgs', 'visualization_msgs',
        'stereo_msgs', 'shape_msgs', 'std_srvs', 'lifecycle_msgs',
        'example_interfaces', 'nav2_msgs', 'turtlesim', 'turtlesim_msgs',
    })
    INTERFACE_SUBMODULES: Set[str] = frozenset({'msg', 'srv', 'action'})

    # Attributes of otherwise-allowed modules that reach files, build code
    # objects or reflect on other modules.
    MODULE_BLOCKED_ATTRS = {
        'numpy': frozenset({
            'load', 'save', 'savez', 'savez_compressed', 'loadtxt', 'savetxt',
            'genfromtxt', 'fromfile', 'tofile', 'fromregex', 'memmap', 'lib',
            'ctypeslib', 'distutils', 'f2py', 'testing', 'DataSource', 'os',
            'sys', 'core', 'compat',
        }),
        'io': frozenset({'open', 'open_code', 'FileIO'}),
        'json': frozenset({'codecs'}),
        'yaml': frozenset({'load', 'load_all', 'unsafe_load', 'unsafe_load_all',
                           'full_load', 'full_load_all', 'add_constructor',
                           'add_multi_constructor'}),
        'operator': frozenset({'attrgetter', 'methodcaller'}),
        'types': frozenset({'CodeType', 'FunctionType', 'LambdaType', 'ModuleType',
                            'MethodType', 'FrameType', 'TracebackType', 'CellType',
                            'new_class', 'prepare_class', 'resolve_bases'}),
        'rclpy': frozenset({'impl'}),
        'logging': frozenset({'FileHandler', 'WatchedFileHandler', 'handlers', 'config'}),
        'string': frozenset({'Formatter'}),
        'threading': frozenset({'settrace', 'setprofile'}),
    }

    # Allowed AST node types for allowlist-based validation (Python 3.9+)
    ALLOWED_AST_NODES: Set[str] = frozenset({
        # Module structure
        'Module', 'Expression',
        # Literals
        'Constant', 'FormattedValue', 'JoinedStr', 'List', 'Tuple', 'Set', 'Dict',
        # Variables
        'Name', 'Load', 'Store', 'Del', 'Starred',
        # Expressions
        'Expr', 'UnaryOp', 'UAdd', 'USub', 'Not', 'Invert',
        'BinOp', 'Add', 'Sub', 'Mult', 'MatMult', 'Div', 'FloorDiv', 'Mod', 'Pow',
        'LShift', 'RShift', 'BitOr', 'BitXor', 'BitAnd',
        'BoolOp', 'And', 'Or',
        'Compare', 'Eq', 'NotEq', 'Lt', 'LtE', 'Gt', 'GtE', 'Is', 'IsNot',
        'In', 'NotIn',
        'Call', 'keyword', 'arg', 'arguments', 'Subscript', 'Slice',
        'Attribute',
        'IfExp', 'NamedExpr', 'Await',
        # Control flow
        'If', 'For', 'While', 'Break', 'Continue', 'Return', 'Yield', 'YieldFrom',
        'Try', 'TryStar', 'ExceptHandler', 'Raise', 'Assert', 'Pass',
        'With', 'withitem',
        'Match', 'match_case', 'MatchValue', 'MatchSingleton', 'MatchSequence',
        'MatchMapping', 'MatchClass', 'MatchStar', 'MatchAs', 'MatchOr',
        # Functions and classes
        'FunctionDef', 'AsyncFunctionDef', 'Lambda', 'ClassDef', 'Global', 'Nonlocal',
        # Comprehensions
        'ListComp', 'SetComp', 'GeneratorExp', 'DictComp', 'comprehension',
        # Assignments
        'Assign', 'AugAssign', 'AnnAssign',
        # Imports (validated separately)
        'Import', 'ImportFrom', 'alias',
        # Async
        'AsyncFor', 'AsyncWith',
        # Other
        'Delete',
        # Python 3.12+ type parameter syntax
        'TypeAlias', 'TypeVar', 'ParamSpec', 'TypeVarTuple',
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
        self._check_dangerous_builtins(tree)
        self._check_imports(tree)
        self._check_dangerous_attributes(tree)
        self._check_file_operations(tree)
        self._check_network_operations(tree)
        self._check_obfuscation(code)

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

    def _error(self, message: str, node: Optional[ast.AST] = None,
               severity: SecuritySeverity = SecuritySeverity.CRITICAL) -> None:
        line = getattr(node, 'lineno', None)
        self.errors.append(message)
        self.violations.append(SecurityViolation(message, severity, line))

    def _warn(self, message: str, node: Optional[ast.AST] = None,
              severity: SecuritySeverity = SecuritySeverity.MEDIUM) -> None:
        line = getattr(node, 'lineno', None)
        self.warnings.append(message)
        self.violations.append(SecurityViolation(message, severity, line))

    def _is_dunder(self, name: str) -> bool:
        return len(name) > 4 and name.startswith('__') and name.endswith('__')

    def _check_dangerous_builtins(self, tree: ast.AST) -> None:
        """Check for dangerous builtins and interpreter-introspection names.

        Works on ``ast.Name`` nodes, so ``re.compile(...)`` or
        ``self.gripper.open()`` (attributes) and words inside strings or
        comments are not matched.
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id in self.DANGEROUS_BUILTINS:
                    self._error(
                        f"Security Error: Dangerous builtin '{node.id}' detected at line "
                        f"{node.lineno}. This function can execute arbitrary code or access files.",
                        node)
                elif node.id in self.INTROSPECTION_NAMES:
                    self._error(
                        f"Security Error: Access to interpreter internals '{node.id}' detected "
                        f"at line {node.lineno}.", node)
                elif self._is_dunder(node.id) and node.id not in self.ALLOWED_DUNDERS:
                    self._error(
                        f"Security Error: Use of the special name '{node.id}' detected "
                        f"at line {node.lineno}.", node)

            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                if name in self.DANGEROUS_CALLS:
                    self._error(
                        f"Security Error: Dangerous builtin '{name}' detected at line "
                        f"{node.lineno}. Interactive input is not available in a node.", node)
                elif name in ('getattr', 'setattr', 'delattr', 'hasattr'):
                    self._check_dynamic_attribute(node, name)
                elif name == 'type' and len(node.args) == 3:
                    self._error(
                        f"Security Error: Dynamic class creation with type() detected at "
                        f"line {node.lineno}.", node)

    def _check_dynamic_attribute(self, node: ast.Call, func: str) -> None:
        """getattr/setattr/delattr must name the attribute with a safe string literal."""
        if len(node.args) < 2:
            return
        attr = node.args[1]
        if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
            self._error(
                f"Security Error: {func}() with a non-literal attribute name detected at "
                f"line {node.lineno}. Use a string literal so the access can be checked.",
                node)
            return
        if self._is_dunder(attr.value) and attr.value not in self.ALLOWED_DUNDERS:
            self._error(
                f"Security Error: {func}() of special attribute '{attr.value}' detected "
                f"at line {node.lineno}.", node)
        elif attr.value in self.DANGEROUS_ATTRIBUTES or attr.value in self.DANGEROUS_BUILTINS:
            self._error(
                f"Security Error: {func}() of dangerous attribute '{attr.value}' detected "
                f"at line {node.lineno}.", node)

    def _module_allowed(self, name: str) -> bool:
        """True if ``name`` (a full dotted module name) is on the allow-list."""
        if name in self.SAFE_MODULES:
            return True
        root, _, rest = name.partition('.')
        if root in self.INTERFACE_PACKAGES:
            return not rest or rest.split('.')[0] in self.INTERFACE_SUBMODULES
        return False

    def _check_module_name(self, name: str, node: ast.AST, kind: str) -> None:
        """Validate one imported module name against the block- and allow-lists."""
        parts = name.split('.')
        # sensitive if the module or any parent package is on the blocklist
        blocked = next((('.'.join(parts[:i + 1])) for i in range(len(parts))
                        if '.'.join(parts[:i + 1]) in self.SENSITIVE_MODULES), None)
        if blocked:
            self._error(
                f"Security Error: {kind} of sensitive module '{blocked}' detected. "
                f"This module is in the blocklist.", node)
        elif not self._module_allowed(name):
            if self.strict_mode:
                self._error(
                    f"Security Error: {kind} of unverified module '{name}' detected. "
                    f"Only pre-approved modules are allowed.", node, SecuritySeverity.HIGH)
            else:
                self._warn(
                    f"Security Warning: {kind} of unverified module '{name}' detected. "
                    f"Please verify this is safe.", node)

    def _check_imports(self, tree: ast.AST) -> None:
        """Check import statements against the module allow-list.

        Names must match exactly: ``import rclpy`` does not allow
        ``import rclpy.impl.implementation_singleton``.  Names imported with
        ``from module import name`` are checked against the module's blocked
        attributes.
        """
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            if not self.allow_imports:
                self._error("Security Error: Import statements are disabled.", node)
                continue

            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check_module_name(alias.name, node, "Import")
                continue

            if node.level:
                self._error("Security Error: Relative imports are not allowed.", node)
                continue

            module = node.module or ''
            self._check_module_name(module, node, "Import from")
            blocked_attrs = self.MODULE_BLOCKED_ATTRS.get(module, frozenset())
            for alias in node.names:
                if alias.name in blocked_attrs:
                    self._error(
                        f"Security Error: Import of '{module}.{alias.name}' is blocked "
                        f"(file, code-object or reflection access).", node)
                elif alias.name == '*' and module in self.MODULE_BLOCKED_ATTRS:
                    self._error(
                        f"Security Error: Wildcard import from '{module}' is blocked.", node)

    def _bound_names(self, tree: ast.AST) -> Set[str]:
        """Names the snippet itself defines (assignments, arguments, imports, ...)."""
        bound: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.ExceptHandler) and node.name:
                bound.add(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add((alias.asname or alias.name).split('.')[0])
        return bound

    def _import_aliases(self, tree: ast.AST) -> dict:
        """Map local names bound by ``import m [as a]`` to the module they refer to."""
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        aliases[alias.asname] = alias.name
                    else:
                        aliases[alias.name.split('.')[0]] = alias.name.split('.')[0]
        return aliases

    def _check_dangerous_attributes(self, tree: ast.AST) -> None:
        """Check attribute access: dunders, process-spawning names, module internals."""
        aliases = self._import_aliases(tree)
        bound = self._bound_names(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                attr = node.attr
                base = node.value.id if isinstance(node.value, ast.Name) else None
                if base in self.SENSITIVE_MODULES and base not in bound:
                    self._error(
                        f"Security Error: Use of sensitive module '{base}' detected at line "
                        f"{node.lineno}. This module is in the blocklist.", node)
                if self._is_dunder(attr) and attr not in self.ALLOWED_DUNDERS:
                    self._error(
                        f"Security Error: Access to special attribute '.{attr}' detected at "
                        f"line {node.lineno}. This could expose interpreter internals.", node)
                elif attr in self.DANGEROUS_ATTRIBUTES:
                    self._error(
                        f"Security Error: Dangerous attribute access '.{attr}' detected at "
                        f"line {node.lineno}. This could allow arbitrary code execution or "
                        f"system access.", node)
                elif base:
                    module = aliases.get(base) or (
                        base if base in self.MODULE_BLOCKED_ATTRS and base not in bound else None)
                    if module and attr in self.MODULE_BLOCKED_ATTRS.get(module, ()):
                        self._error(
                            f"Security Error: '{module}.{attr}' is blocked at line "
                            f"{node.lineno} (file, code-object or reflection access).", node)

            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in ('format', 'format_map'):
                self._check_format_call(node)

    _FORMAT_FIELD = re.compile(r'\{[^{}]*\}')

    def _check_format_call(self, node: ast.Call) -> None:
        """``'{0.__class__}'.format(x)`` walks attributes inside a string."""
        template = node.func.value
        if isinstance(template, ast.Constant) and isinstance(template.value, str):
            for field_text in self._FORMAT_FIELD.findall(template.value):
                if re.search(r'[.\[]\s*_', field_text):
                    self._error(
                        f"Security Error: str.format template {field_text!r} accesses a "
                        f"private or special attribute (line {node.lineno}).", node)
        else:
            self._warn(
                f"Security Warning: str.format with a non-literal template at line "
                f"{node.lineno}; attribute access inside format fields cannot be checked.",
                node, SecuritySeverity.LOW)

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
