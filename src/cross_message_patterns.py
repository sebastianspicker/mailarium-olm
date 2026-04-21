"""Cross-message aggregation helpers for behavioural-analysis case patterns."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Literal, TypedDict

CASE_PATTERN_VERSION = "1"

RecurrenceLabel = Literal[
    "isolated",
    "repeated",
    "escalating",
    "systematic",
    "targeted",
    "possibly_coordinated",
]


class PatternSummary(TypedDict):
    """Case-level summary for one behavior or taxonomy cluster."""

    cluster_id: str
    cluster_type: Literal["behavior", "taxonomy", "thread"]
    key: str
    message_count: int
    message_uids: list[str]
    actor_ids: list[str]
    thread_group_ids: list[str]
    first_date: str
    last_date: str
    primary_recurrence: RecurrenceLabel
    recurrence_flags: list[RecurrenceLabel]


def _date_key(value: str) -> tuple[int, str]:
    """Return a sortable date key tolerant of partial or invalid inputs."""
    if not value:
        return (1, "")
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return (0, parsed.isoformat())
    except ValueError:
        return (0, value)


def _ordered_unique(values: list[str]) -> list[str]:
    """Return ordered unique strings, skipping empties."""
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _confidence_score(confidence: str) -> int:
    """Map candidate confidence labels to a sortable numeric value."""
    return {
        "low": 1,
        "medium": 2,
        "high": 3,
    }.get(str(confidence or "").lower(), 0)


def _primary_recurrence(
    *,
    message_count: int,
    actor_count: int,
    thread_count: int,
    target_actor_id: str,
    sender_actor_ids: list[str],
    dated_rows: list[dict[str, Any]],
) -> tuple[RecurrenceLabel, list[RecurrenceLabel]]:
    """Return a conservative recurrence classification with supporting flags."""
    flags: list[RecurrenceLabel] = []
    if message_count == 1:
        return "isolated", flags
    if target_actor_id and len(_ordered_unique(sender_actor_ids)) == 1 and message_count >= 2:
        flags.append("targeted")
    if actor_count >= 2 and thread_count >= 2 and message_count >= 3:
        flags.append("possibly_coordinated")
    confidence_trend = [
        _confidence_score(str(row.get("confidence") or ""))
        for row in sorted(dated_rows, key=lambda row: _date_key(str(row.get("date") or "")))
    ]
    if (
        message_count >= 4
        and actor_count >= 2
        and thread_count >= 2
    ):
        primary: RecurrenceLabel = "systematic"
    elif (
        message_count >= 3
        and confidence_trend
        and confidence_trend[-1] >= confidence_trend[0]
        and any(
            str(row.get("behavior_id") or "") in {"escalation", "deadline_pressure", "public_correction"}
            for row in dated_rows
        )
    ):
        primary = "escalating"
    else:
        primary = "repeated"
    return primary, flags


def _pattern_summary(
    *,
    cluster_type: Literal["behavior", "taxonomy", "thread"],
    key: str,
    rows: list[dict[str, Any]],
    target_actor_id: str,
) -> PatternSummary:
    """Build one conservative pattern summary from clustered message rows."""
    ordered_rows = sorted(rows, key=lambda row: (_date_key(str(row.get("date") or "")), str(row.get("uid") or "")))
    message_uids = _ordered_unique([str(row.get("uid") or "") for row in ordered_rows])
    actor_ids = _ordered_unique([str(row.get("sender_actor_id") or "") for row in ordered_rows])
    thread_group_ids = _ordered_unique([str(row.get("thread_group_id") or "") for row in ordered_rows])
    primary_recurrence, recurrence_flags = _primary_recurrence(
        message_count=len(message_uids),
        actor_count=len(actor_ids),
        thread_count=len(thread_group_ids),
        target_actor_id=target_actor_id,
        sender_actor_ids=actor_ids,
        dated_rows=ordered_rows,
    )
    return {
        "cluster_id": f"{cluster_type}:{key}",
        "cluster_type": cluster_type,
        "key": key,
        "message_count": len(message_uids),
        "message_uids": message_uids,
        "actor_ids": actor_ids,
        "thread_group_ids": thread_group_ids,
        "first_date": str(ordered_rows[0].get("date") or "") if ordered_rows else "",
        "last_date": str(ordered_rows[-1].get("date") or "") if ordered_rows else "",
        "primary_recurrence": primary_recurrence,
        "recurrence_flags": recurrence_flags,
    }


def build_case_patterns(
    *,
    candidates: list[dict[str, Any]],
    target_actor_id: str = "",
) -> dict[str, Any]:
    """Aggregate BA6 message findings into conservative case-level pattern summaries."""
    behavior_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    taxonomy_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    thread_rows: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    directional_rows: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    all_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        message_findings = candidate.get("message_findings")
        if not isinstance(message_findings, dict):
            continue
        sender_actor_id = str(candidate.get("sender_actor_id") or "")
        thread_group_id = str(candidate.get("thread_group_id") or "")
        date = str(candidate.get("date") or "")
        uid = str(candidate.get("uid") or "")
        authored = message_findings.get("authored_text")
        if isinstance(authored, dict):
            for behavior_candidate in authored.get("behavior_candidates", []):
                if not isinstance(behavior_candidate, dict):
                    continue
                row = {
                    "uid": uid,
                    "date": date,
                    "sender_actor_id": sender_actor_id,
                    "thread_group_id": thread_group_id,
                    "behavior_id": str(behavior_candidate.get("behavior_id") or ""),
                    "confidence": str(behavior_candidate.get("confidence") or ""),
                }
                all_rows.append(row)
                behavior_rows[row["behavior_id"]].append(row)
                for taxonomy_id in behavior_candidate.get("taxonomy_ids", []):
                    taxonomy_rows[str(taxonomy_id)].append(row)
                if thread_group_id:
                    thread_rows[thread_group_id].append(row)
                if sender_actor_id and target_actor_id:
                    directional_rows[(sender_actor_id, target_actor_id)].append(row)

    behavior_summaries = [
        _pattern_summary(cluster_type="behavior", key=key, rows=rows, target_actor_id=target_actor_id)
        for key, rows in sorted(behavior_rows.items())
    ]
    taxonomy_summaries = [
        _pattern_summary(cluster_type="taxonomy", key=key, rows=rows, target_actor_id=target_actor_id)
        for key, rows in sorted(taxonomy_rows.items())
    ]
    thread_summaries = [
        _pattern_summary(cluster_type="thread", key=key, rows=rows, target_actor_id=target_actor_id)
        for key, rows in sorted(thread_rows.items())
    ]
    directional_summaries = []
    for (sender_actor_id, resolved_target_actor_id), rows in sorted(directional_rows.items()):
        behavior_counts = Counter(str(row.get("behavior_id") or "") for row in rows)
        directional_summaries.append(
            {
                "sender_actor_id": sender_actor_id,
                "target_actor_id": resolved_target_actor_id,
                "message_count": len(_ordered_unique([str(row.get("uid") or "") for row in rows])),
                "behavior_counts": dict(sorted(behavior_counts.items())),
                "message_uids": _ordered_unique([str(row.get("uid") or "") for row in rows]),
            }
        )

    cluster_index = [
        {
            "uid": str(row.get("uid") or ""),
            "behavior_id": str(row.get("behavior_id") or ""),
            "sender_actor_id": str(row.get("sender_actor_id") or ""),
            "thread_group_id": str(row.get("thread_group_id") or ""),
            "date": str(row.get("date") or ""),
        }
        for row in sorted(all_rows, key=lambda row: (_date_key(str(row.get("date") or "")), str(row.get("uid") or "")))
    ]
    recurrence_counts = Counter(summary["primary_recurrence"] for summary in [*behavior_summaries, *taxonomy_summaries])

    return {
        "version": CASE_PATTERN_VERSION,
        "summary": {
            "message_count_with_findings": len(_ordered_unique([str(row.get("uid") or "") for row in all_rows])),
            "behavior_cluster_count": len(behavior_summaries),
            "taxonomy_cluster_count": len(taxonomy_summaries),
            "thread_cluster_count": len(thread_summaries),
            "recurrence_counts": dict(sorted(recurrence_counts.items())),
        },
        "behavior_patterns": behavior_summaries,
        "taxonomy_patterns": taxonomy_summaries,
        "thread_patterns": thread_summaries,
        "directional_summaries": directional_summaries,
        "cluster_index": cluster_index,
    }
