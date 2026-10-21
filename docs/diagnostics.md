# Diagnostics

The compiler prints `file:line:col: error: message` for syntax errors and
`file:line:col: ERROR|WARNING: message` for semantic diagnostics.  A problem in the
compiler itself is reported as `internal compiler error` (re-run with `-v` for the
traceback and please file an issue).

| Code | Severity | Meaning |
|------|----------|---------|
| E001 | error | Duplicate node definition |
| E002 | error | Duplicate parameter |
| E003 | error | Duplicate launch definition |
| E004 | error | Duplicate launch argument |
| E005 | error | Undefined reference |
| E006 | error | Member not found on a struct |
| E007 | error | Member not found in an imported scope |
| E008 | error | Unknown package: add it to `depends:` or `import` it |
| E010 | error | `message` / `service` / `action` interface declarations are parsed but not supported yet |
| E011 | error | Duplicate callback (for example two `on_init`) |
| E012 | error | A `@constraint` is used on the wrong kind of declaration or with the wrong number of arguments |
| E013 | error | Invalid `@qos` setting or value |
| E014 | error | `@range` minimum is greater than the maximum |
| E015 | error | A literal default does not match the declared type |
| W001-W005 | warning | Duplicate subscription / publication / service / action / component name |
| W009 | warning | Duplicate import |
| W020 | warning | Unknown `@constraint` |
| W021 | warning | Type not found in the installed ROS package (only when ROS is available) |
| W022 | warning | Unqualified type: write `package::Type` or `import package::Type` |
| W023 | warning | Launch event handlers are parsed but not generated yet |
| W024 | warning | Lifecycle manager transitions are not generated |
| W025 | warning | Node `components` are parsed but not generated yet |

Embedded Python that violates the sanitizer rules is reported as a `Security Error`
(see [security.md](security.md)).

The constraints the compiler understands, their targets and arities live in
`nos/semantic/constraints.py`.
