import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = ("tests._custody_cases",)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _DummyCollection:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []
        self.metadata: dict[str, Any] = {}

    def modify(self, metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        if metadata:
            self.metadata.update(metadata)

    def add(self, ids, embeddings, documents, metadatas):
        for idx, chunk_id in enumerate(ids):
            self._items.append(
                {
                    "id": chunk_id,
                    "embedding": embeddings[idx],
                    "document": documents[idx],
                    "metadata": metadatas[idx],
                }
            )

    def upsert(self, ids, embeddings, documents, metadatas):
        existing_ids = {item["id"] for item in self._items}
        for idx, chunk_id in enumerate(ids):
            item = {
                "id": chunk_id,
                "embedding": embeddings[idx],
                "document": documents[idx],
                "metadata": metadatas[idx],
            }
            if chunk_id in existing_ids:
                self._items = [it if it["id"] != chunk_id else item for it in self._items]
            else:
                self._items.append(item)

    def count(self):
        return len(self._items)

    def get(self, include=None, limit=None, offset=0):
        include = include or []
        limit = len(self._items) if limit is None else limit
        batch = self._items[offset : offset + limit]
        out = {"ids": [item["id"] for item in batch]}
        if "metadatas" in include:
            out["metadatas"] = [item["metadata"] for item in batch]
        if "documents" in include:
            out["documents"] = [item["document"] for item in batch]
        return out

    def query(self, query_embeddings, n_results, include=None, where=None):
        include = include or []
        candidates = self._items
        if where:
            candidates = [item for item in candidates if _matches_where(item["metadata"], where)]

        picked = candidates[:n_results]
        response = {"ids": [[item["id"] for item in picked]]}
        if "documents" in include:
            response["documents"] = [[item["document"] for item in picked]]
        if "metadatas" in include:
            response["metadatas"] = [[item["metadata"] for item in picked]]
        if "distances" in include:
            response["distances"] = [[0.1 for _ in picked]]
        return response


def _matches_where(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
    for key, value in where.items():
        if isinstance(value, dict) and "$eq" in value:
            if metadata.get(key) != value["$eq"]:
                return False
        elif metadata.get(key) != value:
            return False
    return True


class _DummyClient:
    def __init__(self, path=None, settings=None):
        self._collection = _DummyCollection()

    def get_or_create_collection(self, name, metadata=None):
        return self._collection

    def delete_collection(self, name):
        self._collection = _DummyCollection()


class _ChromaSettings:
    def __init__(self, anonymized_telemetry=False):
        self.anonymized_telemetry = anonymized_telemetry


def _ensure_chromadb_stub() -> None:
    if "chromadb" in sys.modules:
        return

    chromadb = types.ModuleType("chromadb")
    chromadb.PersistentClient = _DummyClient
    sys.modules["chromadb"] = chromadb

    chromadb_config = types.ModuleType("chromadb.config")
    chromadb_config.Settings = _ChromaSettings
    sys.modules["chromadb.config"] = chromadb_config


def _ensure_sentence_transformers_stub() -> None:
    if "sentence_transformers" in sys.modules:
        return

    sentence_transformers = types.ModuleType("sentence_transformers")

    class SentenceTransformer:
        def __init__(self, model_name, device=None):
            self.model_name = model_name
            self.device = device

        def encode(self, texts, show_progress_bar=False, batch_size=32):
            return [[0.1, 0.2, 0.3] for _ in texts]

    class CrossEncoder:
        def __init__(self, model_name=None):
            self.model_name = model_name

        def predict(self, pairs, show_progress_bar=False):
            return [0.5] * len(pairs)

    sentence_transformers.SentenceTransformer = SentenceTransformer
    sentence_transformers.CrossEncoder = CrossEncoder
    sys.modules["sentence_transformers"] = sentence_transformers


def _ensure_mcp_stub() -> None:
    if "mcp.server.fastmcp" in sys.modules:
        return

    mcp_mod = types.ModuleType("mcp")
    server_mod = types.ModuleType("mcp.server")
    fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    mcp_types_mod = types.ModuleType("mcp.types")

    class FastMCP:
        def __init__(self, name):
            self.name = name

        def tool(self, *args, **kwargs):
            def _decorator(fn):
                return fn

            return _decorator

        def run(self):
            return None

    class ToolAnnotations:
        def __init__(
            self,
            title=None,
            readOnlyHint=None,
            destructiveHint=None,
            idempotentHint=None,
            openWorldHint=None,
        ):
            self.title = title
            self.readOnlyHint = readOnlyHint
            self.destructiveHint = destructiveHint
            self.idempotentHint = idempotentHint
            self.openWorldHint = openWorldHint

    fastmcp_mod.FastMCP = FastMCP
    mcp_types_mod.ToolAnnotations = ToolAnnotations
    sys.modules["mcp"] = mcp_mod
    sys.modules["mcp.server"] = server_mod
    sys.modules["mcp.server.fastmcp"] = fastmcp_mod
    sys.modules["mcp.types"] = mcp_types_mod


_ensure_chromadb_stub()
_ensure_sentence_transformers_stub()
_ensure_mcp_stub()


class FakeMultiVectorEmbedder:
    """Offline-safe embedder stub for unit tests that do not need live models."""

    def __init__(self, **kwargs: Any) -> None:
        self.model_name = kwargs.get("model_name", "fake-bge-m3")
        self.device = kwargs.get("device", "cpu")
        self.batch_size = kwargs.get("batch_size", 16)
        self.load_mode = kwargs.get("load_mode", "local_only")
        self.has_sparse = kwargs.get("sparse_enabled", False)
        self.has_colbert = kwargs.get("colbert_enabled", False)
        self._model = object()

    def encode(self, texts, **kwargs: Any):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def encode_dense(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def encode_all(self, texts):
        from src.multi_vector_embedder import MultiVectorResult

        dense = [[0.1, 0.2, 0.3] for _ in texts]
        sparse = [{1: 0.5} for _ in texts] if self.has_sparse else None
        colbert = [None for _ in texts] if self.has_colbert else None
        return MultiVectorResult(dense=dense, sparse=sparse, colbert=colbert)

    def warmup(self) -> None:
        return None

    def runtime_summary(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "device": self.device,
            "batch_size": self.batch_size,
            "load_mode": self.load_mode,
            "backend": "fake",
            "has_sparse": self.has_sparse,
            "has_colbert": self.has_colbert,
        }


@pytest.fixture
def stub_multi_vector_embedder(monkeypatch):
    """Replace MultiVectorEmbedder with an offline-safe fake in selected modules."""

    def _apply(module):
        monkeypatch.setattr(module, "MultiVectorEmbedder", FakeMultiVectorEmbedder)
        return FakeMultiVectorEmbedder

    return _apply


def _close_sqlite_handle(candidate: object) -> None:
    close = getattr(candidate, "close", None)
    if callable(close):
        try:
            close()
        except sqlite3.Error:
            return
        return

    conn = getattr(candidate, "conn", None)
    if isinstance(conn, sqlite3.Connection):
        try:
            conn.close()
        except sqlite3.Error:
            return
        try:
            candidate.conn = None
        except AttributeError:
            return


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Close lingering in-memory SQLite handles held by test doubles."""
    del session, exitstatus
    for module in list(sys.modules.values()):
        if module is None or not getattr(module, "__name__", "").startswith("tests."):
            continue
        module_dict = getattr(module, "__dict__", {})
        for value in module_dict.values():
            if isinstance(value, sqlite3.Connection):
                try:
                    value.close()
                except sqlite3.Error:
                    pass
                continue
            mock_db = getattr(value, "_email_db", None)
            if mock_db is not None:
                _close_sqlite_handle(mock_db)
            helper_db = getattr(value, "_db", None)
            if helper_db is not None:
                _close_sqlite_handle(helper_db)
            conn = getattr(value, "conn", None)
            if isinstance(conn, sqlite3.Connection):
                _close_sqlite_handle(value)


@pytest.fixture(autouse=True)
def allow_tmp_output_roots_for_tests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Allow each test's temp workspace as an explicit output root."""

    existing = os.environ.get("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", "")
    roots = [str(tmp_path), tempfile.gettempdir()]
    if existing:
        roots.append(existing)
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_OUTPUT_ROOTS", os.pathsep.join(roots))


@pytest.fixture(autouse=True)
def allow_tmp_local_read_roots_for_tests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Allow temp workspaces as explicit local-read roots during tests."""

    existing = os.environ.get("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", "")
    roots = [str(tmp_path), tempfile.gettempdir()]
    if existing:
        roots.append(existing)
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_LOCAL_READ_ROOTS", os.pathsep.join(dict.fromkeys(roots)))


@pytest.fixture(autouse=True)
def allow_tmp_runtime_roots_for_tests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Allow temp workspaces as explicit runtime-reset roots during tests."""

    existing = os.environ.get("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", "")
    roots = [str(tmp_path), tempfile.gettempdir()]
    if existing:
        roots.append(existing)
    monkeypatch.setenv("EMAIL_RAG_ALLOWED_RUNTIME_ROOTS", os.pathsep.join(dict.fromkeys(roots)))


@pytest.fixture(autouse=True)
def reset_ephemeral_tool_state():
    """Keep module-level MCP tool state isolated between tests."""
    from src import mcp_server
    from src.scan_session import _sessions
    from src.tools import search as search_tools

    _close_sqlite_handle(getattr(mcp_server, "_email_db", None))
    mcp_server._email_db = None
    mcp_server._retriever = None
    _sessions.clear()
    search_tools._deps = mcp_server.ToolDeps()
    yield
    _close_sqlite_handle(getattr(mcp_server, "_email_db", None))
    mcp_server._email_db = None
    mcp_server._retriever = None
    _sessions.clear()
    search_tools._deps = mcp_server.ToolDeps()
