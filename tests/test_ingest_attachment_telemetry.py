from __future__ import annotations

from .helpers.ingest_fixtures import _make_mock_email, _MockEmbedder


def test_ingest_reports_attachment_surface_and_duplicate_telemetry(monkeypatch, tmp_path) -> None:
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

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

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    sqlite_file = str(tmp_path / "telemetry.db")
    stats = ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    telemetry = stats["ingest_attachment_telemetry"]
    assert telemetry["attachments_seen"] == 2
    assert telemetry["duplicate_content_attachments"] == 1
    assert telemetry["locator_rich_count"] == 2
    assert telemetry["surface_kind_mix"]["verbatim"] >= 2
    assert telemetry["surface_kind_mix"]["normalized_retrieval"] >= 2


def test_ingest_preserves_attachment_extraction_failure_reason(monkeypatch) -> None:
    import src.attachment_extractor as attachment_mod
    import src.ingest as ingest_mod

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachments = [{"name": "broken.pdf", "mime_type": "application/pdf", "size": 4}]
    email.attachment_contents = [("broken.pdf", b"%PDF")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "chunk_email", lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}])
    monkeypatch.setattr(
        attachment_mod,
        "extract_text_with_reason",
        lambda _name, _content, *, mime_type=None: (None, "text_extraction_failed:PDF:RuntimeError"),
    )
    monkeypatch.setattr(attachment_mod, "extract_attachment_text_ocr", lambda _name, _content: None)

    ingest_mod.ingest("mock.olm", dry_run=True, extract_attachments=True)

    assert email.attachments[0]["extraction_state"] == "extraction_failed"
    assert email.attachments[0]["failure_reason"] == "text_extraction_failed:PDF:RuntimeError"
    assert email.attachments[0]["text_locator"]["extraction_state"] == "extraction_failed"


def test_ingest_keeps_textless_attachment_distinct_from_extraction_failure(monkeypatch) -> None:
    import src.attachment_extractor as attachment_mod
    import src.ingest as ingest_mod

    email = _make_mock_email(1)
    email.has_attachments = True
    email.attachments = [{"name": "empty.bin", "mime_type": "application/octet-stream", "size": 4}]
    email.attachment_contents = [("empty.bin", b"\x00\x01\x02")]

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr(ingest_mod, "chunk_email", lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}])
    monkeypatch.setattr(attachment_mod, "extract_text_with_reason", lambda _name, _content, *, mime_type=None: (None, None))
    monkeypatch.setattr(attachment_mod, "extract_attachment_text_ocr", lambda _name, _content: None)

    ingest_mod.ingest("mock.olm", dry_run=True, extract_attachments=True)

    assert email.attachments[0]["extraction_state"] != "extraction_failed"
    assert email.attachments[0]["failure_reason"] != "text_extraction_failed:PDF:RuntimeError"
