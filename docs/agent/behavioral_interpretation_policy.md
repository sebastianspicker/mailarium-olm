# Behavioural Analysis Interpretation Policy

Version: `1`

This BA17 policy constrains the investigation-style renderer for workplace-conflict analysis.

## Claim levels

- `observed_fact`
  - allowed when the cited material directly supports a bounded statement about wording or behaviour in the message itself
- `pattern_concern`
  - required when the current record is suggestive but still materially ambiguous
- `stronger_interpretation`
  - allowed for multi-signal case-level findings only as a cautious interpretation
- `insufficient_evidence`
  - required when the record does not support a reliable interpretation

## Hard guardrails

- do not assert motive unless separately established outside the current report
- do not assert legal conclusions from the behavioural-analysis layer alone
- do not treat pattern, comparator, graph, or retaliation findings as direct facts
- surface alternative explanations when they materially weaken the current read
- surface ambiguity when quote ownership or interpretation confidence remains weak
- do not use `discrimination_concern` unless explicit discriminatory content, strong comparator asymmetry, or protected-context evidence materially supports it
- do not use `retaliation_concern` unless a defined trigger event and a measurable adverse before/after shift are both present
- do not use `mobbing_like_pattern_concern` from one isolated message or one weak signal family alone
- do not infer protected-category motive from generic hostility, formality, or exclusion by itself
- do not use psychiatric, character, or diagnosis-style labels for actors
- keep retaliation, comparator, graph, discrimination-style, and mobbing-style findings at concern wording in this layer even when support is strong

## Bounded final assessments

When a final case-analysis report renders an overall assessment, the allowed bounded categories are:

- `ordinary_workplace_conflict`
- `poor_communication_or_process_noise`
- `targeted_hostility_concern`
- `unequal_treatment_concern`
- `retaliation_concern`
- `discrimination_concern`
- `mobbing_like_pattern_concern`
- `insufficient_evidence`

These are review classifications, not legal determinations.

Additional renderer rule:

- if more than one category remains materially plausible, render one primary assessment plus visible secondary plausible interpretations instead of collapsing ambiguity

## Output contract

The investigation report now includes:

- top-level `interpretation_policy`
  - `refuse_to_overclaim`
  - per-entry:
  - `claim_level`
  - `policy_reason`
  - `ambiguity_disclosures`
  - `alternative_explanations`

The top-level policy block also exposes:

- `prohibited_claims`
- `refusal_rules`

The policy layer sits on top of BA12 and BA13 outputs. It does not rescore evidence. It only constrains what the renderer is allowed to say.
