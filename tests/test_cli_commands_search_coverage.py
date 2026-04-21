"""Targeted coverage tests for cli_commands_search.py missing lines."""

from __future__ import annotations

import sys  # noqa: F401 - used implicitly by import machinery mocks
from dataclasses import dataclass
from unittest.mock import MagicMock, patch


@dataclass
class _FakeResult:
    chunk_id: str
    text: str
    metadata: dict
    distance: float

    @property
    def score(self) -> float:
        return min(1.0, max(0.0, 1.0 - self.distance))


def _make_results(n: int = 2) -> list[_FakeResult]:
    return [
        _FakeResult(
            chunk_id=f"c{i}",
            text=f"Body text number {i} " * 20,
            metadata={
                "subject": f"Subject {i}",
                "sender_name": f"Sender {i}",
                "sender_email": f"s{i}@test.invalid",
                "date": f"2024-0{i + 1}-01",
                "folder": "Inbox",
            },
            distance=0.1 * i,
        )
        for i in range(1, n + 1)
    ]


# ── render_single_query_plain_impl (lines 205-221) ───────────────────────────


def test_render_single_query_plain_impl_output(capsys) -> None:
    from src.cli_commands_search import render_single_query_plain_impl

    results = _make_results(2)
    render_single_query_plain_impl(query="test query", results=results, sanitize_text=lambda t: t)
    out = capsys.readouterr().out
    assert "test query" in out
    assert "Subject 1" in out
    assert "Subject 2" in out
    assert "Sender 1" in out


def test_render_single_query_plain_impl_long_body_truncated(capsys) -> None:
    from src.cli_commands_search import render_single_query_plain_impl

    long_result = _FakeResult(
        chunk_id="c1",
        text="x" * 700,
        metadata={"subject": "Long body", "sender_name": "A", "date": "2024-01-01", "folder": "Inbox"},
        distance=0.1,
    )
    render_single_query_plain_impl("q", [long_result], sanitize_text=lambda t: t)
    out = capsys.readouterr().out
    assert "..." in out


# ── run_browse_impl — ImportError fallback (lines 271-283) ──────────────────


def _mock_page(n: int = 3, total: int | None = None) -> dict:
    emails = [
        {
            "uid": f"uid{i:04d}xxxxxxxx",
            "subject": f"Email subject {i}",
            "sender_email": f"user{i}@test.invalid",
            "date": f"2024-0{i}-01",
            "conversation_id": f"conv{i}",
        }
        for i in range(1, n + 1)
    ]
    return {"emails": emails, "total": total if total is not None else n}


def _make_db(page: dict) -> MagicMock:
    db = MagicMock()
    db.list_emails_paginated.return_value = page
    return db


def test_run_browse_impl_import_error_fallback(capsys) -> None:
    """Lines 271-283: run_browse_impl prints plain text when rich is unavailable."""
    from src.cli_commands_search import run_browse_impl

    page = _mock_page(2, total=5)
    db = _make_db(page)

    with patch("builtins.__import__") as mock_import:

        def _side_effect(name, *args, **kwargs):
            if name.startswith("rich"):
                raise ImportError(f"mocked: {name}")
            return original_import(name, *args, **kwargs)

        mock_import.side_effect = _side_effect

        run_browse_impl(
            get_email_db=lambda: db,
            sanitize_text=lambda t: t,
            offset=0,
            limit=2,
            folder=None,
            sender=None,
        )

    out = capsys.readouterr().out
    assert "Browsing emails" in out
    assert "Email subject 1" in out
    assert "Email subject 2" in out
    # "Next page" hint because total=5 > offset+limit=2
    assert "Next page" in out


original_import = __import__


def test_run_browse_impl_no_emails(capsys) -> None:
    """Empty page exits early."""
    from src.cli_commands_search import run_browse_impl

    db = _make_db({"emails": [], "total": 0})
    run_browse_impl(
        get_email_db=lambda: db,
        sanitize_text=lambda t: t,
        offset=0,
        limit=20,
        folder=None,
        sender=None,
    )
    out = capsys.readouterr().out
    assert "No emails found" in out


# ── run_interactive_impl — ImportError branch (lines 30-32) ─────────────────


def test_run_interactive_impl_without_rich(capsys) -> None:
    """Lines 30-32: run_interactive_impl prints help message when rich unavailable."""
    from src.cli_commands_search import run_interactive_impl

    retriever = MagicMock()

    with patch("builtins.__import__") as mock_import:

        def _side_effect(name, *args, **kwargs):
            if name.startswith("rich"):
                raise ImportError(f"mocked: {name}")
            return original_import(name, *args, **kwargs)

        mock_import.side_effect = _side_effect

        run_interactive_impl(
            retriever=retriever,
            top_k=5,
            render_interactive_intro=MagicMock(),
            interactive_action=MagicMock(),
            render_stats=MagicMock(),
            render_senders=MagicMock(),
            render_results_table=MagicMock(),
        )

    out = capsys.readouterr().out
    assert "rich" in out.lower() or "interactive" in out.lower()
