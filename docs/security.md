# Security model of embedded Python

NOS callbacks (`on_init -> { ... }`, `on foo(x: int) -> { ... }`) contain
ordinary Python that the compiler copies into the generated node.

## What the sanitizer is

The sanitizer (`nos.security`) is a **guard rail, not a sandbox**.  It parses
every callback with `ast` and rejects code that:

- calls or even names `eval`, `exec`, `compile`, `__import__`, `open`,
  `globals`, `locals`, `vars` or `__builtins__`;
- reads dunder attributes such as `__class__`, `__globals__` or `__subclasses__`;
- uses `getattr`/`setattr`/`delattr` with a computed attribute name, or
  `type(name, bases, dict)`;
- walks attributes through `str.format` templates (`'{0.__class__}'.format(x)`);
- imports anything that is not on the module allow-list (exact module names;
  `os`, `sys`, `subprocess`, `socket`, `pickle`, ... are blocked);
- uses attributes of allowed modules that touch files or build code objects
  (`numpy.loadtxt`, `json.codecs`, `types.CodeType`, `operator.attrgetter`, ...).

The checks run on the syntax tree, so a word inside a string or a comment is
never mistaken for code, and `self.gripper.open()` or `re.compile(...)` are fine.
Ordinary ROS code (threads, hashing, `client.call(req)`, `numpy`, message
classes) is accepted.

## What it is not

Static filtering of Python cannot contain a determined attacker: the language
has too many ways to reach its own internals.  Callback code runs **inside the
node process with the privileges of the user who launches it**.

- Only compile `.node` files you trust, exactly as you would only run Python
  scripts you trust.
- If you must compile untrusted `.node` files, do it (and run the result) in an
  OS-level sandbox: a container, a separate unprivileged user, or a VM.  Do not
  rely on the sanitizer for that.

If you find a snippet that gets past the sanitizer, please report it as a bug;
it is added to the regression tests in `tests/unit/test_sanitizer.py`.

## Diagnostics

Violations are reported as compile errors and the offending callback is not
emitted as runnable code.  Warnings (file- or network-looking method names,
obfuscation heuristics) do not stop compilation.
