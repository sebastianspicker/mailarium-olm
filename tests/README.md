# Test Layout Contract

Purpose:

- keep future tests easier to audit by component and workflow
- avoid adding more permanent ambiguity to the flat `tests/` root

Rules for new tests:

1. new tests should go in a component-aligned subdirectory when a stable family exists
2. keep the `tests/` root for legacy files and compatibility cases that have not been reorganized yet
3. add new helper utilities under `tests/helpers/`
4. add new static fixtures under `tests/fixtures/`

Current reality:

- the historical suite is still root-heavy
- the first migrated workflow slice now lives under `tests/case_workflows/`
- `tests/case_workflows/` currently owns case-intake, full-pack, case-CLI, and campaign-workflow slices
- the remaining root-level files are still legacy and should only move when a bounded workflow family is ready
