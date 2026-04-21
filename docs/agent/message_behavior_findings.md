# BA6 Message Behavior Findings

Version: `1`

This BA6 layer turns per-message rhetoric and bounded message context into behaviour candidates. It is still message-local. It does not yet infer recurrence, coordination, retaliation patterns, or case-level conclusions.

## Behaviour candidates

### `exclusion`

- Meaning:
  - the case target is referenced or contextually implicated while absent from visible recipients
- Typical evidence:
  - message metadata showing target absence
  - authored text naming the target
- Typical neutral alternative:
  - the target may not need to be included in that specific administrative message

### `escalation`

- Meaning:
  - the message uses formal-process or escalation framing as a behaviour-level move
- Typical evidence:
  - `for the record`
  - `HR`
  - `formal process`
  - `disciplinary`
- Typical neutral alternative:
  - routine escalation may be policy-required or time-critical

### `public_correction`

- Meaning:
  - corrective or accusatory wording is sent with unnecessary visible recipients
- Typical evidence:
  - multi-recipient visibility
  - accusation or competence-framing in authored text
- Typical neutral alternative:
  - wider circulation may be operationally required

### `withholding`

- Meaning:
  - decision or update wording appears while the case target is absent from visible recipients
- Typical evidence:
  - update/decision wording
  - target absence from visible recipients
- Typical neutral alternative:
  - the update may be preparatory and later communicated through another channel

### `selective_accountability`

- Meaning:
  - the message assigns sole or exceptional responsibility to one person
- Typical evidence:
  - `only you`
  - `you alone`
  - `your responsibility`
- Typical neutral alternative:
  - the person may genuinely own the task in that workflow

### `deadline_pressure`

- Meaning:
  - the message applies explicit time pressure or urgency
- Typical evidence:
  - `today`
  - `by end of day`
  - `immediately`
  - `without delay`
- Typical neutral alternative:
  - the deadline may be operationally justified

### `undermining`

- Meaning:
  - competence or credibility framing rises to a behaviour candidate rather than remaining tone-only
- Typical evidence:
  - ridicule
  - competence framing
  - patronizing wording
- Typical neutral alternative:
  - a one-off correction or performance concern may explain the phrasing

## Message-level fields

- `behavior_candidates`
  - behaviour candidates with rationale, evidence, linked taxonomy ids, and neutral alternatives
- `wording_only_signal_ids`
  - rhetorical cues that did not have enough support to become behaviour candidates
- `counter_indicators`
  - message-local facts against a stronger hostile reading

## Boundaries

- BA6 is still message-local only.
- Behaviour candidates are not recurrence claims.
- Omission-aware findings are low-confidence by default unless later phases add stronger cross-message support.
- Later BA phases still need recurrence, comparator logic, counter-indicator aggregation, and interpretation policy.
