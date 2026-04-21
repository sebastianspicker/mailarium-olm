# MCP Client Config Snippet

Use this snippet to connect an MCP-compatible client to this repo's MCP server
with the active private runtime corpus.

## Recommended Persistent Setup

For reliable follow-up sessions, use the MCP client's persistent server
configuration:

- `<mcp-client-config>`

Substitute:

- `<repo-root>` with the absolute path to this checkout
- `<mcp-client-config>` with the client's persistent config path on the local machine

Reason:

- the server should be declared once in the client configuration
- the active runtime path should stay stable across sessions
- repo docs alone do not make the server available in the next session

Recommended persistent block:

```toml
[mcp_servers.email_search]
command = "<repo-root>/.venv/bin/python"
args = [
  "-m",
  "src.mcp_server",
  "--chromadb-path",
  "private/runtime/current/chromadb",
  "--sqlite-path",
  "private/runtime/current/email_metadata.db",
]
cwd = "<repo-root>"
enabled = true
required = false
startup_timeout_sec = 30
tool_timeout_sec = 300
```

Path policy:

- the MCP client must point at the stable `private/runtime/current/` contract
- do not repoint the client config for every new run directory
- instead, update the `private/runtime/current` symlink when the active runtime changes

After adding or changing the server block, fully restart the MCP client so it
reloads the server definition.

Canonical server command:

```bash
<repo-root>/.venv/bin/python \
  -m src.mcp_server \
  --chromadb-path private/runtime/current/chromadb \
  --sqlite-path private/runtime/current/email_metadata.db
```

## Ready-To-Paste Config

```json
{
  "mcpServers": {
    "email_search": {
      "command": "<repo-root>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server",
        "--chromadb-path",
        "private/runtime/current/chromadb",
        "--sqlite-path",
        "private/runtime/current/email_metadata.db"
      ],
      "cwd": "<repo-root>"
    }
  }
}
```

## Environment-Variable Variant

Use this only if your MCP client supports an `env` block for MCP servers.

```json
{
  "mcpServers": {
    "email_search": {
      "command": "<repo-root>/.venv/bin/python",
      "args": [
        "-m",
        "src.mcp_server"
      ],
      "cwd": "<repo-root>",
      "env": {
        "CHROMADB_PATH": "private/runtime/current/chromadb",
        "SQLITE_PATH": "private/runtime/current/email_metadata.db"
      }
    }
  }
}
```

## Verification

Before relying on the client integration, verify the server starts cleanly:

```bash
cd <repo-root>
.venv/bin/python -m src.mcp_server \
  --chromadb-path private/runtime/current/chromadb \
  --sqlite-path private/runtime/current/email_metadata.db
```

If the client still does not see the tools:

1. confirm the config uses absolute paths
2. confirm the repo-local virtual environment exists
3. confirm the MCP client was fully restarted after editing its config
4. confirm no other `src.mcp_server` process is holding the runtime lock

## Expected MCP Tool Surface

Once connected, the MCP client should be able to call the repo's `email_*` MCP
tools needed for question-first execution, including:

- `email_stats`
- `email_admin`
- `email_search_structured`
- `email_triage`
- `email_scan`
- `email_thread_lookup`
- `email_find_similar`
- `email_deep_context`
- `email_attachments`
- `email_provenance`
- `evidence_add`
- `evidence_verify`
- `email_case_analysis_exploratory`
- `email_case_execute_wave`
- `email_case_execute_all_waves`
- `email_case_gather_evidence`

and the downstream legal-support product tools:

- `email_case_prompt_preflight`
- `email_case_full_pack`
- `email_case_evidence_index`
- `email_case_master_chronology`
- `email_case_comparator_matrix`
- `email_case_issue_matrix`
- `email_case_skeptical_review`
- `email_case_document_request_checklist`
- `email_case_actor_witness_map`
- `email_case_promise_contradictions`
- `email_case_lawyer_briefing_memo`
- `email_case_draft_preflight`
- `email_case_controlled_draft`
- `email_case_retaliation_timeline`
- `email_case_dashboard`

## Important Boundary

This config enables the MCP client to talk to the MCP server over stdio.

It is different from using the repository CLI directly:

- MCP path: MCP client -> `src.mcp_server` -> `email_*` tools
- CLI path: shell -> `python -m src.cli ...`

For the synthetic matter runbook:

- shared campaign execution may come from either the MCP path or the documented CLI `case execute-wave`, `case execute-all-waves`, and `case gather-evidence` wrappers
- dedicated `email_case_*` product refresh and counsel-facing export still belong to the MCP path
- local CLI wrappers are operator conveniences, not a replacement for the MCP-governed product surface
