# Cross-Output Consistency

## Goal

Prevent the shared legal-support outputs from drifting into silent contradictions once they are rendered from the same matter workspace.

## Output

`cross_output_consistency` is a machine-readable parity payload generated from the shared registries and the downstream products that reuse them.

Fields:

- `version`
- `overall_status`
  - `consistent`
  - `review_required`
- `machine_review_required`
- `summary`
  - `check_count`
  - `pass_count`
  - `mismatch_count`
- `affected_outputs`
- `checks`

## Current checks

- chronology-reference parity across memo, dashboard, and controlled draft
- issue-reference parity across issue matrix, memo, dashboard, and controlled draft
- exhibit-reference plus ranking/strength parity against `matter_evidence_index`
- chronology-to-issue-matrix alignment using selected chronology support reads
- dashboard actor-role parity against the shared actor map
- skeptical-review carry-through into memo and dashboard risk surfaces
- framing-preflight and controlled-draft ceiling alignment

## Interpretation

- `consistent` means the checked outputs align on the current structural references and bounded parity rules
- `review_required` means at least one mismatch was found and the affected products should be reviewed before external reliance or export
- this layer is a parity control, not a legal-opinion layer
