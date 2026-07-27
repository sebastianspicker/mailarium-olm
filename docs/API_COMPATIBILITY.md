# API Compatibility Policy

This document defines the automation-facing contract for the `0.5.x` alpha
series.

## Supported Surfaces

The supported public interfaces are:

1. Subcommands and arguments exposed by `python -m mailarium.cli`.
2. MCP tool names and parameter schemas exposed by
   `python -m mailarium.mcp_server`.
3. Environment and constructor settings documented in the public guides.

Streamlit is an exploratory interface. Its layout is not a stable automation
contract.

## Deliberate Breaks In 0.5

The `0.5.0a1` Mailarium rebrand is an intentional hard cutover:

- `src` and `ews_inbox_assistant` are no longer importable packages. The Python
  namespace is `mailarium`, and EWS helpers now live below `mailarium.ews`.
- Installed commands are `mailarium` and `mailarium-ingest`; the former
  `email-rag*` commands are not installed as aliases.
- The four former `EMAIL_RAG_*` product variables were replaced by their
  `MAILARIUM_*` equivalents. Supplying a removed name fails with migration
  guidance instead of being ignored.
- Installed per-user runtime homes use a `mailarium` directory. Runtime data is
  migrated manually; Mailarium never moves, deletes, or falls back to the old
  directory automatically.
- The EWS proposal-correlation extended property is now
  `MailariumProposalId`. Resolve or reject outstanding pre-0.5 proposals before
  upgrading because their former correlation property is not read as an alias.
- MCP tool names and parameter schemas remain unchanged.

The canonical GitHub repository URL intentionally remains
`sebastianspicker/outlook-email-rag`.

## Earlier 0.4 Breaks

The following compatibility surfaces were removed:

- ChromaDB storage and the `CHROMADB_PATH` / `COLLECTION_NAME` settings.
- FlagEmbedding-specific model, fine-tuning, and ColBERT compatibility paths.
- The legal-domain compatibility pack and all case-, matter-, investigation-,
  behavioral-analysis-, and legal-support-specific schemas and tools.
- Flat legacy CLI flags and their dispatch shims.

Old backend environment variables fail explicitly instead of being silently
ignored. Re-index existing archives into a new `VECTOR_INDEX_PATH`; SQLite is
the authoritative vector store and USearch files are derived acceleration
artifacts.

## CLI Contract

The supported CLI is subcommand based:

- `search`
- `browse`
- `export`
- `evidence`
- `analytics`
- `training`
- `admin`
- `topics`
- `mailbox`

Run `python -m mailarium.cli <subcommand> --help` for its current arguments. Removed
flat flags and removed domain commands are parser errors.

MCP local-read paths, runtime storage paths, and output paths are validated
against their configured roots. The ingest CLI accepts an explicit `.olm`
source path, and training commands accept explicit local input paths. Date
filters use ISO `YYYY-MM-DD`; score and count inputs are range checked.

## MCP Contract

The MCP server exposes the general archive, retrieval, evidence, analytics,
thread, topic, reporting, and operational tools documented in
[MCP_TOOLS.md](MCP_TOOLS.md).

Compatibility rules:

- Do not rename a tool or change a parameter's type or requiredness within the
  `0.5.x` series without documenting the break.
- Additive optional fields are allowed.
- Response payloads may add diagnostic fields.
- Removed domain-specific schemas are not accepted through generic models.
- Retrieval scope is explicit user input and is never inferred from query text.

## Storage And Model Contract

- `SQLITE_PATH` identifies the authoritative relational and vector data.
- `VECTOR_INDEX_PATH` contains rebuildable USearch acceleration files.
- Text and image vectors use separate embedding spaces.
- Dense embedding, optional learned-sparse encoding, late interaction, and
  cross-encoder reranking are independent capabilities with explicit fallback
  behavior.
- Offline operation requires local-only embedding settings and
  `SPACY_AUTO_DOWNLOAD_DURING_INGEST=0` when entity extraction is enabled.

## Alpha Change Policy

Breaking changes remain possible between prereleases, but each break must:

1. fail clearly rather than silently changing meaning;
2. update source, tests, public docs, and release notes together;
3. include a migration or re-index instruction when stored data is affected;
4. be verified on Python 3.14.6.
