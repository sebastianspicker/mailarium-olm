from .helpers.ingest_fixtures import _make_mock_email, _MockEmbedder


def _make_image_email(idx: int):
    email = _make_mock_email(idx)
    filename = f"photo-{idx}.png"
    email.has_attachments = True
    email.attachment_names = [filename]
    email.attachments = [
        {
            "name": filename,
            "mime_type": "image/png",
            "size": 128,
            "content_id": "",
            "is_inline": False,
        }
    ]
    email.attachment_contents = [(filename, b"fake-image")]
    return email


def test_reprocess_degraded_attachments_batches_upserts_across_emails(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    emails = [_make_image_email(1), _make_image_email(2)]
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("src.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    upsert_calls = []
    get_existing_ids_calls = 0

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: None})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            nonlocal get_existing_ids_calls
            get_existing_ids_calls += 1
            return set()

        def upsert_chunks(self, chunks, batch_size=100):
            upsert_calls.append([chunk.chunk_id for chunk in chunks])
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: f"Recovered screenshot text for {filename}",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["updated"] == 2
    assert result["chunks_added"] == 2
    assert get_existing_ids_calls == 1
    assert len(upsert_calls) == 1
    assert len(upsert_calls[0]) == 2


def test_reprocess_degraded_attachments_flushes_at_batch_threshold(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    emails = [_make_image_email(1), _make_image_email(2)]
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("src.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    upsert_calls = []

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: None})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return set()

        def upsert_chunks(self, chunks, batch_size=100):
            upsert_calls.append([chunk.chunk_id for chunk in chunks])
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: emails)
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: f"Recovered screenshot text for {filename}",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=1,
    )

    assert result["updated"] == 2
    assert result["chunks_added"] == 2
    assert [len(call) for call in upsert_calls] == [1, 1]


def test_reprocess_degraded_attachments_deletes_only_obsolete_chunk_ids(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.ingest_reingest import _attachment_chunk_prefix

    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    email = _make_image_email(1)
    email_uid = email.uid
    filename = email.attachment_names[0]
    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [email])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    monkeypatch.setattr("src.attachment_extractor.extract_image_text_ocr", lambda filename, content, **_kw: None)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    stale_prefix = _attachment_chunk_prefix(email_uid, filename, 0)
    operations = []

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type(
                "Collection",
                (),
                {"delete": lambda self, ids: operations.append(("delete", list(ids)))},
            )()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {f"{stale_prefix}0", f"{stale_prefix}1"}

        def upsert_chunks(self, chunks, batch_size=100):
            operations.append(("upsert", [chunk.chunk_id for chunk in chunks]))
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)
    monkeypatch.setattr(ingest_mod, "parse_olm", lambda _path, **_kw: [_make_image_email(1)])
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: True)
    monkeypatch.setattr(
        "src.attachment_extractor.extract_image_text_ocr",
        lambda filename, content, **_kw: "Recovered screenshot text",
    )

    result = ingest_mod.reprocess_degraded_attachments(
        "mock.olm",
        sqlite_path=sqlite_file,
        batch_size=10,
    )

    assert result["chunks_deleted"] == 1
    assert operations == [
        ("upsert", [f"{stale_prefix}0"]),
        ("delete", [f"{stale_prefix}1"]),
    ]


def test_reprocess_does_not_promote_missing_payload_attachments_to_completed(tmp_path, monkeypatch):
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod
    from src.email_db import EmailDatabase

    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    degraded_email = _make_image_email(1)
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

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: None})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {f"{degraded_email.uid}__att_old__0"}

        def upsert_chunks(self, chunks, batch_size=100):
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)
    reparsed_email = _make_image_email(1)
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
    import src.embedder as embedder_mod
    import src.ingest as ingest_mod

    sqlite_file = str(tmp_path / "test.db")
    monkeypatch.setattr(
        ingest_mod,
        "chunk_email",
        lambda email_dict: [{"chunk_id": f"{email_dict.get('uid', 'x')}-a"}],
    )
    monkeypatch.setattr(embedder_mod, "EmailEmbedder", _MockEmbedder)

    old_email = _make_image_email(1)
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
    monkeypatch.setattr("src.attachment_extractor.extract_text", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.attachment_extractor.extract_attachment_text_ocr", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("src.attachment_extractor.image_ocr_available", lambda: False)
    ingest_mod.ingest("mock.olm", dry_run=False, sqlite_path=sqlite_file, extract_attachments=True)

    old_chunk_id = f"{old_email.uid}__att_old_hash__0"
    kept_other_chunk_id = f"{old_email.uid}__att_old_hash__1"
    delete_calls: list[list[str]] = []
    upsert_calls: list[list[str]] = []

    class _TrackingEmbedder:
        def __init__(self, **_kw):
            self.collection = type("Collection", (), {"delete": lambda self, ids: delete_calls.append(list(ids))})()

        def set_sparse_db(self, db):
            pass

        def close(self):
            pass

        def get_existing_ids(self, refresh=False):
            return {old_chunk_id, kept_other_chunk_id}

        def upsert_chunks(self, chunks, batch_size=100):
            upsert_calls.append([str(chunk.chunk_id) for chunk in chunks])
            return len(chunks)

    monkeypatch.setattr("src.embedder.EmailEmbedder", _TrackingEmbedder)

    renamed_email = _make_image_email(1)
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
    monkeypatch.setattr("src.attachment_extractor.extract_text", lambda *_args, **_kwargs: "Recovered text")
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
