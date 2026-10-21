# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking changes

- The `.nos` extension is no longer accepted; use `.node` (`.interface` is unchanged).
- `nos --target cpp` was removed (it never generated anything). Empty input and files that
  declare no node or launch now fail instead of "succeeding" with no output.
- The VS Code extension is no longer installed as a side effect of every `nos` run; use
  `nos --install-vscode`.
- Requires Python 3.9 or newer (3.8 is end of life).
- `nos.runtime.decorators` (unused FlowLang-era decorators) was removed.
- `depends:` / `import` now decide which interface packages may be used. The built-in list
  still covers the standard ROS 2 packages, but `turtlesim`/`turtlesim_msgs` must be declared.
- Embedded code: `${param}` inside a plain (non-f) string is left alone; inside an f-string it
  becomes `{self.param}`.

### Added

- GitHub Actions CI (lint, Python 3.9-3.13 matrix, `ros:humble` job, wheel/sdist checks),
  `pyproject.toml`, `.flake8`.
- Golden-file snapshots and `pyflakes` checks for generated code; a fake `rclpy` for tests.
- `@qos(reliability=..., durability=..., history=..., depth=...)` is parsed and validated.
- Constraint registry (`nos.semantic.constraints`); new diagnostics E010-E015 and W021-W025
  (see `docs/diagnostics.md`).
- Packages shared by several inputs are compiled together; `package.xml`/`setup.py` use the
  `version` and `depends:` of the source.
- `nos --install-vscode`; `docs/security.md` (threat model of embedded Python).

### Changed

- Compiler diagnostics are `file:line:col: error: message`; compiler bugs are reported as
  "internal compiler error" instead of looking like source errors.
- The sanitizer works on the AST (no more false positives for `re.compile`, `obj.open()`,
  `client.call()`, `threading`, `hashlib`) and closes known bypasses; it is documented as a
  guard rail, not a sandbox.
- `nos-codeblock` binds to 127.0.0.1, requires a session token and confines file writes.
- Generated code imports explicit names (no wildcard imports) and only what it uses.

### Fixed

- Binary, member-access, index, call and unary expressions collapsed to their first operand.
- `list<T>` types and interface declarations crashed the AST builder.
- Launch files: `include` with args was a SyntaxError, declared arguments were never added to
  the `LaunchDescription`, wrong package/executable names, invented `lifecycle_manager` package,
  node remaps and `@when` conditions were dropped.
- Lifecycle nodes: duplicate/recursive `on_shutdown`, missing import, communications created twice.
- `@range`, `duration` literals, keyword identifiers, struct defaults, `@description`.
- Security errors of all nodes are reported (only the last node's were before).
- Multi-file packages no longer overwrite each other's `setup.py` entry points.
- Analyzer: `@reentrant`/`@client` no longer warn; `analyze()` can be called twice.

### Security

- Sanitizer hardened (dunder access, `getattr` with computed names, `str.format` traversal,
  module-attribute allow-list, exact-name import allow-list).
- `nos-codeblock`: arbitrary file write, CSRF and all-interface binding fixed.

## [0.1.7] - 2026-07-07

### Fixed

- Launch file suffix matching (`.launch.py` -> `_launch.py`).

## [0.1.6] - 2026-07-07

### Fixed

- `CompilerPipeline` import in the code block editor.
- VS Code extension packaging (duplicate directory nesting, tmLanguage JSON).

## [0.1.5] - 2026-07-07

### Added

- VS Code syntax highlighting extension, bundled and auto-installed.

## [0.1.4] - 2026-07-07

### Added

- Visual code block editor (`nos-codeblock`).

## [0.1.3] - 2026-07-07

### Added

- Action server validation, outgoing service/action clients, reentrant callback groups.

## [0.1.2] - 2026-07-06

### Changed

- The CLI resolves its version from the installed package metadata.

## [0.1.1] - 2026-07-06

### Fixed

- Added `nos/grammar/__init__.py` so the grammar is included in the distribution;
  `rclpy` removed from `install_requires`.

## [0.1.0] - 2026-04-20

### Phase 1: Core Language Implementation

This release establishes the foundational compiler infrastructure for NOS (Node Orchestration System), a declarative DSL for ROS2 robotics development.

### Added

- **ANTLR4 Grammar** (`nos/grammar/`)
  - Complete lexer and parser for NOS syntax
  - Support for `.nos`, `.node`, and `.interface` file extensions
  - Auto-generated parser files from grammar definitions

- **AST Construction** (`nos/ast/`)
  - Typed AST node hierarchy with 40+ node types
  - Source location tracking for accurate error reporting
  - Visitor pattern implementation for AST traversal
  - ASTBuilder for converting ANTLR4 parse trees to typed AST

- **Semantic Analysis** (`nos/semantic/`)
  - Symbol table with scoped symbol resolution
  - Multi-pass semantic analyzer (symbol building, reference resolution)
  - Type checking for ROS2 message types
  - Constraint validation (range, one_of, etc.)
  - Comprehensive diagnostic reporting with error codes

- **Python Code Generation** (`nos/codegen/`)
  - PythonGenerator: Generates ROS2 Python nodes from AST
  - LaunchTranspiler: Converts NOS launch to ROS2 Python launch
  - Support for lifecycle-managed nodes
  - QoS profile generation
  - Automatic parameter declaration with validation

- **Runtime Library** (`nos/runtime/`)
  - NOSNode: Enhanced base class for ROS2 nodes
  - NOSLifecycleNode: Lifecycle-managed node base class
  - Decorators for declarative parameter/subscription/service definitions
  - QoS utility functions (reliable, best_effort, sensor, parameter profiles)

- **Compilation Pipeline** (`nos/compiler/`)
  - End-to-end compiler pipeline (parse -> analyze -> generate)
  - CLI entry point with argparse interface
  - Support for file and string-based compilation
  - Batch compilation for multiple files
  - Dry-run mode for validation without generation

- **Security Validation** (`nos/security/`)
  - PythonCodeSanitizer with defense-in-depth validation
  - AST allowlist-based validation
  - Dangerous builtin detection (eval, exec, compile, etc.)
  - Import restriction to safe modules only
  - Pattern-based detection of obfuscation attempts
  - Comprehensive audit logging

- **Test Suite** (`tests/`)
  - Unit tests for AST nodes and builder
  - Semantic analysis tests
  - Code generation tests
  - Security validation tests
  - Integration tests for full compilation pipeline

### Known Limitations

- C++ code generator is planned but not yet implemented
- IDE/language server support not yet available
- Visual diagram generation not yet implemented
- Some advanced constraint types not yet enforced at runtime
- No incremental compilation support
- Limited error recovery in parser (fails on first syntax error)

### Security

- Implemented security validation for all embedded Python code
- Blocked dangerous builtins (eval, exec, __import__, etc.)
- Restricted imports to safe module allowlist
- Added detection for code obfuscation attempts
- All callback code is wrapped in try/except for runtime safety

[Unreleased]: https://github.com/YasiruRF/nos/compare/v0.1.7...HEAD
[0.1.7]: https://github.com/YasiruRF/nos/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/YasiruRF/nos/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/YasiruRF/nos/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/YasiruRF/nos/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/YasiruRF/nos/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/YasiruRF/nos/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/YasiruRF/nos/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/YasiruRF/nos/releases/tag/v0.1.0
