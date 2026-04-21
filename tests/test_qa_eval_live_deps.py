import asyncio
from pathlib import Path

from tests.helpers.qa_eval_fixtures import make_email


def test_resolve_live_deps_falls_back_to_sqlite_when_chromadb_missing(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        make_email(
            subject="Budget request",
            sender_email="employee@example.test",
            body_text="Please send the budget draft.",
        )
    )
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "sqlite_fallback"
    assert deps.get_retriever().backend_name == "sqlite_fallback"


def test_resolve_live_deps_uses_embedding_backend_when_requested(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        make_email(
            subject="Budget request",
            sender_email="employee@example.test",
            body_text="Please send the budget draft.",
        )
    )
    db.close()

    class _EmbeddingRetriever:
        backend_name = "embedding"

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)
    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", lambda email_db, preferred_backend="auto": _EmbeddingRetriever())

    try:
        deps = resolve_live_deps(preferred_backend="embedding")
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "embedding"
    assert deps.get_retriever().backend_name == "embedding"


def test_sqlite_live_retriever_returns_real_results(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    db.insert_email(
        make_email(
            subject="Budget request",
            sender_email="employee@example.test",
            body_text="Please send the updated budget draft for the committee.",
            has_attachments=True,
        )
    )

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="updated budget draft", top_k=5)

    assert results
    assert results[0].metadata["uid"]
    assert any(result.metadata.get("is_attachment") == "True" for result in results)
    assert any("budget" in result.text.lower() for result in results)


def test_sqlite_live_retriever_preserves_attachment_evidence_metadata(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = make_email(
        subject="Invoice scan",
        sender_email="employee@example.test",
        body_text="Please review the scanned invoice attachment.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "invoice-scan.pdf",
            "mime_type": "application/pdf",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "ocr_text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": True,
            "failure_reason": None,
            "text_preview": "Invoice total 123.45 EUR approved for payment.",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="invoice scan", top_k=5)

    attachment_results = [result for result in results if result.metadata.get("is_attachment") == "True"]
    assert attachment_results
    metadata = attachment_results[0].metadata
    assert metadata["extraction_state"] == "ocr_text_extracted"
    assert metadata["evidence_strength"] == "strong_text"
    assert metadata["ocr_used"] is True
    assert metadata["failure_reason"] in (None, "")
    assert metadata["text_preview"] == "Invoice total 123.45 EUR approved for payment."


def test_sqlite_live_retriever_uses_attachment_text_preview_in_result_text(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = make_email(
        subject="Budget spreadsheet",
        sender_email="employee@example.test",
        body_text="See the attachment.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "budget.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": False,
            "failure_reason": None,
            "text_preview": "Budget Q4 total: 25000 EUR",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="What does the budget spreadsheet say?", top_k=5)

    attachment_results = [result for result in results if result.metadata.get("is_attachment") == "True"]
    assert attachment_results
    assert "Budget Q4 total: 25000 EUR" in attachment_results[0].text


def test_live_payload_preserves_strong_attachment_text_with_sqlite_preview(tmp_path: Path, monkeypatch):
    import asyncio

    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import QuestionCase, _live_payload, resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    email = make_email(
        subject="Budget spreadsheet",
        sender_email="employee@example.test",
        body_text="Please review the sheet.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "budget.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "text_extracted",
            "evidence_strength": "strong_text",
            "ocr_used": False,
            "failure_reason": None,
            "text_preview": "Budget Q4 total: 25000 EUR",
        }
    ]
    db.insert_email(email)
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
        payload = asyncio.run(
            _live_payload(
                QuestionCase(
                    id="attach-preview-001",
                    bucket="attachment_lookup",
                    question="What does the budget spreadsheet say?",
                    expected_support_uids=[email.uid],
                ),
                deps,
            )
        )
    finally:
        get_settings.cache_clear()

    assert payload["attachment_candidates"]
    attachment = payload["attachment_candidates"][0]["attachment"]
    assert attachment["evidence_strength"] == "strong_text"
    assert attachment["text_available"] is True
    assert "Budget Q4 total: 25000 EUR" in payload["attachment_candidates"][0]["snippet"]


def test_sqlite_live_retriever_finds_attachment_case_from_natural_language_query(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    email = make_email(
        subject="MDM",
        sender_email="employee@example.test",
        body_text="Configurator 2 Blueprints stores the blueprints in the Apple Configurator profile path.",
        has_attachments=True,
    )
    email.attachments = [
        {
            "name": "profile.mobileconfig",
            "mime_type": "application/x-apple-aspen-config",
            "size": 2048,
            "content_id": "",
            "is_inline": False,
            "extraction_state": "binary_only",
            "evidence_strength": "weak_reference",
            "ocr_used": False,
            "failure_reason": "no_text_extracted",
        }
    ]
    db.insert_email(email)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(
        query="Which email had attachments and discussed Configurator 2 Blueprints?",
        top_k=5,
        has_attachments=True,
    )

    assert results
    assert results[0].metadata["uid"] == email.uid


def test_sqlite_live_retriever_prefers_subject_topic_match_for_fact_queries(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    generic = make_email(
        subject="Please confirm your email address",
        sender_email="no-reply@example.org",
        body_text="This certificate email requires confirmation.",
    )
    expected = make_email(
        subject="AW: Zertifikat Harica",
        sender_email="cert-admin@example.org",
        body_text="Your HARICA certificate is attached.",
    )
    db.insert_email(generic)
    db.insert_email(expected)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="Who sent the HARICA certificate mail?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_sqlite_live_retriever_prefers_earliest_topic_anchor_for_begin_questions(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    early = make_email(
        subject="Re: Physics Reimagined",
        sender_email="external.contact@example.org",
        body_text="Short reply on the thread.",
    )
    early.date = "2022-06-28T16:04:50"
    late = make_email(
        subject="Re: [WARNING: UNSCANNABLE EXTRACTION FAILED]RE: Physics Reimagined",
        sender_email="speaker.one@example.org",
        body_text="Physics Reimagined thread notes with repeated Physics Reimagined details.",
    )
    late.date = "2022-07-06T07:21:37"
    db.insert_email(early)
    db.insert_email(late)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="When did the Physics Reimagined thread begin?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == early.uid


def test_sqlite_live_retriever_prefers_exact_title_match_for_titled_queries(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    expected = make_email(
        subject="Manual",
        sender_email="target.person.personal@example.org",
        body_text="",
    )
    distractor = make_email(
        subject="ICETOL: International Conference on Educational Technology and Online Learning",
        sender_email="events@example.com",
        body_text="Attached manual and conference guide for participants.",
    )
    db.insert_email(expected)
    db.insert_email(distractor)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(query="Which image-only message was titled Manual?", top_k=5)

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_sqlite_live_retriever_prefers_exact_forward_topic_over_version_variant(tmp_path: Path):
    from src.email_db import EmailDatabase
    from src.qa_eval import _SQLiteEvalRetriever

    db = EmailDatabase(str(tmp_path / "email_metadata.db"))
    older = make_email(
        subject="Fwd: Aktuelle Version Videographie-Manual",
        sender_email="target.person.personal@example.org",
        body_text="Forwarding the current manual version.",
        has_attachments=True,
    )
    older.date = "2022-03-14T14:03:38"
    expected = make_email(
        subject="Fwd: Videographie-Manual",
        sender_email="target.person.personal@example.org",
        body_text="Forwarding the manual thread anchor.",
        has_attachments=True,
    )
    expected.date = "2023-04-21T10:37:09"
    db.insert_email(older)
    db.insert_email(expected)

    retriever = _SQLiteEvalRetriever(db)
    results = retriever.search_filtered(
        query="Which forwarded email opened the Videographie-Manual attachment thread?",
        top_k=5,
        has_attachments=True,
    )

    assert results
    assert results[0].metadata["uid"] == expected.uid


def test_resolve_live_deps_uses_sqlite_fallback_backend(monkeypatch, tmp_path: Path):
    from src.config import get_settings
    from src.email_db import EmailDatabase
    from src.qa_eval import resolve_live_deps
    from src.tools import search as search_tools

    sqlite_path = tmp_path / "email_metadata.db"
    db = EmailDatabase(str(sqlite_path))
    db.insert_email(
        make_email(
            subject="Budget request",
            sender_email="employee@example.test",
            body_text="Please send the updated budget draft.",
        )
    )
    db.close()

    monkeypatch.setenv("SQLITE_PATH", str(sqlite_path))
    get_settings.cache_clear()
    monkeypatch.setattr(search_tools, "_deps", None)

    def fake_resolve(email_db, *, preferred_backend="auto"):
        assert preferred_backend == "auto"
        from src.qa_eval import _SQLiteEvalRetriever

        return _SQLiteEvalRetriever(email_db)

    monkeypatch.setattr("src.qa_eval._resolve_live_retriever", fake_resolve)

    try:
        deps = resolve_live_deps()
        payload = asyncio.run(
            __import__("src.qa_eval", fromlist=["_live_payload"])._live_payload(
                __import__("src.qa_eval", fromlist=["QuestionCase"]).QuestionCase(
                    id="fact-001",
                    bucket="fact_lookup",
                    question="updated budget draft",
                    expected_support_uids=[],
                ),
                deps,
            )
        )
    finally:
        get_settings.cache_clear()

    assert deps.live_backend == "sqlite_fallback"
    assert payload["count"] >= 1
    assert payload["candidates"][0]["subject"] == "Budget request"
