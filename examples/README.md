# Examples

Small, complete NOS programs.  They double as test fixtures: every file here is compiled
by the test suite, the output is checked for valid Python and `pyflakes` cleanliness, and
the generated code is compared with the snapshots in `tests/golden/`.

| File | Shows |
|------|-------|
| `publisher.node` | parameters with `@range`, a publisher, `on_init` |
| `subscriber_service_action.node` | subscription with QoS, publisher, service, action, typed callback |
| `lifecycle.node` | `lifecycle: managed`, `on_shutdown` |
| `launch.node` | launch arguments, a namespaced group, `include` with and without arguments |
| `full_feature.node` | nearly every construct: imports, structs, lists, durations, `@reentrant`, `@client`, remaps, `@when`, containers, lifecycle manager |

```bash
nos examples/publisher.node -o generated --no-build
```

After an intentional change to the generators, refresh the snapshots with
`NOS_UPDATE_GOLDEN=1 pytest tests/integration/test_golden.py` and review the diff.
