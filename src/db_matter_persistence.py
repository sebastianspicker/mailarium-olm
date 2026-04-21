"""Persistence helpers for matter snapshots and export records."""

from __future__ import annotations

import hashlib
from typing import Any

from .db_matter_helpers import (
    as_dict,
    as_list,
    compact,
    comparator_rows,
    dashboard_rows,
    first_supported_read,
    json_text,
    review_state,
    snapshot_id,
    witness_rows,
)

_REVIEW_STATE_RANK = {
    "superseded": -1,
    "machine_extracted": 0,
    "draft_only": 1,
    "human_verified": 2,
    "disputed": 3,
    "export_approved": 4,
}


def persist_snapshot(
    db: Any,
    *,
    payload: dict[str, Any],
    review_mode: str,
    source_scope: str,
) -> dict[str, Any] | None:
    """Persist one matter snapshot plus flattened registry rows."""
    workspace = as_dict(payload.get("matter_workspace"))
    matter = as_dict(workspace.get("matter"))
    workspace_id = compact(workspace.get("workspace_id"))
    matter_id = compact(matter.get("matter_id"))
    if not workspace_id or not matter_id:
        return None

    snapshot_json = json_text(payload)
    snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    persisted_snapshot_id = snapshot_id(payload)
    persisted_review_state = review_state(payload)
    existing_snapshot = db.latest_matter_snapshot(workspace_id=workspace_id)
    if existing_snapshot and str(existing_snapshot.get("snapshot_id") or "") == persisted_snapshot_id:
        existing_review_state = compact(existing_snapshot.get("review_state"))
        if _REVIEW_STATE_RANK.get(existing_review_state, 0) > _REVIEW_STATE_RANK.get(persisted_review_state, 0):
            persisted_review_state = existing_review_state
    coverage_summary = as_dict(as_dict(payload.get("matter_coverage_ledger")).get("summary"))
    previous_approved_snapshot = db.latest_matter_snapshot(
        workspace_id=workspace_id,
        review_states={"human_verified", "export_approved"},
    )

    db.conn.execute(
        """INSERT INTO matters(
               matter_id, workspace_id, case_label, analysis_goal, date_from, date_to,
               target_person_entity_id, latest_snapshot_id
           ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(matter_id) DO UPDATE SET
               workspace_id=excluded.workspace_id,
               case_label=excluded.case_label,
               analysis_goal=excluded.analysis_goal,
               date_from=excluded.date_from,
               date_to=excluded.date_to,
               target_person_entity_id=excluded.target_person_entity_id,
               latest_snapshot_id=excluded.latest_snapshot_id,
               updated_at=datetime('now')""",
        (
            matter_id,
            workspace_id,
            compact(matter.get("case_label")),
            compact(matter.get("analysis_goal")),
            compact(as_dict(matter.get("date_range")).get("date_from")),
            compact(as_dict(matter.get("date_range")).get("date_to")),
            compact(matter.get("target_person_entity_id")),
            persisted_snapshot_id,
        ),
    )
    db.conn.execute(
        """INSERT INTO matter_snapshots(
               snapshot_id, workspace_id, matter_id, review_mode, source_scope,
               review_state, payload_json, coverage_summary_json
           ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(snapshot_id) DO UPDATE SET
               review_mode=excluded.review_mode,
               source_scope=excluded.source_scope,
               review_state=excluded.review_state,
               payload_json=excluded.payload_json,
               coverage_summary_json=excluded.coverage_summary_json""",
        (
            persisted_snapshot_id,
            workspace_id,
            matter_id,
            review_mode,
            source_scope,
            persisted_review_state,
            snapshot_json,
            json_text(coverage_summary),
        ),
    )

    _clear_snapshot_rows(db, snapshot_id=persisted_snapshot_id)
    row_counts = _persist_snapshot_registry_rows(db, payload=payload, snapshot_id=persisted_snapshot_id)

    db.conn.commit()
    db.log_custody_event(
        "matter_snapshot_upsert",
        target_type="matter_snapshot",
        target_id=persisted_snapshot_id,
        details={
            "workspace_id": workspace_id,
            "matter_id": matter_id,
            "review_mode": review_mode,
            "source_scope": source_scope,
            "review_state": persisted_review_state,
            "row_counts": row_counts,
        },
        content_hash=snapshot_hash,
    )

    changes_since_last_approved: dict[str, Any] | None = None
    if previous_approved_snapshot and str(previous_approved_snapshot.get("snapshot_id") or "") != persisted_snapshot_id:
        changes_since_last_approved = db.diff_matter_snapshots(
            older_snapshot_id=str(previous_approved_snapshot.get("snapshot_id") or ""),
            newer_snapshot_id=persisted_snapshot_id,
        )
    return {
        "workspace_id": workspace_id,
        "matter_id": matter_id,
        "snapshot_id": persisted_snapshot_id,
        "review_state": persisted_review_state,
        "last_approved_snapshot_id": (
            str(previous_approved_snapshot.get("snapshot_id") or "") if previous_approved_snapshot else ""
        ),
        "changes_since_last_approved": changes_since_last_approved,
        "row_counts": row_counts,
    }


def record_export(
    db: Any,
    *,
    snapshot_id: str,
    workspace_id: str,
    delivery_target: str,
    delivery_format: str,
    output_path: str,
    review_state: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one export event tied to a persisted matter snapshot."""
    export_digest = hashlib.sha256(f"{snapshot_id}|{delivery_target}|{delivery_format}|{output_path}".encode()).hexdigest()[:16]
    export_id = f"export:{export_digest}"
    db.conn.execute(
        """INSERT INTO matter_exports(
               export_id, snapshot_id, workspace_id, delivery_target, delivery_format,
               output_path, review_state, details_json
           ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(export_id) DO UPDATE SET
               review_state=excluded.review_state,
               details_json=excluded.details_json,
               output_path=excluded.output_path""",
        (
            export_id,
            snapshot_id,
            workspace_id,
            delivery_target,
            delivery_format,
            output_path,
            review_state,
            json_text(details or {}),
        ),
    )
    db.conn.commit()
    db.log_custody_event(
        "matter_export_record",
        target_type="matter_export",
        target_id=export_id,
        details={
            "snapshot_id": snapshot_id,
            "workspace_id": workspace_id,
            "delivery_target": delivery_target,
            "delivery_format": delivery_format,
            "output_path": output_path,
            "review_state": review_state,
        },
    )
    return {
        "export_id": export_id,
        "snapshot_id": snapshot_id,
        "workspace_id": workspace_id,
        "delivery_target": delivery_target,
        "delivery_format": delivery_format,
        "output_path": output_path,
        "review_state": review_state,
    }


def _clear_snapshot_rows(db: Any, *, snapshot_id: str) -> None:
    for statement in (
        "DELETE FROM matter_sources WHERE snapshot_id = ?",
        "DELETE FROM matter_exhibits WHERE snapshot_id = ?",
        "DELETE FROM matter_chronology_entries WHERE snapshot_id = ?",
        "DELETE FROM matter_actors WHERE snapshot_id = ?",
        "DELETE FROM matter_witnesses WHERE snapshot_id = ?",
        "DELETE FROM matter_comparator_points WHERE snapshot_id = ?",
        "DELETE FROM matter_issue_rows WHERE snapshot_id = ?",
        "DELETE FROM matter_dashboard_cards WHERE snapshot_id = ?",
    ):
        db.conn.execute(statement, (snapshot_id,))


def _persist_snapshot_registry_rows(db: Any, *, payload: dict[str, Any], snapshot_id: str) -> dict[str, int]:
    source_rows = [
        row for row in as_list(as_dict(payload.get("multi_source_case_bundle")).get("sources")) if isinstance(row, dict)
    ]
    if source_rows:
        db.conn.executemany(
            """INSERT INTO matter_sources(
                   snapshot_id, source_id, source_type, document_kind, source_date,
                   actor_id, title, support_level, quality_rank, text_available, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("source_id")),
                    compact(row.get("source_type")),
                    compact(row.get("document_kind")),
                    compact(row.get("date")),
                    compact(row.get("actor_id")),
                    compact(row.get("title")),
                    compact(as_dict(as_dict(row.get("documentary_support")).get("format_profile")).get("support_level")),
                    compact(as_dict(as_dict(row.get("documentary_support")).get("extraction_quality")).get("quality_rank")),
                    int(bool(as_dict(row.get("source_weighting")).get("text_available"))),
                    json_text(row),
                )
                for row in source_rows
                if compact(row.get("source_id"))
            ],
        )

    exhibit_rows = [row for row in as_list(as_dict(payload.get("matter_evidence_index")).get("rows")) if isinstance(row, dict)]
    if exhibit_rows:
        db.conn.executemany(
            """INSERT INTO matter_exhibits(
                   snapshot_id, exhibit_id, source_id, exhibit_date, strength, readiness, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("exhibit_id")),
                    compact(row.get("source_id")),
                    compact(row.get("date")),
                    compact(as_dict(row.get("exhibit_reliability")).get("strength")),
                    compact(as_dict(as_dict(row.get("exhibit_reliability")).get("next_step_logic")).get("readiness")),
                    json_text(row),
                )
                for row in exhibit_rows
                if compact(row.get("exhibit_id"))
            ],
        )

    chronology_rows = [row for row in as_list(as_dict(payload.get("master_chronology")).get("entries")) if isinstance(row, dict)]
    if chronology_rows:
        db.conn.executemany(
            """INSERT INTO matter_chronology_entries(
                   snapshot_id, chronology_id, chronology_date, entry_type, title, primary_read, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("chronology_id")),
                    compact(row.get("date")),
                    compact(row.get("entry_type")),
                    compact(row.get("title")),
                    compact(first_supported_read(row)),
                    json_text(row),
                )
                for row in chronology_rows
                if compact(row.get("chronology_id"))
            ],
        )

    actor_rows = [row for row in as_list(as_dict(payload.get("actor_map")).get("actors")) if isinstance(row, dict)]
    if actor_rows:
        db.conn.executemany(
            """INSERT INTO matter_actors(
                   snapshot_id, actor_id, name, email, role_hint, classification, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("actor_id")),
                    compact(row.get("name")),
                    compact(row.get("email")),
                    compact(row.get("role_hint")),
                    compact(row.get("helps_hurts_mixed")),
                    json_text(row),
                )
                for row in actor_rows
                if compact(row.get("actor_id"))
            ],
        )

    persisted_witness_rows = witness_rows(payload)
    if persisted_witness_rows:
        db.conn.executemany(
            """INSERT INTO matter_witnesses(
                   snapshot_id, witness_id, actor_id, witness_kind, title, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("witness_id")),
                    compact(row.get("actor_id")),
                    compact(row.get("witness_kind")),
                    compact(row.get("title")),
                    json_text(row),
                )
                for row in persisted_witness_rows
                if compact(row.get("witness_id"))
            ],
        )

    persisted_comparator_rows = comparator_rows(payload)
    if persisted_comparator_rows:
        db.conn.executemany(
            """INSERT INTO matter_comparator_points(
                   snapshot_id, comparator_point_id, comparator_issue, comparison_strength,
                   claimant_treatment, comparator_treatment, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("comparator_point_id")),
                    compact(row.get("comparator_issue")),
                    compact(row.get("comparison_strength")),
                    compact(row.get("claimant_treatment")),
                    compact(row.get("comparator_treatment")),
                    json_text(row),
                )
                for row in persisted_comparator_rows
                if compact(row.get("comparator_point_id"))
            ],
        )

    issue_rows = [row for row in as_list(as_dict(payload.get("lawyer_issue_matrix")).get("rows")) if isinstance(row, dict)]
    if issue_rows:
        db.conn.executemany(
            """INSERT INTO matter_issue_rows(
                   snapshot_id, issue_id, title, legal_relevance_status, payload_json
               ) VALUES(?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("issue_id")),
                    compact(row.get("title")),
                    compact(row.get("legal_relevance_status")),
                    json_text(row),
                )
                for row in issue_rows
                if compact(row.get("issue_id"))
            ],
        )

    persisted_dashboard_rows = dashboard_rows(payload)
    if persisted_dashboard_rows:
        db.conn.executemany(
            """INSERT INTO matter_dashboard_cards(
                   snapshot_id, card_id, card_group, title, summary, payload_json
               ) VALUES(?, ?, ?, ?, ?, ?)""",
            [
                (
                    snapshot_id,
                    compact(row.get("card_id")),
                    compact(row.get("card_group")),
                    compact(row.get("title")),
                    compact(row.get("summary")),
                    json_text(row),
                )
                for row in persisted_dashboard_rows
                if compact(row.get("card_id"))
            ],
        )

    return {
        "matter_sources": len(source_rows),
        "matter_exhibits": len(exhibit_rows),
        "matter_chronology_entries": len(chronology_rows),
        "matter_actors": len(actor_rows),
        "matter_witnesses": len(persisted_witness_rows),
        "matter_comparator_points": len(persisted_comparator_rows),
        "matter_issue_rows": len(issue_rows),
        "matter_dashboard_cards": len(persisted_dashboard_rows),
    }
