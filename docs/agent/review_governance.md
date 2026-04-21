# Human Review State And Provenance Governance

Version: `1`

Status: `approved_for_implementation`

This milestone adds durable human-review state and override persistence for shared matter products.

## Review states

Supported `review_state` values:

- `machine_extracted`
- `human_verified`
- `disputed`
- `draft_only`
- `export_approved`

Counsel-facing export policy:

- `autonomous internal completion` means the shared campaign workflow and results-control surfaces are complete enough for internal use, but the snapshot may still be `machine_extracted` or `draft_only`
- `human-gated counsel export` means counsel-facing delivery remains blocked until a persisted snapshot is `human_verified` or `export_approved`
- `machine_extracted` is the default autonomous snapshot state and is not counsel-exportable
- `draft_only` is an explicit internal-handoff state and is still not counsel-exportable
- counsel-facing exports require `human_verified` or `export_approved`
- an unpersisted payload is never counsel-exportable, even if the machine-side classification claims counsel-grade completeness
- when counsel export is blocked, use internal surfaces such as `dashboard`, `exhibit_register`, or the persisted case payload instead of a counsel handoff bundle

## Persistence contract

SQLite now keeps one `matter_review_overrides` row per:

- `workspace_id`
- `target_type`
- `target_id`

Each row stores:

- `review_state`
- `override_payload_json`
- `machine_payload_json`
- `source_evidence_json`
- `reviewer`
- `review_notes`
- `apply_on_refresh`
- `created_at`
- `updated_at`

## Supported override targets

Version `1` supports persisted overrides for:

- `actor_link`
- `chronology_entry`
- `issue_tag_assignment`
- `exhibit_description`
- `contradiction_judgment`

## Refresh behavior

Case-analysis refresh now:

1. builds the machine payload
2. annotates reviewable items as `machine_extracted`
3. loads persisted overrides for the current `matter_workspace.workspace_id`
4. reapplies any override with `apply_on_refresh = true`
5. emits `review_governance` summary metadata on the outward payload

This keeps machine output, human edits, and cited source evidence distinct instead of overwriting machine provenance.

## Current boundary

Version `1` is a persistence-and-refresh layer.

- it supports durable correction and approval metadata
- it does not yet add dedicated MCP write tools or a UI workflow for editing overrides
- it does not yet resolve factual conflicts automatically; that remains Milestone 11.4
- it intentionally keeps counsel-facing export as a post-review action rather than an autonomous machine-only step
