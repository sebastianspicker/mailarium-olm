"""Reports attachment-surface and duplicate telemetry while preserving distinguishable extraction failure states."""

from __future__ import annotations

from .helpers.ingest_fixtures import _make_mock_email, _seed_ingest_database


def test_ingest_reports_attachment_surface_and_duplicate_telemetry(monkeypatch, tmp_path) -> None:
    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachment_names = ["a.txt", "b.txt"]
    email.attachments = [
        {
            "name": "a.txt",
            "mime_type": "text/plain",
            "size": 32,
            "content_id": "",
            "is_inline": False,
        },
        {
            "name": "b.txt",
            "mime_type": "text/plain",
            "size": 32,
            "content_id": "",
            "is_inline": False,
        },
    ]
    payload = b"[Page 2]\nDies ist ein Beleg."
    email.attachment_contents = [("a.txt", payload), ("b.txt", payload)]

    _, _, stats = _seed_ingest_database(
        monkeypatch,
        tmp_path,
        [email],
        extract_attachments=True,
        database_name="telemetry.db",
        return_stats=True,
    )

    telemetry = stats["ingest_attachment_telemetry"]
    assert telemetry["attachments_seen"] == 2
    assert telemetry["duplicate_content_attachments"] == 1
    assert telemetry["locator_rich_count"] == 2
    assert telemetry["surface_kind_mix"]["verbatim"] >= 2
    assert telemetry["surface_kind_mix"]["normalized_retrieval"] >= 2


def test_ingest_preserves_attachment_extraction_failure_reason(monkeypatch, tmp_path) -> None:
    import mailarium.attachment_extractor as attachment_mod

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachments = [{"name": "broken.pdf", "mime_type": "application/pdf", "size": 4}]
    email.attachment_contents = [("broken.pdf", b"%PDF")]

    monkeypatch.setattr(
        attachment_mod,
        "extract_text_with_reason",
        lambda _name, _content, *, mime_type=None: (None, "text_extraction_failed:PDF:RuntimeError"),
    )
    monkeypatch.setattr(attachment_mod, "extract_attachment_text_ocr", lambda _name, _content: None)

    _seed_ingest_database(monkeypatch, tmp_path, [email], extract_attachments=True, dry_run=True)

    assert email.attachments[0]["extraction_state"] == "extraction_failed"
    assert email.attachments[0]["failure_reason"] == "text_extraction_failed:PDF:RuntimeError"
    assert email.attachments[0]["text_locator"]["extraction_state"] == "extraction_failed"


def test_ingest_keeps_textless_attachment_distinct_from_extraction_failure(monkeypatch, tmp_path) -> None:
    import mailarium.attachment_extractor as attachment_mod

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachments = [{"name": "empty.bin", "mime_type": "application/octet-stream", "size": 4}]
    email.attachment_contents = [("empty.bin", b"\x00\x01\x02")]

    monkeypatch.setattr(attachment_mod, "extract_text_with_reason", lambda _name, _content, *, mime_type=None: (None, None))
    monkeypatch.setattr(attachment_mod, "extract_attachment_text_ocr", lambda _name, _content: None)

    _seed_ingest_database(monkeypatch, tmp_path, [email], extract_attachments=True, dry_run=True)

    assert email.attachments[0]["extraction_state"] != "extraction_failed"
    assert email.attachments[0]["failure_reason"] != "text_extraction_failed:PDF:RuntimeError"
