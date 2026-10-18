# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows semantic versioning principles for public interfaces.

## [Unreleased]

### Changed

- Redesigned the Streamlit interface and the synthetic Pages demo around one
  token system that separates stored message text, analyst input, and
  machine-derived values typographically. Fonts are local; nothing is fetched.
  Quoted history in message bodies is set apart, a typed evidence quote is
  underlined in its source while drafting, and charts follow the selected
  theme. The Evidence page's inline export form now hands its filters to the
  Export page, which previews the selection first. Several web labels moved to
  sentence case.

- Reorganised internal modules into explicit platform, model, archive,
  retrieval, ingestion, investigation, mailbox, and interface packages. CLI
  commands, MCP tool schemas, the archive schema, and environment variables
  are unchanged.
- The `mailarium` and `mailarium-ingest` console scripts now target
  `mailarium.interfaces.cli.main:main` and `mailarium.interfaces.cli.ingest:main`;
  command names are unchanged.
- The MCP server loads `.env` inside `main()` instead of at import time. Code
  that imports `mailarium.mcp_server` without running it no longer loads
  `.env`.
- HTML export, report, and dossier templates ship under
  `mailarium/investigation/templates/`.

### Removed

- The publication privacy scanner is release tooling under
  `scripts/release/privacy/` and is no longer included in the wheel.

### Fixed

- Hardened untrusted archive, attachment, image, HTML, address, and body-tail
  processing with pre-decode size checks, aggregate budgets, safe ZIP-method
  restrictions, and bounded traversal. EWS response, pagination, folder
  discovery, and approved-draft identity checks now fail closed at their
  respective protocol boundaries.
- Closed report-redaction, plain-terminal, maintenance-path, local-only
  reranker, and publication privacy-scan gaps. Security floors were raised for
  dependencies with fixed releases; the audit still reports the upstream
  `accelerate` and `nltk` advisories for which no fixed release is available.
- MCP tools that resolve a runtime dependency no longer fail with `NameError`,
  a regression since the 0.5 modularization.
- Thread and email HTML export and dossier generation find their templates
  again; they previously looked in a non-existent directory.
- Sender e-mail addresses are read from the nested `emailAddress` record of
  OLM sender elements; they were previously stored empty, which left sender,
  contact, network, and response-time views blank. Rebuild archives ingested
  before this fix from the `.olm` into a fresh runtime: messages without a
  Message-ID derive their identifier from the sender and would otherwise be
  stored twice.
- Re-running ingestion with `--extract-attachments` or `--extract-entities`
  now adds attachment text, attachment vectors, and entities to messages that
  are already stored, with or without `--incremental`.
- `--reembed` rebuilds attachment-text vectors from SQLite, so
  `admin reset-index` followed by `--reembed` keeps attachment search.
- `mailarium topics build` stores clusters instead of failing with
  `KeyError: 'cluster_id'`.
- Path-policy violations and a missing `.olm` file are reported as one-line
  errors before any model is loaded.
- EWS proposals whose request never reached Exchange (DNS, refused connection,
  proxy, or connect timeout) become retryable instead of uncertain.
- Raised security floors for `fsspec`, `multidict`, and `mcp` (kept below 2).
- A failed first-run model download names the model instead of reporting an
  unreadable archive, and local-only model loading no longer sends a metadata
  request to the Hugging Face Hub.
- `--reembed` also rebuilds attachment text of messages with an empty body.
- Re-extracted entities keep their per-message occurrence counts, and messages
  completed without vector writes no longer stay `pending`.
- A send interrupted after its draft was tagged becomes conflicted instead of
  offering a retry that could not succeed.
- Help, usage, and the missing-archive hint use the `mailarium` and
  `mailarium-ingest` entry points; a fresh archive logs one schema line instead
  of one per migration; PDF export explains a blocked HTML fallback.
- The README notes the tri-licensed `pyphen` dependency (via `textstat`).
- IMAP and POP archives without Exchange conversation ids are threaded through
  their In-Reply-To and References headers; `export thread` also accepts an
  email uid, and `--reingest-metadata` links archives ingested earlier.
- Allowlisted paths typed with different letter case than on disk (on
  case-insensitive macOS volumes) are accepted when they name the same
  directory; the tracked-file guard compares the same way.

### Added

- `mailarium mailbox resolve <proposal-id> --outcome executed|not-executed`
  closes an uncertain EWS proposal after the local operator has checked the
  mailbox. It requires an interactive terminal and is not exposed over MCP.

## [0.5.0a1] - Unreleased

### Added

- Added explicit retrieval scope and query-shape weighting across CLI, MCP, and
  Streamlit search.
- Added optional on-premises EWS synchronization, bounded attachment handling,
  and proposal-controlled actions.
- Added current public guidance for architecture, answer grounding, attachment
  support, privacy, runtime tuning, and alpha release operations.

### Changed

- Organised the runtime as a modular monolith with model, archive, ingestion,
  retrieval, investigation, mailbox, interface, and composition boundaries.
- Kept SQLite authoritative for archive data and vectors, with USearch as
  rebuildable acceleration.
- Made CLI subcommands and the separate `mailarium-ingest` entry point the
  supported terminal interface.
- Raised the supported interpreter to Python 3.14.6 and aligned the locked
  environment, tooling, and release procedure with that baseline.

### Fixed

- Kept EWS proposal execution fail-closed on configuration or expected-state
  drift and kept Streamlit bound to loopback in documented examples.
- Corrected public references to the current package layout and canonical
  verification profiles.

## [0.2.0] - 2026-04-21

### Added

- Added SQLite-backed archive metadata, analytics, attachment records, evidence
  collections, provenance, and relationship analysis.
- Added hybrid search, reranking, query expansion, thread intelligence, model
  diagnostics, and response budgeting.
- Added HTML/PDF-capable export paths, archive reporting, and a local Streamlit
  browsing interface.
- Expanded the MCP surface for search, browsing, analytics, entities, threads,
  attachments, evidence, reports, and administration.

### Changed

- Introduced the subcommand-oriented CLI while retaining transitional legacy
  compatibility.
- Adopted BGE-M3-family multilingual retrieval defaults.
- Tightened runtime path validation, transaction handling, output sanitization,
  and package-template inclusion.
- Documented a canonical local-first runtime layout under `private/`.

### Fixed

- Corrected attachment chunk identity, image-embedding retention, thread
  lookup, query expansion, response budgeting, and evidence update behavior.
- Prevented partial ingestion and re-embedding failures from silently
  discarding previously committed state.
- Improved OLM metadata recovery, quoted-content handling, and attachment text
  extraction.

## [0.1.0] - 2026-03-02

### Added

- Initial public release for local Outlook email RAG.
- Added CLI search and operational commands, MCP integration, and an optional
  local Streamlit UI.
- Added linting, typing, tests, static security analysis, and dependency-audit
  gates.

### Security

- Added input validation, terminal/output sanitization, and safe XML parsing
  constraints for OLM ingestion.
