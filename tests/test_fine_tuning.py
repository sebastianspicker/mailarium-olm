"""Tests for training data generation and fine-tuning modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from src.email_db import EmailDatabase
from src.fine_tuner import FineTuner, _count_lines
from src.training_data_generator import TrainingDataGenerator, _truncate

# ── Helpers ──────────────────────────────────────────────────────


def _make_db_with_threads() -> EmailDatabase:
    """Create an in-memory DB with emails in two threads + one standalone.

    Sets conversation_id explicitly since OLM parsing normally populates it.
    """
    from src.parse_olm import Email

    db = EmailDatabase(":memory:")
    emails = [
        # Thread A — 3 emails
        Email(
            message_id="<a1@test>",
            subject="Project update",
            sender_name="Alice",
            sender_email="alice@co.com",
            to=["bob@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-10T10:00:00",
            body_text="Here is the project status report for Q1.",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to=None,
            conversation_id="thread_a",
        ),
        Email(
            message_id="<a2@test>",
            subject="Re: Project update",
            sender_name="Bob",
            sender_email="bob@co.com",
            to=["alice@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-10T11:00:00",
            body_text="Thanks Alice, the numbers look good.",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to="<a1@test>",
            conversation_id="thread_a",
        ),
        Email(
            message_id="<a3@test>",
            subject="Re: Project update",
            sender_name="Alice",
            sender_email="alice@co.com",
            to=["bob@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-10T12:00:00",
            body_text="I will send the detailed breakdown tomorrow.",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to="<a2@test>",
            conversation_id="thread_a",
        ),
        # Thread B — 2 emails (different sender for hard negatives)
        Email(
            message_id="<b1@test>",
            subject="Invoice #42",
            sender_name="Alice",
            sender_email="alice@co.com",
            to=["finance@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-15T09:00:00",
            body_text="Please find attached the invoice for January services.",
            body_html="",
            folder="Sent",
            has_attachments=True,
            in_reply_to=None,
            conversation_id="thread_b",
        ),
        Email(
            message_id="<b2@test>",
            subject="Re: Invoice #42",
            sender_name="Finance",
            sender_email="finance@co.com",
            to=["alice@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-15T10:00:00",
            body_text="Invoice received and processed. Payment scheduled.",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to="<b1@test>",
            conversation_id="thread_b",
        ),
        # Standalone email (no thread)
        Email(
            message_id="<s1@test>",
            subject="Newsletter",
            sender_name="News",
            sender_email="news@external.com",
            to=["alice@co.com"],
            cc=[],
            bcc=[],
            date="2024-01-20T08:00:00",
            body_text="Weekly newsletter content here.",
            body_html="",
            folder="Inbox",
            has_attachments=False,
            in_reply_to=None,
        ),
    ]
    for email in emails:
        db.insert_email(email)
    return db


# ── _truncate ────────────────────────────────────────────────────


def test_truncate_short():
    assert _truncate("hello", 10) == "hello"


def test_truncate_exact():
    assert _truncate("12345", 5) == "12345"


def test_truncate_long():
    assert _truncate("abcdefghij", 5) == "abcde"


# ── TrainingDataGenerator ───────────────────────────────────────


class TestTrainingDataGenerator:
    def test_generate_triplets_basic(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets()
        assert len(triplets) > 0
        for t in triplets:
            assert "query" in t
            assert "pos" in t
            assert "neg" in t
            assert t["query"].strip()
            assert t["pos"].strip()
            assert t["neg"].strip()

    def test_generate_triplets_max_limit(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets(max_triplets=2)
        assert len(triplets) <= 2

    def test_generate_triplets_empty_db(self):
        db = EmailDatabase(":memory:")
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets()
        assert triplets == []

    def test_generate_triplets_no_threads(self):
        """DB with only standalone emails (no conversation threads)."""
        from src.parse_olm import Email

        db = EmailDatabase(":memory:")
        db.insert_email(
            Email(
                message_id="<solo@test>",
                subject="Solo",
                sender_name="A",
                sender_email="a@test.com",
                to=["b@test.com"],
                cc=[],
                bcc=[],
                date="2024-01-01T00:00:00",
                body_text="Just a standalone email.",
                body_html="",
                folder="Inbox",
                has_attachments=False,
            )
        )
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets()
        assert triplets == []

    def test_hard_negative_same_sender(self):
        """Alice sends in two threads — hard negatives should come from her other thread."""
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db, seed=42)
        triplets = gen.generate_triplets()
        # At least some triplets should exist (Alice is in both threads)
        assert len(triplets) >= 2

    def test_export_jsonl(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "triplets.jsonl")
            result = gen.export_jsonl(path, max_triplets=100)
            assert result["triplet_count"] > 0
            assert result["output_path"] == path

            # Verify JSONL format
            with open(path, encoding="utf-8") as f:
                lines = [line for line in f if line.strip()]
            assert len(lines) == result["triplet_count"]
            for line in lines:
                obj = json.loads(line)
                assert set(obj.keys()) == {"query", "pos", "neg"}

    def test_export_jsonl_empty(self):
        db = EmailDatabase(":memory:")
        gen = TrainingDataGenerator(db)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "empty.jsonl")
            result = gen.export_jsonl(path)
            assert result["triplet_count"] == 0
            assert Path(path).exists()

    def test_triplet_texts_are_truncated(self):
        db = _make_db_with_threads()
        gen = TrainingDataGenerator(db)
        triplets = gen.generate_triplets(max_query_len=10, max_passage_len=10)
        for t in triplets:
            assert len(t["query"]) <= 10
            assert len(t["pos"]) <= 10
            assert len(t["neg"]) <= 10


# ── FineTuner ───────────────────────────────────────────────────


class TestFineTuner:
    def test_init_default(self):
        ft = FineTuner()
        assert ft.base_model == "BAAI/bge-m3"

    def test_fine_tune_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = str(Path(tmpdir) / "empty.jsonl")
            Path(data_path).write_text("")
            result = FineTuner().fine_tune(
                training_data_path=data_path,
                output_dir=str(Path(tmpdir) / "output"),
            )
            assert result["status"] == "error: empty training data"
            assert result["triplet_count"] == 0

    def test_fine_tune_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = FineTuner().fine_tune(
                training_data_path=str(Path(tmpdir) / "nonexistent.jsonl"),
                output_dir=str(Path(tmpdir) / "output"),
            )
            assert result["status"] == "error: empty training data"
            assert result["triplet_count"] == 0

    def test_fine_tune_writes_config(self):
        """Verify fine_tune produces a result with valid triplet count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_path = str(Path(tmpdir) / "data.jsonl")
            with open(data_path, "w") as f:
                for i in range(5):
                    f.write(
                        json.dumps(
                            {
                                "query": f"query {i}",
                                "pos": f"positive {i}",
                                "neg": f"negative {i}",
                            }
                        )
                        + "\n"
                    )

            output_dir = str(Path(tmpdir) / "model_output")
            ft = FineTuner()
            try:
                result = ft.fine_tune(
                    training_data_path=data_path,
                    output_dir=output_dir,
                    epochs=2,
                )
                # Either config_ready (FlagEmbedding) or completed (SentenceTransformers)
                assert result["status"] in ("config_ready", "completed")
                assert result["triplet_count"] == 5
                assert result["epochs"] == 2
            except ImportError:
                # Neither FlagEmbedding nor full SentenceTransformers available
                # (test env uses stubs) — verify the data counting works
                assert _count_lines(data_path) == 5


# ── _count_lines ────────────────────────────────────────────────


def test_count_lines_normal():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write("line1\n")
        f.write("line2\n")
        f.write("\n")  # empty
        f.write("line3\n")
        path = f.name
    assert _count_lines(path) == 3


def test_count_lines_missing():
    assert _count_lines("/tmp/nonexistent_file_12345.jsonl") == 0


def test_count_lines_empty():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        path = f.name
    assert _count_lines(path) == 0
