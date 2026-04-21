# Open Tasks Companion Template

Status: `operator-facing`

Use this template to initialize:

- `private/tests/results/11_memo_draft_dashboard/open_tasks_companion.md`

Canonical dependencies:

- `docs/agent/Plan.md`
- `docs/agent/question_execution_companion.md`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`

Important rule:

- this file is for true missing-record items and downstream refresh work
- it is not the place to park locally fixable repo, schema, truncation, or runtime defects that should be repaired inside the run

## Suggested markdown layout

```md
# Open Tasks Companion

## True Missing Records

| task_id | linked_question_ids | blocker_class | exact missing record | why it matters | current best sources | next acquisition path | resume_wave | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `OT-__` | `Q__` | `true external missing record` | | | | | | |

## Downstream Refresh After New Material

| task_id | linked_question_ids | trigger_for_refresh | required rerun scope | current supporting artifact | resume_wave | status |
| --- | --- | --- | --- | --- | --- | --- |
| `OT-__` | `Q__` | | | | | |

## Notes

- date:
- last completed checkpoint:
- next acquisition dependency:
```

## Minimum fields

For every open item, record:

- `task_id`
- `linked_question_ids`
- `blocker_class`
- `exact missing record` or `trigger_for_refresh`
- `why it matters`
- `next acquisition path`
- `resume_wave`
- `status`
