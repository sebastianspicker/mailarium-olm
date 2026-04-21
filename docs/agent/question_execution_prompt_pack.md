# Question Execution Prompt Pack

Status: `operator-facing`

Purpose:

- provide copy-paste prompts for kickoff, resume, wave execution, blocker remediation, checkpointing, and closure
- keep prompt wording aligned with `docs/agent/Plan.md`
- stop the campaign from depending on improvised instructions

Use with:

- `docs/agent/Plan.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/question_execution_query_packs.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_register_template.md`
- `docs/agent/open_tasks_companion_template.md`
- `docs/agent/email_matter_investigation_checkpoint_template.md`

## Required substitutions

Replace these placeholders before use:

- `<checkpoint_path>`
- `<question_register_path>`
- `<open_tasks_path>`
- `<runtime_chromadb_path>`
- `<runtime_sqlite_path>`
- `<case_scope_path>`
- `<case_input_path>`
- `<matter_manifest_path>`
- `<query_pack_path>`
- `<wave_id>`
- `<question_ids>`
- `<materials_dir>`
- `<matter_prompt_path>`
- `<evidence_harvest_path>`
- `<run_id>`
- `<phase_id>`
- `<scan_id_prefix>`

## Mandatory Matter Inputs

Use these as mandatory inputs for any serious run, rerun, post-harvest refinement pass, or resume flow:

- strict case input: `private/cases/case.json`
- durable harvest output: `private/results/evidence-harvest.json`
- active identifiers:
  - `run_id`
  - `phase_id`
  - `scan_id_prefix`
- any known human corrections already verified for the matter:
  - verified trigger events
  - alleged adverse actions
  - comparators
  - role hints
  - institutional actors or mailboxes

Do not treat free-form recollection or stale prompt fragments as a replacement when those artifacts already exist.

## MCP Readiness Prompt

```text
Use docs/agent/Plan.md, docs/agent/mcp_client_config_snippet.md, and docs/agent/email_matter_analysis_single_source_of_truth.md as the contract.

1. Verify the MCP server is connected to the private runtime corpus:
   - chromadb path: <runtime_chromadb_path>
   - sqlite path: <runtime_sqlite_path>
2. Confirm the question-execution surface is available by checking at least:
   - email_stats
   - email_admin(action="diagnostics")
   - email_quality(check="languages")
   - email_search_structured
   - email_triage
   - email_thread_lookup
   - email_deep_context
   - email_scan
   - evidence_add
   - evidence_verify
   - email_case_analysis_exploratory
   - email_case_full_pack
3. Report any missing or failing MCP surface as an execution blocker and repair it immediately before proceeding.
4. If language analytics are missing or empty, run email_admin(action="reingest_analytics") and rerun email_quality(check="languages").
5. Do not use CLI-generated analytical artifacts as completion evidence.
```

## Corpus Language Baseline Prompt

```text
Use docs/agent/Plan.md, docs/agent/question_execution_query_packs.md, and docs/agent/email_matter_analysis_single_source_of_truth.md as the language-baseline contract.

Before Wave 1:

1. Run email_quality(check="languages").
2. If no language analytics are available, run email_admin(action="reingest_analytics") and rerun email_quality(check="languages").
3. Record the dominant corpus language.
4. If German is dominant or the matter posture is German employment, set the active case input to:
   - output_language=`de`
   - translation_mode=`source_only`
5. Treat English output only as an explicit downstream export choice.
6. Note any obvious language-detection drift on short, forwarded, or header-heavy messages and carry that into the wave query design.
```

## Intake Rebuild Prompt

```text
Use docs/agent/Plan.md, docs/agent/question_execution_query_packs.md, and docs/agent/email_matter_analysis_single_source_of_truth.md as the intake contract.

Rebuild the active matter inputs before Wave 1.

Required behavior:
- replace synthetic validation anchors with real dated trigger events, actors, issue tracks, and known missing-record classes
- rebuild or confirm:
  - <case_scope_path>
  - <matter_manifest_path>
  - <case_input_path>
- require these matter inputs before continuing:
  - `private/cases/case.json`
  - active `run_id`, `phase_id`, and `scan_id_prefix`
  - any known human corrections for verified trigger events, alleged adverse actions, comparators, role hints, and institutional actors or mailboxes
- inspect case-scope quality and record any still-missing recommended inputs
- if the corpus baseline or matter posture is German-dominant, keep the rebuilt input on:
  - output_language=`de`
  - translation_mode=`source_only`
- if the manifest contains non-email supplied records, keep the run on:
  - source_scope=`mixed_case_file`
  - review_mode=`exhaustive_matter_review`
- do not continue into wave execution until the rebuilt input validates cleanly
```

## Full Campaign Kickoff Prompt

```text
Use docs/agent/Plan.md, docs/agent/question_execution_companion.md, docs/agent/question_execution_query_packs.md, and docs/agent/email_matter_analysis_single_source_of_truth.md as binding instructions.

Start a full autonomous matter-analysis run.

Requirements:
- work question-first, not artifact-first
- use MCP queries only for analytical results
- use German-native retrieval and German answer drafting when the corpus baseline or matter posture is German-dominant
- rebuild the active case scope and matter manifest first if the current inputs still use synthetic placeholders
- read and carry forward as mandatory inputs:
  - `private/cases/case.json`
  - `private/results/evidence-harvest.json` when it already exists for the active run
  - the current `run_id`, `phase_id`, and `scan_id_prefix`
  - any known human corrections for verified trigger events, alleged adverse actions, comparators, role hints, and institutional actors or mailboxes
- initialize and maintain:
  - <question_register_path>
  - <open_tasks_path>
  - <checkpoint_path>
- use <query_pack_path> for every wave instead of one broad retrieval query
- follow the wave order from the companion
- repair query, schema, truncation, runtime, checkpoint, or workflow blockers inside the run instead of logging and stopping
- only mark a question requires missing record when the remaining gap is truly external
- treat language-detection drift or English-first query design as execution defects to repair inside the run
- persist checkpoints and question-register deltas after each meaningful wave

Begin with runtime verification, corpus inventory, and Wave 1.
```

## Resume Prompt

```text
Use docs/agent/Plan.md, docs/agent/question_execution_companion.md, docs/agent/email_matter_analysis_single_source_of_truth.md, `private/tests/results/active_run.json`, and <checkpoint_path> as the resume contract.

Resume the matter-analysis campaign from the latest valid checkpoint.

Required behavior:
- read `private/tests/results/active_run.json` first and trust its active pointers over filename recency guesses
- read the checkpoint, question register, and open-tasks companion first
- read and validate the mandatory matter inputs before resuming:
  - `private/cases/case.json`
  - `private/results/evidence-harvest.json` when the active run has already harvested evidence
  - the current `run_id`, `phase_id`, and `scan_id_prefix`
  - any known human corrections for verified trigger events, alleged adverse actions, comparators, role hints, and institutional actors or mailboxes
- verify the MCP runtime still points to:
  - <runtime_chromadb_path>
  - <runtime_sqlite_path>
- verify the recorded corpus language baseline still holds or refresh it with email_quality(check="languages")
- identify the next incomplete or rerun wave
- continue autonomously until the next checkpoint boundary
- if you hit a locally fixable blocker, repair it, verify the repair, rerun the failed MCP step, and continue
- do not repeat already green work unless the runbook says that wave must refresh
```

## Wave Execution Prompt Template

```text
Use docs/agent/question_execution_companion.md for the wave mapping, docs/agent/question_execution_query_packs.md for query design, and docs/agent/email_matter_analysis_single_source_of_truth.md for gates and checkpoints.

Execute <wave_id> for <question_ids>.

Required behavior:
- start from the standard MCP lane unless the wave defines a different bundle
- load the matching wave section from <query_pack_path>
- run `3` to `5` retrieval queries with one shared `scan_id`
- make the first retrieval lanes German-native when the matter is German-dominant
- preserve umlaut-native and ASCII-fallback spellings in the query pack
- collect both supporting and counterevidence
- meet the minimum evidence quota before closure
- update <question_register_path> for every touched question
- write a checkpoint to <checkpoint_path> using the checkpoint template
- update <open_tasks_path> only for irreducible missing-record or downstream-refresh items
- if a tool call fails, classify the blocker, repair it immediately, rerun the MCP path, and continue the wave
- do not close any question green without meeting the wave-specific closure rule
```

## Blocker Remediation Prompt

```text
Treat the current failure as an execution defect, not a question outcome.

1. Classify the blocker:
   - retrieval mismatch
   - language detection or language-lane mismatch
   - missing context expansion
   - tool-contract mismatch
   - truncation or budget failure
   - runtime or checkpoint issue
   - phase-order or workflow misuse
   - true external missing record
2. Repair locally fixable classes immediately.
3. Run targeted verification for the repair.
4. Rerun the failed MCP step in the same wave.
5. Update <question_register_path> with:
   - blocker_class
   - remediation_taken
   - rerun_count
   - next_mcp_step
6. Only if the remaining gap is external, write the item into <open_tasks_path>.
```

## Checkpoint And Register Update Prompt

```text
Update the local execution artifacts after the current wave.

Required outputs:
- checkpoint file at <checkpoint_path>
- refreshed `private/tests/results/active_run.json`
- refreshed question register at <question_register_path>
- refreshed open-tasks companion at <open_tasks_path> if and only if any true missing-record or downstream refresh item remains

Supported workflow owner:
- refresh the active manifest through `python -m src.cli case refresh-active-run ...`
- move superseded local outputs through `python -m src.cli case archive-results ...`
- do not hand-edit `active_run.json` when the CLI helper can write or archive the same state
- require `active_run.json.curation.status` to show whether the register and open-tasks ledgers are current, raw, or stale after the rerun

The checkpoint must record:
- exact runtime paths
- exact matter-input artifacts used:
  - `private/cases/case.json`
  - `private/results/evidence-harvest.json` when applicable
- active identifiers:
  - `run_id`
  - `phase_id`
  - `scan_id_prefix`
- any known human corrections applied for:
  - verified trigger events
  - alleged adverse actions
  - comparators
  - role hints
  - institutional actors or mailboxes
- touched questions
- blocker class and remediation for each non-green question
- next MCP step
- resume rule
```

## Final Closure Prompt

```text
Use docs/agent/Plan.md, docs/agent/question_execution_companion.md, and docs/agent/email_matter_analysis_single_source_of_truth.md as the closure contract.

Close the campaign only after:
- every reachable wave has run
- every touched question is marked as:
  - answered by direct evidence
  - partially answered
  - not answered
  - requires missing record
- all locally fixable execution blockers have been remediated and rerun
- the question register, checkpoint set, and open-tasks companion are synchronized

In the final report, separate:
- direct evidence
- bounded inference
- unresolved point
- true missing record
```

## Wave 1 Prompt

```text
Execute Wave 1: Dossier Reconciliation for Q10, Q11, and Q34.

Use the Wave 1 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- meeting-note contradiction chain
- legacy dossier quote repair
- promise-to-reversal window

MCP emphasis:
- email_search_structured
- email_thread_lookup
- email_deep_context
- email_case_analysis_exploratory using the promise_contradiction_analysis section
- email_case_promise_contradictions once exhaustive review is ready
- email_provenance
- evidence_provenance

Language rule:
- use German-native BEM, protocol, and mobile-work phrasing first
- add umlaut and ASCII fallback variants where relevant
- use English wording only as a supplemental expansion lane

Do not close a contradiction question green unless both the earlier statement and the later conduct are source-anchored.
```

## Wave 2 Prompt

```text
Execute Wave 2: Null-Result And Silence Evidence for Q1, Q12, Q24, and Q37.

Use the Wave 2 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- silence after complaint
- negative evidence registry
- counterevidence register
- follow-up silence after clarification requests

MCP emphasis:
- email_search_structured
- email_thread_lookup
- email_deep_context
- email_temporal
- email_case_master_chronology
- email_case_document_request_checklist

Language rule:
- use German complaint, reply, and silence phrasing first
- preserve institution-specific German labels such as Personalrat, SBV, and HR mailbox

Separate searched-but-not-found, likely missing record, and ambiguous limited-scope outcomes.
```

## Wave 3 Prompt

```text
Execute Wave 3: Complaint -> Reaction -> Follow-up Chains for Q13, Q14, Q21, Q22, Q26, and Q30.

Use the Wave 3 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- complaint or escalation
- management reaction
- follow-up implementation gap
- strongest alternative explanation

MCP emphasis:
- email_search_structured
- email_find_similar
- email_thread_lookup
- email_action_items
- email_decisions
- email_case_master_chronology
- email_case_issue_matrix
- email_case_skeptical_review

Language rule:
- use German escalation, response, and implementation terminology first
- keep English management-language expansions secondary to the German lanes
```

## Wave 4 Prompt

```text
Execute Wave 4: Home Office / Mobiles Arbeiten Differential for Q8 and Q32.

Use the Wave 4 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- policy baseline
- claimant-specific deviation
- comparator-supported differential treatment

MCP emphasis:
- email_search_structured
- email_find_similar
- email_attachments
- email_case_comparator_matrix
- email_case_issue_matrix
```

## Wave 5 Prompt

```text
Execute Wave 5: Eingruppierung / Tätigkeitsdarstellung / Task Withdrawal for Q7, Q15, Q33, and Q36.

Use the Wave 5 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- task withdrawal
- actual duties
- role acknowledgment versus later denial
- exclusion from role-clarification process

MCP emphasis:
- email_search_structured
- email_attachments
- email_thread_lookup
- email_action_items
- email_decisions
- email_case_evidence_index
- email_case_master_chronology
```

## Wave 5A Prompt

```text
Execute Wave 5A: EG 12 Proof-Building for Q17, Q18, Q19, and Q20.

Use the Wave 5A query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- management transmission
- continuity
- under-recording
- institutional reliance

MCP emphasis:
- email_search_structured
- email_find_similar
- email_attachments
- email_deep_context
- email_case_evidence_index
- email_case_issue_matrix

Keep at most partially answered if the corpus lacks tariff-relevant continuity proof.
```

## Wave 5B Prompt

```text
Execute Wave 5B: Project-Brief And Role-Ownership Evidence for Q33.

Use the Wave 5B query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- project brief inventory
- role-ownership citations
- downstream linkage into Wave 5 and Wave 5A

MCP emphasis:
- email_attachments
- email_search_structured
- email_case_evidence_index
```

## Wave 6 Prompt

```text
Execute Wave 6: BEM / Section 167 SGB IX / Prevention Failures for Q5, Q6, Q27, Q28, and Q29.

Use the Wave 6 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- BEM continuity
- recommendation handling
- prevention-process framing
- return-from-AU protection

MCP emphasis:
- email_search_structured
- email_attachments
- email_thread_lookup
- email_case_master_chronology
- email_case_issue_matrix
- email_case_document_request_checklist
```

## Wave 7 Prompt

```text
Execute Wave 7: SBV / PR Participation Path for Q3, Q4, Q25, and Q38.

Use the Wave 7 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- SBV trail
- PR trail
- participation visibility
- participation-approved work versus management stop

MCP emphasis:
- email_search_structured
- email_thread_lookup
- email_find_similar
- email_case_actor_witness_map
- email_case_issue_matrix
```

## Wave 8 Prompt

```text
Execute Wave 8: time system / Attendance Control / Surveillance for Q9 and Q31.

Use the Wave 8 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- correction trail
- summary-versus-raw-proof gap
- attendance-control evidence discipline

MCP emphasis:
- email_search_structured
- email_attachments
- email_thread_lookup
- email_case_master_chronology
- email_case_evidence_index
```

## Wave 9 Prompt

```text
Execute Wave 9: Coordination And Actor Cluster Analysis for Q2, Q16, Q23, Q35, and Q39.

Use the Wave 9 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- coordination patterns
- gatekeeper routing
- comparator baseline discovery
- PA bottleneck pattern
- calendar and cancellation pattern

MCP emphasis:
- email_search_structured
- email_triage
- email_contacts
- relationship_summary
- relationship_paths
- shared_recipients
- coordinated_timing
- email_case_actor_witness_map
```

## Wave 10 Prompt

```text
Execute Wave 10: Open Questions Register.

Use the Wave 10 query pack and evidence quotas from docs/agent/question_execution_query_packs.md.

Focus:
- refresh any remaining yellow or blocked questions
- confirm that every unresolved item is either a true missing record or a bounded unresolved point
- synchronize final question states across:
  - <question_register_path>
  - <open_tasks_path>
  - <checkpoint_path>

Do not leave silent gaps after the owning wave has already run.
```
