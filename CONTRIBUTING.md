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

1. Update the public interface documentation when CLI, MCP, configuration,
   privacy, EWS, or output behavior changes.
2. Run the canonical profile:

```bash
uv run python scripts/verify.py fast
```

Use `uv run python scripts/verify.py pr` when the change needs type checking,
offline and native ingestion, security,
dependency, or privacy evidence. Reserve
`uv run python scripts/verify.py release` (`pr` followed by `package`) for a
frozen release candidate. The dependency audit can fail on newly published
advisories independently of the change.

Linux CI runs `pr` once, then `package` after that job succeeds. The `package`
profile covers Streamlit and built-wheel checks and is not a substitute for
the complete local `release` profile. macOS retains its independent release
validation.

These general CI jobs run automatically only for pull requests authored by
`dependabot[bot]`; maintainers can run them for other changes with the CI
workflow's manual dispatch. Read-only dependency and source security checks
also run on ordinary pull requests, main-branch pushes, and a weekly schedule.
The synthetic Pages demo is deployed only by manual workflow dispatch on `main`.
Set the repository's Pages source to **GitHub Actions** before publishing these
workflow changes. Legacy branch-based Pages publishing bypasses workflow gates
and can still deploy on a push; changing the workflow alone does not disable it.

3. State every skipped check and why.

Do not commit runtime data, generated exports, model artifacts, private logs,
or tool state. Do not expose Streamlit or MCP beyond a trusted local boundary.
Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.
