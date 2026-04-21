# Matter Evidence Index

Version: `1`

Status: `approved_for_implementation`

`matter_evidence_index` is the first durable exhibit register for case analysis.

It exists to give later outputs one reusable source of truth for:

- exhibit-style review
- chronology work
- dossier-building
- later export surfaces

It is not yet:

- a ranked top-exhibits list
- a missing-exhibits list
- a final export formatter

## Top-level shape

`matter_evidence_index` contains:

- `version`
- `row_count`
- `summary`
- `rows`
- `top_15_exhibits`
- `top_10_missing_exhibits`

## Row contract

Each row contains:

- `exhibit_id`
- `date`
- `document_type`
- `sender_or_author`
- `sender_identity`
- `recipients`
- `recipient_identities`
- `short_description`
- `main_issue_tags`
- `issue_tags`
- `key_quoted_passage`
- `source_language`
- `quoted_evidence`
- `why_it_matters`
- `exhibit_reliability`
- `reliability_or_evidentiary_strength`
- `follow_up_needed`
- `source_format_support`
- `extraction_quality`

To keep rows reproducible, the payload also keeps:

- `source_id`
- `source_type`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `supporting_uids`
- `provenance`
- `document_locator`

## Current rules

- one stable exhibit row is emitted per mixed-source bundle source
- `exhibit_id` is deterministic within one rendered index ordering
- `main_issue_tags` is the flat grouping helper derived from structured `issue_tags`
- `issue_tags` is the structured source of truth and keeps:
  - `tag_id`
  - `label`
  - `assignment_basis`
  - `evidence_status`
  - `assignment_reason`
- `exhibit_reliability` is now the structured source of truth for exhibit-level use decisions and keeps:
  - `strength`
  - `reason`
  - `source_basis`
  - `next_step_logic.readiness`
  - `next_step_logic.recommended_steps`
  - `next_step_logic.blocking_points`
- `reliability_or_evidentiary_strength` is conservative and derived from the current source reliability basis
- `follow_up_needed` stays as the compatibility helper and is derived from `exhibit_reliability.next_step_logic.recommended_steps`
- `source_format_support` mirrors the mixed-source `documentary_support.format_profile` payload so unsupported or lossy file classes remain visible on exhibit rows
- `extraction_quality` mirrors the mixed-source `documentary_support.extraction_quality` payload so OCR recovery, flattening, and reference-only states stay visible in downstream legal-support outputs
- `source_language` is a conservative detected-language hint for the visible source text
- `quoted_evidence.original_text` keeps the original-language passage separate from any output-language summary fields
- `sender_identity` keeps structured identity fields:
  - `name`
  - `email`
  - `display`
  - `role`
  - `identity_source`
- `recipient_identities` keeps per-channel structured identity groups for `to`, `cc`, and `bcc` where email metadata exists; chat-like sources may use `participants`
- non-email rows degrade explicitly to actor-id or UID fallback instead of pretending email-style recipient certainty
- `summary` now also keeps:
  - `exhibit_strength_counts`
  - `exhibit_readiness_counts`
  - `top_exhibit_count`
  - `missing_exhibit_count`

## Prioritization layer

`top_15_exhibits` is the first dossier-style priority view derived from the durable exhibit rows.

Each item contains:

- `rank`
- `exhibit_id`
- `source_id`
- `source_type`
- `priority_score`
- `strength`
- `readiness`
- `short_description`
- `why_prioritized`
- `main_issue_tags`
- `supporting_finding_ids`
- `supporting_citation_ids`
- `source_date`

Current ranking is conservative and bounded. It mixes:

- issue relevance
- exhibit reliability
- chronology usefulness
- citation and finding support
- direct corroboration or contradiction potential

`top_10_missing_exhibits` is the first concrete missing-document layer.

Each item contains:

- `rank`
- `issue_track`
- `issue_track_title`
- `requested_exhibit`
- `priority_score`
- `why_missing_matters`
- `chronology_signal`
- `linked_date_gap_ids`

## Current boundary

Version `1` now includes a first prioritization layer, but remains bounded:

- it gives later milestones a reusable exhibit register plus initial dossier priorities
- missing exhibits remain checklist-derived and document-oriented rather than speculative
- it does not yet produce final export formatting or pleading-ready selections
