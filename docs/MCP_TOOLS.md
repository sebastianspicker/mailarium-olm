# Email RAG — Full MCP Tool Reference

> This file is the detailed MCP tool reference for the built-in server.
>
> Start with [README.md](../README.md) for setup, [README.md](README.md) in this directory for the docs map, and use this file when you need the exact MCP surface and legal-support workflow boundaries.

## Best-Practice Use

- Use this document as a reference after the runtime is already configured.
- Use the CLI when you want deterministic local commands and shell-visible output.
- Use MCP when your assistant or MCP client should decide which tool to call.
- Keep a human approval boundary around destructive, exporting, or
  counsel-facing actions. The MCP tools specification treats model-controlled
  tool invocation as compatible with human-in-the-loop denial and confirmation.
- Review every export artifact before sharing it outside your local machine.
- Keep live data under `private/` and treat tracked `data/` as sanitized examples only.

## How to Search

Start broad, then narrow down:

- `email_search_structured` — the main search tool: semantic query + filters (sender, date, folder, to, cc, bcc, attachments, priority, topic, cluster, reranking, hybrid search, query expansion)
- `email_triage` — fast triage scan: ultra-compact results (uid, sender, date, subject, score, preview), up to 100 results. Issue 3-5 calls with different queries for pseudo-parallel scanning
- `email_answer_context` — assemble a question-to-evidence payload when you already know the question you need to answer
- `email_find_similar` — find emails similar to a known one (pattern discovery)
- `email_search_by_entity` — find emails mentioning an organization, URL, phone, or person name
- `email_thread_lookup` — retrieve all emails in a thread by conversation_id or thread_topic

## Progressive Scan Sessions

Pass `scan_id` to `email_triage`, `email_search_structured`, or `email_find_similar` to auto-exclude previously seen results across calls.

- `email_scan` — manage progressive search sessions with server-side dedup:
  - `action='status'`: session stats (seen count, candidate breakdown by label/phase)
  - `action='flag'`: flag UIDs as candidates with a label (evidence category or 'relevant'/'maybe')
  - `action='candidates'`: list flagged candidates, filter by label/phase
  - `action='reset'`: clear a session (use `scan_id='__all__'` for all)

## Attachment Discovery

- `email_attachments` — unified attachment tool:
  - `mode='list'`: browse all attachments with filters (filename, extension, MIME type, sender) and pagination
  - `mode='search'`: find emails with matching attachments using the same supported filters (`filename`, `extension`, `mime_type`, optional `sender`); this is not a generic free-text `query` lane
  - `mode='stats'`: aggregate statistics (counts, sizes, type distribution)
- `email_search_structured` also supports `attachment_name` and `attachment_type` filters

## How to Analyze

Once you find relevant emails, dig deeper:

- `email_case_analysis` — dedicated workplace case analysis: structured intake for target person, alleged actors, time window, allegation focus, source scope, optional `chat_log_entries`, optional native `chat_exports`, and optional `matter_manifest`; returns a case bundle, chronology, language/behaviour findings, power/context analysis, evidence table, message appendix, and investigation-style report. This exploratory surface is retrieval-bounded and does not refresh persisted matter snapshots.
- `email_case_execute_wave` — execute one documented wave through the shared campaign workflow; derives wave-native query lanes, canonical `scan_id`, archive-harvest diagnostics, and wave execution metadata
- `email_case_execute_all_waves` — execute all documented waves through the shared campaign workflow; returns a machine-readable per-wave summary and can optionally include every per-wave payload
- `email_case_gather_evidence` — execute all documented waves, persist each wave's harvested body and attachment candidates into the SQLite evidence-candidate table as the run progresses, and auto-promote exact verified body quotes into the durable evidence corpus
- `email_case_prompt_preflight` — convert a long natural-language matter prompt into a conservative draft intake plus missing-field guidance; this does not bypass exhaustive-review requirements
- `email_case_full_pack` — compile a long natural-language matter prompt plus a materials directory into a strict manifest-backed full legal-support workflow; returns explicit blockers when required structured inputs are missing and otherwise runs the downstream exhaustive case-analysis path with optional export
- `email_case_evidence_index` — return the standalone exhibit-centric evidence index only
- `email_case_master_chronology` — return the standalone master chronology only
- `email_case_comparator_matrix` — return the standalone comparator matrix only
- `email_case_issue_matrix` — return the lawyer-usable German employment issue matrix only
- `email_case_skeptical_review` — return the employer-side stress test plus repair guidance only
- `email_case_document_request_checklist` — return the concrete records-request and preservation checklist only
- `email_case_actor_witness_map` — return the actor map and witness map only
- `email_case_promise_contradictions` — return the promise-versus-action, omission, and contradiction layer only
- `email_case_lawyer_briefing_memo` — return the compact lawyer onboarding memo only
- `email_case_draft_preflight` — return the framing preflight and allegation-ceiling review only
- `email_case_controlled_draft` — return the controlled factual draft only
- `email_case_retaliation_timeline` — return the structured retaliation timeline assessment only
- `email_case_dashboard` — return the compact refreshable case dashboard only
- `email_case_export` — write portable legal-support artifacts for counsel handoff, exhibit-register delivery, dashboard delivery, or a zipped handoff bundle
- `email_deep_context` — one-call deep analysis: full body + thread summary + evidence + sender profile
- `email_thread_summary` — summarize a conversation thread
- `email_action_items` — extract action items and assignments from threads
- `email_decisions` — extract decisions made in threads
- `email_contacts` — top contacts (omit compare_with) or bidirectional stats (set compare_with)
- `email_network_analysis` — centrality, communities, bridge nodes
- `relationship_paths` — find communication paths between two people through intermediaries
- `shared_recipients` — identify recipients common to multiple senders
- `coordinated_timing` — detect time windows where multiple senders were simultaneously active
- `relationship_summary` — one-call profile: top contacts, community, bridge score, send/receive ratio
- `email_temporal` — temporal analysis:
  - `analysis='volume'`: email volume trends (day/week/month)
  - `analysis='activity'`: activity heatmap (hour vs day-of-week)
  - `analysis='response_times'`: recent-sample response times per sender based on canonical reply pairs
- `email_entity_timeline` — track how often an entity appears over time

Campaign authority note:

- wave execution is now a shared campaign surface exposed through both CLI `case execute-wave` / `case execute-all-waves` and MCP `email_case_execute_wave` / `email_case_execute_all_waves`
- evidence harvest is now a first-class shared campaign phase exposed through CLI `case gather-evidence` and MCP `email_case_gather_evidence`
- dedicated legal-support analytical products remain MCP-governed, are registered as idempotent write surfaces, and may refresh shared persisted matter snapshots when they rerun the exhaustive workflow

## How to Collect Evidence

The evidence system lets users mark emails and quotes as evidence items with categories, relevance scores, and chain-of-custody tracking.

1. **Add evidence:** `evidence_add` with the email UID, the exact quote, a category, a brief summary, relevance score (1-5), and optional notes. The system auto-verifies the quote against the source email.
2. **Batch add:** `evidence_add_batch` for up to 20 items at once.
3. **Query:** `evidence_query` — omit query to list, set query to search text, use sort='date' for timeline view. Filter by category, relevance, email UID.
4. **Update:** `evidence_update` to refine category, quote, summary, relevance, or notes.
5. **Verify:** `evidence_verify` to re-verify all quotes against source emails.
6. **Overview:** `evidence_overview` — combined stats + category breakdown.

## How to Export and Report

- `evidence_export` — export evidence collection as HTML report or CSV
- `email_dossier` — generate or preview proof dossier (HTML/PDF). Set preview_only=True to check scope first
- `email_export` — export a single email (by uid) or conversation thread (by conversation_id) as formatted HTML/PDF; omit `output_path` only for in-memory HTML export, because `format='pdf'` requires a file path
  - output/write paths default below `private/exports/`, must resolve inside configured allowlisted local roots, and must not overwrite existing files; extend via `EMAIL_RAG_ALLOWED_OUTPUT_ROOTS` when needed
- `email_report` — reports:
  - `type='archive'`: HTML overview report of the entire archive
  - `type='network'`: GraphML export for Gephi/Cytoscape
  - `type='writing'`: writing style and readability metrics per sender

## Chain of Custody

Every action is logged with SHA-256 hashes and timestamps:

- `custody_chain` — view the audit trail (filter by email UID, event type, date range)
- `email_provenance` — full provenance for an email: OLM source hash, ingestion run, custody events
- `evidence_provenance` — full chain for an evidence item: details + source email provenance + history

## Browsing and Reading

- `email_deep_context` — read the complete body of a specific email by UID, with optional thread/evidence/sender context. When response budgets are tight, the tool now compacts low-priority sidecars before it trims the body surface; if a live runtime still returns a truncated body, fall back to `email_thread_lookup`, `email_export`, or local SQLite body recovery before preserving wording-sensitive evidence.
  - `max_body_chars=None` uses the runtime profile default (`MCP_MAX_FULL_BODY_CHARS`), while `max_body_chars=0` disables body truncation
- `email_browse` — page through emails with filters. Also supports:
  - `list_categories=True`: list Outlook categories with counts
  - `is_calendar=True`: browse calendar/meeting emails

## Archive Overview

- `email_stats` — total counts, date range, senders, folders
- `email_list_senders` — top senders by frequency
- `email_list_folders` — all folders with counts
- `email_topics` — discovered topics (omit topic_id to list, set topic_id to list emails)
- `email_clusters` — email clusters (omit cluster_id to list, set cluster_id to list emails)
- `email_discovery` — `mode='keywords'` for top keywords, `mode='suggestions'` for search suggestions
- `email_quality` — data quality checks:
  - `check='languages'`: language distribution plus labeled vs unlabeled coverage
  - `check='sentiment'`: sentiment distribution
  - `check='duplicates'`: find near-duplicate emails

## Admin & Diagnostics

- `email_admin` — admin operations:
  - `action='diagnostics'`: show resolved runtime profile/load mode/device/batch size, current embedder backend state, MCP budgets, and sparse-index status
  - `action='reingest_bodies'`: backfill full body text (requires olm_path)
  - `action='reembed'`: rebuild ChromaDB embeddings from SQLite body text
  - `action='reingest_metadata'`: backfill v7 metadata (requires olm_path)
  - `action='reingest_analytics'`: backfill language detection and sentiment analysis
- `email_ingest` — trigger ingestion of an .olm file
  - ingest targets the requested archive paths but does not silently switch the currently active runtime archive for future search calls

## Legal-Support Refresh Behavior

The dedicated `email_case_*` legal-support tools all use the same structured intake as `email_case_analysis`.

Dedicated legal-support product tools require:

- `review_mode='exhaustive_matter_review'`
- `matter_manifest` with at least one supplied artifact
- persisted review state `human_verified` or `export_approved` before counsel-facing delivery

Question-first execution note:

- when you are still stabilizing source anchors or do not yet have a matter manifest, use `email_case_analysis_exploratory` first and read the needed section from its payload
- promote to the dedicated `email_case_*` product tool only after the run is ready for manifest-backed exhaustive review

`email_case_prompt_preflight` is the prompt-only entry lane. It can derive bounded intake hints, but it does not fabricate structured `trigger_events`, comparator actors, or a `matter_manifest`, and it does not turn raw prose into a counsel-grade exhaustive review automatically.

`email_case_full_pack` is the prompt-plus-materials execution lane. It:

- runs prompt preflight internally
- builds a conservative `matter_manifest` from the supplied materials directory
- derives a bounded material-preflight from enriched manifest artifacts and auto-applies only unambiguous source-backed intake values
- validates materials and output/runtime paths conservatively instead of accepting arbitrary local paths implicitly
- merges optional structured overrides
- blocks on missing mandatory inputs such as target person, bounded dates, retaliation triggers, or comparators where required
- when no blockers remain, runs the downstream exhaustive legal-support workflow
- can optionally write an export artifact when `output_path` is supplied

Counsel-facing delivery remains human-gated:

- `counsel_handoff` and `counsel_handoff_bundle` require a persisted snapshot in `human_verified` or `export_approved`
- self-classified counsel-grade payloads without a persisted reviewed snapshot stay internal-only
- when the gate is not satisfied, use `dashboard` or `exhibit_register`

Native mixed-source chat intake can now be supplied through either:

- `chat_log_entries`
- `chat_exports`
- `matter_manifest.artifacts[*]` with `source_class='chat_log'` or `source_class='chat_export'`

`email_case_export` uses the same intake plus:

- `delivery_target`
  - `counsel_handoff`
  - `exhibit_register`
  - `dashboard`
  - `counsel_handoff_bundle`
- `delivery_format`
  - `html`
  - `pdf`
  - `json`
  - `csv`
  - `bundle`
- `output_path`

- rerun the same tool with the same `case_scope` and `source_scope` to refresh that product from the shared matter entities
- the dedicated product tools force an internal full case-analysis pass so their contract stays stable even if the caller requested `report_only`
- controlled drafting stays constrained by the framing preflight and allegation ceiling rather than by free-form adversarial prompting
- archive-harvest diagnostics now separate direct retrieval coverage from expanded thread or attachment context so widened evidence does not masquerade as directly retrieved support

## MCP Runtime

Use the repository virtual environment when starting the MCP server:

```bash
.venv/bin/python -m src.mcp_server
```

If the active interpreter does not have the `mcp` package installed, startup now fails with an actionable message pointing back to the venv-backed command above instead of raising a raw import traceback during module import.
