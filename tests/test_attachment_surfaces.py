from __future__ import annotations

from src.attachment_surfaces import build_attachment_surfaces, primary_surface_payload
from src.email_db import EmailDatabase
from src.parse_olm import Email


def test_build_attachment_surfaces_creates_verbatim_normalized_and_alignment_rows() -> None:
    surfaces = build_attachment_surfaces(
        attachment_id="sha256:att-1",
        extracted_text="[Page 2] Hallo Welt",
        normalized_text="hallo welt",
        text_locator={"page_number": 2},
        extraction_state="text_extracted",
        evidence_strength="strong_text",
        ocr_used=False,
        ocr_confidence=0.0,
    )

    kinds = {str(surface.get("surface_kind")) for surface in surfaces}
    assert kinds == {"verbatim", "normalized_retrieval", "normalized_alignment"}
    primary = primary_surface_payload(surfaces)
    assert primary["surface_kind"] == "verbatim"
    assert primary["locator"] == {"page_number": 2}


def test_build_attachment_surfaces_falls_back_to_reference_only_without_text() -> None:
    surfaces = build_attachment_surfaces(
        attachment_id="sha256:att-2",
        extracted_text="",
        normalized_text="",
        text_locator={"attachment_index": 0},
        extraction_state="binary_only",
        evidence_strength="weak_reference",
        ocr_used=False,
        ocr_confidence=0.0,
    )

    assert len(surfaces) == 1
    assert surfaces[0]["surface_kind"] == "reference_only"
    assert surfaces[0]["locator"] == {"attachment_index": 0}


def test_email_db_persists_attachment_surfaces_and_compatibility_fields() -> None:
    db = EmailDatabase(":memory:")
    email = Email(
        message_id="<surface@example.com>",
        subject="Surface",
        sender_name="Alice",
        sender_email="employee@example.test",
        to=["bob@example.com"],
        cc=[],
        bcc=[],
        date="2026-03-10T10:00:00",
        body_text="Body",
        body_html="",
        folder="Inbox",
        has_attachments=True,
        attachment_names=["report.pdf"],
        attachments=[
            {
                "name": "report.pdf",
                "mime_type": "application/pdf",
                "size": 128,
                "content_id": "",
                "is_inline": False,
                "attachment_id": "sha256:report",
                "content_sha256": "hash-report",
                "extraction_state": "text_extracted",
                "evidence_strength": "strong_text",
                "ocr_used": False,
                "ocr_confidence": 0.0,
                "extracted_text": "[Page 1] Beleg",
                "normalized_text": "beleg",
                "text_locator": {"page_number": 1},
                "text_source_path": "attachment://uid/0/report.pdf",
                "locator_version": 2,
            }
        ],
    )

    inserted = db.insert_email(email)
    assert inserted is True
    rows = db.conn.execute("SELECT COUNT(*) AS c FROM attachment_surfaces WHERE email_uid = ?", (email.uid,)).fetchone()
    assert rows is not None
    assert int(rows["c"]) >= 2

    attachments = db.attachments_for_email(email.uid)
    assert len(attachments) == 1
    surface_kinds = {str(surface.get("surface_kind")) for surface in attachments[0]["surfaces"]}
    assert "verbatim" in surface_kinds
    assert "normalized_retrieval" in surface_kinds
    assert attachments[0]["text_locator"] == {"page_number": 1}
    db.close()
