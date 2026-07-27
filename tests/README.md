# Test structure

Pytest collects the complete suite from `tests/`, as configured in
`pyproject.toml`.

## Layout

```text
tests/
├── test_*.py              Collected component and contract tests
├── _*_cases.py            Active split case modules imported by collected tests
├── conftest.py            Shared fixtures and offline dependency stubs
├── helpers/               Reusable builders and test doubles
├── fixtures/              Tracked static and golden fixtures
└── mailbox/               Optional EWS and mailbox tests with XML fixtures
```

The underscore-prefixed case modules are active test source. They partition
large suites while the corresponding `test_*.py` modules provide stable
collection paths. Do not ignore or archive them.

New standalone tests should use a descriptive `test_*.py` module. Add shared
utilities to `helpers/`, static inputs and expected outputs to `fixtures/`, and
mailbox protocol cases to `mailbox/`.

## Fixture policy

- `fixtures/html_normalization/` contains tracked input and expected-output
  pairs.
- `fixtures/qa_eval/` contains tracked synthetic questions and captured golden
  results. The refresh script must reproduce the captured files exactly.
- `mailbox/fixtures/` contains tracked synthetic EWS XML responses.
- Local runtime data belongs under ignored temporary paths, not in the tracked
  fixture directories.

## Running tests

Run the complete suite:

```bash
uv run pytest -q
```

Run the CI coverage gate:

```bash
uv run pytest -q --cov=mailarium --cov-report=term-missing --cov-fail-under=80
```

Run one component while developing:

```bash
uv run pytest -q tests/test_storage.py
uv run pytest -q tests/mailbox
```
