---
applyTo: "**/*.py"
---

# Python 3.12

## Tooling

- Use `uv` to create environments, manage dependencies, and run commands.
- Define project metadata, dependencies, tool settings, and Python version requirements in `pyproject.toml`; do not add `requirements.txt`, `setup.py`, or `setup.cfg`.
- Use Ruff for linting and formatting. Run `uv run ruff check .` and `uv run ruff format --check .` before completing Python changes.
- Use pytest for tests. Add or update focused tests for behavior changes and run them with `uv run pytest`.

## Code

- Target Python 3.12. Use modern syntax: built-in generics (`list[str]`, `dict[str, int]`), `X | None`, `match` where it improves clarity, and `typing.Self` when appropriate.
- Follow the strict typing rules in `python-typing.instructions.md`.
- Keep modules focused and functions small. Make dependencies explicit through parameters or constructors rather than hidden global state.
- Prefer `pathlib.Path`, context managers, f-strings, `collections.abc` interfaces, and `datetime` values with explicit time zones.
- Use `@dataclass(frozen=True, slots=True)` for immutable value objects when it fits the domain.
- Validate external input at boundaries. Raise specific exceptions with actionable messages; do not catch broad `Exception` or silently ignore failures.
- Do not use mutable default arguments. Avoid `assert` for validating user input or runtime behavior.
- Prefer standard-library solutions before adding a dependency.

## Tests

- Keep tests deterministic, independent, and behavior-focused.
- Use pytest fixtures for setup and teardown. Inject clocks, randomness, I/O, and network clients so tests can use fakes.
- Cover successful behavior, expected failures, and important edge cases. Do not make external network calls in unit tests.
