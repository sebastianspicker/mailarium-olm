# Master Chronology

Version: `1`

Status: `approved_for_implementation`

`master_chronology` is the shared chronology registry for case analysis.

It exists to give later outputs one reusable source of truth for:

- chronology review
- trigger-before/after analysis
- exhibit-to-sequence linkage
- later chronology exports

## Top-level shape

`master_chronology` contains:

- `version`
- `entry_count`
- `summary`
- `entries`
- `views`

## Entry contract

Each entry contains:

- `chronology_id`
- `date`
- `date_precision`
- `date_origin`
- optional `coverage_window`
- optional `source_recorded_date`
- `entry_type`
- `title`
- `description`
- `event_support_matrix`
- `source_linkage`
- `source_conflict_ids`
- `fact_stability`

`event_support_matrix` contains one object for:

- `disability_disadvantage`
- `retaliation_after_protected_event`
- `eingruppierung_dispute`
- `prevention_duty_gap`
- `participation_duty_gap`
- `ordinary_managerial_explanation`

Each matrix item contains:

- `read_id`
- `status`
- `reason`
- `linked_issue_tags`
- `selected_in_case_scope`

`source_linkage` contains:

- `source_ids`
- `source_types`
- `supporting_uids`
- `supporting_citation_ids`
- `evidence_handles`
- `document_locators`

## Current rules

- one `source_event` is emitted for each mixed-source chronology anchor that resolves to a source object
- supplied case-scope trigger events are emitted as `trigger_event`
- timeline events without a matching source object may surface as `timeline_event` fallback entries
- `event_support_matrix` is neutral and event-local; it does not decide the whole case
- issue-track statuses are currently:
  - `direct_event_support`
  - `contextual_support_only`
  - `not_supported_by_current_event`
- the competing ordinary explanation currently uses:
  - `plausible_alternative`
  - `not_obvious_from_current_event`
- `date_precision` is conservative and currently uses:
  - `year`
  - `month`
  - `day`
  - `minute`
  - `second`
  - `unknown`
- `summary` keeps:
  - `entry_type_counts`
  - `date_precision_counts`
  - `event_read_status_counts`
  - `source_type_counts`
  - `source_linked_entry_count`
  - `date_range`
- `date_gap_count`
- `largest_gap_days`
- `date_gaps_and_unexplained_sequences`
- `sequence_breaks_and_contradictions`
- `source_conflict_registry`

## Date-gap layer

`summary.date_gaps_and_unexplained_sequences` is the first chronology-priority surface.

Each item contains:

- `gap_id`
- `from_chronology_id`
- `to_chronology_id`
- `start_date`
- `end_date`
- `gap_days`
- `priority`
- `linked_issue_tracks`
- `involved_source_types`
- `why_it_matters`
- `missing_bridge_record_suggestions`

`summary.sequence_breaks_and_contradictions` is the current review surface for chronology conflicts where extracted event timing materially differs from recorded source timing.

Each item contains:

- `conflict_id`
- `chronology_id`
- `source_recorded_date`
- `event_date`
- `delta_days`
- `source_types`
- `why_it_matters`

`summary.source_conflict_registry` is the shared source-conflict surface for contradictory dates, summaries, and priority-rule handling.

It contains:

- `version`
- `source_conflict_status`
- `priority_rules`
- `conflict_count`
- `unresolved_conflict_count`
- `affected_source_count`
- `affected_chronology_count`
- `conflicts`

Each conflict contains:

- `conflict_id`
- `conflict_kind`
- `resolution_status`
- `summary`
- `source_ids`
- `source_types`
- `chronology_ids`
- `priority_rule_applied`
- optional `preferred_source_id`
- `preferred_reason`
- `conflicting_claims`

Current conflict kinds:

- `inconsistent_dates`
- `inconsistent_summary`

## Multi-view chronology layer

`views` renders four chronology perspectives from the same event registry:

- `short_neutral_chronology`
- `claimant_favorable_chronology`
- `defense_favorable_chronology`
- `balanced_timeline_assessment`

Current rules:

- the four views do not create new events; they only restate the existing chronology entries
- `short_neutral_chronology` keeps dated neutral statements
- `claimant_favorable_chronology` highlights the strongest issue-supportive reading per event while keeping an explicit uncertainty note and counterargument note
- `defense_favorable_chronology` highlights the ordinary-managerial reading while keeping the strongest issue-supportive counterpoint visible
- `balanced_timeline_assessment` keeps:
  - per-event balanced statements
  - `summary.strongest_timeline_inferences`
  - `summary.strongest_limits`

## Current boundary

Version `1` remains bounded even with date-gap ranking:

- it is a reusable chronology registry, not the final narrative chronology
- gap detection is conservative and currently flags larger unexplained spans between dated events
- coverage-aware gap detection now uses time-record ranges where available instead of only one timestamp per source
- chronology conflict detection is bounded and currently highlights large extracted-date versus recorded-date differences for review
- multi-view rendering stays tied to the same event registry and does not become a separate fact source
- it does not infer causation or legal conclusions from those gaps
- it does not replace the legacy timeline summary used by current report prose
