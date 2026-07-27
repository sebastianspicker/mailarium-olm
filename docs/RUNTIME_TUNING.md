# Runtime Tuning

This document describes runtime modes, hardware settings, and performance
tuning.

Use this file after the first setup succeeds. It is an advanced tuning reference, not required reading for a normal first run.

## Network And Disk Expectations

- Email content stays local.
- First-run embedding or reranking model loading may contact Hugging Face.
- Entity extraction can invoke spaCy's model downloader unless
  `SPACY_AUTO_DOWNLOAD_DURING_INGEST=0`.
- Model caches and local runtime stores can consume several gigabytes on disk depending on archive size and enabled models.
- In a source checkout, keep live operator runtimes under `private/runtime/current/` and keep tracked `data/` limited to sanitized examples.
- An installed wheel keeps relative runtime data under its per-user runtime home, never under `site-packages`. Override that home with an absolute `MAILARIUM_RUNTIME_HOME` when needed.

## Recommended Profiles

Use `RUNTIME_PROFILE` as the first lever, then override individual flags only when you need to.

| Profile | Intended use | Retrieval defaults | Load mode |
| --- | --- | --- | --- |
| `balanced` | conservative default | leaves advanced retrieval features off unless explicitly enabled | `auto` |
| `quality` | local use with hybrid retrieval and reranking | enables hybrid search and reranking; optional sparse and local late interaction remain explicit | `auto` |
| `low-memory` | smaller-memory machines or parallel workloads | disables the heavier query-time features and lowers the default embedding batch size | `local_only` |
| `offline-test` | deterministic local/offline runs | disables advanced retrieval features and uses local-only embedding defaults | `local_only` |

Environment overrides still win. For example, `RUNTIME_PROFILE=quality` plus `RERANK_ENABLED=false` keeps the rest of the quality defaults but disables cross-encoder fallback.

## Model Load Modes

`EMBEDDING_LOAD_MODE` controls what happens when required embedding and
reranking model weights are not already available locally. It does not control
spaCy's entity-extraction model bootstrap.

| Mode | Behavior |
| --- | --- |
| `auto` | try local cache first, then allow download on cache miss |
| `local_only` | stay offline and fail fast if the model is missing |
| `download` | skip the cache-only probe and allow download immediately |

For privacy-sensitive or CI-style runs, prefer `local_only`. For first-time setup on a normal workstation, `auto` is the least surprising mode.

## Model Revisions

Dense and image embeddings are pinned to immutable Hugging Face revisions so a
moving upstream branch cannot silently mix incompatible vectors in one SQLite
embedding space. The defaults are:

- `EMBEDDING_MODEL=BAAI/bge-m3` with
  `EMBEDDING_MODEL_REVISION=5617a9f61b028005a4858fdac845db406aefb181`
- `IMAGE_EMBEDDING_MODEL=google/siglip2-base-patch16-256` with
  `IMAGE_EMBEDDING_MODEL_REVISION=3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab`

When overriding either model, set its revision variable explicitly. An empty or
floating model override is rejected. Changing a configured model or revision
requires resetting that embedding space and re-ingesting it.

## Apple Silicon Guidance

For an Apple MacBook Air M4 with 16 GB unified memory:

```env
DEVICE=auto
RUNTIME_PROFILE=quality
EMBEDDING_LOAD_MODE=auto
EMBEDDING_BATCH_SIZE=0
MPS_CACHE_CLEAR_ENABLED=0
INGEST_BATCH_COOLDOWN=1
```

Why:

- `DEVICE=auto` resolves to `mps` when the local Torch build supports Apple Metal.
- `EMBEDDING_BATCH_SIZE=0` resolves to `32` on a 16 GB M-series machine.
- `INGEST_BATCH_COOLDOWN=1` is the safer sustained-ingest default on fanless Air hardware.
- `MPS_CACHE_CLEAR_ENABLED=0` remains the conservative default because `torch.mps.empty_cache()` is not stable on every stack.

## Runtime Summary and Diagnostics

The repo now exposes a resolved-runtime summary in two places:

- ingestion startup logs
- MCP diagnostics via `email_admin(action="diagnostics")`

That summary reports:

- runtime profile
- embedding model
- dense and image model revisions
- embedding load mode
- configured device and resolved device
- configured batch size and resolved batch size
- sparse / hybrid / rerank / late-interaction state
- MPS cache-clear state
- whether image embedding is allowed on the current machine

Use that summary instead of inferring behavior from `.env` alone.

## Throughput Measurement

The embedding forward pass is usually the main ingestion cost. This alpha does
not publish a representative cross-hardware benchmark because the repository
does not contain a reproducible benchmark artifact. Measure a bounded ingest on
the target archive and machine before estimating a full run. Model availability,
message size, attachment extraction, thermal behavior, and the selected runtime
profile can all affect elapsed time.

## High-Value Knobs

| Variable | Default | Description |
| --- | --- | --- |
| `RUNTIME_PROFILE` | `balanced` | opinionated retrieval/runtime preset |
| `RAG_SCOPE` | `general` | process default for retrieval context; per-query CLI/MCP/web scope overrides it |
| `EMBEDDING_MODEL_REVISION` | pinned commit | immutable dense-model provenance; required with a custom dense model |
| `IMAGE_EMBEDDING_MODEL_REVISION` | pinned commit | immutable image-model provenance; required with a custom image model |
| `EMBEDDING_LOAD_MODE` | `auto` | cache-only vs download-allowed model loading |
| `DEVICE` | `auto` | backend selection: `mps`, `cuda`, or `cpu` |
| `EMBEDDING_BATCH_SIZE` | `0` | resolved at runtime when left on auto |
| `MPS_CACHE_CLEAR_ENABLED` | `0` | opt into `torch.mps.empty_cache()` only if your stack is stable |
| `MPS_CACHE_CLEAR_INTERVAL` | `1` | cache-clear frequency when enabled |
| `INGEST_BATCH_COOLDOWN` | `1` | thermal cooldown between ingestion batches |
| `INGEST_WAL_CHECKPOINT_INTERVAL` | `10` | SQLite WAL checkpoint cadence |
| `SPARSE_ENABLED` | profile-dependent | enable learned sparse vectors |
| `LATE_INTERACTION_ENABLED` | profile-dependent | enable the configured local late-interaction runner |

## Scope and Retrieval Policy

`RAG_SCOPE=general` is the default. Operators can supply a narrower scope for
one query with CLI `--scope`, an MCP tool's `scope` field, or the web Retrieval
Scope input. The process variable is useful for a long-running CLI or MCP
server, but it is not required for ordinary scoped queries.

The policy is deterministic and explainable: query shape selects semantic and
keyword channel weights for weighted RRF, then the configured sparse and
reranking stages apply. Embedding, sparse, and reranking models are used during
retrieval; no online self-training occurs from query or mailbox data.

## Offline and CI-Like Runs

If you need deterministic local behavior with no model downloads:

```env
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
SPACY_AUTO_DOWNLOAD_DURING_INGEST=0
```

Pre-seed the required Hugging Face and spaCy models before disconnecting the
machine. When the local spaCy model is missing and automatic download is
disabled, entity extraction falls back to the built-in regex extractor.
