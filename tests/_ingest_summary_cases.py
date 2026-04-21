# ruff: noqa: F401, I001
import queue
import threading
import time

import pytest

from src.ingest import _SENTINEL, _EmbedPipeline, main, parse_args

from .helpers.ingest_fixtures import _MockEmbedder, _make_mock_email


def test_format_ingestion_summary_includes_qol_fields():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 1.5,
        }
    )

    assert "=== Ingestion Summary ===" in lines
    assert "Emails parsed: 10" in lines
    assert "Chunks created: 20" in lines
    assert "Chunks added: 18" in lines
    assert "Chunks skipped: 2" in lines
    assert "Write batches: 3" in lines
    assert "Total in DB: 99" in lines


def test_format_ingestion_summary_for_dry_run_hides_db_totals():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 0,
            "chunks_skipped": 0,
            "batches_written": 0,
            "total_in_db": None,
            "dry_run": True,
            "elapsed_seconds": 1.5,
        }
    )

    assert "Database write disabled (dry-run)." in lines
    assert not any(line.startswith("Chunks added:") for line in lines)
    assert not any(line.startswith("Total in DB:") for line in lines)


def test_format_ingestion_summary_includes_timing():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 10.5,
            "timing": {"embed_seconds": 8.0, "write_seconds": 1.5},
        }
    )

    assert any("Timing:" in line for line in lines)
    assert any("embed=8.0s" in line for line in lines)


def test_format_ingestion_summary_detailed_timing():
    from src.ingest import format_ingestion_summary

    lines = format_ingestion_summary(
        {
            "emails_parsed": 10,
            "chunks_created": 20,
            "chunks_added": 18,
            "chunks_skipped": 2,
            "batches_written": 3,
            "total_in_db": 99,
            "dry_run": False,
            "elapsed_seconds": 10.5,
            "timing": {
                "embed_seconds": 6.0,
                "write_seconds": 3.0,
                "parse_seconds": 1.2,
                "queue_wait_seconds": 0.3,
                "sqlite_seconds": 1.5,
                "entity_seconds": 0.8,
                "analytics_seconds": 0.7,
            },
        }
    )

    assert any("Timing:" in line for line in lines)
    assert any("Breakdown:" in line for line in lines)
    assert any("parse=1.2s" in line for line in lines)
    assert any("sqlite=1.5s" in line for line in lines)
    assert any("analytics=0.7s" in line for line in lines)
