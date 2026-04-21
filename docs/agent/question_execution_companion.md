# Question Execution Companion

Status: `operator-facing`

Purpose:

- turn the `Q1` to `Q39` register into an MCP-centered execution plan
- keep question closure aligned with `docs/agent/email_matter_analysis_single_source_of_truth.md`
- make the next run question-first instead of artifact-first

Canonical dependencies:

- `docs/agent/Plan.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/MCP_TOOLS.md`
- `docs/agent/question_execution_prompt_pack.md`
- `docs/agent/question_execution_query_packs.md`
- `docs/agent/question_register_template.md`
- `docs/agent/open_tasks_companion_template.md`

This file is a companion, not a replacement.

The single-source-of-truth runbook still defines:

- campaign gates
- phase ordering
- completion contract
- checkpoint rules

This companion adds:

- MCP tool bundles per question family
- query-pack discipline per wave
- question-to-wave mapping
- execution order inside each wave
- closure criteria per question family

## Core rule

For every `Q` item:

- start with search and context expansion MCP tools
- for German-dominant matters, start with German-native retrieval and German answer drafting unless an explicit English-facing output requirement overrides it
- before a manifest-backed exhaustive review exists, use `email_case_analysis_exploratory` and read the needed product section from its payload
- move to dedicated `email_case_*` outputs only after the source anchor set is stable and the matter manifest is ready
- treat query mistakes, schema mismatches, truncation failures, runtime issues, and wrong-tool choices as execution defects to repair inside the run
- rerun the affected MCP path after each local repair before downgrading the question
- record both supporting and counterevidence
- close the question only as:
  - `answered by direct evidence`
  - `partially answered`
  - `not answered`
  - `requires missing record`

Do not close a question directly from:

- prompt wording
- prior dossier prose
- prior CLI artifacts
- one isolated email when a thread or attachment likely changes the reading

## German-first language gate

Before Wave 1 on a fresh or rebuilt cycle:

- run `email_quality(check='languages')`
- if language analytics are missing or stale, run `email_admin(action='reingest_analytics')` and rerun `email_quality(check='languages')`
- when German is the dominant corpus language or the matter posture is German employment, set:
  - `output_language='de'`
  - `translation_mode='source_only'`
- treat English-facing rendering as an explicit downstream export choice, not the default working mode
- do not trust `detected_language` blindly on short, forwarded, or formulaic messages
- preserve umlaut-native and ASCII-fallback query variants in the wave pack

## Intake and mixed-source gate

Before Wave 1 on a fresh or rebuilt cycle:

- rebuild `case_scope` from real dated trigger events, actors, issue tracks, and known missing-record classes
- rebuild `matter_manifest` from the current materials directory
- when the corpus baseline or matter posture is German-dominant, keep the rebuilt case input on:
  - `output_language='de'`
  - `translation_mode='source_only'`
- if the manifest contains non-email supplied records, keep the run on:
  - `source_scope='mixed_case_file'`
  - `review_mode='exhaustive_matter_review'`
- inspect `case_scope_quality.recommended_next_inputs` before accepting the rebuilt scope as stable

## Query-pack rule

For every wave:

- use the matching section in `docs/agent/question_execution_query_packs.md`
- run `3` to `5` retrieval queries with one shared `scan_id`
- include German exact-phrase, actor-plus-issue, timeline, orthographic-variant, and attachment or mixed-source lanes where relevant
- add English or translated search phrasing only after the German lanes have run
- use `email_find_similar` or `email_thread_lookup` on the strongest recovered hit before concluding the wave is sparse

## Evidence preservation quota

Minimum per question:

- `answered by direct evidence`
  - `2` supporting anchors where available
  - `1` counterevidence check or explicit `none located`
- `partially answered`
  - `3` supporting anchors
  - `1` counter or competing-explanation anchor
- `requires missing record`
  - `1` source-backed gap reason
  - the exact missing-record class

Wording-sensitive questions must preserve and verify at least one exact quote.

## Standard MCP lane

Use this baseline sequence unless a wave below says otherwise:

1. `3` to `5` query-pack retrieval calls through `email_search_structured` or `email_triage` with one wave-level `scan_id`
2. `email_scan`
3. `email_thread_lookup` or `email_find_similar`
4. `email_deep_context`
5. one of:
   - `email_case_analysis_exploratory` and extract the relevant product section while the run is still retrieval-bounded
   - once manifest-backed exhaustive review is ready, use the dedicated product tool:
   - `email_case_evidence_index`
   - `email_case_master_chronology`
   - `email_case_comparator_matrix`
   - `email_case_issue_matrix`
   - `email_case_document_request_checklist`
   - `email_case_actor_witness_map`
   - `email_case_promise_contradictions`
6. `evidence_add` or `evidence_add_batch` for exact quote preservation when the question hinges on wording
7. `evidence_verify` before marking a wording-sensitive question green
8. if any step fails or returns unusable output, enter the remediation loop below before downgrading the question

Local execution support:

- `python -m src.cli case execute-wave --input case.json --wave wave_1 --scan-id-prefix matter-2026-04`
- `python -m src.cli case execute-all-waves --input case.json --scan-id-prefix matter-2026-04`
- `python -m src.cli case gather-evidence --input case.json --run-id investigation_2026-04-16_P60 --phase-id P60 --scan-id-prefix matter-2026-04`
- these commands are the CLI entrypoints for the shared campaign workflow exposed through MCP `email_case_execute_wave`, `email_case_execute_all_waves`, and `email_case_gather_evidence`
- `case gather-evidence` is not an end-of-run append step; it must persist each completed wave into durable evidence storage before the next wave starts
- dedicated legal-support analytical products still remain on the broader MCP `email_case_*` surface
- they now emit canonical per-wave `scan_id` metadata, `archive_harvest`, coverage-gate status, quality-gate status, actor-discovery summaries, query-lane classes, and `wave_local_views` so the local rerun can be audited wave by wave instead of only as a batch summary

Evidence-harvest rule:

- `execute-all-waves` is not enough for evidence collection by itself
- after a meaningful rerun, execute `case gather-evidence` or MCP `email_case_gather_evidence`
- treat harvested evidence candidates and exact-quote promotion as a required campaign phase before closure claims are refreshed

Archive-harvest rule:

- the local wave runtime now separates archive harvest from compact synthesis
- for email-centered questions, the indexed mailbox remains the primary evidence substrate
- a thin matter manifest supplements non-email records; it does not replace archive harvesting
- if `archive_harvest.coverage_gate.status == "needs_more_harvest"`, do not treat the wave as closure-ready yet
- if `archive_harvest.quality_gate.status == "weak"`, do not treat the wave as detection-complete even when breadth is acceptable
- `case gather-evidence` now prefers the enriched archive evidence bank over the compact outward answer surface, so raw thread and attachment harvest can exceed the visible compact candidate list

Results-control rule:

- after each meaningful rerun, refresh `private/tests/results/active_run.json`
- read `active_run.json.curation.status` before resuming
- do not treat a newer raw rerun as ledger-current when `curation.status` is `raw_results_pending_curation`, `partially_curated_stale`, or `stale_curated_ledgers`

Autonomy boundary:

- `autonomous internal completion` means the campaign is runnable, checkpointed, and ledger-current for internal analysis
- `human-gated counsel export` means counsel-facing delivery remains blocked until the persisted snapshot review state clears the review gate

## Autonomous remediation loop

When a question hits a hurdle, do not treat that hurdle as the answer state until it has been classified.

Classify the blocker as one of:

- retrieval mismatch
- language detection or language-lane mismatch
- missing context expansion
- tool-contract mismatch
- truncation or budget failure
- runtime or checkpoint issue
- phase-order or workflow misuse
- true external missing record

Required actions by blocker type:

- retrieval mismatch
  - rewrite the query, widen or narrow filters, switch between `email_search_structured`, `email_triage`, `email_find_similar`, and rerun immediately
- language detection or language-lane mismatch
  - inspect corpus language baseline, sample the affected messages, widen German-native and umlaut or ASCII fallback lanes, rerun `email_admin(action='reingest_analytics')` if analytics are missing or stale, and rerun the wave step without over-trusting `detected_language`
- missing context expansion
  - add `email_thread_lookup`, `email_attachments`, `email_deep_context`, `email_provenance`, or the relevant product tool before reassessing the question
- tool-contract mismatch
  - patch the repo-side model, alias, or workflow bug, run targeted verification, and rerun the failed MCP call in the same wave
- truncation or budget failure
  - repair the payload surface or fallback path, then rerun the same call and preserve the repaired source anchor
- runtime or checkpoint issue
  - restart MCP, reload the latest valid checkpoint, and rerun the failed wave step
- phase-order or workflow misuse
  - switch to the correct exploratory or dedicated product path and rerun the question
- true external missing record
  - mark the question `requires missing record`, state the missing item explicitly, and continue the rest of the wave

Hard rule:

- no wave closes while a locally fixable execution blocker remains unresolved

## Question record

Persist each question with these fields:

- `question_id`
- `wave`
- `status`
- `query_language_lanes`
- `language_detection_notes`
- `best_supporting_sources`
- `best_counter_sources`
- `current_answer`
- `remaining_uncertainty`
- `missing_record_needed`
- `blocker_class`
- `remediation_taken`
- `rerun_count`
- `last_phase_touched`
- `next_mcp_step`

Use the tracked template:

- `docs/agent/question_register_template.md`

If a question remains open after the wave finishes and all local remediation paths are exhausted, also update:

- `private/tests/results/11_memo_draft_dashboard/open_tasks_companion.md`

Initialize that local file from:

- `docs/agent/open_tasks_companion_template.md`

For kickoff, resume, per-wave execution, blocker remediation, and closure prompts, use:

- `docs/agent/question_execution_prompt_pack.md`

## Wave Execution Map

### Wave 1: Dossier Reconciliation

Questions:

- `Q10` Meeting-note contradiction chain
- `Q11` Legacy dossier quote repair
- `Q34` Promise-to-reversal window

Primary MCP bundle:

- `email_search_structured`
- `email_thread_lookup`
- `email_deep_context`
- `email_case_analysis_exploratory` (`promise_contradiction_analysis` section) before manifest-backed review
- `email_case_promise_contradictions` once exhaustive matter review is ready
- `email_provenance`
- `evidence_provenance`

Required outputs:

- contradiction rows with both sides source-anchored
- quote-repair ledger for legacy dossier claims
- short note separating:
  - confirmed contradiction
  - tension without contradiction
  - unsupported legacy statement

Closure rule:

- no contradiction question closes green unless both the earlier statement and later conduct are tied to source

### Wave 2: Null-Result And Silence Evidence

Questions:

- `Q1` PA silence after complaint
- `Q12` Negative evidence registry
- `Q24` Counterevidence register
- `Q37` Follow-up silence after explicit clarification requests

Primary MCP bundle:

- `email_search_structured`
- `email_thread_lookup`
- `email_deep_context`
- `email_temporal`
- `email_case_master_chronology`
- `email_case_document_request_checklist`

Required outputs:

- silence intervals with explicit start event and expected follow-up
- counterevidence list
- negative-evidence note that distinguishes:
  - searched but not found
  - likely missing record
  - ambiguous due to limited scope

Closure rule:

- a silence question cannot be `answered by direct evidence` unless the triggering communication and the missing expected response are both explicit

### Wave 3: Complaint -> Reaction -> Follow-up Chains

Questions:

- `Q13` Leadership-transition reversal
- `Q14` Support-message implementation gap
- `Q21` Management-side explanation gap
- `Q22` Alibi-measure versus effective-remedy
- `Q26` Upper-level escalation response
- `Q30` Formal notice and deadline trail

Primary MCP bundle:

- `email_search_structured`
- `email_find_similar`
- `email_thread_lookup`
- `email_action_items`
- `email_decisions`
- `email_case_master_chronology`
- `email_case_issue_matrix`
- `email_case_skeptical_review`

Required outputs:

- chronology chain from complaint or escalation to reaction
- implementation-versus-message table
- strongest non-retaliatory alternative explanation

Closure rule:

- any post-complaint treatment-change question must show both the protected or escalation event and the later response window

### Wave 4: Home Office / Mobiles Arbeiten Differential

Questions:

- `Q8` Comparator mobile-work differential
- `Q32` DV baseline versus claimant-specific deviation

Primary MCP bundle:

- `email_search_structured`
- `email_find_similar`
- `email_attachments`
- `email_case_comparator_matrix`
- `email_case_issue_matrix`

Required outputs:

- baseline rule extract from supplied policy material
- claimant-specific treatment row
- comparator row or explicit comparator gap

Closure rule:

- if no named comparator survives source review, downgrade to `partially answered` or `requires missing record`

### Wave 5: Eingruppierung / Tätigkeitsdarstellung / Task Withdrawal

Questions:

- `Q7` TD fixation after task withdrawal
- `Q15` Actual-duties acknowledgement versus later denial
- `Q33` Project brief role-evidence
- `Q36` Exclusion from TD or role-clarification process

Primary MCP bundle:

- `email_search_structured`
- `email_attachments`
- `email_thread_lookup`
- `email_action_items`
- `email_decisions`
- `email_case_evidence_index`
- `email_case_master_chronology`

Required outputs:

- actual-duties evidence table
- role-acknowledgement versus later-denial comparison
- project-brief exhibit list

Closure rule:

- no duty-scope question closes green without at least one source that ties the claimant to concrete work or role recognition

### Wave 5A: EG 12 Proof-Building

Questions:

- `Q17` EG 12 management-transmission proof
- `Q18` EG 12 continuity proof
- `Q19` EG 12 under-recording proof
- `Q20` EG 12 institutional-reliance proof

Primary MCP bundle:

- `email_search_structured`
- `email_find_similar`
- `email_attachments`
- `email_deep_context`
- `email_case_evidence_index`
- `email_case_issue_matrix`

Required outputs:

- exhibit set for transmission, continuity, under-recording, and reliance
- exact quote set for management-side acknowledgement where present
- missing-proof list for tariff-relevant gaps

Closure rule:

- if the corpus shows only weak role references but not tariff-relevant continuity, keep at most `partially answered`

### Wave 5B: Project-Brief And Role-Ownership Evidence

Questions:

- `Q33` Project brief role-evidence

Primary MCP bundle:

- `email_attachments`
- `email_search_structured`
- `email_case_evidence_index`

Required outputs:

- project brief inventory
- role ownership citations
- link to downstream EG 12 and task-withdrawal questions

Closure rule:

- this question is subordinate to Wave 5 and Wave 5A and should be refreshed when those waves change

### Wave 6: BEM / §167 SGB IX / Prevention Failures

Questions:

- `Q5` BEM process continuity
- `Q6` Medical recommendation handling
- `Q27` Return-from-AU protection question set
- `Q28` §167 framing question
- `Q29` Medical recommendation implementation trail

Primary MCP bundle:

- `email_search_by_entity`
- `email_search_structured`
- `email_thread_lookup`
- `email_attachments`
- `email_decisions`
- `email_case_master_chronology`
- `email_case_issue_matrix`
- `email_case_document_request_checklist`

Required outputs:

- event chain from medical record or AU phase to employer response
- implementation gap note for each medical recommendation
- explicit distinction between:
  - prevention framing
  - accommodation implementation
  - return-to-work handling

Closure rule:

- do not mark these questions green when only medical records exist without employer-side implementation or response material

### Wave 7: SBV / PR Participation Path

Questions:

- `Q3` SBV request persistence
- `Q4` PR process visibility
- `Q25` Participation-trail omission
- `Q38` PR-approved work versus management stop

Primary MCP bundle:

- `email_search_by_entity`
- `email_search_structured`
- `email_thread_lookup`
- `shared_recipients`
- `email_browse`
- `email_case_actor_witness_map`
- `email_case_document_request_checklist`

Required outputs:

- participation timeline
- actor map for SBV / PR / PA / management
- omission table showing where participation was expected versus evidenced

Closure rule:

- participation questions require explicit visibility into who was copied, consulted, bypassed, or informed afterward

### Wave 8: time system / Attendance Control / Surveillance

Questions:

- `Q9` time system correction trail
- `Q31` time system summary versus raw-proof gap

Primary MCP bundle:

- `email_search_structured`
- `email_search_by_entity`
- `email_attachments`
- `email_temporal`
- `email_case_evidence_index`
- `email_case_document_request_checklist`

Required outputs:

- correction or attendance-control timeline
- summary-versus-raw-record gap note
- explicit statement whether the archive contains:
  - policy only
  - summary only
  - raw proof

Closure rule:

- if only summary records exist and no raw proof survives, mark `requires missing record`

### Wave 9: Coordination And Actor Cluster Analysis

Questions:

- `Q2` Schwellenbach routine-only period
- `Q16` Gatekeeper routing pattern
- `Q23` Comparator baseline records
- `Q35` Tasks-only-via-PA bottleneck
- `Q39` Calendar and cancellation pattern

Primary MCP bundle:

- `email_search_structured`
- `email_contacts`
- `relationship_summary`
- `relationship_paths`
- `shared_recipients`
- `coordinated_timing`
- `email_network_analysis`
- `email_browse`

Required outputs:

- coordination windows
- routing and gatekeeper note
- calendar visibility note where applicable
- comparator-discovery note for unresolved baseline questions

Closure rule:

- do not infer deliberate coordination from adjacency alone; require either synchronized timing, recipient overlap, or thread linkage

### Wave 10: Open Questions Register

Questions:

- all `Q1` to `Q39`

Primary MCP bundle:

- `email_case_dashboard`
- `email_case_lawyer_briefing_memo`
- `email_case_draft_preflight`

Required outputs:

- closure register for all questions
- unresolved list
- missing-record campaign carry-forward
- outward allegation ceiling consistent with the weakest still-open major question

Closure rule:

- no global closure unless every `Q` has a status, source anchors, and a next-step or final answer

## Question Index

Use this index when deciding which wave to rerun.

| Question | Primary wave | Core MCP emphasis |
| --- | --- | --- |
| `Q1` | Wave 2 | silence, chronology, follow-up gap |
| `Q2` | Wave 9 | actor pattern, coordination, routing |
| `Q3` | Wave 7 | SBV trail, participation visibility |
| `Q4` | Wave 7 | PR trail, process visibility |
| `Q5` | Wave 6 | BEM continuity, prevention process |
| `Q6` | Wave 6 | medical recommendation handling |
| `Q7` | Wave 5 | TD fixation, task withdrawal |
| `Q8` | Wave 4 | comparator mobile-work differential |
| `Q9` | Wave 8 | time system correction trail |
| `Q10` | Wave 1 | contradiction chain |
| `Q11` | Wave 1 | quote repair, provenance |
| `Q12` | Wave 2 | negative evidence registry |
| `Q13` | Wave 3 | leadership transition reversal |
| `Q14` | Wave 3 | support message implementation gap |
| `Q15` | Wave 5 | duties acknowledgement versus denial |
| `Q16` | Wave 9 | gatekeeper routing |
| `Q17` | Wave 5A | EG 12 transmission proof |
| `Q18` | Wave 5A | EG 12 continuity proof |
| `Q19` | Wave 5A | EG 12 under-recording proof |
| `Q20` | Wave 5A | EG 12 institutional-reliance proof |
| `Q21` | Wave 3 | management-side explanation gap |
| `Q22` | Wave 3 | alibi-measure versus remedy |
| `Q23` | Wave 9 | comparator baseline discovery |
| `Q24` | Wave 2 | counterevidence register |
| `Q25` | Wave 7 | participation-trail omission |
| `Q26` | Wave 3 | upper-level escalation response |
| `Q27` | Wave 6 | return-from-AU protection |
| `Q28` | Wave 6 | section 167 framing |
| `Q29` | Wave 6 | recommendation implementation trail |
| `Q30` | Wave 3 | formal notice and deadline trail |
| `Q31` | Wave 8 | summary versus raw-proof gap |
| `Q32` | Wave 4 | DV baseline versus deviation |
| `Q33` | Wave 5B | project brief role-evidence |
| `Q34` | Wave 1 | promise-to-reversal window |
| `Q35` | Wave 9 | PA bottleneck pattern |
| `Q36` | Wave 5 | exclusion from role-clarification process |
| `Q37` | Wave 2 | follow-up silence |
| `Q38` | Wave 7 | PR-approved work versus management stop |
| `Q39` | Wave 9 | calendar and cancellation pattern |

## Minimal execution order

Run the questions in this order unless a fresh materials change forces a lower phase restart:

1. Wave 1
2. Wave 2
3. Wave 3
4. Wave 7
5. Wave 6
6. Wave 5
7. Wave 5A
8. Wave 5B
9. Wave 4
10. Wave 8
11. Wave 9
12. Wave 10

Reason:

- early waves reduce false positives in later legal framing
- participation, prevention, and task-scope questions materially affect the allegation ceiling
- coordination analysis should come after chronology, contradiction, and participation paths are already stabilized

## Re-run triggers

Refresh only the necessary waves when new material arrives:

- new contradiction source: rerun Wave 1, then Wave 10
- new silence-breaking response or escalation source: rerun Wave 2 or Wave 3, then Wave 10
- new SBV / PR / PA source: rerun Wave 7, then Wave 10
- new medical, BEM, AU, or prevention source: rerun Wave 6, then Wave 10
- new TD, task, project, or role material: rerun Wave 5, Wave 5A, Wave 5B as applicable, then Wave 10
- new mobile-work or comparator source: rerun Wave 4 or Wave 9, then Wave 10
- new time system raw proof or attendance records: rerun Wave 8, then Wave 10
- new actor or calendar evidence: rerun Wave 9, then Wave 10

## Companion use

Use this companion in the live run like this:

1. pick the active wave
2. run the listed MCP bundle
3. if a hurdle appears, remediate it inside the same wave and rerun the failed step
4. close or downgrade each listed `Q` only after the remediation loop is exhausted
5. persist only irreducibly open items
6. move to the next wave only after every question in the current wave has been touched and every fixable execution blocker has been cleared
