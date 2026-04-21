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

## Output contract

The investigation report now includes:

- top-level `interpretation_policy`
- per-entry:
  - `claim_level`
  - `policy_reason`
  - `ambiguity_disclosures`
  - `alternative_explanations`

The policy layer sits on top of BA12 and BA13 outputs. It does not rescore evidence. It only constrains what the renderer is allowed to say.
