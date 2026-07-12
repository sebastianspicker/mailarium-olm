"""Review-governance helpers for case-analysis payloads."""
# pylint: disable=too-many-branches,too-many-locals,too-many-statements

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
    override = as_dict(override)
    return {
        "review_state": str(override.get("review_state") or "machine_extracted"),
        "provenance_status": ("human_override_applied" if override else "machine_output_only"),
        "reviewer": str(override.get("reviewer") or ""),
        "review_notes": str(override.get("review_notes") or ""),
        "apply_on_refresh": bool(override.get("apply_on_refresh")) if override else False,
        "source_evidence": [item for item in as_list(override.get("source_evidence")) if isinstance(item, dict)],
    }


def _annotate_rows(rows: list[Any]) -> None:
    """Attach default provenance to mutable review rows that lack it."""
    for row in rows:
        if isinstance(row, dict) and "review_provenance" not in row:
            row["review_provenance"] = review_provenance_entry()


def _apply_override(row: dict[str, Any], override: dict[str, Any]) -> None:
    """Merge one persisted human override and record its provenance."""
    row.update(merge_dict(row, as_dict(override.get("override_payload"))))
    row["review_provenance"] = review_provenance_entry(override)


def _apply_keyed_overrides(
    rows: list[Any], by_target: dict[tuple[str, str], dict[str, Any]], target_type: str, id_field: str
) -> None:
    """Apply one target-type override to each matching mutable row."""
    for row in rows:
        if isinstance(row, dict):
            override = by_target.get((target_type, str(row.get(id_field) or "")))
            if override:
                _apply_override(row, override)


def _apply_evidence_overrides(rows: list[Any], by_target: dict[tuple[str, str], dict[str, Any]]) -> None:
    """Apply the independent description and issue-tag overrides for evidence rows."""
    for row in rows:
        if not isinstance(row, dict):
            continue
        identifiers = (str(row.get("source_id") or ""), str(row.get("exhibit_id") or ""))
        overrides = [
            by_target.get((target_type, identifiers[0])) or by_target.get((target_type, identifiers[1]))
            for target_type in ("exhibit_description", "issue_tag_assignment")
        ]
        for override in (item for item in overrides if item):
            _apply_override(row, override)


def annotate_reviewable_items(payload: dict[str, Any]) -> dict[str, Any]:
    """Mark machine-generated reviewable items with default review provenance."""
    targets = (
        ("actor_identity_graph", "actors"),
        ("actor_map", "actors"),
        ("master_chronology", "entries"),
        ("matter_evidence_index", "rows"),
        ("promise_contradiction_analysis", "contradiction_table"),
    )
    for section_name, row_name in targets:
        _annotate_rows(as_list(as_dict(payload.get(section_name)).get(row_name)))

    return payload


def apply_review_overrides(payload: dict[str, Any], overrides: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply persisted human overrides to the shared case-analysis payload."""
    by_target = {
        (str(item.get("target_type") or ""), str(item.get("target_id") or "")): item
        for item in overrides
        if isinstance(item, dict) and bool(item.get("target_type")) and bool(item.get("target_id"))
    }

    _apply_keyed_overrides(
        as_list(as_dict(payload.get("actor_identity_graph")).get("actors")), by_target, "actor_link", "actor_id"
    )
    _apply_keyed_overrides(as_list(as_dict(payload.get("actor_map")).get("actors")), by_target, "actor_link", "actor_id")
    _apply_keyed_overrides(
        as_list(as_dict(payload.get("master_chronology")).get("entries")), by_target, "chronology_entry", "chronology_id"
    )
    _apply_evidence_overrides(as_list(as_dict(payload.get("matter_evidence_index")).get("rows")), by_target)
    _apply_keyed_overrides(
        as_list(as_dict(payload.get("promise_contradiction_analysis")).get("contradiction_table")),
        by_target,
        "contradiction_judgment",
        "row_id",
    )

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
