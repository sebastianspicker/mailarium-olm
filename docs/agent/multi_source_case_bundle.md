# Multi-Source Case Bundle

Version: `1`

## Purpose

`multi_source_case_bundle` exposes case-scoped evidence as explicit source objects instead of flattening everything into email-body hits. It is meant to preserve source type, provenance, and weighting context for later behavioural-analysis phases.

## Source types

- `email`
  - authored email-body evidence
- `attachment`
  - non-document attachment evidence
- `formal_document`
  - document-like attachment evidence such as `pdf`, `docx`, `txt`, or similar MIME types
- `meeting_note`
  - meeting metadata extracted from the parent email row
- `chat_log`
  - declared source type for future support; currently surfaced as unavailable unless present in future evidence builders

## Top-level shape

```json
{
  "version": "1",
  "summary": {
    "source_count": 3,
    "source_type_counts": {
      "email": 1,
      "formal_document": 1,
      "meeting_note": 1
    },
    "available_source_types": ["email", "formal_document", "meeting_note"],
    "missing_source_types": ["attachment", "chat_log"],
    "link_count": 2,
    "direct_text_source_count": 3,
    "contradiction_ready_source_count": 2
  },
  "sources": [],
  "source_links": [],
  "source_type_profiles": []
}
```

## Source object

Each source preserves:

- `source_id`
- `source_type`
- `document_kind`
- `uid`
- `actor_id`
- `title`
- `date`
- `snippet`
- `provenance`
- optional `attachment`
- optional `follow_up`
- `source_reliability`
- `source_weighting`

## Source reliability

`source_reliability` is explicit and conservative:

- `level`
  - `high`
  - `medium`
  - `low`
- `basis`
  - `authored_email_body`
  - `forensic_body_verification`
  - `weak_message_semantics`
  - `attachment_text_extracted`
  - `formal_document_text_extracted`
  - `attachment_reference_only`
  - `calendar_meeting_metadata`
  - `exchange_extracted_meeting_reference`
- `caveats`

## Source weighting

`source_weighting` exists for later evidence synthesis:

- `weight_label`
- `base_weight`
- `text_available`
- `can_corroborate_or_contradict`

This flag is intentionally narrower than “credible.” It only means the source exposes enough direct text to support later corroboration or contradiction review.

## Source links

`source_links` currently exposes:

- `attached_to_email`
- `extracted_from_email`

Relationship labels remain conservative:

- `can_corroborate_or_contradict_message`
- `reference_only_attachment`
- `contextual_metadata`

## Current boundary

Version `1` only fuses source types already available on the current repo surface:

- email bodies
- attachment hits
- document-like attachments
- meeting metadata extracted from email rows

It does not yet ingest standalone chat logs or external formal-document stores. Those source types remain explicitly visible through `source_type_profiles` and `missing_source_types` instead of being implied.
