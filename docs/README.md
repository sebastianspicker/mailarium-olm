# Mailarium documentation

- [../README.md](../README.md): installation, first ingest, interfaces, and
  local-data boundary
- [ARCHITECTURE.md](ARCHITECTURE.md): current modular-monolith design and
  dependency direction
- [CLI_REFERENCE.md](CLI_REFERENCE.md): command-line and EWS mailbox workflows
- [MCP_TOOLS.md](MCP_TOOLS.md): stdio server, tool groups, and mutation limits
- [README_USAGE_AND_OPERATIONS.md](README_USAGE_AND_OPERATIONS.md): runtime
  paths, maintenance, offline operation, and troubleshooting
- [RUNTIME_TUNING.md](RUNTIME_TUNING.md): profiles, model loading, and
  performance controls
- [ATTACHMENT_SUPPORT.md](ATTACHMENT_SUPPORT.md): optional extraction and OCR
  capabilities
- [ANSWER_GROUNDING.md](ANSWER_GROUNDING.md): evidence and citation contract
- [PRIVACY_AND_REDACTION.md](PRIVACY_AND_REDACTION.md): data placement,
  redaction modes, and review limits

The CLI and MCP schemas exposed by the installed package are the authoritative
automation interface. Streamlit is a trusted-local exploratory interface.
