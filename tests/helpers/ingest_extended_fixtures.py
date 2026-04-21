# ruff: noqa: F401
"""Extended tests for src/ingest.py to increase coverage from ~73% to >=85%.

Covers: reingest paths, _reset_index, _resolve_entity_extractor,
_auto_download_spacy_models, _checkpoint_wal, _NoOpProgressBar,
_make_progress_bar, _hash_file_sha256, pipeline edge cases,
main() dispatch branches, attachment processing, and more.
"""

import argparse
import types
from unittest.mock import MagicMock, patch

import pytest

from src.ingest import (
    _auto_download_spacy_models,
    _EmbedPipeline,
    _hash_file_sha256,
    _make_progress_bar,
    _NoOpProgressBar,
    _resolve_entity_extractor,
    format_ingestion_summary,
    main,
    parse_args,
    reembed,
    reingest_analytics,
    reingest_bodies,
    reingest_metadata,
)
from src.parse_olm import Email

# ── Helpers ──────────────────────────────────────────────────────────


def _make_email(idx, body_text="Body text that is long enough for analytics processing and detection"):
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
    def __init__(self, **_kw):
        self.chromadb_path = "mock"
        self.model_name = "mock"
        self._count = 0
        self.collection = MagicMock()
        self.collection.metadata = {"hnsw:space": "cosine"}

    def count(self):
        return self._count

    def add_chunks(self, chunks, **_kw):
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        pass

    def warmup(self):
        pass

    def close(self):
        pass

    def get_existing_ids(self, refresh=False):
        return set()

    def delete_chunks_by_uid(self, uid):
        return 0

    def upsert_chunks(self, chunks, batch_size=100):
        return len(chunks)


class _MockEmailDB:
    """Lightweight mock for EmailDatabase used in pipeline tests."""

    def __init__(self):
        self.conn = MagicMock()
        self._inserted = []
        self._entities = []
        self._analytics = []
        self._pending = []
        self._completed = []
        self._failed = {}

    def insert_emails_batch(self, emails, ingestion_run_id=None, commit=True):
        uids = [e.uid for e in emails]
        self._inserted.extend(uids)
        return set(uids)

    def insert_entities_batch(self, uid, entities, commit=True, **kwargs):
        self._entities.extend(entities)

    def update_analytics_batch(self, rows, commit=True):
        self._analytics.extend(rows)
        return len(rows)

    def mark_ingest_batch_pending(self, rows, commit=True):
        self._pending = list(rows)

    def mark_ingest_batch_completed(self, rows, commit=True):
        self._completed = list(rows)

    def mark_ingest_batch_failed(self, email_uids, *, error_message, commit=True):
        self._failed = {"email_uids": list(email_uids), "error_message": error_message}

    def email_exists(self, uid):
        return uid in self._inserted

    def email_count(self):
        return len(self._inserted)

    def close(self):
        pass


def _block_import(module_name):
    """Return an __import__ replacement that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _mock_import(name, *args, **kwargs):
        if name == module_name:
            raise ImportError(f"blocked {module_name}")
        return real_import(name, *args, **kwargs)

    return _mock_import
