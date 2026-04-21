# Actor And Witness Map

## Goal

Render one shared actor-facing registry for counsel workflows from the existing identity graph, chronology, mixed-source bundle, communication graph, and matter workspace.

## Top-level contract

The shared builder emits:

- `version`
- `actor_map`
- `witness_map`
- `witness_question_packs` may be derived downstream from this shared registry plus chronology, exhibits, and missing-proof workflow data

## Actor map contract

`actor_map` contains:

- `actor_count`
- `actors`
- `summary`
  - `decision_maker_count`
  - `witness_count`
  - `gatekeeper_count`
  - `supporter_count`
  - `coordination_point_count`

Each `actors[*]` row contains:

- `actor_id`
- `name`
- `email`
- `role_hint`
- `roles_in_matter`
- `relationship_to_events`
- `status`
  - `decision_maker`
  - `witness`
  - `gatekeeper`
  - `supporter`
- `tied_event_ids`
- `tied_message_or_document_ids`
- `coordination_points`
- `helps_hurts_mixed`
- `source_record_count`

Rules:

- this registry is an evidence-organization surface, not a liability conclusion
- `helps_hurts_mixed` reflects current case positioning or likely adverse/helpful impact, not witness credibility or truthfulness
- actor rows must stay linked back to chronology ids, message/document ids, or communication-graph coordination points when available

## Witness map contract

`witness_map` contains:

- `primary_decision_makers`
- `potentially_independent_witnesses`
- `high_value_record_holders`
- `coordination_points`

Rules:

- `primary_decision_makers` should identify actors whose role context or decision-flow patterns make them likely decision owners or approvers
- `potentially_independent_witnesses` should keep witness candidacy separate from decision-maker status when the current record allows that distinction
- `high_value_record_holders` should identify actors tied to note, calendar, time, participation, email, or other mixed-source records that are likely important for corroboration
- `coordination_points` should expose graph-backed side-channel, exclusion, escalation, or visibility-asymmetry patterns without overstating motive

## Downstream interview prep

`witness_question_packs` is a downstream product built from this shared registry together with chronology, evidence, and checklist data.

It should translate witness mapping into:

- likely knowledge areas
- tied events to ask about
- documents to show or confirm
- factual gaps to probe
- caution notes on independence, discretion, or record ownership
- practical non-leading interview questions
