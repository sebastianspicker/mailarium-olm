# Quote Attribution Policy

## Version

- `1`

## Goal

Keep authored text, quoted history, and inferred speaker cues separate so high-stakes behavioural findings do not overclaim quoted ownership.

## Attribution states

- `explicit_header`
  - A visible quoted `From:` header identifies one non-authored speaker.
  - This is treated as quoted history with direct textual ownership support.
  - Quote-driven findings are not downgraded for ambiguity on this basis alone.
- `corroborated_reply_context`
  - The quoted block exposes one speaker through reply-context structure, optionally corroborated by message-level reply-context metadata.
  - This is treated as quoted history with bounded but sufficient ownership support.
  - Quote-driven findings are not downgraded for ambiguity on this basis alone.
- `inferred_single_candidate`
  - Only one non-authored identity is visible in the quoted block, but ownership is still inferential.
  - Quote-driven findings are downgraded for ambiguity.
- `participant_exclusion`
  - Ownership is inferred only because one non-authored conversation participant remains after exclusions.
  - Quote-driven findings are downgraded for ambiguity.
- `unresolved`
  - Multiple plausible quoted speakers remain.
  - Quote-driven findings are downgraded for ambiguity.

## Report-model separation

- `text_origin`
  - `authored`, `quoted`, or `metadata`
- `speaker_status`
  - `canonical`, `inferred`, `unresolved`, or `not_applicable`
- `authored_quoted_inferred_status`
  - `authored`
  - `quoted`
  - `inferred`
- `quote_attribution_status`
  - one of the attribution states above

## Downgrade rule

Downgrade quote-driven findings only when `quote_attribution_status` is one of:

- `inferred_single_candidate`
- `participant_exclusion`
- `unresolved`

Do not downgrade solely because the text is quoted. Quoted history with explicit header support or corroborated reply-context support remains quoted evidence, not an automatically weakened inference.

## Metrics

Case-scoped behavioural payloads emit `quote_attribution_metrics` with:

- `quoted_block_count`
- `resolved_block_count`
- `unresolved_block_count`
- `status_counts`
- `source_counts`
- `quote_finding_count`
- `downgraded_quote_finding_count`

These metrics are the benchmark-facing BA14 contract for measuring quote-attribution quality without collapsing authored and quoted evidence into one bucket.
