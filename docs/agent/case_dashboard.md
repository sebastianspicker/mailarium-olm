# Case Dashboard

## Goal

Render a compact, refreshable dashboard from stable matter entities and shared registries instead of hand-written summaries.

## Top-level contract

The shared builder emits:

- `version`
- `dashboard_format`
  - `refreshable_case_dashboard`
- `matter_ref`
- `summary`
- `cards`

## Summary fields

- `card_count`
- `issue_count`
- `actor_count`
- `exhibit_count`
- `refreshable_from_shared_entities`

## Card sections

`cards` contains:

- `main_claims_or_issues`
- `key_dates`
- `strongest_exhibits`
- `open_evidence_gaps`
- `main_actors`
- `comparator_points`
- `process_irregularities`
- `drafting_priorities`
- `risks_or_weak_spots`
- `recommended_next_actions`

Rules:

- the dashboard must be derived from the shared matter workspace, evidence index, chronology, issue matrix, actor map, and adjacent stable products
- the dashboard should stay card-like and compact rather than turning into another memo or report
- cards must remain refreshable when shared entities change, without needing hand-edited restructuring
- weak spots and next actions should remain visible alongside strongest exhibits and issues
