# ruff: noqa: F401
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args


def _make_mock_email(idx):
    from src.parse_olm import Email

    return Email(
        message_id=f"<msg{idx}@test.com>",
        subject=f"Subject {idx}",
        sender_name="Sender",
        sender_email="sender@example.test",
        to=["recipient@example.test"],
        cc=[],
        bcc=[],
        date=f"2024-01-0{idx}T10:00:00",
        body_text=f"Body {idx}",
        body_html="",
        folder="Inbox",
        has_attachments=False,
    )


class _MockEmbedder:
    def __init__(self, **_kw):
        self.chromadb_path = "mock"
        self.model_name = "mock"
        self._count = 0

    def count(self):
        return self._count

    def add_chunks(self, chunks, **_kw):
        self._count += len(chunks)
        return len(chunks)

    def set_sparse_db(self, db):
        pass

    def warmup(self):
        pass
