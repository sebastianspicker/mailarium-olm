# Source Conflict Resolution

Version: `1`

Status: `approved_for_implementation`

This contract makes contradictory dates, summaries, and source-quality clashes explicit instead of leaving them implicit in chronology prose.

## Goal

`source_conflict_registry` exists so downstream evidence, issue-matrix, and drafting surfaces can distinguish:

- stable facts
- disputed facts
- provisional machine preferences
- conflicts that still require human review

## Priority rules

Current machine priority rules are conservative and review-facing:

- `explicit_document_date_over_source_timestamp`
- `primary_document_over_operator_note`
- `authored_text_over_metadata`
- `native_text_over_ocr_or_image`

These rules do not silently delete contrary records. They only provide a bounded machine preference while keeping the conflict visible.

## Current conflict kinds

- `inconsistent_dates`
  - used when extracted event timing materially differs from the source-recorded timestamp
- `inconsistent_summary`
  - used when linked sources describe the same topic with opposite polarity or incompatible summary wording

## Resolution statuses

- `provisional_preference`
  - the current record supports a bounded machine preference under the priority rules, but the conflict still stays visible
- `unresolved_human_review_needed`
  - the machine could not safely rank the competing records strongly enough and a human reviewer should decide

## Downstream propagation

Current shared outputs use the registry as follows:

- `master_chronology.entries[*]`
  - `source_conflict_ids`
  - `fact_stability`
- `matter_evidence_index.rows[*]`
  - `source_conflict_ids`
  - `source_conflict_status`
  - `linked_source_conflicts`
- `lawyer_issue_matrix.rows[*]`
  - `source_conflict_status`
  - `unresolved_source_conflicts`

This is enough for counsel-facing review and controlled drafting to avoid treating disputed records as fully stable facts.

## Current boundary

Version `1` remains intentionally bounded:

- it does not auto-resolve every factual clash
- it does not yet merge or rewrite contradictory records
- it does not yet create human approvals automatically
- it prefers visible conflict rows over aggressive machine reconciliation
