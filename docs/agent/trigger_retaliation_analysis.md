# BA8 Trigger And Retaliation Analysis

Version: `1`

This BA8 layer adds explicit trigger events and conservative before/after deltas. It does not yet prove retaliation. It only surfaces conditional shifts around operator-supplied trigger points.

## Supported trigger events

- `complaint`
- `illness_disability_disclosure`
- `escalation_to_hr`
- `objection_refusal`
- `boundary_assertion`
- `other`

## Before/after metrics

- `response_time`
  - based on BA11 reply-pairing when request-expected target-authored messages exist
- `escalation_rate`
  - count of BA6 `escalation` candidates
- `inclusion_changes`
  - count of BA6 `exclusion` and `withholding` candidates
- `criticism_frequency`
  - count of BA6 `public_correction` and `undermining` candidates
- `demand_intensity`
  - count of BA6 `deadline_pressure`, `selective_accountability`, and `escalation` candidates

## Trigger windows

Each trigger event now keeps a bounded window breakdown:

- `immediate_after`
  - 0 to 14 days after the trigger
- `medium_term`
  - 15 to 45 days after the trigger
- `long_tail`
  - more than 45 days after the trigger

These windows are descriptive. BA8 still does not infer retaliation from timing alone.

## Assessment states

### `adverse_shift_after_trigger`

- before/after context exists
- adverse message-level behaviour totals increased after the trigger event
- still conditional because comparator support is not present yet

### `mixed_shift`

- before/after context exists
- some adverse metrics increased, but others moved in a different direction
- confounders or mixed metric movement keep the assessment below a cleaner adverse-shift read

### `no_clear_shift`

- before/after context exists
- adverse totals stayed stable or decreased

### `insufficient_context`

- either the before or after side is missing
- timing evidence is too thin to assess change

## Evidence chain

Each trigger event emits:

- `before_uids`
- `after_uids`

These UID lists are the traceability anchor for later report phases.

## Structured retaliation timeline assessment

`retaliation_analysis` now also emits `retaliation_timeline_assessment` for counsel-facing timeline review.

It contains:

- `protected_activity_timeline`
- `adverse_action_timeline`
- `temporal_correlation_analysis`
- `strongest_retaliation_indicators`
- `strongest_non_retaliatory_explanations`
- `overall_evidentiary_rating`

Rules:

- this is still a timing-and-sequence review layer, not a final retaliation holding
- timing-based indicators must stay paired with confounders, uncertainty reasons, or both when those exist
- `overall_evidentiary_rating` stays conservative and evidence-bound

## Boundaries

- BA8 requires explicit trigger events from the operator.
- BA8 does not yet compare against peer comparators.
- BA8 does not yet infer retaliation from timing alone.
- BA8 now surfaces simple confounder signals such as new senders, topic shifts, thread/workflow changes, and narrow post-trigger bursts.
- Later BA phases still need comparator logic, stronger evidence scoring, and report wording policy.
