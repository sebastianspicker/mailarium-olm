from __future__ import annotations

import json

from src.chunker import EmailChunk, chunk_attachment


def test_chunk_attachment_short():
    parent_meta = {"uid": "e1", "subject": "Report", "date": "2025-01-01"}
    chunks = chunk_attachment("e1", "report.pdf", "Short content.", parent_meta)
    assert len(chunks) == 1
    assert "[Attachment: report.pdf" in chunks[0].text
    assert chunks[0].metadata["is_attachment"] == "True"
    assert chunks[0].metadata["attachment_filename"] == "report.pdf"
    assert chunks[0].metadata["parent_uid"] == "e1"
    assert "att_" in chunks[0].chunk_id


def test_chunk_attachment_persists_extraction_metadata():
    parent_meta = {"uid": "e1", "subject": "Scan", "date": "2025-01-01"}
    chunks = chunk_attachment(
        "e1",
        "scan.png",
        "Recovered OCR text.",
        parent_meta,
        extraction_state="ocr_text_extracted",
        evidence_strength="strong_text",
        ocr_used=True,
        failure_reason=None,
    )

    assert len(chunks) == 1
    metadata = chunks[0].metadata
    assert metadata["extraction_state"] == "ocr_text_extracted"
    assert metadata["evidence_strength"] == "strong_text"
    assert metadata["ocr_used"] == "True"
    assert metadata["failure_reason"] == ""


def test_chunk_attachment_long():
    parent_meta = {"uid": "e2", "subject": "Big doc", "date": "2025-06-01"}
    long_text = "Word " * 500
    chunks = chunk_attachment("e2", "big.txt", long_text, parent_meta)
    assert len(chunks) >= 2
    assert "[Attachment: big.txt" in chunks[0].text
    assert "Part 2/" in chunks[1].text


def test_chunk_attachment_empty():
    chunks = chunk_attachment("e3", "empty.txt", "", {})
    assert chunks == []
    chunks = chunk_attachment("e3", "spaces.txt", "   ", {})
    assert chunks == []


def test_email_chunk_embedding_field():
    chunk = EmailChunk(uid="u1", chunk_id="u1__0", text="hello", metadata={})
    assert chunk.embedding is None

    chunk_with = EmailChunk(
        uid="u1",
        chunk_id="u1__img",
        text="[Image]",
        metadata={},
        embedding=[0.1, 0.2, 0.3],
    )
    assert chunk_with.embedding == [0.1, 0.2, 0.3]


def test_chunk_attachment_unique_ids_same_filename():
    parent_meta = {"uid": "e1", "subject": "Report", "date": "2025-01-01"}
    chunks_a = chunk_attachment("e1", "report.pdf", "Content A.", parent_meta, att_index=0)
    chunks_b = chunk_attachment("e1", "report.pdf", "Content B.", parent_meta, att_index=1)
    assert len(chunks_a) == 1
    assert len(chunks_b) == 1
    assert chunks_a[0].chunk_id != chunks_b[0].chunk_id


def test_chunk_attachment_uses_attachment_id_for_rename_continuity():
    parent_meta = {"uid": "e1", "subject": "Report", "date": "2025-01-01"}
    chunks_old = chunk_attachment(
        "e1",
        "old-name.pdf",
        "Stable content.",
        parent_meta,
        att_index=0,
        attachment_id="sha256:deadbeef",
    )
    chunks_new = chunk_attachment(
        "e1",
        "new-name.pdf",
        "Stable content.",
        parent_meta,
        att_index=0,
        attachment_id="sha256:deadbeef",
    )

    assert len(chunks_old) == 1
    assert len(chunks_new) == 1
    assert chunks_old[0].chunk_id == chunks_new[0].chunk_id
    assert chunks_old[0].metadata["attachment_id"] == "sha256:deadbeef"


def test_chunk_attachment_normalizes_parent_metadata_for_chroma():
    parent_meta = {
        "uid": "e1",
        "subject": "Report",
        "date": "2025-01-01",
        "to": ["a@example.com", "b@example.com"],
        "cc": [],
        "attachments": [{"name": "raw.json"}],
    }
    chunks = chunk_attachment("e1", "raw.json", "Content A.", parent_meta, att_index=0)
    assert len(chunks) == 1
    metadata = chunks[0].metadata
    assert metadata["to"] == "a@example.com, b@example.com"
    assert metadata["cc"] == ""
    assert metadata["attachments"] == '[{"name": "raw.json"}]'


def test_chunk_attachment_propagates_surface_metadata() -> None:
    parent_meta = {"uid": "e1", "subject": "Report", "date": "2025-01-01"}
    chunks = chunk_attachment(
        "e1",
        "report.pdf",
        "[Page 2] Content A.",
        parent_meta,
        att_index=0,
        surface_id="surface:verbatim:1",
        surface_kind="verbatim",
        surface_origin_kind="native",
        surface_locator={"page_number": 2, "attachment_index": 0},
        surface_ocr_confidence=0.0,
    )

    assert len(chunks) == 1
    metadata = chunks[0].metadata
    assert metadata["surface_id"] == "surface:verbatim:1"
    assert metadata["surface_kind"] == "verbatim"
    assert metadata["origin_kind"] == "native"
    assert metadata["surface_ocr_confidence"] == "0.0"
    assert json.loads(str(metadata["surface_locator_json"])) == {"page_number": 2, "attachment_index": 0}
