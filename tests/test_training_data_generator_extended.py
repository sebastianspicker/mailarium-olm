"""Extended tests for src/training_data_generator.py — targeting uncovered lines."""

from __future__ import annotations

from src.email_db import EmailDatabase
from src.parse_olm import Email
from src.training_data_generator import TrainingDataGenerator, _truncate

# ── Helpers ──────────────────────────────────────────────────


def _make_email(**overrides) -> Email:
    defaults = {
        "message_id": "<msg1@test>",
        "subject": "Hello",
        "sender_name": "Alice",
        "sender_email": "alice@co.com",
        "to": ["bob@co.com"],
        "cc": [],
        "bcc": [],
        "date": "2024-01-10T10:00:00",
        "body_text": "Test body text.",
        "body_html": "",
        "folder": "Inbox",
        "has_attachments": False,
    }
    defaults.update(overrides)
    return Email(**defaults)


def _make_db_with_threads() -> EmailDatabase:
    db = EmailDatabase(":memory:")
    emails = [
        _make_email(
            message_id="<a1@test>",
            sender_email="alice@co.com",
            body_text="Here is the project status report for Q1.",
            conversation_id="thread_a",
            date="2024-01-10T10:00:00",
        ),
        _make_email(
            message_id="<a2@test>",
            sender_email="bob@co.com",
            sender_name="Bob",
            body_text="Thanks Alice, the numbers look good.",
            conversation_id="thread_a",
            date="2024-01-10T11:00:00",
        ),
        _make_email(
            message_id="<a3@test>",
            sender_email="alice@co.com",
            body_text="I will send the detailed breakdown tomorrow.",
            conversation_id="thread_a",
            date="2024-01-10T12:00:00",
        ),
        _make_email(
            message_id="<b1@test>",
            sender_email="alice@co.com",
            body_text="Please find attached the invoice for January services.",
            conversation_id="thread_b",
            date="2024-01-15T09:00:00",
        ),
        _make_email(
            message_id="<b2@test>",
            sender_email="finance@co.com",
            sender_name="Finance",
            body_text="Invoice received and processed. Payment scheduled.",
            conversation_id="thread_b",
            date="2024-01-15T10:00:00",
        ),
    ]
    for email in emails:
        db.insert_email(email)
    return db


# ── _load_threads (lines 146-158) ───────────────────────────


class TestLoadThreads:
    def test_load_threads_returns_dict(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        threads = gen._load_threads(min_size=2)
        assert isinstance(threads, dict)
        assert len(threads) >= 1
        for _conv_id, emails in threads.items():
            assert len(emails) >= 2

    def test_load_threads_min_size_filter(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        # thread_a has 3 emails, thread_b has 2
        threads = gen._load_threads(min_size=3)
        assert "thread_a" in threads
        assert "thread_b" not in threads

    def test_load_threads_empty_db(self):
        db = EmailDatabase(":memory:")
        gen = TrainingDataGenerator(db)
        threads = gen._load_threads(min_size=2)
        assert threads == {}


# ── _build_sender_index (lines 162-171) ──────────────────────


class TestBuildSenderIndex:
    def test_build_sender_index_groups_by_sender(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        index = gen._build_sender_index()
        assert isinstance(index, dict)
        assert "alice@co.com" in index
        assert len(index["alice@co.com"]) >= 3

    def test_build_sender_index_empty_db(self):
        db = EmailDatabase(":memory:")
        gen = TrainingDataGenerator(db)
        index = gen._build_sender_index()
        assert index == {}


# ── _load_all_emails (lines 175-178) ────────────────────────


class TestLoadAllEmails:
    def test_load_all_emails_returns_list(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        all_emails = gen._load_all_emails()
        assert isinstance(all_emails, list)
        assert len(all_emails) == 5

    def test_load_all_emails_empty_db(self):
        db = EmailDatabase(":memory:")
        gen = TrainingDataGenerator(db)
        all_emails = gen._load_all_emails()
        assert all_emails == []


# ── _find_negative: no candidates at all (line 215) ─────────


class TestFindNegativeNoCandidates:
    def test_find_negative_returns_none_when_no_candidates(self):
        """When all emails are in the same thread, no negative can be found."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<only1@test>",
                sender_email="alice@co.com",
                body_text="Only email body",
                conversation_id="only_thread",
            )
        )
        gen = TrainingDataGenerator(db)
        _, sender_index, all_emails = gen._load_email_data(min_thread_size=1)

        query_email = {
            "sender_email": "alice@co.com",
            "conversation_id": "only_thread",
            "body_text": "Only email body",
        }
        result = gen._find_negative(
            query_email,
            "only_thread",
            sender_index,
            all_emails,
            max_len=512,
        )
        assert result is None

    def test_find_negative_hard_negative_from_same_sender(self):
        """Hard negative comes from same sender, different thread."""
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        _, sender_index, all_emails = gen._load_email_data(min_thread_size=2)

        query_email = {
            "sender_email": "alice@co.com",
            "conversation_id": "thread_a",
            "body_text": "Here is the project status report.",
        }
        result = gen._find_negative(
            query_email,
            "thread_a",
            sender_index,
            all_emails,
            max_len=512,
        )
        assert result is not None
        assert isinstance(result, str)


# ── generate_triplets: skip empty body (line 65) ────────────


class TestGenerateTripletsEdgeCases:
    def test_skips_emails_with_empty_body(self):
        """Emails with empty body_text and subject are skipped."""
        db = EmailDatabase(":memory:")
        db.insert_email(
            _make_email(
                message_id="<empty1@test>",
                subject="",
                body_text="",
                conversation_id="empty_thread",
                date="2024-01-10T10:00:00",
            )
        )
        db.insert_email(
            _make_email(
                message_id="<empty2@test>",
                subject="",
                body_text="",
                conversation_id="empty_thread",
                date="2024-01-10T11:00:00",
            )
        )
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets()
        assert triplets == []

    def test_skips_when_no_negative_found(self):
        """When no negative can be found, triplet is skipped."""
        db = EmailDatabase(":memory:")
        # All emails in same thread, same sender — no negatives possible
        for i in range(3):
            db.insert_email(
                _make_email(
                    message_id=f"<no_neg{i}@test>",
                    sender_email="only@co.com",
                    body_text=f"Body text number {i}",
                    conversation_id="solo_thread",
                    date=f"2024-01-{10 + i}T10:00:00",
                )
            )
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets()
        # No negatives possible, so no triplets
        assert triplets == []

    def test_generate_triplets_max_reached_during_inner_loop(self):
        """max_triplets limit is respected even mid-loop."""
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets(max_triplets=1)
        assert len(triplets) == 1

    def test_generate_triplets_shuffled(self):
        """Triplets are shuffled for randomness."""
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db, seed=42)
        t1 = gen.generate_triplets()
        gen2 = TrainingDataGenerator(db, seed=42)
        t2 = gen2.generate_triplets()
        # Same seed should produce same shuffle
        assert len(t1) == len(t2)
        if len(t1) > 0:
            assert t1[0]["query"] == t2[0]["query"]


# ── _truncate edge cases ─────────────────────────────────────


class TestTruncateEdgeCases:
    def test_truncate_empty_string(self):
        assert _truncate("", 10) == ""

    def test_truncate_zero_length(self):
        assert _truncate("hello", 0) == ""

    def test_truncate_exact_boundary(self):
        assert _truncate("abc", 3) == "abc"
        assert _truncate("abcd", 3) == "abc"
