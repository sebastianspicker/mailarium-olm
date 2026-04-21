# Security Policy

## Supported Versions

Only the latest version on the `main` branch is supported with security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue.
2. Email a description of the vulnerability, steps to reproduce, and any relevant context.
3. Allow reasonable time for a fix before any public disclosure.

## Scope

This project runs entirely locally — no data leaves the machine. The primary attack surfaces are:

- **OLM/XML parsing** — mitigated with XXE-safe lxml parser settings.
- **SQL injection** — mitigated with parameterized queries throughout.
- **Dependency supply chain** — mitigated with Dependabot, pip-audit, and bandit in CI.
- **Input sanitization** — ANSI/control character stripping on untrusted text.
