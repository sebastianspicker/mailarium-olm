# Repo Audit 2026-04-20

Scope:

- public documentation and release-facing metadata
- GitHub workflow and repository metadata surface
- CLI, MCP, ingest, export, Streamlit, SQLite, and path-handling trust boundaries
- repo quality gates, dependency audit, and publication-safety checks

## Executive Summary

The repo is broadly healthy at the static-analysis layer: lint, type checking,
Bandit, and dependency audit pass. The confirmed issues found in this pass were
release-surface and publication-hygiene problems rather than runtime logic
failures.

Fixed in this pass:

- removed the provider-specific repo-agent GitHub workflow and prompt surface
  from the publishable `.github/` tree
- converted the agent-specific MCP setup guide into a neutral
  `docs/agent/mcp_client_config_snippet.md`
- removed public documentation references to the former provider-specific MCP
  config guide
- neutralized historical changelog wording that named provider-specific client
  integration paths
- removed a provider-specific temporary filename from a test fixture
- kept public package and README links privacy-neutral

## Confirmed Findings

### AUD-2026-04-20-01: Provider-specific GitHub workflow exposed in public repo

Severity: medium

Affected boundary: GitHub Actions, repository public surface

Evidence:

- a manually-triggered repo-agent workflow existed under `.github/workflows/`
- the workflow referenced a provider-specific hosted action and API secret
- a paired prompt file under `.github/` described agent-specific execution rules

Impact:

- public repository readers saw automation and secret assumptions that are not
  part of the product
- the workflow expanded the public attack/review surface without being required
  for normal CI
- it conflicted with the privacy-neutral publication goal

Fix:

- removed the workflow and prompt files from the publishable GitHub tree
- kept `.github/workflows/ci.yml` as the repo-native CI surface

### AUD-2026-04-20-02: MCP setup docs were tied to one client brand

Severity: medium

Affected boundary: advanced operator docs, public docs index, contract tests

Evidence:

- public docs linked to an agent-specific MCP config snippet
- runbooks used that same path as a persistent execution dependency

Impact:

- the repo looked coupled to one private/local agent setup even though the
  product exposes a generic MCP server
- public docs were less portable for other MCP-compatible clients

Fix:

- renamed the guide to `docs/agent/mcp_client_config_snippet.md`
- rewrote the content around generic MCP-client configuration
- updated docs and tests to use the generic guide

### AUD-2026-04-20-03: Historical release notes contained provider-specific client wording

Severity: low

Affected boundary: GitHub polish, release-facing docs

Evidence:

- older changelog bullets named provider-specific client integration and flags

Impact:

- stale historical wording made the current public surface look less
  privacy-neutral than the code and docs now are

Fix:

- rewrote the affected changelog bullets as generic MCP-client and
  provider-specific-flag removals

### AUD-2026-04-20-04: Live GitHub topics missing

Severity: low

Affected boundary: GitHub discoverability

Evidence:

- live repository metadata read-back returned no repository topics

Impact:

- the project is harder to discover and classify on GitHub

Fix:

- set neutral topics describing the actual project scope:
  `outlook`, `email-search`, `rag`, `mcp`, `local-first`, `python`,
  `chromadb`, `sqlite`, `privacy`, `ediscovery`

### AUD-2026-04-20-05: Full test suite emitted stale warning noise

Severity: low

Affected boundary: CI signal quality, release readiness

Evidence:

- the full regression suite passed but emitted 24 known warnings from deprecated
  flat CLI flag coverage and SWIG/importlib deprecation noise

Impact:

- the warning summary obscured new warnings that should be visible during future
  release and publication checks

Fix:

- added targeted pytest warning filters for the known flat-flag and SWIG/importlib
  deprecations
- verified the targeted warning slice and full suite no longer emit the warning
  summary

### AUD-2026-04-20-06: Bandit suppression hygiene obscured audit output

Severity: low

Affected boundary: security scan signal quality

Evidence:

- the security scan had no failing runtime issue under the configured policy, but
  historical inline `nosec` explanations produced Bandit manager/tester warnings
- removing stale suppression text exposed expected `B608` false positives around
  parameterized SQLite query fragments and one HuggingFace download pin finding

Impact:

- noisy suppression handling weakened the audit signal and made it harder to
  distinguish real findings from justified dynamic SQL patterns

Fix:

- converted justified dynamic SQL suppressions to minimal local `# nosec`
  annotations on the exact expression lines
- kept query fragments parameterized or allowlist-derived
- pinned the Visualized-BGE HuggingFace download to commit
  `a53c18db9fd0015b8f8d6a8d778a20a20d4cc21b`
- kept the Jinja HTML filter as escape-then-Markup and narrowed the suppression
  to that exact line

## Non-Findings

- No confirmed runtime code bug was found by the sampled full-repo static gates.
- No known dependency vulnerability was reported by the dependency audit with
  the documented ignore for the currently unfixed Pygments advisory.
- Bandit is quiet under the configured `-q -ll -ii` policy after suppression
  hygiene and the HuggingFace revision pin.
- Mypy reported only untyped-function notes and no errors.

## Verification Matrix

Final gates executed for this pass:

- `python -m ruff check .`
- `python -m ruff format --check .`
- `python -m mypy src`
- `python -m bandit -r src -q -ll -ii`
- `python scripts/dependency_audit.py`
- `python scripts/privacy_scan.py --json`
- `python scripts/privacy_scan.py --tracked-only --json`
- `python scripts/privacy_scan.py --include-history --json`
- strict marker grep over public docs, GitHub config, packaging, and tests
- `python -m pytest -q --tb=short tests/test_repo_contracts.py`
- `python -m pytest -q --tb=short tests/test_matter_file_ingestion.py`
- `python -m pytest -q --tb=short`
- CLI surface probes for `src.cli`, `src.cli case`, and `src.ingest`
- live GitHub metadata read-back for description and topics

## Residual Risks

- The working tree was already heavily dirty before this pass. Review and
  staging must remain path-specific.
- Provider-specific legacy operator artifacts are intentionally not represented
  in the tracked public `.gitignore`; keep any personal local ignores in
  `.git/info/exclude` or another untracked Git exclude file.
- Historical archived docs may still describe old execution models as archive
  context. They should stay outside the public first-reader path.
- The full repo contains extensive legal-support workflow code; static gates do
  not replace scenario-specific acceptance review for every legal-support
  product.
