# Mailarium

Mailarium is a local-first mailbox investigation tool for Outlook `.olm`
archives. It normalizes messages and selected attachments into a local SQLite
archive, builds rebuildable USearch acceleration, and offers CLI, MCP, and
Streamlit interfaces for search, evidence, analysis, exports, and controlled
mailbox workflows.

Mailarium is alpha software. Commands, storage details, and defaults can change
within the `0.5.x` line.

## Boundaries

- SQLite holds canonical messages, metadata, provenance, and vector data.
  USearch is derived acceleration and can be rebuilt.
- An `.olm` archive remains the recovery source. Retrieval scores, OCR output,
  and generated summaries require review against original material.
- Streamlit and MCP are trusted-local interfaces, not authenticated public
  services.
- Optional EWS support is limited to a configured HTTPS endpoint. Reads,
  writes, and attachment content are independently opt-in. Live EWS operation
  is not verified by the local source checks.
- First model use may download local model weights unless local-only mode is
  selected. No mailbox content is sent to a hosted model service by Mailarium.

## Requirements

- Python `>=3.14.6,<3.15`
- macOS 14 or later on Apple Silicon for the documented operator runtime
- Disk space for the archive, SQLite database, model cache, and vector index

## Install

```bash
git clone https://github.com/sebastianspicker/mailarium.git
cd mailarium
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development, use the locked environment:

```bash
python -m pip install "uv==0.10.7"
uv sync --locked --extra dev --extra nlp --extra training --extra ews-ntlm
```

## Configure and ingest

Copy the tracked template, then keep live data under ignored paths:

```bash
cp .env.example .env
mkdir -p private/ingest private/runtime/current private/exports
mailarium-ingest private/ingest/archive.olm --max-emails 200
```

The normal source-checkout paths are:

```dotenv
VECTOR_INDEX_PATH=private/runtime/current/vector-index
SQLITE_PATH=private/runtime/current/email_metadata.db
RUNTIME_PROFILE=quality
EMBEDDING_LOAD_MODE=auto
```

For offline runs, use `RUNTIME_PROFILE=offline-test`,
`EMBEDDING_LOAD_MODE=local_only`, and
`SPACY_AUTO_DOWNLOAD_DURING_INGEST=0`. Required model files must already be
available locally.

## Use the interfaces

```bash
mailarium search "project handoff" --scope customer-support --hybrid
mailarium browse --page 1 --page-size 20
mailarium analytics stats
mailarium export report --output private/exports/report.html
```

The installed commands are `mailarium` and `mailarium-ingest`. Their module
forms are `python -m mailarium.cli` and `python -m mailarium.ingest`.

Start the stdio MCP server with the environment interpreter:

```bash
.venv/bin/python -m mailarium.mcp_server
```

Start Streamlit only on a trusted local interface:

```bash
python -m streamlit run mailarium/web_app.py --server.address 127.0.0.1
```

See [the documentation index](docs/README.md) for CLI, MCP, privacy, EWS, and
runtime details.

## Development

Run the canonical verification profile that matches the work:

```bash
python scripts/verify.py fast
python scripts/verify.py pr
python scripts/verify.py release
```

`fast` is the deterministic lint, format, architecture, and contract gate.
`pr` adds type checking, offline ingestion, security, dependency, and privacy
checks. `release` also builds, inspects, installs, and smokes the distribution.
These are local checks; they do not prove live EWS, model-download, browser, or
remote CI behavior.

## Project layout

```text
mailarium/
├── archive/        SQLite schema, repositories, and source mappings
├── ingestion/      OLM parsing and archive construction
├── interfaces/     CLI, MCP, and Streamlit adapters
├── investigation/  Evidence and derived analysis
├── mailbox/         EWS accounts, sync, proposals, and execution
├── model/           Shared value objects and normalization
├── platform/        Paths, validation, and sanitization
├── privacy/         Publication-boundary scanning
├── retrieval/       Embeddings, indexes, ranking, and filters
└── runtime.py       Application composition
```

Keep real archives, databases, exports, and credentials out of version control.
See [SECURITY.md](SECURITY.md) before reporting a vulnerability or exposing an
interface outside a trusted local environment.
