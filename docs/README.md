# Documentation

This directory contains the public documentation for Mailarium `0.5.0a1`.

## Start here

- [../README.md](../README.md) - product overview, installation, privacy
  boundary, and first run
- [README_USAGE_AND_OPERATIONS.md](README_USAGE_AND_OPERATIONS.md) -
  configuration, runtime layout, Streamlit launch, troubleshooting, and
  lifecycle operations
- [CLI_REFERENCE.md](CLI_REFERENCE.md) - terminal commands and installed entry
  points
- [MCP_TOOLS.md](MCP_TOOLS.md) - MCP server setup and the 54-tool surface

## System references

- [ARCHITECTURE_AND_METHODS.md](ARCHITECTURE_AND_METHODS.md) - storage,
  retrieval, reranking, and limits
- [ANSWER_GROUNDING.md](ANSWER_GROUNDING.md) - answer states, verification
  modes, citations, and quote attribution
- [ATTACHMENT_SUPPORT.md](ATTACHMENT_SUPPORT.md) - format handling,
  extraction quality, and lossiness
- [PRIVACY_AND_REDACTION.md](PRIVACY_AND_REDACTION.md) - data placement,
  archive-report privacy modes, and their limits
- [RUNTIME_TUNING.md](RUNTIME_TUNING.md) - model loading, profiles, and
  performance guidance
- [API_COMPATIBILITY.md](API_COMPATIBILITY.md) - automation-facing stability
  expectations for the `0.5.x` alpha line

## Interfaces

| Surface | Use it for | Launch |
| --- | --- | --- |
| CLI | Repeatable searches, browsing, exports, analytics, and local administration | `mailarium --help` |
| Ingest CLI | Loading an Outlook `.olm` archive | `mailarium-ingest --help` |
| MCP | Structured archive workflows and integrations | `python -m mailarium.mcp_server` |
| Streamlit | Trusted-local exploration and review | `python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1` |

Streamlit is an exploratory source-checkout surface. CLI and MCP contracts are
the supported automation interfaces.

## Runtime and data boundaries

- Use tracked `data/` only for sanitized examples.
- In a source checkout, put live exports and runtime state below `private/`.
- Use `private/runtime/current/vector-index` and
  `private/runtime/current/email_metadata.db` for a source checkout.
- Installed wheels resolve relative runtime paths below the platform user-data
  directory or an explicit absolute `MAILARIUM_RUNTIME_HOME`.
- Source-checkout outputs default below `private/exports/`. Installed packages
  require an absolute writable root in `MAILARIUM_ALLOWED_OUTPUT_ROOTS` and
  absolute output paths inside it.
- Outputs must remain inside configured allowlisted roots and do not overwrite
  existing files.
- Keep all tracked docs, screenshots, and test fixtures synthetic.

## Release state

The docs describe the current source-tree interface, not a published release.
[../RELEASE_STATUS.md](../RELEASE_STATUS.md) separates measured local evidence
from the remaining candidate-review and remote-verification gates.
[../RELEASING.md](../RELEASING.md) defines the maintainer release procedure.
