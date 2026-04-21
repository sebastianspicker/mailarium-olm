# Source-Format Ingestion Matrix

Version: `2`

Status: `approved_for_implementation`

This matrix is the shared format-support contract for mixed-source case work. It exists to make per-file handling explicit instead of leaving support assumptions buried in extractor code.

## Purpose

- make likely employment-matter file classes visible and testable
- distinguish supported, degraded, reference-only, and unsupported handling
- keep extraction lossiness visible through downstream evidence and legal-support products

## Output contract

Attachment-backed sources may expose two nested payloads under `documentary_support`:

- `format_profile`
- `extraction_quality`

`format_profile` keeps the format-class decision:

- `format_id`
- `format_family`
- `format_label`
- `handling_mode`
- `support_level`
- `lossiness`
- `manual_review_required`
- `degrade_reason`
- `limitations`

`extraction_quality` keeps the observed extraction state:

- `quality_label`
- `quality_rank`
- `lossiness`
- `visible_limitations`
- `manual_review_required`

## Current matrix

- scanned PDFs
  - `format_id: scanned_pdf`
  - `support_level: degraded_supported`
  - `handling_mode: ocr_recovered_text`
  - lossiness remains visible because OCR wording can drift from the page image
- OCR-poor PDFs
  - `format_id: ocr_poor_pdf`
  - `support_level: reference_only`
  - `handling_mode: reference_only_after_ocr_failure`
  - must stay weak until the original PDF is reviewed
- DOCX files
  - `format_id: docx_document`
  - `support_level: supported`
  - `handling_mode: native_docx_text_extraction`
  - degrades to `reference_only` if reliable text is unavailable
- legacy and portable word-processing documents such as `doc`, `odt`, and `rtf`
  - `format_id: portable_word_processing_document`
  - `support_level: degraded_supported`
  - `handling_mode: document_text_extraction_or_plain_text_fallback`
  - richer layout and tracked-change context may be flattened
- spreadsheets and time exports
  - `format_id: spreadsheet_export`
  - `support_level: degraded_supported`
  - `handling_mode: flattened_tabular_text`
  - formulas, workbook structure, and formatting are treated as lossy
  - now also covers `xls`, `xlsm`, and `ods` as explicit loss-visible classes in the matrix
- calendar files
  - `format_id: calendar_file`
  - `support_level: degraded_supported`
  - `handling_mode: calendar_text_flattened`
  - richer recurrence and calendar semantics are treated as lossy
- screenshots and image-only exhibits
  - `format_id: image_only_exhibit`
  - `support_level: reference_only`
  - `handling_mode: image_embedding_or_reference_only`
  - visual review remains mandatory before serious reliance
- screenshots and image exhibits with sidecar transcript text
  - `format_id: image_sidecar_transcript`
  - `support_level: degraded_supported`
  - `handling_mode: sidecar_transcript_text`
  - the sidecar transcript can surface wording, but visual emphasis and layout still require manual review
- transcript-like text bundles
  - `format_id: transcript_text_bundle`
  - `support_level: supported`
  - `handling_mode: plain_text_ingestion`
- archive bundles
  - `format_id: archive_bundle`
  - `support_level: unsupported`
  - `handling_mode: unsupported_archive_container`
  - unsupported formats must remain explicit rather than silently flattened
- archive bundles with member inventory
  - `format_id: archive_inventory_bundle`
  - `support_level: degraded_supported`
  - `handling_mode: archive_member_inventory_only`
  - only member names are available; the archive contents still need manual extraction before serious reliance

## Current boundary

Version `2` is still a format-support visibility layer, not a full parser stack.

- it classifies the current pipeline honestly
- it now supports companion sidecar transcripts for weak image exhibits and archive member inventory for container files
- it does not yet add full archive unpacking, robust OCR, or spreadsheet formula recovery
- calendar artifacts now surface basic invite or update or cancellation semantics, but they still do not reconstruct the full original calendar object model
- unsupported and lossy formats remain visible in the bundle and exhibit surfaces so later outputs do not overstate evidentiary quality

## Matter-review note

When artifacts are supplied through `matter_manifest`, these format profiles still apply even when the artifact did not come from mailbox attachment extraction. That keeps fidelity warnings and refusal semantics aligned between retrieval-derived and manifest-derived matter evidence.
