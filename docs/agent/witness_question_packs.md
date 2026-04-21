# Witness Question Packs

## Goal

Turn the shared actor and witness registry into practical interview preparation materials without drifting into scripted advocacy.

## Shared payload

`witness_question_packs` is a shared legal-support product derived from:

- `actor_witness_map`
- `master_chronology`
- `matter_evidence_index`
- `document_request_checklist`

Fields:

- `version`
- `pack_count`
- `summary`
  - `decision_maker_pack_count`
  - `independent_witness_pack_count`
  - `record_holder_pack_count`
- `packs`

Each `packs[*]` object contains:

- `pack_id`
- `actor_id`
- `actor_name`
- `actor_email`
- `pack_type`
- `likely_knowledge_areas`
- `key_tied_events`
- `documents_to_show_or_confirm`
- `factual_gaps_to_probe`
- `caution_notes`
- `suggested_questions`
- `non_leading_style`

## Rules

- packs must stay tied to shared ids and existing evidence rather than generic witness templates
- decision-maker packs should focus on rationale, approvals, discretion, and comparator treatment
- independent-witness packs should focus on firsthand observation and separation from later summaries
- record-holder packs should focus on provenance, retention, native exports, and metadata
- suggested questions must remain practical and non-leading
