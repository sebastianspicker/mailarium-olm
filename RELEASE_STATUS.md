# Release Status

Evidence date: 2026-07-24

Candidate version: `0.5.0a1`

Publication status: not ready

## Candidate scope

The candidate provides local Outlook `.olm` ingestion, SQLite-authoritative
storage, rebuildable USearch acceleration, CLI and MCP interfaces, a
trusted-local Streamlit interface, and optional on-premises EWS workflows.

The supported operator runtime is macOS 14 or later on Apple Silicon with
Python 3.14.6. The Ubuntu CI job validates source compatibility but is not an
operator-runtime claim.

EWS remains experimental. Offline fixtures cover the implemented protocol and
action contracts, but live server interoperability and write behavior have not
been verified for this candidate. Offline verified; live EWS writes unverified.

## Local verification

| Gate | Result |
| --- | --- |
| Lockfile | `uv lock --check` passed with 177 packages |
| Clean environment installation | `uv sync --locked --extra dev --extra nlp --extra image --extra training --extra ews-ntlm` passed in an isolated snapshot |
| Ruff lint | `uv run ruff check .` passed |
| Ruff formatting | `uv run ruff format --check .` passed for 515 files |
| Mypy | `uv run mypy mailarium` passed for 187 source files |
| Full tests | 2,715 passed, 2 skipped, 1 warning |
| Coverage | 88.96 percent; required threshold is 80 percent |
| Bandit | No findings at high severity and confidence |
| Dependency audit | No unignored vulnerabilities; the documented NLTK exception remains |
| Captured QA fixtures | All four captured reports matched their source fixtures |
| Streamlit startup | Loopback startup smoke passed |
| Build | Wheel and source distribution built successfully |
| Release artifact inspection | Both package artifacts passed inspection |
| Installed wheel | Both version interfaces, packaged templates, EWS preflight, and an isolated SQLite vector round trip passed outside the checkout |
| Public-tree privacy scan | The isolated 619-file candidate snapshot returned no findings |
| Clean-snapshot tests | 2,715 passed, 2 skipped, 1 warning |

The pytest warning is a non-fatal assertion-rewrite warning for
`tests._scan_session_cases`, which is imported as a pytest plugin and as a test
support module.

## Publication requirements

Before publishing `0.5.0a1`:

1. Review and commit the complete package-namespace migration and file
   deletions as one intentional candidate.
2. Run both configured GitHub Actions jobs against that exact commit.
3. Repeat the tracked-only privacy scan and artifact checks against the exact
   committed tree.
4. Confirm package-name and project-name availability for each publication
   channel.
5. Reevaluate the accepted NLTK vulnerability exception against the current
   advisory database.
6. If EWS support is included in release notes, validate a disposable
   authorized server profile or state clearly that only offline protocol
   fixtures were verified.

Do not publish from the current unstaged worktree.
