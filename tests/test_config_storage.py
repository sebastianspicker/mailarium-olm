"""Resolves runtime settings, device profiles, and model revisions while rejecting unsafe configured paths."""

import os

import pytest

from mailarium.repo_paths import repo_root


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("VECTOR_INDEX_PATH", raising=False)
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL_REVISION", raising=False)
    monkeypatch.delenv("IMAGE_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_EMBEDDING_MODEL_REVISION", raising=False)
    monkeypatch.delenv("TOP_K", raising=False)
    monkeypatch.delenv("RAG_SCOPE", raising=False)
    monkeypatch.delenv("DEVICE", raising=False)

    from mailarium.config import Settings

    settings = Settings.from_env()
    assert settings.vector_index_path == str(repo_root() / "data/vector-index")
    assert settings.sqlite_path == str(repo_root() / "data/email_metadata.db")
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_model_revision == "5617a9f61b028005a4858fdac845db406aefb181"
    assert settings.image_embedding_model_revision == "3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab"
    assert settings.top_k == 10
    assert settings.rag_scope == "general"
    assert settings.device == "auto"


def test_settings_normalizes_configured_rag_scope(monkeypatch):
    monkeypatch.setenv("RAG_SCOPE", "  Customer   Support ")

    from mailarium.config import Settings

    assert Settings.from_env().rag_scope == "customer support"


def test_settings_rejects_invalid_rag_scope(monkeypatch):
    monkeypatch.setenv("RAG_SCOPE", "\x07invalid")

    from mailarium.config import Settings

    with pytest.raises(ValueError, match="control characters"):
        Settings.from_env()


def test_settings_top_k_clamps_below_min_env(monkeypatch):
    monkeypatch.setenv("TOP_K", "0")

    from mailarium.config import Settings

    settings = Settings.from_env()
    assert settings.top_k == 1  # clamped to min_value, not default


def test_settings_top_k_clamps_large_env(monkeypatch):
    monkeypatch.setenv("TOP_K", "5000")

    from mailarium.config import Settings

    settings = Settings.from_env()
    assert settings.top_k == 1000


def test_resolve_runtime_settings_uses_defaults(monkeypatch):
    monkeypatch.delenv("VECTOR_INDEX_PATH", raising=False)
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    from mailarium.config import resolve_runtime_settings

    settings = resolve_runtime_settings()
    assert settings.vector_index_path == str(repo_root() / "data/vector-index")
    assert settings.sqlite_path == str(repo_root() / "data/email_metadata.db")
    assert settings.embedding_model == "BAAI/bge-m3"


def test_resolve_runtime_settings_applies_overrides(tmp_path):
    from mailarium.config import resolve_runtime_settings

    vector_index_path = repo_root() / "tests/private" / tmp_path.name / "index"
    settings = resolve_runtime_settings(
        vector_index_path=str(vector_index_path),
        embedding_model="mini-test-model",
        embedding_model_revision="a" * 40,
    )
    assert settings.vector_index_path == str(vector_index_path)
    assert settings.embedding_model == "mini-test-model"
    assert settings.embedding_model_revision == "a" * 40


def test_custom_model_requires_explicit_revision(monkeypatch):
    from mailarium.config import Settings, resolve_runtime_settings

    monkeypatch.setenv("EMBEDDING_MODEL", "custom/model")
    monkeypatch.delenv("EMBEDDING_MODEL_REVISION", raising=False)
    with pytest.raises(ValueError, match="EMBEDDING_MODEL_REVISION"):
        Settings.from_env()

    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(ValueError, match="embedding_model_revision"):
        resolve_runtime_settings(embedding_model="custom/model")


@pytest.mark.parametrize("revision", ["", "main", "v1.0.0", "abc123", "g" * 40])
def test_custom_model_requires_full_commit_revision(monkeypatch, revision):
    from mailarium.config import Settings

    monkeypatch.setenv("EMBEDDING_MODEL", "custom/model")
    monkeypatch.setenv("EMBEDDING_MODEL_REVISION", revision)
    with pytest.raises(ValueError, match="full 40-character hexadecimal commit hash"):
        Settings.from_env()


def test_resolve_runtime_settings_rejects_runtime_paths_outside_roots():
    from mailarium.config import resolve_runtime_settings

    try:
        resolve_runtime_settings(sqlite_path="/etc/passwd")
    except ValueError as exc:
        assert "allowed runtime roots" in str(exc)
    else:
        raise AssertionError("resolve_runtime_settings accepted a runtime path outside allowed roots")


def test_settings_from_env_rejects_runtime_paths_outside_roots(monkeypatch):
    from mailarium.config import Settings

    monkeypatch.setenv("SQLITE_PATH", "/etc/passwd")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "allowed runtime roots" in str(exc)
    else:
        raise AssertionError("Settings.from_env accepted a runtime path outside allowed roots")


def test_settings_from_env_resolves_default_runtime_paths_from_repo_root(monkeypatch, tmp_path):
    monkeypatch.delenv("VECTOR_INDEX_PATH", raising=False)
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)

    from mailarium.config import Settings

    settings = Settings.from_env()

    assert settings.vector_index_path == str(repo_root() / "data/vector-index")
    assert settings.sqlite_path == str(repo_root() / "data/email_metadata.db")


def test_settings_from_env_retains_explicit_absolute_runtime_path(monkeypatch, tmp_path):
    explicit_sqlite_path = repo_root() / "data" / "explicit-email-metadata.db"
    monkeypatch.setenv("SQLITE_PATH", str(explicit_sqlite_path))
    monkeypatch.chdir(tmp_path)

    from mailarium.config import Settings

    settings = Settings.from_env()

    assert settings.sqlite_path == str(explicit_sqlite_path)


def test_settings_device_from_env(monkeypatch):
    monkeypatch.setenv("DEVICE", "cpu")

    from mailarium.config import Settings

    settings = Settings.from_env()
    assert settings.device == "cpu"


@pytest.mark.parametrize(
    "environment_name",
    ["CHROMADB_PATH", "COLLECTION_NAME", "COLBERT_RERANK_ENABLED", "MPS_FLOAT16"],
)
def test_settings_rejects_removed_environment_names(monkeypatch, environment_name):
    from mailarium.config import Settings

    monkeypatch.setenv(environment_name, "true")
    with pytest.raises(ValueError, match="Removed environment variable"):
        Settings.from_env()


def test_runtime_profile_quality_sets_retrieval_defaults(monkeypatch):
    from mailarium.config import Settings

    monkeypatch.setenv("RUNTIME_PROFILE", "quality")
    for var in [
        "RERANK_ENABLED",
        "HYBRID_ENABLED",
        "SPARSE_ENABLED",
        "LATE_INTERACTION_ENABLED",
        "EMBEDDING_LOAD_MODE",
    ]:
        monkeypatch.delenv(var, raising=False)

    settings = Settings.from_env()
    assert settings.runtime_profile == "quality"
    assert settings.rerank_enabled is True
    assert settings.hybrid_enabled is True
    assert settings.sparse_enabled is False
    assert settings.late_interaction_enabled is False
    assert settings.embedding_load_mode == "auto"


def test_runtime_profile_offline_test_sets_local_only(monkeypatch):
    from mailarium.config import Settings

    monkeypatch.setenv("RUNTIME_PROFILE", "offline-test")
    monkeypatch.delenv("EMBEDDING_LOAD_MODE", raising=False)
    settings = Settings.from_env()
    assert settings.runtime_profile == "offline-test"
    assert settings.embedding_load_mode == "local_only"


def test_env_override_wins_over_runtime_profile(monkeypatch):
    from mailarium.config import Settings

    monkeypatch.setenv("RUNTIME_PROFILE", "quality")
    monkeypatch.setenv("RERANK_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_LOAD_MODE", "download")
    settings = Settings.from_env()
    assert settings.rerank_enabled is False
    assert settings.embedding_load_mode == "download"


# --- resolve_device tests ---


def test_resolve_device_explicit_passthrough():
    from mailarium.config import resolve_device

    assert resolve_device("cpu") == "cpu"
    assert resolve_device("mps") == "mps"
    assert resolve_device("cuda") == "cuda"


def _install_fake_torch(monkeypatch, *, mps_available: bool, cuda_available: bool) -> None:
    import types

    mock_torch = types.ModuleType("torch")
    mock_backends = types.ModuleType("torch.backends")
    mock_backends.mps = types.SimpleNamespace(is_available=lambda: mps_available)
    mock_torch.backends = mock_backends
    mock_torch.cuda = types.SimpleNamespace(is_available=lambda: cuda_available)
    monkeypatch.setitem(__import__("sys").modules, "torch", mock_torch)


def test_resolve_device_auto_mps(monkeypatch):
    """resolve_device('auto') should return 'mps' when MPS is available."""
    _install_fake_torch(monkeypatch, mps_available=True, cuda_available=False)

    from mailarium.config import resolve_device

    assert resolve_device("auto") == "mps"


def test_resolve_device_auto_cuda(monkeypatch):
    """resolve_device('auto') should return 'cuda' when only CUDA is available."""
    _install_fake_torch(monkeypatch, mps_available=False, cuda_available=True)

    from mailarium.config import resolve_device

    assert resolve_device("auto") == "cuda"


def test_resolve_device_auto_cpu_fallback(monkeypatch):
    """resolve_device('auto') should fall back to 'cpu' when nothing is available."""
    _install_fake_torch(monkeypatch, mps_available=False, cuda_available=False)

    from mailarium.config import resolve_device

    assert resolve_device("auto") == "cpu"


def test_resolve_device_auto_no_torch(monkeypatch):
    """resolve_device('auto') should return 'cpu' when torch is not installed."""
    monkeypatch.setitem(__import__("sys").modules, "torch", None)

    from mailarium.config import resolve_device

    assert resolve_device("auto") == "cpu"


def test_get_system_memory_gb_returns_positive():
    from mailarium.config import _get_system_memory_gb

    mem = _get_system_memory_gb()
    assert mem > 0


def test_resolve_embedding_batch_size_mps_memory_tiers(monkeypatch):
    from mailarium import config

    monkeypatch.setattr(config, "resolve_device", lambda _d: "mps")

    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 8.0)
    assert config.resolve_embedding_batch_size("mps") == 16

    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 16.0)
    assert config.resolve_embedding_batch_size("mps") == 32

    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 36.0)
    assert config.resolve_embedding_batch_size("mps") == 48

    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 64.0)
    assert config.resolve_embedding_batch_size("mps") == 48


def test_resolve_embedding_batch_size_mps_detection_fallback(monkeypatch):
    """When os.sysconf raises, _get_system_memory_gb returns 8.0 → MPS batch = 16."""
    from mailarium import config

    def _raise(*_a):
        raise ValueError("unsupported")

    monkeypatch.setattr(os, "sysconf", _raise)
    monkeypatch.setattr(config, "resolve_device", lambda _d: "mps")

    assert config._get_system_memory_gb() == 8.0
    assert config.resolve_embedding_batch_size("mps") == 16


def test_should_enable_image_embedding_low_memory(monkeypatch):
    from mailarium import config

    monkeypatch.delenv("IMAGE_EMBED_ALLOW_LOW_MEMORY", raising=False)
    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 16.0)
    assert config.should_enable_image_embedding() is False


def test_should_enable_image_embedding_override(monkeypatch):
    from mailarium import config

    monkeypatch.setenv("IMAGE_EMBED_ALLOW_LOW_MEMORY", "1")
    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 16.0)
    assert config.should_enable_image_embedding() is True


def test_resolve_runtime_summary_reports_effective_state(monkeypatch):
    from mailarium import config

    monkeypatch.setattr(config, "resolve_device", lambda _device: "mps")
    monkeypatch.setattr(config, "resolve_embedding_batch_size", lambda _device: 32)
    monkeypatch.setattr(config, "_get_system_memory_gb", lambda: 16.0)
    monkeypatch.delenv("MPS_CACHE_CLEAR_ENABLED", raising=False)

    settings = config.Settings(
        device="auto",
        runtime_profile="quality",
        sparse_enabled=True,
        hybrid_enabled=True,
        rerank_enabled=True,
        late_interaction_enabled=True,
        embedding_batch_size=0,
        embedding_load_mode="local_only",
    )
    summary = config.resolve_runtime_summary(settings)
    assert summary["runtime_profile"] == "quality"
    assert summary["resolved_device"] == "mps"
    assert summary["resolved_batch_size"] == 32
    assert summary["embedding_load_mode"] == "local_only"
    assert summary["image_embedding_allowed"] is False
