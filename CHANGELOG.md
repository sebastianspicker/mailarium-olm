# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows semantic versioning principles for public interfaces.

## [0.5.0a1] - Unreleased

### Added

- Added explicit retrieval scope and query-shape weighting across CLI, MCP, and
  Streamlit search.
- Added a source-checkout Streamlit interface for search, analytics, entity and
  network browsing, evidence review, and mailbox operations.
- Added optional on-premises EWS synchronization, canonical source mappings,
  bounded attachment handling, and proposal-controlled actions.
- Added public guidance for answer grounding, attachment support, privacy,
  runtime tuning, compatibility, and alpha release operations.
- Added authored synthetic QA fixtures with a provenance manifest.
- Added explicit migration guidance for installed runtime homes and renamed
  product-prefixed environment variables.
- Added a current synthetic Streamlit empty-archive screenshot rendered from
  the maintained HTML fixture.

### Changed

- Rebranded the distribution and public product to Mailarium while retaining
  the existing GitHub repository URL.
- Consolidated the Python implementation into `mailarium`, including the EWS
  transport under `mailarium.ews`.
- Raised the supported interpreter to Python 3.14.6 and aligned CI, Ruff, mypy,
  packaging metadata, and release instructions with that baseline.
- Replaced ChromaDB with SQLite-authoritative dense-vector storage and
  rebuildable USearch acceleration.
- Replaced FlagEmbedding with Sentence Transformers, Transformers, PyTorch,
  optional learned-sparse encoding, and a local late-interaction backend.
- Renamed installed commands to `mailarium` and `mailarium-ingest`, and moved
  supported module execution to `python -m mailarium.*`.
- Made CLI subcommands the supported terminal contract and retained ingestion
  as the separate `mailarium-ingest` entry point.
- Changed installed runtime defaults to the per-user `mailarium` directory.
- Renamed the EWS proposal-correlation property to `MailariumProposalId`;
  outstanding pre-0.5 proposals must be resolved before upgrading.
- Consolidated the former nested EWS implementation into one package, SQLite
  schema, runtime policy, release flow, and tool manifest.

### Fixed

- Serialized shared SQLite operations, made vector-index checkpoints
  recoverable, and retained SQLite exact-search fallback when USearch state is
  absent or stale.
- Fixed cross-process USearch cache freshness, installed-wheel runtime-home
  resolution, and embedding-model revision provenance.
- Preserved bounded EWS error bodies and HTTP status through SOAP parsing so
  conflicts, transient faults, expired watermarks, and unknown write outcomes
  retain their fail-closed state semantics.
- Made proposal reconciliation deduplicate repeated item IDs and durably
  conflict multiple unique correlation matches without projecting or
  tombstoning an arbitrary remote item.
- Bound the documented Streamlit launch to loopback and aligned the Streamlit
  theme with the dark application surface so labels and metric captions remain
  readable.
- Corrected the lockfile, synchronized environment command, public
  configuration example, documentation links, and privacy-scanner handling of
  redaction-key names.

### Removed

- Removed the `src` and `ews_inbox_assistant` import namespaces, the
  `email-rag*` commands, and compatibility aliases for `EMAIL_RAG_*` variables.
- Removed automatic use of the former installed runtime directory; migration
  is explicit and operator-controlled.
- Removed the legal/case/matter compatibility surface, schemas, tools, fixtures,
  reports, CLI paths, templates, and dead compatibility shims.
- Removed legacy flat CLI flags and backend-specific compatibility settings.

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
