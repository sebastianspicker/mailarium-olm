from __future__ import annotations

from types import SimpleNamespace

from src.language_analytics import (
    build_analytics_update_row,
    build_surface_language_rows_from_email,
    build_surface_language_rows_from_row,
    select_analytics_text_from_email,
    select_analytics_text_from_row,
)


def test_select_analytics_text_from_row_uses_subject_and_attachment_when_body_sparse() -> None:
    text, source = select_analytics_text_from_row(
        {
            "subject": "WG: Bitte um Rückmeldung",
            "forensic_body_text": "",
            "forensic_body_source": "",
            "body_text": "",
            "normalized_body_source": "",
            "raw_body_text": "",
            "attachment_text": "Protokoll zum BEM Gespräch",
        }
    )

    assert "Bitte um Rückmeldung" in text
    assert "Protokoll zum BEM Gespräch" in text
    assert source == "subject_plus_attachment_text"


def test_build_analytics_update_row_persists_unknown_language_explicitly() -> None:
    row = build_analytics_update_row(
        uid="email-1",
        text="xyzzy plugh frotz gnusto rezrov",
        source="body_text",
    )

    assert row[0] == "unknown"
    assert row[3] == "body_text"
    assert row[-1] == "email-1"


def test_select_analytics_text_from_email_prefers_authored_segment_over_quoted_body() -> None:
    email = SimpleNamespace(
        subject="AW: Bitte Rückmeldung",
        forensic_body_text="",
        forensic_body_source="",
        clean_body="Quoted text body that should not dominate",
        clean_body_source="body_text",
        raw_body_text="",
        attachments=[],
        segments=[
            SimpleNamespace(
                ordinal=0,
                segment_type="authored_body",
                source_surface="body_text",
                text="Ich bitte um Rückmeldung bis morgen.",
            ),
            SimpleNamespace(
                ordinal=1,
                segment_type="quoted_reply",
                source_surface="body_text",
                text="Quoted historical block",
            ),
        ],
    )

    text, source = select_analytics_text_from_email(email)

    assert text == "Ich bitte um Rückmeldung bis morgen."
    assert source == "segment:authored_body"


def test_build_surface_language_rows_from_email_emits_source_aware_rows() -> None:
    email = SimpleNamespace(
        uid="uid-1",
        attachments=[
            {"name": "scan.pdf", "normalized_text": "Betriebsrat Terminprotokoll"},
        ],
        segments=[
            SimpleNamespace(
                ordinal=0,
                segment_type="authored_body",
                source_surface="body_text",
                text="Bitte um Rückmeldung bis morgen.",
            ),
            SimpleNamespace(
                ordinal=1,
                segment_type="quoted_reply",
                source_surface="body_text",
                text="Quoted historical context",
            ),
            SimpleNamespace(
                ordinal=2,
                segment_type="header_block",
                source_surface="body_text",
                text="From: hr@example.org",
            ),
        ],
    )

    rows = build_surface_language_rows_from_email(email)
    scopes = {str(row[1]) for row in rows}

    assert "authored_body" in scopes
    assert "quoted_body" in scopes
    assert "forwarded_header" in scopes
    assert "attachment_text" in scopes
    assert "segment_text" in scopes


def test_select_analytics_text_from_row_prefers_authored_segment() -> None:
    text, source = select_analytics_text_from_row(
        {
            "subject": "AW: Bitte Rückmeldung",
            "forensic_body_text": "Quoted thread content should not dominate",
            "forensic_body_source": "forensic_body_text",
            "body_text": "Quoted thread content should not dominate",
            "normalized_body_source": "body_text",
            "raw_body_text": "",
            "attachment_text": "",
            "authored_segment_text": "Bitte Rückmeldung bis morgen.",
        }
    )

    assert text == "Bitte Rückmeldung bis morgen."
    assert source == "segment:authored_body"


def test_build_surface_language_rows_from_row_includes_attachment_and_segment_scopes() -> None:
    rows = build_surface_language_rows_from_row(
        {
            "uid": "uid-2",
            "forensic_body_text": "Bitte zeitnah reagieren.",
            "forensic_body_source": "raw_body_text",
            "body_text": "",
            "raw_body_text": "",
            "attachment_text": "BEM Teilnahmeprotokoll",
            "authored_segment_text": "Bitte zeitnah reagieren.",
            "authored_segment_ordinal": 0,
            "quoted_segment_text": "Historische Antwort",
            "quoted_segment_ordinal": 1,
            "forwarded_header_text": "From: hr@example.org",
            "forwarded_header_ordinal": 2,
            "segment_text": "Bitte zeitnah reagieren. Historische Antwort",
            "segment_ordinal": 0,
        }
    )
    scopes = {str(row[1]) for row in rows}

    assert "authored_body" in scopes
    assert "quoted_body" in scopes
    assert "forwarded_header" in scopes
    assert "attachment_text" in scopes
    assert "segment_text" in scopes
