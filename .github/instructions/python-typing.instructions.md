---
applyTo: "**/*.py"
---

# Strict Python typing

- Treat type checking as strict: every function, method, parameter, return value, class attribute, and module-level variable must have a precise type.
- Configure and run a strict type checker through `pyproject.toml`. Prefer `uv run mypy --strict .` unless the project establishes another checker.
- Do not use unbounded `Any`, `# type: ignore`, `cast()`, or `assert_type()` to bypass a type error. Fix the type model, narrow the value with a runtime check, or define a protocol instead.
- Use `object` for values whose type is genuinely unknown, then narrow with `isinstance`, pattern matching, or a type guard before use.
- Prefer concrete domain types over primitives where ambiguity matters: `NewType` for distinct identifiers, `Enum` for fixed values, `Literal` for finite strings, and frozen dataclasses for structured values.
- Prefer `TypedDict` for typed dictionary-shaped data and `Protocol` for structural interfaces. Avoid `dict[str, object]` when the shape is known.
- Use `TypeAlias` for meaningful complex types. Keep aliases close to their domain and name them clearly.
- Model absent values explicitly with `T | None`; validate and narrow before calling members that require `T`.
- Use `Sequence`, `Mapping`, `Iterable`, and other `collections.abc` abstractions for read-only inputs; return concrete collection types when callers need them.
- Use generics to preserve type information. Make `TypeVar` bounds and variance explicit only when required by the API.
