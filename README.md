# Mailarium

**Local Outlook OLM archive search with optional Exchange EWS integration.**

Mailarium is a local-first mailbox investigation tool for Outlook `.olm`
archives. It normalizes messages and selected attachments into a local SQLite
archive, builds rebuildable search acceleration, and exposes the same archive
through CLI, MCP, and trusted-local Streamlit interfaces.

Mailarium is alpha software. Commands, storage details, and defaults can change
within the `0.5.x` line.

## Capabilities and limits

Mailarium supports:

- bounded and incremental `.olm` ingestion;
- lexical, dense, hybrid, and optional reranked retrieval;
- message, thread, entity, attachment, relationship, and temporal analysis;
- evidence collections, archive reports, and allowlisted exports;
- optional synchronization of selected on-premises EWS folders; and
- proposal-gated EWS actions with local interactive approval.

The operating boundaries are deliberate:

- SQLite is the canonical archive. USearch, BM25, sparse, and other retrieval
  indexes are derived and may be rebuilt.
- The original `.olm` remains the recovery source. Rankings, OCR, extracted
  entities, and generated summaries must be checked against source material.
- Streamlit and MCP are trusted-local interfaces, not authenticated public
  services.
- EWS reads, writes, and attachment content are separate, disabled-by-default
  opt-ins against one explicitly configured HTTPS endpoint.
- Model weights may be downloaded on first use unless local-only settings are
  selected. Mailarium does not send mailbox content to a hosted model service.

Mailarium is not a hosted mailbox service, an Outlook replacement, or a legal
case or matter management system.

## Requirements

- Python `>=3.14.6,<3.15`
- macOS 14 or later on Apple Silicon for the documented operator runtime
- Enough disk space for the source archive, SQLite database, model cache, and
  derived indexes

## Quick start

Run these commands from the repository root:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
cp .env.example .env
mkdir -p private/ingest private/runtime/current private/exports
mailarium-ingest private/ingest/archive.olm --max-emails 200
mailarium search "project handoff" --hybrid
```

Place the real archive at `private/ingest/archive.olm` or substitute another
allowed local path. The tracked `.env.example` uses source-checkout runtime
paths below `private/`. Keep archives, databases, exports, model artifacts, and
credentials out of version control.

For deterministic offline ingestion, pre-seed the required models and set both
spaCy download controls:

```dotenv
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
SPACY_AUTO_DOWNLOAD_DURING_INGEST=0
SPACY_AUTO_DOWNLOAD=0
```

See [operations](docs/OPERATIONS.md) for path rules, configuration precedence,
maintenance, backups, EWS readiness, and troubleshooting.

## Interfaces

The installed terminal entry points are `mailarium` and `mailarium-ingest`.
Use their live help for the exact command schema:

```bash
mailarium --help
mailarium-ingest --help
mailarium mailbox --help
```

Common archive commands include:

```bash
mailarium browse --page 1 --page-size 20
mailarium analytics stats
mailarium export report --output private/exports/report.html
```

Start the stdio MCP server with the environment interpreter:

```bash
.venv/bin/python -m mailarium.mcp_server
```

Streamlit does not load `.env` itself. Export its runtime variables or pass
them in the launch environment, and bind only to a trusted local interface:

```bash
VECTOR_INDEX_PATH=private/runtime/current/vector-index \
SQLITE_PATH=private/runtime/current/email_metadata.db \
python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1
```

The source module forms are `python -m mailarium.cli`,
`python -m mailarium.ingest`, and `python -m mailarium.mcp_server`.
`python -m mailarium` also starts the MCP server.

## Public synthetic demo

The prepared GitHub Pages URL is
[https://sebastianspicker.github.io/mailarium/](https://sebastianspicker.github.io/mailarium/).
It is a static, synthetic demonstration only: it has no mailbox, archive,
credentials, runtime paths, or network connection, and it is not a deployed
Mailarium instance. Preview it locally without installing dependencies:

```bash
python3 -m http.server --directory demo 8000
```

Then open <http://localhost:8000>.

## Repository structure

Mailarium is one Python distribution and one modular monolith. Its interfaces
are independently started, but they are not separately published packages.

| Path | Responsibility | Independent surface |
| --- | --- | --- |
| `mailarium/model/` | Shared messages, attachments, chunks, scopes, and value objects | No |
| `mailarium/archive/` | Canonical SQLite schema, repositories, provenance, and source mappings | No |
| `mailarium/ingestion/` | OLM parsing, extraction, normalization, chunking, and archive writes | `mailarium-ingest` |
| `mailarium/retrieval/` | Embeddings, indexes, ranking, filters, and index lifecycle | No |
| `mailarium/investigation/` | Evidence, reports, exports, entities, networks, topics, and threads | No |
| `mailarium/mailbox/` | EWS accounts, synchronization, proposals, and controlled execution | CLI and MCP operations |
| `mailarium/interfaces/` | CLI (`cli/`), MCP (`mcp/`), and Streamlit (`web/`) adapters; `runtime.py` composes long-lived resources | `mailarium`, `mailarium-ingest`, MCP, Streamlit |
| `mailarium/platform/` | Configuration (`settings.py`), runtime paths, validation, and sanitization | No |
| `mailarium/*.py` | Launchers for `python -m` and Streamlit that delegate to `mailarium/interfaces/` | Entry points |
| `scripts/` | Architecture policy, verification profiles, smokes, operations, and release tooling (including the publication privacy scanner) | Development tooling |
| `demo/` | Dependency-free synthetic interface demonstration | Static files only |

See [architecture](docs/ARCHITECTURE.md) for dependencies, runtime ownership,
and data flows.

## Development

Create the locked development environment from the repository root:

```bash
python -m pip install "uv==0.10.7"
uv sync --locked --extra dev --extra nlp --extra training --extra ews-ntlm
```

Run the repository-owned verification profile that matches the change:

```bash
uv run python scripts/verify.py fast
uv run python scripts/verify.py pr
uv run python scripts/verify.py release
```

`fast` runs lock, lint, format, architecture, and contract checks. `pr` adds
typing, the complete tests under critical branch coverage floors, offline and
native ingestion smokes, security analysis, dependency audit, and privacy
scanning. `package` covers the Streamlit smoke, build, artifact inspection,
and installed-wheel smoke; `release` runs `pr` and then `package`. These
local profiles do not prove live EWS, real model downloads, a manual browser
session, remote CI, or publication.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Operations and configuration](docs/OPERATIONS.md)
- [CLI reference](docs/CLI_REFERENCE.md)
- [MCP tools](docs/MCP_TOOLS.md)
- [Web interfaces](docs/WEB_INTERFACE.md)
- [Runtime tuning](docs/RUNTIME_TUNING.md)
- [Attachment support](docs/ATTACHMENT_SUPPORT.md)
- [Answer grounding](docs/ANSWER_GROUNDING.md)
- [Privacy and redaction](docs/PRIVACY_AND_REDACTION.md)
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), and
  [releasing](RELEASING.md)

Support requests must use synthetic examples and sanitized diagnostics. Use
the repository issue forms for questions, defects, and feature proposals, and
follow [SECURITY.md](SECURITY.md) for suspected vulnerabilities.

Mailarium is licensed under the [MIT License](LICENSE).
