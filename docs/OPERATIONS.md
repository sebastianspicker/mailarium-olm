# Operations and configuration

This is the operator source of truth for runtime paths, configuration
precedence, ingestion maintenance, recovery boundaries, EWS readiness, and
troubleshooting. Run commands from the repository root unless noted otherwise.

## Configuration sources and precedence

All Mailarium-owned settings and their defaults are defined in
`mailarium/platform/settings.py`. The CLI, ingestion entry point, and MCP
server load `.env` when they start (inside their `main()` functions), without
replacing variables already present in the process. Streamlit does not load `.env`; it
uses the launch environment and optional validated path overrides entered in
its sidebar.

For the entry points that load `.env`, effective settings resolve in this
order:

1. an explicit process environment value;
2. the corresponding value loaded from `.env`;
3. the selected `RUNTIME_PROFILE` or `MCP_MODEL_PROFILE` default; and
4. the application default in `mailarium/platform/settings.py`.

Field-specific environment variables override profile values. The tracked
`.env.example` is the starting template, not a record of the effective
runtime. Use ingestion startup logs or MCP
`email_admin(action="diagnostics")` to inspect resolved model, device, batch,
retrieval-stage, and profile settings.

For Streamlit, export the required variables first or provide them in the
launch command:

```bash
VECTOR_INDEX_PATH=private/runtime/current/vector-index \
SQLITE_PATH=private/runtime/current/email_metadata.db \
python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1
```

## Runtime data and paths

Use this layout in a source checkout:

```text
private/
├── ingest/archive.olm
├── runtime/current/email_metadata.db
├── runtime/current/vector-index/
└── exports/
```

`SQLITE_PATH` selects the canonical SQLite archive.
`VECTOR_INDEX_PATH` selects derived index files. Relative source-checkout
paths resolve below the repository root and must remain in an allowed runtime
root.

An installed package resolves relative runtime data below the operating
system's per-user data directory. Set an absolute `MAILARIUM_RUNTIME_HOME` to
override that base. Additional roots must also be absolute:

- `MAILARIUM_ALLOWED_RUNTIME_ROOTS` for databases and indexes;
- `MAILARIUM_ALLOWED_LOCAL_READ_ROOTS` for local inputs; and
- `MAILARIUM_ALLOWED_OUTPUT_ROOTS` for exports.

In a source checkout, configured roots extend the built-in `private/` and
`data/` roots. For installed runtime storage, configured runtime roots extend
`MAILARIUM_RUNTIME_HOME`. An installed operator should configure explicit
absolute local-read and output roots before using file import or export tools.
No override disables path validation. Output creation rejects paths outside the
allowlist and does not overwrite existing files.

## First and incremental ingestion

Begin with a bounded run:

```bash
mailarium-ingest private/ingest/archive.olm --max-emails 200
```

After checking the resulting archive, run a complete or incremental ingest:

```bash
mailarium-ingest private/ingest/archive.olm
mailarium-ingest private/ingest/archive.olm --incremental
```

`--incremental` skips source records already committed to SQLite. Attachment
and entity extraction are optional ingest stages; see
[attachment support](ATTACHMENT_SUPPORT.md) before enabling rich-format parsing
or OCR.

## Offline operation

Pre-seed required Hugging Face and spaCy models before disconnecting the
machine. Set both spaCy controls to prevent an ingestion-triggered model
download:

```dotenv
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
SPACY_AUTO_DOWNLOAD_DURING_INGEST=0
SPACY_AUTO_DOWNLOAD=0
```

`SPACY_AUTO_DOWNLOAD_DURING_INGEST=0` prevents ingestion from initiating the
download path when models are absent. `SPACY_AUTO_DOWNLOAD=0` prevents the
downloader from fetching models if it is invoked. When spaCy models are
unavailable, entity extraction falls back to the built-in regex extractor.
Local-only embedding mode fails if required embedding or reranking weights are
absent.

See [runtime tuning](RUNTIME_TUNING.md) for profiles, pinned model identities,
devices, retrieval stages, and performance controls.

## Index maintenance and recovery

SQLite remains canonical during index maintenance. Retain the original `.olm`
and take a consistent SQLite backup before resetting or reconstructing derived
state.

```bash
mailarium-ingest private/ingest/archive.olm --reembed --resume
mailarium admin reset-index --yes
```

`--reembed --resume` reconstructs vector state from stored corrected text
while retaining matching committed vectors. `reset-index` removes derived
vector state for the configured runtime; confirm the resolved paths before
accepting it.

Analytics backfills read at most 256 candidate messages per page and aggregate
their attachment and segment surfaces together. Completed pages remain durable
if the job stops; running the backfill again selects records still missing
analytics.

For a fully clean source-checkout ingestion reset, inspect the destructive
repository helper first:

```bash
bash scripts/ops/clean_ingest_reset.sh --dry-run
bash scripts/ops/clean_ingest_reset.sh --yes
```

The helper preserves `private/files/`, `private/context.md`,
`private/ingest/`, and `private/README.local.md`. It deletes listed runtime
stores, ledgers, run history, stale `data/` databases and indexes, and common
workspace caches. The dry run is the required way to confirm the exact
candidate paths before using `--yes`.

The repository does not automate backup, restore, retention, encryption at
rest, or disaster recovery. Copy the original archive and a quiescent SQLite
database with operating-system tools appropriate to the storage environment.
After restoration, rebuild derived indexes and verify important records against
the original source.

## EWS operation

EWS is optional and disabled by default. Account configuration stores an HTTPS
endpoint, authentication mode, selected folders, and a credential reference.
Credential values remain in the named environment variables.

Run a local readiness check before network activity:

```bash
mailarium mailbox readiness --account ACCOUNT_ID
```

Readiness validates local configuration and credential references without
performing network I/O. Remote reads require both account read enablement and
`EWS_READ_ENABLED=true`. Writes require account write enablement and
`EWS_WRITE_ENABLED=true`. Attachment bodies additionally require
`EWS_ATTACHMENT_CONTENT_ENABLED=true` and the sync
`--include-attachment-content` option.

Set bounded EWS limits in the process environment when the defaults are not
appropriate:

- `EWS_MAX_SYNC_ITEMS`;
- `EWS_MAX_ATTACHMENT_BYTES`;
- `EWS_MAX_ATTACHMENTS_PER_ITEM`;
- `EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_ITEM`;
- `EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_SYNC`; and
- `EWS_REQUEST_TIMEOUT_SECONDS`.

Use the local interactive CLI to approve or reject proposals. MCP may inspect
and execute an already approved proposal, but cannot approve one. See the
[CLI reference](CLI_REFERENCE.md) for account, sync, triage, proposal, and
reconciliation commands.

## Backup and disclosure checks

Back up at least:

- the original `.olm` or other controlled source;
- the SQLite database; and
- the effective non-secret configuration needed to reconstruct the runtime.

Derived indexes may be rebuilt and do not replace those backups. Exports,
SQLite files, indexes, and logs can contain mailbox data. Keep them under
private storage, review them before sharing, and apply the
[privacy and redaction](PRIVACY_AND_REDACTION.md) guidance.

## Troubleshooting

- **No indexed messages:** confirm the `.olm` path is readable and the
  configured SQLite and vector paths are writable. Retry with
  `--max-emails 200`.
- **MCP cannot start:** use the intended environment interpreter, confirm the
  resolved absolute paths, and check whether another live MCP process holds the
  archive lock. Stale process locks are detected during startup.
- **Search or model loading fails:** inspect
  `email_admin(action="diagnostics")`, then check the runtime profile, model
  identity and revision, load mode, device, and derived-index state.
- **Entity extraction tries to use the network:** set both spaCy no-download
  controls shown above and confirm the effective environment before ingestion.
- **EWS readiness fails:** correct local account configuration, the HTTPS
  endpoint, selected folders, credential references, and process gates before
  attempting a sync.
- **PDF export returns HTML:** HTML is the baseline export. Install and verify
  WeasyPrint in the active environment before relying on PDF output.
- **An export path is rejected:** use an absolute path inside
  `MAILARIUM_ALLOWED_OUTPUT_ROOTS` or a source-checkout path below
  `private/`; choose a path that does not already exist.

Local checks cannot establish live EWS interoperability, model-download
availability, manual browser behavior, remote deployment, or publication.
