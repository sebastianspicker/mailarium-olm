# Repository Functional Audit Map

Date: `2026-04-16`

Scope:

- full repository surface audit for functional categorization
- read-only mapping for follow-up deep audits
- includes implementation code, MCP surface, scripts, docs, tests, and local runtime/result lanes

Assumptions:

- “corpus” means the full repository corpus, not only the indexed email archive
- this pass is for decomposition and prioritization, not bug-fixing

## Top-Level Surface

| Area | Function | Notes |
| --- | --- | --- |
| `src/` | production implementation | core application, retrieval, MCP server, legal-support analysis, storage, UI |
| `src/tools/` | MCP tool handlers | request/response layer over the core services |
| `tests/` | verification corpus | large regression and contract surface covering nearly every subsystem |
| `scripts/` | operator and CI helpers | acceptance matrix, ingest smoke, QA-eval refresh, topology helper |
| `docs/` | public and operator documentation | public usage docs plus extensive `docs/agent/` execution contracts |
| `private/` | local-only live runtime and matter work products | real runtime DB/vector store, materials, results, checkpoints |
| `data/` | tracked sanitized runtime fixtures | tracked Chroma surface for non-private examples and smoke paths |
| `.github/` | CI/workflow automation | repository automation and checks |
| `.agents/` / local client cache | local agent support | skills, hooks, agent-facing local tooling |

## Quantitative Snapshot

| Area | Files | Approx. lines |
| --- | --- | --- |
| `src/` | `239` | `65,804` |
| `src/tools/` | `29` | `7,391` |
| `tests/` | `400` | `59,675` |
| `scripts/` | `7` | `979` |
| `docs/agent/` | `94` | `28,693` |
| `private/tests/results/` | `110` | `30,598` |

Interpretation:

- the repo is implementation-heavy, but the operator-doc and result-artifact surface is also substantial
- audit work should not focus on `src/` alone; the runbooks and generated local artifacts are part of the effective control plane

## Functional Categories

### 1. Entry Points, User Interfaces, And Execution Wrappers

Purpose:

- operator-facing execution surfaces
- local CLI and supported execution wrappers
- Streamlit/UI, exporters, and HTML/PDF outputs

Primary files:

- `src/cli.py`
- `src/cli_commands.py`
- `src/cli_commands_search.py`
- `src/cli_commands_case.py`
- `src/cli_commands_evidence.py`
- `src/web_app.py`
- `src/web_ui.py`
- `src/email_exporter.py`
- `src/evidence_exporter.py`
- `src/legal_support_exporter.py`
- `src/dossier_generator.py`

Audit focus:

- argument contracts
- execution authority boundaries
- parity between CLI and MCP behavior
- unsafe or stale legacy entrypoints
- output/export correctness

Priority:

- `High`

### 2. MCP Tool Surface, Analytical Products, And Contract Boundaries

Purpose:

- tool registration
- MCP input models
- tool-level orchestration and formatting
- analytical product ownership and campaign-control boundaries

Primary files:

- `src/mcp_server.py`
- `src/mcp_models.py`
- `src/mcp_models_base.py`
- `src/mcp_models_search.py`
- `src/mcp_models_evidence.py`
- `src/mcp_models_case_analysis_manifest.py`
- `src/tools/search.py`
- `src/tools/evidence.py`
- `src/tools/case_analysis.py`
- `src/tools/legal_support.py`
- `src/tools/diagnostics.py`
- `src/tools/utils.py`

Footprint:

- `42` files
- about `10,399` lines

Audit focus:

- schema drift
- stale runtime compatibility
- payload-shape tolerance
- tool naming and discoverability
- MCP-only versus CLI-assisted execution boundaries
- missing wave-native or results-workspace MCP surfaces

Priority:

- `High`

### 3. Ingestion, Parsing, And Normalization

Purpose:

- OLM parsing
- attachment extraction
- body recovery and forensics
- chunking and ingestion pipelines
- analytics enrichment during ingest

Primary files:

- `src/ingest.py`
- `src/ingest_pipeline.py`
- `src/ingest_embed_pipeline.py`
- `src/ingest_reingest.py`
- `src/parse_olm.py`
- `src/parse_olm_normalization.py`
- `src/parse_olm_postprocess.py`
- `src/parse_olm_xml_parser.py`
- `src/chunker.py`
- `src/attachment_extractor.py`
- `src/body_recovery.py`
- `src/body_forensics.py`
- `src/conversation_segments.py`

Footprint:

- `22` files
- about `7,239` lines

Audit focus:

- message-body fidelity
- forwarded/reply reconstruction
- attachment-text recovery
- parser determinism
- ingestion idempotence and reingest safety

Priority:

- `High`

### 4. Storage, Schema, And Persistence

Purpose:

- SQLite schema and migrations
- evidence, custody, entities, attachments, matter persistence
- config/runtime path resolution

Primary files:

- `src/email_db.py`
- `src/db_schema.py`
- `src/db_schema_migrations.py`
- `src/db_queries.py`
- `src/db_queries_browse.py`
- `src/db_evidence.py`
- `src/db_evidence_queries.py`
- `src/db_custody.py`
- `src/db_entities.py`
- `src/db_attachments.py`
- `src/db_matter.py`
- `src/db_matter_persistence.py`
- `src/config.py`
- `src/storage.py`

Footprint:

- `14` files
- about `4,905` lines

Audit focus:

- migration safety
- persistence invariants
- evidence verification rules
- config caching and runtime path correctness
- separation of tracked `data/` and private runtime state

Priority:

- `High`

### 5. Retrieval, Archive Harvest, Ranking, And Context Expansion

Purpose:

- semantic and structured retrieval
- archive harvest and evidence banking
- query expansion
- reranking
- thread and reply context
- scan-state and candidate handling

Primary files:

- `src/retriever.py`
- `src/retriever_hybrid.py`
- `src/retriever_filtered_search.py`
- `src/retriever_threads.py`
- `src/retriever_query.py`
- `src/query_expander.py`
- `src/query_suggestions.py`
- `src/reranker.py`
- `src/colbert_reranker.py`
- `src/bm25_index.py`
- `src/sparse_index.py`
- `src/thread_intelligence.py`
- `src/thread_summarizer.py`
- `src/reply_pairing.py`
- `src/scan_session.py`
- `src/case_analysis_harvest.py`
- `src/tools/search_answer_context_impl.py`
- `src/tools/search_answer_context_runtime.py`

Footprint:

- `28` files
- about `6,306` lines

Audit focus:

- retrieval completeness
- archive-harvest breadth and evidence-bank sufficiency
- thread reconstruction correctness
- hybrid ranking behavior
- search-answer-context truncation/budget logic
- query-language handling for German-heavy corpora

Priority:

- `High`

### 6. Case Analysis, Wave Orchestration, And Legal-Support Core

Purpose:

- structured workplace-matter intake
- exhaustive mixed-source review
- wave execution orchestration and question closure
- chronology, comparator, issue matrix, memo, dashboard, contradiction, retaliation, and behavior products

Primary files:

- `src/case_analysis.py`
- `src/case_analysis_transform.py`
- `src/case_analysis_scope.py`
- `src/question_execution_waves.py`
- `src/wave_local_views.py`
- `src/case_operator_intake.py`
- `src/case_full_pack.py`
- `src/case_prompt_intake.py`
- `src/multi_source_case_bundle.py`
- `src/matter_evidence_index.py`
- `src/master_chronology.py`
- `src/comparative_treatment.py`
- `src/lawyer_issue_matrix.py`
- `src/lawyer_briefing_memo.py`
- `src/controlled_factual_drafting.py`
- `src/promise_contradiction_analysis.py`
- `src/trigger_retaliation_assessment.py`
- `src/actor_witness_map.py`
- `src/investigation_report.py`

Footprint:

- `66` files
- about `20,568` lines

Why this is the largest audit block:

- it is the dominant domain layer
- it contains the most matter-specific reasoning
- it depends on ingestion, retrieval, MCP, and bilingual metadata all being correct

Audit focus:

- evidence-vs-inference boundaries
- mixed-source completeness claims
- question closure rules
- wave-local versus full-matter product shaping
- output consistency across products
- German employment terminology handling
- missing-record accounting

Priority:

- `Highest`

### 7. NLP, Embeddings, Language, And Text Analytics

Purpose:

- dense/sparse embedding support
- language detection
- entity extraction
- sentiment and writing analysis

Primary files:

- `src/embedder.py`
- `src/multi_vector_embedder.py`
- `src/image_embedder.py`
- `src/language_detector.py`
- `src/language_detector_core.py`
- `src/language_detector_data.py`
- `src/nlp_entity_extractor.py`
- `src/entity_extractor.py`
- `src/sentiment_analyzer.py`
- `src/writing_analyzer.py`
- `src/bilingual_workflows.py`

Footprint:

- `11` files
- about `2,329` lines

Audit focus:

- German detection quality
- short-text failure modes
- multilingual edge cases
- model-loading/runtime fallback behavior
- whether analytics are strong enough to drive workflow decisions

Priority:

- `High` for German-first execution

### 8. Evaluation, Acceptance, QA-Eval, And Quality Gates

Purpose:

- QA evaluation fixtures and scoring
- legal-support acceptance projection
- workflow-quality verification and smoke gates
- training/fine-tuning helpers

Primary files:

- `src/qa_eval.py`
- `src/qa_eval_impl.py`
- `src/qa_eval_live.py`
- `src/qa_eval_scoring.py`
- `src/qa_eval_taxonomy.py`
- `src/legal_support_acceptance_projection.py`
- `src/training_data_generator.py`
- `src/fine_tuner.py`

Footprint:

- `15` files
- about `3,972` lines

Audit focus:

- captured-artifact drift
- realism of eval coverage
- German-case acceptance fidelity
- projection-layer normalization assumptions
- whether the verification layer enforces the live workflow contract

Priority:

- `Medium-High`

### 9. Documentation, Runbooks, And Operator Contracts

Purpose:

- public documentation
- MCP tool reference
- runtime tuning
- agent/operator runbooks
- prompt packs and templates
- execution-authority and resume contracts

Primary files:

- `README.md`
- `docs/README.md`
- `docs/MCP_TOOLS.md`
- `docs/RUNTIME_TUNING.md`
- `docs/agent/Plan.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/question_execution_query_packs.md`
- `docs/agent/Documentation.md`

Footprint:

- `docs/agent/` alone is `94` files and about `28,693` lines

Audit focus:

- docs-to-code parity
- stale operator guidance
- contradictory workflow instructions
- German-first execution alignment
- captured JSON artifact freshness

Priority:

- `High`

### 10. Scripts, Smoke Runs, And Operational Helpers

Purpose:

- acceptance matrix
- smoke tests
- QA-eval refresh
- workspace cleanup
- topology inventory
- workflow replay helpers

Primary files:

- `scripts/run_acceptance_matrix.sh`
- `scripts/ingest_smoke.py`
- `scripts/run_qa_eval.py`
- `scripts/refresh_qa_eval_captured_reports.py`
- `scripts/streamlit_smoke.py`
- `scripts/topology_inventory.sh`
- `scripts/clean_workspace.sh`

Footprint:

- `7` files
- about `979` lines

Audit focus:

- local-vs-CI parity
- stale assumptions about runtime profiles
- whether docs and scripts still agree
- whether automation exercises the actual campaign workflow

Priority:

- `Medium`

### 11. Tests And Verification Corpus

Purpose:

- regression protection
- contract validation
- fixture-backed behavior checks

Observed structure:

- `tests/` contains `400` files and about `59,675` lines
- most files are in the top-level `tests/` namespace with helper fixtures under `tests/helpers/`

Functional test clusters:

| Cluster | Approx. file count | Main purpose |
| --- | --- | --- |
| ingest/parse | `47` | OLM parsing, chunking, ingestion, recovery |
| retrieval/search | `38` | search, browse, thread/context, answer-context |
| MCP tools | `30` | tool registration and payload behavior |
| CLI | `23` | command-family and subcommand coverage |
| evidence/custody | `24` | evidence lifecycle and chain of custody |
| analysis/policy | `13` | behavior, language, comparative, retaliation |
| case-analysis | `7` | full legal-support / case-analysis contracts |
| UI | `11` | Streamlit/web-app surfaces |
| other | `144` | broad subsystem and regression coverage |

Audit focus:

- missing cross-subsystem integration tests
- stale snapshots
- German-language fixture realism
- runtime mismatch between tests and live MCP runs
- executable enforcement of workflow and ledger freshness

Priority:

- `High`

### 12. Local Runtime, Matter Inputs, And Results Control Plane

Purpose:

- actual local archive runtime
- local-only case materials and manifest-backed inputs
- local checkpoints, ledgers, and analysis outputs
- active-run and archive control-plane state

Primary paths:

- `private/runtime/chromadb/`
- `private/runtime/email_metadata.db`
- `private/tests/materials/`
- `private/tests/results/`
- `private/tests/results/_checkpoints/`

Observed structure:

- `private/tests/results/` is already organized by execution phase:
  - `00_intake_lock`
  - `01_corpus_inventory`
  - `02_intake_repair`
  - `03_exhaustive_run`
  - `04_evidence_index`
  - `05_master_chronology`
  - `06_behavior`
  - `07_comparators`
  - `08_issue_matrix`
  - `09_requests_preservation`
  - `10_contradictions`
  - `11_memo_draft_dashboard`
  - `_archive`
  - `_checkpoints`

Audit focus:

- tracked-vs-private boundary discipline
- whether local artifacts are authoritative, stale, or superseded
- whether active-run pointers, curated ledgers, and manifests stay synchronized
- whether result lanes mirror the runbooks accurately

Priority:

- `Medium-High`

## Largest Implementation Hotspots

These files are likely to be the most expensive deep-audit targets because of size and centrality:

| Lines | File | Primary function |
| --- | --- | --- |
| `665` | `src/tools/search_answer_context_runtime.py` | answer-context runtime path |
| `630` | `src/multi_source_case_bundle_helpers.py` | mixed-source case bundling |
| `620` | `src/cross_message_patterns.py` | cross-message pattern inference |
| `617` | `src/email_db.py` | central DB façade |
| `613` | `src/case_prompt_intake_helpers.py` | prompt-to-structured-intake heuristics |
| `596` | `src/qa_eval_scoring_helpers.py` | evaluation scoring logic |
| `586` | `src/qa_eval_taxonomy.py` | eval taxonomy and labels |
| `585` | `src/legal_support_acceptance_context.py` | acceptance/eval context |
| `568` | `src/matter_evidence_index_helpers.py` | evidence-index assembly |
| `560` | `src/investigation_report_sections_extra.py` | report output normalization |
| `556` | `src/db_evidence.py` | evidence persistence and verification |
| `552` | `src/controlled_factual_drafting.py` | drafting layer |

## Current Remediation Priority Order

1. `docs_runbook_and_execution_authority`
   Reason:
   the repo currently carries conflicting authority models between MCP-only runbooks and the supported local wave workflow
2. `entrypoints_and_mcp_contract_boundary`
   Reason:
   CLI wave execution, MCP analytical products, and active-results maintenance are not yet one coherent campaign surface
3. `local_runtime_and_results_control_plane`
   Reason:
   `active_run.json`, curated ledgers, and thin manifest inputs can drift apart and blur what is actually current
4. `retrieval_archive_harvest`
   Reason:
   evidence density across a `~20k` email corpus is still bounded by conservative harvest and selection caps
5. `case_analysis_wave_orchestration`
   Reason:
   wave-local views are still partly heuristic and not fully evidence-linked
6. `scripts_and_tests`
   Reason:
   verification still proves the local wrapper lane more strongly than the canonical campaign contract
7. `language_and_ingest_analytics`
   Reason:
   German-heavy corpus handling still depends on lightweight detection and post-hoc repair
8. `evaluation_quality_projection`
   Reason:
   QA and acceptance are still weaker at corpus-saturation quality measurement than at shape regression
9. `storage_and_export_governance`
   Reason:
   review-state and counsel-export gates need to remain explicit so autonomy claims do not outrun governance boundaries

## Immediate Follow-Up Questions For Deep Audit

- Which execution surface is the canonical campaign owner: MCP-only, local wave workflow, or one shared orchestration layer exposed through both?
- How should wave-local analytical views be derived from evidence linkage instead of term-matching heuristics?
- Which retrieval and archive-harvest caps are still too conservative for a `~20k` email corpus?
- How should ledger freshness be enforced after raw reruns so `active_run.json`, `question_register.md`, and `open_tasks_companion.md` cannot drift silently?
- Which language-analytics improvements belong in initial ingest rather than in reingest-only repair paths?

## Current Deliverable

This file is the refreshed functional decomposition map for the current repo state.

It is not yet:

- a bug list
- a remediation plan
- a line-by-line code review
