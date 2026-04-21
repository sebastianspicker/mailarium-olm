# Behavioral Evidence Citations

Version: `1`

## Purpose

`finding_evidence_index` and `evidence_table` make behavioural-analysis findings reproducible from stable evidence handles instead of relying on free-form summaries.

This contract does not score strength yet. It only binds findings to evidence.

## Top-level outputs

Case-scoped `email_answer_context` now emits:

- `finding_evidence_index`
- `evidence_table`

## `finding_evidence_index`

```json
{
  "version": "1",
  "finding_count": 2,
  "findings": []
}
```

Each finding entry contains:

- `finding_id`
- `finding_scope`
- `finding_label`
- `supporting_evidence`
- `contradictory_evidence`
- `counter_indicators`
- `quote_ambiguity`

## Citation fields

Each citation in `supporting_evidence` or `contradictory_evidence` contains:

- `citation_id`
- `evidence_role`
- `message_or_document_id`
- `timestamp`
- `source_type`
- `title`
- `actors`
  - `actor_ids`
  - `actor_emails`
- `text_attribution`
  - `text_origin`
  - `speaker_status`
  - `authored_quoted_inferred_status`
- `passage`
  - `excerpt`
  - `bounds.start`
  - `bounds.end`
  - `bounds.segment_ordinal`
  - `bounds.segment_type`
- `provenance`
  - `evidence_handle`
  - `uid`
  - `snippet_start`
  - `snippet_end`
  - `provenance_kind`
  - `inference_basis`
  - `evidence_chain_role`
- `note`

## Documentary follow-up note

For attachment-backed and formal-document evidence, citation review should be read together with the matching
`multi_source_case_bundle.sources[*].documentary_support` and `document_locator` payloads.

Reason:

- citation rows preserve finding-to-evidence binding
- documentary support preserves OCR state, extraction weakness, and reviewer follow-up guidance
- document locator preserves stable chunk-level provenance for later exhibit or chronology work

## Quote ambiguity downgrade

Quoted findings are automatically marked in `quote_ambiguity`:

- `downgraded_due_to_quote_ambiguity`
- `reason`
- `speaker_source`
- `speaker_confidence`

Current rule:

- `speaker_source == canonical_sender`
  - no downgrade
- any inferred or unresolved quoted speaker source
  - downgrade the finding

This is a caution flag only. Strength scoring still belongs to BA13.

## `evidence_table`

`evidence_table` is the flat export structure for downstream review.

```json
{
  "version": "1",
  "row_count": 2,
  "summary": {
    "finding_scope_counts": {},
    "evidence_role_counts": {}
  },
  "rows": []
}
```

Each row keeps the essential export fields:

- `finding_id`
- `finding_scope`
- `finding_label`
- `evidence_role`
- `message_or_document_id`
- `timestamp`
- `source_type`
- `actor_ids`
- `actor_emails`
- `text_origin`
- `authored_quoted_inferred_status`
- `speaker_status`
- `evidence_handle`
- `provenance_kind`
- `inference_basis`
- `evidence_chain_role`
- `excerpt`
- `segment_ordinal`
- `start`
- `end`

## Current boundary

Version `1` covers:

- message-level behaviour findings
- quoted-block behaviour findings
- case-pattern summaries
- directional summaries
- retaliation trigger summaries
- comparator summaries
- communication-graph findings

It does not yet assign evidence strength, legal interpretation weight, or contradiction scoring. Those stay in later BA phases.

## Provenance kinds

Current `provenance.provenance_kind` values include:

- `direct_text`
  - direct authored-text support for a message-local finding
- `message_metadata`
  - message-local metadata support, such as recipient omission or reply-pairing evidence
- `quoted_text`
  - quoted-block support with separate quote-attribution state
- `pattern_inference`
  - case-pattern summary support tied to contributing message UIDs
- `directional_inference`
  - directional summary support tied to contributing message UIDs
- `trigger_inference`
  - retaliation before/after support tied to trigger buckets
- `comparative_inference`
  - target/comparator support tied to comparator buckets
- `graph_inference`
  - communication-graph support tied to visibility or side-channel evidence chains

These fields are meant to stop higher-level inferred findings from reading like plain direct text findings.
