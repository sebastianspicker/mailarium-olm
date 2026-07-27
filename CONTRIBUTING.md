# Contributing To Mailarium

Mailarium is currently alpha software. Small, reviewable changes with explicit
tests and privacy boundaries are the easiest to merge.

## Before Opening An Issue

- Use the public docs in [`docs/README.md`](docs/README.md) for setup and
  operations questions.
- Search existing issues before filing a duplicate.
- Use synthetic examples only. Never paste real email bodies, addresses, local
  private paths, mailbox exports, databases, model caches, or exported reports.
- Report vulnerabilities through the private process in
  [`SECURITY.md`](SECURITY.md), not a public issue.

## Development Setup

Package metadata requires Python `>=3.14.6,<3.15`; CI uses Python 3.14.6.

```bash
git clone https://github.com/sebastianspicker/outlook-email-rag.git
cd outlook-email-rag
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install "uv==0.10.7"
uv lock --check
uv sync --locked --extra dev --extra nlp --extra image --extra training --extra ews-ntlm
```

Keep real mailbox data below the ignored `private/` directory. Tests and docs
must use synthetic fixtures.

## Pull Requests

1. Branch from `main` and keep the change focused.
2. Add a regression test for behavior changes.
3. Update public docs when a CLI, MCP, Streamlit, configuration, privacy, or
   compatibility contract changes.
4. Run the narrowest relevant check, then the repository gates:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy mailarium
uv run pytest -q
uv run python scripts/privacy_scan.py --tracked-only --json
```

5. List skipped checks and their reasons in the pull request.

Do not commit runtime data, exports, local work logs, tool state, release
artifacts, or private screenshots. Do not mix unrelated formatting-only edits
into a functional change.

## Compatibility

General, explicitly scoped retrieval is the product surface. Removed legacy
domain workflows, flat CLI flags, and backend-specific configuration names are
not compatibility contracts.
