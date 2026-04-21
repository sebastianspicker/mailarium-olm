# Case Full Pack

## Goal

Bridge the gap between prompt-first operator workflows and the repo's strict manifest-backed legal-support products.

## Workflow

`case_full_pack` now does the following in one bounded flow:

1. run `case_prompt_preflight`
   - now includes review-facing candidate structures for trigger events, adverse actions, comparators, protected-context references, and missing-record classes
2. build a conservative `matter_manifest` from the supplied materials directory
3. enrich the manifest into a bounded material-preflight
   - auto-apply only unambiguous target/date/trigger/adverse-action values backed by supplied materials
   - keep ambiguous values in review-facing candidate structures instead of silently guessing
4. merge optional structured overrides
5. validate mandatory and conditional gates
6. if blockers remain, stop with a machine-readable blocker payload
   - include `intake_compilation.override_suggestions` with:
      - exact blocked fields
      - bounded candidate values when confidence is adequate
      - minimal override examples
7. otherwise run the downstream exhaustive legal-support workflow
8. optionally write an export artifact through the shared legal-support exporter

## Output states

- `blocked`
  - missing mandatory or conditional structured inputs still prevent a defensible exhaustive run
- `ready`
  - compile-only mode succeeded and the downstream run was intentionally not executed
- `completed`
  - the downstream exhaustive workflow ran successfully

## Important rules

- do not fabricate trigger events, comparators, or adverse actions from prose alone
- candidate structures from prompt preflight are advisory and review-facing unless explicitly promoted by override or a later deterministic rule
- supplied materials may auto-fill intake only when the extracted value is unambiguous and source-backed
- use explicit blockers instead of weak guessing
- blocked runs should be repairable by thin clients without reverse-engineering the internal schema
- reuse the shared case-analysis and export pipeline instead of creating a parallel legal-support stack
- keep `matter_manifest` generation conservative and visibility-first
- preserve the compile layer as a reusable preflight even after execution support exists
