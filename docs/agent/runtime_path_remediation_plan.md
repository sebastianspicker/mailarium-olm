# Runtime Path Remediation Plan

Status: `implemented on 2026-04-17 for runtime-path normalization; clean-ingest cutover pending deliberate operator rerun`

Implementation note:

- `private/runtime/current` now exists and targets the preserved `baseline-p73-2026-04-17` runtime
- the former `chromadb_p73` and `email_metadata_p73.db` names now remain as compatibility aliases pointing into that normalized baseline run
- the stronger legacy SQLite ledgers were moved under `private/runtime/ledgers/`
- the old live default pair remains available as a compatibility reference
- `private/ingest/my-export.olm` currently resolves through the checked local example archive, so source-archive availability is no longer the blocking condition

Purpose:

- eliminate runtime-path ambiguity between MCP and CLI
- stop binding operator workflows to versioned or ad hoc runtime filenames
- preserve the best existing legacy evidence state without treating any legacy runtime as the final canonical corpus
- prepare a clean future ingest run as the only acceptable long-term authority
- define how legacy SQLite and Chroma artifacts may be consolidated safely without destroying evidence or governance state

## Executive Decision

Long-term authoritative runtime:

- no existing `private/runtime/*` pair should be promoted as the final canonical corpus
- the final canonical runtime should come from a fresh clean ingest into a normalized run directory

Best existing legacy pair to preserve as the temporary reference baseline:

- `private/runtime/chromadb_p73`
- `private/runtime/email_metadata_p73.db`

Why this pair is the best legacy baseline:

- it is one of only two clean on-disk Chroma plus SQLite pairs currently visible
- it carries a stronger SQLite-side evidence state than the live default pair
- it is versioned, which makes it safer to preserve as a frozen comparison target instead of silently mutating it in place

Why it is still not the final authority:

- the repo currently contains divergent SQLite snapshots with different evidence counts
- the richest SQLite state is not part of a clean dedicated Chroma plus SQLite pair
- the current MCP and many docs still point at a different runtime pair
- a clean ingest is the only defensible way to re-establish one coherent runtime baseline

Consolidation decision:

- existing SQLite databases may be selectively consolidated into one interim target database
- existing Chroma directories must not be merged by copying or combining their internal storage files
- if one interim merged runtime is needed before the clean ingest, the safe path is:
  - consolidate SQLite first
  - rebuild one fresh Chroma collection from that consolidated SQLite
- this consolidation path is only an interim preservation and migration tool; it does not replace the later clean ingest as the final authority

## Current Runtime Evidence

Observed runtime artifacts in `private/runtime/`:

- Chroma directories:
  - `chromadb`
  - `chromadb_p73`
- SQLite databases:
  - `email_metadata.db`
  - `email_metadata_p73.db`
  - `email_metadata_finalrun.db`
  - `email_metadata_harvest.db`
  - `email_metadata_rerun.db`

Observed MCP client configuration:

- global MCP client config currently points to:
  - `private/runtime/chromadb`
  - `private/runtime/email_metadata.db`

Observed live MCP process:

- current running `src.mcp_server` is using:
  - `--chromadb-path private/runtime/chromadb`
  - `--sqlite-path private/runtime/email_metadata.db`

SQLite comparison snapshot:

| runtime sqlite | emails | message_segments | evidence_items | evidence_candidates | note |
| --- | ---: | ---: | ---: | ---: | --- |
| `email_metadata.db` | `19948` | `47690` | `30` | `300` | current live MCP sqlite |
| `email_metadata_p73.db` | `19948` | `47690` | `44` | `364` | best clean dedicated pair with `chromadb_p73` |
| `email_metadata_finalrun.db` | `19948` | `47690` | `30` | `300` | richer naming only, no dedicated Chroma sibling |
| `email_metadata_harvest.db` | `19948` | `47690` | `55` | `416` | richest SQLite-only state, but not a clean pair |
| `email_metadata_rerun.db` | `19948` | `47690` | `30` | `300` | side snapshot, no dedicated Chroma sibling |

Pair comparison snapshot:

| pair | total_chunks | evidence_items | decision role |
| --- | ---: | ---: | --- |
| `chromadb` + `email_metadata.db` | `36963` | `30` | current live operational pair only |
| `chromadb_p73` + `email_metadata_p73.db` | `36765` | `45` | best existing legacy baseline pair to preserve |

Interpretation:

- the current live pair has slightly more vector chunks
- the `p73` pair has materially richer verified evidence
- `email_metadata_harvest.db` is richer still, but it is not attached to its own dedicated Chroma runtime
- this means no existing artifact set is clean enough to become the final canonical runtime without a rebuild

## Planning Assumptions

1. the next canonical runtime should be created by a clean ingest, not by blessing one legacy snapshot forever
2. legacy runtime artifacts still have value and must be preserved long enough for comparison, migration, and evidence recovery
3. MCP and CLI must resolve to the same active runtime path after remediation
4. explicit runtime paths must remain mandatory for operator workflows; implicit fallback to tracked `data/` remains unsafe for this matter
5. private runtime layout belongs in operator and local-only docs, not in the public generic install path as a default replacement

## Target Runtime Layout

Target normalized layout:

```text
private/runtime/
  current -> runs/<run-id>/
  chromadb/
  email_metadata.db
  chromadb_p73 -> runs/baseline-p73-2026-04-17/chromadb
  email_metadata_p73.db -> runs/baseline-p73-2026-04-17/email_metadata.db
  runs/
    baseline-p73-2026-04-17/
      chromadb/
      email_metadata.db
      manifest.json
      notes.md
    live-default-legacy-2026-04-17/
      chromadb -> ../../chromadb
      email_metadata.db -> ../../email_metadata.db
      manifest.json
      notes.md
    merged-preclean-<date>/
      chromadb/
      email_metadata.db
      manifest.json
      notes.md
    clean-ingest-<date>/
      chromadb/
      email_metadata.db
      manifest.json
      notes.md
  archive/
    legacy-top-level/
  ledgers/
    email_metadata_harvest.db
    email_metadata_finalrun.db
    email_metadata_rerun.db
```

Rules for this layout:

- `current` must be the only path consumed by MCP client config
- `current` must be the only path referenced in operator-facing CLI examples for the private runtime
- every run directory must expose normalized child names:
  - `chromadb`
  - `email_metadata.db`
- versioned filenames may exist only under `archive/` or `ledgers/`, not as the active runtime contract

## Why The `current` Symlink Layer Is Preferred

Minimal rename or promote approach:

- simpler short-term
- still leaves future path churn likely
- invites the same ambiguity again once another run is created

Preferred `current` indirection layer:

- decouples operator and MCP client config from run-specific filenames
- allows an atomic cutover from one runtime to the next by changing one symlink
- makes rollback explicit
- keeps the final clean-ingest promotion small and reversible

Decision:

- use the `current` symlink layer
- do not rely on top-level `private/runtime/chromadb` and `private/runtime/email_metadata.db` as the lasting contract

## Critical Risk: Evidence Loss On Clean Rebuild

A clean ingest rebuilds searchable corpus state, but it does not automatically preserve every legacy operator-side evidence or campaign artifact already accumulated in SQLite.

High-risk legacy tables and state to preserve before any destructive reset:

- `evidence_items`
- `evidence_candidates`
- `custody_chain`
- matter-related tables used by legal-support outputs

Why this matters:

- `email_metadata_harvest.db` currently contains the richest SQLite evidence ledger
- `email_metadata_p73.db` currently contains the richest clean dedicated pair
- a naïve clean ingest could reduce the repo to a technically fresh corpus with weaker preserved evidence history than the best current sidecar state
- several high-value tables in SQLite are not raw mailbox data; they represent analytical work product, governance state, or audit trail

High-risk legacy state categories:

- durable evidence:
  - `evidence_items`
- harvest and promotion history:
  - `evidence_candidates`
- governance and human correction state:
  - `matter_review_overrides`
- chain-of-custody and ingest provenance:
  - `custody_chain`
  - `ingestion_runs`
- persisted matter-review work product:
  - `matters`
  - `matter_snapshots`
  - `matter_sources`
  - `matter_exhibits`
  - `matter_chronology_entries`
  - `matter_actors`
  - `matter_witnesses`
  - `matter_comparator_points`
  - `matter_issue_rows`
  - `matter_dashboard_cards`
  - `matter_exports`

Rebuildable without special migration policy:

- `emails`
- `message_segments`
- `attachments`
- `entities`
- language and sentiment analytics
- ingest status helpers
- vector collections and sparse-vector surfaces

Operational consequence:

- a destructive reset against the active SQLite path can erase both mailbox metadata and the higher-level legal-support workspace state
- a Chroma-only reset is less destructive, but it still creates an inconsistent state until vectors are rebuilt
- a clean ingest into a brand-new runtime directory is safe only if the old SQLite state remains preserved until migration decisions are complete

Legacy evidence preservation policy before clean ingest:

- Selected policy: preserve verified evidence plus harvested candidates and custody history.
- Rationale: verified evidence alone is too narrow for later audit reconstruction, while starting from empty evidence tables would discard useful retrieval and custody state that can be preserved without treating it as final proof.
- Migration rule: imported verified evidence remains verified only when its source quote still verifies against the preserved source body; harvested candidates and custody records remain labeled as candidate or provenance state until re-verified after the clean ingest.

## Consolidation Strategy For Existing Databases

This repo can plausibly be reduced to one runtime, but only through an asymmetric process.

Safe:

- selectively merge SQLite state into one new target SQLite
- build one fresh Chroma collection from that target SQLite

Unsafe:

- merging `private/runtime/chromadb` and `private/runtime/chromadb_p73` at the file level
- promoting the richest SQLite-only ledger directly to `current` without a matching dedicated Chroma rebuild
- deleting old SQLite snapshots before the migration policy is executed and verified

### Consolidation Answer

The practical answer to "can the existing databases be migrated to one?" is:

- yes for SQLite
- no for raw Chroma storage
- yes for the overall runtime, if Chroma is rebuilt after SQLite consolidation

### Recommended Interim Consolidation Model

If the project decides to preserve legacy analytical state before the later clean ingest, use this model:

1. create a new target SQLite in a new run directory
2. choose one structural base database
3. overlay high-value donor tables from the richer legacy snapshots
4. deduplicate with table-specific rules
5. rebuild Chroma from the resulting target SQLite
6. keep the old runtime read-only until the merged runtime is validated

### Suggested Base And Donor Roles

Suggested structural base:

- `email_metadata_harvest.db`

Why:

- it currently has the richest SQLite-side evidence state
- all observed SQLite snapshots currently agree on the same email and message-segment counts, which makes a SQLite-first consolidation plausible

Suggested clean paired comparison baseline:

- `chromadb_p73`
- `email_metadata_p73.db`

Why:

- it is the strongest existing clean Chroma plus SQLite pair
- it should remain preserved as the best rollback and comparison reference even if a merged-preclean runtime is produced

### Priority Tables To Preserve Or Merge

Highest priority:

- `evidence_items`
- `custody_chain`
- `matter_review_overrides`
- `matters`
- `matter_snapshots`
- `matter_sources`
- `matter_exhibits`
- `matter_chronology_entries`
- `matter_actors`
- `matter_witnesses`
- `matter_comparator_points`
- `matter_issue_rows`
- `matter_dashboard_cards`
- `matter_exports`

Second priority:

- `evidence_candidates`
- `ingestion_runs`

Usually rebuild rather than merge:

- vector-store contents
- sparse-vector tables
- analytics and entity helper surfaces when they can be regenerated deterministically
- ingest-state helper tables when they no longer reflect the rebuilt vector state

### Table-Level Merge Policy

`evidence_items`:

- do not blindly append every row
- deduplicate by verified quote identity and source email context
- preserve the strongest available version when summaries or notes differ

`evidence_candidates`:

- merge only if historical harvest provenance is considered useful
- use the existing run plus wave plus content-hash uniqueness logic as the main dedupe frame
- acceptable to leave behind if the team treats candidates as regenerable workflow trace rather than durable state

`matter_review_overrides`:

- preserve aggressively
- these rows may contain the most important human corrections and review-state decisions

`matter_snapshots` and `matter_*` tables:

- preserve approved or human-touched snapshots first
- machine-only snapshots may be regenerable, but approved states should not be discarded casually

`custody_chain` and `ingestion_runs`:

- preserve unless the team intentionally decides the clean ingest should start a new audit lineage

### Why Chroma Must Be Rebuilt

The current Chroma directories are not ordinary document folders that can be safely unioned.

Rebuilding is preferred because it:

- ensures vector state matches the final chosen SQLite body and attachment text
- prevents hidden duplication or partial overwrite problems in collection internals
- gives one deterministic collection aligned to the final merged or rebuilt SQLite state

### Decision Boundary

Use interim SQLite consolidation only if at least one of these is true:

- legacy evidence or governance state must be preserved into the eventual canonical runtime
- the richer SQLite-only ledgers contain important state that cannot be responsibly discarded
- the team wants one merged-preclean runtime for comparison before the full clean ingest

Skip interim SQLite consolidation if:

- the project explicitly chooses to preserve old runtimes only as archives
- the team accepts rerunning all evidence-harvest and matter-review workflows from scratch after the clean ingest
- no human-governed or approved analytical state needs to survive into the new canonical runtime

## Remediation Phases

### Phase 0: Freeze And Inventory The Legacy State

Goal:

- stop further ambiguous promotion of multiple runtime artifacts
- capture enough metadata to compare old and new runtimes later

Actions:

- stop the active `src.mcp_server` before moving, relinking, or archiving runtime files
- record a manifest for each existing runtime artifact:
  - path
  - size
  - mtime
  - email count
  - message segment count
  - total chunks where measurable
  - evidence item count
  - evidence candidate count
- record which artifact is:
  - current live MCP pair
  - best legacy pair
  - richest SQLite-only ledger
- export or snapshot the evidence-related tables before any cleanup or reset

Deliverables:

- one runtime inventory note under `docs/agent/`
- one local machine-readable manifest under `private/runtime/runs/` or `private/tests/results/`

Exit criteria:

- no one has to infer runtime importance from filenames or recency alone

### Phase 0A: Decide Whether Interim SQLite Consolidation Is Required

Goal:

- decide whether the team needs one merged-preclean SQLite before the later clean ingest

Actions:

- classify legacy tables into:
  - must preserve
  - nice to preserve
  - safe to regenerate
- decide whether the richer SQLite-only ledgers should feed a merged-preclean runtime
- decide whether old harvest provenance and custody history belong in the future canonical runtime or in archive only

Exit criteria:

- the team explicitly chooses one of these paths:
  - archive-only legacy preservation plus later clean ingest
  - merged-preclean SQLite preservation path plus later clean ingest

### Phase 1: Normalize Legacy Pairs Into Run Directories

Goal:

- wrap the legacy artifacts behind normalized per-run directories without copying terabytes unnecessarily

Actions:

- create `private/runtime/runs/baseline-p73-2026-04-17/`
- materialize the preserved baseline pair there under normalized child names:
  - `chromadb/`
  - `email_metadata.db`
- keep the historical `p73` names as compatibility aliases pointing into the normalized run:
  - `private/runtime/chromadb_p73 -> runs/baseline-p73-2026-04-17/chromadb`
  - `private/runtime/email_metadata_p73.db -> runs/baseline-p73-2026-04-17/email_metadata.db`
- create `manifest.json` describing why this is the best preserved legacy pair
- optionally create `private/runtime/runs/live-default-legacy-2026-04-17/` with symlinks to:
  - `../../chromadb`
  - `../../email_metadata.db`

Rationale:

- this preserves the best pair under the normalized active-run shape while retaining the old `p73` names as compatibility aliases
- it also creates the exact directory shape later required by `current`

Exit criteria:

- the best legacy pair can be addressed through normalized child names

### Phase 2: Introduce The Stable `current` Contract

Goal:

- make all operator tooling resolve through one stable runtime path

Actions:

- create `private/runtime/current` as a symlink to the chosen active run directory
- during the transition period, point `current` either to:
  - the preserved legacy live pair if zero behavior change is required immediately
  - or the preserved `baseline-p73` pair if the team explicitly wants the best legacy paired state as the temporary active baseline
- do not point `current` at `email_metadata_harvest.db`, `finalrun`, or `rerun` directly because there is no clean matching dedicated Chroma directory for those snapshots

Recommendation:

- do not treat this as the final cutover
- use `current` first as the abstraction layer
- repoint `current` to the future clean-ingest run only after that run passes verification

Exit criteria:

- a single stable path exists for active runtime resolution:
  - `private/runtime/current/chromadb`
  - `private/runtime/current/email_metadata.db`

### Phase 3: Unify MCP And CLI Path Resolution

Goal:

- make MCP and CLI consume the same runtime path contract

Actions:

- change the MCP client config from:
  - `private/runtime/chromadb`
  - `private/runtime/email_metadata.db`
- to:
  - `private/runtime/current/chromadb`
  - `private/runtime/current/email_metadata.db`
- keep CLI examples explicit:
  - `--chromadb-path private/runtime/current/chromadb`
  - `--sqlite-path private/runtime/current/email_metadata.db`
- add or plan a repo-local launcher for operator use, for example:
  - a shell snippet that exports `CHROMADB_PATH` and `SQLITE_PATH`
  - or a small wrapper script used only for local private-runtime execution

Policy:

- do not rely on implicit CLI defaults for the sensitive local runtime
- the tracked generic defaults in `src/config.py` may remain generic, but operator docs for this matter must always show explicit private-runtime paths

Exit criteria:

- MCP and CLI target the same active runtime without hidden divergence

### Phase 3A: Optional Interim SQLite Consolidation And Chroma Rebuild

Goal:

- produce one interim merged runtime when preservation requirements justify it

Actions:

- create `private/runtime/runs/merged-preclean-<date>/`
- build one target SQLite there, using the chosen base and donor policy
- preserve the old legacy runtimes read-only during consolidation
- rebuild a fresh Chroma collection for the merged-preclean target SQLite
- verify that the merged-preclean runtime is internally coherent before it is ever considered for `current`

Required checks:

- email count parity with the known corpus baseline
- message-segment parity with the known corpus baseline
- evidence-item count and category audit
- matter-snapshot and override presence audit
- one explicit search probe
- one evidence lookup probe

Exit criteria:

- one internally coherent merged-preclean runtime exists, or the team explicitly skips this phase and documents why

### Phase 4: Execute A Clean New Ingest Run

Goal:

- create the first actually canonical runtime under the normalized run layout

Actions:

- create a new run directory, for example:
  - `private/runtime/runs/clean-ingest-<YYYY-MM-DD>/`
- ingest the current `.olm` export into that directory using explicit paths
- enable the intended enrichment features during the clean build according to the current repo contract
- verify the new runtime on:
  - email count
  - chunk count
  - language coverage
  - entity coverage
  - attachment extraction coverage
  - evidence workflow operability

Required comparison baselines:

- compare the clean ingest against the preserved `baseline-p73` pair
- compare evidence-bearing SQLite state against the preserved `harvest` ledger before discarding anything

Exit criteria:

- one fresh run exists with normalized runtime paths and verifiable corpus quality

### Phase 5: Promote The Clean Ingest To `current`

Goal:

- make the clean rebuild the only active runtime contract

Actions:

- repoint `private/runtime/current` from the temporary legacy baseline to the clean-ingest run
- fully restart the MCP client after the MCP config points at `current`
- rerun runtime verification through both MCP and CLI

Required verification:

- MCP:
  - `email_admin(action='diagnostics')`
  - `email_stats`
  - `email_quality(check='languages')`
- CLI:
  - `python -m src.cli --chromadb-path private/runtime/current/chromadb --sqlite-path private/runtime/current/email_metadata.db analytics stats`
  - `python -m src.cli --chromadb-path private/runtime/current/chromadb --sqlite-path private/runtime/current/email_metadata.db evidence stats`
- surface:
  - one known search query
  - one evidence lookup
  - one legal-support or case-analysis smoke path

Exit criteria:

- MCP client and local CLI both resolve through `current` and observe the same corpus state

### Phase 6: Archive Or Remove Legacy Top-Level Artifacts

Goal:

- remove the runtime ambiguity from the filesystem itself

Actions:

- move unused top-level legacy artifacts into `private/runtime/archive/legacy-top-level/`
- keep the richer SQLite ledgers only if they still serve one of these functions:
  - evidence migration source
  - audit comparison source
  - rollback source
- once their role is complete, archive them away from the active root

Do not delete yet:

- any legacy SQLite file that still holds evidence or custody state not reproduced elsewhere
- any legacy pair still needed for rollback or comparison during the clean-ingest validation phase

Success condition:

- the active root no longer contains multiple equally plausible runtime choices

## Documentation Update Plan

Docs that should be updated when the implementation phase starts:

- `docs/agent/mcp_client_config_snippet.md`
  - switch examples to `private/runtime/current/...`
- `docs/agent/email_matter_analysis_single_source_of_truth.md`
  - switch MCP and CLI runtime examples to `current`
  - make explicit that the private runtime contract is path-stable while the run target may change
- `private/tests/REAL_DATA_VALIDATION_PLAN.md`
  - switch validation examples to `current`
- `private/tests/results/01_corpus_inventory/*runtime_verification*.md`
  - future checkpoints should record `current/...`, not top-level legacy names
- `docs/README.md`
  - link this remediation plan from the autonomous execution runbooks section

Docs that should not be rewritten as private-runtime defaults:

- public generic examples in `README.md` that intentionally describe the sanitized `data/` defaults for broad usage

## Verification Gates For The Remediation Itself

The remediation is complete only when all of the following are true:

1. there is exactly one operator-facing active runtime contract:
   - `private/runtime/current/chromadb`
   - `private/runtime/current/email_metadata.db`
2. MCP client config points to `current`, not to a versioned path
3. operator CLI examples for the private runtime always use explicit path flags or an explicit launcher
4. the clean-ingest run has been verified against the preserved best legacy baseline
5. the stronger legacy evidence state has either been migrated, intentionally discarded by policy, or archived with a written justification
6. the active runtime root no longer presents multiple top-level candidate databases as equally active

## Recommended Implementation Order

Recommended execution order for a future implementation pass:

1. freeze and inventory current runtime artifacts
2. decide whether interim SQLite consolidation is required
3. preserve the best legacy pair as `baseline-p73`
4. preserve the richer SQLite-only ledgers for evidence migration review
5. introduce the `current` symlink abstraction
6. update MCP and CLI operator docs to `current`
7. if needed, build the merged-preclean SQLite plus rebuilt Chroma runtime
8. perform the clean new ingest into a fresh normalized run directory
9. verify the clean run against the preserved legacy baseline
10. repoint `current` to the clean run
11. archive obsolete top-level legacy artifacts

## Final Recommendation

Use the `current` indirection layer, but do not confuse that with blessing an old runtime as the final corpus.

The correct stance is:

- preserve `chromadb_p73` plus `email_metadata_p73.db` as the best existing legacy pair
- preserve `email_metadata_harvest.db` as the richest SQLite evidence ledger until migration policy is decided
- if the project wants one interim consolidated legacy runtime, merge SQLite selectively and rebuild Chroma instead of trying to merge Chroma storage files
- build a clean new ingest run under `private/runtime/runs/<run-id>/`
- only then let `private/runtime/current` become the stable long-term contract for both MCP and CLI
