# Runtime Tuning

This document collects the runtime-mode, hardware, and performance tuning details that used to sit inline in the README.

Use this file after the first setup succeeds. It is an advanced tuning reference, not required reading for a normal first run.

## Network And Disk Expectations

- Email content stays local.
- First-run model loading may contact Hugging Face unless you explicitly choose offline mode.
- Model caches and local runtime stores can consume several gigabytes on disk depending on archive size and enabled models.
- Keep live operator runtimes under `private/runtime/current/` and keep tracked `data/` limited to sanitized examples.

## Recommended Profiles

Use `RUNTIME_PROFILE` as the first lever, then override individual flags only when you need to.

| Profile | Intended use | Retrieval defaults | Load mode |
| --- | --- | --- | --- |
| `balanced` | conservative default | leaves advanced retrieval features off unless explicitly enabled | `auto` |
| `quality` | best retrieval quality on a normal local machine | enables sparse retrieval, hybrid search, reranking, and ColBERT reranking | `auto` |
| `low-memory` | smaller-memory machines or parallel workloads | disables the heavier query-time features and lowers the default embedding batch size | `local_only` |
| `offline-test` | deterministic local/offline runs | disables advanced retrieval features and refuses model downloads | `local_only` |

Environment overrides still win. For example, `RUNTIME_PROFILE=quality` plus `RERANK_ENABLED=false` keeps the rest of the quality defaults but disables cross-encoder fallback.

## Model Load Modes

`EMBEDDING_LOAD_MODE` controls what happens when the required model weights are not already available locally.

| Mode | Behavior |
| --- | --- |
| `auto` | try local cache first, then allow download on cache miss |
| `local_only` | stay offline and fail fast if the model is missing |
| `download` | skip the cache-only probe and allow download immediately |

For privacy-sensitive or CI-style runs, prefer `local_only`. For first-time setup on a normal workstation, `auto` is the least surprising mode.

## Apple Silicon Guidance

For an Apple MacBook Air M4 with 16 GB unified memory:

```env
DEVICE=auto
RUNTIME_PROFILE=quality
EMBEDDING_LOAD_MODE=auto
EMBEDDING_BATCH_SIZE=0
MPS_FLOAT16=false
MPS_CACHE_CLEAR_ENABLED=0
INGEST_BATCH_COOLDOWN=1
```

Why:

- `DEVICE=auto` resolves to `mps` when the local Torch build supports Apple Metal.
- `EMBEDDING_BATCH_SIZE=0` resolves to `32` on a 16 GB M-series machine.
- `MPS_FLOAT16=false` keeps retrieval quality stable on current Apple Silicon stacks.
- `INGEST_BATCH_COOLDOWN=1` is the safer sustained-ingest default on fanless Air hardware.
- `MPS_CACHE_CLEAR_ENABLED=0` remains the conservative default because `torch.mps.empty_cache()` is not stable on every stack.

## Runtime Summary and Diagnostics

The repo now exposes a resolved-runtime summary in two places:

- ingestion startup logs
- MCP diagnostics via `email_admin(action="diagnostics")`

That summary reports:

- runtime profile
- embedding model
- embedding load mode
- configured device and resolved device
- configured batch size and resolved batch size
- sparse / hybrid / rerank / ColBERT state
- MPS cache-clear state
- whether image embedding is allowed on the current machine

Use that summary instead of inferring behavior from `.env` alone.

## Throughput Expectations

The embedding forward pass remains the dominant ingestion cost.

| Hardware | Device | Batch size | Observed sustained rate | 20K emails (~47K chunks) |
| --- | --- | --- | --- | --- |
| Apple M4 / 16 GB | `mps` | 32 | 5 to 3 chunks/s | about 4 hours |
| Apple M1 Pro / 16 GB | `mps` | 32 | about 4 to 5 chunks/s | about 4.5 hours |
| Apple M2 Max / 32 GB | `mps` | 32 | about 5 to 6 chunks/s | about 3.5 hours |
| NVIDIA RTX 3090 / 4090 | `cuda` | 64 | about 15 to 30 chunks/s | about 30 to 60 min |
| CPU only | `cpu` | 16 | about 1 to 2 chunks/s | about 10+ hours |

These numbers are local engineering baselines, not vendor guarantees. On Apple
Silicon, sustained runs can degrade from the peak warm-up rate because of
thermal and memory-pressure behavior, especially on fanless hardware.

## High-Value Knobs

| Variable | Default | Description |
| --- | --- | --- |
| `RUNTIME_PROFILE` | `balanced` | opinionated retrieval/runtime preset |
| `EMBEDDING_LOAD_MODE` | `auto` | cache-only vs download-allowed model loading |
| `DEVICE` | `auto` | backend selection: `mps`, `cuda`, or `cpu` |
| `EMBEDDING_BATCH_SIZE` | `0` | resolved at runtime when left on auto |
| `MPS_CACHE_CLEAR_ENABLED` | `0` | opt into `torch.mps.empty_cache()` only if your stack is stable |
| `MPS_CACHE_CLEAR_INTERVAL` | `1` | cache-clear frequency when enabled |
| `INGEST_BATCH_COOLDOWN` | `1` | thermal cooldown between ingestion batches |
| `INGEST_WAL_CHECKPOINT_INTERVAL` | `10` | SQLite WAL checkpoint cadence |
| `SPARSE_ENABLED` | profile-dependent | enable learned sparse vectors |
| `COLBERT_RERANK_ENABLED` | profile-dependent | enable ColBERT reranking |

## Offline and CI-Like Runs

If you need deterministic local behavior with no model downloads:

```env
RUNTIME_PROFILE=offline-test
EMBEDDING_LOAD_MODE=local_only
```

Pre-seed the Hugging Face cache before running the repo in that mode.
