# Plan

Status: `operator-facing and verified`

Purpose:

- provide the live execution entrypoint for autonomous matter analysis
- require on-the-fly remediation of hurdles, errors, and repo issues during question answering
- route detailed execution rules into the canonical runbook and question companion

Canonical execution documents:

- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/Documentation.md` (verification/change log, not a general docs index)

Archive and history surfaces:

- `docs/agent/matter_analysis/` for supporting phase maps, heuristics, and operations detail
- `docs/agent/deprecated/` for archived audit-era docs and deprecated path shims
- `docs/agent/implementation_log/` for chronological change logs
- `docs/agent/plan_history/` for preserved planning-program history

## Execution enablement pack

Use these files together for a fully autonomous run:

- `docs/agent/mcp_client_config_snippet.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/question_execution_query_packs.md`
- `docs/agent/post_harvest_evidence_refinement_manual.md`
- `docs/agent/question_register_template.md`
- `docs/agent/open_tasks_companion_template.md`
- `docs/agent/email_matter_investigation_checkpoint_template.md`

## Fresh-run prerequisites

Before starting Wave 1 on a fresh run:

1. connect the MCP client to `private/runtime/current/` using `docs/agent/mcp_client_config_snippet.md`
2. verify the live runtime with:
   - `email_admin(action='diagnostics')`
   - `email_stats`
   - `email_quality(check='languages')`
   - if language analytics are missing or stale, run `email_admin(action='reingest_analytics')` and rerun `email_quality(check='languages')`
3. rebuild or confirm the active case scope from real trigger dates, actors, issue tracks, and known missing-record classes
4. rebuild or confirm the active matter manifest from the current materials directory
5. initialize the local question register from:
   - `docs/agent/question_register_template.md`
6. initialize the local open-tasks file from:
   - `docs/agent/open_tasks_companion_template.md`
7. use the kickoff prompt and query packs from:
   - `docs/agent/question_execution_prompt_pack.md`
   - `docs/agent/question_execution_query_packs.md`

## German-first execution rule

For this matter family, do not treat bilingual support as permission to default to English.

When either of these is true:

- `email_quality(check='languages')` shows German as the dominant corpus language
- the matter posture is a German employment / workplace matter

default the active run to:

- `output_language: de`
- `translation_mode: source_only`

Use English output only when the operator explicitly needs English-facing counsel export or comparison output.

Even then:

- keep German-source quotations preserved
- keep German-native retrieval lanes primary
- use English phrasing only as supplemental expansion

## Language baseline and detection rule

Before Wave 1 and after any major corpus refresh:

- record the corpus language baseline from `email_quality(check='languages')`
- treat `detected_language` as heuristic, not ground truth, especially for:
  - short emails
  - forwarded or header-heavy messages
  - subject-only or acknowledgement-heavy messages
- sample high-value wave hits where German records appear as `unknown` or non-`de`
- if analytics are missing or clearly stale, run `email_admin(action='reingest_analytics')`
- if German records are still being missed, expand the query pack before downgrading the question:
  - native German spellings
  - umlaut and ASCII fallback variants
  - subject, snippet, forensic text, and attachment phrasing

Language-detection repair is an execution task, not a reason to stop the campaign.

## Prompt rule

Do not improvise campaign-launch instructions from scratch when the prompt pack already covers the task.

Use:

- the kickoff prompt for a fresh run
- the resume prompt after interruption or crash recovery
- the wave prompts when running one wave at a time
- the blocker-remediation prompt when the run fails for a locally fixable reason
- the closure prompt when consolidating final question states

## Scope rebuild rule

Do not start Wave 1 from a synthetic placeholder scope when real wave findings already identify:

- dated trigger events
- real actors
- real issue tracks
- known missing-record classes

If those are known, rebuild the case scope and matter manifest first and only then launch the next wave cycle.

## Query-pack rule

Each wave must run from the query-pack contract in:

- `docs/agent/question_execution_query_packs.md`

Minimum rule:

- use `3` to `5` retrieval queries per wave
- make the first retrieval lane German-native when the matter is German-dominant
- include an orthographic variant lane for German spellings such as:
  - `ä/ae`
  - `ö/oe`
  - `ü/ue`
  - `ß/ss`
- use one shared `scan_id` for the wave
- include supporting and counterevidence lanes
- include attachment or mixed-source lanes when the question depends on non-email material
- use English or translation-style query terms only as supplementary expansion after the German lanes have run

## Evidence quota rule

Before closing a question:

- `answered by direct evidence` requires at least `2` supporting anchors where available plus a counterevidence check
- `partially answered` requires at least `3` supporting anchors plus one counter or competing-explanation anchor
- `requires missing record` requires at least one source-backed reason for the gap plus the exact missing-record class

Wording-sensitive questions must preserve at least one verified quote.

## Autonomous execution principle

The agent must finish every reachable task in the same run.

Do not stop a question or wave merely because:

- a query was too narrow or too broad
- the wrong MCP tool was chosen first
- a tool returned truncated or incomplete output
- a schema or alias mismatch broke a call
- MCP state, cache, or checkpoint state became stale
- a repo-side workflow bug prevented normal execution

These are execution defects, not question outcomes.

## Remediation ladder

For every hurdle, classify it before downgrading the question:

1. query, retrieval, or language-lane mismatch
2. missing thread, attachment, provenance, or context expansion
3. tool-contract or schema mismatch
4. truncation, response-budget, or payload-shape failure
5. runtime, cache, checkpoint, restart, or stale analytics issue
6. phase-order or workflow misuse
7. true external missing record

Required handling:

- for classes `1` through `6`, repair the problem immediately, rerun the failed step, and continue the wave
- for class `7`, mark the affected question `requires missing record` or `blocked by missing record`, then continue the rest of the campaign

## Question closure rule

No question may remain open because of a locally fixable execution problem.

Before a question is left yellow, red, or open, the agent must have already:

1. retried with the correct MCP path
2. expanded context where needed
3. repaired any repo-side contract or workflow issue discovered during execution
4. rerun the affected step after the repair

Only after that may the agent conclude that the gap is truly in the record rather than in execution.

## Wave execution rule

Use the wave order and question mapping from:

- `docs/agent/question_execution_companion.md`

Use the phase gates, checkpoints, crash recovery, and outward-release rules from:

- `docs/agent/email_matter_analysis_single_source_of_truth.md`

Global override:

- no wave is complete while a fixable execution blocker remains unresolved inside that wave
- open-tasks logging is for irreducible record gaps and downstream follow-up, not for repo defects that can be fixed during the run

## Archive-Harvest Improvement Program

Status: `implemented on 2026-04-16`

Purpose:

- stop treating a thin matter manifest as the effective evidence ceiling when the indexed mailbox is much larger
- split archive harvesting from question closure so evidence collection can saturate the archive neighborhood before synthesis
- add executable coverage gates so the workflow can detect under-scanned waves instead of overclassifying them

Problem statement:

- the archive can contain tens of thousands of indexed emails while the active matter manifest contains only a small set of supplied non-email artifacts
- if the workflow closes questions before archive harvest reaches a minimum coverage floor, evidence quality remains artificially thin even when the corpus is large

Execution rule:

- for email-centered questions, the indexed mailbox is the primary retrieval substrate
- the matter manifest supplements chronology, attachments, and non-email records; it must not silently become the effective ceiling for archive evidence gathering
- every wave must finish archive harvest before its question states are treated as closure-ready

### Milestone 1: Archive Harvest Before Closure

Implementation scope:

- add an explicit archive-harvest stage before wave synthesis in the case-analysis runtime
- keep wave execution two-phase:
  - archive harvest
  - wave synthesis from the harvested evidence neighborhood

Required tests:

- one regression proving case-analysis now emits archive-harvest metadata before closure surfaces
- one regression proving wave execution exposes harvest status in its payload

Definition of done:

- each wave payload contains a machine-readable archive-harvest section
- question closure no longer depends only on the final compact candidate list

## Database And Evidence-Detection Improvement Program

Status: `implemented on 2026-04-16`

Purpose:

- make evidence harvest a required persisted phase instead of a transient side effect of wave execution
- expand the database from only durable curated evidence items to a two-layer model:
  - harvested evidence candidates
  - promoted durable evidence items
- improve exact-quote detection so retrieval-mode candidates can be promoted safely when the snippet is truly verified

Milestone order:

1. add an `evidence_candidates` database surface with run, phase, wave, and provenance metadata
2. distinguish `retrieval_exact` from `retrieval_fallback` in the answer-context provenance layer
3. add a shared campaign workflow for evidence harvest across all waves
4. expose the harvest workflow through CLI and MCP as `case gather-evidence` / `email_case_gather_evidence`
5. auto-promote only exact verified body quotes; keep weaker or attachment-only hits in the candidate layer
6. require a live evidence-gathering run plus refreshed stats before claiming the corpus has been rescanned

Required tests:

- schema and DB tests for `evidence_candidates`
- harvest-regression tests for candidate persistence, dedupe, and exact-quote promotion
- shared-campaign tests for aggregated evidence harvest
- CLI parse and write-path tests for `case gather-evidence`

Definition of done:

- the database stores harvested evidence candidates separately from curated evidence items
- evidence harvest is executable as a first-class shared campaign phase
- exact verified retrieval snippets can be promoted automatically without manual copy-paste
- evidence rescans now increase the stored corpus through the supported run path rather than only through ad-hoc manual evidence entry

### Milestone 2: Archive-Primary Source Basis

Implementation scope:

- expose source-basis diagnostics that distinguish:
  - email archive as primary source
  - matter manifest as supplemental mixed-source support
  - manifest-only fallback when no archive is available
- keep thin manifests visible as insufficiency, not as a silent substitute for archive retrieval

Required tests:

- one regression proving mixed-source runs with archive access are marked archive-primary
- one regression proving thin manifests stay downgraded even when structurally valid

Definition of done:

- archive-backed case-analysis payloads disclose that the mailbox remains the primary evidence substrate
- the manifest is represented as supplement rather than as silent closure authority

### Milestone 3: Coverage Metrics And Gates

Implementation scope:

- add wave-level coverage metrics, including at least:
  - unique hits reviewed
  - unique threads covered
  - unique senders or actor proxies touched
  - unique months covered
  - attachment-bearing hits
  - folders touched
  - lane coverage across the query pack
- derive wave-level coverage thresholds and a pass or fail harvest gate

Required tests:

- one regression proving archive-harvest metrics are emitted
- one regression proving under-scanned waves are marked `needs_more_harvest`

Definition of done:

- wave payloads expose coverage metrics and thresholds
- low-coverage waves can be detected mechanically before question closure

### Milestone 4: Wider Retrieval Budgets And Evidence Banking

Implementation scope:

- raise retrieval breadth for archive-harvest phases without bloating the final compact answer bundle
- use wider per-lane retrieval and a larger merged evidence bank before selecting the compact synthesis set
- preserve lane diversity so weaker but relevant German lanes survive the merge

Required tests:

- one retrieval regression proving broader per-lane harvesting preserves a weaker lane hit
- one regression proving the evidence bank and harvest budgets are exposed in diagnostics

Definition of done:

- archive harvest scans a meaningfully larger candidate neighborhood than the final compact answer surface
- wave payloads expose an evidence bank or equivalent harvest summary

### Milestone 5: Wave Summaries, Tests, And Acceptance Gates

Implementation scope:

- expose archive-harvest and coverage summaries in `case execute-wave` and `case execute-all-waves`
- extend regressions and smoke coverage so the suite validates harvest quality rather than only JSON shape
- keep operator docs synchronized with the implemented workflow

Required tests:

- updated CLI regressions for wave summaries
- updated case-analysis regressions for harvest metadata and coverage gates
- executable smoke or acceptance coverage for the improved wave workflow

Definition of done:

- the local wave runner surfaces harvest status and coverage metrics directly
- the test and smoke layers can catch a regression back to under-scanned wave execution


## Historical Programs

- Full-corpus and remediation-program history moved to `docs/agent/plan_history/2026-04-16_programs.md`.
