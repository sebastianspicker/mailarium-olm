# CLI Reference

Mailarium installs two terminal entry points:

```bash
mailarium --help
mailarium-ingest --help
```

The equivalent source-checkout modules are `python -m mailarium.cli` and
`python -m mailarium.ingest`.

## Runtime flags

The `mailarium` root command and its subcommands accept:

- `--vector-index-path`
- `--sqlite-path`
- `--log-level`

Environment variables remain the simplest persistent configuration:

```bash
export VECTOR_INDEX_PATH=private/runtime/current/vector-index
export SQLITE_PATH=private/runtime/current/email_metadata.db
```

## Search

```bash
mailarium search "invoice from vendor" \
  --sender billing@example.test \
  --date-from 2026-01-01 \
  --scope finance \
  --hybrid \
  --rerank
```

Search supports sender, subject, folder, recipient, attachment, priority,
email-type, date, score, topic, and cluster filters. Use `--format json` for
machine-readable output. `--json` remains an alias.

## Browse

```bash
mailarium browse --page 1 --page-size 20 --folder Inbox
```

Page size is limited to 50.

## Export

```bash
mailarium export email UID --format html --output private/exports/email.html
mailarium export thread CONVERSATION_ID --format html \
  --output private/exports/thread.html
mailarium export report --output private/exports/report.html
mailarium export network --output private/exports/network.graphml
```

HTML is the supported baseline. PDF output requires the optional `weasyprint`
package and falls back to HTML when that package is absent:

```bash
python -m pip install weasyprint
weasyprint --version
```

## Evidence

```bash
mailarium evidence list --category decision --min-relevance 3
mailarium evidence stats
mailarium evidence verify
mailarium evidence provenance UID
mailarium evidence export private/exports/evidence.html --format html
mailarium evidence dossier private/exports/collection.html --format html
mailarium evidence custody
```

## Analytics

```bash
mailarium analytics stats
mailarium analytics senders 30
mailarium analytics suggest
mailarium analytics contacts analyst@example.test
mailarium analytics volume month
mailarium analytics entities --type organization
mailarium analytics heatmap
mailarium analytics response-times
```

## Topics and training

```bash
mailarium topics build --n-topics 20
mailarium training generate-data private/training/triplets.jsonl
mailarium training fine-tune private/training/triplets.jsonl \
  --output-dir private/models/fine-tuned \
  --epochs 3 \
  --mode dense
```

Topic tables are conditional: the default ingest path does not populate them
until `topics build` runs.

## Administration

The supported CLI administration command is:

```bash
mailarium admin reset-index --yes
```

Re-embedding and metadata/body backfills are available through the MCP
`email_admin` tool, not as CLI subcommands.

## EWS mailbox

From a source checkout, install the optional on-premises profile with
`python -m pip install -e '.[ews-ntlm]'`. For downloaded release assets, install
`'./mailarium-0.5.0a1-py3-none-any.whl[ews-ntlm]'` with the release's
`requirements.locked.txt` as a pip constraint. Configuration stores only
environment-variable names, never credential values:

```bash
mailarium mailbox accounts configure \
  --account local-exchange \
  --mailbox mailbox@example.test \
  --endpoint https://exchange.example.test/EWS/Exchange.asmx \
  --auth ntlm \
  --credential-ref basic-env:EWS_USER:EWS_PASSWORD \
  --folder inbox \
  --folder 'AAMk...opaque-folder-id...' \
  --read-enabled
mailarium mailbox accounts list
mailarium mailbox readiness --account local-exchange
```

Remote access is additionally process-gated:

Folder values are either EWS distinguished IDs such as `inbox`, `drafts`, and
`sentitems`, or opaque EWS FolderId values. Display names are not resolved
implicitly.

```bash
export EWS_USER='external-runtime-value'
export EWS_PASSWORD='external-runtime-value'
export EWS_READ_ENABLED=true
mailarium mailbox sync --account local-exchange
mailarium mailbox triage --account local-exchange --create-proposals
```

Attachment metadata is synchronized by default. Content requires both
`EWS_ATTACHMENT_CONTENT_ENABLED=true` and
`--include-attachment-content`, and remains subject to byte limits.
The bounded process controls are `EWS_MAX_SYNC_ITEMS`,
`EWS_MAX_ATTACHMENT_BYTES`, `EWS_MAX_ATTACHMENTS_PER_ITEM`,
`EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_ITEM`,
`EWS_MAX_ATTACHMENT_TOTAL_BYTES_PER_SYNC`, and
`EWS_REQUEST_TIMEOUT_SECONDS`.

Proposal inspection and human-only decisions:

```bash
mailarium mailbox proposals list --state pending
mailarium mailbox proposals show PROPOSAL_ID
mailarium mailbox approve PROPOSAL_ID
mailarium mailbox reject PROPOSAL_ID --reason 'not appropriate'
```

Approval requires an interactive terminal and the displayed proposal-ID
suffix. There is no non-interactive approval bypass. After approval:

```bash
export EWS_WRITE_ENABLED=true
mailarium mailbox execute PROPOSAL_ID
mailarium mailbox reconcile PROPOSAL_ID
```

The account must also have been configured with `--write-enabled`.

## Ingest

```bash
mailarium-ingest private/ingest/archive.olm
python -m mailarium.ingest private/ingest/archive.olm --max-emails 200
```

Run `mailarium <subcommand> --help` or `mailarium-ingest --help` for the exact
options in the installed candidate.
