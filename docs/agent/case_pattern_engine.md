# BA7 Case Pattern Engine

Version: `1`

This BA7 layer aggregates BA6 message findings into conservative case-level pattern summaries. It is intentionally narrower than retaliation, comparator, or legal interpretation analysis.

## Aggregation axes

- time
- actor pairs
- behaviour candidates
- linked taxonomy ids
- thread groups

## Recurrence labels

### `isolated`

- one message with one cluster only

### `repeated`

- two or more messages in the same cluster without stronger escalation or system indicators

### `escalating`

- at least three messages
- later messages do not weaken in confidence
- cluster contains pressure-like behaviour such as:
  - `escalation`
  - `deadline_pressure`
  - `public_correction`

### `systematic`

- at least four messages
- at least two actors
- at least two threads

## Additional recurrence flags

### `targeted`

- same sender actor repeatedly appears against the case target actor

### `possibly_coordinated`

- multiple actors and multiple threads are present in the same cluster

## Output sections

- `behavior_patterns`
  - recurrence summaries by BA6 behaviour candidate
- `taxonomy_patterns`
  - recurrence summaries by linked BA4 taxonomy ids
- `thread_patterns`
  - recurrence summaries by thread group
- `directional_summaries`
  - sender-to-target message counts and behaviour counts
- `cluster_index`
  - traceable per-message rows linking UID, behaviour, sender actor, thread group, and date

## Boundaries

- BA7 is still conservative and aggregation-only.
- It does not yet infer retaliation, discrimination, comparator-based unequal treatment, or coordination as conclusions.
- `targeted` and `possibly_coordinated` are flags, not final claims.
- Later BA phases still need trigger-event logic, comparator logic, evidence-strength scoring, and interpretation policy.
