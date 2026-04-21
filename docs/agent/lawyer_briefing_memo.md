# Lawyer Briefing Memo

## Goal

Render a compact, evidence-bound onboarding memo for external or internal counsel after the shared matter model, evidence index, chronology, and issue matrix are stable.

## Top-level contract

The shared builder emits:

- `version`
- `memo_format`
  - `lawyer_onboarding_brief`
- `summary`
- `sections`

## Summary fields

- `section_count`
- `entry_count`
- `compact_length_budget`
- `non_repetition_policy`
- `evidence_bound`

## Memo sections

`sections` contains:

- `executive_summary`
- `key_facts`
- `timeline`
- `core_theories`
- `strongest_evidence`
- `weaknesses_or_risks`
- `urgent_next_steps`
- `open_questions_for_counsel`

Each memo entry contains:

- `entry_id`
- `text`
- `supporting_exhibit_ids`
- `supporting_chronology_ids`
- `supporting_issue_ids`
- `supporting_source_ids`

Rules:

- the memo must be derived from the shared matter, evidence, chronology, issue, and weakness/request products rather than from free-form prompting
- the memo should stay compact and non-repetitive instead of restating the full report
- weak spots, open questions, and urgent next steps must remain visible rather than being buried behind the strongest evidence
- the memo is an onboarding product for counsel, not final legal advice
