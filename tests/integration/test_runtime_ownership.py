"""Integration checks for application-runtime archive ownership."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from mailarium.archive import ArchiveDatabase
from mailarium.runtime import ApplicationRuntime


def _runtime(monkeypatch, tmp_path) -> ApplicationRuntime:
    monkeypatch.setenv("MAILARIUM_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("MAILARIUM_ALLOWED_RUNTIME_ROOTS", raising=False)
    return ApplicationRuntime(
        sqlite_path="archive/archive.db",
        vector_index_path="vectors",
    )


def _assert_shared_archive(runtime: ApplicationRuntime, embedder) -> None:
    database = runtime.archive_database
    search = runtime.search_engine
    service = runtime.mailbox_service()

    assert database is not None
    assert service is not None
    assert search.email_db is database
    assert service.db is database
    assert search.collection._database is database
    assert search.image_collection._database is database
    assert embedder._sparse_db is database
    assert embedder.collection._database is database
    assert embedder.image_collection._database is database


def test_runtime_shares_archive_when_search_precedes_mailbox(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)

    search = runtime.search_engine
    service = runtime.mailbox_service()

    assert service is not None
    embedder = service.embedder_factory()
    try:
        assert search.email_db is runtime.archive_database
        _assert_shared_archive(runtime, embedder)
    finally:
        embedder.close()
        runtime.close()


def test_runtime_shares_archive_when_mailbox_precedes_search(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)

    service = runtime.mailbox_service(create_archive=True)

    assert service is not None
    embedder = service.embedder_factory()
    try:
        assert runtime.search_engine.email_db is runtime.archive_database
        _assert_shared_archive(runtime, embedder)
    finally:
        embedder.close()
        runtime.close()


def test_runtime_close_is_idempotent_and_closes_canonical_archive_once(monkeypatch, tmp_path) -> None:
    close_calls: list[ArchiveDatabase] = []
    original_close = ArchiveDatabase.close

    def close_spy(database: ArchiveDatabase) -> None:
        close_calls.append(database)
        original_close(database)

    monkeypatch.setattr(ArchiveDatabase, "close", close_spy)
    runtime = _runtime(monkeypatch, tmp_path)
    database = runtime.open_archive_database()
    search = runtime.search_engine
    assert runtime.mailbox_service() is not None

    runtime.close()
    runtime.close()

    assert close_calls == [database]
    assert search.collection._database is None
    with pytest.raises(RuntimeError, match="ApplicationRuntime is closed"):
        runtime.open_archive_database()


def test_concurrent_first_callers_share_one_runtime_generation_and_close_once(monkeypatch, tmp_path) -> None:
    runtime = _runtime(monkeypatch, tmp_path)
    calls = ("database", "search", "mailbox") * 4
    barrier = threading.Barrier(len(calls))

    def first_call(kind: str):
        assert barrier.wait(timeout=5) >= 0
        if kind == "database":
            return runtime.open_archive_database()
        if kind == "search":
            return runtime.search_engine
        return runtime.mailbox_service(create_archive=True)

    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        results = list(executor.map(first_call, calls))

    database = next(result for kind, result in zip(calls, results, strict=True) if kind == "database")
    search = next(result for kind, result in zip(calls, results, strict=True) if kind == "search")
    mailbox = next(result for kind, result in zip(calls, results, strict=True) if kind == "mailbox")
    assert mailbox is not None
    assert all(result is database for kind, result in zip(calls, results, strict=True) if kind == "database")
    assert all(result is search for kind, result in zip(calls, results, strict=True) if kind == "search")
    assert all(result is mailbox for kind, result in zip(calls, results, strict=True) if kind == "mailbox")
    assert search.email_db is database
    assert mailbox.db is database

    close_calls = {"database": 0, "search": 0, "mailbox": 0}
    for name, resource in (("database", database), ("search", search), ("mailbox", mailbox)):
        original_close = resource.close

        def close_spy(*, _name=name, _close=original_close) -> None:
            close_calls[_name] += 1
            _close()

        monkeypatch.setattr(resource, "close", close_spy)

    close_barrier = threading.Barrier(2)

    def close_runtime() -> None:
        assert close_barrier.wait(timeout=5) >= 0
        runtime.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _unused: close_runtime(), range(2)))

    assert close_calls == {"database": 1, "search": 1, "mailbox": 1}
    for state_method in (
        lambda: runtime.archive_database,
        runtime.open_archive_database,
        lambda: runtime.search_engine,
        lambda: runtime.mailbox_service(create_archive=True),
        runtime.__enter__,
    ):
        with pytest.raises(RuntimeError, match="ApplicationRuntime is closed"):
            state_method()
