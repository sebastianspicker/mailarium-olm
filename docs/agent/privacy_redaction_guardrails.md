# Privacy, Redaction, And Access-Control Guardrails

Version: `1`

Status: `approved_for_implementation`

This milestone adds an explicit privacy contract to outward case-analysis, legal-support, and archive-report outputs.

## Supported privacy modes

- `full_access`
  - internal case-team review mode
  - no privacy redaction beyond terminal-safe sanitization
- `external_counsel_export`
  - counsel handoff mode
  - redacts direct contact data while preserving factual and medical context
- `internal_complaint_use`
  - internal complaint mode
  - redacts direct contact data, privileged material, and sensitive medical detail
- `witness_sharing`
  - limited-circulation witness mode
  - redacts direct contact data, privileged material, sensitive medical detail, and structured participant identity fields

## Product-surface contract

Redacted outward products now keep `privacy_guardrails` metadata with:

- `privacy_mode`
- `audience`
- `description`
- `least_exposure_rules`
- `redaction_summary`

This metadata is emitted on:

- dedicated case-analysis payloads
- legal-support MCP products backed by case analysis
- investigation reports nested inside the case-analysis payload
- archive HTML reports rendered through `ReportGenerator`

## Current heuristic categories

The first guardrail pass distinguishes:

- contact data
  - email addresses and phone-like strings
- privileged content
  - strategy or privilege-marked text
- sensitive medical content
  - medical, diagnosis, disability, and physician-style wording
- structured participant identity
  - keyed identity fields in high-redaction witness-sharing mode

## Current boundary

Version `1` is a least-exposure layer, not a full authorization system.

- it makes privacy mode explicit in the product contract
- it emits full and redacted variants by switching `privacy_mode`
- it does not yet implement user authentication, role-backed persistence, or human approval workflows
