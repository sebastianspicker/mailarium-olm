# Promise And Contradiction Analysis

## Goal

Compare what meeting notes, note records, summaries, and follow-up records say should happen against what later records show, omit, or contradict.

## Top-level contract

The shared builder emits:

- `version`
- `summary`
  - `promise_action_row_count`
  - `omission_row_count`
  - `contradiction_row_count`
- `promises_vs_actions`
- `omission_rows`
- `contradiction_table`

## Promise-versus-action rows

Each `promises_vs_actions[*]` row contains:

- `row_id`
- `original_statement_or_promise`
- `later_action`
- `original_source_id`
- `later_source_id`
- `likely_significance`
- `confidence_level`
- `action_alignment`
- `supporting_uids`

## Omission rows

Each `omission_rows[*]` row contains:

- `row_id`
- `original_statement_or_promise`
- `later_summary_context`
- `original_source_id`
- `later_source_ids`
- `likely_significance`
- `confidence_level`
- `omission_type`
- `supporting_uids`

## Contradiction table

Each `contradiction_table[*]` row contains:

- `row_id`
- `original_statement_or_promise`
- `later_action`
- `original_source_id`
- `later_source_id`
- `likely_significance`
- `confidence_level`
- `contradiction_kind`
- `supporting_uids`

Rules:

- the layer is source-linked and confidence-scored, not dispositive
- omission rows should appear only when later related summary or follow-up material exists and the prior promise/topic is not clearly carried forward
- contradiction rows may also reuse chronology sequence-break conflicts where extracted event timing materially diverges from recorded source timing
- the builder should stay conservative and prefer under-calling a contradiction over inventing one from weak text overlap
