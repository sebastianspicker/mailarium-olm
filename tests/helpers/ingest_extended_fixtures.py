"""Fake ingest dependencies, email records, and import blockers for ingest tests."""

from unittest.mock import MagicMock

from mailarium.parse_olm import Email

# ── Helpers ──────────────────────────────────────────────────────────


def _make_email(idx, body_text="Body text that is long enough for analytics processing and detection"):
    """Build deterministic email data without external services."""
    return Email(
        message_id=f"<msg{idx}@test.com>",
        subject=f"Subject {idx}",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date=f"2024-01-0{idx}T10:00:00",
        body_text=body_text,
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


class _MockEmbedder:
    """Test double carrying deterministic MockEmbedder state for focused unit tests."""

    def __init__(self, **_kw):
        """Implement the init behavior exposed by the _MockEmbedder test double."""
        self.vector_index_path = "mock"
        self.model_name = "mock"
        self._count = 0
        self.collection = MagicMock()
        self.collection.metadata = {"hnsw:space": "cosine"}

    def count(self):
        """Implement the count behavior exposed by the _MockEmbedder test double."""
        return self._count

    def add_chunks(self, chunks, **_kw):
        """Implement the add chunks behavior exposed by the _MockEmbedder test double."""
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        """Implement the set sparse db behavior exposed by the _MockEmbedder test double."""

    def warmup(self):
        """Implement the warmup behavior exposed by the _MockEmbedder test double."""

    def close(self):
        """Implement the close behavior exposed by the _MockEmbedder test double."""

    def get_existing_ids(self, refresh=False):
        """Implement the get existing ids behavior exposed by the _MockEmbedder test double."""
        return set()

    def delete_chunks_by_uid(self, uid):
        """Implement the delete chunks by uid behavior exposed by the _MockEmbedder test double."""
        return 0

    def upsert_chunks(self, chunks, batch_size=100):
        """Implement the upsert chunks behavior exposed by the _MockEmbedder test double."""
        return len(chunks)


class _MockEmailDB:
    """Lightweight mock for EmailDatabase used in pipeline tests."""

    def __init__(self):
        """Implement the init behavior exposed by the _MockEmailDB test double."""
        self.conn = MagicMock()
        self._inserted = []
        self._entities = []
        self._analytics = []
        self._pending = []
        self._completed = []
        self._failed = {}

    def insert_emails_batch(self, emails, ingestion_run_id=None, commit=True):
        """Implement the insert emails batch behavior exposed by the _MockEmailDB test double."""
        uids = [e.uid for e in emails]
        self._inserted.extend(uids)
        return set(uids)

    def insert_entities_batch(self, uid, entities, commit=True, **kwargs):
        """Implement the insert entities batch behavior exposed by the _MockEmailDB test double."""
        self._entities.extend(entities)

    def update_analytics_batch(self, rows, commit=True):
        """Implement the update analytics batch behavior exposed by the _MockEmailDB test double."""
        self._analytics.extend(rows)
        return len(rows)

    def mark_ingest_batch_pending(self, rows, commit=True):
        """Implement the mark ingest batch pending behavior exposed by the _MockEmailDB test double."""
        self._pending = list(rows)

    def mark_ingest_batch_completed(self, rows, commit=True):
        """Implement the mark ingest batch completed behavior exposed by the _MockEmailDB test double."""
        self._completed = list(rows)

    def mark_ingest_batch_failed(self, email_uids, *, error_message, commit=True):
        """Implement the mark ingest batch failed behavior exposed by the _MockEmailDB test double."""
        self._failed = {"email_uids": list(email_uids), "error_message": error_message}

    def email_exists(self, uid):
        """Implement the email exists behavior exposed by the _MockEmailDB test double."""
        return uid in self._inserted

    def email_count(self):
        """Implement the email count behavior exposed by the _MockEmailDB test double."""
        return len(self._inserted)

    def close(self):
        """Implement the close behavior exposed by the _MockEmailDB test double."""


def _block_import(module_name):
    """Return an __import__ replacement that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _mock_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"blocked {module_name}")
        return real_import(name, *args, **kwargs)

    return _mock_import
