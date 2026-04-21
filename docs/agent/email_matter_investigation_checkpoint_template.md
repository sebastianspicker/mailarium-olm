# Email Matter Investigation Checkpoint Template

Version: `1`

Use this template at the end of every investigation phase.

Canonical runbook:

- `docs/agent/email_matter_analysis_single_source_of_truth.md`

Store completed checkpoints locally under:

- `private/tests/results/_checkpoints/`

Recommended filename:

- `investigation_<YYYY-MM-DD>_P<NN>_<slug>.md`

## Template

```md
# Investigation Checkpoint

## Identity

- checkpoint_id:
- date:
- run_id:
- phase_id:
- phase_title:
- operator:
- scan_id_prefix:

## Matter Scope

- matter prompt path:
- materials directory:
- runtime chromadb path:
- runtime sqlite path:
- corpus language baseline:
- language analytics status:
- source scope:
- review mode:
- default output language:
- translation mode:

## Inputs Used

- structured case scope file:
- evidence harvest file:
- override file:
- manifest source:
- newly added materials in this pass:

## Human Corrections Applied

- verified trigger events:
- alleged adverse actions:
- comparators:
- role hints:
- institutional actors or mailboxes:

## MCP / CLI Operations

- tool or command:
- tool or command:
- tool or command:

## Output Files

- result path:
- result path:
- result path:

## Question Register Delta

- local register path:

| question_id | wave | status | query_language_lanes | language_detection_notes | best_supporting_sources | best_counter_sources | current_answer | remaining_uncertainty | missing_record_needed | blocker_class | remediation_taken | rerun_count | last_phase_touched | next_mcp_step |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Q__` | `Wave __` | | | | | | | | | | | | | |
| `Q__` | `Wave __` | | | | | | | | | | | | | |

## Open-Tasks Delta

- local open-tasks path:

| task_id | linked_question_ids | blocker_class | exact missing record or follow-up | why it matters | current best sources | next acquisition path | resume_wave | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `OT-__` | `Q__` | | | | | | | |
| `OT-__` | `Q__` | | | | | | | |

## Gate Result

- gate status: `green | yellow | red`
- gate rationale:

## Proven

- source-backed fact:
- source-backed fact:

## Reasonable Inference

- bounded inference:
- bounded inference:

## Not Yet Proven

- unresolved point:
- unresolved point:

## Main Findings

- finding:
- finding:

## Contradictions / Alternative Explanations

- contradiction or competing explanation:
- contradiction or competing explanation:

## Missing Evidence

- missing item:
- missing item:

## Date Gaps

- gap:
- gap:

## Risks

- risk:
- risk:

## Next Exact Step

- next phase:
- next tool or command:
- expected gate for next phase:

## Resume Rule

- if interrupted, resume from:
- rerun required if new dated record appears:
- rerun required if new comparator record appears:
- rerun required if MCP crashed during this phase:
- rerun required if output artifact is truncated:
```

## Minimum completion rule

Do not mark a checkpoint `green` unless:

- the output files were actually written
- the exact runtime paths are recorded
- the exact mandatory matter inputs are recorded, including `case.json`, `evidence-harvest.json` when applicable, `run_id`, `phase_id`, and `scan_id_prefix`
- any known human corrections carried into the phase are recorded explicitly
- the language baseline, analytics status, and working output language are recorded
- the question-register delta records blocker class, remediation taken, rerun count, and next MCP step for every touched `Q`
- any true missing-record remainder is mirrored into the open-tasks delta
- the phase-specific gate from the runbook is satisfied
- unresolved items are explicit

## Shortcut variant

Use this only for very small refresh passes:

```md
# Investigation Checkpoint

- checkpoint_id:
- date:
- phase_id:
- outputs:
- gate status:
- main delta:
- unresolved blocker:
- next step:
- resume from:
```
