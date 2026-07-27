"""Application configuration and logging helpers."""
# pylint: disable=too-many-instance-attributes

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Any

from .repo_paths import validate_runtime_path
from .retrieval_policy import normalize_scope

# ── Model-aware MCP response profiles ─────────────────────────
#
# Budget presets tuned for the calling client's context window size.
# Selected via ``MCP_MODEL_PROFILE`` env var (default: ``"auto"`` = balanced).
#
# 3-tier precedence for every MCP budget knob:
#   1. Env var override (e.g. ``MCP_MAX_BODY_CHARS=1000``) - always wins.
#   2. Profile default - from the dict below for the active profile.
#   3. Hardcoded default - the ``Settings`` dataclass field default (used
#      only when no env var is set AND no profile is active).
#
# Profiles:
#   "tight"    - Tight budgets for smaller-context clients.
#   "balanced" - Balanced budgets for most clients. Also used as the "auto" alias.
#   "generous" - Generous budgets for large-context clients.
#
# Keys map 1:1 to ``Settings`` field names (which map 1:1 to env vars
# via UPPER_SNAKE_CASE, e.g. ``mcp_max_body_chars`` -> ``MCP_MAX_BODY_CHARS``).
MODEL_PROFILES: dict[str, dict[str, int]] = {
    "tight": {
        "mcp_max_body_chars": 300,  # chars per email body in search results
        "mcp_max_response_tokens": 4000,  # total token budget for search responses
        "mcp_max_full_body_chars": 5000,  # soft limit for email_deep_context body
        "mcp_max_json_response_chars": 16000,  # safety cap on JSON tool responses
        "mcp_max_triage_results": 30,  # max results per email_triage call
        "mcp_max_search_results": 15,  # max results per email_search_structured call
    },
    "balanced": {
        "mcp_max_body_chars": 500,
        "mcp_max_response_tokens": 8000,
        "mcp_max_full_body_chars": 10000,
        "mcp_max_json_response_chars": 32000,
        "mcp_max_triage_results": 50,
        "mcp_max_search_results": 30,
    },
    "generous": {
        "mcp_max_body_chars": 800,
        "mcp_max_response_tokens": 16000,
        "mcp_max_full_body_chars": 20000,
        "mcp_max_json_response_chars": 64000,
        "mcp_max_triage_results": 100,
        "mcp_max_search_results": 50,
    },
}
MODEL_PROFILES["auto"] = MODEL_PROFILES["balanced"]  # "auto" is an alias for "balanced"

RUNTIME_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {},
    "quality": {
        "rerank_enabled": True,
        "hybrid_enabled": True,
        "sparse_enabled": False,
        "late_interaction_enabled": False,
        "embedding_load_mode": "auto",
    },
    "low-memory": {
        "rerank_enabled": False,
        "hybrid_enabled": False,
        "sparse_enabled": False,
        "late_interaction_enabled": False,
        "embedding_batch_size": 8,
        "embedding_load_mode": "local_only",
    },
    "offline-test": {
        "rerank_enabled": False,
        "hybrid_enabled": False,
        "sparse_enabled": False,
        "late_interaction_enabled": False,
        "embedding_load_mode": "local_only",
    },
}
VALID_EMBEDDING_LOAD_MODES = frozenset({"auto", "local_only", "download"})
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_EMBEDDING_MODEL_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
DEFAULT_IMAGE_EMBEDDING_MODEL = "google/siglip2-base-patch16-256"
DEFAULT_IMAGE_EMBEDDING_MODEL_REVISION = "3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab"
_IMMUTABLE_MODEL_REVISION = re.compile(r"[0-9a-f]{40}", re.IGNORECASE)


def _get_system_memory_gb() -> float:
    """Return total system memory in GB. Falls back to 8.0 on error."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024**3)
    except ValueError, OSError, AttributeError:
        return 8.0


def resolve_device(device: str = "auto") -> str:
    """Resolve device string to the best available compute backend.

    ``"auto"`` probes for MPS (Apple Silicon GPU), then CUDA, then falls
    back to CPU.  Any other value is returned as-is.

    When MPS is selected, sets ``PYTORCH_ENABLE_MPS_FALLBACK=1`` so ops
    not yet implemented on MPS fall back to CPU transparently.
    """
    if device != "auto":
        if device == "mps":
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        return device
    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass  # torch not installed - fall back to CPU
    return "cpu"


def resolve_embedding_batch_size(device: str = "auto") -> int:
    """Return a sensible default embedding batch size for the device.

    MPS batch size is auto-tuned based on available system memory.
    BGE-M3 weights are ~1.2 GB; larger batches use more activation memory
    but remain well within headroom on 16 GB+ unified memory machines.
    """
    resolved = device if device != "auto" else resolve_device(device)
    if resolved == "mps":
        mem_gb = _get_system_memory_gb()
        if mem_gb >= 36:
            return 48
        if mem_gb >= 16:
            return 32
        if mem_gb >= 8:
            return 16
        return 8
    if resolved == "cuda":
        return 32
    return 16


def resolve_embedding_load_mode(mode: str = "auto") -> str:
    """Normalize embedding load mode to a supported value."""
    normalized = (mode or "auto").strip().lower()
    if normalized in VALID_EMBEDDING_LOAD_MODES:
        return normalized
    return "auto"


def should_enable_image_embedding(min_memory_gb: float = 24.0) -> bool:
    """Return whether image embedding is safe to enable on this machine.

    SigLIP2 adds substantial model memory on top of the text embedder.
    On lower-memory Apple Silicon machines, keep it opt-in via an override.
    """
    override = os.getenv("IMAGE_EMBED_ALLOW_LOW_MEMORY", "").lower()
    if override in ("1", "true", "yes"):
        return True
    return _get_system_memory_gb() >= min_memory_gb


@dataclass(frozen=True)
class Settings:
    """Environment-backed settings for the Mailarium application.

    Every field has a corresponding env var (UPPER_SNAKE_CASE of the field
    name).  Boolean fields accept ``"1"``, ``"true"``, or ``"yes"``
    (case-insensitive).  Integer fields are parsed via ``_int_from_env``
    with min/max clamping.  MCP budget fields use the 3-tier precedence
    described in ``MODEL_PROFILES`` above.
    """

    # Directory for rebuildable USearch files.
    # Env: VECTOR_INDEX_PATH  |  Default: "data/vector-index"
    vector_index_path: str = "data/vector-index"

    # Path to the SQLite metadata database (email headers, entities, evidence, etc.).
    # Env: SQLITE_PATH  |  Default: "data/email_metadata.db"
    sqlite_path: str = "data/email_metadata.db"

    # HuggingFace model name or local path for the embedding model.
    # Env: EMBEDDING_MODEL  |  Default: "BAAI/bge-m3"
    embedding_model: str = DEFAULT_EMBEDDING_MODEL

    # Immutable Hugging Face revision for the dense embedding model.
    # Env: EMBEDDING_MODEL_REVISION
    embedding_model_revision: str = DEFAULT_EMBEDDING_MODEL_REVISION

    # Default number of results returned by search queries.
    # Env: TOP_K  |  Valid: 1-1000  |  Default: 10
    top_k: int = 10

    # Python logging level for the application.
    # Env: LOG_LEVEL  |  Valid: DEBUG, INFO, WARNING, ERROR, CRITICAL  |  Default: "INFO"
    log_level: str = "INFO"

    # Enable cross-encoder reranking (uses rerank_model below). The isolated
    # late-interaction backend is tried first when enabled and configured.
    # Env: RERANK_ENABLED  |  Valid: 1/true/yes  |  Default: False
    rerank_enabled: bool = False

    # HuggingFace model name for cross-encoder reranking.
    # Env: RERANK_MODEL  |  Default: "BAAI/bge-reranker-v2-m3"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # Enable hybrid search combining semantic embeddings with BM25/sparse keyword search.
    # Env: HYBRID_ENABLED  |  Valid: 1/true/yes  |  Default: False
    hybrid_enabled: bool = False

    # Env: DEVICE  |  Valid: "auto", "cpu", "mps", "cuda"  |  Default: "auto"
    # "auto" probes MPS (Apple Silicon GPU) -> CUDA -> CPU.
    device: str = "auto"

    # Runtime profile for common operator goals.
    # Env: RUNTIME_PROFILE  |  Valid: "balanced", "quality", "low-memory", "offline-test"  |  Default: "balanced"
    runtime_profile: str = "balanced"

    # Default relevance scope for retrieval. Individual CLI/MCP/Web requests
    # can override it without mutating this process-level setting.
    # Env: RAG_SCOPE  |  Default: "general"
    rag_scope: str = "general"

    # Enable sparse vector storage and retrieval via the in-memory inverted index.
    # Experimental opt-in; BM25 remains the default lexical path.
    # Env: SPARSE_ENABLED  |  Valid: 1/true/yes  |  Default: False
    sparse_enabled: bool = False

    # SentenceTransformers SparseEncoder model used only when sparse_enabled.
    # Env: SPARSE_MODEL
    sparse_model: str = "opensearch-project/opensearch-neural-sparse-encoding-multilingual-v1"

    # Optional immutable Hugging Face revision for the sparse model.
    # Env: SPARSE_MODEL_REVISION
    sparse_model_revision: str = ""

    # Enable an explicitly configured local late-interaction runner.
    # Env: LATE_INTERACTION_ENABLED  |  Valid: 1/true/yes  |  Default: False
    late_interaction_enabled: bool = False

    # Executable for the isolated JSONL late-interaction runner.
    # Env: LATE_INTERACTION_RUNNER
    late_interaction_runner: str = ""

    # Pinned local model directory consumed by the isolated runner.
    # Env: LATE_INTERACTION_MODEL_PATH
    late_interaction_model_path: str = ""

    # Standard Transformers image/text model in a separate vector space.
    # Env: IMAGE_EMBEDDING_MODEL
    image_embedding_model: str = DEFAULT_IMAGE_EMBEDDING_MODEL

    # Immutable Hugging Face revision for the image embedding model.
    # Env: IMAGE_EMBEDDING_MODEL_REVISION
    image_embedding_model_revision: str = DEFAULT_IMAGE_EMBEDDING_MODEL_REVISION

    # Fuse the dedicated image vector space into text queries.
    # Env: IMAGE_SEARCH_ENABLED  |  Default: False
    image_search_enabled: bool = False

    # Batch size for embedding model encode calls. 0 = auto-detect based on
    # device and system memory (see resolve_embedding_batch_size()).
    # Env: EMBEDDING_BATCH_SIZE  |  Valid: 0-256  |  Default: 0 (auto)
    embedding_batch_size: int = 0

    # Controls whether model loading may download missing weights.
    # Env: EMBEDDING_LOAD_MODE  |  Valid: "auto", "local_only", "download"  |  Default: "auto"
    embedding_load_mode: str = "auto"

    # Max characters per email body snippet in search/browse results.
    # Bodies exceeding this are truncated with "...". 0 = unlimited.
    # Env: MCP_MAX_BODY_CHARS  |  Default: profile-dependent (balanced: 500)
    mcp_max_body_chars: int = 500

    # Max total estimated tokens for serialized search responses.
    # serialize_results() stops emitting results when this budget is exceeded.
    # 0 = unlimited.
    # Env: MCP_MAX_RESPONSE_TOKENS  |  Default: profile-dependent (balanced: 8000)
    mcp_max_response_tokens: int = 8000

    # Soft character limit for full email bodies returned by email_deep_context.
    # 0 = unlimited.
    # Env: MCP_MAX_FULL_BODY_CHARS  |  Default: profile-dependent (balanced: 10000)
    mcp_max_full_body_chars: int = 10000

    # Safety cap on the total character length of JSON tool responses.
    # Roughly ~4 chars per token. 0 = unlimited.
    # Env: MCP_MAX_JSON_RESPONSE_CHARS  |  Default: profile-dependent (balanced: 32000)
    mcp_max_json_response_chars: int = 32000

    # Active model profile name. Determines default values for all MCP budget
    # fields above. "auto" is an alias for "balanced".
    # Env: MCP_MODEL_PROFILE  |  Valid: "auto", "tight", "balanced", "generous"  |  Default: "auto"
    mcp_model_profile: str = "auto"

    # Display timezone used for temporal analytics bucketing.
    # Use "local" for the system timezone or an IANA name like "Europe/Berlin".
    # Env: ANALYTICS_TIMEZONE  |  Default: "local"
    analytics_timezone: str = "local"

    # Max results returned per email_triage call (clamped server-side).
    # Env: MCP_MAX_TRIAGE_RESULTS  |  Default: profile-dependent (balanced: 50)
    mcp_max_triage_results: int = 50

    # Max results returned per email_search_structured call (clamped server-side).
    # Env: MCP_MAX_SEARCH_RESULTS  |  Default: profile-dependent (balanced: 30)
    mcp_max_search_results: int = 30

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables with safe defaults.

        MCP budget knobs use profile defaults: env override > profile > hardcoded.
        """
        profile_name = os.getenv("MCP_MODEL_PROFILE", "auto").lower()
        profile = MODEL_PROFILES.get(profile_name, MODEL_PROFILES["auto"])
        if profile_name not in MODEL_PROFILES:
            profile_name = "auto"
        runtime_profile_name = os.getenv("RUNTIME_PROFILE", cls.runtime_profile).lower()
        runtime_profile = RUNTIME_PROFILES.get(runtime_profile_name, RUNTIME_PROFILES[cls.runtime_profile])
        if runtime_profile_name not in RUNTIME_PROFILES:
            runtime_profile_name = cls.runtime_profile

        _reject_removed_environment_variables()
        embedding_model, embedding_model_revision = _model_identity_from_env(
            model_variable="EMBEDDING_MODEL",
            revision_variable="EMBEDDING_MODEL_REVISION",
            default_model=cls.embedding_model,
            default_revision=cls.embedding_model_revision,
        )
        image_embedding_model, image_embedding_model_revision = _model_identity_from_env(
            model_variable="IMAGE_EMBEDDING_MODEL",
            revision_variable="IMAGE_EMBEDDING_MODEL_REVISION",
            default_model=cls.image_embedding_model,
            default_revision=cls.image_embedding_model_revision,
        )
        return cls(
            vector_index_path=_runtime_path_from_env(
                "VECTOR_INDEX_PATH",
                cls.vector_index_path,
                field_name="vector_index_path",
            ),
            sqlite_path=_runtime_path_from_env("SQLITE_PATH", cls.sqlite_path, field_name="sqlite_path"),
            embedding_model=embedding_model,
            embedding_model_revision=embedding_model_revision,
            top_k=_int_from_env("TOP_K", cls.top_k, min_value=1, max_value=1000),
            log_level=os.getenv("LOG_LEVEL", cls.log_level).upper(),
            rerank_enabled=_bool_from_env("RERANK_ENABLED", runtime_profile.get("rerank_enabled", cls.rerank_enabled)),
            rerank_model=os.getenv("RERANK_MODEL", cls.rerank_model),
            hybrid_enabled=_bool_from_env("HYBRID_ENABLED", runtime_profile.get("hybrid_enabled", cls.hybrid_enabled)),
            device=os.getenv("DEVICE", cls.device),
            runtime_profile=runtime_profile_name,
            rag_scope=normalize_scope(os.getenv("RAG_SCOPE", cls.rag_scope)),
            sparse_enabled=_bool_from_env("SPARSE_ENABLED", runtime_profile.get("sparse_enabled", cls.sparse_enabled)),
            sparse_model=os.getenv("SPARSE_MODEL", cls.sparse_model),
            sparse_model_revision=os.getenv("SPARSE_MODEL_REVISION", cls.sparse_model_revision),
            late_interaction_enabled=_bool_from_env(
                "LATE_INTERACTION_ENABLED",
                runtime_profile.get("late_interaction_enabled", cls.late_interaction_enabled),
            ),
            late_interaction_runner=os.getenv("LATE_INTERACTION_RUNNER", cls.late_interaction_runner),
            late_interaction_model_path=os.getenv(
                "LATE_INTERACTION_MODEL_PATH",
                cls.late_interaction_model_path,
            ),
            image_embedding_model=image_embedding_model,
            image_embedding_model_revision=image_embedding_model_revision,
            image_search_enabled=_bool_from_env("IMAGE_SEARCH_ENABLED", cls.image_search_enabled),
            embedding_batch_size=_int_from_env(
                "EMBEDDING_BATCH_SIZE",
                int(runtime_profile.get("embedding_batch_size", cls.embedding_batch_size)),
                min_value=0,
                max_value=256,
            ),
            embedding_load_mode=resolve_embedding_load_mode(
                os.getenv("EMBEDDING_LOAD_MODE", str(runtime_profile.get("embedding_load_mode", cls.embedding_load_mode)))
            ),
            mcp_max_body_chars=_int_from_env("MCP_MAX_BODY_CHARS", profile["mcp_max_body_chars"], min_value=0),
            mcp_max_response_tokens=_int_from_env("MCP_MAX_RESPONSE_TOKENS", profile["mcp_max_response_tokens"], min_value=0),
            mcp_max_full_body_chars=_int_from_env("MCP_MAX_FULL_BODY_CHARS", profile["mcp_max_full_body_chars"], min_value=0),
            mcp_max_json_response_chars=_int_from_env(
                "MCP_MAX_JSON_RESPONSE_CHARS",
                profile["mcp_max_json_response_chars"],
                min_value=0,
            ),
            mcp_model_profile=profile_name,
            analytics_timezone=os.getenv("ANALYTICS_TIMEZONE", cls.analytics_timezone) or cls.analytics_timezone,
            mcp_max_triage_results=_int_from_env("MCP_MAX_TRIAGE_RESULTS", profile["mcp_max_triage_results"], min_value=1),
            mcp_max_search_results=_int_from_env("MCP_MAX_SEARCH_RESULTS", profile["mcp_max_search_results"], min_value=1),
        )


_settings_cache_lock = threading.Lock()
_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Return process-level cached settings.

    Unlike ``functools.lru_cache``, this guarantees concurrent first callers
    receive the same frozen Settings object, which keeps singleton users from
    observing separate instances during startup races.
    """
    global _settings_cache  # pylint: disable=global-statement
    if _settings_cache is not None:
        return _settings_cache
    with _settings_cache_lock:
        if _settings_cache is None:
            _settings_cache = Settings.from_env()
        return _settings_cache


def clear_settings_cache() -> None:
    """Clear cached settings after environment-loading or test setup changes."""
    global _settings_cache  # pylint: disable=global-statement
    with _settings_cache_lock:
        _settings_cache = None


get_settings.cache_clear = clear_settings_cache  # type: ignore[attr-defined]


def resolve_runtime_settings(
    vector_index_path: str | None = None,
    embedding_model: str | None = None,
    sqlite_path: str | None = None,
    sparse_enabled: bool | None = None,
    image_search_enabled: bool | None = None,
    embedding_model_revision: str | None = None,
) -> Settings:
    """Derive runtime settings from env defaults with optional overrides."""
    from dataclasses import replace

    base = Settings.from_env()
    overrides: dict[str, Any] = {}
    if vector_index_path:
        overrides["vector_index_path"] = _runtime_path_override(
            vector_index_path,
            field_name="vector_index_path",
        )
    if sqlite_path:
        overrides["sqlite_path"] = _runtime_path_override(sqlite_path, field_name="sqlite_path")
    if embedding_model:
        if embedding_model != base.embedding_model and embedding_model_revision is None:
            raise ValueError("embedding_model_revision is required when overriding embedding_model")
        overrides["embedding_model"] = embedding_model
    if embedding_model_revision is not None:
        overrides["embedding_model_revision"] = _require_model_revision(
            embedding_model_revision,
            variable_name="embedding_model_revision",
        )
    if sparse_enabled is not None:
        overrides["sparse_enabled"] = sparse_enabled
    if image_search_enabled is not None:
        overrides["image_search_enabled"] = image_search_enabled
    return replace(base, **overrides)


def resolve_runtime_summary(settings: Settings | None = None) -> dict[str, Any]:
    """Return a compact resolved-runtime summary for logs and diagnostics."""
    active = settings or get_settings()
    resolved_device = resolve_device(active.device)
    resolved_batch_size = active.embedding_batch_size or resolve_embedding_batch_size(resolved_device)
    return {
        "runtime_profile": active.runtime_profile,
        "rag_scope": active.rag_scope,
        "embedding_model": active.embedding_model,
        "embedding_model_revision": active.embedding_model_revision,
        "vector_index_path": active.vector_index_path,
        "embedding_load_mode": active.embedding_load_mode,
        "device_setting": active.device,
        "resolved_device": resolved_device,
        "embedding_batch_size_setting": active.embedding_batch_size,
        "resolved_batch_size": resolved_batch_size,
        "sparse_enabled": active.sparse_enabled,
        "sparse_model": active.sparse_model,
        "hybrid_enabled": active.hybrid_enabled,
        "rerank_enabled": active.rerank_enabled,
        "late_interaction_enabled": active.late_interaction_enabled,
        "late_interaction_configured": bool(active.late_interaction_runner and active.late_interaction_model_path),
        "image_embedding_model": active.image_embedding_model,
        "image_embedding_model_revision": active.image_embedding_model_revision,
        "image_search_enabled": active.image_search_enabled,
        "mps_cache_clear_enabled": os.getenv("MPS_CACHE_CLEAR_ENABLED", "0") == "1",
        "image_embedding_allowed": should_enable_image_embedding(),
        "memory_gb": round(_get_system_memory_gb(), 1),
    }


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once for CLI-style entrypoints."""
    settings = get_settings()
    chosen_level = (level or settings.log_level).upper()
    numeric_level = getattr(logging, chosen_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _int_from_env(name: str, default: int, min_value: int = 1, max_value: int | None = None) -> int:
    """Parse an integer env var, clamping to [min_value, max_value] or returning default."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
        if value < min_value:
            return min_value
        if max_value is not None and value > max_value:
            return max_value
        return value
    except ValueError:
        return default


def _runtime_path_from_env(name: str, default: str, *, field_name: str) -> str:
    """Resolve a runtime path from its environment variable or default."""
    value = os.getenv(name, default)
    return str(validate_runtime_path(value, field_name=field_name))


def _runtime_path_override(value: str, *, field_name: str) -> str:
    """Apply an explicit path override while preserving the configured default."""
    return str(validate_runtime_path(value, field_name=field_name))


def _model_identity_from_env(
    *,
    model_variable: str,
    revision_variable: str,
    default_model: str,
    default_revision: str,
) -> tuple[str, str]:
    """Resolve a model and immutable revision without accepting a floating override."""
    model = os.getenv(model_variable, default_model).strip()
    revision_was_set = revision_variable in os.environ
    revision = os.getenv(revision_variable, default_revision)
    if not model:
        raise ValueError(f"{model_variable} must not be empty")
    if model != default_model and not revision_was_set:
        raise ValueError(f"{revision_variable} is required when overriding {model_variable}")
    return model, _require_model_revision(revision, variable_name=revision_variable)


def _require_model_revision(value: str, *, variable_name: str) -> str:
    """Require a full commit hash so remote model identity cannot float."""
    revision = value.strip()
    if _IMMUTABLE_MODEL_REVISION.fullmatch(revision) is None:
        raise ValueError(f"{variable_name} must be a full 40-character hexadecimal commit hash")
    return revision


def _bool_from_env(name: str, default: bool) -> bool:
    """Parse common truthy and falsey environment values with a safe default."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes")


def _reject_removed_environment_variables() -> None:
    """Fail loudly for removed storage and reranking configuration."""
    removed = [name for name in ("CHROMADB_PATH", "COLLECTION_NAME", "COLBERT_RERANK_ENABLED", "MPS_FLOAT16") if os.getenv(name)]
    if removed:
        joined = ", ".join(removed)
        raise ValueError(
            f"Removed environment variable(s): {joined}. "
            "Use VECTOR_INDEX_PATH for vector storage and current documented model settings."
        )
