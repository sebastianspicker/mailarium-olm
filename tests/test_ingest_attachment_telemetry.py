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
