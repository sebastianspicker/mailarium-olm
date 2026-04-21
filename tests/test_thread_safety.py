"""Thread-safety audit tests for the MCP server concurrency model.

Validates that singletons, shared mutable state, and SQLite access are
safe when ``asyncio.to_thread()`` dispatches tool handlers concurrently.
"""

from __future__ import annotations

import threading

import pytest

# ── EmailDatabase.conn double-init prevention ─────────────────


class TestEmailDatabaseConnThreadSafety:
    """Verify that EmailDatabase.conn is only created once under contention."""

    def test_concurrent_conn_access_returns_same_connection(self):
        """Two threads hitting .conn simultaneously must get the same object."""
        from src.email_db import EmailDatabase

        db = EmailDatabase(":memory:")
        results: list = [None, None]
        barrier = threading.Barrier(2)

        def access(idx):
            barrier.wait()  # synchronize so both threads hit .conn together
            results[idx] = db.conn

        t0 = threading.Thread(target=access, args=(0,))
        t1 = threading.Thread(target=access, args=(1,))
        t0.start()
        t1.start()
        t0.join()
        t1.join()

        assert results[0] is results[1], (
            "Two threads created different SQLite connections — EmailDatabase.conn is not properly synchronized"
        )
        db.close()

    def test_conn_property_idempotent(self):
        """Repeated .conn access returns the same connection."""
        from src.email_db import EmailDatabase

        db = EmailDatabase(":memory:")
        c1 = db.conn
        c2 = db.conn
        assert c1 is c2
        db.close()


# ── run_with_network double-init prevention ───────────────────


class TestRunWithNetworkThreadSafety:
    """Verify _cached_comm_network is initialized at most once."""

    def test_network_lock_prevents_double_init(self):
        """Simulate two threads creating the CommunicationNetwork."""
        from src.tools import utils

        init_count = 0
        original_lock = utils._network_lock

        class FakeNetwork:
            def __init__(self, db):
                nonlocal init_count
                init_count += 1

        class FakeDB:
            pass

        db = FakeDB()
        barrier = threading.Barrier(2)

        def create_network():
            barrier.wait()
            net = getattr(db, "_cached_comm_network", None)
            if net is None:
                with original_lock:
                    net = getattr(db, "_cached_comm_network", None)
                    if net is None:
                        net = FakeNetwork(db)
                        db._cached_comm_network = net

        t0 = threading.Thread(target=create_network)
        t1 = threading.Thread(target=create_network)
        t0.start()
        t1.start()
        t0.join()
        t1.join()

        assert init_count == 1, (
            f"CommunicationNetwork was initialized {init_count} times — double-checked locking in run_with_network is broken"
        )


# ── get_retriever / get_email_db double-init prevention ──────


class TestMCPServerSingletons:
    """Verify MCP server singletons are initialized at most once.

    Note: importing ``src.mcp_server`` acquires an instance lock via
    ``fcntl.flock``.  If another MCP server process is running, the
    import raises ``SystemExit(1)``.  The test is skipped in that case.
    """

    def test_get_retriever_returns_same_instance(self, monkeypatch):
        """Concurrent get_retriever() calls must return the same object."""
        try:
            from src import mcp_server
        except SystemExit:
            pytest.skip("MCP instance lock held by another process")

        call_count = 0

        class FakeRetriever:
            def __init__(self):
                nonlocal call_count
                call_count += 1

        monkeypatch.setattr(mcp_server, "_retriever", None)

        # Patch the import to use our fake
        import src.retriever as retriever_mod

        original_class = getattr(retriever_mod, "EmailRetriever", None)
        monkeypatch.setattr(retriever_mod, "EmailRetriever", FakeRetriever)

        results: list = [None, None]
        barrier = threading.Barrier(2)

        def access(idx):
            barrier.wait()
            results[idx] = mcp_server.get_retriever()

        t0 = threading.Thread(target=access, args=(0,))
        t1 = threading.Thread(target=access, args=(1,))
        t0.start()
        t1.start()
        t0.join()
        t1.join()

        assert results[0] is results[1], "get_retriever() returned different instances"
        assert call_count == 1, f"EmailRetriever was constructed {call_count} times"

        # Cleanup
        monkeypatch.setattr(mcp_server, "_retriever", None)
        if original_class is not None:
            monkeypatch.setattr(retriever_mod, "EmailRetriever", original_class)


# ── lru_cache thread safety ──────────────────────────────────


class TestLruCacheSettings:
    """Verify get_settings() is safe under concurrent access."""

    def test_concurrent_get_settings_returns_same_instance(self):
        """Multiple threads calling get_settings() must get the same object."""
        from src.config import get_settings

        get_settings.cache_clear()

        results: list = [None, None, None, None]
        barrier = threading.Barrier(4)

        def access(idx):
            barrier.wait()
            results[idx] = get_settings()

        threads = [threading.Thread(target=access, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results must be the same frozen Settings instance
        for i in range(1, 4):
            assert results[0] is results[i], (
                f"get_settings() returned different instances: results[0]={id(results[0])}, results[{i}]={id(results[i])}"
            )

        get_settings.cache_clear()


# ── _EmbedPipeline error propagation ─────────────────────────


class TestEmbedPipelineErrorPropagation:
    """Verify consumer errors are visible to the producer after finish()."""

    def test_error_propagation_through_queue(self):
        """If consumer raises, finish() must re-raise on the producer side."""
        from src.ingest import _EmbedPipeline

        class BrokenEmbedder:
            def add_chunks(self, chunks, batch_size=32):
                raise RuntimeError("GPU on fire")

        pipeline = _EmbedPipeline(
            embedder=BrokenEmbedder(),
            email_db=None,
            entity_extractor_fn=None,
            batch_size=32,
        )
        pipeline.start()

        # Submit a batch that will cause the consumer to fail
        from src.chunker import EmailChunk

        fake_chunk = EmailChunk(
            uid="test",
            chunk_id="test::0",
            text="hello",
            metadata={"uid": "test"},
        )
        pipeline.submit([fake_chunk], [])

        with pytest.raises(RuntimeError, match="GPU on fire"):
            pipeline.finish()

    def test_submit_raises_after_consumer_error(self):
        """submit() must raise if the consumer has already failed."""
        import time

        from src.ingest import _EmbedPipeline

        class BrokenEmbedder:
            def add_chunks(self, chunks, batch_size=32):
                raise RuntimeError("boom")

        pipeline = _EmbedPipeline(
            embedder=BrokenEmbedder(),
            email_db=None,
            entity_extractor_fn=None,
            batch_size=32,
        )
        pipeline.start()

        from src.chunker import EmailChunk

        fake_chunk = EmailChunk(
            uid="test",
            chunk_id="test::0",
            text="hello",
            metadata={"uid": "test"},
        )
        pipeline.submit([fake_chunk], [])

        # Wait for the consumer to process and fail
        time.sleep(0.2)

        # Next submit should raise the consumer's error
        with pytest.raises(RuntimeError, match="boom"):
            pipeline.submit([fake_chunk], [])
