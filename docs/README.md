# Documentation Guide

This directory contains the public reference material for Email RAG.

## Start Here

- [../README.md](../README.md) for product overview, privacy boundaries, first-run setup, interface choice, and quick start
- [ARCHITECTURE_AND_METHODS.md](ARCHITECTURE_AND_METHODS.md) for system architecture, retrieval mathematics, evaluation methodology, and a synthetic end-to-end example
- [README_USAGE_AND_OPERATIONS.md](README_USAGE_AND_OPERATIONS.md) for configuration, runtime layout, troubleshooting, lifecycle, and go-live practices
- [CLI_REFERENCE.md](CLI_REFERENCE.md) for the terminal interface
- [MCP_TOOLS.md](MCP_TOOLS.md) for the full MCP tool surface
- [RUNTIME_TUNING.md](RUNTIME_TUNING.md) for performance, model-loading, and Apple Silicon guidance
- [API_COMPATIBILITY.md](API_COMPATIBILITY.md) for interface-stability expectations and automation-facing boundaries

## Choose The Right Surface

Use these rules when deciding where to start:

- Start with the CLI when you want explicit, repeatable local commands.
- Start with MCP when an assistant or MCP client should orchestrate the tool calls.
- Use Streamlit for exploration and browsing, not for authoritative counsel-ready output.

## Runtime And Data Boundaries

- Use tracked `data/` only for sanitized demo fixtures and checked-in examples.
- Point active operator runtimes at `private/runtime/current/`.
- Put real Outlook exports and live matter files in `private/`.
- Write/export outputs default below `private/exports/`, must resolve inside configured local allowlisted roots, and must not overwrite existing files; extend with `EMAIL_RAG_ALLOWED_OUTPUT_ROOTS` when required.
- Default live QA eval reports now write under `private/tests/results/qa_eval/`.
- MCP `email_ingest` does not silently switch the active runtime archive used by later searches.
- Keep checked-in `data/` and `tests/fixtures/` content sanitized.

## Public Vs Advanced Docs

The public reading path should stay in the files above unless you are intentionally working on advanced legal-support or operator material.

### Public Reference Docs

- `README.md`
- `ARCHITECTURE_AND_METHODS.md`
- `README_USAGE_AND_OPERATIONS.md`
- `CLI_REFERENCE.md`
- `MCP_TOOLS.md`
- `RUNTIME_TUNING.md`
- `API_COMPATIBILITY.md`

### Advanced `docs/agent/` Material

Treat [`agent/README.md`](agent/README.md) as the single entry point for advanced legal-support product docs, operator runbooks, synthetic fixtures/goldens, and archive/history surfaces. Keep the top-level public docs hub focused on stable product and operations references.

`agent/Documentation.md` is a verification/change log, not the public docs map.

Historical audit artifacts live under [`agent/deprecated/`](agent/deprecated/) and remain archive-only context, not current execution inputs.
