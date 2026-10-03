# Contributing to Mailarium

Mailarium is alpha software. Keep changes focused, use synthetic mail data, and
preserve local-first and fail-closed boundaries.

## Setup

Mailarium requires Python `>=3.14.6,<3.15`.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install "uv==0.10.7"
uv sync --locked --extra dev --extra nlp --extra training --extra ews-ntlm
```

Keep real archives, databases, model caches, exports, credentials, and local
paths below ignored storage. Tests, fixtures, screenshots, and documentation
must use synthetic content only.

## Change rules

- Preserve the dependency policy in `scripts/check_architecture.py`. Put
  SQL in `mailarium/archive/`, configuration in `mailarium/platform/`, and
  argument parsing, tool schemas, and rendering in `mailarium/interfaces/`;
  see "Where new code belongs" in [architecture](docs/ARCHITECTURE.md).
- Keep SQLite canonical and treat retrieval indexes as rebuildable state.
- Keep CLI, MCP, Streamlit, and bounded job resource ownership explicit.
- Preserve separate fail-closed gates for EWS reads, writes, and attachment
  content.
- Update the focused document under `docs/` when an interface, configuration,
  privacy, evidence, or operator contract changes.

## Before opening a pull request

1. Add or update focused tests when behavior changes.
2. Update the public interface documentation when CLI, MCP, configuration,
   privacy, EWS, or output behavior changes.
3. Run the narrowest useful test, then the canonical profile:

```bash
uv run python scripts/verify.py fast
```

Use `uv run python scripts/verify.py pr` when the change needs type checking,
the complete tests, critical coverage, offline and native ingestion, security,
dependency, or privacy evidence. Reserve
`uv run python scripts/verify.py release` (`pr` followed by `package`) for a
frozen release candidate. The dependency audit can fail on newly published
advisories independently of the change.

Interface snapshots for the MCP catalog, CLI help tree, archive schema, and
representative tool, search, and answer-context outputs live under
`tests/contract/snapshots/` and `tests/integration/snapshots/`. Regenerate
them for an intentional interface change with
`MAILARIUM_UPDATE_SNAPSHOTS=1` and review the diff as a contract change.

Linux CI runs `pr` once, then `package` after that job succeeds. The `package`
profile covers Streamlit and built-wheel checks and is not a substitute for
the complete local `release` profile. macOS retains its independent release
validation.

4. State every skipped check and why.

Do not commit runtime data, generated exports, model artifacts, private logs,
or tool state. Do not expose Streamlit or MCP beyond a trusted local boundary.
Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.
