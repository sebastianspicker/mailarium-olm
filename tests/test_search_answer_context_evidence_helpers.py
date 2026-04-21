def test_thread_locator_prefers_inferred_thread_when_canonical_missing():
    from src.tools.search_answer_context import _thread_locator_for_candidate

    locator = _thread_locator_for_candidate(
        {"uid": "u1", "conversation_id": ""},
        {
            "uid": "u1",
            "conversation_id": "",
            "inferred_thread_id": "thread-inferred-1",
        },
    )

    assert locator["conversation_id"] == ""
    assert locator["inferred_thread_id"] == "thread-inferred-1"
    assert locator["thread_group_id"] == "thread-inferred-1"
    assert locator["thread_group_source"] == "inferred"


def test_attachment_evidence_profile_marks_ocr_text_as_strong():
    from src.tools.search_answer_context import _attachment_evidence_profile

    profile = _attachment_evidence_profile(
        {
            "extraction_state": "ocr_text_extracted",
        },
        chunk_id="uid-1__att_scan__0",
        snippet="Invoice amount due is 120 EUR.",
    )

    assert profile["extraction_state"] == "ocr_text_extracted"
    assert profile["text_available"] is True
    assert profile["ocr_used"] is True
    assert profile["failure_reason"] is None
    assert profile["evidence_strength"] == "strong_text"


def test_attachment_evidence_profile_marks_binary_only_as_weak():
    from src.tools.search_answer_context import _attachment_evidence_profile

    profile = _attachment_evidence_profile(
        {
            "extraction_state": "binary_only",
        },
        chunk_id="uid-1__att_archive__0",
        snippet='[Attachment: archive.bin from email "Artifacts"]',
    )

    assert profile["extraction_state"] == "binary_only"
    assert profile["text_available"] is False
    assert profile["ocr_used"] is False
    assert profile["failure_reason"] == "no_text_extracted"
    assert profile["evidence_strength"] == "weak_reference"


def test_weak_message_semantics_describes_source_shell_message():
    from src.formatting import weak_message_semantics

    weak_message = weak_message_semantics(
        {
            "body_kind": "content",
            "body_empty_reason": "source_shell_only",
            "recovery_strategy": "source_shell_summary",
            "recovery_confidence": 0.2,
        }
    )

    assert weak_message is not None
    assert weak_message["code"] == "source_shell_only"
    assert weak_message["label"] == "Source-shell message"
    assert "visible authored text" in weak_message["explanation"]
