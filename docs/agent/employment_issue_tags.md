# Employment Issue Tags

Version: `1`

Status: `approved_for_implementation`

Employment issue tags are the first-class structured issue labels for matter review.

They exist to make issue organization machine-readable across:

- case intake
- exhibit rows
- report summaries

They do not:

- decide legal liability
- decide statutory satisfaction
- replace the neutral issue frameworks

## Canonical tags

- `eingruppierung`
- `agg_disability_disadvantage`
- `retaliation_massregelung`
- `mobile_work_home_office`
- `sbv_participation`
- `pr_participation`
- `prevention_bem_sgb_ix_167`
- `medical_recommendations_ignored`
- `task_withdrawal_td_fixation`
- `worktime_control_surveillance`
- `witness_relevance`
- `comparator_evidence`

## Assignment bases

Structured issue tags keep an explicit `assignment_basis`:

- `operator_supplied`
- `direct_document_content`
- `bounded_inference`

## Evidence status

Structured issue tags also keep an `evidence_status`:

- `operator_supplied`
- `directly_supported`
- `inferred`

## Shared rules

- a tag may appear more than once across different assignment bases when that distinction matters
- exhibit rows keep both:
  - `issue_tags`
  - `main_issue_tags`
- `issue_tags` is the structured source of truth
- `main_issue_tags` is the flat grouping helper for later filters and exports

## Current assignment logic

Version `1` supports three bounded assignment paths:

1. structured operator input from case scope
2. direct keyword support in the current source text
3. bounded inference from issue tracks, allegation focus, or comparator findings

The logic is intentionally conservative and may be expanded later.
