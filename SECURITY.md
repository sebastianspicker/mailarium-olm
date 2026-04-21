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

## Operational Notes

- Email content stays local, but first-run model loading may contact Hugging Face to download or validate cached model weights unless you explicitly run in offline mode.
- Generated HTML, PDF, CSV, JSON, and bundle exports may contain sensitive source content and should be reviewed before sharing.
- For serious operator use, keep live runtime data under `private/runtime/current/` and keep tracked `data/` sanitized.
