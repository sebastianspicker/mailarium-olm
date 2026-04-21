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
  - currently `not_available`
  - explicit request-response pairing is not modeled yet
- `escalation_rate`
  - count of BA6 `escalation` candidates
- `inclusion_changes`
  - count of BA6 `exclusion` and `withholding` candidates
- `criticism_frequency`
  - count of BA6 `public_correction` and `undermining` candidates
- `demand_intensity`
  - count of BA6 `deadline_pressure`, `selective_accountability`, and `escalation` candidates

## Assessment states

### `possible_retaliatory_shift`

- before/after context exists
- adverse message-level behaviour totals increased after the trigger event
- still conditional because comparator support is not present yet

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

## Boundaries

- BA8 requires explicit trigger events from the operator.
- BA8 does not yet compare against peer comparators.
- BA8 does not yet infer retaliation from timing alone.
- Later BA phases still need comparator logic, stronger evidence scoring, and report wording policy.
