# Usage and operations

## Runtime data

In a source checkout, keep operator data under ignored `private/` paths:

```text
private/
├── ingest/archive.olm
├── runtime/current/email_metadata.db
├── runtime/current/vector-index/
└── exports/
```

Use `SQLITE_PATH` for the canonical SQLite archive and `VECTOR_INDEX_PATH` for
derived USearch files. An installed package resolves relative runtime data under
its platform user-data directory; set an absolute `MAILARIUM_RUNTIME_HOME` to
override it. For installed exports, configure an absolute
`MAILARIUM_ALLOWED_OUTPUT_ROOTS` and pass output paths inside it.

## Maintenance

Start with a bounded ingest. Re-running with `--incremental` skips records
already present in SQLite. `--reembed --resume` reconstructs vector state from
stored corrected text while retaining matching committed vectors.

```bash
mailarium-ingest private/ingest/archive.olm --max-emails 200
mailarium-ingest private/ingest/archive.olm --incremental
mailarium-ingest private/ingest/archive.olm --reembed --resume
```

Treat `--reset-index` and `mailarium admin reset-index --yes` as derived-index
maintenance. Confirm the archive paths first and retain the original `.olm` and
a SQLite backup.

## Offline operation

```bash
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
SPACY_AUTO_DOWNLOAD_DURING_INGEST=0
```

Local-only operation fails when required model files are absent. Pre-seed model
files before disconnecting the machine. This configuration does not verify a
model download path.

## EWS operation

Use `mailarium mailbox readiness --account ACCOUNT_ID` before any remote action.
It checks local configuration and credential references without performing
network I/O. Process and account read gates must both be enabled for reads;
writes need both write gates; attachment content needs its own process gate.
See [CLI_REFERENCE.md](CLI_REFERENCE.md) for commands and limits.

## Troubleshooting

- No indexed messages: confirm the `.olm` path is readable and the configured
  SQLite and vector paths are writable. Retry with `--max-emails 200`.
- MCP cannot start: use the intended environment interpreter and confirm no
  other MCP server holds the archive lock.
- Search or model loading fails: inspect `email_admin(action="diagnostics")`,
  then check runtime profile, load mode, device, model revisions, and index
  state.
- PDF export returns HTML: HTML is the baseline. Install and verify WeasyPrint
  in the active environment before relying on PDF output.

Back up the original archive and SQLite database. Rebuild USearch when needed,
then verify important results against original messages and attachments.
