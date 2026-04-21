# API Compatibility Policy

This document defines the public interface compatibility contract for `outlook-email-rag`.

## Scope

Stable public interfaces for the `0.1.x` release series:

1. CLI arguments and behavior in `python -m src.cli`.
2. MCP tool names and parameter schemas exposed by `python -m src.mcp_server`.

## CLI Compatibility Contract

The following CLI capabilities are stable for `0.1.x`:

1. Query path:
   1. `--query` / `-q`
   2. `--top-k`
   3. `--sender`
   4. `--subject`
   5. `--folder`
   6. `--cc`
   7. `--to`
   8. `--bcc`
   9. `--has-attachments`
   10. `--priority`
   11. `--email-type`
   12. `--date-from`
   13. `--date-to`
   14. `--min-score`
   15. `--rerank`
   16. `--hybrid`
   17. `--cluster-id`
   18. `--expand-query`
   19. `--json` and `--format {text,json}`
   20. `--version`
2. Operational path:
   1. `--stats`
   2. `--list-senders N`
   3. `--reset-index --yes`
   4. `--suggest`
   5. `--top-contacts EMAIL`
   6. `--volume {day,week,month}`
   7. `--entities`
   8. `--heatmap`
   9. `--response-times`
   10. `--generate-report`
   11. `--export-network`
3. Export & browse path:
   1. `--browse`
   2. `--page`, `--page-size`
   3. `--export-thread CONVERSATION_ID`
   4. `--export-email UID`
   5. `--export-format {html,pdf}`
   6. `--output PATH` / `-o`
4. Evidence path:
   1. `--evidence-list`
   2. `--evidence-export PATH`
   3. `--evidence-export-format {html,csv,pdf}`
   4. `--evidence-stats`
   5. `--evidence-verify`
   6. `--category`
   7. `--min-relevance`
5. Chain of custody & dossier path:
   1. `--dossier PATH`
   2. `--dossier-format {html,pdf}`
   3. `--custody-chain`
   4. `--provenance UID`
6. Fine-tuning & image embedding path:
   1. `--generate-training-data [PATH]`
   2. `--fine-tune [PATH]`
   3. `--embed-images`
7. Validation semantics:
   1. `--date-from` and `--date-to` are ISO `YYYY-MM-DD`.
   2. `--date-from` must be less than or equal to `--date-to`.
   3. `--min-score` is bounded to `[0.0, 1.0]`.
   4. `--top-k` is a positive integer and bounded.

## MCP Compatibility Contract

The following 45 tool names are stable for `0.1.x`:

### Core Search (6)

1. `email_ingest`
2. `email_list_folders`
3. `email_list_senders`
4. `email_search_structured`
5. `email_stats`
6. `email_triage`

### Email Reading & Export (3)

7. `email_browse`
8. `email_deep_context`
9. `email_export`

### Evidence & Custody (13)

10. `custody_chain`
11. `email_dossier`
12. `email_provenance`
13. `evidence_add`
14. `evidence_add_batch`
15. `evidence_export`
16. `evidence_get`
17. `evidence_overview`
18. `evidence_provenance`
19. `evidence_query`
20. `evidence_remove`
21. `evidence_update`
22. `evidence_verify`

### Network & Relationships (6)

23. `coordinated_timing`
24. `email_contacts`
25. `email_network_analysis`
26. `relationship_paths`
27. `relationship_summary`
28. `shared_recipients`

### Entities (4)

29. `email_entity_network`
30. `email_entity_timeline`
31. `email_list_entities`
32. `email_search_by_entity`

### Thread Intelligence (4)

33. `email_action_items`
34. `email_decisions`
35. `email_thread_lookup`
36. `email_thread_summary`

### Topics & Discovery (4)

37. `email_clusters`
38. `email_discovery`
39. `email_find_similar`

### Temporal (1)

40. `email_temporal` (discriminator: `analysis`)

### Data Quality (1)

41. `email_quality` (discriminator: `check`)

### Reporting (1)

42. `email_report` (discriminator: `type`)

### Attachments (1)

43. `email_attachments` (discriminator: `mode`)

### Admin (1)

44. `email_admin` (discriminator: `action`)

### Scan Sessions (1)

45. `email_scan` (discriminator: `action`)

`email_topics` and the CLI `--topic` filter remain available in the codebase, but they are excluded from the stable `0.1.x` compatibility contract until the repository ships a first-party workflow that populates topic tables.

## Stable MCP Input Schema Summary

### Core Search

1. `email_ingest`
    1. `olm_path: str` (required) — absolute path to `.olm` file
    2. `max_emails: int | null` (optional, ge=1)
    3. `dry_run: bool` (optional, default false)
    4. `extract_attachments: bool` (optional, default false) — extract and index text from attachments
    5. `embed_images: bool` (optional, default false) — embed image attachments using Visualized-BGE-M3
    6. `extract_entities: bool` (optional, default false) — extract entities into SQLite
2. `email_list_folders`
    1. no parameters
3. `email_list_senders`
    1. `limit: int` (optional, default 30, bounded 1-200)
4. `email_search_structured`
    1. `query: str` (required, 1-500 chars)
    2. `top_k: int` (optional, default 10, bounded 1-30)
    3. `sender: str | null` (optional)
    4. `subject: str | null` (optional)
    5. `folder: str | null` (optional)
    6. `cc: str | null` (optional) — CC recipient partial match
    7. `to: str | null` (optional) — To recipient partial match
    8. `bcc: str | null` (optional) — BCC recipient partial match
    9. `has_attachments: bool | null` (optional)
    10. `attachment_name: str | null` (optional) — partial filename match
    11. `attachment_type: str | null` (optional) — file extension filter
    12. `priority: int | null` (optional, ge=0)
    13. `date_from: str | null` (optional, ISO date)
    14. `date_to: str | null` (optional, ISO date)
    15. `min_score: float | null` (optional, bounded 0.0-1.0)
    16. `rerank: bool` (optional, default false)
    17. `hybrid: bool` (optional, default false)
    18. `cluster_id: int | null` (optional, ge=0)
    19. `expand_query: bool` (optional, default false)
    20. `email_type: str | null` (optional, one of reply/forward/original)
    21. `category: str | null` (optional) — Outlook category partial match
    22. `is_calendar: bool | null` (optional) — filter calendar/meeting messages
    23. `scan_id: str | null` (optional, 1-100 chars) — scan session ID for progressive search
5. `email_stats`
    1. no parameters
6. `email_triage`
    1. `query: str` (required, 1-500 chars)
    2. `top_k: int` (optional, default 50, bounded 1-100)
    3. `preview_chars: int` (optional, default 200, bounded 0-500)
    4. `sender: str | null` (optional) — partial match
    5. `folder: str | null` (optional)
    6. `has_attachments: bool | null` (optional)
    7. `date_from: str | null` (optional, ISO date)
    8. `date_to: str | null` (optional, ISO date)
    9. `hybrid: bool` (optional, default false)
    10. `scan_id: str | null` (optional, 1-100 chars) — scan session ID for progressive search

### Email Reading & Export

7. `email_browse`
    1. `offset: int` (optional, default 0, ge=0)
    2. `limit: int` (optional, default 10, bounded 1-50)
    3. `folder: str | null` (optional, exact match)
    4. `sender: str | null` (optional, partial match)
    5. `category: str | null` (optional, exact match)
    6. `sort_order: str` (optional, default "desc", one of asc/desc)
    7. `include_body: bool` (optional, default false)
    8. `is_calendar: bool | null` (optional) — filter calendar/meeting messages
    9. `list_categories: bool` (optional, default false) — return category list instead of emails
    10. `date_from: str | null` (optional, ISO date)
    11. `date_to: str | null` (optional, ISO date)
8. `email_deep_context`
    1. `uid: str` (required)
    2. `include_thread: bool` (optional, default true)
    3. `include_evidence: bool` (optional, default true)
    4. `include_sender_stats: bool` (optional, default true)
    5. `max_body_chars: int` (optional, default 10000, ge=0)
9. `email_export`
    1. `uid: str | null` (optional) — export a single email by UID
    2. `conversation_id: str | null` (optional) — export a thread by conversation ID
    3. `output_path: str | null` (optional)
    4. `format: str` (optional, default "html", one of html/pdf)

### Evidence & Custody

10. `custody_chain`
    1. `target_type: str | null` (optional)
    2. `target_id: str | null` (optional)
    3. `action: str | null` (optional)
    4. `limit: int` (optional, default 50, bounded 1-200)
    5. `compact: bool` (optional, default true) — omit details JSON and content_hash
11. `email_dossier`
    1. `preview_only: bool` (optional, default false) — return scope only, no file generated
    2. `output_path: str` (optional, default "dossier.html")
    3. `format: str` (optional, default "html", one of html/pdf)
    4. `title: str` (optional, default "Proof Dossier")
    5. `case_reference: str` (optional, default "")
    6. `custodian: str` (optional, default "")
    7. `prepared_by: str` (optional, default "")
    8. `min_relevance: int | null` (optional, bounded 1-5)
    9. `category: str | null` (optional)
    10. `include_relationships: bool` (optional, default true)
    11. `include_custody: bool` (optional, default true)
    12. `persons_of_interest: list[str] | null` (optional)
12. `email_provenance`
    1. `email_uid: str` (required)
13. `evidence_add`
    1. `email_uid: str` (required)
    2. `category: str` (required)
    3. `key_quote: str` (required) — must appear verbatim in email body
    4. `summary: str` (required)
    5. `relevance: int` (required, bounded 1-5)
    6. `notes: str` (optional, default "")
14. `evidence_add_batch`
    1. `items: list[EvidenceAddInput]` (required, 1-20 items)
15. `evidence_export`
    1. `output_path: str` (optional, default "evidence_report.html")
    2. `format: str` (optional, default "html", one of html/csv/pdf)
    3. `min_relevance: int | null` (optional, bounded 1-5)
    4. `category: str | null` (optional)
16. `evidence_get`
    1. `evidence_id: int` (required, ge=1)
17. `evidence_overview`
    1. `category: str | null` (optional)
    2. `min_relevance: int | null` (optional, bounded 1-5)
18. `evidence_provenance`
    1. `evidence_id: int` (required, ge=1)
19. `evidence_query`
    1. `query: str | null` (optional, max 500 chars) — text search across key_quote, summary, notes
    2. `sort: str` (optional, default "relevance") — "relevance" or "date" (chronological timeline)
    3. `category: str | null` (optional)
    4. `min_relevance: int | null` (optional, bounded 1-5)
    5. `email_uid: str | null` (optional)
    6. `limit: int` (optional, default 25, bounded 1-200)
    7. `offset: int` (optional, default 0, ge=0)
    8. `include_quotes: bool` (optional, default false) — full key_quote vs 80-char preview
20. `evidence_remove`
    1. `evidence_id: int` (required, ge=1)
21. `evidence_update`
    1. `evidence_id: int` (required, ge=1)
    2. `category: str | null` (optional)
    3. `key_quote: str | null` (optional)
    4. `summary: str | null` (optional)
    5. `relevance: int | null` (optional, bounded 1-5)
    6. `notes: str | null` (optional)
22. `evidence_verify`
    1. no parameters

### Network & Relationships

23. `coordinated_timing`
    1. `email_addresses: list[str]` (required, 2+ items)
    2. `window_hours: int` (optional, default 24, bounded 1-168)
    3. `min_events: int` (optional, default 3, ge=2)
    4. `limit: int` (optional, default 20, bounded 1-100)
24. `email_contacts`
    1. `email_address: str` (required)
    2. `compare_with: str | null` (optional) — second address for bidirectional stats
    3. `limit: int` (optional, default 20, bounded 1-100)
25. `email_network_analysis`
    1. `top_n: int` (optional, default 20, bounded 1-100)
26. `relationship_paths`
    1. `source: str` (required)
    2. `target: str` (required)
    3. `max_hops: int` (optional, default 3, bounded 1-6)
    4. `top_k: int` (optional, default 5, bounded 1-20)
27. `relationship_summary`
    1. `email_address: str` (required)
    2. `limit: int` (optional, default 20, bounded 1-100)
28. `shared_recipients`
    1. `email_addresses: list[str]` (required, 2+ items)
    2. `min_shared: int` (optional, default 2, ge=2)
    3. `limit: int` (optional, default 30, bounded 1-200)

### Entities

29. `email_entity_network`
    1. `entity: str` (required)
    2. `limit: int` (optional, default 20, bounded 1-100)
30. `email_entity_timeline`
    1. `entity: str` (required)
    2. `period: str` (optional, default "month", one of day/week/month)
31. `email_list_entities`
    1. `entity_type: str | null` (optional)
    2. `limit: int` (optional, default 20, bounded 1-100)
32. `email_search_by_entity`
    1. `entity: str` (required)
    2. `entity_type: str | null` (optional)
    3. `limit: int` (optional, default 20, bounded 1-100)

### Thread Intelligence

33. `email_action_items`
    1. `conversation_id: str | null` (optional) — thread ID; omit to scan recent emails
    2. `days: int | null` (optional, bounded 1-365)
    3. `limit: int` (optional, default 20, bounded 1-100)
34. `email_decisions`
    1. `conversation_id: str | null` (optional)
    2. `days: int | null` (optional, bounded 1-365)
    3. `limit: int` (optional, default 30, bounded 1-100)
35. `email_thread_lookup`
    1. `conversation_id: str | null` (optional) — exactly one of conversation_id or thread_topic required
    2. `thread_topic: str | null` (optional)
    3. `limit: int` (optional, default 50, bounded 1-200)
36. `email_thread_summary`
    1. `conversation_id: str` (required)
    2. `max_sentences: int` (optional, default 5, bounded 1-20)

### Topics & Discovery

37. `email_clusters`
    1. `cluster_id: int | null` (optional, ge=0) — omit to list clusters; set to list emails in cluster
    2. `limit: int` (optional, default 30, bounded 1-100)
38. `email_discovery`
    1. `mode: str` (required) — "keywords" or "suggestions"
    2. `sender: str | null` (optional) — filter keywords by sender
    3. `folder: str | null` (optional) — filter keywords by folder
    4. `limit: int` (optional, default 30, bounded 1-200)
39. `email_find_similar`
    1. `uid: str | null` (optional) — email UID to find similar emails for
    2. `query: str | null` (optional) — query text to find similar emails for
    3. `top_k: int` (optional, default 10, bounded 1-50)
    4. `scan_id: str | null` (optional, 1-100 chars) — scan session ID for progressive search

### Conditional Topic Surface (not stable for `0.1.x`)

40. `email_topics`
    1. `topic_id: int | null` (optional, ge=0) — omit to list topics; set to list emails for topic
    2. `limit: int` (optional, default 20, bounded 1-100)

### Temporal

41. `email_temporal`
    1. `analysis: str` (required) — "volume", "activity", or "response_times"
    2. `period: str` (optional, default "day") — aggregation for volume: day/week/month
    3. `sender: str | null` (optional) — filter by sender
    4. `date_from: str | null` (optional, ISO date)
    5. `date_to: str | null` (optional, ISO date)
    6. `limit: int` (optional, default 20, bounded 1-100) — for response_times

### Data Quality

42. `email_quality`
    1. `check: str` (required) — "duplicates", "languages", or "sentiment"
    2. `limit: int` (optional, default 50, bounded 1-200) — for duplicates
    3. `threshold: float` (optional, default 0.85, bounded 0.5-1.0) — for duplicates

### Reporting

43. `email_report`
    1. `type: str` (required) — "archive", "network", or "writing"
    2. `output_path: str` (optional, default "report.html") — for archive/network
    3. `title: str` (optional, default "Email Archive Report") — for archive
    4. `sender: str | null` (optional) — for writing analysis
    5. `limit: int` (optional, default 10, bounded 1-50) — for writing

### Attachments

44. `email_attachments`
    1. `mode: str` (required) — "list", "search", or "stats"
    2. `filename: str | null` (optional) — partial match
    3. `extension: str | null` (optional) — e.g. "pdf"
    4. `mime_type: str | null` (optional) — partial match
    5. `sender: str | null` (optional) — list mode only
    6. `limit: int` (optional, default 50, bounded 1-200)
    7. `offset: int` (optional, default 0, ge=0) — list mode only

### Admin

45. `email_admin`
    1. `action: str` (required) — "diagnostics", "reingest_bodies", "reembed", "reingest_metadata", or "reingest_analytics"
       `diagnostics` returns resolved runtime settings, current embedder/backend state, MCP budgets, and sparse-index status.
    2. `olm_path: str | null` (optional) — required for reingest_bodies and reingest_metadata
    3. `force: bool` (optional, default false) — for reingest_bodies only
    4. `batch_size: int` (optional, default 100, ge=1) — for reembed only

### Scan Sessions

46. `email_scan`
    1. `action: str` (required) — "status", "flag", "candidates", or "reset"
    2. `scan_id: str` (required, 1-100 chars) — scan session identifier
    3. `uids: list[str] | null` (optional, max 50) — email UIDs to flag
    4. `label: str | null` (optional) — label for flagging or filtering
    5. `phase: int | null` (optional, bounded 1-3) — 1=scan, 2=refine, 3=deep
    6. `score: float | null` (optional, bounded 0.0-1.0) — relevance score

## Breaking Change Rule

A breaking change is any modification that invalidates existing automation or user workflows relying on the stable interfaces above, including:

1. Removing or renaming stable CLI flags.
2. Changing expected semantics of stable flags.
3. Removing or renaming MCP tools.
4. Altering MCP parameter names/types/requiredness in an incompatible way.

Breaking changes require:

1. A version bump.
2. A `Breaking` entry in [CHANGELOG.md](../CHANGELOG.md).
3. Updated migration guidance in release notes.
