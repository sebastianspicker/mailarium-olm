from __future__ import annotations

from types import SimpleNamespace

from src.event_extractor import extract_event_rows_from_email


def test_extract_event_rows_from_email_emits_authored_and_attachment_events() -> None:
    email = SimpleNamespace(
        uid="uid-event-1",
        date="2026-03-01",
        segments=[
            SimpleNamespace(
                ordinal=0,
                segment_type="authored_body",
                text="Bitte um Rückmeldung bis spätestens morgen.",
            ),
            SimpleNamespace(
                ordinal=1,
                segment_type="quoted_reply",
                text="Historischer Block ohne neue Ereignisse.",
            ),
        ],
        attachments=[
            {
                "name": "meeting.txt",
                "normalized_text": "SBV Beteiligung wurde nicht einbezogen.",
            }
        ],
    )

    rows = extract_event_rows_from_email(email)
    kinds = {str(row[2]) for row in rows}
    scopes = {str(row[3]) for row in rows}

    assert "request" in kinds
    assert "deadline_pressure" in kinds
    assert "exclusion_or_omission" in kinds
    assert "authored_body" in scopes
    assert "attachment_text" in scopes


def test_extract_event_rows_from_email_returns_empty_without_uid() -> None:
    email = SimpleNamespace(uid="", date="", segments=[], attachments=[])

    assert extract_event_rows_from_email(email) == []


def test_extract_event_rows_skips_quoted_events_when_authored_signal_exists() -> None:
    email = SimpleNamespace(
        uid="uid-event-quoted-1",
        date="2026-03-02",
        segments=[
            SimpleNamespace(ordinal=0, segment_type="authored_body", text="Bitte um Rueckmeldung heute."),
            SimpleNamespace(ordinal=1, segment_type="quoted_reply", text="Der Antrag wurde abgelehnt."),
        ],
        attachments=[],
    )

    rows = extract_event_rows_from_email(email)
    kinds = {str(row[2]) for row in rows}
    scopes = {str(row[3]) for row in rows}

    assert "request" in kinds
    assert "denial" not in kinds
    assert "quoted_body" not in scopes


def test_extract_event_rows_quoted_fallback_marks_low_confidence() -> None:
    email = SimpleNamespace(
        uid="uid-event-quoted-fallback",
        date="2026-03-03",
        segments=[SimpleNamespace(ordinal=0, segment_type="quoted_reply", text="Der Antrag wurde abgelehnt.")],
        attachments=[],
    )

    rows = extract_event_rows_from_email(email)
    assert rows
    assert any(str(row[2]) == "denial" for row in rows)
    assert all(str(row[3]) == "quoted_body" for row in rows)
    assert all(str(row[12]) == "low" for row in rows)


def test_extract_event_rows_ignores_footer_boilerplate() -> None:
    footer_text = "This email is confidential and intended recipient only. Bitte nicht drucken. Diese E-Mail ist vertraulich."
    email = SimpleNamespace(
        uid="uid-event-footer",
        date="2026-03-04",
        segments=[SimpleNamespace(ordinal=0, segment_type="authored_body", text=footer_text)],
        attachments=[],
    )

    assert extract_event_rows_from_email(email) == []
