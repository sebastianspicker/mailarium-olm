# Architecture

Mailarium is a modular monolith for one local mailbox archive at a time. It
keeps canonical archive data in SQLite and treats USearch files as derived
acceleration. An Outlook `.olm` archive is the recovery source. Optional EWS
support is a bounded source and action adapter, not a second archive database.

## Composition

```text
CLI, MCP, Streamlit              ingest and maintenance jobs
        |                                   |
ApplicationRuntime                 open_archive_database
        |                                   |
  retrieval  investigation  mailbox       ingestion
      |           |            |          /    |    \
  archive      retrieval    ingestion  archive model retrieval
   model        archive      retrieval
                             archive + EWS
```

`ApplicationRuntime` owns the shared SQLite connection, search engine, and
mailbox service for validated archive paths. It closes derived search resources
before the canonical database. Interfaces receive services through this
composition boundary and do not own their lifecycle. The public Streamlit
entrypoint, `mailarium/web_app.py`, maintains one `st.cache_resource` runtime
per validated path pair; pages receive that runtime's database, search engine,
or mailbox service and never construct parallel resources.

Ingestion and maintenance are bounded jobs rather than long-lived interface
sessions. They open one caller-owned archive through
`mailarium.archive.open_archive_database`, inject it into embedding and vector
storage, and close it at job completion. `SearchEngine`, `EmailEmbedder`, and
`SQLiteVectorCollection` never create fallback database connections.

## Packages

| Package | Responsibility |
| --- | --- |
| `model` | Message, attachment, chunk, scope, and normalization value objects. |
| `archive` | SQLite connection, schema, repositories, persistence, provenance, and source mappings. |
| `ingestion` | OLM parsing, content extraction, chunking, reprocessing, and archive writes. |
| `retrieval` | Embeddings, BM25 and optional sparse indexes, vector lookup, ranking, filters, and index lifecycle. |
| `investigation` | Evidence, reports, exports, entity, network, temporal, language, topic, and thread analysis. |
| `mailbox` | Non-secret EWS account configuration, selected folders, synchronization, proposals, and controlled execution. |
| `interfaces` | CLI, MCP, and Streamlit adapters. |
| `platform` | Runtime paths, validation, and sanitization. |
| `privacy` | Git-aware publication scanning and private-artifact detection. |

## Data flow

OLM ingestion parses and normalizes messages and selected attachments, then
writes canonical records and vectors to SQLite. Retrieval reads those records,
combines available ranking channels, and returns ranked candidates. Investigation
uses stored records to produce evidence and derived analysis. Exports remain
inside configured output roots and do not overwrite existing files.

EWS synchronization is allowed only for an explicitly configured HTTPS endpoint
and selected folders. It maps remote items into the same archive model. EWS
actions use immutable proposals: a local interactive CLI approval precedes
execution, and expected item state is checked rather than silently rebased.

## Dependency direction

Feature packages never import interfaces or application entry points. The
enforced package rules are in `scripts/check_architecture.py`:

- `model` does not depend on archive, ingestion, retrieval, investigation, or
  mailbox.
- `archive` does not depend on ingestion, retrieval, investigation, or mailbox.
- `retrieval` does not depend on ingestion, investigation, or mailbox.
- `investigation` and `mailbox` do not depend on one another.
- ingestion may invoke retrieval and investigation processors while building
  the archive; mailbox may invoke ingestion when projecting synchronized
  records into that same archive.
- interfaces and runtime composition may depend on feature packages.

Run `python scripts/check_architecture.py` whenever imports or package ownership
change.

## Verification boundary

`python scripts/verify.py fast` is the deterministic architecture, style, and
contract gate. `pr` adds the complete test tree, independent branch-coverage
floors for critical modules, a native SQLite/USearch ingestion round trip,
typing, offline parser orchestration, security, dependency, and privacy checks.
`release` adds build, artifact, installed-wheel, and Streamlit AppTest smoke
checks. The AppTest smoke executes the app body, rejects app exceptions, and
asserts that the initial search screen is visible for both source and
installed-wheel paths. None of these profiles proves live EWS connectivity,
real model loading, a manual browser session, or remote CI.
