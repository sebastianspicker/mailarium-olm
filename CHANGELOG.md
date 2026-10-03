# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows semantic versioning principles for public interfaces.

## [Unreleased]

### Changed

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

- MCP tools that resolve a runtime dependency no longer fail with `NameError`,
  a regression since the 0.5 modularization.
- Thread and email HTML export and dossier generation find their templates
  again; they previously looked in a non-existent directory.

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
