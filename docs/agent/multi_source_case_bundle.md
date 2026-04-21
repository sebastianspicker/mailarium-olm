# Multi-Source Case Bundle

Version: `1`

## Purpose

`multi_source_case_bundle` exposes case-scoped evidence as explicit source objects instead of flattening everything into email-body hits. It is meant to preserve source type, provenance, and weighting context for later behavioural-analysis phases.

Version `1` now supports two parallel inputs:

- retrieval-derived email and attachment evidence
- operator-supplied `matter_manifest` artifacts for exhaustive matter-review and completeness accounting

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
  - operator-supplied chat-log evidence when explicitly included in mixed-case analysis
- `note_record`
  - attachment-backed notes, Gedächtnisprotokolle, meeting summaries, memos, or similar note-like records
- `time_record`
  - attachment-backed time, attendance, timesheet, or Arbeitszeit records
- `participation_record`
  - attachment-backed SBV, Personalrat, Betriebsrat, consultation, or similar participation-path records

Additional explicit manifest `source_class` values may normalize into the source types above while preserving the original class in `summary.source_class_counts` and per-source `source_class` fields. These include:

- `personnel_file_record`
- `job_evaluation_record`
- `prevention_record`
- `medical_record`
- `attendance_export`
- `calendar_export`
- `chat_export`
- `archive_bundle`
- `screenshot`

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
    "source_class_counts": {
      "personnel_file_record": 1
    },
    "available_source_types": ["email", "formal_document", "meeting_note"],
    "missing_source_types": [
      "attachment",
      "chat_log",
      "note_record",
      "time_record",
      "participation_record"
    ],
    "link_count": 2,
    "direct_text_source_count": 3,
    "contradiction_ready_source_count": 2,
    "documentary_source_count": 2,
    "weak_extraction_source_count": 0,
    "ocr_source_count": 0,
    "unsupported_format_source_count": 0,
    "lossy_extraction_source_count": 0,
    "chronology_anchor_count": 3,
    "source_format_matrix_version": "1"
  },
  "sources": [],
  "source_links": [],
  "source_type_profiles": [],
  "chronology_anchors": []
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
- optional `document_locator`
- optional `documentary_support`
- optional `follow_up`
- `source_reliability`
- `source_weighting`
- optional `chronology_anchor`

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
- `attachment_ocr_text_extracted`
- `formal_document_text_extracted`
- `formal_document_ocr_text_extracted`
- `note_record_text_extracted`
- `note_record_ocr_text_extracted`
- `time_record_text_extracted`
- `time_record_ocr_text_extracted`
- `participation_record_text_extracted`
- `participation_record_ocr_text_extracted`
- `attachment_ocr_failed`
- `formal_document_ocr_failed`
- `note_record_ocr_failed`
- `time_record_ocr_failed`
- `participation_record_ocr_failed`
- `attachment_binary_only`
- `formal_document_binary_only`
- `note_record_binary_only`
- `time_record_binary_only`
- `participation_record_binary_only`
- `attachment_reference_only`
- `calendar_meeting_metadata`
- `exchange_extracted_meeting_reference`
- `caveats`

## Documentary support

Attachment-backed and document-backed sources now keep explicit documentary extraction semantics:

- `filename`
- `mime_type`
- `text_available`
- `evidence_strength`
- `extraction_state`
- `ocr_used`
- `failure_reason`
- `text_preview`
- `format_profile`
- `extraction_quality`
- `review_recommendation`

This is the main downgrade surface that stops OCR failures, binary-only hits, and weak reference-only attachments from reading like ordinary strong text evidence.

`format_profile` is the format-support contract:

- `format_id`
- `format_family`
- `format_label`
- `handling_mode`
- `support_level`
- `lossiness`
- `manual_review_required`
- `degrade_reason`
- `limitations`

`extraction_quality` is the observed extraction-result contract:

- `quality_label`
- `quality_rank`
- `lossiness`
- `visible_limitations`
- `manual_review_required`

## Document locator

Documentary sources may also expose compact locator metadata for downstream exhibit and chronology work:

- `evidence_handle`
- `chunk_id`
- `snippet_start`
- `snippet_end`
- `page_hint`
- `section_hint`

Page or section hints appear only when the upstream source exposes them; otherwise the locator still keeps the stable evidence handle and chunk reference.

## Chronology anchors

`chronology_anchors` is a flattened mixed-source date list for downstream chronology work.

Each anchor contains:

- `source_id`
- `source_type`
- `document_kind`
- `date`
- `title`
- `reliability_level`
- `date_origin`
- optional `date_range`
- optional `source_recorded_date`

This is intentionally lightweight. It is a chronology-ready staging surface, not yet the final exhibit or timeline product.

Current chronology extraction rules:

- meeting notes may prefer extracted meeting-start metadata over the parent email timestamp
- note, participation, formal-document, and attachment records may prefer explicit ISO-like dates found in visible document text
- time records may expose a `date_range` and anchor from the range start instead of only the file or email timestamp
- when a source-derived event date materially differs from the recorded source timestamp, the anchor may also keep `source_recorded_date` for later contradiction review

## Source type profiles

`source_type_profiles` now keep richer availability metadata per source type:

- `direct_text_count`
- `contradiction_ready_count`
- `reliability_counts`
- `weak_extraction_count`
- `ocr_source_count`
- `format_support_counts`
- `extraction_quality_counts`

## Matter manifest and completeness

Case-analysis runs may now also carry a sibling `matter_ingestion_report` payload.

This ledger records:

- `review_mode`
  - `retrieval_only`
  - `exhaustive_matter_review`
- `completeness_status`
- `total_supplied_artifacts`
- `parsed_artifacts`
- `degraded_artifacts`
- `unsupported_artifacts`
- `excluded_artifacts`
- `not_yet_reviewed_artifacts`
- `accounted_artifacts`
- `unaccounted_artifacts`
- `source_class_counts`
- `custodian_counts`

Each manifest artifact row also keeps:

- `artifact_id`
- `source_id`
- `source_class`
- `normalized_source_type`
- `review_status`
- `accounting_status`
- `format_support_level`
- `related_email_uid`

This is the repo’s machine-readable proof surface for “all supplied artifacts accounted for” claims.

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
- attachment-backed note-like records
- attachment-backed time and attendance records
- attachment-backed participation records

The shared file-class handling matrix is documented separately in [source_format_ingestion_matrix.md](./source_format_ingestion_matrix.md).

It still does not ingest external formal-document stores beyond the retrieved attachment/document surface. Record-type widening remains conservative: weak or binary-only materials stay visibly downgraded through `documentary_support`, and the compact `email_answer_context` path may emit a trimmed bundle view that preserves summary counts, source ids, source links, and the documentary fields needed for lightweight answer-context follow-up without the full chronology metadata.
