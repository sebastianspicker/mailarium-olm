# Security Policy

## Supported Versions

Before the first alpha tag is published, security work targets the current
`main` branch. After alpha publication begins, fixes target the latest tagged
alpha and current `main`. Older tags, development snapshots, and local forks
are not guaranteed to receive backports.

## Report A Vulnerability Privately

Do not disclose a suspected vulnerability in a public issue, discussion, log,
or pull request.

1. Use [GitHub private vulnerability reporting](https://github.com/sebastianspicker/outlook-email-rag/security/advisories/new).
2. Include the affected version or commit, a minimal reproduction, impact, and
   sanitized diagnostics. Do not attach real mailbox content.
3. Allow reasonable time for triage and remediation before disclosure.

If private vulnerability reporting is unavailable, open a content-free issue
titled `[security] private contact requested`. Do not include vulnerability
details; a maintainer can establish a private channel.

## Scope And Threat Model

Mailarium is local-first, but the data and process boundaries remain sensitive:

- OLM, XML, MIME, and attachments: inputs are untrusted and are parsed with
  bounded, hardened helpers. Treat parser and extraction bypasses as security
  issues.
- Local paths and exports: MCP-provided local read paths and all runtime and
  output paths are purpose-bound and validated against configured allowlisted
  roots. The ingest CLI accepts a direct `.olm` path.
- SQLite and query handling: parameterized queries and shared validation
  constrain dynamic identifiers and placeholder fragments.
- On-premises EWS: remote access is limited to an explicitly configured
  HTTPS endpoint. Credential values remain outside SQLite, reads/writes/content
  are independently opt-in, SOAP parsing is hardened, redirects are rejected,
  attachment content has per-file/count/aggregate budgets, unsupported sync
  changes cannot advance cursors, approved actions are bound to non-secret
  account configuration, and remote diagnostics omit SOAP bodies and credential
  material.
- Streamlit and MCP: both are trust boundaries if exposed to another local
  account, browser session, MCP client, container, or network listener. They are
  not designed as unauthenticated public services.
- Model loading: first-run model resolution may contact Hugging Face unless
  local-only settings are selected. Entity extraction can separately invoke
  spaCy's downloader unless `SPACY_AUTO_DOWNLOAD_DURING_INGEST=0`.
- Dependency audits: CI runs source analysis and the bounded dependency-audit
  wrapper. A passing audit is evidence for that candidate and database snapshot,
  not a permanent guarantee.

Email bodies, attachments, SQLite databases, vector indexes, and exported
reports can contain sensitive material. In a source checkout, keep live data
under ignored `private/` paths. Installed packages use the per-user runtime
home and explicit allowed output roots. Review every export before sharing.

## Accepted Dependency Exception

The `0.5.0a1` candidate accepts `PYSEC-2026-597`, also identified as
`CVE-2026-12243`, in the transitive `nltk==3.9.4` dependency. No fixed NLTK
release is available in the audit data used on 2026-07-24. Mailarium reaches
NLTK through `textstat` for optional readability scoring and does not call
`nltk.data.load` or `nltk.data.find` with operator-controlled resource
names. This limits the known path-traversal exposure but does not remove it.
The exception must be reevaluated when a fixed NLTK release becomes available.

## Publication Boundary

Checked-in examples, fixtures, and screenshots must be synthetic. Before a
release candidate is published, run:

```bash
uv run python scripts/privacy_scan.py --tracked-only --json
uv build --out-dir dist
uv run python scripts/check_release_artifacts.py dist
```

An unreadable candidate file is a failed privacy scan, not an implicit pass.

Last reviewed: 2026-07-24.
