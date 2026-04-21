# Export Delivery Formats

Version: `1`

Status: `approved_for_implementation`

This contract makes the stable legal-support products usable outside the MCP client without manual reconstruction.

## Export targets

Current portable export targets are:

- `counsel_handoff`
  - supported formats: `html`, `pdf`
- `exhibit_register`
  - supported formats: `csv`, `json`
- `dashboard`
  - supported formats: `csv`, `json`
- `counsel_handoff_bundle`
  - supported format: `bundle`

## Delivery rules

- all exports are derived from the same shared `case_analysis` payload
- format differences must not change the substantive record
- spreadsheet exports are emitted as spreadsheet-safe CSV
- bundle exports are zipped archives with a manifest
- PDF delivery reuses the HTML rendering path and falls back to HTML if PDF support is unavailable
- `counsel_handoff` and `counsel_handoff_bundle` remain blocked until the persisted snapshot review state is `human_verified` or `export_approved`
- when the snapshot is still `machine_extracted` or `draft_only`, use `dashboard` or `exhibit_register` as the internal handoff surface instead of a counsel export

## Current bundle contents

`counsel_handoff_bundle` currently includes:

- `manifest.json`
- `counsel_handoff.html`
- `exhibit_register.csv`
- `case_dashboard.json`
- `lawyer_briefing_memo.json`
- `lawyer_issue_matrix.json`
- `investigation_report.json`

The manifest records:

- bundle version
- workflow
- generated time
- analysis query
- privacy mode
- included artifact list

## Current boundary

Version `1` is intentionally bounded:

- it does not yet generate native `.xlsx`
- it does not yet add email or filesystem delivery automation
- it does not yet add signature workflows or approval routing
- it focuses on parity and traceability across the most important counsel-handoff artifacts
