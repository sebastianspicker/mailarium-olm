"""Exercises evidence helper selection for inferred threads, attachment strength, and weak message semantics.

It avoids upgrading binary-only or shell-message material into stronger evidence than the source supports.
"""

from .helpers.mcp_tool_fakes import _assert_source_shell_message_semantics


def test_thread_locator_prefers_inferred_thread_when_canonical_missing():
    from mailarium.tools.search_answer_context import _thread_locator_for_candidate

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
    from mailarium.tools.search_answer_context import _attachment_evidence_profile

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
    from mailarium.tools.search_answer_context import _attachment_evidence_profile

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
    _assert_source_shell_message_semantics()
