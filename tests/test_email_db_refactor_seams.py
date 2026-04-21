"""Structural tests for EmailDatabase persistence/enrichment extraction."""

from __future__ import annotations

from unittest.mock import patch

from src.email_db import EmailDatabase
from tests._email_db_cases import _make_email


def test_insert_email_wrapper_delegates_to_helper() -> None:
    db = EmailDatabase(":memory:")
    email = _make_email()
    with patch("src.email_db.insert_email_impl", return_value=True) as mock_impl:
        result = db.insert_email(email, ingestion_run_id=5)
    assert result is True
    mock_impl.assert_called_once_with(db, email, ingestion_run_id=5)
    db.close()


def test_insert_emails_batch_wrapper_delegates_to_helper() -> None:
    db = EmailDatabase(":memory:")
    emails = [_make_email(message_id="<m1@example.com>")]
    with patch("src.email_db.insert_emails_batch_impl", return_value={"uid-1"}) as mock_impl:
        result = db.insert_emails_batch(emails, ingestion_run_id=9)
    assert result == {"uid-1"}
    mock_impl.assert_called_once_with(db, emails, ingestion_run_id=9)
    db.close()
