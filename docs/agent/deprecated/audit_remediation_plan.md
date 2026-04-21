# Audit Remediation Plan

Status: `implemented and closed on 2026-04-16 after the six-milestone remediation round`

Completion note:

- Milestones `1` to `6` are fully implemented
- all covered findings `C1-R5` through `C12-R5` are closed as repo-side issues
- the remaining ceiling is external missing matter records, not repo workflow or contract drift

Purpose:

- translate the current live audit state in [AUDIT_COMPANION.md](AUDIT_COMPANION.md) into an execution-ready remediation program
- give one autonomous agent a strict order of operations for the open repo-side blockers and quality gaps
- define contracts, tests, quality gates, and definition-of-done criteria before another implementation round starts

Source of truth:

- [AUDIT.md](AUDIT.md)
- [AUDIT_COMPANION.md](AUDIT_COMPANION.md)

Covered findings in this plan:

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

Planning assumptions:

1. this program is for repo-side remediation only
2. external missing matter records remain outside scope
3. German-first execution remains the default for this matter family
4. the human review gate for counsel-facing export remains in place unless explicitly changed later

Recommended implementation stance:

- do not try to keep two competing campaign owners alive
- the simpler durable fix is one shared campaign orchestration core exposed through both MCP and CLI, with docs, tests, and scripts all pointing at the same behavior

## Agent Contract

The implementing agent must execute milestones in the order below.

Rules:

1. do not start a later milestone while an earlier milestone still fails its definition of done
2. write the regression or contract test first for every confirmed bug or drift that is testable
3. keep changes surgical and milestone-local
4. sync code, docs, and verification in the same milestone; do not leave contract drift for a later pass
5. if a new blocker is discovered:
   - fix it immediately if it blocks the active milestone
   - otherwise record it in [AUDIT_COMPANION.md](AUDIT_COMPANION.md) before moving on
6. do not declare completion from local inspection alone; every milestone needs executable proof
7. do not silently weaken the German-first posture, the human review gate, or the matter-evidence discipline while fixing workflow issues

## Global Definition Of Done

This remediation program is done only when all of the following are true:

1. the repo has one coherent authority model for campaign execution and closure
2. MCP and CLI run through the same wave-execution logic or an explicitly shared orchestration layer
3. the local results control plane can distinguish raw reruns from curated ledgers without ambiguity
4. archive-harvest breadth scales more honestly for a dense multi-year corpus
5. wave-local views are derived from evidence-linked metadata rather than term matching alone
6. initial ingest analytics handle short and best-available-body cases better than the current default
7. scripts and tests exercise campaign-faithful behavior instead of wrapper shape only
8. autonomous internal completion is clearly separated from human-gated counsel export

## Global Quality Gates

Every milestone must pass:

- `git diff --check`
- `ruff check` on touched files
- targeted `pytest` for the touched behavior

When a milestone edits shell scripts, also pass:

- `shellcheck` on touched scripts

When a milestone edits typed Python surfaces, also pass:

- targeted `python -m mypy src` for the touched import graph or the full `src` tree when the seam is broad

Before final closure, the repo must pass:

- `ruff check .`
- `python -m mypy src`
- `pytest -q --tb=short --cov=src --cov-report=term-missing --cov-fail-under=80`
- `bash scripts/run_acceptance_matrix.sh local`
- `python -m src.cli --help`
- `python -m src.mcp_server --help`

## Milestone Order

### Milestone 1: Unify Campaign Authority And Execution Contract

Findings:

- `C1-R5`
- `C2-R5`
- `C9-R5`

Why first:

- the repo currently documents one workflow as canonical while executing another
- later improvements are weaker if the campaign owner is still ambiguous

Primary surfaces:

- `src/cli_commands_case.py`
- `src/cli_parser.py`
- `src/tools/case_analysis.py`
- `src/tools/legal_support.py`
- `src/mcp_server.py`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_execution_companion.md`
- `docs/CLI_REFERENCE.md`
- `docs/MCP_TOOLS.md`

Implementation tasks:

1. define one shared campaign-orchestration owner for wave execution
2. expose that owner through both MCP and CLI or explicitly make one a thin wrapper over the other
3. remove contradictory `MCP-only` versus `supported local workflow` wording from the runbooks
4. keep analytical-product authority explicit without invalidating the practical wave runner
5. document the exact completion boundary for campaign closure, raw reruns, and debug traces

Required tests:

- one MCP registration or parity test for the new orchestration surface
- one CLI or MCP contract test proving both surfaces report the same execution-authority model
- one repo-contract test proving runbook, companion, and CLI reference no longer contradict each other

Definition of done:

1. the repo has one coherent authority model
2. the supported wave owner is the same workflow the runbooks describe
3. no top-level doc still declares the practical execution surface invalid for campaign closure evidence

### Milestone 2: Repair Results-Control Freshness And Ledger State

Findings:

- `C12-R5`
- `C11-R5`

Why here:

- the current workspace can point to a new raw rerun while curated ledgers remain stale
- this ambiguity affects every later execution and audit pass

Primary surfaces:

- `src/investigation_results_workspace.py`
- `src/cli_commands_case.py`
- `private/tests/results/README.local.md`
- `docs/agent/question_execution_companion.md`
- `tests/test_investigation_results_workspace.py`
- `tests/case_workflows/test_cli_subcommands_case.py`

Implementation tasks:

1. encode raw-versus-curated status explicitly in `active_run.json`
2. require one of:
   - ledger refresh
   - machine-visible stale marker
   - explicit invalidation marker
   after every meaningful rerun
3. prevent `active_run.json` from silently advertising a newer run while the curated ledgers still describe an older one
4. make `refresh-active-run` and related helpers own that state transition instead of leaving it as prose discipline

Required tests:

- one results-workspace regression proving stale curated ledgers are marked or rejected
- one rerun regression proving the active manifest records raw-versus-curated state correctly
- one repo-contract test proving the local-results docs match the machine-readable manifest behavior

Definition of done:

1. the results-control plane can no longer drift silently
2. a later agent can tell whether the current state is raw, curated, or stale from machine-readable fields
3. `active_run.json`, checkpoint metadata, and ledger state are coherent after a rerun

### Milestone 3: Scale Archive Harvest For Dense Corpora

Findings:

- `C5-R5`

Why here:

- evidence quality still caps out too early for a corpus of roughly `20k` emails across multiple years

Primary surfaces:

- `src/case_analysis.py`
- `src/case_analysis_harvest.py`
- `src/tools/search_answer_context_runtime.py`
- `src/mcp_models_case_analysis_core.py`
- `tests/test_case_analysis.py`
- `tests/_mcp_tools_search_answer_context_core_cases.py`

Implementation tasks:

1. replace or relax the fixed `10` / `25` / `40` synthesis and harvest caps with adaptive logic
2. let harvest breadth respond to corpus size, date span, wave sparsity, and coverage-gate failure
3. keep retrieval diagnostics explicit so increased breadth remains auditable
4. preserve sensible hard limits so the runtime stays stable under local hardware constraints

Required tests:

- one harvest regression proving a dense fake corpus yields a larger evidence bank than the current fixed path
- one case-analysis regression proving the adaptive effective breadth is surfaced in the payload
- one retrieval regression proving lane coverage remains visible after the wider merge

Definition of done:

1. archive harvest is no longer anchored to conservative small fixed caps
2. coverage-gate failures can trigger wider harvest instead of immediate synthesis
3. the effective harvest breadth is machine-visible in payloads and summaries

### Milestone 4: Replace Heuristic Wave-Local Views With Evidence-Linked Views

Findings:

- `C6-R5`

Why here:

- the repo now executes waves, but per-wave analytical views are still derived from term matching over full-matter payloads

Primary surfaces:

- `src/wave_local_views.py`
- `src/case_analysis_transform.py`
- `src/master_chronology.py`
- `src/matter_evidence_index.py`
- `src/lawyer_issue_matrix.py`
- `tests/test_case_analysis.py`

Implementation tasks:

1. carry question or wave provenance into the transformed analytical rows
2. derive wave-local chronology, findings, issue rows, checklist groups, and contradiction rows from those links
3. keep full-matter surfaces intact while making wave-local views trustworthy
4. minimize false positives from generic terms and English fallback terms

Required tests:

- one regression proving unrelated rows do not leak into a wave-local view merely because of shared vocabulary
- one regression proving linked rows survive even when their text does not repeat the wave label or issue term
- one case-analysis regression proving different waves yield meaningfully different linked views from one shared full payload

Definition of done:

1. wave-local views are evidence-linked rather than text-matched heuristics
2. per-wave outputs become trustworthy analytical slices, not just convenience filters

### Milestone 5: Harden Ingest And Language Analytics

Findings:

- `C3-R5`
- `C7-R5`

Why here:

- the current German-first workflow still relies on post-hoc analytics repair and lightweight detection for important short-text cases

Primary surfaces:

- `src/ingest_embed_pipeline.py`
- `src/ingest_reingest.py`
- `src/language_detector_core.py`
- `src/language_detector.py`
- `src/tools/data_quality.py`
- `tests/test_language_detector.py`
- `tests/test_ingest_pipeline.py`
- `tests/test_ingest_reingest.py`

Implementation tasks:

1. compute analytics from the best available body surface during default ingest
2. stop dropping short messages entirely; route them into a low-confidence analytics lane
3. persist enough metadata to distinguish confident labels from fallback or short-text labels
4. keep `email_quality(check='languages')` honest about labeled versus unlabeled coverage and confidence caveats

Required tests:

- one ingest regression proving short messages receive low-confidence analytics instead of silent omission
- one regression proving best-available-body selection prefers richer recovered text when present
- one language-quality regression proving the coverage output remains accurate after the ingest changes

Definition of done:

1. default ingest no longer leaves the main short-text blind spot untouched
2. language analytics are better aligned with the actual German-heavy corpus shape
3. operators can see confidence and coverage limits directly from the quality surface

### Milestone 6: Make Verification Campaign-Faithful And Clarify Governance Boundaries

Findings:

- `C4-R5`
- `C8-R5`
- `C10-R5`
- `C11-R5`

Why last:

- this milestone locks the repaired workflow in place and makes the autonomy boundary honest

Primary surfaces:

- `scripts/run_acceptance_matrix.sh`
- `scripts/wave_workflow_smoke.py`
- `scripts/run_qa_eval.py`
- `src/qa_eval_live.py`
- `tests/case_workflows/test_cli_subcommands_case.py`
- `tests/test_repo_contracts.py`
- `tests/test_investigation_results_workspace.py`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/review_governance.md`

Implementation tasks:

1. add one bounded campaign-faithful verification slice that uses the actual orchestration owner and results-control rules
2. reduce reliance on monkeypatched wrapper-only smoke coverage
3. make QA-eval or a dedicated smoke run validate campaign-fidelity properties, not just output shape
4. make the human review gate explicit as:
   - autonomous internal completion
   - human-gated counsel export
5. ensure docs, tests, and scripts all use the same terminology for those boundaries

Required tests:

- one smoke or integration test that exercises the real orchestration owner end to end
- one repo-contract test proving the autonomy boundary and human review gate are documented consistently
- one verification regression proving raw reruns and curated ledger state are treated correctly in the final gates

Definition of done:

1. verification now measures the real campaign workflow, not only wrapper shape
2. the autonomy boundary is honest and machine-visible
3. the repo can distinguish “analysis complete” from “counsel export ready” without ambiguity

## Final Closure Checklist

Before marking this plan complete, the implementing agent must confirm all of the following:

1. every covered finding above is either:
   - fixed in code and docs with tests, or
   - reclassified in [AUDIT_COMPANION.md](AUDIT_COMPANION.md) with local proof that it is not a repo defect
2. [AUDIT_COMPANION.md](AUDIT_COMPANION.md) reflects the post-remediation state instead of only the pre-fix findings
3. [AUDIT.md](AUDIT.md) still matches the actual repo taxonomy after the implementation round
4. the final verification matrix results are recorded in the appropriate durable doc

## Milestone Reporting Format

After each milestone, record:

1. the finding IDs closed or reclassified
2. the files changed
3. the tests and gates run
4. the remaining blockers, if any
5. the milestone verdict:
   - `PASS`
   - `PARTIAL`
   - `FAIL`
