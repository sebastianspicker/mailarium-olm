"""Shared helpers for persisted matter workspace rows and diffs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def snapshot_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(json_text(payload).encode("utf-8")).hexdigest()[:16]
    return f"snapshot:{digest}"


def review_state(payload: dict[str, Any]) -> str:
    review_counts = as_dict(as_dict(payload.get("review_governance")).get("review_state_counts"))
    if int(review_counts.get("export_approved") or 0) > 0:
        return "export_approved"
    if int(review_counts.get("disputed") or 0) > 0:
        return "disputed"
    if int(review_counts.get("human_verified") or 0) > 0:
        return "human_verified"
    if int(review_counts.get("draft_only") or 0) > 0:
        return "draft_only"
    return "machine_extracted"


def first_supported_read(row: dict[str, Any]) -> str:
    matrix = as_dict(row.get("event_support_matrix"))
    for read_id in (
        "ordinary_managerial_explanation",
        "retaliation",
        "prevention_or_participation_failures",
        "eingruppierung",
        "disability_related_disadvantage",
    ):
        status = compact(as_dict(matrix.get(read_id)).get("status"))
        if status in {"supported", "mixed"}:
            return read_id
    return ""


def witness_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    witness_map = as_dict(payload.get("witness_map"))
    rows: list[dict[str, Any]] = []
    seen_witness_ids: set[str] = set()
    for group_key in (
        "primary_decision_makers",
        "potentially_independent_witnesses",
        "high_value_record_holders",
    ):
        for index, row in enumerate(as_list(witness_map.get(group_key)), start=1):
            if not isinstance(row, dict):
                continue
            actor_id = compact(row.get("actor_id"))
            witness_id = f"{group_key}:{actor_id or index}"
            if witness_id in seen_witness_ids:
                continue
            seen_witness_ids.add(witness_id)
            rows.append(
                {
                    **row,
                    "witness_id": witness_id,
                    "witness_kind": group_key,
                    "title": compact(row.get("name")) or compact(row.get("record_holder_type")) or group_key,
                }
            )
    return rows


def comparator_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    comparative = as_dict(payload.get("comparative_treatment"))
    comparator_points = [row for row in as_list(comparative.get("comparator_points")) if isinstance(row, dict)]
    if comparator_points:
        point_rows: list[dict[str, Any]] = []
        for index, row in enumerate(comparator_points, start=1):
            point_rows.append(
                {
                    "comparator_point_id": compact(row.get("comparator_point_id")) or f"cmp:{index}",
                    "comparator_issue": compact(row.get("issue_label")) or compact(row.get("issue_id")),
                    "comparison_strength": compact(row.get("comparison_strength")),
                    "claimant_treatment": compact(row.get("claimant_treatment")),
                    "comparator_treatment": compact(row.get("comparator_treatment")),
                    "summary_ref": compact(row.get("comparator_actor_id")) or compact(row.get("comparator_email")),
                    **row,
                }
            )
        return point_rows
    rows: list[dict[str, Any]] = []
    for summary_index, summary in enumerate(as_list(comparative.get("comparator_summaries")), start=1):
        if not isinstance(summary, dict):
            continue
        matrix_rows = as_list(as_dict(summary.get("comparator_matrix")).get("rows"))
        if matrix_rows:
            for row_index, row in enumerate(matrix_rows, start=1):
                if not isinstance(row, dict):
                    continue
                rows.append(
                    {
                        "comparator_point_id": f"cmp:{summary_index}:{row_index}",
                        "comparator_issue": compact(row.get("issue_label")) or compact(row.get("title")),
                        "comparison_strength": compact(row.get("comparison_strength")),
                        "claimant_treatment": compact(row.get("claimant_treatment")),
                        "comparator_treatment": compact(row.get("comparator_treatment")),
                        "summary_ref": compact(summary.get("comparator_actor_id")) or compact(summary.get("comparator_email")),
                        **row,
                    }
                )
            continue
        rows.append(
            {
                "comparator_point_id": f"cmp:{summary_index}",
                "comparator_issue": compact(summary.get("status")) or "comparator_status",
                "comparison_strength": compact(summary.get("comparison_quality")),
                "claimant_treatment": "",
                "comparator_treatment": "",
                **summary,
            }
        )
    return rows


def dashboard_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    dashboard = as_dict(payload.get("case_dashboard"))
    rows: list[dict[str, Any]] = []
    for group_name, cards in as_dict(dashboard.get("cards")).items():
        for index, card in enumerate(as_list(cards), start=1):
            if not isinstance(card, dict):
                continue
            rows.append(
                {
                    "card_id": f"{group_name}:{index}",
                    "card_group": group_name,
                    "title": compact(card.get("title")) or compact(card.get("issue_id")) or compact(card.get("warning_id")),
                    "summary": compact(card.get("summary"))
                    or compact(card.get("evidence_hint"))
                    or compact(card.get("date"))
                    or compact(card.get("severity")),
                    **card,
                }
            )
    return rows


def registry_ids(payload: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "source_ids": {
            compact(row.get("source_id"))
            for row in as_list(as_dict(payload.get("multi_source_case_bundle")).get("sources"))
            if isinstance(row, dict) and compact(row.get("source_id"))
        },
        "exhibit_ids": {
            compact(row.get("exhibit_id"))
            for row in as_list(as_dict(payload.get("matter_evidence_index")).get("rows"))
            if isinstance(row, dict) and compact(row.get("exhibit_id"))
        },
        "chronology_ids": {
            compact(row.get("chronology_id"))
            for row in as_list(as_dict(payload.get("master_chronology")).get("entries"))
            if isinstance(row, dict) and compact(row.get("chronology_id"))
        },
        "actor_ids": {
            compact(row.get("actor_id"))
            for row in as_list(as_dict(payload.get("actor_map")).get("actors"))
            if isinstance(row, dict) and compact(row.get("actor_id"))
        },
        "witness_ids": {compact(row.get("witness_id")) for row in witness_rows(payload) if compact(row.get("witness_id"))},
        "comparator_point_ids": {
            compact(row.get("comparator_point_id")) for row in comparator_rows(payload) if compact(row.get("comparator_point_id"))
        },
        "issue_ids": {
            compact(row.get("issue_id"))
            for row in as_list(as_dict(payload.get("lawyer_issue_matrix")).get("rows"))
            if isinstance(row, dict) and compact(row.get("issue_id"))
        },
        "dashboard_card_ids": {compact(row.get("card_id")) for row in dashboard_rows(payload) if compact(row.get("card_id"))},
    }


def diff_registry_sets(previous: dict[str, set[str]], current: dict[str, set[str]]) -> dict[str, Any]:
    changed_registries: list[str] = []
    registry_changes: dict[str, Any] = {}
    for registry_name in sorted(set(previous) | set(current)):
        previous_ids = previous.get(registry_name, set())
        current_ids = current.get(registry_name, set())
        added = sorted(current_ids - previous_ids)
        removed = sorted(previous_ids - current_ids)
        unchanged_count = len(current_ids & previous_ids)
        if added or removed:
            changed_registries.append(registry_name)
        registry_changes[registry_name] = {
            "added_ids": added,
            "removed_ids": removed,
            "added_count": len(added),
            "removed_count": len(removed),
            "unchanged_count": unchanged_count,
        }
    return {
        "changed": bool(changed_registries),
        "changed_registries": changed_registries,
        "registry_changes": registry_changes,
    }
