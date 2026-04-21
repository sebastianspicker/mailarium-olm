# Investigation Report Format

## Version

- `1`

## Goal

Render a structured investigation-style report from the existing case-scoped behavioural-analysis payload without inventing new evidence beyond BA1 to BA15.

## Top-level contract

`investigation_report` is emitted only for case-scoped `email_answer_context` responses.

Fields:

- `version`
- `report_format`
  - `investigation_briefing`
- `section_order`
- `summary`
  - `section_count`
  - `supported_section_count`
  - `insufficient_section_count`
- `sections`

## Section order

1. `executive_summary`
2. `chronological_pattern_analysis`
3. `language_analysis`
4. `behaviour_analysis`
5. `power_context_analysis`
6. `evidence_table`
7. `overall_assessment`
8. `missing_information`

## Section contract

Each section contains:

- `section_id`
- `title`
- `status`
  - `supported`
  - `insufficient_evidence`
- `entries`
- `insufficiency_reason`

Each `entries[*]` object contains:

- `entry_id`
- `statement`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`

Rule:

- every supported section must carry at least one entry
- every entry must either point to supporting evidence through `finding_id`, `citation_id`, or `uid`
- insufficient sections must state an explicit `insufficiency_reason`

## Budget behavior

Under tight JSON budgets the report is compacted, not dropped.

Compact mode keeps:

- `version`
- `report_format`
- `section_order`
- `summary`
- per-section:
  - `title`
  - `status`
  - `entry_count`
  - first representative entry
  - `insufficiency_reason`

## Interpretation boundary

BA16 is a renderer only.

It does not:

- change evidence strength
- change quote ambiguity policy
- add new behavioural findings
- introduce legal or motive conclusions

Those concerns remain with earlier evidence/scoring milestones and the later BA17 policy milestone.
