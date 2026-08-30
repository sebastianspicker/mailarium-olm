# MCP tools

Mailarium exposes a stdio MCP server for local archive workflows. The schema
advertised by the running server is authoritative for tool names, parameters,
required fields, limits, and annotations.

## Start the server

```bash
.venv/bin/python -m mailarium.mcp_server
```

Use absolute paths in an MCP client configuration:

```json
{
  "mcpServers": {
    "mailarium": {
      "command": "/absolute/path/to/mailarium/.venv/bin/python",
      "args": ["-m", "mailarium.mcp_server"],
      "cwd": "/absolute/path/to/mailarium"
    }
  }
}
```

Pass `--vector-index-path` and `--sqlite-path` only when process-local archive
overrides are required. The server holds an instance lock for its configured
archive runtime.

## Tool groups

- Archive search, browsing, deep context, scan sessions, and exports
- Threads, topics, entities, contacts, relationship, network, and temporal
  analysis
- Evidence collection, provenance, custody, dossier, validation, and export
- Attachment inspection, archive reporting, diagnostics, and maintenance
- Optional EWS mailbox status, synchronization, triage, proposal, execution,
  and reconciliation workflows

Use `email_search_structured` to find candidates, then
`email_deep_context` or `email_answer_context` for stronger source context.
Use evidence tools to retain exact, reviewable material rather than treating a
ranking score as proof.

## Mutation and privacy boundaries

Ingestion, evidence mutation, export, and maintenance tools are write
operations. Their paths remain inside configured roots and outputs do not
overwrite existing files. Review generated outputs before sharing them.

EWS reads and writes are disabled by default. A remote read needs process and
account read enablement; a remote write additionally needs process and account
write enablement. Attachment content is separately gated. Credentials, SOAP
bodies, and synchronization watermarks are not returned in tool responses or
diagnostics.

MCP can create or inspect a proposal and execute an already-approved proposal.
It cannot approve or reject one: that human decision belongs to the local
interactive CLI. Remote MCP operations are not proof of live EWS behavior.

`email_report(type="archive")` supports the privacy modes in
[PRIVACY_AND_REDACTION.md](PRIVACY_AND_REDACTION.md). Redaction is heuristic;
review every output before sharing it.
