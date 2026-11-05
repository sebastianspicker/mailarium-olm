# Architecture

Mailarium is one Python distribution organized as a modular monolith. It
constructs and investigates one local mailbox archive at a time. SQLite owns
canonical application state; USearch, BM25, sparse, and other retrieval indexes
are rebuildable acceleration. Optional EWS support projects selected remote
items into the same archive rather than maintaining a second source of truth.

New to the code? Read [System context](#system-context), then
[Search a query](#user-journey-search-the-archive), then the
[Components](#components) table as the code map.

## System context

What runs, and what does it read and write? Everything below runs in local
Python processes on the operator's machine; only EWS is remote.

```mermaid
flowchart LR
    OLM["Outlook .olm file"]
    EWS["On-premises EWS"]
    subgraph proc [Local Python process]
        Ingest["mailarium-ingest"]
        subgraph ifaces [Interfaces]
            CLI["mailarium CLI"]
            MCP["stdio MCP server"]
            Web["Streamlit app"]
        end
        Runtime["ApplicationRuntime"]
        Search["SearchEngine"]
        Investigation["investigation"]
        Mailbox["MailboxService"]
    end
    SQLite[("SQLite archive")]
    Derived[("Derived indexes")]

    OLM -->|parse records| Ingest
    Ingest -->|"INSERT messages, vectors"| SQLite
    Ingest -.->|rebuild accelerator| Derived
    ifaces -->|compose once| Runtime
    Runtime --> Search
    Runtime --> Mailbox
    ifaces -->|"reports, evidence"| Investigation
    Investigation -->|ranked chunks| Search
    Search -->|"query USearch, BM25"| Derived
    Search -->|SELECT| SQLite
    Mailbox <-->|"SOAP over HTTPS"| EWS
    Mailbox -->|project via ingestion| SQLite

    classDef focus fill:#fde68a,stroke:#b45309,color:#1f2937
    class SQLite focus
```

SQLite is highlighted because it is the only source of truth: `Derived`
indexes can be deleted and rebuilt from it. The three interfaces are
independently started processes over the same feature packages; each builds
its own `ApplicationRuntime`, and none is a separately deployed service.
`Investigation` reads the archive directly as well as through `SearchEngine`
(edge omitted for readability). The files in `demo/` are a dependency-free
interface demonstration and never connect to Mailarium, a mailbox, or a
runtime archive.

Where in the code:
[mailarium/interfaces/runtime.py](../mailarium/interfaces/runtime.py),
[mailarium/interfaces/cli/main.py](../mailarium/interfaces/cli/main.py),
[mailarium/interfaces/cli/ingest.py](../mailarium/interfaces/cli/ingest.py),
[mailarium/interfaces/mcp/server.py](../mailarium/interfaces/mcp/server.py),
[mailarium/interfaces/web/app.py](../mailarium/interfaces/web/app.py).

## Components

| Component | Responsibility |
| --- | --- |
| `mailarium/platform/` | Dependency leaf. `settings.py` holds all Mailarium-owned configuration, runtime profiles, and environment parsing helpers; `repo_paths.py` resolves runtime, output, and local-read roots; `validation.py` and `sanitization.py` hold input checks and output sanitization. |
| `mailarium/model/` | Presentation-neutral messages, attachments, chunks, body normalization, thread inference, and other value objects. |
| `mailarium/archive/` | The only SQLite owner. `ArchiveDatabase` (`database.py`) owns one `ArchiveSession` (`session.py`: connection plus one re-entrant operation lock) and exposes focused repositories under `repositories/` (messages, queries, attachments, evidence, custody, ingest ledger, entities, events, analytics, sparse, vector maintenance, diagnostics, mailbox-source visibility, and `mailbox` for accounts, sources, and proposals). `locking.py` serializes every public repository operation; `schema/` holds tables, migrations, and mailbox tables; `vectors.py` holds canonical vector rows with a rebuildable USearch accelerator; `visibility.py` holds default-retrieval visibility rules. |
| `mailarium/retrieval/` | `SearchEngine` (`retriever.py`) composed from collaborators: query encoding, dense, image, and semantic search, sparse/BM25 retrieval and hybrid fusion (`hybrid.py`), reranking, semantic filters, query expansion, filtered search, visibility, archive summary, diagnostics, and threads. Embedders, index modules, and training helpers live alongside. |
| `mailarium/ingestion/` | OLM parsing (`olm/`), attachment extraction and reprocessing (`attachments/`), entity, event, language, and sentiment enrichment (`enrichment/`), chunking, the ingest/embed pipeline, bounded maintenance, re-embedding, and reset jobs, and EWS record projection (`mailbox_ingest.py`). `api.py` and `context.py` expose the production facades and `ProductionIngestDependencies`; package exports are lazy. |
| `mailarium/investigation/` | Answer-context assembly (`answer_context/`, split by responsibility: lanes, ranking, candidates, provenance, packing, rendering, workflow, and related modules), evidence and HTML exports, reports and dossiers (templates under `templates/`), network, temporal, thread, topic, deduplication, and writing analysis. |
| `mailarium/mailbox/` | `MailboxService` (`service.py`) composes account configuration (`accounts.py`), selected-folder sync (`sync.py`), immutable proposals (`proposals.py`, `ProposalPolicy`), and controlled execution (`execution.py`, `ProposalExecutor`); `policy.py` holds process gates and limits; `ews/` is the bounded HTTPS SOAP transport. |
| `mailarium/interfaces/` | `runtime.py` (`ApplicationRuntime`, long-lived composition); `presentation.py` (result serialization shared by CLI and MCP); `cli/` (entry points, parser, dependencies, and command families under `cli/commands/`); `mcp/` (server, runtime state, instance lock, input models under `mcp/models/`, tools under `mcp/tools/`); `web/` (Streamlit app and pages). |
| Root modules | `cli.py`, `ingest.py`, `mcp_server.py`, `__main__.py`, and `web_app.py` are launchers for the documented invocations and import only `mailarium.interfaces`. |
| `scripts/` | Architecture policy, verification profiles, coverage floors, smokes, operations helpers, and release tooling, including the publication privacy scanner under `scripts/release/privacy/` (not part of the wheel). |

## Dependency direction

`PACKAGE_DEPENDENCIES` and `ROOT_MODULE_DEPENDENCIES` in
`scripts/check_architecture.py` are the executable, complete allow-list. Any
new package or cross-package import must extend it deliberately. The same
script rejects import cycles between packages and between modules, including
inside one package.

```mermaid
flowchart TD
    Entry["Root launchers"] --> Interfaces["interfaces"]
    Interfaces --> Mailbox["mailbox"]
    Interfaces --> Ingestion["ingestion"]
    Interfaces --> Investigation["investigation"]
    Interfaces --> Retrieval["retrieval"]
    Interfaces --> Archive["archive"]

    Mailbox --> Ingestion
    Mailbox --> Archive

    Ingestion --> Retrieval
    Ingestion --> Archive

    Investigation --> Retrieval
    Investigation --> Archive

    Retrieval --> Archive
    Archive --> Model["model"]
    Platform["platform"]
```

Every package except `archive`, `model`, and `platform` may also import
`model` and `platform` directly; `archive` imports only `model`. Important
negative rules:

- `platform` and `model` import nothing else from `mailarium`.
- `archive` does not import retrieval, ingestion, investigation, mailbox, or
  platform.
- `retrieval` does not import ingestion, investigation, or mailbox.
- `ingestion` does not import investigation.
- `mailbox` does not import retrieval.
- investigation and mailbox do not import one another.
- no feature package imports `interfaces` or a root module; root modules import
  only `interfaces`.
- SQL stays inside `archive`.

Run `uv run python scripts/check_architecture.py` whenever imports, package
ownership, or a root module changes.

## Runtime and data flows

### Long-lived interfaces

`ApplicationRuntime` lazily owns one `ArchiveDatabase`, one
`SearchEngine`, and one `MailboxService` for a validated runtime path pair.
The search engine and mailbox service receive the runtime-owned archive; the
mailbox service persists through the archive's `mailbox` repository on the same
connection and operation lock. Neither opens fallback connections. Shutdown
closes mailbox and derived search resources before closing SQLite.

`mailarium/interfaces/web/app.py` (launched through `mailarium/web_app.py`)
maintains one Streamlit `st.cache_resource` runtime
per validated path pair. Search receives its `SearchEngine`; overview, people,
connections, and evidence receive its archive; mailbox receives its mailbox
service. Page modules never create parallel resources. Cache invalidation must
close existing runtimes before clearing the Streamlit cache.

The MCP server constructs the same runtime and holds an exclusive,
stale-process-aware lock for its configured archive. The CLI constructs a
runtime only for the selected command.

### OLM ingestion

What happens when the operator runs `mailarium-ingest archive.olm`?

```mermaid
sequenceDiagram
    autonumber
    actor U as Operator
    participant CLI as mailarium-ingest
    participant Orch as orchestration.ingest
    participant Parser as OLM parser
    participant Pipeline as embed pipeline
    participant DB as SQLite archive
    participant Index as Derived indexes

    U->>CLI: mailarium-ingest archive.olm
    CLI->>Orch: ingest_archive(...)
    Orch->>DB: open caller-owned archive
    loop each bounded batch
        Orch->>Parser: next parsed message
        Parser-->>Orch: ParsedMessage + attachments
        Orch->>Pipeline: submit batch
        Pipeline->>DB: INSERT messages, chunks, vectors
    end
    Pipeline-)Index: rebuild USearch once per space
    Orch->>DB: checkpoint and close
    Orch-->>CLI: result summary
```

Steps 4–7 repeat per batch; `--incremental` skips messages the ingest ledger
already marks complete. Step 8 happens once per changed embedding space at
the end of the job, so an interrupted ingest leaves committed SQLite rows and
a stale accelerator; queries then fall back to the canonical vectors (see
below).

Where in the code:
[mailarium/interfaces/cli/ingest.py](../mailarium/interfaces/cli/ingest.py)
(`_run_ingest_command`),
[mailarium/ingestion/orchestration.py](../mailarium/ingestion/orchestration.py)
(`ingest`, `_run_ingest_parser`),
[mailarium/ingestion/olm/parser.py](../mailarium/ingestion/olm/parser.py),
[mailarium/ingestion/ingest_embed_pipeline.py](../mailarium/ingestion/ingest_embed_pipeline.py),
[mailarium/archive/vectors.py](../mailarium/archive/vectors.py).

Ingestion and maintenance are bounded jobs. They open one caller-owned archive
through `mailarium.archive.open_archive_database`, inject it into embedding
and vector storage, and close it at job completion. Incremental ingest skips
already committed source records; re-embedding rebuilds derived vector state
from stored corrected text.

Vector storage is `SQLiteVectorCollection` (`mailarium/archive/vectors.py`):
SQLite vector rows are canonical and the USearch file is a rebuildable
accelerator, both governed by one atomic checkpoint protocol. The embedding
consumer defers accelerator checkpoints until its bounded job
finishes. Vector rows and retry state still commit to SQLite during the job;
the derived index is rebuilt once per changed embedding space at scope exit.
Nested checkpoint scopes share that boundary. Queries with pending operations
use canonical vectors when an accelerator cannot yet be refreshed.

### Retrieval and investigation

Retrieval reads canonical records, obtains candidates from the indexes
available under the current runtime profile, combines their scores, applies
filters, and returns ranked chunks. Investigation consumes stored archive
records and retrieval results to produce evidence and derived analyses.
Answer-context assembly exposes ambiguity and insufficient-evidence states
instead of converting a ranking into proof.

### User journey: search the archive

What happens when the operator runs `mailarium search "project handoff" --hybrid`?
The MCP search tools and the Streamlit search page reach the same
`SearchEngine.execute` call.

```mermaid
sequenceDiagram
    autonumber
    actor U as Operator
    participant CLI as mailarium CLI
    participant Engine as SearchEngine
    participant FS as FilteredSearch
    participant Hybrid as HybridFusion
    participant Store as Vector store

    U->>CLI: mailarium search "..." --hybrid
    CLI->>Engine: search_filtered(query, filters)
    Engine->>FS: execute(SearchRequest)
    FS->>Store: dense top-k for query embedding
    Store-->>FS: candidate chunks
    opt hybrid enabled
        FS->>Hybrid: merge(query, candidates)
        Hybrid-->>FS: weighted RRF of dense + sparse or BM25
    end
    FS->>FS: visibility, filters, one hit per email
    opt rerank enabled
        FS->>FS: ResultReranker.rerank
    end
    FS-->>CLI: SearchResponse
    CLI-->>U: Rich table or JSON
```

Step 2 is the only place the CLI touches retrieval; `ApplicationRuntime`
built the `SearchEngine` before the command ran. If steps 4–9 leave fewer
than `top_k` emails (filters and per-email deduplication drop candidates),
`FilteredSearch` doubles the fetch size and repeats, up to a fixed ceiling.
`HybridFusion` prefers learned sparse vectors and falls back to BM25; if
keyword retrieval fails it returns the dense results unchanged.

Where in the code:
[mailarium/interfaces/cli/commands/search.py](../mailarium/interfaces/cli/commands/search.py)
(`run`, `run_query`),
[mailarium/retrieval/retriever.py](../mailarium/retrieval/retriever.py)
(`SearchEngine.search_filtered`),
[mailarium/retrieval/filtered_search.py](../mailarium/retrieval/filtered_search.py)
(`_execute`, `_collect_candidates`, `_post_process_candidates`),
[mailarium/retrieval/hybrid.py](../mailarium/retrieval/hybrid.py)
(`HybridFusion.merge`),
[mailarium/retrieval/dense.py](../mailarium/retrieval/dense.py),
[mailarium/retrieval/reranking.py](../mailarium/retrieval/reranking.py).

Vector storage caches metadata snapshots against the connection's change count
and SQLite's external-commit version. Warm queries reuse verified index files
while their identity, size, timestamps, and expected checksum remain unchanged;
explicit verification still hashes the complete file. Answer-context assembly
batches archive lookups across candidates and reuses provenance within one
request.

### EWS synchronization and actions

EWS synchronization requires both process and account read gates. It fetches
bounded deltas only from selected folders, maps them to normalized mailbox
records, and projects them through the ingestion boundary into the canonical
archive. Attachment content has a separate process gate and per-sync flag.

Synchronization and proposal operations reuse one transport session within
their operation scope and close it afterward. Projection batches contain at
most 100 distinct source identities. Canonical rows and durable pending markers
commit together before vector work; source hashes are finalized together only
after indexing and its checkpoint succeed. A repeated source identity starts a
new batch, preserving event order. Failed projection leaves retry markers and
does not advance the folder cursor. Obsolete vectors are selected by message
UID rather than scanning all indexed IDs.

Writes require process and account write gates plus an approved immutable
proposal. Approval and rejection are local interactive CLI operations.
Execution claims the proposal, validates the expected remote item state and
change key, calls the EWS gateway, and records or reconciles the outcome. It
does not silently rebase a stale proposal.

Which states does a write proposal go through?

```mermaid
stateDiagram-v2
    [*] --> pending: create_proposal
    pending --> approved: approve (CLI)
    pending --> rejected: reject (CLI)
    approved --> rejected: reject (CLI)
    pending --> expired: deadline passed
    approved --> executing: claim_execution
    retryable --> executing: claim_execution
    approved --> conflicted: remote item changed
    executing --> succeeded
    executing --> retryable
    executing --> failed
    executing --> conflicted
    executing --> uncertain: outcome unknown or lease expired
    uncertain --> succeeded: reconcile
    uncertain --> failed: operator resolves
    uncertain --> conflicted
    expired --> pending: same proposal re-created
    failed --> pending: same proposal re-created
    conflicted --> pending: same proposal re-created
    succeeded --> [*]
    rejected --> [*]
```

Only `approved` and `retryable` proposals can be claimed, and a claim moves
the proposal to `executing` inside one SQLite write so two processes cannot
execute it twice. `uncertain` exists because a network failure after the EWS
call leaves the remote result unknown; it is reconciled against the remote
item or resolved by the operator, never retried blindly. Re-creating a
proposal with the same digest reopens an `expired`, `failed` or `conflicted`
row instead of inserting a duplicate.

Where in the code:
[mailarium/model/mailbox_models.py](../mailarium/model/mailbox_models.py)
(`ProposalState`),
[mailarium/archive/repositories/mailbox/proposals.py](../mailarium/archive/repositories/mailbox/proposals.py)
(transitions),
[mailarium/mailbox/execution.py](../mailarium/mailbox/execution.py)
(`ProposalExecutor`).

## State ownership and recovery

- The original `.olm` is the external recovery source for archive imports.
- SQLite owns messages, metadata, source mappings, vectors, evidence, custody,
  mailbox configuration, synchronization state, and proposals.
- Retrieval directories and indexes are derived. They may be reset and rebuilt
  without redefining archive truth.
- Credentials remain in externally named environment variables. SQLite stores
  credential reference names, not values.
- Exports are derived disclosure artifacts. They must remain inside allowed
  output roots, never overwrite an existing path, and require review before
  sharing.

### Data model

How are the main tables related? This shows the core of about 40 tables;
analytics, topic, keyword, and ingest-bookkeeping tables hang off `emails`
the same way.

```mermaid
erDiagram
    emails ||--o{ attachments : "email_uid"
    emails ||--o{ message_segments : "email_uid"
    emails ||--o{ entity_mentions : "email_uid"
    entities ||--o{ entity_mentions : "entity_id"
    emails ||--o{ evidence_items : "email_uid"
    emails ||..o{ vector_chunks : "email_uid (no FK)"
    vector_chunks ||--o| dense_vectors : "vector_id"
    mailbox_accounts ||--o{ mailbox_folders : "account_id"
    mailbox_folders ||--o{ email_sources : "folder_id"
    email_sources }o..|| emails : "canonical_email_uid"
    mailbox_folders ||--o{ mailbox_action_proposals : "folder_id"
```

`emails.uid` is the key nearly everything joins on. Vectors link to emails
only by value (dotted), because a vector row belongs to an embedding space
and is deleted and rebuilt independently of the message. EWS items never get
their own message table: an `email_sources` row maps a remote item to the
same `emails` row an OLM import would create.

Where in the code:
[mailarium/archive/schema/tables.py](../mailarium/archive/schema/tables.py),
[mailarium/archive/schema/mailbox.py](../mailarium/archive/schema/mailbox.py),
[mailarium/archive/schema/migrations.py](../mailarium/archive/schema/migrations.py).

Back up both the original source and SQLite before destructive maintenance.
The repository does not provide automated backup, retention, encryption at
rest, or disaster-recovery orchestration.

## Configuration and trust boundaries

All Mailarium-owned configuration is defined in
`mailarium/platform/settings.py`. The CLI, ingest, and MCP `main()` functions
load `.env` when they start, without replacing variables already present in
the process; importing those modules does not load it. Streamlit does not load
`.env`; it uses its process environment and optional validated sidebar path
overrides. Explicit environment values override runtime and MCP profile
defaults, which in turn override dataclass defaults. Runtime and export paths
are resolved by `mailarium/platform/repo_paths.py` and checked against
purpose-specific roots.

OLM, XML, MIME, and attachment content are untrusted input. EWS accepts only an
explicit HTTPS endpoint without embedded credentials. SOAP bodies, credential
values, and synchronization watermarks must not appear in responses or
diagnostics. Streamlit and MCP provide no public-network authentication or
authorization; deployment controls are outside the application.

Model and entity-extraction weights can contact their upstream model sources
unless local-only and no-download settings are selected. Mailarium has no
hosted inference integration and performs no online training on mailbox
content or queries.

## Where new code belongs

- Configuration values, environment parsing, and path roots: `platform/`.
- Value objects shared by several packages, and pure message-content semantics
  such as header and body parsing, normalization, and thread inference:
  `model/`.
- Any SQL, schema change, or migration: a repository or `schema/` in
  `archive/`, exposed through `ArchiveDatabase`.
- Index, embedding, or ranking behavior: a `retrieval/` collaborator composed
  by `SearchEngine`.
- Parsing, extraction, enrichment, or archive-construction jobs: `ingestion/`.
- Analysis, evidence, export, report, or answer-context behavior:
  `investigation/`.
- EWS account, sync, proposal, or execution behavior: `mailbox/`; SOAP
  transport: `mailbox/ews/`.
- Argument parsing, MCP tool schemas, page rendering, and output formatting:
  the matching adapter in `interfaces/`. Keep root modules as launchers.

## Build, verification, and deployment boundaries

Mailarium builds one wheel and one source archive from `pyproject.toml`. The
wheel contains `mailarium*` packages and the investigation HTML templates; it
does not contain `scripts/`.

`scripts/verify.py` owns the verification profiles:

- `fast`: lockfile check, Ruff lint and format check, architecture policy
  (package allow-list and package/module import-cycle checks).
- `pr`: the static `fast` checks, mypy, offline and native-storage ingest
  smokes, Bandit, dependency audit, and the publication privacy scan.
- `package`: Streamlit AppTest smoke, build, locked requirements export,
  artifact inspection, and installed-wheel smoke.
- `release`: `pr` followed by `package`. It validates and installs local
  artifacts but does not publish them.

Which of these run in GitHub Actions, and when?

```mermaid
flowchart LR
    dispatch["Manual dispatch<br/>or Dependabot PR"]
    push["Push or PR to main,<br/>weekly cron"]
    manual["Manual dispatch on main"]
    subgraph ci [ci.yml]
        pr["verify.py pr"]
        pkg["verify.py package"]
        mac["verify.py release<br/>macOS 14 arm64"]
    end
    subgraph sec [security.yml]
        audit["dependency_audit.py<br/>+ Bandit"]
    end
    subgraph pages [pages-demo.yml]
        smoke["pages_demo.py smoke"]
        deploy["Deploy demo/ to Pages"]
    end
    dispatch --> pr
    dispatch --> pkg
    dispatch --> mac
    push --> audit
    manual --> smoke -->|artifact| deploy
```

General CI does not run on every contributor PR; it runs on manual dispatch
and Dependabot PRs only, so run `scripts/verify.py pr` locally before
proposing a change. Only `pages-demo.yml` deploys anything, and what it
deploys is the static synthetic `demo/`, never the application. No workflow
publishes a package.

Where in the code:
[.github/workflows/ci.yml](../.github/workflows/ci.yml),
[.github/workflows/security.yml](../.github/workflows/security.yml),
[.github/workflows/pages-demo.yml](../.github/workflows/pages-demo.yml),
[scripts/verify.py](../scripts/verify.py).

The Streamlit application is a local process. The static `demo/` can be
served directly or published by its Pages workflow, but that deployment is
only a synthetic demonstration. The repository contains no supported hosted
Mailarium deployment, migration service, public API gateway, authentication
layer, or operational database service.

No local profile proves live EWS interoperability, real model downloads, a
manual browser session, remote CI, a Pages deployment, or package publication.
