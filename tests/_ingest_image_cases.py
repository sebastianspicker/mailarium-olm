# ruff: noqa: F401,F811,I001
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


def test_ingest_embed_images_enables_extract_attachments(monkeypatch):
    """embed_images=True should auto-enable extract_attachments."""
    import src.ingest as ingest_mod

    class _Email:
        def __init__(self, idx):
            self.idx = idx
            self.uid = f"uid-{idx}"
            self.attachment_contents = []

        def to_dict(self):
            return {"id": self.idx, "uid": self.uid}

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **kw: [_Email(1)])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email: [{"chunk_id": f"{email.get('uid', 'x')}-a"}],
    )

    # When embed_images=True, dry_run works without needing the embedder
    stats = ingest_mod.ingest("data/mock.olm", dry_run=True, embed_images=True)
    assert stats["extract_attachments"] is True
    assert stats["image_embeddings"] == 0


def test_ingest_embed_images_param_accepted(monkeypatch):
    """Verify embed_images param is accepted by ingest() function."""
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])

    stats = ingest_mod.ingest("data/mock.olm", dry_run=True, embed_images=False)
    assert stats["image_embeddings"] == 0


def test_ingest_stats_include_image_embeddings(monkeypatch):
    """Verify image_embeddings key exists in ingestion stats."""
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])

    stats = ingest_mod.ingest("data/mock.olm", dry_run=True)
    assert "image_embeddings" in stats


def test_ingest_embed_images_skipped_on_low_memory(monkeypatch):
    """Low-memory systems skip Visualized-BGE startup unless explicitly forced."""
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [])
    monkeypatch.setattr(ingest_mod, "should_enable_image_embedding", lambda: False)
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    stats = ingest_mod.ingest("data/mock.olm", dry_run=False, embed_images=True)
    assert stats["extract_attachments"] is True
    assert stats["image_embeddings"] == 0


def test_image_embedder_unavailable_marks_not_requested(monkeypatch, tmp_path):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["photo.png"]
    email.attachments = [
        {
            "name": "photo.png",
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [("photo.png", b"fake-image")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "should_enable_image_embedding", lambda: True)
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr("src.attachment_extractor._get_image_embedder", lambda: type("Probe", (), {"is_available": False})())
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "test.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, embed_images=True)

    assert stats["image_embeddings"] == 0
    db = EmailDatabase(sqlite_file)
    row = db.conn.execute("SELECT image_status FROM email_ingest_state WHERE email_uid = ?", (email.uid,)).fetchone()
    assert row is not None
    assert row["image_status"] == "not_requested"
    db.close()


def test_embed_pipeline_error_propagation():
    """Errors in the consumer thread should be re-raised by finish()."""
    from src.ingest import _EmbedPipeline

    class _BrokenEmbedder:
        def add_chunks(self, chunks, **_kw):
            raise RuntimeError("embed failed")

    pipeline = _EmbedPipeline(
        embedder=_BrokenEmbedder(),
        email_db=None,
        entity_extractor_fn=None,
        batch_size=100,
    )
    pipeline.start()
    pipeline.submit(["fake_chunk"], [])

    with pytest.raises(RuntimeError, match="embed failed"):
        pipeline.finish()


def test_embed_pipeline_empty_batch():
    """Submitting empty lists should not crash."""
    from src.ingest import _EmbedPipeline

    pipeline = _EmbedPipeline(
        embedder=None,
        email_db=None,
        entity_extractor_fn=None,
        batch_size=100,
    )
    pipeline.start()
    pipeline.submit([], [])  # Should be no-op (filtered out)
    pipeline.finish()
    assert pipeline.chunks_added == 0
    assert pipeline.sqlite_inserted == 0
