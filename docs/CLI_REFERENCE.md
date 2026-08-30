# CLI reference

Mailarium installs `mailarium` for archive operations and `mailarium-ingest`
for archive construction and maintenance. Use the active environment for the
authoritative command schema:

```bash
mailarium --help
mailarium-ingest --help
mailarium mailbox --help
```

The source-checkout forms are `python -m mailarium.cli` and
`python -m mailarium.ingest`.

## Archive operations

```bash
mailarium search "invoice from vendor" --sender billing@example.test --scope finance --hybrid
mailarium browse --page 1 --page-size 20 --folder Inbox
mailarium analytics stats
mailarium export report --output private/exports/report.html
mailarium evidence list --category decision --min-relevance 3
mailarium topics build --n-topics 20
```

The root command accepts `--vector-index-path`, `--sqlite-path`, and
`--log-level`. Search, output, and maintenance options are defined by each
subcommand. Output paths must stay in configured allowlisted roots and do not
overwrite existing files.

## Ingestion and maintenance

```bash
mailarium-ingest private/ingest/archive.olm --max-emails 200
mailarium-ingest private/ingest/archive.olm --incremental --extract-attachments --extract-entities
mailarium-ingest private/ingest/archive.olm --reembed --resume
mailarium admin reset-index --yes
```

`--reset-index` and `mailarium admin reset-index --yes` affect derived vector
state. Confirm the target paths before using them. SQLite remains canonical.

## EWS mailbox

EWS is optional and disabled by default. Configuration stores an HTTPS endpoint,
authentication mode, selected folders, and a reference to credential environment
variables, never the credential values themselves.

```bash
mailarium mailbox accounts configure \
  --account local-exchange \
  --mailbox mailbox@example.test \
  --endpoint https://exchange.example.test/EWS/Exchange.asmx \
  --auth ntlm \
  --credential-ref basic-env:EWS_USER:EWS_PASSWORD \
  --folder inbox \
  --read-enabled

mailarium mailbox readiness --account local-exchange
```

Remote reads require both account read enablement and `EWS_READ_ENABLED=true`.
Writes also require account write enablement and `EWS_WRITE_ENABLED=true`.
Attachment content additionally needs `EWS_ATTACHMENT_CONTENT_ENABLED=true` and
the sync `--include-attachment-content` flag. The process bounds are
`EWS_MAX_SYNC_ITEMS`, `EWS_MAX_ATTACHMENT_BYTES`,
`EWS_MAX_ATTACHMENTS_PER_ITEM`, `EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_ITEM`,
`EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_SYNC`, and
`EWS_REQUEST_TIMEOUT_SECONDS`.

```bash
export EWS_USER='external-runtime-value'
export EWS_PASSWORD='external-runtime-value'
export EWS_READ_ENABLED=true
mailarium mailbox sync --account local-exchange
mailarium mailbox triage --account local-exchange --create-proposals
mailarium mailbox proposals list --state pending
```

The local interactive CLI is the only approval and rejection surface. An
approved proposal can be executed only after `EWS_WRITE_ENABLED=true`; uncertain
outcomes are handled through `mailarium mailbox reconcile`. These commands do
not establish that a live EWS server is reachable or that a write succeeded.
