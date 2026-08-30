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

## Before opening a pull request

1. Add or update focused tests when behavior changes.
2. Update the public interface documentation when CLI, MCP, configuration,
   privacy, EWS, or output behavior changes.
3. Run the narrowest useful test, then the canonical profile:

```bash
python scripts/verify.py fast
```

Use `python scripts/verify.py pr` when the change needs type checking,
offline-ingest, security, dependency, or privacy evidence. Reserve
`python scripts/verify.py release` for a frozen release candidate.

4. State every skipped check and why.

Do not commit runtime data, generated exports, model artifacts, private logs,
or tool state. Do not expose Streamlit or MCP beyond a trusted local boundary.
Report vulnerabilities through [SECURITY.md](SECURITY.md), not a public issue.
