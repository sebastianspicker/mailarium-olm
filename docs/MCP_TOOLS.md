# Email RAG — Full MCP Tool Reference (46 tools)

> This file is the detailed MCP tool reference for the built-in server.

## How to Search

Start broad, then narrow down:

- `email_search_structured` — the main search tool: semantic query + filters (sender, date, folder, to, cc, bcc, attachments, priority, topic, cluster, reranking, hybrid search, query expansion)
- `email_triage` — fast triage scan: ultra-compact results (uid, sender, date, subject, score, preview), up to 100 results. Issue 3-5 calls with different queries for pseudo-parallel scanning
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
  - `mode='search'`: find emails with matching attachments
  - `mode='stats'`: aggregate statistics (counts, sizes, type distribution)
- `email_search_structured` also supports `attachment_name` and `attachment_type` filters

## How to Analyze

Once you find relevant emails, dig deeper:

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
  - `analysis='response_times'`: average response times per sender
- `email_entity_timeline` — track how often an entity appears over time

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
- `email_export` — export a single email (by uid) or conversation thread (by conversation_id) as formatted HTML/PDF
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

- `email_deep_context` — read the complete body of a specific email by UID, with optional thread/evidence/sender context
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
  - `check='languages'`: language distribution
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
