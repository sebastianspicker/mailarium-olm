from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

from src.email_db import EmailDatabase
from src.evidence_harvest import harvest_wave_payload
from src.mcp_models import BehavioralCaseScopeInput, CasePartyInput
from tests._evidence_cases import make_email


def _wave_payload(uid: str) -> dict[str, object]:
    return {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10", "Q11", "Q34"],
            "scan_id": "scan:test:wave_1",
        },
        "candidates": [
            {
                "uid": uid,
                "rank": 1,
                "score": 0.91,
                "subject": "Meeting notes",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "We decided to cancel your mobile-work day.",
                "verification_status": "retrieval_exact",
                "matched_query_lanes": ["lane_1"],
                "matched_query_queries": ["mobiles Arbeiten BEM"],
                "provenance": {
                    "evidence_handle": "email:test-uid-1:retrieval:body_text:0:42:0",
                },
            },
            {
                "uid": uid,
                "rank": 2,
                "score": 0.74,
                "subject": "Meeting notes",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Fallback summary snippet",
                "verification_status": "retrieval_fallback",
                "matched_query_lanes": ["lane_2"],
                "matched_query_queries": ["home office complaint"],
                "provenance": {
                    "evidence_handle": "email:test-uid-1:retrieval:body_text:42:65:1",
                },
            },
        ],
        "attachment_candidates": [
            {
                "uid": uid,
                "rank": 1,
                "score": 0.63,
                "subject": "Meeting notes",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Attachment excerpt",
                "attachment": {"filename": "protocol.pdf"},
                "matched_query_lanes": ["lane_4"],
                "matched_query_queries": ["Protokoll invite"],
                "provenance": {
                    "evidence_handle": "attachment:test-uid-1:protocol.pdf:0:18",
                },
            }
        ],
    }


def test_evidence_candidate_table_exists() -> None:
    db = EmailDatabase(":memory:")
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "evidence_candidates" in tables
    db.close()


def test_harvest_wave_payload_persists_candidates_and_promotes_exact_quotes() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="We decided to cancel your mobile-work day. Please confirm.")
    db.insert_email(email)

    result = harvest_wave_payload(
        db,
        payload=_wave_payload(email.uid),
        run_id="investigation_2026-04-16_P60",
        phase_id="P60",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert result["status"] == "completed"
    assert result["candidate_count"] == 3
    assert result["body_candidate_count"] == 2
    assert result["attachment_candidate_count"] == 1
    assert result["exact_body_candidate_count"] == 1
    assert result["promoted_count"] == 1

    candidate_stats = db.evidence_candidate_stats(run_id="investigation_2026-04-16_P60")
    assert candidate_stats["total"] == 3
    assert candidate_stats["exact_body_candidates"] == 1
    assert candidate_stats["promoted"] == 1
    assert candidate_stats["attachments"] == 1
    assert candidate_stats["by_wave"][0]["wave_id"] == "wave_1"

    evidence_stats = db.evidence_stats()
    assert evidence_stats["total"] == 1
    assert evidence_stats["verified"] == 1
    db.close()


def test_harvest_wave_payload_dedupes_same_run_and_wave() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="We decided to cancel your mobile-work day. Please confirm.")
    db.insert_email(email)
    payload = _wave_payload(email.uid)

    first = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P60",
        phase_id="P60",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )
    second = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P60",
        phase_id="P60",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert first["candidate_count"] == 3
    assert second["candidate_count"] == 0
    assert second["duplicate_candidate_count"] == 3
    assert second["promoted_count"] == 0
    assert db.evidence_candidate_stats(run_id="investigation_2026-04-16_P60")["total"] == 3
    assert db.evidence_stats()["total"] == 1
    db.close()


def test_harvest_wave_payload_prefers_archive_harvest_bank_over_compact_candidates() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Wir haben entschieden, den mobilen Arbeitstag zu streichen. Bitte bestätigen.")
    db.insert_email(email)
    payload = _wave_payload(email.uid)
    payload["candidates"] = []
    payload["attachment_candidates"] = []
    payload["archive_harvest"] = {
        "evidence_bank": [
            {
                "uid": email.uid,
                "candidate_kind": "body",
                "rank": 1,
                "score": 0.88,
                "subject": "BEM und mobiles Arbeiten",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Wir haben entschieden, den mobilen Arbeitstag zu streichen.",
                "verification_status": "retrieval_exact",
                "body_render_source": "forensic_body_text",
                "harvest_source": "search_result",
                "matched_query_lanes": ["lane_2"],
                "matched_query_queries": ["mobiles Arbeiten widerrufen"],
                "provenance": {"evidence_handle": "email:test-uid-1:retrieval:forensic_body_text:0:63"},
            },
            {
                "uid": email.uid,
                "candidate_kind": "attachment",
                "rank": 2,
                "score": 0.55,
                "subject": "BEM und mobiles Arbeiten",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Anlage: Protokoll",
                "verification_status": "attachment_reference",
                "harvest_source": "attachment_expansion",
                "attachment": {"filename": "protokoll.pdf", "mime_type": "application/pdf"},
                "matched_query_lanes": ["lane_4"],
                "matched_query_queries": ["Protokoll invite"],
                "provenance": {"evidence_handle": "attachment:test-uid-1:protokoll.pdf"},
            },
        ]
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P61",
        phase_id="P61",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert result["candidate_count"] == 2
    assert result["body_candidate_count"] == 1
    assert result["attachment_candidate_count"] == 1
    assert result["exact_body_candidate_count"] == 1
    assert result["promoted_count"] == 1
    db.close()


def test_harvest_wave_payload_does_not_promote_truncated_snippet_as_exact() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Please document the restriction in writing before Friday.")
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10"],
            "scan_id": "scan:test:wave_1",
        },
        "candidates": [
            {
                "uid": email.uid,
                "rank": 1,
                "score": 0.9,
                "subject": "Restriction note",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Please document the restriction...",
                "verification_status": "retrieval_exact",
                "matched_query_lanes": ["lane_1"],
                "matched_query_queries": ["restriction in writing"],
                "provenance": {"evidence_handle": "email:test-uid-1:retrieval:body_text:0:42"},
            }
        ],
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P62",
        phase_id="P62",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    stored = db.conn.execute("SELECT verified_exact, quote_candidate FROM evidence_candidates").fetchone()

    assert result["candidate_count"] == 1
    assert result["exact_body_candidate_count"] == 0
    assert result["promoted_count"] == 0
    assert stored["verified_exact"] == 0
    assert stored["quote_candidate"] == "Please document the restriction..."
    assert db.evidence_stats()["total"] == 0
    db.close()


def test_harvest_wave_payload_persists_support_type_context_for_counterevidence() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Wir haben entschieden, den Antrag nicht zu genehmigen.")
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10"],
            "scan_id": "scan:test:wave_1",
        },
        "archive_harvest": {
            "evidence_bank": [
                {
                    "uid": email.uid,
                    "candidate_kind": "body",
                    "rank": 1,
                    "score": 0.8,
                    "subject": "Follow-up",
                    "sender_email": "alice@example.test",
                    "sender_name": "Alice Manager",
                    "date": "2024-03-15T10:30:00",
                    "conversation_id": "conv-1",
                    "snippet": "den Antrag nicht zu genehmigen",
                    "verification_status": "retrieval_exact",
                    "support_type": "counterevidence",
                    "matched_query_lanes": ["lane_1"],
                    "matched_query_queries": ["Widerspruch"],
                    "provenance": {"evidence_handle": "email:test-uid-1:retrieval:forensic_body_text:0:30"},
                }
            ]
        },
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P63",
        phase_id="P63",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )
    row = db.conn.execute("SELECT context_json FROM evidence_candidates LIMIT 1").fetchone()
    assert row is not None
    context = json.loads(str(row["context_json"] or "{}"))

    assert result["candidate_count"] == 1
    assert context["support_type"] == "counterevidence"
    assert context["counterevidence"] is True
    assert context["comparator_evidence"] is False
    db.close()


def test_actor_discovery_summary_uses_recipients_speakers_and_reply_context() -> None:
    from src.case_analysis_harvest import _actor_discovery_summary

    summary = _actor_discovery_summary(
        evidence_bank=[
            {
                "sender_email": "manager@example.org",
                "sender_name": "Morgan Manager",
                "subject": "Process note",
                "matched_query_lanes": ["lane_1"],
                "recipients_summary": {
                    "visible_recipient_emails": ["peer@example.org"],
                },
                "speaker_attribution": {
                    "quoted_blocks": [{"speaker_email": "witness@example.org"}],
                },
                "reply_context_emails": ["hr@example.org"],
            }
        ],
        params=cast(
            Any,
            SimpleNamespace(
                case_scope=BehavioralCaseScopeInput(
                    target_person=CasePartyInput(name="Alex Example", email="alex@example.org"),
                    suspected_actors=[CasePartyInput(name="Morgan Manager", email="manager@example.org")],
                    allegation_focus=["retaliation"],
                    analysis_goal="lawyer_briefing",
                )
            ),
        ),
    )

    discovered = {row["sender_email"]: row for row in summary["top_discovered_actors"]}

    assert "peer@example.org" in discovered
    assert "witness@example.org" in discovered
    assert "hr@example.org" in discovered


def test_harvest_wave_payload_dedupes_per_phase_not_just_run_and_wave() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="We decided to cancel your mobile-work day. Please confirm.")
    db.insert_email(email)
    payload = _wave_payload(email.uid)

    first = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P63",
        phase_id="P63A",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )
    second = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P63",
        phase_id="P63B",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert first["candidate_count"] == 3
    assert second["candidate_count"] == 3
    assert second["duplicate_candidate_count"] == 0
    assert db.evidence_candidate_stats(run_id="investigation_2026-04-16_P63", phase_id="P63A")["total"] == 3
    assert db.evidence_candidate_stats(run_id="investigation_2026-04-16_P63", phase_id="P63B")["total"] == 3
    db.close()


def test_harvest_wave_payload_promotes_structured_provenance_into_durable_evidence() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Please document the restriction in writing before Friday.")
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10"],
            "scan_id": "scan:test:wave_1",
        },
        "candidates": [
            {
                "uid": email.uid,
                "rank": 1,
                "score": 0.9,
                "subject": "Restriction note",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "Please document the restriction in writing before Friday.",
                "verification_status": "forensic_exact",
                "body_render_source": "forensic_body_text",
                "matched_query_lanes": ["lane_1"],
                "matched_query_queries": ["restriction in writing"],
                "provenance": {
                    "evidence_handle": "email:test-uid-1:retrieval:body_text:0:52",
                    "chunk_id": "chunk-1",
                    "snippet_start": 0,
                    "snippet_end": 52,
                },
            }
        ],
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P64",
        phase_id="P64",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    evidence = db.get_evidence(result["promoted_evidence_ids"][0])

    assert evidence is not None
    assert evidence["candidate_kind"] == "body"
    assert evidence["provenance"] == {
        "evidence_handle": "email:test-uid-1:retrieval:body_text:0:52",
        "chunk_id": "chunk-1",
        "snippet_start": 0,
        "snippet_end": 52,
    }
    assert evidence["document_locator"] == {
        "evidence_handle": "email:test-uid-1:retrieval:body_text:0:52",
        "chunk_id": "chunk-1",
        "snippet_start": 0,
        "snippet_end": 52,
        "body_render_source": "forensic_body_text",
    }
    assert evidence["context"]["wave_id"] == "wave_1"
    assert evidence["context"]["candidate_kind"] == "body"
    db.close()


def test_harvest_wave_payload_does_not_merge_body_and_attachment_exhibits_with_same_quote() -> None:
    db = EmailDatabase(":memory:")
    quote = "Bitte den Termin schriftlich bestaetigen."
    email = make_email(
        body_text=f"Eintrag im Verlauf. {quote} Weitere Details folgen.",
        has_attachments=True,
        attachments=[
            {
                "name": "protokoll.txt",
                "mime_type": "text/plain",
                "size": 64,
                "is_inline": False,
                "extracted_text": quote,
                "text_preview": quote,
                "extraction_state": "text_extracted",
                "evidence_strength": "strong_text",
            }
        ],
    )
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10"],
            "scan_id": "scan:test:wave_1",
        },
        "archive_harvest": {
            "evidence_bank": [
                {
                    "uid": email.uid,
                    "candidate_kind": "body",
                    "rank": 1,
                    "score": 0.9,
                    "subject": "Restriction note",
                    "sender_email": "alice@example.test",
                    "sender_name": "Alice Manager",
                    "date": "2024-03-15T10:30:00",
                    "conversation_id": "conv-1",
                    "snippet": quote,
                    "verification_status": "retrieval_exact",
                    "provenance": {"evidence_handle": f"email:{email.uid}:retrieval:body_text:0:42"},
                },
                {
                    "uid": email.uid,
                    "candidate_kind": "attachment",
                    "rank": 2,
                    "score": 0.8,
                    "subject": "Restriction note",
                    "sender_email": "alice@example.test",
                    "sender_name": "Alice Manager",
                    "date": "2024-03-15T10:30:00",
                    "conversation_id": "conv-1",
                    "snippet": quote,
                    "verification_status": "attachment_reference",
                    "attachment": {"filename": "protokoll.txt", "mime_type": "text/plain"},
                    "provenance": {"evidence_handle": f"attachment:{email.uid}:protokoll.txt"},
                },
            ]
        },
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P65",
        phase_id="P65",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    assert result["promoted_count"] == 2
    assert result["linked_existing_evidence_count"] == 0
    assert db.evidence_stats()["total"] == 2
    promoted = db.list_evidence(limit=10)["items"]
    assert {item["candidate_kind"] for item in promoted} == {"body", "attachment"}
    db.close()


def test_harvest_wave_payload_prefers_locator_slice_for_exact_quote_recovery() -> None:
    db = EmailDatabase(":memory:")
    email = make_email(body_text="Alpha Beta Gamma Delta")
    db.insert_email(email)

    payload = {
        "wave_execution": {
            "wave_id": "wave_1",
            "label": "Dossier Reconciliation",
            "questions": ["Q10"],
            "scan_id": "scan:test:wave_1",
        },
        "candidates": [
            {
                "uid": email.uid,
                "rank": 1,
                "score": 0.9,
                "subject": "Restriction note",
                "sender_email": "alice@example.test",
                "sender_name": "Alice Manager",
                "date": "2024-03-15T10:30:00",
                "conversation_id": "conv-1",
                "snippet": "non-matching snippet",
                "verification_status": "retrieval_exact",
                "body_render_source": "body_text",
                "matched_query_lanes": ["lane_1"],
                "matched_query_queries": ["beta gamma"],
                "provenance": {
                    "evidence_handle": f"email:{email.uid}:retrieval:body_text:6:16",
                    "snippet_start": 6,
                    "snippet_end": 16,
                },
            }
        ],
    }

    result = harvest_wave_payload(
        db,
        payload=payload,
        run_id="investigation_2026-04-16_P66",
        phase_id="P66",
        harvest_limit_per_wave=10,
        promote_limit_per_wave=5,
    )

    stored = db.conn.execute("SELECT quote_candidate, verified_exact FROM evidence_candidates").fetchone()
    assert result["candidate_count"] == 1
    assert result["promoted_count"] == 1
    assert stored["quote_candidate"] == "Beta Gamma"
    assert stored["verified_exact"] == 1
    db.close()
