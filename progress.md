# NOS Project Progress

## Current Status: Phase 1 (Core Language Implementation)

### Done
- **ANTLR4 grammar** for `.node` and `.interface` files; operator precedence is encoded in the
  grammar and, since the expression-builder fix, preserved in the AST.
- **AST construction**, typed nodes with source locations; `list<T>` and interface declarations parse.
- **Semantic analysis**: packages resolved from `depends:`/`import`, constraint registry, duplicate
  and type checks, diagnostic codes documented in [docs/diagnostics.md](docs/diagnostics.md).
- **Python code generation** for nodes (parameters, subscriptions, publications, services, actions,
  lifecycle, callbacks) and **launch files** (arguments, groups, containers, includes).
- **CLI** (`nos`), visual editor (`nos-codeblock`), VS Code syntax highlighting.
- **Sanitizer** for embedded Python (a guard rail, see [docs/security.md](docs/security.md)).
- **CI**: lint, tests on Python 3.9-3.13, a ROS 2 container job and package checks.
- Open issues tracked on GitHub: callback/diagnostic work formerly listed here as "done"
  (#2-#6) is covered by tests in `tests/unit/test_diagnostics.py`,
  `tests/unit/test_callback_formatting.py` and `tests/integration/test_callbacks.py`.

### Not done yet
- Message/service/action interface *generation* (declarations parse, E010 is reported).
- Node `components`, launch event handlers and lifecycle transitions (parsed, warned about).
- C++ code generation (Phase 2); LSP/IDE support beyond syntax highlighting.
- Stress tests with large nested launch configurations.

## Known Limitations
- Expressions within `PYTHON_CODE` blocks are handled as raw strings by the DSL; the internal
  Python logic is checked by the sanitizer but not parsed into the NOS AST.
- The documentation site lives in `YasiruRF/nos-documentation`; its samples are not checked here.
  Samples in this repository's README and `docs/` are compiled by `tests/doc_examples/`.
