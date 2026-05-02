# Security Policy

## Supported Versions

Security fixes are only guaranteed for the latest state of the `dev` branch.

Best-practice support assumptions:

- no backport promise for older snapshots or local forks
- reports should reproduce against the latest `dev` branch when possible
- local configuration mistakes, unsafe export handling, and unsupported environment changes may fall outside coordinated disclosure scope

## Reporting A Vulnerability

Do not open a public GitHub issue for a suspected vulnerability.

Preferred process:

1. Use GitHub private vulnerability reporting for this repository if it is available.
2. If private reporting is unavailable, contact the maintainer directly before public disclosure.
3. Include the affected branch or commit, reproduction steps, impact, and any relevant logs or proof-of-concept details.
4. Give reasonable time for triage and remediation before public disclosure.

## Scope And Threat Model

This project is local-first, but that does not mean risk-free.

Primary security-sensitive areas include:

- **OLM/XML parsing**: mitigated with XXE-safe parsing limits and local-file handling constraints.
- **Local file and export paths**: write/export paths are validated against allowlisted local roots.
- **SQLite and query handling**: mitigated with parameterized queries and constrained input models.
- **Dependency supply chain**: monitored with CI checks including `bandit` and the bounded `scripts/dependency_audit.py` wrapper around `pip-audit`.
- **Untrusted content rendering**: ANSI/control-character stripping and output sanitization reduce terminal/rendering abuse.

## Defensive Review Notes

Last reviewed: 2026-05-02.

Architecture index:

- `src/cli.py`, `src/cli_parser.py`, and `src/cli_commands*.py`: local operator CLI entrypoints.
- `src/mcp_server.py` and `src/mcp_models*.py`: MCP tool surface and strict input models.
- `src/web_app.py`, `src/web_app_pages.py`, and `src/web_app_search.py`: local Streamlit browser surface.
- `src/parse_olm*.py`, `src/olm_xml_helpers.py`, and `src/attachment_extractor*.py`: untrusted OLM/XML and attachment parsing.
- `src/email_db*.py`, `src/db_*.py`, and `src/retriever*.py`: SQLite persistence and retrieval.
- `scripts/privacy_scan.py`, `scripts/dependency_audit.py`, and `scripts/run_acceptance_matrix.sh`: publication, dependency, and verification gates.

Current threat model:

- The intended deployment is local-first, but the Streamlit UI and MCP server still form trust boundaries when exposed to another local account, browser session, MCP client, or LAN listener.
- Operator-supplied paths must be authorized by purpose: runtime stores under allowed runtime roots, read inputs under allowed local-read roots, and generated artifacts under allowed output roots.
- Email bodies, attachments, generated reports, and legal-support bundles are sensitive even when synthetic test data is committed publicly.
- Model-loading paths may contact external model registries unless offline/local-only settings are used.

Finding fixed in this review:

- Severity: Medium.
- Boundary: Streamlit runtime path inputs in `src/web_app.py`.
- Evidence: the web UI accepted ChromaDB and SQLite paths through plain normalization, while CLI/MCP used allowlisted runtime-root validation.
- Impact: if the exploratory UI is exposed beyond the trusted operator browser, a user could point the process at arbitrary local runtime paths instead of the configured private/data/test roots.
- Patch: the web UI now validates ChromaDB and SQLite inputs with `validate_runtime_path()`.
- Regression: `tests/test_web_app_refactor_seams.py` rejects `/etc/archive.db` and only accepts `/tmp/archive.db` when `EMAIL_RAG_ALLOWED_RUNTIME_ROOTS=/tmp` is explicitly set.
- Verification evidence: targeted Streamlit regressions, repo-contract tests, focused ruff lint/format checks, `bandit`, dependency audit, current-tree privacy scan, `git diff --check`, and the top-level CLI help surface probe passed on 2026-05-02.

## Operational Notes

- Email content stays local, but first-run model loading may contact Hugging Face to download or validate cached model weights unless you explicitly run in offline mode.
- Generated HTML, PDF, CSV, JSON, and bundle exports may contain sensitive source content and should be reviewed before sharing.
- For serious operator use, keep live runtime data under `private/runtime/current/` and keep tracked `data/` sanitized.
