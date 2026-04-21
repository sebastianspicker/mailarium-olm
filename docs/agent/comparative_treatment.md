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

## Similarity checks

- `shared_request_type`
- `shared_error_type`
- `shared_escalation_context`
- `shared_process_step`
- `shared_tags`
- `similarity_score`

These checks are meant to bound comparator misuse. They do not prove comparability on their own.

## Comparator statuses

### `comparator_available`

- same sender addressed both the target and comparator
- some shared context exists

### `weak_similarity`

- same sender addressed both sides
- but the shared context remains weak

### `no_suitable_comparator`

- no same-sender comparison pair is available in the current evidence set

## Unequal-treatment signals

Examples:

- `tone_to_target_harsher_than_to_comparator`
- `same_sender_escalates_more_against_target`
- `same_sender_criticizes_target_more`
- `same_sender_demands_more_from_target`

These are still comparative indicators, not final conclusions.

## Boundaries

- BA9 does not yet compare full workflow equivalence beyond bounded similarity checks.
- BA9 does not prove discrimination by itself.
- Later BA phases still need communication-graph analysis, stronger evidence scoring, and interpretation policy.
