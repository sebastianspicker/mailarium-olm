# CLI Reference

The command-line interface is a standalone way to search and analyze your email archive directly from Terminal. It doesn't require any MCP client — it works entirely on its own.

See [README.md](../README.md) for setup and [README.md](README.md) in this directory for the public docs map. Use the CLI for the full legal-support workflow surface; the Streamlit app is intentionally narrower and exploratory.

## When To Use The CLI

Use the CLI when you want:

- explicit local commands and saved output files
- repeatable operator workflows and shell history
- runtime diagnostics, cleanup, export, and maintenance steps
- local campaign/case execution without depending on an MCP client

Best-practice note:

- Prefer the CLI for authoritative local workflows.
- Prefer MCP when an assistant should orchestrate the search/tool selection.
- Keep Streamlit for exploration, not for final counsel-ready output.

## Starting the CLI

Make sure the virtual environment is active first:

```bash
source .venv/bin/activate
```

If you installed the package with `pip install -e .`, the packaged entry points are also available:

```bash
email-rag --help
email-rag-ingest --help
```

`python -m src.cli --help` shows the same modern subcommand interface. The older flat-flag form still works for compatibility, but new usage should prefer subcommands.

## Subcommands (recommended)

The modern subcommand syntax is the primary interface. Root-level flags such as `--log-level` and `--chromadb-path` can appear before or after the subcommand.

```bash
# Search
python -m src.cli search "Q3 budget" --sender finance
python -m src.cli search --query "contract renewal" --date-from 2024-01-01 --rerank
python -m src.cli --log-level INFO search "Q3 budget"

# Browse
python -m src.cli browse --folder Inbox --page 2 --page-size 30

# Export
python -m src.cli export thread CONV_ID --format pdf --output private/exports/thread.pdf
python -m src.cli export email UID --output private/exports/email.html
python -m src.cli export report --output private/exports/report.html
python -m src.cli export network --output private/exports/network.graphml

# Evidence
python -m src.cli evidence list --category discrimination --min-relevance 4
python -m src.cli evidence export private/exports/evidence_report.html --format html
python -m src.cli evidence stats
python -m src.cli evidence verify
python -m src.cli evidence dossier private/exports/dossier.html --format pdf
python -m src.cli evidence custody
python -m src.cli evidence provenance UID

# Analytics
python -m src.cli analytics stats
python -m src.cli analytics senders 20
python -m src.cli analytics contacts role@example.test
python -m src.cli analytics volume month
python -m src.cli analytics entities --type organization
python -m src.cli analytics heatmap
python -m src.cli analytics response-times

# Training
python -m src.cli training generate-data triplets.jsonl
python -m src.cli training fine-tune triplets.jsonl --epochs 5

# Admin
python -m src.cli admin reset-index --yes
```

Run `python -m src.cli <subcommand> --help` for subcommand-specific help.

## Dedicated workplace case analysis

Authority note:

- `case execute-wave`, `case execute-all-waves`, and `case gather-evidence` share the campaign execution contract with the MCP `email_case_*` campaign tools
- those wave commands now mark themselves as `execution_authority.status = shared_campaign_execution_surface`
- exploratory intake, full-pack drafting, and dedicated legal-support products remain governed by the MCP `email_case_*` analytical surface

Use `case analyze` when you need a structured workplace-review payload rather than a normal mailbox search result.

```bash
python -m src.cli case prompt-preflight --input matter.md --output preflight.json
python -m src.cli case analyze --input case.json --output case-analysis.json
python -m src.cli case execute-wave --input case.json --wave wave_1 --scan-id-prefix matter-2026-04 --output wave-1.json
python -m src.cli case execute-all-waves --input case.json --scan-id-prefix matter-2026-04 --output all-waves.json
python -m src.cli case gather-evidence --input case.json --run-id investigation_2026-04-16_P60 --phase-id P60 --scan-id-prefix matter-2026-04 --output evidence-harvest.json
python -m src.cli case full-pack --prompt matter.md --materials-dir ./matter --output handoff.bundle
python -m src.cli case counsel-pack --case-scope scope.json --materials-dir ./matter --output handoff.zip
```

Use `case execute-wave` when you want one documented wave to run as a real local workflow instead of a manual checklist. The command validates the case input, derives German-first query lanes for the selected wave, runs archive harvest before compact synthesis, and records `wave_execution`, `archive_harvest`, the effective query lanes, the canonical wave-level `scan_id`, and `wave_local_views` in the output JSON. This is now the same shared campaign workflow exposed through the MCP `email_case_execute_wave` tool.

Use `case execute-all-waves` when you want the full wave sequence executed locally with a machine-readable summary. Add `--include-payloads` if you need every per-wave payload instead of only the summary rows. The summary now exposes per-wave `scan_id` values, archive-harvest status, and `wave_local_views` counts so lane state, coverage, and wave-local differentiation stay auditable. This is the CLI entrypoint for the same shared campaign workflow exposed through `email_case_execute_all_waves`.

Use `case gather-evidence` when archive harvest must become durable evidence collection instead of only a transient analysis input. The command runs every documented wave, harvests each wave immediately as it completes, writes harvested body and attachment candidates into the SQLite `evidence_candidates` table, and auto-promotes exact verified body quotes into `evidence_items`. This is the CLI entrypoint for the same shared evidence-harvest workflow exposed through `email_case_gather_evidence`.

Use `case prompt-preflight` when the operator starts with a long natural-language matter description instead of structured JSON. The output is a conservative scaffold, not a free-form legal analysis. It reports:

- `draft_case_scope`
- `draft_case_analysis_input`
- `missing_required_inputs`
- `recommended_next_inputs`
- `prompt_limits`

Example:

```bash
python -m src.cli case prompt-preflight --input matter.md --output preflight.json --output-language de
```

Best-practice follow-up:

```bash
python scripts/prepare_case_inputs.py \
  --preflight preflight.json \
  --case-json-out case.json
```

That helper strips prompt-preflight helper keys such as `extraction_basis` and `date_confidence` before you start curating a reusable strict `case.json` for `case analyze`, `case execute-wave`, `case execute-all-waves`, or `case gather-evidence`. It also normalizes the human-facing top-level preflight mirrors back into the canonical machine payload so curated edits in `draft_case_scope`, `recommended_source_scope`, or top-level `matter_factual_context` are carried into the generated `case.json`.

When the prompt contains heading-based factual matter sections, prompt preflight also preserves them in `matter_factual_context`. It now also extracts bounded structured `context_people` and `institutional_actors` when the prompt explicitly lists natural persons, functional actors, shared mailboxes, or distribution surfaces. `scripts/prepare_case_inputs.py` carries those fields into `case.json`, but it still does not auto-confirm `trigger_events`, `alleged_adverse_actions`, or comparator facts. Unknown human email addresses may still remain `null` when the prompt does not explicitly supply them.

Use `case full-pack` when the operator has:

- a long natural-language matter prompt
- a directory of supplied matter files
- no finalized structured `case_scope` yet

The command now:

- runs prompt preflight
- builds a conservative `matter_manifest` from `--materials-dir`
- applies optional JSON overrides
- stops with explicit blockers when required structured fields are still missing
- emits `intake_compilation.override_suggestions` so blocked runs are repairable with minimal JSON overrides
- otherwise runs the downstream exhaustive legal-support workflow
- optionally writes an export artifact when `--output` is provided

Example:

```bash
python -m src.cli case full-pack \
  --prompt matter.md \
  --materials-dir ./matter \
  --overrides overrides.json \
  --output handoff.bundle \
  --output-language de \
  --translation-mode translation_aware
```

Use `--compile-only` when you want the blocker-or-ready payload without running the downstream exhaustive workflow yet.

If you curated a strict `case.json` for `case gather-evidence`, keep the full-pack lane aligned by generating matching overrides from that curated file:

```bash
python scripts/prepare_case_inputs.py \
  --case-json case.json \
  --overrides-out full_pack_overrides.json

python -m src.cli case full-pack \
  --prompt matter.md \
  --materials-dir ./matter \
  --overrides full_pack_overrides.json \
  --compile-only
```

Do not curate one structured case input for evidence harvest and then drop back to `case full-pack` from the raw prompt alone unless you intentionally want to discard those repairs.

The case input should stay bounded and structured. At minimum include:

- `target_person`
- `allegation_focus`
- `analysis_goal`
- `date_from`
- `date_to`

Recommended fields depend on what you are asking:

- add `trigger_events` for retaliation review
- add `comparator_actors` for unequal-treatment or discrimination-style review
- add `org_context` for bossing, mobbing, abuse-of-authority, or other power-heavy review
- add `context_notes` when the record needs neutral background facts to be interpreted fairly
- add `suspected_actors` when you want the output to stay focused on named actors instead of broad workplace dynamics
- add `institutional_actors` when shared mailboxes, distribution lists, workflow surfaces, or system routes matter for notice, routing, or institutional-knowledge review

Operator intake examples:

Retaliation review:

```json
{
  "case_scope": {
    "target_person": {"name": "employee", "email": "employee@example.test"},
    "suspected_actors": [{"name": "manager", "email": "manager@example.test", "role_hint": "manager"}],
    "allegation_focus": ["retaliation"],
    "analysis_goal": "hr_review",
    "trigger_events": [
      {
        "trigger_type": "complaint",
        "date": "2025-03-01",
        "notes": "Formelle Beschwerde der Zielperson."
      }
    ],
    "context_notes": "Teamkonflikt nach Eskalation zu Arbeitslast und Fristen.",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30"
  },
  "source_scope": "emails_and_attachments"
}
```

Unequal-treatment or discrimination-style review:

```json
{
  "case_scope": {
    "target_person": {"name": "employee", "email": "employee@example.test"},
    "suspected_actors": [{"name": "manager", "email": "manager@example.test", "role_hint": "manager"}],
    "comparator_actors": [{"name": "comparison employee", "email": "comparator@example.test", "role_hint": "employee"}],
    "allegation_focus": ["unequal_treatment", "discrimination"],
    "analysis_goal": "lawyer_briefing",
    "org_context": {
      "reporting_lines": [
        {
          "manager": {"name": "manager", "email": "manager@example.test"},
          "report": {"name": "employee", "email": "employee@example.test"},
          "source": "operator"
        }
      ]
    },
    "context_notes": "Beide Personen hatten vergleichbare Aufgaben im selben Prozessschritt.",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30"
  },
  "source_scope": "emails_and_attachments"
}
```

Mobbing or bossing-style review:

```json
{
  "case_scope": {
    "target_person": {"name": "employee", "email": "employee@example.test"},
    "suspected_actors": [{"name": "manager", "email": "manager@example.test", "role_hint": "manager"}],
    "allegation_focus": ["mobbing", "abuse_of_authority", "exclusion"],
    "analysis_goal": "formal_complaint",
    "org_context": {
      "role_facts": [
        {
          "person": {"name": "manager", "email": "manager@example.test"},
          "role_type": "manager",
          "title": "Team Lead",
          "source": "operator"
        }
      ]
    },
    "context_notes": "Prüfe wiederholte Ausgrenzung, öffentliche Korrektur und hierarchischen Druck im selben Zeitraum.",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30"
  },
  "source_scope": "emails_only"
}
```

Neutral chronology:

```json
{
  "case_scope": {
    "target_person": {"name": "employee", "email": "employee@example.test"},
    "allegation_focus": ["hostility", "exclusion"],
    "analysis_goal": "neutral_chronology",
    "context_notes": "Nur den Ablauf rekonstruieren, noch keine starke Einordnung erzwingen.",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30"
  },
  "source_scope": "emails_only"
}
```

Mixed-source case files require at least one native mixed-source input:

```json
{
  "case_scope": {
    "target_person": {"name": "employee", "email": "employee@example.test"},
    "allegation_focus": ["retaliation"],
    "analysis_goal": "internal_review",
    "date_from": "2025-01-01",
    "date_to": "2025-06-30"
  },
  "source_scope": "mixed_case_file",
  "chat_exports": [
    {
      "source_path": "/absolute/path/to/teams-export.html",
      "platform": "Teams",
      "title": "Teams export"
    }
  ]
}
```

Structured `chat_log_entries` are still supported as a compatibility override. Manifest-backed mixed-source artifacts also satisfy the mixed-source requirement when `matter_manifest.artifacts[*]` contains non-email supplied records such as `chat_export`, `calendar_export`, `meeting_note`, `time_record`, `attendance_export`, `participation_record`, `formal_document`, or `screenshot`.

## Counsel-pack workflow

Use `case counsel-pack` when the operator already has a bounded `case_scope` JSON file and a directory of supplied matter files:

```bash
python -m src.cli case counsel-pack \
  --case-scope scope.json \
  --materials-dir ./matter \
  --output handoff.zip \
  --delivery-target counsel_handoff_bundle \
  --delivery-format bundle
```

The command:

- builds a conservative `matter_manifest` from the materials directory
- forces manifest-backed `exhaustive_matter_review`
- routes chat-like files into mixed-source handling where possible
- writes a portable legal-support artifact through the shared exporter

Use `case counsel-pack` when the structured scope is already known and you want the final local export lane to use that curated scope directly instead of re-deriving it from the prompt.

This remains the correct local wrapper for dedicated legal-support deliverables and exporter checks. `case prompt-preflight` does not replace the manifest-backed exhaustive-review requirement for counsel-facing products, and CLI output still does not replace MCP-produced campaign-completion evidence.

Boundary:

- `autonomous internal completion` covers shared campaign execution plus current results-control state for internal analysis
- `human-gated counsel export` still requires the persisted snapshot review state to be `human_verified` or `export_approved`

`case full-pack` now bridges that gap for prompt-first operator workflows: it compiles the prompt into a strict manifest-backed exhaustive run, but it still refuses to invent missing trigger events, comparators, or other critical structured inputs.

The output includes machine-readable intake guidance so operators can see when the request is too weak for the claim they asked about:

- `case_scope_quality.warnings`
- `case_scope_quality.recommended_next_inputs`
- `analysis_limits.scope_warnings`
- mirrored warning entries in `investigation_report.sections.missing_information`

Typical downgrade warnings include retaliation without triggers, comparator-based review without comparators, power-heavy review without org context, and high-stakes review without neutral context notes.

## Local investigation-results workspace helpers

Use the supported CLI helpers instead of hand-editing `private/tests/results/active_run.json` or manually moving superseded files:

```bash
python -m src.cli case refresh-active-run \
  --matter-id matter:current_email_matter \
  --run-id investigation_2026-04-16_P32 \
  --phase-id P32 \
  --active-checkpoint _checkpoints/investigation_2026-04-16_P32_higher_quality_run.md \
  --active-result-path 03_exhaustive_run/investigation_2026-04-16_P30_case_analysis_higher_quality.json \
  --active-result-path 03_exhaustive_run/investigation_2026-04-16_P32_higher_quality_run.md \
  --question-register-path 11_memo_draft_dashboard/question_register.md \
  --open-tasks-companion-path 11_memo_draft_dashboard/open_tasks_companion.md
```

Archive superseded local outputs through the paired helper:

```bash
python -m src.cli case archive-results \
  --archive-label superseded_run \
  --path 03_exhaustive_run/investigation_2026-04-16_P30_case_analysis_higher_quality.json
```

## Interactive mode

Run without arguments to enter an interactive search loop:

```bash
python -m src.cli
```

You'll see a summary of your archive and a search prompt:

```
+-------------- Email RAG ---------------+
| Emails: 1842 | Chunks: 4210 |          |
| Senders: 312 | Range: 2023-01 -> 2024  |
| Type 'quit' to exit, 'stats', ...      |
+-----------------------------------------+

Search: _
```

Type a query, press Enter, and you get a table of results. Type `stats` for archive statistics, `senders` for the top sender list, or `quit` to exit.

## Single query mode

For one-off searches, use the `search` subcommand:

```bash
python -m src.cli search --query "Q3 budget approval"
```

Output shows each result with relevance score, sender, date, subject, and the matching text:

```
============================================================
Result 1 (relevance: 0.87)
Subject: Re: Q3 Budget Approval
Sender:  finance@example.test
Date:    2024-07-15
Folder:  Inbox

The Q3 budget has been approved with the following allocations...
(~180 tokens)
```

## Filtering results

Combine `search` with any filter flag to narrow results:

```bash
# By sender (partial match on name or email)
python -m src.cli search --query "contract renewal" --sender legal

# By date range (ISO format)
python -m src.cli search --query "invoice" \
    --date-from 2024-01-01 \
    --date-to 2024-06-30

# By recipient
python -m src.cli search --query "proposal" --to reviewer@example.test

# Only emails with attachments
python -m src.cli search --query "report" --has-attachments

# By folder (partial match)
python -m src.cli search --query "update" --folder "Sent Items"

# By CC recipient
python -m src.cli search --query "review" --cc manager@example.test

# By BCC recipient
python -m src.cli search --query "announcement" --bcc board@example.test

# By email type (reply, forward, or original)
python -m src.cli search --query "meeting notes" --email-type reply

# By minimum priority level
python -m src.cli search --query "urgent" --priority 3

# Combine multiple filters
python -m src.cli search --query "contract" \
    --sender legal \
    --date-from 2024-01-01 \
    --has-attachments \
    --min-score 0.5
```

## Search modes

Three search modes provide different trade-offs between speed and accuracy:

```bash
# Standard semantic search (default — fast)
python -m src.cli search --query "budget discussion"

# Hybrid: semantic + BM25 keyword search (better for exact terms)
python -m src.cli search --query "invoice #INV-2024-0847" --hybrid

# With cross-encoder reranking (slower but most precise)
python -m src.cli search --query "budget discussion" --rerank

# Query expansion: auto-adds related terms
python -m src.cli search --query "security" --expand-query

# Combine all three
python -m src.cli search --query "infrastructure costs" --hybrid --rerank --expand-query

# Filter by cluster
python -m src.cli search --query "hiring" --cluster-id 3
```

`--topic` is still accepted for compatibility, but the default ingest workflow does not populate topic tables yet.

## Output format

```bash
# Human-readable text (default)
python -m src.cli search --query "budget" --format text

# Machine-readable JSON
python -m src.cli search --query "budget" --format json

# Legacy JSON shorthand
python -m src.cli search --query "budget" --json

# Control number of results (default: 10, max: 1000)
python -m src.cli search --query "budget" --top-k 20
```

## Analytics commands

These don't require a query — they analyze your entire archive:

```bash
# Archive statistics (total emails, chunks, senders, date range)
python -m src.cli analytics stats

# Top senders (show top 20)
python -m src.cli analytics senders 20

# Top contacts for a specific email address
python -m src.cli analytics contacts role@example.test

# Email volume over time
python -m src.cli analytics volume day     # daily
python -m src.cli analytics volume week    # weekly
python -m src.cli analytics volume month   # monthly

# Activity heatmap (hour x day-of-week)
python -m src.cli analytics heatmap

# Recent-sample response times per sender (canonical reply pairs)
python -m src.cli analytics response-times

# Most frequently mentioned entities (organizations, URLs, etc.)
python -m src.cli analytics entities
python -m src.cli analytics entities --type organization   # filter by type

# Search suggestions based on your data
python -m src.cli analytics suggest
```

## Topics commands

Build NMF topic models and TF-IDF KMeans cluster assignments for your archive. Requires scikit-learn. Run once after ingestion; re-run after significant archive changes.

```bash
# Build topics (NMF) and clusters (KMeans) with defaults
python -m src.cli topics build

# Tune number of topics and clusters
python -m src.cli topics build --n-topics 20 --n-clusters 15

# Build only topics (skip clustering)
python -m src.cli topics build --skip-clusters

# Build only clusters (skip topic modelling)
python -m src.cli topics build --skip-topics
```

After running `topics build`, the `email_topics` and `email_clusters` MCP tools serve real data. Before running it, those tools return a guidance message directing you here.

## Browsing emails

Browse your archive page by page for systematic review:

```bash
# Browse newest emails (default: 20 per page)
python -m src.cli browse

# Navigate pages
python -m src.cli browse --page 3 --page-size 10

# Filter by folder or sender
python -m src.cli browse --folder Inbox
python -m src.cli browse --sender legal@example.test
```

## Exporting emails

Export conversation threads or individual emails as formatted HTML (or PDF with weasyprint):

```bash
# Export a conversation thread by conversation ID
python -m src.cli export thread conv_abc123

# Export a single email by UID
python -m src.cli export email uid_xyz789

# Choose format (html or pdf) and output path
python -m src.cli export thread conv_abc123 --format pdf --output thread.pdf
python -m src.cli export email uid_xyz789 --output email.html
```

> **PDF support** requires `weasyprint`: `pip install weasyprint`. Without it, export falls back to HTML automatically.

For MCP parity: the `email_export` tool enforces allowlisted write roots for output paths; extend those roots explicitly with `EMAIL_RAG_ALLOWED_OUTPUT_ROOTS` when needed.

## Evidence management

List, export, and verify evidence items collected through the MCP tools:

```bash
# List all evidence items
python -m src.cli evidence list

# Filter by category or minimum relevance
python -m src.cli evidence list --category discrimination
python -m src.cli evidence list --min-relevance 4

# Export evidence report (HTML by default)
python -m src.cli evidence export private/exports/evidence_report.html

# Export as CSV (for Excel)
python -m src.cli evidence export private/exports/evidence.csv --format csv

# Get evidence statistics (counts by category, verified vs unverified)
python -m src.cli evidence stats

# Re-verify all evidence quotes against source emails
python -m src.cli evidence verify
```

## Reporting commands

```bash
# Generate an HTML report (default: private/exports/report.html)
python -m src.cli export report
python -m src.cli export report --output private/exports/archive_report.html

# Export communication network as GraphML
python -m src.cli export network
python -m src.cli export network --output private/exports/archive_network.graphml
```

## Index management

```bash
# Delete and recreate the index (requires --yes)
python -m src.cli admin reset-index --yes
```

## Legacy Flat-Flag Reference

The commands below still work for compatibility, but they are deprecated. Prefer the subcommand forms documented above for new usage.

| Flag | Type | Description |
|------|------|-------------|
| `--query`, `-q` | string | Search query (required for search mode) |
| `--top-k` | int | Number of results (default: 10, max: 1000) |
| `--sender` | string | Filter by sender (partial match on name or email) |
| `--subject` | string | Filter by subject (partial match) |
| `--folder` | string | Filter by folder (partial match) |
| `--cc` | string | Filter by CC recipient (partial match) |
| `--to` | string | Filter by To recipient (partial match) |
| `--bcc` | string | Filter by BCC recipient (partial match) |
| `--has-attachments` | flag | Only emails with attachments |
| `--priority` | int | Minimum priority level |
| `--email-type` | choice | `reply`, `forward`, or `original` |
| `--date-from` | YYYY-MM-DD | Start date (inclusive) |
| `--date-to` | YYYY-MM-DD | End date (inclusive) |
| `--min-score` | float | Minimum relevance score (0.0–1.0) |
| `--rerank` | flag | Re-rank with cross-encoder |
| `--hybrid` | flag | Hybrid semantic + BM25 search |
| `--expand-query` | flag | Expand query with related terms |
| `--topic` | int | Filter by topic ID when topic tables were populated outside the default ingest workflow |
| `--cluster-id` | int | Filter by email cluster ID |
| `--format` | choice | Output format: `text` or `json` |
| `--json` | flag | Shorthand for `--format json` |
| `--stats` | flag | Print archive statistics |
| `--list-senders` | int | List top N senders |
| `--top-contacts` | string | Top contacts for an email address |
| `--volume` | choice | Email volume: `day`, `week`, or `month` |
| `--entities` | string? | List top entities (optionally by type) |
| `--heatmap` | flag | Activity heatmap |
| `--response-times` | flag | Response time statistics |
| `--suggest` | flag | Search suggestions |
| `--browse` | flag | Browse emails page by page |
| `--page` | int | Page number for `--browse` (default: 1) |
| `--page-size` | int | Emails per page for `--browse` (default: 20, max: 50) |
| `--export-thread` | string | Export a conversation thread by conversation ID |
| `--export-email` | string | Export a single email by UID |
| `--export-format` | choice | Export format: `html` or `pdf` (default: `html`) |
| `--output`, `-o` | string | Output file path for exports |
| `--generate-report` | string? | Generate HTML report (default: `private/exports/report.html`) |
| `--export-network` | string? | Export GraphML network (default: `private/exports/network.graphml`) |
| `--evidence-list` | flag | List all evidence items |
| `--evidence-export` | string | Export evidence report to file |
| `--evidence-export-format` | choice | Evidence export format: `html`, `csv`, or `pdf` (default: `html`) |
| `--evidence-stats` | flag | Show evidence collection statistics |
| `--evidence-verify` | flag | Re-verify all evidence quotes against source emails |
| `--category` | string | Filter evidence by category |
| `--min-relevance` | int | Filter evidence by minimum relevance (1-5) |
| `--dossier` | string | Generate proof dossier and write to file |
| `--dossier-format` | choice | Dossier format: `html` or `pdf` (default: `html`) |
| `--custody-chain` | flag | View chain-of-custody audit trail |
| `--provenance` | string | View email provenance by UID (OLM source hash, ingestion run, custody events) |
| `--generate-training-data` | string? | Generate contrastive triplets from threads (default: `training_data.jsonl`) |
| `--fine-tune` | string? | Fine-tune embedding model on generated triplets |
| `--fine-tune-output` | string | Output directory for fine-tuned model (default: `models/fine-tuned`) |
| `--fine-tune-epochs` | int | Number of fine-tuning epochs (default: 3) |
| `--reset-index` | flag | Delete and recreate the index (requires `--yes`) |
| `--yes` | flag | Confirm destructive operations |
| `--chromadb-path` | string | Override ChromaDB path |
| `--log-level` | string | Logging level (`DEBUG`, `INFO`, etc.) |
| `--version` | flag | Print version and exit |

## Ingestion CLI (`src.ingest`)

The ingestion CLI is a separate entry point for importing `.olm` email exports:

```bash
python -m src.ingest path/to/export.olm
```

MCP parity note: `email_ingest` ingests into the requested target paths but does not implicitly switch the active runtime archive used by later search tools.

### Ingestion flags

| Flag | Type | Description |
|------|------|-------------|
| `olm_path` | positional | Path to the `.olm` file to ingest (required) |
| `--chromadb-path` | string | Custom path for ChromaDB storage |
| `--sqlite-path` | string | Custom path for SQLite metadata database |
| `--batch-size` | int | Chunks per ingest write batch (default: 500) |
| `--max-emails` | int | Optional cap on the number of emails to parse |
| `--dry-run` | flag | Parse and chunk emails without writing embeddings to ChromaDB |
| `--incremental` | flag | Skip emails already present in SQLite (saves compute on re-runs) |
| `--extract-attachments` | flag | Extract and index text content from attachments (PDF, DOCX, XLSX, text) |
| `--embed-images` | flag | Embed image attachments (JPG, PNG, etc.) using Visualized-BGE-M3 |
| `--extract-entities` | flag | Extract entities (organizations, URLs, phones) and store in SQLite |
| `--reingest-bodies` | flag | Re-parse OLM to backfill body_text/body_html; with `--force`, also updates subjects and sender names |
| `--reingest-metadata` | flag | Re-parse OLM to backfill v7 metadata (categories, thread_topic, calendar, references, attachments) |
| `--reingest-analytics` | flag | Backfill language detection and sentiment analysis for emails missing analytics data |
| `--reembed` | flag | Re-chunk and re-embed all emails from corrected SQLite body text into ChromaDB |
| `--force` | flag | Force re-parse all emails (use with `--reingest-bodies` to overwrite existing data) |
| `--timing` | flag | Show per-phase timing breakdown (parse, embed, sqlite, entities, analytics) |
| `--reset-index` | flag | Delete ChromaDB collection and SQLite DB, then exit |
| `--yes` | flag | Confirm destructive operations (required for `--reset-index`) |
| `--log-level` | string | Logging level override (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Ingestion examples

```bash
# Basic ingestion
python -m src.ingest export.olm

# Incremental re-run with entity extraction
python -m src.ingest export.olm --incremental --extract-entities

# Full re-ingestion with attachments and images
python -m src.ingest export.olm --extract-attachments --embed-images --extract-entities

# OCR-sensitive evidence ingest for the active private runtime
export CHROMADB_PATH=private/runtime/current/chromadb
export SQLITE_PATH=private/runtime/current/email_metadata.db
export RUNTIME_PROFILE=quality
export EMBEDDING_LOAD_MODE=auto
export ATTACHMENT_OCR_LANG=deu+eng
export ATTACHMENT_PDF_OCR_MAX_PAGES=10
export ATTACHMENT_OCR_PSM=6
python -m src.ingest private/ingest/latest-export.olm \
  --chromadb-path "$CHROMADB_PATH" \
  --sqlite-path "$SQLITE_PATH" \
  --extract-attachments \
  --embed-images \
  --extract-entities \
  --timing

# Backfill analytics (language + sentiment) for existing emails
python -m src.ingest export.olm --reingest-analytics

# Re-embed after fixing body text
python -m src.ingest export.olm --reembed

# Dry run to see parsing stats without writing to ChromaDB
python -m src.ingest export.olm --dry-run --timing
```

Best-practice note:

- On a fresh successful ingest, `--reingest-analytics` and `--reextract-entities --force` are usually unnecessary.
- Reserve those backfill passes for older runtimes or post-fix repair runs.
- Use `--reprocess-degraded-attachments --force` only when degraded or scanned attachment recovery matters for the record.
