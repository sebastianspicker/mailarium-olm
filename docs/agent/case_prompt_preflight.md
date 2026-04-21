# Case Prompt Preflight

Version: `1`

Status: `implemented`

`case_prompt_preflight` is the bounded prompt-only intake lane for legal-support work.

It exists to:

- accept a long natural-language matter description
- extract conservative structured intake hints
- identify missing fields before a structured case run
- keep prompt-only usage clearly below the threshold for exhaustive legal-support review

It does not:

- prove facts
- fabricate `trigger_events`
- fabricate comparator actors
- fabricate a `matter_manifest`
- turn raw prose into a counsel-grade exhaustive review automatically

## Output contract

The payload contains:

- `workflow`
- `analysis_goal`
- `recommended_source_scope`
- `draft_case_scope`
- `draft_case_analysis_input`
- `candidate_structures`
- `extraction_summary`
- `missing_required_inputs`
- `recommended_next_inputs`
- `ready_for_case_analysis`
- `supports_exhaustive_legal_support`
- `prompt_limits`

## Current rules

- extracted actor and date fields must come from visible prompt text or bounded parsing of visible prompt text
- `candidate_structures` may surface:
  - trigger-event candidates
  - adverse-action candidates
  - comparator candidates
  - protected-context candidates
  - missing-record candidates
- every serious missing field should be surfaced explicitly instead of inferred away
- candidate structures are not confirmed case facts; they remain review-facing unless a later deterministic rule or explicit override promotes them
- retaliation-focused prompts still require explicit structured `trigger_events` and `alleged_adverse_actions`
- comparator-heavy prompts still require explicit `comparator_actors`
- dedicated legal-support product tools remain strict about `review_mode='exhaustive_matter_review'` and `matter_manifest`
