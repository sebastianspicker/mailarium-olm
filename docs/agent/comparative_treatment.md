# BA9 Comparative Treatment

Version: `1`

This BA9 layer compares the target against named comparator actors. It is conservative by design and refuses unequal-treatment claims when no suitable same-sender comparator context is available.

## Comparator requirements

- named `comparator_actors` in case intake
- same sender has messaged both:
  - the target
  - the comparator

If that condition is not met, the comparator state stays:

- `no_suitable_comparator`

## Compared metrics

- `tone_signal_count`
  - BA5 authored rhetoric signal count
- `escalation_count`
  - BA6 `escalation`
- `criticism_count`
  - BA6 `public_correction` and `undermining`
- `demand_intensity_count`
  - BA6 `deadline_pressure`, `selective_accountability`, and `escalation`
- `procedural_pressure_count`
  - BA6 `deadline_pressure`, `selective_accountability`, `withholding`, and `escalation`
- `average_visible_recipient_count`
  - visible-recipient breadth for the compared bucket
- `multi_recipient_rate`
  - how often the sender used broader visible audience handling against each side
- `average_response_delay_hours`
  - only when comparable reply-latency observations exist for both sides; otherwise BA9 keeps this as unavailable

## Similarity checks

- `shared_request_type`
- `shared_error_type`
- `shared_escalation_context`
- `shared_process_step`
- `shared_subject_family`
- `shared_tags`
- `shared_day_window`
- `shared_context_count`
- `similarity_score`

These checks are meant to bound comparator misuse. They do not prove comparability on their own.

## Comparator statuses

### `comparator_available`

- same sender addressed both the target and comparator
- some bounded shared context exists
- `comparison_quality` will still distinguish:
  - `high`
  - `partial`

### `weak_similarity`

- same sender addressed both sides
- but the shared context remains weak
- `comparison_quality` is `weak`

### `no_suitable_comparator`

- no same-sender comparison pair is available in the current evidence set

## Unequal-treatment signals

Examples:

- `tone_to_target_harsher_than_to_comparator`
- `same_sender_escalates_more_against_target`
- `same_sender_criticizes_target_more`
- `same_sender_demands_more_from_target`
- `same_sender_uses_more_procedural_pressure_against_target`
- `same_sender_uses_more_public_visibility_against_target`
- `same_sender_uses_broader_visibility_against_target`
- `same_sender_replies_slower_to_target_requests`

These are still comparative indicators, not final conclusions.

## Durable comparator matrix

Each comparator summary now also emits `comparator_matrix`.

`comparator_matrix` contains:

- `row_count`
- `table_columns`
- `rows`

Each row contains:

- `matrix_row_id`
- `issue_id`
- `issue_label`
- `claimant_treatment`
- `comparator_treatment`
- `evidence`
- `comparison_strength`
- `evidence_needed_to_strengthen_point`
- `likely_significance`
- `supported_signal_ids`

Current issue rows:

- `mobile_work_approvals_or_restrictions`
- `formality_of_application_requirements`
- `control_intensity`
- `project_allocation`
- `training_or_development_opportunities`
- `sbv_or_pr_participation`
- `reaction_to_technical_incidents`
- `flexibility_around_medical_needs`
- `treatment_after_complaints_or_rights_assertions`

`comparison_strength` is bounded to:

- `strong`
- `moderate`
- `weak`
- `not_comparable`

This is the durable lawyer-usable table layer for:

- `Comparator issue`
- `Claimant treatment`
- `Colleague treatment`
- `Evidence`
- `Likely significance`

## Boundaries

- BA9 does not yet compare full workflow equivalence beyond bounded similarity checks.
- BA9 does not prove discrimination by itself.
- Later BA phases still need communication-graph analysis, stronger evidence scoring, and interpretation policy.
