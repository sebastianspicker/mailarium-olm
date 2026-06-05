from __future__ import annotations

# Evidence bank for test 1 (widens_dense_corpus) - first call (narrow)
SPARSE_EVIDENCE_BANK: list[dict] = [
    {
        "uid": "uid-1",
        "conversation_id": "thread-1",
        "sender_email": "a@example.org",
        "date": "2025-01-01",
        "matched_query_lanes": ["lane_1"],
    }
]

# Evidence bank for test 1 - second call (wider)
DENSE_EVIDENCE_BANK: list[dict] = [
    {
        "uid": f"uid-{index}",
        "conversation_id": f"thread-{(index % 5) + 1}",
        "sender_email": f"sender-{index % 4}@example.org",
        "date": f"2025-{(index % 6) + 1:02d}-01",
        "has_attachments": index % 3 == 0,
        "matched_query_lanes": [f"lane_{(index % 5) + 1}"],
    }
    for index in range(1, 13)
]

# Lane diagnostics for test 1 - first call
NARROW_LANE_DIAGNOSTICS: list[dict] = [{"lane_id": f"lane_{idx}", "result_count": 1} for idx in range(1, 5)]

# Lane diagnostics for test 1 - second call
WIDE_LANE_DIAGNOSTICS: list[dict] = [{"lane_id": f"lane_{idx}", "result_count": 1} for idx in range(1, 6)]

# Evidence bank for test 2 (changes_query_shape) - first call
SINGLE_RESULT_EVIDENCE_BANK: list[dict] = [
    {
        "uid": "uid-1",
        "candidate_kind": "body",
        "sender_name": "Neue Beteiligte",
        "sender_email": "peer@example.org",
        "subject": "Koordination und Weiterleitung",
        "date": "2025-01-05",
        "conversation_id": "thread-1",
        "matched_query_lanes": ["lane_1"],
        "verification_status": "retrieval_exact",
        "provenance": {"evidence_handle": "email:uid-1:retrieval"},
    }
]

# Evidence bank for test 2 - second call (expanded)
EXPANDED_EVIDENCE_BANK: list[dict] = [
    {
        "uid": "uid-1",
        "candidate_kind": "body",
        "sender_name": "Neue Beteiligte",
        "sender_email": "peer@example.org",
        "subject": "Koordination und Weiterleitung",
        "date": "2025-01-05",
        "conversation_id": "thread-1",
        "matched_query_lanes": ["lane_1"],
        "verification_status": "retrieval_exact",
        "provenance": {"evidence_handle": "email:uid-1:retrieval"},
    },
    {
        "uid": "uid-2",
        "candidate_kind": "attachment",
        "attachment_filename": "protocol.pdf",
        "sender_name": "Neue Beteiligte",
        "sender_email": "peer@example.org",
        "subject": "Meeting notes",
        "date": "2025-01-06",
        "conversation_id": "thread-2",
        "matched_query_lanes": ["lane_3"],
        "verification_status": "attachment_reference",
        "provenance": {"evidence_handle": "attachment:uid-2:protocol.pdf"},
    },
]

# Evidence bank for test 3 (quality_gate_and_actor_discovery)
ATTACHMENT_EVIDENCE_BANK: list[dict] = [
    {
        "uid": "uid-1",
        "candidate_kind": "body",
        "sender_name": "Neue Beteiligte",
        "sender_email": "peer@example.org",
        "subject": "Koordination und Weiterleitung",
        "date": "2025-01-05",
        "conversation_id": "thread-1",
        "snippet": "Koordination und Absage.",
        "has_attachments": True,
        "matched_query_lanes": ["lane_1"],
        "verification_status": "retrieval_exact",
        "provenance": {"evidence_handle": "email:uid-1:retrieval"},
    },
    {
        "uid": "uid-2",
        "candidate_kind": "attachment",
        "sender_name": "Neue Beteiligte",
        "sender_email": "peer@example.org",
        "subject": "Kalendereinladung",
        "date": "2025-01-06",
        "conversation_id": "thread-1",
        "snippet": "invite.ics",
        "has_attachments": True,
        "matched_query_lanes": ["lane_1"],
        "verification_status": "attachment_reference",
        "provenance": {"evidence_handle": "attachment:uid-2:invite.ics"},
    },
]

# Evidence bank for tests 6-8 (direct/expanded metrics, expansion failures)
SINGLE_BODY_EVIDENCE_BANK: list[dict] = [
    {
        "uid": "uid-1",
        "candidate_kind": "body",
        "sender_email": "alice@example.org",
        "date": "2025-01-05",
        "conversation_id": "thread-1",
        "matched_query_lanes": ["lane_1"],
    }
]

# Test 10: augment_mixed_source_harvest_summary inputs
MIXED_SOURCE_SUMMARY_INPUT: dict = {
    "source_basis": {"email_archive_available": False, "primary_source": "matter_manifest_primary"},
    "coverage_gate": {
        "status": "needs_more_harvest",
        "reasons": [
            "unique_hits_below_threshold",
            "unique_threads_below_threshold",
            "lane_coverage_below_threshold",
        ],
        "recommendations": [
            "Raise harvest breadth and widen actor-plus-issue query lanes.",
            "Expand the strongest hits with thread lookup and similar-message replay.",
        ],
    },
    "quality_gate": {"status": "weak", "score": 0.0, "reasons": ["empty_evidence_bank"]},
    "actor_discovery": {"discovered_actor_count": 0, "roles": {}, "top_discovered_actors": []},
}

MIXED_SOURCE_BUNDLE_INPUT: dict = {
    "sources": [
        {
            "source_id": "manifest:doc:1",
            "source_type": "formal_document",
            "title": "2026-03-12 dossier.pdf",
            "document_locator": {"evidence_handle": "manifest:doc:1", "text_locator": {"line_start": 1}},
        },
        {
            "source_id": "manifest:doc:2",
            "source_type": "formal_document",
            "title": "2026-03-13 memo.pdf",
            "document_locator": {"evidence_handle": "manifest:doc:2", "text_locator": {"line_start": 1}},
        },
        {
            "source_id": "manifest:doc:3",
            "source_type": "formal_document",
            "title": "2026-03-14 note.pdf",
            "document_locator": {"evidence_handle": "manifest:doc:3", "text_locator": {"line_start": 1}},
        },
    ],
    "source_links": [],
    "chronology_anchors": [
        {"source_id": "manifest:doc:1", "date": "2026-03-12"},
        {"source_id": "manifest:doc:2", "date": "2026-03-13"},
        {"source_id": "manifest:doc:3", "date": "2026-03-14"},
    ],
}
