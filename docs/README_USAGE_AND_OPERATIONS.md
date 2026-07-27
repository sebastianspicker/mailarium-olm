# Usage and Operations

## Runtime layout

For a source checkout, keep live data under the ignored `private/` directory:

```text
private/
├── ingest/
│   └── archive.olm
├── runtime/
│   └── current/
│       ├── vector-index/
│       └── email_metadata.db
└── exports/
```

Recommended starting configuration:

```bash
VECTOR_INDEX_PATH=private/runtime/current/vector-index
SQLITE_PATH=private/runtime/current/email_metadata.db
RUNTIME_PROFILE=quality
EMBEDDING_LOAD_MODE=auto
```

In an installed wheel, relative runtime paths resolve below the per-user runtime
home instead of `site-packages`:

- macOS: `~/Library/Application Support/mailarium`
- Windows: `%LOCALAPPDATA%/mailarium`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/mailarium`

Set `MAILARIUM_RUNTIME_HOME` to an absolute user-writable path to override that
location.

Output paths use a separate allowlist. In an installed package, configure an
absolute writable export directory and pass absolute output paths:

```bash
export MAILARIUM_ALLOWED_OUTPUT_ROOTS=/absolute/path/to/mailarium-exports
mailarium export report --output /absolute/path/to/mailarium-exports/report.html
```

### Migrating a pre-0.5 installed runtime

There is no automatic migration or old-path fallback. Stop every process using
the archive, copy the complete former `outlook-email-rag` runtime directory to
the corresponding `mailarium` location, and keep the original as a backup.
Start Mailarium and verify archive statistics, a known search, and configured
paths before archiving or removing that backup.

| Platform | Former default | Mailarium default |
| --- | --- | --- |
| macOS | `~/Library/Application Support/outlook-email-rag` | `~/Library/Application Support/mailarium` |
| Windows | `%LOCALAPPDATA%/outlook-email-rag` | `%LOCALAPPDATA%/mailarium` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/outlook-email-rag` | `${XDG_DATA_HOME:-~/.local/share}/mailarium` |

Rename explicit product variables as follows; a supplied removed name fails
with an actionable error:

| Removed variable | Replacement |
| --- | --- |
| `EMAIL_RAG_RUNTIME_HOME` | `MAILARIUM_RUNTIME_HOME` |
| `EMAIL_RAG_ALLOWED_OUTPUT_ROOTS` | `MAILARIUM_ALLOWED_OUTPUT_ROOTS` |
| `EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS` | `MAILARIUM_ALLOWED_LOCAL_READ_ROOTS` |
| `EMAIL_RAG_ALLOWED_RUNTIME_ROOTS` | `MAILARIUM_ALLOWED_RUNTIME_ROOTS` |

Source-checkout relative paths continue to resolve from the checkout root.

## Ingest

Ingestion is a separate entry point; it is not a `mailarium` subcommand:

```bash
mailarium-ingest private/ingest/archive.olm
# source-checkout equivalent
python -m mailarium.ingest private/ingest/archive.olm
```

For a bounded first pass:

```bash
python -m mailarium.ingest private/ingest/archive.olm --max-emails 200
```

Re-running ingest is idempotent for already-indexed messages.

## Use the interfaces

CLI:

```bash
mailarium analytics stats
mailarium search "project handoff" --scope customer-support --hybrid
```

MCP server:

```bash
.venv/bin/python -m mailarium.mcp_server
```

Streamlit from a source checkout:

```bash
python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1
```

Streamlit and MCP are intended for a trusted local operator. This alpha does not
provide authentication for public or shared deployment.

## Storage and maintenance

SQLite is canonical for messages, metadata, vectors, sparse weights, and
provenance. The vector-index directory contains rebuildable USearch
acceleration.

Supported CLI administration is intentionally narrow:

```bash
mailarium admin reset-index --yes
```

That command resets the derived vector collection. Preview any broader local
reset with `bash scripts/clean_ingest_reset.sh --dry-run`.

MCP exposes additional maintenance through `email_admin`:

- `action="diagnostics"`
- `action="reingest_bodies"` with `olm_path`
- `action="reembed"`
- `action="reingest_metadata"` with `olm_path`
- `action="reingest_analytics"`

These are MCP tool actions, not CLI subcommands.

## Retrieval behavior

`RAG_SCOPE=general` is the process default. A request can supply a narrower
scope through CLI `--scope`, an MCP `scope` field, or the Streamlit
`Retrieval Scope` input. Scope is explicit user context and is not inferred
from the query.

Hybrid retrieval and reranking are runtime choices. The system does not train
on mailbox queries or content.

## Offline operation

Use:

```bash
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
SPACY_AUTO_DOWNLOAD_DURING_INGEST=0
```

Local-only mode fails fast when required embedding or reranking weights are
absent. The spaCy setting separately prevents entity extraction from invoking
its model downloader. Pre-seed both model stores before disconnecting the
machine.

## Troubleshooting

### No emails indexed

- Confirm the `.olm` path exists and is readable.
- Run a bounded ingest and inspect the error before starting a full archive.
- Check that `SQLITE_PATH` and `VECTOR_INDEX_PATH` resolve to writable
  locations.

### MCP client is disconnected

- Use an absolute Python path and repository working directory in the client
  configuration.
- Confirm dependencies are installed in that interpreter.
- Run `.venv/bin/python -m mailarium.mcp_server --version` manually.

### Search or model loading fails

- Run `email_admin(action="diagnostics")`.
- Check the resolved runtime profile, load mode, device, model revisions, and
  index state.
- In offline mode, confirm the pinned models exist in the local cache.

### PDF output is unavailable

HTML is the supported export baseline. PDF output requires WeasyPrint and falls
back to HTML when it is absent:

```bash
python -m pip install weasyprint
weasyprint --version
```

Inspect the returned output path and format before sharing.

## Go-live checklist

1. Keep the original `.olm` archive as the recovery source.
2. Confirm runtime paths are below ignored `private/` or an explicit runtime
   home.
3. For installed operation, configure an absolute allowed output root.
4. Run diagnostics and a small set of known-answer searches.
5. Verify important results against the original messages and attachments.
6. Review every export for sensitive content.
7. Back up SQLite and the original archive; USearch acceleration can be rebuilt.
