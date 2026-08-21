# MCP Tools

Mailarium exposes 54 local tools through the MCP server.

## Start the server

From a source checkout:

```bash
.venv/bin/python -m mailarium.mcp_server
```

Example client configuration:

```json
{
  "mcpServers": {
    "mailarium": {
      "command": "/absolute/path/to/mailarium/.venv/bin/python",
      "args": ["-m", "mailarium.mcp_server"],
      "cwd": "/absolute/path/to/mailarium",
      "env": {
        "VECTOR_INDEX_PATH": "private/runtime/current/vector-index",
        "SQLITE_PATH": "private/runtime/current/email_metadata.db"
      }
    }
  }
}
```

Use absolute command and working-directory paths. Relative runtime paths are
then resolved from the source checkout.

## Tool surface

The client-provided MCP schema is authoritative for parameter types,
requiredness, limits, and enumerated values.

### Search and archive access

- `email_search_structured`
- `email_answer_context`
- `email_triage`
- `email_scan`
- `email_find_similar`
- `email_browse`
- `email_deep_context`
- `email_export`
- `email_ingest`
- `email_list_senders`
- `email_list_folders`
- `email_stats`
- `email_discovery`

### Topics and threads

- `email_clusters`
- `email_topics`
- `email_thread_lookup`
- `email_thread_summary`
- `email_action_items`
- `email_decisions`

### Entities and relationships

- `email_search_by_entity`
- `email_list_entities`
- `email_entity_network`
- `email_entity_timeline`
- `email_contacts`
- `email_network_analysis`
- `relationship_paths`
- `shared_recipients`
- `coordinated_timing`
- `relationship_summary`

### Evidence and provenance

- `custody_chain`
- `email_provenance`
- `evidence_provenance`
- `email_dossier`
- `evidence_add`
- `evidence_add_batch`
- `evidence_query`
- `evidence_get`
- `evidence_update`
- `evidence_remove`
- `evidence_verify`
- `evidence_export`
- `evidence_overview`

### Analysis, reporting, attachments, and administration

- `email_temporal`
- `email_quality`
- `email_report`
- `email_attachments`
- `email_admin`

### EWS mailbox

- `email_mailbox_status`
- `email_mailbox_sync`
- `email_mailbox_triage`
- `email_mailbox_propose_action`
- `email_mailbox_proposal_status`
- `email_mailbox_execute_approved`
- `email_mailbox_reconcile`

There is deliberately no MCP approval or rejection tool. MCP proposals are
created with the trusted MCP principal; only the interactive local CLI
can approve or reject them as the human principal. Execution reuses the exact
approved target, expected change key, and parameters. Remote sync and execution
are marked open-world; approved execution is destructive and is not advertised
as transport-idempotent.

## Common workflows

### Search, inspect, and answer

1. Call `email_search_structured` with the query, optional metadata filters,
   and optional `scope`.
2. Call `email_deep_context` for the selected UID when full body, thread,
   evidence, or sender context is needed.
3. Use `email_answer_context` when the client needs a bounded, citable answer
   contract with ambiguity and weak-evidence handling.

See [ANSWER_GROUNDING.md](ANSWER_GROUNDING.md) for the decision and citation
contract.

### Progressive triage

Use a shared `scan_id` with `email_triage`, `email_search_structured`, and
`email_find_similar`. Manage the session through `email_scan`.

### Evidence collection

1. Read the full source with `email_deep_context`.
2. Add an exact body substring through `evidence_add`.
3. Review through `evidence_query` or `evidence_overview`.
4. Re-check quotes with `evidence_verify`.
5. Export with `evidence_export` or build a collection with `email_dossier`.

### Administration

`email_admin` accepts these actions:

- `diagnostics`
- `reingest_bodies` with `olm_path`
- `reembed`
- `reingest_metadata` with `olm_path`
- `reingest_analytics`

Diagnostics reports resolved runtime settings, model/backend state, vector and
sparse-index status, MCP response budgets, and available QA-readiness metrics.

## Write and privacy boundaries

Tools that ingest, mutate evidence, rebuild indexes, or write exports are
explicit write operations. Output paths must remain inside configured
allowlisted local roots and may not overwrite existing files.

EWS reads and writes default to disabled. Remote reads require both account
enablement and `EWS_READ_ENABLED=true`; writes additionally require account
write enablement and `EWS_WRITE_ENABLED=true`. Attachment content has its own
explicit process gate. SOAP bodies, credentials, and synchronization watermarks
are not returned in tool responses or diagnostics.

`email_report(type="archive")` supports the privacy modes documented in
[PRIVACY_AND_REDACTION.md](PRIVACY_AND_REDACTION.md). Redaction is heuristic;
review every output before sharing it.
