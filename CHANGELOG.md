# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to semantic versioning principles for public interfaces.

## [Unreleased]

### Fixed

#### Polish pass

- **`_int_from_env` clamped to `min_value` not `default`** -- `TOP_K=0` now correctly returns 1 (the floor) instead of returning the default of 10. Consistent with how `max_value` clamping already worked.
- **`search_by_thread` used dummy embedding** -- replaced `_query_with_embedding()` + synthetic vector with `collection.get()` metadata filter, the intended ChromaDB API for non-semantic lookups.
- **`flag_candidates` overwrote existing flags** -- already-flagged UIDs are now skipped instead of silently overwritten, preserving the original label and phase.
- **`_truncate_json` returned invalid JSON for non-dict data** -- now wraps truncated content in `{"data": ..., "_truncated": true}` instead of appending a bare `[response truncated]` string.
- **`email_deep_context` ignored model profile** -- when the caller didn't set `max_body_chars` explicitly, it now uses the `MCP_MODEL_PROFILE` budget instead of hardcoded 10000.
- **`email_find_similar` passed unbounded body as query** -- body text is now truncated to 1500 chars before being used as a similarity query.
- **`insert_email` left partial data on failure** -- categories, recipients, attachments, contacts, and communication edges are now wrapped in a try/except with rollback.
- **`reingest_bodies` / `reingest_metadata` committed per-row** -- batched commits every 200 rows for faster re-ingestion.
- **MCP server startup ran side effects at import time** -- `_acquire_instance_lock()` and `_log_startup_info()` moved into `main()`, called from `__main__.py`.
- **`get_settings()` cache could be stale** -- `cache_clear()` called after `load_dotenv()` so settings reflect `.env` values.
- **Image attachment chunk IDs used `::` separator** -- changed to `__img_` for consistency with ChromaDB ID conventions.

### Changed

- CI: bumped `actions/checkout` to v6.0.2 and `actions/setup-python` to v6.2.0 (Dependabot PRs #5 and #6).
- Gitignore: added `data/mcp_server.lock` (runtime PID lock file should not be tracked).

#### Codebase Bug Audit — Rounds 5-7 (9 bugs)

- **P1: Legacy CLI dispatch broken** — `_infer_subcommand()` now sets `*_action` attributes (e.g. `analytics_action`, `evidence_action`) so that legacy `--stats`, `--evidence-list`, etc. flags reach the correct handler branch instead of hitting `sys.exit(2)`.
- **P1: Image embeddings computed but discarded** — `EmailChunk` gains an optional `embedding` field; `add_chunks()` splits batches into pre-embedded (images) vs needs-encoding (text) groups. Previously, `image_embedder_fn()` output was silently discarded and the placeholder text `"[Image attachment: …]"` was re-encoded instead.
- **P2: `_has_subcommand` flag-value collision** — simplified to only check `argv[0]`, preventing false subcommand detection when a flag value like `--db-path analytics` contained a subcommand name.
- **P2: Hybrid search inflated `raw_count`** — `raw_count` now measured before `_merge_hybrid()` appends BM25/sparse results, eliminating up to 6 unnecessary retry iterations.
- **P2: `QueryExpander.expand` substring skip** — changed from `term in query` substring check to word-boundary regex, so query `"art"` no longer skips term `"artificial"`.
- **P2: Phone regex false positives** — added `_DATE_LIKE_RE` exclusion to skip date strings (`2024-01-15`, `15/01/2024`) that previously matched `_PHONE_RE`.
- **P2: Evidence report stats showed unfiltered globals** — `evidence_stats()` now accepts `category` and `min_relevance` params; `EvidenceExporter` passes filters through.
- **P2: Attachment chunk ID collision** — `chunk_attachment()` takes new `att_index` param; two attachments with the same filename on the same email now produce unique chunk IDs.
- **P2: `has_attachments`/`priority` type mismatch** — verified existing coercion in `result_filters.py` handles both `str` and native types correctly; added regression tests.

### Added

#### Progressive Multi-Pass Scan Sessions

- `src/scan_session.py`: in-memory session state with TTL auto-cleanup.
- `scan_id` parameter on `email_triage`, `email_search_structured`, `email_find_similar`.
- `email_scan` tool: status/flag/candidates/reset actions for session management.
- 38 new tests in `tests/test_scan_session.py`.

#### Model-Aware MCP Response Profiles

- `MCP_MODEL_PROFILE` env var (`haiku`/`sonnet`/`opus`/`auto`) selects budget presets.
- Per-tool result clamping in `email_triage` and `email_search_structured`.
- `email_diagnostics` includes `mcp_profile` + `mcp_budget` dict.

#### MCP Response Budgeting

- `mcp_max_full_body_chars` setting (default 10000) for `email_deep_context`.
- `serialize_results()` token budget with `max_response_tokens`.
- `\xa0` normalization in `html_to_text()` and `truncate_body()`.
- CLAUDE.md split — tool reference moved to `docs/CLAUDE-TOOLS.md`.

#### OLM Metadata Extraction & Search Quality

- Parse OLM fields: categories, thread_topic, thread_index, inference_classification, is_calendar_message, meeting_data, Exchange-extracted links/emails/contacts/meetings, attachment content_id.
- Schema v7: categories/thread_topic/inference_classification/is_calendar_message/references_json columns, `email_categories` + `attachments` tables.
- Body recovery: text/calendar MIME parts, multipart fallback for attachment-only emails.
- Chunking enrichment: categories, calendar tag, thread_topic in chunk metadata and text.
- New MCP tools: `email_list_categories`, `email_browse_calendar`, `email_search_by_thread_topic`, `email_search_by_attachment`, `email_list_attachments`, `email_attachment_stats`.

#### Ingest Quality & Analytics

- Schema v8: `detected_language`, `sentiment_label`, `sentiment_score` columns with indexes and `update_analytics_batch()`.
- Auto-analytics during ingest: language detection + sentiment wired into `_EmbedPipeline._process_batch()`.
- New MCP tools: `email_reingest_analytics`, `email_reingest_metadata`.
- Multilingual quoted content separators for FR/ES/NL/IT/PT/SV/DA/PL; "wrote" patterns for 8 languages; closing phrases for 7 languages.
- Sparse index normalization: `normalize=True` option on `SparseIndex.search()`.
- Entity dedup: Exchange types changed to canonical (`url`/`email`/`person`/`event`) for `ON CONFLICT` dedup.

#### Code Decomposition

- `src/db_schema.py`: SQLite schema DDL and migrations (v3–v9).
- `src/db_attachments.py`: Attachment query mixin with dedup filter builder.
- `src/db_custody.py`: Chain-of-custody mixin.
- `src/db_entities.py`: Entity storage mixin.
- `src/db_analytics.py`: Analytics mixin (language detection, sentiment analysis).
- `src/db_evidence.py`: Evidence CRUD mixin.
- `src/html_converter.py`: HTML-to-text conversion extracted from `parse_olm.py`.
- `src/rfc2822.py`: RFC 2822 header, MIME, and iCalendar parsing extracted from `parse_olm.py`.
- `src/result_filters.py`: Result filtering logic.

#### BGE-M3 Multi-Vector Optimization

- `src/multi_vector_embedder.py`: Unified embedder supporting BGEM3FlagModel (dense + sparse + ColBERT) with SentenceTransformer fallback. MPS float32 workaround, auto batch sizing.
- `src/sparse_index.py`: In-memory inverted index backed by SQLite (schema v5, packed BLOB). Replaces BM25 when sparse vectors available.
- `src/colbert_reranker.py`: ColBERT MaxSim token-level reranking using same BGE-M3 model. Supersedes cross-encoder when available.
- `src/email_clusterer.py`: `fit_hybrid()` for dense + sparse SVD features with weighted concatenation.
- `src/training_data_generator.py`: Contrastive triplet generation from email threads with hard negative mining (same-sender, cross-thread).
- `src/fine_tuner.py`: Domain fine-tuning via FlagEmbedding config or SentenceTransformers direct training.
- `src/image_embedder.py`: Visualized-BGE-M3 for cross-modal image→text retrieval in shared 1024-d space.
- CLI flags: `--generate-training-data`, `--fine-tune`, `--embed-images`.
- Env vars: `SPARSE_ENABLED`, `COLBERT_RERANK_ENABLED`, `EMBEDDING_BATCH_SIZE`.

#### Integration & Polish Pass

- `src/ingest.py`: `embed_images` parameter wired end-to-end — creates `chunk_type: "image"` ChromaDB chunks with 1024-d embeddings. Auto-enables `extract_attachments` when `embed_images=True`.
- `src/mcp_server.py`: New MCP tools `email_model_info` (embedding backend diagnostics) and `email_sparse_status` (sparse index status).
- `src/mcp_server.py`: `email_search_structured` now supports `email_type` filter (reply/forward/original).
- `src/mcp_server.py`: `email_ingest` now accepts `extract_attachments` and `embed_images` parameters.
- `src/web_app.py`: Advanced Search Options expander with hybrid search, re-ranking, and query expansion checkboxes.
- `src/attachment_extractor.py`: Deduplicated `_IMAGE_EXTENSIONS` — now imports from `image_embedder.py`.
- `.env.example`: Added `SPARSE_ENABLED`, `COLBERT_RERANK_ENABLED`, `EMBEDDING_BATCH_SIZE` documentation.

### Changed

#### MCP Tool Consolidation (70→45)

- Removed 4 search tools subsumed by existing tools: `email_search` → `email_search_structured`, `email_get_full` → `email_deep_context`, `email_find_people` → `email_search_by_entity`, `email_smart_search` → `email_search_structured(expand_query=True)`.
- Merged 13 tools into 6 via `Optional[id]` discriminators: clusters/topics, thread lookup, contacts, evidence query/overview, dossier.
- Consolidated 17 tools into 5 via discriminator parameters: `email_temporal(analysis=...)`, `email_quality(check=...)`, `email_report(type=...)`, `email_attachments(mode=...)`, `email_admin(action=...)`.
- Deleted `categories.py` (absorbed into `browse.py`).

#### MCP Tool Consolidation (74→70)

- Removed 3 search wrappers (`email_search_by_sender`, `email_search_by_date`, `email_search_by_recipient`) — subsumed by `email_search_structured`.
- Merged `email_model_info` + `email_sparse_status` → `email_diagnostics`.
- Merged `email_export_thread` + `email_export_single` → `email_export` (with `uid` or `conversation_id`).
- Moved reingest/reembed tools from `browse.py` to `diagnostics.py`.
- `src/tools/` reorganized: 46 tools across 13 domain modules (was 54 tools in 9 modules).

- `src/config.py`, `src/reranker.py`: Default rerank model changed from `cross-encoder/ms-marco-MiniLM-L-6-v2` (English-only) to `BAAI/bge-reranker-v2-m3` (multilingual, aligned with BGE-M3 embeddings). Drop-in replacement via `sentence_transformers.CrossEncoder`.
- `src/fine_tuner.py`: FlagEmbedding status changed from `"config_written"` to `"config_ready"` with clear training command in output.
- `src/cli.py`: `--json` flag now emits deprecation warning recommending `--format json`.
- `src/cli.py`: Refactored from flat 58-flag argparse to 7 subcommand groups (`search`, `browse`, `export`, `evidence`, `analytics`, `training`, `admin`) with full backward compatibility. Legacy flat-flag usage emits `DeprecationWarning` but continues to work. `parse_known_args` dual-parser dispatches to subcommand or legacy parser automatically.
- `src/mcp_server.py`: Split from 1,873 lines into `src/tools/` subpackage — 54 tools moved to 9 domain modules (`network`, `temporal`, `entities`, `threads`, `topics`, `data_quality`, `reporting`, `browse`, `evidence`). 14 core tools remain in `mcp_server.py`. `ToolDeps` dependency injection avoids circular imports.
- `tests/conftest.py`: `_matches_where()` now supports ChromaDB `{"field": {"$eq": value}}` nested filter syntax.

#### Evidence Collection & Legal Export

- `src/email_db.py`: `evidence_items` SQLite table with FK to `emails`, auto-populated sender/date/recipients, quote verification against email body text.
- `src/email_db.py`: CRUD methods — `add_evidence()`, `list_evidence()`, `get_evidence()`, `update_evidence()`, `remove_evidence()`, `verify_evidence_quotes()`, `evidence_stats()`.
- `src/evidence_exporter.py`: Evidence report export as HTML (with appendix of full source emails) or CSV.
- `src/templates/evidence_report.html`: Professional Jinja2 template with category badges, relevance stars, verification status banner, and print-friendly appendix.

#### Evidence MCP Tools (12)

- **Evidence Management**: `evidence_add`, `evidence_add_batch`, `evidence_list`, `evidence_get`, `evidence_update`, `evidence_remove`, `evidence_search`, `evidence_verify`, `evidence_export`, `evidence_stats`, `evidence_timeline`, `evidence_categories`.

#### New CLI Flags

- `--evidence-list` — list evidence items with optional `--category` and `--min-relevance` filters.
- `--evidence-export PATH` — export evidence report.
- `--evidence-export-format {html,csv,pdf}` — format for evidence export.
- `--evidence-stats` — show evidence collection statistics.
- `--evidence-verify` — re-verify all quotes against source emails.
- `--category` — evidence category filter.
- `--min-relevance` — minimum relevance filter (1-5).

- `src/__main__.py`: `python -m src` now starts the MCP server directly.
- `.claude/settings.json`: project-level MCP server registration — Claude Code auto-discovers tools when the project is opened.
- `pyproject.toml`: added `[project]` and `[build-system]` sections; `pip install -e .[dev]` now works.

#### Enhanced Parsing

- BCC recipient extraction from OLM email headers.
- Attachment metadata: MIME type, file size, filename.
- Email type detection via `in_reply_to` header (new/reply/forward).
- HTML-to-text conversion preserving headings, lists, tables, links, and blockquotes.
- Signature detection and separation from email body.
- Attachment text extraction (`src/attachment_extractor.py`): PDF, DOCX, XLSX, CSV, HTML, TXT.

#### SQLite + Analytics

- `src/email_db.py`: SQLite metadata store with emails, recipients, contacts, and communication_edges tables.
- `src/network_analysis.py`: Communication network analysis using NetworkX — centrality, communities, bridge nodes.
- `src/temporal_analysis.py`: Time-series analytics using pandas — volume over time, activity heatmaps, response times.
- `src/entity_extractor.py`: Regex-based entity extraction (organizations, URLs, phones, @mentions).

#### Advanced Search

- `src/bm25_index.py`: BM25 keyword index for hybrid semantic + keyword search.
- `src/reranker.py`: Cross-encoder reranking for improved result precision.
- `src/query_expander.py`: Semantic query expansion using vocabulary similarity.
- `src/query_suggestions.py`: Search suggestion generation from indexed data.

#### NLP Intelligence

- `src/nlp_entity_extractor.py`: spaCy NER for person, organization, and location extraction.
- `src/topic_modeler.py`: NMF topic modeling with TF-IDF.
- `src/keyword_extractor.py`: TF-IDF keyword extraction (global and per-sender/folder).
- `src/email_clusterer.py`: KMeans email clustering with automatic labeling.
- `src/thread_summarizer.py`: Extractive thread summarization.
- `src/thread_intelligence.py`: Action item and decision extraction from email threads.
- `src/writing_analyzer.py`: Writing style and readability metrics (Flesch Reading Ease, grade level).

#### Data Quality

- `src/dedup_detector.py`: Near-duplicate email detection using character n-gram similarity.
- `src/language_detector.py`: Language detection and distribution statistics.
- `src/sentiment_analyzer.py`: Rule-based sentiment analysis across emails.

#### Reporting

- `src/report_generator.py`: Self-contained HTML report generation using Jinja2 templates.
- `src/dashboard_charts.py`: Chart generation helpers for Streamlit dashboard.

#### Email Export & Browse

- `src/email_exporter.py`: Export conversation threads and single emails as styled HTML or PDF (Jinja2 template, optional weasyprint for PDF).
- `src/templates/thread_export.html`: Mail-client-style HTML template with headers, body, attachment listings, and print-friendly CSS.
- SQLite schema v3: `body_text` and `body_html` columns now persist full email bodies during ingestion.
- `get_email_full()`, `get_thread_emails()`, `list_emails_paginated()` methods on `EmailDatabase`.
- `reingest_bodies()` function to backfill body text for existing databases from OLM.

#### Search & Analytics MCP Tools (43)

- **Core Search**: `email_search_by_recipient`, `email_search_thread`, `email_smart_search`, `email_find_similar`.
- **Archive Info**: `email_query_suggestions`.
- **Email Reading & Export**: `email_get_full`, `email_browse`, `email_export_thread`, `email_export_single`.
- **Ingestion**: `email_reingest_bodies`.
- **Network Analysis**: `email_top_contacts`, `email_communication_between`, `email_network_analysis`.
- **Temporal Analysis**: `email_volume_over_time`, `email_activity_pattern`, `email_response_times`.
- **Entity & NLP**: `email_search_by_entity`, `email_list_entities`, `email_entity_network`, `email_find_people`, `email_entity_timeline`.
- **Thread Intelligence**: `email_thread_summary`, `email_action_items`, `email_decisions`.
- **Topics & Clusters**: `email_topics`, `email_search_by_topic`, `email_keywords`, `email_clusters`, `email_cluster_emails`.
- **Data Quality**: `email_find_duplicates`, `email_language_stats`, `email_sentiment_overview`.
- **Reporting & Export**: `email_generate_report`, `email_export_network`, `email_writing_analysis`.

#### New CLI Flags

- `--to`, `--bcc`, `--has-attachments`, `--priority`, `--email-type` filters.
- `--rerank`, `--hybrid`, `--expand-query` search mode flags.
- `--topic`, `--cluster-id` semantic filter flags.
- `--suggest` for search suggestions.
- `--top-contacts EMAIL` for communication partners.
- `--volume {day,week,month}` for email volume trends.
- `--entities` for entity listing.
- `--heatmap` for activity pattern.
- `--response-times` for response time stats.
- `--generate-report` for HTML report generation.
- `--export-network` for GraphML network export.
- `--browse` for paginated email browsing.
- `--page`, `--page-size` for browse pagination control.
- `--export-thread CONV_ID` for thread export.
- `--export-email UID` for single email export.
- `--export-format {html,pdf}` for export format selection.
- `--output PATH` (`-o`) for export output path.

#### Streamlit UI Enhancements

- To filter field in search form.
- Has-attachments checkbox filter.
- Email type and attachment badges in results.
- To field display in result cards.
- Thread view button for conversation exploration.
- CSV export for search results.
- Folder sidebar with counts.
- Date picker widgets (replaced manual text inputs).
- Pagination (20 results per page).
- CC filter field in search form.
- Improved empty-state message with ingestion instructions.

#### Other

- New MCP tool `email_list_folders`: lists archive folders with email counts.
- New MCP tool `email_ingest`: triggers `.olm` ingestion directly from Claude Code.
- `--cc` filter flag for CLI search.
- `--version` flag for CLI.
- `list_folders()` method on `EmailRetriever`.
- CC recipient filter in `search_filtered()` and `email_search_structured`.
- Shared `positive_int()` validator in `src/validation.py`.
- To, BCC, has_attachments, priority filters in `search_filtered()`.

#### Dependencies Added

- `networkx>=3.2` — communication network analysis.
- `pandas>=2.1.0` — temporal analytics.
- `rank_bm25>=0.2.2` — BM25 keyword search.
- `jinja2>=3.0.0` — HTML report generation.
- `spacy>=3.7.0` — NLP entity extraction.
- `textstat>=0.7.0` — writing readability metrics.
- `streamlit>=1.40.0` — web UI.

#### Multilingual Embedding & MPS GPU Acceleration

- Default embedding model changed from `all-MiniLM-L6-v2` (384 dims, English-only) to `BAAI/bge-m3` (1024 dims, 100+ languages including German).
- `src/config.py`: `device` setting with auto-detection (`mps` on Apple Silicon, `cuda` on NVIDIA, `cpu` fallback).
- `resolve_device()` function for automatic GPU backend selection.
- PyTorch MPS backend support for 3-10x faster embedding on Apple Silicon.

#### Chain of Custody & Integrity

- `src/email_db.py`: `custody_chain` SQLite table for cryptographic audit trail (action, timestamp, actor, target, content hash).
- `src/email_db.py`: `log_custody_event()`, `get_custody_chain()`, `email_provenance()`, `evidence_provenance()`, `compute_content_hash()` methods.
- `src/email_db.py`: Evidence lifecycle tracking — `add_evidence()`, `update_evidence()`, `remove_evidence()` auto-log custody events with content hashes and old-value snapshots.
- `src/email_db.py`: `content_sha256` column on emails, `content_hash` and `ingestion_run_id` on evidence items.
- `src/email_db.py`: `ingestion_runs` extended with `olm_sha256`, `file_size_bytes`, `custodian`.
- `src/ingest.py`: Streaming SHA-256 hash of OLM file at ingestion start, per-email content hashing during batch insert.

#### Chain of Custody MCP Tools (3)

- `custody_chain` — view chain-of-custody audit trail with optional filters.
- `email_provenance` — full provenance: OLM source hash, ingestion run, custody events.
- `evidence_provenance` — full evidence chain: item details + source email provenance + modification history.

#### Relationship & Complicity Analysis

- `src/network_analysis.py`: `find_paths()` — shortest communication paths between two people via NetworkX.
- `src/network_analysis.py`: `shared_recipients()` — recipients common to multiple senders.
- `src/network_analysis.py`: `coordinated_timing()` — time windows where multiple senders were active simultaneously.
- `src/network_analysis.py`: `relationship_summary()` — single-call profile covering top contacts, community, bridge score, and send/receive ratio.
- `src/email_db.py`: `shared_recipients_query()` and `sender_activity_timeline()` SQL methods.

#### Relationship Analysis MCP Tools (4)

- `relationship_paths` — find communication paths between two people through intermediaries.
- `shared_recipients` — identify recipients common to multiple senders.
- `coordinated_timing` — detect synchronized communication windows.
- `relationship_summary` — one-call profile: top contacts, community, bridge score.

#### Proof Dossier Generation

- `src/dossier_generator.py`: `DossierGenerator` class — proof dossier combining evidence timeline, source emails, relationship context, and chain-of-custody log.
- `src/templates/dossier.html`: Print-optimized HTML template with cover page, stats, TOC, evidence timeline, source email appendix, relationship analysis, custody log.
- `DossierGenerator.preview()` — token-efficient check of dossier contents before generation.
- `DossierGenerator.generate_file()` — HTML or PDF (via weasyprint) export.

#### Proof Dossier MCP Tools (2)

- `dossier_generate` — generate proof dossier as HTML/PDF.
- `dossier_preview` — preview dossier contents (counts, categories, date range) without generating.

#### New CLI Flags

- `--dossier PATH` — generate proof dossier.
- `--dossier-format {html,pdf}` — dossier output format.
- `--custody-chain` — view chain-of-custody audit trail.
- `--provenance UID` — view email provenance (OLM source hash, ingestion run, custody events).

### Changed

- Removed `anthropic` SDK dependency — MCP server is now the sole Claude integration point.
- Removed `ask_claude()` synthesis from CLI; results are always shown as formatted retrieval output.
- Removed `--no-claude` and `--raw` CLI flags (replaced by `--format {text,json}`).
- Removed `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` from configuration.
- Removed over-engineered governance docs: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `docs/RELEASE_CHECKLIST.md`, `docs/RELEASE_FILE_MANIFEST.md`, `docs/TEST_ACCEPTANCE_MATRIX.md`, GitHub issue/PR templates, and release workflow.
- Removed `src/converters.py`; `to_builtin_list()` moved to `src/storage.py`.
- Removed backward-compat wrapper methods `search_by_sender()` and `search_by_date()` from `EmailRetriever`; callers now use `search_filtered()` directly.
- `email_search_by_sender` and `email_search_by_date` MCP tools now call `search_filtered()` directly.
- Simplified `_serialize_results` helper in MCP server to direct `retriever.serialize_results()` call.
- Removed trivial wrapper functions `_sanitize_terminal_text()` (CLI) and `_sanitize_untrusted_text()` (MCP server).
- Ingest progress log interval reduced from 500 to 100 emails.
- README rewritten to reflect 46 MCP tools, 1360+ tests, full architecture.
- `docs/API_COMPATIBILITY.md` expanded to cover all 46 tools and all CLI flags.
- Default embedding model changed to `BAAI/bge-m3` (multilingual, 1024 dims). Requires re-ingestion.

### Removed

- `src/auto_tagger.py`: Dead code — simple keyword tagger never imported by production code.

### Breaking

- `--no-claude` and `--raw` CLI flags removed. Use `--format {text,json}` instead.
- `EmailRetriever.search_by_sender()` and `search_by_date()` methods removed. Use `search_filtered()`.
- `src.converters` module removed. Import `to_builtin_list` from `src.storage`.

## [0.1.0] - 2026-03-02

### Added

- Initial public release for local Outlook email RAG.
- Interfaces:
  - CLI for search and operational commands.
  - MCP server tools for agent integration.
  - Optional local Streamlit UI.
- Safety and quality gates:
  - Linting, typing, tests, static security scan, dependency audit.

### Security

- Input validation and output sanitization for untrusted email content pathways.
- Safe XML parsing constraints for OLM ingestion.

### Policy

- CLI and MCP interfaces are considered stable for this release series. Breaking changes require an explicit changelog `Breaking` entry and version bump.
- See [API compatibility policy](docs/API_COMPATIBILITY.md).
