# Bilingual And Translation-Aware Workflows

Version: `1`

Status: `approved_for_implementation`

This workspace now supports German-first and bilingual legal-support rendering for matters where source evidence is primarily German but some outward work products may still need English.

## Scope

The bilingual layer currently applies to:

- `lawyer_issue_matrix`
- `lawyer_briefing_memo`
- `controlled_factual_drafting`
- `case_dashboard`

It also adds shared run metadata at:

- top-level `case_analysis.bilingual_workflow`
- top-level `investigation_report.bilingual_workflow`

## Core rules

- original-language evidence must remain preserved
- translated or output-language summaries must stay separate from quoted evidence
- the system may render narrative summaries in the requested output language without rewriting the source record
- quoted evidence must remain tied to the original-language text fields

## German-first default

For German-dominant matters:

- use `output_language='de'` as the working default
- use `translation_mode='source_only'` as the working default
- treat English output as an explicit export or comparison mode, not as the default execution language
- keep German-native retrieval and issue terminology primary even when an English-facing product is requested later

## Detection guardrails

- `source_language` and `primary_source_language` are only as good as the current analytics pass
- if `email_quality(check='languages')` is empty or stale, run `email_admin(action='reingest_analytics')`
- if short or forwarded German messages are misclassified, do not let the misclassification drive retrieval suppression
- preserve German-native spellings and orthographic fallback variants in the query packs

## Input controls

`EmailCaseAnalysisInput` and `EmailLegalSupportInput` now accept:

- `output_language`
  - `en`
  - `de`
- `translation_mode`
  - `source_only`
  - `translation_aware`

## Shared metadata

`bilingual_workflow` contains:

- `version`
- `output_language`
- `output_language_label`
- `translation_mode`
- `primary_source_language`
- `primary_source_language_label`
- `source_languages`
- `source_language_labels`
- `source_language_counts`
- `preserve_original_quotations`
- `translated_summaries_allowed`
- `cross_language_rendering`
- `translation_boundary`

## Evidence preservation

`matter_evidence_index.rows[*]` now also carry:

- `source_language`
- `quoted_evidence`
  - `original_language`
  - `original_language_label`
  - `original_text`
  - `quote_translation_included`
  - `translated_summary_fields`

This keeps the original German-source passage visible even when the surrounding product is rendered for English-facing counsel workflows.
