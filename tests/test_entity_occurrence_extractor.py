from __future__ import annotations

from types import SimpleNamespace

from src.entity_occurrence_extractor import extract_entity_occurrence_rows_from_email


def test_extract_entity_occurrence_rows_from_email_prefers_segment_and_attachment_surfaces() -> None:
    email = SimpleNamespace(
        segments=[
            SimpleNamespace(ordinal=0, segment_type="authored_body", text="Bitte SBV und Personalrat beteiligen."),
        ],
        attachments=[
            {"name": "memo.txt", "normalized_text": "AGG Gleichbehandlung Hinweis"},
        ],
    )
    entities = [
        ("SBV", "organization", "sbv"),
        ("Gleichbehandlung", "legal_reference", "gleichbehandlung"),
    ]

    rows = extract_entity_occurrence_rows_from_email(email, entities)
    source_scopes = {str(row[3]) for row in rows}

    assert rows
    assert "authored_body" in source_scopes
    assert "attachment_text" in source_scopes
