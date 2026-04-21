"""Review-governance helpers for case-analysis payloads."""

from __future__ import annotations

from typing import Any

from .case_analysis_common import as_dict, as_list, merge_dict

_REVIEWABLE_TARGET_TYPES = (
    "actor_link",
    "chronology_entry",
    "issue_tag_assignment",
    "exhibit_description",
    "contradiction_judgment",
)


def review_provenance_entry(override: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one review-provenance row."""
    override = override if isinstance(override, dict) else {}
    return {
        "review_state": str(override.get("review_state") or "machine_extracted"),
        "provenance_status": ("human_override_applied" if override else "machine_output_only"),
        "reviewer": str(override.get("reviewer") or ""),
        "review_notes": str(override.get("review_notes") or ""),
        "apply_on_refresh": bool(override.get("apply_on_refresh")) if override else False,
        "source_evidence": [item for item in as_list(override.get("source_evidence")) if isinstance(item, dict)],
    }


def annotate_reviewable_items(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark machine-generated reviewable items with default review provenance."""
    actor_graph = as_dict(payload.get("actor_identity_graph"))
    for actor in as_list(actor_graph.get("actors")):
        if isinstance(actor, dict) and "review_provenance" not in actor:
            actor["review_provenance"] = review_provenance_entry()

    actor_map = as_dict(payload.get("actor_map"))
    for actor in as_list(actor_map.get("actors")):
        if isinstance(actor, dict) and "review_provenance" not in actor:
            actor["review_provenance"] = review_provenance_entry()

    chronology = as_dict(payload.get("master_chronology"))
    for entry in as_list(chronology.get("entries")):
        if isinstance(entry, dict) and "review_provenance" not in entry:
            entry["review_provenance"] = review_provenance_entry()

    evidence_index = as_dict(payload.get("matter_evidence_index"))
    for row in as_list(evidence_index.get("rows")):
        if isinstance(row, dict) and "review_provenance" not in row:
            row["review_provenance"] = review_provenance_entry()

    contradictions = as_dict(payload.get("promise_contradiction_analysis"))
    for row in as_list(contradictions.get("contradiction_table")):
        if isinstance(row, dict) and "review_provenance" not in row:
            row["review_provenance"] = review_provenance_entry()

    return payload


def apply_review_overrides(payload: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply persisted human overrides to the shared case-analysis payload."""
    by_target = {
        (str(item.get("target_type") or ""), str(item.get("target_id") or "")): item
        for item in overrides
        if isinstance(item, dict) and bool(item.get("target_type")) and bool(item.get("target_id"))
    }

    actor_graph = as_dict(payload.get("actor_identity_graph"))
    for actor in as_list(actor_graph.get("actors")):
        if not isinstance(actor, dict):
            continue
        actor_id = str(actor.get("actor_id") or "")
        override = by_target.get(("actor_link", actor_id))
        if not override:
            continue
        actor.update(merge_dict(actor, as_dict(override.get("override_payload"))))
        actor["review_provenance"] = review_provenance_entry(override)

    actor_map = as_dict(payload.get("actor_map"))
    for actor in as_list(actor_map.get("actors")):
        if not isinstance(actor, dict):
            continue
        actor_id = str(actor.get("actor_id") or "")
        override = by_target.get(("actor_link", actor_id))
        if not override:
            continue
        actor.update(merge_dict(actor, as_dict(override.get("override_payload"))))
        actor["review_provenance"] = review_provenance_entry(override)

    chronology = as_dict(payload.get("master_chronology"))
    for entry in as_list(chronology.get("entries")):
        if not isinstance(entry, dict):
            continue
        chronology_id = str(entry.get("chronology_id") or "")
        override = by_target.get(("chronology_entry", chronology_id))
        if not override:
            continue
        entry.update(merge_dict(entry, as_dict(override.get("override_payload"))))
        entry["review_provenance"] = review_provenance_entry(override)

    evidence_index = as_dict(payload.get("matter_evidence_index"))
    for row in as_list(evidence_index.get("rows")):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "")
        exhibit_id = str(row.get("exhibit_id") or "")
        exhibit_override = by_target.get(("exhibit_description", source_id)) or by_target.get(("exhibit_description", exhibit_id))
        tag_override = by_target.get(("issue_tag_assignment", source_id)) or by_target.get(("issue_tag_assignment", exhibit_id))
        applied_override = exhibit_override or tag_override
        if exhibit_override:
            row.update(merge_dict(row, as_dict(exhibit_override.get("override_payload"))))
        if tag_override:
            row.update(merge_dict(row, as_dict(tag_override.get("override_payload"))))
        if applied_override:
            row["review_provenance"] = review_provenance_entry(applied_override)

    contradictions = as_dict(payload.get("promise_contradiction_analysis"))
    for row in as_list(contradictions.get("contradiction_table")):
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("row_id") or "")
        override = by_target.get(("contradiction_judgment", row_id))
        if not override:
            continue
        row.update(merge_dict(row, as_dict(override.get("override_payload"))))
        row["review_provenance"] = review_provenance_entry(override)

    return payload


def review_governance_payload(
    *,
    workspace_id: str,
    overrides: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return structured review-state summary for the synthetic matter workspace."""
    review_state_counts = {
        "machine_extracted": 0,
        "human_verified": 0,
        "disputed": 0,
        "draft_only": 0,
        "export_approved": 0,
    }
    target_type_counts = dict.fromkeys(_REVIEWABLE_TARGET_TYPES, 0)
    for override in overrides:
        review_state = str(override.get("review_state") or "")
        target_type = str(override.get("target_type") or "")
        if review_state in review_state_counts:
            review_state_counts[review_state] += 1
        if target_type in target_type_counts:
            target_type_counts[target_type] += 1
    return {
        "workspace_id": workspace_id,
        "default_machine_state": "machine_extracted",
        "override_count": len(overrides),
        "review_state_counts": review_state_counts,
        "target_type_counts": target_type_counts,
        "overrides": overrides,
    }
