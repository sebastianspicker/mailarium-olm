import pytest


def test_dedupe_evidence_items_prefers_first_unique_handle():
    from src.tools.search_answer_context import _dedupe_evidence_items

    items = [
        {
            "uid": "u1",
            "score": 0.9,
            "snippet": "same",
            "provenance": {"evidence_handle": "email:u1:1"},
        },
        {
            "uid": "u1",
            "score": 0.8,
            "snippet": "same",
            "provenance": {"evidence_handle": "email:u1:1"},
        },
        {
            "uid": "u2",
            "score": 0.7,
            "snippet": "other",
            "provenance": {"evidence_handle": "email:u2:1"},
        },
    ]

    kept, dropped = _dedupe_evidence_items(items)

    assert dropped == 1
    assert [item["uid"] for item in kept] == ["u1", "u2"]
    assert kept[0]["score"] == pytest.approx(0.9)


def test_answer_quality_reports_ambiguity_for_close_top_scores():
    from src.tools.search_answer_context import _answer_quality

    summary = _answer_quality(
        candidates=[
            {"uid": "u1", "score": 0.81, "conversation_id": "c1"},
            {"uid": "u2", "score": 0.79, "conversation_id": "c2"},
        ],
        attachment_candidates=[],
        conversation_groups=[],
    )

    assert summary["confidence_label"] == "ambiguous"
    assert summary["ambiguity_reason"] == "close_top_scores"
    assert summary["alternative_candidates"] == ["u2"]


def test_compact_timeline_events_keeps_anchor_uids():
    from src.tools.search_answer_context import _compact_timeline_events

    timeline = {
        "event_count": 6,
        "date_range": {"first": "2025-01-01", "last": "2025-01-06"},
        "first_uid": "u1",
        "last_uid": "u6",
        "key_transition_uid": "u4",
        "events": [
            {"uid": "u1", "date": "2025-01-01"},
            {"uid": "u2", "date": "2025-01-02"},
            {"uid": "u3", "date": "2025-01-03"},
            {"uid": "u4", "date": "2025-01-04"},
            {"uid": "u5", "date": "2025-01-05"},
            {"uid": "u6", "date": "2025-01-06"},
        ],
    }

    compacted, dropped = _compact_timeline_events(timeline, max_events=4)

    kept_uids = [event["uid"] for event in compacted["events"]]
    assert dropped == 2
    assert compacted["event_count"] == 4
    assert "u1" in kept_uids
    assert "u4" in kept_uids
    assert "u6" in kept_uids


def test_summarize_timeline_for_budget_keeps_anchor_uids_without_snippets():
    from src.tools.search_answer_context import _summarize_timeline_for_budget

    timeline = {
        "event_count": 5,
        "date_range": {"first": "2025-06-01", "last": "2025-06-05"},
        "first_uid": "u1",
        "last_uid": "u5",
        "key_transition_uid": "u3",
        "events": [
            {"uid": "u1", "date": "2025-06-01", "score": 0.91, "snippet": "first"},
            {"uid": "u2", "date": "2025-06-02", "score": 0.83, "snippet": "second"},
            {"uid": "u3", "date": "2025-06-03", "score": 0.97, "snippet": "third"},
            {"uid": "u4", "date": "2025-06-04", "score": 0.80, "snippet": "fourth"},
            {"uid": "u5", "date": "2025-06-05", "score": 0.88, "snippet": "fifth"},
        ],
    }

    summarized, dropped = _summarize_timeline_for_budget(timeline)

    assert dropped == 2
    assert summarized["event_count"] == 3
    assert [event["uid"] for event in summarized["events"]] == ["u1", "u3", "u5"]
    assert all("snippet" not in event for event in summarized["events"])


def test_infer_quoted_speaker_prefers_quoted_header_context():
    from src.tools.search_answer_context import _infer_quoted_speaker

    speaker_email, source, confidence = _infer_quoted_speaker(
        full_email=None,
        authored_email="alice@example.com",
        conversation_context={"participants": ["alice@example.com", "bob@example.com"]},
        segment_text=(
            "From: Bob Example <bob@example.com>\n"
            "Sent: Tuesday, April 1, 2025 09:00\n"
            "To: Alice Example <alice@example.com>\n"
            "Subject: Figures\n\n"
            "Can you send the figures?"
        ),
    )

    assert speaker_email == "bob@example.com"
    assert source == "quoted_from_header"
    assert confidence == pytest.approx(0.85)


def test_infer_quoted_speaker_uses_single_email_in_quoted_block():
    from src.tools.search_answer_context import _infer_quoted_speaker

    speaker_email, source, confidence = _infer_quoted_speaker(
        full_email=None,
        authored_email="alice@example.com",
        conversation_context={"participants": ["alice@example.com", "bob@example.com", "carol@example.com"]},
        segment_text="On Tue, Bob Example <bob@example.com> wrote:",
    )

    assert speaker_email == "bob@example.com"
    assert source == "quoted_block_email"
    assert confidence == pytest.approx(0.6)


def test_infer_quoted_speaker_keeps_multi_party_case_unresolved():
    from src.tools.search_answer_context import _infer_quoted_speaker

    speaker_email, source, confidence = _infer_quoted_speaker(
        full_email=None,
        authored_email="alice@example.com",
        conversation_context={"participants": ["alice@example.com", "bob@example.com", "carol@example.com"]},
        segment_text="Bob Example <bob@example.com>\nCc: Carol Example <carol@example.com>",
    )

    assert speaker_email == ""
    assert source == "unresolved"
    assert confidence == pytest.approx(0.0)


def test_infer_quoted_speaker_prefers_from_header_in_multi_party_case():
    from src.tools.search_answer_context import _infer_quoted_speaker

    speaker_email, source, confidence = _infer_quoted_speaker(
        full_email=None,
        authored_email="alice@example.com",
        conversation_context={"participants": ["alice@example.com", "bob@example.com", "carol@example.com"]},
        segment_text=(
            "From: Bob Example <bob@example.com>\n"
            "Cc: Carol Example <carol@example.com>\n"
            "To: Alice Example <alice@example.com>\n\n"
            "Can you send the figures?"
        ),
    )

    assert speaker_email == "bob@example.com"
    assert source == "quoted_from_header"
    assert confidence == pytest.approx(0.85)


def test_infer_quoted_speaker_does_not_overclaim_from_reply_context_only():
    from src.tools.search_answer_context import _infer_quoted_speaker

    speaker_email, source, confidence = _infer_quoted_speaker(
        full_email={
            "reply_context_from": "bob@example.com",
            "reply_context_to": ["alice@example.com", "carol@example.com"],
        },
        authored_email="alice@example.com",
        conversation_context={"participants": ["alice@example.com", "bob@example.com", "carol@example.com"]},
        segment_text="Bob Example <bob@example.com>\nCc: Carol Example <carol@example.com>",
    )

    assert speaker_email == ""
    assert source == "unresolved"
    assert confidence == pytest.approx(0.0)


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


def test_answer_policy_prefers_forensic_verification_for_quotes():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="What exactly did Alice write about the budget?",
        evidence_mode="retrieval",
        candidates=[
            {"uid": "u1", "score": 0.93},
        ],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "high",
            "ambiguity_reason": "",
            "top_candidate_uid": "u1",
        },
    )

    assert policy["decision"] == "answer"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["max_citations"] == 1
    assert policy["cite_candidate_uids"] == ["u1"]
    assert policy["confidence_phrase"] == "The evidence strongly indicates"


def test_answer_policy_marks_ambiguous_cases_without_overclaiming():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="Who approved the rollout?",
        evidence_mode="retrieval",
        candidates=[
            {"uid": "u1", "score": 0.81},
            {"uid": "u2", "score": 0.79},
        ],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "ambiguous",
            "ambiguity_reason": "close_top_scores",
            "top_candidate_uid": "u1",
            "alternative_candidates": ["u2"],
        },
    )

    assert policy["decision"] == "ambiguous"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["max_citations"] == 2
    assert policy["refuse_to_overclaim"] is True
    assert policy["ambiguity_phrase"] == "The available evidence is ambiguous"


def test_answer_policy_marks_insufficient_evidence_for_weak_message():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="What did the scan say?",
        evidence_mode="forensic",
        candidates=[
            {
                "uid": "u1",
                "score": 0.55,
                "weak_message": {"code": "image_only"},
            }
        ],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "low",
            "ambiguity_reason": "weak_scan_body",
            "top_candidate_uid": "u1",
        },
    )

    assert policy["decision"] == "insufficient_evidence"
    assert policy["verification_mode"] == "already_forensic"
    assert policy["max_citations"] == 1
    assert (
        policy["fallback_phrase"]
        == "I can identify the likely message, but the available evidence is too weak to state the content confidently."
    )


def test_packing_priority_prefers_strong_evidence_over_weak_high_score():
    from src.tools.search_answer_context import _packing_priority

    weak_priority = _packing_priority(
        {
            "uid": "u-weak",
            "rank": 1,
            "score": 0.99,
            "weak_message": {"code": "source_shell_only"},
            "verification_status": "retrieval",
        },
        cited_candidate_uids=[],
    )
    strong_priority = _packing_priority(
        {
            "uid": "u-strong",
            "rank": 2,
            "score": 0.76,
            "verification_status": "forensic_exact",
        },
        cited_candidate_uids=[],
    )

    assert strong_priority > weak_priority


def test_final_answer_contract_for_ambiguous_response():
    from src.tools.search_answer_context import _final_answer_contract

    contract = _final_answer_contract(
        answer_policy={
            "decision": "ambiguous",
            "verification_mode": "verify_forensic",
            "max_citations": 2,
            "cite_candidate_uids": ["u1", "u2"],
            "confidence_phrase": "The available evidence suggests",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "fallback_phrase": "fallback",
            "refuse_to_overclaim": True,
        }
    )

    assert contract["decision"] == "ambiguous"
    assert contract["answer_format"]["shape"] == "two_short_paragraphs"
    assert contract["answer_format"]["cite_at_sentence_end"] is True
    assert contract["citation_format"]["style"] == "inline_uid_brackets"
    assert contract["citation_format"]["pattern"] == "[uid:<EMAIL_UID>]"
    assert contract["ambiguity_wording"] == "The available evidence is ambiguous"
    assert contract["required_citation_uids"] == ["u1", "u2"]


def test_final_answer_contract_for_insufficient_evidence_response():
    from src.tools.search_answer_context import _final_answer_contract

    contract = _final_answer_contract(
        answer_policy={
            "decision": "insufficient_evidence",
            "verification_mode": "already_forensic",
            "max_citations": 1,
            "cite_candidate_uids": ["u1"],
            "confidence_phrase": "The available evidence is limited",
            "ambiguity_phrase": "ambiguous",
            "fallback_phrase": (
                "I can identify the likely message, but the available evidence is too weak to state the content confidently."
            ),
            "refuse_to_overclaim": True,
        }
    )

    assert contract["decision"] == "insufficient_evidence"
    assert contract["answer_format"]["shape"] == "single_paragraph"
    assert contract["confidence_wording"] == "The available evidence is limited"
    assert (
        contract["fallback_wording"]
        == "I can identify the likely message, but the available evidence is too weak to state the content confidently."
    )
    assert contract["required_citation_uids"] == ["u1"]


def test_render_final_answer_for_answer_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "subject": "Budget approval",
                "date": "2025-06-05",
                "snippet": "Please approve the budget by Friday.",
                "score": 0.94,
            }
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "answer",
            "verification_mode": "verify_forensic",
            "max_citations": 1,
            "cite_candidate_uids": ["u1"],
            "confidence_phrase": "The evidence strongly indicates",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "fallback_phrase": "fallback",
            "refuse_to_overclaim": True,
        },
        final_answer_contract={
            "decision": "answer",
            "answer_format": {"shape": "single_paragraph"},
            "citation_format": {"style": "inline_uid_brackets"},
            "required_citation_uids": ["u1"],
            "verification_mode": "verify_forensic",
            "refuse_to_overclaim": True,
        },
    )

    assert final_answer["decision"] == "answer"
    assert final_answer["citations"] == ["u1"]
    assert final_answer["text"].startswith("The evidence strongly indicates")
    assert "[uid:u1]" in final_answer["text"]


def test_render_final_answer_for_ambiguous_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {"uid": "u1", "subject": "Vendor A", "date": "2025-06-05", "snippet": "Vendor A was proposed.", "score": 0.81},
            {"uid": "u2", "subject": "Vendor B", "date": "2025-06-06", "snippet": "Vendor B was proposed.", "score": 0.79},
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "ambiguous",
            "verification_mode": "verify_forensic",
            "max_citations": 2,
            "cite_candidate_uids": ["u1", "u2"],
            "confidence_phrase": "The available evidence suggests",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "fallback_phrase": "fallback",
            "refuse_to_overclaim": True,
        },
        final_answer_contract={
            "decision": "ambiguous",
            "answer_format": {"shape": "two_short_paragraphs"},
            "citation_format": {"style": "inline_uid_brackets"},
            "required_citation_uids": ["u1", "u2"],
            "verification_mode": "verify_forensic",
            "refuse_to_overclaim": True,
        },
    )

    assert final_answer["decision"] == "ambiguous"
    assert final_answer["citations"] == ["u1", "u2"]
    assert "\n\n" in final_answer["text"]
    assert "The available evidence is ambiguous" in final_answer["text"]
    assert "[uid:u1]" in final_answer["text"]
    assert "[uid:u2]" in final_answer["text"]


def test_render_final_answer_for_insufficient_evidence_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "subject": "Scan message",
                "date": "2025-06-05",
                "snippet": "No readable body text recovered.",
                "score": 0.55,
                "weak_message": {"code": "image_only"},
            }
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "insufficient_evidence",
            "verification_mode": "already_forensic",
            "max_citations": 1,
            "cite_candidate_uids": ["u1"],
            "confidence_phrase": "The available evidence is limited",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "fallback_phrase": (
                "I can identify the likely message, but the available evidence is too weak to state the content confidently."
            ),
            "refuse_to_overclaim": True,
        },
        final_answer_contract={
            "decision": "insufficient_evidence",
            "answer_format": {"shape": "single_paragraph"},
            "citation_format": {"style": "inline_uid_brackets"},
            "required_citation_uids": ["u1"],
            "verification_mode": "already_forensic",
            "refuse_to_overclaim": True,
        },
    )

    assert final_answer["decision"] == "insufficient_evidence"
    assert final_answer["citations"] == ["u1"]
    assert "too weak to state the content confidently" in final_answer["text"]
    assert "[uid:u1]" in final_answer["text"]
