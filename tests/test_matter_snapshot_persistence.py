from __future__ import annotations

from src.email_db import EmailDatabase


def _payload() -> dict[str, object]:
    return {
        "matter_workspace": {
            "workspace_id": "workspace:abc123",
            "matter": {
                "matter_id": "matter:abc123",
                "bundle_id": "case-123",
                "case_label": "Case 123",
                "analysis_goal": "lawyer_briefing",
                "date_range": {
                    "date_from": "2025-01-01",
                    "date_to": "2025-06-30",
                },
                "target_person_entity_id": "person:target",
            },
        },
        "multi_source_case_bundle": {
            "sources": [
                {
                    "source_id": "email:uid-1",
                    "source_type": "email",
                    "document_kind": "email_body",
                    "date": "2025-03-10",
                    "actor_id": "actor-manager",
                    "title": "Status",
                    "source_weighting": {"text_available": True},
                }
            ]
        },
        "matter_evidence_index": {
            "rows": [
                {
                    "exhibit_id": "EXH-001",
                    "source_id": "email:uid-1",
                    "date": "2025-03-10",
                    "exhibit_reliability": {
                        "strength": "strong",
                        "next_step_logic": {"readiness": "usable_now"},
                    },
                }
            ]
        },
        "master_chronology": {
            "entries": [
                {
                    "chronology_id": "CHR-001",
                    "date": "2025-03-10",
                    "entry_type": "source_record",
                    "title": "Status",
                    "event_support_matrix": {
                        "ordinary_managerial_explanation": {"status": "mixed"},
                    },
                }
            ]
        },
        "actor_map": {
            "actors": [
                {
                    "actor_id": "actor-manager",
                    "name": "manager",
                    "email": "manager@example.test",
                    "role_hint": "manager",
                    "helps_hurts_mixed": "mixed",
                }
            ]
        },
        "witness_map": {
            "primary_decision_makers": [{"actor_id": "actor-manager", "name": "manager"}],
            "potentially_independent_witnesses": [],
            "high_value_record_holders": [],
        },
        "comparative_treatment": {
            "comparator_summaries": [
                {
                    "comparator_actor_id": "actor-peer",
                    "comparator_matrix": {
                        "rows": [
                            {
                                "issue_label": "Mobile work approvals",
                                "comparison_strength": "moderate",
                                "claimant_treatment": "Restricted",
                                "comparator_treatment": "Approved",
                            }
                        ]
                    },
                }
            ]
        },
        "lawyer_issue_matrix": {
            "rows": [
                {
                    "issue_id": "issue:retaliation",
                    "title": "Retaliation / Maßregelung",
                    "legal_relevance_status": "potentially_relevant",
                }
            ]
        },
        "case_dashboard": {
            "cards": {
                "main_claims_or_issues": [
                    {
                        "issue_id": "issue:retaliation",
                        "title": "Retaliation / Maßregelung",
                        "evidence_hint": "Timing shift after rights assertion.",
                    }
                ]
            }
        },
        "review_governance": {
            "review_state_counts": {
                "machine_extracted": 0,
                "human_verified": 1,
                "disputed": 0,
                "draft_only": 0,
                "export_approved": 0,
            }
        },
        "matter_coverage_ledger": {
            "summary": {
                "coverage_status": "complete",
                "total_source_count": 1,
            }
        },
    }


def test_matter_snapshot_tables_exist() -> None:
    db = EmailDatabase(":memory:")
    tables = {row[0] for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "matters" in tables
    assert "matter_snapshots" in tables
    assert "matter_sources" in tables
    assert "matter_exhibits" in tables
    assert "matter_chronology_entries" in tables
    assert "matter_actors" in tables
    assert "matter_witnesses" in tables
    assert "matter_comparator_points" in tables
    assert "matter_issue_rows" in tables
    assert "matter_dashboard_cards" in tables
    assert "matter_exports" in tables
    db.close()


def test_persist_matter_snapshot_writes_registry_rows_and_can_be_loaded() -> None:
    db = EmailDatabase(":memory:")

    result = db.persist_matter_snapshot(
        payload=_payload(),
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )

    assert result is not None
    assert result["workspace_id"] == "workspace:abc123"
    assert result["review_state"] == "human_verified"
    assert result["row_counts"]["matter_sources"] == 1
    assert result["row_counts"]["matter_exhibits"] == 1
    assert result["row_counts"]["matter_dashboard_cards"] == 1

    snapshots = db.list_matter_snapshots(workspace_id="workspace:abc123")
    assert len(snapshots) == 1
    assert snapshots[0]["coverage_summary"]["coverage_status"] == "complete"
    assert db.latest_matter_snapshot(workspace_id="workspace:abc123") is not None

    loaded = db.get_matter_snapshot(snapshot_id=result["snapshot_id"])
    assert loaded is not None
    assert loaded["matter_workspace"]["matter"]["matter_id"] == "matter:abc123"

    export = db.record_matter_export(
        snapshot_id=result["snapshot_id"],
        workspace_id="workspace:abc123",
        delivery_target="counsel_handoff",
        delivery_format="html",
        output_path="out/legal_support_export.html",
        review_state="human_verified",
        details={"artifact_count": 1},
    )
    assert export["delivery_target"] == "counsel_handoff"
    events = db.get_custody_chain(action="matter_snapshot_upsert")
    assert events
    export_events = db.get_custody_chain(action="matter_export_record")
    assert export_events
    db.close()


def test_snapshot_review_state_and_diff_workflow() -> None:
    db = EmailDatabase(":memory:")

    first_result = db.persist_matter_snapshot(
        payload=_payload(),
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert first_result is not None

    approved = db.set_matter_snapshot_review_state(
        snapshot_id=first_result["snapshot_id"],
        review_state="export_approved",
    )
    assert approved["review_state"] == "export_approved"

    updated_payload = _payload()
    updated_payload["multi_source_case_bundle"]["sources"].append(  # type: ignore[index]
        {
            "source_id": "formal_document:policy-1",
            "source_type": "formal_document",
            "document_kind": "attached_document",
            "date": "2025-03-12",
            "title": "Policy note",
            "source_weighting": {"text_available": True},
        }
    )
    second_result = db.persist_matter_snapshot(
        payload=updated_payload,
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert second_result is not None
    assert second_result["last_approved_snapshot_id"] == first_result["snapshot_id"]
    changes = second_result["changes_since_last_approved"]
    assert changes is not None
    assert changes["changed"] is True
    assert "source_ids" in changes["changed_registries"]
    assert changes["registry_changes"]["source_ids"]["added_ids"] == ["formal_document:policy-1"]

    second_approved = db.set_matter_snapshot_review_state(
        snapshot_id=second_result["snapshot_id"],
        review_state="export_approved",
    )
    assert second_approved["superseded_snapshot_ids"] == [first_result["snapshot_id"]]

    snapshots = db.list_matter_snapshots(workspace_id="workspace:abc123")
    by_id = {row["snapshot_id"]: row for row in snapshots}
    assert by_id[first_result["snapshot_id"]]["review_state"] == "superseded"
    assert by_id[second_result["snapshot_id"]]["review_state"] == "export_approved"
    db.close()


def test_persist_identical_snapshot_preserves_stronger_review_state() -> None:
    db = EmailDatabase(":memory:")

    first_result = db.persist_matter_snapshot(
        payload=_payload(),
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert first_result is not None

    db.set_matter_snapshot_review_state(
        snapshot_id=first_result["snapshot_id"],
        review_state="human_verified",
    )

    repeated_result = db.persist_matter_snapshot(
        payload=_payload(),
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert repeated_result is not None
    assert repeated_result["snapshot_id"] == first_result["snapshot_id"]
    assert repeated_result["review_state"] == "human_verified"

    latest = db.latest_matter_snapshot(workspace_id="workspace:abc123")
    assert latest is not None
    assert latest["review_state"] == "human_verified"
    db.close()


def test_persist_snapshot_uses_draft_only_for_internal_review_state() -> None:
    db = EmailDatabase(":memory:")
    payload = _payload()
    payload["review_governance"]["review_state_counts"] = {
        "machine_extracted": 0,
        "human_verified": 0,
        "disputed": 0,
        "draft_only": 1,
        "export_approved": 0,
    }

    result = db.persist_matter_snapshot(
        payload=payload,
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )

    assert result is not None
    assert result["review_state"] == "draft_only"
    latest = db.latest_matter_snapshot(workspace_id="workspace:abc123")
    assert latest is not None
    assert latest["review_state"] == "draft_only"
    db.close()


def test_latest_snapshot_prefers_latest_snapshot_id_on_same_second() -> None:
    db = EmailDatabase(":memory:")

    first_payload = _payload()
    first_result = db.persist_matter_snapshot(
        payload=first_payload,
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert first_result is not None

    second_payload = _payload()
    second_payload["case_dashboard"]["cards"]["main_claims_or_issues"][0]["evidence_hint"] = "Updated hint"  # type: ignore[index]
    second_result = db.persist_matter_snapshot(
        payload=second_payload,
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )
    assert second_result is not None

    latest = db.latest_matter_snapshot(workspace_id="workspace:abc123")
    assert latest is not None
    assert latest["snapshot_id"] == second_result["snapshot_id"]

    snapshots = db.list_matter_snapshots(workspace_id="workspace:abc123")
    assert snapshots[0]["snapshot_id"] == second_result["snapshot_id"]
    db.close()


def test_persist_matter_snapshot_deduplicates_duplicate_witness_ids() -> None:
    db = EmailDatabase(":memory:")

    payload = _payload()
    payload["witness_map"]["high_value_record_holders"] = [  # type: ignore[index]
        {"actor_id": "actor-manager", "name": "manager"},
        {"actor_id": "actor-manager", "name": "manager"},
    ]

    result = db.persist_matter_snapshot(
        payload=payload,
        review_mode="exhaustive_matter_review",
        source_scope="mixed_case_file",
    )

    assert result is not None
    assert result["row_counts"]["matter_witnesses"] == 2

    witness_count = db.conn.execute("SELECT COUNT(*) FROM matter_witnesses").fetchone()[0]
    assert witness_count == 2
    db.close()
