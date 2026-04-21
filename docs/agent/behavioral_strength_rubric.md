# Behavioral Strength Rubric

Version: `1`

## Purpose

BA13 adds a rule-backed strength layer on top of `finding_evidence_index` and `evidence_table`.

It does not decide legality or motive. It only scores how strong the current evidence is and how cautiously the interpretation should be read.

## Per-finding fields

Each non-trivial finding now carries:

- `evidence_strength`
  - `label`
  - `score`
  - `rationale`
- `confidence_split`
  - `evidence_confidence`
    - `label`
    - `score`
  - `interpretation_confidence`
    - `label`
    - `score`
- `alternative_explanations`
- `counter_indicators`

## Strength labels

The current rule-backed labels are:

- `strong_indicator`
- `moderate_indicator`
- `weak_indicator`
- `insufficient_evidence`

## Current rubric summary

Evidence strength increases when:

- at least one supporting citation exists
- multiple supporting citations exist
- support spans more than one evidence handle or message/document
- direct authored text is present
- canonical quoted text is present

Evidence strength decreases when:

- support is metadata-heavy without direct authored or quoted text
- contradictory evidence is present
- multiple counter-indicators are present
- quote ambiguity downgrades the finding

Interpretation confidence is reduced further when the finding is more inferential, especially for:

- `case_pattern`
- `directional_summary`
- `communication_graph`
- `comparative_treatment`
- `retaliation_analysis`

## Top-level payload block

Case-scoped `email_answer_context` now emits:

- `behavioral_strength_rubric`

```json
{
  "version": "1",
  "labels": [
    "strong_indicator",
    "moderate_indicator",
    "weak_indicator",
    "insufficient_evidence"
  ],
  "rule_summary": []
}
```

## Evidence-table enrichment

Each `evidence_table.rows[*]` entry now also includes:

- `evidence_strength`
- `evidence_confidence`
- `interpretation_confidence`

This lets downstream exports stay flat without losing the BA13 assessment.

## Current boundary

Version `1` is intentionally conservative:

- it scores evidence strength
- it surfaces alternative explanations
- it splits evidence confidence from interpretation confidence

It still does not:

- rank contradictory evidence by weight
- perform legal qualification
- determine discrimination or mobbing as a conclusion

Those remain later-phase work.
