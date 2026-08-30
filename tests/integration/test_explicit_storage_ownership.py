"""Regression checks for explicit archive ownership at production boundaries."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from mailarium.archive import open_archive_database
from mailarium.archive.storage import get_vector_collection
from mailarium.retrieval.embedder import EmailEmbedder
from mailarium.retrieval.retriever import SearchEngine

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_PRODUCTION_FILES = (
    "mailarium/archive/__init__.py",
    "mailarium/archive/storage.py",
    "mailarium/runtime.py",
    "mailarium/retrieval/embedder.py",
    "mailarium/retrieval/retriever.py",
    "mailarium/mailbox/mailbox_service.py",
    "mailarium/ingestion/runtime.py",
    "mailarium/ingestion/reembedding.py",
    "mailarium/ingestion/maintenance.py",
    "mailarium/ingestion/attachment_reprocessing.py",
    "mailarium/ingestion/reset.py",
    "scripts/smoke/installed_wheel.py",
)
_LAZY_FALLBACK_FIELDS = {
    "_owned_database",
    "_shared_archive_database",
    "_email_db_checked",
    "_sparse_db_fallback",
}


def _raw_archive_constructor_calls(path: Path) -> list[tuple[str, int]]:
    """Return ``ArchiveDatabase(...)`` calls outside the allowed archive factory."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ArchiveDatabase":
            calls.append((path.name, node.lineno))
    return calls


def _factory_constructor_calls(path: Path) -> list[ast.Call]:
    """Return raw constructors located within the archive factory function."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    factory = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "open_archive_database")
    return [
        node
        for node in ast.walk(factory)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ArchiveDatabase"
    ]


def test_production_storage_creation_uses_only_the_archive_factory() -> None:
    """Production code has one raw archive constructor: the documented factory."""
    constructors = {relative: _raw_archive_constructor_calls(_REPOSITORY_ROOT / relative) for relative in _PRODUCTION_FILES}
    assert len(_factory_constructor_calls(_REPOSITORY_ROOT / "mailarium/archive/__init__.py")) == 1
    assert len(constructors["mailarium/archive/__init__.py"]) == 1
    assert all(not calls for relative, calls in constructors.items() if relative != "mailarium/archive/__init__.py")


def test_production_storage_has_no_lazy_database_fallback_fields() -> None:
    """Storage consumers retain no state that can silently create another archive."""
    fields: set[str] = set()
    for relative in _PRODUCTION_FILES:
        tree = ast.parse((_REPOSITORY_ROOT / relative).read_text(encoding="utf-8"))
        fields.update(node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute))
    assert not fields & _LAZY_FALLBACK_FIELDS


@pytest.mark.parametrize("constructor", [SearchEngine, EmailEmbedder, get_vector_collection])
def test_vector_storage_constructors_require_an_explicit_database(constructor) -> None:
    """Search and vector services cannot open archive state as a hidden side effect."""
    parameter = inspect.signature(constructor).parameters["database"]
    assert parameter.default is inspect.Parameter.empty


def test_vector_collection_writes_to_the_injected_archive_and_never_closes_it(tmp_path) -> None:
    """A real vector round trip proves collection binding and close ownership."""
    database = open_archive_database(str(tmp_path / "archive.db"))
    collection = get_vector_collection(
        database=database,
        vector_index_path=str(tmp_path / "vectors"),
        model_id="ownership-test",
        model_revision="v1",
    )
    try:
        collection.add(
            ids=["mail-1__chunk_0"],
            embeddings=[[1.0, 0.0]],
            documents=["canonical storage"],
            metadatas=[{"email_uid": "mail-1", "kind": "body"}],
        )
        assert database.conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0] == 1
        assert collection.query(query_embeddings=[[1.0, 0.0]], n_results=1)["ids"] == [["mail-1__chunk_0"]]
        collection.close()
        assert database.conn.execute("SELECT COUNT(*) FROM vector_chunks").fetchone()[0] == 1
    finally:
        database.close()
