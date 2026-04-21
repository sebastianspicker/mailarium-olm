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


def test_answer_quality_prefers_calibrated_body_evidence_over_slightly_higher_synthetic_segment_score():
    from src.tools.search_answer_context import _answer_quality

    summary = _answer_quality(
        candidates=[
            {"uid": "u-body", "score": 0.81, "conversation_id": "c1", "score_calibration": "calibrated"},
            {
                "uid": "u-segment",
                "score": 0.82,
                "conversation_id": "c2",
                "score_kind": "segment_sql",
                "score_calibration": "synthetic",
            },
        ],
        attachment_candidates=[],
        conversation_groups=[],
    )

    assert summary["top_candidate_uid"] == "u-body"


def test_answer_quality_exposes_stable_top_candidate_reference():
    from src.tools.search_answer_context import _answer_quality

    summary = _answer_quality(
        candidates=[
            {
                "uid": "u-body",
                "score": 0.83,
                "conversation_id": "c1",
                "provenance": {"evidence_handle": "email:u-body:retrieval:body_text:0:18"},
            },
            {
                "uid": "u-attachment",
                "score": 0.81,
                "conversation_id": "c1",
                "attachment": {"filename": "note.pdf"},
                "provenance": {"evidence_handle": "attachment:u-attachment:note.pdf:chunk-1:0:18"},
            },
        ],
        attachment_candidates=[],
        conversation_groups=[],
    )

    assert summary["top_candidate_reference"] == {
        "uid": "u-body",
        "evidence_handle": "email:u-body:retrieval:body_text:0:18",
    }


def test_timeline_summary_tracks_sender_thread_and_recipient_set_changes():
    from src.tools.search_answer_context import _timeline_summary

    timeline = _timeline_summary(
        candidates=[
            {
                "uid": "u1",
                "date": "2025-06-01",
                "conversation_id": "conv-a",
                "thread_group_id": "conv-a",
                "sender_email": "employee@example.test",
                "sender_actor_id": "actor-alice",
                "score": 0.81,
                "snippet": "First",
                "recipients_summary": {
                    "status": "available",
                    "signature": "bob@example.com",
                    "visible_recipient_count": 1,
                    "visible_recipient_emails": ["bob@example.com"],
                },
            },
            {
                "uid": "u2",
                "date": "2025-06-02",
                "conversation_id": "conv-a",
                "thread_group_id": "conv-a",
                "sender_email": "employee@example.test",
                "sender_actor_id": "actor-alice",
                "score": 0.92,
                "snippet": "Second",
                "recipients_summary": {
                    "status": "available",
                    "signature": "bob@example.com|carol@example.com",
                    "visible_recipient_count": 2,
                    "visible_recipient_emails": ["bob@example.com", "carol@example.com"],
                },
            },
            {
                "uid": "u3",
                "date": "2025-06-03",
                "conversation_id": "conv-b",
                "thread_group_id": "conv-b",
                "sender_email": "carol@example.com",
                "sender_actor_id": "actor-carol",
                "score": 0.77,
                "snippet": "Third",
                "recipients_summary": {
                    "status": "available",
                    "signature": "bob@example.com|carol@example.com",
                    "visible_recipient_count": 2,
                    "visible_recipient_emails": ["bob@example.com", "carol@example.com"],
                },
            },
        ],
        attachment_candidates=[],
    )

    assert timeline["event_count"] == 3
    assert timeline["unique_sender_count"] == 2
    assert timeline["unique_thread_group_count"] == 2
    assert timeline["sender_change_count"] == 1
    assert timeline["thread_change_count"] == 1
    assert timeline["recipient_set_change_count"] == 1
    assert timeline["events"][1]["recipient_set_changed_from_previous"] is True
    assert timeline["events"][2]["sender_changed_from_previous"] is True
    assert timeline["events"][2]["thread_changed_from_previous"] is True


def test_answer_policy_prefers_forensic_verification_for_quotes():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="What did they say exactly about the complaint?",
        evidence_mode="retrieval",
        candidates=[{"uid": "u1", "score": 0.92}],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "high",
            "ambiguity_reason": "",
            "top_candidate_uid": "u1",
            "alternative_candidates": [],
        },
    )

    assert policy["decision"] == "answer"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["cite_candidate_uids"] == ["u1"]
    assert policy["cite_candidate_references"] == [{"uid": "u1", "evidence_handle": ""}]


def test_answer_policy_marks_ambiguous_cases_without_overclaiming():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="Who sent the note?",
        evidence_mode="retrieval",
        candidates=[{"uid": "u1", "score": 0.81}, {"uid": "u2", "score": 0.79}],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "ambiguous",
            "ambiguity_reason": "close_top_scores",
            "top_candidate_uid": "u1",
            "alternative_candidates": ["u2"],
        },
    )

    assert policy["decision"] == "ambiguous"
    assert policy["max_citations"] == 2
    assert policy["cite_candidate_uids"] == ["u1", "u2"]
    assert policy["cite_candidate_references"] == [
        {"uid": "u1", "evidence_handle": ""},
        {"uid": "u2", "evidence_handle": ""},
    ]
    assert policy["refuse_to_overclaim"] is True


def test_answer_policy_marks_insufficient_evidence_for_weak_message():
    from src.tools.search_answer_context import _answer_policy

    policy = _answer_policy(
        question="What does the scan prove?",
        evidence_mode="retrieval",
        candidates=[{"uid": "u1", "score": 0.88, "weak_message": {"reason": "scan-only"}}],
        attachment_candidates=[],
        answer_quality={
            "confidence_label": "high",
            "ambiguity_reason": "",
            "top_candidate_uid": "u1",
            "alternative_candidates": [],
        },
    )

    assert policy["decision"] == "insufficient_evidence"
    assert policy["verification_mode"] == "verify_forensic"
    assert policy["cite_candidate_uids"] == ["u1"]
    assert policy["cite_candidate_references"] == [{"uid": "u1", "evidence_handle": ""}]


def test_final_answer_contract_for_ambiguous_response():
    from src.tools.search_answer_context import _final_answer_contract

    contract = _final_answer_contract(
        answer_policy={
            "decision": "ambiguous",
            "max_citations": 2,
            "cite_candidate_uids": ["u1", "u2"],
            "cite_candidate_references": [
                {"uid": "u1", "evidence_handle": "email:u1:retrieval:body_text:0:12"},
                {"uid": "u2", "evidence_handle": "email:u2:retrieval:body_text:0:12"},
            ],
            "verification_mode": "verify_forensic",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "refuse_to_overclaim": True,
        }
    )

    assert contract["decision"] == "ambiguous"
    assert contract["answer_format"]["shape"] == "two_short_paragraphs"
    assert contract["required_citation_uids"] == ["u1", "u2"]
    assert contract["required_citation_handles"] == [
        "email:u1:retrieval:body_text:0:12",
        "email:u2:retrieval:body_text:0:12",
    ]


def test_final_answer_contract_for_insufficient_evidence_response():
    from src.tools.search_answer_context import _final_answer_contract

    contract = _final_answer_contract(
        answer_policy={
            "decision": "insufficient_evidence",
            "max_citations": 1,
            "cite_candidate_uids": ["u1"],
            "cite_candidate_references": [{"uid": "u1", "evidence_handle": "email:u1:retrieval:body_text:0:12"}],
            "verification_mode": "verify_forensic",
            "fallback_phrase": "Too weak to state confidently.",
            "refuse_to_overclaim": True,
        }
    )

    assert contract["decision"] == "insufficient_evidence"
    assert contract["answer_format"]["include_fallback_wording"] is True
    assert contract["required_citation_uids"] == ["u1"]
    assert contract["required_citation_handles"] == ["email:u1:retrieval:body_text:0:12"]


def test_render_final_answer_for_answer_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "score": 0.94,
                "subject": "Complaint update",
                "date": "2025-06-03",
                "provenance": {"evidence_handle": "email:u1:retrieval:body_text:0:18"},
            },
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "answer",
            "confidence_phrase": "The evidence strongly indicates",
            "verification_mode": "verify_forensic",
        },
        final_answer_contract={
            "decision": "answer",
            "confidence_wording": "The evidence strongly indicates",
            "required_citation_uids": ["u1"],
            "required_citation_handles": ["email:u1:retrieval:body_text:0:18"],
            "verification_mode": "verify_forensic",
            "answer_format": {"shape": "single_paragraph"},
        },
    )

    assert final_answer["decision"] == "answer"
    assert "[ref:email:u1:retrieval:body_text:0:18]" in final_answer["text"]
    assert "Complaint update" in final_answer["text"]


def test_render_final_answer_prefers_exact_excerpt_for_exact_wording_requests():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "score": 0.94,
                "snippet": "We are withdrawing the task assignment effective immediately.",
                "verification_status": "forensic_exact",
                "exact_wording_requested": True,
                "provenance": {"evidence_handle": "email:u1:retrieval:body_text:0:58"},
            },
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "answer",
            "confidence_phrase": "The evidence strongly indicates",
            "verification_mode": "verify_forensic",
            "exact_wording_requested": True,
        },
        final_answer_contract={
            "decision": "answer",
            "confidence_wording": "The evidence strongly indicates",
            "required_citation_uids": ["u1"],
            "required_citation_handles": ["email:u1:retrieval:body_text:0:58"],
            "verification_mode": "verify_forensic",
            "exact_wording_requested": True,
            "answer_format": {"shape": "single_paragraph"},
        },
    )

    assert '"We are withdrawing the task assignment effective immediately."' in final_answer["text"]


def test_exact_wording_classifier_handles_broader_english_and_german_variants():
    from src.tools.search_answer_context_rendering import _question_requests_exact_wording

    assert _question_requests_exact_wording("Give the exact quote word-for-word.") is True
    assert _question_requests_exact_wording("Mit welchem Wortlaut genau wurde das geschrieben?") is True
    assert _question_requests_exact_wording("Who replied first after the complaint?") is False


def test_render_final_answer_for_ambiguous_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "score": 0.81,
                "subject": "First option",
                "date": "2025-06-03",
                "provenance": {"evidence_handle": "email:u1:retrieval:body_text:0:10"},
            },
            {
                "uid": "u2",
                "score": 0.79,
                "subject": "Second option",
                "date": "2025-06-04",
                "provenance": {"evidence_handle": "email:u2:retrieval:body_text:0:11"},
            },
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "ambiguous",
            "ambiguity_phrase": "The available evidence is ambiguous",
            "verification_mode": "verify_forensic",
        },
        final_answer_contract={
            "decision": "ambiguous",
            "ambiguity_wording": "The available evidence is ambiguous",
            "required_citation_uids": ["u1", "u2"],
            "required_citation_handles": [
                "email:u1:retrieval:body_text:0:10",
                "email:u2:retrieval:body_text:0:11",
            ],
            "verification_mode": "verify_forensic",
            "answer_format": {"shape": "two_short_paragraphs"},
        },
    )

    assert final_answer["decision"] == "ambiguous"
    assert "\n\n" in final_answer["text"]
    assert "[ref:email:u1:retrieval:body_text:0:10]" in final_answer["text"]
    assert "[ref:email:u2:retrieval:body_text:0:11]" in final_answer["text"]


def test_render_final_answer_for_insufficient_evidence_response():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[
            {
                "uid": "u1",
                "score": 0.61,
                "subject": "Likely option",
                "date": "2025-06-03",
                "provenance": {"evidence_handle": "email:u1:retrieval:body_text:0:12"},
            },
        ],
        attachment_candidates=[],
        answer_policy={
            "decision": "insufficient_evidence",
            "fallback_phrase": "Too weak to state confidently.",
            "verification_mode": "verify_forensic",
        },
        final_answer_contract={
            "decision": "insufficient_evidence",
            "fallback_wording": "Too weak to state confidently.",
            "required_citation_uids": ["u1"],
            "required_citation_handles": ["email:u1:retrieval:body_text:0:12"],
            "verification_mode": "verify_forensic",
            "answer_format": {"shape": "single_paragraph"},
        },
    )

    assert final_answer["decision"] == "insufficient_evidence"
    assert "Too weak to state confidently." in final_answer["text"]
    assert "[ref:email:u1:retrieval:body_text:0:12]" in final_answer["text"]


def test_render_final_answer_uses_attachment_handle_for_attachment_evidence():
    from src.tools.search_answer_context import _render_final_answer

    final_answer = _render_final_answer(
        candidates=[],
        attachment_candidates=[
            {
                "uid": "u-attachment",
                "score": 0.91,
                "subject": "Policy memo",
                "date": "2025-06-03",
                "attachment": {"filename": "policy.pdf"},
                "provenance": {"evidence_handle": "attachment:u-attachment:policy.pdf:chunk-1:0:40"},
            },
        ],
        answer_policy={
            "decision": "answer",
            "confidence_phrase": "The evidence strongly indicates",
            "verification_mode": "verify_forensic",
        },
        final_answer_contract={
            "decision": "answer",
            "confidence_wording": "The evidence strongly indicates",
            "required_citation_uids": ["u-attachment"],
            "required_citation_handles": ["attachment:u-attachment:policy.pdf:chunk-1:0:40"],
            "verification_mode": "verify_forensic",
            "answer_format": {"shape": "single_paragraph"},
        },
    )

    assert "[ref:attachment:u-attachment:policy.pdf:chunk-1:0:40]" in final_answer["text"]
