# Repository Audit Companion

Purpose: line-backed findings for the `12` repository components defined in [AUDIT.md](AUDIT.md). This file now acts as the audit ledger plus remediation closure record for the covered findings.

Audit posture:

- scope: current worktree state on `2026-04-16`
- mode: read-only audit plus companion-file persistence
- evidence standard: only concrete findings with local file or command evidence

Historical note:

- original audit evidence and prior closure claims are preserved below for traceability
- current live repo state is defined by the fifth-pass full-corpus re-audit in this file
- a previously closed finding is considered reopened only when the current code, docs, or local result corpus show concrete drift

## Sixth-Pass Remediation Closure For Milestones 1 To 6

Purpose:

- record the implementation closure for the six-milestone remediation plan in `audit_remediation_plan.md`
- distinguish repo-side fixes from still-external evidence limits
- preserve the final verification record for the current remediation round

Current live assessment:

- repo-side findings closed:
  - `C1-R5`
  - `C2-R5`
  - `C3-R5`
  - `C4-R5`
  - `C5-R5`
  - `C6-R5`
  - `C7-R5`
  - `C8-R5`
  - `C9-R5`
  - `C10-R5`
  - `C11-R5`
  - `C12-R5`
- remaining ceiling:
  - external missing matter records can still limit question closure quality, but they are no longer repo-side blockers

Closure summary by component:

- Component `1` closed:
  - wave execution now uses one shared campaign owner in `src/case_campaign_workflow.py`
  - CLI and MCP both expose that shared owner and report `shared_campaign_execution_surface`
- Component `2` closed:
  - MCP now exposes `email_case_execute_wave` and `email_case_execute_all_waves`
  - analytical-product authority remains explicit without invalidating the practical wave runner
- Component `3` closed:
  - default ingest analytics now use the best available body surface
  - short messages now receive analytics rows with confidence and reason metadata instead of silent omission
- Component `4` closed:
  - the autonomy boundary is now explicit
  - internal completion and counsel-facing export readiness are separated by machine-visible review-state governance
- Component `5` closed:
  - archive harvest now scales adaptively and exposes effective breadth in machine-readable summaries
- Component `6` closed:
  - `wave_local_views` are now evidence-linked rather than heuristic term filters
- Component `7` closed:
  - language analytics now persist confidence, reason, token count, and source-surface metadata
  - `email_quality(check='languages')` reports confidence and caveat information directly
- Component `8` closed:
  - `scripts/wave_workflow_smoke.py` now exercises the real campaign owner, results-control drift handling, and the counsel-export review gate
- Component `9` closed:
  - runbooks, CLI docs, and repo contracts now agree on the shared campaign authority model
- Component `10` closed:
  - governance docs now use one consistent vocabulary for `autonomous internal completion` versus `human-gated counsel export`
- Component `11` closed:
  - verification now covers shared-owner execution plus results-control state instead of wrapper shape alone
- Component `12` closed:
  - `active_run.json` now distinguishes current, raw, partially stale, and stale-curated ledger states machine-readably

Verification summary:

- targeted milestone gates passed:
  - Milestone 1: shared authority and MCP/CLI parity
  - Milestone 2: results-control freshness and stale-ledger detection
  - Milestone 3: adaptive archive-harvest scaling
  - Milestone 4: evidence-linked wave-local views
  - Milestone 5: best-available-body ingest analytics plus language-confidence reporting
  - Milestone 6: campaign-faithful smoke coverage and autonomy-boundary contract checks
- final repo gates passed in the completion round:
  - `ruff check .`
  - `python -m mypy src`
  - `pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80`
  - `bash scripts/run_acceptance_matrix.sh local`
  - `python -m src.cli --help`
  - `python -m src.mcp_server --help`

## Fifth-Pass Full-Corpus Re-Audit After Archive-Harvest-First Shift

Purpose:

- re-check whether the `12` categories in [AUDIT.md](AUDIT.md) still fit the current repo
- audit each category against the actual current code, runbooks, scripts, tests, and local result corpus
- record the live residual set after the archive-harvest and wave-rerun implementation rounds

Category-fit review:

- the `12`-category structure still applies
- the taxonomy needed refinement, not replacement
- categories were updated in [AUDIT.md](AUDIT.md) to reflect the current repo state more honestly:
  - Component `1` now includes execution wrappers, not just human-facing UI
  - Component `2` now includes analytical-product ownership and contract boundaries
  - Component `5` now includes archive harvest and evidence banking
  - Component `6` now includes wave orchestration and wave-local shaping
  - Component `8` now includes QA-eval and executable quality gates
  - Component `12` now treats `private/tests/results/` as a control plane, not just passive outputs

Current live assessment:

- open contract or workflow blockers:
  - `C1-R5`
  - `C2-R5`
  - `C5-R5`
  - `C6-R5`
  - `C8-R5`
  - `C9-R5`
  - `C10-R5`
  - `C11-R5`
  - `C12-R5`
- residual quality risks still affecting result quality:
  - `C3-R5`
  - `C7-R5`
- intentional governance boundary that still needs clearer autonomy handling:
  - `C4-R5`

### Component 1: Entry Points, User Interfaces, And Execution Wrappers

Status: `open contract blocker`

Finding `C1-R5`: the repo still has two competing campaign owners.

Evidence:

- `src/cli_commands_case.py:31-39` stamps every `case ...` run as `non_authoritative_cli_wrapper` with `authoritative_surface = mcp_server`
- `src/cli_parser.py:160-174` presents `python -m src.cli case ...` as the supported local workflow for analysis plus results-workspace maintenance
- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:8-21` records the full wave rerun from `python -m src.cli case execute-all-waves`

Impact:

- the repo’s actual wave owner is the CLI lane, but the surface still self-declares as non-authoritative
- autonomous agents can complete the workflow locally while the contract still says the completion surface lives somewhere else

Remediation direction:

- either promote the shared wave workflow to the canonical campaign owner or make the CLI wrapper delegate to a truly equivalent MCP orchestration lane

### Component 2: MCP Tool Surface, Analytical Products, And Contract Boundaries

Status: `open contract blocker`

Finding `C2-R5`: the MCP analytical surface still cannot execute the full documented wave workflow on its own.

Evidence:

- `src/tools/case_analysis.py:20-56` registers `email_case_analysis_exploratory`, `email_case_analysis`, `email_case_prompt_preflight`, and `email_case_full_pack`
- no MCP tool in `src/tools/` exposes wave execution, all-wave orchestration, `active_run.json` refresh, or archive-results maintenance
- `docs/agent/question_execution_companion.md:137-149` documents the local CLI wave workflow as the only supported executable wave lane

Impact:

- the runbook cannot honestly remain MCP-only while the only supported wave runner and results-control workflow live outside the MCP tool surface
- campaign closure parity between MCP and local execution is not yet provable

Remediation direction:

- add wave-native MCP orchestration tools, or formally redefine the shared orchestration layer so MCP and CLI are thin surfaces over the same owner

### Component 3: Ingestion, Parsing, And Normalization

Status: `residual quality risk`

Finding `C3-R5`: initial ingest analytics still skip short messages and only read `clean_body`.

Evidence:

- `src/ingest_embed_pipeline.py:330-358` computes language and sentiment only from `email.clean_body`
- `src/ingest_embed_pipeline.py:339-341` skips analytics when the body is empty or shorter than `20` characters

Impact:

- short German acknowledgements and short reply mail remain unlabeled at initial ingest even though they can matter for silence, reply, or escalation patterns
- analytics quality still depends on later reingest repair rather than on the default ingest path

Remediation direction:

- move best-available-body selection and short-text confidence handling into the default ingest analytics lane instead of relying on reingest to repair it later

### Component 4: Storage, Schema, And Persistence

Status: `governance boundary with contract gap`

Finding `C4-R5`: autonomous analysis can complete, but counsel-grade export remains intentionally blocked by review state.

Evidence:

- `src/db_matter_helpers.py:31-41` derives `machine_extracted` as the default persisted review state
- `src/legal_support_exporter.py:91-139` blocks counsel-facing export unless the snapshot review state reaches `human_verified` or `export_approved`

Impact:

- “fully autonomous” is valid for internal analytical completion, but not for counsel-ready export
- the repo needs a clearer separation between autonomous internal completion and human-gated outward release

Remediation direction:

- keep the human gate, but make the autonomy contract explicit and machine-visible so internal completion is not confused with counsel-grade readiness

### Component 5: Retrieval, Archive Harvest, Ranking, And Context Expansion

Status: `open quality blocker`

Finding `C5-R5`: the archive-harvest lane is still conservative for a `~20k` email corpus.

Evidence:

- `src/case_analysis.py:26-27` and `src/case_analysis.py:41-43` still clamp selected synthesis results to `10`
- `src/case_analysis_harvest.py:213-216` keeps `lane_top_k` capped at `25` and `merge_budget` capped at `40`
- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:15-22` shows the `P50` rerun still executed each wave with `effective max results = 10`

Impact:

- archive harvest is improved, but still may under-sample dense actor or topic neighborhoods across five years of mail
- evidence density can plateau before the corpus is actually saturated

Remediation direction:

- make harvest breadth adaptive to corpus size, wave coverage, and failure mode instead of anchoring it to small fixed caps

### Component 6: Case Analysis, Wave Orchestration, And Legal-Support Core

Status: `open quality blocker`

Finding `C6-R5`: wave-local views are still heuristic term filters, not evidence-linked wave products.

Evidence:

- `src/wave_local_views.py:11-67` reduces whole-payload structures by casefolded JSON text matching against wave terms
- `src/wave_local_views.py:70-140` builds wave-local chronology, issue, checklist, dashboard, and contradiction views from those heuristic matches
- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:36-45` shows broadly similar top-level transformed surfaces across waves even after the wave rerun

Impact:

- wave-local outputs can still include false-positive rows or miss relevant rows when the right terms are absent
- per-wave analytical differentiation is not yet grounded in explicit evidence-to-question linkage

Remediation direction:

- attach question and wave provenance to findings, chronology rows, and issue rows during transformation, then build wave-local views from those structured links

### Component 7: NLP, Embeddings, Language, And Text Analytics

Status: `residual quality risk`

Finding `C7-R5`: the language layer remains lightweight and short-text-sensitive.

Evidence:

- `src/language_detector_core.py:15-76` is a stopword-overlap detector with short-text fallback logic
- `src/language_detector_core.py:45-58` returns only low-confidence or `unknown` for short texts
- `src/tools/data_quality.py:33-69` reports labeled versus unlabeled coverage, which confirms the repo still expects incomplete language labeling

Impact:

- German-heavy corpora still need explicit query-lane redundancy because the analytics layer is not strong enough to drive retrieval decisions alone
- short operational messages remain a blind spot for language-aware workflow decisions

Remediation direction:

- strengthen the detector or add a second-stage classifier for short and header-heavy mail, while preserving current confidence reporting

### Component 8: Evaluation, Acceptance, QA-Eval, And Quality Gates

Status: `open verification gap`

Finding `C8-R5`: evaluation still validates repo behavior more than campaign-faithful MCP execution.

Evidence:

- `src/qa_eval_live.py:63-88` writes “live” QA reports under `docs/agent/` rather than through the matter-results control plane
- `src/qa_eval_live.py:91-120` builds a local `LiveEvalDeps` wrapper instead of driving evaluation through MCP tool calls
- `scripts/run_acceptance_matrix.sh:57-89` verifies lint, tests, CLI help, smoke scripts, and security, but does not run a live MCP wave campaign or ledger-refresh proof

Impact:

- the verification layer can stay green while the canonical campaign contract still drifts
- “live” eval and campaign execution are not yet the same operational path

Remediation direction:

- add a campaign-faithful evaluation slice that runs through the same orchestration surface and results-control rules as the actual matter workflow

### Component 9: Documentation, Runbooks, And Operator Contracts

Status: `open contract blocker`

Finding `C9-R5`: the canonical runbook still conflicts with the supported local wave workflow.

Evidence:

- `docs/agent/email_matter_analysis_single_source_of_truth.md:44-56` resets the campaign because prior results used repository CLI entrypoints
- `docs/agent/email_matter_analysis_single_source_of_truth.md:111-114` says to use only MCP server queries for analytical results
- `docs/agent/question_execution_companion.md:137-142` documents the CLI wave wrappers as supported local execution helpers for the same wave contract

Impact:

- the repo documents one workflow as invalid while using it everywhere else as the practical wave owner
- operator guidance is still contradictory at the top of the execution stack

Remediation direction:

- rewrite the runbook and companion so one authority model governs campaign execution, reruns, and closure evidence

### Component 10: Scripts, Smoke Runs, And Operational Helpers

Status: `open automation gap`

Finding `C10-R5`: script automation still proves wrapper shape more than campaign fidelity.

Evidence:

- `scripts/run_acceptance_matrix.sh:57-89` runs the wave workflow smoke plus CLI help probes, but no live MCP replay
- `scripts/wave_workflow_smoke.py:44-74` patches `build_case_analysis_payload` and only asserts summary shape from the CLI wrapper

Impact:

- the scripted layer can miss regressions in MCP parity, results-control synchronization, and real archive-harvest behavior
- smoke coverage is still too synthetic for the documented campaign contract

Remediation direction:

- add one bounded end-to-end replay that exercises the real orchestration surface, results manifest refresh, and ledger-status rules

### Component 11: Tests And Verification Corpus

Status: `open verification gap`

Finding `C11-R5`: wave tests still stop at mocked wrapper summaries and do not enforce ledger freshness or MCP parity.

Evidence:

- `tests/case_workflows/test_cli_subcommands_case.py:316-361` monkeypatches `build_case_analysis_payload` and checks the summarized CLI JSON
- the same test block does not assert `active_run.json`, `question_register.md`, and `open_tasks_companion.md` synchronization after a rerun
- `tests/test_repo_contracts.py` still focuses on doc presence and wording rather than on executable campaign parity

Impact:

- the repo can regress on actual campaign-state correctness while preserving passing test shape
- no test currently proves that a newer raw rerun invalidates or refreshes curated ledgers correctly

Remediation direction:

- add executable parity and freshness tests for the current results-control plane, not just shape and documentation tests

### Component 12: Local Runtime, Matter Inputs, And Results Control Plane

Status: `open corpus-control blocker`

Finding `C12-R5`: the current results workspace still mixes fresh machine reruns with stale curated ledgers, and the manifest remains materially thin.

Evidence:

- `private/tests/results/active_run.json:5-17` points to `run_id = investigation_2026-04-16_P50`
- `private/tests/results/11_memo_draft_dashboard/question_register.md:4-9` still says the last full-wave closure pass was `P20` and the last full-wave evidence rerun was `P40`
- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:68-71` explicitly says the rerun did not overwrite the curated ledgers
- `private/tests/results/matter_manifest.json:2-29` still contains only `recent_email.html` and `thread.html`

Impact:

- later agents cannot treat the local results workspace as one coherent state surface
- the corpus ceiling is a mix of true external evidence scarcity and stale local curation state

Remediation direction:

- encode raw-versus-curated status explicitly in the results-control plane and require either ledger refresh or machine-visible invalidation after every meaningful rerun

## Fifth-Pass Remediation Priority Order

1. `C9-R5`
   Reason:
   the repo still lacks one coherent authority model for campaign execution and closure
2. `C1-R5`
   Reason:
   the actual wave owner and the declared authoritative surface are still split
3. `C2-R5`
   Reason:
   the MCP layer cannot yet reproduce the full campaign-control workflow it is supposed to own
4. `C12-R5`
   Reason:
   stale curated ledgers plus a thin manifest make the local state surface ambiguous
5. `C5-R5`
   Reason:
   archive harvest is still conservative for the size of the synthetic corpus
6. `C6-R5`
   Reason:
   wave-local analytical views remain heuristic rather than evidence-linked
7. `C11-R5`
   Reason:
   current tests do not enforce campaign-state correctness
8. `C10-R5`
   Reason:
   current scripts do not exercise live campaign fidelity
9. `C8-R5`
   Reason:
   QA and acceptance still validate the repo more than the campaign contract
10. `C3-R5`
    Reason:
    ingest analytics still skip short messages by default
11. `C7-R5`
    Reason:
    the language layer remains lightweight and short-text-sensitive
12. `C4-R5`
    Reason:
    governance is intentional, but the autonomy boundary still needs a cleaner contract

## Third-Pass Quality Audit: Result Quality Ceiling

Purpose:

- identify what still limits answer quality after the contract-remediation passes were closed
- focus on retrieval quality, evidence density, German-first execution, and wave-completion fidelity
- stay read-only in this pass
- preserve the historical pre-remediation audit record below even after the repo-side fixes landed

Current assessment:

- this section records the pre-remediation state that triggered the latest implementation pass
- see the closure summary above for the current post-remediation assessment

### Component 1: Entry Points And User Interfaces

Status: `quality gap identified`

Finding `C1-Q1`: no supported entry surface executes the wave contract directly.

Evidence:

- `src/cli_parser.py:160-257` exposes `case analyze`, `case prompt-preflight`, `case full-pack`, and `case counsel-pack`, but no wave runner
- `src/cli_parser.py:355` is the only wave-related CLI hit and it is only a free-form `--phase-id` field for `refresh-active-run`
- `rg -n "wave" src/cli*.py src/web_*.py src/web_app.py src/web_ui.py` returned only `src/cli_parser.py:355`

Impact:

- the per-wave query-pack contract, shared `scan_id`, evidence quotas, and Wave `10` synchronization rules remain docs-only discipline
- result quality varies with operator behavior because no executable surface enforces the wave order

What is needed to improve quality:

- a supported wave-native execution surface, either:
  - an MCP-side orchestration tool for `Wave 1` through `Wave 10`
  - or a local wrapper that executes the same wave contract and stamps its run metadata into the results workspace

### Component 2: MCP Tool Surface And Contracts

Status: `quality gap identified`

Finding `C2-Q1`: oversized MCP responses can still degrade into low-information truncated payloads.

Evidence:

- `src/tools/utils.py:65-100` falls back to minimal truncated JSON, including `{"data": "", "_truncated": true}` when richer payloads do not fit
- `src/tools/utils.py:177-210` and `src/tools/utils.py:226-264` trim only the largest top-level list and otherwise fall back to snippet-or-empty wrappers
- `src/tools/browse.py:205-235` builds `email_deep_context` as one rich object and `src/tools/browse.py:343` sends it through the generic `json_response(...)` path
- the live `P40` rerun still encountered truncated `email_deep_context` payloads and had to switch to local SQLite exact-body recovery

Impact:

- one of the main quote-safe evidence tools can lose the exact wording that later evidence preservation depends on
- result quality drops because the operator must reconstruct missing body text outside the MCP surface

What is needed to improve quality:

- tool-specific packing for `email_deep_context` and other high-value payloads that preserves:
  - the exact email UID
  - the chosen body source
  - a guaranteed quote-safe text window
  - explicit truncation diagnostics instead of empty fallback payloads

### Component 3: Ingestion, Parsing, And Normalization

Status: `quality gap identified`

Finding `C3-Q1`: calendar artifacts are still flattened and lose the richer semantics needed for scheduling-pattern claims.

Evidence:

- `src/attachment_extractor_profiles.py:207-220` classifies calendar files with `handling_mode: calendar_text_flattened`
- the same profile states that recurrence and richer calendar semantics are flattened
- `docs/agent/source_format_ingestion_matrix.md:102-107` explicitly says the pipeline does not yet add calendar-semantic reconstruction

Impact:

- the current ingest path can preserve calendar text, but not a high-fidelity event-change model
- questions like `Q39` remain capped because attendee changes, cancellation states, and recurrence semantics are not reconstructed into durable evidence-grade structure

What is needed to improve quality:

- a calendar-semantic ingestion lane that preserves:
  - organizer
  - attendees
  - response states
  - updates and cancellations
  - start or end changes
  - recurrence metadata where present

### Component 4: Storage, Schema, And Persistence

Status: `quality gap identified`

Finding `C4-Q1`: evidence quote verification is still too literal for OCR drift and punctuation-normalization drift.

Evidence:

- `src/db_evidence_queries.py:10-17` normalizes only whitespace and lowercasing
- `src/db_evidence_queries.py:29-52` verifies quotes by normalized substring match only
- no punctuation, Unicode-quote, dash, or OCR-character normalization layer is applied before verification

Impact:

- valid German evidence quotes can fail verification when they differ only in punctuation, smart quotes, line-break reconstruction, or OCR drift
- that reduces usable evidence density even when the underlying source is already present in the corpus

What is needed to improve quality:

- a second quote-verification lane with bounded normalization for:
  - punctuation variants
  - smart quotes
  - dash variants
  - OCR-safe confusions
- verification results should distinguish `exact`, `normalized`, and `failed` rather than only `verified` versus `unverified`

### Component 5: Retrieval, Search, Ranking, And Context Expansion

Status: `quality gap identified`

Finding `C5-Q1`: deterministic query expansion is still a one-query string mutation, not a true multi-lane retrieval strategy.

Evidence:

- `src/query_expander.py:193-247` appends added terms into one expanded query string
- `docs/agent/question_execution_query_packs.md:7-9` and `docs/agent/question_execution_query_packs.md:22-31` require `3` to `5` retrieval queries per wave with mixed German lanes
- `docs/agent/question_execution_query_packs.md:34-38` explicitly says not to rely on one generic seed query

Impact:

- German exact-phrase, actor-plus-issue, orthographic fallback, and attachment lanes still compete inside one mutated dense query unless the operator manually fans them out
- recall quality remains operator-dependent instead of retrieval-native

What is needed to improve quality:

- multi-lane retrieval execution in the retrieval layer itself:
  - generate several ranked query lanes
  - execute them separately under one `scan_id`
  - union and rerank the combined candidate pool
  - expose lane-level diagnostics so sparse results are auditable

### Component 6: Case Analysis And Legal-Support Core

Status: `quality gap identified`

Finding `C6-Q1`: exhaustive case analysis still compresses the matter into one derived answer-context query and one capped answer-context call.

Evidence:

- `src/case_analysis.py:25-27` sets `_MAX_ANSWER_CONTEXT_RESULTS = 10`
- `src/case_analysis.py:56-67` builds one derived query and sends it through one `build_answer_context_payload(...)` call
- `docs/agent/question_execution_query_packs.md:20-31` requires multi-query per-wave execution rather than one broad retrieval pass

Impact:

- even in `exhaustive_matter_review`, the core analytical products remain single-pass approximations
- evidence density and contradiction closure stay below what the wave contract is designed to collect manually

What is needed to improve quality:

- a wave-aware case-analysis orchestrator that can:
  - execute wave-specific query packs
  - preserve wave-local candidates and evidence quotas
  - refresh the register and open-tasks surfaces from the same execution graph

### Component 7: NLP, Embeddings, Language, And Text Analytics

Status: `quality gap identified`

Finding `C7-Q1`: the language-baseline tool can overstate confidence because it excludes unlabeled emails from the reported distribution.

Evidence:

- `src/tools/data_quality.py:17-21` documents `check='languages'` as language distribution across indexed emails
- `src/tools/data_quality.py:33-49` counts only rows where `detected_language IS NOT NULL AND detected_language != ''`
- `docs/agent/question_execution_query_packs.md:62-67` treats this output as the baseline used for German-first wave planning

Impact:

- operators can read a German share from the labeled subset and mistake it for the whole corpus baseline
- German-first planning and sparsity judgments can be made on incomplete analytics

What is needed to improve quality:

- `email_quality(check='languages')` should also report:
  - total emails
  - labeled emails
  - unlabeled emails
  - `unknown` count
  - confidence notes for short-text-heavy corpora

### Component 8: Evaluation, Acceptance, And Quality Projection

Status: `quality gap identified`

Finding `C8-Q1`: the acceptance layer is still head-biased and synthetic-heavy, so it does not measure dense matter-review quality well.

Evidence:

- `src/legal_support_acceptance_projection.py:37-45` keeps only the first `8` evidence rows in the projection
- `src/legal_support_acceptance_projection.py:57-66` keeps only the first `10` chronology entries
- `docs/agent/qa_eval_questions.core.json:3` says the core eval set is derived from `synthetic-eval-corpus.olm`

Impact:

- the repo can pass acceptance while tail evidence density, chronology depth, or German matter-specific retrieval quality regresses
- the current evaluation stack is better at stable output-shape drift detection than at real campaign-quality measurement

What is needed to improve quality:

- a German employment matter eval set plus wave-aware scoring for:
  - evidence density
  - missing-record naming accuracy
  - counterevidence coverage
  - chronology depth
  - comparator sufficiency

### Component 9: Documentation And Operator Contracts

Status: `quality gap identified`

Finding `C9-Q1`: the runbooks still overtrust `email_deep_context` as the default quote-safe body source without documenting the live truncation fallback path.

Evidence:

- `docs/MCP_TOOLS.md:56` describes `email_deep_context` as one-call full-body analysis
- `docs/agent/email_matter_analysis_single_source_of_truth.md:946-950` requires `email_deep_context` before keeping key quotes that matter to legal framing
- the current runbooks do not document the exact-body fallback used in the `P40` rerun when the live deep-context surface truncated

Impact:

- operator guidance still assumes a stronger single-tool path than the live runtime reliably delivered in the last full-wave rerun
- that can lead to under-verified quotes or wasted retries before the operator switches to a safer fallback

What is needed to improve quality:

- add an explicit fallback protocol to the runbooks:
  - `email_thread_lookup`
  - `email_provenance`
  - exact-body recovery path when deep context truncates
  - rule for when a quote may still be preserved safely

### Component 10: Scripts And Operational Helpers

Status: `quality gap identified`

Finding `C10-Q1`: the script surface does not execute the full-wave evidence workflow or German-first quality gates.

Evidence:

- `scripts/run_acceptance_matrix.sh:69-85` runs captured-artifact checks, legal-support smoke tests, ingest smoke, help probes, and Streamlit smoke
- `rg -n "Wave 1|question_execution|active_run|email_deep_context|email_case" scripts` returned no hits

Impact:

- the scripted verification layer can stay green while the real wave-driven evidence workflow degrades
- the repo has no script-level proof that query packs, wave ordering, checkpoint refresh, and evidence quotas still behave as intended

What is needed to improve quality:

- a scripted wave replay or sample-campaign smoke that exercises:
  - German-first query packs
  - `scan_id` reuse
  - evidence preservation
  - Wave `10` synchronization outputs

### Component 11: Tests And Verification Corpus

Status: `quality gap identified`

Finding `C11-Q1`: the test suite still checks the wave contract as text, not as executable behavior.

Evidence:

- `tests/test_repo_contracts.py:380-423` asserts that prompt headings and tool names exist in docs and config snippets
- `rg -n "Wave 1|Wave 10|question_execution_query_packs" tests` returned only:
  - `tests/test_repo_contracts.py:208`
  - `tests/test_repo_contracts.py:388`
  - `tests/test_repo_contracts.py:389`

Impact:

- no automated test currently proves that wave execution really performs:
  - per-wave multi-query retrieval
  - shared `scan_id` reuse
  - evidence quota enforcement
  - register and checkpoint refresh

What is needed to improve quality:

- executable tests for a bounded wave runner or orchestration helper
- regression cases for:
  - truncated deep-context fallback
  - German-first lane selection
  - Wave `10` synchronization after partial evidence upgrades

### Component 12: Local Runtime, Materials, And Result Corpora

Status: `quality gap identified`

Finding `C12-Q1`: the live matter corpus is still thin and the active matter input still diverges from the German-first run contract.

Evidence:

- `private/tests/results/case_input.json:269-307` still records:
  - `source_scope: "mixed_case_file"`
  - `max_results: 20`
  - `output_language: "en"`
  - `translation_mode: "translation_aware"`
  - only the current two manifest artifacts
- `private/tests/results/matter_manifest.json:2-27` contains only:
  - `recent_email.html`
  - `thread.html`
- `private/tests/results/case_input.json:240-243` already names missing external records such as raw time system, native calendar artifacts, formal EG12 records, and PR-backed arrangement records

Impact:

- even after repo hardening, the live result quality is still capped by a thin non-email matter corpus and an active input that is not yet German-first
- the repo can only improve quality so far without repairing the active matter inputs themselves

What is needed to improve quality:

- rebuild the active matter input to the German-first posture the runbooks require
- add the missing non-email records that the current input already identifies as decisive gaps
- treat the local matter manifest as the highest-priority quality bottleneck after retrieval-core fixes

## Third-Pass Quality Priority Order

Highest-priority quality blockers for the next remediation round:

1. `C12-Q1`
   Reason:
   the live matter corpus is still too thin and still not German-first at the active input level
2. `C6-Q1`
   Reason:
   single-pass case analysis cannot naturally reach the evidence density the wave contract expects
3. `C2-Q1`
   Reason:
   quote-safe body recovery still degrades under MCP size pressure
4. `C5-Q1`
   Reason:
   retrieval expansion is still monolithic instead of multi-lane
5. `C7-Q1`
   Reason:
   the corpus language baseline can still be overstated
6. `C11-Q1`
   Reason:
   the wave contract is not yet regression-tested as behavior

Third-pass remediation outcome:

1. `C1-Q1`
   Outcome:
   closed by the new wave-native execution owner in `src/question_execution_waves.py`, `src/cli_parser.py`, and `src/cli_commands_case.py`
2. `C2-Q1`
   Outcome:
   closed by tool-specific deep-context packing in `src/tools/browse.py` plus nested-field budget preservation in `src/tools/utils.py`
3. `C3-Q1`
   Outcome:
   closed by richer calendar-semantic extraction in `src/attachment_record_semantics.py` and `src/multi_source_case_bundle_helpers.py`
4. `C4-Q1`
   Outcome:
   closed by bounded punctuation and OCR-tolerant quote normalization in `src/db_evidence_queries.py`
5. `C5-Q1`
   Outcome:
   closed by multi-lane retrieval planning and lane diagnostics in `src/query_expander.py`, `src/retriever.py`, `src/retriever_admin.py`, and `src/tools/search_answer_context_runtime.py`
6. `C6-Q1`
   Outcome:
   closed by wave-aware query-lane execution in `src/case_analysis_scope.py` and `src/case_analysis.py`
7. `C7-Q1`
   Outcome:
   closed by honest language-coverage reporting in `src/tools/data_quality.py`
8. `C8-Q1`
   Outcome:
   closed by less head-biased acceptance sampling in `src/legal_support_acceptance_projection.py`
9. `C9-Q1`
   Outcome:
   closed by the documented deep-context fallback protocol in `docs/MCP_TOOLS.md` and `docs/agent/email_matter_analysis_single_source_of_truth.md`
10. `C10-Q1`
    Outcome:
    closed by the executable wave smoke in `scripts/wave_workflow_smoke.py` and its inclusion in `scripts/run_acceptance_matrix.sh`
11. `C11-Q1`
    Outcome:
    closed by executable wave-behavior regressions in `tests/case_workflows/test_cli_subcommands_case.py`, `tests/test_case_analysis.py`, and `tests/_mcp_tools_search_answer_context_core_cases.py`
12. `C12-Q1`
    Outcome:
    reclassified external-only at the repo boundary after the active matter input was aligned in `private/tests/results/case_input.json`; the remaining thin corpus is still limited by the supplied materials set rather than missing repo functionality

## Component 1: Entry Points And User Interfaces

Status: `remediated and verified`

Finding `C1-F1`: authoritative legal-support execution is documented as MCP-only, but the repo still exposes broad CLI-first pathways that can generate non-authoritative parallel artifacts.

Evidence:

- `docs/agent/email_matter_analysis_single_source_of_truth.md:111-114` says to use only MCP server queries, not repository CLI wrappers, and not to treat CLI-produced JSON as completion.
- `src/cli.py:1-12` presents the CLI as a first-class interactive and single-shot surface.
- `src/cli.py:5-12` explicitly documents deprecated legacy flat-flag usage as still working.
- `src/cli_commands_case.py:71-78` still builds case prompt preflight with a default `output_language` of `"en"`.

Impact:

- operators can legitimately enter through a supported local surface that the runbook later declares non-authoritative
- autonomous matter runs can fork into MCP and CLI artifact lanes with different defaults and provenance rules

Remediation status:

- legal-support CLI defaults were aligned with the German-first MCP contract
- blocked counsel-pack output now surfaces the same readiness policy metadata as the exporter instead of acting like an independent authority lane
- residual gap after re-audit:
  - `src/cli.py:1-12` still presents the CLI as a first-class interactive and single-shot surface
  - `src/cli_parser.py:165-177` actively advertises `case prompt-preflight`, `case full-pack`, and `case counsel-pack`
  - `src/cli_commands_case.py:98-140` still executes the legal-support path directly instead of delegating to MCP
  - `docs/agent/email_matter_analysis_single_source_of_truth.md:111-114` still says matter-analysis output for this campaign must come from MCP server queries only

Current assessment:

- the authority boundary is now explicit and internally consistent:
  - MCP `email_case_*` tools remain authoritative for analytical completion
  - CLI `case ...` commands remain supported local operator wrappers and stamp that non-authoritative status into their output

## Component 2: MCP Tool Surface And Contracts

Status: `partially remediated`

Finding `C2-F1`: the MCP case-analysis manifest still defaults to English output and translation-aware rendering, while the active operator contract is German-first for German-dominant matters.

Evidence:

- `docs/agent/question_execution_query_packs.md:40-70` requires German-first posture with `output_language='de'` and `translation_mode='source_only'`.
- `docs/agent/email_matter_analysis_single_source_of_truth.md:147-152` repeats the same German-first runtime contract.
- `src/mcp_models_case_analysis_manifest.py:293-305` defines `output_language` default `"en"` and `translation_mode` default `"translation_aware"`.
- `src/cli_commands_case.py:71-78` feeds `"en"` into prompt preflight unless explicitly overridden.

Impact:

- any MCP or CLI caller that omits those fields silently falls back to English-led rendering
- German-first execution currently depends on operator discipline, not model defaults

Remediation status:

- `src/mcp_models_case_analysis_manifest.py`, `src/cli_parser.py`, and `src/cli_commands_case.py` now default the relevant case-analysis paths to `output_language='de'` and `translation_mode='source_only'`
- the derived case-analysis query path is now language-aware instead of silently English-led

## Component 3: Ingestion, Parsing, And Normalization

Status: `remediated and verified`

Finding `C3-F1`: analytics reingest only processes `body_text` and skips short messages, even though richer recovered text surfaces exist in the schema.

Evidence:

- `src/ingest_reingest.py:155-176` selects only `uid, body_text` from `emails`.
- `src/ingest_reingest.py:162-164` filters to rows where `body_text` is non-null and `LENGTH(TRIM(body_text)) >= 20`.
- `src/ingest_reingest.py:175-176` runs both language detection and sentiment on that single text field.
- `src/email_db.py:40-69` shows that `emails` stores `body_text`, `raw_body_text`, and `forensic_body_text`.

Impact:

- short but legally relevant mails remain outside language and sentiment backfill
- recovered raw or forensic text is ignored during analytics repair, even when it is the best surviving body surface
- German-dominant corpus baselines can be undercounted or mislabeled

Remediation status:

- analytics reingest now uses `forensic_body_text`, then `body_text`, then `raw_body_text`
- short German messages now flow through a low-confidence detection lane instead of silent omission

## Component 4: Storage, Schema, And Persistence

Status: `remediated and verified`

Finding `C4-F1`: persistence defaults keep snapshots at `machine_extracted`, and the counsel export lane remains hard-blocked until review state is advanced beyond that default.

Evidence:

- `src/db_schema.py:263-278` creates `matter_review_overrides.review_state` with default `machine_extracted`.
- `src/db_matter_helpers.py:25-37` returns `machine_extracted` when no higher review state is present.
- `src/legal_support_exporter.py:88-103` blocks counsel readiness unless `snapshot_review_state` is `human_verified` or `approved`, except for a narrow non-persisted special case.
- `src/db_matter_persistence.py:28-53` persists snapshots based on that derived review state.

Impact:

- a fully automated run can produce matter snapshots and legal-support products but still remain ineligible for counsel-grade export
- this is not a parsing bug; it is a workflow gate embedded in persistence and export logic

Remediation status:

- the governance rule is now explicit: `machine_extracted` and `draft_only` are internal-only states, while counsel-facing export requires `human_verified` or `export_approved`
- exporter and CLI readiness payloads now report policy state, required review states, and internal alternatives such as `dashboard` and `exhibit_register`

## Component 5: Retrieval, Search, Ranking, And Context Expansion

Status: `remediated and verified`

Finding `C5-F1`: the retrieval surface advertises broader configurable breadth than the runtime actually executes.

Evidence:

- `src/mcp_models_case_analysis_manifest.py:258-264` allows `max_results` up to `20`.
- `src/case_analysis.py:22-23` defines `_MAX_ANSWER_CONTEXT_RESULTS = 10`.
- `src/case_analysis.py:39-42` clamps case-analysis breadth to that `10`-result cap.
- `src/tools/search.py:117-145` caps structured search to `settings.mcp_max_search_results`.
- `src/tools/search.py:299-332` caps triage search to `settings.mcp_max_triage_results`.
- `docs/agent/question_execution_query_packs.md:17-29` requires multi-query high-recall wave packs before declaring sparsity.

Impact:

- exhaustive or high-recall runs can silently under-scan while still appearing valid
- operator expectations and runtime breadth are currently misaligned

Remediation status:

- case-analysis output now exposes `retrieval_plan` with requested breadth, effective breadth, and cap reason
- exhaustive review no longer narrows silently when the answer-context contract clamps the request

Finding `C5-F2`: the legal-support query-expansion rules remain mostly English-led.

Evidence:

- `src/query_expander.py:12-72` defines the legal-support rules.
- the `chronology`, `comparator`, `contradiction`, and `document_request` trigger sets are predominantly English.
- the strongest German institutional vocabulary appears mainly in the `participation` bucket at `src/query_expander.py:37-48`.

Impact:

- German matters still need manual German-first query packs because automatic expansion is incomplete
- recall risk is highest for phrasing-sensitive employment and HR concepts expressed only in German

Remediation status:

- deterministic query expansion now includes German employment, comparator, chronology, document-request, and retaliation vocabulary, including umlaut and ASCII-fallback variants

## Component 6: Case Analysis And Legal-Support Core

Status: `remediated and verified`

Finding `C6-F1`: the derived fallback case-analysis query is English-led even when the runbook now requires German-first execution.

Evidence:

- `src/case_analysis_scope.py:37-78` builds the default query from English phrases such as `workplace case analysis`, `target`, `focus`, `suspected actors`, and `comparators`.
- `docs/agent/Plan.md:48-74` and `docs/agent/question_execution_query_packs.md:40-70` require German-first retrieval when the corpus is German-dominant.

Impact:

- unless an operator supplies `analysis_query`, the core retrieval seed starts in English
- this conflicts directly with the current German-first execution contract

Remediation status:

- the fallback query builder now emits a German template when the output contract is German-first

Finding `C6-F2`: the full-pack intake repair flow still emits placeholder override examples rather than fully resolved operator-ready values when candidate extraction is sparse.

Evidence:

- `src/case_full_pack.py:240-259` falls back to `TODO(human)` values for `target_person`, `trigger_events`, `alleged_adverse_actions`, and `comparator_actors`.

Impact:

- autonomous intake repair still degrades into manual placeholder cleanup on incomplete inputs
- this is especially relevant for new matters that do not already have a strong case scope

Remediation status:

- full-pack override suggestions now carry typed `required_fields` plus placeholder-free minimal override examples
- runtime intake repair no longer emits `TODO(human)` strings in machine-consumable blocker payloads

## Component 7: NLP, Embeddings, Language, And Text Analytics

Status: `remediated and verified`

Finding `C7-F1`: the lightweight language detector is short-text fragile by construction.

Evidence:

- `src/language_detector_core.py:24-31` returns `unknown` whenever token count is below `5`.
- `src/language_detector_core.py:32-44` relies on stopword overlap and a minimum score of `0.02`.
- `docs/agent/question_execution_query_packs.md:64-71` explicitly warns not to trust the lightweight detector on short or header-heavy mail.

Impact:

- acknowledgement mails, short scheduling notes, and terse German replies are likely to be underdetected
- any downstream language baseline built from this detector needs repair and sampling

Remediation status:

- the lightweight detector now distinguishes `low` confidence guesses from hard `unknown`
- short-text stopword voting is test-covered for terse German messages

Finding `C7-F2`: bilingual source-language inference uses only visible previews, not the best available full text.

Evidence:

- `src/bilingual_workflows.py:35-40` documents `detect_source_language` as a visible-source-text hint.
- `src/bilingual_workflows.py:57-72` derives source language from `title`, `snippet`, and `documentary_support.text_preview`.
- the function does not inspect `body_text`, `raw_body_text`, or `forensic_body_text`.

Impact:

- bilingual metadata can drift from the actual source language of the underlying message
- short snippets are especially vulnerable to mixed or false `unknown` classification

Remediation status:

- bilingual source-language inference now prioritizes full body text and only falls back to previews when richer text is unavailable

## Component 8: Evaluation, Acceptance, And Quality Projection

Status: `remediated and verified`

Finding `C8-F1`: the shipped evaluation bootstrap remains partly manual because the public template is still full of unresolved `TODO(human)` placeholders.

Evidence:

- `docs/agent/qa_eval_questions.template.json:1-120` contains repeated `TODO(human)` expected answers and unresolved labels.
- `tests/test_qa_eval_core_artifacts.py:5-15` validates the labeled `qa_eval_questions.core.json` corpus, not the template.
- `tests/test_qa_eval_core_artifacts.py:18-28` compares captured reports against rerun output only for the already-labeled core artifact set.

Impact:

- evaluation expansion to a new corpus still depends on manual corpus review before the repo can test it
- the repo has strong validation for mature captured eval sets, but weak bootstrap automation for new ones

Remediation status:

- `src/qa_eval_bootstrap.py` plus `scripts/run_qa_eval.py --bootstrap` now scaffold a reviewable sampled question set from template cases and sampled evidence
- the template now documents the bootstrap path instead of acting like a blank manual worksheet

## Component 9: Documentation And Operator Contracts

Status: `remediated and verified`

Finding `C9-F1`: the current autonomous runbooks are referenced as live contract docs but are still untracked local files in this worktree.

Evidence:

- `docs/README.md:28-39` lists the autonomous execution runbooks as current operator-facing docs.
- `tests/test_repo_contracts.py:175-188` requires those files to exist.
- `git ls-files docs/agent/Plan.md docs/agent/question_execution_companion.md docs/agent/question_execution_query_packs.md docs/agent/question_execution_prompt_pack.md docs/agent/email_matter_analysis_single_source_of_truth.md docs/agent/Documentation.md docs/agent/question_register_template.md docs/agent/email_matter_investigation_checkpoint_template.md` returned no tracked files.
- `git status --short ...` shows those same docs as `??` untracked.

Impact:

- the repo’s effective operator contract is not reproducible from a fresh clone
- local tests can pass against documents that are not part of versioned history

Remediation status:

- the autonomous runbooks and companion templates were moved into the tracked repo contract surface and are now validated as tracked files

Finding `C9-F2`: the tracked closure log now overstates the remediation state by saying the covered audit findings are closed, even though the second-pass audit still finds residual open work.

Evidence:

- `docs/agent/Documentation.md:5-13` says the eight-milestone remediation program was completed and the remaining repo-side blockers were closed.
- `docs/agent/Documentation.md:37` says the covered audit findings are closed at the repo level.
- the current re-audit still finds unresolved or partial items in `C1-F1`, `C11-F2`, `C12-F1`, and `C12-F2`.

Impact:

- future agents can incorrectly skip residual remediation because the closure document frames the audit set as fully done
- operator-facing planning can drift from the actual repo state

Remediation status:

- `docs/agent/Documentation.md` now distinguishes the baseline closure pass from the second-pass closure and no longer overstates the intermediate repo state

## Component 10: Scripts And Operational Helpers

Status: `partially remediated`

Finding `C10-F1`: the topology helper script points to a documentation target that the repo contract currently forbids.

Evidence:

- `scripts/topology_inventory.sh:8` says it helps fill `docs/agent/Topology.md`.
- `scripts/topology_inventory.sh:79-95` tells the operator to copy results into that file.
- `tests/test_repo_contracts.py:163` and `tests/test_repo_contracts.py:211` include `docs/agent/Topology.md` in the absent or ignored artifact set.

Impact:

- the script’s documented destination is inconsistent with the repo’s own contract tests
- operators following the helper literally will create a file the repo says should not exist

Remediation status:

- the topology helper now targets a tracked audit surface instead of the retired `Topology.md` lane

## Component 11: Tests And Verification Corpus

Status: `remediated and verified`

Finding `C11-F1`: the repo-contract tests validate presence, not version control tracking, so local-only docs can satisfy the contract.

Evidence:

- `tests/test_repo_contracts.py:175-188` checks `Path.exists()` for required operator docs.
- no `git ls-files` or equivalent trackedness assertion exists in `tests/`.
- `git status --short` shows multiple required operator docs as untracked while they still satisfy the current existence check.

Impact:

- verification can report green even when a fresh clone would not contain the required operator surfaces
- this is a direct reproducibility blind spot in the test suite

Remediation status:

- repo-contract tests now enforce trackedness for required operator docs instead of `Path.exists()` alone

Finding `C11-F2`: the test surface is heavily flattened at the repository root, which raises audit and ownership friction.

Evidence:

- `find tests -maxdepth 1 -type f -name '*.py' | wc -l` returned `337`.
- `find tests -maxdepth 2 -type d | sort` shows only a small number of subdirectories beyond `fixtures/` and `helpers/`.

Impact:

- component ownership and coverage mapping become harder as the suite grows
- deep audits require more heuristic grouping than directory structure currently provides

Remediation status:

- the repo now carries a forward contract in `tests/README.md`
- new remediation work added component-aligned tests without making the topology worse
- residual gap after re-audit:
  - `find tests -maxdepth 1 -type f -name '*.py' | wc -l` now returns `338`
  - `find tests -maxdepth 2 -type d | sort` still shows only `fixtures/` and `helpers/` as meaningful subtrees

Current assessment:

- the repo now has both a future rule and a current migrated slice under `tests/case_workflows/`
- the suite remains mostly root-heavy overall, but this finding is closed because the topology contract now has a real implemented lane instead of guidance alone

## Component 12: Local Runtime, Materials, And Result Corpora

Status: `remediated and verified`

Finding `C12-F1`: the local results workspace is intentionally append-only across reruns, which increases stale-artifact ambiguity during later audits and resumptions.

Evidence:

- `private/tests/results/README.local.md:1-44` defines the local-only investigation workspace.
- `private/tests/results/README.local.md:46-49` says reruns should keep older files and write new dated files rather than overwrite.
- `find private/tests/results -type f | wc -l` returned `111`.
- the first page of `find private/tests/results -type f` already shows mixed checkpoints, stdout logs, stderr logs, JSON payloads, and scratch artifacts such as `private/tests/results/.DS_Store`.

Impact:

- later automated or human review can accidentally read superseded artifacts as if they were current
- local result volume is already large enough to act as an uncontrolled secondary corpus

Remediation status:

- `src/investigation_results_workspace.py` now provides an active-manifest writer/loader plus an archive helper
- `private/tests/results/README.local.md`, the runbook, and the prompt pack now use `private/tests/results/active_run.json` as the canonical current pointer
- the live local workspace now has an `active_run.json` pointer for the active result set

Current assessment:

- stale-artifact ambiguity is reduced materially
- the active pointer exists, is documented, and now has a supported CLI owner
- superseded outputs can move through the paired archive workflow instead of ad hoc manual file operations

Finding `C12-F2`: the new active-results manifest is only exercised by tests and manual/operator flows; no production CLI or workflow path updates it automatically.

Evidence:

- `src/investigation_results_workspace.py:24-78` defines the helper surface.
- `rg -n "write_active_results_manifest\\(|active_results_manifest_path\\(|archive_results_paths\\(" src` returns only `src/investigation_results_workspace.py`.
- `tests/test_investigation_results_workspace.py:8-102` covers the helper directly, but no CLI or legal-support workflow test references it.
- `docs/agent/Documentation.md:37` explicitly notes that operators or agents still need to refresh `private/tests/results/active_run.json` when a new run supersedes the current one.

Impact:

- the freshness contract exists, but it depends on manual discipline
- a future run can still leave `active_run.json` stale without any runtime guardrail catching it

Remediation status:

- `python -m src.cli case refresh-active-run ...` is now the supported repo workflow for writing `active_run.json`
- `python -m src.cli case archive-results ...` is now the supported repo workflow for moving superseded local outputs under `_archive/`
- targeted CLI and contract tests cover both helpers

## Cross-Component Priority Order

Highest-priority blockers for later remediation:

- none from the second-pass residual set; the covered follow-up findings are closed at the repo level

## Audit Boundary

The original audit pass was read-only. Most covered findings were remediated in later milestone implementation passes. A second-pass re-audit exposed a smaller residual set in components `1`, `9`, `11`, and `12`; that residual set has now been remediated and verified through targeted tests plus the repo acceptance surfaces.

## Fourth-Pass Evidence-Driven Audit After P50 Wave Rerun

Purpose:

- review the new `P50` full-wave rerun as evidence rather than only as a runtime success
- identify repo-side improvement opportunities still limiting result quality
- stay read-only in this pass

Current assessment:

- this section records the pre-remediation state that triggered the fourth-pass implementation
- the improved wave-native stack executes all waves to completion
- the remaining repo-side quality ceiling is no longer basic execution failure
- the main open improvement areas are:
  - stateful wave orchestration versus batch-only wave looping
  - retrieval breadth under multi-lane competition
  - wave-local output shaping
  - executable quality assertions instead of shape-only wave tests
  - stronger thin-manifest sufficiency warnings

### Component 1: Entry Points And User Interfaces

Status: `quality gap identified`

Finding `C1-Q2`: `case execute-all-waves` is still a batch wrapper, not a stateful owner of the documented wave workflow.

Evidence:

- `docs/agent/question_execution_companion.md:91-123` requires one shared `scan_id`, explicit evidence quotas, and a standard MCP lane per wave.
- `src/cli_commands_case.py:162-199` loops through wave definitions, runs `build_case_analysis_payload(...)`, and only emits summaries or payloads.
- `src/cli_commands_case.py:162-199` does not pass or derive a `scan_id`, track per-question quotas, or refresh the register or open-tasks surfaces.
- `private/tests/results/active_run.json:14-15` still points to the older curated `question_register.md` and `open_tasks_companion.md` even after the new `P50` rerun artifact was added.

Impact:

- the repo can execute all waves, but it still cannot enforce the full stateful contract described in the runbook
- evidence gathering remains partly decoupled from the ledgers that later humans or agents actually resume from

What would improve quality:

- add one stateful wave orchestrator that owns:
  - wave-level `scan_id`
  - evidence quota counters
  - candidate carry-forward or dedupe state
  - optional register and open-tasks delta generation

### Component 5: Retrieval, Search, Ranking, And Context Expansion

Status: `quality gap identified`

Finding `C5-Q2`: multi-lane retrieval still collapses into one merged top-`10` pool, so the five wave lanes compete too aggressively.

Evidence:

- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:20-21` records `5` query lanes per wave but only `10` effective max results.
- `src/case_analysis.py:25-27` fixes `_MAX_ANSWER_CONTEXT_RESULTS = 10`.
- `src/case_analysis.py:40-47` and `src/case_analysis.py:61-67` clamp every case-analysis run to that cap before answer-context execution.
- `src/tools/search_answer_context_runtime.py:87-116` merges lane results and slices the final combined pool to `top_k`.

Impact:

- even a well-formed five-lane wave can end up with only a small number of surviving hits from weaker or later lanes
- diverse German exact-phrase, attachment, and orthographic-fallback lanes can be starved by one dominant lane

What would improve quality:

- keep a larger intermediate merged pool and rerank after lane union
- or reserve a minimum per-lane budget before final truncation

### Component 6: Case Analysis And Legal-Support Core

Status: `quality gap identified`

Finding `C6-Q2`: per-wave outputs are still mostly full-matter outputs with wave metadata attached, not truly wave-local products.

Evidence:

- `private/tests/results/11_memo_draft_dashboard/investigation_2026-04-16_P50_all_waves_rerun_improved_stack.md:36-49` records nearly identical high-level surface sizes for every wave:
  - `master_chronology.entry_count = 14`
  - `lawyer_issue_matrix.row_count = 9`
  - `document_request_checklist.group_count = 7`
  - `case_dashboard.cards = 11`
- `src/case_analysis_transform.py:72-83` builds chronology and evidence index from the full case bundle and multi-source bundle.
- `src/case_analysis_transform.py:145-195` builds the lawyer issue matrix and document checklist without a wave filter.
- `src/case_analysis_transform.py:287-321` builds the full dashboard and consistency layer for every wave payload.

Impact:

- later waves are harder to review because every payload still contains almost the same global narrative surfaces
- wave outputs are less useful for per-question closure and for spotting what genuinely changed in one rerun

What would improve quality:

- pass wave question IDs or issue scopes into the transform layer
- add wave-local filtered views for chronology, issue matrix, evidence index, and document requests
- keep the full-matter bundle separately as an optional background surface rather than the default per-wave output

### Component 11: Tests And Verification Corpus

Status: `quality gap identified`

Finding `C11-Q2`: the new wave tests still validate execution shape more than wave-quality behavior.

Evidence:

- `tests/case_workflows/test_cli_subcommands_case.py:282-329` checks that `execute-all-waves` returns a workflow, `wave_count == 12`, and a first wave ID.
- the same test block does not assert:
  - wave-local differentiation
  - register or open-task refresh
  - evidence quota enforcement
  - scan-state reuse
- `tests/case_workflows/test_cli_subcommands_case.py:332-360` covers `refresh-active-run` separately, but not as a coupled part of `execute-all-waves`.

Impact:

- the repo can regress back to “valid JSON with 12 waves” while still missing the quality properties the operator contract depends on
- the current suite would not catch the difference between a batch rerun and a true stateful wave workflow

What would improve quality:

- add one fixture-backed golden test where different waves must produce different filtered source or issue sets
- add one integration test for a stateful wave run that also writes register or open-task updates
- add one regression asserting that wave execution uses or exposes a scan-session concept if that remains part of the contract

### Component 12: Local Runtime, Materials, And Result Corpora

Status: `quality gap identified`

Finding `C12-Q2`: `exhaustive_matter_review` still treats a two-artifact manifest as sufficient, so thin supplied corpora degrade quality without a strong machine warning.

Evidence:

- `private/tests/results/case_input.json:278-306` shows the active exhaustive manifest still contains only `recent_email.html` and `thread.html`.
- `src/mcp_models_case_analysis_manifest.py:373-382` validates exhaustive review by requiring a manifest and at least one artifact, but it does not require breadth or source-class diversity.
- `src/case_analysis_scope.py:191-230` warns only when mixed-record support is absent altogether, not when the manifest is present but still too thin for the declared issue tracks.

Impact:

- the repo accepts an exhaustive review posture that looks valid structurally while still lacking the non-email record classes the matter itself depends on
- the quality ceiling remains easy to misread as a retrieval or reasoning failure instead of a thin-input problem

What would improve quality:

- add manifest-sufficiency diagnostics keyed to source classes and declared issue tracks
- downgrade or fail exhaustive review when decisive artifact classes are still absent
- surface those missing classes directly in `analysis_limits` and the wave summary

## Fourth-Pass Priority Order

Highest-value improvements after the `P50` rerun:

1. `C6-Q2`
   Reason:
   wave payloads are still too global, which makes full reruns expensive to interpret and weak for per-question closure
2. `C1-Q2`
   Reason:
   the repo now has wave execution, but not yet the stateful wave workflow the docs promise
3. `C5-Q2`
   Reason:
   the five-lane design still funnels into a small merged top-`10` pool
4. `C12-Q2`
   Reason:
   thin exhaustive manifests still look more complete than they really are
5. `C11-Q2`
   Reason:
   the current tests would not catch several of the quality regressions above

## Sixth-Pass Audit: Evidence Discovery And Ingestion Blind Spots

Scope:

- read-only audit focused on every stage that can lose viable evidence before it becomes durable evidence
- examined source parsing, SQLite persistence, attachment extraction, language and entity enrichment, retrieval, harvest, and promotion
- validated findings against the live archive state in `private/runtime/email_metadata.db`

synthetic corpus snapshot used for this audit:

- `19948` emails
- `6483` attachments
- `300` harvested evidence candidates
- `30` durable evidence items
- `3037` emails with no detected language
- `0` rows in `entities`
- `0` rows in `entity_mentions`
- `0` emails marked `is_calendar_message = 1`

### Component 3: Ingestion And Parsing

Status: `quality gap identified`

Finding `C3-Q1`: calendar and Exchange meeting metadata are parsed but not persisted into the main relational model, so viable scheduling evidence is lost after ingest.

Evidence:

- `src/parse_olm.py` and `src/parse_olm_xml_parser.py` populate `meeting_data`, `exchange_extracted_links`, `exchange_extracted_emails`, `exchange_extracted_contacts`, and `exchange_extracted_meetings` on the parsed `Email` object.
- `src/email_db_persistence.py` persists canonical email fields, recipients, categories, attachments, and message segments, but it does not store any of those meeting or Exchange-extracted fields.
- `src/db_schema.py` has no columns or companion tables for `meeting_data` or the `exchange_extracted_*` surfaces.
- the live DB reports `0` emails with `is_calendar_message = 1` while attachments include `29` `text/calendar` parts.

Impact:

- meeting invitation semantics, attendee hints, organizer metadata, and Exchange-extracted meeting references are available transiently during parse but disappear from the persistent evidence substrate
- later bundle builders already know how to use `meeting_data`, but the DB-backed workflow cannot actually provide it after ingest

What viable information is currently missed:

- meeting and invitation metadata
- organizer and attendee references
- Exchange-derived meeting objects and smart-link context

How to improve:

- persist `meeting_data` and `exchange_extracted_*` into dedicated JSON columns or normalized tables
- backfill from existing archives with a metadata reingest pass
- treat calendar evidence as first-class searchable material rather than incidental attachment text

Finding `C3-Q2`: reply-context extraction is only attempted when canonical thread headers are absent, which leaves a large amount of useful reply-header evidence unmodeled.

Evidence:

- `src/parse_olm_postprocess.py` only calls `extract_reply_context(...)` when both `in_reply_to` and `references` are missing.
- the live DB shows `9816` emails with non-empty `references_json` but only `58` emails with populated `reply_context_from` or `reply_context_subject`.

Impact:

- visible quoted header information that could help speaker attribution and thread repair is not captured for the vast majority of standard replies
- downstream quote attribution and inferred-thread logic lose corroborating metadata that is still present in the raw message body

What viable information is currently missed:

- visible quoted `From`, `To`, `Subject`, and date context in normal replies

How to improve:

- extract reply-context data even when canonical thread headers exist
- store canonical and quoted reply context separately rather than treating them as mutually exclusive

### Component 4: Storage And Schema

Status: `quality gap identified`

Finding `C4-Q1`: quoted and forwarded message structure is persisted in `message_segments`, but that surface is not part of the retrieval substrate.

Evidence:

- `src/chunker.py` strips quoted content from reply and forward bodies before embedding.
- `src/email_db_persistence.py` persists `message_segments` for authored body, quoted replies, forwarded messages, signatures, and header blocks.
- live DB counts:
  - `19421` `forwarded_message` segments
  - `4419` `quoted_reply` segments
  - `18887` `authored_body` segments
- retrieval code under `src/retriever.py` and `src/retriever_filtered_search.py` searches vector chunks, not `message_segments`.

Impact:

- evidence that only survives as quoted history is effectively not searchable unless the surrounding authored body happens to retrieve the email first
- the repo stores a richer conversational decomposition than it actually uses for discovery

What viable information is currently missed:

- quoted prior statements
- forwarded historical summaries
- nested reply context that could be evidentiary on its own

How to improve:

- build a segment-level sparse or lexical index over `message_segments`
- expose quoted and forwarded segments as searchable retrieval lanes
- keep authored and quoted surfaces separately scorable so discovery can target one without flooding the other

Finding `C4-Q2`: several enriched body surfaces exist, but the analytics and promotion layers still treat them unevenly.

Evidence:

- the schema stores `body_text`, `raw_body_text`, and `forensic_body_text`.
- live DB counts:
  - `231` emails have empty normalized `body_text`
  - `1100` emails have empty `forensic_body_text`
  - `606` emails still have `raw_body_text` even though `forensic_body_text` is empty
- `src/language_analytics.py` can use forensic, normalized, raw, and attachment text, but `src/ingest_reingest.py` only reingests analytics for rows where at least one body field is already non-empty.

Impact:

- some recoverable body surfaces remain underused for analytics and downstream evidence scoring
- attachment-only or header-heavy rows can stay analytically invisible even when the archive contains usable secondary text

What viable information is currently missed:

- attachment-only message signals
- raw-source-only or shell-heavy body recovery that was not promoted into the preferred surface

How to improve:

- widen analytics eligibility to rows with attachment text or rich raw source, not only pre-existing body fields
- add explicit diagnostics for `raw_body_text present but forensic_body_text empty`

### Component 5: Retrieval, Search, Ranking, And Context Expansion

Status: `quality gap identified`

Finding `C5-Q3`: attachment retrieval still overweights inline noise and underweights non-inline documentary evidence.

Evidence:

- live DB counts:
  - `6483` total attachments
  - `5854` inline attachments
- `src/case_analysis_harvest.py` attachment expansion uses `attachments_for_email(uid)[:3]` and does not skip inline attachments.
- `src/db_attachments.py` returns both inline and non-inline attachments without ranking or evidence weighting.

Impact:

- attachment-first lanes can waste budget on signatures, logos, and inline decorative images
- strong non-inline documentary attachments compete with much noisier inline material

What viable information is currently missed:

- non-inline documents that should outrank inline decorative assets

How to improve:

- explicitly downrank or exclude inline attachments in evidence-harvest expansion
- rank attachments by `is_inline`, `evidence_strength`, `extraction_state`, filename semantics, and text availability before sampling

Finding `C5-Q4`: exact quote promotion still depends on short retrieval snippets rather than a first-class exact-quote extraction stage.

Evidence:

- `src/tools/search_answer_context_evidence_helpers.py` reduces search hits to compact snippets.
- `src/evidence_harvest.py` harvests `candidate.get(\"snippet\")`, normalizes it with `_clean_text`, and only auto-promotes body candidates when `verification_status` is one of a small exact set.
- the live candidate bank shows `300` candidates but only `30` durable evidence items; earlier `P70` harvest diagnostics reported `0` exact-body hits and `0` auto-promotions.

Impact:

- the repo retrieves relevant emails but still fails to convert many of them into durable evidence without manual SQLite recovery
- discovery breadth is now much better than promotion precision

What viable information is currently missed:

- longer exact excerpts that do not fit the compact snippet surface
- body text that is present in the email but not in the retrieval snippet window

How to improve:

- add an exact-quote extraction pass after retrieval that uses full stored bodies instead of compact snippets
- treat retrieval snippets as pointers into the body, not as the final evidence quote candidate

### Component 7: NLP, Language, Entity, And Signal Extraction

Status: `quality gap identified`

Finding `C7-Q2`: the entity layer is effectively absent in the live archive, and even when enabled it ignores attachment text and most non-body surfaces.

Evidence:

- live DB counts:
  - `0` rows in `entities`
  - `0` rows in `entity_mentions`
- `src/ingest.py` defaults `extract_entities` to `False`.
- `src/ingest_reingest.py` reextracts entities from `body_text` only.
- `src/entity_extractor.py` is regex-focused and only derives organizations from sender domains, not body context.

Impact:

- the actor-discovery, comparator, witness, and network layers are starting from a nearly empty structured-entity substrate
- person, role, and organization mentions inside attachment text, forensic bodies, raw bodies, and subjects are missed

What viable information is currently missed:

- person and organization names in attachments
- names or role labels in subjects and forwarded headers
- comparator and witness mentions in quoted or forwarded content

How to improve:

- make entity extraction part of the default ingest contract for evidence-heavy runs
- reextract from a richer surface union:
  - `subject`
  - `forensic_body_text`
  - `body_text`
  - `raw_body_text`
  - attachment extracted text
- persist extractor provenance by surface so false positives can be audited

Finding `C7-Q3`: language analytics still leave a large unlabeled tail and do not fully exploit attachment-bearing rows.

Evidence:

- live DB counts:
  - `13712` rows labeled `de`
  - `1934` rows labeled `en`
  - `3037` rows with empty `detected_language`
- `src/ingest_reingest.py` only selects rows for analytics when at least one body field is non-empty, even though it also computes `attachment_text`.

Impact:

- a significant corpus segment remains invisible to German-first routing and heuristics
- attachment-heavy or body-poor emails can evade language-aware retrieval planning

What viable information is currently missed:

- attachment-driven language cues
- subject-plus-attachment language cues on body-poor emails

How to improve:

- allow analytics reingest to process rows with usable attachment text or subject text alone
- surface a specific dashboard metric for unlabeled emails by body-kind and attachment availability

### Component 8: Attachment And Document Evidence

Status: `quality gap identified`

Finding `C8-Q1`: there is no OCR path for PDF attachments, so scanned or image-heavy PDFs remain reference-only.

Evidence:

- `src/attachment_extractor.py` only exposes OCR via `extract_image_text_ocr(...)`.
- `extract_image_text_ocr(...)` returns `None` unless `is_image_attachment(filename)` is true.
- the live DB shows:
  - `685` attachments with no extracted text ending mostly in `.pdf`
  - `326` non-inline `.pdf` attachments with no extracted text
- examples include:
  - `2024.04.04_FAQ mobiles Arbeiten.pdf`
  - `2023 DV BEM inkl. Anschreiben Kanzler u. Personalrat.pdf`
  - `Team-Workshop am 25.03.2024_Fotoprotokoll.pdf`

Impact:

- many likely high-value documentary records are visible only by filename, not by content
- those files cannot participate in semantic search, quote extraction, or exact evidence promotion

What viable information is currently missed:

- scanned PDF text
- image-only PDF text
- protocol and policy PDFs with no native text layer

How to improve:

- add PDF OCR fallback using page rasterization plus OCR
- store page-level OCR provenance and page locators so later quotes can be verified precisely

Finding `C8-Q2`: attached emails and archives are still unsupported, which leaves viable evidence containers unopened.

Evidence:

- `src/attachment_extractor_text.py` skips `.eml`, `.msg`, `.zip`, `.gz`, `.tar`, `.rar`, and `.7z`.
- live DB counts show:
  - `64` `.eml` attachments with no extracted text
  - `.zip` archives marked `archive_contents_not_extracted`
- live unsupported examples include:
  - `Entwicklungsmöglichkeiten institution (11,8 KB).eml`
  - `Bitte um Zwischenzeugnis (10,9 KB).eml`
  - `zertifikate_mdm.zip`

Impact:

- forwarded or attached email chains are lost as evidence containers
- archives that may contain exported records or configs are only weak references

What viable information is currently missed:

- attached email content and metadata
- nested documentary evidence inside archives

How to improve:

- add `.eml` and `.msg` text and metadata extraction
- add controlled archive inventory and selected file extraction for safe archive formats

### Component 9: Promotion, Evidence, And Dossier Surfaces

Status: `quality gap identified`

Finding `C9-Q3`: the evidence system still treats meeting and attachment provenance as second-class compared with body quotes.

Evidence:

- `src/db_evidence.py` verifies quotes only against `forensic_body_text`, `body_text`, and `raw_body_text`.
- attachment-derived evidence currently requires body-text workarounds or separate weak-reference semantics.
- calendar and meeting metadata are not persisted in the same durable manner as body text.

Impact:

- attachment-native and meeting-native evidence is harder to preserve as exact, promotable proof
- discovery may find a useful file, but durable-evidence workflows still prefer body quotes

What viable information is currently missed:

- exact attachment-native quotes with durable locators
- exact meeting metadata citations

How to improve:

- extend evidence verification to attachment text plus locator metadata
- add first-class evidence handles for page, sheet, calendar field, and attachment section references

### Sixth-Pass Priority Order

Highest-value improvements from this ingestion and discovery audit:

1. `C8-Q1`
   Reason:
   scanned and image-heavy PDFs are still invisible to semantic discovery even though they likely contain core documentary evidence
2. `C7-Q2`
   Reason:
   the structured entity layer is empty, which blocks actor discovery, comparator mapping, and witness expansion
3. `C4-Q1`
   Reason:
   thousands of quoted and forwarded segments are stored but not discoverable
4. `C3-Q1`
   Reason:
   calendar and Exchange meeting metadata are parsed and then dropped before persistence
5. `C5-Q3`
   Reason:
   attachment-first discovery is still spending too much budget on inline noise
6. `C5-Q4`
   Reason:
   retrieval now finds more, but durable promotion still lags because exact-quote extraction is not first-class
