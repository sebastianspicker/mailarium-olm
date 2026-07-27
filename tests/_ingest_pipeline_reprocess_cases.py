"""Degraded attachment reprocessing, batch flushing, and obsolete-chunk cleanup behavior."""

import pytest

from .helpers.ingest_fixtures import _make_mock_image_email, _make_reembed_embedder, _MockEmbedder, _seed_ingest_database


@pytest.mark.parametrize(
    ("batch_size", "expected_call_sizes"),
    [(10, [2]), (1, [1, 1])],
    ids=["batches-across-emails", "flushes-at-threshold"],
)
def test_reprocess_degraded_attachments_batches_by_requested_size(tmp_path, monkeypatch, batch_size, expected_call_sizes):
    emails = [_make_mock_image_email(1), _make_mock_image_email(2)]
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("mailarium.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod, sqlite_file = _seed_ingest_database(monkeypatch, tmp_path, emails, extract_attachments=True)

    upsert_calls = []
    id_lookups = []
    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(existing_ids=set(), upsert_calls=upsert_calls, id_lookups=id_lookups),
    )
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "mailarium.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: f"Recovered screenshot text for {filename}",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=batch_size,
    )

    assert result["updated"] == 2
    assert result["chunks_added"] == 2
    assert len(id_lookups) == 1
    assert [len(call) for call in upsert_calls] == expected_call_sizes


def test_reprocess_degraded_attachments_deletes_only_obsolete_chunk_ids(tmp_path, monkeypatch):
    import mailarium.embedder as embedder_mod
    import mailarium.ingest as ingest_mod
    from mailarium.ingest_reingest import _attachment_chunk_prefix

    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    email = _make_mock_image_email(1)
    email_uid = email.uid
    filename = email.attachment_names[0]
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("mailarium.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    stale_prefix = _attachment_chunk_prefix(email_uid, filename, 0)
    operations = []

    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(
            existing_ids={f"{stale_prefix}0", f"{stale_prefix}1"},
            on_upsert=lambda chunks: operations.append(("upsert", [chunk.chunk_id for chunk in chunks])),
            on_delete=lambda ids: operations.append(("delete", list(ids))),
        ),
    )
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_mock_image_email(1)])
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "mailarium.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: "Recovered screenshot text",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["chunks_deleted"] == 2
    assert operations[0][0] == "upsert"
    assert len(operations[0][1]) == 1
    assert operations[0][1][0] not in {f"{stale_prefix}0", f"{stale_prefix}1"}
    assert operations[1] == ("delete", [f"{stale_prefix}0", f"{stale_prefix}1"])


def test_reprocess_does_not_promote_missing_payload_attachments_to_completed(tmp_path, monkeypatch):
    import mailarium.embedder as embedder_mod
    import mailarium.ingest as ingest_mod
    from mailarium.email_db import EmailDatabase

    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    degraded_email = _make_mock_image_email(1)
    degraded_email.attachment_names = ["scan.pdf"]
    degraded_email.attachments = [
        {
            "name": "scan.pdf",
            "mime_type": "application/pdf",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    degraded_email.attachment_contents = []
    degraded_email.__dict__["_attachment_payload_extraction_failed"] = True

    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [degraded_email])
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(existing_ids={f"{degraded_email.uid}__att_old__0"}),
    )
    reparsed_email = _make_mock_image_email(1)
    reparsed_email.attachment_names = ["scan.pdf"]
    reparsed_email.attachments = [
        {
            "name": "scan.pdf",
            "mime_type": "application/pdf",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    reparsed_email.attachment_contents = []
    reparsed_email.__dict__["_attachment_payload_extraction_failed"] = True
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [reparsed_email])

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["updated"] == 1
    assert result["chunks_deleted"] == 0
    db = EmailDatabase(sqlite_file)
    row = db.conn.execute(
        "SELECT attachment_status FROM email_ingest_state WHERE email_uid = ?",
        (reparsed_email.uid,),
    ).fetchone()
    assert row is not None
    assert row["attachment_status"] == "degraded"
    db.close()


def test_reprocess_renamed_attachment_deletes_old_chunk_ids(tmp_path, monkeypatch):
    import mailarium.embedder as embedder_mod
    import mailarium.ingest as ingest_mod

    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    old_email = _make_mock_image_email(1)
    old_email.attachment_names = ["old-name.pdf"]
    old_email.attachments = [
        {
            "name": "old-name.pdf",
            "mime_type": "application/pdf",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    old_email.attachment_contents = [("old-name.pdf", b"old-bytes")]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [old_email])
    monkeypatch.setattr("mailarium.attachment_extractor.extract_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("mailarium.attachment_extractor.extract_attachment_text_ocr", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("mailarium.attachment_extractor.image_ocr_available", lambda: False)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    old_chunk_id = f"{old_email.uid}__att_old_hash__0"
    kept_other_chunk_id = f"{old_email.uid}__att_old_hash__1"
    delete_calls: list[list[str]] = []
    upsert_calls: list[list[str]] = []

    monkeypatch.setattr(
        "mailarium.embedder.EmailEmbedder",
        _make_reembed_embedder(
            existing_ids={old_chunk_id, kept_other_chunk_id},
            upsert_calls=upsert_calls,
            delete_calls=delete_calls,
        ),
    )

    renamed_email = _make_mock_image_email(1)
    renamed_email.attachment_names = ["new-name.pdf"]
    renamed_email.attachments = [
        {
            "name": "new-name.pdf",
            "mime_type": "application/pdf",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    renamed_email.attachment_contents = [("new-name.pdf", b"new-bytes")]
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [renamed_email])
    monkeypatch.setattr("mailarium.attachment_extractor.extract_text", lambda *_args, **_kwargs: "Recovered text")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_attachment",
        lambda email_uid, filename, text, parent_metadata, **_kwargs: [
            type("Chunk", (), {"chunk_id": f"{email_uid}__att_new_hash__0"})()
        ],
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["updated"] == 1
    assert result["chunks_deleted"] == 2
    assert upsert_calls == [[f"{renamed_email.uid}__att_new_hash__0"]]
    assert len(delete_calls) == 1
    assert set(delete_calls[0]) == {old_chunk_id, kept_other_chunk_id}
