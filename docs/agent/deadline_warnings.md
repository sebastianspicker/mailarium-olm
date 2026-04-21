# Deadline Warnings

## Goal

Surface operational timing risks without pretending to determine final legal deadlines, limitation periods, or hold scope.

## Shared payload

`deadline_warnings` is a shared legal-support payload reused by the issue matrix, document-request checklist, dashboard, case-analysis wrapper, and investigation report.

Fields:

- `version`
- `as_of_date`
- `overall_status`
  - `no_material_timing_warning`
  - `timing_review_recommended`
- `summary`
  - `warning_count`
  - `high_severity_count`
  - `categories`
- `warnings`

Each `warnings[*]` object contains:

- `warning_id`
- `category`
  - `possible_deadline_relevance`
  - `limitation_sensitivity`
  - `document_preservation_urgency`
  - `escalating_evidence_loss_risk`
- `severity`
- `summary`
- `caution`
- `not_final_legal_advice`
- `linked_issue_ids`
- `linked_group_ids`
- `linked_date_gap_ids`

## Rules

- warnings must stay evidence-bound and operational rather than statute-conclusive
- age-of-record signals may justify review urgency, but must not claim that a matter is timely or untimely
- preservation warnings may justify prompt collection or hold review, but must not claim that a legal hold already exists or is legally sufficient
- downstream products should reference the shared warning ids instead of inventing separate timing narratives
