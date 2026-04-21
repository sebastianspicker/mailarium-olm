# Email Matter Analysis Single Source Of Truth

Version: `1`

Status: `operator-facing`

Canonical path:

- `docs/agent/Plan.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`

Deprecated operator docs moved to:

- `docs/agent/deprecated/Plan.md`
- `docs/agent/deprecated/email_matter_investigation_runbook.md`

## Goal

Provide the single source of truth for planning, documenting, running, recovering, and completing the shared campaign execution plus MCP-governed legal-support analysis of the current email matter.

This is the campaign control document for:

- corpus investigation
- evidence organization
- chronology building
- pattern testing
- missing-record acquisition
- counsel-grade output preparation

This is not an outward memo and not a status note.

This file is designed so an AI agent can run the matter end-to-end without human interaction, including:

- scope stabilization
- corpus analysis
- evidence extraction
- chronology building
- question closure
- report generation
- runtime and workflow remediation
- crash recovery
- long-running continuation

## Current campaign reset

This campaign is currently under a full execution reset.

Reason:

- prior result production used repository CLI entrypoints instead of MCP client queries against the running MCP server
- those outputs may be useful as debugging traces, but they are not valid completion evidence for this runbook

Effective rule:

- every phase from `P00` through `P11` is reset to `RERUN`
- no phase may be marked `completed`, `green`, or relied upon for counsel-grade output until it has been reproduced through MCP server queries

Current phase reset register:

- `P00`: `RERUN`
- `P01`: `RERUN`
- `P02`: `RERUN`
- `P03`: `RERUN`
- `P04`: `RERUN`
- `P05`: `RERUN`
- `P06`: `RERUN`
- `P07`: `RERUN`
- `P08`: `RERUN`
- `P09`: `RERUN`
- `P10`: `RERUN`
- `P11`: `RERUN`

Current task-state vocabulary for this campaign:

- `NOT COMPLETED`
- `RERUN`
- `BLOCKED BY MISSING RECORD`
- `ANSWERED BY DIRECT EVIDENCE`
- `ANSWERED BY BOUNDED INFERENCE`

## Matter posture

Use this runbook for a German-language employment-related matter involving, at minimum, possible issues around:

- Eingruppierung
- disability-related disadvantage
- retaliation / Maßregelung
- mobile work / home office
- SBV participation
- PR participation
- §167 SGB IX prevention / BEM
- medical recommendations ignored
- task withdrawal / TD fixation
- worktime control / surveillance
- comparator treatment

## Non-negotiable rules

- Work only from the provided materials.
- Quote or precisely reference the source for every important finding.
- Preserve chronology and exact dates where available.
- Default the working run to German when the corpus baseline or matter posture is German-dominant.
- Separate:
  - direct evidence
  - reasonable inference
  - unresolved / speculative points
- Keep competing explanations visible.
- Do not convert prompt wording, dossier summaries, or prior notes into fact.
- Do not label conduct as discrimination, retaliation, mobbing, or gaslighting unless the evidence supports that label.
- Do not advance into drafting or lawyer-facing framing while the evidence-index and chronology gates are still red.
- Use the shared campaign workflow for wave execution and evidence harvest, whether it is entered through the documented CLI wrappers or the MCP `email_case_*` campaign tools.
- Use MCP server queries for dedicated legal-support product refresh, counsel-facing export, and other `email_case_*` analytical outputs that are still MCP-governed.
- Do not mark a task complete merely because a local CLI command produced a JSON artifact.
- Treat CLI-produced dedicated legal-support artifacts from earlier cycles as non-authoritative unless and until the same result is reproduced through MCP server queries.
- Do not keep synthetic validation anchors once real dated trigger events, actors, and missing-record classes are known for the matter.
- When non-email supplied records exist in the matter manifest, switch the run to `mixed_case_file` plus `exhaustive_matter_review`.
- If a hurdle, error, or repo-side issue blocks question completion, treat it as a repair task inside the run rather than as a reason to stop.
- Do not leave a question open while a locally fixable query, schema, truncation, runtime, or workflow defect remains unresolved.
- Do not let bilingual output support silently turn a German-dominant matter into an English-first retrieval run.

## Global output style contract

All generated matter outputs must be:

- concise but rigorous
- organized with structured headings
- table-based where that improves legal review
- neutral in tone
- suitable for lawyer review, internal complaint use, or documentary follow-up

Every important point in every analytical output must include:

- source reference or quote
- date or date range
- explicit separation between:
  - direct evidence
  - reasonable inference
  - unresolved or speculative point
- a missing-evidence or uncertainty note where relevant

## German-language baseline and detection gate

For this campaign family, language posture is a real execution gate, not presentation polish.

Before Wave 1 on a fresh or rebuilt run:

1. run `email_quality(check='languages')`
2. if language analytics are missing or stale, run `email_admin(action='reingest_analytics')` and rerun `email_quality(check='languages')`
3. record the corpus language baseline in the checkpoint, including labeled versus unlabeled coverage
4. when German is dominant or the matter posture is German employment, set:
   - `output_language='de'`
   - `translation_mode='source_only'`
5. preserve English-facing rendering only for explicit downstream export needs

Local execution lane:

- use `python -m src.cli case execute-wave --input case.json --wave wave_1` or `python -m src.cli case execute-all-waves --input case.json` when you need a reproducible local wave run backed by the same query-lane contract
- use `python -m src.cli case gather-evidence --input case.json --run-id <run_id> --phase-id <phase_id> --scan-id-prefix <scan_id_prefix>` when the wave run must write harvested candidates into the database and promote exact verified quotes
- the gather-evidence lane must harvest per wave as execution progresses; it is not acceptable to defer evidence persistence until all waves have already finished
- treat that CLI lane as a shared campaign execution surface paired with MCP `email_case_execute_wave`, `email_case_execute_all_waves`, and `email_case_gather_evidence`
- dedicated legal-support analytical products still belong to the broader MCP `email_case_*` surface

Mandatory matter inputs before any launch, resume, or harvest-backed refinement step:

- `private/cases/case.json`
- `private/results/evidence-harvest.json` once harvest has already completed for the active run
- the current:
  - `run_id`
  - `phase_id`
  - `scan_id_prefix`
- any known human corrections already verified for the matter:
  - verified trigger events
  - alleged adverse actions
  - comparators
  - role hints
  - institutional actors or mailboxes

Do not let the agent infer these from memory or stale prompt fragments when the current artifacts already exist.

Detection guardrails:

- the current detector is lightweight and short-text-sensitive
- do not trust `detected_language` blindly for:
  - short acknowledgements
  - subject-heavy messages
  - forwarded or header-heavy bodies
  - formulaic HR or calendar notices
- if high-value German messages are misclassified or `unknown`, repair the language lane inside the run:
  - rerun analytics if needed
  - widen German-native and orthographic-variant queries
  - use subject, snippet, forensic, and attachment text before treating the wave as sparse

## Autonomous execution contract

The agent must be able to continue the campaign on its own until every live question is closed as one of:

- `answered by direct evidence`
- `answered by bounded inference`
- `not answered in current corpus`
- `blocked by missing record`

The agent must not stop merely because:

- a run is long
- one MCP product fails once
- one subphase returns partial output
- some questions remain unresolved

The agent should instead:

1. checkpoint current state
2. isolate the failing phase or tool
3. restart from the correct resume gate
4. continue until all reachable outputs are generated
5. mark only the truly blocked questions as blocked
6. write every unresolved, blocked, or deferred item into the open-tasks companion file

Human interaction is not required for normal continuation. Only absent source material should remain as a blocker, and even then the agent must still complete every other answerable part of the matter.

## Active MCP runtime contract

The active archive for this matter is the private runtime corpus.

```bash
source .venv/bin/activate
eval "$(bash scripts/private_runtime_current_env.sh)"
python -m src.mcp_server
```

Equivalent explicit form:

```bash
python -m src.mcp_server \
  --chromadb-path private/runtime/current/chromadb \
  --sqlite-path private/runtime/current/email_metadata.db
```

Do not silently fall back to tracked `data/`.

For CLI execution against the active private runtime, prefer either:

```bash
bash scripts/private_runtime_current_env.sh python -m src.cli analytics stats
```

or explicit flags:

```bash
python -m src.cli \
  --chromadb-path private/runtime/current/chromadb \
  --sqlite-path private/runtime/current/email_metadata.db \
  analytics stats
```

## Execution enablement pack

The autonomous run depends on the following tracked operator docs:

- `docs/agent/mcp_client_config_snippet.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/question_execution_query_packs.md`
- `docs/agent/question_register_template.md`
- `docs/agent/open_tasks_companion_template.md`
- `docs/agent/email_matter_investigation_checkpoint_template.md`

Before the first wave of a fresh run:

1. connect the MCP client to `private/runtime/current/` using `docs/agent/mcp_client_config_snippet.md`
2. verify the active runtime with `email_admin(action='diagnostics')`, `email_stats`, and `email_quality(check='languages')`
3. if language analytics are missing or stale, run `email_admin(action='reingest_analytics')` and rerun `email_quality(check='languages')`
4. rebuild or confirm the active case scope from real trigger dates, actors, issue tracks, and known missing-record classes
5. rebuild or confirm the active matter manifest from the materials directory
6. when the corpus baseline or matter posture is German-dominant, keep the active case input on:
   - `output_language='de'`
   - `translation_mode='source_only'`
7. initialize `private/tests/results/11_memo_draft_dashboard/question_register.md` from `docs/agent/question_register_template.md`
8. initialize `private/tests/results/11_memo_draft_dashboard/open_tasks_companion.md` from `docs/agent/open_tasks_companion_template.md`
9. launch the campaign from `docs/agent/question_execution_prompt_pack.md` plus `docs/agent/question_execution_query_packs.md`

## Shared campaign execution contract

For this campaign, wave execution must come from the shared campaign workflow, not from ad hoc helper calls.

Allowed execution surface for wave execution:

- a client connected to `src.mcp_server` calling `email_case_execute_wave` or `email_case_execute_all_waves`
- `python -m src.cli case execute-wave ...`
- `python -m src.cli case execute-all-waves ...`

Still not sufficient for completion:

- direct Python helper invocation
- ad hoc local JSON generation that does not come from the shared campaign workflow

Permitted support work:

- local file organization
- checkpoint writing
- local results-workspace maintenance through `python -m src.cli case refresh-active-run ...`
- superseded local-output archival through `python -m src.cli case archive-results ...`
- copying MCP outputs into phase folders
- documenting blockers, retries, and resume state

Every wave-level analytical artifact that claims campaign execution must point back to the shared campaign workflow.
Dedicated legal-support product artifacts should still point back to the MCP `email_case_*` tool that produced them.
`active_run.json.curation.status` is the machine-readable truth for whether the curated ledgers are current, raw, or stale after a rerun.

Autonomy boundary:

- `autonomous internal completion` means the shared campaign workflow, wave outputs, checkpoints, and `active_run.json` state are complete enough for internal analysis
- `human-gated counsel export` means outward counsel-facing delivery is still blocked until the persisted snapshot review state is `human_verified` or `export_approved`

## Workspace contract

Tracked operator docs:

- `docs/agent/Plan.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/question_register_template.md`
- `docs/agent/open_tasks_companion_template.md`
- `docs/agent/mcp_client_config_snippet.md`
- `docs/agent/email_matter_investigation_checkpoint_template.md`

Deprecated operator docs:

- `docs/agent/deprecated/Plan.md`
- `docs/agent/deprecated/email_matter_investigation_runbook.md`

Local-only matter inputs:

- `private/ingest/`
- `private/tests/materials/`

Local-only analysis outputs:

- `private/tests/results/`
- `private/tests/results/README.local.md`
- `private/tests/results/active_run.json`
- `private/tests/results/_checkpoints/`

Recommended output directories:

- `private/tests/results/00_intake_lock/`
- `private/tests/results/01_corpus_inventory/`
- `private/tests/results/02_intake_repair/`
- `private/tests/results/03_exhaustive_run/`
- `private/tests/results/04_evidence_index/`
- `private/tests/results/05_master_chronology/`
- `private/tests/results/06_behavior/`
- `private/tests/results/07_comparators/`
- `private/tests/results/08_issue_matrix/`
- `private/tests/results/09_requests_preservation/`
- `private/tests/results/10_contradictions/`
- `private/tests/results/11_memo_draft_dashboard/`
- `private/tests/results/_archive/`

Do not place sensitive matter content in tracked docs.

Supported results-workspace owner:

- refresh the active manifest through `python -m src.cli case refresh-active-run ...`
- move superseded result artifacts through `python -m src.cli case archive-results ...`
- do not rely on hand-edited `active_run.json` updates when the supported CLI workflow is available

Current invalidation note:

- local result files under `private/tests/results/` from the CLI-driven cycle remain on disk for auditability
- they are not current completion evidence
- unless refreshed via MCP queries, treat them as `RERUN`

## Source-of-truth MCP products

The campaign should converge on these products:

- `email_case_prompt_preflight`
- `email_case_full_pack`
- `email_case_evidence_index`
- `email_case_master_chronology`
- `email_case_comparator_matrix`
- `email_case_issue_matrix`
- `email_case_skeptical_review`
- `email_case_document_request_checklist`
- `email_case_actor_witness_map`
- `email_case_promise_contradictions`
- `email_case_lawyer_briefing_memo`
- `email_case_draft_preflight`
- `email_case_controlled_draft`
- `email_case_retaliation_timeline`
- `email_case_dashboard`

Execution note:

- before a manifest-backed exhaustive review is available, use `email_case_analysis_exploratory` and read the needed product section from that payload
- switch to the dedicated `email_case_*` product tools once the source anchor set is stable and the matter manifest is ready

Required end-state local products:

- evidence index
- master chronology
- behavior and language analysis
- comparator matrix
- issue matrix
- skeptical review
- document-request checklist
- actor and witness map
- contradiction table
- retaliation timeline where applicable
- lawyer briefing memo
- dashboard
- open-questions closure register
- open-tasks companion file

Canonical open-tasks companion file:

- `private/tests/results/11_memo_draft_dashboard/open_tasks_companion.md`

## Full MCP utilization policy

The dedicated `email_case_*` outputs remain the authoritative end-state products for the campaign.

That is not a reason to underuse the rest of the MCP surface.

For this runbook, the broader `email_*`, `evidence_*`, provenance, and export tools must be used whenever they improve one of these causes:

- scope discovery
- source-class confirmation
- candidate discovery
- thread expansion
- quote anchoring
- actor / witness mapping
- coordination testing
- timing-pattern testing
- comparator search
- contradiction repair
- preservation targeting
- outward export and chain-of-custody support

Hard rule:

- do not treat supportive MCP calls as optional convenience when they close a real proof gap, reduce overclaiming, or validate a disputed pattern

### MCP lanes by function

Use these MCP lanes deliberately.

Archive and scope discovery:

- `email_stats`
- `email_list_folders`
- `email_list_senders`
- `email_discovery`
- `email_topics`
- `email_clusters`
- `email_quality`
- `email_browse`
- `email_attachments`

Progressive search and candidate control:

- `email_triage`
- `email_search_structured`
- `email_search_by_entity`
- `email_find_similar`
- `email_thread_lookup`
- `email_scan`

Deep reading and message-level extraction:

- `email_deep_context`
- `email_thread_summary`
- `email_action_items`
- `email_decisions`

Evidence capture and verification:

- `evidence_add`
- `evidence_add_batch`
- `evidence_query`
- `evidence_update`
- `evidence_verify`
- `evidence_overview`

Relationship, coordination, and timing analysis:

- `email_contacts`
- `relationship_summary`
- `relationship_paths`
- `shared_recipients`
- `coordinated_timing`
- `email_network_analysis`
- `email_temporal`
- `email_entity_timeline`

Provenance, custody, and export:

- `custody_chain`
- `email_provenance`
- `evidence_provenance`
- `email_export`
- `evidence_export`
- `email_dossier`
- `email_case_export`

### Suitability rules by issue cause

Use the broader MCP surface most aggressively for these issue causes.

Eingruppierung, task withdrawal, and role-scope change:

- use `email_search_structured`, `email_triage`, `email_find_similar`, `email_thread_lookup`, `email_action_items`, and `email_decisions`
- use `email_attachments` when Tätigkeitsdarstellungen, evaluation sheets, or role descriptions may exist outside the message body

Disability disadvantage, accommodation, BEM, and medical recommendations ignored:

- use `email_search_by_entity`, `email_search_structured`, `email_thread_lookup`, `email_browse` with calendar scope where relevant, and `email_attachments`
- use `email_decisions` and `email_action_items` to isolate stated obligations, promised follow-up, and ignored recommendations

Retaliation, Maßregelung, escalation, and coordination:

- use `email_temporal`, `coordinated_timing`, `shared_recipients`, `relationship_paths`, `relationship_summary`, and `email_entity_timeline`
- use `email_deep_context` on key trigger and response emails before retaining any strong motive or coordination claim

SBV participation, PR participation, and procedural omission:

- use `email_search_by_entity`, `email_search_structured`, `email_thread_lookup`, `shared_recipients`, and `email_browse` for calendar items
- use `email_decisions` and `email_action_items` to identify whether participation was promised, omitted, or bypassed

Comparator treatment:

- use `email_case_comparator_matrix` as the final product, but drive comparator discovery with `email_search_structured`, `email_find_similar`, `email_contacts`, `shared_recipients`, and `relationship_summary`

Worktime control, surveillance, and response-time pressure:

- use `email_temporal`, `email_entity_timeline`, `email_search_structured`, and `email_attachments`
- use `coordinated_timing` where multiple actors appear to move at once around a trigger event

Witness relevance and custodian discovery:

- use `email_case_actor_witness_map`, `email_contacts`, `relationship_summary`, `relationship_paths`, and `email_network_analysis`

### Search discipline

Default search sequence:

1. `email_triage` or `email_search_structured` to identify candidates
2. `email_scan` to deduplicate and preserve progressive review state
3. `email_thread_lookup` or `email_find_similar` to expand context
4. `email_deep_context` to inspect exact wording and source anchors
5. `evidence_add` or `evidence_add_batch` only after exact quote verification

Do not jump directly from a broad hit list to a retained legal-significance claim without the deep-context step.

## Evidence taxonomy

Each important point in local outputs must be tagged as:

- `DE`: direct evidence
- `RI`: reasonable inference
- `UP`: unresolved point
- `MP`: missing proof

Each important record should also carry an evidentiary strength flag:

- `high`
- `medium`
- `low`
- `unknown / needs source check`

## Core issue tags

Use these issue tags consistently:

- `Eingruppierung`
- `AGG / disability disadvantage`
- `retaliation / Maßregelung`
- `mobile work / home office`
- `SBV participation`
- `PR participation`
- `§167 SGB IX prevention / BEM`
- `medical recommendations ignored`
- `task withdrawal / TD fixation`
- `worktime control / surveillance`
- `witness relevance`
- `comparator evidence`

## Campaign modes

### Mode A: Intake repair

Use when the matter is still blocked by missing structured fields.

Primary goal:

- move from prompt ambiguity to a stable structured scope

Primary MCP:

- `email_case_prompt_preflight`

Supportive MCP when the prompt is too vague, overbroad, or materially inconsistent with the archive:

- `email_stats`
- `email_list_folders`
- `email_list_senders`
- `email_search_structured`
- `email_search_by_entity`
- `email_discovery`

### Mode B: Exhaustive matter review

Use when the matter scope and materials are sufficient for manifest-backed review.

Primary goal:

- build the full product set and stress-test it

Primary MCP:

- `email_case_full_pack`

Supportive MCP for proof-gap repair and stress testing during the same cycle:

- `email_deep_context`
- `email_thread_lookup`
- `email_action_items`
- `email_decisions`
- `evidence_verify`

### Mode C: Delta refresh

Use when new emails, attachments, notes, calendar items, or time records arrive.

Primary goal:

- rerun only the affected waves while preserving prior structure and gates

Primary supportive MCP:

- `email_search_structured`
- `email_attachments`
- `email_entity_timeline`
- `email_scan`

### Mode D: Crash recovery

Use when:

- MCP server exited unexpectedly
- a tool call returned incomplete output
- the run stopped mid-phase
- the agent process was interrupted

Primary goal:

- restore the last valid checkpoint and continue from the earliest invalidated phase without human help

Primary actions:

- restart MCP with the active runtime contract
- inspect `private/tests/results/active_run.json`
- inspect the referenced checkpoint and active result artifacts
- repair any stale runtime, checkpoint, or workflow issue that caused the interruption
- determine the earliest invalidated phase
- rerun that phase and all dependent downstream phases

## Autonomous remediation contract

This campaign must repair local execution blockers on the fly while answering questions.

Treat these as execution defects first:

- query or filter mismatch
- missing context expansion
- wrong MCP tool choice for the current phase
- schema or alias mismatch between caller and tool
- truncation or response-budget failure
- stale runtime, cache, or checkpoint state
- repo-side workflow bugs discovered during the run

Required remediation order:

1. classify the blocker
2. apply the smallest local repair that can restore forward progress
3. rerun the failed MCP step
4. rerun the affected phase gate if the output changed materially
5. continue the campaign

Only treat a question as blocked when the missing piece is truly external to the current repo and archive, such as a record that is not present in scope.

Open-tasks logging is therefore for:

- true missing records
- residual uncertainty after the repaired run
- downstream refresh work after a repaired upstream phase changed the evidence base

It is not the default home for fixable repo, tooling, or workflow defects.

## Operating loop

Each investigation cycle should follow this loop:

1. confirm scope, runtime, and materials
2. inventory supplied versus missing sources
3. repair intake ambiguity
4. run the bounded MCP product set
5. classify every hurdle as either execution defect or true record gap
6. remediate every locally fixable execution defect and rerun the failed step
7. inspect repaired outputs against the phase gate
8. convert remaining proof gaps into explicit requests or targeted corpus questions
9. checkpoint
10. resume only from the highest invalidated downstream phase
11. continue until all reachable questions and reports are closed

## Query-pack and evidence-quota discipline

Every wave must use:

- the matching wave section in `docs/agent/question_execution_query_packs.md`
- `3` to `5` retrieval queries with one shared `scan_id`
- an explicit supporting-evidence lane and counterevidence lane

Minimum evidence quotas:

- `answered by direct evidence`
  - `2` supporting anchors where available
  - `1` counterevidence check
- `partially answered`
  - `3` supporting anchors
  - `1` counter or competing-explanation anchor
- `requires missing record`
  - `1` source-backed explanation of the gap
  - the exact missing-record class

Wording-sensitive questions must preserve at least one verified quote before closure.

## Completion contract

The campaign is complete only when:

- all wave checkpoints exist for the executed scope
- all `Q` items in the live register are closed with a closure status
- every important finding is tied to source evidence, date, and actor
- every unresolved issue is explicitly marked as unresolved or blocked
- the required report set is generated
- the final dashboard and briefing memo are refreshed after the last evidentiary change
- every required analytical artifact was produced through MCP server queries rather than CLI-only execution

The campaign is not complete merely because a single MCP batch finished.


## Detailed Sections

- Phase map: `docs/agent/matter_analysis/phase_map.md`
- Wave program: `docs/agent/matter_analysis/wave_program.md`
- Pattern heuristics: `docs/agent/matter_analysis/heuristics.md`

- Operations, gate model, resume matrix, checkpoint rules, promotion rules, and recovery procedures moved to `docs/agent/matter_analysis/operations_and_gates.md`.
